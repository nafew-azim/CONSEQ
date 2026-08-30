# CONSEQ — Datasheet

**Execution-grounded per-token consequence in code generation.**
143,786 positions · 14 models · 9 families · 9 languages · 3 benchmarks · 28 configurations.
Instrument version 2. Companion to `FINDINGS.md`.

---

## 1. What is measured

For every token position in a **verified-correct** model trajectory, CONSEQ records what happens when
the model's *own second choice* is substituted at that position and the program is re-executed.

The counterfactual is always the model's **top-2 alternative** — never an arbitrary token, never
another model's choice. This matters for interpretation: CONSEQ measures the consequence of *the
nearest decision the model could have made*, not the consequence of arbitrary corruption.

---

## 2. Columns

| column | type | meaning |
|---|---|---|
| `problem` | str | benchmark task id |
| `pos` | int | token index within the generated completion |
| `n_pos` | int | completion length in tokens |
| `tok` / `alt` | str | the emitted token and the model's second choice |
| `verdict` | str | `pass` / `fail:<Class>` / `type_error:<Class>` / `parse_error` / `timeout` |
| `err` | str | error class parsed from the runtime's stderr |
| **`K_syn`** | bool | substitution **fails to parse** |
| **`K_type`** | bool | parses but **fails static type checking** — see §4 |
| **`K_sem`** | bool | parses, type-checks, but **fails its tests** |
| **`K_timeout`** | bool | execution timed out — **unmeasured, not consequential** (§5) |
| `entropy` | float | Shannon entropy of the model's distribution at this position |
| `margin` | float | p(top-1) − p(top-2) |
| `suffix_len` | int | tokens remaining after this position |
| `equivalent` | bool | substitution is AST-equivalent after normalisation |
| `lang` / `typing` | str | language, and `dynamic` / `gradual` / `static` |
| `model` / `family` / `params` | str | provenance |
| `iv` | int | instrument version (2 throughout this release) |

---

## 3. THE critical caveat: `K_sem` is language-conditional

**`K_sem` is not comparable across languages with different type disciplines.** This is a measured
property of the data, not a hypothetical concern:

| discipline | languages | `K_sem` |
|---|---|---|
| dynamic | JavaScript, Python, Ruby, PHP, Perl | **24.7 – 37.3%** |
| gradual / static | TypeScript, Go, Java, Rust | **9.6 – 13.2%** |

Static checking converts what would be a silent logic fault in a dynamic language into a
**compile-time** fault. The consequence does not disappear — it moves from `K_sem` into `K_type`.
And the amount that moves scales with checker strictness: `K_type` runs Rust 24–29% > Java 20–22% >
TypeScript 18–19% > Go 13–15%, in the same order across two independent model families.

**Therefore:** to compare consequence across languages, use `K_sem + K_type`, never `K_sem` alone.
A method tuned on Python token importance is not optimising the same quantity as one tuned on Rust.

---

## 4. `K_type` availability

`K_type` is meaningful only where the toolchain has a type-check phase separable from parsing:

| language | how the split is obtained |
|---|---|
| TypeScript | `tsc` error codes — TS1xxx = syntax, TS2xxx+ = type |
| Go | `gofmt -e` parses without type-checking; `go test` type-checks and runs |
| Java | `javac` diagnostics |
| Rust | bare `error:` = syntax; `error[E….]` = type/borrow |
| JS / Python / Ruby / PHP / Perl | **always `false`** — no separate phase exists |

---

## 5. Timeouts are unmeasured, not consequential

`K_timeout` is excluded from `K_sem` by construction. A slow toolchain under CPU contention times out
on positions that are perfectly fine — Java initially showed a 19.0% timeout rate against ≤1.4%
elsewhere, and counting those as consequence produced a `K_sem` of 26.9% that *contradicted* the
typing result. With timeouts excluded it is 11.2%. Treat `K_timeout` rows as missing data.

---

## 6. Instrument artifacts — filter before analysis

34.0% of raw `K_sem` positions are **artifacts of the instrument**, not decisions the model made:

| artifact | share | detection |
|---|---|---|
| inconsistent-reference mutants | 29.7% | renaming at one site breaks a reference: `ReferenceError` (JS), `NameError` (Python), `undefined:` (Go), `Cannot find name` (TS) |
| BPE fragment alternatives | 4.3% | `.length` → `.l`: tokenizer truncation. **Careful:** `<` → `<=` is also a prefix relation but IS a genuine decision — only flag when *both* sides are word-like |
| equivalent mutants | 0.0% of `K_sem` (2.7% of all positions) | AST-identical after normalisation; by construction these cannot fail a test, so a non-zero share would mean the normaliser is broken |

**Artifact rates are tokenizer-specific** — 19.9–46.2% across the six adequately-powered families (up to 56% in the smallest, on a few hundred positions). Re-validate the
filter on any new model family rather than assuming it transfers. Reference implementation:
`is_artifact()` in `phase_a.py`.

---

## 7. Known limitations

- **Correct trajectories only.** CONSEQ measures where correctness was *decided*, not where failure
  *originates*. Failing-trajectory analysis needs different ground truth.
- **Single-token perturbations.** Marginal effects do compose well on a fixed sequence (93.2% survival
  across ~23 simultaneous free substitutions), but they do **not** transfer once decoding leaves the
  trajectory — a perfect oracle buys nothing at decode time. Valid for **editing**, not **steering**.
- **Greedy trajectories** at temperature 0. Sampled-trajectory behaviour is unmeasured.
- **Retention varies sharply by model.** Older and non-code-specialised models solve few problems —
  InCoder-1B keeps 11 of 161. Three runs are flagged `underpowered` (<25 problems) in the manifest:
  `o_codegen` (15 problems), `o_incoder` (11), `o_phi2` (20). Excluded from headline claims, retained for coverage.
- **Language coverage is uneven.** JavaScript is 40.0% of positions; Ruby and Rust are 3.0% and 3.9%.
- **Benchmark-derived.** HumanEval and MBPP via MultiPL-E, plus original HumanEval for Python.
  Idioms are benchmark idioms, not repository code.

---

## 8. Provenance and reproducibility

`conseq_manifest.json` records per run: directory, model, family, parameters, language, instrument
version, positions, problems, clean-consequential count, and the underpowered flag.

**Determinism verified.** Re-running the same model and dataset in a fresh kernel reproduces position
counts exactly (5,097 → 5,097; 4,555 → 4,555; 3,613 → 3,613). Greedy trajectories, splice sets and
verdicts are stable across sessions.

**Assembly refuses to merge incompatible rows.** `K_sem` changed meaning at instrument v2 (timeouts
excluded); v1 rows are quarantined rather than pooled. All 12 v1 runs in this release have been
superseded by v2 re-runs, and a v1→v2 coverage diff guards against silent problem-count regressions.

Build: `python3 assemble.py` → `conseq.jsonl` + `conseq_manifest.json`.
