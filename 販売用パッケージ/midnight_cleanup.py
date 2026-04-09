#!/usr/bin/env python3
"""Midnight cleanup - clears last_error and old data from storage.json (multi-user)"""
import json, os
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

JST = timezone(timedelta(hours=9))
now = datetime.now(JST).replace(tzinfo=None)
today = now.strftime("%Y-%m-%d")

if not os.path.isdir(DATA_DIR):
    print(f"[{now.isoformat()}] DATA_DIR not found: {DATA_DIR}")
    exit(1)

total_changed = 0
for user_id in sorted(os.listdir(DATA_DIR)):
    user_dir = os.path.join(DATA_DIR, user_id)
    if not os.path.isdir(user_dir):
        continue
    storage_path = os.path.join(user_dir, "storage.json")
    if not os.path.exists(storage_path):
        continue
    try:
        with open(storage_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        changed = False
        for p in data:
            if p.get("last_error"):
                p["last_error"] = ""
                changed = True
            # Reset today_count if today_date is not today
            if p.get("today_date") and p["today_date"] != today:
                p["today_count"] = 0
                p["today_date"] = today
                changed = True
        if changed:
            with open(storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"[{now.isoformat()}] User {user_id}: cleanup done")
            total_changed += 1
        else:
            print(f"[{now.isoformat()}] User {user_id}: nothing to clean")
    except Exception as e:
        print(f"[{now.isoformat()}] User {user_id}: Error - {e}")

print(f"[{now.isoformat()}] Finished. {total_changed} user(s) updated.")
