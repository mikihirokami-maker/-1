"""
認証モジュール (Streamlit SaaS版)
- ログイン画面の表示
- セッション管理
- サイドバーのユーザー情報表示
"""

from typing import Optional

import streamlit as st
import user_manager


def check_auth() -> Optional[dict]:
    """
    認証ゲート。各ページの先頭で呼び出す。
    ログイン済みならユーザー辞書を返す。
    未ログインならログイン画面を表示し st.stop() で処理を中断する。
    """
    user = st.session_state.get("user")

    if user:
        # DBから最新のユーザー情報を再取得して有効性を確認
        fresh_user = user_manager.get_user(user["id"])
        if fresh_user and fresh_user.get("is_active"):
            st.session_state["user"] = fresh_user
            return fresh_user
        else:
            # ユーザーが無効化された場合はセッションをクリア
            st.session_state.pop("user", None)

    # 未ログイン → ログイン画面を表示して停止
    login_page()
    st.stop()
    return None


def login_page():
    """ログイン画面を表示する"""

    # ダークテーマのカスタムCSS
    st.markdown("""
    <style>
        .stApp {
            background-color: #0a0a0a;
        }
        .login-title {
            text-align: center;
            color: #00c6ff;
            font-size: 2.2rem;
            font-weight: 700;
            margin-bottom: 0.2rem;
        }
        .login-subtitle {
            text-align: center;
            color: #cccccc;
            font-size: 1.1rem;
            margin-bottom: 2rem;
        }
        .stTextInput > div > div > input {
            background-color: #1a1a2e;
            color: #ffffff;
            border: 1px solid #333355;
            border-radius: 8px;
        }
        .stTextInput > div > div > input:focus {
            border-color: #00c6ff;
            box-shadow: 0 0 0 1px #00c6ff;
        }
        .stButton > button {
            background: linear-gradient(135deg, #00c6ff, #0072ff);
            color: white;
            border: none;
            border-radius: 8px;
            padding: 0.6rem 2rem;
            font-size: 1rem;
            font-weight: 600;
            width: 100%;
            transition: opacity 0.2s;
        }
        .stButton > button:hover {
            opacity: 0.85;
            color: white;
        }
        div[data-testid="stForm"] {
            background-color: #111122;
            padding: 2rem;
            border-radius: 12px;
            border: 1px solid #222244;
        }
    </style>
    """, unsafe_allow_html=True)

    # 中央寄せレイアウト
    _col_left, col_center, _col_right = st.columns([1, 2, 1])

    with col_center:
        st.markdown("")
        st.markdown("")
        st.markdown('<div class="login-title">🔐 Threads Auto Master</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-subtitle">ログイン</div>', unsafe_allow_html=True)

        with st.form("login_form"):
            username = st.text_input("ユーザー名", placeholder="ユーザー名を入力")
            password = st.text_input("パスワード", type="password", placeholder="パスワードを入力")
            submitted = st.form_submit_button("ログイン")

            if submitted:
                if not username or not password:
                    st.error("ユーザー名とパスワードを入力してください。")
                else:
                    user = user_manager.authenticate(username, password)
                    if user is None:
                        # authenticate は非アクティブユーザーにも None を返す。
                        # 区別のため、ユーザー名でDBを直接確認はしない（セキュリティ上）。
                        # ただし、存在するが無効なケースを親切に伝えたい場合は
                        # user_manager 側で別のシグナルが必要。ここでは汎用メッセージ。
                        st.error("ユーザー名またはパスワードが間違っています")
                    elif not user.get("is_active"):
                        st.error("アカウントが無効です。管理者にお問い合わせください。")
                    else:
                        st.session_state["user"] = user
                        st.rerun()


def logout():
    """セッションをクリアしてリロードする"""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()


def show_user_sidebar(user: dict):
    """サイドバーにユーザー情報を表示する"""
    with st.sidebar:
        # 表示名（未設定ならusername）
        display_name = user.get("display_name") or user.get("username", "")
        st.markdown(f"**👤 {display_name}**")

        # プラン情報
        plan_name = user.get("plan_name", "ライト")
        max_accounts = user.get("max_accounts", 3)
        # 現在のアカウント使用数はここでは取得しない（呼び出し側が渡す想定もあるが、
        # シンプルに上限のみ表示）
        st.caption(f"プラン: {plan_name} (上限 {max_accounts} アカウント)")

        # 有効期限
        expires_at = user.get("expires_at")
        if expires_at:
            # ISO形式から表示用に変換
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(expires_at)
                st.caption(f"有効期限: {dt.strftime('%Y年%m月%d日')}")
            except (ValueError, TypeError):
                st.caption(f"有効期限: {expires_at}")

        st.divider()

        if st.button("ログアウト", use_container_width=True):
            logout()
