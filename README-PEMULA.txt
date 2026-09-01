CLIPNOW AI — VERSI SIAP DIPASANG

PENTING:
Versi ini sudah mempunyai backend nyata untuk:
- upload video
- membaca durasi
- transkripsi memakai Faster-Whisper jika model tersedia
- mencari momen
- membuat 3 clip dengan FFmpeg
- burn subtitle dari transcript
- download MP4

CARA TERMUDAH DI KOMPUTER:
1. Install Python 3.11+
2. Install FFmpeg dan pastikan perintah "ffmpeg" bisa dipakai.
3. Buka folder backend.
4. Jalankan:
   python -m venv .venv
   .venv\Scripts\activate       (Windows)
   pip install -r requirements.txt
   uvicorn main:app --reload --port 8000
5. Buka frontend/index.html dengan browser.
6. Upload video dan klik Proses dengan AI.

CATATAN:
Faster-Whisper akan membutuhkan model saat pertama kali dipakai dan bisa cukup berat untuk PC/HP.
Untuk website publik/berbayar, jangan memakai file HTML sebagai pengaman Premium. Login, Owner, kuota, pembayaran, dan akses Premium harus diverifikasi di server.

UNTUK ONLINE:
Upload folder ini ke server yang bisa menjalankan Python + FFmpeg. Frontend dapat ditempatkan di hosting statis. Ubah API URL di localStorage:
localStorage.setItem('clipnow_api','https://ALAMAT-BACKEND-KAMU')
lalu refresh.

VERSI KOMERSIAL BERIKUTNYA:
- PostgreSQL
- Redis/Celery/RQ
- S3/R2
- Login JWT/session
- Stripe/Xendit/Midtrans
- Owner account
- FREE/PREMIUM quota server-side
- signed download URL
- rate limiting
- virus/file scanning
