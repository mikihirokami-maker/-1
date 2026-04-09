# -*- coding: utf-8 -*-
import time
import random
import requests
import json
import os
import traceback
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCK_FILE = os.path.join(BASE_DIR, "worker.lock")

# === Prevent duplicate worker processes ===
import fcntl
_lock_fp = open(LOCK_FILE, "w")
try:
    fcntl.flock(_lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
    _lock_fp.write(str(os.getpid()))
    _lock_fp.flush()
except IOError:
    print("Another worker is already running. Exiting.")
    import sys
    sys.exit(0)
ACCOUNTS_FILE = os.path.join(BASE_DIR, "accounts.json")
STORAGE_FILE = os.path.join(BASE_DIR, "storage.json")
SCHEDULED_REPOSTS_FILE = os.path.join(BASE_DIR, "scheduled_reposts.json")
REPEAT_POSTS_FILE = os.path.join(BASE_DIR, "repeat_posts.json")
TOKEN_REFRESH_FILE = os.path.join(BASE_DIR, "token_refresh.json")
ERROR_LOG_FILE = os.path.join(BASE_DIR, "error_log.json")
MAX_CONSECUTIVE_RETRIES = 5  # Give up after this many retries per post

# Thread-safe file lock
_file_lock = threading.Lock()

# --- Proxy Settings (IPRoyal Residential Rotating) ---
PROXY_HOST = ""  # プロキシホスト（例: geo.iproyal.com）
PROXY_PORT = ""  # プロキシポート（例: 12321）
PROXY_USER = ""  # プロキシユーザー名
PROXY_PASS = ""  # プロキシパスワード

MAX_WORKERS = 5  # Parallel posting threads

def get_proxy(account=None):
    """Get proxy with sticky IP per account (same account = same IP).
    Without account, uses random rotating IP.
    IPRoyal format: session params go in PASSWORD, session ID must be 8 alphanumeric chars."""
    if account and account.get('ip_slot') is not None:
        import hashlib
        slot = account['ip_slot']
        session_id = hashlib.md5(f"acc{slot}".encode()).hexdigest()[:8]
        password = f"{PROXY_PASS}_country-jp_session-{session_id}_lifetime-24h"
    else:
        password = PROXY_PASS
    proxy_url = f"http://{PROXY_USER}:{password}@{PROXY_HOST}:{PROXY_PORT}"
    return {"http": proxy_url, "https": proxy_url}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/131.0.0.0 Mobile Safari/537.36",
]

def get_safe_session():
    s = requests.Session()
    s.headers.update({"User-Agent": random.choice(USER_AGENTS)})
    return s

def get_jst_time():
    return datetime.now(timezone(timedelta(hours=9)))

def load_json(file_path):
    with _file_lock:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return []
        return []

def save_json(file_path, data):
    with _file_lock:
        # storage.json の保護: エントリ数が50%以下に激減したら保存をブロック
        if file_path.endswith("storage.json") and isinstance(data, list):
            try:
                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        old_data = json.load(f)
                    if isinstance(old_data, list) and len(old_data) > 20:
                        ratio = len(data) / len(old_data)
                        if ratio < 0.5:
                            import shutil
                            bak_path = file_path + ".safety_bak"
                            shutil.copy2(file_path, bak_path)
                            logging.error(f"storage.json save BLOCKED: {len(old_data)} -> {len(data)} entries (ratio {ratio:.2f}). Backup: {bak_path}")
                            return
            except Exception:
                pass
        # 保存前に自動バックアップ（storage.json のみ）
        if file_path.endswith("storage.json") and os.path.exists(file_path):
            try:
                import shutil
                shutil.copy2(file_path, file_path + ".auto_bak")
            except Exception:
                pass
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def safe_save_storage(worker_storage, original_len):
    """Save storage while preserving new entries added by my_bot.py."""
    import shutil, tempfile
    with _file_lock:
        try:
            with open(STORAGE_FILE, 'r', encoding='utf-8') as f:
                latest = json.load(f)
        except:
            latest = []
        # Preserve entries my_bot.py added after worker loaded
        if len(latest) > original_len:
            worker_storage.extend(latest[original_len:])
        # 0件保存防止
        if len(worker_storage) == 0 and os.path.exists(STORAGE_FILE):
            logging.error("storage.json 0件保存をブロックしました")
            return
        # 自動バックアップ
        if os.path.exists(STORAGE_FILE):
            try:
                shutil.copy2(STORAGE_FILE, STORAGE_FILE + ".auto_bak")
            except:
                pass
        # アトミック書き込み
        dir_name = os.path.dirname(STORAGE_FILE) or "."
        try:
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(worker_storage, f, ensure_ascii=False, indent=2)
            shutil.move(tmp_path, STORAGE_FILE)
        except Exception as e:
            logging.error(f"Atomic save failed: {e}")
            try:
                os.unlink(tmp_path)
            except:
                pass
            with open(STORAGE_FILE, 'w', encoding='utf-8') as f:
                json.dump(worker_storage, f, ensure_ascii=False, indent=2)

def safe_save_accounts(worker_accounts, original_len):
    """Save accounts while preserving new accounts added by my_bot.py
    and respecting accounts deleted by my_bot.py."""
    with _file_lock:
        try:
            with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
                latest = json.load(f)
        except:
            latest = []
        # Get usernames currently in the file (source of truth for deletions)
        latest_usernames = {a.get('username') for a in latest if a.get('username')}
        # Remove accounts from worker that were deleted via my_bot.py
        worker_accounts = [a for a in worker_accounts if a.get('username') in latest_usernames]
        # Add any new accounts that my_bot.py added after worker loaded
        worker_usernames = {a.get('username') for a in worker_accounts if a.get('username')}
        for a in latest:
            if a.get('username') and a['username'] not in worker_usernames:
                worker_accounts.append(a)
        with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(worker_accounts, f, ensure_ascii=False, indent=2)

