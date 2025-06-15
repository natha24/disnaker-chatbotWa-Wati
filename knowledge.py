import json
import os
import re
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# File untuk menyimpan basis data pengetahuan
KNOWLEDGE_FILE = os.getenv("KNOWLEDGE_FILE", "knowledge_db.json")

def load_knowledge():
    """Memuat basis data pengetahuan dari file JSON"""
    knowledge_db = {}
    if os.path.exists(KNOWLEDGE_FILE):
        try:
            with open(KNOWLEDGE_FILE, 'r', encoding='utf-8') as f:
                knowledge_db = json.load(f)
            logger.info(f"Basis data pengetahuan berhasil dimuat dari {KNOWLEDGE_FILE}")
        except Exception as e:
            logger.error(f"Gagal memuat basis data: {str(e)}")
            knowledge_db = initialize_default_knowledge()
    else:
        knowledge_db = initialize_default_knowledge()
        save_knowledge(knowledge_db)
    return knowledge_db

def initialize_default_knowledge():
    """Inisialisasi basis data pengetahuan dengan data default"""
    logger.info("Menginisialisasi basis data pengetahuan default")
    return {
        "syarat_ak1": {
            "pertanyaan": ["syarat ak1", "persyaratan ak1", "dokumen ak1", "ak1"],
            "jawaban": "Syarat pembuatan AK1:\n1. Fotokopi KTP\n2. Pas foto 4x6 (2 lembar)\n3. Surat pengantar dari kelurahan\n4. Fotokopi kartu kuning (jika ada)",
            "sumber": "Peraturan Menteri Ketenagakerjaan No. 9 Tahun 2020",
            "terakhir_update": "2025-06-10"
        },
        "syarat_kartu_kuning": {
            "pertanyaan": ["syarat kartu kuning", "dokumen kartu kuning", "kartu kuning"],
            "jawaban": "Syarat pembuatan Kartu Kuning:\n1. Fotokopi KTP\n2. Pas foto 3x4 (2 lembar)\n3. Surat pengantar dari kelurahan\n4. Mengisi formulir pendaftaran",
            "sumber": "Peraturan Menteri Ketenagakerjaan No. 9 Tahun 2020",
            "terakhir_update": "2025-06-10"
        },
        "jam_operasional": {
            "pertanyaan": ["jam buka", "jam pelayanan", "waktu pelayanan"],
            "jawaban": "Jam pelayanan DISNAKERTRANSPERIN Bartim:\n- Senin-Kamis: 08.00-14.00 WIB\n- Jumat: 08.00-11.00 WIB",
            "sumber": "SK Kepala Dinas No. 123/2025",
            "terakhir_update": "2025-06-10"
        },
        "siapkerja": {
            "pertanyaan": ["siapkerja", "aplikasi siapkerja", "cara daftar siapkerja"],
            "jawaban": (
                "Aplikasi SIAPkerja adalah platform digital layanan ketenagakerjaan dari Kemnaker RI.\n\n"
                "Cara instal:\n"
                "1. Kunjungi https://www.kemnaker.go.id\n"
                "2. Cari menu 'SIAPkerja' di beranda\n"
                "3. Download aplikasi atau akses versi web\n\n"
                "Cara daftar akun:\n"
                "1. Akses platform SIAPkerja\n"
                "2. Klik 'Daftar Sekarang'\n"
                "3. Isi NIK, nama lengkap, dan nama ibu kandung\n"
                "4. Gunakan email dan nomor handphone aktif\n"
                "5. Lengkapi profil\n\n"
                "Syarat:\n"
                "- Memiliki NIK\n"
                "- Email aktif\n"
                "- Nomor handphone aktif"
            ),
            "sumber": "Panduan SIAPkerja Kemnaker 2025",
            "terakhir_update": "2025-06-10"
        }
    }

def save_knowledge(knowledge_db):
    """Menyimpan basis data pengetahuan ke file JSON"""
    try:
        with open(KNOWLEDGE_FILE, 'w', encoding='utf-8') as f:
            json.dump(knowledge_db, f, ensure_ascii=False, indent=2)
        logger.info(f"Basis data pengetahuan berhasil disimpan ke {KNOWLEDGE_FILE}")
        return True
    except Exception as e:
        logger.error(f"Gagal menyimpan basis data: {str(e)}")
        return False

def get_knowledge_context(question, knowledge_db):
    """Mencari jawaban dari basis data pengetahuan yang sesuai dengan pertanyaan"""
    question_lower = question.lower()
    for key, data in knowledge_db.items():
        for pattern in data['pertanyaan']:
            if re.search(r'\b' + re.escape(pattern.lower()) + r'\b', question_lower):
                return data['jawaban']
    return None

def add_update(new_info, knowledge_db):
    """Menambahkan atau memperbarui basis data pengetahuan dari input admin"""
    try:
        # Format yang diharapkan: 
        #   "keyword: pertanyaan1, pertanyaan2; jawaban"
        parts = new_info.split(';')
        if len(parts) < 2:
            return "Format salah. Gunakan: keyword: pertanyaan1, pertanyaan2; jawaban"
        
        keyword_part = parts[0].strip()
        jawaban = ';'.join(parts[1:]).strip()
        
        if ':' not in keyword_part:
            return "Format keyword salah. Gunakan: 'keyword: pertanyaan1, pertanyaan2'"
        
        keyword, pertanyaans = keyword_part.split(':', 1)
        keyword = keyword.strip()
        pertanyaan_list = [p.strip() for p in pertanyaans.split(',')]
        
        # Perbarui atau tambahkan entri baru
        knowledge_db[keyword] = {
            "pertanyaan": pertanyaan_list,
            "jawaban": jawaban,
            "sumber": "Admin DISNAKERTRANSPERIN",
            "terakhir_update": datetime.now().strftime("%Y-%m-%d")
        }
        
        save_knowledge(knowledge_db)
        return f"Pengetahuan '{keyword}' berhasil diperbarui"
    except Exception as e:
        return f"Error: {str(e)}"
