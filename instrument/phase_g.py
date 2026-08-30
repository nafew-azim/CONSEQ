"""Phase G -- a ground-truth ruler for RL credit assignment.

GRPO and friends assign the SAME advantage to every token in a rollout. Recent work modulates it
by entropy or token probability. Nobody has checked whether those heuristics actually find the
token where a failed rollout became unrecoverable, because there was no ground truth for it.

This builds one. For a FAILING rollout, binary-search the largest prefix length t from which the
model can still produce a passing program. Everything after t is already doomed; the decision at
t is where credit belongs. That position is the ground-truth credit target.

Note this is the *editing* regime (the rollout is fixed before credit is assigned), which is where
CONSEQ's composition result holds -- unlike decode-time steering, which Phase D closed.

Scorers, all evaluated on the same failing rollouts:
    uniform    the GRPO baseline: every token equally
    random     floor
    entropy    the "high-entropy forking token" heuristic
    nll        token surprisal (probability-based credit, TEPO-style)
    margin     p(top1) - p(top2)
    role       ours -- a regex, no model call
"""
import argparse, json, sys
import torch
from phase_a import trajectory, cut_at_stop, entropy, STOPS, selftest
from execjs import run
from roles import role

ROLE_RATE = {"numeric literal": .624, "identifier": .243, "property access": .225,
             "operator": .208, "other": .189, "whitespace": .084, "keyword": .063,
             "punctuation": .009, "string": .010}


def sample_rollouts(model, tok, prompt, stops, k, temp=0.8, max_new=320, seed=0):
    """k independent rollouts, as an RL trainer would generate them."""
    enc = tok(prompt, return_tensors="pt").to(model.device)
    torch.manual_seed(seed)
    with torch.no_grad():
        g = model.generate(**enc, max_new_tokens=max_new, do_sample=True, temperature=temp,
                           top_p=0.95, num_return_sequences=k, pad_token_id=tok.eos_token_id,
                           return_dict_in_generate=True, output_scores=True)
    out = []
    plen = enc.input_ids.shape[1]
    for i in range(k):
        ids = g.sequences[i][plen:].tolist()
        if tok.eos_token_id in ids:
            ids = ids[:ids.index(tok.eos_token_id)]
        ids = ids[:cut_at_stop(tok, ids, stops)]
        if ids:
            out.append(ids)
    return out


def recoverable(model, tok, prompt, prefix_ids, tests, stops, n, timeout, lang, seed):
    """Can the model still reach a passing program from this prefix?"""
    enc = tok(prompt, return_tensors="pt").to(model.device)
    pre = torch.tensor([prefix_ids], device=model.device, dtype=enc.input_ids.dtype)
    ids = torch.cat([enc.input_ids, pre], 1)
    torch.manual_seed(seed)
    with torch.no_grad():
        g = model.generate(input_ids=ids, attention_mask=torch.ones_like(ids),
                           max_new_tokens=200, do_sample=True, temperature=0.8, top_p=0.95,
                           num_return_sequences=n, pad_token_id=tok.eos_token_id)
    head = tok.decode(prefix_ids)
    for s in g:
        c = s[ids.shape[1]:].tolist()
        if tok.eos_token_id in c:
            c = c[:c.index(tok.eos_token_id)]
        body = head + tok.decode(c[:cut_at_stop(tok, c, stops)])
        if run(prompt + body + "\n" + tests, timeout, lang) == "pass":
            return True
    return False


def find_fatal(model, tok, prompt, ids, tests, stops, timeout, lang, n=4):
    """Largest t with a recoverable prefix. The decision at t is where credit belongs.
    Binary search: ~log2(L) probes instead of L."""
    lo, hi = 0, len(ids)
    if not recoverable(model, tok, prompt, ids[:0], tests, stops, n, timeout, lang, 0):
        return None                      # unrecoverable even from empty prefix: model can't solve it
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if recoverable(model, tok, prompt, ids[:mid], tests, stops, n, timeout, lang, mid):
            lo = mid
        else:
            hi = mid - 1
    return lo if lo < len(ids) else None


