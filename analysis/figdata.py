"""Compute every number the paper's figures plot, from the release build.

Definitions are imported from the analysis modules the tables use, so a figure
cannot silently disagree with the table beside it.
"""
import json, random, collections, sys
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "instrument"))
from _paths import RELEASE, FIGURES, require_release

HERE = os.path.dirname(os.path.abspath(__file__))
from phase_a import is_artifact
from roles import role

REL = require_release()

def clean(r):
    return bool(r["K_sem"]) and not is_artifact(r["tok"], r["alt"], r.get("err"), r["lang"])

def load(path=None):
    return [json.loads(l) for l in open(path or REL)]

def heldout(rows, lang, seed=0, topks=None):
    """Fit role ranking on half the problems, score on the other half.

    Returns (budgets, role_recall, entropy_recall) over topk = 1..len(roles),
    which is the same procedure as roles.py's table, swept over all budgets so
    it can be drawn as a curve rather than three points.
    """
    probs = sorted({r["problem"] for r in rows})
    random.Random(seed).shuffle(probs)
    A = set(probs[: len(probs) // 2])
    tr = [r for r in rows if r["problem"] in A]
    te = [r for r in rows if r["problem"] not in A]
    if not tr or not te:
        return [], [], []
    fit = collections.defaultdict(lambda: [0, 0])
    for r in tr:
        b = fit[role(r, lang)]; b[0] += 1; b[1] += clean(r)
    ranked = sorted(fit, key=lambda k: -(fit[k][1] / max(1, fit[k][0])))
    tot = sum(map(clean, te))
    if tot == 0:
        return [], [], []
    te_ent = sorted(te, key=lambda r: -r["entropy"])
    bud, rec_role, rec_ent = [], [], []
    for topk in (topks if topks is not None else range(1, len(ranked) + 1)):
        sel = set(ranked[:topk])
        picked = [r for r in te if role(r, lang) in sel]
        if not picked:
            continue
        b = len(picked) / len(te)
        bud.append(b)
        rec_role.append(sum(map(clean, picked)) / tot)
        rec_ent.append(sum(map(clean, te_ent[: len(picked)])) / tot)
    return bud, rec_role, rec_ent

def entropy_vs_random(rows, lang):
    """Recall lift of an entropy selector over random at a matched budget.

    Budget is fixed at the top-2-role budget so every configuration is scored at
    a comparable operating point; random recall equals the budget by definition.
    """
    bud, _, ent = heldout(rows, lang, topks=(2,))
    if not bud:
        return None
    return bud[0], ent[0]

def configs(rows):
    by = collections.defaultdict(list)
    for r in rows:
        by[(r["model"], r["family"], r["params"], r["lang"])].append(r)
    return by

def verdict_shares(rows):
    n = len(rows)
    if not n:
        return None
    g = lambda f: sum(bool(r[f]) for r in rows) / n
    return {"n": n, "K_syn": g("K_syn"), "K_type": g("K_type"),
            "K_sem": g("K_sem"), "K_timeout": g("K_timeout")}

if __name__ == "__main__":
    rows = load()
    out = {"configs": [], "lang": {}, "curves": {}}
    for (model, fam, params, lang), rs in sorted(configs(rows).items()):
        ev = entropy_vs_random(rs, lang)
        if ev is None:
            continue
        b, e = ev
        out["configs"].append({"model": model, "family": fam, "params": params,
                               "lang": lang, "n": len(rs), "budget": b,
                               "entropy": e, "random": b,
                               "problems": len({r["problem"] for r in rs})})
    bylang = collections.defaultdict(list)
    for r in rows:
        bylang[r["lang"]].append(r)
    for lang, rs in bylang.items():
        out["lang"][lang] = verdict_shares(rs)
        b, rr, re_ = heldout(rs, lang)
        out["curves"][lang] = {"budget": b, "role": rr, "entropy": re_}
    json.dump(out, open(os.path.join(HERE, "figdata.json"), "w"), indent=1)

    # Figure 4 / Table 12 hold model and benchmark constant so the grouping is attributable
    # to the language, not to which models happen to cover it.
    ctl = collections.defaultdict(collections.Counter)
    for r in rows:
        if r["model"] != "Qwen/Qwen2.5-Coder-1.5B" or not r["problem"].startswith("HumanEval"):
            continue
        d = ctl[r["lang"]]; d["n"] += 1
        for f in ("K_syn", "K_type", "K_sem"):
            d[f] += bool(r[f])
    json.dump({k: {"n": ctl[k]["n"],
                   **{f: ctl[k][f] / ctl[k]["n"] for f in ("K_syn", "K_type", "K_sem")}}
               for k in ("rb", "pl", "php", "py", "js", "ts", "go", "java", "rs")},
              open(os.path.join(HERE, "figdata_typing.json"), "w"), indent=1)
    print("configs:", len(out["configs"]), "langs:", len(out["lang"]),
          "-> figdata.json, figdata_typing.json")
