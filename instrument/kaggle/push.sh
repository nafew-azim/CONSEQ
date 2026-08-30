#!/usr/bin/env bash
# ./push.sh [a|b] [n_problems] [model]  -- assemble one self-contained kernel and push it.
set -euo pipefail
export PATH="/Library/Frameworks/Python.framework/Versions/3.13/bin:$PATH"
cd "$(dirname "$0")"
ACCT="${1:-a}"; N="${2:-50}"; MODEL="${3:-Qwen/Qwen2.5-Coder-1.5B}"
# ./push.sh <acct> <n> <model> <phase> <slug-tag> <multipl-e-config> <lang: js|py>
./kacct.sh "$ACCT" >/dev/null
USER=$(kaggle config view 2>&1 | awk '/^- username/{print $3}')
PHASE="${4:-a}"; TAG="${5:-}"; DS="${6:-humaneval-js}"; LANG="${7:-js}"; CF="${8:-top2}"; SLUG="conseq-phase-$PHASE${TAG:+-$TAG}"

{
  echo "# auto-assembled by push.sh -- edit execjs.py / phase_a.py, never this file"
  echo "import subprocess, shutil"
  echo 'if not shutil.which("node"): subprocess.run(["apt-get","-qq","install","-y","nodejs"], check=True)'
  case "$LANG" in
    rb)  echo 'if not shutil.which("ruby"):'
         echo '    subprocess.run(["apt-get","-qq","update"], check=False)'
         echo '    subprocess.run(["apt-get","-qq","install","-y","ruby"], check=True)' ;;
    php) echo 'if not shutil.which("php"):'
         echo '    subprocess.run(["apt-get","-qq","update"], check=False)'
         echo '    subprocess.run(["apt-get","-qq","install","-y","php-cli"], check=True)' ;;
    rs)  echo 'if not shutil.which("rustc"):'
         echo '    subprocess.run(["apt-get","-qq","update"], check=False)'
         echo '    subprocess.run(["apt-get","-qq","install","-y","rustc"], check=True)'
         echo 'print("rustc:", subprocess.run(["rustc","--version"],capture_output=True).stdout.decode().strip(), flush=True)' ;;
    pl)  echo 'if not shutil.which("perl"):'
         echo '    subprocess.run(["apt-get","-qq","update"], check=False)'
         echo '    subprocess.run(["apt-get","-qq","install","-y","perl"], check=True)'
         echo 'subprocess.run(["apt-get","-qq","update"], check=False)'
         echo 'subprocess.run(["apt-get","-qq","install","-y","libtest-deep-perl"], check=False)'
         echo '_td = subprocess.run(["perl","-MTest::Deep","-e1"], capture_output=True)'
         echo 'print("Test::Deep available:", _td.returncode == 0, _td.stderr.decode()[:200], flush=True)'
         echo 'if _td.returncode != 0:'
         echo '    subprocess.run(["cpanm","--notest","--quiet","Test::Deep"], check=False)'
         echo '    subprocess.run(["apt-get","-qq","install","-y","cpanminus"], check=False)'
         echo '    subprocess.run(["cpanm","--notest","--quiet","Test::Deep"], check=False)'
         echo '    _td = subprocess.run(["perl","-MTest::Deep","-e1"], capture_output=True)'
         echo '    print("Test::Deep after cpanm:", _td.returncode == 0, flush=True)' ;;
    lua) echo 'if not shutil.which("lua"):'
         echo '    subprocess.run(["apt-get","-qq","update"], check=False)'
         echo '    subprocess.run(["apt-get","-qq","install","-y","lua5.3"], check=True)' ;;
  esac
  if [ "$LANG" = java ]; then
    echo 'import os, urllib.request'
    echo 'if not shutil.which("javac"):'
    echo '    subprocess.run(["apt-get","-qq","update"], check=False)'
    echo '    subprocess.run(["apt-get","-qq","install","-y","default-jdk"], check=True)'
    echo '_jar = "/tmp/javatuples-1.2.jar"'
    echo 'if not os.path.exists(_jar):'
    echo '    urllib.request.urlretrieve("https://repo1.maven.org/maven2/org/javatuples/javatuples/1.2/javatuples-1.2.jar", _jar)'
    echo 'os.environ["JAVATUPLES_JAR"] = _jar'
    echo 'print("javac:", subprocess.run(["javac","-version"],capture_output=True).stdout.decode().strip() or subprocess.run(["javac","-version"],capture_output=True).stderr.decode().strip(), flush=True)'
  fi
  if [ "$LANG" = ts ]; then
    echo 'if not shutil.which("tsc"): subprocess.run(["npm","install","-g","--silent","typescript"], check=True)'
    echo 'print("tsc:", subprocess.run(["tsc","--version"],capture_output=True).stdout.decode().strip(), flush=True)'
  fi
  if [ "$LANG" = go ]; then
    echo 'import os'
    echo 'if not shutil.which("go"):'
    echo '    subprocess.run(["apt-get","-qq","update"], check=False)'
    echo '    subprocess.run(["apt-get","-qq","install","-y","golang-go"], check=True)'
    echo 'os.environ["GOCACHE"]="/tmp/gocache"; os.environ["GOPATH"]="/tmp/gopath"'
    echo 'os.makedirs("/tmp/gocache", exist_ok=True); os.makedirs("/tmp/gopath", exist_ok=True)'
    echo 'print("go:", subprocess.run(["go","version"],capture_output=True).stdout.decode().strip(), flush=True)'
  fi
  # no pip -U: image torch is CUDA-matched, upgrading it breaks the arch kernels
  echo "import torch"
  echo 'assert torch.cuda.is_available(), "no GPU in this session"'
  echo 'cap = torch.cuda.get_device_capability(); print("GPU:", torch.cuda.get_device_name(0), cap)'
  echo 'assert cap >= (7, 0), f"unsupported arch {cap} - rerun until Kaggle assigns a T4"'
  cat execjs.py
  sed -e '/^if __name__ ==/,$d' loader.py
  sed -e '/^from execjs import/d' -e '/^if __name__ ==/,$d' phase_a.py
  if [ "$PHASE" = b ]; then
    sed -e '/^from phase_a import/d' -e '/^from execjs import/d' -e '/^if __name__ ==/,$d' phase_b.py
  fi
  if [ "$PHASE" = g ]; then
    for f in roles.py phase_g.py; do
      sed -e '/^from phase_a import/d' -e '/^from execjs import/d' -e '/^from roles import/d' \
          -e '/^if __name__ ==/,$d' "$f"
    done
  fi
  if [ "$PHASE" = f ]; then
    for f in criteria.py phase_f.py; do
      sed -e '/^from phase_a import/d' -e '/^from execjs import/d' -e '/^from criteria import/d' \
          -e '/^if __name__ ==/,$d' "$f"
    done
  fi
  if [ "$PHASE" = e ]; then
    for f in roles.py phase_e.py; do
      sed -e '/^from phase_a import/d' -e '/^from execjs import/d' -e '/^from roles import/d' \
          -e '/^if __name__ ==/,$d' "$f"
    done
  fi
  if [ "$PHASE" = d ]; then
    for f in roles.py phase_d.py; do
      sed -e '/^from phase_a import/d' -e '/^from execjs import/d' -e '/^from roles import/d' \
          -e '/^if __name__ ==/,$d' "$f"
    done
  fi
  if [ "$PHASE" = c ]; then
    # one sed per file: with multiple inputs, '$' is the end of the LAST file, which
    # would delete phase_c.py entirely from roles.py's __main__ guard onward.
    for f in roles.py phase_c.py; do
      sed -e '/^from phase_a import/d' -e '/^from execjs import/d' -e '/^from roles import/d' \
          -e '/^if __name__ ==/,$d' "$f"
    done
  fi

  echo "selftest()"
  echo "tok = AutoTokenizer.from_pretrained('$MODEL')"
  # StableLM/Phi read config.pad_token_id inside __init__, so the config must be patched
  # BEFORE from_pretrained -- fixing it afterwards is too late, the load never completes.
  echo "from transformers import AutoConfig"
  echo "_cfg = AutoConfig.from_pretrained('$MODEL', trust_remote_code=True)"
  echo "if getattr(_cfg, 'pad_token_id', None) is None: _cfg.pad_token_id = tok.eos_token_id"
  echo "model = AutoModelForCausalLM.from_pretrained('$MODEL', config=_cfg, torch_dtype=torch.float16, trust_remote_code=True).to('cuda').eval()"
  echo "if tok.pad_token_id is None: tok.pad_token = tok.eos_token"
  echo "ds = load_problems('$DS', $N, '$LANG')"
  if [ "$PHASE" = b ]; then
    echo "phase_b(model, tok, ds, '/kaggle/working/phase_b.jsonl', lang='$LANG')"
  elif [ "$PHASE" = g ]; then
    echo "phase_g(model, tok, ds, '/kaggle/working/phase_g.jsonl', k=8, lang='$LANG')"
  elif [ "$PHASE" = f ]; then
    echo "phase_f('$MODEL', 'Qwen/Qwen2.5-0.5B', 'Qwen/Qwen2.5-Coder-3B', 'Qwen/Qwen2.5-1.5B', tok, ds, '/kaggle/working/phase_f.jsonl', lang='$LANG')"
  elif [ "$PHASE" = e ]; then
    echo "phase_e(model, tok, ds, '/kaggle/working/phase_e.jsonl')"
  elif [ "$PHASE" = d ]; then
    echo "phase_d(model, tok, ds, '/kaggle/working/phase_d.jsonl', n_samp=3, ent_thresh=0.4161)"
  elif [ "$PHASE" = c ]; then
    echo "phase_c(model, tok, ds, '/kaggle/working/phase_c.jsonl', n_samp=3, t_lo=0.0, t_hi=1.0, t_mid=0.579, ent_thresh=0.4161)"
  else
    echo "phase_a(model, tok, ds, '/kaggle/working/phase_a.jsonl', lang='$LANG', cf_mode='$CF')"
  fi
} > run.py