def find_account_by_username(accounts, username):
    """Find account by username. Returns (index, account) or (-1, None)."""
    if not username:
        return -1, None
    for i, acc in enumerate(accounts):
        if acc.get('username') == username:
            return i, acc
    return -1, None

def schedule_next_run(time_range, posts_per_day=1, today_count=0, post_interval=None):
    """Schedule next run: within today if more posts needed, else tomorrow.
    post_interval: fixed hours between posts (None = auto even spacing)."""
    s, e = time_range
    now = get_jst_time()
    today_str = now.strftime('%Y-%m-%d')

    if today_count < posts_per_day:
        current_hour = now.hour + now.minute / 60.0
        # Only schedule today if still within time range
        if current_hour < e:
            if post_interval is not None:
                # Fixed interval between posts
                next_hour = current_hour + post_interval
            else:
                # Auto even spacing
                remaining = posts_per_day - today_count
                hours_left = e - current_hour
                interval = hours_left / (remaining + 1)
                next_hour = current_hour + max(interval, 0.5)

            next_h = int(next_hour)
            next_m = int((next_hour - next_h) * 60) + random.randint(0, 5)
            if next_h >= e:
                next_h = e - 1 if e > s else s
                next_m = random.randint(0, 59)

            return now.replace(hour=next_h, minute=min(next_m, 59), second=0).isoformat(), today_str

    # Schedule for tomorrow
    tomorrow = now + timedelta(days=1)
    h = random.randint(s, max(s, min(e, 23)))
    next_run = tomorrow.replace(hour=h, minute=random.randint(0, 59), second=0).isoformat()
    tomorrow_str = tomorrow.strftime('%Y-%m-%d')
    return next_run, tomorrow_str

def refresh_tokens_if_needed(accounts, orig_len=None):
    """Auto refresh tokens every 50 days (for permanent operation)"""
    refresh_data = {}
    if os.path.exists(TOKEN_REFRESH_FILE):
        try:
            with open(TOKEN_REFRESH_FILE, 'r', encoding='utf-8') as f:
                refresh_data = json.load(f)
        except:
            refresh_data = {}

    now = get_jst_time()
    updated = False

    for i, acc in enumerate(accounts):
        if not acc.get('app_secret'):
            continue

        acc_id = acc.get('id', str(i))
        last_refresh = refresh_data.get(acc_id)

        should_refresh = False
        if not last_refresh:
            should_refresh = True
        else:
            try:
                last_dt = datetime.fromisoformat(last_refresh)
                if (now - last_dt).days >= 50:
                    should_refresh = True
            except:
                should_refresh = True

        if should_refresh:
            try:
                # Try with proxy first, fallback to direct
                try:
                    res = requests.get(
                        "https://graph.threads.net/refresh_access_token",
                        params={'grant_type': 'th_refresh_token', 'access_token': acc['token']},
                        proxies=get_proxy(acc), timeout=15
                    ).json()
                except:
                    res = requests.get(
                        "https://graph.threads.net/refresh_access_token",
                        params={'grant_type': 'th_refresh_token', 'access_token': acc['token']},
                        timeout=15
                    ).json()

                new_token = res.get('access_token')
                if new_token:
                    acc['token'] = new_token
                    refresh_data[acc_id] = now.isoformat()
                    updated = True
                    print(f"[{now.strftime('%H:%M:%S')}] Token refreshed: {acc.get('name', acc_id)}")
            except Exception as e:
                print(f"[{now.strftime('%H:%M:%S')}] Token refresh failed: {acc.get('name', acc_id)} - {e}")

    if updated:
        if orig_len is not None:
            safe_save_accounts(accounts, orig_len)
        else:
            save_json(ACCOUNTS_FILE, accounts)
        with _file_lock:
            with open(TOKEN_REFRESH_FILE, 'w', encoding='utf-8') as f:
                json.dump(refresh_data, f, ensure_ascii=False, indent=2)

    return accounts

def classify_error(error_msg):
    """Classify error type for smart auto-fix."""
    msg = error_msg.lower()
    if any(w in msg for w in ['rate limit', 'too many', '429', 'throttl', 'limit reached']):
        return 'RATE_LIMIT'
    if any(w in msg for w in ['token', 'oauth', 'expired', 'invalid access', 'oauthexception']):
        return 'TOKEN_ERROR'
    if any(w in msg for w in ['image', 'upload', 'imgur', 'catbox', 'file_not_found', 'upload_failed', 'file not found']):
        return 'IMAGE_ERROR'
    if any(w in msg for w in ['network', 'timeout', 'connection', 'socket', 'resolve']):
        return 'NETWORK_ERROR'
    if any(w in msg for w in ['publish', 'media_not_ready', 'media not ready']):
        return 'PUBLISH_ERROR'
    return 'UNKNOWN'

