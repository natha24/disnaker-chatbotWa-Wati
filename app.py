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
from knowledge import load_knowledge, get_knowledge_context, add_update  # Import modul knowledge

app = Flask(__name__)

# ===================== KONFIGURASI UTAMA =====================
WATI_API_ENDPOINT = os.getenv("WATI_API_ENDPOINT", "https://api.wati.io/v1")
WATI_API_TOKEN = os.getenv("WATI_API_TOKEN")
WATI_NUMBER = os.getenv("WATI_NUMBER")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ADMIN_PHONES = json.loads(os.getenv("ADMIN_PHONES", "[]"))
MAPS_LOCATION = os.getenv("MAPS_LOCATION", "https://maps.app.goo.gl/XXXXX")
OFFICIAL_DOMAINS = json.loads(os.getenv("OFFICIAL_DOMAINS", "[\"kemnaker.go.id\", \"transmigrasi.go.id\", \"kemenperin.go.id\", \"disnakertransperin.bartimkab.go.id\"]"))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Muat basis data pengetahuan
knowledge_db = load_knowledge()

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
    'jam buka', 'alamat', 'lokasi', 'kantor', 'dinas', 'bartim', 'barito timur',
    'siapkerja'
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

def is_gratitude(message):
    """Deteksi ucapan terima kasih"""
    gratitudes = [
        'terima kasih', 'thanks', 'makasih', 'tengkyu', 'thx',
        'sangat membantu', 'membantu sekali', 'terimakasih'
    ]
    return any(gratitude in message.lower() for gratitude in gratitudes)

def generate_gratitude_response():
    """Buat respons untuk ucapan terima kasih"""
    responses = [
        "Sama-sama! 😊 Senang bisa membantu. Jika ada pertanyaan lain, silakan bertanya ya!",
        "Terima kasih kembali! 🙏 Jangan ragu hubungi kami jika butuh bantuan lebih lanjut",
        "Dengan senang hati! 😊 Semoga informasinya bermanfaat untuk Anda"
    ]
    return random.choice(responses)

def is_conversational(message):
    """Deteksi pesan percakapan umum yang wajar"""
    conversational = [
        'baik', 'kabar', 'apa kabar', 'bagaimana', 'siapa', 'kenapa',
        'bisa bantu', 'tolong', 'permisi', 'mohon bantuan'
    ]
    return any(term in message.lower() for term in conversational)

# ===================== FUNGSI PENCARIAN INFORMASI RESMI =====================
def is_question_requires_web_search(question):
    """Deteksi apakah pertanyaan memerlukan pencarian web"""
    web_triggers = [
        'lokasi', 'alamat', 'tempat', 'peta', 'maps',
        'sharelock', 'bagikan lokasi', 'bagikan alamat',
        'hubungan industrial', 'pemecatan', 'phk', 'pesangon',
        'prosedur', 'tatacara', 'syarat', 'proses', 'ketentuan',
        'aturan', 'pasal', 'uu', 'undang-undang', 'peraturan'
    ]
    return any(trigger in question.lower() for trigger in web_triggers)

def perform_official_web_search(query):
    """Lakukan pencarian web dengan prioritas situs resmi"""
    if not os.getenv("WEB_SEARCH_API_KEY"):
        logger.error("API key pencarian web tidak tersedia")
        return None
        
    try:
        # Konfigurasi pencarian dengan fokus pada domain resmi
        params = {
            'q': f"{query}",
            'api_key': os.getenv("WEB_SEARCH_API_KEY"),
            'engine': 'google',
            'num': 5,  # Ambil lebih banyak hasil untuk seleksi
            'hl': 'id',
            'gl': 'id'  # Hasil dari Indonesia
        }
        
        # Filter domain resmi
        official_sites = " OR ".join([f"site:{domain}" for domain in OFFICIAL_DOMAINS])
        params['q'] += f" ({official_sites})"
        
        response = requests.get('https://serpapi.com/search', params=params, timeout=15)
        results = response.json()
        
        if 'organic_results' in results and results['organic_results']:
            # Prioritaskan hasil dari domain resmi
            official_results = [
                r for r in results['organic_results'] 
                if any(domain in r.get('link', '') for domain in OFFICIAL_DOMAINS)
            ]
            
            # Jika ada hasil resmi, kembalikan yang teratas
            if official_results:
                return official_results[0]
            
            # Jika tidak ada, kembalikan hasil organik teratas
            return results['organic_results'][0]
            
    except Exception as e:
        logger.error(f"Web search error: {str(e)}")
        
    return None

