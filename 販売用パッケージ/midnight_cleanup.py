#!/usr/bin/env python3
"""Midnight cleanup - clears last_error and old data from storage.json"""
import json
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
now = datetime.now(JST).replace(tzinfo=None)
today = now.strftime("%Y-%m-%d")

STORAGE = "/root/storage.json"
try:
    with open(STORAGE, "r", encoding="utf-8") as f:
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
        with open(STORAGE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[{now.isoformat()}] Cleanup done")
    else:
        print(f"[{now.isoformat()}] Nothing to clean")
except Exception as e:
    print(f"[{now.isoformat()}] Error: {e}")
