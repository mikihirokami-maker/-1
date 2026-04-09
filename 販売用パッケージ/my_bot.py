# -*- coding: utf-8 -*-
import streamlit as st
import streamlit.components.v1 as components
import time
import random
import requests
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Page Config ---
st.set_page_config(page_title="Threads Auto Master Pro", layout="wide", page_icon="robot")

# --- CSS ---
st.markdown("""
<style>
    html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"],
    .stApp, .main, section[data-testid="stSidebar"],
    [data-testid="stAppViewBlockContainer"] {
        background-color: #0a0a0a !important; color: #e0e0e0;
    }
    /* rerun時のちらつき防止 */
    iframe[title="streamlit_app"] { background-color: #0a0a0a !important; }
    h1, h2, h3, h4 { color: #00f2ff !important; font-family: 'Helvetica Neue', sans-serif; }
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea {
        background-color: #1a1a2e !important; color: #fff !important;
        border: 1px solid #333 !important; border-radius: 8px !important;
    }
    .stSelectbox > div > div { background-color: #1a1a2e !important; }
    .stButton > button {
        background: linear-gradient(90deg, #00c6ff, #0072ff); color: white;
        font-weight: bold; border: none; border-radius: 8px; padding: 0.5rem 1rem;
        transition: all 0.3s;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 15px rgba(0, 114, 255, 0.4);
    }
    .next-run-badge {
        background: linear-gradient(90deg, #0072ff, #00c6ff); color: white;
        padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 0.9em;
    }
    .comp-card {
        background: rgba(255, 255, 255, 0.05); padding: 14px; border-radius: 10px;
        border: 1px solid rgba(255, 255, 255, 0.1); margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# Fix Streamlit React DOM reconciliation error (removeChild bug)
# Must target parent window since components.html runs in an iframe
components.html("""
<script>
try {
    var W = window.parent;
    var _rc = W.Node.prototype.removeChild;
    W.Node.prototype.removeChild = function(c) {
        if (c.parentNode !== this) return c;
        return _rc.call(this, c);
    };
    var _ib = W.Node.prototype.insertBefore;
    W.Node.prototype.insertBefore = function(n, r) {
        if (r && r.parentNode !== this) return n;
        return _ib.call(this, n, r);
    };

    // Selectbox dropdown: scroll to selected item when opened
    if (!W._pfDropdownObserver) {
        W._pfDropdownObserver = new MutationObserver(function() {
            var listbox = W.document.querySelector('[role="listbox"]');
            if (listbox && !listbox._pf) {
                listbox._pf = true;
                setTimeout(function() {
                    // Find the selectbox that triggered this dropdown
                    // by finding which select container has aria-expanded="true"
                    var selects = W.document.querySelectorAll('[data-baseweb="select"]');
                    var selectedText = '';
                    for (var s = 0; s < selects.length; s++) {
                        var inp = selects[s].querySelector('input');
                        if (inp && inp.getAttribute('aria-expanded') === 'true') {
                            // Get the displayed value from sibling div
                            var valDiv = selects[s].querySelector('[data-baseweb="select"] > div > div > div > div');
                            if (!valDiv) valDiv = selects[s].querySelector('div[class*="valueContainer"] > div');
                            if (!valDiv) {
                                // fallback: get text from the first div child
                                var firstChild = selects[s].querySelector('div > div');
                                if (firstChild) selectedText = firstChild.textContent.trim();
                            } else {
                                selectedText = valDiv.textContent.trim();
                            }
                            break;
                        }
                    }
                    if (!selectedText) return;
                    // Find matching option in dropdown and scroll to it
                    var options = listbox.querySelectorAll('[role="option"]');
                    for (var i = 0; i < options.length; i++) {
                        if (options[i].textContent.trim() === selectedText) {
                            options[i].scrollIntoView({block: 'center'});
                            break;
                        }
                    }
                }, 30);
            }
        });
        W._pfDropdownObserver.observe(W.document.body, {childList:true, subtree:true});
    }
} catch(e) {}
</script>
""", height=0)

# --- Safety Profiles (unique fingerprint per account) ---
UA_PROFILES = [
    {"name": "Chrome/Win", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"},
    {"name": "Chrome/Mac", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"},
    {"name": "Safari/Mac", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15"},
    {"name": "Firefox/Win", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"},
    {"name": "Edge/Win", "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Edge/131.0.0.0"},
    {"name": "Chrome/Android", "ua": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/131.0.0.0 Mobile Safari/537.36"},
    {"name": "Safari/iOS", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/605.1.15"},
    {"name": "Firefox/Mac", "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0"},
    {"name": "Samsung", "ua": "Mozilla/5.0 (Linux; Android 14; SM-S911B) AppleWebKit/537.36 SamsungBrowser/23.0 Chrome/115.0.0.0 Mobile Safari/537.36"},
    {"name": "Chrome/Linux", "ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"},
]

def get_slot_profile(slot):
    """Get UA profile for a given slot number (1-based, cycles if >10)"""
    return UA_PROFILES[(slot - 1) % len(UA_PROFILES)]

# --- Proxy Settings (IPRoyal Residential Rotating) ---
PROXY_HOST = ""  # プロキシホスト（例: geo.iproyal.com）
PROXY_PORT = ""  # プロキシポート（例: 12321）
PROXY_USER = ""  # プロキシユーザー名
PROXY_PASS = ""  # プロキシパスワード

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

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_FILE = os.path.join(BASE_DIR, "accounts.json")
STORAGE_FILE = os.path.join(BASE_DIR, "storage.json")
IMAGE_DIR = os.path.join(BASE_DIR, "images")
COMPETITORS_FILE = os.path.join(BASE_DIR, "competitors.json")
BOX_TEMPLATES_FILE = os.path.join(BASE_DIR, "box_templates.json")
REPOST_BOXES_FILE = os.path.join(BASE_DIR, "repost_boxes.json")
SCHEDULED_REPOSTS_FILE = os.path.join(BASE_DIR, "scheduled_reposts.json")
REPEAT_POSTS_FILE = os.path.join(BASE_DIR, "repeat_posts.json")
REPEAT_TEMPLATES_FILE = os.path.join(BASE_DIR, "repeat_templates.json")
if not os.path.exists(IMAGE_DIR):
    os.makedirs(IMAGE_DIR)

# ===================== Utility =====================

def get_jst_time():
    return datetime.now(timezone(timedelta(hours=9)))

def load_json(file_path):
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data
        except Exception:
            # JSONパース失敗時: auto_bakから復旧を試みる
            bak_path = file_path + ".auto_bak"
            if os.path.exists(bak_path):
                try:
                    with open(bak_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if data:  # バックアップが有効なら使う
                        return data
                except Exception:
                    pass
            return []
    return []

def save_json(file_path, data):
    import shutil, tempfile
    # storage.json の保護: 読み込み時に壊れていた場合は保存禁止
    if file_path.endswith("storage.json"):
        try:
            if hasattr(st, 'session_state') and not getattr(st.session_state, '_storage_loaded_ok', True):
                st.error("⚠️ storage.json の読み込みに失敗していたため、保存をブロックしました。ページをリロードしてください。")
                return
        except Exception:
            pass
    # storage.json の保護: エントリ数が50%以下に激減したら保存をブロック
    if file_path.endswith("storage.json") and isinstance(data, list):
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    old_data = json.load(f)
                if isinstance(old_data, list) and len(old_data) > 20:
                    if len(data) == 0:
                        shutil.copy2(file_path, file_path + ".safety_bak")
                        st.error(f"⚠️ storage.json の保存をブロック！0件への上書きを防止しました。バックアップ: {file_path}.safety_bak")
                        return
                    ratio = len(data) / len(old_data)
                    if ratio < 0.5:
                        shutil.copy2(file_path, file_path + ".safety_bak")
                        st.error(f"⚠️ storage.json の保存をブロック！エントリ数が {len(old_data)} → {len(data)} に激減。バックアップ: {file_path}.safety_bak")
                        return
        except Exception:
            pass
    # 保存前に自動バックアップ（storage.json のみ）
    if file_path.endswith("storage.json") and os.path.exists(file_path):
        try:
            shutil.copy2(file_path, file_path + ".auto_bak")
        except Exception:
            pass
    # アトミック書き込み（一時ファイル→リネーム）で破損防止
    dir_name = os.path.dirname(file_path) or "."
    try:
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        shutil.move(tmp_path, file_path)
    except Exception:
        # フォールバック: 通常書き込み
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def shortcode_to_media_id(shortcode):
    """Threads/Instagram shortcode → numeric media ID"""
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    media_id = 0
    for char in shortcode:
        media_id = media_id * 64 + alphabet.index(char)
    return str(media_id)

def extract_threads_username_and_shortcode(url):
    """Threads URL → (username, shortcode) を取得"""
    import re
    m = re.search(r'/@([^/]+)/post/([A-Za-z0-9_-]+)', url)
    if m:
        return m.group(1), m.group(2)
    return None, None

def get_threads_user_id(token):
    """トークンからThreads user_idを取得"""
    try:
        resp = requests.get("https://graph.threads.net/v1.0/me", params={"access_token": token}, timeout=15)
        if resp.status_code == 200:
            return resp.json().get('id')
    except:
        pass
    return None

def find_threads_post_id(account, shortcode):
    """アカウントのトークンでme/threadsを検索し、shortcodeに一致する投稿のIDを返す"""
    token = account.get('token', '')
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

def repost_thread(account, threads_post_id):
    """Threads公式APIでリポスト実行 (POST /{post_id}/repost)"""
    try:
        resp = requests.post(
            f"https://graph.threads.net/v1.0/{threads_post_id}/repost",
            params={"access_token": account['token']},
            timeout=30
        )
        if resp.status_code == 200:
            return True, resp.json()
        else:
            return False, resp.text
    except Exception as e:
        return False, str(e)

def quote_thread(account, threads_post_id, quote_text):
    """Threads公式APIで引用投稿 (quote_post_id)"""
    try:
        user_id = account['id']
        token = account['token']
        # Step 1: コンテナ作成（quote_post_id はPOSTボディで送信）
        resp = requests.post(
            f"https://graph.threads.net/v1.0/{user_id}/threads",
            params={"media_type": "TEXT", "text": quote_text, "access_token": token},
            data={"quote_post_id": str(threads_post_id)},
            timeout=30
        )
        if resp.status_code != 200:
            return False, f"Container error({resp.status_code}): {resp.text}"
        resp_json = resp.json()
        container_id = resp_json.get('id')
        if not container_id:
            return False, f"Container ID not returned: {resp_json}"
        # Step 2: 公開
        time.sleep(3)
        pub_resp = requests.post(
            f"https://graph.threads.net/v1.0/{user_id}/threads_publish",
            params={"access_token": token},
            data={"creation_id": container_id},
            timeout=30
        )
        if pub_resp.status_code == 200:
            return True, pub_resp.json()
        else:
            return False, f"Publish error({pub_resp.status_code}): {pub_resp.text}"
    except Exception as e:
        return False, str(e)

QUOTE_BOXES_FILE = os.path.join(BASE_DIR, "quote_boxes.json")

def calculate_next_run(time_range):
    s, e = time_range
    now = get_jst_time()
    h = random.randint(s, max(s, min(e, 23)))
    target = now.replace(hour=h, minute=random.randint(0, 59), second=0)
    if target <= now:
        target += timedelta(days=1)
    return target.isoformat()

def resolve_image_path(path):
    """Resolve image path (supports absolute, relative, and URL)"""
    if not path:
        return None
    if isinstance(path, str) and path.startswith("http"):
        return path
    if os.path.isabs(path):
        return path if os.path.exists(path) else None
    abs_path = os.path.join(BASE_DIR, path)
    return abs_path if os.path.exists(abs_path) else None

def to_hiragana(text):
    """Convert katakana to hiragana for unified search"""
    result = []
    for c in text:
        cp = ord(c)
        if 0x30A1 <= cp <= 0x30F6:
            result.append(chr(cp - 0x60))
        else:
            result.append(c)
    return ''.join(result)

def kana_match(query, target):
    """Search with hiragana/katakana support"""
    if not query:
        return True
    q = to_hiragana(query.lower())
    t = to_hiragana(target.lower())
    return q in t

def _api_get(url, params, account=None):
    """API GET with proxy fallback: try proxy first, then direct if proxy fails."""
    # Try 1: with proxy
    try:
        res = requests.get(url, params=params, proxies=get_proxy(account), timeout=15)
        return res.json()
    except Exception:
        pass
    # Try 2: direct (no proxy)
    try:
        res = requests.get(url, params=params, timeout=15)
        return res.json()
    except Exception as e:
        raise e

def refresh_long_lived_token(account):
    if not account.get('app_secret'):
        return account['token']
    try:
        res = _api_get(
            "https://graph.threads.net/refresh_access_token",
            {'grant_type': 'th_refresh_token', 'access_token': account['token']},
            account
        )
        return res.get('access_token', account['token'])
    except:
        return account['token']

def search_threads_keyword(account, query):
    """Threads API keyword search (limit: 500 queries / 7 days)"""
    try:
        url = f"https://graph.threads.net/v1.0/{account['id']}/threads_search"
        params = {
            'q': query,
            'access_token': account['token'],
            'fields': 'id,text,timestamp,username,media_url,media_type,permalink'
        }
        res = _api_get(url, params, account)
        if 'data' in res:
            return True, res['data']
        elif 'error' in res:
            return False, res['error'].get('message', str(res))
        else:
            return False, str(res)
    except Exception as e:
        return False, str(e)

def fetch_user_threads(account, limit=25):
    """Fetch user's recent threads with carousel children pre-fetched"""
    try:
        url = f"https://graph.threads.net/v1.0/{account['id']}/threads"
        params = {
            'access_token': account['token'],
            'fields': 'id,text,timestamp,media_type,media_url,like_count,permalink,children{id,media_type,media_url}',
            'limit': limit
        }
        res = _api_get(url, params, account)
        if 'data' in res:
            # Extract carousel children URLs into each post
            for post in res['data']:
                if post.get('media_type') == 'CAROUSEL_ALBUM' and 'children' in post:
                    child_data = post['children'].get('data', [])
                    post['_child_urls'] = [c.get('media_url') for c in child_data if c.get('media_url')]
                else:
                    post['_child_urls'] = []
            return True, res['data']
        return False, res.get('error', {}).get('message', str(res))
    except Exception as e:
        return False, str(e)

def fetch_carousel_children(account, thread_id):
    """Fetch children media URLs for a CAROUSEL post"""
    try:
        url = f"https://graph.threads.net/v1.0/{thread_id}/children"
        params = {
            'access_token': account['token'],
            'fields': 'id,media_type,media_url'
        }
        res = _api_get(url, params, account)
        if 'data' in res:
            return [c.get('media_url') for c in res['data'] if c.get('media_url')]
        return []
    except:
        return []

def _download_single_media(url):
    """Download a single image/video URL and save to IMAGE_DIR. Returns saved path or None.
    CDN media are public - no proxy needed (much faster)."""
    for attempt in range(2):
        try:
            use_proxy = attempt > 0
            kwargs = {'timeout': 30}
            if use_proxy:
                kwargs['proxies'] = get_proxy()
            media_data = requests.get(url, **kwargs).content
            if not media_data or len(media_data) < 500:
                continue
            # Detect file type by magic bytes or URL
            is_video = False
            if media_data[:4] == b'\x00\x00\x00\x18' or media_data[:4] == b'\x00\x00\x00\x1c' or media_data[4:8] == b'ftyp':
                is_video = True
            elif '.mp4' in url.split('?')[0].lower() or 'video' in url.lower():
                is_video = True
            # Reject HTML error pages (but not videos which won't have image headers)
            if not is_video and media_data[:2] not in (b'\xff\xd8', b'\x89\x50', b'\x47\x49', b'\x52\x49') and b'<html' in media_data[:200].lower():
                continue
            ext = '.mp4' if is_video else '.jpg'
            path = os.path.join(IMAGE_DIR, f"{uuid.uuid4()}_repost{ext}")
            with open(path, 'wb') as f:
                f.write(media_data)
            return os.path.abspath(path)
        except:
            continue
    return None

def download_post_images(account, post, cached_child_urls=None):
    """Download images from a past post and save to IMAGE_DIR. Returns list of saved paths.
    Uses parallel downloads for speed. cached_child_urls can be passed to skip re-fetching."""
    media_type = post.get('media_type', 'TEXT')
    urls_to_download = []

    try:
        if media_type == 'CAROUSEL_ALBUM':
            if cached_child_urls:
                urls_to_download = list(cached_child_urls)
            else:
                urls_to_download = fetch_carousel_children(account, post.get('id'))
        elif media_type in ('IMAGE', 'VIDEO') and post.get('media_url'):
            urls_to_download = [post['media_url']]
        elif post.get('media_url'):
            urls_to_download = [post['media_url']]
    except:
        pass

    if not urls_to_download:
        return []

    # Single image: download directly (no thread overhead)
    if len(urls_to_download) == 1:
        result = _download_single_media(urls_to_download[0])
        return [result] if result else []

    # Multiple images: parallel download (up to 6 at once)
    saved_paths = [None] * len(urls_to_download)
    with ThreadPoolExecutor(max_workers=min(6, len(urls_to_download))) as executor:
        future_to_idx = {}
        for i, url in enumerate(urls_to_download):
            future = executor.submit(_download_single_media, url)
            future_to_idx[future] = i
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            result = future.result()
            if result:
                saved_paths[idx] = result

    # Remove None entries while keeping order
    return [p for p in saved_paths if p is not None]

# ===================== Test Functions =====================

def _api_post(url, data, account=None):
    """API POST with proxy fallback: try proxy first, then direct if proxy fails."""
    try:
        res = requests.post(url, data=data, proxies=get_proxy(account), timeout=30)
        return res.json()
    except Exception:
        pass
    try:
        res = requests.post(url, data=data, timeout=30)
        return res.json()
    except Exception as e:
        raise e

def _api_post_files(url, headers, files, account=None):
    """API POST with files + proxy fallback."""
    try:
        res = requests.post(url, headers=headers, files=files, proxies=get_proxy(account), timeout=30)
        return res.json()
    except Exception:
        pass
    try:
        res = requests.post(url, headers=headers, files=files, timeout=30)
        return res.json()
    except Exception as e:
        raise e

def test_connection_only(account, text, image_files=None, saved_image_paths=None):
    try:
        res = _api_get(
            "https://graph.threads.net/v1.0/me",
            {'fields': 'id', 'access_token': account['token']}, account
        )
        if 'id' not in res:
            return False, f"Token error: {res}"

        img_status = ""
        total_checked = 0

        if image_files and len(image_files) > 0:
            img_status = " | Image test: "
            for idx, f in enumerate(image_files):
                u = _upload_to_local(f.getvalue())
                if u:
                    total_checked += 1
                    img_status += f"[{total_checked}:OK] "
                else:
                    return False, f"Image error ({idx+1}): upload failed"
                time.sleep(1)
        elif saved_image_paths and len(saved_image_paths) > 0:
            img_status = " | Saved image test: "
            for idx, path in enumerate(saved_image_paths):
                resolved = resolve_image_path(path)
                if resolved:
                    total_checked += 1
                    img_status += f"[{total_checked}:OK] "
                else:
                    return False, f"Image error ({idx+1}): file not found on server"

        if total_checked > 0:
            return True, f"Connection OK!{img_status} ({total_checked} images ready, not actually posted)"
        else:
            return True, "Connection OK! | Text only (not actually posted)"
    except Exception as e:
        return False, str(e)

def _upload_to_local(file_data_or_path, is_path=False):
    """画像をローカルに保存してYOUR_SERVER_IPのURLを返す"""
    import hashlib
    IMAGE_DIR = "/root/images"
    IMAGE_BASE_URL = "http://YOUR_SERVER_IP/images"
    os.makedirs(IMAGE_DIR, exist_ok=True)
    try:
        if is_path:
            with open(file_data_or_path, 'rb') as f:
                data = f.read()
            ext = os.path.splitext(file_data_or_path)[1] or '.jpg'
        else:
            data = file_data_or_path
            ext = '.jpg'
        fname = hashlib.md5(data).hexdigest() + ext
        dest = os.path.join(IMAGE_DIR, fname)
        if not os.path.exists(dest):
            with open(dest, 'wb') as f:
                f.write(data)
        return f"{IMAGE_BASE_URL}/{fname}"
    except:
        return None

def real_post_test(account, text, image_files=None, saved_image_paths=None):
    user_id, token = account['id'], account['token']
    image_urls = []

    if image_files:
        for f in image_files:
            u = _upload_to_local(f.getvalue())
            if u:
                image_urls.append(u)
            else:
                return False, "Image upload failed"
            time.sleep(1)
    elif saved_image_paths:
        for path in saved_image_paths:
            resolved = resolve_image_path(path)
            if resolved:
                if resolved.startswith("http"):
                    image_urls.append(resolved)
                else:
                    u = _upload_to_local(resolved, is_path=True)
                    if u:
                        image_urls.append(u)
                    else:
                        return False, "Saved image upload failed"
                    time.sleep(1)
            else:
                return False, "Image file not found on server"

    base_url = f"https://graph.threads.net/v1.0/{user_id}/threads"
    try:
        if image_urls:
            if len(image_urls) == 1:
                is_vid = image_urls[0].lower().endswith('.mp4')
                if is_vid:
                    res = _api_post(base_url, {
                        'access_token': token, 'media_type': 'VIDEO',
                        'video_url': image_urls[0], 'text': text
                    }, account)
                else:
                    res = _api_post(base_url, {
                        'access_token': token, 'media_type': 'IMAGE',
                        'image_url': image_urls[0], 'text': text
                    }, account)
            else:
                child_ids = []
                for u in image_urls:
                    is_vid = u.lower().endswith('.mp4')
                    if is_vid:
                        cr = _api_post(base_url, {
                            'access_token': token, 'media_type': 'VIDEO',
                            'video_url': u, 'is_carousel_item': 'true'
                        }, account)
                    else:
                        cr = _api_post(base_url, {
                            'access_token': token, 'media_type': 'IMAGE',
                            'image_url': u, 'is_carousel_item': 'true'
                        }, account)
                    if 'id' in cr:
                        child_ids.append(cr['id'])
                    else:
                        return False, f"Carousel error: {cr}"
                    time.sleep(1)
                res = _api_post(base_url, {
                    'access_token': token, 'media_type': 'CAROUSEL',
                    'children': ','.join(child_ids), 'text': text
                }, account)
        else:
            res = _api_post(base_url, {
                'access_token': token, 'media_type': 'TEXT', 'text': text
            }, account)

        cid = res.get('id')
        if not cid:
            return False, f"Container error: {res}"
        # Poll container status then publish immediately when ready
        pub_err = ""
        for _poll in range(30):
            time.sleep(3)
            try:
                _st = requests.get(f"https://graph.threads.net/v1.0/{cid}",
                    params={"fields": "status", "access_token": token}, timeout=10).json()
                _status = _st.get("status", "")
                if _status == "FINISHED":
                    pub = _api_post(
                        f"https://graph.threads.net/v1.0/{user_id}/threads_publish",
                        {'creation_id': cid, 'access_token': token}, account
                    )
                    if 'id' in pub:
                        return True, "Post SUCCESS! Actually posted to Threads!"
                    pub_err = str(pub)
                    break
                elif _status in ("ERROR", "EXPIRED"):
                    return False, f"Container {_status}: {_st}"
            except Exception as pe:
                pub_err = str(pe)
        else:
            # Timeout after polling - try publish anyway
            try:
                pub = _api_post(
                    f"https://graph.threads.net/v1.0/{user_id}/threads_publish",
                    {'creation_id': cid, 'access_token': token}, account
                )
                if 'id' in pub:
                    return True, "Post SUCCESS! Actually posted to Threads!"
                pub_err = str(pub)
            except Exception as pe:
                pub_err = str(pe)
        return False, f"Publish error: {pub_err}"
    except Exception as e:
        return False, f"Network error: {str(e)}"

# ===================== Session Init =====================

st.session_state.accounts = load_json(ACCOUNTS_FILE)
_raw_storage = load_json(STORAGE_FILE)
st.session_state.storage = _raw_storage
if not hasattr(st.session_state, '_storage_loaded_ok'):
    st.session_state._storage_loaded_ok = len(_raw_storage) > 0
if 'form_key_suffix' not in st.session_state:
    st.session_state.form_key_suffix = str(uuid.uuid4())
if 'edit_text' not in st.session_state:
    st.session_state.edit_text = ""
    st.session_state.edit_range = (12, 15)
    st.session_state.edit_index = None
if 'edit_interval' not in st.session_state:
    st.session_state.edit_interval = None
if 'edit_schedule_mode' not in st.session_state:
    st.session_state.edit_schedule_mode = "ランダム"
if 'edit_fixed_hour' not in st.session_state:
    st.session_state.edit_fixed_hour = 12
if 'edit_fixed_minute' not in st.session_state:
    st.session_state.edit_fixed_minute = 0
if 'edit_acc_idx' not in st.session_state:
    st.session_state.edit_acc_idx = None

# Auto-fix: re-fetch account names from Threads API if corrupted
if 'names_fixed' not in st.session_state:
    _names_changed = False
    for _a in st.session_state.accounts:
        _name = _a.get('name', '')
        # Detect corrupted names (not containing @ means it's likely wrong)
        if not _name or '(@' not in _name or _name.startswith('st.'):
            try:
                _res = requests.get("https://graph.threads.net/v1.0/me",
                    params={'fields': 'id,username,name', 'access_token': _a['token']},
                    timeout=10).json()
                if 'username' in _res:
                    _a['name'] = f"{_res.get('name', '')} (@{_res['username']})"
                    _a['username'] = _res['username']
                    _names_changed = True
            except:
                pass
    # Auto-assign ip_slot to active accounts missing one
    _used_slots = {a.get('ip_slot') for a in st.session_state.accounts if a.get('ip_slot') is not None and a.get('ip_slot') > 0}
    _slot_changed = False
    for _a in st.session_state.accounts:
        if _a.get('active', True) and (_a.get('ip_slot') is None or _a.get('ip_slot') == 0):
            _next = 1
            while _next in _used_slots:
                _next += 1
            _a['ip_slot'] = _next
            _used_slots.add(_next)
            _slot_changed = True
            _names_changed = True
    if _names_changed:
        save_json(ACCOUNTS_FILE, st.session_state.accounts)
    st.session_state.names_fixed = True
if 'search_results' not in st.session_state:
    st.session_state.search_results = []
if 'edit_images' not in st.session_state:
    st.session_state.edit_images = []
if 'selected_comp' not in st.session_state:
    st.session_state.selected_comp = None
if 'past_posts' not in st.session_state:
    st.session_state.past_posts = []
if 'past_posts_acc' not in st.session_state:
    st.session_state.past_posts_acc = -1
if 'post_queue' not in st.session_state:
    st.session_state.post_queue = []

# ===================== Main UI =====================

MEMO_FILE = os.path.join(BASE_DIR, "memo.txt")
_memo_col1, _memo_col2 = st.columns([3, 1])
_memo_col1.title("THREADS AUTO MASTER (Complete Edition)")
with _memo_col2.popover("📝 メモ帳", use_container_width=True):
    _memo_current = ""
    if os.path.exists(MEMO_FILE):
        with open(MEMO_FILE, 'r', encoding='utf-8') as _mf:
            _memo_current = _mf.read()
    _memo_text = st.text_area("メモ", value=_memo_current, height=200, key="memo_input", label_visibility="collapsed")
    if st.button("💾 保存", key="memo_save"):
        with open(MEMO_FILE, 'w', encoding='utf-8') as _mf:
            _mf.write(_memo_text)
        st.success("✅ 保存しました")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["アカウント管理", "ポストファクトリー", "投稿モニター", "リポスト", "引用投稿", "バズリサーチ"])

