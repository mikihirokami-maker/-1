#!/usr/bin/env python3
"""storage.json watchdog - 消失を即検知して自動復元"""
import json, shutil, time, os, logging
from datetime import datetime, timezone, timedelta

STORAGE = "/root/storage.json"
AUTO_BAK = STORAGE + ".auto_bak"
DAILY_BAK = STORAGE + ".daily_bak"
MIN_ENTRIES = 100  # これ以下になったら異常
CHECK_INTERVAL = 30  # 30秒ごとにチェック

JST = timezone(timedelta(hours=9))
logging.basicConfig(
    filename="/root/storage_watchdog.log",
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

def restore_from_best_backup():
    """最も良いバックアップから復元"""
    candidates = [
        DAILY_BAK,
        AUTO_BAK,
        STORAGE + ".safety_bak",
        STORAGE + ".bak",
    ]
    for bak in candidates:
        count = get_entry_count(bak)
        if count >= MIN_ENTRIES:
            shutil.copy2(bak, STORAGE)
            logging.warning(f"RESTORED from {bak} ({count} entries)")
            return True, bak, count
    return False, None, 0

def daily_backup():
    """1日1回のバックアップ"""
    count = get_entry_count(STORAGE)
    if count >= MIN_ENTRIES:
        shutil.copy2(STORAGE, DAILY_BAK)
        logging.info(f"Daily backup saved ({count} entries)")

last_daily = None
last_good_count = 0

logging.info("Watchdog started")

while True:
    try:
        now = datetime.now(JST)
        
        # 1日1回バックアップ (6時)
        if last_daily != now.date() and now.hour >= 6:
            count = get_entry_count(STORAGE)
            if count >= MIN_ENTRIES:
                daily_backup()
                last_daily = now.date()
        
        # storage.jsonチェック
        count = get_entry_count(STORAGE)
        
        if count < 0:
            # ファイルが壊れている
            logging.error(f"storage.json CORRUPTED! Restoring...")
            ok, src, n = restore_from_best_backup()
            if ok:
                logging.warning(f"Auto-restored from {src} ({n} entries)")
            else:
                logging.critical("NO VALID BACKUP FOUND!")
        elif count < MIN_ENTRIES:
            # エントリが激減
            logging.error(f"storage.json has only {count} entries (expected {MIN_ENTRIES}+)! Restoring...")
            ok, src, n = restore_from_best_backup()
            if ok:
                logging.warning(f"Auto-restored from {src} ({n} entries)")
            else:
                logging.critical("NO VALID BACKUP FOUND!")
        else:
            if count != last_good_count and last_good_count > 0:
                logging.info(f"storage.json OK: {count} entries")
            last_good_count = count
    except Exception as e:
        logging.error(f"Watchdog error: {e}")
    
    time.sleep(CHECK_INTERVAL)