def extract_location_info():
    """Info lokasi standar untuk respons cepat"""
    return (
        "Kantor DISNAKERTRANSPERIN Bartim:\n"
        "📍 *Lokasi*: Jl. Tjilik Riwut KM 5, Tamiang Layang\n"
        "🗓️ *Jam Pelayanan*: Senin-Kamis 08.00-14.00 WIB | Jumat 08.00-11.00 WIB\n"
        "📞 *Telepon*: 0538-1234567\n"
        f"🗺️ *Peta*: {MAPS_LOCATION}"
    )

def handle_industrial_relations(question):
    """Penanganan khusus masalah hubungan industrial"""
    # Cari informasi prosedur mediasi
    web_result = perform_official_web_search("prosedur mediasi hubungan industrial")
    
    response = (
        "Untuk masalah hubungan industrial seperti pemutusan hubungan kerja (PHK), "
        "DISNAKERTRANSPERIN Bartim menyediakan layanan mediasi. Berikut langkah-langkahnya:\n\n"
        "1. Datang ke kantor dengan membawa dokumen pendukung (surat peringatan, kontrak kerja, dll)\n"
        "2. Isi formulir pengaduan\n"
        "3. Tim mediasi akan memproses dalam 7 hari kerja\n"
        "4. Mediasi akan dilaksanakan dengan melibatkan kedua belah pihak\n\n"
    )
    
    if web_result:
        response += (
            f"Info lebih detail: {web_result.get('link', '')}\n\n"
        )
    
    response += (
        "Kami sarankan Anda segera datang ke kantor untuk konsultasi langsung. "
        f"{extract_location_info()}"
    )
    
    return response

def handle_siapkerja_inquiry():
    """Penanganan khusus untuk pertanyaan tentang SIAPkerja"""
    # Pertama cek di basis data pengetahuan
    siapkerja_knowledge = get_knowledge_context("SIAPkerja", knowledge_db)
    if siapkerja_knowledge:
        return siapkerja_knowledge
    
    # Jika tidak ada di basis data, lakukan pencarian
    web_result = perform_official_web_search("aplikasi SIAPkerja")
    
    response = (
        "SIAPkerja adalah platform digital layanan publik di bidang ketenagakerjaan yang dikembangkan Kemnaker RI. Berikut info dasar:\n\n"
        "- Fungsi: Memudahkan akses layanan ketenagakerjaan\n"
        "- Fitur: Info lowongan, pelatihan, pengaduan, dll\n"
        "- Satu data untuk semua layanan\n\n"
        "Cara instal:\n"
        "1. Kunjungi situs resmi Kemnaker: https://www.kemnaker.go.id\n"
        "2. Cari menu SIAPkerja\n"
        "3. Download aplikasi atau akses versi web\n\n"
        "Cara daftar akun:\n"
        "1. Akses platform SIAPkerja\n"
        "2. Klik 'Daftar Sekarang'\n"
        "3. Isi NIK, nama lengkap, dan nama ibu kandung\n"
        "4. Gunakan email dan nomor handphone aktif\n"
        "5. Lengkapi profil\n"
    )
    
    if web_result:
        response += f"\nInfo lebih lanjut: {web_result.get('link', '')}"
    
    return response