# ==================== TAB 1: Account Management ====================
with tab1:
    st.header("Account Settings")
    if st.session_state.edit_acc_idx is not None:
        # Find account by ID (robust against list reordering)
        idx = None
        for _ei, _ea in enumerate(st.session_state.accounts):
            if _ea.get('id') == st.session_state.edit_acc_idx:
                idx = _ei
                break
        if idx is None:
            st.session_state.edit_acc_idx = None
            st.rerun()
        acc = st.session_state.accounts[idx]
        st.markdown(f"### 編集：{acc['name']}")
        e_token = st.text_input("トークン", value=acc.get('token', ""), type="password")
        e_id = st.text_input("アプリID", value=acc.get('app_id', ""))
        e_secret = st.text_input("アプリシークレット", value=acc.get('app_secret', ""), type="password")

        c_eb1, c_eb2 = st.columns(2)
        if c_eb1.button("保存", key="save_acc_edit"):
            acc.update({'token': e_token, 'app_id': e_id, 'app_secret': e_secret, 'proxy': None})
            save_json(ACCOUNTS_FILE, st.session_state.accounts)
            st.session_state.edit_acc_idx = None
            st.rerun()
        if c_eb2.button("キャンセル", key="cancel_acc_edit"):
            st.session_state.edit_acc_idx = None
            st.rerun()
    else:
        with st.expander("Add New Account"):
            nt = st.text_input("Access Token", type="password", key="ntok")

            # Collect previously used App ID + Secret pairs
            prev_apps = []
            seen_ids = set()
            for a in st.session_state.accounts:
                aid = a.get('app_id', '').strip()
                asec = a.get('app_secret', '').strip()
                if aid and aid not in seen_ids:
                    seen_ids.add(aid)
                    label = f"{aid[:6]}...{aid[-4:]}" if len(aid) > 12 else aid
                    prev_apps.append({"label": label, "app_id": aid, "app_secret": asec})

            if prev_apps:
                app_options = ["新規入力（手動）"] + [p["label"] for p in prev_apps]
                app_choice = st.selectbox("過去のアプリ情報を使う", app_options, key="app_choice")
                if app_choice == "新規入力（手動）":
                    ni = st.text_input("App ID", key="napp")
                    ns = st.text_input("App Secret", type="password", key="nsec")
                else:
                    chosen = prev_apps[app_options.index(app_choice) - 1]
                    ni = chosen["app_id"]
                    ns = chosen["app_secret"]
                    sec_label = f"{ns[:4]}...{ns[-4:]}" if len(ns) > 10 else ("設定済み" if ns else "未設定")
                    st.success(f"✅ App ID: {chosen['label']}　|　App Secret: {sec_label}")
            else:
                ni = st.text_input("App ID", key="napp")
                ns = st.text_input("App Secret", type="password", key="nsec")

            st.caption("App ID + App Secretで自動トークン更新（永久運用）")
            st.caption("IPアドレス・フィンガープリントは自動的にユニークに割り当てられます")

            # Show current IP/slot assignments
            if st.session_state.accounts:
                with st.expander(f"現在のIP割り当て ({len(st.session_state.accounts)} accounts)"):
                    for ea in st.session_state.accounts:
                        slot = ea.get('ip_slot')
                        profile = get_slot_profile(slot) if slot is not None and slot > 0 else {"name": "未割当"}
                        st.caption(f"{ea['name']}: Slot {slot} ({profile['name']})")

            if st.button("Save", key="save_new_acc"):
                # Reload from file to get latest slot data
                st.session_state.accounts = load_json(ACCOUNTS_FILE)
                # First fix any existing accounts missing ip_slot
                used_slots = {a.get('ip_slot') for a in st.session_state.accounts if a.get('ip_slot') is not None and a.get('ip_slot') > 0}
                for _ea in st.session_state.accounts:
                    if _ea.get('ip_slot') is None or _ea.get('ip_slot') == 0:
                        _ns = 1
                        while _ns in used_slots:
                            _ns += 1
                        _ea['ip_slot'] = _ns
                        used_slots.add(_ns)

                # Auto-assign unique IP slot for new account
                new_slot = 1
                while new_slot in used_slots:
                    new_slot += 1

                try:
                    res = _api_get(
                        "https://graph.threads.net/v1.0/me",
                        {'fields': 'id,username,name', 'access_token': nt}
                    )
                    if 'id' in res:
                        st.session_state.accounts.append({
                            "name": f"{res.get('name', '')} (@{res.get('username', '')})",
                            "username": res.get('username', ''),
                            "id": res.get('id'), "token": nt, "app_id": ni,
                            "app_secret": ns, "ip_slot": new_slot, "active": False,
                            "added_at": get_jst_time().isoformat()
                        })
                        save_json(ACCOUNTS_FILE, st.session_state.accounts)
                        st.success(f"Slot {new_slot} ({get_slot_profile(new_slot)['name']}) を自動割り当て")
                        st.rerun()
                    else:
                        st.error(f"Error: Token may be incorrect ({res})")
                except Exception as e:
                    st.error(f"Connection error ({str(e)})")

        # Search & Sort for account list
        _sf1, _sf2, _sf3 = st.columns([3, 1, 1])
        _acc_search = _sf1.text_input("🔍 アカウント検索", placeholder="名前で絞り込み", key="acc_search_t1")
        _acc_sort = _sf2.selectbox("並び替え", ["最新追加順", "名前順", "Slot順"], key="acc_sort_t1")
        _sf3.write("")  # spacing
        if _sf3.button("🚀 全員ON", key="all_active_on"):
            for _a in st.session_state.accounts:
                if not _a.get('auto_on_at'):  # タイマー予約中はスキップ
                    _a['active'] = True
            save_json(ACCOUNTS_FILE, st.session_state.accounts)
            st.rerun()
        _acc_list = list(enumerate(st.session_state.accounts))
        if _acc_sort == "最新追加順":
            _acc_list.sort(key=lambda x: x[1].get('added_at', ''), reverse=True)
        elif _acc_sort == "名前順":
            _acc_list.sort(key=lambda x: x[1]['name'])
        elif _acc_sort == "Slot順":
            _acc_list.sort(key=lambda x: x[1].get('ip_slot') or 999)
        if _acc_search:
            _acc_list = [(i, a) for i, a in _acc_list if kana_match(_acc_search, a.get('name', ''))]
        st.caption(f"{len(_acc_list)} / {len(st.session_state.accounts)} 件表示")
        st.markdown("---")

        _active_changed = False
        for i, acc in _acc_list:
            c1, c2, c3, c4, c5 = st.columns([2.0, 1.0, 1.0, 1.0, 1.2])
            status = "常設" if acc.get('app_secret') else "60日制限"
            slot = acc.get('ip_slot')
            if slot is not None and slot > 0:
                profile = get_slot_profile(slot)
                c1.write(f"**{acc['name']}** ({status} | スロット{slot}: {profile['name']})")
            else:
                c1.write(f"**{acc['name']}** ({status} | IP未割当)")
            prev_active = acc.get('active', True)
            # タイマーON予定がある場合は表示
            _timer_at = acc.get('auto_on_at')
            if _timer_at and not prev_active:
                try:
                    from datetime import datetime as _dt2
                    _timer_dt = _dt2.fromisoformat(_timer_at)
                    _remain = (_timer_dt - _dt2.now(_timer_dt.tzinfo)).total_seconds() / 3600
                    if _remain > 0:
                        c1.caption(f"⏰ {_remain:.1f}時間後にON")
                    else:
                        # タイマー到達 → 自動ON
                        acc['active'] = True
                        acc.pop('auto_on_at', None)
                        _active_changed = True
                except:
                    pass
            _has_timer = bool(acc.get('auto_on_at'))
            _tog_val = c2.toggle("アクティブ", value=acc.get('active', True), key=f"tog_{i}")
            if _has_timer:
                # タイマー予約中: ユーザーが手動でONにした場合のみ反映
                if _tog_val and not prev_active:
                    acc['active'] = True
                    acc.pop('auto_on_at', None)
                    _active_changed = True
                # それ以外はタイマー設定を維持
            else:
                acc['active'] = _tog_val
                if acc['active'] != prev_active:
                    _active_changed = True
            if c3.button("編集", key=f"ae_{i}"):
                st.session_state.edit_acc_idx = acc.get('id')
                st.rerun()
            if c4.button("消去", key=f"ad_{i}"):
                _del_uname = acc.get('username', '')
                latest_storage = load_json(STORAGE_FILE)
                latest_storage = [s for s in latest_storage if s.get('acc_username') != _del_uname]
                save_json(STORAGE_FILE, latest_storage)
                st.session_state.storage = latest_storage
                st.session_state.accounts.pop(i)
                save_json(ACCOUNTS_FILE, st.session_state.accounts)
                st.rerun()
            # タイマーON機能
            _timer_opts = ["⏰ ON予約"] + [f"{h}h後" for h in range(1, 25)]
            # タイマーセット済みなら残り時間に最も近い選択肢を初期値に
            _timer_default_idx = 0
            _timer_at_val = acc.get('auto_on_at')
            if _timer_at_val and not acc.get('active', True):
                try:
                    from datetime import datetime as _dt4, timezone as _tz4, timedelta as _td4
                    _remain_h = max(1, round((_dt4.fromisoformat(_timer_at_val) - _dt4.now(_tz4(_td4(hours=9)))).total_seconds() / 3600))
                    _remain_h = min(_remain_h, 24)
                    _timer_default_idx = _remain_h  # index matches hours (1h後=1, 2h後=2...)
                except:
                    pass
            _timer_sel = c5.selectbox("", _timer_opts, index=_timer_default_idx, key=f"timer_{i}", label_visibility="collapsed")
            _timer_prev_key = f"_timer_prev_{i}"
            if _timer_sel != "⏰ ON予約" and st.session_state.get(_timer_prev_key) != _timer_sel:
                st.session_state[_timer_prev_key] = _timer_sel
                _h_val = int(_timer_sel.replace("h後", ""))
                from datetime import datetime as _dt3, timezone as _tz3, timedelta as _td3
                _on_at = _dt3.now(_tz3(_td3(hours=9))) + _td3(hours=_h_val)
                acc['auto_on_at'] = _on_at.isoformat()
                acc['active'] = False
                _active_changed = True
                save_json(ACCOUNTS_FILE, st.session_state.accounts)
            elif _timer_sel == "⏰ ON予約":
                st.session_state.pop(_timer_prev_key, None)

        # Save active toggle changes immediately
        if _active_changed:
            save_json(ACCOUNTS_FILE, st.session_state.accounts)

