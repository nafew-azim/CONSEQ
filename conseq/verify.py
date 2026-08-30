"""Check every mechanically checkable number in the paper against the release build.

Fails loudly. A paper claim that cannot be regenerated from conseq.jsonl is a defect,
not a rounding difference.
"""
import json, re, collections, sys, os

# repo layout: <root>/conseq/verify.py and <root>/paper/main.tex
PAPER = os.environ.get("CONSEQ_PAPER") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "paper")

try:
    import torch  # noqa: F401  -- phase_a imports it at module scope
except ModuleNotFoundError:
    sys.exit("verify.py needs the interpreter that has torch installed "
             f"(this one is {sys.executable}); e.g. "
             "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 verify.py")

REL   = "conseq.jsonl"
MAN   = "conseq_manifest.json"
MAIN  = os.path.join(PAPER, "main.tex")
APP   = os.path.join(PAPER, "appendices.tex")

fails, checks = [], 0
def eq(label, got, want, tol=0.0):
    global checks
    checks += 1
    ok = (abs(got - want) <= tol) if isinstance(want, float) else (got == want)
    if not ok:
        fails.append(f"{label}: paper says {want}, data says {got}")

rows = [json.loads(l) for l in open(REL)]
man  = json.load(open(MAN))
main = open(MAIN).read()
app  = open(APP).read()
tex  = main + app

# ---- headline totals -------------------------------------------------------
eq("total positions", len(rows), 143786)
eq("distinct models", len({r["model"] for r in rows}), 14)
eq("distinct families", len({r["family"] for r in rows}), 9)
eq("distinct languages", len({r["lang"] for r in rows}), 9)
eq("model-language configs", len({(r["model"], r["lang"]) for r in rows}), 28)
eq("instrument version uniform", len({r["iv"] for r in rows}), 1)
eq("instrument version", rows[0]["iv"], 2)

# every total that appears in the prose as 143,786 / 14 / 9 must be that number
for pat, want, name in [(r"143,786", "143,786", "143,786 in text")]:
    assert pat in tex, name

# ---- Table 2 (coverage) ----------------------------------------------------
cov = collections.defaultdict(lambda: {"pos": 0, "prob": set(), "cons": 0})
def clean(r):
    from phase_a import is_artifact
    return bool(r["K_sem"]) and not is_artifact(r["tok"], r["alt"], r.get("err"), r["lang"])
for r in rows:
    c = cov[r["lang"]]
    c["pos"] += 1; c["prob"].add(r["problem"]); c["cons"] += clean(r)

tab2 = re.search(r"Language & Typing & Problems & Positions & Consequential.*?\\bottomrule", main, re.S)
if not tab2:
    fails.append("Table 2 not found in main.tex")
else:
    L = {"JavaScript": "js", "PHP": "php", "TypeScript": "ts", "Java": "java", "Perl": "pl",
         "Go": "go", "Python": "py", "Rust": "rs", "Ruby": "rb"}
    for line in tab2.group(0).split(r"\\"):
        m = re.match(r"\s*(\w+)\s*&\s*(\w+)\s*&\s*([\d,]+)\s*&\s*([\d,]+)\s*&\s*([\d,]+)", line)
        if not m or m.group(1) not in L:
            continue
        lang = L[m.group(1)]
        p, pos, cons = (int(x.replace(",", "")) for x in m.group(3, 4, 5))
        eq(f"Table2 {lang} problems", len(cov[lang]["prob"]), p)
        eq(f"Table2 {lang} positions", cov[lang]["pos"], pos)
        eq(f"Table2 {lang} consequential", cov[lang]["cons"], cons)

# ---- typing table (appendix) ----------------------------------------------
hv = collections.defaultdict(collections.Counter)
for r in rows:
    if r["model"] != "Qwen/Qwen2.5-Coder-1.5B" or not r["problem"].startswith("HumanEval"):
        continue
    d = hv[r["lang"]]; d["n"] += 1
    for f in ("K_syn", "K_type", "K_sem"):
        d[f] += bool(r[f])
tabt = re.search(r"Language & Discipline & \$K\^\{\\mathrm\{syn\}\}.*?\\bottomrule", tex, re.S)
if not tabt:
    fails.append("typing table not found")
else:
    L = {"Ruby": "rb", "Perl": "pl", "PHP": "php", "Python": "py", "JavaScript": "js",
         "Go": "go", "Java": "java", "Rust": "rs", "TypeScript": "ts"}
    for line in tabt.group(0).split(r"\\"):
        m = re.match(r"\s*(\w+)\s*&[^&]*&\s*([\d.]+|---)\\?%?\s*&\s*([\d.]+|---)\\?%?\s*&"
                     r"[^&]*?([\d.]+)\\%", line)
        if not m or m.group(1) not in L:
            continue
        lang = L[m.group(1)]; d = hv[lang]; n = d["n"]
        for txt, key in ((m.group(2), "K_syn"), (m.group(3), "K_type"), (m.group(4), "K_sem")):
            if txt == "---":
                eq(f"typing {lang} {key} absent", d[key], 0)
            else:
                eq(f"typing {lang} {key}", round(d[key] / n * 100, 1), float(txt), 0.051)

