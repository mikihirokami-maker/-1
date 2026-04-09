#!/bin/bash
# nginx check
if ! systemctl is-active --quiet nginx; then
    systemctl start nginx
    echo "$(date) nginx restarted" >> /root/watchdog.log
fi

# streamlit check
if ! pgrep -f "streamlit run /root/my_bot.py" > /dev/null; then
    nohup streamlit run /root/my_bot.py --server.port 8501 --server.address 0.0.0.0 --server.headless true > /dev/null 2>&1 &
    echo "$(date) streamlit restarted" >> /root/watchdog.log
fi

# worker check - start via script (bash flock prevents duplicates)
if ! pgrep -f 'python3.*worker\.py' > /dev/null; then
    nohup /root/start_worker.sh > /dev/null 2>&1 &
    echo "$(date) worker restarted" >> /root/watchdog.log
fi