def log_error(acc_name, error_type, error_msg, action_taken):
    """Log error to error_log.json for monitoring (keeps last 100 entries)."""
    try:
        now = get_jst_time()
        log = []
        if os.path.exists(ERROR_LOG_FILE):
            try:
                with open(ERROR_LOG_FILE, 'r', encoding='utf-8') as f:
                    log = json.load(f)
            except:
                log = []
        log.append({
            'time': now.strftime('%Y-%m-%d %H:%M:%S'),
            'account': acc_name,
            'type': error_type,
            'error': error_msg[:100],
            'action': action_taken
        })
        # Keep only today's entries
        today_str = now.strftime('%Y-%m-%d')
        log = [e for e in log if e.get('time', '').startswith(today_str)]
        with open(ERROR_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
    except:
        pass

def auto_fix_and_reschedule(p, acc, error_type, error_msg):
    """Smart auto-fix based on error type. Returns (updated_p, action_description)."""
    now = get_jst_time()
    retry_count = p.get('retry_count', 0)

    # Give up after too many retries — schedule for tomorrow
    if retry_count >= MAX_CONSECUTIVE_RETRIES:
        time_range = p.get('time_range', [12, 15])
        tomorrow = now + timedelta(days=1)
        h = random.randint(time_range[0], max(time_range[0], min(time_range[1], 23)))
        p['next_run'] = tomorrow.replace(hour=h, minute=random.randint(0, 59), second=0).isoformat()
        p['retry_count'] = 0
        p.pop('_fallback_text_only', None)
        return p, f'MAX_RETRY({MAX_CONSECUTIVE_RETRIES}回) → 明日に延期'

    if error_type == 'RATE_LIMIT':
        # Exponential backoff: 30, 60, 90, 120, 150 min
        wait_min = 30 * (retry_count + 1)
        p['next_run'] = (now + timedelta(minutes=wait_min)).isoformat()
        p['retry_count'] = retry_count + 1
        return p, f'レート制限 → {wait_min}分後にリトライ'

    elif error_type == 'TOKEN_ERROR':
        # Force token refresh and retry in 5 min
        acc_idx = p.get('acc_idx', -1)
        try:
            accounts = load_json(ACCOUNTS_FILE)
            if acc_idx < len(accounts) and accounts[acc_idx].get('app_secret'):
                a = accounts[acc_idx]
                res = requests.get(
                    "https://graph.threads.net/refresh_access_token",
                    params={'grant_type': 'th_refresh_token', 'access_token': a['token']},
                    timeout=15
                ).json()
                new_token = res.get('access_token')
                if new_token:
                    accounts[acc_idx]['token'] = new_token
                    save_json(ACCOUNTS_FILE, accounts)
                    print(f"  [AUTO-FIX] Token refreshed for {acc.get('name', '')}")
                    p['next_run'] = (now + timedelta(minutes=5)).isoformat()
                    p['retry_count'] = retry_count + 1
                    return p, 'トークン自動更新 → 5分後にリトライ'
        except Exception as e:
            print(f"  [AUTO-FIX] Token refresh failed: {e}")
        # Fallback: longer wait
        p['next_run'] = (now + timedelta(minutes=60)).isoformat()
        p['retry_count'] = retry_count + 1
        return p, 'トークンエラー → 60分後にリトライ'

    elif error_type == 'IMAGE_ERROR':
        if retry_count >= 2:
            # After 2 image failures, try text-only as fallback
            p['_fallback_text_only'] = True
            p['next_run'] = (now + timedelta(minutes=5)).isoformat()
            p['retry_count'] = retry_count + 1
            return p, '画像3回失敗 → テキストのみでリトライ'
        else:
            p['next_run'] = (now + timedelta(minutes=15)).isoformat()
            p['retry_count'] = retry_count + 1
            return p, f'画像エラー → 15分後にリトライ ({retry_count+1}回目)'

    elif error_type == 'NETWORK_ERROR':
        # Short backoff for network issues: 5, 10, 15, 20, 25 min
        wait_min = 5 * (retry_count + 1)
        p['next_run'] = (now + timedelta(minutes=wait_min)).isoformat()
        p['retry_count'] = retry_count + 1
        return p, f'ネットワークエラー → {wait_min}分後にリトライ'

    elif error_type == 'PUBLISH_ERROR':
        # Publish errors need longer wait (media processing)
        wait_min = 20 * (retry_count + 1)
        p['next_run'] = (now + timedelta(minutes=wait_min)).isoformat()
        p['retry_count'] = retry_count + 1
        return p, f'公開エラー → {wait_min}分後にリトライ'

    else:
        p['next_run'] = (now + timedelta(minutes=15)).isoformat()
        p['retry_count'] = retry_count + 1
        return p, f'不明エラー → 15分後にリトライ ({retry_count+1}回目)'


def upload_image(image_path, account=None):
    """Save image locally and serve via YOUR_SERVER_IP"""
    # HTTP URLの場合、非対応形式ならダウンロードしてJPEGに変換
    if isinstance(image_path, str) and image_path.startswith("http"):
        url_lower = image_path.lower().split('?')[0]
        if url_lower.endswith(('.jpg', '.jpeg', '.png', '.mp4')):
            return image_path
        # 非対応形式 or 拡張子不明 → ダウンロードしてJPEG変換
        try:
            import hashlib
            from PIL import Image as PILImage
            import io
            IMAGE_DIR_HTTP = "/root/images"
            IMAGE_BASE_URL_HTTP = "http://YOUR_SERVER_IP/images"
            os.makedirs(IMAGE_DIR_HTTP, exist_ok=True)
            resp = requests.get(image_path, timeout=30)
            img = PILImage.open(io.BytesIO(resp.content)).convert('RGB')
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=90)
            data = buf.getvalue()
            fname = hashlib.md5(data).hexdigest() + '.jpg'
            dest = os.path.join(IMAGE_DIR_HTTP, fname)
            if not os.path.exists(dest):
                with open(dest, 'wb') as f:
                    f.write(data)
            return f"{IMAGE_BASE_URL_HTTP}/{fname}"
        except:
            return image_path  # 変換失敗時は元URLをそのまま返す

    IMAGE_DIR = "/root/images"
    IMAGE_BASE_URL = "http://YOUR_SERVER_IP/images"
    os.makedirs(IMAGE_DIR, exist_ok=True)

    if os.path.isabs(image_path):
        abs_path = image_path
    else:
        abs_path = os.path.join(BASE_DIR, image_path)
    if not os.path.exists(abs_path):
        return "FILE_NOT_FOUND"

    try:
        import hashlib
        from PIL import Image as PILImage
        import io
        ext = os.path.splitext(abs_path)[1].lower()
        # Threads APIはJPEG/PNGのみ対応。非対応形式はJPEGに変換
        if ext not in ('.jpg', '.jpeg', '.png', '.mp4'):
            img = PILImage.open(abs_path).convert('RGB')
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=90)
            data = buf.getvalue()
            ext = '.jpg'
        else:
            with open(abs_path, 'rb') as f:
                data = f.read()
        fname = hashlib.md5(data).hexdigest() + ext
        dest = os.path.join(IMAGE_DIR, fname)
        if not os.path.exists(dest):
            with open(dest, 'wb') as f:
                f.write(data)
        return f"{IMAGE_BASE_URL}/{fname}"
    except:
        return "UPLOAD_FAILED"

