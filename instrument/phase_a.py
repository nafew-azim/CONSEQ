"""CONSEQ Phase A: deterministic consequence by forced splice.

One greedy pass per problem gives the trajectory AND the logits. For every position we
substitute the model's own second choice, keep the original suffix, and execute.
No generation beyond that single pass.
"""
import argparse, json, math, re, shutil, sys
import torch
try:                       # selftest needs only node + torch; keep it runnable locally
    from transformers import AutoModelForCausalLM, AutoTokenizer
except ImportError:
    pass
from execjs import run, run_many, syntax_ok, SIMPLE

STOPS = ["\nfunction ", "\nconst ", "\nclass ", "\nmodule.exports", "\n//", "\n/*", "\nconsole.log"]  # fallback; MultiPL-E ships per-problem stop_tokens


def entropy(logits):
    lp = torch.log_softmax(logits.float(), -1)
    return float(-(lp.exp() * lp).sum())


def cut_at_stop(tok, ids, stops):
    """Earliest token index k such that decode(ids[:k]) reaches a stop marker."""
    full = tok.decode(ids)
    hits = [full.find(s) for s in stops if full.find(s) > 0]
    if not hits:
        return len(ids)
    ch = min(hits)
    for k in range(1, len(ids) + 1):
        if len(tok.decode(ids[:k])) >= ch:
            return k
    return len(ids)


