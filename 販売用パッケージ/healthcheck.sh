#!/bin/bash
# Check if worker is running
if ! systemctl is-active --quiet threads-worker; then
    curl -s -H "Content-Type: application/json" \
        -d "{\"content\":\"🚨 **Worker停止検知！** threads-workerが停止しています。自動再起動を試みます...\"}" \
        "https://discord.com/api/webhooks/1481271128495493172/dwIcf2D5kRjkUGKuYXnS0a5XNkmY7nC31QT3LsjjQAbCRIQw_vUf2CFFhA4IdQ0KV3Hm"
    systemctl restart threads-worker
    sleep 5
    if systemctl is-active --quiet threads-worker; then
        curl -s -H "Content-Type: application/json" \
            -d "{\"content\":\"✅ Worker自動再起動成功\"}" \
            "https://discord.com/api/webhooks/1481271128495493172/dwIcf2D5kRjkUGKuYXnS0a5XNkmY7nC31QT3LsjjQAbCRIQw_vUf2CFFhA4IdQ0KV3Hm"
    else
        curl -s -H "Content-Type: application/json" \
            -d "{\"content\":\"❌ Worker再起動失敗！手動で確認してください\"}" \
            "https://discord.com/api/webhooks/1481271128495493172/dwIcf2D5kRjkUGKuYXnS0a5XNkmY7nC31QT3LsjjQAbCRIQw_vUf2CFFhA4IdQ0KV3Hm"
    fi
fi
