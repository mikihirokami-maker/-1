#!/bin/bash
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"

# nginx check
if ! systemctl is-active --quiet nginx; then
    systemctl start nginx
    echo "$(date) nginx restarted" >> "$BASE_DIR/watchdog.log"
fi

# streamlit check
if ! pgrep -f "streamlit run $BASE_DIR/my_bot.py" > /dev/null; then
    nohup streamlit run "$BASE_DIR/my_bot.py" --server.port 8501 --server.address 0.0.0.0 --server.headless true > /dev/null 2>&1 &
    echo "$(date) streamlit restarted" >> "$BASE_DIR/watchdog.log"
fi

# worker check - start via script (bash flock prevents duplicates)
if ! pgrep -f 'python3.*worker\.py' > /dev/null; then
    nohup "$BASE_DIR/start_worker.sh" > /dev/null 2>&1 &
    echo "$(date) worker restarted" >> "$BASE_DIR/watchdog.log"
fi
