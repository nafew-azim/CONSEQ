#!/usr/bin/env bash
# Launch a list of Phase-A runs, one per free account slot, waiting when both are busy.
#   ./queue.sh "model|tag|dataset|lang" "model|tag|dataset|lang" ...
set -uo pipefail
export PATH="/Library/Frameworks/Python.framework/Versions/3.13/bin:$PATH"
cd "$(dirname "$0")"

busy() {   # busy <acct> <user>
  ./kacct.sh "$1" >/dev/null 2>&1
  for k in $(kaggle kernels list --mine -s conseq-phase-a 2>/dev/null | awk 'NR>2{print $1}'); do
    st=$(kaggle kernels status "$k" 2>&1 | grep -oE 'KernelWorkerStatus\.[A-Z]+')
    case "$st" in *RUNNING|*QUEUED) return 0 ;; esac
  done
  return 1
}

for spec in "$@"; do
  IFS='|' read -r model tag ds lang <<< "$spec"
  placed=0; waited=0
  while [ $placed -eq 0 ]; do
    if [ $waited -gt 180 ]; then echo "  !! no free slot after ~3h for $model -- skipping"; break; fi
    for acct in a b; do
      if ! busy "$acct"; then
        echo "[$(date +%H:%M)] $acct <- $model ($tag)"
        if ./push.sh "$acct" 161 "$model" a "$tag" "$ds" "$lang" 2>&1 | tail -1; then
          placed=1
        else
          echo "  !! push failed for $model -- skipping"
          placed=1
        fi
        break
      fi
    done
    [ $placed -eq 0 ] && { waited=$((waited+1)); sleep 60; }
  done
done
echo "all queued"
