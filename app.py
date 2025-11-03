from flask import Flask, request, jsonify
from telethon import TelegramClient
from telethon.sessions import StringSession
import asyncio
import os

app = Flask(__name__)

# Твои API данные
API_ID = '9348118'
API_HASH = 'b6e1802b599d8f4fb8716fcd912f20f2'

active_clients = {}

async def create_telegram_client(phone, code):
    try:
        client = TelegramClient(StringSession(), int(API_ID), API_HASH)
        await client.connect()
        
        await client.sign_in(phone=phone, code=code)
        
        session_string = client.session.save()
        active_clients[phone] = {
            'client': client,
            'session': session_string
        }
        
        me = await client.get_me()
        return {
            'status': 'success',
            'user': {
                'id': me.id,
                'first_name': me.first_name,
                'username': me.username,
                'phone': me.phone
            },
            'session': session_string
        }
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

@app.route('/telegram-login', methods=['POST'])
def telegram_login():
    try:
        data = request.json
        phone = data.get('phone')
        code = data.get('code')
        
        if not phone or not code:
            return jsonify({'status': 'error', 'message': 'Phone and code required'})
        
        result = run_async(create_telegram_client(phone, code))
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'message': 'Server is running'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)