# ===================== FUNGSI UTAMA GENERASI RESPONS =====================
def generate_ai_response(user_message, from_number):
    """Generasi respons AI dengan integrasi pengetahuan dan web search"""
    user_message_lower = user_message.lower()
    
    # 1. Tangani sapaan
    if is_greeting(user_message_lower):
        return generate_greeting_response()
    
    # 2. Tangani ucapan terima kasih
    if is_gratitude(user_message_lower):
        return generate_gratitude_response()
    
    # 3. Periksa perintah admin khusus
    if from_number in ADMIN_PHONES and user_message.startswith("/update "):
        new_info = user_message.replace("/update ", "")
        return add_update(new_info, knowledge_db)
    
    # 4. Cek dalam basis data pengetahuan
    knowledge_response = get_knowledge_context(user_message, knowledge_db)
    if knowledge_response:
        return knowledge_response
    
    # 5. Tangani permintaan tentang SIAPkerja
    if "siapkerja" in user_message_lower:
        return handle_siapkerja_inquiry()
    
    # 6. Tangani permintaan lokasi khusus
    if "lokasi" in user_message_lower or "alamat" in user_message_lower or "maps" in user_message_lower:
        return extract_location_info()
    
    # 7. Tangani permintaan share location
    if "sharelock" in user_message_lower or "bagikan lokasi" in user_message_lower:
        return (
            f"{extract_location_info()}\n\n"
            "Silakan klik link peta di atas untuk petunjuk arah."
        )
    
    # 8. Tangani masalah hubungan industrial
    industrial_keywords = ['phk', 'pemecatan', 'pesangon', 'hubungan industrial', 'sengketa kerja']
    if any(kw in user_message_lower for kw in industrial_keywords):
        return handle_industrial_relations(user_message)
    
    # 9. Cek apakah perlu pencarian web untuk info terkini
    if is_question_requires_web_search(user_message):
        web_result = perform_official_web_search(user_message)
        if web_result:
            response = (
                f"🔍 Berdasarkan informasi resmi:\n"
                f"*{web_result.get('title', 'Info terkait')}*\n"
                f"{web_result.get('snippet', '')}\n\n"
                f"📚 Sumber: {web_result.get('link', '')}\n\n"
                "Info dapat berubah, silakan konfirmasi ke 0538-1234567 untuk verifikasi."
            )
            return response
    
    # 10. Gunakan Groq AI sebagai fallback
    return generate_groq_response(user_message)

def generate_groq_response(user_message):
    """Menggunakan Groq API untuk merespons dengan konteks dinas ketenagakerjaan"""
    if not GROQ_API_KEY:
        return "Maaf, layanan AI sedang dalam pemeliharaan"
    
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Siapkan prompt yang menginstruksikan AI untuk merujuk ke sumber resmi
    system_prompt = (
        "Anda adalah asisten virtual Dinas Tenaga Kerja, Transmigrasi, dan Perindustrian Barito Timur (DISNAKERTRANSPERIN). "
        "Anda HANYA boleh memberikan informasi yang akurat dan terkini seputar ketenagakerjaan, transmigrasi, dan perindustrian. "
        "Gunakan bahasa Indonesia yang formal namun ramah. Jika Anda tidak yakin dengan jawaban, sarankan pengguna menghubungi kantor dinas.\n\n"
        "Referensi utama:\n"
        "- UU Ketenagakerjaan\n"
        "- Situs resmi Kemnaker (kemnaker.go.id)\n"
        "- Situs resmi Kementerian Transmigrasi (transmigrasi.go.id)\n"
        "- Situs resmi DISNAKERTRANSPERIN Bartim\n"
        "- Peraturan daerah terkait\n\n"
        "Contoh jawaban yang baik:\n"
        "Pertanyaan: 'Apa syarat membuat kartu kuning?'\n"
        "Jawaban: 'Berdasarkan Peraturan Menteri Ketenagakerjaan No. 9 Tahun 2020, syarat pembuatan kartu kuning adalah: ...'"
    )
    
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "model": "llama3-70b-8192",
        "temperature": 0.3,
        "max_tokens": 500,
        "stream": False
    }
    
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            return data['choices'][0]['message']['content']
        else:
            logger.error(f"Groq API error: {response.status_code} - {response.text}")
            return "Maaf, terjadi kesalahan saat memproses permintaan Anda."
            
    except Exception as e:
        logger.error(f"Groq API exception: {str(e)}")
        return "Maaf, layanan AI sedang sibuk. Silakan coba lagi nanti."

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