def post_to_threads(account, text, image_paths=None):
    user_id, token = account['id'], account['token']
    proxies = get_proxy(account)
    session = get_safe_session()
    media_urls = []
    video_flags = []  # True if video, False if image

    if image_paths:
        for i, img_p in enumerate(image_paths):
            u = upload_image(img_p, account)
            if u == "FILE_NOT_FOUND":
                return False, f"Media error: file {i+1} not found"
            elif u == "UPLOAD_FAILED" or not u:
                return False, f"Media upload error: file {i+1} failed"
            else:
                media_urls.append(u)
                is_vid = img_p.lower().endswith('.mp4') or u.lower().endswith('.mp4')
                video_flags.append(is_vid)
            time.sleep(2)

        if len(media_urls) != len(image_paths):
            return False, "Some media failed to prepare"

    def _post(url, data):
        """POST with proxy fallback"""
        try:
            return session.post(url, data=data, proxies=proxies, timeout=30).json()
        except:
            return session.post(url, data=data, timeout=30).json()

    base_url = f"https://graph.threads.net/v1.0/{user_id}/threads"
    try:
        if media_urls:
            if len(media_urls) == 1:
                if video_flags[0]:
                    res = _post(base_url, {
                        'access_token': token, 'media_type': 'VIDEO',
                        'video_url': media_urls[0], 'text': text
                    })
                else:
                    res = _post(base_url, {
                        'access_token': token, 'media_type': 'IMAGE',
                        'image_url': media_urls[0], 'text': text
                    })
            else:
                child_ids = []
                for i, u in enumerate(media_urls):
                    cr = None
                    for _retry in range(3):
                        if video_flags[i]:
                            cr = _post(base_url, {
                                'access_token': token, 'media_type': 'VIDEO',
                                'video_url': u, 'is_carousel_item': 'true'
                            })
                        else:
                            cr = _post(base_url, {
                                'access_token': token, 'media_type': 'IMAGE',
                                'image_url': u, 'is_carousel_item': 'true'
                            })
                        if 'id' in cr:
                            break
                        print(f"    Carousel item {i+1} retry {_retry+1}/3: {str(cr)[:100]}")
                        time.sleep(30)
                    if 'id' in cr:
                        child_ids.append(cr['id'])
                    else:
                        return False, f"Carousel item {i+1} failed after 3 retries: {cr}"
                    time.sleep(2)
                res = _post(base_url, {
                    'access_token': token, 'media_type': 'CAROUSEL',
                    'children': ','.join(child_ids), 'text': text
                })
        else:
            res = _post(base_url, {
                'access_token': token, 'media_type': 'TEXT', 'text': text
            })

        cid = res.get('id')
        if not cid:
            return False, f"Send error: {res.get('error', {}).get('message', 'unknown')}"

        pub_err = "unknown"
        for _poll in range(30):
            time.sleep(3)
            try:
                _st = requests.get(f"https://graph.threads.net/v1.0/{cid}",
                    params={"fields": "status", "access_token": token}, timeout=10).json()
                _status = _st.get("status", "")
                if _status == "FINISHED":
                    pub = _post(
                        f"https://graph.threads.net/v1.0/{user_id}/threads_publish",
                        {'creation_id': cid, 'access_token': token}
                    )
                    if 'id' in pub:
                        return True, "Success"
                    pub_err = pub.get('error', {}).get('message', str(pub))
                    break
                elif _status in ("ERROR", "EXPIRED"):
                    return False, f"Container {_status}: {_st}"
                else:
                    print(f"    Container status: {_status}, polling...")
            except Exception as pe:
                pub_err = str(pe)
        else:
            try:
                pub = _post(
                    f"https://graph.threads.net/v1.0/{user_id}/threads_publish",
                    {'creation_id': cid, 'access_token': token}
                )
                if 'id' in pub:
                    return True, "Success"
                pub_err = pub.get('error', {}).get('message', str(pub))
            except Exception as pe:
                pub_err = str(pe)
        return False, f"Publish error: {pub_err}"
    except Exception as e:
        return False, f"Network error: {e}"