# ==================== TAB 2: Post Factory ====================
with tab2:
    sel_username = ''
    sel_idx = 0
    if not st.session_state.accounts:
        st.warning("Please register an account first")
    else:
        acc_names = [a['name'] for a in st.session_state.accounts]

        # Backup button
        _bk1, _bk2 = st.columns([1, 3])
        if _bk1.button("💾 バックアップ", key="manual_backup"):
            import shutil
            from datetime import datetime as _dt, timezone as _tz, timedelta as _td
            _now_str = _dt.now(_tz(_td(hours=9))).strftime('%Y%m%d_%H%M')
            _bak_path = STORAGE_FILE + f".manual_bak_{_now_str}"
            _count = len(st.session_state.storage)
            if _count > 50:
                shutil.copy2(STORAGE_FILE, _bak_path)
                shutil.copy2(STORAGE_FILE, STORAGE_FILE + ".daily_bak")
                _bk2.success(f"✅ バックアップ完了（{_count}件）")
            else:
                _bk2.warning(f"⚠️ エントリ数が少なすぎます（{_count}件）")

        # Account selection (search + sort fused)
        sel_username = ''
        sf1, sf2 = st.columns([3, 1])
        acc_filter = sf1.text_input("アカウント選択", placeholder="名前で絞り込み（ひらがな/カタカナ対応）", key="acc_search_t2")
        sort_mode = sf2.selectbox("並び替え", ["最新追加順", "名前順", "Slot順"], key="sort_t2")
        acc_with_idx = list(enumerate(st.session_state.accounts))
        if sort_mode == "最新追加順":
            acc_with_idx.sort(key=lambda x: x[1].get('added_at', ''), reverse=True)
        elif sort_mode == "名前順":
            acc_with_idx.sort(key=lambda x: x[1]['name'])
        elif sort_mode == "Slot順":
            acc_with_idx.sort(key=lambda x: x[1].get('ip_slot') or 999)
        sorted_names = [a['name'] for _, a in acc_with_idx]
        sorted_indices = [i for i, _ in acc_with_idx]
        filtered_pairs = [(n, idx) for n, idx in zip(sorted_names, sorted_indices) if kana_match(acc_filter, n)]
        if not filtered_pairs:
            filtered_pairs = list(zip(sorted_names, sorted_indices))
        display_names = [f"{ni+1}. {p[0]}" for ni, p in enumerate(filtered_pairs)]
        display_indices = [p[1] for p in filtered_pairs]
        st.markdown('<div id="pf-acc-anchor"></div>', unsafe_allow_html=True)
        sel_name = st.selectbox("", display_names, key="sel_acc_t2", label_visibility="collapsed")
        sel_idx = display_indices[display_names.index(sel_name)]
        sel_username = st.session_state.accounts[sel_idx].get('username', '')

        # Clear past posts cache when account changes
        if st.session_state.past_posts_acc != sel_idx:
            st.session_state.past_posts = []
            st.session_state.past_posts_acc = sel_idx
            # Scroll to selectbox position after account change
            components.html("""<script>
                const anchor = window.parent.document.getElementById('pf-acc-anchor');
                if (anchor) anchor.scrollIntoView({block: 'start', behavior: 'instant'});
            </script>""", height=0)

        # --- Two Column Layout ---
        post_col, comp_col = st.columns([3, 2])

        # ========== LEFT: Post Management ==========
        with post_col:
            _sp_h1, _sp_h2 = st.columns([3, 2])
            _sp_h1.subheader("Scheduled Posts")
            components.html(f"""<button onclick="window.open('https://www.threads.net/@{sel_username}', '_blank', 'width=420,height=750,scrollbars=yes,resizable=yes,noopener').focus();"
                style="background:linear-gradient(90deg,#00c6ff,#0072ff);color:white;border:none;
                border-radius:8px;padding:8px 16px;font-weight:bold;cursor:pointer;font-size:13px;
                width:100%;">🔍 @{sel_username} のスレッド情報</button>""", height=45)

            # 投稿合間設定 (アカウントレベル - 即時反映)
            suffix = st.session_state.form_key_suffix
            _iv_options = ["なし (自動均等配分)", "1時間", "2時間", "3時間", "4時間", "5時間", "6時間", "7時間", "8時間"]
            _iv_values = [None, 1, 2, 3, 4, 5, 6, 7, 8]
            _iv_default = 0
            # storageから現在値を取得
            _stored_interval = None
            for _ep in st.session_state.storage:
                if _ep.get('acc_username') == sel_username and _ep.get('post_interval') is not None:
                    _stored_interval = _ep['post_interval']
                    try:
                        _iv_default = _iv_values.index(_stored_interval)
                    except ValueError:
                        pass
                    break

            def _on_interval_change():
                """selectbox変更時に即座にstorage.jsonへ保存"""
                _key = f"iv_{sel_idx}"
                _sel = st.session_state.get(_key)
                _opts = ["なし (自動均等配分)", "1時間", "2時間", "3時間", "4時間", "5時間", "6時間", "7時間", "8時間"]
                _vals = [None, 1, 2, 3, 4, 5, 6, 7, 8]
                _new_val = _vals[_opts.index(_sel)]
                _stor = load_json(STORAGE_FILE)
                # 合間設定を全エントリーに反映 + next_runを再計算
                _acc_entries = []
                for _ei, _e in enumerate(_stor):
                    if _e.get('acc_username') == sel_username:
                        _e['post_interval'] = _new_val
                        _acc_entries.append((_ei, _e))
                # next_runを合間間隔で再スケジュール
                if _new_val and len(_acc_entries) > 1:
                    from datetime import datetime, timedelta, timezone
                    _jst = timezone(timedelta(hours=9))
                    _acc_entries.sort(key=lambda x: x[1].get('next_run', ''))
                    for _j in range(1, len(_acc_entries)):
                        _prev_nr = _acc_entries[_j-1][1].get('next_run', '')
                        _curr_nr = _acc_entries[_j][1].get('next_run', '')
                        if _prev_nr and _curr_nr:
                            try:
                                _prev_t = datetime.fromisoformat(_prev_nr)
                                _curr_t = datetime.fromisoformat(_curr_nr)
                                _gap = (_curr_t - _prev_t).total_seconds() / 3600
                                if _gap < _new_val:
                                    _new_t = _prev_t + timedelta(hours=_new_val)
                                    _acc_entries[_j][1]['next_run'] = _new_t.isoformat()
                            except:
                                pass
                save_json(STORAGE_FILE, _stor)
                st.session_state.storage = _stor

            _iv_key = f"iv_{sel_idx}"
            if _iv_key not in st.session_state:
                st.session_state[_iv_key] = _iv_options[_iv_default]
            _iv_selected = st.selectbox("投稿合間設定", _iv_options, key=_iv_key, on_change=_on_interval_change)
            post_interval = _iv_values[_iv_options.index(_iv_selected)]

            my_posts = [x for x in st.session_state.storage if x.get('acc_username') == sel_username]

            if not my_posts:
                st.info("No scheduled posts. Add one below.")
            elif len(my_posts) > 1:
                _all_paused = all(p.get('paused', False) for p in my_posts)
                _bp1, _bp2 = st.columns(2)
                if _all_paused:
                    if _bp1.button(f"▶️ 全て再開（{len(my_posts)}件）", key=f"bulk_resume_{suffix}"):
                        latest_storage = load_json(STORAGE_FILE)
                        for e in latest_storage:
                            if e.get('acc_username') == sel_username:
                                e['paused'] = False
                        save_json(STORAGE_FILE, latest_storage)
                        st.session_state.storage = latest_storage
                        st.session_state.form_key_suffix = str(uuid.uuid4())
                        st.rerun()
                else:
                    if _bp1.button(f"⏸️ 全て停止（{len(my_posts)}件）", key=f"bulk_pause_{suffix}"):
                        latest_storage = load_json(STORAGE_FILE)
                        for e in latest_storage:
                            if e.get('acc_username') == sel_username:
                                e['paused'] = True
                        save_json(STORAGE_FILE, latest_storage)
                        st.session_state.storage = latest_storage
                        st.session_state.form_key_suffix = str(uuid.uuid4())
                        st.rerun()
                if _bp2.button(f"🗑️ 全削除（{len(my_posts)}件）", key=f"bulk_del_{suffix}"):
                    st.session_state[f"confirm_bulk_del_{sel_username}"] = True
                if st.session_state.get(f"confirm_bulk_del_{sel_username}"):
                    st.warning(f"⚠️ @{sel_username} の自動投稿 {len(my_posts)}件 を全て削除しますか？")
                    _bd1, _bd2 = st.columns(2)
                    if _bd1.button("✅ はい、全削除", key=f"bulk_del_yes_{suffix}"):
                        latest_storage = load_json(STORAGE_FILE)
                        latest_storage = [e for e in latest_storage if e.get('acc_username') != sel_username]
                        save_json(STORAGE_FILE, latest_storage)
                        st.session_state.storage = latest_storage
                        st.session_state[f"confirm_bulk_del_{sel_username}"] = False
                        st.success(f"✅ {len(my_posts)}件 削除しました")
                        st.rerun()
                    if _bd2.button("❌ キャンセル", key=f"bulk_del_no_{suffix}"):
                        st.session_state[f"confirm_bulk_del_{sel_username}"] = False
                        st.rerun()

            for pi, p in enumerate(my_posts):
                try:
                    idx = st.session_state.storage.index(p)
                except ValueError:
                    continue
                st.markdown("---")
                _is_paused = p.get('paused', False)
                _pause_col1, _pause_col2 = st.columns([6, 1])
                n_run = p.get('next_run', '--').replace('T', ' ')[:16]
                posts_queue = p.get('posts', [])
                cur_idx = p.get('current_idx', 0)
                _ft_label = f" ⏰ 毎日 {p['fixed_time']}" if p.get('fixed_time') else ""
                _pause_col1.write(f"**次へ:** {'⏸️' if _is_paused else '🕐'} {n_run}{_ft_label}{' **[停止中]**' if _is_paused else ''}")
                _tkey = f"pause_{idx}_{pi}_{suffix}"
                _toggle_on = not _is_paused  # ON = not paused
                _toggle = _pause_col2.toggle("", value=_toggle_on, key=_tkey)
                # Only act if user actually clicked (not first render)
                _prev_key = f"_prev_toggle_{idx}_{pi}"
                if _prev_key in st.session_state:
                    if st.session_state[_prev_key] != _toggle:
                        new_paused = not _toggle
                        latest_storage = load_json(STORAGE_FILE)
                        if idx < len(latest_storage):
                            latest_storage[idx]['paused'] = new_paused
                        save_json(STORAGE_FILE, latest_storage)
                        st.session_state.storage = latest_storage
                        st.session_state[_prev_key] = _toggle
                        st.rerun()
                st.session_state[_prev_key] = _toggle
                if posts_queue:
                    show_post = posts_queue[cur_idx % len(posts_queue)]
                    show_imgs = show_post.get('saved_image_paths', [])
                    show_text = show_post.get('text', '')
                else:
                    show_imgs = p.get('saved_image_paths', [])
                    show_text = p.get('text', '')
                # Image display (single row, no dynamic columns)
                if show_imgs:
                    first_img = None
                    for img_p in show_imgs:
                        resolved = resolve_image_path(img_p)
                        if resolved:
                            first_img = resolved
                            break
                    if first_img:
                        st.image(first_img, width=200)
                        if len(show_imgs) > 1:
                            st.caption(f"📷 他{len(show_imgs)-1}枚")
                    else:
                        st.caption("📷 画像ファイルが見つかりません")
                st.write(f"{show_text[:120]}{'...' if len(show_text) > 120 else ''}")
                if len(posts_queue) > 1:
                    st.caption(f"全{len(posts_queue)}件のローテーション")
                _b1, _b2 = st.columns(2)
                if _b1.button("消去", key=f"sd_{idx}_{pi}"):
                    latest_storage = load_json(STORAGE_FILE)
                    if idx < len(latest_storage):
                        latest_storage.pop(idx)
                    save_json(STORAGE_FILE, latest_storage)
                    st.session_state.storage = latest_storage
                    st.rerun()
                if _b2.button("編集", key=f"se_{idx}_{pi}"):
                    st.session_state.edit_text = show_text
                    st.session_state.edit_range = tuple(p['time_range'])
                    st.session_state.edit_index = idx
                    st.session_state.edit_images = show_imgs
                    st.session_state.edit_interval = p.get('post_interval')
                    # 固定時間モードの読み込み
                    _ft = p.get('fixed_time')
                    if _ft:
                        st.session_state.edit_schedule_mode = "固定時間"
                        _ftp = _ft.split(':')
                        st.session_state.edit_fixed_hour = int(_ftp[0])
                        st.session_state.edit_fixed_minute = int(_ftp[1])
                    else:
                        st.session_state.edit_schedule_mode = "ランダム"
                    st.session_state.post_queue = []
                    st.session_state.form_key_suffix = str(uuid.uuid4())
                    st.rerun()

            # --- Metrics ---
            st.markdown("---")
            acc_data = st.session_state.accounts[sel_idx]
            metrics = acc_data.get('metrics', {
                'attempts': 0, 'successes': 0, 'failures': 0, 'last_error': 'None'
            })
            att = metrics.get('attempts', 0)
            suc_count = metrics.get('successes', 0)
            fai = metrics.get('failures', 0)
            rate = (suc_count / att * 100) if att > 0 else 0.0

            m1, m2, m3 = st.columns(3)
            m1.metric("Attempts", f"{att}")
            m2.metric("Success", f"{suc_count}")
            m3.metric("Failed", f"{fai}")
            if att > 0:
                st.progress(min(rate / 100.0, 1.0), text=f"Success rate: {rate:.1f}%")

            # --- Post Form ---
            st.markdown("---")
            st.subheader("Create / Edit Post")

            # (Watch Listインポートはボタン押下時に直接edit_text/edit_imagesにセット済み)

            # Load existing queue when editing
            if st.session_state.edit_index is not None and not st.session_state.post_queue:
                entry = st.session_state.storage[st.session_state.edit_index]
                if 'posts' in entry:
                    st.session_state.post_queue = [dict(p) for p in entry['posts']]
                elif entry.get('text'):
                    st.session_state.post_queue = [{"text": entry['text'], "saved_image_paths": entry.get('saved_image_paths', [])}]

            # 投稿モード切り替え
            _mode_options = ["ランダム", "固定時間", "ボックス24時間"]
            _mode_idx = 0
            if st.session_state.edit_schedule_mode == "固定時間":
                _mode_idx = 1
            elif st.session_state.edit_schedule_mode == "ボックス24時間":
                _mode_idx = 2
            _sched_mode = st.radio(
                "投稿モード", _mode_options,
                index=_mode_idx,
                key=f"sched_mode_{suffix}", horizontal=True
            )

            if _sched_mode == "ランダム":
                t_range = st.slider(
                    "投稿時間帯 (JST)", 0, 24,
                    st.session_state.edit_range, key=f"sl_{suffix}"
                )
                fixed_time = None
            elif _sched_mode == "固定時間":
                _ft_col1, _ft_col2 = st.columns(2)
                _ft_hour = _ft_col1.number_input(
                    "時", min_value=0, max_value=23,
                    value=st.session_state.edit_fixed_hour, key=f"fth_{suffix}"
                )
                _ft_min = _ft_col2.number_input(
                    "分", min_value=0, max_value=59,
                    value=st.session_state.edit_fixed_minute, key=f"ftm_{suffix}"
                )
                fixed_time = f"{int(_ft_hour):02d}:{int(_ft_min):02d}"
                t_range = (int(_ft_hour), int(_ft_hour))
            else:
                fixed_time = None
                t_range = (0, 23)

            # ========== ボックス24時間テンプレート ==========
            if _sched_mode == "ボックス24時間":
                st.markdown("---")
                st.markdown("**📦 ボックス24時間テンプレート**")
                st.caption("各時間帯にテキストを入力 → 入力済みの枠だけ固定時間投稿として登録されます（各枠に複数テキスト追加可）")

                # テンプレート読み込み・選択（共通 + 個人）
                _box_templates_all = load_json(BOX_TEMPLATES_FILE) if os.path.exists(BOX_TEMPLATES_FILE) else []
                # 表示対象: 共通テンプレ（acc_usernameなし）+ 現アカウント専用テンプレ
                _box_templates = []
                _tmpl_names = ["新規作成"]
                for _ti, _t in enumerate(_box_templates_all):
                    _t_owner = _t.get('acc_username')
                    if _t_owner is None or _t_owner == sel_username:
                        _box_templates.append(_t)
                        _tname = _t.get('name', f'テンプレ{_ti}')
                        if _t_owner:
                            # 個人テンプレ: アカウント名を表示
                            _acc_display = _t_owner
                            for _ta in st.session_state.accounts:
                                if _ta.get('username') == _t_owner:
                                    _acc_display = _ta.get('name', _t_owner)
                                    break
                            _label = f"👤 {_tname}（{_acc_display}）"
                        else:
                            _label = f"🌐 {_tname}"
                        _tmpl_names.append(_label)

                # テンプレ切替時にキーをリセットする
                _prev_tmpl = st.session_state.get('_box_prev_tmpl', None)
                _tmpl_c1, _tmpl_c2 = st.columns([5, 1])
                _sel_tmpl = _tmpl_c1.selectbox("テンプレート選択", _tmpl_names, key=f"box_sel_{suffix}")
                if _sel_tmpl != "新規作成" and _tmpl_c2.button("🗑️", key=f"tmpl_quick_del_{suffix}"):
                    _del_idx = _tmpl_names.index(_sel_tmpl) - 1
                    if 0 <= _del_idx < len(_box_templates):
                        _del_tmpl = _box_templates[_del_idx]
                        _box_templates_all = [t for t in _box_templates_all if not (t.get('name') == _del_tmpl.get('name') and t.get('acc_username') == _del_tmpl.get('acc_username'))]
                        save_json(BOX_TEMPLATES_FILE, _box_templates_all)
                        st.success("テンプレート削除しました")
                        st.rerun()
                if _prev_tmpl != _sel_tmpl:
                    st.session_state['_box_prev_tmpl'] = _sel_tmpl
                    if _prev_tmpl is not None:
                        st.session_state['_box_key_ver'] = st.session_state.get('_box_key_ver', 0) + 1
                _bkv = st.session_state.get('_box_key_ver', 0)

                # テンプレからスロットをロード（新フォーマット: リスト / 旧フォーマット: 文字列 → リスト変換）
                _loaded_slots = {}
                _loaded_is_personal = False
                if _sel_tmpl != "新規作成":
                    _tmpl_idx = _tmpl_names.index(_sel_tmpl) - 1
                    if 0 <= _tmpl_idx < len(_box_templates):
                        _raw_slots = _box_templates[_tmpl_idx].get('slots', {})
                        _loaded_is_personal = _box_templates[_tmpl_idx].get('acc_username') is not None
                        for _hs, _sv in _raw_slots.items():
                            if isinstance(_sv, list):
                                _loaded_slots[_hs] = _sv
                            else:
                                _loaded_slots[_hs] = [_sv]

                # 選択中テンプレの入力済み枠数・テキスト総数を表示
                _filled_preview = len(_loaded_slots)
                _total_texts = sum(len(v) for v in _loaded_slots.values())
                if _sel_tmpl != "新規作成" and _filled_preview > 0:
                    st.caption(f"📝 {_filled_preview}枠 / {_total_texts}件のテキスト")

                # 適用ボタン（テンプレ選択時、畳んだままでも使える）
                if _sel_tmpl != "新規作成" and _filled_preview > 0:
                    if st.button(f"📤 このアカウントに{_total_texts}件を登録", key=f"box_apply_{suffix}", type="primary"):
                        latest_storage = load_json(STORAGE_FILE)
                        _added = 0
                        for _h_str, _texts in _loaded_slots.items():
                            _h_int = int(_h_str)
                            _fn = get_jst_time()
                            _ft_target = _fn.replace(hour=_h_int, minute=0, second=0)
                            if _ft_target <= _fn:
                                _ft_target += timedelta(days=1)
                            # 複数テキスト → posts配列、ローテーション投稿
                            _posts_arr = [{"text": t.strip(), "saved_image_paths": []} for t in _texts if t.strip()]
                            if not _posts_arr:
                                continue
                            _entry = {
                                "posts": _posts_arr,
                                "current_idx": 0,
                                "text": _posts_arr[0]["text"],
                                "saved_image_paths": [],
                                "acc_username": sel_username,
                                "time_range": [_h_int, _h_int],
                                "today_count": 0,
                                "today_date": "",
                                "next_run": _ft_target.isoformat(),
                                "post_interval": post_interval,
                                "fixed_time": f"{_h_int:02d}:00"
                            }
                            latest_storage.append(_entry)
                            _added += 1
                        save_json(STORAGE_FILE, latest_storage)
                        st.session_state.storage = latest_storage
                        st.success(f"✅ {_added}件の投稿を登録しました！")
                        st.rerun()

                # 編集エリア（折りたたみ）
                with st.expander("📝 テンプレート編集", expanded=(_sel_tmpl == "新規作成")):
                    # テンプレ名からアイコンプレフィックスとアカウント名を除去
                    _tmpl_display_name = _sel_tmpl
                    if _sel_tmpl.startswith("🌐 ") or _sel_tmpl.startswith("👤 "):
                        _tmpl_display_name = _sel_tmpl[2:].strip()
                    # 個人テンプレの「（アカウント名）」部分を除去
                    if "（" in _tmpl_display_name and _tmpl_display_name.endswith("）"):
                        _tmpl_display_name = _tmpl_display_name[:_tmpl_display_name.rfind("（")].strip()
                    _tmpl_name = st.text_input("テンプレート名", value=_tmpl_display_name if _sel_tmpl != "新規作成" else "", key=f"box_name_{suffix}_{_bkv}")
                    _is_personal = st.checkbox(f"👤 個人テンプレート（{sel_username} 専用）", value=_loaded_is_personal, key=f"box_personal_{suffix}_{_bkv}")

                    # セッションでキュー管理（各時間枠の追加テキスト）
                    _sq_key = f"_box_slot_queues_{suffix}_{_bkv}"
                    if _sq_key not in st.session_state:
                        # ロードしたスロットから初期化
                        st.session_state[_sq_key] = {}
                        for _hs, _sv_list in _loaded_slots.items():
                            if len(_sv_list) > 1:
                                st.session_state[_sq_key][_hs] = _sv_list[1:]  # 2番目以降をキューに

                    # 24時間のテキスト入力（下から23時→0時）
                    _box_slots = {}
                    for _h in range(23, -1, -1):
                        _h_str = str(_h)
                        _default_text = _loaded_slots.get(_h_str, [""])[0] if _h_str in _loaded_slots else ""
                        _slot_queue = st.session_state[_sq_key].get(_h_str, [])

                        # メインテキスト入力
                        _sc1, _sc2 = st.columns([8, 1])
                        _slot_text = _sc1.text_input(
                            f"{_h:02d}:00", value=_default_text,
                            key=f"box_{_h}_{suffix}_{_bkv}", label_visibility="visible"
                        )

                        # キュー追加ボタン（＋）
                        if _sc2.button("＋", key=f"boxq_add_{_h}_{suffix}_{_bkv}"):
                            if _h_str not in st.session_state[_sq_key]:
                                st.session_state[_sq_key][_h_str] = []
                            st.session_state[_sq_key][_h_str].append("")
                            st.rerun()

                        # キューのテキスト入力表示
                        _new_queue = []
                        for _qi, _qt in enumerate(_slot_queue):
                            _qc1, _qc2 = st.columns([8, 1])
                            _qt_val = _qc1.text_input(
                                f"{_h:02d}:00 キュー#{_qi+1}", value=_qt,
                                key=f"boxq_{_h}_{_qi}_{suffix}_{_bkv}", label_visibility="collapsed"
                            )
                            if _qc2.button("✕", key=f"boxq_del_{_h}_{_qi}_{suffix}_{_bkv}"):
                                continue  # 削除（追加しない）
                            _new_queue.append(_qt_val)
                        st.session_state[_sq_key][_h_str] = _new_queue

                        # スロットデータ構築（メイン＋キュー）
                        _all_texts = []
                        if _slot_text.strip():
                            _all_texts.append(_slot_text.strip())
                        for _qt in _new_queue:
                            if _qt.strip():
                                _all_texts.append(_qt.strip())
                        if _all_texts:
                            _box_slots[_h_str] = _all_texts

                    # 個人テンプレートチェック（下部にも配置）
                    _is_personal_bottom = st.checkbox(f"👤 個人テンプレート（{sel_username} 専用）", value=_is_personal, key=f"box_personal_bottom_{suffix}_{_bkv}")
                    if _is_personal_bottom != _is_personal:
                        _is_personal = _is_personal_bottom

                    # テンプレート保存ボタン
                    _bc1, _bc2, _bc3 = st.columns(3)
                    if _bc1.button("💾 上書き保存", key=f"box_save_{suffix}_{_bkv}"):
                        if _tmpl_name.strip():
                            _new_tmpl = {"name": _tmpl_name.strip(), "slots": _box_slots}
                            if _is_personal:
                                _new_tmpl["acc_username"] = sel_username
                            _save_name = _tmpl_name.strip()
                            _save_owner = sel_username if _is_personal else None
                            _found = False
                            for _ti, _t in enumerate(_box_templates_all):
                                if _t.get('name') == _save_name and _t.get('acc_username') == _save_owner:
                                    _box_templates_all[_ti] = _new_tmpl
                                    _found = True
                                    break
                            if not _found:
                                _box_templates_all.append(_new_tmpl)
                            save_json(BOX_TEMPLATES_FILE, _box_templates_all)
                            _total_saved = sum(len(v) for v in _box_slots.values())
                            _type_label = "👤 個人" if _is_personal else "🌐 共通"
                            st.success(f"✅ {_type_label}テンプレート「{_tmpl_name}」を保存（{len(_box_slots)}枠 / {_total_saved}件）")
                            st.rerun()
                        else:
                            st.warning("テンプレート名を入力してください")

                    if _bc2.button("📋 新規として保存", key=f"box_saveas_{suffix}_{_bkv}"):
                        if _tmpl_name.strip():
                            _new_tmpl = {"name": _tmpl_name.strip(), "slots": _box_slots}
                            if _is_personal:
                                _new_tmpl["acc_username"] = sel_username
                            # 常に新規追加（同名チェックせず追加）
                            # 同名が既にある場合は末尾に(2)等を付ける
                            _base_name = _tmpl_name.strip()
                            _save_owner = sel_username if _is_personal else None
                            _existing_names = [t.get('name') for t in _box_templates_all if t.get('acc_username') == _save_owner]
                            _final_name = _base_name
                            _cnt = 2
                            while _final_name in _existing_names:
                                _final_name = f"{_base_name}({_cnt})"
                                _cnt += 1
                            _new_tmpl["name"] = _final_name
                            _box_templates_all.append(_new_tmpl)
                            save_json(BOX_TEMPLATES_FILE, _box_templates_all)
                            _total_saved = sum(len(v) for v in _box_slots.values())
                            _type_label = "👤 個人" if _is_personal else "🌐 共通"
                            st.success(f"✅ {_type_label}テンプレート「{_final_name}」を新規保存（{len(_box_slots)}枠 / {_total_saved}件）")
                            st.rerun()
                        else:
                            st.warning("テンプレート名を入力してください")

                    if _bc3.button("🗑️ 削除", key=f"box_del_{suffix}_{_bkv}"):
                        if _sel_tmpl != "新規作成":
                            _del_idx = _tmpl_names.index(_sel_tmpl) - 1
                            if 0 <= _del_idx < len(_box_templates):
                                _del_tmpl = _box_templates[_del_idx]
                                _box_templates_all = [t for t in _box_templates_all if not (t.get('name') == _del_tmpl.get('name') and t.get('acc_username') == _del_tmpl.get('acc_username'))]
                                save_json(BOX_TEMPLATES_FILE, _box_templates_all)
                            st.success(f"テンプレート削除しました")
                            st.rerun()

            _show_normal_form = (_sched_mode != "ボックス24時間")

            # Show current queue
            if _show_normal_form and st.session_state.post_queue:
                q_count = len(st.session_state.post_queue)
                st.markdown(f"**投稿キュー ({q_count} 件)** — 毎日1件ずつローテーション投稿されます")
                for qi, qp in enumerate(st.session_state.post_queue):
                    q_imgs = qp.get('saved_image_paths', [])
                    q_text = qp.get('text', '')
                    img_info = f" 📷{len(q_imgs)}枚" if q_imgs else ""
                    st.caption(f"#{qi+1}{img_info} | {q_text[:80]}{'...' if len(q_text)>80 else ''}")
                    _qcol1, _qcol2 = st.columns(2)
                    if _qcol1.button(f"#{qi+1} を編集", key=f"qedit_{qi}_{suffix}"):
                        st.session_state.edit_text = q_text
                        st.session_state.edit_images = list(q_imgs)
                        st.session_state.post_queue.pop(qi)
                        st.session_state.form_key_suffix = str(uuid.uuid4())
                        st.rerun()
                    if _qcol2.button(f"#{qi+1} を削除", key=f"qdel_{qi}_{suffix}"):
                        st.session_state.post_queue.pop(qi)
                        st.rerun()
                st.markdown("---")

            # Show current images when editing or automating past post
            edit_imgs = st.session_state.edit_images
            if edit_imgs:
                st.success(f"画像 {len(edit_imgs)} 枚がセットされています")
                num_cols = min(len(edit_imgs), 4)
                if num_cols > 0:
                    cols_edit = st.columns(num_cols)
                    displayed_count = 0
                    for j, img_p in enumerate(edit_imgs):
                        resolved = resolve_image_path(img_p)
                        if resolved:
                            try:
                                if isinstance(resolved, str) and resolved.startswith("http"):
                                    _ih = f'<img src="{resolved}" style="width:100%;border-radius:8px;">'
                                    cols_edit[j % num_cols].markdown(_ih, unsafe_allow_html=True)
                                else:
                                    cols_edit[j % num_cols].image(resolved, use_container_width=True)
                                displayed_count += 1
                            except:
                                cols_edit[j % num_cols].caption(f"画像{j+1}: 表示エラー")
                        else:
                            cols_edit[j % num_cols].caption(f"画像{j+1}: ファイル未検出")
                    if displayed_count < len(edit_imgs):
                        st.warning(f"{len(edit_imgs)}枚中{displayed_count}枚のみ表示可能（サーバー上のファイル）")

            # ボックス24時間モード時は通常フォームをスキップ
            if not _show_normal_form:
                txt = ""
                img_files = []
            if _show_normal_form:
              img_files = st.file_uploader(
                "Images (multiple OK)", type=['png', 'jpg', 'jpeg', 'webp', 'gif'],
                accept_multiple_files=True, key=f"fi_{suffix}"
              )

            if _show_normal_form and img_files:
                st.write("Selected images:")
                num_prev = min(len(img_files), 4)
                cols_preview = st.columns(num_prev)
                for j, f in enumerate(img_files):
                    cols_preview[j % num_prev].image(f, use_container_width=True)

            # インポート画像プレビュー
            if _show_normal_form and not img_files and st.session_state.edit_images:
                _ei_urls = [p for p in st.session_state.edit_images if isinstance(p, str) and p.startswith("http")]
                if _ei_urls:
                    st.write(f"インポート画像: {len(_ei_urls)}枚")
                    _ei_cols = st.columns(min(len(_ei_urls), 4))
                    for j, _eiu in enumerate(_ei_urls[:4]):
                        _ei_html = f'<img src="{_eiu}" style="width:100%;border-radius:8px;">'
                        _ei_cols[j].markdown(_ei_html, unsafe_allow_html=True)

            if _show_normal_form:
                txt = st.text_area(
                    "Post text", value=st.session_state.edit_text,
                    key=f"tx_{suffix}", height=150
                )

            if _show_normal_form:
              col1, col2, col3, col4, col5 = st.columns([1, 1, 1, 1, 0.8])

            # Add to queue button
            if _show_normal_form and col1.button("キューに追加", key="add_queue"):
                saved_paths = []
                if img_files:
                    for f in img_files:
                        path = os.path.abspath(os.path.join(IMAGE_DIR, f"{uuid.uuid4()}_{f.name}"))
                        with open(path, "wb") as out:
                            out.write(f.getbuffer())
                        saved_paths.append(path)
                elif st.session_state.edit_images:
                    for _ei in st.session_state.edit_images:
                        if isinstance(_ei, str) and ("YOUR_SERVER_IP/" in _ei):
                            _local = os.path.join(os.path.dirname(os.path.abspath(__file__)), _ei.split("YOUR_SERVER_IP/")[1])
                            if os.path.exists(_local):
                                saved_paths.append(_local)
                        elif isinstance(_ei, str):
                            saved_paths.append(_ei)
                st.session_state.post_queue.append({"text": txt, "saved_image_paths": saved_paths})
                st.session_state.edit_text = ""
                # 画像はキュー追加後も残す（テキストのみリセット）
                st.rerun()

            # Save all button
            if _show_normal_form and col2.button("保存", key="save_post"):
                # If queue is empty, save current form as single post
                queue = list(st.session_state.post_queue)
                if not queue:
                    saved_paths = []
                    if img_files:
                        for f in img_files:
                            path = os.path.abspath(os.path.join(IMAGE_DIR, f"{uuid.uuid4()}_{f.name}"))
                            with open(path, "wb") as out:
                                out.write(f.getbuffer())
                            saved_paths.append(path)
                    elif st.session_state.edit_images:
                        for _ei in st.session_state.edit_images:
                            if isinstance(_ei, str) and ("YOUR_SERVER_IP/" in _ei):
                                _local = os.path.join(os.path.dirname(os.path.abspath(__file__)), _ei.split("YOUR_SERVER_IP/")[1])
                                if os.path.exists(_local):
                                    saved_paths.append(_local)
                            elif isinstance(_ei, str):
                                saved_paths.append(_ei)
                    queue = [{"text": txt, "saved_image_paths": saved_paths}]
                elif len(queue) == 1:
                    # 編集モード: フォームのテキスト・画像でキューの1件目を更新
                    saved_paths = []
                    if img_files:
                        for f in img_files:
                            path = os.path.abspath(os.path.join(IMAGE_DIR, f"{uuid.uuid4()}_{f.name}"))
                            with open(path, "wb") as out:
                                out.write(f.getbuffer())
                            saved_paths.append(path)
                    elif st.session_state.edit_images:
                        for _ei in st.session_state.edit_images:
                            if isinstance(_ei, str) and ("YOUR_SERVER_IP/" in _ei):
                                _local = os.path.join(os.path.dirname(os.path.abspath(__file__)), _ei.split("YOUR_SERVER_IP/")[1])
                                if os.path.exists(_local):
                                    saved_paths.append(_local)
                            elif isinstance(_ei, str):
                                saved_paths.append(_ei)
                    else:
                        saved_paths = queue[0].get('saved_image_paths', [])
                    queue[0] = {"text": txt, "saved_image_paths": saved_paths}

                # 固定時間モードのnext_run計算
                if fixed_time:
                    _fh, _fm = map(int, fixed_time.split(':'))
                    _fn = get_jst_time()
                    _ft_target = _fn.replace(hour=_fh, minute=_fm, second=0)
                    if _ft_target <= _fn:
                        _ft_target += timedelta(days=1)
                    _next_run = _ft_target.isoformat()
                else:
                    _next_run = calculate_next_run(t_range)

                new_entry = {
                    "posts": queue,
                    "current_idx": 0,
                    "text": queue[0].get('text', ''),
                    "saved_image_paths": queue[0].get('saved_image_paths', []),
                    "acc_username": sel_username,
                    "time_range": list(t_range),
                    "today_count": 0,
                    "today_date": "",
                    "next_run": _next_run,
                    "post_interval": post_interval,
                    "fixed_time": fixed_time
                }
                if st.session_state.edit_index is not None and st.session_state.edit_index < len(st.session_state.storage):
                    old_entry = st.session_state.storage[st.session_state.edit_index]
                    if 'last_posted_at' in old_entry:
                        new_entry['last_posted_at'] = old_entry['last_posted_at']
                    if 'current_idx' in old_entry:
                        new_entry['current_idx'] = old_entry['current_idx'] % len(queue)
                    if 'today_count' in old_entry:
                        new_entry['today_count'] = old_entry['today_count']
                        new_entry['today_date'] = old_entry.get('today_date', '')
                    # next_run: time_rangeやfixed_timeが変わった場合は再計算、同じなら引き継ぎ
                    old_tr = old_entry.get('time_range')
                    old_ft = old_entry.get('fixed_time')
                    if old_tr == list(t_range) and old_ft == fixed_time and 'next_run' in old_entry:
                        new_entry['next_run'] = old_entry['next_run']
                    # else: 新しく計算済みの_next_runをそのまま使う
                    if 'retry_count' in old_entry:
                        new_entry['retry_count'] = old_entry['retry_count']
                latest_storage = load_json(STORAGE_FILE)
                if st.session_state.edit_index is not None:
                    if st.session_state.edit_index < len(latest_storage):
                        latest_storage[st.session_state.edit_index] = new_entry
                    else:
                        latest_storage.append(new_entry)
                else:
                    latest_storage.append(new_entry)
                # 合間設定を同じアカウントの全エントリーに同期
                for _si, _se in enumerate(latest_storage):
                    if _se.get('acc_username') == sel_username:
                        latest_storage[_si]['post_interval'] = post_interval
                save_json(STORAGE_FILE, latest_storage)
                st.session_state.storage = latest_storage
                st.session_state.edit_text = ""
                st.session_state.edit_range = (12, 15)
                st.session_state.edit_interval = post_interval  # 合間設定を保持
                # 投稿モードを保持（固定で保存したら次も固定から）
                st.session_state.edit_schedule_mode = _sched_mode
                if fixed_time:
                    _ftp = fixed_time.split(':')
                    st.session_state.edit_fixed_hour = int(_ftp[0])
                    st.session_state.edit_fixed_minute = int(_ftp[1])

                st.session_state.edit_index = None
                st.session_state.edit_images = []
                st.session_state.post_queue = []
                st.session_state.form_key_suffix = str(uuid.uuid4())
                st.rerun()

            if _show_normal_form and col3.button("Test", key="test_post"):
                old_p = st.session_state.edit_images or []
                suc_t, msg_t = test_connection_only(
                    st.session_state.accounts[sel_idx], txt, img_files, old_p
                )
                if suc_t:
                    st.success(msg_t)
                else:
                    st.error(msg_t)

            if _show_normal_form and col4.button("Real Post Test", key="real_test"):
                with st.spinner("Posting to Threads... (up to 1 min)"):
                    old_p = st.session_state.edit_images or []
                    suc_t, msg_t = real_post_test(
                        st.session_state.accounts[sel_idx], txt, img_files, old_p
                    )
                    if suc_t:
                        st.success(msg_t)
                    else:
                        st.error(msg_t)

            if _show_normal_form and col5.button("🗑 削除", key="del_editing"):
                if st.session_state.edit_index is not None:
                    latest_storage = load_json(STORAGE_FILE)
                    if st.session_state.edit_index < len(latest_storage):
                        latest_storage.pop(st.session_state.edit_index)
                    save_json(STORAGE_FILE, latest_storage)
                    st.session_state.storage = latest_storage
                st.session_state.edit_text = ""
                st.session_state.edit_range = (12, 15)
                # 合間設定はアカウントレベルなので残りエントリーから保持
                _remaining_interval = None
                for _re in (latest_storage if 'latest_storage' in dir() else st.session_state.storage):
                    if _re.get('acc_username') == sel_username and _re.get('post_interval') is not None:
                        _remaining_interval = _re['post_interval']
                        break
                st.session_state.edit_interval = _remaining_interval

                st.session_state.edit_index = None
                st.session_state.edit_images = []
                st.session_state.post_queue = []
                st.session_state.form_key_suffix = str(uuid.uuid4())
                st.rerun()

            # --- Past Posts Automation ---
            st.markdown("---")
            st.subheader("過去の投稿を自動化")
            st.caption("このアカウントの過去の投稿を取得して、ワンクリックで自動投稿に追加できます")

            pp_col1, pp_col2 = st.columns([1, 1])
            pp_limit = pp_col1.selectbox("取得件数", [10, 25, 50], index=1, key=f"pp_limit_{sel_idx}")
            if pp_col2.button("過去の投稿を取得", key=f"fetch_past_{sel_idx}"):
                with st.spinner("投稿を取得中..."):
                    ok, result = fetch_user_threads(st.session_state.accounts[sel_idx], limit=pp_limit)
                    if ok:
                        st.session_state.past_posts = result
                        st.success(f"{len(result)} 件の投稿を取得しました")
                    else:
                        st.error(f"取得失敗: {result}")
                        st.session_state.past_posts = []

            if st.session_state.past_posts:
                # Cache carousel children URLs to avoid re-fetching
                if 'carousel_cache' not in st.session_state:
                    st.session_state.carousel_cache = {}

                st.caption(f"表示中: {len(st.session_state.past_posts)} 件")
                for pi, pp in enumerate(st.session_state.past_posts):
                    pp_text = (pp.get('text') or '')
                    pp_date = (pp.get('timestamp') or '')[:10]
                    pp_likes = pp.get('like_count', 0)
                    pp_type = pp.get('media_type', 'TEXT')
                    pp_link = pp.get('permalink', '')

                    with st.container():
                        pp_media_url = pp.get('media_url', '')
                        is_video = pp_type == 'VIDEO'
                        has_media = pp_type in ('IMAGE', 'VIDEO', 'CAROUSEL_ALBUM') or pp_media_url

                        # Get carousel children (pre-fetched or cached fallback)
                        child_urls = pp.get('_child_urls', [])
                        if not child_urls and pp_type == 'CAROUSEL_ALBUM':
                            cache_key = pp.get('id', '')
                            if cache_key in st.session_state.carousel_cache:
                                child_urls = st.session_state.carousel_cache[cache_key]
                            else:
                                child_urls = fetch_carousel_children(st.session_state.accounts[sel_idx], pp.get('id'))
                                if cache_key:
                                    st.session_state.carousel_cache[cache_key] = child_urls

                        # Media label
                        if pp_type == 'VIDEO':
                            media_label = "🎥 動画"
                        elif pp_type == 'IMAGE':
                            media_label = "📷 1枚"
                        elif pp_type == 'CAROUSEL_ALBUM':
                            img_count = len(child_urls) if child_urls else "複数"
                            media_label = f"📷 {img_count}枚"
                        elif pp_media_url:
                            media_label = "📷 1枚"
                        else:
                            media_label = ""

                        st.write(f"**#{pi+1}** {pp_date} | ❤ {pp_likes} | {pp_type} {media_label}")
                        st.caption(f"{pp_text[:200]}{'...' if len(pp_text)>200 else ''}")
                        # Show media (image/video/carousel)
                        if pp_type == 'CAROUSEL_ALBUM' and child_urls:
                            num_img_cols = min(len(child_urls), 4)
                            img_cols = st.columns(num_img_cols)
                            for ci, curl in enumerate(child_urls):
                                try:
                                    img_cols[ci % num_img_cols].image(curl, width=150)
                                except:
                                    img_cols[ci % num_img_cols].caption(f"画像{ci+1}: 表示エラー")
                        elif is_video and pp_media_url:
                            try:
                                st.video(pp_media_url)
                            except:
                                st.caption("動画: 表示エラー")
                        elif pp_media_url:
                            try:
                                st.image(pp_media_url, width=180)
                            except:
                                pass
                        pp_b1, pp_b2 = st.columns([1, 1])
                        media_count_label = ""
                        if pp_type == 'CAROUSEL_ALBUM' and child_urls:
                            media_count_label = f" ({len(child_urls)}枚)"
                        elif pp_type == 'VIDEO':
                            media_count_label = ""
                        elif has_media:
                            media_count_label = " (1枚)"
                        if is_video:
                            btn_label = "🎥 動画付きで自動化"
                        elif has_media:
                            btn_label = f"📷 画像付きで自動化{media_count_label}"
                        else:
                            btn_label = "この投稿を自動化"
                        if pp_b1.button(btn_label, key=f"automate_pp_{pi}"):
                            saved_media_paths = []
                            if has_media:
                                with st.spinner("メディアをダウンロード中..."):
                                    saved_media_paths = download_post_images(
                                        st.session_state.accounts[sel_idx], pp,
                                        cached_child_urls=child_urls if child_urls else None
                                    )
                            # Add to queue AND reflect in edit area
                            st.session_state.post_queue.append({
                                "text": pp_text,
                                "saved_image_paths": saved_media_paths
                            })
                            st.session_state.edit_text = pp_text
                            st.session_state.edit_images = saved_media_paths
                            st.session_state.edit_index = None
                            st.session_state.form_key_suffix = str(uuid.uuid4())
                            st.rerun()
                        if pp_link:
                            pp_b2.markdown(f"[Threadsで見る]({pp_link})")

        # ========== RIGHT: Watch List ==========
        with comp_col:
            st.subheader("Watch List")
            st.caption("Save competitor Threads profiles for quick access")

            competitors = load_json(COMPETITORS_FILE)
            if not isinstance(competitors, list):
                competitors = []

            # アカウント検索から追加
            with st.expander("🔍 アカウント検索から追加"):
                _new_uname = st.text_input("ユーザー名", placeholder="@username", key="wl_search_input")
                if st.button("追加", key="wl_search_add"):
                    if _new_uname:
                        _uname = _new_uname.replace("@", "").strip()
                        _existing = [c.get('username', '') for c in competitors]
                        if _uname and _uname not in _existing:
                            competitors.append({
                                "username": _uname,
                                "added": get_jst_time().strftime('%Y-%m-%d')
                            })
                            save_json(COMPETITORS_FILE, competitors)
                            st.rerun()
                        elif _uname in _existing:
                            st.warning("登録済みです")

            # Watch Listアカウント選択
            if not competitors:
                st.info("アカウントを追加してください")
            else:
                _sort_opt = st.radio("並び順", ["追加順", "最新追加順", "名前順"], horizontal=True, key="wl_sort", label_visibility="collapsed")
                _sorted_comps = list(competitors)
                if _sort_opt == "最新追加順":
                    _sorted_comps = list(reversed(_sorted_comps))
                elif _sort_opt == "名前順":
                    _sorted_comps = sorted(_sorted_comps, key=lambda c: c.get('username', ''))
                _comp_names = [f"@{c.get('username', '')}" for c in _sorted_comps]
                _wl_c1, _wl_c2, _wl_c3 = st.columns([4, 1, 1])
                _sel_comp_name = _wl_c1.selectbox("アカウント選択", _comp_names, key="wl_comp_sel")
                _sel_comp_uname = _sel_comp_name.replace("@", "").strip()
                _wl_c2.link_button("開ける", f"https://www.threads.net/@{_sel_comp_uname}")
                if _wl_c3.button("🗑️ 削除", key="wl_del_comp"):
                    competitors = [c for c in competitors if c.get('username') != _sel_comp_uname]
                    save_json(COMPETITORS_FILE, competitors)
                    st.session_state.selected_comp = None
                    st.rerun()
                st.session_state.selected_comp = _sel_comp_uname

            if st.session_state.selected_comp:
                st.subheader(f"@{st.session_state.selected_comp}")

                # 別ウィンドウで開くボタン
                components.html(f"""
                <button onclick="var w=window.open('https://www.threads.net/@{st.session_state.selected_comp}', '_blank', 'width=420,height=750,scrollbars=yes,resizable=yes,noopener'); if(w)w.focus();"
                    style="background:linear-gradient(90deg,#00c6ff,#0072ff);color:white;border:none;
                    border-radius:8px;padding:10px 20px;font-weight:bold;cursor:pointer;font-size:14px;
                    width:100%;margin-bottom:10px;">
                    🔗 @{st.session_state.selected_comp} を別ウィンドウで開く
                </button>
                """, height=55)

                # Playwright-based post fetch (no API needed)
                comp_cache_key = f"comp_posts_{st.session_state.selected_comp}"
                if st.button("📜 過去投稿を取得", key="fetch_comp_posts"):
                    with st.spinner(f"@{st.session_state.selected_comp} の投稿を取得中..."):
                        try:
                            from playwright.sync_api import sync_playwright as _sp
                            import re as _re
                            _comp_posts = []
                            with _sp() as _pw:
                                _br = _pw.chromium.launch(headless=True)
                                _pg = _br.new_page()
                                _pg.goto(f"https://www.threads.net/@{st.session_state.selected_comp}", wait_until="domcontentloaded", timeout=60000)
                                _pg.wait_for_timeout(2000)
                                # 「Threads」タブをクリックして最新順を確保（Pinnedタブ回避）
                                try:
                                    _threads_tab = _pg.query_selector("text=Threads")
                                    if _threads_tab:
                                        _threads_tab.click()
                                        _pg.wait_for_timeout(1500)
                                except:
                                    pass
                                # Scroll down to load more posts
                                for _ in range(3):
                                    _pg.evaluate("window.scrollBy(0, 1000)")
                                    _pg.wait_for_timeout(1000)
                                # Get all article/post elements
                                _articles = _pg.query_selector_all("div[data-pressable-container='true']")
                                if not _articles:
                                    _articles = _pg.query_selector_all("article")
                                for _art in _articles[:20]:
                                    try:
                                        _txt = _art.inner_text()
                                        _lines = [l.strip() for l in _txt.split("\n") if l.strip()]
                                        # Skip navigation, metadata, username, likes, Translate etc
                                        _skip_words = {"Threads", "Replies", "Reposts", "Pinned", "Follow", "Following", "Translate", "More", "Reply", "Like", "Share", "Verified", "Log in", "Sign up", "Mention", "Comment", "Repost"}
                                        _comp_user = st.session_state.selected_comp
                                        _content_lines = []
                                        for _l in _lines:
                                            if len(_l) <= 1:
                                                continue
                                            if _l in _skip_words:
                                                continue
                                            # Skip username
                                            if _l == _comp_user or _l.startswith("@"):
                                                continue
                                            # Skip pure alphanumeric (usernames)
                                            if _re.match(r'^[a-zA-Z0-9_.]+$', _l) and len(_l) < 30:
                                                continue
                                            # Skip counts (2.5K, 123, 1K)
                                            if _re.match(r'^[\d,.]+[KMkm]?$', _l):
                                                continue
                                            # Skip date patterns
                                            if _re.match(r'^\d+[hmd]$|^\d{1,2}/\d{1,2}/\d{2,4}$|^\d+\s*(時間|分|日|秒)', _l):
                                                continue
                                            # Skip "Translate" anywhere
                                            if _l.strip() == "Translate":
                                                continue
                                            # Skip lines containing UI junk (Like/Comment/Repost/Share/Translate combined)
                                            if _re.search(r'(Translate|Like\d|Comment\d|Repost\w|Share$|More$)', _l):
                                                continue
                                            # Skip lines that are just "More" suffix or start with username+time pattern
                                            if _re.match(r'^[a-zA-Z0-9_.]+\d+[hmd]', _l):
                                                continue
                                            # Skip lines that are username+More or username+time+More patterns
                                            if _re.match(r'^[a-zA-Z0-9_.]+More$', _l):
                                                continue
                                            # Skip concatenated UI text (TranslateLike407Comment21RepostShare etc)
                                            if _re.search(r'(TranslateLike|Like\d+Comment|Comment\d+Repost|RepostShare)', _l):
                                                continue
                                            _content_lines.append(_l)
                                        if _content_lines:
                                            # Find date-like patterns
                                            _date_str = ""
                                            for _l in _lines:
                                                if _re.match(r"^\d+[hmd]$|^\d{1,2}/\d{1,2}/\d{2,4}$|^\d+\s*(時間|分|日|秒)", _l):
                                                    _date_str = _l
                                                    break
                                            # Find links
                                            _links = _art.query_selector_all("a[href*='/post/']")
                                            _permalink = ""
                                            for _lnk in _links:
                                                _href = _lnk.get_attribute("href") or ""
                                                if "/post/" in _href:
                                                    _permalink = f"https://www.threads.net{_href}" if _href.startswith("/") else _href
                                                    break
                                            # 画像取得→サーバーにダウンロード
                                            _images = []
                                            _img_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images", "watchlist")
                                            os.makedirs(_img_dir, exist_ok=True)
                                            for _img in _art.query_selector_all("img"):
                                                _src = _img.get_attribute("src") or ""
                                                _alt = _img.get_attribute("alt") or ""
                                                if _src and "cdninstagram" in _src and "profile" not in _alt.lower() and "s150x150" not in _src:
                                                    try:
                                                        _ir = requests.get(_src, timeout=10)
                                                        if _ir.status_code == 200:
                                                            _ifn = f"wl_{st.session_state.selected_comp}_{len(_comp_posts)}_{len(_images)}.jpg"
                                                            _ifp = os.path.join(_img_dir, _ifn)
                                                            with open(_ifp, 'wb') as _f:
                                                                _f.write(_ir.content)
                                                            _images.append(f"http://YOUR_SERVER_IP/images/watchlist/{_ifn}")
                                                    except:
                                                        pass
                                            _post_text = "\n".join(_content_lines[:5])
                                            if len(_post_text) > 5:
                                                _comp_posts.append({
                                                    "text": _post_text,
                                                    "date": _date_str,
                                                    "permalink": _permalink,
                                                    "images": _images
                                                })
                                    except:
                                        pass
                                _pg.close()
                                _br.close()
                            if _comp_posts:
                                st.session_state[comp_cache_key] = _comp_posts
                                st.success(f"✅ {len(_comp_posts)}件の投稿を取得しました")
                            else:
                                st.warning("投稿が見つかりませんでした")
                        except Exception as _e:
                            st.error(f"取得エラー: {str(_e)[:100]}")

                # 自動化に使う成功メッセージ
                if st.session_state.get('_wl_used'):
                    st.success("✅ 投稿を反映しました（左側のエディタに反映済み）")
                    st.session_state._wl_used = False

                if comp_cache_key in st.session_state and st.session_state[comp_cache_key]:
                    _all_posts = st.session_state[comp_cache_key]
                    _total_posts = len(_all_posts)
                    # 10件ずつ区切って表示
                    for _chunk_start in range(0, _total_posts, 10):
                        _chunk_end = min(_chunk_start + 10, _total_posts)
                        _chunk_label = f"📄 {_chunk_start+1}～{_chunk_end}件目"
                        _expanded = (_chunk_start == 0)
                        with st.expander(_chunk_label, expanded=_expanded):
                            for ci in range(_chunk_start, _chunk_end):
                                cp = _all_posts[ci]
                                _date_label = f" ({cp['date']})" if cp.get('date') else ""
                                st.markdown(f"**{ci+1}.{_date_label}**")
                                st.caption(cp.get('text', '')[:300])
                                if cp.get('images'):
                                    _img_html = "".join(f'<img src="{u}" style="width:120px;height:120px;object-fit:cover;border-radius:8px;margin-right:6px;">' for u in cp['images'][:3])
                                    st.markdown(f'<div style="display:flex;gap:4px;">{_img_html}</div>', unsafe_allow_html=True)
                                _cp_c1, _cp_c2 = st.columns([1, 1])
                                if cp.get('permalink'):
                                    _cp_c1.caption(f"[Threadsで見る]({cp['permalink']})")
                                if _cp_c2.button("📥 自動化に使う", key=f"wl_use_{ci}"):
                                    _cp_text = cp.get('text', '')[:300]
                                    _cp_imgs = list(cp.get('images', []))
                                    st.session_state.edit_text = _cp_text
                                    st.session_state.edit_images = _cp_imgs
                                    st.session_state.form_key_suffix = str(__import__('uuid').uuid4())
                                    # 過去投稿キャッシュを保持したままrerun
                                    st.session_state._wl_used = True
                                    st.rerun()



    # ==================== リピート投稿 ====================
    st.markdown("---")
    st.subheader("🔁 リピート投稿")
    st.caption("画像は共通、テキストだけ切り替えて繰り返し投稿")

    _rp_data = load_json(REPEAT_POSTS_FILE) if os.path.exists(REPEAT_POSTS_FILE) else []

    with st.expander("➕ 新規作成 / 編集", expanded='_rp_edit_pending' in st.session_state and st.session_state.get('_rp_edit_pending') is not None):
        _rp_edit = st.session_state.get('_rp_edit_pending')
        _rp_acc_uname = _rp_edit.get('acc_username', sel_username) if _rp_edit else sel_username

        # 画像アップロード（共通）
        _rp_images = st.file_uploader("共通画像（任意）", type=["png", "jpg", "jpeg", "webp", "gif"], accept_multiple_files=True, key="rp_images")

        # アップロード画像プレビュー
        if _rp_images:
            st.caption(f"アップロード画像: {len(_rp_images)}枚")
            _up_cols = st.columns(min(len(_rp_images), 4))
            for _up_i, _up_file in enumerate(_rp_images):
                _up_cols[_up_i % 4].image(_up_file, width=150)

        # 既存画像表示（編集時）
        _rp_existing_imgs = []
        if _rp_edit and _rp_edit.get('images'):
            _rp_existing_imgs = _rp_edit['images']
            st.caption(f"既存画像: {len(_rp_existing_imgs)}枚")
            _img_cols = st.columns(min(len(_rp_existing_imgs), 4))
            for _img_i, _img_path in enumerate(_rp_existing_imgs):
                if os.path.exists(_img_path):
                    _img_cols[_img_i % 4].image(_img_path, width=150)

        # テキストエントリ管理（動的追加）
        if '_rp_entry_count' not in st.session_state:
            st.session_state._rp_entry_count = len(_rp_edit.get('entries', [])) if _rp_edit and _rp_edit.get('entries') else 1

        # 編集モード切替時にエントリ数を合わせる
        if _rp_edit and st.session_state.get('_rp_edit_id') != _rp_edit.get('id'):
            st.session_state._rp_entry_count = len(_rp_edit.get('entries', []))
            st.session_state._rp_edit_id = _rp_edit.get('id')

        # 各エントリのテキストと日数
        _rp_entries = []
        for _ei in range(st.session_state._rp_entry_count):
            _ec1, _ec2, _ec3 = st.columns([4, 1, 0.5])
            _default_text = ""
            _default_days = 5
            if _rp_edit and _ei < len(_rp_edit.get('entries', [])):
                _default_text = _rp_edit['entries'][_ei].get('text', '')
                _default_days = _rp_edit['entries'][_ei].get('days', 5)
            _rp_key_suffix = st.session_state.get('_rp_edit_id', 'new')
            _e_text = _ec1.text_area(f"テキスト {_ei+1}", value=_default_text, height=80, key=f"rp_text_{_ei}_{_rp_key_suffix}")
            _e_days = _ec2.number_input(f"日数", min_value=1, max_value=365, value=_default_days, step=1, key=f"rp_days_{_ei}")
            if st.session_state._rp_entry_count > 1:
                if _ec3.button("✖", key=f"rp_del_entry_{_ei}"):
                    st.session_state._rp_entry_count -= 1
                    st.rerun()
            _rp_entries.append({"text": _e_text, "days": _e_days})

        if st.button("➕ テキスト追加", key="rp_add_entry"):
            st.session_state._rp_entry_count += 1
            st.rerun()

        # ========== テキストテンプレートボックス ==========
        with st.expander("📦 テキストテンプレート"):
            _rpt_file = REPEAT_TEMPLATES_FILE
            _rpt_data = load_json(_rpt_file) if os.path.exists(_rpt_file) else []

            # テンプレート選択 & 読み込み
            _rpt_names = ["選択してください"] + [t.get('name', '無名') for t in _rpt_data]
            _rpt_sel_col, _rpt_del_col = st.columns([3, 1])
            _rpt_sel = _rpt_sel_col.selectbox("テンプレート", _rpt_names, key="rpt_select")

            if _rpt_sel != "選択してください":
                _rpt_idx = _rpt_names.index(_rpt_sel) - 1
                if _rpt_idx >= 0 and _rpt_idx < len(_rpt_data):
                    _rpt_tmpl = _rpt_data[_rpt_idx]
                    _rpt_entries = _rpt_tmpl.get('entries', [])

                    # プレビュー
                    for _ti, _te in enumerate(_rpt_entries):
                        st.caption(f"テキスト{_ti+1} ({_te.get('days',5)}日): {_te.get('text','')[:50]}...")

                    _rpt_load_col, _rpt_rm_col = st.columns([1, 1])
                    if _rpt_load_col.button("📥 読み込み", key="rpt_load"):
                        st.session_state._rp_edit_pending = {
                            "id": str(__import__('uuid').uuid4())[:8],
                            "acc_username": sel_username,
                            "images": [],
                            "entries": _rpt_entries,
                            "current_entry_idx": 0,
                            "days_on_current": 0,
                            "last_posted_date": None,
                            "time_start": 0,
                            "time_end": 24,
                            "active": True
                        }
                        st.session_state._rp_entry_count = len(_rpt_entries)
                        if '_rp_edit_id' in st.session_state:
                            del st.session_state._rp_edit_id
                        st.rerun()
                    if _rpt_rm_col.button("🗑️ 削除", key="rpt_delete"):
                        _rpt_data.pop(_rpt_idx)
                        save_json(_rpt_file, _rpt_data)
                        st.success("テンプレート削除しました")
                        st.rerun()

            st.markdown("---")
            # 現在のテキストをテンプレートとして保存
            _rpt_save_name = st.text_input("テンプレート名", key="rpt_save_name")
            if st.button("💾 テンプレートとして保存", key="rpt_save"):
                _valid = [e for e in _rp_entries if e['text'].strip()]
                if not _rpt_save_name.strip():
                    st.warning("テンプレート名を入力してください")
                elif not _valid:
                    st.warning("テキストを1つ以上入力してください")
                else:
                    # 同名があれば上書き
                    _rpt_data = [t for t in _rpt_data if t.get('name') != _rpt_save_name.strip()]
                    _rpt_data.append({
                        "name": _rpt_save_name.strip(),
                        "entries": _valid
                    })
                    save_json(_rpt_file, _rpt_data)
                    st.success(f"✅ 「{_rpt_save_name}」を保存しました")
                    st.rerun()

        # 投稿時間帯
        _rp_default_range = (_rp_edit.get('time_start', 0), _rp_edit.get('time_end', 24)) if _rp_edit else (0, 24)
        _rp_time_range = st.slider("投稿時間帯 (JST)", 0, 24, _rp_default_range, key="rp_time_range")
        _rp_time_start = _rp_time_range[0]
        _rp_time_end = _rp_time_range[1]

        _rp_save_col, _rp_clear_col = st.columns([1, 1])
        if _rp_clear_col.button("🗑️ クリア", key="rp_clear_btn"):
            st.session_state._rp_edit_pending = None
            st.session_state._rp_entry_count = 1
            if '_rp_edit_id' in st.session_state:
                del st.session_state._rp_edit_id
            st.rerun()
        if _rp_save_col.button("💾 保存", key="rp_save_btn", type="primary"):
            if not _rp_acc_uname:
                st.warning("アカウントを選択してください")
            elif not any(e['text'].strip() for e in _rp_entries):
                st.warning("テキストを1つ以上入力してください")
            else:
                # 画像保存
                _rp_img_paths = list(_rp_existing_imgs)
                if _rp_images:
                    _rp_img_dir = os.path.join(BASE_DIR, "repeat_images")
                    os.makedirs(_rp_img_dir, exist_ok=True)
                    _rp_img_paths = []
                    for _uf in _rp_images:
                        _img_path = os.path.join(_rp_img_dir, f"{_rp_acc_uname}_{_uf.name}")
                        with open(_img_path, "wb") as _f:
                            _f.write(_uf.getvalue())
                        _rp_img_paths.append(_img_path)

                # エントリ（空テキスト除外）
                _valid_entries = [e for e in _rp_entries if e['text'].strip()]

                _rp_new = {
                    "id": _rp_edit['id'] if _rp_edit else str(__import__('uuid').uuid4())[:8],
                    "acc_username": _rp_acc_uname,
                    "images": _rp_img_paths,
                    "entries": _valid_entries,
                    "current_entry_idx": _rp_edit.get('current_entry_idx', 0) if _rp_edit else 0,
                    "days_on_current": _rp_edit.get('days_on_current', 0) if _rp_edit else 0,
                    "last_posted_date": _rp_edit.get('last_posted_date') if _rp_edit else None,
                    "time_start": int(_rp_time_start),
                    "time_end": int(_rp_time_end),
                    "active": True
                }

                # 更新 or 追加
                _rp_found = False
                for _ri, _rd in enumerate(_rp_data):
                    if _rd['id'] == _rp_new['id']:
                        _rp_data[_ri] = _rp_new
                        _rp_found = True
                        break
                if not _rp_found:
                    _rp_data.append(_rp_new)

                save_json(REPEAT_POSTS_FILE, _rp_data)
                st.session_state._rp_edit_pending = None
                st.success("✅ 保存しました")
                st.rerun()

    # 一覧表示
    if _rp_data:
        for _rpi, _rpd in enumerate(_rp_data):
            _rp_uname = _rpd.get('acc_username', '?')
            # 選択中のアカウントのみ表示
            if _rp_uname != sel_username:
                continue
            _rp_entries_info = _rpd.get('entries', [])
            _rp_cur = _rpd.get('current_entry_idx', 0)
            _rp_days_cur = _rpd.get('days_on_current', 0)
            _rp_active = _rpd.get('active', True)
            _rp_total_days = sum(e.get('days', 1) for e in _rp_entries_info)
            _rp_status = "🟢" if _rp_active else "⏸️"

            # 現在のエントリ情報
            _cur_entry = _rp_entries_info[_rp_cur] if _rp_cur < len(_rp_entries_info) else {}
            _cur_text_preview = _cur_entry.get('text', '')[:30]
            _cur_days_total = _cur_entry.get('days', 1)

            _rp_hdr = f"{_rp_status} **@{_rp_uname}** | {len(_rp_entries_info)}パターン | 現在: {_rp_cur+1}番目（{_rp_days_cur}/{_cur_days_total}日目）| 画像{len(_rpd.get('images',[]))}枚"
            st.markdown(_rp_hdr)
            # 画像プレビュー表示
            _rp_imgs = _rpd.get('images', [])
            if _rp_imgs:
                _rp_img_cols = st.columns(min(len(_rp_imgs), 4))
                for _img_i, _img_path in enumerate(_rp_imgs):
                    if os.path.exists(_img_path):
                        _rp_img_cols[_img_i % 4].image(_img_path, width=150)
            st.caption(f"現在のテキスト: {_cur_text_preview}...")

            _rp_bc1, _rp_bc2, _rp_bc3 = st.columns(3)
            # 一時停止/再開
            if _rp_active:
                if _rp_bc1.button("⏸️ 停止", key=f"rp_pause_{_rpi}"):
                    _rp_data[_rpi]['active'] = False
                    save_json(REPEAT_POSTS_FILE, _rp_data)
                    st.rerun()
            else:
                if _rp_bc1.button("▶️ 再開", key=f"rp_resume_{_rpi}"):
                    _rp_data[_rpi]['active'] = True
                    save_json(REPEAT_POSTS_FILE, _rp_data)
                    st.rerun()
            # 編集
            if _rp_bc2.button("✏️ 編集", key=f"rp_edit_{_rpi}"):
                _edit_data = dict(_rp_data[_rpi])
                _edit_data['entry_count'] = len(_edit_data.get('entries', []))
                st.session_state._rp_edit_pending = _edit_data
                st.rerun()
            # 削除
            if _rp_bc3.button("🗑️ 削除", key=f"rp_del_{_rpi}"):
                _rp_data.pop(_rpi)
                save_json(REPEAT_POSTS_FILE, _rp_data)
                st.rerun()
            st.markdown("---")

    # ==================== 過去の投稿からリピート作成 ====================
    st.markdown("---")
    st.subheader("📜 過去の投稿からリピート作成")
    st.caption(f"@{sel_username} の過去投稿を取得して、リピート投稿に追加できます")

    _rp_past_uname_ctx = sel_username
    _rp_past_acc_data = st.session_state.accounts[sel_idx] if st.session_state.accounts else {}

    _rp_past_col1, _rp_past_col2 = st.columns([1, 1])
    _rp_past_limit = _rp_past_col1.selectbox("取得件数", [10, 25, 50], index=1, key="rp_past_limit")
    if _rp_past_col2.button("📜 過去の投稿を取得", key="rp_fetch_past"):
        with st.spinner(f"@{sel_username} の投稿を取得中..."):
            ok, result = fetch_user_threads(_rp_past_acc_data, limit=_rp_past_limit)
            if ok:
                st.session_state._rp_past_posts = result
                st.session_state._rp_past_uname = sel_username
                st.success(f"{len(result)} 件の投稿を取得しました")
            else:
                st.error(f"取得失敗: {result}")
                st.session_state._rp_past_posts = []

    if st.session_state.get('_rp_past_posts') and st.session_state.get('_rp_past_uname') == sel_username:
        st.caption(f"@{sel_username} の投稿: {len(st.session_state._rp_past_posts)} 件")

        for _ppi, _pp in enumerate(st.session_state._rp_past_posts):
            _pp_text = (_pp.get('text') or '')
            _pp_date = (_pp.get('timestamp') or '')[:10]
            _pp_likes = _pp.get('like_count', 0)
            _pp_type = _pp.get('media_type', 'TEXT')
            _pp_link = _pp.get('permalink', '')
            _pp_media_url = _pp.get('media_url', '')
            _pp_child_urls = _pp.get('_child_urls', [])
            _pp_is_video = _pp_type == 'VIDEO'
            _pp_has_media = _pp_type in ('IMAGE', 'VIDEO', 'CAROUSEL_ALBUM') or _pp_media_url

            with st.container():
                # メディアラベル
                if _pp_type == 'VIDEO':
                    _pp_mlabel = "🎥 動画"
                elif _pp_type == 'CAROUSEL_ALBUM':
                    _pp_mlabel = f"📷 {len(_pp_child_urls) if _pp_child_urls else '複数'}枚"
                elif _pp_media_url:
                    _pp_mlabel = "📷 1枚"
                else:
                    _pp_mlabel = ""

                st.write(f"**#{_ppi+1}** {_pp_date} | ❤ {_pp_likes} | {_pp_mlabel}")
                st.caption(f"{_pp_text[:200]}{'...' if len(_pp_text)>200 else ''}")

                # 画像プレビュー
                if _pp_type == 'CAROUSEL_ALBUM' and _pp_child_urls:
                    _pp_icols = st.columns(min(len(_pp_child_urls), 4))
                    for _ci, _curl in enumerate(_pp_child_urls):
                        try:
                            _pp_icols[_ci % 4].image(_curl, width=150)
                        except:
                            pass
                elif _pp_is_video and _pp_media_url:
                    try:
                        st.video(_pp_media_url)
                    except:
                        pass
                elif _pp_media_url:
                    try:
                        st.image(_pp_media_url, width=180)
                    except:
                        pass

                _pp_btn_col1, _pp_btn_col2 = st.columns([1, 1])
                if _pp_btn_col1.button("🔁 リピート投稿に追加", key=f"rp_add_past_{_ppi}"):
                    # 画像ダウンロード
                    _pp_saved_paths = []
                    if _pp_has_media and not _pp_is_video and _rp_past_acc_data:
                        with st.spinner("画像をダウンロード中..."):
                            _pp_saved_paths = download_post_images(
                                _rp_past_acc_data, _pp,
                                cached_child_urls=_pp_child_urls if _pp_child_urls else None
                            )
                    # 編集画面にセット
                    st.session_state._rp_edit_pending = {
                        "id": str(__import__('uuid').uuid4())[:8],
                        "acc_username": _rp_past_uname_ctx,
                        "images": _pp_saved_paths,
                        "entries": [{"text": _pp_text, "days": 5}],
                        "current_entry_idx": 0,
                        "days_on_current": 0,
                        "last_posted_date": None,
                        "time_start": 0,
                        "time_end": 24,
                        "active": True
                    }
                    st.session_state._rp_entry_count = 1
                    if '_rp_edit_id' in st.session_state:
                        del st.session_state._rp_edit_id
                    st.success("✅ 編集画面にセットしました。上の「新規作成/編集」を確認してください")
                    st.rerun()
                if _pp_link:
                    _pp_btn_col2.markdown(f"[Threadsで見る]({_pp_link})")
                st.markdown("---")

