import os
from dotenv import load_dotenv
import tempfile
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import yt_dlp
import requests
import mutagen
from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, TDRC, TRCK, TCON, TPE2, TCOM, TEXT
import telegram
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, PicklePersistence, ContextTypes
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputTextMessageContent, Update, constants
import asyncio
import logging
import random
from datetime import time, datetime

# Spotify ID
load_dotenv()

sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=os.getenv('SPOTIPY_CLIENT_ID'), 
    client_secret=os.getenv('SPOTIPY_CLIENT_SECRET')
))

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# ==============================================================================
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_CHAT_ID = int(os.getenv('ADMIN_CHAT_ID'))
TARGET_CHAT_ID = int(os.getenv('TARGET_CHAT_ID'))
MAX_MESSAGES_COUNT = 3 # Batas pesan dari target sebelum muncul prompt '/send'
# ==============================================================================
BIRTHDAY_STATE = 'birthday_state'
STATE_START = 0
STATE_WAITING_DATE = 1
STATE_WAITING_IMAGE = 2
STATE_DONE = 3

MESSAGE_COUNT_KEY = 'message_count'
STATE_KEY = 'state'
STATE_ACTIVE = 'ACTIVE' 
STATE_PROMPT_SEND = 'PROMPT_SEND' 

AUTO_RESPONSES = [
    (
        "Halo {full_name}, saat ini aku belum pesan rahasia untukmu, tunggu aku ya... ❤️\n\n"
        "*Tolong jangan hapus bot ini ya* 😊"
    ),
    (
        "Halo {full_name}, mohon maaf aku bukan manusia, "
        "aku hanya bot yang diperintahkan untuk meneruskan pesan rahasia untukmu (apabila ada) 😊\n\n"
        "*Tolong jangan hapus bot ini ya* 😊"
    ),
    (
        "Halo {full_name}, aku benar benar minta maaf, aku tidak bisa memberitahumu siapa yang "
        "mengirim pesan rahasia itu kepadamu, karena dia tidak ingin kamu mengetahuinya 😊\n\n"
        "*Tolong jangan hapus bot ini ya* 😊"
    )
]

# Pesan ketika batas reply tercapai (Instruksi)
LIMIT_REACHED_MESSAGE = (
    "Halo {full_name}, mohon maaf aku hanya bot, aku tidak bisa memberitahumu tapi kamu bisa mengirim pesan untuk Dia "
    "dengan ketik \"/send (isi pesan yang ingin kamu sampaikan)\" lalu kirim pada chat ini 😊\n\n"
    "*Contoh: /send aku suka cara kamu tertawa*"
)

# 🌟 LIST PERTANYAAN PEMANTIK RAHASIA 🌟
MYSTERY_QUESTIONS = [
    {
        "question": "Lebih suka menghabiskan malam minggu di mana?",
        "options": [
            {"text": "Di Rumah, rebahan dan nonton.", "data": "RUMAH"},
            {"text": "Di luar, mencari keramaian.", "data": "LUAR"}
        ]
    },
    {
        "question": "Kalau ada waktu luang, pilih mana?",
        "options": [
            {"text": "Baca buku / dengar podcast.", "data": "TENANG"},
            {"text": "Main game / olahraga.", "data": "AKTIF"}
        ]
    },
    {
        "question": "Menurutmu, aku orang yang lebih cenderung...",
        "options": [
            {"text": "Sangat serius.", "data": "SERIUS"},
            {"text": "Ceria dan santai.", "data": "SANTAI"}
        ]
    }
]

# Pesan konfirmasi setelah Target User menjawab
ANSWER_CONFIRMATION = "Terima kasih, jawabanmu sudah tercatat! Mungkin aku akan mengirimkan hal lain besok. 😉"

