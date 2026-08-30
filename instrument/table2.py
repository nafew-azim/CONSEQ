"""Table 2 -- every published selection criterion vs execution ground truth.

Each criterion is scored in the direction ITS OWN literature uses it, so nothing is strawmanned:
entropy/NLL/KL/excess-loss select HIGH values; margin selects LOW (low margin = uncertain);
prefix methods select EARLY positions. The reverse direction is reported too, so a criterion that
would do better flipped is visible rather than hidden.
"""
import json, sys
from statistics import mean

# +1: literature selects the HIGH end.  -1: literature selects the LOW end.
SIGN = {"P0_random": +1, "P1_entropy": +1, "P2_margin": -1, "P3_nll": +1,
        "P4_excess_loss": +1, "P5_teacher_kl": +1, "P6_expert_delta": +1,
        "P7_position": -1, "P8_conf_wrong": +1, "P9_varentropy": +1, "P10_minp_width": +1}


def spearman(x, y):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = rank(x), rank(y)
    mx, my = mean(rx), mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** .5
    dy = sum((b - my) ** 2 for b in ry) ** .5
    return num / (dx * dy) if dx and dy else 0.0


def main(path):
    rows = [json.loads(l) for l in open(path)]
    sys.path.insert(0, ".")
    from phase_a import is_artifact
    truth = [1.0 if (r["K_sem"] and not is_artifact(r["tok"], r["alt"], r.get("err"),
                                                    r.get("lang", "js"))) else 0.0 for r in rows]
    tot = sum(truth)
    n = len(rows)
    print(f"{path}: {n} positions, {int(tot)} clean consequential ({tot/n:.1%})\n")
    crits = [c for c in SIGN if c in rows[0]]
    print(f"  {'criterion':>16} {'rho':>7} {'CC@10':>7} {'CC@25':>7} {'CC@50':>7} {'waste@25':>9} {'flip?':>6}")
    out = []
    for c in crits:
        raw = [float(r[c]) for r in rows]
        s = [SIGN[c] * v for v in raw]
        rho = spearman(s, truth)
        cc = {}
        for b in (.10, .25, .50):
            k = max(1, int(b * n))
            top = sorted(range(n), key=lambda i: -s[i])[:k]
            cc[b] = sum(truth[i] for i in top) / max(1, tot)
        k25 = max(1, int(.25 * n))
        top25 = sorted(range(n), key=lambda i: -s[i])[:k25]
        waste = 1 - sum(truth[i] for i in top25) / len(top25)
        rev = spearman([-v for v in s], truth)
        out.append((c, rho, cc, waste, rev > rho))
    for c, rho, cc, waste, flip in sorted(out, key=lambda x: -x[1]):
        print(f"  {c:>16} {rho:+7.3f} {cc[.10]:7.1%} {cc[.25]:7.1%} {cc[.50]:7.1%} "
              f"{waste:9.1%} {'YES' if flip else '':>6}")
    print(f"\n  {'random baseline':>16} {'0.000':>7} {'10.0%':>7} {'25.0%':>7} {'50.0%':>7}")


if __name__ == "__main__":
    main(sys.argv[1])
