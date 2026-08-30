# CONSEQ

**An execution-grounded dataset of per-token consequence in code generation.**

143,786 token positions · 14 models · 9 model families · 9 programming languages · 3 benchmarks

Companion artifact for *Most Uncertainty Doesn't Matter: An Execution-Grounded Dataset of Per-Token
Consequence in Code Generation* ([`paper/main.pdf`](paper/main.pdf)).

## Overview

Selective distillation, reinforcement learning with verifiable rewards, adaptive decoding, and
token attribution all route compute or supervision by a model's *uncertainty*, measured as entropy,
margin, loss, or KL divergence. Each assumes uncertainty tracks **consequence**: whether committing
differently at a token would have changed the outcome. That assumption had not been tested against
ground truth, because testing it requires per-token counterfactual outcomes.

Code execution supplies them. For every position in a verified-correct model trajectory, CONSEQ
records what happens when the model's own second-choice token is substituted at that position and
the program is re-executed against its own test suite:

```
function f(n) { return n * 2; }     greedy trajectory, verified to pass its tests
                          |
function f(n) { return n + 2; }     one token replaced, suffix held fixed, executed once
```

The measurement requires one execution and no generation, so the label is a deterministic function
of the substitution rather than a sample from a decoder.

## Principal findings

| Measurement | Result |
|---|---|
| Entropy at or below a random baseline | 24 of 28 model-language configurations |
| Published selection criteria beating random | 0 of 11 |
| Syntactic-role selector beating random | 28 of 28 configurations |

Consequence is carried by syntactic role — numeric literals, operators, and property accesses —
which a regular expression over the token string identifies at no inference cost. Numeric literals
are simultaneously the lowest-entropy and the most consequential role in every language measured,
which is why an entropy-ranked selector systematically avoids them.

Two boundaries constrain how the data may be used. Consequence **composes** on a fixed sequence:
93.2% of programs survive 1–32 simultaneous individually-harmless substitutions. It does **not
transfer** once decoding leaves that sequence: a perfect consequence oracle is statistically
indistinguishable from random position selection (t = 0.00). Per-token attribution is therefore
valid for editing a fixed sequence and invalid for steering generation.

## Getting started

```bash
git clone https://github.com/nafew-azim/CONSEQ.git
cd CONSEQ/conseq
gunzip -k conseq.jsonl.gz          # 58 MB, newline-delimited JSON
```

Scoring a token-importance criterion against execution ground truth:

```python
import json
from scipy.stats import spearmanr

rows = [json.loads(line) for line in open("conseq.jsonl")]
subset = [r for r in rows if r["lang"] == "js"]

scores = [your_criterion(r) for r in subset]
truth  = [r["K_sem"] for r in subset]

print(spearmanr(scores, truth))     # entropy scores about -0.196
```

Two conditions must be observed:

1. **Filter instrument artifacts before analysis.** 34.0% of raw `K_sem` positions are artifacts of
   the measurement rather than decisions the model made. Use `is_artifact()` from `phase_a.py`.
2. **Do not compare `K_sem` across typing disciplines.** Static type checking relocates faults from
   `K_sem` into `K_type`. Cross-language comparisons must use `K_sem + K_type`.

[`DATASHEET.md`](DATASHEET.md) documents the column semantics, both conditions, and the known
limitations in full.

## Repository layout

| Path | Contents |
|---|---|
| `conseq/conseq.jsonl.gz` | The assembled release, gzipped |
| `conseq/conseq_manifest.json` | Provenance for all 35 runs |
| `conseq/phase_a.py` | The forced-splice measurement and the artifact filter |
| `conseq/execjs.py` | Execution contracts for the nine languages |
| `conseq/criteria.py` | The eleven published selection criteria |
| `conseq/roles.py` | Syntactic-role taxonomy and the held-out selector |
| `conseq/assemble.py` | Rebuilds the release from the raw per-run outputs |
| `conseq/verify.py` | Re-derives every reported number from the data |
| `conseq/figdata.py`, `figures.py` | Figure data and figure generation |
| `conseq/o_*/`, `conseq/out*/` | Raw per-run outputs: 35 phase-A runs and phases B–G |
| `paper/` | LaTeX source, figures, and the compiled PDF |
| `DATASHEET.md` | Datasheet following Gebru et al. (2021) |
| `FINDINGS.md` | Complete working log, including retracted claims |

## Reproducing the release

```bash
cd conseq
python3 assemble.py     # raw runs   -> conseq.jsonl, byte-identical to the release
python3 figdata.py      # release    -> figure data
python3 figures.py      # figure data -> paper/figs/*.pdf
python3 verify.py       # paper vs data -> 122 checks
```

Assembly refuses to merge rows whose column semantics differ across instrument versions, so a
future correction cannot retroactively contaminate this release.

`verify.py` re-derives every mechanically checkable quantity in the paper from `conseq.jsonl` and
exits non-zero if the manuscript and the data disagree. It covers the coverage tables, the typing
gradient, every cell of the criterion audit, the artifact taxonomy, and the hardcoded section
cross-references. Seven errors in the manuscript were found this way.

Requirements: Python 3.10+ with PyTorch for the measurement code; Matplotlib for the figures;
`pdftotext` (poppler) for the cross-reference checks in `verify.py`. Re-running the measurement
itself additionally requires the nine language toolchains listed in Appendix D of the paper.

## Corrections

Eleven results were believed before they were found to be artifacts of the instrument. Each is
documented in Appendix C of the paper and in [`FINDINGS.md`](FINDINGS.md), together with the symptom
that exposed it. Two published claims were retracted.

Ten of the eleven were caught by a number being implausibly clean rather than by an error: nothing
crashed, and each produced well-formed output that would have survived casual inspection. One
signature recurs — when positions that ought to be inert, such as punctuation and whitespace, appear
consequential, the instrument is broken. In a working instrument those roles sit near 1%.

The eleventh marks the limit of that heuristic. Rho-1's excess loss had been implemented with the
operands reversed, inverting the criterion; its numbers were unremarkable, and the defect surfaced
only on reading the source paper's equation. It had been reported as the one criterion pointing in
the right direction. Scored as published, it points the wrong way like the other ten.

This log is published because a dataset paper's central claim is that its numbers mean what they
say, and the credible form of that claim is a demonstration that the failure modes are known.

## Citation

```bibtex
@article{azim2026conseq,
  title  = {Most Uncertainty Doesn't Matter: An Execution-Grounded Dataset of
            Per-Token Consequence in Code Generation},
  author = {Azim, Nafew},
  year   = {2026},
  note   = {Dataset and code: https://github.com/nafew-azim/CONSEQ}
}
```

## Licence

The dataset is released under [CC BY 4.0](LICENSE-DATA); the accompanying code under the
[MIT licence](LICENSE). Instances derive from HumanEval (MIT), MBPP (CC BY 4.0), and MultiPL-E
(MIT), each of which permits redistribution of derived work with attribution. Model weights are not
redistributed; the dataset contains only measurements taken with them.

## Contact

Nafew Azim — Department of Electrical and Computer Engineering, North South University —
[nafew.azim@northsouth.edu](mailto:nafew.azim@northsouth.edu)