# -----------------------------------------------------------------------------------
async def search_and_send_song(update, context):
    """Mencari lagu di Spotify, mengunduh via yt_dlp, menanamkan metadata, dan mengirim audio."""

    # ⭐️ BARU: Notifikasi ke Admin (Anda/Wisnu) ⭐️
    user_full_name = update.effective_user.full_name
    query = " ".join(context.args)
    
    admin_notification = (
        f"📥 **TARGET ACTIVITY DETECTED**\n\n"
        f"**{user_full_name}** baru saja meminta lagu!\n"
        f"Lagu yang diminta: `{query}`"
    )
    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=admin_notification,
        parse_mode=telegram.constants.ParseMode.MARKDOWN
    )
    
    if update.effective_chat.id != TARGET_CHAT_ID:
        await update.message.reply_text("Maaf, command ini hanya untuk Target User.")
        return
        
    query = " ".join(context.args)
    if not query or ' - ' not in query:
        await update.message.reply_text(
            "❌ Format request salah. Silahkan ketik: `/get Artis - Judul Lagu` (Contoh: `/get Ava Max - So Am I`)",
            parse_mode=telegram.constants.ParseMode.MARKDOWN
        )
        return

    await context.bot.send_chat_action(TARGET_CHAT_ID, telegram.constants.ChatAction.UPLOAD_DOCUMENT)
    await update.message.reply_text("⏳ Oke, aku sedang mencari dan menyiapkan lagunya.\n\nMohon bersabar butuh waktu sekitar 1 menit.")

    # 1. Cari Metadata di Spotify
    try:
        results = sp.search(q=query, limit=1, type='track')
        tracks = results['tracks']['items']
    except Exception as e:
        logger.error(f"Spotify Search Error: {e}")
        await update.message.reply_text("Maaf, terjadi kesalahan saat mencari lagu di Spotify.")
        return

    if not tracks:
        await update.message.reply_text(f"Maaf, aku tidak menemukan lagu untuk query: `{query}`")
        return
        
    # --- Ekstraksi Metadata Spotify ---
    track = tracks[0]
    artist_name = track['artists'][0]['name']
    track_name = track['name']
    album_name = track['album']['name']
    cover_url = track['album']['images'][0]['url'] if track['album']['images'] else None
    release_date = track['album'].get('release_date', 'Unknown Year')[:4] # Ambil 4 karakter pertama (Tahun)
    track_number = track.get('track_number', 1)
    album_artist_name = artist_name
    genre_name = "Unknown" 
    try:
        # Panggil API Spotify lagi untuk mendapatkan detail artist (tempat genre berada)
        artist_info = sp.artist(track['artists'][0]['id'])
        # Ambil genre pertama, atau 'Pop' sebagai default jika list kosong
        genre_name = artist_info['genres'][0].title() if artist_info['genres'] else "Pop" 
    except Exception as e:
        logger.warning(f"Gagal mengambil genre dari Spotify Artist API: {e}")
        genre_name = "Pop"
    temp_file_path = None
    try:
        # Gunakan NamedTemporaryFile untuk memastikan file dihapus setelah digunakan
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
            temp_file_path = temp_file.name 
        
        yt_search_query = f"ytsearch1:{artist_name} - {track_name} official audio"
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': temp_file_path.rsplit('.', 1)[0], # Hapus ekstensi agar yt-dlp menambahkannya sendiri
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '256',
            }],
            'quiet': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([yt_search_query])
            
        # Perbaiki nama file yang diunduh (yt-dlp akan menambahkan .mp3)
        final_mp3_path = temp_file_path.rsplit('.', 1)[0] + '.mp3'
        if not os.path.exists(final_mp3_path):
             raise FileNotFoundError("Gagal mengunduh file MP3.")
        
        # 3. Sisipkan Metadata (Mutagen)
        audio = ID3(final_mp3_path)
        audio.delete() # Hapus tag yang mungkin ada sebelumnya

        # Sisipkan tag
        audio['TIT2'] = TIT2(encoding=3, text=track_name)
        audio['TPE1'] = TPE1(encoding=3, text=artist_name)
        audio['TALB'] = TALB(encoding=3, text=album_name)
        audio['TDRC'] = TDRC(encoding=3, text=release_date)
        audio['TRCK'] = TRCK(encoding=3, text=f"{track_number}")
        audio['TCON'] = TCON(encoding=3, text=genre_name)
        audio['TPE2'] = TPE2(encoding=3, text=album_artist_name)
        # Sisipkan Cover Art
        if cover_url:
            cover_data = requests.get(cover_url).content
            audio['APIC'] = APIC(
                encoding=3,
                mime='image/jpeg',
                type=3, # 3 adalah tipe 'Front Cover'
                desc='Cover',
                data=cover_data
            )
        
        audio.save()

        # 4. Kirim Audio ke Target User (Bagian Caption)
        with open(final_mp3_path, 'rb') as audio_file:
            await context.bot.send_document(
                chat_id=TARGET_CHAT_ID,
                document=audio_file,
                caption=(
                    f"✅ **Berhasil!** Lagu `{track_name}`.\n"
                    f"**Album:** `{album_name}` ({release_date})\n" # 👈 Tambahkan Tahun
                    f"*Metadata lengkap dari Spotify terlampir.*"
                ),
                performer=artist_name,
                title=track_name,
                parse_mode=telegram.constants.ParseMode.MARKDOWN
            )


    except Exception as e:
        logger.error(f"Error dalam proses download/tagging/kirim: {e}")
        await context.bot.send_message(
            chat_id=TARGET_CHAT_ID,
            text="❌ Maaf, terjadi kesalahan saat memproses lagu. Coba lagi atau coba lagu lain."
        )

    finally:
        # 5. Cleanup (Hapus file sementara)
        if 'final_mp3_path' in locals() and os.path.exists(final_mp3_path):
            os.remove(final_mp3_path)
            logger.info(f"File sementara {final_mp3_path} berhasil dihapus.")
        elif temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)

