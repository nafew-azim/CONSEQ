#!/usr/bin/env bash
# Drain a batch file of "model|tag|dataset|lang" specs, one per free GPU slot.
# Writes progress to batch.log immediately (unbuffered) so it can be polled.
set -uo pipefail
export PATH="/Library/Frameworks/Python.framework/Versions/3.13/bin:$PATH"
cd "$(dirname "$0")"
LOG=batch.log
: > "$LOG"
# No pre-flight slot check: `kaggle kernels list` returns empty under rate limiting, which
# reads as "0 running" and makes every slot look free. The push itself is the authoritative
# test -- it fails loudly on the 2-session cap, so just retry with backoff.
while read -r spec; do
  [ -z "$spec" ] && continue
  IFS='|' read -r model tag ds lang cf <<< "$spec"; cf="${cf:-top2}"
  placed=0
  for try in $(seq 1 40); do
    for acct in a b; do
      case "$ds" in mbpp-*) N=400 ;; *) N=161 ;; esac
      if ./push.sh "$acct" "$N" "$model" a "$tag" "$ds" "$lang" "$cf" >/tmp/p.log 2>&1; then
        echo "$(date +%H:%M) OK   $tag -> $acct" >> "$LOG"
        placed=1; break
      fi
    done
    [ $placed -eq 1 ] && break
    sleep 120
  done
  [ $placed -eq 0 ] && echo "$(date +%H:%M) GAVE UP $tag" >> "$LOG"
done < "$1"
echo "$(date +%H:%M) batch drained" >> "$LOG"