grep -q '\$[A-Z_]\{2,\}' run.py && { echo "BUG: unexpanded shell var in run.py"; grep -n '\$[A-Z_]\{2,\}' run.py; exit 1; }
python3 -m py_compile run.py || { echo "run.py does not compile"; exit 1; }
grep -q "^def phase_$PHASE" run.py || { echo "BUG: run.py has no phase_$PHASE definition"; exit 1; }

cat > kernel-metadata.json <<JSON
{ "id": "$USER/$SLUG", "title": "$SLUG", "code_file": "run.py", "language": "python",
  "kernel_type": "script", "is_private": true, "enable_internet": true, "enable_gpu": true,
  "dataset_sources": [], "competition_sources": [], "kernel_sources": [] }
JSON

# machine_shape must come from the flag; valid: NvidiaTeslaT4 | NvidiaTeslaP100 | Tpu1VmV38
# `kaggle kernels push` prints "Kernel push error: ..." but still EXITS 0 -- e.g. when the
# per-account cap of 2 concurrent GPU sessions is hit. Without this check a failed push looks
# like a successful launch.
out=$(kaggle kernels push -p . --accelerator NvidiaTeslaT4 2>&1)
echo "$out"
case "$out" in
  *"push error"*|*"Maximum batch"*) echo "PUSH FAILED for $SLUG"; exit 1 ;;
esac
echo "-> https://www.kaggle.com/code/$USER/$SLUG"
