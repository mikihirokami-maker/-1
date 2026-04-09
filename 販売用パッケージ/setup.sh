#!/bin/bash
# ========================================
# Threads Auto Master Pro - セットアップ
# ========================================

echo "=== Threads Auto Master Pro セットアップ ==="

# 必要パッケージインストール
apt update && apt install -y python3 python3-pip nginx

# Pythonライブラリ
pip3 install streamlit requests Pillow playwright

# Playwright ブラウザインストール
playwright install chromium
playwright install-deps chromium

# 画像配信用ディレクトリ
mkdir -p /root/images

# Nginx設定（画像配信用）
cat > /etc/nginx/sites-available/images << 'NGINX'
server {
    listen 80;
    server_name _;

    location /images/ {
        alias /root/images/;
        autoindex off;
    }

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/images /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

# Streamlit設定
mkdir -p /root/.streamlit
cat > /root/.streamlit/config.toml << 'TOML'
[server]
headless = true
address = "0.0.0.0"
port = 8501

[theme]
base = "dark"
TOML

echo ""
echo "=== セットアップ完了 ==="
echo ""
echo "次のステップ:"
echo "1. my_bot.py の IMAGE_BASE_URL を http://YOUR_SERVER_IP に変更"
echo "2. worker.py の IMAGE_BASE_URL も同様に変更"
echo "3. プロキシを使う場合は PROXY_HOST/PORT/USER/PASS を設定"
echo ""
echo "起動方法:"
echo "  streamlit run my_bot.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true &"
echo "  python3 -u worker.py &"
echo ""
echo "ブラウザから http://YOUR_SERVER_IP でアクセスできます"
