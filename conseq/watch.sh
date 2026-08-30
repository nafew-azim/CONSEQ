#!/usr/bin/env bash
# Poll many kernels across BOTH accounts from ONE process, so the shared
# ~/.kaggle/access_token is never swapped underneath a concurrent query.
#   ./watch.sh a:nafewazim/conseq-phase-b b:nafew01/conseq-phase-a-xfam
# bash 3.2 compatible (macOS): no associative arrays.
set -uo pipefail
export PATH="/Library/Frameworks/Python.framework/Versions/3.13/bin:$PATH"
cd "$(dirname "$0")"
FIN=""
TRIES=0
while :; do
  TRIES=$((TRIES+1))
  [ $TRIES -gt 240 ] && { echo "watch.sh: giving up after ~3h"; break; }
  pending=0
  for spec in "$@"; do
    acct="${spec%%:*}"; kern="${spec#*:}"
    case " $FIN " in *" $kern "*) continue ;; esac
    ./kacct.sh "$acct" >/dev/null 2>&1
    raw=$(kaggle kernels status "$kern" 2>&1)
    st=$(echo "$raw" | grep -oE 'KernelWorkerStatus\.[A-Z]+' | head -1)
    case "$st" in
      *COMPLETE|*ERROR|*CANCEL) FIN="$FIN $kern"; echo "DONE $kern ${st##*.}" ;;
      "")  # no status at all: wrong account, wrong slug, or the kernel does not exist.
           # Without this the loop polls forever -- the exact hang seen on a mis-addressed kernel.
           echo "UNREACHABLE $kern -- $(echo "$raw" | head -1 | cut -c1-70)"
           FIN="$FIN $kern" ;;
      *) pending=1 ;;
    esac
  done
  [ $pending -eq 0 ] && break
  sleep 45
done
echo "--- all finished:$FIN"
