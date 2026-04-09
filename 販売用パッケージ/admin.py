"""
管理パネル - SaaSユーザー管理用Streamlitアプリ
ポート8502で起動: streamlit run admin.py --server.port 8502
"""

import streamlit as st
import pandas as pd
import shutil
from datetime import datetime, date, timedelta

import user_manager

# === ページ設定 ===
st.set_page_config(
    page_title="管理パネル",
    page_icon="🔧",
    layout="wide",
)

# === ダークテーマCSS ===
st.markdown("""
<style>
    .stApp {
        background-color: #0e1117;
        color: #fafafa;
    }
    .metric-card {
        background-color: #1e2130;
        border-radius: 10px;
        padding: 20px;
        text-align: center;
        border: 1px solid #2d3250;
    }
    .metric-value {
        font-size: 2.5rem;
        font-weight: bold;
        color: #00d4ff;
    }
    .metric-label {
        font-size: 0.9rem;
        color: #8b8fa3;
        margin-top: 5px;
    }
    .status-active {
        color: #00e676;
        font-weight: bold;
    }
    .status-inactive {
        color: #ff5252;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# === DB初期化 ===
user_manager.init_db()


# === 認証 ===

def show_login():
    """管理者ログインフォームを表示"""
    st.markdown("## 🔐 管理パネル ログイン")
    st.markdown("---")

    with st.form("admin_login_form"):
        username = st.text_input("ユーザー名")
        password = st.text_input("パスワード", type="password")
        submitted = st.form_submit_button("ログイン", use_container_width=True)

    if submitted:
        if not username or not password:
            st.error("ユーザー名とパスワードを入力してください。")
            return

        user = user_manager.authenticate(username, password)
        if user is None:
            st.error("認証に失敗しました。ユーザー名またはパスワードが正しくありません。")
            return

        if not user.get("is_admin"):
            st.error("管理者権限がありません。")
            return

        st.session_state["admin_user"] = user
        st.rerun()


def show_admin_panel():
    """管理パネルのメインコンテンツを表示"""
    admin = st.session_state["admin_user"]

    # ヘッダー
    col_title, col_logout = st.columns([8, 2])
    with col_title:
        st.markdown("# 🔧 管理パネル")
    with col_logout:
        st.markdown(f"👤 **{admin.get('display_name') or admin['username']}**")
        if st.button("ログアウト", use_container_width=True):
            del st.session_state["admin_user"]
            st.rerun()

    st.markdown("---")

    # === ダッシュボード概要 ===
    show_dashboard()

    st.markdown("---")

    # === ユーザー一覧テーブル ===
    show_user_table()

    st.markdown("---")

    # === ユーザー操作 ===
    show_user_operations()


def show_dashboard():
    """ダッシュボード概要を表示"""
    st.markdown("## 📊 ダッシュボード")

    stats = user_manager.count_users()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(label="📋 総ユーザー数", value=stats["total"])

    with col2:
        st.metric(label="✅ アクティブユーザー数", value=stats["active"])

    with col3:
        plan_parts = []
        for plan_key, plan_info in user_manager.PLANS.items():
            count = stats["by_plan"].get(plan_key, 0)
            plan_parts.append(f"{plan_info['name']}: {count}")
        st.markdown("**📦 プラン別内訳**")
        for part in plan_parts:
            st.markdown(f"- {part}")


def show_user_table():
    """ユーザー一覧テーブルを表示"""
    st.markdown("## 👥 ユーザー一覧")

    users = user_manager.get_all_users()

    if not users:
        st.info("ユーザーが登録されていません。")
        return

    # DataFrameを構築
    rows = []
    for u in users:
        status = "🟢 有効" if u["is_active"] else "🔴 無効"
        admin_badge = " 👑" if u["is_admin"] else ""
        expires = u.get("expires_at") or "無期限"
        last_login = u.get("last_login") or "未ログイン"

        # 日付を見やすく整形
        if expires != "無期限":
            try:
                dt = datetime.fromisoformat(expires)
                expires = dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass
        if last_login != "未ログイン":
            try:
                dt = datetime.fromisoformat(last_login)
                last_login = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                pass

        rows.append({
            "ユーザー名": u["username"] + admin_badge,
            "表示名": u.get("display_name") or "-",
            "プラン": u.get("plan_name", u.get("plan", "-")),
            "アカウント上限": u.get("max_accounts", "-"),
            "ステータス": status,
            "有効期限": expires,
            "最終ログイン": last_login,
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


def show_user_operations():
    """ユーザー操作タブを表示"""
    st.markdown("## ⚙️ ユーザー操作")

    tab_add, tab_edit, tab_delete = st.tabs([
        "➕ ユーザー追加",
        "✏️ ユーザー編集",
        "🗑️ ユーザー削除",
    ])

    with tab_add:
        show_add_user()

    with tab_edit:
        show_edit_user()

    with tab_delete:
        show_delete_user()


def show_add_user():
    """ユーザー追加フォーム"""
    st.markdown("### ユーザー追加")

    with st.form("add_user_form"):
        col1, col2 = st.columns(2)
        with col1:
            new_username = st.text_input("ユーザー名 *", key="add_username")
            new_password = st.text_input("パスワード *", type="password", key="add_password")
            new_display_name = st.text_input("表示名", key="add_display_name")
        with col2:
            new_email = st.text_input("メールアドレス", key="add_email")
            plan_options = {
                v["name"]: k for k, v in user_manager.PLANS.items()
            }
            selected_plan_name = st.selectbox(
                "プラン",
                options=list(plan_options.keys()),
                key="add_plan",
            )
            use_expiry = st.checkbox("有効期限を設定する", key="add_use_expiry")

        if use_expiry:
            expires_date = st.date_input(
                "有効期限",
                value=date.today() + timedelta(days=30),
                key="add_expires",
            )
        else:
            expires_date = None

        submitted = st.form_submit_button("✅ ユーザーを作成", use_container_width=True)

    if submitted:
        if not new_username or not new_password:
            st.error("ユーザー名とパスワードは必須です。")
            return

        plan_key = plan_options[selected_plan_name]
        expires_at = expires_date.isoformat() if expires_date else None

        result = user_manager.create_user(
            username=new_username,
            password=new_password,
            plan=plan_key,
            expires_at=expires_at,
            display_name=new_display_name,
            email=new_email,
        )

        if result:
            st.success(
                f"ユーザー「{new_username}」を作成しました。"
                f"（プラン: {selected_plan_name}）"
            )
            st.rerun()
        else:
            st.error(f"ユーザー名「{new_username}」は既に使用されています。")


def show_edit_user():
    """ユーザー編集フォーム"""
    st.markdown("### ユーザー編集")

    users = user_manager.get_all_users()
    if not users:
        st.info("編集可能なユーザーがいません。")
        return

    user_options = {
        f"{u['username']}（{u.get('plan_name', u['plan'])}）": u["id"]
        for u in users
    }
    selected_label = st.selectbox(
        "編集するユーザーを選択",
        options=list(user_options.keys()),
        key="edit_user_select",
    )

    if not selected_label:
        return

    user_id = user_options[selected_label]
    user = user_manager.get_user(user_id)

    if not user:
        st.error("ユーザーが見つかりません。")
        return

    st.markdown(f"**現在の情報:** ユーザー名={user['username']}　"
                f"プラン={user.get('plan_name', user['plan'])}　"
                f"ステータス={'有効' if user['is_active'] else '無効'}　"
                f"有効期限={user.get('expires_at') or '無期限'}")

    with st.form("edit_user_form"):
        col1, col2 = st.columns(2)

        with col1:
            # 表示名変更
            edit_display_name = st.text_input(
                "表示名",
                value=user.get("display_name") or "",
                key="edit_display_name",
            )

            # プラン変更
            plan_options = {
                v["name"]: k for k, v in user_manager.PLANS.items()
            }
            current_plan_name = user_manager.PLANS.get(
                user["plan"], user_manager.PLANS["lite"]
            )["name"]
            plan_names = list(plan_options.keys())
            current_index = (
                plan_names.index(current_plan_name)
                if current_plan_name in plan_names
                else 0
            )
            selected_plan_name = st.selectbox(
                "プラン",
                options=plan_names,
                index=current_index,
                key="edit_plan",
            )

        with col2:
            # 有効/無効切り替え
            is_active = st.checkbox(
                "有効（チェックを外すと無効化）",
                value=user["is_active"],
                key="edit_is_active",
            )

            # 有効期限変更
            use_expiry = st.checkbox(
                "有効期限を設定する",
                value=user.get("expires_at") is not None,
                key="edit_use_expiry",
            )

        if use_expiry:
            default_date = date.today() + timedelta(days=30)
            if user.get("expires_at"):
                try:
                    dt = datetime.fromisoformat(user["expires_at"])
                    default_date = dt.date()
                except (ValueError, TypeError):
                    pass
            expires_date = st.date_input(
                "有効期限",
                value=default_date,
                key="edit_expires",
            )
        else:
            expires_date = None

        # パスワードリセット
        st.markdown("---")
        new_password = st.text_input(
            "新しいパスワード（空欄なら変更しない）",
            type="password",
            key="edit_password",
        )

        submitted = st.form_submit_button("💾 変更を保存", use_container_width=True)

    if submitted:
        plan_key = plan_options[selected_plan_name]
        expires_at = expires_date.isoformat() if expires_date else None

        # プラン・有効期限を更新
        user_manager.update_user_plan(user_id, plan_key, expires_at)

        # 表示名・有効/無効を更新
        user_manager.update_user(
            user_id,
            display_name=edit_display_name,
            is_active=1 if is_active else 0,
        )

        # パスワードリセット
        if new_password:
            user_manager.change_password(user_id, new_password)

        st.success(f"ユーザー「{user['username']}」の情報を更新しました。")
        st.rerun()


def show_delete_user():
    """ユーザー削除フォーム"""
    st.markdown("### ユーザー削除")

    users = user_manager.get_all_users()
    if not users:
        st.info("削除可能なユーザーがいません。")
        return

    user_options = {
        f"{u['username']}（{u.get('plan_name', u['plan'])}）": u["id"]
        for u in users
    }
    selected_label = st.selectbox(
        "削除するユーザーを選択",
        options=list(user_options.keys()),
        key="delete_user_select",
    )

    if not selected_label:
        return

    user_id = user_options[selected_label]
    user = user_manager.get_user(user_id)

    if not user:
        st.error("ユーザーが見つかりません。")
        return

    st.warning(
        f"⚠️ ユーザー「{user['username']}」"
        f"（プラン: {user.get('plan_name', user['plan'])}）を削除しようとしています。"
    )

    confirm = st.checkbox(
        "本当に削除しますか？",
        key="delete_confirm",
    )
    delete_data = st.checkbox(
        "ユーザーデータディレクトリも削除する",
        key="delete_data",
    )

    if st.button("🗑️ ユーザーを削除", use_container_width=True, type="primary"):
        if not confirm:
            st.error("確認チェックボックスにチェックを入れてください。")
            return

        username = user["username"]

        # データディレクトリの削除
        if delete_data:
            try:
                data_dir = user_manager.get_user_data_dir(user_id)
                if data_dir:
                    shutil.rmtree(data_dir, ignore_errors=True)
            except Exception as e:
                st.warning(f"データディレクトリの削除中にエラーが発生しました: {e}")

        # ユーザー削除
        user_manager.delete_user(user_id)
        st.success(f"ユーザー「{username}」を削除しました。")
        st.rerun()


# === メインルーティング ===

def main():
    if "admin_user" not in st.session_state:
        show_login()
    else:
        show_admin_panel()


if __name__ == "__main__":
    main()