# ==================== TAB 3: Post Monitor ====================
with tab3:
    st.subheader("投稿モニター")

    if st.button("🔄 更新", key="refresh_monitor"):
        st.session_state.accounts = load_json(ACCOUNTS_FILE)
        st.session_state.storage = load_json(STORAGE_FILE)
        st.rerun()

    # --- Freeze / Suspension Check ---
    if 'freeze_check' not in st.session_state:
        st.session_state.freeze_check = None
    if st.button("🧊 凍結確認", key="freeze_check_btn"):
        _frozen = []
        _check_bar = st.progress(0, text="チェック中...")
        _total_accs = max(len(st.session_state.accounts), 1)
        _completed = [0]
        _lock = __import__('threading').Lock()

        def _check_one_account(_fa):
            _name = _fa.get('name', '?')
            _uname = _fa.get('username', '')
            issues = []

            # 1) APIトークンチェック
            try:
                _fr = requests.get("https://graph.threads.net/v1.0/me",
                    params={'fields': 'id,username,name', 'access_token': _fa.get('token', '')},
                    timeout=8).json()
                if 'error' in _fr:
                    issues.append(f"API: {_fr['error'].get('message', 'トークン無効')}")
            except Exception as _fe:
                issues.append(f"API: {str(_fe)[:80]}")

            # 2) プロフィールページチェック（bot UAでメタタグを確認）
            # 凍結アカウント → al:android:url = "https://www.threads.com/login"
            # 正常アカウント → al:android:url = "https://www.threads.com/@username"
            if _uname:
                try:
                    import re as _re2
                    _pr = requests.get(f"https://www.threads.net/@{_uname}",
                        headers={"User-Agent": "facebookexternalhit/1.1", "Accept": "text/html"},
                        timeout=10, allow_redirects=True)
                    _head = _pr.text[:3000]
                    if _pr.status_code == 404:
                        issues.append("🔴 アカウントが存在しない (404)")
                    else:
                        # al:android:url でログインリダイレクトを検出
                        _android = _re2.findall(r'al:android:url.*?content="([^"]*)"', _head)
                        _android_url = _android[0] if _android else ""
                        if "/login" in _android_url:
                            issues.append("🔴 凍結（異議申し立て状態）")
                except Exception as _pe:
                    pass  # ページチェック失敗は無視（APIチェックで十分）

            if issues:
                return {'name': _name, 'username': _uname, 'error': ' / '.join(issues)}
            return None

        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=15) as _executor:
            _futures = {_executor.submit(_check_one_account, _fa): _fi for _fi, _fa in enumerate(st.session_state.accounts)}
            for _fut in as_completed(_futures):
                _completed[0] += 1
                _check_bar.progress(_completed[0] / _total_accs, text=f"チェック中... {_completed[0]}/{_total_accs}")
                _result = _fut.result()
                if _result:
                    _frozen.append(_result)
        _check_bar.empty()
        st.session_state.freeze_check = _frozen

    if st.session_state.freeze_check is not None:
        _frozen = st.session_state.freeze_check
        _fz_hdr1, _fz_hdr2 = st.columns([6, 1])
        if _fz_hdr2.button("✖ 閉じる", key="freeze_close"):
            st.session_state.freeze_check = None
            st.rerun()
        if _frozen:
            _fz_hdr1.error(f"🧊 {len(_frozen)}件のアカウントに問題あり")
            for _fi, _ff in enumerate(_frozen):
                _uname = _ff.get('username', '')
                _fc1, _fc2 = st.columns([4, 1])
                _link = f"https://www.threads.net/@{_uname}" if _uname else ""
                if _link:
                    _fc1.markdown(f"**{_ff['name']}** — [{_link}]({_link})")
                else:
                    _fc1.write(f"**{_ff['name']}**")
                _fc1.caption(f"⚠️ {_ff['error'][:150]}")
                if _fc2.button("🗑️ 削除", key=f"freeze_del_{_fi}"):
                    st.session_state.accounts = [a for a in st.session_state.accounts if a.get('username') != _uname]
                    save_json(ACCOUNTS_FILE, st.session_state.accounts)
                    st.session_state.freeze_check = [f for f in _frozen if f.get('username') != _uname]
                    st.success(f"✅ {_uname} を削除しました")
                    st.rerun()
        else:
            _fz_hdr1.success("✅ 全アカウント正常（凍結なし）")

    # --- 固定投稿チェッカー ---
    if 'pin_check' not in st.session_state:
        st.session_state.pin_check = None
    if st.button("📌 固定投稿チェック", key="pin_check_btn"):
        _pin_results = []
        _pin_bar = st.progress(0, text="固定投稿を確認中（Playwrightで各プロフィールをチェック）...")
        _pin_total = len(st.session_state.accounts)
        _pin_done = [0]
        _pin_lock = __import__('threading').Lock()

        def _check_pinned_batch(_accounts_batch):
            results = []
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as pw:
                    br = pw.chromium.launch(headless=True)
                    for _pa in _accounts_batch:
                        _pname = _pa.get('name', '?')
                        _puname = _pa.get('username', '')
                        if not _puname:
                            continue
                        try:
                            pg = br.new_page()
                            pg.goto(f"https://www.threads.net/@{_puname}", wait_until="domcontentloaded", timeout=25000)
                            # 投稿要素が読み込まれるまで待機（最大8秒）
                            try:
                                pg.wait_for_selector("div[data-pressable-container='true']", timeout=8000)
                            except:
                                pg.wait_for_timeout(4000)
                            _body = pg.inner_text("body")
                            has_pin = "ピン留め済み" in _body or "Pinned" in _body
                            _pin_broken = False
                            if has_pin:
                                _broken_words = ["この投稿は表示できません", "This post is unavailable", "Post not available", "Content not available", "Unavailable"]
                                _articles = pg.query_selector_all("div[data-pressable-container='true']")
                                if not _articles:
                                    _articles = pg.query_selector_all("article")
                                for _art in _articles[:5]:
                                    _art_text = _art.inner_text()
                                    if "ピン留め済み" in _art_text or "Pinned" in _art_text:
                                        if any(w in _art_text for w in _broken_words):
                                            _pin_broken = True
                                        break
                                if not _pin_broken and not _articles:
                                    _blines = _body.split('\n')
                                    for _li, _bline in enumerate(_blines):
                                        if "ピン留め済み" in _bline or "Pinned" in _bline:
                                            _nearby = '\n'.join(_blines[max(0,_li-2):_li+10])
                                            if any(w in _nearby for w in _broken_words):
                                                _pin_broken = True
                                            break
                            results.append({'name': _pname, 'username': _puname, 'has_pin': has_pin, 'pin_broken': _pin_broken})
                            pg.close()
                        except:
                            results.append({'name': _pname, 'username': _puname, 'has_pin': None, 'pin_broken': False})
                            try:
                                pg.close()
                            except:
                                pass
                        with _pin_lock:
                            _pin_done[0] += 1
                    br.close()
            except Exception:
                pass
            return results

        import math
        _batch_size = math.ceil(_pin_total / 5)
        _batches = [list(st.session_state.accounts)[i:i+_batch_size] for i in range(0, _pin_total, _batch_size)]

        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=5) as _pin_exec:
            _pin_futs = [_pin_exec.submit(_check_pinned_batch, b) for b in _batches]
            while any(not f.done() for f in _pin_futs):
                import time as _ptime
                _ptime.sleep(1)
                with _pin_lock:
                    _pin_bar.progress(min(_pin_done[0] / _pin_total, 1.0), text=f"確認中... {_pin_done[0]}/{_pin_total}")
            for f in _pin_futs:
                _pin_results.extend(f.result())
        _pin_bar.empty()
        st.session_state.pin_check = _pin_results

    if st.session_state.pin_check is not None:
        _pin_data = st.session_state.pin_check
        _no_pin = [p for p in _pin_data if p['has_pin'] is False]
        _broken_pin = [p for p in _pin_data if p.get('pin_broken')]
        _has_pin = [p for p in _pin_data if p['has_pin'] is True and not p.get('pin_broken')]
        _unknown = [p for p in _pin_data if p['has_pin'] is None]
        if _no_pin:
            st.warning(f"📌 固定投稿なし: {len(_no_pin)}件 / 固定あり: {len(_has_pin)}件")
            with st.expander(f"固定なしアカウント一覧（{len(_no_pin)}件）", expanded=True):
                for _np in _no_pin:
                    st.write(f"・{_np['name']} — [@{_np['username']}](https://www.threads.net/@{_np['username']})")
        else:
            st.success(f"✅ 全アカウントに固定投稿あり（{len(_has_pin)}件）")
        if _broken_pin:
            st.error(f"⚠️ 固定投稿が表示できない: {len(_broken_pin)}件")
            with st.expander(f"固定投稿が壊れているアカウント一覧（{len(_broken_pin)}件）", expanded=True):
                for _bp in _broken_pin:
                    st.write(f"・{_bp['name']} — [@{_bp['username']}](https://www.threads.net/@{_bp['username']})")
        if _unknown:
            st.caption(f"⚠️ {len(_unknown)}件は確認できませんでした")

    # --- 重要アカウント固定チェック ---
    st.divider()
    _vip_accounts = []  # オーナーアカウントのユーザー名を設定
    if 'vip_pin_check' not in st.session_state:
        st.session_state.vip_pin_check = None
    if st.button("🔒 重要アカウント固定チェック", key="vip_pin_btn"):
        _vip_results = []
        _vip_bar = st.progress(0, text="重要アカウントの固定投稿を確認中...")
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                br = pw.chromium.launch(headless=True)
                for _vi, _vuname in enumerate(_vip_accounts):
                    try:
                        pg = br.new_page()
                        pg.goto(f"https://www.threads.net/@{_vuname}", wait_until="domcontentloaded", timeout=25000)
                        try:
                            pg.wait_for_selector("div[data-pressable-container='true']", timeout=10000)
                        except:
                            pg.wait_for_timeout(5000)
                        _body = pg.inner_text("body")
                        _has_pin = "ピン留め済み" in _body or "Pinned" in _body
                        _pin_broken = False
                        _pin_text = ""
                        if _has_pin:
                            _articles = pg.query_selector_all("div[data-pressable-container='true']")
                            if not _articles:
                                _articles = pg.query_selector_all("article")
                            for _art in _articles[:5]:
                                _art_text = _art.inner_text()
                                if "ピン留め済み" in _art_text or "Pinned" in _art_text:
                                    _pin_text = _art_text[:200]
                                    _broken_words = ["この投稿は表示できません", "This post is unavailable", "Post not available", "Content not available", "Unavailable"]
                                    if any(w in _art_text for w in _broken_words):
                                        _pin_broken = True
                                    break
                        _vip_results.append({'username': _vuname, 'has_pin': _has_pin, 'pin_broken': _pin_broken, 'pin_text': _pin_text})
                        pg.close()
                    except Exception as _ve:
                        _vip_results.append({'username': _vuname, 'has_pin': None, 'pin_broken': False, 'pin_text': '', 'error': str(_ve)})
                        try:
                            pg.close()
                        except:
                            pass
                    _vip_bar.progress((_vi + 1) / len(_vip_accounts), text=f"確認中... {_vi + 1}/{len(_vip_accounts)}")
                br.close()
        except Exception as _ve2:
            st.error(f"エラー: {_ve2}")
        _vip_bar.empty()
        st.session_state.vip_pin_check = _vip_results

    if st.session_state.vip_pin_check is not None:
        _vip_hdr1, _vip_hdr2 = st.columns([6, 1])
        if _vip_hdr2.button("✖ 閉じる", key="vip_close"):
            st.session_state.vip_pin_check = None
            st.rerun()
        _all_ok = True
        for _vr in st.session_state.vip_pin_check:
            _vu = _vr['username']
            _link = f"https://www.threads.net/@{_vu}"
            if _vr.get('error'):
                st.warning(f"⚠️ **@{_vu}** — 確認失敗: {_vr['error']}")
                _all_ok = False
            elif _vr['has_pin'] is False:
                st.error(f"🚨 **@{_vu}** — 固定投稿がありません！ [プロフィール]({_link})")
                _all_ok = False
            elif _vr.get('pin_broken'):
                st.error(f"🚨 **@{_vu}** — 固定投稿が壊れています！ [プロフィール]({_link})")
                _all_ok = False
            else:
                _pt = _vr.get('pin_text', '')
                _preview = _pt.replace('\n', ' ')[:80] if _pt else ''
                st.success(f"✅ **@{_vu}** — 固定投稿あり  `{_preview}`")
        if _all_ok:
            st.balloons()

    # --- 固定URL一致チェック ---
    st.divider()
    st.subheader("🔍 固定投稿URL一致チェック")

    _pin_url_boxes = []
    try:
        _pin_url_boxes = json.load(open(QUOTE_BOXES_FILE, "r"))
    except:
        pass

    if _pin_url_boxes:
        # 各ボックスのオーナー・固定URL設定
        with st.expander("⚙️ ボックス設定（オーナー・固定URL）"):
            _vip_list = []  # オーナーアカウントのユーザー名を設定
            _pin_settings_changed = False
            for _pbi, _pb in enumerate(_pin_url_boxes):
                st.markdown(f"**📦 {_pb.get('name', '?')}**（{len(_pb.get('acc_usernames', []))}人）")
                _pb_c1, _pb_c2 = st.columns([1, 3])
                _cur_owner = _pb.get('owner_username', '')
                _owner_idx = _vip_list.index(_cur_owner) if _cur_owner in _vip_list else 0
                _new_owner = _pb_c1.selectbox("オーナー", _vip_list, index=_owner_idx, key=f"pin_owner_{_pbi}")
                _cur_pin_url = _pb.get('pin_url', '')
                _new_pin_url = _pb_c2.text_input("固定投稿URL", value=_cur_pin_url, key=f"pin_url_{_pbi}", placeholder="https://www.threads.net/@.../post/...")
            if st.button("💾 設定保存", key="pin_settings_save"):
                for _pbi, _pb in enumerate(_pin_url_boxes):
                    _pb['owner_username'] = st.session_state.get(f"pin_owner_{_pbi}", _pb.get('owner_username', ''))
                    _pb['pin_url'] = st.session_state.get(f"pin_url_{_pbi}", _pb.get('pin_url', ''))
                save_json(QUOTE_BOXES_FILE, _pin_url_boxes)
                st.success("✅ 設定を保存しました")
                st.rerun()

        # 全ボックスの固定URL情報を表示（ファイルから最新データを読み込み）
        _fresh_boxes = load_json(QUOTE_BOXES_FILE) if os.path.exists(QUOTE_BOXES_FILE) else []
        _boxes_with_url = [b for b in _fresh_boxes if b.get('pin_url', '').strip()]
        if _boxes_with_url:
            for _bwu in _boxes_with_url:
                import re as _pin_re
                _bwu_sc = _pin_re.search(r'/post/([^/?]+)', _bwu.get('pin_url', ''))
                _bwu_sc_str = _bwu_sc.group(1) if _bwu_sc else '?'
                st.caption(f"📦 {_bwu.get('name')} → @{_bwu.get('owner_username', '?')} → `{_bwu_sc_str}`")

        if 'pin_url_check' not in st.session_state:
            st.session_state.pin_url_check = None

        if st.button("🔎 全ボックス一括チェック", key="pin_url_check_btn", type="primary"):
            # 固定URLが設定されているボックスのみチェック
            _check_boxes = [b for b in _pin_url_boxes if b.get('pin_url', '').strip()]
            if not _check_boxes:
                st.warning("先に各ボックスの固定投稿URLを設定してください")
            else:
                import re as _pin_re2
                # ボックスごとのshortcodeマップ: shortcode -> box_name
                _sc_to_box = {}
                for _cb in _check_boxes:
                    _cb_match = _pin_re2.search(r'/post/([^/?]+)', _cb.get('pin_url', ''))
                    if _cb_match:
                        _sc_to_box[_cb_match.group(1)] = _cb.get('name', '')

                # 全ボックスの全アカウントをチェック
                _all_check_usernames = []
                _uname_to_box = {}
                for _cb in _check_boxes:
                    for _cu in _cb.get('acc_usernames', []):
                        _all_check_usernames.append(_cu)
                        _uname_to_box[_cu] = _cb.get('name', '')

                _pub_total = len(_all_check_usernames)
                _pub_bar = st.progress(0, text=f"固定投稿を確認中... 0/{_pub_total}")
                _pub_done = [0]
                _pub_lock = __import__('threading').Lock()
                _pub_results = []

                def _check_pin_all_batch(_unames_batch, _sc_map):
                    import re as _re_local
                    results = []
                    try:
                        from playwright.sync_api import sync_playwright
                        with sync_playwright() as pw:
                            br = pw.chromium.launch(headless=True)
                            for _uname in _unames_batch:
                                status = "unknown"
                                found_sc = ""
                                found_url = ""
                                try:
                                    pg = br.new_page()
                                    pg.goto(f"https://www.threads.net/@{_uname}", wait_until="domcontentloaded", timeout=25000)
                                    try:
                                        pg.wait_for_selector("div[data-pressable-container='true']", timeout=8000)
                                    except:
                                        pg.wait_for_timeout(4000)

                                    _body = pg.inner_text("body")
                                    _has_pin = "ピン留め済み" in _body or "Pinned" in _body

                                    if not _has_pin:
                                        status = "no_pin"
                                    else:
                                        _articles = pg.query_selector_all("div[data-pressable-container='true']")
                                        if not _articles:
                                            _articles = pg.query_selector_all("article")

                                        for _art in _articles[:5]:
                                            _art_text = _art.inner_text()
                                            if "ピン留め済み" not in _art_text and "Pinned" not in _art_text:
                                                continue
                                            # 固定投稿内の全リンクから引用元を探す
                                            _links = _art.query_selector_all("a")
                                            for _lnk in _links:
                                                _href = _lnk.get_attribute("href") or ""
                                                if "/post/" not in _href:
                                                    continue
                                                # 自分の投稿はスキップ、引用元の投稿を見つける
                                                if f"/@{_uname}/" in _href:
                                                    continue
                                                _sc_m = _re_local.search(r'/post/([^/?]+)', _href)
                                                if _sc_m:
                                                    found_sc = _sc_m.group(1)
                                                    found_url = _href
                                                    break
                                            break

                                        if found_sc:
                                            # どのボックスのURLと一致するか判定
                                            if found_sc in _sc_map:
                                                status = "match"
                                            else:
                                                status = "mismatch"
                                        else:
                                            status = "no_quote_link"

                                    pg.close()
                                except Exception:
                                    status = "error"
                                    try:
                                        pg.close()
                                    except:
                                        pass

                                # found_scがどのボックスに属するか
                                matched_box = _sc_map.get(found_sc, "")

                                results.append({
                                    'username': _uname,
                                    'status': status,
                                    'found_sc': found_sc,
                                    'found_url': found_url,
                                    'should_be_in': matched_box
                                })

                                with _pub_lock:
                                    _pub_done[0] += 1
                            br.close()
                    except Exception:
                        pass
                    return results

                import math
                _pub_batch_size = math.ceil(_pub_total / 5)
                _pub_batches = [_all_check_usernames[i:i+_pub_batch_size] for i in range(0, _pub_total, _pub_batch_size)]

                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=5) as _pub_exec:
                    _pub_futs = [_pub_exec.submit(_check_pin_all_batch, batch, _sc_to_box) for batch in _pub_batches]
                    while any(not f.done() for f in _pub_futs):
                        import time as _pub_time
                        _pub_time.sleep(1)
                        with _pub_lock:
                            _pub_bar.progress(min(_pub_done[0] / _pub_total, 1.0), text=f"確認中... {_pub_done[0]}/{_pub_total}")
                    for f in _pub_futs:
                        _pub_results.extend(f.result())
                _pub_bar.empty()

                st.session_state.pin_url_check = {
                    'results': _pub_results,
                    'uname_to_box': _uname_to_box,
                    'sc_to_box': _sc_to_box
                }

        if st.session_state.pin_url_check is not None:
            _puc = st.session_state.pin_url_check
            _puc_hdr1, _puc_hdr2 = st.columns([6, 1])
            if _puc_hdr2.button("✖ 閉じる", key="pin_url_close"):
                st.session_state.pin_url_check = None
                st.rerun()

            _puc_results = _puc['results']
            _puc_uname_to_box = _puc.get('uname_to_box', {})
            _puc_match = [r for r in _puc_results if r['status'] == 'match']
            _puc_mismatch = [r for r in _puc_results if r['status'] == 'mismatch']
            _puc_no_pin = [r for r in _puc_results if r['status'] == 'no_pin']
            _puc_no_quote = [r for r in _puc_results if r['status'] == 'no_quote_link']
            _puc_error = [r for r in _puc_results if r['status'] == 'error']

            # 移動が必要なアカウント（違うボックスの投稿を固定している）
            _puc_wrong_box = [r for r in _puc_mismatch if r.get('should_be_in')]
            # どこにも属さない不一致
            _puc_unknown = [r for r in _puc_mismatch if not r.get('should_be_in')]

            _puc_hdr1.markdown(f"**全ボックス** チェック結果（{len(_puc_results)}アカウント）")

            if _puc_wrong_box:
                st.error(f"🔀 違うボックスの投稿が固定されている: {len(_puc_wrong_box)}件")
                with st.expander(f"移動が必要なアカウント（{len(_puc_wrong_box)}件）", expanded=True):
                    for _pw in _puc_wrong_box:
                        _pw_cur = _puc_uname_to_box.get(_pw['username'], '?')
                        _pw_should = _pw.get('should_be_in', '?')
                        st.write(f"・@{_pw['username']}：**{_pw_cur}** → **{_pw_should}** に移動すべき")

                if st.button("🔄 自動移動する", key="pin_auto_move", type="primary"):
                    _move_boxes = json.load(open(QUOTE_BOXES_FILE, "r"))
                    _move_count = 0
                    for _mw in _puc_wrong_box:
                        _mu = _mw['username']
                        _m_from = _puc_uname_to_box.get(_mu, '')
                        _m_to = _mw.get('should_be_in', '')
                        if not _m_from or not _m_to or _m_from == _m_to:
                            continue
                        # 元のボックスから削除
                        for _mb in _move_boxes:
                            if _mb.get('name') == _m_from:
                                if _mu in _mb.get('acc_usernames', []):
                                    _mb['acc_usernames'].remove(_mu)
                                break
                        # 移動先ボックスに追加
                        for _mb in _move_boxes:
                            if _mb.get('name') == _m_to:
                                if _mu not in _mb.get('acc_usernames', []):
                                    _mb['acc_usernames'].append(_mu)
                                break
                        _move_count += 1

                    save_json(QUOTE_BOXES_FILE, _move_boxes)
                    st.success(f"✅ {_move_count}アカウントを移動しました")
                    st.session_state.pin_url_check = None
                    st.rerun()

            if _puc_unknown:
                st.warning(f"❓ 不明な投稿が固定されている: {len(_puc_unknown)}件")
                with st.expander(f"不明な固定投稿（{len(_puc_unknown)}件）"):
                    for _pu in _puc_unknown:
                        st.write(f"・@{_pu['username']} → `{_pu.get('found_url', '?')}`")

            if _puc_no_pin:
                st.warning(f"📌 固定投稿なし: {len(_puc_no_pin)}件")
                with st.expander(f"固定なしアカウント（{len(_puc_no_pin)}件）"):
                    for _pn in _puc_no_pin:
                        _pn_box = _puc_uname_to_box.get(_pn['username'], '?')
                        st.write(f"・@{_pn['username']}（{_pn_box}）")

            if _puc_no_quote:
                st.warning(f"🔗 引用元リンク取得不可: {len(_puc_no_quote)}件")

            if _puc_match:
                st.success(f"✅ 正しいボックスに所属: {len(_puc_match)}件")

            if _puc_error:
                st.caption(f"⚠️ 確認失敗: {len(_puc_error)}件")

    
        # --- バズチェック ---
    if 'buzz_check' not in st.session_state:
        st.session_state.buzz_check = None
    _bz_c1, _bz_c2 = st.columns([1, 2])
    _bz_limit = _bz_c2.selectbox("直近N件の投稿で判定", [5, 10, 15, 20], index=1, key="bz_limit")
    if _bz_c1.button("📊 バズチェック", key="buzz_check_btn"):
        _bz_results = []
        _bz_bar = st.progress(0, text="いいね数を取得中...")
        _bz_total = max(len(st.session_state.accounts), 1)

        def _check_buzz(_ba, _limit):
            _bn = _ba.get('name', '?')
            _bu = _ba.get('username', '')
            _bt = _ba.get('token', '')
            if not _bt:
                return {'name': _bn, 'username': _bu, 'avg_likes': 0, 'total_posts': 0, 'top_post': '', 'error': 'トークンなし'}
            try:
                _br = requests.get(f"https://graph.threads.net/v1.0/{_ba['id']}/threads",
                    params={'access_token': _bt, 'fields': 'id,text,like_count,timestamp', 'limit': _limit},
                    timeout=10).json()
                if 'data' not in _br:
                    return {'name': _bn, 'username': _bu, 'avg_likes': 0, 'total_posts': 0, 'top_post': '', 'error': _br.get('error', {}).get('message', 'API Error')}
                _posts = _br['data']
                if not _posts:
                    return {'name': _bn, 'username': _bu, 'avg_likes': 0, 'total_posts': 0, 'top_post': '', 'error': None}
                _likes = [p.get('like_count', 0) for p in _posts]
                _avg = sum(_likes) / len(_likes) if _likes else 0
                _max_idx = _likes.index(max(_likes))
                _top = _posts[_max_idx].get('text', '')[:60]
                return {'name': _bn, 'username': _bu, 'avg_likes': round(_avg, 1), 'max_likes': max(_likes), 'total_posts': len(_posts), 'top_post': _top, 'error': None}
            except Exception as _e:
                return {'name': _bn, 'username': _bu, 'avg_likes': 0, 'total_posts': 0, 'top_post': '', 'error': str(_e)[:80]}

        from concurrent.futures import ThreadPoolExecutor, as_completed
        _bz_done = [0]
        with ThreadPoolExecutor(max_workers=15) as _bz_exec:
            _bz_futs = {_bz_exec.submit(_check_buzz, _ba, _bz_limit): _bi for _bi, _ba in enumerate(st.session_state.accounts)}
            for _bfut in as_completed(_bz_futs):
                _bz_done[0] += 1
                _bz_bar.progress(_bz_done[0] / _bz_total, text=f"取得中... {_bz_done[0]}/{_bz_total}")
                _bz_results.append(_bfut.result())
        _bz_bar.empty()
        # いいね平均でソート（低い順）
        _bz_results.sort(key=lambda x: x['avg_likes'])
        st.session_state.buzz_check = _bz_results

    if st.session_state.buzz_check is not None:
        _bz_data = st.session_state.buzz_check
        _low_buzz = [b for b in _bz_data if b['avg_likes'] < 5 and not b.get('error')]
        _err_buzz = [b for b in _bz_data if b.get('error')]
        _ok_buzz = [b for b in _bz_data if b['avg_likes'] >= 5 and not b.get('error')]

        if _low_buzz:
            st.warning(f"📉 バズってないアカウント: {len(_low_buzz)}件（平均いいね5未満）")
            for _bi, _bz in enumerate(_low_buzz):
                _bz_exp = st.expander(f"❌ {_bz['name']} (@{_bz['username']}) — 平均 {_bz['avg_likes']}❤ / 最大 {_bz.get('max_likes', 0)}❤")
                with _bz_exp:
                    st.caption(f"投稿数: {_bz['total_posts']}件 | トップ投稿: {_bz['top_post']}")
                    components.html(f"""<button onclick="window.open('https://www.threads.net/@{_bz['username']}', '_blank', 'width=420,height=750,scrollbars=yes,resizable=yes,noopener').focus();"
                        style="background:#333;color:white;border:none;border-radius:6px;padding:6px 12px;cursor:pointer;font-size:12px;">
                        🔍 プロフィールを見る</button>""", height=40)

        if _ok_buzz:
            with st.expander(f"✅ バズってるアカウント: {len(_ok_buzz)}件", expanded=False):
                for _bz in sorted(_ok_buzz, key=lambda x: x['avg_likes'], reverse=True):
                    st.caption(f"✅ {_bz['name']} (@{_bz['username']}) — 平均 {_bz['avg_likes']}❤ / 最大 {_bz.get('max_likes', 0)}❤")

        if _err_buzz:
            with st.expander(f"⚠️ エラー: {len(_err_buzz)}件", expanded=False):
                for _bz in _err_buzz:
                    st.caption(f"⚠️ {_bz['name']} (@{_bz['username']}) — {_bz['error']}")

    st.markdown("---")

    _now = get_jst_time()
    _today_str = _now.strftime('%Y-%m-%d')
    _accounts = st.session_state.accounts
    _storage = st.session_state.storage

    # Auto-reset: reschedule entries with next_run from previous days (midnight reset)
    _stale_fixed = False
    for _sp in _storage:
        try:
            _nr = datetime.fromisoformat(_sp.get('next_run', ''))
            if _nr.strftime('%Y-%m-%d') < _today_str:
                _sp['next_run'] = calculate_next_run(tuple(_sp.get('time_range', [12, 15])))
                if _sp.get('today_date', '') != _today_str:
                    _sp['today_count'] = 0
                    _sp['today_date'] = _today_str
                _stale_fixed = True
        except:
            pass
    if _stale_fixed:
        save_json(STORAGE_FILE, _storage)

    # --- Today's Stats Dashboard ---
    _today_success = 0
    _today_errors = 0
    _today_accounts_posted = set()

    # Count today's successful posts from storage
    for _si, _sp in enumerate(_storage):
        if _sp.get('today_date', '') == _today_str:
            _tc = _sp.get('today_count', 0)
            if _tc > 0:
                _today_success += _tc
                _today_accounts_posted.add(_sp.get('acc_username', _sp.get('acc_idx', -1)))

    # Count today's errors from error_log
    _error_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "error_log.json")
    if os.path.exists(_error_log_path):
        try:
            with open(_error_log_path, 'r', encoding='utf-8') as _elf:
                _elog = json.load(_elf)
            _today_errors = len([e for e in _elog if e.get('time', '').startswith(_today_str)])
        except:
            pass

    _today_total = _today_success + _today_errors
    _today_rate = (_today_success / _today_total * 100) if _today_total > 0 else 0

    _dc1, _dc2, _dc3, _dc4 = st.columns(4)
    _dc1.metric("今日の成功", f"{_today_success}件")
    _dc2.metric("エラー", f"{_today_errors}件")
    _dc3.metric("成功率", f"{_today_rate:.0f}%")
    _dc4.metric("稼働アカウント", f"{len(_today_accounts_posted)}件")

    if _today_errors > 0:
        _today_error_list = [e for e in _elog if e.get('time', '').startswith(_today_str)] if '_elog' in dir() else []
        if _today_error_list:
            with st.expander(f"❌ 今日のエラー詳細（{len(_today_error_list)}件）"):
                _err_by_acc = {}
                for _te in _today_error_list:
                    _acc_name = _te.get('account', '?')
                    if _acc_name not in _err_by_acc:
                        _err_by_acc[_acc_name] = []
                    _err_by_acc[_acc_name].append(_te)
                for _acc_name, _errs in _err_by_acc.items():
                    st.write(f"**{_acc_name}** — {len(_errs)}回エラー")
                    for _e in _errs[-3:]:
                        _emoji = {'RATE_LIMIT': '⏳', 'TOKEN_ERROR': '🔑', 'IMAGE_ERROR': '🖼️', 'NETWORK_ERROR': '🌐', 'PUBLISH_ERROR': '📤'}.get(_e.get('type', ''), '❓')
                        st.caption(f"  {_emoji} {_e.get('time', '')[11:16]} | {_e.get('error', '')[:60]}")
                    st.markdown("---")

    st.markdown("---")

    _total_ok = 0
    _issues = []

    for ai, acc in enumerate(_accounts):
        acc_name = acc.get('name', f'acc_{ai}')
        is_active = acc.get('active', True)
        if not is_active:
            continue
        metrics = acc.get('metrics', {'attempts': 0, 'successes': 0, 'failures': 0, 'last_error': 'None'})
        attempts = metrics.get('attempts', 0)
        successes = metrics.get('successes', 0)
        failures = metrics.get('failures', 0)
        last_error = metrics.get('last_error', 'None')
        success_rate = (successes / attempts * 100) if attempts > 0 else 0
        has_error = last_error and last_error != 'None'

        _acc_uname = acc.get('username', '')
        acc_posts = [s for s in _storage if s.get('acc_username') == _acc_uname or (not s.get('acc_username') and s.get('acc_idx') == ai)]
        if not acc_posts:
            continue

        for sp in acc_posts:
            next_run_str = sp.get('next_run', '')
            last_posted = sp.get('last_posted_at', '')
            today_count = sp.get('today_count', 0)
            today_date = sp.get('today_date', '')

            try:
                nr_dt = datetime.fromisoformat(next_run_str) if next_run_str else None
                if nr_dt and nr_dt.tzinfo is None:
                    nr_dt = nr_dt.replace(tzinfo=timezone(timedelta(hours=9)))
            except:
                nr_dt = None

            try:
                is_past = nr_dt and _now > nr_dt
            except TypeError:
                # offset-naive vs offset-aware fallback
                if nr_dt:
                    nr_dt = nr_dt.replace(tzinfo=timezone(timedelta(hours=9)))
                    is_past = _now > nr_dt
                else:
                    is_past = False
            is_today_done = (today_date == _today_str and today_count >= 1)

            # Skip issue detection if paused
            if sp.get('paused', False):
                _total_ok += 1
                continue

            # Skip issue detection if account has never posted (just activated or new)
            if not last_posted and attempts == 0:
                _total_ok += 1
                continue

            if is_today_done:
                _total_ok += 1
            elif is_past and not is_today_done:
                hours_late = (_now - nr_dt).total_seconds() / 3600 if nr_dt else 0
                if hours_late > 2:
                    reason = f'予定時刻を{int(hours_late)}時間経過'
                    if has_error:
                        reason += f'\nエラー内容: {last_error}'
                    else:
                        reason += '\nworkerが停止している可能性があります'
                    _issues.append({
                        'name': acc_name, 'type': '⚠️ 取りこぼし',
                        'reason': reason,
                        'next_run': next_run_str.replace('T', ' ')[:16],
                        'last_posted': last_posted.replace('T', ' ')[:16] if last_posted else '未投稿',
                        'success_rate': success_rate
                    })
                else:
                    _total_ok += 1  # Within 2 hours, worker will handle
            else:
                _total_ok += 1  # Future scheduled or no issues

    # Summary
    if not _issues:
        st.success(f"✅ 全アカウント正常（{_total_ok}件の自動投稿が稼働中）")
    else:
        st.error(f"🚨 {len(_issues)}件の問題が検出されました（正常: {_total_ok}件）")
        for iss in _issues:
            st.markdown("---")
            st.write(f"**{iss['type']}** — {iss['name']}")
            st.write(f"予定: {iss['next_run']} | 最終投稿: {iss['last_posted']}")
            st.warning(iss['reason'])

    # Error log (auto-fix history)
    st.markdown("---")
    _error_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "error_log.json")
    if os.path.exists(_error_log_path):
        try:
            with open(_error_log_path, 'r', encoding='utf-8') as _elf:
                _error_log = json.load(_elf)
            if _error_log:
                with st.expander(f"🔧 自動修復ログ（直近{len(_error_log)}件）"):
                    for _el in reversed(_error_log[-20:]):
                        _emoji = {'RATE_LIMIT': '⏳', 'TOKEN_ERROR': '🔑', 'IMAGE_ERROR': '🖼️', 'NETWORK_ERROR': '🌐', 'PUBLISH_ERROR': '📤'}.get(_el.get('type', ''), '❓')
                        st.caption(f"{_emoji} {_el.get('time', '')} | {_el.get('account', '')} | {_el.get('action', '')}")
        except:
            pass

