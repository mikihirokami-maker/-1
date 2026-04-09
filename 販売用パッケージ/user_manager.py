"""
ユーザー管理モジュール (SaaS版)
- SQLiteによるユーザーデータ管理
- パスワードのハッシュ化 (PBKDF2)
- スレッドセーフなDB接続
- JSTタイムスタンプ
"""

import sqlite3
import hashlib
import os
import uuid
import threading
from datetime import datetime, timezone, timedelta

# === 定数 ===

# スクリプトのディレクトリを基準パスとする
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db")

# 日本標準時 (UTC+9)
JST = timezone(timedelta(hours=9))

# スレッドセーフ用ロック
_db_lock = threading.Lock()

# プラン定義
PLANS = {
    'lite':        {'name': 'ライト',        'max_accounts': 10,   'price': 1980},
    'standard':    {'name': 'スタンダード',    'max_accounts': 30,   'price': 3980},
    'pro':         {'name': 'プロ',          'max_accounts': 50,   'price': 5980},
    'business100': {'name': 'ビジネス100',    'max_accounts': 100,  'price': 9800},
    'business200': {'name': 'ビジネス200',    'max_accounts': 200,  'price': 14800},
    'business300': {'name': 'ビジネス300',    'max_accounts': 300,  'price': 19800},
}


# === ヘルパー関数 ===

def _now_jst() -> str:
    """現在時刻をJST ISO形式で返す"""
    return datetime.now(JST).isoformat()


def _hash_password(password: str) -> str:
    """パスワードをPBKDF2でハッシュ化し、 'salt_hex:hash_hex' 形式で返す"""
    salt = os.urandom(32)
    pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return f"{salt.hex()}:{pw_hash.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    """保存済みハッシュとパスワードを照合する"""
    try:
        salt_hex, hash_hex = stored.split(':')
        salt = bytes.fromhex(salt_hex)
        pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        return pw_hash.hex() == hash_hex
    except (ValueError, AttributeError):
        return False


def _get_conn() -> sqlite3.Connection:
    """スレッドセーフなDB接続を取得する"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # WALモードで並行アクセス性能向上
    return conn


def _row_to_dict(row) -> dict:
    """DBの行をユーザー辞書に変換する (plan_name付き)"""
    if row is None:
        return None
    d = dict(row)
    # bool変換
    d['is_active'] = bool(d['is_active'])
    d['is_admin'] = bool(d['is_admin'])
    # expires_at が空文字列ならNoneに変換
    if not d.get('expires_at'):
        d['expires_at'] = None
    # プラン名を付加
    plan_info = PLANS.get(d.get('plan', 'lite'), PLANS['lite'])
    d['plan_name'] = plan_info['name']
    return d


# === データベース初期化 ===

def init_db():
    """
    データベースとテーブルを初期化する。
    ユーザーが1人もいない場合、デフォルト管理者を作成する。
    """
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id            TEXT PRIMARY KEY,
                    username      TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    email         TEXT DEFAULT '',
                    display_name  TEXT DEFAULT '',
                    plan          TEXT DEFAULT 'lite',
                    max_accounts  INTEGER DEFAULT 3,
                    is_active     INTEGER DEFAULT 1,
                    is_admin      INTEGER DEFAULT 0,
                    created_at    TEXT,
                    expires_at    TEXT,
                    last_login    TEXT
                )
            """)
            conn.commit()

            # ユーザーが存在しない場合、デフォルト管理者を作成
            row = conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()
            if row['cnt'] == 0:
                now = _now_jst()
                admin_id = str(uuid.uuid4())
                conn.execute("""
                    INSERT INTO users (id, username, password_hash, plan, max_accounts,
                                       is_active, is_admin, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    admin_id,
                    'admin',
                    _hash_password('admin123'),
                    'business300',
                    PLANS['business300']['max_accounts'],
                    1,  # is_active
                    1,  # is_admin
                    now,
                ))
                conn.commit()
                print(f"[init_db] デフォルト管理者を作成しました (ID: {admin_id})")
        finally:
            conn.close()


# === ユーザー操作関数 ===

def create_user(username: str, password: str, plan: str = 'lite',
                expires_at=None, display_name: str = '', email: str = '') -> dict:
    """
    新規ユーザーを作成する。
    成功時はユーザー辞書を返す。ユーザー名が重複している場合はNoneを返す。
    """
    plan_info = PLANS.get(plan, PLANS['lite'])
    user_id = str(uuid.uuid4())
    now = _now_jst()

    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("""
                INSERT INTO users (id, username, password_hash, email, display_name,
                                   plan, max_accounts, is_active, is_admin,
                                   created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?)
            """, (
                user_id, username, _hash_password(password),
                email, display_name,
                plan, plan_info['max_accounts'],
                now, expires_at,
            ))
            conn.commit()
            # 作成したユーザーを返す
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return _row_to_dict(row)
        except sqlite3.IntegrityError:
            # ユーザー名の重複
            return None
        finally:
            conn.close()


def authenticate(username: str, password: str) -> dict:
    """
    ユーザー認証を行う。
    成功時はユーザー辞書を返し、last_loginを更新する。
    失敗時 (パスワード不一致、無効ユーザー、期限切れ) はNoneを返す。
    """
    with _db_lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()

            if row is None:
                return None

            user = dict(row)

            # パスワード照合
            if not _verify_password(password, user['password_hash']):
                return None

            # アクティブチェック
            if not user['is_active']:
                return None

            # 期限切れチェック
            if user['expires_at']:
                expires = datetime.fromisoformat(user['expires_at'])
                if datetime.now(JST) > expires:
                    # 期限切れ → 無効化
                    conn.execute(
                        "UPDATE users SET is_active = 0 WHERE id = ?", (user['id'],)
                    )
                    conn.commit()
                    return None

            # last_login を更新
            now = _now_jst()
            conn.execute(
                "UPDATE users SET last_login = ? WHERE id = ?", (now, user['id'])
            )
            conn.commit()

            # 更新後のデータを取得して返す
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (user['id'],)
            ).fetchone()
            return _row_to_dict(row)
        finally:
            conn.close()


