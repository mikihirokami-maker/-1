#!/bin/bash
# ========================================
# Threads Auto Master Pro - 統合インストーラー
# すべてのセットアップを1コマンドで完了
# ========================================
set -e

# --- 1. ベースディレクトリ自動検出 ---
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "============================================"
echo "  Threads Auto Master Pro - 統合インストーラー"
echo "============================================"
echo ""
echo "📁 インストールディレクトリ: $BASE_DIR"
echo ""

# --- 2. root権限チェック ---
if [ "$(id -u)" -ne 0 ]; then
    echo "❌ エラー: rootユーザーで実行してください"
    echo "   sudo bash $0"
    exit 1
fi
echo "✅ root権限確認OK"

# --- 3. パッケージインストール ---
echo ""
echo "📦 システムパッケージインストール中..."
apt update && apt install -y python3 python3-pip nginx cron
echo "✅ システムパッケージインストール完了"

# --- 4. Pythonライブラリインストール ---
echo ""
echo "🐍 Pythonライブラリインストール中..."
pip3 install streamlit requests Pillow
echo "✅ Pythonライブラリインストール完了"

# --- 5. サーバーIP自動検出 ---
echo ""
echo "🌐 サーバーIP検出中..."
SERVER_IP=$(curl -s --max-time 5 ifconfig.me 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "")
if [ -z "$SERVER_IP" ]; then
    echo "⚠️  IP自動検出に失敗しました。手動で入力してください:"
    read -r SERVER_IP
fi
echo "✅ サーバーIP: $SERVER_IP"

# --- 6. IMAGE_BASE_URL自動設定 ---
echo ""
echo "🔧 IMAGE_BASE_URL を自動設定中..."
# my_bot.py
sed -i "s|IMAGE_BASE_URL = \"http://YOUR_SERVER_IP/images\"|IMAGE_BASE_URL = \"http://${SERVER_IP}/images\"|g" "$BASE_DIR/my_bot.py" || true
# worker.py (IMAGE_BASE_URL and IMAGE_BASE_URL_HTTP)
sed -i "s|IMAGE_BASE_URL_HTTP = \"http://YOUR_SERVER_IP/images\"|IMAGE_BASE_URL_HTTP = \"http://${SERVER_IP}/images\"|g" "$BASE_DIR/worker.py" || true
sed -i "s|IMAGE_BASE_URL = \"http://YOUR_SERVER_IP/images\"|IMAGE_BASE_URL = \"http://${SERVER_IP}/images\"|g" "$BASE_DIR/worker.py" || true
echo "✅ IMAGE_BASE_URL → http://${SERVER_IP}/images に設定完了"

# --- 7. 画像ディレクトリ作成 ---
echo ""
echo "📂 画像ディレクトリ作成中..."
mkdir -p "$BASE_DIR/images"
echo "✅ $BASE_DIR/images 作成完了"

# --- 8. Nginx設定 ---
echo ""
echo "🌍 Nginx設定中..."
cat > /etc/nginx/sites-available/images << NGINX
server {
    listen 80;
    server_name _;

    location /images/ {
        alias $BASE_DIR/images/;
        autoindex off;
    }

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/images /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx
echo "✅ Nginx設定完了"

# --- 9. Streamlit設定 ---
echo ""
echo "⚙️  Streamlit設定中..."
mkdir -p ~/.streamlit
cat > ~/.streamlit/config.toml << 'TOML'
[server]
headless = true
address = "0.0.0.0"
port = 8501

[theme]
base = "dark"
TOML
echo "✅ Streamlit設定完了"

# --- 10. シェルスクリプトに実行権限付与 ---
echo ""
echo "🔑 実行権限設定中..."
find "$BASE_DIR" -name "*.sh" -exec chmod +x {} \;
echo "✅ .shファイルに実行権限付与完了"

# --- 11. systemdサービス作成 ---
echo ""
echo "🔧 systemdサービス作成中..."

# 既存プロセスの停止
pkill -f "streamlit run" 2>/dev/null || true
pkill -f "python3.*worker.py" 2>/dev/null || true
sleep 2

# threads-web サービス
cat > /etc/systemd/system/threads-web.service << SVCEOF
[Unit]
Description=Threads Auto Master Web
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$BASE_DIR
ExecStart=/usr/local/bin/streamlit run $BASE_DIR/my_bot.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true
Restart=always
RestartSec=10
Environment=PYTHONIOENCODING=utf-8

[Install]
WantedBy=multi-user.target
SVCEOF

# threads-worker サービス
cat > /etc/systemd/system/threads-worker.service << SVCEOF
[Unit]
Description=Threads Auto Master Worker
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$BASE_DIR
ExecStart=/usr/bin/python3 $BASE_DIR/worker.py
Restart=always
RestartSec=10
Environment=PYTHONIOENCODING=utf-8

[Install]
WantedBy=multi-user.target
SVCEOF

# threads-storage-watchdog サービス
cat > /etc/systemd/system/threads-storage-watchdog.service << SVCEOF
[Unit]
Description=Threads Auto Master Storage Watchdog
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$BASE_DIR
ExecStart=/usr/bin/python3 $BASE_DIR/storage_watchdog.py
Restart=always
RestartSec=10
Environment=PYTHONIOENCODING=utf-8

[Install]
WantedBy=multi-user.target
SVCEOF

echo "✅ systemdサービス作成完了"

# --- 12. Cron設定 ---
echo ""
echo "⏰ Cron設定中..."
( crontab -l 2>/dev/null | grep -v 'watchdog.sh' | grep -v 'midnight_cleanup.py' ; \
  echo "* * * * * $BASE_DIR/watchdog.sh" ; \
  echo "0 0 * * * /usr/bin/python3 $BASE_DIR/midnight_cleanup.py" \
) | crontab -
echo "✅ Cron設定完了"

# --- 13. サービス起動 ---
echo ""
echo "🚀 サービス起動中..."
systemctl daemon-reload
systemctl enable threads-web threads-worker threads-storage-watchdog
systemctl restart threads-web threads-worker threads-storage-watchdog
sleep 3
echo "✅ サービス起動完了"

# --- 14. ステータス確認 ---
echo ""
echo "============================================"
echo "  📊 サービスステータス"
echo "============================================"

ALL_OK=true

check_service() {
    local name=$1
    local label=$2
    if systemctl is-active --quiet "$name" 2>/dev/null; then
        echo "  ✅ $label: 稼働中"
    else
        echo "  ❌ $label: 停止中"
        ALL_OK=false
    fi
}

check_service "threads-web" "Web UI"
check_service "threads-worker" "Worker"
check_service "threads-storage-watchdog" "Storage Watchdog"
check_service "nginx" "Nginx"

echo ""
echo "  ⏰ Cron設定:"
crontab -l 2>/dev/null | grep -E 'watchdog|midnight_cleanup' | while read -r line; do
    echo "     $line"
done

echo ""
echo "============================================"
if [ "$ALL_OK" = true ]; then
    echo "  🎉 インストール完了！すべて正常に稼働中です"
else
    echo "  ⚠️  一部サービスが停止しています"
    echo "  ログ確認: journalctl -u サービス名 -f"
fi
echo "============================================"
echo ""
echo "  🌐 アクセスURL: http://${SERVER_IP}"
echo ""
echo "  便利なコマンド:"
echo "    systemctl status threads-web"
echo "    systemctl status threads-worker"
echo "    systemctl status threads-storage-watchdog"
echo "    journalctl -u threads-web -f"
echo "    journalctl -u threads-worker -f"
echo "============================================"
echo ""
