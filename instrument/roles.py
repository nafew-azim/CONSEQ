"""Role analysis: is consequence carried by syntactic role, and does entropy beat random?

    python3 roles.py <phase_a.jsonl> [--lang js|py]

Roles are fit on half the problems and evaluated on the held-out half, so the selector
is never scored on the data that chose it.
"""
import json, re, sys, random
from collections import defaultdict
from phase_a import is_artifact

KW = {"js": {"let","const","var","return","if","else","for","while","function","break",
             "continue","new","typeof","of","in"},
      "py": {"def","return","if","elif","else","for","while","in","not","and","or","None",
             "True","False","import","lambda","yield","break","continue","is"},
      "java": {"public","private","protected","static","final","class","interface","void","int",
               "long","float","double","boolean","char","String","return","if","else","for","while",
               "new","this","null","true","false","import","package","extends","implements","try",
               "catch","throw","throws","break","continue","switch","case","default","assert"},
      "rb": {"def","end","if","elsif","else","unless","while","until","for","in","return",
             "do","then","class","module","nil","true","false","and","or","not","yield"},
      "php": {"function","return","if","elseif","else","for","foreach","while","do","echo",
              "class","new","null","true","false","as","array","public","private","static"},
      "rs": {"fn","let","mut","const","if","else","match","for","while","loop","return",
             "struct","enum","impl","trait","pub","use","mod","true","false","None",
             "Some","Ok","Err","as","ref","move","where","self"},
      "pl": {"sub","return","if","elsif","else","unless","while","until","for","foreach",
             "my","our","local","use","package","last","next","undef","eq","ne","lt","gt"},
      "lua": {"function","end","if","then","else","elseif","for","while","do","return",
              "local","nil","true","false","and","or","not","in","repeat","until"},
      "ts": {"let","const","var","return","if","else","for","while","function","break","continue",
             "new","typeof","of","in","interface","type","as","implements","extends","readonly",
             "public","private","number","string","boolean","void","any"},
      "go": {"func","var","const","if","else","for","range","return","package","import","type",
             "struct","interface","map","chan","go","defer","select","switch","case","default",
             "break","continue","nil","true","false","len","append","make","new"}}
OPS = {"+","-","*","/","%","=","==","===","!=","!==","<",">","<=",">=","+=","-=","*=","/=",
       "&&","||","??","!","++","--","**","//","is","not","and","or","%=","//=","**="}

def role(r, lang):
    t = r["tok"].strip()
    if t in KW[lang]: return "keyword"
    if t in OPS: return "operator"
    if re.fullmatch(r"-?\d+(\.\d+)?", t): return "numeric literal"
    if t.startswith("."): return "property access"
    if re.fullmatch(r'["\'].*', t): return "string"
    if re.fullmatch(r"[A-Za-z_$][\w$]*", t): return "identifier"
    if re.fullmatch(r"[^\w\s]+", t): return "punctuation"
    if not t: return "whitespace"
    return "other"

def main(path, lang):
    rows = [json.loads(l) for l in open(path)]
    # lang matters: a rename shows up as ReferenceError in JS and NameError in Python.
    clean = lambda r: r["K_sem"] and not is_artifact(r["tok"], r["alt"], r.get("err"), lang)
    tot_all = sum(map(clean, rows))
    print(f"{path}  positions {len(rows)}  problems {len({r['problem'] for r in rows})}  "
          f"clean consequential {tot_all} ({tot_all/len(rows):.1%})\n")

    by = defaultdict(lambda: [0, 0, 0.0])
    for r in rows:
        b = by[role(r, lang)]; b[0] += 1; b[1] += clean(r); b[2] += r["entropy"]
    print(f"{'role':>16} {'n':>5} {'rate':>7} {'mass':>7} {'meanH':>7}")
    for k, (n, c, h) in sorted(by.items(), key=lambda x: -x[1][1]):
        print(f"{k:>16} {n:5d} {c/n:6.1%} {c/max(1,tot_all):6.1%} {h/n:7.3f}")

    probs = sorted({r["problem"] for r in rows}); random.Random(0).shuffle(probs)
    A = set(probs[:len(probs)//2])
    tr = [r for r in rows if r["problem"] in A]
    te = [r for r in rows if r["problem"] not in A]
    fit = defaultdict(lambda: [0, 0])
    for r in tr:
        b = fit[role(r, lang)]; b[0] += 1; b[1] += clean(r)
    ranked = sorted(fit, key=lambda k: -(fit[k][1] / max(1, fit[k][0])))
    tot = max(1, sum(map(clean, te)))
    print(f"\nheld-out selector (roles fit on {len(A)} problems, scored on {len(probs)-len(A)}):")
    print(f"{'budget':>8} {'ROLE':>8} {'entropy':>8} {'random':>8}   roles")
    for topk in (2, 3, 4):
        sel = set(ranked[:topk])
        picked = [r for r in te if role(r, lang) in sel]
        if not picked: continue
        b = len(picked) / len(te)
        ent = sorted(te, key=lambda r: -r["entropy"])[:len(picked)]
        print(f"{b:7.1%} {sum(map(clean,picked))/tot:7.1%} {sum(map(clean,ent))/tot:8.1%} "
              f"{b:8.1%}   {sorted(sel)}")

if __name__ == "__main__":
    lang = sys.argv[sys.argv.index("--lang")+1] if "--lang" in sys.argv else "js"
    main(sys.argv[1], lang)