def process_single_post(p, p_idx, accounts):
    """Process a single scheduled post. Returns (p_idx, updated_p, updated_acc, success)."""
    now = get_jst_time()
    today_str = now.strftime('%Y-%m-%d')

    # username-based lookup (with acc_idx fallback for old data)
    acc_username = p.get('acc_username')
    if acc_username:
        acc_real_idx, acc = find_account_by_username(accounts, acc_username)
        if acc is None:
            return p_idx, p, None, False
    else:
        if p.get('acc_idx', -1) >= len(accounts) or p.get('acc_idx', -1) < 0:
            return p_idx, p, None, False
        acc_real_idx = p['acc_idx']
        acc = accounts[acc_real_idx]
    if not acc.get('active', True):
        return p_idx, p, None, False

    if 'metrics' not in acc:
        acc['metrics'] = {'attempts': 0, 'successes': 0, 'failures': 0, 'last_error': 'None'}

    posts_per_day = p.get('posts_per_day', 1)

    # Reset daily counter if new day
    if p.get('today_date', '') != today_str:
        p['today_count'] = 0
        p['today_date'] = today_str

    today_count = p.get('today_count', 0)

    # Skip if already reached daily limit
    if today_count >= posts_per_day:
        return p_idx, p, None, False

    # Duplicate post prevention (skip if ANY entry for same account posted within 60 min)
    _dup_uname = acc.get('username', '')
    try:
        dup_storage = load_json(STORAGE_FILE)
        for dup_entry in dup_storage:
            if dup_entry.get('acc_username') == _dup_uname or (not dup_entry.get('acc_username') and dup_entry.get('acc_idx') == p.get('acc_idx')):
                dup_lp = dup_entry.get('last_posted_at')
                if dup_lp:
                    dup_lp_time = datetime.fromisoformat(dup_lp)
                    if (now - dup_lp_time).total_seconds() < 3600:
                        return p_idx, p, None, False
    except:
        pass

    acc_name = acc.get('name', acc.get('username', '?'))

    # 合間機能: cross-entry interval check (ボックス24時間=fixed_timeありはスキップ)
    post_interval = p.get('post_interval')
    if post_interval and not p.get('fixed_time'):
        try:
            current_storage = load_json(STORAGE_FILE)
            for sp in current_storage:
                if sp.get('acc_username') == _dup_uname or (not sp.get('acc_username') and sp.get('acc_idx') == p.get('acc_idx')):
                    sp_lp = sp.get('last_posted_at')
                    if sp_lp:
                        sp_lp_time = datetime.fromisoformat(sp_lp)
                        hours_since = (now - sp_lp_time).total_seconds() / 3600
                        if hours_since < post_interval:
                            print(f"  [{now.strftime('%H:%M')}] {acc_name}: 合間制限スキップ ({hours_since:.1f}h < {post_interval}h)")
                            # Reschedule
                            wait_until = sp_lp_time + timedelta(hours=post_interval)
                            p['next_run'] = wait_until.isoformat()
                            return p_idx, p, None, False
        except:
            pass

    # next_run check is already done in main loop, skip here
    # (safety lock sets next_run to future before calling this function)

    print(f"[{now.strftime('%H:%M:%S')}] Posting: {acc_name} (today {today_count+1}/{posts_per_day})")

    acc['metrics']['attempts'] += 1

    # Get current post (support rotation queue)
    post_text = p.get('text', '')
    post_images = p.get('saved_image_paths', [])
    posts_queue = p.get('posts', [])
    current_idx = p.get('current_idx', 0)
    if posts_queue:
        current_idx = current_idx % len(posts_queue)
        current_post = posts_queue[current_idx]
        post_text = current_post.get('text', '')
        post_images = current_post.get('saved_image_paths', [])
        print(f"  Queue: posting #{current_idx+1}/{len(posts_queue)}")

    # Fallback: text-only if image failed too many times
    use_images = post_images
    if p.get('_fallback_text_only') and post_images:
        print(f"  [FALLBACK] Posting text-only (image failed previously)")
        use_images = []

    # Retry entire post up to 3 times
    max_retries = 3
    suc = False
    msg = ""
    for attempt in range(max_retries):
        suc, msg = post_to_threads(acc, post_text, use_images if use_images else None)
        if suc:
            break
        if attempt < max_retries - 1:
            retry_wait = 60 * (attempt + 1) + random.randint(10, 30)
            print(f"  Retry {attempt+2}/{max_retries} in {retry_wait}s: {msg}")
            time.sleep(retry_wait)
    print(f"  Result: {'OK' if suc else 'FAIL'} {msg}")

    if suc:
        p['last_posted_at'] = now.isoformat()
        p['today_count'] = today_count + 1
        p['today_date'] = today_str
        acc['metrics']['successes'] += 1
        acc['metrics']['last_error'] = 'None'
        # If succeeded after previous auto-fix retries, undo the 1 failure count
        prev_retries = p.get('retry_count', 0)
        if prev_retries > 0:
            acc['metrics']['failures'] = max(0, acc['metrics'].get('failures', 0) - 1)
            try:
                if os.path.exists(ERROR_LOG_FILE):
                    with open(ERROR_LOG_FILE, 'r', encoding='utf-8') as f:
                        elog = json.load(f)
                    elog = [e for e in elog if e.get('account') != acc_name]
                    with open(ERROR_LOG_FILE, 'w', encoding='utf-8') as f:
                        json.dump(elog, f, ensure_ascii=False, indent=2)
            except:
                pass
        p['retry_count'] = 0  # Reset retry counter on success
        p.pop('_fallback_text_only', None)  # Clear fallback flag

        # Advance rotation queue
        if posts_queue:
            next_idx = (current_idx + 1) % len(posts_queue)
            p['current_idx'] = next_idx
            p['text'] = posts_queue[next_idx].get('text', '')
            p['saved_image_paths'] = posts_queue[next_idx].get('saved_image_paths', [])

        # Schedule next run
        new_today_count = today_count + 1
        _fixed = p.get('fixed_time')
        if _fixed:
            # 固定時間モード: 翌日の同じ時刻にセット
            _fh, _fm = map(int, _fixed.split(':'))
            _tomorrow = now + timedelta(days=1)
            p['next_run'] = _tomorrow.replace(hour=_fh, minute=_fm, second=0).isoformat()
        else:
            next_run_str, next_date = schedule_next_run(
                p.get('time_range', [12, 15]),
                posts_per_day, new_today_count,
                post_interval=p.get('post_interval')
            )
            p['next_run'] = next_run_str

        # 合間機能: 同アカウントの他エントリーのnext_runもずらす（ボックス24時間はスキップ）
        post_interval_val = p.get('post_interval')
        if post_interval_val and not p.get('fixed_time'):
            min_next = now + timedelta(hours=post_interval_val)
            try:
                current_storage = load_json(STORAGE_FILE)
                _updated = False
                for _si, _se in enumerate(current_storage):
                    _se_match = (_se.get('acc_username') == _dup_uname) if _se.get('acc_username') else (_se.get('acc_idx') == p.get('acc_idx'))
                    if _se_match and _si != p_idx:
                        try:
                            _se_nr = datetime.fromisoformat(_se['next_run'])
                            if _se_nr < min_next:
                                current_storage[_si]['next_run'] = min_next.isoformat()
                                _updated = True
                                print(f"  [合間調整] entry {_si} next_run → {min_next.strftime('%H:%M')}")
                        except:
                            pass
                if _updated:
                    save_json(STORAGE_FILE, current_storage)
            except:
                pass
    else:
        # 失敗は初回のみカウント（リトライ時は加算しない）
        if p.get('retry_count', 0) == 0:
            acc['metrics']['failures'] += 1
        acc['metrics']['last_error'] = msg[:40]
        # Smart auto-fix based on error type
        error_type = classify_error(msg)
        p, action = auto_fix_and_reschedule(p, acc, error_type, msg)
        log_error(acc_name, error_type, msg, action)
        print(f"  [AUTO-FIX] {error_type}: {action}")

    return p_idx, p, acc, True


