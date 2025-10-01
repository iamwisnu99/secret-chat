# 🎵 Spotify Telegram Bot  

Bot Telegram ini menghubungkan **Spotify API** dengan **Telegram Bot** untuk mencari, mengunduh, dan mengirim lagu lengkap dengan metadata.  
Selain itu, bot juga memiliki fitur **pesan rahasia**, **relay pesan**, dan **quiz interaktif** untuk Target User.  

---

## 🚀 Fitur Utama
- 🔎 Cari lagu di **Spotify** lalu unduh audio via **YouTube** (`yt-dlp`).
- 🎶 Otomatis menambahkan **metadata & cover art** ke file MP3.
- 💌 Relay pesan rahasia antara **Admin** dan **Target User**.
- 🎂 Fitur **pengingat ulang tahun** dengan foto & pesan spesial.
- ❓ **Quiz harian** dengan notifikasi jawaban ke Admin.

---

## 📦 Instalasi

1. **Clone repository**
   ```bash
   git clone https://github.com/username/repo-name.git
   cd repo-name
   ```

2. **Buat virtual environment (opsional tapi direkomendasikan)**
   ```bash
   python -m venv venv
   source venv/bin/activate   # Linux/Mac
   venv\Scripts\activate      # Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

---

## ⚙️ Konfigurasi

1. Ubah nama file `config.env` menjadi **`.env`**  
   ```bash
   mv config.env .env
   ```

2. Isi file `config.env` dengan kredensial kamu lalu ubah file ke   `.env` :

   ```env
   # ------ Spotify Credentials ------
   SPOTIPY_CLIENT_ID="YOUR_SPOTIFY_CLIENT_ID"
   SPOTIPY_CLIENT_SECRET="YOUR_SPOTIFY_CLIENT_SECRET"

   # ------ Telegram Credentials ------
   BOT_TOKEN="YOUR_TELEGRAM_TOKEN_BOT"
   ADMIN_CHAT_ID="YOUR_CHAT_ID_TELEGRAM"
   TARGET_CHAT_ID="TARGET_ID_TELEGRAM"
   ```

   - `SPOTIPY_CLIENT_ID` dan `SPOTIPY_CLIENT_SECRET` bisa didapatkan dari [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/).  
   - `BOT_TOKEN` bisa didapat dari [BotFather](https://t.me/botfather) di Telegram.  
   - `ADMIN_CHAT_ID` = Chat ID kamu (Admin). Bisa dicek dengan mengirim `/start` ke bot.  
   - `TARGET_CHAT_ID` = Chat ID target user (orang yang jadi tujuan bot).  

---

## ▶️ Cara Menjalankan

Jalankan bot dengan perintah berikut:

```bash
python server.py
```

Jika berhasil, bot akan aktif dan menunggu perintah di Telegram.  

---

## 📖 Cara Penggunaan

- `/start` → Menampilkan pesan selamat datang & Chat ID.  
- `/get Artist - Song Title` → Mendapatkan lagu lengkap dengan metadata.  
- `/love Pesan Rahasia` → (Hanya Admin) mengirim pesan ke Target User.  
- `/send Pesan` → (Hanya Target) mengirim pesan ke Admin.  
- `/addme` → (Hanya Target) setup ulang tahun & foto untuk dikirim otomatis.  

---

## 🛠️ Dependencies
Beberapa library utama yang digunakan:
- [python-telegram-bot](https://python-telegram-bot.org/)  
- [spotipy](https://spotipy.readthedocs.io/)  
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)  
- [mutagen](https://mutagen.readthedocs.io/)  
- [requests](https://docs.python-requests.org/)  
- [python-dotenv](https://saurabh-kumar.com/python-dotenv/)  

---

## 💡 Catatan
- Pastikan **Target User sudah pernah chat dengan bot**, jika tidak bot tidak bisa mengirim pesan ke target.  
- Bot akan otomatis menghapus file sementara setelah mengirim lagu.  
- Jalankan di **server/VPS/Heroku/Render** agar bot aktif 24/7.  

---

## 📜 Lisensi
Proyek ini dibuat untuk keperluan pribadi/eksperimen. Silakan gunakan & modifikasi sesuai kebutuhan.  