async def album_search_and_send(update: Update, context):
    """
    Mencari dan mengirim semua lagu dari sebuah album berdasarkan query teks atau link Spotify.
    """
    if update.effective_chat.id != TARGET_CHAT_ID:
        return

    query_parts = context.args
    if not query_parts:
        await update.message.reply_text(
            "Format salah. Gunakan:\n"
            "`/album Spotify - Nama Album - Nama Artis`\n"
            "ATAU\n"
            "`/album [link album Spotify]`",
            parse_mode=constants.ParseMode.MARKDOWN
        )
        return

    query = ' '.join(query_parts)
    await update.message.reply_text(f"🔍 Oke, aku sedang mencari album untuk **{query}**. Ini mungkin memakan waktu sebentar ya...", parse_mode=constants.ParseMode.MARKDOWN)

    album_uri = None
    
    # Cek apakah input adalah link album Spotify
    if "open.spotify.com/album/" in query:
        try:
            # Mengambil URI dari link
            album_uri = query.split('album/')[-1].split('?')[0]
            # Pastikan format URI yang benar untuk Spotipy
            if ":" not in album_uri:
                album_uri = "spotify:album:" + album_uri
        except Exception:
            album_uri = None
    
    # Jika bukan link, coba cari album
    if not album_uri:
        try:
            results = sp.search(q=query, limit=1, type='album')
            if results and results['albums']['items']:
                album_uri = results['albums']['items'][0]['uri']
            else:
                await update.message.reply_text("❌ Maaf, album tersebut tidak ditemukan di Spotify.")
                return
        except Exception as e:
            logger.error(f"Spotify album search error: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan saat mencari album di Spotify.")
            return

    # Ambil detail album
    try:
        album_info = sp.album(album_uri)
    except Exception as e:
        logger.error(f"Spotify album info error: {e}")
        await update.message.reply_text("❌ Tidak dapat mengambil detail album.")
        return
    
    album_name = album_info['name']
    album_artist = album_info['artists'][0]['name']
    album_year = album_info['release_date'].split('-')[0]
    album_cover_url = album_info['images'][0]['url'] if album_info['images'] else None
    
    await update.message.reply_text(
        f"✅ Album **{album_name}** oleh **{album_artist}** ditemukan! Mengirim **{len(album_info['tracks']['items'])}** lagu...",
        parse_mode=constants.ParseMode.MARKDOWN
    )

    # LOOPING UNTUK MENGUNDUH DAN MENGIRIM SETIAP LAGU
    for i, track in enumerate(album_info['tracks']['items']):
        # --- Definisikan nilai default agar variabel selalu ada di scope ---
        track_title = "Unknown Title"
        track_artist = "Unknown Artist"
        
        try:
            # 1. Ekstraksi Data dari Spotify (DIBUNGKUS TRY)
            track_title = track.get('name', 'Unknown Title')
            
            # Cek keamanan list artis sebelum diakses
            if track.get('artists') and track['artists']:
                track_artist = track['artists'][0]['name']
            else:
                track_artist = album_artist # Gunakan nama album artist sebagai default

            track_number = track['track_number']
            
            # 2. Buat query pencarian YouTube yang optimal
            yt_query = f"{track_artist} - {track_title} official audio"
            
            # 3. Panggil fungsi unduhan dan kirim
            await download_album_track(
                update, 
                context, 
                yt_query, 
                album_name, 
                album_artist, 
                album_year, 
                album_cover_url, 
                track_title, 
                track_number,
                track_artist
            )
            
        except Exception as e:
            # ⭐️ LOGGING AMAN: Karena track_title dan track_artist sudah diinisialisasi ⭐️
            logger.error(f"Gagal memproses track {track_artist} - {track_title}: {e}")
            await update.message.reply_text(
                f"❌ Maaf, gagal memproses lagu **{track_title}** dari **{track_artist}**.", 
                parse_mode=constants.ParseMode.MARKDOWN
            )
            
        # Beri jeda sejenak untuk menghindari rate limit Telegram
        await asyncio.sleep(1)

    # Pesan Selesai
    await update.message.reply_text(
        f"🥳 Selesai! Semua lagu dari album **{album_name}** sudah terkirim. Selamat Mendengarkan!", 
        parse_mode=constants.ParseMode.MARKDOWN
    )