# ==================== Scheduled Repost Processing ====================
import re as _repost_re

def extract_threads_username_and_shortcode(url):
    """URLからusernameとshortcodeを抽出"""
    m = _repost_re.search(r'threads\.(?:net|com)/@([^/]+)/post/([^/?]+)', url)
    if m:
        return m.group(1), m.group(2)
    return None, None

def find_threads_post_id_worker(account, shortcode):
    """アカウントのトークンでme/threadsを検索し、shortcodeに一致する投稿のIDを返す"""
    token = account.get("token", "")
    if not token:
        return None
    try:
        after = None
        for _ in range(10):
            params = {"fields": "id,permalink", "limit": 25, "access_token": token}
            if after:
                params["after"] = after
            resp = requests.get("https://graph.threads.net/v1.0/me/threads", params=params, timeout=15)
            if resp.status_code != 200:
                return None
            data = resp.json()
            for post in data.get("data", []):
                plink = post.get("permalink", "")
                if shortcode in plink:
                    return post["id"]
            paging = data.get("paging", {})
            after = paging.get("cursors", {}).get("after")
            if not after or "next" not in paging:
                break
    except:
        pass
    return None

def repost_thread_worker(account, threads_post_id):
    """リポスト実行"""
    try:
        resp = requests.post(
            f"https://graph.threads.net/v1.0/{threads_post_id}/repost",
            params={"access_token": account["token"]},
            timeout=30
        )
        if resp.status_code == 200:
            return True, resp.json()
        else:
            return False, resp.text
    except Exception as e:
        return False, str(e)

def process_scheduled_reposts():
    """Check and execute scheduled reposts that are due."""
    if not os.path.exists(SCHEDULED_REPOSTS_FILE):
        return

    try:
        tasks = load_json(SCHEDULED_REPOSTS_FILE)
    except:
        return

    if not tasks:
        return

    now = get_jst_time()
    changed = False

    # Load accounts
    try:
        accounts = load_json(ACCOUNTS_FILE)
    except:
        return

    acc_by_username = {a.get("username", ""): a for a in accounts}

    for task in tasks:
        if task.get("status") != "pending":
            continue

        # Parse scheduled time
        sched_str = task.get("scheduled_at", "")
        try:
            from datetime import datetime, timezone, timedelta
            sched_time = datetime.fromisoformat(sched_str)
            if sched_time.tzinfo is None:
                JST = timezone(timedelta(hours=9))
                sched_time = sched_time.replace(tzinfo=JST)
        except:
            continue

        if now < sched_time:
            continue

        # Time to execute this repost
        print(f"[Scheduled Repost] Executing: {task['box_name']} -> {task['post_url']}")
        task["status"] = "running"
        changed = True

        # Extract post info from URL
        username, shortcode = extract_threads_username_and_shortcode(task["post_url"])
        if not username or not shortcode:
            task["status"] = "failed"
            task["results"] = [{"error": "URLの解析に失敗"}]
            continue

        # Find the post owner account
        owner_acc = acc_by_username.get(username)
        if not owner_acc:
            # Try to find by similar username
            for a in accounts:
                if a.get("username", "").lower() == username.lower():
                    owner_acc = a
                    break

        if not owner_acc:
            task["status"] = "failed"
            task["results"] = [{"error": f"投稿者{username}のアカウントが見つかりません"}]
            continue

        # Find post ID
        post_id = find_threads_post_id_worker(owner_acc, shortcode)
        if not post_id:
            task["status"] = "failed"
            task["results"] = [{"error": "投稿IDが見つかりません"}]
            continue

        # Execute reposts for all accounts in the box
        results = []
        for uname in task.get("acc_usernames", []):
            acc = acc_by_username.get(uname)
            if not acc:
                results.append({"username": uname, "ok": False, "error": "アカウント不明"})
                continue

            ok, resp = repost_thread_worker(acc, post_id)
            results.append({"username": uname, "ok": ok, "response": str(resp)[:100]})
            print(f"  Repost {uname}: {'OK' if ok else 'FAIL'}")

            import time
            time.sleep(1)

        task["status"] = "completed"
        task["results"] = results

    if changed:
        save_json(SCHEDULED_REPOSTS_FILE, tasks)
        print("[Scheduled Repost] Tasks updated")





