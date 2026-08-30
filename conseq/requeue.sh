#!/usr/bin/env bash
# Retry a push until a GPU slot frees (Kaggle caps 2 concurrent GPU sessions per account).
set -uo pipefail
export PATH="/Library/Frameworks/Python.framework/Versions/3.13/bin:$PATH"
cd "$(dirname "$0")"
for i in $(seq 1 60); do
  for acct in a b; do
    if ./push.sh "$acct" 161 "$1" a "$2" "$3" "$4" >/tmp/pq.log 2>&1; then
      echo "[$(date +%H:%M)] launched $1 on $acct"; tail -1 /tmp/pq.log; exit 0
    fi
  done
  sleep 90
done
echo "gave up on $1"; exit 1
