# Deploy SAHAM ke Server Linux

Panduan menjalankan SAHAM 24 jam di server Linux (VPS) beserta bot Telegram-nya. Di server, SAHAM berjalan
**tanpa jendela desktop**: engine yang sama menyajikan tampilan web, menjalankan scan otomatis, dan bot Telegram.

```
Telegram  ◄──(HTTPS keluar, long polling)──  SAHAM (Docker, port 8765 hanya lokal)  ──►  Yahoo Finance, berita, AI
                                                   ▲
Anda (browser) ──► SSH tunnel  atau  HTTPS (Caddy + login) ┘
```

Bot Telegram **tidak butuh port masuk** — server cukup bisa mengakses internet keluar.

---

## 0. Yang perlu disiapkan

| Kebutuhan | Rekomendasi |
|---|---|
| Server | VPS Ubuntu 22.04/24.04 atau Debian 12, 1–2 vCPU, RAM ≥ 2 GB, disk ≥ 10 GB |
| Akses | SSH sebagai user dengan `sudo` |
| Bot Telegram | Token dari @BotFather (dibuat di langkah 6) |
| AI (opsional) | Mode **API key** (Claude/OpenAI/9router). Login akun Anthropic hanya bisa di aplikasi desktop Windows |

> **Hanya satu instance SAHAM yang boleh menjalankan bot Telegram.** Jangan aktifkan bot di aplikasi desktop dan
> di server sekaligus (atau di dua server/container) — keduanya akan berebut pesan (pesan error "dipakai instance
> lain"). Setelah server jalan, matikan centang "Aktif" Telegram di desktop.

---

## 1. Siapkan server (sekali saja)

```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install ca-certificates curl ufw
# Docker resmi
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER      # lalu logout & login lagi
# Firewall: hanya SSH (dan 80/443 bila memakai domain di langkah 5B)
sudo ufw allow OpenSSH
sudo ufw enable
```

Cek: `docker --version` dan `docker compose version`.

---

## 2. Kirim kode dari komputer Windows ke server

Di **PowerShell** pada folder proyek (`D:\Henok\Projects\SAHAM`):

```powershell
tar --exclude=ui/node_modules --exclude=ui/dist --exclude=dist --exclude=build --exclude="*.db" --exclude="*.db-wal" --exclude="*.db-shm" --exclude=__pycache__ -czf saham-deploy.tgz engine ui deploy docs Dockerfile docker-compose.yml .dockerignore
scp saham-deploy.tgz USER@IP_SERVER:~
```

Di **server**:

```bash
mkdir -p ~/saham && tar -xzf ~/saham-deploy.tgz -C ~/saham && cd ~/saham
cp deploy/.env.example .env
nano .env        # isi SAHAM_BASIC_AUTH=user:sandi-panjang
chmod 600 .env
```

---

## 3. Build & jalankan

```bash
cd ~/saham
docker compose up -d --build       # build pertama ±3–6 menit
docker compose ps                  # STATUS harus "Up ... (healthy)" setelah ±1 menit
docker compose logs -f --tail=50   # lihat log; Ctrl+C untuk keluar (container tetap jalan)
```

Container otomatis hidup lagi setelah server reboot (`restart: unless-stopped`). Database dan cache yfinance
(`XDG_CACHE_HOME=/data/.cache`, sudah diset di image) tersimpan di volume `/data`, jadi tetap ada setelah rebuild.

---

## 4. (Opsional) Pindahkan data dari aplikasi desktop

Agar watchlist, pengaturan AI, riwayat prediksi & rekam jejak AI ikut pindah. **Tutup aplikasi desktop dulu.**

Windows (PowerShell): `scp "$env:APPDATA\SAHAM\saham.db" USER@IP_SERVER:~/saham/saham.db`

Server:

```bash
cd ~/saham
docker compose stop
docker compose cp saham.db saham:/data/saham.db
docker compose start
rm saham.db
```

---

## 5. Membuka SAHAM di browser

Port 8765 hanya terbuka di dalam server (aman). Pilih salah satu cara:

### 5A. SSH tunnel (paling aman, tanpa domain)

Di komputer Anda:

```bash
ssh -N -L 8765:127.0.0.1:8765 USER@IP_SERVER
```

Biarkan jendela itu terbuka, lalu buka **http://localhost:8765** di browser (login dengan `SAHAM_BASIC_AUTH`).

### 5B. Domain + HTTPS (bisa dibuka dari mana saja)

Arahkan DNS (A record) `saham.domainanda.com` ke IP server, lalu:

```bash
sudo ufw allow 80,443/tcp
sudo apt -y install caddy
sudo tee /etc/caddy/Caddyfile >/dev/null <<'EOF'
saham.domainanda.com {
    reverse_proxy 127.0.0.1:8765
}
EOF
sudo systemctl reload caddy
```

Caddy mengurus sertifikat HTTPS otomatis. Buka **https://saham.domainanda.com** → browser meminta user & sandi
dari `SAHAM_BASIC_AUTH`. **Jangan pernah** membuka port 8765 langsung ke internet (`ufw allow 8765` ✗).

---

## 6. Hubungkan bot Telegram

1. Di Telegram buka **@BotFather** → `/newbot` → beri nama → salin **token**.
2. Buat grup Telegram (atau pakai grup yang ada), **tambahkan bot** ke grup.
3. Di SAHAM (browser): **Pengaturan → Bot Telegram**
   1. Tempel token → **Cek & simpan** (muncul `Bot: @nama_bot`).
   2. Klik **jalankan bot untuk mendeteksi grup** (atau centang *Aktif*).
   3. Di grup Telegram ketik **`/start`** → dalam ±30 detik grup muncul di pilihan **Grup** → pilih.
   4. Pastikan **Aktif** tercentang, pilih jenis pesan otomatis.
   5. **Kirim pesan uji** → pesan harus muncul di grup.

Jadwal otomatis (WIB):

| Pesan | Kapan |
|---|---|
| Rencana untuk besok | setelah scan penutupan (±16:50–17:50) — sekali per hari bursa |
| Cek tengah hari | saat jeda siang (Senin–Kamis 12:00–13:30, Jumat 11:30–14:00) |
| Peringatan langsung | setiap scan saat sesi berjalan (±5 menit): harga turun ke **harga beli (limit)** / sentuh TP1 (hanya bila harga beli sempat tercapai) / sentuh cut loss — sekali per saham per hari, untuk saham di rencana terakhir + watchlist; saham HINDARI tidak diberi peringatan beli |
| Rekam jejak mingguan | Jumat, setelah rencana |

Perintah di grup: `/top10`, `/cek BBCA`, `/rencana`, `/tengahhari`, `/pasar`, `/rekam`, `/bantuan`.
Hanya grup yang dipilih di Pengaturan yang dijawab; chat lain yang mengetik `/start` hanya diberi tahu ID-nya.

> Grup privat & bot privat sangat disarankan. Pesan bot selalu memuat keterangan "bukan ajakan beli/jual".
> Bila grup menjadi besar atau berbayar, pelajari aturan OJK tentang penasihat investasi.

---

## 7. Pengaturan AI di server

- **Claude**: pilih mode **API key** (login akun hanya di desktop Windows).
- **9router di server yang sama**: base URL `http://host.docker.internal:20128/v1` (bukan `localhost`, karena
  `localhost` di dalam container adalah container itu sendiri).
- **9router di komputer lain**: base URL berisi IP/domain komputer itu; pastikan bisa dijangkau dari server.

---

## 8. Perawatan

| Tugas | Perintah |
|---|---|
| Lihat log | `docker compose logs -f --tail=100` |
| Restart | `docker compose restart` |
| Update ke versi baru | kirim ulang `saham-deploy.tgz` (langkah 2), ekstrak menimpa folder (`.env` tetap), lalu `docker compose up -d --build` |
| Backup database | `docker compose cp saham:/data/saham.db ./backup-$(date +%F).db` |
| Restore | `docker compose stop && docker compose cp ./backup.db saham:/data/saham.db && docker compose start` |
| Pakai disk | `docker system df` · bersihkan image lama: `docker image prune -f` |

Backup otomatis harian (crontab -e):

```
30 18 * * * cd ~/saham && docker compose cp saham:/data/saham.db ~/backup/saham-$(date +\%F).db && find ~/backup -name 'saham-*.db' -mtime +14 -delete
```

(buat folder dulu: `mkdir -p ~/backup`)

---

## 9. Tanpa Docker (alternatif: systemd)

```bash
sudo apt -y install python3.12 python3.12-venv nodejs npm
sudo useradd --system --create-home --home-dir /var/lib/saham saham
sudo mkdir -p /opt/saham && sudo tar -xzf ~/saham-deploy.tgz -C /opt/saham
cd /opt/saham/ui && sudo npm ci && sudo npm run build
cd /opt/saham && sudo python3.12 -m venv .venv && sudo .venv/bin/pip install -r engine/requirements.txt
echo 'SAHAM_BASIC_AUTH=admin:sandi-panjang' | sudo tee /etc/saham.env && sudo chmod 600 /etc/saham.env
sudo cp deploy/saham.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now saham
journalctl -u saham -f
```

Akses tetap lewat langkah 5A/5B (service mendengarkan di 127.0.0.1:8765).

---

## 10. Masalah umum

| Gejala | Penyebab & solusi |
|---|---|
| Bot: "dipakai instance SAHAM lain" | Telegram aktif di desktop dan server bersamaan → matikan di salah satu |
| Bot: "Token bot tidak valid" | Salin ulang token dari @BotFather (token bisa di-*revoke* lewat `/revoke`) |
| Grup tidak muncul di pilihan | Bot belum aktif saat `/start` diketik, atau bot belum dimasukkan ke grup → aktifkan, ketik `/start` lagi |
| Rencana harian tidak terkirim | Server mati saat 16:50 → saat hidup lagi aplikasi menjalankan scan penutupan susulan, dan bot meminta scan susulan maks. 2× per hari bursa (jeda ≥1 jam); hari libur bursa tidak ada rencana |
| Data harga kosong / sering gagal | Yahoo membatasi permintaan dari IP datacenter → tunggu; scan memakai unduhan batch untuk mengurangi permintaan |
| Browser terus meminta login | User/sandi tidak sama dengan `SAHAM_BASIC_AUTH` di `.env` → perbaiki lalu `docker compose up -d` |
| Tab "Uji Historis" lama | Pertama kali dihitung ±15 menit di latar belakang (CPU kecil bisa lebih lama) |