async def download_album_track(update, context, yt_query, album_name, album_artist, album_year, album_cover_url, track_title, track_number, track_artist):
    """
    Fungsi pembantu untuk mengunduh, menambahkan metadata, dan mengirim satu lagu album.
    """
    final_filename = None # Inisialisasi variabel di luar try
    temp_dir = tempfile.mkdtemp()

    try:
        # 1. Unduh dan Ganti Nama File
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'}],
            'outtmpl': os.path.join(temp_dir, f"{track_artist} - {track_title}.%(ext)s"),
            'quiet': True,
            'nocheckcertificate': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(f"ytsearch:{yt_query}", download=True)
            # Pastikan nama file adalah .mp3
            final_filename = ydl.prepare_filename(info_dict['entries'][0]).rsplit('.', 1)[0] + '.mp3'

        # 2. Tagging Metadata (Menggunakan Mutagen) - TIDAK BERUBAH
        audio = ID3()

        # Tag Dasar
        audio['TIT2'] = TIT2(encoding=3, text=track_title)
        audio['TPE1'] = TPE1(encoding=3, text=track_artist)
        # Tag Album (Baru)
        audio['TALB'] = TALB(encoding=3, text=album_name)
        audio['TDRC'] = TDRC(encoding=3, text=album_year)
        audio['TRCK'] = TRCK(encoding=3, text=str(track_number))
        audio['TPE2'] = TPE2(encoding=3, text=album_artist)

        # 3. Download dan Embed Album Art - TIDAK BERUBAH
        if album_cover_url:
            try:
                image_response = requests.get(album_cover_url)
                audio['APIC'] = APIC(
                    encoding=3,
                    mime='image/jpeg',
                    type=3, # 3 = Cover Front
                    desc='Cover',
                    data=image_response.content
                )
            except Exception as e:
                logger.warning(f"Gagal mengunduh atau menanamkan cover: {e}")
        audio.save(final_filename)

        # 4. Kirim Audio sebagai DOKUMEN ke Telegram 
        caption = f"🎶 **{track_title}**\n👤 **{track_artist}**\n💿 *{album_name} ({album_year})*"
        
        with open(final_filename, 'rb') as audio_file:
            await context.bot.send_document( 
                chat_id=TARGET_CHAT_ID,
                document=audio_file,
                filename=os.path.basename(final_filename),
                caption=caption,
                parse_mode=constants.ParseMode.MARKDOWN
            )
            
    except Exception as e:
        raise e 
        
    finally:
        if final_filename and os.path.exists(final_filename):
            try:
                os.remove(final_filename)
                logger.info(f"Cleanup: File {os.path.basename(final_filename)} dihapus.")
            except OSError as e:
                logger.error(f"Cleanup Error: Gagal menghapus file {final_filename}: {e}")
                
        if os.path.exists(temp_dir):
            try:
                os.rmdir(temp_dir)
            except OSError as e:
                 logger.error(f"Cleanup Error: Gagal menghapus direktori sementara {temp_dir}: {e}")

