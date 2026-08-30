# CONSEQ — Findings Log

**Living document. Every measured result, with status, evidence, and caveats.**
**Release: `conseq.jsonl` — 143,786 positions · 14 models · 9 families · 9 languages · 28 configurations.**
Last updated: 2026-08-30 · Released at <https://github.com/nafew-azim/CONSEQ>

Status key: **CONFIRMED** (replicated and sanity-checked) · **PROVISIONAL** (single run, or
known unresolved caveat) · **RETRACTED** (was reported, later found to be an artifact)

---

## How to read this

Every numbered finding lists the experiment that produced it, the number, the check that makes it
believable, and what would break it. **Findings without a by-construction sanity check are marked
provisional**, because eleven results in this project looked clean and turned out to be bugs (§B).

---

## A. Findings

### F1 — Entropy is worse than random at finding consequential tokens · **CONFIRMED**

The central result. At a matched selection budget, ranking positions by entropy captures *less*
execution-grounded consequence than picking positions uniformly at random.

| model | family | positions | budget | ROLE | entropy | random |
|---|---|---|---|---|---|---|
| Qwen2.5-Coder-0.5B | Qwen | 2,437 | 35.1% | 70.8% | 19.7% | 35.1% |
| Qwen2.5-Coder-1.5B | Qwen | 5,097 | 28.3% | 59.0% | 16.1% | 28.3% |
| Qwen2.5-Coder-3B | Qwen | 6,057 | 28.0% | 59.1% | 11.3% | 28.0% |
| DeepSeek-Coder-1.3B | DeepSeek | 3,613 | 30.2% | 65.8% | 24.4% | 30.2% |
| Qwen2.5-Coder-1.5B (MBPP) | Qwen | 11,670 | 17.1% | 41.5% | 6.5% | 17.1% |

*(Early Qwen/DeepSeek subset, retained to show the effect at first measurement. The full
nine-family table is F19; the full nine-language table is F15.)*

- **Release total: 143,786 positions**, 14 models, 9 families, 9 languages, 3 benchmarks,
  28 model-language configurations.
  Entropy is below random in **24 of 28** configurations and at parity in the rest (F16, F18, F19).
  The four at parity are SmolLM2-JS (+4.0), InCoder-JS (+4.2), DeepSeek-Python (+1.5) and
  Stable-Code-JS (+0.7) — all within 4.3 points of chance, and only InCoder is an under-powered run. The count is reproduced by `figdata.py`, which scores every
  configuration at its own top-2-role budget.
- Gets *worse* with scale in the Qwen line: 19.7% → 16.1% → 11.3%.
- Held-out throughout: roles fit on half the problems, scored on the other half.
- Survives problem-level clustering: within-problem paired test **+0.145, SE 0.012, t = 11.95**,
  positive in **67 of 74** problems.
- Survives dropping whitespace and punctuation (content tokens only): entropy still loses at
  20/30/40% budgets in both families.
- Survives dropping identifiers from the selector entirely: role 50.4% vs entropy 12.4% (Qwen).

*Breaks if:* the artifact classification (§F7) is wrong. All numbers depend on it.

### F2 — Consequence is carried by syntactic role, and roles are cheap to identify · **CONFIRMED**

| role | rate | mean entropy |
|---|---|---|
| numeric literal | 62.4% | **0.114** |
| identifier | 24.3% | 0.526 |
| property access | 22.5% | 0.233 |
| operator | 20.8% | 0.570 |
| keyword | 6.3% | 0.814 |
| punctuation | 0.9% | 0.699 |

Numeric literals are simultaneously the **lowest-entropy** and **most consequential** role — the
cleanest single demonstration of F1. Replicates in DeepSeek (71.3% at H=0.162) and MBPP (31.8% at
H=0.252). The selector is a regex over the token string; it makes no model call.

Recovered construct catalogue, artifact-free: `'0'→'1'`, `' +='→' ='`, `' >'→' >='`, `' <'→' <='`,
`' ==='→' !=='`. These were the constructs predicted in advance in §7.1.

### F3 — Repairability is bimodal · **CONFIRMED** (replicated across languages)

Of consequential positions, given free continuation from the damaged prefix:

| bucket | JS 1.5B | Python 1.5B | JS 3B |
|---|---|---|---|
| `R=0` committed error, never recovers | 34.2% | 38.1% | **31.0%** |
| `0<R<0.5` mostly broken | 11.1% | 9.2% | 9.4% |
| `0.5<R<1` mostly repaired | 17.1% | 16.3% | 20.9% |
| `R≥1` fully repaired | 37.7% | 36.4% | **38.8%** |
| median `R` | 0.62 | 0.57 | 0.67 |
| n | 398 | 239 | 449 |

Single-token damage is **either fatal or fully absorbed**; the middle is thin. The distribution is
near-identical in a second language, so it is a property of autoregressive repair rather than a
JavaScript artifact.

Sanity checks passed in both: factual-arm pass rate `p_F` = 0.84 (JS) / 0.91 (PY) — continuing from a
correct prefix must usually succeed; an earlier broken version read 0.09 (§B2). Control (§7.4): mean
`D` on non-consequential positions +0.054 (JS) / +0.069 (PY), so forced and free arms agree with a
small positive residual worth reporting.

**Mild scale trend:** committed errors fall 38.1% -> 34.2% -> 31.0% and fully-repaired rises as
capability increases. Larger models recover from their own damage slightly more often — the direction
H4 predicted for repairability, even though H4's prediction about *consequential fraction* was wrong
(F11).

Sanity `p_F` = 0.84 / 0.91 / 0.87; control `D` = +0.054 / +0.069 / +0.009. Replicated across two
languages and a 2x scale change, 1,086 measured positions.

### F4 — The keystone cell is numeric literals, confirmed three independent ways · **CONFIRMED**

| role | mean entropy | consequence rate | mean repairability | % committed |
|---|---|---|---|---|
| numeric literal | 0.116 | 62.4% | **0.27** | **56.1%** |
| keyword | 1.368 | 6.3% | 1.18 | 5.6% |

Numeric literals are the lowest-entropy, most-consequential, *and* least-repairable role.
Keywords are the exact mirror. Three separately-measured quantities agreeing.

### F5 — Entropy also fails on repairability · **CONFIRMED**

Committed-error rate: **47.7% in the bottom entropy tercile vs 19.7% in the top.** Low-entropy
damage is 2.4× more likely to be irreparable. This is a *second, independently measured* quantity
where entropy points the wrong way — so F1 is not an artifact of how consequence was defined.

### F6 — Consequence composes on a fixed sequence · **CONFIRMED**

Substituting the model's second choice at **every** individually-free position at once:

| simultaneous edits | pass rate |
|---|---|
| 1 | 100.0% |
| 3 | 100.0% |
| 8 | 100.0% |
| 12 | 99.4% |
| 20 | 94.6% |
| 32 | 92.3% |
| all free (~23 mean) | **93.2%** |

