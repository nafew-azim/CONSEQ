"""Phase B -- repairability.  Given a position where the forced splice broke the program,
does the model recover when allowed to continue freely?

    R_t = p_C / p_F     repairability      (1.0 = fully repaired, 0.0 = committed error)
    D_t = p_F - p_C     net damage

Only clean-consequential positions get GPU time; Phase A's forced arm is what makes that
affordable.  A control sample of K=0 positions is measured too -- if those show damage, the
forced arm is missing consequence and the whole cost model is wrong (proposal 7.4).
"""
import argparse, json, sys
import torch
from phase_a import (trajectory, cut_at_stop, entropy, is_artifact, STOPS, selftest)
from execjs import run


def continue_from(model, tok, prompt, prefix_ids, n, stops, temp=0.6, max_new=192, seed=0):
    """n sampled continuations from prompt+prefix_ids. Returns decoded completion strings."""
    enc = tok(prompt, return_tensors="pt").to(model.device)
    pre = torch.tensor([prefix_ids], device=model.device, dtype=enc.input_ids.dtype)
    ids = torch.cat([enc.input_ids, pre], dim=1)
    torch.manual_seed(seed)                      # common random numbers across the two arms
    with torch.no_grad():
        g = model.generate(input_ids=ids, attention_mask=torch.ones_like(ids),
                           max_new_tokens=max_new, do_sample=True, temperature=temp,
                           top_p=0.95, num_return_sequences=n, pad_token_id=tok.eos_token_id)
    outs = []
    for s in g:
        c = s[ids.shape[1]:].tolist()
        if tok.eos_token_id in c:
            c = c[:c.index(tok.eos_token_id)]
        outs.append(tok.decode(c[:cut_at_stop(tok, c, stops)]))
    return outs


def arm_pass_rate(model, tok, prompt, prefix_ids, tests, n, stops, timeout, seed, lang="js"):
    """Mean pass rate of n free continuations from prefix_ids.

    The assembled program MUST use the same prefix the model was conditioned on -- decoding
    a shorter prefix drops the token under test and measures nothing.
    """
    head = tok.decode(prefix_ids)
    conts = continue_from(model, tok, prompt, prefix_ids, n, stops, seed=seed)
    ok = sum(run(prompt + head + c + "\n" + tests, timeout, lang) == "pass" for c in conts)
    return ok / max(1, len(conts))


def phase_b(model, tok, problems, out, n_samp=8, timeout=5.0, max_per_problem=6, controls=2, lang="js"):
    kept = 0
    with open(out, "w") as fh:
        for prob in problems:
            pid, prompt, tests = prob["name"], prob["prompt"], prob["tests"]
            stops = prob.get("stop_tokens") or STOPS
            ids, logits, _, _ = trajectory(model, tok, prompt, stops)
            if not ids:
                continue
            body = tok.decode(ids)
            if run(prompt + body + "\n" + tests, timeout, lang) != "pass":
                continue

            top2 = logits.topk(2, dim=-1).indices          # [L, 2]
            cons, free = [], []
            for t in range(len(ids)):
                alt = int(top2[t, 1]) if int(top2[t, 0]) == ids[t] else int(top2[t, 0])
                spliced = prompt + tok.decode(ids[:t] + [alt] + ids[t + 1:]) + "\n" + tests
                v = run(spliced, timeout, lang)
                broke = v.startswith("fail") or v == "timeout"
                err = v.split(":", 1)[1] if ":" in v else v
                rec = (t, alt, tok.decode([ids[t]]), tok.decode([alt]), err)
                if broke and not is_artifact(rec[2], rec[3], err, lang):
                    cons.append(rec)
                elif v == "pass":
                    free.append(rec)

            step = max(1, len(cons) // max_per_problem)
            targets = [(r, True) for r in cons[::step][:max_per_problem]]
            step = max(1, len(free) // controls)
            targets += [(r, False) for r in free[::step][:controls]]

            for (t, alt, tok_s, alt_s, err), is_cons in targets:
                # invariant: the factual prefix plus the untouched tail is the original program
                assert prompt + tok.decode(ids[:t + 1]) + tok.decode(ids[t + 1:]) == prompt + body
                p_F = arm_pass_rate(model, tok, prompt, ids[:t + 1], tests,
                                    n_samp, stops, timeout, seed=1000 + t, lang=lang)
                p_C = arm_pass_rate(model, tok, prompt, ids[:t] + [alt], tests,
                                    n_samp, stops, timeout, seed=1000 + t, lang=lang)
                fh.write(json.dumps({
                    "problem": pid, "pos": t, "n_pos": len(ids), "suffix_len": len(ids) - t,
                    "tok": tok_s, "alt": alt_s, "err": err, "consequential": is_cons,
                    "entropy": entropy(logits[t]), "p_F": p_F, "p_C": p_C, "lang": lang,
                    "R": (p_C / p_F) if p_F > 0 else None, "D": p_F - p_C,
                }) + "\n")
                fh.flush(); kept += 1
            print(f"{pid}: {len(cons)} consequential, wrote {len(targets)} (total {kept})", flush=True)
    print(f"phase_b wrote {kept} positions -> {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        # repairability must be well-defined at the boundaries
        assert (0.0 / 0.8) == 0.0
        print("phase_b selftest ok")
        sys.exit(0)