async def admin_send_love(update, context):
    """Mendengarkan command /love dari ADMIN_CHAT_ID dan mengirimkannya ke TARGET_CHAT_ID."""

    # 1. Pastikan pesan berasal dari Admin
    if update.effective_chat.id != ADMIN_CHAT_ID:
        await update.message.reply_text("Maaf, command ini hanya untuk Admin.")
        return

    if not context.args:
        await update.message.reply_text("❌ Pesan gagal dikirim. Silahkan ketik: /love (isi pesanmu)")
        return
        
    message_to_relay = " ".join(context.args)
    
    try:
        await context.bot.send_message(
            chat_id=TARGET_CHAT_ID,
            text=message_to_relay 
        )
        logger.info(f"Pesan dari Admin berhasil dikirim ke Target: {TARGET_CHAT_ID}")

        await update.message.reply_text(
            "✅ Pesan rahasia berhasil dikirim ke target! 💌"
        )
        
    except telegram.error.BadRequest as e:
        logger.error(f"Gagal me-relay pesan: {e}")
        await update.message.reply_text(
            "❌ Gagal mengirim pesan. Pastikan TARGET_CHAT_ID sudah benar dan target sudah pernah chat dengan bot."
        )

async def target_send_message(update, context):
    """Menerima command /send dari Target User dan meneruskannya ke Admin."""
    
    user_full_name = update.effective_user.full_name
    current_state = context.user_data.get(STATE_KEY, STATE_ACTIVE)
    
    message_to_forward = " ".join(context.args)

    if current_state != STATE_PROMPT_SEND:
        await update.message.reply_text(
            "Halo {full_name}, kamu belum bisa mengirim pesan. Coba kirim beberapa pesan biasa dulu ya... 😊".format(full_name=user_full_name)
        )
        return

    if not message_to_forward:
        await update.message.reply_text(
            "❌ Pesanmu kosong! Silahkan ketik: /send (isi pesan yang ingin kamu sampaikan)"
        )
        return

    forward_text = (
        f"📨 *Pesan Diteruskan dari Target:*\n\n"
        f"Dari: {user_full_name}\n"
        f"Pesan: {message_to_forward}"
    )
    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=forward_text,
            parse_mode=telegram.constants.ParseMode.MARKDOWN
        )

        await update.message.reply_text(
            "✅ Pesanmu sudah aku sampaikan! Jika ingin mengirim pesan lain, silahkan ketik /send (isi pesan) lagi. 😊",
            parse_mode=telegram.constants.ParseMode.MARKDOWN
        )
        
    except Exception as e:
            await update.message.reply_text(
            "❌ Gagal meneruskan pesan. Ada masalah teknis di bot."
        )

