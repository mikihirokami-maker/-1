#!/usr/bin/env python3
"""storage.json watchdog - 全ユーザーの消失・破損を即検知して自動復元 (multi-user)"""
import json, shutil, time, os, logging
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

MIN_ENTRIES = 100  # これ以下になったら異常
CHECK_INTERVAL = 30  # 30秒ごとにチェック

JST = timezone(timedelta(hours=9))
logging.basicConfig(
    filename=os.path.join(BASE_DIR, "storage_watchdog.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

def get_entry_count(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            return len(data)
    except:
        pass
    return -1

def restore_from_best_backup(user_dir, storage_path):
    """最も良いバックアップから復元"""
    candidates = [
        storage_path + ".daily_bak",
        storage_path + ".auto_bak",
        storage_path + ".safety_bak",
        storage_path + ".bak",
    ]
    for bak in candidates:
        count = get_entry_count(bak)
        if count >= MIN_ENTRIES:
            shutil.copy2(bak, storage_path)
            logging.warning(f"RESTORED from {bak} ({count} entries)")
            return True, bak, count
    return False, None, 0

def daily_backup(user_id, storage_path):
    """1日1回のバックアップ"""
    daily_bak = storage_path + ".daily_bak"
    count = get_entry_count(storage_path)
    if count >= MIN_ENTRIES:
        shutil.copy2(storage_path, daily_bak)
        logging.info(f"User {user_id}: Daily backup saved ({count} entries)")

# Track per-user state
last_daily = {}      # user_id -> date
last_good_count = {} # user_id -> int

logging.info("Watchdog started (multi-user mode)")

while True:
    try:
        now = datetime.now(JST)

        if not os.path.isdir(DATA_DIR):
            logging.error(f"DATA_DIR not found: {DATA_DIR}")
            time.sleep(CHECK_INTERVAL)
            continue

        for user_id in sorted(os.listdir(DATA_DIR)):
            user_dir = os.path.join(DATA_DIR, user_id)
            if not os.path.isdir(user_dir):
                continue
            storage_path = os.path.join(user_dir, "storage.json")
            if not os.path.exists(storage_path):
                continue

            try:
                # 1日1回バックアップ (6時)
                if last_daily.get(user_id) != now.date() and now.hour >= 6:
                    count = get_entry_count(storage_path)
                    if count >= MIN_ENTRIES:
                        daily_backup(user_id, storage_path)
                        last_daily[user_id] = now.date()

                # storage.jsonチェック
                count = get_entry_count(storage_path)

                if count < 0:
                    # ファイルが壊れている
                    logging.error(f"User {user_id}: storage.json CORRUPTED! Restoring...")
                    ok, src, n = restore_from_best_backup(user_dir, storage_path)
                    if ok:
                        logging.warning(f"User {user_id}: Auto-restored from {src} ({n} entries)")
                    else:
                        logging.critical(f"User {user_id}: NO VALID BACKUP FOUND!")
                elif count < MIN_ENTRIES:
                    # エントリが激減
                    logging.error(f"User {user_id}: storage.json has only {count} entries (expected {MIN_ENTRIES}+)! Restoring...")
                    ok, src, n = restore_from_best_backup(user_dir, storage_path)
                    if ok:
                        logging.warning(f"User {user_id}: Auto-restored from {src} ({n} entries)")
                    else:
                        logging.critical(f"User {user_id}: NO VALID BACKUP FOUND!")
                else:
                    prev = last_good_count.get(user_id, 0)
                    if count != prev and prev > 0:
                        logging.info(f"User {user_id}: storage.json OK: {count} entries")
                    last_good_count[user_id] = count
            except Exception as e:
                logging.error(f"User {user_id}: check error: {e}")

    except Exception as e:
        logging.error(f"Watchdog error: {e}")

    time.sleep(CHECK_INTERVAL)
