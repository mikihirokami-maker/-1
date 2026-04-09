#!/bin/bash
# Threads Auto Master - Server Setup Script
# This script sets up systemd services for permanent operation

echo "=== Threads Auto Master Setup ==="

# Stop existing processes
echo "Stopping existing processes..."
pkill -f "streamlit run" 2>/dev/null
pkill -f "python3 /root/worker.py" 2>/dev/null
pkill -f "python3 worker.py" 2>/dev/null
sleep 2

# Create systemd service for Streamlit web app
echo "Creating web service..."
cat > /etc/systemd/system/threads-web.service << 'SVCEOF'
[Unit]
Description=Threads Auto Master Web
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root
ExecStart=/usr/local/bin/streamlit run /root/my_bot.py --server.port=80 --server.address=0.0.0.0 --server.headless=true
Restart=always
RestartSec=10
Environment=PYTHONIOENCODING=utf-8

[Install]
WantedBy=multi-user.target
SVCEOF

# Create systemd service for worker
echo "Creating worker service..."
cat > /etc/systemd/system/threads-worker.service << 'SVCEOF'
[Unit]
Description=Threads Auto Master Worker
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root
ExecStart=/usr/bin/python3 /root/worker.py
Restart=always
RestartSec=10
Environment=PYTHONIOENCODING=utf-8

[Install]
WantedBy=multi-user.target
SVCEOF

# Reload and enable services
echo "Enabling services..."
systemctl daemon-reload
systemctl enable threads-web threads-worker
systemctl restart threads-web threads-worker

sleep 3

# Check status
echo ""
echo "=== Status ==="
systemctl is-active threads-web && echo "Web: RUNNING" || echo "Web: STOPPED"
systemctl is-active threads-worker && echo "Worker: RUNNING" || echo "Worker: STOPPED"
echo ""
echo "Setup complete!"
echo "Web UI: http://$(curl -s ifconfig.me 2>/dev/null || echo '163.44.101.4')/"
echo ""
echo "Useful commands:"
echo "  systemctl status threads-web"
echo "  systemctl status threads-worker"
echo "  journalctl -u threads-web -f"
echo "  journalctl -u threads-worker -f"