async def target_text_message(update, context):
    """Mengelola status, counter, dan auto-reply untuk pesan teks biasa dari Target User."""

    user_text = update.message.text
    user_id = update.effective_chat.id
    user_full_name = update.effective_user.full_name

    current_state = context.user_data.get(BIRTHDAY_STATE, STATE_START)

    if current_state == STATE_WAITING_DATE:
        try:
            modified_input = f"{user_text.strip()}/2000"
            bday_date = datetime.strptime(modified_input, '%d/%m/%Y')

            context.user_data['birthday_day'] = bday_date.day
            context.user_data['birthday_month'] = bday_date.month
            context.user_data[BIRTHDAY_STATE] = STATE_WAITING_IMAGE

            pesan = (
                f"Pertanyaan 2:\n"
                f"Apakah kamu ingin menambahkan gambar juga? Jika **Iya**, kirim gambar kamu ke chat ini, "
                f"yang ingin dikirim saat kamu ulang tahun. Jika **tidak**, balas pesan ini dengan `skip`."
            )
            await update.message.reply_text(pesan, parse_mode=constants.ParseMode.MARKDOWN)

        except ValueError:
            await update.message.reply_text(
                "❌ Format tanggal salah. Mohon kirim ulang dengan format `DD/MM` (misal: 15/09)."
            )
            
        return
    
    elif current_state == STATE_WAITING_IMAGE and user_text.lower() == 'skip':

        if 'birthday_photo_id' in context.user_data:
            del context.user_data['birthday_photo_id']
            
        await finish_birthday_setup(update, context)
        return

    if MESSAGE_COUNT_KEY not in context.user_data:
        context.user_data[MESSAGE_COUNT_KEY] = 0
        context.user_data[STATE_KEY] = STATE_ACTIVE
    
    current_state = context.user_data[STATE_KEY]
    current_count = context.user_data[MESSAGE_COUNT_KEY]

    if current_state == STATE_ACTIVE:

        current_count += 1
        context.user_data[MESSAGE_COUNT_KEY] = current_count
        logger.info(f"Target count: {current_count}")
        
        if current_count >= MAX_MESSAGES_COUNT:
            response_text = LIMIT_REACHED_MESSAGE.format(full_name=user_full_name)
            context.user_data[STATE_KEY] = STATE_PROMPT_SEND
            
        else:
            random_template = random.choice(AUTO_RESPONSES)
            response_text = random_template.format(full_name=user_full_name)

        await update.message.reply_text(
            response_text,
            parse_mode=telegram.constants.ParseMode.MARKDOWN
        )

    elif current_state == STATE_PROMPT_SEND:
        response_text = LIMIT_REACHED_MESSAGE.format(full_name=user_full_name)
        await update.message.reply_text(
            response_text,
            parse_mode=telegram.constants.ParseMode.MARKDOWN
        )

async def send_mystery_question(application: Application):
    """Memilih pertanyaan acak dan mengirimkannya ke TARGET_CHAT_ID dengan Inline Keyboard."""
    
    question_data = random.choice(MYSTERY_QUESTIONS)
    question = question_data["question"]
    options = question_data["options"]

    keyboard = []
    for opt in options:

        callback_data = f"QUIZ|{opt['data']}|{question}" 
        keyboard.append(InlineKeyboardButton(opt["text"], callback_data=callback_data))

    reply_markup = InlineKeyboardMarkup([keyboard])

    try:
        await application.bot.send_message(
            chat_id=TARGET_CHAT_ID,
            text=f"💌 **Pesan Rahasia Hari Ini**:\n{question}",
            reply_markup=reply_markup,
            parse_mode=telegram.constants.ParseMode.MARKDOWN
        )
        logger.info(f"Mystery Quiz dikirim ke Target: {TARGET_CHAT_ID}")

    except Exception as e:
        logger.error(f"Gagal mengirim Mystery Quiz: {e}")
        
