#!/bin/bash
# Threads Auto Master - Server Setup Script
# This script sets up systemd services for permanent operation

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Threads Auto Master Setup ==="
echo "Install directory: $BASE_DIR"

# Stop existing processes
echo "Stopping existing processes..."
pkill -f "streamlit run" 2>/dev/null
pkill -f "python3.*worker.py" 2>/dev/null
sleep 2

# Create systemd service for Streamlit web app
echo "Creating web service..."
cat > /etc/systemd/system/threads-web.service << SVCEOF
[Unit]
Description=Threads Auto Master Web
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$BASE_DIR
ExecStart=/usr/local/bin/streamlit run $BASE_DIR/my_bot.py --server.port=80 --server.address=0.0.0.0 --server.headless=true
Restart=always
RestartSec=10
Environment=PYTHONIOENCODING=utf-8

[Install]
WantedBy=multi-user.target
SVCEOF

# Create systemd service for worker
echo "Creating worker service..."
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

# Create systemd service for storage watchdog
echo "Creating storage watchdog service..."
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

# Reload and enable services
echo "Enabling services..."
systemctl daemon-reload
systemctl enable threads-web threads-worker threads-storage-watchdog
systemctl restart threads-web threads-worker threads-storage-watchdog

sleep 3

# Setup cron jobs
echo "Setting up cron jobs..."
# Remove old entries if they exist, then add new ones
( crontab -l 2>/dev/null | grep -v 'watchdog.sh' | grep -v 'midnight_cleanup.py' ; \
  echo "* * * * * $BASE_DIR/watchdog.sh" ; \
  echo "0 0 * * * /usr/bin/python3 $BASE_DIR/midnight_cleanup.py" \
) | crontab -

# Check status
echo ""
echo "=== Status ==="
systemctl is-active threads-web && echo "Web: RUNNING" || echo "Web: STOPPED"
systemctl is-active threads-worker && echo "Worker: RUNNING" || echo "Worker: STOPPED"
systemctl is-active threads-storage-watchdog && echo "Storage Watchdog: RUNNING" || echo "Storage Watchdog: STOPPED"
echo ""
echo "Cron jobs:"
crontab -l 2>/dev/null | grep -E 'watchdog|midnight_cleanup'
echo ""
echo "Setup complete!"
echo "Web UI: http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_SERVER_IP')/"
echo ""
echo "Useful commands:"
echo "  systemctl status threads-web"
echo "  systemctl status threads-worker"
echo "  systemctl status threads-storage-watchdog"
echo "  journalctl -u threads-web -f"
echo "  journalctl -u threads-worker -f"
echo "  journalctl -u threads-storage-watchdog -f"
