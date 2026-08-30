#!/usr/bin/env bash
# Wait for the Python repairability run to finish, then launch TypeScript on that slot.
set -uo pipefail
export PATH="/Library/Frameworks/Python.framework/Versions/3.13/bin:$PATH"
cd "$(dirname "$0")"
while :; do
  ./kacct.sh a >/dev/null 2>&1
  st=$(kaggle kernels status nafewazim/conseq-phase-b-bpy 2>&1 | grep -oE 'KernelWorkerStatus\.[A-Z]+')
  case "$st" in *COMPLETE|*ERROR|*CANCEL) echo "bpy -> ${st##*.}"; break ;; esac
  sleep 60
done
./push.sh a 161 Qwen/Qwen2.5-Coder-1.5B a ts humaneval-ts ts 2>&1 | tail -1
