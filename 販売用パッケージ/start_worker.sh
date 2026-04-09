#!/bin/bash
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCKFILE="$BASE_DIR/worker_bash.lock"
exec 200>$LOCKFILE
flock -n 200 || { echo "Worker already running"; exit 0; }
echo $$ >&200
exec python3 -u "$BASE_DIR/worker.py"
