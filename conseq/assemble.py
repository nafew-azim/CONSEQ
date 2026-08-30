"""Assemble CONSEQ from per-run outputs into one validated release.

The corpus was collected incrementally across instrument versions, tokenizers and language
taxonomies, so assembly is not concatenation -- it must refuse to merge rows whose columns do
not mean the same thing. Specifically:

  * `K_sem` changed meaning at instrument v2 (timeouts excluded -- see B9). v1 rows are NOT
    comparable and are quarantined, not silently pooled.
  * `K_type` exists only for languages with a separate static type-check phase (ts/go/java).
  * artifact classification is language- AND tokenizer-specific (F7, F16).

Emits: conseq.jsonl (release), conseq_manifest.json (provenance), and a coverage report.
"""
import json, glob, os, sys, hashlib
from collections import defaultdict

MIN_IV = 2          # instrument version required for release
UNDERPOWERED = 25   # problems below this are flagged, not dropped

# run directory -> (model, family, params)
PROVENANCE = {
    "out": ("Qwen/Qwen2.5-Coder-1.5B", "Qwen", "1.5B"),
    "out05": ("Qwen/Qwen2.5-Coder-0.5B", "Qwen", "0.5B"),
    "out3b": ("Qwen/Qwen2.5-Coder-3B", "Qwen", "3B"),
    "outnc": ("Qwen/Qwen2.5-1.5B", "Qwen", "1.5B"),
    "outx": ("deepseek-ai/deepseek-coder-1.3b-base", "DeepSeek", "1.3B"),
    "outsc": ("bigcode/starcoder2-3b", "BigCode", "3B"),
    "o_gr": ("ibm-granite/granite-3b-code-base", "IBM", "3B"),
    "o_g33": ("ibm-granite/granite-3.3-2b-base", "IBM", "2B"),
    "o_stable": ("stabilityai/stable-code-3b", "Stability", "3B"),
    "o_codegen": ("Salesforce/codegen-2B-mono", "Salesforce", "2B"),
    "o_phi2": ("microsoft/phi-2", "Microsoft", "2.7B"),
    "o_incoder": ("facebook/incoder-1B", "Meta", "1B"),
    "o_qwen3": ("Qwen/Qwen3-1.7B", "Qwen", "1.7B"),
    "o_smol": ("HuggingFaceTB/SmolLM2-1.7B", "HuggingFace", "1.7B"),
}
# v2 re-runs and later additions. A missing entry silently defaults to Qwen and corrupts the
# family count, so every run directory must be listed explicitly.
PROVENANCE.update({
    "o_v2js": ("Qwen/Qwen2.5-Coder-1.5B", "Qwen", "1.5B"),
    "o_v205": ("Qwen/Qwen2.5-Coder-0.5B", "Qwen", "0.5B"),
    "o_v23b": ("Qwen/Qwen2.5-Coder-3B", "Qwen", "3B"),
    "o_v2nc": ("Qwen/Qwen2.5-1.5B", "Qwen", "1.5B"),
    "o_v2ds": ("deepseek-ai/deepseek-coder-1.3b-base", "DeepSeek", "1.3B"),
    "o_v2dspy": ("deepseek-ai/deepseek-coder-1.3b-base", "DeepSeek", "1.3B"),
    "o_v2sc": ("bigcode/starcoder2-3b", "BigCode", "3B"),
    "o_scgo": ("bigcode/starcoder2-3b", "BigCode", "3B"),
    "o_scjava": ("bigcode/starcoder2-3b", "BigCode", "3B"),
    "o_scts": ("bigcode/starcoder2-3b", "BigCode", "3B"),
})
PROVENANCE["outdt"] = ("deepseek-ai/deepseek-coder-1.3b-base", "DeepSeek", "1.3B")
PROVENANCE["o_mpl"] = ("Qwen/Qwen2.5-Coder-1.5B", "Qwen", "1.5B")
PROVENANCE["o_scts"] = ("bigcode/starcoder2-3b", "BigCode", "3B")
PROVENANCE["o_rust"] = ("Qwen/Qwen2.5-Coder-1.5B", "Qwen", "1.5B")
PROVENANCE["o_scrust"] = ("bigcode/starcoder2-3b", "BigCode", "3B")
PROVENANCE["o_mphp"] = ("Qwen/Qwen2.5-Coder-1.5B", "Qwen", "1.5B")
PROVENANCE["o_rb"] = ("Qwen/Qwen2.5-Coder-1.5B", "Qwen", "1.5B")
PROVENANCE["o_php"] = ("Qwen/Qwen2.5-Coder-1.5B", "Qwen", "1.5B")
PROVENANCE["o_perl"] = ("Qwen/Qwen2.5-Coder-1.5B", "Qwen", "1.5B")
for _d in ("o_v2mbpp", "o_v2py", "o_v2ts", "o_v2go", "o_v2java",
           "o_mgo", "o_mrb", "o_mts", "o_mjava", "o_mphp", "o_mpl"):
    PROVENANCE[_d] = ("Qwen/Qwen2.5-Coder-1.5B", "Qwen", "1.5B")

# v1 directory -> the v2 run that replaces it. Superseded runs are excluded from the release
# and must NOT be reported as "needs re-run".
SUPERSEDED = {"out": "o_v2js", "out05": "o_v205", "out3b": "o_v23b", "outnc": "o_v2nc",
              "outx": "o_v2ds", "outsc": "o_v2sc", "outm": "o_v2mbpp", "outpy": "o_v2py",
              "outds": "o_v2dspy", "outts": "o_v2ts", "outgo": "o_v2go", "outjv": "o_v2java"}