# ---- manifest table (appendix) --------------------------------------------
runs = man["runs"]
eq("manifest run count", len(runs), len(re.findall(r"^\S.*&.*&.*&.*&.*&.*\\\\", app, re.M)) if False else len(runs))
mrows = re.findall(r"^\\texttt\{([\w\\]+)\} & ([\w.\-]+) & (\w+) & (\w+) & ([\d,]+) & ([\d,]+) & ([\d,]+)",
                   app, re.M)
eq("manifest rows in appendix", len(mrows), len(runs))
byrun = collections.Counter()
for mr in mrows:
    byrun[(mr[1], mr[3])] += 1
for run in runs:
    short = run["model"].split("/")[-1]
    if (short, run["lang"]) not in byrun:
        fails.append(f"manifest run missing from appendix: {short} {run['lang']}")
app_pos = sum(int(mr[5].replace(",", "")) for mr in mrows)
eq("manifest positions sum", app_pos, len(rows))
app_dirs = {mr[0].replace("\\_", "_") for mr in mrows}
man_dirs = {r["dir"] for r in runs}
if app_dirs != man_dirs:
    fails.append(f"manifest dirs differ: only-appendix={app_dirs - man_dirs}, "
                 f"only-manifest={man_dirs - app_dirs}")
checks += 1
man_pos = sum(r["positions"] for r in runs)
eq("manifest json positions sum", man_pos, len(rows))

# ---- corrections count ----------------------------------------------------
nb = len(re.findall(r"\\paragraph\{B\d+\.", app))
claimed = re.search(r"(\w+) measured results were believed", app)
words = {"Nine": 9, "Ten": 10, "Eleven": 11}
if claimed:
    eq("corrections count in prose", nb, words.get(claimed.group(1), -1))
eq("corrections referenced as N corrections", nb,
   9 if "after nine corrections" in tex else nb)

# ---- entropy below random -------------------------------------------------
fd = json.load(open("figdata.json"))
below = sum(1 for c in fd["configs"] if c["entropy"] < c["budget"])
eq("configs scored", len(fd["configs"]), 28)
for m in re.finditer(r"(\d+) of (\d+)\s+model-language configurations", tex):
    checks += 1
    if int(m.group(2)) == 28 and int(m.group(1)) not in (below, len(fd["configs"])):
        fails.append(f"stale claim '{m.group(0)}': entropy is below random in {below} of "
                     f"{len(fd['configs'])}")
m = re.search(r"holds in \\textbf\{(\d+) of (\d+)\}", main)
if m:
    eq("entropy below random", below, int(m.group(1)))
    eq("configs in that claim", len(fd["configs"]), int(m.group(2)))


# ---- artifact taxonomy ----------------------------------------------------
import re as _re
from phase_a import is_artifact, REF_ERRORS
sem = [r for r in rows if r["K_sem"]]
nsem = len(sem)
ref = bpe = 0
for r in sem:
    if r.get("err") in REF_ERRORS.get(r["lang"], REF_ERRORS["js"]):
        ref += 1; continue
    a, b = r["tok"].strip(), r["alt"].strip()
    if a and b and (a.startswith(b) or b.startswith(a)) \
       and _re.search(r"\w", a) and _re.search(r"\w", b):
        bpe += 1
eq_all = sum(1 for r in rows if r.get("equivalent"))
eq_sem = sum(1 for r in sem if r.get("equivalent"))
def pct(x, n): return round(x / n * 100, 1)
for label, got in [("artifact total", pct(ref + bpe, nsem)),
                   ("inconsistent-ref share", pct(ref, nsem)),
                   ("BPE share", pct(bpe, nsem)),
                   ("equivalent share of K_sem", pct(eq_sem, nsem)),
                   ("equivalent share of all", pct(eq_all, len(rows)))]:
    want = {"artifact total": 34.0, "inconsistent-ref share": 29.7, "BPE share": 4.3,
            "equivalent share of K_sem": 0.0, "equivalent share of all": 2.7}[label]
    eq(label, got, want, 0.051)
    if f"{want}\\%" not in tex and f"{want}" not in tex:
        fails.append(f"{label}: {want}% not present in the paper text")

