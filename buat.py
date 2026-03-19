#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║          MOLTY ROYALE — Account Manager & Wallet Setup       ║
║          Simpan semua akun ke database JSON lokal            ║
╚══════════════════════════════════════════════════════════════╝

Cara Pakai:
  python3 molty_account_manager.py            → Menu interaktif
  python3 molty_account_manager.py --create   → Buat akun baru
  python3 molty_account_manager.py --list     → Lihat semua akun
  python3 molty_account_manager.py --refresh  → Refresh dari server
  python3 molty_account_manager.py --export   → Backup database
  python3 molty_account_manager.py --debug    → Aktifkan debug mode
  python3 molty_account_manager.py --showdb   → Tampilkan raw JSON database
"""

import requests
import json
import os
import re
import sys
import subprocess
import argparse
import time
from datetime import datetime, timezone

# ─────────────────────────────────────────────
# KONFIGURASI
# ─────────────────────────────────────────────
BASE_URL_CDN  = "https://cdn.moltyroyale.com/api"
BASE_URL_MAIN = "https://moltyroyale.com/api"

# Simpan di folder yang mudah ditemukan (HOME, bukan hidden folder)
DB_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(DB_DIR, "accounts_db.json")

DEBUG_MODE = False

# ─────────────────────────────────────────────
# WARNA TERMINAL
# ─────────────────────────────────────────────
class C:
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    RED     = "\033[91m"
    CYAN    = "\033[96m"
    BOLD    = "\033[1m"
    RESET   = "\033[0m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    DIM     = "\033[2m"

# ─────────────────────────────────────────────
# SAFE INPUT (handle Ctrl+C gracefully)
# ─────────────────────────────────────────────
def safe_input(prompt: str = "", default: str = "") -> str:
    """Input yang tidak crash saat Ctrl+C — return default value."""
    try:
        return input(prompt)
    except (KeyboardInterrupt, EOFError):
        print(f"\n{C.YELLOW}  [Dibatalkan]{C.RESET}")
        return default


# ─────────────────────────────────────────────
# HELPER: PILIH AKUN DARI LIST
# ─────────────────────────────────────────────
def pick_account(db: dict, prompt_label: str = "Pilih") -> int:
    """
    Tampilkan list akun dan minta user pilih.
    Return index (0-based), atau -1 jika user batalkan.
    Loop terus sampai input valid atau user ketik '0'/'q'/Enter kosong.
    """
    accounts = db["accounts"]
    if not accounts:
        print(f"{C.YELLOW}Database kosong.{C.RESET}")
        return -1

    while True:
        print(f"\n{C.CYAN}Pilih akun:{C.RESET}")
        for i, acc in enumerate(accounts, 1):
            ws = f"{C.GREEN}✓{C.RESET}" if acc.get("walletAddress") else f"{C.RED}✗{C.RESET}"
            print(f"  [{i}] {acc['name']:<22} Wallet: {ws}")
        print(f"  [0] Kembali ke menu")

        raw = safe_input(f"\n{prompt_label} (1-{len(accounts)}, 0=kembali): ").strip()

        if raw in ("", "0", "q", "Q"):
            print(f"{C.YELLOW}  Kembali ke menu.{C.RESET}")
            return -1

        try:
            idx = int(raw) - 1
            if 0 <= idx < len(accounts):
                return idx
            print(f"  {C.RED}Nomor harus antara 1 sampai {len(accounts)}.{C.RESET}")
        except ValueError:
            print(f"  {C.RED}Masukkan angka atau 0 untuk kembali.{C.RESET}")


# ─────────────────────────────────────────────
# DATABASE HELPER
# ─────────────────────────────────────────────
def load_db() -> dict:
    os.makedirs(DB_DIR, exist_ok=True)
    if not os.path.exists(DB_FILE):
        db = {
            "meta": {
                "created_at"    : datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "last_updated"  : datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "total_accounts": 0,
                "description"   : "Molty Royale Account Database",
                "db_path"       : DB_FILE
            },
            "accounts": []
        }
        save_db(db)
        return db
    with open(DB_FILE, "r") as f:
        return json.load(f)


def save_db(db: dict):
    os.makedirs(DB_DIR, exist_ok=True)
    db["meta"]["last_updated"]   = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    db["meta"]["total_accounts"] = len(db["accounts"])
    db["meta"]["db_path"]        = DB_FILE
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


def migrate_old_db():
    """Migrasi dari lokasi lama (~/.molty-royale/) ke lokasi baru (~/molty-royale/)"""
    old_path = os.path.expanduser("~/.molty-royale/accounts_db.json")
    if os.path.exists(old_path) and not os.path.exists(DB_FILE):
        print(f"{C.YELLOW}[MIGRASI]{C.RESET} Ditemukan database lama di: {old_path}")
        print(f"          Memindahkan ke: {DB_FILE}")
        os.makedirs(DB_DIR, exist_ok=True)
        with open(old_path, "r") as f:
            old_data = json.load(f)
        with open(DB_FILE, "w") as f:
            json.dump(old_data, f, indent=2, ensure_ascii=False)
        print(f"{C.GREEN}[MIGRASI]{C.RESET} Selesai! File lama tetap ada di {old_path}")


def find_account_by_name(db, name):
    for acc in db["accounts"]:
        if acc["name"].lower() == name.lower():
            return acc
    return None


def find_account_by_id(db, account_id: str):
    """Cari akun berdasarkan accountId."""
    for acc in db["accounts"]:
        if acc.get("accountId") == account_id:
            return acc
    return None


def find_account_by_apikey(db, api_key: str):
    """Cari akun berdasarkan API key."""
    for acc in db["accounts"]:
        if acc.get("apiKey") == api_key:
            return acc
    return None


# ─────────────────────────────────────────────
# VALIDASI
# ─────────────────────────────────────────────
def validate_name(name: str) -> tuple:
    if not name:
        return True, "", name
    original   = name
    name       = name.replace(" ", "_")
    name_clean = re.sub(r"[^a-zA-Z0-9_\-]", "", name)
    errors     = []
    if len(name_clean) < 3:
        errors.append(f"Terlalu pendek (min 3 karakter)")
    if len(name_clean) > 20:
        name_clean = name_clean[:20]
        errors.append(f"Dipotong jadi: '{name_clean}'")
    if name_clean and name_clean[0].isdigit():
        name_clean = "a" + name_clean[1:]
        errors.append(f"Tidak boleh diawali angka → '{name_clean}'")
    if name_clean != original:
        errors.append(f"'{original}' → '{name_clean}'")
    return (False, " | ".join(errors), name_clean) if errors else (True, "", name_clean)


def validate_wallet(wallet: str) -> tuple:
    if not wallet:
        return False, "Wallet tidak boleh kosong"
    if not wallet.startswith("0x"):
        return False, "Harus diawali '0x'"
    if len(wallet) != 42:
        return False, f"Harus 42 karakter (sekarang: {len(wallet)})"
    try:
        int(wallet[2:], 16)
    except ValueError:
        return False, "Mengandung karakter bukan hex"
    return True, ""


# ─────────────────────────────────────────────
# HTTP HELPERS
# ─────────────────────────────────────────────
def _do_request(method: str, endpoint: str, payload: dict = None, api_key: str = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    urls = [(BASE_URL_CDN + endpoint, "cdn"), (BASE_URL_MAIN + endpoint, "main")]
    last_err = ""

    for url, label in urls:
        try:
            if DEBUG_MODE:
                print(f"{C.DIM}[DEBUG] {method.upper()} {url}{C.RESET}")
                if payload:
                    print(f"{C.DIM}[DEBUG] Payload: {json.dumps(payload)}{C.RESET}")

            if method == "post":
                res = requests.post(url, headers=headers, json=payload or {}, timeout=15)
            elif method == "put":
                res = requests.put(url, headers=headers, json=payload or {}, timeout=15)
            else:
                res = requests.get(url, headers=headers, timeout=10)

            if DEBUG_MODE:
                print(f"{C.DIM}[DEBUG] Status: {res.status_code}{C.RESET}")
                print(f"{C.DIM}[DEBUG] Response: {res.text[:600]}{C.RESET}")

            try:
                body = res.json()
            except Exception:
                return {"success": False, "error": {"message": f"Response bukan JSON: {res.text[:100]}", "code": "PARSE_ERROR"}, "_status": res.status_code}

            return {"_status": res.status_code, **body}

        except requests.exceptions.ConnectionError as e:
            last_err = str(e)
            continue
        except requests.exceptions.Timeout:
            last_err = f"Timeout ({label})"
            continue

    return {"success": False, "error": {"message": f"Tidak bisa terhubung. {last_err}", "code": "CONNECTION_ERROR"}, "_status": 0}


# ─────────────────────────────────────────────
# API FUNCTIONS
# ─────────────────────────────────────────────
def create_account(name: str, wallet_address: str) -> dict | None:
    print(f"\n{C.CYAN}[API]{C.RESET} Mengirim request buat akun...")
    payload = {"wallet_address": wallet_address}
    if name:
        payload["name"] = name

    data = _do_request("post", "/accounts", payload)

    if not data.get("success"):
        err  = data.get("error", {})
        code = err.get("code", "?")
        msg  = err.get("message", "Unknown error")
        print(f"{C.RED}[ERROR]{C.RESET} {msg}")
        print(f"{C.RED}        Kode: {code} | HTTP: {data.get('_status', '?')}{C.RESET}")
        details = err.get("details", [])
        if details:
            print(f"{C.YELLOW}        Detail:{C.RESET}")
            for d in details:
                print(f"          • field={d.get('field','?')} | {d.get('message','?')} ({d.get('code','?')})")
        return None

    return data.get("data")


def update_wallet_separate(api_key: str, wallet_address: str) -> bool:
    data = _do_request("put", "/accounts/wallet", {"wallet_address": wallet_address}, api_key)
    if data.get("_status") == 401:
        print(f"{C.RED}[ERROR]{C.RESET} API key tidak valid.")
        return False
    if not data.get("success"):
        err = data.get("error", {})
        print(f"{C.RED}[ERROR]{C.RESET} {err.get('message', 'Unknown')} ({err.get('code', '?')})")
        return False
    return True


def get_account_info(api_key: str) -> tuple:
    """
    Fetch account info dari server.
    Return: (data_dict | None, error_msg | None)
    """
    data = _do_request("get", "/accounts/me", api_key=api_key)
    if data.get("success"):
        return data.get("data"), None
    else:
        err = data.get("error", {})
        msg = f"{err.get('message','Unknown')} (code: {err.get('code','?')}, HTTP: {data.get('_status','?')})"
        return None, msg


# ─────────────────────────────────────────────
# FLOW: BUAT AKUN BARU
# ─────────────────────────────────────────────
def flow_create_account():
    print(f"\n{C.BOLD}{'═'*57}{C.RESET}")
    print(f"{C.BOLD}  BUAT AKUN BARU{C.RESET}")
    print(f"{C.BOLD}{'═'*57}{C.RESET}")

    db = load_db()

    print(f"\n{C.DIM}Aturan nama:{C.RESET} huruf/angka/underscore, 3-20 karakter\n")
    while True:
        raw_name = safe_input(f"{C.YELLOW}Nama akun{C.RESET} (kosongkan = otomatis): ").strip()
        if not raw_name:
            final_name = ""
            break
        is_valid, err_msg, fixed = validate_name(raw_name)
        if not is_valid:
            print(f"  {C.YELLOW}[AUTO-FIX]{C.RESET} {err_msg}")
            if safe_input(f"  Gunakan '{C.BOLD}{fixed}{C.RESET}' ? (y/n): ").strip().lower() == "y":
                final_name = fixed
                break
            continue
        final_name = fixed
        break

    if final_name and find_account_by_name(db, final_name):
        print(f"{C.YELLOW}[INFO]{C.RESET} Nama '{final_name}' sudah ada di DB.")
        if safe_input("Tetap lanjut? (y/n): ").strip().lower() != "y":
            return

    print(f"\n{C.BOLD}Wallet Address{C.RESET} {C.RED}(WAJIB — diperlukan oleh API){C.RESET}")
    print(f"{C.DIM}Format: 0x + 40 hex chars = 42 karakter total{C.RESET}\n")
    while True:
        wallet = safe_input(f"{C.YELLOW}Wallet address{C.RESET} (0x...): ").strip()
        ok, err = validate_wallet(wallet)
        if ok:
            print(f"  {C.GREEN}✓ Format valid{C.RESET}")
            break
        print(f"  {C.RED}✗ {err}{C.RESET}\n")

    acc_data = create_account(final_name, wallet)
    if not acc_data:
        print(f"\n{C.RED}✗ Gagal membuat akun.{C.RESET}")
        return

    print(f"\n{C.GREEN}{'═'*57}{C.RESET}")
    print(f"{C.GREEN}✓  AKUN BERHASIL DIBUAT!{C.RESET}")
    print(f"{'═'*57}")
    print(f"  Account ID      : {C.BOLD}{acc_data['accountId']}{C.RESET}")
    print(f"  Nama            : {C.BOLD}{acc_data['name']}{C.RESET}")
    print(f"  API Key         : {C.BOLD}{C.GREEN}{acc_data['apiKey']}{C.RESET}")
    print(f"  Kode Verifikasi : {acc_data.get('verificationCode', '—')}")
    print(f"  Balance         : {acc_data.get('balance', 0)} $Moltz")
    print(f"  Wallet          : {wallet}")
    print(f"\n{C.RED}⚠  API KEY HANYA MUNCUL SEKALI — disimpan otomatis ke DB!{C.RESET}")
    print(f"{'═'*57}")

    record = {
        "accountId"        : acc_data["accountId"],
        "name"             : acc_data["name"],
        "apiKey"           : acc_data["apiKey"],
        "verificationCode" : acc_data.get("verificationCode", ""),
        "walletAddress"    : wallet,
        "walletSynced"     : True,
        "balance"          : acc_data.get("balance", 0),
        "crossBalanceWei"  : acc_data.get("crossBalanceWei", "0"),
        "totalGames"       : 0,
        "totalWins"        : 0,
        "currentGames"     : [],
        "createdAt"        : acc_data.get("createdAt", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")),
        "lastUpdated"      : datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "notes"            : ""
    }

    db["accounts"].append(record)
    save_db(db)

    print(f"\n{C.GREEN}✓ Tersimpan ke database!{C.RESET}")
    print(f"\n  {'─'*53}")
    print(f"  {C.BOLD}Lokasi file DB:{C.RESET}")
    print(f"  {C.CYAN}{DB_FILE}{C.RESET}")
    print(f"  {'─'*53}")
    print(f"  Total akun: {C.BOLD}{len(db['accounts'])}{C.RESET}")
    print(f"\n  {C.DIM}Buka file:{C.RESET}  cat \"{DB_FILE}\"")
    print(f"  {C.DIM}Edit file:{C.RESET}  nano \"{DB_FILE}\"")


# ─────────────────────────────────────────────
# FLOW: TAMPILKAN RAW DATABASE JSON
# ─────────────────────────────────────────────
def flow_show_db():
    """Tampilkan isi database JSON langsung di terminal."""
    print(f"\n{C.BOLD}{'═'*70}{C.RESET}")
    print(f"{C.BOLD}  RAW DATABASE JSON{C.RESET}")
    print(f"  Path: {C.CYAN}{DB_FILE}{C.RESET}")
    print(f"{C.BOLD}{'═'*70}{C.RESET}\n")

    if not os.path.exists(DB_FILE):
        print(f"{C.YELLOW}File tidak ditemukan: {DB_FILE}{C.RESET}")
        print(f"Buat akun dulu via menu [1].")
        return

    with open(DB_FILE, "r") as f:
        content = f.read()
        db      = json.loads(content)

    # Pretty print dengan highlight
    print(f"{C.DIM}File size: {os.path.getsize(DB_FILE)} bytes | "
          f"Akun: {len(db.get('accounts', []))}{C.RESET}\n")

    # Tampilkan JSON dengan warna sederhana
    lines = json.dumps(db, indent=2, ensure_ascii=False).splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('"apiKey"'):
            # Sembunyikan sebagian API key di display
            print(f"{C.YELLOW}{line}{C.RESET}")
        elif stripped.startswith('"accountId"') or stripped.startswith('"name"') or stripped.startswith('"walletAddress"'):
            print(f"{C.GREEN}{line}{C.RESET}")
        elif stripped.startswith('"balance"') or stripped.startswith('"totalGames"') or stripped.startswith('"totalWins"'):
            print(f"{C.CYAN}{line}{C.RESET}")
        elif line.strip() in ["{", "}", "[", "]", "},", "],"] or stripped == "":
            print(f"{C.DIM}{line}{C.RESET}")
        else:
            print(line)

    print(f"\n{C.BOLD}{'─'*70}{C.RESET}")
    print(f"  {C.BOLD}Lokasi file:{C.RESET}")
    print(f"  {C.CYAN}{DB_FILE}{C.RESET}")
    print(f"\n  {C.DIM}Perintah terminal untuk mengakses file:{C.RESET}")
    print(f"  cat  \"{DB_FILE}\"")
    print(f"  nano \"{DB_FILE}\"")
    print(f"  cp   \"{DB_FILE}\" ~/Desktop/accounts_backup.json")


# ─────────────────────────────────────────────
# FLOW: LOKASI & INFO FILE DATABASE
# ─────────────────────────────────────────────
def flow_db_info():
    """Tampilkan info lokasi file database dan cara mengaksesnya."""
    print(f"\n{C.BOLD}{'═'*57}{C.RESET}")
    print(f"{C.BOLD}  INFO FILE DATABASE{C.RESET}")
    print(f"{C.BOLD}{'═'*57}{C.RESET}")

    exists = os.path.exists(DB_FILE)
    size   = os.path.getsize(DB_FILE) if exists else 0
    db     = load_db() if exists else {"accounts": []}

    print(f"""
  {C.BOLD}Lokasi file:{C.RESET}
  {C.CYAN}{DB_FILE}{C.RESET}

  {C.BOLD}Status:{C.RESET}
  Ada      : {C.GREEN + "✓ YA" if exists else C.RED + "✗ BELUM ADA"}{C.RESET}
  Ukuran   : {size} bytes
  Total akun: {len(db['accounts'])}

  {C.BOLD}Cara membuka file:{C.RESET}

  {C.YELLOW}# Tampilkan di terminal:{C.RESET}
  cat "{DB_FILE}"

  {C.YELLOW}# Edit dengan nano:{C.RESET}
  nano "{DB_FILE}"

  {C.YELLOW}# Buka dengan text editor GUI (kalau ada):{C.RESET}
  xdg-open "{DB_FILE}"
  gedit "{DB_FILE}"
  code  "{DB_FILE}"

  {C.YELLOW}# Copy ke Desktop:{C.RESET}
  cp "{DB_FILE}" ~/Desktop/accounts_db.json

  {C.YELLOW}# Folder database:{C.RESET}
  ls -la "{DB_DIR}/"