# ==================== Repeat Post Processing ====================
def process_repeat_posts():
    """Check and execute repeat posts that are due today."""
    if not os.path.exists(REPEAT_POSTS_FILE):
        return

    try:
        rp_data = load_json(REPEAT_POSTS_FILE)
    except:
        return

    if not rp_data:
        return

    now = get_jst_time()
    today_str = now.strftime("%Y-%m-%d")
    current_hour = now.hour
    changed = False

    # Load accounts
    try:
        accounts = load_json(ACCOUNTS_FILE)
    except:
        return

    acc_by_username = {a.get("username", ""): a for a in accounts}

    for rp in rp_data:
        if not rp.get("active", True):
            continue

        # Check if already posted today
        if rp.get("last_posted_date") == today_str:
            continue

        # Check time range
        time_start = rp.get("time_start", 8)
        time_end = rp.get("time_end", 22)
        if current_hour < time_start or current_hour > time_end:
            continue

        # Get account
        acc = acc_by_username.get(rp.get("acc_username", ""))
        if not acc:
            continue

        # アカウントが非アクティブなら投稿しない
        if not acc.get("active", True):
            continue

        entries = rp.get("entries", [])
        if not entries:
            continue

        cur_idx = rp.get("current_entry_idx", 0) % len(entries)
        cur_entry = entries[cur_idx]
        post_text = cur_entry.get("text", "")
        images = rp.get("images", [])

        print(f"[Repeat Post] @{rp['acc_username']} entry {cur_idx+1}/{len(entries)} day {rp.get('days_on_current',0)+1}/{cur_entry.get('days',1)}")

        # Post
        try:
            # Load images
            image_urls = []
            for img_path in images:
                if os.path.exists(img_path):
                    image_urls.append(img_path)

            ok, result = post_to_threads(acc, post_text, image_urls)
            if ok:
                print(f"  Result: OK")
            else:
                print(f"  Result: FAIL - {str(result)[:100]}")
                continue  # Don't advance on failure
        except Exception as e:
            print(f"  Error: {e}")
            continue

        # Update state
        days_on_current = rp.get("days_on_current", 0) + 1
        max_days = cur_entry.get("days", 1)

        if days_on_current >= max_days:
            # Move to next entry
            rp["current_entry_idx"] = (cur_idx + 1) % len(entries)
            rp["days_on_current"] = 0
        else:
            rp["days_on_current"] = days_on_current

        rp["last_posted_date"] = today_str
        changed = True

    if changed:
        save_json(REPEAT_POSTS_FILE, rp_data)
        print("[Repeat Post] State updated")