async def handle_quiz_answer(update, context):
    """Menerima jawaban dari Target User (CallbackQuery), mengirim notifikasi ke Admin."""
    
    query = update.callback_query
    await query.answer()

    user_full_name = query.from_user.full_name
    
    try:
        command, answer_data, question_text = query.data.split('|', 2)
    except ValueError:
        logger.error(f"Callback data tidak sesuai format: {query.data}")
        await query.edit_message_text("Maaf, terjadi kesalahan pada data jawaban.")
        return

    admin_notification = (
        f"🔔 *Notifikasi Jawaban Rahasia*\n\n"
        f"Dari: {user_full_name}\n"
        f"Pertanyaan: {question_text}\n"
        f"Jawaban: **{answer_data}**"
    )

    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=admin_notification,
            parse_mode=telegram.constants.ParseMode.MARKDOWN
        )
        logger.info(f"Jawaban Quiz '{answer_data}' dari Target dikirim ke Admin.")
        
    except Exception as e:
        logger.error(f"Gagal mengirim notifikasi jawaban ke Admin: {e}")

    new_text = f"~~{question_text}~~ \n\n**Jawabanmu:** {answer_data}\n\n{ANSWER_CONFIRMATION}"
    await query.edit_message_text(
        text=new_text,
        parse_mode=telegram.constants.ParseMode.MARKDOWN
    )