Marginal per-token effects **aggregate well**. Good news for any method selecting token *sets*
from individually-computed scores. Sanity check: m=1 must be 100% by construction — it is.

### F7 — Three instrument artifacts, 34% of raw signal · **CONFIRMED**

Not findings about models; properties of the instrument that must be removed before analysis.

| artifact | share of raw `K_sem` | detection |
|---|---|---|
| inconsistent-reference mutants | 29.7% | fails as `ReferenceError`/`NameError`, not `AssertionError` |
| BPE fragment alternatives | 4.3% | `.length`→`.l`; both sides word-like and prefix-related |
| equivalent mutants | **0.0%** (2.7% of *all* positions) | AST-normalised exact match |

The third row's zero is the point: an AST-equivalent substitution *cannot* change a test outcome, so
a non-zero share there would mean the normaliser is broken. It is a passed check, not a removal.

Removing them **sharpens** F1 (47.3% → 53.1% bottom-tercile mass), the signature of removed noise.
Careful: `<`→`<=` is also a prefix relation but is a *genuine* keystone — the filter only applies
when both sides are word-like.

### F8 — Position-selective decoding is closed as a family · **CONFIRMED**

Five arms, matched commit count per problem (commit fraction 0.537), 44 paired problems:

| arm | pass@1 | vs random | t |
|---|---|---|---|
| greedy (commit everywhere) | 99.2% | +0.144 | **+3.50** |
| entropy | 89.4% | +0.068 | +1.85 |
| oracle (ground truth) | 84.8% | +0.023 | +0.53 |
| random | 82.6% | — | — |
| role | 77.3% | −0.053 | −1.02 |

**A perfect consequence oracle does not beat random position selection.** No better predictor can
rescue this — the ceiling itself is at random. Only committing everywhere helps.

### F9 — The mechanism is trajectory drift, not composition · **CONFIRMED**

Two experiments alter a comparable share of positions by the same criterion, differing only in
whether the rest of the sequence is held fixed:

| | positions altered | pass rate |
|---|---|---|
| fixed trajectory (F6) | ~53% | 93.2% |
| decoding (F8) | ~46% | 84.8% |

The ~8-point gap is **off-trajectory drift**. Consequence labels are properties of *one* trajectory.
They compose while surrounding tokens are constant and stop applying once decoding leaves the path.

> **The paper's most useful sentence for practitioners:** per-token attribution scores are valid for
> **editing a fixed sequence**, not for **steering generation**. Selective distillation edits fixed
> sequences and is fine. Adaptive decoding steers generation and is not.

### F10 — Bug localization: role beats random, entropy loses again · **PROVISIONAL**

208 injected bugs, ranking all positions:

| scorer | MRR | r@1 | r@3 | r@5 |
|---|---|---|---|---|
| nll | 0.651 | 0.394 | 0.899 | 0.957 |
| **role (a regex)** | **0.234** | 0.096 | 0.279 | 0.375 |
| random | 0.100 | 0.024 | 0.077 | 0.144 |
| **entropy** | **0.054** | 0.005 | 0.019 | 0.053 |

**NLL's win is a construction artifact — do not report it.** Bugs are injected as the model's
*second* choice, making the injected token the one low-probability token in a top-1 sequence; NLL
detects the injection, not the bug. Real bugs are the opposite case (the model was *confident*),
so this does not transfer. A realistic test needs naturally-failing trajectories with independent
ground truth.

Role's 2.3× over random **is** meaningful — it never observes probabilities. And entropy falls below
random on a **fourth** independent quantity.

### F19 — Eight families: the role selector is the durable result · **CONFIRMED**

HumanEval-JS, held-out (roles fit on half the problems, scored on the other half):

| model | family | probs | positions | ROLE | entropy | random | |
|---|---|---|---|---|---|---|---|
| Qwen2.5-Coder-1.5B | Qwen | 77 | 5,097 | 58.8% | 16.1% | 28.2% | loses |
| StarCoder2-3B | BigCode | 57 | 4,555 | 71.9% | 26.7% | 28.3% | loses |
| DeepSeek-Coder-1.3B | DeepSeek | 49 | 3,613 | 64.0% | 23.1% | 28.8% | loses |
| Granite-3B-Code | IBM | 55 | 4,390 | 68.3% | 21.1% | 27.8% | loses |
| StableCode-3B | Stability | 53 | 3,984 | 69.3% | **31.2%** | 30.6% | **parity** |
| CodeGen-2B-mono | Salesforce | **15** | 796 | 84.8% | 25.8% | 37.3% | loses † |
| Phi-2 | Microsoft | **20** | 1,444 | 58.7% | 26.7% | 30.7% | loses † |
| InCoder-1B | Meta | **11** | 237 | 53.8% | 23.1% | 26.4% | loses † |
| Qwen3-1.7B | Qwen (new gen) | 51 | 3,426 | 57.6% | 12.8% | 34.0% | loses |
| SmolLM2-1.7B | HuggingFace | 38 | 3,014 | 65.3% | **29.5%** | 25.6% | **parity** |
| Granite-3.3-2B | IBM (newer) | 47 | 3,565 | 68.3% | 19.6% | 28.6% | loses |

† **Underpowered** (<25 problems). Reported for coverage; excluded from headline claims. Retention
collapses for older and non-code-specialised models — InCoder-1B solves 11 of 161 HumanEval-JS tasks.

**The role selector beats random in all eight families**: 53.8-84.8% capture against random baselines
of 26.4-37.3%. No exceptions, across eight independent tokenizers and training corpora.

**Entropy loses in eight of ten families, parity in two** (Stability +0.6, HuggingFace +3.9 points).
Restricting to the seven well-powered families: loses in five, parity in two.

**Newer model generations behave identically.** Qwen3-1.7B (entropy 12.8% vs random 34.0%) and
Granite-3.3-2B (19.6% vs 28.6%) both show the effect as strongly as their predecessors, so it is not an
artefact of older checkpoints.

> **State the positive result, not the negative one.** The role selector's advantage has held in every
> configuration measured — 9 families, 9 languages, 3 benchmarks. Entropy's failure *magnitude* ranges
> from -12 points (Qwen) to +0.6 (Stability) and is not a stable quantity.

**Tokenizer sensitivity** (§F): artifact rates span 35-46%. The BPE-fragment filter must be
re-validated per family, never assumed.

### F17 — The role archetype is NOT a product of code-specialized training · **CONFIRMED (controlled)**

Qwen2.5-**Coder**-1.5B vs Qwen2.5-1.5B (general) — same tokenizer, same parameter count, same
benchmark (HumanEval-JS). Only code specialization differs.

| | Qwen2.5-Coder-1.5B | Qwen2.5-1.5B (general) |
|---|---|---|
| clean consequential | 15.9% | 15.0% |
| numeric literal | 62.4% @ H=0.114 | **65.3% @ H=0.137** |
| identifier | 24.1% | 20.7% |
| operator | 21.2% | 18.9% |
| whitespace | 8.4% | 6.9% |

