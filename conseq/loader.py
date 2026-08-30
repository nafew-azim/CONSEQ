"""Normalize problem sets to one schema: name / prompt / tests / stop_tokens.

MultiPL-E covers 24 target languages but NOT Python -- Python is the source it translates
from. Python therefore comes from the original openai_humaneval, which has a different
schema (a `check(candidate)` function plus an entry_point) and needs its own stop tokens.
"""

PY_STOPS = ["\ndef ", "\n#", "\nif ", "\nclass ", "\nprint(", "\n@", "\nassert "]


def load_problems(name, n, lang="js"):
    from datasets import load_dataset
    if name == "openai_humaneval":
        ds = load_dataset("openai/openai_humaneval", split="test")
        out = []
        for r in list(ds)[:n]:
            out.append({
                "name": r["task_id"].replace("/", "_"),
                "prompt": r["prompt"],
                # the suite defines check(candidate); it must actually be invoked
                "tests": r["test"] + f"\ncheck({r['entry_point']})\n",
                "stop_tokens": PY_STOPS,
            })
        return out
    ds = list(load_dataset("nuprl/MultiPL-E", name, split="test"))[:n]
    if lang == "pl":
        # MultiPL-E Perl defines `sub testhumaneval` but never calls it -- the same shape as
        # the Go bug (B8). Without the invocation every program trivially "passes".
        for r in ds:
            if "testhumaneval" in r["tests"] and "testhumaneval()" not in r["tests"]:
                r["tests"] = r["tests"] + "\ntesthumaneval();\n"
    return ds


def selftest():
    p = load_problems("openai_humaneval", 3, "py")
    assert len(p) == 3
    r = p[0]
    assert {"name", "prompt", "tests", "stop_tokens"} <= set(r)
    assert "check(" in r["tests"], "the check() harness must be invoked, not just defined"
    assert r["prompt"].strip(), "empty prompt"
    # the canonical solution plus the test harness must actually pass, or the loader is wrong
    from execjs import run
    from datasets import load_dataset
    d = list(load_dataset("openai/openai_humaneval", split="test"))[0]
    prog = d["prompt"] + d["canonical_solution"] + "\n" + p[0]["tests"]
    v = run(prog, 10.0, "py")
    assert v == "pass", f"canonical solution must pass, got {v}"
    print("loader selftest ok")


if __name__ == "__main__":
    selftest()
