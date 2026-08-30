"""Phase D -- the oracle arm.  Bounds what a PERFECT decode-time consequence predictor buys.

Every arm samples at the same fraction of positions and commits (greedy) at the rest, so the
arms differ only in WHERE they commit, never in how much diversity they spend:

    greedy    commit everywhere                          (reference ceiling)
    random    commit at a random FRAC of positions       (the control Phase C lacked)
    entropy   commit where entropy is high               (the incumbent)
    role      commit at consequential syntactic roles    (ours)
    oracle    commit exactly where the instrument measured K_sem=1   (perfect predictor)

If `oracle` cannot beat `random`, consequence is unexploitable by commit-scheduling and the
negative is final.  If it can, the gap is in the predictor, not the concept.

Oracle labels are computed on the greedy reference trajectory. Once an arm samples a different
token the indices drift; we commit at consequential positions, so drift only accumulates through
positions the instrument calls free.  Reported as a caveat, not hidden.
"""
import argparse, json, sys
import torch
from phase_a import trajectory, cut_at_stop, is_artifact, STOPS, selftest
from execjs import run
from roles import role

# Per-role consequence rates measured in Phase A; used to rank positions for the role arm.
ROLE_RATE = {"numeric literal": .624, "identifier": .243, "property access": .225,
             "operator": .208, "other": .189, "whitespace": .084, "keyword": .063,
             "punctuation": .009, "string": .010}


def oracle_labels(tok, ids, logits, prompt, tests, timeout):
    """K_sem per position on the greedy trajectory. No GPU: forced splice + execute."""
    top2 = logits.topk(2, dim=-1).indices
    lab, passed = [], []
    for t in range(len(ids)):
        alt = int(top2[t, 1]) if int(top2[t, 0]) == ids[t] else int(top2[t, 0])
        v = run(prompt + tok.decode(ids[:t] + [alt] + ids[t + 1:]) + "\n" + tests, timeout)
        broke = v.startswith("fail") or v == "timeout"
        err = v.split(":", 1)[1] if ":" in v else v
        lab.append(bool(broke) and not is_artifact(tok.decode([ids[t]]), tok.decode([alt]), err))
        # "free" must mean the splice ACTUALLY PASSED -- not merely "not K_sem".
        # Artifact-breakers are excluded from K_sem but still break the program, and
        # including them in the free set would blame composition for artifact damage.
        passed.append(v == "pass")
    return lab, passed


def commit_sets(tok, ids, logits, labels, passed=None):
    """Every arm commits at exactly k = |consequential| positions, so the arms differ only in
    WHICH positions they pick -- never in how much diversity they spend."""
    import random as _r
    # The DECODING oracle must commit wherever the alternative breaks the program at all --
    # including reference/BPE artifacts. K_sem excludes those for the scientific claim about
    # consequence, but at decode time a break is a break, and leaving them in the sampled set
    # handicaps the oracle against its own controls.
    brk = [not p for p in passed] if passed is not None else labels
    k = sum(brk)
    ent = [float(-(torch.softmax(logits[t], -1) *
                   torch.log(torch.softmax(logits[t], -1) + 1e-12)).sum()) for t in range(len(ids))]
    rol = [ROLE_RATE.get(role({"tok": tok.decode([ids[t]])}, "js"), 0.0) for t in range(len(ids))]
    order = lambda sc: set(sorted(range(len(ids)), key=lambda t: -sc[t])[:k])
    rng = _r.Random(0)
    return {
        "greedy":  set(range(len(ids))),
        "oracle":  {t for t, v in enumerate(brk) if v},
        "entropy": order(ent),
        "role":    order(rol),
        "random":  set(rng.sample(range(len(ids)), min(k, len(ids)))),
    }, k


def decode(model, tok, prompt, stops, arm, cset, max_new=320, seed=0):
    enc = tok(prompt, return_tensors="pt").to(model.device)
    ids, past, out = enc.input_ids, None, []
    g = torch.Generator(device="cpu").manual_seed(seed)
    for step in range(max_new):
        with torch.no_grad():
            o = model(input_ids=ids if past is None else ids[:, -1:],
                      past_key_values=past, use_cache=True)
        past = o.past_key_values
        lg = o.logits[0, -1, :].float()
        top = lg.topk(2)

        commit = (step in cset) if step < max_new else True

        if commit:
            nxt = int(top.indices[0])
        else:                                  # sample within top-2, matching the instrument
            j = int(torch.multinomial(torch.softmax(top.values, -1).cpu(), 1, generator=g))
            nxt = int(top.indices[j])
        if nxt == tok.eos_token_id:
            break
        out.append(nxt)
        ids = torch.cat([ids, torch.tensor([[nxt]], device=ids.device)], 1)
    return tok.decode(out[:cut_at_stop(tok, out, stops)])


