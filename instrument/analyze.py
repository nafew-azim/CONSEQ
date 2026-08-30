"""Week-1 pilot readout: the five checks from proposal section 19."""
import json, re, sys, statistics as st
from collections import Counter

rows = [json.loads(l) for l in open(sys.argv[1] if len(sys.argv) > 1 else "phase_a.jsonl")]
n = len(rows)
sem = [r for r in rows if r["K_sem"]]
syn = [r for r in rows if r["K_syn"]]
eq  = [r for r in rows if r["equivalent"]]

print(f"positions {n}   problems {len({r['problem'] for r in rows})}")
print(f"1. consequential   {len(sem)+len(syn):5d}  {(len(sem)+len(syn))/n:6.1%}   [gate G2: 5-60%]")
print(f"2. semantic K_sem  {len(sem):5d}  {len(sem)/n:6.1%}   [need >3%]")
print(f"   syntactic K_syn {len(syn):5d}  {len(syn)/n:6.1%}")
print(f"   equivalent      {len(eq):5d}  {len(eq)/n:6.1%}")

# 3. entropy decile x consequence -- draft of Figure 1
print("\n3. entropy decile x semantic consequence")
rows.sort(key=lambda r: r["entropy"])
w = max(1, n // 10)
print("   dec   mean_H   rate   share_of_mass")
for d in range(10):
    b = rows[d * w:(d + 1) * w] if d < 9 else rows[9 * w:]
    if not b: continue
    hits = sum(r["K_sem"] for r in b)
    bar = "#" * round(40 * hits / len(b))
    print(f"   {d}  {st.mean(r['entropy'] for r in b):7.3f}  {hits/len(b):5.1%}  "
          f"{hits/max(1,len(sem)):5.1%}  {bar}")

lo = rows[:n // 3]; hi = rows[2 * n // 3:]
print(f"\n   H1 check: bottom entropy tercile holds {sum(r['K_sem'] for r in lo)/max(1,len(sem)):.1%} "
      f"of semantic mass (top tercile {sum(r['K_sem'] for r in hi)/max(1,len(sem)):.1%})")
print(f"   [H1 predicts bottom >= 30%]")

# rename artifacts (broken reference) are not keystones -- report them apart
def bpe_frag(r):
    """'.length' -> '.l' is BPE truncation, not a decision. '<' -> '<=' IS a decision."""
    a, b = r["tok"].strip(), r["alt"].strip()
    if not (a and b and (a.startswith(b) or b.startswith(a))):
        return False
    return bool(re.search(r"\w", a)) and bool(re.search(r"\w", b))

art = [r for r in sem if r.get("err") in ("ReferenceError", "TypeError") or bpe_frag(r)]
true_sem = [r for r in sem if r not in art]
print(f"\n   failure mode split: {len(true_sem)} assertion/logic | {len(art)} reference artifact "
      f"({len(art)/max(1,len(sem)):.1%} of K_sem: broken reference + BPE fragment)")
rows.sort(key=lambda r: r["entropy"]); t = n // 3
lo2 = sum(r in true_sem for r in rows[:t]); m2 = max(1, len(true_sem))
print(f"   H1 on artifact-free mass: bottom tercile {lo2/m2:.1%} "
      f"(top {sum(r in true_sem for r in rows[2*t:])/m2:.1%})")

print("\n4. top consequential tokens by frequency (artifact-free)")
# label by the substitution, not the original token: a ' ' -> '1' splice is a numeric edit
for (a, b), c in Counter((r["tok"], r["alt"]) for r in true_sem).most_common(22):
    print(f"   {c:4d}  {a!r:>12} -> {b!r}")
print("\n5. sample of FREE positions (should look arbitrary)")
for r in [x for x in rows if not x["K_sem"] and not x["K_syn"]][::max(1, (n - len(sem)) // 15)][:15]:
    print(f"   {r['tok']!r:>18} -> {r['alt']!r:<18} H={r['entropy']:.2f}")