""")

    if exists and safe_input("Tampilkan isi JSON sekarang? (y/n): ").strip().lower() == "y":
        flow_show_db()


# ─────────────────────────────────────────────
# FLOW: UPDATE WALLET
# ─────────────────────────────────────────────
def flow_update_wallet():
    print(f"\n{C.BOLD}{'═'*57}{C.RESET}")
    print(f"{C.BOLD}  UPDATE WALLET{C.RESET}")
    print(f"{C.BOLD}{'═'*57}{C.RESET}")

    db = load_db()
    if not db["accounts"]:
        print(f"{C.YELLOW}Database kosong.{C.RESET}")
        return

    idx = pick_account(db, "Pilih akun")
    if idx == -1:
        return

    account = db["accounts"][idx]
    print(f"\nAkun: {C.BOLD}{account['name']}{C.RESET}")
    if account.get("walletAddress"):
        print(f"Wallet lama: {account['walletAddress']}")

    while True:
        wallet = safe_input("\nWallet baru (0x...42 karakter): ").strip()
        ok, err = validate_wallet(wallet)
        if ok:
            break
        print(f"  {C.RED}✗ {err}{C.RESET}")

    success = update_wallet_separate(account["apiKey"], wallet)
    db["accounts"][idx]["walletAddress"] = wallet
    db["accounts"][idx]["walletSynced"]  = success
    db["accounts"][idx]["lastUpdated"]   = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    save_db(db)

    label = f"{C.GREEN}✓ Server + DB{C.RESET}" if success else f"{C.YELLOW}✓ DB lokal saja{C.RESET}"
    print(f"\nUpdate wallet: {label}")


# ─────────────────────────────────────────────
# FLOW: LIST AKUN
# ─────────────────────────────────────────────
def flow_list_accounts():
    db = load_db()
    print(f"\n{C.BOLD}{'═'*70}{C.RESET}")
    print(f"{C.BOLD}  DATABASE AKUN MOLTY ROYALE{C.RESET}")
    print(f"  File  : {C.CYAN}{DB_FILE}{C.RESET}")
    print(f"  Update: {db['meta']['last_updated']}")
    print(f"{C.BOLD}{'═'*70}{C.RESET}")

    if not db["accounts"]:
        print(f"\n  {C.YELLOW}Kosong — belum ada akun.{C.RESET}\n")
        return

    print(f"\n  Total: {C.BOLD}{len(db['accounts'])}{C.RESET} akun\n")

    for i, acc in enumerate(db["accounts"], 1):
        w      = acc.get("walletAddress", "")
        w_disp = (f"{C.GREEN}✓ {w[:8]}...{w[-4:]}{C.RESET}") if w else f"{C.RED}✗ Belum diset{C.RESET}"
        sync   = (f"{C.GREEN}Synced{C.RESET}") if acc.get("walletSynced") else f"{C.YELLOW}Lokal{C.RESET}"

        print(f"  {C.BOLD}[{i}] {acc['name']}{C.RESET}")
        print(f"       Account ID   : {acc['accountId']}")
        print(f"       API Key      : {acc['apiKey'][:18]}...{C.DIM}(hidden){C.RESET}")
        print(f"       Verify Code  : {acc.get('verificationCode','—')}")
        print(f"       Balance      : {C.GREEN}{acc.get('balance',0)} $Moltz{C.RESET}")
        print(f"       Wallet       : {w_disp}  [{sync}]")
        print(f"       Games/Wins   : {acc.get('totalGames',0)} / {acc.get('totalWins',0)}")
        print(f"       Dibuat       : {acc.get('createdAt','—')[:10]}")
        if i < len(db["accounts"]):
            print(f"       {'─'*52}")
    print()


# ─────────────────────────────────────────────
# FLOW: REFRESH DARI SERVER
# ─────────────────────────────────────────────
def flow_refresh_all():
    db = load_db()
    if not db["accounts"]:
        print(f"{C.YELLOW}Database kosong.{C.RESET}")
        return

    print(f"\n{C.CYAN}Refresh {len(db['accounts'])} akun dari server...{C.RESET}\n")
    for idx, acc in enumerate(db["accounts"]):
        print(f"  [{idx+1}] {acc['name']}...", end=" ", flush=True)
        info, err_msg = get_account_info(acc["apiKey"])
        if info:
            db["accounts"][idx].update({
                "balance"          : info.get("balance", acc.get("balance", 0)),
                "crossBalanceWei"  : info.get("crossBalanceWei", "0"),
                "totalGames"       : info.get("totalGames", 0),
                "totalWins"        : info.get("totalWins", 0),
                "currentGames"     : info.get("currentGames", []),
                "verificationCode" : info.get("verificationCode", acc.get("verificationCode", "")),
                "lastUpdated"      : datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            })
            print(f"{C.GREEN}✓{C.RESET} {info.get('balance',0)} $Moltz | "
                  f"G:{info.get('totalGames',0)} W:{info.get('totalWins',0)}")
        else:
            print(f"{C.YELLOW}✗ Gagal — {err_msg}{C.RESET}")

    save_db(db)
    print(f"\n{C.GREEN}✓ Selesai. DB diperbarui.{C.RESET}")


# ─────────────────────────────────────────────
# FLOW: EXPORT / BACKUP
# ─────────────────────────────────────────────
def flow_export():
    db = load_db()
    if not db["accounts"]:
        print(f"{C.YELLOW}Database kosong.{C.RESET}")
        return

    print(f"\nSimpan backup ke mana?")
    print(f"  [1] Desktop           : ~/Desktop/molty_backup.json")
    print(f"  [2] Home folder       : ~/molty_backup.json")
    print(f"  [3] Folder DB         : {DB_DIR}/backup_<timestamp>.json")
    print(f"  [4] Path custom")

    while True:
        raw = safe_input("\nPilih (1-4, 0=kembali): ").strip()
        if raw in ("1", "2", "3", "4", "", "0", "q"):
            break
        print(f"  {C.RED}Masukkan angka 1-4 atau 0 untuk kembali.{C.RESET}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if raw == "1":
        path = os.path.expanduser(f"~/Desktop/molty_backup_{ts}.json")
    elif raw == "2":
        path = os.path.expanduser(f"~/molty_backup_{ts}.json")
    elif raw == "3":
        path = os.path.join(DB_DIR, f"backup_{ts}.json")
    elif raw == "4":
        path = safe_input("Path lengkap: ").strip()
        if not path:
            print("Dibatalkan.")
            return
    elif raw in ("", "0", "q"):
        print(f"{C.YELLOW}  Kembali ke menu.{C.RESET}")
        return
    else:
        print(f"  {C.RED}Pilihan tidak valid. Masukkan 1-4 atau 0 untuk batal.{C.RESET}")
        return

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

    print(f"\n{C.GREEN}✓ Backup tersimpan!{C.RESET}")
    print(f"  Path  : {C.CYAN}{path}{C.RESET}")
    print(f"  Akun  : {len(db['accounts'])}")
    print(f"  Size  : {os.path.getsize(path)} bytes")


# ─────────────────────────────────────────────
# FLOW: HAPUS AKUN
# ─────────────────────────────────────────────
def flow_delete_account():
    db = load_db()
    if not db["accounts"]:
        print(f"{C.YELLOW}Database kosong.{C.RESET}")
        return

    idx = pick_account(db, "Pilih akun yang dihapus")
    if idx == -1:
        return

    acc = db["accounts"][idx]
    if safe_input(f"\n{C.RED}Ketik 'hapus' untuk konfirmasi: {C.RESET}").strip().lower() == "hapus":
        db["accounts"].pop(idx)
        save_db(db)
        print(f"{C.GREEN}✓ Dihapus dari DB lokal.{C.RESET}")
    else:
        print("Dibatalkan.")


# ─────────────────────────────────────────────
# MENU UTAMA
# ─────────────────────────────────────────────
def print_banner():
    db    = load_db()
    total = len(db["accounts"])
    print(f"\n{C.BOLD}{C.CYAN}╔══════════════════════════════════════════════════════╗{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}║      MOLTY ROYALE — Account Manager v1.3             ║{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}╠══════════════════════════════════════════════════════╣{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}║{C.RESET}  DB   : {DB_FILE:<44}{C.BOLD}{C.CYAN}║{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}║{C.RESET}  Akun : {C.BOLD}{str(total):<44}{C.CYAN}║{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}╚══════════════════════════════════════════════════════╝{C.RESET}")



# ─────────────────────────────────────────────
# FLOW: IMPORT AKUN DARI API KEY
# ─────────────────────────────────────────────
def flow_import_account():
    """
    Tambahkan akun ke DB dari API key yang sudah ada.
    Fetch data dari server: nama, accountId, balance, dll.
    """
    print(f"\n{C.BOLD}{'═'*57}{C.RESET}")
    print(f"{C.BOLD}  IMPORT AKUN DARI API KEY{C.RESET}")
    print(f"{C.BOLD}{'═'*57}{C.RESET}")
    print(f"""
{C.DIM}Gunakan fitur ini jika:{C.RESET}
  • Pindah komputer / install ulang
  • DB terhapus tapi masih punya API key
  • Mau sync akun lama ke database baru
  • Punya beberapa API key dan mau dimasukkan semua