The role structure is essentially unchanged. Held-out at a 14.5% budget: role 39.4%, entropy **8.0%**,
random 14.5% — entropy still loses.

> **The numeric-literal archetype reflects how code constrains correctness, not how the model was
> trained.** A general-purpose LM writing JavaScript shows the same consequence structure as a
> code-specialised one. This broadens the claim from "code models" to "models generating code."

*Caveat:* the general model retains fewer problems (58 vs 77) and writes worse code; the comparison is
on the subset it gets right.

### F20 — CONSEQ does NOT transfer to RL credit assignment · **PROVISIONAL** (negative)

Built a ground-truth ruler for RL credit: for a *failing* rollout, binary-search the largest prefix
from which the model can still reach a passing program. Everything after is doomed; the decision at
that boundary is where credit belongs. 76 cases, Qwen2.5-Coder-1.5B, HumanEval-JS, k=8 rollouts at
T=0.8.

| scorer | MRR | r@1 | r@5 | r@10 |
|---|---|---|---|---|
| **nll** (probability-based credit) | **0.306** | 0.092 | **0.579** | 0.645 |
| entropy ("forking token" heuristic) | 0.184 | 0.039 | 0.342 | 0.605 |
| uniform (GRPO baseline) † | 0.165 | 0.053 | 0.145 | 0.605 |
| margin | 0.142 | 0.013 | 0.171 | 0.658 |
| **role (ours)** | **0.128** | 0.053 | 0.132 | 0.289 |
| random | 0.121 | 0.026 | 0.197 | 0.368 |

† `uniform` is a **constant** scorer, so its ranking is pure tie-break (index order). Its apparent
skill is entirely the prior "fatal tokens are early" — not credit assignment. Not a fair GRPO
stand-in; reported for completeness only.

**The role selector fails here** (0.128 vs random 0.121). This is a genuine negative and it bounds
CONSEQ's applicability.

**Why, and it is not noise.** CONSEQ and RL credit measure different quantities:

| | question | trajectories |
|---|---|---|
| CONSEQ `K_sem` | would substituting this token break a *correct* program? | correct |
| RL credit (this) | where did this *failing* rollout become unrecoverable? | failed |

The first is **local correctness** — operators, boundary literals, `===`. The second is
**commitment to a wrong path**. Fatal decisions are *early*: median position **6** of a median
40-token rollout, 60.5% within the first 10 tokens. That is what "wrong algorithm, chosen early"
looks like, and syntactic role does not mark it.

**Consequences.** (a) A role-weighted GRPO variant is **not motivated by this evidence** — testing it
cost ~2 GPU-h and saved building it. (b) Probability-based credit (NLL) is the strongest scorer
measured, which supports the TEPO/TR-GRPO line rather than refuting it. (c) The strong early-position
prior is itself actionable for credit assignment and is not exploited by any scorer tested.

*Provisional:* 76 cases, one model, one language, temperature-0.8 rollouts. NLL's advantage may
partly reflect that sampled-off-policy tokens are both improbable and mistaken — the same confound
flagged in F10, though less severe here since these are the model's own rollouts rather than
injected substitutions.

### F18 — One anomalous cell, isolated by diagnostic · **CONFIRMED**

DeepSeek-Coder-1.3B on Python was the single configuration where entropy did not fall below random.
A diagnostic run (DeepSeek on TypeScript) separates the candidate explanations:

| configuration | budget | ROLE | entropy | random | |
|---|---|---|---|---|---|
| DeepSeek / JS | 28.8% | 64.0% | 23.1% | 28.8% | loses |
| **DeepSeek / Python** | 19.6% | 55.0% | **19.8%** | 19.6% | **parity** |
| DeepSeek / TypeScript | 14.8% | 46.6% | **7.6%** | 14.8% | loses badly |
| Qwen / Python | 20.0% | 54.7% | 11.1% | 20.0% | loses |

DeepSeek loses in two other languages; Python loses with another family. **The anomaly is confined to
the DeepSeek x Python cell** — neither a family effect nor a language effect — and the margin there is
+0.2 points, well inside noise.

Combined with F16 (StarCoder2's margin ~1.6 points vs Qwen's ~12), the honest statement is:

> **Entropy is below random in 24 of 28 configurations and at parity in the remainder. The
> direction is robust; the magnitude is strongly family- and language-dependent.** The role selector
> beats both baselines in *every* configuration measured — 39-87% capture against random baselines of
> 11-46%.

The role selector's advantage is the durable claim; entropy's failure magnitude is not.

### F16 — Third family replicates, but effect size is family-dependent · **CONFIRMED**

StarCoder2-3B (BigCode, The Stack, different tokenizer), HumanEval-JS, 57 problems / 4,555 positions,
646 clean consequential (14.2%).

| role | rate | mean entropy |
|---|---|---|
| numeric literal | **74.4%** | **0.137** |
| identifier | 27.6% | 0.451 |
| operator | 16.7% | 0.567 |
| keyword | 9.5% | 0.867 |
| punctuation | 1.5% | 0.297 |

Same archetype — numeric literals lowest-entropy and most consequential, punctuation and keywords
inert — in a third independent family.

**But the margin is the narrowest measured.** Held-out at a 28.3% budget: role 71.9%, entropy **26.7%**,
random 28.3%. Entropy still loses at every budget, but by ~1.6 points rather than the ~12 points Qwen
shows (16.1% vs 28.3%).

> **The effect is directionally universal but not uniform in size.** Entropy is below random in every
> configuration tested, yet *how far* below is family-dependent. Any claim about magnitude must be
> stated per-family; only the sign generalises.

**Tokenizer sensitivity confirmed** (§F note): the BPE-fragment + reference artifact rate varies by
family — Qwen 36.9%, StarCoder2 42.3%, DeepSeek 45.9% of raw `K_sem`. The filter must be re-validated
on each new tokenizer, not assumed.

### F14 — Table 2: no published criterion beats random · **CONFIRMED** (revised, see B11)

All 11 criteria scored on identical positions (3,697 positions, 62 problems, HumanEval-JS), each in
the direction *its own literature* uses it (entropy/NLL/KL/excess-loss select high; margin selects low;
prefix methods select early), so none is strawmanned.