def get_user(user_id: str) -> dict:
    """ユーザーIDでユーザーを取得する"""
    with _db_lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            return _row_to_dict(row)
        finally:
            conn.close()


def get_all_users() -> list:
    """全ユーザーのリストを返す"""
    with _db_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM users ORDER BY created_at"
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        finally:
            conn.close()


def get_all_active_users() -> list:
    """アクティブかつ期限内のユーザーリストを返す"""
    now = _now_jst()
    with _db_lock:
        conn = _get_conn()
        try:
            rows = conn.execute("""
                SELECT * FROM users
                WHERE is_active = 1
                  AND (expires_at IS NULL OR expires_at = '' OR expires_at > ?)
                ORDER BY created_at
            """, (now,)).fetchall()
            return [_row_to_dict(r) for r in rows]
        finally:
            conn.close()


def update_user(user_id: str, **kwargs):
    """
    ユーザーの任意のフィールドを更新する。
    例: update_user(uid, display_name='新しい名前', email='new@example.com')
    """
    if not kwargs:
        return

    # 許可フィールド (password_hashは change_password を使うこと)
    allowed = {
        'username', 'email', 'display_name', 'plan', 'max_accounts',
        'is_active', 'is_admin', 'expires_at', 'last_login',
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return

    # planが変更された場合、max_accountsも自動更新
    if 'plan' in fields and 'max_accounts' not in fields:
        plan_info = PLANS.get(fields['plan'])
        if plan_info:
            fields['max_accounts'] = plan_info['max_accounts']

    set_clause = ', '.join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [user_id]

    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                f"UPDATE users SET {set_clause} WHERE id = ?", values
            )
            conn.commit()
        finally:
            conn.close()


def update_user_plan(user_id: str, plan: str, expires_at=None):
    """ユーザーのプランと有効期限を変更する"""
    plan_info = PLANS.get(plan, PLANS['lite'])
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("""
                UPDATE users SET plan = ?, max_accounts = ?, expires_at = ?
                WHERE id = ?
            """, (plan, plan_info['max_accounts'], expires_at, user_id))
            conn.commit()
        finally:
            conn.close()


def set_user_active(user_id: str, is_active: bool):
    """ユーザーの有効/無効を切り替える"""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE users SET is_active = ? WHERE id = ?",
                (1 if is_active else 0, user_id)
            )
            conn.commit()
        finally:
            conn.close()


def check_and_disable_expired_users():
    """有効期限が過ぎたユーザーを無効化する"""
    now = _now_jst()
    with _db_lock:
        conn = _get_conn()
        try:
            cursor = conn.execute("""
                UPDATE users SET is_active = 0
                WHERE is_active = 1
                  AND expires_at IS NOT NULL
                  AND expires_at != ''
                  AND expires_at < ?
            """, (now,))
            conn.commit()
            count = cursor.rowcount
            if count > 0:
                print(f"[check_expired] {count}件の期限切れユーザーを無効化しました")
            return count
        finally:
            conn.close()


def delete_user(user_id: str):
    """ユーザーをデータベースから削除する"""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
        finally:
            conn.close()


def get_user_data_dir(user_id: str) -> str:
    """
    ユーザー固有のデータディレクトリパスを返す。
    ディレクトリが存在しない場合は作成する。
    """
    data_dir = os.path.join(BASE_DIR, "data", user_id)
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def change_password(user_id: str, new_password: str):
    """ユーザーのパスワードを変更する"""
    new_hash = _hash_password(new_password)
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (new_hash, user_id)
            )
            conn.commit()
        finally:
            conn.close()


def count_users() -> dict:
    """
    ユーザー数の集計を返す。
    戻り値: {'total': int, 'active': int, 'by_plan': {'lite': int, ...}}
    """
    with _db_lock:
        conn = _get_conn()
        try:
            # 全体数
            total = conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()['cnt']

            # アクティブ数
            active = conn.execute(
                "SELECT COUNT(*) as cnt FROM users WHERE is_active = 1"
            ).fetchone()['cnt']

            # プラン別集計
            rows = conn.execute(
                "SELECT plan, COUNT(*) as cnt FROM users GROUP BY plan"
            ).fetchall()
            by_plan = {r['plan']: r['cnt'] for r in rows}

            # 全プランのキーを確保 (0件のプランも含む)
            for plan_key in PLANS:
                if plan_key not in by_plan:
                    by_plan[plan_key] = 0

            return {
                'total': total,
                'active': active,
                'by_plan': by_plan,
            }
        finally:
            conn.close()


# === メイン (テスト用) ===

if __name__ == '__main__':
    print("=== ユーザー管理モジュール テスト ===")
    init_db()

    # テストユーザー作成
    user = create_user('testuser', 'pass123', plan='standard', display_name='テストユーザー')
    if user:
        print(f"ユーザー作成成功: {user['username']} ({user['plan_name']})")

    # 認証テスト
    auth = authenticate('admin', 'admin123')
    if auth:
        print(f"管理者認証成功: {auth['username']} (admin={auth['is_admin']})")

    # 集計テスト
    stats = count_users()
    print(f"ユーザー数: 合計={stats['total']}, アクティブ={stats['active']}")
    print(f"プラン別: {stats['by_plan']}")
