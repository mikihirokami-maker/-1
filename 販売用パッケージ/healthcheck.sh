#!/bin/bash
# Discord Webhook URL for notifications (set your webhook URL here)
DISCORD_WEBHOOK=""

# Check if worker is running
if ! systemctl is-active --quiet threads-worker; then
    if [ -n "$DISCORD_WEBHOOK" ]; then
        curl -s -H "Content-Type: application/json" \
            -d "{\"content\":\"🚨 **Worker停止検知！** threads-workerが停止しています。自動再起動を試みます...\"}" \
            "$DISCORD_WEBHOOK"
    fi
    systemctl restart threads-worker
    sleep 5
    if systemctl is-active --quiet threads-worker; then
        if [ -n "$DISCORD_WEBHOOK" ]; then
            curl -s -H "Content-Type: application/json" \
                -d "{\"content\":\"✅ Worker自動再起動成功\"}" \
                "$DISCORD_WEBHOOK"
        fi
    else
        if [ -n "$DISCORD_WEBHOOK" ]; then
            curl -s -H "Content-Type: application/json" \
                -d "{\"content\":\"❌ Worker再起動失敗！手動で確認してください\"}" \
                "$DISCORD_WEBHOOK"
        fi
    fi
fi