{C.DIM}Format API key:{C.RESET} mr_live_xxxxxxxxxxxxxxxxxxxxxxxx
""")

    db = load_db()

    # ── Bisa import satu atau banyak sekaligus ──
    print(f"  {C.BOLD}Mode import:{C.RESET}")
    print(f"  [1] Import satu API key")
    print(f"  [2] Import banyak sekaligus (paste baris per baris)")
    print(f"  [0] Kembali")

    mode = safe_input(f"\n  Pilih (1/2/0): ").strip()

    if mode == "0" or mode == "":
        return
    elif mode == "1":
        api_keys = []
        raw = safe_input(f"\n{C.YELLOW}Masukkan API key{C.RESET} (mr_live_...): ").strip()
        if raw:
            api_keys = [raw]
    elif mode == "2":
        print(f"\n{C.YELLOW}Paste API key satu per baris.{C.RESET}")
        print(f"{C.DIM}Ketik {C.RESET}{C.BOLD}DONE{C.DIM} lalu Enter jika sudah selesai.{C.RESET}\n")
        api_keys = []
        while True:
            line = safe_input(f"  API key [{len(api_keys)+1}]: ").strip()
            if line.upper() == "DONE" or line == "":
                break
            if line:
                api_keys.append(line)
        if not api_keys:
            print(f"{C.YELLOW}Tidak ada API key dimasukkan.{C.RESET}")
            return
    else:
        print(f"{C.RED}Pilihan tidak valid.{C.RESET}")
        return

    # ── Proses tiap API key ──
    print(f"\n{C.CYAN}Memproses {len(api_keys)} API key...{C.RESET}\n")
    print(f"  {'─'*55}")

    results = {"berhasil": 0, "duplikat": 0, "gagal": 0}

    for i, api_key in enumerate(api_keys, 1):
        print(f"\n  [{i}/{len(api_keys)}] {api_key[:20]}...")

        # Validasi format dasar
        if not api_key.startswith("mr_live_"):
            print(f"         {C.RED}✗ Format tidak valid (harus diawali mr_live_){C.RESET}")
            results["gagal"] += 1
            continue

        if len(api_key) < 20:
            print(f"         {C.RED}✗ API key terlalu pendek{C.RESET}")
            results["gagal"] += 1
            continue

        # Fetch dari server — retry sekali jika gagal
        info = None
        err_msg = None
        for attempt in range(1, 3):
            print(f"         Fetching dari server (attempt {attempt}/2)...", end=" ", flush=True)
            info, err_msg = get_account_info(api_key)
            if info:
                print(f"{C.GREEN}✓{C.RESET}")
                break
            else:
                print(f"{C.RED}✗{C.RESET}")
                print(f"         {C.RED}Detail: {err_msg}{C.RESET}")
                if attempt < 2:
                    print(f"         {C.YELLOW}Mencoba ulang...{C.RESET}")

        if not info:
            print(f"\n         {C.RED}✗ Gagal fetch setelah 2 percobaan.{C.RESET}")
            print(f"         {C.YELLOW}Kemungkinan penyebab:{C.RESET}")
            print(f"           • API key salah atau sudah expired")
            print(f"           • Koneksi internet bermasalah")
            print(f"           • Server sedang down")
            results["gagal"] += 1
            continue

        account_id = info.get("id") or info.get("accountId") or info.get("account_id", "")
        if not account_id:
            print(f"         {C.RED}✗ Tidak bisa mendapatkan account ID dari response server{C.RESET}")
            print(f"         {C.DIM}Response fields: {list(info.keys())}{C.RESET}")
            results["gagal"] += 1
            continue
        name       = info.get("name", "unknown")

        # Cek duplikat di DB (by accountId ATAU by API key)
        dup_by_id  = find_account_by_id(db, account_id)
        dup_by_key = find_account_by_apikey(db, api_key)
        dup_by_id  = dup_by_id or dup_by_key

        if dup_by_id:
            print(f"         {C.YELLOW}⚠ Sudah ada di DB: {name} ({account_id[:12]}...){C.RESET}")
            choice = safe_input(f"         Update data akun ini? (y/n): ").strip().lower()
            if choice == "y":
                # Update record yang ada
                for idx2, acc in enumerate(db["accounts"]):
                    if acc["accountId"] == account_id:
                        db["accounts"][idx2].update({
                            "apiKey"      : api_key,
                            "balance"     : info.get("balance", 0),
                            "crossBalanceWei": info.get("crossBalanceWei", "0"),
                            "totalGames"  : info.get("totalGames", 0),
                            "totalWins"   : info.get("totalWins", 0),
                            "currentGames": info.get("currentGames", []),
                            "lastUpdated" : datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                        })
                        break
                print(f"         {C.GREEN}✓ Data diperbarui.{C.RESET}")
                results["berhasil"] += 1
            else:
                print(f"         {C.YELLOW}Dilewati.{C.RESET}")
                results["duplikat"] += 1
            continue

        # Tampilkan info akun
        print(f"\n         {C.BOLD}Info akun dari server:{C.RESET}")
        print(f"         Nama        : {C.BOLD}{name}{C.RESET}")
        print(f"         Account ID  : {account_id}")
        print(f"         Balance     : {C.GREEN}{info.get('balance', 0)} $Moltz{C.RESET}")
        print(f"         Total Games : {info.get('totalGames', 0)}")
        print(f"         Total Wins  : {info.get('totalWins', 0)}")

        # Wallet
        wallet_from_server = info.get("walletAddress") or info.get("wallet_address", "")
        if wallet_from_server:
            print(f"         Wallet      : {C.GREEN}✓ {wallet_from_server[:10]}...{wallet_from_server[-4:]}{C.RESET}")
        else:
            print(f"         Wallet      : {C.RED}✗ Belum diset di server{C.RESET}")

        # Konfirmasi simpan
        save = safe_input(f"\n         Simpan ke database? (y/n): ").strip().lower()
        if save != "y":
            print(f"         {C.YELLOW}Dilewati.{C.RESET}")
            results["duplikat"] += 1
            continue

        # Tanya wallet jika belum ada
        wallet = wallet_from_server
        wallet_synced = bool(wallet_from_server)

        if not wallet_from_server:
            print(f"\n         {C.YELLOW}Akun ini belum punya wallet.{C.RESET}")
            set_wallet = safe_input("         Set wallet sekarang? (y/n): ").strip().lower()
            if set_wallet == "y":
                while True:
                    w = safe_input("         Wallet (0x...): ").strip()
                    ok, err = validate_wallet(w)
                    if ok:
                        # Coba sync ke server
                        synced = update_wallet_separate(api_key, w)
                        wallet        = w
                        wallet_synced = synced
                        break
                    print(f"         {C.RED}✗ {err}{C.RESET}")

        # Buat record
        record = {
            "accountId"        : account_id,
            "name"             : name,
            "apiKey"           : api_key,
            "verificationCode" : info.get("verificationCode", ""),
            "walletAddress"    : wallet,
            "walletSynced"     : wallet_synced,
            "balance"          : info.get("balance", 0),
            "crossBalanceWei"  : info.get("crossBalanceWei", "0"),
            "totalGames"       : info.get("totalGames", 0),
            "totalWins"        : info.get("totalWins", 0),
            "currentGames"     : info.get("currentGames", []),
            "createdAt"        : info.get("createdAt", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")),
            "lastUpdated"      : datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "notes"            : "imported"
        }

        db["accounts"].append(record)
        print(f"         {C.GREEN}✓ Berhasil ditambahkan ke DB!{C.RESET}")
        results["berhasil"] += 1

    # ── Simpan & Ringkasan ──
    if results["berhasil"] > 0:
        save_db(db)

    print(f"\n  {'─'*55}")
    print(f"  {C.BOLD}HASIL IMPORT:{C.RESET}")
    print(f"  {C.GREEN}✓ Berhasil : {results['berhasil']}{C.RESET}")
    print(f"  {C.YELLOW}⚠ Dilewati : {results['duplikat']}{C.RESET}")
    print(f"  {C.RED}✗ Gagal    : {results['gagal']}{C.RESET}")
    print(f"  Total akun di DB: {C.BOLD}{len(db['accounts'])}{C.RESET}")
    if results["berhasil"] > 0:
        print(f"\n  {C.GREEN}DB tersimpan ke: {DB_FILE}{C.RESET}")


# ─────────────────────────────────────────────
# FLOW: BULK CREATE ACCOUNT
# ─────────────────────────────────────────────
def flow_bulk_create():
    print(f"\n{C.BOLD}{'═'*57}{C.RESET}")
    print(f"{C.BOLD}  BULK CREATE AKUN{C.RESET}")
    print(f"{C.BOLD}{'═'*57}{C.RESET}")
    print(f"  {C.DIM}Buat banyak akun sekaligus. Setiap akun disimpan")
    print(f"  ke DB setelah berhasil dibuat.{C.RESET}\n")

    db = load_db()

    # ── Jumlah akun ──
    while True:
        raw = safe_input(f"  {C.YELLOW}Jumlah akun yang mau dibuat{C.RESET} (1-50): ").strip()
        if not raw.isdigit() or not (1 <= int(raw) <= 50):
            print(f"  {C.RED}✗ Masukkan angka 1–50.{C.RESET}")
            continue
        total = int(raw)
        break

    # ── Mode nama ──
    print(f"\n  {C.BOLD}Mode penamaan:{C.RESET}")
    print(f"  {C.GREEN}[1]{C.RESET} Prefix otomatis  {C.DIM}→ contoh: hero1, hero2, ...{C.RESET}")
    print(f"  {C.YELLOW}[2]{C.RESET} Nama manual      {C.DIM}→ input satu per satu{C.RESET}")
    print(f"  {C.BLUE}[3]{C.RESET} Biarkan server   {C.DIM}→ nama digenerate otomatis{C.RESET}\n")

    while True:
        mode_name = safe_input(f"  Pilih mode nama (1/2/3): ").strip()
        if mode_name in ("1", "2", "3"):
            break
        print(f"  {C.RED}✗ Masukkan 1, 2, atau 3.{C.RESET}")

    names = []
    if mode_name == "1":
        while True:
            prefix = safe_input(f"  {C.YELLOW}Prefix nama{C.RESET} (contoh: hero → hero811, hero812): ").strip()
            if not prefix:
                print(f"  {C.RED}✗ Prefix tidak boleh kosong.{C.RESET}")
                continue
            _, _, prefix = validate_name(prefix)
            if len(prefix) < 2:
                print(f"  {C.RED}✗ Prefix terlalu pendek.{C.RESET}")
                continue
            raw_start = safe_input(f"  {C.YELLOW}Mulai dari angka berapa?{C.RESET} (default: 1): ").strip()
            start_num = int(raw_start) if raw_start.isdigit() else 1
            suffix_len = len(f"{start_num + total - 1}")
            max_prefix = 20 - suffix_len
            if len(prefix) > max_prefix:
                prefix = prefix[:max_prefix]
                print(f"  {C.YELLOW}[AUTO-FIX]{C.RESET} Prefix dipotong jadi: '{prefix}'")
            names = [f"{prefix}{i}" for i in range(start_num, start_num + total)]
            print(f"  {C.DIM}Preview: {', '.join(names[:3])}{'...' if total > 3 else ''}{C.RESET}")
            if safe_input("  Lanjut? (y/n): ").strip().lower() == "y":
                break
    elif mode_name == "2":
        print(f"\n  {C.DIM}Masukkan {total} nama akun satu per satu:{C.RESET}")
        for i in range(1, total + 1):
            while True:
                raw_name = safe_input(f"  Nama akun [{i}/{total}]: ").strip()
                if not raw_name:
                    print(f"  {C.YELLOW}Nama kosong, akan digenerate server.{C.RESET}")
                    names.append("")
                    break
                is_valid, err_msg, fixed = validate_name(raw_name)
                if err_msg:
                    print(f"  {C.YELLOW}[AUTO-FIX]{C.RESET} {err_msg}")
                if find_account_by_name(db, fixed):
                    print(f"  {C.YELLOW}⚠ '{fixed}' sudah ada di DB.{C.RESET}")
                    if safe_input("  Tetap pakai? (y/n): ").strip().lower() != "y":
                        continue
                names.append(fixed)
                break
    else:
        names = [""] * total

    # ── Mode wallet ──
    print(f"\n  {C.BOLD}Mode wallet:{C.RESET}")
    print(f"  {C.GREEN}[1]{C.RESET} Satu wallet untuk semua akun")
    print(f"  {C.YELLOW}[2]{C.RESET} Wallet berbeda tiap akun  {C.DIM}→ input satu per satu{C.RESET}")
    print(f"  {C.BLUE}[3]{C.RESET} Load dari file .txt        {C.DIM}→ satu wallet per baris{C.RESET}\n")

    while True:
        mode_wallet = safe_input(f"  Pilih mode wallet (1/2/3): ").strip()
        if mode_wallet in ("1", "2", "3"):
            break
        print(f"  {C.RED}✗ Masukkan 1, 2, atau 3.{C.RESET}")

    wallets = []
    if mode_wallet == "1":
        while True:
            w = safe_input(f"  {C.YELLOW}Wallet address{C.RESET} (0x...): ").strip()
            ok, err = validate_wallet(w)
            if ok:
                wallets = [w] * total
                print(f"  {C.GREEN}✓ Wallet valid — akan dipakai untuk semua {total} akun.{C.RESET}")
                break
            print(f"  {C.RED}✗ {err}{C.RESET}")

    elif mode_wallet == "2":
        print(f"\n  {C.DIM}Masukkan {total} wallet address:{C.RESET}")
        for i in range(1, total + 1):
            while True:
                w = safe_input(f"  Wallet [{i}/{total}] (0x...): ").strip()
                ok, err = validate_wallet(w)
                if ok:
                    wallets.append(w)
                    break
                print(f"  {C.RED}✗ {err}{C.RESET}")

    else:
        while True:
            path = safe_input(f"  {C.YELLOW}Path file .txt{C.RESET}: ").strip().strip("'\"")
            path = os.path.expanduser(path)
            if not os.path.exists(path):
                print(f"  {C.RED}✗ File tidak ditemukan: {path}{C.RESET}")
                continue
            with open(path, "r") as f:
                raw_lines = [l.strip() for l in f.readlines() if l.strip()]
            valid_wallets = []
            invalid_count = 0
            for line in raw_lines:
                ok, _ = validate_wallet(line)
                if ok:
                    valid_wallets.append(line)
                else:
                    invalid_count += 1
            if invalid_count:
                print(f"  {C.YELLOW}⚠ {invalid_count} baris tidak valid diabaikan.{C.RESET}")
            if len(valid_wallets) == 0:
                print(f"  {C.RED}✗ Tidak ada wallet valid di file.{C.RESET}")
                continue
            if len(valid_wallets) < total:
                print(f"  {C.YELLOW}⚠ File hanya punya {len(valid_wallets)} wallet, tapi mau buat {total} akun.{C.RESET}")
                print(f"  {C.DIM}Wallet akan dipakai berulang (cycling).{C.RESET}")
                wallets = [valid_wallets[i % len(valid_wallets)] for i in range(total)]
            else:
                wallets = valid_wallets[:total]
            print(f"  {C.GREEN}✓ {len(wallets)} wallet siap dipakai.{C.RESET}")
            break

    # ── Delay antar request ──
    print(f"\n  {C.BOLD}Delay antar request:{C.RESET} {C.DIM}(hindari rate limit server){C.RESET}")
    print(f"  {C.GREEN}[1]{C.RESET} Cepat   — 0.5 detik")
    print(f"  {C.YELLOW}[2]{C.RESET} Normal  — 1 detik  {C.DIM}(direkomendasikan){C.RESET}")
    print(f"  {C.BLUE}[3]{C.RESET} Lambat  — 2 detik")
    print(f"  {C.DIM}[4]{C.RESET} Custom\n")

    while True:
        d = safe_input(f"  Pilih delay (1/2/3/4, default=2): ").strip() or "2"
        if   d == "1": delay = 0.5; break
        elif d == "2": delay = 1.0; break
        elif d == "3": delay = 2.0; break
        elif d == "4":
            raw_d = safe_input("  Delay (detik, contoh: 1.5): ").strip()
            try:
                delay = float(raw_d)
                if delay < 0: raise ValueError
                break
            except ValueError:
                print(f"  {C.RED}✗ Masukkan angka positif.{C.RESET}")
        else:
            print(f"  {C.RED}✗ Pilih 1–4.{C.RESET}")

    # ── Konfirmasi ──
    print(f"\n  {'─'*53}")
    print(f"  {C.BOLD}RINGKASAN:{C.RESET}")
    print(f"  Jumlah akun  : {C.BOLD}{total}{C.RESET}")
    print(f"  Mode nama    : {['Prefix otomatis','Manual','Server auto'][int(mode_name)-1]}")
    print(f"  Mode wallet  : {['Satu untuk semua','Per akun','Dari file'][int(mode_wallet)-1]}")
    print(f"  Delay        : {delay} detik/akun  {C.DIM}(est. {total*delay:.0f}s total){C.RESET}")
    print(f"  {'─'*53}\n")

    if safe_input(f"  {C.YELLOW}Mulai buat {total} akun? (y/n):{C.RESET} ").strip().lower() != "y":
        print(f"  {C.YELLOW}Dibatalkan.{C.RESET}")
        return

    # ── Eksekusi ──
    print(f"\n  {C.BOLD}{'═'*57}{C.RESET}")
    results = {"berhasil": 0, "gagal": 0, "records": []}

    for i in range(total):
        name   = names[i]
        wallet = wallets[i]
        label  = name if name else f"(auto_{i+1})"

        print(f"\n  [{i+1}/{total}] {C.BOLD}{label}{C.RESET} | {wallet[:10]}...{wallet[-4:]}", end=" ")

        acc_data = create_account(name, wallet)

        if not acc_data:
            print(f"  {C.RED}✗ GAGAL{C.RESET}")
            results["gagal"] += 1
        else:
            record = {
                "accountId"        : acc_data["accountId"],
                "name"             : acc_data["name"],
                "apiKey"           : acc_data["apiKey"],
                "verificationCode" : acc_data.get("verificationCode", ""),
                "walletAddress"    : wallet,
                "walletSynced"     : True,
                "balance"          : acc_data.get("balance", 0),
                "crossBalanceWei"  : acc_data.get("crossBalanceWei", "0"),
                "totalGames"       : 0,
                "totalWins"        : 0,
                "currentGames"     : [],
                "createdAt"        : acc_data.get("createdAt", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")),
                "lastUpdated"      : datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "notes"            : "bulk_create"
            }
            db["accounts"].append(record)
            save_db(db)
            results["berhasil"] += 1
            results["records"].append(record)
            print(f"\n      {C.GREEN}✓{C.RESET} ID: {acc_data['accountId']} | Key: {acc_data['apiKey'][:18]}...")

        if i < total - 1:
            time.sleep(delay)

    # ── Ringkasan akhir ──
    print(f"\n  {'═'*57}")
    print(f"  {C.BOLD}SELESAI — HASIL BULK CREATE:{C.RESET}")
    print(f"  {C.GREEN}✓ Berhasil : {results['berhasil']}{C.RESET}")
    print(f"  {C.RED}✗ Gagal    : {results['gagal']}{C.RESET}")
    print(f"  Total akun di DB: {C.BOLD}{len(db['accounts'])}{C.RESET}")

    if results["records"]:
        print(f"\n  {C.BOLD}Akun baru:{C.RESET}")
        for r in results["records"]:
            print(f"  • {C.BOLD}{r['name']}{C.RESET} | {r['accountId']} | {r['apiKey'][:22]}...")
        print(f"\n  {C.GREEN}DB tersimpan ke: {DB_FILE}{C.RESET}")


def main_menu():
    global DEBUG_MODE
    migrate_old_db()  # Auto-migrasi dari lokasi lama jika ada

    while True:
        print_banner()
        print(f"""
  {C.BOLD}MENU:{C.RESET}
  {C.GREEN}[1]{C.RESET} Buat akun baru
  {C.GREEN}[2]{C.RESET} Bulk create akun  {C.DIM}← buat banyak akun sekaligus{C.RESET}
  {C.YELLOW}[3]{C.RESET} Import dari API key  {C.DIM}← tambah akun yang sudah ada{C.RESET}
  {C.BLUE}[4]{C.RESET} Update wallet akun
  {C.CYAN}[5]{C.RESET} Lihat semua akun
  {C.YELLOW}[6]{C.RESET} Refresh data dari server
  {C.MAGENTA}[7]{C.RESET} Export / Backup database
  {C.RED}[8]{C.RESET} Hapus akun dari DB lokal
  {C.GREEN}[9]{C.RESET} Tampilkan isi JSON database
  {C.BLUE}[10]{C.RESET} Info & lokasi file database
  {C.DIM}[d]{C.RESET} Toggle debug ({C.GREEN+'ON' if DEBUG_MODE else 'OFF'}{C.RESET})
  {C.BOLD}[0]{C.RESET} Keluar