# ==================== TAB 4: リポスト ====================
with tab4:
    st.header("リポスト")
    st.caption("複数アカウントでThreads投稿にリポストを実行")

    # ボックスデータ読み込み
    _rp_boxes = load_json(REPOST_BOXES_FILE) if os.path.exists(REPOST_BOXES_FILE) else []

    # ---------- ボックス作成・編集 ----------
    if '_rpbox_edit_pending' not in st.session_state:
        st.session_state._rpbox_edit_pending = None
    # 保存後のクリア処理
    if st.session_state.get('_rp_clear_after_save'):
        st.session_state['rp_box_name'] = ""
        st.session_state['rp_acc_select'] = []
        st.session_state._rp_clear_after_save = False
    # 編集ボタンから来た場合、widget keyに直接値をセット
    if st.session_state.get('_rpbox_edit_pending') is not None:
        _pending = st.session_state._rpbox_edit_pending
        st.session_state.rp_box_name = _pending['name']
        st.session_state.rp_acc_select = _pending['accs']
        st.session_state._rpbox_edit_pending = None
    _rp_is_editing = 'rp_box_name' in st.session_state and bool(st.session_state.get('rp_box_name', ''))
    with st.expander("📦 ボックス作成 / 編集", expanded=len(_rp_boxes) == 0 or _rp_is_editing):
        _rp_name = st.text_input("ボックス名", key="rp_box_name")

        # アカウント選択（既存ボックスに入っているアカウントは除外。編集中のボックスは除外しない）
        _rp_used_unames = set()
        for _rb in _rp_boxes:
            if _rb.get('name') != _rp_name:
                _rp_used_unames.update(_rb.get('acc_usernames', []))
        _vip_usernames = set()  # オーナーアカウントのユーザー名を設定
        _acc_options = []
        for _rp_num, _ac in enumerate(st.session_state.accounts, 1):
            _uname = _ac.get('username', '')
            if _uname and _uname not in _rp_used_unames:
                _aname = _ac.get('name', _ac.get('username', ''))
                _star = "⭐ " if _uname in _vip_usernames else ""
                _display_name = _aname.split(" (@")[0]
                _acc_options.append(f"{_uname}: {_rp_num}. {_star}{_display_name}")
        _rp_selected_accs = st.multiselect("アカウント選択", _acc_options, key="rp_acc_select")

        _rp_c1, _rp_c2 = st.columns(2)
        if _rp_c1.button("💾 ボックス保存", key="rp_save_box"):
            if _rp_name.strip() and _rp_selected_accs:
                _sel_unames = [s.split(":")[0].strip() for s in _rp_selected_accs]
                _new_box = {
                    "name": _rp_name.strip(),
                    "acc_usernames": _sel_unames
                }
                _found_rp = False
                for _ri, _rb in enumerate(_rp_boxes):
                    if _rb.get('name') == _rp_name.strip():
                        _rp_boxes[_ri] = _new_box
                        _found_rp = True
                        break
                if not _found_rp:
                    _rp_boxes.append(_new_box)
                save_json(REPOST_BOXES_FILE, _rp_boxes)
                st.session_state._rp_clear_after_save = True
                st.rerun()
            else:
                st.warning("ボックス名とアカウントを入力してください")

    # ---------- リポスト実行エリア ----------
    if not _rp_boxes:
        st.info("ボックスを作成してください")
    else:
        st.markdown("---")

        # ボックス一覧表示（削除ボタン付き）
        for _bi, _box in enumerate(_rp_boxes):
            _box_name = _box.get('name', f'Box{_bi}')
            _box_unames = _box.get('acc_usernames', [])
            _acc_names_list = []
            _uname_to_acc = {a.get('username',''): a for a in st.session_state.accounts}
            for _bu in _box_unames:
                _a = _uname_to_acc.get(_bu)
                if _a:
                    _dname = _a.get('name', _bu)
                    if _bu in set():  # オーナーアカウントのユーザー名を設定
                        _dname = f"⭐{_dname}"
                    _acc_names_list.append(_dname)
                else:
                    _acc_names_list.append(f'@{_bu}(不明)')
            _del_c1, _del_c2, _del_c3 = st.columns([5, 1, 1])
            _del_c1.markdown(f"**📦 {_box_name}** — 👥 {len(_box_unames)}人: {', '.join(_acc_names_list)}")
            if _del_c2.button("✏️", key=f"rpbox_edit_{_bi}"):
                _uname_to_num = {}
                for _eni, _ena in enumerate(st.session_state.accounts, 1):
                    _enu = _ena.get('username', '')
                    if _enu:
                        _uname_to_num[_enu] = _eni
                _edit_opts = [f"{u}: {_uname_to_num.get(u, '?')}. {_uname_to_acc[u].get('name', u).split(' (@')[0]}" for u in _box_unames if u in _uname_to_acc and u not in {}]
                st.session_state._rpbox_edit_pending = {'name': _box_name, 'accs': _edit_opts}
                st.rerun()
            if _del_c3.button("🗑️", key=f"rpbox_del_{_bi}"):
                _rp_boxes.pop(_bi)
                save_json(REPOST_BOXES_FILE, _rp_boxes)
                st.rerun()

        st.markdown("---")

        # ボックス選択 + URL入力 + 実行
        _box_names = [b.get('name', f'Box{i}') for i, b in enumerate(_rp_boxes)]
        _sel_box_name = st.selectbox("ボックス選択", _box_names, key="rp_sel_box")
        _sel_box = next((b for b in _rp_boxes if b.get('name') == _sel_box_name), None)

        _rp_url = st.text_input("Threads投稿URL", placeholder="https://www.threads.net/@user/post/xxxxx", key="rp_url")

        if st.button("🔄 リポスト実行", key="rp_exec", type="primary"):
            if not _sel_box:
                st.error("ボックスを選択してください")
            elif not _rp_url.strip():
                st.warning("Threads投稿URLを入力してください")
            else:
                _rp_username, _rp_shortcode = extract_threads_username_and_shortcode(_rp_url.strip())
                if not _rp_username or not _rp_shortcode:
                    st.error("❌ URLの形式が正しくありません")
                else:
                    # URLのユーザー名からアカウントを探してpost IDを取得
                    _status = st.empty()
                    _status.info(f"⏳ @{_rp_username} の投稿IDを検索中...")
                    _owner_acc = None
                    for _a in st.session_state.accounts:
                        if _a.get('username', '') == _rp_username:
                            _owner_acc = _a
                            break
                    if not _owner_acc:
                        st.error(f"❌ @{_rp_username} はアカウント管理に登録されていません。対象の投稿者アカウントを追加してください。")
                    else:
                        _threads_post_id = find_threads_post_id(_owner_acc, _rp_shortcode)
                        if not _threads_post_id:
                            st.error(f"❌ @{_rp_username} の投稿一覧からこの投稿が見つかりませんでした")
                        else:
                            _status.info(f"✅ 投稿ID取得成功: {_threads_post_id}")
                            _box_unames_exec = _sel_box.get('acc_usernames', [])
                            _uname_to_acc_exec = {a.get('username',''): a for a in st.session_state.accounts}
                            _progress = st.progress(0)
                            _results = []
                            _total = len(_box_unames_exec)

                            for _idx, _acc_uname in enumerate(_box_unames_exec):
                                _acc = _uname_to_acc_exec.get(_acc_uname)
                                if _acc:
                                    _aname = _acc.get('name', _acc.get('username', ''))
                                    _status.info(f"⏳ {_aname} をリポスト中... ({_idx+1}/{_total})")

                                    _ok, _res = repost_thread(_acc, _threads_post_id)
                                    if _ok:
                                        _results.append(f"✅ {_aname}")
                                    else:
                                        _results.append(f"❌ {_aname}: {str(_res)[:80]}")

                                    _progress.progress((_idx + 1) / _total)

                                    if _idx < _total - 1:
                                        time.sleep(1)
                                else:
                                    _results.append(f"⚠️ #{_acc_i} アカウント見つからず")

                    _status.empty()
                    _progress.empty()

                    _ok_count = sum(1 for r in _results if r.startswith("✅"))
                    st.success(f"🎉 リポスト完了！ 成功: {_ok_count}/{_total}")
                    for _r in _results:
                        st.write(_r)


    # ==================== 予約リポスト ====================
    st.markdown("---")
    st.subheader("⏰ 予約リポスト")
    st.caption("指定した時間後に自動でリポストを実行")

    _sr_boxes = load_json(REPOST_BOXES_FILE) if os.path.exists(REPOST_BOXES_FILE) else []
    if _sr_boxes:
        _sr_col1, _sr_col2 = st.columns([1, 1])
        _sr_box_names = [b["name"] for b in _sr_boxes]
        _sr_sel_box = _sr_col1.selectbox("リポストボックス", _sr_box_names, key="sr_box_sel")
        _sr_url = _sr_col2.text_input("投稿URL", key="sr_url", placeholder="https://www.threads.net/@user/post/xxxxx")

        _sr_tcol1, _sr_tcol2, _sr_tcol3 = st.columns([1, 1, 2])
        _sr_hours = _sr_tcol1.number_input("時間", min_value=0, max_value=72, value=1, step=1, key="sr_hours")
        _sr_mins = _sr_tcol2.number_input("分", min_value=0, max_value=59, value=0, step=5, key="sr_mins")
        _sr_tcol3.write("")
        _sr_tcol3.write("")

        if _sr_tcol3.button("⏰ 予約する", key="sr_schedule_btn", type="primary"):
            if not _sr_url.strip():
                st.warning("URLを入力してください")
            elif "threads.net" not in _sr_url and "threads.com" not in _sr_url:
                st.warning("Threads投稿のURLを入力してください")
            elif _sr_hours == 0 and _sr_mins == 0:
                st.warning("時間を設定してください")
            else:
                _sr_existing = load_json(SCHEDULED_REPOSTS_FILE) if os.path.exists(SCHEDULED_REPOSTS_FILE) else []
                _sr_now = get_jst_time()
                _sr_run_at = _sr_now + timedelta(hours=_sr_hours, minutes=_sr_mins)
                _sr_box_data = next((b for b in _sr_boxes if b["name"] == _sr_sel_box), None)
                if _sr_box_data:
                    import uuid as _sr_uuid
                    _sr_task = {
                        "id": str(_sr_uuid.uuid4())[:8],
                        "box_name": _sr_sel_box,
                        "acc_usernames": _sr_box_data.get("acc_usernames", []),
                        "post_url": _sr_url.strip(),
                        "created_at": _sr_now.isoformat(),
                        "scheduled_at": _sr_run_at.isoformat(),
                        "status": "pending",
                        "results": []
                    }
                    _sr_existing.append(_sr_task)
                    save_json(SCHEDULED_REPOSTS_FILE, _sr_existing)
                    _sr_time_str = f"{_sr_hours}時間{_sr_mins}分" if _sr_hours > 0 else f"{_sr_mins}分"
                    st.success(f"✅ 予約完了！ {_sr_sel_box}で{_sr_time_str}後（{_sr_run_at.strftime('%H:%M')}）にリポストします")
                    st.rerun()

        # 予約一覧表示
        _sr_all = load_json(SCHEDULED_REPOSTS_FILE) if os.path.exists(SCHEDULED_REPOSTS_FILE) else []
        _sr_pending = [s for s in _sr_all if s.get("status") == "pending"]
        _sr_done = [s for s in _sr_all if s.get("status") in ("completed", "failed")]

        if _sr_pending:
            st.markdown("**⏳ 予約中**")
            for _sri, _sr in enumerate(_sr_pending):
                _sr_sched = _sr.get("scheduled_at", "")[:16].replace("T", " ")
                _sr_pcol1, _sr_pcol2 = st.columns([5, 1])
                _sr_pcol1.write(f"📌 **{_sr['box_name']}** → {_sr['post_url'][:50]}... | 実行予定: **{_sr_sched}**")
                if _sr_pcol2.button("❌", key=f"sr_cancel_{_sr['id']}"):
                    _sr_all = [s for s in _sr_all if s["id"] != _sr["id"]]
                    save_json(SCHEDULED_REPOSTS_FILE, _sr_all)
                    st.rerun()

        if _sr_done:
            with st.expander(f"📋 実行済み（{len(_sr_done)}件）"):
                for _sr in _sr_done[-10:]:
                    _sr_status = "✅" if _sr["status"] == "completed" else "❌"
                    _sr_time = _sr.get("scheduled_at", "")[:16].replace("T", " ")
                    _sr_res = _sr.get("results", [])
                    _sr_ok = sum(1 for r in _sr_res if r.get("ok"))
                    _sr_total = len(_sr_res)
                    st.write(f"{_sr_status} **{_sr['box_name']}** | {_sr_time} | 成功: {_sr_ok}/{_sr_total}")

                if st.button("🗑️ 履歴クリア", key="sr_clear_history"):
                    _sr_all = [s for s in _sr_all if s.get("status") == "pending"]
                    save_json(SCHEDULED_REPOSTS_FILE, _sr_all)
                    st.rerun()
    else:
        st.info("先にリポストボックスを作成してください")