DEFAULT = ("Qwen/Qwen2.5-Coder-1.5B", "Qwen", "1.5B")
TYPING = {"rs": "static", "js": "dynamic", "py": "dynamic", "rb": "dynamic", "php": "dynamic",
          "pl": "dynamic", "ts": "gradual", "go": "static", "java": "static"}
KEEP = ["problem", "pos", "n_pos", "tok", "alt", "err", "verdict", "entropy", "margin",
        "suffix_len", "equivalent", "K_syn", "K_sem", "K_type", "K_timeout", "lang", "iv"]


def load_runs():
    runs = []
    for f in sorted(glob.glob("out*/phase_a.jsonl") + glob.glob("o_*/phase_a.jsonl")):
        d = os.path.dirname(f)
        try:
            rows = [json.loads(l) for l in open(f)]
        except Exception as e:
            print(f"  !! {d}: unreadable ({e})"); continue
        if rows:
            runs.append((d, rows))
    return runs


def main(out="conseq.jsonl"):
    sys.path.insert(0, ".")
    from phase_a import is_artifact
    runs = load_runs()
    released, quarantined = [], []
    manifest, cover = [], defaultdict(lambda: [0, set(), 0])

    dirs = {d for d, _ in runs}
    for d, rows in runs:
        if d in SUPERSEDED and SUPERSEDED[d] in dirs:
            continue                      # replaced by a v2 re-run; not part of the release
        h = rows[0]
        lang = h.get("lang", "js")
        iv = h.get("iv", 1)
        if d not in PROVENANCE:
            print(f"  !! {d}: no provenance entry -- defaulting to Qwen (FIX THIS)")
        model, family, params = PROVENANCE.get(d, DEFAULT)
        probs = {r["problem"] for r in rows}
        clean = sum(r["K_sem"] and not is_artifact(r["tok"], r["alt"], r.get("err"), lang)
                    for r in rows)
        rec = {"dir": d, "model": model, "family": family, "params": params, "lang": lang,
               "typing": TYPING.get(lang, "?"), "iv": iv, "positions": len(rows),
               "problems": len(probs), "clean_consequential": clean,
               "underpowered": len(probs) < UNDERPOWERED,
               "released": iv >= MIN_IV}
        manifest.append(rec)
        target = released if iv >= MIN_IV else quarantined
        for r in rows:
            row = {k: r[k] for k in KEEP if k in r}
            row.update(model=model, family=family, params=params,
                       typing=TYPING.get(lang, "?"))
            target.append(row)
        if iv >= MIN_IV:
            c = cover[lang]; c[0] += len(rows); c[1] |= probs; c[2] += clean

    with open(out, "w") as fh:
        for r in released:
            fh.write(json.dumps(r) + "\n")
    with open("conseq_manifest.json", "w") as fh:
        json.dump({"min_instrument_version": MIN_IV, "runs": manifest}, fh, indent=2)

    print(f"released    {len(released):7d} rows -> {out}")
    print(f"quarantined {len(quarantined):7d} rows (instrument v1: K_sem includes timeouts, B9)")
    print(f"\n{'lang':<6} {'typing':<8} {'probs':>6} {'positions':>10} {'clean':>7}")
    for k, (pos, pr, cl) in sorted(cover.items(), key=lambda x: -x[1][0]):
        print(f"{k:<6} {TYPING.get(k,'?'):<8} {len(pr):6d} {pos:10d} {cl:7d}")
    fams = {m["family"] for m in manifest if m["released"]}
    print(f"\n{len(cover)} languages, {len(fams)} families in release: {sorted(fams)}")
    up = [m['dir'] for m in manifest if m['released'] and m['underpowered']]
    if up:
        print(f"underpowered (<{UNDERPOWERED} problems), flagged not dropped: {up}")
    # Coverage regression check: a v2 re-run must not cover FEWER problems than the v1 run it
    # replaces. The MBPP re-run silently lost 130 problems to a hardcoded n=161, and that was
    # only visible against its predecessor -- standalone the numbers looked fine.
    by_dir = {d: rows for d, rows in runs}
    print("\n=== v1 -> v2 coverage diff ===")
    regressions = 0
    for v1, v2 in sorted(SUPERSEDED.items()):
        if v1 not in by_dir or v2 not in by_dir:
            continue
        p1 = len({r["problem"] for r in by_dir[v1]})
        p2 = len({r["problem"] for r in by_dir[v2]})
        n1, n2 = len(by_dir[v1]), len(by_dir[v2])
        flag = ""
        if p2 < p1:
            flag = f"  <-- REGRESSION: lost {p1 - p2} problems"; regressions += 1
        elif p2 > p1:
            flag = f"  (+{p2 - p1} problems)"
        print(f"  {v1:<8} -> {v2:<10} problems {p1:4d} -> {p2:4d}   positions {n1:6d} -> {n2:6d}{flag}")
    print(f"  {regressions} regression(s)" if regressions else "  no coverage regressions")

    stale = [m['dir'] for m in manifest if not m['released']]
    if stale:
        print(f"\nSTALE, needs re-run before release: {stale}")
    sup = [d for d in SUPERSEDED if d in dirs and SUPERSEDED[d] in dirs]
    print(f"superseded by v2 re-runs (excluded, correctly): {len(sup)}/{len(SUPERSEDED)}")
    missing = [d for d, v in SUPERSEDED.items() if d in dirs and v not in dirs]
    if missing:
        print(f"!! v1 runs with NO v2 replacement yet: {missing}")


if __name__ == "__main__":
    main()