""")
        choice = safe_input(f"  {C.BOLD}Pilih:{C.RESET} ").strip().lower()

        if   choice == "1":  flow_create_account()
        elif choice == "2":  flow_bulk_create()
        elif choice == "3":  flow_import_account()
        elif choice == "4":  flow_update_wallet()
        elif choice == "5":  flow_list_accounts()
        elif choice == "6":  flow_refresh_all()
        elif choice == "7":  flow_export()
        elif choice == "8":  flow_delete_account()
        elif choice == "9":  flow_show_db()
        elif choice == "10": flow_db_info()
        elif choice == "d":
            DEBUG_MODE = not DEBUG_MODE
            print(f"\n  Debug: {C.GREEN+'ON' if DEBUG_MODE else C.YELLOW+'OFF'}{C.RESET}")
        elif choice == "0":
            print(f"\n{C.GREEN}Sampai jumpa!{C.RESET}\n")
            sys.exit(0)
        else:
            print(f"\n{C.RED}Pilihan tidak valid.{C.RESET}")

        if choice != "0":
            safe_input(f"\n  {C.YELLOW}[Tekan Enter untuk kembali ke menu...]{C.RESET}")


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

def run():
    """Entry point dengan global error handling."""
    try:
        parser = argparse.ArgumentParser(description="Molty Royale Account Manager")
        parser.add_argument("--create",  action="store_true")
        parser.add_argument("--bulk",    action="store_true")
        parser.add_argument("--list",    action="store_true")
        parser.add_argument("--refresh", action="store_true")
        parser.add_argument("--export",  action="store_true")
        parser.add_argument("--showdb",  action="store_true")
        parser.add_argument("--debug",   action="store_true")
        args = parser.parse_args()

        if args.debug:
            global DEBUG_MODE
            DEBUG_MODE = True

        migrate_old_db()

        if   args.create  : flow_create_account()
        elif args.bulk    : flow_bulk_create()
        elif args.list    : flow_list_accounts()
        elif args.refresh : flow_refresh_all()
        elif args.export  : flow_export()
        elif args.showdb  : flow_show_db()
        else              : main_menu()

    except KeyboardInterrupt:
        print(f"\n\n{C.YELLOW}Keluar... Sampai jumpa!{C.RESET}\n")
        sys.exit(0)
    except Exception as e:
        print(f"\n{C.RED}[ERROR TIDAK TERDUGA]{C.RESET} {e}")
        if DEBUG_MODE:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run()