def main():
    now = get_jst_time()
    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] worker.py started (parallel edition, max {MAX_WORKERS} threads)")
    last_token_check = None

    while True:
        try:
            now = get_jst_time()

            # Check token refresh every 6 hours
            if last_token_check is None or (now - last_token_check).total_seconds() > 21600:
                accounts = load_json(ACCOUNTS_FILE)
                _orig_acc_len = len(accounts)
                accounts = refresh_tokens_if_needed(accounts, _orig_acc_len)
                last_token_check = now

            storage = load_json(STORAGE_FILE)
            accounts = load_json(ACCOUNTS_FILE)
            orig_storage_len = len(storage)
            orig_accounts_len = len(accounts)
            today_str = now.strftime('%Y-%m-%d')

            # auto_on_at タイマーチェック: 時間が来たらアカウントをONにする
            _acc_changed = False
            for _acc in accounts:
                _aon = _acc.get('auto_on_at')
                if _aon and not _acc.get('active', True):
                    try:
                        _aon_dt = datetime.fromisoformat(_aon)
                        if now >= _aon_dt:
                            _acc['active'] = True
                            _acc.pop('auto_on_at', None)
                            _acc_changed = True
                            print(f"  [Timer ON] {_acc.get('name', _acc.get('username', '?'))} activated")
                    except:
                        pass
            if _acc_changed:
                # 最新のaccounts.jsonを再読み込みしてからタイマー変更だけ適用（削除済みアカウント復活防止）
                _fresh_accs = load_json(ACCOUNTS_FILE)
                _fresh_map = {a.get('username'): a for a in _fresh_accs}
                for _acc in accounts:
                    _u = _acc.get('username', '')
                    if _u in _fresh_map and _acc.get('active') and not _fresh_map[_u].get('active'):
                        _fresh_map[_u]['active'] = True
                        _fresh_map[_u].pop('auto_on_at', None)
                save_json(ACCOUNTS_FILE, list(_fresh_map.values()))

            # Build account-level last_posted_at map for 合間機能 (username-based)
            acc_last_posted = {}
            for si, sp in enumerate(storage):
                _sp_uname = sp.get('acc_username', '')
                if not _sp_uname:
                    # fallback for old data
                    _sp_idx = sp.get('acc_idx', -1)
                    if 0 <= _sp_idx < len(accounts):
                        _sp_uname = accounts[_sp_idx].get('username', '')
                lp = sp.get('last_posted_at')
                if _sp_uname and lp:
                    try:
                        lp_time = datetime.fromisoformat(lp)
                        if _sp_uname not in acc_last_posted or lp_time > acc_last_posted[_sp_uname]:
                            acc_last_posted[_sp_uname] = lp_time
                    except:
                        pass

            # Find all posts that need to run now
            ready_tasks = []
            for i, p in enumerate(storage):
                # username-based lookup (with acc_idx fallback)
                _p_uname = p.get('acc_username')
                if _p_uname:
                    _p_real_idx, acc = find_account_by_username(accounts, _p_uname)
                    if acc is None:
                        continue
                else:
                    _p_idx = p.get('acc_idx', -1)
                    if _p_idx < 0 or _p_idx >= len(accounts):
                        continue
                    acc = accounts[_p_idx]
                    _p_uname = acc.get('username', '')
                if not acc.get('active', True):
                    continue
                if p.get('paused', False):
                    continue

                # Reset daily counter if new day
                if p.get('today_date', '') != today_str:
                    p['today_count'] = 0

                # Duplicate prevention: skip if ANY entry for same account posted within 60 min
                _dominated = False
                for _dp in storage:
                    _dp_uname = _dp.get('acc_username', '')
                    if not _dp_uname and 0 <= _dp.get('acc_idx', -1) < len(accounts):
                        _dp_uname = accounts[_dp['acc_idx']].get('username', '')
                    if _dp_uname == _p_uname:
                        _dlp = _dp.get('last_posted_at')
                        if _dlp:
                            try:
                                if (now - datetime.fromisoformat(_dlp)).total_seconds() < 3600:
                                    _dominated = True
                                    break
                            except:
                                pass
                if _dominated:
                    continue

                posts_per_day = p.get('posts_per_day', 1)
                today_count = p.get('today_count', 0)

                if today_count >= posts_per_day:
                    continue

                try:
                    next_run = datetime.fromisoformat(p['next_run'])
                    if now >= next_run:
                        # Check if current time is within posting time range
                        time_range = p.get('time_range', [7, 23])
                        current_hour = now.hour
                        range_start = time_range[0]
                        range_end = time_range[1] + 1  # Include the end hour (e.g., 21:59)
                        if range_start <= current_hour < range_end:
                            # 合間機能: check cross-entry interval (ボックス24時間=fixed_timeありはスキップ)
                            post_interval = p.get('post_interval')
                            if post_interval and not p.get('fixed_time') and _p_uname in acc_last_posted:
                                last_post_time = acc_last_posted[_p_uname]
                                hours_since = (now - last_post_time).total_seconds() / 3600
                                if hours_since < post_interval:
                                    # Not enough time passed, reschedule
                                    wait_until = last_post_time + timedelta(hours=post_interval)
                                    p['next_run'] = wait_until.isoformat()
                                    print(f"  [{now.strftime('%H:%M')}] {acc.get('name','?')[:15]}: 合間制限 ({hours_since:.1f}h < {post_interval}h) → {wait_until.strftime('%H:%M')}まで待機")
                                    continue
                            ready_tasks.append((i, p))
                        else:
                            # Outside time range: reschedule to tomorrow's range
                            tomorrow = now + timedelta(days=1)
                            new_next = tomorrow.replace(
                                hour=random.randint(range_start, min(range_start + 2, time_range[1])),
                                minute=random.randint(0, 59), second=0
                            )
                            p['next_run'] = new_next.isoformat()
                            print(f"  [{now.strftime('%H:%M')}] {acc.get('name','?')[:15]}: time range outside ({range_start}-{time_range[1]}h) → rescheduled to {new_next.strftime('%m/%d %H:%M')}")
                except:
                    continue

            # Save any rescheduled posts (outside time range)
            safe_save_storage(storage, orig_storage_len)

            if ready_tasks:
                print(f"[{now.strftime('%H:%M:%S')}] {len(ready_tasks)} posts ready, processing...")

                # Set next_run to 15min later for all tasks (safety lock)
                for idx, p in ready_tasks:
                    p['next_run'] = (now + timedelta(minutes=15)).isoformat()
                safe_save_storage(storage, orig_storage_len)

                # Process in parallel (up to MAX_WORKERS)
                results = []
                with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(ready_tasks))) as executor:
                    futures = {}
                    for idx, p in ready_tasks:
                        future = executor.submit(process_single_post, p, idx, accounts)
                        futures[future] = idx

                    for future in as_completed(futures):
                        try:
                            result = future.result()
                            results.append(result)
                        except Exception as e:
                            print(f"  Thread error: {e}")
                            traceback.print_exc()

                # Apply results back
                storage_updated = False
                acc_updated = False
                for p_idx, updated_p, updated_acc, did_post in results:
                    if did_post:
                        storage[p_idx] = updated_p
                        storage_updated = True
                        if updated_acc:
                            _uname = updated_acc.get('username', '')
                            _ridx, _ = find_account_by_username(accounts, _uname)
                            if _ridx >= 0:
                                accounts[_ridx] = updated_acc
                            acc_updated = True

                if storage_updated:
                    safe_save_storage(storage, orig_storage_len)
                if acc_updated:
                    safe_save_accounts(accounts, orig_accounts_len)

        except Exception as e:
            print(f"[{get_jst_time().strftime('%H:%M:%S')}] Error: {e}")
            traceback.print_exc()

        
        # Check scheduled reposts
        try:
            process_scheduled_reposts()
        except Exception as e:
            print(f'Scheduled repost error: {e}')

        # Check repeat posts
        try:
            process_repeat_posts()
        except Exception as e:
            print(f'Repeat post error: {e}')

        time.sleep(30)

if __name__ == "__main__":
    main()