# ==================== TAB 5: 引用投稿 ====================
with tab5:
    st.header("引用投稿")
    st.caption("複数アカウントでThreads投稿に引用コメント付き投稿を一斉実行")

    _qt_boxes = load_json(QUOTE_BOXES_FILE) if os.path.exists(QUOTE_BOXES_FILE) else []
    # Always reload accounts to include newly added ones
    _qt_fresh_accounts = load_json(ACCOUNTS_FILE)

    # ---------- ボックス作成・編集 ----------
    if '_qt_edit_pending' not in st.session_state:
        st.session_state._qt_edit_pending = None
    if st.session_state.get('_qt_clear_after_save'):
        st.session_state['qt_box_name'] = ""
        st.session_state['qt_acc_select'] = []
        st.session_state._qt_clear_after_save = False
    if st.session_state._qt_edit_pending is not None:
        _qt_pending = st.session_state._qt_edit_pending
        st.session_state.qt_box_name = _qt_pending['name']
        st.session_state.qt_acc_select = _qt_pending['accs']
        st.session_state._qt_edit_pending = None
    _qt_is_editing = 'qt_box_name' in st.session_state and bool(st.session_state.get('qt_box_name', ''))
    with st.expander("📦 ボックス作成 / 編集", expanded=len(_qt_boxes) == 0 or _qt_is_editing):
        _qt_name = st.text_input("ボックス名", key="qt_box_name")
        # 既に他のボックスに入っているアカウントは除外（編集中のボックスは除外しない）
        _qt_used_unames = set()
        for _qb in _qt_boxes:
            if _qb.get('name') != _qt_name:
                _qt_used_unames.update(_qb.get('acc_usernames', []))
        _qt_acc_options = []
        for _qt_num, _ac in enumerate(_qt_fresh_accounts, 1):
            _uname = _ac.get('username', '')
            if _uname and _uname not in _qt_used_unames:
                _aname = _ac.get('name', _ac.get('username', ''))
                _display_name_qt = _aname.split(" (@")[0]
                _qt_acc_options.append(f"{_uname}: {_qt_num}. {_display_name_qt}")
        _qt_selected_accs = st.multiselect("アカウント選択", _qt_acc_options, key="qt_acc_select")
        st.caption(f"選択中: {len(_qt_selected_accs)}件")

        if st.button("💾 ボックス保存", key="qt_save_box"):
            if _qt_name.strip() and _qt_selected_accs:
                _sel_unames = [s.split(":")[0].strip() for s in _qt_selected_accs]
                _new_box = {"name": _qt_name.strip(), "acc_usernames": _sel_unames}
                _found_qt = False
                for _qi, _qb in enumerate(_qt_boxes):
                    if _qb.get('name') == _qt_name.strip():
                        _qt_boxes[_qi] = _new_box
                        _found_qt = True
                        break
                if not _found_qt:
                    _qt_boxes.append(_new_box)
                save_json(QUOTE_BOXES_FILE, _qt_boxes)
                st.session_state._qt_clear_after_save = True
                st.rerun()
            else:
                st.warning("ボックス名とアカウントを入力してください")

    # ---------- 引用投稿実行エリア ----------
    if not _qt_boxes:
        st.info("ボックスを作成してください")
    else:
        st.markdown("---")

        # ボックス一覧（名前+人数のみ、編集・削除ボタン付き）
        for _bi, _box in enumerate(_qt_boxes):
            _box_name = _box.get('name', f'Box{_bi}')
            _box_unames = _box.get('acc_usernames', [])
            _qc1, _qc2, _qc3, _qc4 = st.columns([5, 1, 1, 1])
            _qc1.markdown(f"**📦 {_box_name}** — 👥 {len(_box_unames)}人")
            if _qc2.button("✏️", key=f"qt_edit_{_bi}"):
                _uname_to_acc_qt = {a.get('username',''): a for a in _qt_fresh_accounts}
                _uname_to_num_qt = {}
                for _eni, _ena in enumerate(_qt_fresh_accounts, 1):
                    _enu = _ena.get('username', '')
                    if _enu:
                        _uname_to_num_qt[_enu] = _eni
                _edit_opts = [f"{u}: {_uname_to_num_qt.get(u, '?')}. {_uname_to_acc_qt[u].get('name', u).split(' (@')[0]}" for u in _box_unames if u in _uname_to_acc_qt and u not in {}]
                st.session_state._qt_edit_pending = {'name': _box_name, 'accs': _edit_opts}
                st.rerun()
            if _qc3.button("🗑️", key=f"qt_del_{_bi}"):
                _qt_boxes.pop(_bi)
                save_json(QUOTE_BOXES_FILE, _qt_boxes)
                st.rerun()
            if _qc4.button("📋", key=f"qt_list_{_bi}"):
                st.session_state[f"qt_show_list_{_bi}"] = not st.session_state.get(f"qt_show_list_{_bi}", False)
                st.rerun()
            if st.session_state.get(f"qt_show_list_{_bi}", False):
                _list_html = ""
                _uname_to_acc_list = {a.get('username',''): a for a in _qt_fresh_accounts}
                for _bi_qt, _bu in enumerate(_box_unames):
                    _a = _uname_to_acc_list.get(_bu)
                    if _a:
                        _aname = _a.get('name', _bu)
                        _auname = _bu
                        _list_html += f'<div style="padding:4px 0;border-bottom:1px solid #333;display:flex;justify-content:space-between;align-items:center;">'
                        _list_html += f'<span style="color:#0ff;">{_bi_qt+1}. {_aname}</span>'
                        _list_html += f'<span style="display:flex;gap:6px;align-items:center;">'
                        _list_html += f'<button onclick="var t=document.createElement(\'textarea\');t.value=\'{_auname}\';document.body.appendChild(t);t.select();document.execCommand(\'copy\');document.body.removeChild(t);this.textContent=\'✓\';setTimeout(()=>this.textContent=\'📋\',1000)" style="background:#333;color:white;border:1px solid #555;border-radius:4px;padding:2px 6px;cursor:pointer;font-size:12px;">📋</button>'
                        _list_html += f'<a href="https://www.threads.net/@{_auname}" target="_blank" onclick="window.open(this.href,\'_blank\',\'width=420,height=750,scrollbars=yes\');return false;" style="background:linear-gradient(90deg,#00c6ff,#0072ff);color:white;padding:3px 10px;border-radius:6px;text-decoration:none;font-size:12px;">@{_auname}</a>'
                        _list_html += f'</span>'
                        _list_html += f'</div>'
                components.html(f'<div style="max-height:400px;overflow-y:auto;padding:8px;background:#1a1a2e;border-radius:8px;">{_list_html}</div>', height=min(len(_box_unames) * 35 + 20, 420))

        # 編集モード
        if 'qt_editing' in st.session_state and st.session_state.qt_editing is not None:
            _edit_idx = st.session_state.qt_editing
            if 0 <= _edit_idx < len(_qt_boxes):
                _edit_box = _qt_boxes[_edit_idx]
                st.markdown(f"---\n**✏️ 「{_edit_box['name']}」を編集中**")
                _qt_all_opts = []
                _qt_uname_opt_map = {}
                for _eni, _ac in enumerate(_qt_fresh_accounts, 1):
                    _u = _ac.get('username', '')
                    if _u:
                        _opt = f"{_u}: {_eni}. {_ac.get('name', _u).split(' (@')[0]}"
                        _qt_all_opts.append(_opt)
                        _qt_uname_opt_map[_u] = _opt
                _qt_current = [_qt_uname_opt_map[u] for u in _edit_box.get('acc_usernames', []) if u in _qt_uname_opt_map]
                _qt_edit_accs = st.multiselect("アカウント編集", _qt_all_opts, default=_qt_current, key="qt_edit_accs")
                _qe1, _qe2 = st.columns(2)
                if _qe1.button("💾 更新", key="qt_update_box"):
                    _new_unames = [s.split(":")[0].strip() for s in _qt_edit_accs]
                    _qt_boxes[_edit_idx]['acc_usernames'] = _new_unames
                    save_json(QUOTE_BOXES_FILE, _qt_boxes)
                    st.session_state.qt_editing = None
                    st.success(f"✅ 更新しました（{len(_new_indices)}アカウント）")
                    st.rerun()
                if _qe2.button("❌ キャンセル", key="qt_cancel_edit"):
                    st.session_state.qt_editing = None
                    st.rerun()

        st.markdown("---")

        # ボックス選択 + URL + 引用テキスト + 実行
        _qt_box_names = [b.get('name', f'Box{i}') for i, b in enumerate(_qt_boxes)]
        _sel_qt_box_name = st.selectbox("ボックス選択", _qt_box_names, key="qt_sel_box")
        _sel_qt_box = next((b for b in _qt_boxes if b.get('name') == _sel_qt_box_name), None)

        _qt_url = st.text_input("Threads投稿URL", placeholder="https://www.threads.net/@user/post/xxxxx", key="qt_url")
        _qt_text = st.text_area("引用コメント", placeholder="引用コメントを入力...", key="qt_text", height=100)

        if st.button("💬 一斉引用投稿", key="qt_exec", type="primary"):
            if not _sel_qt_box:
                st.error("ボックスを選択してください")
            elif not _qt_url.strip():
                st.warning("Threads投稿URLを入力してください")
            elif not _qt_text.strip():
                st.warning("引用コメントを入力してください")
            else:
                _qt_username, _qt_shortcode = extract_threads_username_and_shortcode(_qt_url.strip())
                if not _qt_username or not _qt_shortcode:
                    st.error("❌ URLの形式が正しくありません")
                else:
                    _status_qt = st.empty()
                    _status_qt.info(f"⏳ @{_qt_username} の投稿IDを検索中...")
                    _owner_acc_qt = None
                    for _a in st.session_state.accounts:
                        if _a.get('username', '') == _qt_username:
                            _owner_acc_qt = _a
                            break
                    if not _owner_acc_qt:
                        st.error(f"❌ @{_qt_username} はアカウント管理に登録されていません")
                    else:
                        _threads_post_id_qt = find_threads_post_id(_owner_acc_qt, _qt_shortcode)
                        if not _threads_post_id_qt:
                            st.error(f"❌ @{_qt_username} の投稿一覧からこの投稿が見つかりませんでした")
                        else:
                            _status_qt.info(f"✅ 投稿ID取得成功: {_threads_post_id_qt}")
                            _box_unames_qt = _sel_qt_box.get('acc_usernames', [])
                            _uname_to_acc_qt_exec = {a.get('username',''): a for a in st.session_state.accounts}
                            _progress_qt = st.progress(0)
                            _results_qt = []
                            _total_qt = len(_box_unames_qt)

                            for _idx, _acc_uname in enumerate(_box_unames_qt):
                                _acc = _uname_to_acc_qt_exec.get(_acc_uname)
                                if _acc:
                                    _aname = _acc.get('name', _acc.get('username', ''))
                                    _status_qt.info(f"⏳ {_aname} を引用投稿中... ({_idx+1}/{_total_qt})")

                                    _ok, _res = quote_thread(_acc, _threads_post_id_qt, _qt_text.strip())
                                    if _ok:
                                        _results_qt.append(f"✅ {_aname}")
                                    else:
                                        _results_qt.append(f"❌ {_aname}: {str(_res)[:80]}")

                                    _progress_qt.progress((_idx + 1) / _total_qt)

                                    if _idx < _total_qt - 1:
                                        time.sleep(1)
                                else:
                                    _results_qt.append(f"⚠️ #{_acc_i} アカウント見つからず")

                            _status_qt.empty()
                            _progress_qt.empty()

                            _ok_count_qt = sum(1 for r in _results_qt if r.startswith("✅"))
                            st.success(f"🎉 引用投稿完了！ 成功: {_ok_count_qt}/{_total_qt}")
                            for _r in _results_qt:
                                st.write(_r)

    # ---------- 単体引用投稿 ----------
    st.markdown("---")
    st.subheader("💬 単体引用投稿")
    st.caption("1アカウントで引用投稿（引用リンク履歴あり）")

    QUOTE_HISTORY_FILE = os.path.join(BASE_DIR, "quote_history.json")
    _qt_history = load_json(QUOTE_HISTORY_FILE) if os.path.exists(QUOTE_HISTORY_FILE) else []

    # アカウント選択（1つだけ、最新順で選べる）
    _sq_acc_idx = None
    if not st.session_state.accounts:
        st.warning("アカウントを先に登録してください")
    else:
        _sq_acc_opts = [f"{i}: {a.get('name', a.get('username', ''))}" for i, a in enumerate(st.session_state.accounts)]
        _sq_acc_opts_rev = list(reversed(_sq_acc_opts))
        _sq_sort_col1, _sq_sort_col2 = st.columns([3, 1])
        _sq_newest = _sq_sort_col2.checkbox("最新順", value=False, key="sq_newest")
        _sq_display = _sq_acc_opts_rev if _sq_newest else _sq_acc_opts
        _sq_sel = _sq_sort_col1.selectbox("アカウント選択", _sq_display, key="sq_acc_sel")
        _sq_acc_idx = int(_sq_sel.split(":")[0])

    # URL入力 or 履歴から選択
    _sq_url_input = st.text_input("Threads投稿URL", placeholder="https://www.threads.net/@user/post/xxxxx", key="sq_url")

    if _qt_history:
        _hist_labels = [f"{h.get('url', '')[:60]}..." for h in _qt_history]
        _hist_sel = st.selectbox("📋 引用履歴から選択", ["直接入力"] + _hist_labels, key="sq_hist_sel")
        if _hist_sel != "直接入力":
            _hist_idx = _hist_labels.index(_hist_sel)
            _sq_url_input = _qt_history[_hist_idx].get('url', '')

    _sq_text = st.text_area("引用コメント", placeholder="引用コメントを入力...", key="sq_text", height=100)

    _sq_c1, _sq_c2 = st.columns([2, 1])
    if _sq_c1.button("💬 引用投稿", key="sq_exec", type="primary"):
        if _sq_acc_idx is None:
            st.warning("アカウントを先に登録してください")
        else:
            _sq_url_final = _sq_url_input.strip()
            if not _sq_url_final:
                st.warning("URLを入力してください")
            elif not _sq_text.strip():
                st.warning("引用コメントを入力してください")
            else:
                _sq_uname, _sq_sc = extract_threads_username_and_shortcode(_sq_url_final)
                if not _sq_uname or not _sq_sc:
                    st.error("❌ URLの形式が正しくありません")
                else:
                    _sq_owner = None
                    for _a in st.session_state.accounts:
                        if _a.get('username', '') == _sq_uname:
                            _sq_owner = _a
                            break
                    if not _sq_owner:
                        st.error(f"❌ @{_sq_uname} はアカウント管理に登録されていません")
                    else:
                        with st.spinner("投稿IDを検索中..."):
                            _sq_pid = find_threads_post_id(_sq_owner, _sq_sc)
                        if not _sq_pid:
                            st.error("❌ 投稿が見つかりません（削除された可能性あり）")
                            # 履歴から削除
                            _qt_history = [h for h in _qt_history if h.get('url', '') != _sq_url_final]
                            save_json(QUOTE_HISTORY_FILE, _qt_history)
                        else:
                            _sq_acc = st.session_state.accounts[_sq_acc_idx]
                            _sq_aname = _sq_acc.get('name', _sq_acc.get('username', ''))
                            with st.spinner(f"{_sq_aname} で引用投稿中..."):
                                _ok, _res = quote_thread(_sq_acc, _sq_pid, _sq_text.strip())
                            if _ok:
                                st.success(f"✅ {_sq_aname} で引用投稿しました！")
                                # 履歴に保存（重複チェック）
                                if not any(h.get('url') == _sq_url_final for h in _qt_history):
                                    _qt_history.insert(0, {"url": _sq_url_final, "saved": get_jst_time().strftime('%Y-%m-%d %H:%M')})
                                    save_json(QUOTE_HISTORY_FILE, _qt_history)
                            else:
                                st.error(f"❌ {_sq_aname}: {str(_res)[:100]}")

    # 履歴クリアボタン
    if _qt_history and _sq_c2.button("🗑️ 履歴クリア", key="sq_clear_hist"):
        save_json(QUOTE_HISTORY_FILE, [])
        st.rerun()