async def start_addme(update: Update, context):

    if update.effective_chat.id != TARGET_CHAT_ID:
        return 

    user_full_name = update.effective_user.full_name
    context.user_data[BIRTHDAY_STATE] = STATE_START

    keyboard = [
        [
            InlineKeyboardButton("Ya", callback_data='BDAY_YES'),
            InlineKeyboardButton("Tidak", callback_data='BDAY_NO')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    pesan = (
        f"Hai {user_full_name}, kamu akan diberikan beberapa pertanyaan untuk "
        f"membantu bot ini bisa merayakan di hari ulang tahunmu. Apakah kamu siap?"
    )

    await update.message.reply_text(pesan, reply_markup=reply_markup)

async def handle_birthday_callback(update: Update, context):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_full_name = update.effective_user.full_name

    if data == 'BDAY_NO':
        pesan = "Baiklah, kalo kamu sudah siap cukup kirim pesan \"/addme\" di chat ini ya..."

        await query.edit_message_text(text=pesan)
        
    elif data == 'BDAY_YES':
        
        context.user_data[BIRTHDAY_STATE] = STATE_WAITING_DATE
        
        pesan = (
            f"Pertanyaan 1:\n"
            f"Bisa sebutkan Tanggal dan Bulan Lahir Kamu, {user_full_name}? "
            f"\n\n**Contoh Format:** `DD/MM` (misal: 15/09)" 

        )

        await query.edit_message_text(text=pesan, parse_mode=constants.ParseMode.MARKDOWN)

async def target_photo_message(update: Update, context):
    current_state = context.user_data.get(BIRTHDAY_STATE, STATE_START)
    
    if current_state == STATE_WAITING_IMAGE:
        photo_id = update.message.photo[-1].file_id 
        context.user_data['birthday_photo_id'] = photo_id
        
        await finish_birthday_setup(update, context)
        return

async def finish_birthday_setup(update: Update, context):
    user_full_name = update.effective_user.full_name
    bday_day = context.user_data.get('birthday_day')
    bday_month = context.user_data.get('birthday_month')
    bday_photo_id = context.user_data.get('birthday_photo_id')

    context.user_data[BIRTHDAY_STATE] = STATE_DONE
    
    pesan_sukses_target = (
        f"✅ Horee Berhasil, {user_full_name}! Nanti kamu akan mendapatkan pesan khusus "
        f"di hari ulang tahunmu yaa {chr(0x1F48C)} " 
    )

    await update.effective_message.reply_text(pesan_sukses_target)

    tanggal_ultah = f"{bday_day:02d}/{bday_month:02d}"
    status_foto = "✅ Ada Foto Tersimpan" if bday_photo_id else "❌ Tidak Ada Foto"
    
    admin_notification = (
        f"🔔 **[PEMBERITAHUAN] Data Ulang Tahun Disimpan!**\n\n"
        f"Target User ({user_full_name}) baru saja menyelesaikan pendaftaran ulang tahun.\n"
        f"-----------------------------------------\n"
        f"🎂 **Tanggal Ulang Tahun:** `{tanggal_ultah}`\n"
        f"🖼️ **Status Foto:** {status_foto}\n\n"
        f"Pesan spesial otomatis akan terkirim pada tanggal tersebut!"
    )
    
    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=admin_notification,
        parse_mode=constants.ParseMode.MARKDOWN
    )

    if bday_photo_id:
         await context.bot.send_photo(
            chat_id=ADMIN_CHAT_ID,
            photo=bday_photo_id,
            caption="Foto yang akan dikirim saat ulang tahun Target User."
        )

async def check_and_send_birthday_message(context: ContextTypes.DEFAULT_TYPE, update: Update):
    """Fungsi yang dijalankan setiap hari untuk mengecek siapa yang ulang tahun."""
    
    user_full_name = update.effective_user.full_name
    current_date = datetime.now()
    current_day = current_date.day
    current_month = current_date.month
    
    user_data = context.application.persistence.get_user_data().get(TARGET_CHAT_ID, {})
    
    bday_day = user_data.get('birthday_day')
    bday_month = user_data.get('birthday_month')
    bday_photo_id = user_data.get('birthday_photo_id')

    if bday_day == current_day and bday_month == current_month:
        
        user_full_name = update.effective_user.full_name
        
        pesan_ultah = (
            f"Happy birthday {user_full_name} {chr(0x1F3BA)}{chr(0x1F3C1)}! Sesuai dengan janjiku, "
            f"aku akan mengirim pesan khusus dihari ulang tahunmu 😊. "
            f"Semoga apa yang sedang kamu kerjakan diberikan kelancaran dan semoga rezekinya tidak berbelok arah yaa 😂. "
            f"Pokoknya happy birthday {chr(0x1F370)}"
        )

        if bday_photo_id:
            await context.bot.send_photo(
                chat_id=TARGET_CHAT_ID,
                photo=bday_photo_id,
                caption=pesan_ultah,
                parse_mode=constants.ParseMode.MARKDOWN
            )
        else:
            await context.bot.send_message(
                chat_id=TARGET_CHAT_ID,
                text=pesan_ultah,
                parse_mode=constants.ParseMode.MARKDOWN
            )
        
        logger.info(f"Pesan ulang tahun dikirimkan untuk {user_full_name}.")

def main():
    """Start the bot."""
    persistence = PicklePersistence(filepath='bot_persistence_data.pickle') 
    
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .persistence(persistence) 
        .build()
    )

    application.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text(
        f'Hai {u.effective_user.full_name}! 👋 Chat ID kamu adalah: {u.effective_chat.id}')))
    
    application.add_handler(CommandHandler("love", admin_send_love))
    
    application.add_handler(
        CommandHandler("send", target_send_message, filters=filters.Chat(TARGET_CHAT_ID))
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Chat(TARGET_CHAT_ID) & ~filters.COMMAND,
            target_text_message
        )
    )
    
    application.add_handler(
        CallbackQueryHandler(handle_quiz_answer, pattern='^QUIZ')
    )

    application.job_queue.run_daily(
        lambda context: context.application.create_task(send_mystery_question(context.application)),
        time=time(hour=3, minute=00), 
        days=(0, 1, 2, 3, 4, 5, 6),
        name='daily_mystery_quiz'
    )

    application.add_handler(
    CommandHandler("album", album_search_and_send, filters=filters.Chat(TARGET_CHAT_ID))
    )

    application.add_handler(
        CommandHandler("get", search_and_send_song, filters=filters.Chat(TARGET_CHAT_ID))
    )

    application.add_handler(
        CommandHandler("addme", start_addme, filters=filters.Chat(TARGET_CHAT_ID))
    )

    application.add_handler(
        CallbackQueryHandler(handle_birthday_callback, pattern='^BDAY')
    )

    application.add_handler(
        MessageHandler(filters.PHOTO & filters.Chat(TARGET_CHAT_ID), target_photo_message)
    )

    application.job_queue.run_daily(
        lambda context: context.application.create_task(check_and_send_birthday_message(context)),
        time=time(hour=3, minute=0),
        days=(0, 1, 2, 3, 4, 5, 6),
        name='daily_birthday_check'
    )

    logger.info("Bot sedang berjalan...")
    application.run_polling(timeout=15)
    logger.info("Bot berhenti.")

if __name__ == '__main__': 
    main()