def rank_metrics(scores, truth, n):
    order = sorted(range(n), key=lambda t: -scores[t])
    r = order.index(truth) + 1
    return 1.0 / r, {k: float(r <= k) for k in (1, 5, 10, 20)}


def phase_g(model, tok, problems, out, k=8, timeout=5.0, lang="js", max_fail=2):
    import random as _r
    rng = _r.Random(0)
    names = ("uniform", "random", "entropy", "nll", "margin", "role")
    agg = {s: {"mrr": [], 1: [], 5: [], 10: [], 20: []} for s in names}
    with open(out, "w") as fh:
        for prob in problems:
            pid, prompt, tests = prob["name"], prob["prompt"], prob["tests"]
            stops = prob.get("stop_tokens") or STOPS
            rolls = sample_rollouts(model, tok, prompt, stops, k)
            fails = [r for r in rolls
                     if run(prompt + tok.decode(r) + "\n" + tests, timeout, lang) != "pass"]
            passes = [r for r in rolls
                      if run(prompt + tok.decode(r) + "\n" + tests, timeout, lang) == "pass"]
            if not fails or not passes:
                continue                 # need both: a failure to localise, a pass to prove solvable
            for ids in fails[:max_fail]:
                t = find_fatal(model, tok, prompt, ids, tests, stops, timeout, lang)
                if t is None or t >= len(ids):
                    continue
                enc = tok(prompt, return_tensors="pt").to(model.device)
                inp = torch.cat([enc.input_ids,
                                 torch.tensor([ids], device=model.device)], 1)
                with torch.no_grad():
                    lg = model(input_ids=inp).logits[0, enc.input_ids.shape[1] - 1:-1, :].float().cpu()
                n = len(ids)
                sc = {
                    "uniform": [1.0] * n,                       # GRPO: every token equal
                    "random":  [rng.random() for _ in range(n)],
                    "entropy": [entropy(lg[i]) for i in range(n)],
                    "nll":     [-float(torch.log_softmax(lg[i], -1)[ids[i]]) for i in range(n)],
                    "margin":  [-float(torch.softmax(lg[i], -1).topk(2).values.diff().abs())
                                for i in range(n)],
                    "role":    [ROLE_RATE.get(role({"tok": tok.decode([ids[i]])}, lang), 0.0)
                                for i in range(n)],
                }
                rec = {"problem": pid, "fatal": t, "n": n, "lang": lang}
                for nm, s in sc.items():
                    mrr, rk = rank_metrics(s, t, n)
                    agg[nm]["mrr"].append(mrr)
                    for kk, v in rk.items():
                        agg[nm][kk].append(v)
                    rec[nm] = mrr
                fh.write(json.dumps(rec) + "\n"); fh.flush()
            print(f"{pid}: {len(fails)} fails / {len(passes)} passes", flush=True)

    print("\n=== RL credit assignment: can any heuristic find the fatal token? ===")
    print(f"  {'scorer':>8} {'MRR':>7} {'r@1':>7} {'r@5':>7} {'r@10':>7} {'r@20':>7} {'n':>5}")
    for nm in names:
        a = agg[nm]
        if not a["mrr"]:
            continue
        m = lambda x: sum(x) / len(x)
        print(f"  {nm:>8} {m(a['mrr']):7.3f} {m(a[1]):7.3f} {m(a[5]):7.3f} "
              f"{m(a[10]):7.3f} {m(a[20]):7.3f} {len(a['mrr']):5d}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    if ap.parse_args().selftest:
        selftest()
        mrr, rk = rank_metrics([9, 1, 2, 3], 0, 4); assert mrr == 1.0 and rk[1] == 1.0
        mrr, rk = rank_metrics([1, 2, 3, 9], 0, 4); assert abs(mrr - .25) < 1e-9 and rk[1] == 0.0
        # uniform scoring must be maximally uninformative: truth ranks by tie-break only
        mrr, _ = rank_metrics([1.0] * 10, 5, 10); assert mrr == 1/6, mrr
        print("phase_g selftest ok"); sys.exit(0)