# ==================== TAB 6: バズリサーチ ====================
BUZZ_POSTS_FILE = os.path.join(BASE_DIR, "buzz_posts.json")
BUZZ_LOGIN_FILE = os.path.join(BASE_DIR, "buzz_login.json")
BUZZ_COOKIE_FILE = os.path.join(BASE_DIR, "threads_session.json")

with tab6:
    st.header("バズリサーチ")
    st.caption("Threadsのおすすめフィードからバズ投稿を自動収集")

    # ログイン情報の設定
    _buzz_login = load_json(BUZZ_LOGIN_FILE) if os.path.exists(BUZZ_LOGIN_FILE) else {}
    with st.expander("🔑 ログイン設定", expanded=not _buzz_login):
        _bz_user = st.text_input("Instagramユーザー名", value=_buzz_login.get("username", ""), key="bz_user")
        _bz_pass = st.text_input("パスワード", value=_buzz_login.get("password", ""), type="password", key="bz_pass")
        if st.button("💾 保存", key="bz_save_login"):
            if _bz_user.strip() and _bz_pass.strip():
                save_json(BUZZ_LOGIN_FILE, {"username": _bz_user.strip(), "password": _bz_pass.strip()})
                _buzz_login = {"username": _bz_user.strip(), "password": _bz_pass.strip()}
                st.success("✅ ログイン情報を保存しました")
            else:
                st.warning("ユーザー名とパスワードを入力してください")

    # スクレイピング実行
    if not _buzz_login.get("username"):
        st.info("まずログイン設定からInstagramアカウントを登録してください")
    else:
        _bz_c1, _bz_c2 = st.columns(2)
        _bz_scroll = _bz_c1.selectbox("スクロール回数", [3, 5, 10, 15], index=1, key="bz_scroll")
        _bz_min_likes = _bz_c2.number_input("最低いいね数", min_value=0, value=50, step=10, key="bz_min_likes")

        if st.button("🔍 バズ投稿を取得", key="bz_fetch"):
            with st.spinner("Threadsフィードをスクレイピング中... (30秒〜2分)"):
                try:
                    from playwright.sync_api import sync_playwright as _bz_sp
                    import re as _bz_re

                    _bz_posts = []
                    with _bz_sp() as _pw:
                        _br = _pw.chromium.launch(headless=True)
                        _ctx = _br.new_context(
                            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                            viewport={"width": 1280, "height": 800}
                        )

                        # Cookie復元
                        _has_cookies = False
                        if os.path.exists(BUZZ_COOKIE_FILE):
                            try:
                                _saved_cookies = load_json(BUZZ_COOKIE_FILE)
                                if _saved_cookies:
                                    _ctx.add_cookies(_saved_cookies)
                                    _has_cookies = True
                            except:
                                pass

                        _pg = _ctx.new_page()

                        # ログイン or Cookie復元チェック
                        _pg.goto("https://www.threads.net", wait_until="domcontentloaded", timeout=60000)
                        _pg.wait_for_timeout(3000)

                        # ログインが必要か判定
                        _need_login = False
                        try:
                            _login_btn = _pg.query_selector("text=Log in") or _pg.query_selector("text=ログイン")
                            if _login_btn:
                                _need_login = True
                        except:
                            _need_login = True

                        if _need_login or not _has_cookies:
                            st.info("ログイン中...")
                            _pg.goto("https://www.threads.net/login", wait_until="domcontentloaded", timeout=60000)
                            _pg.wait_for_timeout(2000)

                            # Instagram login form
                            try:
                                _user_input = _pg.query_selector("input[name='username']") or _pg.query_selector("input[autocomplete='username']")
                                _pass_input = _pg.query_selector("input[name='password']") or _pg.query_selector("input[type='password']")
                                if _user_input and _pass_input:
                                    _user_input.fill(_buzz_login["username"])
                                    _pg.wait_for_timeout(500)
                                    _pass_input.fill(_buzz_login["password"])
                                    _pg.wait_for_timeout(500)
                                    _login_submit = _pg.query_selector("button[type='submit']") or _pg.query_selector("div[role='button']")
                                    if _login_submit:
                                        _login_submit.click()
                                        _pg.wait_for_timeout(5000)
                                else:
                                    st.warning("ログインフォームが見つかりません")
                            except Exception as _le:
                                st.warning(f"ログインエラー: {str(_le)[:100]}")

                            # Cookie保存
                            try:
                                _cookies = _ctx.cookies()
                                save_json(BUZZ_COOKIE_FILE, _cookies)
                            except:
                                pass

                            # フィードに戻る
                            _pg.goto("https://www.threads.net", wait_until="domcontentloaded", timeout=60000)
                            _pg.wait_for_timeout(3000)

                        # スクロールしてフィード読み込み
                        import random as _bz_rand
                        for _si in range(_bz_scroll):
                            _pg.evaluate("window.scrollBy(0, 1200)")
                            _pg.wait_for_timeout(_bz_rand.randint(2000, 4000))

                        # 投稿を取得
                        _articles = _pg.query_selector_all("div[data-pressable-container='true']")
                        if not _articles:
                            _articles = _pg.query_selector_all("article")

                        for _art in _articles:
                            try:
                                _txt = _art.inner_text()
                                _lines = [l.strip() for l in _txt.split("\n") if l.strip()]

                                # ユーザー名を取得
                                _post_user = ""
                                for _l in _lines:
                                    if _bz_re.match(r'^[a-zA-Z0-9_.]+$', _l) and len(_l) < 30 and len(_l) > 2:
                                        _post_user = _l
                                        break

                                # いいね数を取得
                                _likes = 0
                                for _l in _lines:
                                    # "1,234" or "1.2K" or "15K" patterns
                                    _m = _bz_re.match(r'^([\d,]+)$', _l)
                                    if _m:
                                        _likes = max(_likes, int(_m.group(1).replace(",", "")))
                                    _m2 = _bz_re.match(r'^([\d.]+)[KkMm]$', _l)
                                    if _m2:
                                        _val = float(_m2.group(1))
                                        if _l[-1] in 'Kk':
                                            _likes = max(_likes, int(_val * 1000))
                                        elif _l[-1] in 'Mm':
                                            _likes = max(_likes, int(_val * 1000000))

                                # コンテンツテキスト抽出
                                _skip_words = {"Threads", "Replies", "Reposts", "Pinned", "Follow", "Following",
                                               "Translate", "More", "Reply", "Like", "Share", "Verified",
                                               "Log in", "Sign up", "Mention", "Comment", "Repost", "おすすめ",
                                               "フォロー中", "いいね", "返信", "シェア", "翻訳", "もっと見る"}
                                _content_lines = []
                                for _l in _lines:
                                    if len(_l) <= 1:
                                        continue
                                    if _l in _skip_words:
                                        continue
                                    if _l == _post_user:
                                        continue
                                    if _bz_re.match(r'^[a-zA-Z0-9_.]+$', _l) and len(_l) < 30:
                                        continue
                                    if _bz_re.match(r'^[\d,.]+[KMkm]?$', _l):
                                        continue
                                    if _bz_re.match(r'^\d+[hmd]$|^\d{1,2}/\d{1,2}|^\d+\s*(時間|分|日|秒)', _l):
                                        continue
                                    if _bz_re.search(r'(TranslateLike|Like\d+Comment|Comment\d+Repost|RepostShare)', _l):
                                        continue
                                    if _bz_re.match(r'^[a-zA-Z0-9_.]+\d+[hmd]', _l):
                                        continue
                                    if _bz_re.match(r'^[a-zA-Z0-9_.]+More$', _l):
                                        continue
                                    _content_lines.append(_l)

                                _post_text = "\n".join(_content_lines[:8])
                                if len(_post_text) < 5:
                                    continue
                                if _likes < _bz_min_likes:
                                    continue

                                # パーマリンク
                                _permalink = ""
                                _links = _art.query_selector_all("a[href*='/post/']")
                                for _lnk in _links:
                                    _href = _lnk.get_attribute("href") or ""
                                    if "/post/" in _href:
                                        _permalink = f"https://www.threads.net{_href}" if _href.startswith("/") else _href
                                        break

                                # 画像URL
                                _media_urls = []
                                for _img in _art.query_selector_all("img"):
                                    _src = _img.get_attribute("src") or ""
                                    _alt = _img.get_attribute("alt") or ""
                                    if _src and "cdninstagram" in _src and "profile" not in _alt.lower() and "s150x150" not in _src:
                                        _media_urls.append(_src)

                                _bz_posts.append({
                                    "username": f"@{_post_user}" if _post_user else "不明",
                                    "text": _post_text,
                                    "like_count": _likes,
                                    "media_urls": _media_urls[:4],
                                    "permalink": _permalink,
                                    "scraped_at": get_jst_time().isoformat()
                                })
                            except:
                                pass

                        # Cookie保存（更新）
                        try:
                            _cookies = _ctx.cookies()
                            save_json(BUZZ_COOKIE_FILE, _cookies)
                        except:
                            pass

                        _pg.close()
                        _br.close()

                    # いいね順にソート
                    _bz_posts.sort(key=lambda x: x.get("like_count", 0), reverse=True)

                    if _bz_posts:
                        # 既存データとマージ（重複排除）
                        _existing = load_json(BUZZ_POSTS_FILE) if os.path.exists(BUZZ_POSTS_FILE) else []
                        _existing_links = set(p.get("permalink", "") for p in _existing if p.get("permalink"))
                        _new_posts = [p for p in _bz_posts if p.get("permalink") and p["permalink"] not in _existing_links]
                        _all_buzz = _new_posts + _existing
                        save_json(BUZZ_POSTS_FILE, _all_buzz[:200])  # 最大200件保持
                        st.session_state.buzz_results = _bz_posts
                        st.success(f"✅ {len(_bz_posts)}件のバズ投稿を取得（新規{len(_new_posts)}件）")
                    else:
                        st.warning("条件に合う投稿が見つかりませんでした（いいね数フィルタを下げてみてください）")

                except Exception as _e:
                    st.error(f"エラー: {str(_e)[:200]}")

        # 結果表示
        _display_posts = st.session_state.get("buzz_results", [])
        if not _display_posts:
            _display_posts = load_json(BUZZ_POSTS_FILE) if os.path.exists(BUZZ_POSTS_FILE) else []

        if _display_posts:
            st.markdown("---")
            st.subheader(f"🔥 バズ投稿一覧（{len(_display_posts)}件）")

            for _bpi, _bp in enumerate(_display_posts[:50]):
                _bp_user = _bp.get("username", "不明")
                _bp_text = _bp.get("text", "")
                _bp_likes = _bp.get("like_count", 0)
                _bp_media = _bp.get("media_urls", [])
                _bp_link = _bp.get("permalink", "")
                _bp_date = _bp.get("scraped_at", "")[:16]

                st.markdown("---")
                _bpc1, _bpc2 = st.columns([4, 1])
                _bpc1.write(f"**#{_bpi+1}** {_bp_user} | ❤ **{_bp_likes:,}** | 取得: {_bp_date}")
                if _bp_link:
                    _bpc2.link_button("🔗 開く", _bp_link)
                st.text(_bp_text[:300])

                # 画像プレビュー
                if _bp_media:
                    _img_cols = st.columns(min(len(_bp_media), 4))
                    for _mi, _mu in enumerate(_bp_media[:4]):
                        try:
                            _img_cols[_mi].image(_mu, width=150)
                        except:
                            pass

        # クリアボタン
        if st.button("🗑️ 履歴クリア", key="bz_clear"):
            save_json(BUZZ_POSTS_FILE, [])
            st.session_state.buzz_results = []
            st.rerun()