"""Phase E -- bug localization. The POSITIVE application.

Phase D showed per-token consequence cannot steer generation. Its compositionality result says
the signal should still be valid for EDITING a fixed sequence. Bug localization is the cleanest
fixed-sequence task: given a program that fails its tests, which token is to blame?

Ground truth is exact by construction -- substitute the model's second choice at one position
until the program fails; that position IS the bug.

Scorers: random (floor), entropy (incumbent), nll (surprisal), role (ours -- a regex).
"""
import argparse, json, sys
import torch
from phase_a import trajectory, is_artifact, STOPS, selftest, entropy
from execjs import run
from roles import role

ROLE_RATE = {"numeric literal": .624, "identifier": .243, "property access": .225,
             "operator": .208, "other": .189, "whitespace": .084, "keyword": .063,
             "punctuation": .009, "string": .010}


def rank_metrics(scores, truth, n):
    order = sorted(range(n), key=lambda t: -scores[t])
    r = order.index(truth) + 1
    return 1.0 / r, {k: float(r <= k) for k in (1, 3, 5, 10)}


def phase_e(model, tok, problems, out, timeout=5.0, max_bugs=4):
    import random as _r
    names = ("random", "entropy", "nll", "role")
    agg = {s: {"mrr": [], 1: [], 3: [], 5: [], 10: []} for s in names}
    rng = _r.Random(0)
    with open(out, "w") as fh:
        for prob in problems:
            pid, prompt, tests = prob["name"], prob["prompt"], prob["tests"]
            stops = prob.get("stop_tokens") or STOPS
            ids, logits, _, _ = trajectory(model, tok, prompt, stops)
            if not ids or run(prompt + tok.decode(ids) + "\n" + tests, timeout) != "pass":
                continue
            top2 = logits.topk(2, dim=-1).indices
            alt_of = lambda t: (int(top2[t, 1]) if int(top2[t, 0]) == ids[t] else int(top2[t, 0]))

            cands = []
            for t in range(len(ids)):
                v = run(prompt + tok.decode(ids[:t] + [alt_of(t)] + ids[t + 1:]) + "\n" + tests, timeout)
                err = v.split(":", 1)[1] if ":" in v else v
                broke = v.startswith("fail") or v == "timeout"
                if broke and not is_artifact(tok.decode([ids[t]]), tok.decode([alt_of(t)]), err):
                    cands.append(t)
            if not cands:
                continue

            for truth in rng.sample(cands, min(max_bugs, len(cands))):
                buggy = ids[:truth] + [alt_of(truth)] + ids[truth + 1:]
                enc = tok(prompt, return_tensors="pt").to(model.device)
                inp = torch.cat([enc.input_ids, torch.tensor([buggy], device=model.device)], 1)
                with torch.no_grad():
                    lg = model(input_ids=inp).logits[0, enc.input_ids.shape[1] - 1:-1, :].float().cpu()
                n = len(buggy)
                sc = {
                    "random":  [rng.random() for _ in range(n)],
                    "entropy": [entropy(lg[t]) for t in range(n)],
                    "nll":     [-float(torch.log_softmax(lg[t], -1)[buggy[t]]) for t in range(n)],
                    "role":    [ROLE_RATE.get(role({"tok": tok.decode([buggy[t]])}, "js"), 0.0)
                                for t in range(n)],
                }
                rec = {"problem": pid, "truth": truth, "n": n}
                for name, s in sc.items():
                    mrr, rk = rank_metrics(s, truth, n)
                    agg[name]["mrr"].append(mrr)
                    for k, v in rk.items():
                        agg[name][k].append(v)
                    rec[name] = mrr
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
            print(f"{pid}: {len(cands)} injectable bugs", flush=True)

    print("\n=== bug localization (higher is better) ===")
    print(f"  {'scorer':>8} {'MRR':>7} {'r@1':>7} {'r@3':>7} {'r@5':>7} {'r@10':>7} {'n':>6}")
    for name in names:
        a = agg[name]
        if not a["mrr"]:
            continue
        m = lambda x: sum(x) / len(x)
        print(f"  {name:>8} {m(a['mrr']):7.3f} {m(a[1]):7.3f} {m(a[3]):7.3f} "
              f"{m(a[5]):7.3f} {m(a[10]):7.3f} {len(a['mrr']):6d}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    if ap.parse_args().selftest:
        selftest()
        mrr, rk = rank_metrics([9, 1, 1, 1], 0, 4)
        assert mrr == 1.0 and rk[1] == 1.0
        mrr, rk = rank_metrics([1, 2, 3, 9], 0, 4)      # distinct: truth ranks last
        assert abs(mrr - 0.25) < 1e-9 and rk[1] == 0.0 and rk[10] == 1.0
        print("phase_e selftest ok")
        sys.exit(0)
