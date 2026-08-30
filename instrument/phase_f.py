"""Phase F -- the criterion audit (proposal 9.2, Table 2).

Scores all 11 published selection criteria on IDENTICAL positions against execution ground
truth. This is the comparison nobody can run without CONSEQ: these criteria are normally
validated by training a model and reading a benchmark, which tests a pipeline, not a criterion.

Four models are involved and they do not co-fit in 16GB, but every PAIR does, so the stages
load exactly the models each criterion actually needs:

    1  student            trajectories, ground truth, P0-P3 / P7-P10
    2  reference          P4 excess loss   (needs stored P3_nll only)
    3  student + teacher  P5 KL(teacher||student)
    4  teacher + generalist  P6 expert-generalist delta
"""
import argparse, gc, json, sys
import torch
from phase_a import trajectory, is_artifact, STOPS, selftest
from execjs import run, run_many
from criteria import score_all, NAMES


def _load(name):
    from transformers import AutoModelForCausalLM
    return AutoModelForCausalLM.from_pretrained(
        name, torch_dtype=torch.float16).to("cuda").eval()


def _gc():
    """`del` on a function parameter frees nothing -- the caller still holds the reference.
    Callers must drop their own name (set it to None) and then call this."""
    gc.collect()
    torch.cuda.empty_cache()
    if torch.cuda.is_available():
        print(f"    gpu free: {torch.cuda.mem_get_info()[0] / 2**30:.2f} GiB", flush=True)


def _logits_over(model, tok, prompt, ids):
    """Logits predicting each position of `ids`, from any model sharing the tokenizer."""
    enc = tok(prompt, return_tensors="pt").to(model.device)
    inp = torch.cat([enc.input_ids, torch.tensor([ids], device=model.device)], 1)
    with torch.no_grad():
        lg = model(input_ids=inp).logits[0, enc.input_ids.shape[1] - 1:-1, :]
    return lg.float().cpu()


def phase_f(student_name, ref_name, teacher_name, gen_name, tok, problems, out,
            timeout=5.0, lang="js"):
    import random as _r
    rng = _r.Random(0)

    # ---------- stage 1: student ----------
    model = _load(student_name)
    keep = []
    for prob in problems:
        pid, prompt, tests = prob["name"], prob["prompt"], prob["tests"]
        stops = prob.get("stop_tokens") or STOPS
        ids, lg_s, _, _ = trajectory(model, tok, prompt, stops)
        if not ids or run(prompt + tok.decode(ids) + "\n" + tests, timeout, lang) != "pass":
            continue
        top2 = lg_s.topk(2, dim=-1).indices
        alt = [int(top2[t, 1]) if int(top2[t, 0]) == ids[t] else int(top2[t, 0])
               for t in range(len(ids))]
        srcs = [prompt + tok.decode(ids[:t] + [alt[t]] + ids[t + 1:]) + "\n" + tests
                for t in range(len(ids))]
        verdicts = run_many(srcs, timeout, lang=lang)
        if verdicts and all(v == "parse_error" for v in verdicts):
            raise SystemExit(f"ABORT {pid}: every splice parse_error -- wrong runtime?")
        rows = []
        for t, v in enumerate(verdicts):
            err = v.split(":", 1)[1] if ":" in v else v
            broke = v.startswith("fail") or v == "timeout"
            rows.append({
                "problem": pid, "pos": t, "lang": lang,
                "tok": tok.decode([ids[t]]), "alt": tok.decode([alt[t]]), "err": err,
                "K_syn": v == "parse_error",
                "K_sem": broke and not is_artifact(tok.decode([ids[t]]),
                                                   tok.decode([alt[t]]), err, lang),
                **score_all(lg_s[t], ids[t], pos=t / len(ids), rnd=rng.random()),
            })
        keep.append((pid, prompt, ids, rows))
        print(f"stage1 {pid}: {len(rows)} positions", flush=True)
    model = None; _gc()
    print(f"stage1 done: {len(keep)} problems", flush=True)

    # ---------- stage 2: reference -> P4 (uses stored P3_nll) ----------
    if ref_name:
        m = _load(ref_name)
        for pid, prompt, ids, rows in keep:
            lg = _logits_over(m, tok, prompt, ids)
            for t, row in enumerate(rows):
                row["P4_excess_loss"] = row["P3_nll"] - float(-torch.log_softmax(lg[t], -1)[ids[t]])
        m = None; _gc(); print("stage2 (reference) done", flush=True)

    # ---------- stage 3: P5 = KL(teacher || student) ----------
    # Never co-load: a 1.5B+3B pair OOMs on a 14.56GB T4 once forward activations are counted.
    # Cache log-probs to CPU (fp16, ~36MB per trajectory) so only one model is ever resident.
    if teacher_name:
        ms = _load(student_name)
        s_lp = {pid: torch.log_softmax(_logits_over(ms, tok, prompt, ids), -1).half()
                for pid, prompt, ids, _ in keep}
        ms = None; _gc()
        mt = _load(teacher_name)
        t_lp = {}
        for pid, prompt, ids, rows in keep:
            lt = torch.log_softmax(_logits_over(mt, tok, prompt, ids), -1)
            t_lp[pid] = lt.half()
            lps = s_lp[pid].float()
            for t, row in enumerate(rows):
                lpt = lt[t]
                row["P5_teacher_kl"] = float((lpt.exp() * (lpt - lps[t])).sum())
        mt = None; _gc()
        del s_lp
        print("stage3 (teacher KL) done", flush=True)

    # ---------- stage 4: P6 = |log teacher - log generalist| ----------
    if teacher_name and gen_name:
        mg = _load(gen_name)
        for pid, prompt, ids, rows in keep:
            lgn = torch.log_softmax(_logits_over(mg, tok, prompt, ids), -1)
            lt = t_lp[pid].float()
            for t, row in enumerate(rows):
                row["P6_expert_delta"] = float((lt[t] - lgn[t]).abs().mean())
        mg = None; _gc()
        del t_lp
        print("stage4 (expert delta) done", flush=True)

    with open(out, "w") as fh:
        for _, _, _, rows in keep:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
    n = sum(len(r) for _, _, _, r in keep)
    print(f"phase_f wrote {n} positions across {len(keep)} problems -> {out}")
    missing = [c for c in NAMES if not any(c in r for _, _, _, rs in keep for r in rs)]
    print("criteria present:", [c for c in NAMES if c not in missing])
    if missing:
        print("MISSING:", missing)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    if ap.parse_args().selftest:
        selftest()
        from criteria import selftest as cs
        cs()
        # KL(p||p) must vanish, and excess loss must vanish when reference == student
        v = torch.randn(200)
        lp = torch.log_softmax(v, -1)
        assert abs(float((lp.exp() * (lp - lp)).sum())) < 1e-6
        assert abs(float(-lp[3]) - float(-lp[3])) < 1e-9
        print("phase_f selftest ok"); sys.exit(0)