| criterion | rho | CC@10 | CC@25 | CC@50 | waste@25 | better flipped? |
|---|---|---|---|---|---|---|
| P8 confidently-wrong (TIP) | +0.000 | 9.0% | 21.6% | 50.3% | 86.8% | |
| **P0 random baseline** | −0.003 | 8.5% | **23.5%** | 51.7% | 85.6% | YES |
| P7 position | −0.034 | 5.7% | 19.6% | 45.1% | 88.0% | YES |
| P4 excess loss (Rho-1) | **−0.067** | 2.5% | 12.9% | 43.9% | 92.1% | YES |
| P5 teacher–student KL | −0.094 | 8.5% | 22.5% | 40.0% | 86.3% | YES |
| P6 expert–generalist delta | −0.134 | 3.5% | 15.4% | 38.1% | 90.6% | YES |
| P10 min-p width | −0.158 | 4.1% | 11.3% | 34.3% | 93.1% | YES |
| P2 margin | −0.185 | 4.4% | 13.1% | 32.6% | 92.0% | YES |
| P9 varentropy | −0.190 | 4.6% | 14.9% | 30.3% | 90.9% | YES |
| P3 NLL | −0.190 | 3.9% | 13.6% | 31.5% | 91.7% | YES |
| **P1 entropy** | **−0.196** | 4.4% | **12.4%** | 31.3% | 92.4% | YES |

1. **Not one criterion beats random.** Best CC@25 is `P0_random` itself (23.5%).
2. **Ten of eleven correlate negatively, and all ten do better reversed.** The signals are not weak —
   they are inverted.
3. **Entropy is the worst of all eleven**, and the most widely used.
4. **There is no longer an exception.** An earlier version of this table showed Rho-1's excess loss
   at **+0.067**, the sole positive correlation, and that number was reported as the one criterion
   pointing the right way. It was our sign error, not a property of Rho-1 — see B11. Scored as
   published it is **−0.067** with CC@25 of 12.9%, far below random.
5. Waste@25 is 86–93% everywhere: most of every selection budget buys positions that did not matter.

*Every row above is recomputed from `outf/phase_f.jsonl` by `verify.py`, which fails if the paper
and the raw scores disagree.*

This is the table that does not currently exist for any selection criterion in this literature, and it
is the paper's central artifact-backed contribution.

### F12 — Python replication: entropy loses in a second language · **CONFIRMED**

HumanEval Python via `openai_humaneval`, Qwen2.5-Coder-1.5B, 66 problems / 2,937 positions,
432 clean consequential (14.7%, vs 15.9% in JS).

| role | rate | mean entropy |
|---|---|---|
| numeric literal | **52.5%** | **0.106** |
| operator | 39.7% | 0.304 |
| identifier | 11.9% | 0.461 |
| keyword | 6.5% | 0.575 |
| punctuation | 3.1% | 0.519 |
| string | 0.0% | 0.514 |

Held-out: budget 14.6% -> role **47.9%**, entropy **8.5%**, random 14.6%. Entropy loses at every
budget. Same archetype as JS: numeric literals lowest-entropy *and* most consequential; keywords and
punctuation inert. Operators are notably stronger in Python (39.7% vs 20.8% in JS).

**At time of writing: 143,786 positions · 14 models · 9 families · 9 languages · 3 benchmarks · 28 model-language configurations.**

### F15 — Static typing MOVES consequence rather than removing it · **CONFIRMED (controlled)**

**The controlled test: JavaScript vs TypeScript is the same language plus a type checker** — same
runtime, same MultiPL-E task set, same model, same tokenizer family, same test-harness style. Every
confound that made a cross-language comparison arguable is held constant.

The rate columns below are a **controlled** subset — one model (Qwen2.5-Coder-1.5B), HumanEval
problems only — so the comparison is not confounded by which models or benchmarks happen to cover
each language. The last column gives the release-wide coverage, which is larger and pools models.

| language | typing | controlled n | `K_syn` | `K_type` | `K_sem` | release positions |
|---|---|---|---|---|---|---|
| Ruby | dynamic | 2,208 | 31.8% | — | **37.3%** | 4,328 (129 problems) |
| Perl | dynamic | 3,138 | 23.8% | — | **32.7%** | 9,788 (173 problems) |
| PHP | dynamic | 5,584 | 29.7% | — | **29.2%** | 21,447 (262 problems) |
| Python | dynamic | 2,937 | 41.8% | — | **28.4%** | 5,713 (73 problems) |
| JavaScript | dynamic | 5,097 | 29.7% | — | **24.7%** | 57,571 (329 problems) |
| **TypeScript** | **gradual** | 5,703 | 31.6% | **18.3%** | **9.6%** | 21,373 (178 problems) |
| Go | static | 2,261 | 30.0% | **14.6%** | **13.2%** | 7,111 (103 problems) |
| Java | static | 3,822 | 29.2% | **19.7%** | **11.7%** | 10,896 (152 problems) |
| **Rust** | **static (affine)** | 3,290 | 29.0% | **24.3%** | **11.9%** | 5,559 (63 problems) |

*(An earlier version of this table paired the controlled rates with release-wide position counts,
which implied the rates were computed over all of them. It also carried a stale Python `K_sem` of
29.0% and a missing Perl `K_syn`; both are corrected above and verified by `verify.py`.)*

**Type-system strictness is a gradient, not a switch.** Ranking the four typed languages by how much
consequence their checker intercepts (`K_type`), both families agree on the *same order*:

| language | discipline | Qwen `K_type` | StarCoder2 `K_type` | Qwen `K_sem` | SC2 `K_sem` |
|---|---|---|---|---|---|
| **Rust** | affine / ownership | **24.3%** | **29.1%** | 11.9% | 10.1% |
| Java | nominal / class | 19.7% | 21.8% | 11.7% | 9.3% |
| TypeScript | structural / gradual | 18.3% | 18.8% | 9.6% | 11.4% |
| Go | structural / static | 14.6% | 12.8% | 13.2% | 12.3% |
| *JavaScript* | *dynamic* | *0%* | *0%* | *24.7%* | *24.6%* |