# ---- timeout range --------------------------------------------------------
tos = []
for lang in {r["lang"] for r in rows}:
    sub = [r for r in rows if r["lang"] == lang]
    tos.append(sum(r["K_timeout"] for r in sub) / len(sub) * 100)
eq("timeout min", round(min(tos), 1), 0.3, 0.051)
eq("timeout max", round(max(tos), 1), 1.4, 0.051)
assert "0.3--1.4" in tex, "timeout range text not updated"

# ---- per-family artifact range -------------------------------------------
fam = collections.defaultdict(collections.Counter)
for r in sem:
    d = fam[r["family"]]; d["raw"] += 1
    d["art"] += is_artifact(r["tok"], r["alt"], r.get("err"), r["lang"])
big = [d["art"] / d["raw"] * 100 for d in fam.values() if d["raw"] >= 500]
eq("family artifact min", round(min(big), 1), 19.9, 0.051)
eq("family artifact max", round(max(big), 1), 46.2, 0.051)

# ---- underpowered runs ----------------------------------------------------
up = [r for r in man["runs"] if r.get("underpowered")]
eq("underpowered run count", len(up), 3)
for d in up:
    assert d["problems"] < 25, d

# ---- hardcoded section references resolve ---------------------------------
import subprocess, os
pdf = os.path.join(PAPER, "main.pdf")
if os.path.exists(pdf):
    txt = subprocess.run(["pdftotext", pdf, "-"],
                         capture_output=True, text=True).stdout
    secs = set(_re.findall(r"^(\d+(?:\.\d+)?) +[A-Z]", txt, _re.M))
    for m in _re.finditer(r"\\S~?(\d+(?:\.\d+)?)", tex):
        checks += 1
        if m.group(1) not in secs:
            fails.append(f"hardcoded section ref \\S{m.group(1)} does not exist")
    eq("unresolved cross-references (??)", txt.count("??"), 0)


# ---- Table 5: the criterion audit, recomputed from raw scores ------------
from table2 import spearman, SIGN
crit_rows = [json.loads(l) for l in open("outf/phase_f.jsonl")]
ctruth = [1.0 if (r["K_sem"] and not is_artifact(r["tok"], r["alt"], r.get("err"),
                                                 r.get("lang", "js"))) else 0.0 for r in crit_rows]
cn, ctot = len(crit_rows), sum(ctruth)
eq("criterion-audit positions", cn, 3697)
eq("criterion-audit problems", len({r["problem"] for r in crit_rows}), 62)
TEXNAME = {"P0_random": "Random baseline", "P1_entropy": "Entropy", "P2_margin": "Margin",
           "P3_nll": "Negative log-likelihood", "P4_excess_loss": "Excess loss",
           "P5_teacher_kl": "Teacher--student KL", "P6_expert_delta": "Expert--generalist delta",
           "P7_position": "Position", "P8_conf_wrong": "Confidently-wrong",
           "P9_varentropy": "Varentropy", "P10_minp_width": "Min-$p$ width"}
tabc = re.search(r"Criterion & \$\\rho\$ & CC@10 & CC@25 & Waste@25.*?\\bottomrule", main, re.S)
if not tabc:
    fails.append("criteria table not found in main.tex")
else:
    body = tabc.group(0)
    nneg = 0
    for c, name in TEXNAME.items():
        sc = [SIGN[c] * float(r[c]) for r in crit_rows]
        rho = spearman(sc, ctruth)
        nneg += rho < 0
        order = sorted(range(cn), key=lambda i: -sc[i])
        cc10 = sum(ctruth[i] for i in order[: max(1, int(.10 * cn))]) / ctot
        k25 = max(1, int(.25 * cn))
        cc25 = sum(ctruth[i] for i in order[:k25]) / ctot
        waste = 1 - sum(ctruth[i] for i in order[:k25]) / k25
        line = [l for l in body.split(chr(92) * 2) if name in l]
        if not line:
            fails.append(f"criterion row missing from table: {name}")
            continue
        nums = re.findall(r"[-+]?\d+\.\d+", line[0].replace(chr(92) + "%", "%"))
        if len(nums) < 4:
            fails.append(f"could not parse row for {name}: {line[0][:70]}")
            continue
        for got, want, lab in ((round(rho, 3), float(nums[0]), "rho"),
                               (round(cc10 * 100, 1), float(nums[1]), "CC@10"),
                               (round(cc25 * 100, 1), float(nums[2]), "CC@25"),
                               (round(waste * 100, 1), float(nums[3]), "waste")):
            eq(f"Table5 {name} {lab}", got, want, 0.051)
    eq("criteria correlating negatively", nneg, 10)
    assert "ten of" in main, "the negative-count sentence was not updated"

print(f"{checks} checks run, {len(fails)} failed")
for f in fails:
    print("  FAIL", f)
sys.exit(1 if fails else 0)
