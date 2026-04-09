#!/bin/bash
LOCKFILE=/root/worker_bash.lock
exec 200>$LOCKFILE
flock -n 200 || { echo "Worker already running"; exit 0; }
echo $$ >&200
exec python3 -u /root/worker.py
