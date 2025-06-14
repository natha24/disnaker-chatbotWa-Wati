import os
import json
import logging
import re
import random
import time
import uuid
import requests
from flask import Flask, request, jsonify
from datetime import datetime, timezone
import pytz
from queue import PriorityQueue
from threading import Thread

app = Flask(__name__)

# ===================== KONFIGURASI UTAMA =====================
WATI_API_ENDPOINT = os.getenv("WATI_API_ENDPOINT", "https://api.wati.io/v1")
WATI_API_TOKEN = os.getenv("WATI_API_TOKEN")
WATI_NUMBER = os.getenv("WATI_NUMBER")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ADMIN_PHONES = json.loads(os.getenv("ADMIN_PHONES", "[]"))
MAPS_LOCATION = os.getenv("MAPS_LOCATION", "https://maps.app.goo.gl/XXXXX")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ===================== FUNGSI UTILITAS ZONA WAKTU =====================
def get_wib_time():
    """Dapatkan waktu saat ini di zona WIB (Asia/Jakarta)"""
    utc_now = datetime.now(timezone.utc)
    wib_tz = pytz.timezone('Asia/Jakarta')
    return utc_now.astimezone(wib_tz)

# ===================== KONFIGURASI DOMAIN =====================
DOMAIN_KEYWORDS = [
    'disnaker', 'tenaga kerja', 'transmigrasi', 'perindustrian',
    'kartu kuning', 'ak1', 'pelatihan', 'lowongan', 'industri',
    'kerja', 'pencari kerja', 'phk', 'pemecatan', 'pesangon', 
    'hubungan industrial', 'mediasi', 'sengketa', 'bpjs ketenagakerjaan',
    'cari kerja', 'bursa kerja', 'transmigran', 'pelayanan', 'syarat',
    'jam buka', 'alamat', 'lokasi', 'kantor', 'dinas', 'bartim', 'barito timur'
]

# ===================== FUNGSI UTILITAS PERCAKAPAN =====================
def is_greeting(message):
    """Deteksi pesan sapaan atau pembuka percakapan"""
    greetings = [
        'halo', 'hai', 'hi', 'pagi', 'siang', 'sore', 'malam',
        'selamat pagi', 'selamat siang', 'selamat sore', 'selamat malam',
        'assalamualaikum', 'salam', 'hey', 'helo'
    ]
    return any(greeting in message.lower() for greeting in greetings)

def generate_greeting_response():
    """Buat respons sapaan yang ramah dan natural"""
    wib_now = get_wib_time()
    current_hour = wib_now.hour
    
    if 5 <= current_hour < 11:
        time_of_day = "pagi"
    elif 11 <= current_hour < 15:
        time_of_day = "siang"
    elif 15 <= current_hour < 19:
        time_of_day = "sore"
    else:
        time_of_day = "malam"
    
    greetings = [
        f"Halo! Selamat {time_of_day} 😊 Ada yang bisa saya bantu seputar DISNAKERTRANSPERIN Bartim?",
        f"Selamat {time_of_day}! 🙏 Saya siap membantu Anda dengan informasi seputar ketenagakerjaan dan perindustrian Bartim",
        f"Hai! Selamat {time_of_day} 😊 DISNAKERTRANSPERIN Bartim siap membantu"
    ]
    
    return random.choice(greetings)

# ... [Fungsi lainnya dari implementasi sebelumnya] ...

# ===================== INTEGRASI WATI API =====================
def send_wati_message(to, message_body):
    """Kirim pesan melalui API WATI"""
    headers = {
        "Authorization": f"Bearer {WATI_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "recipientPhoneNumber": to,
        "messageText": message_body
    }
    
    try:
        response = requests.post(
            f"{WATI_API_ENDPOINT}/sendTemplateMessage",
            json=payload,
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            logger.info(f"Pesan terkirim ke {to} via WATI")
            return True
        else:
            logger.error(f"WATI API error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"WATI API exception: {str(e)}")
        return False

# ===================== SISTEM ANTRIAN PESAN =====================
message_queue = PriorityQueue()
SEND_RETRY_DELAY = 10  # Lebih pendek dari Twilio

def message_sender_worker():
    """Worker untuk mengirim pesan dengan WATI"""
    while True:
        try:
            priority, message_data = message_queue.get()
            to = message_data['to']
            message_body = message_data['body']
            attempt = message_data.get('attempt', 0)
            message_id = message_data.get('id', str(uuid.uuid4()))
            
            if attempt > 3:
                logger.error(f"Gagal mengirim pesan {message_id} setelah 3 percobaan")
                message_queue.task_done()
                continue
                
            success = send_wati_message(to, message_body)
            
            if not success:
                logger.warning(f"Percobaan ke-{attempt+1} gagal, mencoba lagi dalam {SEND_RETRY_DELAY} detik")
                message_data['attempt'] = attempt + 1
                message_queue.put((priority + 1, message_data))  # Tingkatkan prioritas
                time.sleep(SEND_RETRY_DELAY)
            else:
                logger.info(f"Pesan {message_id} terkirim ke {to}")
                
            message_queue.task_done()
        except Exception as e:
            logger.error(f"Worker error: {str(e)}")
            time.sleep(5)

# Mulai worker thread
sender_thread = Thread(target=message_sender_worker, daemon=True)
sender_thread.start()

# ===================== ENDPOINT UTAMA =====================
@app.route('/webhook', methods=['POST'])
def webhook():
    """Endpoint utama untuk webhook WATI"""
    try:
        data = request.json
        event_type = data.get('eventType', '')
        
        # Hanya tangani event message
        if event_type != 'message':
            return jsonify({"status": "ignored"}), 200
        
        payload = data.get('payload', {})
        incoming_msg = payload.get('text', '').strip()
        from_number = payload.get('from', '').strip()
        
        if not incoming_msg or not from_number:
            return jsonify({"error": "Invalid payload"}), 400
        
        logger.info(f"Pesan masuk dari {from_number}: {incoming_msg}")
        
        # Process message
        bot_response = generate_ai_response(incoming_msg, from_number)
        
        # Masukkan ke antrian pengiriman (prioritas tinggi)
        message_data = {
            'id': str(uuid.uuid4()),
            'to': from_number,
            'body': bot_response,
            'attempt': 0
        }
        message_queue.put((1, message_data))  # Prioritas tinggi
        logger.info(f"Pesan dimasukkan ke antrian: {message_data['id']}")
        
        return jsonify({"status": "processed"}), 200
    
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"Starting DISNAKER Chatbot on port {port}")
    app.run(host='0.0.0.0', port=port)