ARMS = ("greedy", "random", "entropy", "role", "oracle")

def phase_d(model, tok, problems, out, n_samp=3, ent_thresh=0.4161, timeout=5.0):
    tally = {a: [0, 0] for a in ARMS}
    with open(out, "w") as fh:
        for prob in problems:
            pid, prompt, tests = prob["name"], prob["prompt"], prob["tests"]
            stops = prob.get("stop_tokens") or STOPS
            ids, logits, _, _ = trajectory(model, tok, prompt, stops)
            if not ids or run(prompt + tok.decode(ids) + "\n" + tests, timeout) != "pass":
                continue
            labels, passed = oracle_labels(tok, ids, logits, prompt, tests, timeout)
            csets, k = commit_sets(tok, ids, logits, labels, passed)
            # Does single-token consequence COMPOSE?  Substitute the second choice at EVERY
            # position the instrument calls free, all at once, and execute.  If individually
            # harmless edits are jointly harmless, this must still pass.
            top2 = logits.topk(2, dim=-1).indices
            comp = [ids[t] if not passed[t] else
                    (int(top2[t, 1]) if int(top2[t, 0]) == ids[t] else int(top2[t, 0]))
                    for t in range(len(ids))]
            comp_ok = run(prompt + tok.decode(comp) + "\n" + tests, timeout) == "pass"
            n_free = sum(passed)

            # Dose-response: how MANY individually-free substitutions can a program absorb?
            # Pure execution, no GPU. Gives the compositionality horizon as a number.
            import random as _r
            free_idx = [t for t in range(len(ids)) if passed[t]]
            alt_of = lambda t: (int(top2[t, 1]) if int(top2[t, 0]) == ids[t] else int(top2[t, 0]))
            dose = {}
            rng2 = _r.Random(1234)
            for m in (1, 2, 3, 5, 8, 12, 20, 32):
                if m > len(free_idx):
                    break
                hits = 0
                for _ in range(5):
                    pick = set(rng2.sample(free_idx, m))
                    prog = [alt_of(t) if t in pick else ids[t] for t in range(len(ids))]
                    hits += run(prompt + tok.decode(prog) + "\n" + tests, timeout) == "pass"
                dose[m] = hits / 5
            rec = {"problem": pid, "n_pos": len(ids), "k": k, "commit_frac": k / len(ids),
                   "compose_ok": comp_ok, "n_free": n_free, "dose": dose}
            for arm in ARMS:
                ok = sum(run(prompt + decode(model, tok, prompt, stops, arm, csets[arm],
                                             seed=9000 + i) + "\n" + tests,
                             timeout) == "pass" for i in range(n_samp))
                rec[arm] = ok / n_samp
                tally[arm][0] += ok; tally[arm][1] += n_samp
            fh.write(json.dumps(rec) + "\n"); fh.flush()
            print(f"{pid}: " + " ".join(f"{a}={rec[a]:.2f}" for a in ARMS), flush=True)
    print("\n=== compositionality: all free positions substituted at once ===")
    print("  (if single-token consequence composes, these must still pass)")
    print("\n=== pass@1, matched commit budget ===")
    for a in ARMS:
        o, n = tally[a]; print(f"  {a:8s} {o/max(1,n):6.1%}  ({o}/{n})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    if ap.parse_args().selftest:
        selftest()
        assert ROLE_RATE[role({"tok": "0"}, "js")] > ROLE_RATE[role({"tok": ";"}, "js")]
        # the invariant the whole comparison rests on: every arm commits the same NUMBER of times
        import torch as _t
        _ids = [1, 2, 3, 4, 5, 6, 7, 8]
        _lg = _t.randn(8, 50)
        class _T:
            def decode(self, x): return {1: "0", 2: ";", 3: " ", 4: "i",
                                         5: "+", 6: "}", 7: "1", 8: "n"}[x[0]]
        _lab = [True, False, False, True, False, False, True, False]
        _pass = [False, True, True, False, True, False, True, True]   # 3 breaking positions
        _cs, _k = commit_sets(_T(), _ids, _lg, _lab, _pass)
        assert _k == 3, _k
        assert _cs["oracle"] == {0, 3, 5}, _cs["oracle"]
        for _a in ("oracle", "entropy", "role", "random"):
            assert len(_cs[_a]) == _k, (_a, len(_cs[_a]), _k)
        print("phase_d selftest ok"); sys.exit(0)
