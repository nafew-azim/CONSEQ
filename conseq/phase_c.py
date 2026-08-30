"""Phase C -- does the finding buy anything?

If consequence is carried by syntactic role, decoding should spend its determinism there:
commit (low temperature) at consequential roles, stay diverse (high temperature) elsewhere.

Three arms at MATCHED average temperature, so no arm gets a free budget advantage:
    A uniform      every position at T_mid
    B entropy-conditioned   low T where entropy is high   (the incumbent family)
    C role-conditioned      low T at consequential roles   (ours)

Arm B is the fair incumbent: entropy-adaptive decoding already exists, so beating uniform
is not the claim -- beating *entropy* at matched temperature is.
"""
import argparse, json, sys
import torch
from phase_a import trajectory, cut_at_stop, STOPS, selftest
from execjs import run
from roles import role

HOT_ROLES = {"numeric literal", "operator", "property access", "identifier"}


def decode_one(model, tok, prompt, stops, mode, t_lo, t_hi, t_mid, ent_thresh,
               max_new=320, seed=0):
    """Custom greedy-ish loop: temperature chosen per step BEFORE committing the token."""
    enc = tok(prompt, return_tensors="pt").to(model.device)
    ids = enc.input_ids
    past, out = None, []
    torch.manual_seed(seed)
    for _ in range(max_new):
        with torch.no_grad():
            o = model(input_ids=ids if past is None else ids[:, -1:],
                      past_key_values=past, use_cache=True)
        past = o.past_key_values
        logits = o.logits[0, -1, :].float()
        p = torch.softmax(logits, -1)
        H = float(-(p * torch.log(p + 1e-12)).sum())

        if mode == "uniform":
            T = t_mid
        elif mode == "entropy":                      # commit where the model is UNSURE
            T = t_lo if H >= ent_thresh else t_hi
        elif mode == "role":                         # commit where the ROLE is consequential
            peek = tok.decode([int(logits.argmax())])
            T = t_lo if role({"tok": peek}, "js") in HOT_ROLES else t_hi
        else:
            raise ValueError(mode)

        # Restrict every arm to the model's own top-2. Phase A measured consequence of the
        # NEAREST alternative; a decoder that samples the full tail is exercising substitutions
        # the measurement never covered, which is not a test of the hypothesis.
        if T <= 1e-6:
            nxt = int(logits.argmax())
        else:
            top = logits.topk(2)
            nxt = int(top.indices[int(torch.multinomial(torch.softmax(top.values / T, -1), 1))])
        if nxt == tok.eos_token_id:
            break
        out.append(nxt)
        ids = torch.cat([ids, torch.tensor([[nxt]], device=ids.device)], 1)
    return tok.decode(out[:cut_at_stop(tok, out, stops)])


def phase_c(model, tok, problems, out, n_samp=5, t_lo=0.0, t_hi=1.0, t_mid=0.5,
            ent_thresh=0.5, timeout=5.0):
    tally = {m: [0, 0] for m in ("uniform", "entropy", "role")}
    with open(out, "w") as fh:
        for prob in problems:
            pid, prompt, tests = prob["name"], prob["prompt"], prob["tests"]
            stops = prob.get("stop_tokens") or STOPS
            rec = {"problem": pid}
            for mode in ("uniform", "entropy", "role"):
                ok = 0
                for i in range(n_samp):
                    body = decode_one(model, tok, prompt, stops, mode,
                                      t_lo, t_hi, t_mid, ent_thresh, seed=7000 + i)
                    ok += run(prompt + body + "\n" + tests, timeout) == "pass"
                rec[mode] = ok / n_samp
                tally[mode][0] += ok; tally[mode][1] += n_samp
            fh.write(json.dumps(rec) + "\n"); fh.flush()
            print(f"{pid}: " + "  ".join(f"{m}={rec[m]:.1f}" for m in tally), flush=True)
    print("\n=== pass@1 (matched average temperature) ===")
    for m, (o, n) in tally.items():
        print(f"  {m:9s} {o/max(1,n):6.1%}  ({o}/{n})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    if ap.parse_args().selftest:
        selftest()
        assert role({"tok": "0"}, "js") == "numeric literal"
        assert role({"tok": " ==="}, "js") == "operator"
        assert role({"tok": "  "}, "js") == "whitespace"
        assert role({"tok": ";"}, "js") == "punctuation"
        print("phase_c selftest ok")
        sys.exit(0)