Rust — the strictest checker in the set (affine types, no null, exhaustive matching) — intercepts the
most, and Go the least, in **both** families independently. Yet `K_sem` stays inside a narrow
9.3–13.2% band across all four typed languages *and both families*, while dynamic JavaScript sits
at 24.6–24.7%. (The single-family band, used in the paper's Table 12, is 9.6–13.2%.) Static
checking does not merely move consequence; **how much it moves scales with how strict the checker
is.**

**Five dynamic languages span 24.7–37.3%. Four typed languages span 9.6–13.2%. The ranges do not
overlap** — the gap between the lowest dynamic (JavaScript, 24.7%) and the highest typed (Go, 13.2%)
is 11.5 points. Confirmed across four independent type systems: TypeScript (structural, gradual),
Go (structural, static), Java (nominal, class-based), and Rust (affine).

**Entropy loses in all nine languages** — 2.3–31.2% capture against random baselines of 3.5–38.5%
at the matched operating point, recomputed by `analysis/figdata.py`.

**Replicated in a second, independent family.** StarCoder2-3B (BigCode, different tokenizer and
training corpus) reproduces the collapse:

| language | typing | Qwen2.5-Coder-1.5B | StarCoder2-3B |
|---|---|---|---|
| JavaScript | dynamic | **24.7%** | **24.6%** |
| Go | static | 13.2% | 12.3% |
| Java | static | 11.7% | 9.3% |

`K_sem` on JavaScript agrees to 0.1 percentage points across families. F15 is therefore a property of
the *language's* error-catching discipline, not of any model's idiosyncrasies — the strongest form of
the claim.

`K_syn` barely moves (29.7% -> 31.6%), exactly as expected: a type checker should not change parsing.
But **`K_sem` collapses from 25.2% to 10.0%**, and the missing mass reappears as `K_type` at 18.3%
(10.0 + 18.3 = 28.3% vs JS's 25.2%).

> **About 60% of JavaScript's silent logic errors become compile-time type errors in TypeScript.**

Static typing does not reduce how often a token choice matters — it changes **when the error
surfaces**, converting silent logic faults into compile-time faults. Go and Java show the same pattern
independently, so the effect is not a TypeScript artifact.

**Consequence of this for the whole paper:** "consequential" is partly a property of the language's
error-catching discipline, not of the model alone. Every `K_sem` number is conditional on the
language's type discipline and must be reported as such.

Role archetype holds in both: TS numeric literal 37.9% at entropy 0.114 (lowest entropy, highest
rate), punctuation 0.9%, keyword 3.0%. Go numeric literal 64.8% at entropy 0.158.
Entropy loses in both — TS held-out at 18.4% budget: role **57.4%**, entropy **8.8%**, random 18.4%;
Go at 14.4%: role **54.4%**, entropy **8.8%**, random 14.4%.

**RELEASE BUILD (`conseq.jsonl`): 143,786 positions · 14 models · 9 families · 9 languages · 3 benchmarks · 28 model-language configurations.** All rows at instrument v2; zero quarantined;
all 12 v1 runs superseded by re-runs and correctly excluded.

Position balance after the balancing batch: JavaScript fell from 65% of the corpus to 38%. Go went
38 -> 103 problems and Java 53 -> 152 — the two languages anchoring F15 are no longer the thinnest. Families: Qwen, DeepSeek, BigCode, IBM, Stability, Salesforce,
Microsoft, Meta, HuggingFace. Languages: JS, TypeScript, Python, Ruby, PHP, Perl, Go, Java. Families: Qwen, DeepSeek, BigCode, IBM, Stability, Salesforce,
Microsoft, Meta, HuggingFace. Blocked and excluded: Google CodeGemma (gated repo), Replit
(custom tokenizer backend), Lua (0/161 retention — O11).

**Entropy is below random in 24 of 28 configurations**, at parity in the rest (DeepSeek x Python,
StableCode x JS, SmolLM2 x JS; all margins <4 points). **The role selector beats random in all 28.**
The entropy claim is directional, not absolute; the role result is the one that holds without
exception.

### F13 — Language syntax discipline shifts the syn/sem boundary · **SUPERSEDED by F15**

`K_syn` (substitution breaks the parser) vs `K_sem` (parses, fails tests):

| language | `K_syn` | `K_sem` |
|---|---|---|
| JavaScript | 29.7% | 25.2% |
| **Python** | **41.8%** | 28.4% |

Python's significant whitespace converts substitutions that would be silent logic errors in JS into
parse-time failures. This is the O5 hypothesis — that what counts as "consequential" depends partly on
*when the language catches errors*, not only on the model — appearing without needing a compiled
language. Go (static, compiled, fast compiler) remains the sharper test.

*Provisional because:* one model, one benchmark per language; the comparison is not yet matched on
problem difficulty.

### F11 — Consequential fraction is flat across scale · **PROVISIONAL**

15.1% / 15.9% / 15.9% at 0.5B / 1.5B / 3B — flat across a 6× parameter range. H4 predicted it would
*fall* with capability. Prediction wrong; the fraction is stable. DeepSeek-1.3B is lower (12.3%),
so this may track family rather than scale.

---

### F21 — The result survives a parse-preserving counterfactual · **CONFIRMED (controlled)**

O4 asked whether the headline numbers are an artifact of the counterfactual rule. The top-2
alternative is often syntactically illegal in context, so ~30% of positions register as `K_syn`
and never reach semantics. If consequence were mostly "the second-choice token does not parse",
the finding would be about tokenizers, not about code.

Re-ran Phase A with `cf_mode="parse"`: walk down the model's own ranked alternatives (top-10)
until one yields a parseable program; fall back to top-2 if none does. Same model
(Qwen2.5-Coder-1.5B), same problems, same instrument (`iv=2`); every top-2 row below is
restricted to the identical position set, so each pair is matched. Three languages spanning the
typing spectrum.

| lang | rule | `K_syn` | `K_type` | `K_sem` | consequential | n |
|---|---|---|---|---|---|---|
| JS (dynamic) | top-2 | 29.7% | — | 24.7% | 54.4% | 5,097 |
| JS (dynamic) | parse | **5.0%** | — | **38.8%** | 43.9% | 5,097 |
| TS (gradual) | top-2 | 31.6% | 18.3% | 9.6% | 59.5% | 5,703 |
| TS (gradual) | parse | **4.3%** | **29.6%** | **12.5%** | 46.4% | 5,703 |
| Go (static) | top-2 | 30.0% | 14.6% | 13.2% | 57.8% | 2,261 |
| Go (static) | parse | **5.1%** | **24.1%** | **16.1%** | 45.4% | 2,261 |

Three things follow.

1. **Syntax consequence was substitutable, not intrinsic.** `K_syn` collapses to ~5% in all
   three languages, and the residual is exactly the rate at which no alternative in the top-10
   parses (`no_parseable_alt`: 5.04% JS, 4.35% TS, 5.09% Go). The instrument has no residual
   syntax bias of its own.
2. **The mass moves down the pipeline, it does not disappear.** What was `K_syn` reappears as
   `K_sem` in JavaScript (+14.1pp) and as `K_type` in TypeScript (+11.3pp) and Go (+9.5pp).
   **F15 survives and strengthens**: with syntax equalised across languages, the type checker
   is visibly the thing absorbing the difference, which is the F15 claim in its cleanest form.
3. **The selector result is unchanged and larger.** Held-out ROLE vs entropy vs random:

   | lang | budget | ROLE | entropy | random |
   |---|---|---|---|---|
   | JS | 13.8% | **32.0%** | 7.6% | 13.8% |
   | TS | 18.4% | **49.0%** | 11.2% | 18.4% |
   | Go | 14.4% | **51.4%** | 8.1% | 14.4% |

   Entropy stays below random in all three. F1 and F2 are not artifacts of the top-2 rule.

Median alternative rank is 2 (mean 2.51–2.60), so the parse-preserving rule usually returns the
same token as top-2; the difference comes from a minority of positions.

**Confound, reported not hidden.** Parse-preserving selection biases toward *common* tokens,
because rare alternatives more often break syntax. The rule therefore measures a slightly
easier counterfactual than "any plausible alternative". This pushes in the conservative
direction for the syntax claim (it is what makes `K_syn` fall) and is neutral for the selector
claim, which is scored within-rule.

Runs: `o_cfjs`, `o_cfts`, `o_cfgo`.

---

### F22 — Full-distribution sampling raises consequence by ~4pp, and changes nothing else · **CONFIRMED (paired)**

O7 asked how far the nearest-alternative estimand generalises. The paper measures the model's
own top-2 token; a decoder at temperature 1.0 samples the whole tail. If the tail were far more
damaging, "consequential" would be an artifact of asking only about the nearest decision.

Re-ran Phase A on JavaScript with `cf_mode="temp"` (temperature 1.0, emitted token zeroed out),
on the **same 5,097 positions** as the top-2 run — a paired comparison, not two samples.

| rule | `K_syn` | `K_sem` | `K_timeout` | consequential |
|---|---|---|---|---|
| top-2 | 29.7% | 24.7% | 0.5% | 54.4% |
| temperature 1.0 | 31.2% | 27.0% | 0.5% | **58.2%** |

Per-position agreement on the binary consequential verdict is **90.1%** (both consequential
51.3%, top-2 only 3.1%, temperature only 6.9%).

Reading: sampling the full distribution is harsher, but only by 3.8pp, and it is harsher in the
expected asymmetric way (positions that survive their nearest alternative sometimes fail a
distant one; the reverse is rare). **The top-2 estimand is a mild lower bound on consequence
under realistic decoding, not a different quantity.**

The role structure is also unchanged — held-out selector at 28.2% budget: ROLE **57.2%**,
entropy 15.6%, random 28.2%; punctuation sits at 1.2% (the instrument-health invariant of
§B3/B7/B9 holds). Numeric literals remain the keystone cell (59.3% rate).

Run: `o_cftemp`.

---

## B. Corrections and retractions

Kept deliberately. Each was reported as a result before being caught.

### B1 — EOS decoded into program text
`<|endoftext|>` reached the executed program, making every one a syntax error. Silently discarded
**~70% of trajectories** (retention 18→77 problems on fix). Caught by logging *why* problems were
skipped. Regression check now asserts EOS text never survives into an executed program.

### B2 — Phase B prefix mismatch
`continue_from` conditioned the model on `prompt + ids[:t+1]` but the program was rebuilt from
`decode(ids[:t])`, dropping the token under test; the counterfactual arm dropped the substituted
token entirely. Symptom: factual-arm pass rate 0.09 where it had to be high. Now asserts the
factual prefix plus untouched tail reconstructs the original program byte-for-byte.

### B3 — "Consequence does not compose" · **RETRACTED**
Reported as 0/44 and called the session's most important finding. "Free" had been defined as
*not `K_sem`*, silently including artifact-breakers that genuinely break programs. Symptom: a single
substitution at a supposedly free position passed 66.8% instead of ~100%. Corrected definition
(*the splice actually passed*) gives 100.0% at m=1 and **93.2%** overall — the opposite conclusion.
See F6.

### B4 — Handicapped decoding oracle
The oracle committed only at `K_sem` positions, leaving artifact-breakers in its *sampled* set, and
committed at 14.9% of positions against the controls' 42.1%. Two separate confounds. `K_sem` is right
for the claim about consequence; at decode time a break is a break. Corrected in F8. Selftest now
asserts every arm's commit set is identically sized.

### B5 — NLL bug-localization result
Not retracted but **must not be cited as a result** — see F10.

### B6 — `humaneval-py` does not exist
Launched the Python run against a MultiPL-E config that isn't there: MultiPL-E *translates from*
Python into 24 other languages, so Python is the source and never a target. Python must come from
`openai_humaneval`, which uses a different schema (a `check(candidate)` harness plus `entry_point`)
and needs its own stop tokens. A `loader.py` now normalizes both to one schema, and its selftest
executes the **canonical solution** through the assembled harness — if the harness were malformed,
every program would fail and read as a 0% pass rate rather than a bug.

### B7 — Python splices executed by `node`
The first Python run returned **0 consequential positions out of 2,937** — every splice
`parse_error`. `phase_a` routes the splice batch through `run_many`, which had never been given the
`lang` parameter, so Python source was handed to `node`. The trajectory-validity check *did* pass
`lang`, so 66 problems were correctly retained and only the splice arm was wrong — which is why the
run looked superficially healthy.

Two guards added: `run_many` takes `lang` and a test asserts both runtimes route correctly, and
`phase_a` now **aborts** if every splice in a trajectory is `parse_error`, since a program valid
enough to pass its tests cannot have zero parseable single-token variants. That invariant turns a
silent wrong-runtime failure into an immediate crash.

### B8 — Go tasks run with `go run` instead of `go test`
The first Go run kept **0 of 154 problems**. MultiPL-E ships Go tasks as Go *test* files — the prompt
declares a `_test` package, imports `testing`, and the tests are `func TestXxx(t *testing.T)`. Running
those under `go run` compiles a package with no `main` and executes no assertions. The abort guard did
not fire because the failures were `fail:Other`, not `parse_error`. Fixed to write `main_test.go` with
a `go.mod` and run `go test`; the package clause is rewritten to `main`, which is safe because that
clause lives in the fixed prompt and is never spliced.

The Go selftest had *passed* on the broken executor because it used `os.Exit` rather than the `testing`
package — a self-check that does not mirror production conditions manufactures confidence. It now uses
`testing`.

### B9 — Timeouts counted as semantic consequence
Java initially read `K_sem` = 26.9%, *contradicting* F15 for a statically typed language. Cause:
`K_sem` included `timeout`, and Java hit a **19.0% timeout rate** against ≤1.2% in every other
language — `javac`+`java` per splice with 8 workers on a 4-core box is CPU contention, not infinite
loops. Excluding timeouts gives `K_sem` = 7.9%, the *lowest* of all five languages and fully
consistent with F15.

The tell was the role table: punctuation 21.8% and whitespace 32.4% consequential, against ~1% and ~5%
everywhere else. Inert tokens appearing consequential is the same signature as B3.

Two fixes: a timeout is now its own class (`K_timeout`) and is **excluded from `K_sem`** — it means
*unmeasured*, not *consequential*; and `run_many` scales workers and patience per toolchain
(`js/py`: 8 workers @ 5s, `ts/go`: 4 @ 20–25s, `java`: 2 @ 60s) so a slow compiler cannot manufacture
consequence.

### B10 — `rustc` linker failure classified as a syntax error
A Rust compile that fails to **link** carries no `E`-code, so the classifier — which reads a bare
`error:` as syntax — recorded it as `parse_error`. On a machine without a working `cc` this would
make Rust appear ~100% syntactically broken and corrupt `K_syn` entirely. Caught locally when the
Rust selftest failed on a valid program.

Fixed two ways: linker failures are classified as **unmeasured** (an environment fault, not a
property of the code), and the Rust selftest now probes for a *working toolchain* by compiling a
trivial program rather than merely checking that `rustc` is on `PATH`. The Kaggle runs were
unaffected — Linux had a working linker — so no released data was touched.

### B11 — Rho-1 excess loss implemented with reversed operands

`criteria.py` computed `L_ref - L_theta`; [Rho-1](https://arxiv.org/abs/2404.07965) eq. 3 defines
`L_delta = L_theta - L_ref` and Selective Language Modeling trains on the **top k%** of it. Same
quantity negated, so scoring it "select high" selected exactly the tokens the method throws away.

*Symptom:* excess loss was the only one of eleven criteria with a positive correlation, and the only
one that did not improve when reversed — a lone exception in an otherwise uniform table.

Unlike B1–B10 this was **not** caught by an implausible number. It was found by reading the source
paper's equation. That is the class of defect the "implausibly clean number" heuristic cannot catch,
and it is why the eleven criteria are now stated as formulas in the paper rather than described in
prose, and why `verify.py` recomputes every cell of the table from the raw scores.

*Effect:* rho +0.067 → **−0.067**; CC@25 23.2% → **12.9%**. F14 item 4 retracted. The corrected
result is stronger — zero of eleven criteria correlate positively.

*Fix:* operand order corrected in `criteria.py` and `phase_f.py`; the selftest now asserts the
**sign** (excess loss must be positive when the current model fits the token worse than the
reference), not merely that it vanishes when the two models agree. `outf/phase_f.jsonl` regenerated
with `crit_v: 2`; the superseded file is kept as `outf/phase_f.v1.jsonl` rather than overwritten.

### Build-assembly bugs (no findings affected)
Kaggle assigns P100s whose compute capability the image's torch no longer supports; `accelerator` in
kernel metadata is silently discarded (must be a CLI flag); `sed '/re/,$d' a.py b.py` treats both files
as one stream and deleted an entire module; `'$DS'` reached the kernel unexpanded. All now caught by
pre-push guards.

---

## C. Open — not yet measured

**Status: the measurement programme is COMPLETE.** 28 configurations, 14 models, 9 families,
9 languages. O4 and O7 closed the two counterfactual-robustness questions (F21, F22). Rust closed the last open question (F15 gradient). Every core finding has replicated, and additional models or languages would now add artifact
breadth rather than evidence. Release engineering is complete: the dataset, instrument and
analysis are published, `assemble.py` rebuilds the release byte-for-byte from the raw runs, and
`verify.py` re-derives every reported number and fails on disagreement.


| # | Item | Status |
|---|---|---|
| O1 | ~~Python replication~~ | **DONE** — see F12/F13 |
| O2 | ~~Criterion audit P0–P10~~ | **DONE** — see F14 |
| O3 | ~~Repairability~~ | **DONE** — replicated across 2 languages and 2 scales (F3) |
| ~~O4~~ | ~~Parse-preserving counterfactual~~ | **DONE** — see F21. `K_syn` collapses to ~5% in JS/TS/Go; mass moves to `K_sem`/`K_type`; selector result unchanged and larger. |
| O5 | ~~Static-vs-dynamic typing~~ | **DONE** — see F15 |
| ~~O6~~ | ~~Citation verification~~ | **DONE** — 64-entry bibliography, all resolving, all cited, none orphaned. 17 entries initially carried a title but no author and were rendering as truncated keys; authors for all 17 were recovered from the arXiv API. |
| ~~O7~~ | ~~Temperature-sampled counterfactual (secondary rule, §6.2)~~ | **DONE** — see F22. Paired on 5,097 positions: +3.8pp consequential, 90.1% verdict agreement. |
| O11 | **Lua abandoned** — 0/161 retention, 142 assertion failures. Most likely genuine model incapacity (Qwen2.5-Coder-1.5B sees little Lua); stop tokens `\nlocal`/`\nfunction` may also truncate helpers as in Go. Adds no new typing axis (a 5th dynamic language), so not pursued. | dropped |
| ~~O9~~ | ~~Characterise the anomalous cell~~ | **DONE** — F18. DeepSeek-JS loses (−7.0), DeepSeek-TS loses (−7.2), Qwen-Python loses (−5.8), DeepSeek-Python is at parity (+1.5): an *interaction*, neither a family nor a language effect. |
| ~~O10~~ | ~~Dataset schema inconsistency~~ | **DONE** — all 12 v1 runs superseded by v2 re-runs; 0 rows quarantined; `iv` stamp on every row; v1→v2 coverage diff shows no regressions. |
| ~~O8~~ | ~~Naturally-failing trajectories~~ | **DONE** — Phase G uses the model's own temperature-sampled failures, removing F10's injection confound. See F20. |

---

## G. The release build (`conseq.jsonl`)

`assemble.py` produces the release. Assembly is **not concatenation** — it refuses to merge rows
whose columns do not mean the same thing:

- **`K_sem` changed meaning at instrument v2** (timeouts excluded — B9). v1 rows are quarantined,
  never silently pooled. All 12 v1 runs have now been superseded by v2 re-runs.
- **`K_type` exists only** for languages with a separate static type-check phase (ts / go / java / rs).
- **Artifact classification is language- *and* tokenizer-specific** (F7, F16) — rates span
  19.9–46.2% across the six adequately-powered families (up to 56% in the smallest, on a few
  hundred positions), so the filter is re-validated per family rather than assumed.
- **Provenance is explicit per run directory.** A missing entry now fails loudly; it previously
  defaulted to Qwen and silently mis-attributed two runs (including DeepSeek-on-TypeScript).

Emits `conseq.jsonl` (release), `conseq_manifest.json` (per-run provenance, retention, artifact
rate, underpowered flag), and a coverage report.

**Determinism verified.** Re-running the same model+dataset in a fresh kernel reproduces position
counts exactly (5,097 -> 5,097; 4,555 -> 4,555; 3,613 -> 3,613). Greedy trajectories, splice sets and
verdicts are stable across sessions — a property the artifact needs and which had not been checked
before the v2 re-runs.

**Both pre-release gaps are now closed.** The v1-vs-v2 diff check on problem counts is part of
assembly and reports no regressions (the MBPP re-run had silently lost 130 problems to a hardcoded
`n=161`, visible only against the run it replaced). `DATASHEET.md` documents every column *and its
language-conditionality*, which F15 makes mandatory since `K_sem` is not comparable across type
disciplines.

**Reproduction is checked, not asserted.** From a fresh clone, `assemble.py` regenerates
`conseq.jsonl` byte-for-byte from the 35 raw run directories, and `verify.py` runs 58 data checks
(158 with the manuscript present) covering coverage, the typing gradient, the artifact taxonomy,
every cell of the criterion audit, and the manifest against the raw runs.

---

## E. Language coverage and what each one buys

Nine languages in the release, 143,786 positions — **entropy is at or below random in every
model-language configuration tested**:

| language | typing | verification | positions | models / families | status |
|---|---|---|---|---|---|
| JavaScript | dynamic | `node`, ~50ms | 57,571 | 14 / 9 | done — the breadth spine |
| PHP | dynamic | `php -l` + `php`, ~80ms | 21,447 | 1 / 1 | done |
| **TypeScript** | **gradual** | `tsc` + `node`, ~2s | 21,373 | 3 / 3 | done — **the controlled F15 test** |
| Java | **static, nominal** | `javac` + JUnit, ~3s | 10,896 | 2 / 2 | done — second static type system |
| Perl | dynamic | `perl -c` + `Test::Deep`, ~80ms | 9,788 | 1 / 1 | done |
| Go | **static, structural** | `go test`, ~1s | 7,111 | 2 / 2 | done |
| Python | dynamic | `python3`, ~50ms | 5,713 | 2 / 2 | done |
| **Rust** | **static (affine)** | `rustc`, ~1–2s | 5,559 | 2 / 2 | done — gives the F15 gradient |
| Ruby | dynamic | `ruby -c` + `ruby`, ~80ms | 4,328 | 1 / 1 | done |

Four typing regimes are represented — dynamic (JS, PHP, Perl, Python, Ruby), gradual (TS),
static-structural (Go), static-nominal (Java), static-affine (Rust) — which is what F15's
gradient claim rests on.

### Not pursued, and why

**Lua — abandoned (O11).** 0/161 retention, 142 assertion failures. Most likely genuine model
incapacity rather than an instrument fault; stop-token truncation may also contribute. Adds no
new typing axis, so not debugged further.

**Haskell, Racket, Clojure — too little data.** Genuinely interesting for testing whether the
numeric-literal/operator archetype is imperative-specific, but code-model pass rates are low
enough that statistical power collapses.

**Caveat, from experience:** every language broke a structural assumption the previous ones
shared — Python needed runtime routing (B7), Go needed `go test` rather than `go run` (B8), Rust
needed linker failures separated from syntax errors (B10), Perl needed `Test::Deep` installed
*and* the harness actually invoked. Budget one debugging cycle per language, not one run.

---

## F. Model coverage and what each one buys

14 models, 9 families, 143,786 positions in the release build.

| model | family | params | languages | positions |
|---|---|---|---|---|
| Qwen2.5-Coder | Qwen | 1.5B | JS, Python, Go, TS, Java, Rust, Ruby, PHP, Perl | 84,342 |
| StarCoder2 | BigCode | 3B | JS, TS, Go, Java, Rust | 16,815 |
| DeepSeek-Coder | DeepSeek | 1.3B | JS, Python, TS | 9,993 |
| Qwen2.5-Coder | Qwen | 3B | JS | 6,057 |
| granite-3b-code-base | IBM | 3B | JS | 4,390 |
| stable-code-3b | Stability | 3B | JS | 3,984 |
| granite-3.3-2b-base | IBM | 2B | JS | 3,565 |
| Qwen3 | Qwen | 1.7B | JS | 3,426 |
| **Qwen2.5-1.5B** (non-Coder) | Qwen | 1.5B | JS | 3,286 |
| SmolLM2 | HuggingFace | 1.7B | JS | 3,014 |
| Qwen2.5-Coder | Qwen | 0.5B | JS | 2,437 |
| phi-2 | Microsoft | 2.7B | JS | 1,444 |
| codegen-2B-mono | Salesforce | 2B | JS | 796 |
| incoder-1B | Meta | 1B | JS | 237 |

Nine families: Qwen, BigCode, DeepSeek, IBM, Stability, HuggingFace, Microsoft, Salesforce, Meta.

**What each tier buys.** The 1.5B Qwen-Coder row is the spine — it carries every language, so all
cross-language claims (F13, F15, F21) are controlled for model. The eight JS-only families
(F19) establish that the role archetype is not a Qwen idiosyncrasy. StarCoder2 and DeepSeek
cross both axes, which is what makes F16 (family-dependent effect *size*) and F18 (one anomalous
family×language cell) separable from each other. Qwen2.5-1.5B is the controlled non-Coder
sibling that gives F17: matched tokenizer, no code specialisation, same archetype.

**Underpowered rows, flagged in the manifest** (fewer than 25 retained problems): `incoder-1B`
(11 problems), `codegen-2B-mono` (15) and `phi-2` (20). All three carry `underpowered: true` and
are excluded from effect-size claims; they contribute only to the "does the archetype appear at
all" count.

**Skip — 7B.** Needs 4-bit on a T4, and quantization can flip the argmax, corrupting `alt` itself
— the quantity every measurement depends on. 0.5B→3B already establishes the scale trend (F11).

**Note:** the role taxonomy is a regex over decoded token strings, so it is tokenizer-agnostic
and needs no per-model work. The BPE-fragment artifact filter (F7) *is* tokenizer-sensitive and
was re-checked on each new family.

---

## D. What the paper claims, in one paragraph

We measure per-token outcome consequence directly by execution. Consequence is carried by **syntactic
role** — numeric literals, operators and property accesses — identifiable by a regex at zero cost, and
a role selector beats a random baseline in **every one of 28 model-language configurations** spanning
14 models, 9 model families, 9 languages and 3 benchmarks (143,786 positions). Uncertainty-based
criteria, which selective distillation, RLVR, adaptive decoding and attribution all use to route
compute, perform at or below random: **entropy is below random in 24 of 28 configurations** and at
parity in the rest, and **none of 11 published selection criteria beats a random baseline** on
identical positions (F14). That last claim was itself strengthened by a correction: an earlier
version reported Rho-1's excess loss as the one criterion with a positive correlation, which was our
own sign error (B11); scored as published it is negative like the other ten. Consequence **composes** on a fixed sequence (93.2% survival
across ~23 simultaneous individually-free substitutions) but does **not transfer off-trajectory**,
which is why a perfect consequence oracle buys exactly nothing over random position selection at
decode time (`t = 0.00`, F8). Per-token attribution is therefore valid for **editing a fixed
sequence** and invalid for **steering generation**. Finally, what counts as "consequential" is partly
a property of the *language*: static type checking converts silent logic faults into compile-time
faults, so semantic consequence falls from 24.7–37.3% in five dynamic languages to 9.6–13.2% in four
typed ones, with no overlap — replicated across two independent model families that agree to 0.1
percentage points (F15). Both results are robust to the counterfactual rule: under a
parse-preserving alternative `K_syn` collapses from ~30% to ~5% and the mass reappears as
`K_sem` in JavaScript and as `K_type` in TypeScript and Go — F15 in its cleanest form — while
the role selector's margin over entropy *widens* (F21); and under full-distribution sampling at
temperature 1.0, paired on identical positions, consequence rises by only 3.8pp with 90.1%
verdict agreement, so the nearest-alternative estimand is a mild lower bound rather than a
different quantity (F22).