def trajectory(model, tok, prompt, stops, max_new=320):
    enc = tok(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        g = model.generate(**enc, max_new_tokens=max_new, do_sample=False,
                           return_dict_in_generate=True, output_logits=True,
                           pad_token_id=tok.eos_token_id)
    ids = g.sequences[0][enc.input_ids.shape[1]:].tolist()
    logits = torch.stack(g.logits, 0)[:, 0, :].cpu()   # [L, V], one per emitted token
    if tok.eos_token_id in ids:            # EOS decodes to literal "<|endoftext|>" -> syntax error
        e = ids.index(tok.eos_token_id)
        ids, logits = ids[:e], logits[:e]
    k = cut_at_stop(tok, ids, stops or STOPS)
    return ids[:k], logits[:k], tok.decode(ids), k


# Per-language names for "you broke a reference", not "you made a bad decision".
# Every language spells these differently; getting the set wrong silently reclassifies
# real keystones as artifacts (or the reverse), so each language needs its own list.
# Bump when the MEANING of any emitted column changes, so a released dataset can never mix
# incompatible semantics silently. v2: timeouts excluded from K_sem and split out as K_timeout (B9).
INSTRUMENT_VERSION = 2

REF_ERRORS = {
    "js": ("ReferenceError", "TypeError"),
    "py": ("NameError", "AttributeError", "TypeError", "UnboundLocalError"),
    # Go: a renamed identifier is `undefined:`, and Go additionally errors on unused
    # variables/imports -- strictness artifacts, not decisions the model made.
    "go": ("Undefined", "UnusedVar", "UnusedImport", "TypeError"),
    "ts": ("ReferenceError", "TypeError", "Undefined"),
    "java": ("Undefined", "TypeError", "NullPointerException"),
    "rb": ("NameError", "NoMethodError", "TypeError"),
    "php": ("Error", "TypeError", "ArgumentCountError"),
    "lua": ("nil value", "attempt to"),
    "pl": ("Undefined subroutine", "Global symbol", "Can't locate"),
    "rs": ("Undefined", "TypeError"),
}


def is_artifact(tok_s, alt_s, err, lang="js"):
    """Not a decision the model made:
       - broken reference: renaming at one site while the forced suffix keeps the old name
       - BPE fragment:     '.length' -> '.l'.  NOTE '<' -> '<=' IS a real decision, so a
                           prefix relation only counts when both sides are word-like.
    """
    if err in REF_ERRORS.get(lang, REF_ERRORS["js"]):
        return True
    a, b = tok_s.strip(), alt_s.strip()
    if not (a and b and (a.startswith(b) or b.startswith(a))):
        return False
    return bool(re.search(r"\w", a)) and bool(re.search(r"\w", b))


def choose_alt(logits_t, emitted, tok, prompt, ids, t, tests, lang, mode, topk=10, temp=1.0):
    """Select the counterfactual token.

    top2  -- the model's nearest alternative. Deterministic; the default and the estimand
             reported in headline results.
    parse -- O4: walk down the ranked alternatives to the first that keeps the program
             PARSEABLE. More faithful to what a model would plausibly emit, since real models
             rarely produce syntactically invalid tokens. Biases toward common tokens, which
             must be reported: rare alternatives break syntax more often.
    temp  -- O7: sample from the model's own distribution at temperature `temp`, excluding the
             emitted token. Measures what sampling actually risks rather than the nearest
             alternative. Introduces sampling noise, so it is a robustness variant only.
    """
    ranked = logits_t.topk(topk).indices.tolist()
    cands = [c for c in ranked if c != emitted]
    if mode == "top2":
        return cands[0], 2, False
    if mode == "temp":
        pr = torch.softmax(logits_t.float() / temp, -1)
        pr[emitted] = 0.0
        return int(torch.multinomial(pr, 1)), -1, False
    for rank, c in enumerate(cands, start=2):          # mode == "parse"
        src = prompt + tok.decode(ids[:t] + [c] + ids[t + 1:]) + "\n" + tests
        if syntax_ok(src, lang):
            return c, rank, False
    return cands[0], 2, True                            # no parseable alternative found


def phase_a(model, tok, problems, out, timeout=5.0, lang="js", cf_mode="top2", cf_temp=1.0):
    fh = open(out, "w")
    kept = skipped = 0
    from collections import Counter
    reasons = Counter()
    for prob in problems:
        pid, prompt, tests = prob["name"], prob["prompt"], prob["tests"]
        ids, logits, raw, k = trajectory(model, tok, prompt, prob.get("stop_tokens"))
        if not ids:
            skipped += 1; reasons["empty"] += 1; continue
        program = prompt + tok.decode(ids) + "\n" + tests

        # determinism screen: flaky suites manufacture findings
        v = run(program, timeout, lang)
        if v != "pass" or run(program + "\n", timeout, lang) != "pass":
            skipped += 1; reasons[v if v != "pass" else "flaky"] += 1
            if reasons["shown"] < 3:
                reasons["shown"] += 1
                print(f"--- SKIP {pid} [{v}] cut={k} stops={prob.get('stop_tokens')}\n"
                      f"RAW[:500]={raw[:500]!r}\nCUT={tok.decode(ids)!r}\n---", flush=True)
            continue
        kept += 1

        top2 = logits.topk(2, dim=-1).indices          # [L, 2]
        alts, srcs, rows = [], [], []
        for t in range(len(ids)):
            if cf_mode == "top2":
                a, b = top2[t].tolist()
                alt = b if a == ids[t] else a          # model's own second choice
                alt_rank, no_parseable = 2, False
            else:
                alt, alt_rank, no_parseable = choose_alt(
                    logits[t], ids[t], tok, prompt, ids, t, tests, lang, cf_mode, temp=cf_temp)
            spliced = ids[:t] + [alt] + ids[t + 1:]
            alts.append(alt)
            srcs.append(prompt + tok.decode(spliced) + "\n" + tests)
            rows.append({
                "problem": pid, "pos": t, "n_pos": len(ids),
                "tok": tok.decode([ids[t]]), "alt": tok.decode([alt]),
                "entropy": entropy(logits[t]),
                "margin": float(torch.softmax(logits[t].float(), -1).topk(2).values.diff().abs()),
                "suffix_len": len(ids) - t,
                "equivalent": tok.decode(spliced).strip() == tok.decode(ids).strip(),
                "cf_mode": cf_mode, "alt_rank": alt_rank, "no_parseable_alt": no_parseable,
            })

        for row, verdict in zip(rows, run_many(srcs, timeout, lang=lang)):
            row["verdict"] = verdict
            row["K_syn"] = verdict == "parse_error"
            row["K_type"] = verdict.startswith("type_error")   # static type check (ts/go/java)
            # A timeout is UNMEASURED, not consequential: under CPU contention a slow toolchain
            # times out on positions that are perfectly fine. Java hit 19% this way while every
            # interpreted language stayed under 1.2%. Timeouts are their own class and are
            # excluded from K_sem entirely.
            row["K_timeout"] = verdict == "timeout"
            row["K_sem"] = verdict.startswith("fail")
            row["err"] = verdict.split(":", 1)[1] if ":" in verdict else verdict
            row["lang"] = lang
            row["iv"] = INSTRUMENT_VERSION
        # A program valid enough to pass its own tests cannot have zero parseable
        # single-token variants. If it does, the splices went to the wrong runtime.
        if rows and all(r["verdict"] == "parse_error" for r in rows):
            raise SystemExit(f"ABORT {pid}: every splice is parse_error -- wrong runtime for "
                             f"lang={lang!r}?")
        for row in rows:
            fh.write(json.dumps(row) + "\n")
        fh.flush()
        print(f"  {pid}: {len(ids)} pos, "
              f"{sum(r['K_sem'] for r in rows)} sem, {sum(r['K_syn'] for r in rows)} syn", flush=True)
    fh.close()
    print(f"kept {kept} / skipped {skipped} -> {out}")
    print("skip reasons:", dict(reasons))


def selftest():
    """The one check: does a forced splice of a known-fatal token get flagged?"""
    # mirror MultiPL-E: node:assert, self-invoking
    tests = "const assert=require('node:assert');\nassert.deepEqual(add(2,2),4);"
    good = "function add(a,b){ return a+b; }\n" + tests
    bad = "function add(a,b){ return a-b; }\n" + tests            # semantic break
    broken = "function add(a,b){ return a+; }\n" + tests          # syntactic break
    assert run(good) == "pass", run(good)
    assert run(bad) == "fail:AssertionError", run(bad)
    ref = "function add(a,b){ return q+b; }\n" + tests
    assert run(ref) == "fail:ReferenceError", run(ref)   # rename artifact, not a keystone
    assert run(broken) == "parse_error", run(broken)
    hot = torch.zeros(10); hot[3] = 50.0
    assert entropy(hot) < 0.01, entropy(hot)
    assert abs(entropy(torch.zeros(10)) - math.log(10)) < 1e-4
    eos = "function add(a,b){ return a+b; }<|endoftext|>\n" + tests
    assert run(eos) == "parse_error", "EOS text must not survive into the program"
    # Python arm: same contract, different error taxonomy
    pt = "assert add(2,2)==4\n"
    assert run("def add(a,b): return a+b\n" + pt, lang="py") == "pass"
    assert run("def add(a,b): return a-b\n" + pt, lang="py") == "fail:AssertionError"
    assert run("def add(a,b): return q+b\n" + pt, lang="py") == "fail:NameError"
    assert run("def add(a,b): return a+\n" + pt, lang="py") == "parse_error"
    assert is_artifact("a", "q", "NameError", "py") is True      # rename, not a decision
    assert is_artifact("0", "1", "AssertionError", "py") is False  # a real keystone
    assert is_artifact("a", "q", "NameError", "js") is False      # js spells it ReferenceError
    if shutil.which("javac"):
        j = ("public class Problem {\n"
             "  static int add(int a, int b) { return a + b; }\n"
             "  public static void main(String[] a) { assert(add(2,2) == 4); }\n}\n")
        assert run(j, lang="java") == "pass", run(j, lang="java")
        # THE critical check: without -ea a failing assert silently passes, and every
        # program in the run would read as correct. This must be a real failure.
        bad = run(j.replace("a + b", "a - b"), lang="java")
        assert bad == "fail:AssertionError", f"-ea not in effect? got {bad}"
        assert run(j.replace("return a + b;", "return a +;"), lang="java") == "parse_error"
        ty = run(j.replace("return a + b", 'return "x"'), lang="java")
        assert ty.startswith("type_error"), f"java type error must be its own bucket, got {ty}"
        print("java selftest ok")
    # table-driven interpreted languages: verify each arm end-to-end where the runtime exists
    for _l, _prog in (
        ("rb",  ("def add(a,b)\n  a+b\nend\nraise unless add(2,2)==4\n",
                 "a-b", "def add(a,b)\n  a+\nend\n", "q+b", "NameError")),
        ("php", ("<?php\nfunction add($a,$b){ return $a+$b; }\nif(add(2,2)!=4) throw new Exception();\n",
                 "$a-$b", "<?php\nfunction add($a,$b){ return $a+; }\n", "$q+$b", None)),
    ):
        if not shutil.which(SIMPLE[_l]["run"][0]):
            continue
        good, bad_sub, broken, ref_sub, ref_err = _prog
        assert run(good, lang=_l) == "pass", (_l, run(good, lang=_l))
        assert run(good.replace("a+b" if _l == "rb" else "$a+$b", bad_sub),
                   lang=_l).startswith("fail"), _l
        assert run(broken, lang=_l) == "parse_error", (_l, run(broken, lang=_l))
        print(f"{_l} selftest ok")

    # rustc alone is not enough -- Rust needs a working linker, and a machine without one
    # produces environment failures rather than code verdicts. Probe before asserting.
    if shutil.which("rustc") and run("fn main() {}\n", lang="rs") == "pass":
        # Rust must show the same three-way split as Go/TS, or the third static discipline
        # adds nothing. Assert each bucket independently.
        g = ("fn add(a: i64, b: i64) -> i64 { a + b }\n"
             "fn main() { assert_eq!(add(2,2), 4); }\n")
        assert run(g, lang="rs") == "pass", run(g, lang="rs")
        assert run(g.replace("a + b", "a - b"), lang="rs").startswith("fail"), "runtime"
        assert run(g.replace("{ a + b }", "{ a + }"), lang="rs") == "parse_error"
        ty = run(g.replace("a + b", '"x"'), lang="rs")
        assert ty.startswith("type_error"), f"rust type error must be its own bucket, got {ty}"
        print("rust selftest ok")

    if shutil.which("tsc"):
        # TS must show the same three-way split as Go, or the JS-vs-TS comparison is meaningless
        # mirror MultiPL-E's TS harness exactly: it declares `require` itself, because tsc
        # has no Node type declarations. A selftest that does not match production manufactures
        # confidence (see B8).
        t = ('function add(a: number, b: number): number { return a + b; }\n'
             'declare var require: any;\nconst assert = require("node:assert");\n'
             'assert.deepEqual(add(2,2), 4);\n')
        assert run(t, lang="ts") == "pass", run(t, lang="ts")
        assert run(t.replace("a + b", "a - b"), lang="ts").startswith("fail")
        assert run(t.replace("return a + b;", "return a +;"), lang="ts") == "parse_error"
        ty = run(t.replace("return a + b", 'return "x"'), lang="ts")
        assert ty.startswith("type_error"), f"TS type error must be its own bucket, got {ty}"
        print("ts selftest ok")
    if shutil.which("go"):
        # Go is the three-way case: parse / type / runtime must be distinguishable, which is
        # the whole reason for running it. Assert each bucket separately.
        g = ('package add_test\nimport "testing"\n'
             'func add(a int, b int) int { return a + b }\n'
             'func TestAdd(t *testing.T) { if add(2,2) != 4 { t.Errorf("bad") } }\n')
        assert run(g, lang="go") == "pass", run(g, lang="go")
        assert run(g.replace("a + b", "a - b"), lang="go").startswith("fail"), "runtime failure"
        assert run(g.replace("return a + b", "return a +"), lang="go") == "parse_error"
        typ = run(g.replace("return a + b", 'return "x"'), lang="go")
        assert typ.startswith("type_error"), f"static type error must be its own bucket, got {typ}"
        assert is_artifact("a", "q", "Undefined", "go") is True
        assert is_artifact("0", "1", "Assertion", "go") is False
        print("go selftest ok")
    print("selftest ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--model", default="Qwen/Qwen2.5-Coder-1.5B")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--out", default="phase_a.jsonl")
    a = ap.parse_args()
    if a.selftest:
        selftest(); sys.exit(0)

    from datasets import load_dataset
    ds = load_dataset("nuprl/MultiPL-E", "humaneval-js", split="test")
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(a.model)
    model = AutoModelForCausalLM.from_pretrained(
        a.model, torch_dtype=torch.float16 if dev == "cuda" else torch.float32).to(dev).eval()
    phase_a(model, tok, list(ds)[:a.n], a.out)
