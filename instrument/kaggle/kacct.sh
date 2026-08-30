#!/usr/bin/env bash
# Switch Kaggle account. CLI 2.2.4 ignores KAGGLE_CONFIG_DIR, so we swap ~/.kaggle/access_token.
#   a = nafewazim   b = nafew01
set -euo pipefail
export PATH="/Library/Frameworks/Python.framework/Versions/3.13/bin:$PATH"
[ $# -eq 1 ] || { kaggle config view 2>&1 | grep -i '^- username'; exit 0; }
src=~/.kaggle-$1/access_token
[ -f "$src" ] || { echo "no such account: $1 (expected a|b)"; exit 1; }
cp "$src" ~/.kaggle/access_token && chmod 600 ~/.kaggle/access_token
kaggle config view 2>&1 | grep -i '^- username'
