"""The 11 published selection criteria, scored on identical positions (proposal 9.2 Table 2).

Every criterion is a function of distributions we already compute, so the marginal cost is two
extra forward passes per trajectory (a reference model for Rho-1 excess loss, a teacher for KD
divergence) -- not extra generation.

    P0  random                  floor
    P1  entropy                 RLVR forking-token line, TIP, adaptive decoding
    P2  margin  p1-p2           decoding, selection
    P3  nll     -log p(y_t)     selection
    P4  excess loss vs ref      Rho-1 (2404.07965)
    P5  teacher-student KL      distillation
    P6  expert-generalist delta delta-teacher family
    P7  position  t/L           prefix methods
    P8  confidently-wrong       TIP
    P9  varentropy              adaptive decoding
    P10 min-p indicator         min-p / eta sampling
"""
import torch


def score_all(lg_s, tok_id, lg_ref=None, lg_t=None, lg_gen=None, pos=0.0, rnd=0.0):
    """All criteria at one position. lg_* are raw logit vectors; higher score = 'more important'."""
    p = torch.softmax(lg_s, -1)
    logp = torch.log_softmax(lg_s, -1)
    top2 = p.topk(2).values
    H = float(-(p * torch.log(p + 1e-12)).sum())
    nll = float(-logp[tok_id])
    out = {
        "P0_random": rnd,
        "P1_entropy": H,
        "P2_margin": float(top2[0] - top2[1]),
        "P3_nll": nll,
        "P7_position": pos,
        # surprisal spread: second moment of -log p under p
        "P9_varentropy": float((p * (-torch.log(p + 1e-12) - H) ** 2).sum()),
        # min-p keeps tokens with p >= alpha*p_max; the indicator is how wide that set is
        "P10_minp_width": float((p >= 0.1 * p.max()).sum()),
    }
    out["P8_conf_wrong"] = float((H < 0.5) and (int(p.argmax()) != tok_id))
    if lg_ref is not None:
        # Rho-1 (Lin et al. 2024) eq. 3: excess loss = L_theta - L_RM, i.e. the CURRENT model's
        # loss minus the reference model's, and SLM trains on the top-k% of it. An earlier
        # version had these reversed, which silently inverted the criterion (correction B11).
        out["P4_excess_loss"] = nll - float(-torch.log_softmax(lg_ref, -1)[tok_id])
    if lg_t is not None:
        pt = torch.softmax(lg_t, -1)
        out["P5_teacher_kl"] = float((pt * (torch.log_softmax(lg_t, -1) - logp)).sum())
    if lg_gen is not None:
        out["P6_expert_delta"] = float((torch.log_softmax(lg_t if lg_t is not None else lg_s, -1)
                                        - torch.log_softmax(lg_gen, -1)).abs().mean())
    return out


NAMES = ["P0_random", "P1_entropy", "P2_margin", "P3_nll", "P4_excess_loss", "P5_teacher_kl",
         "P6_expert_delta", "P7_position", "P8_conf_wrong", "P9_varentropy", "P10_minp_width"]


def selftest():
    torch.manual_seed(0)
    peaked = torch.zeros(50); peaked[3] = 20.0
    flat = torch.zeros(50)
    a = score_all(peaked, 3)
    b = score_all(flat, 3)
    assert a["P1_entropy"] < b["P1_entropy"], "peaked must have lower entropy"
    assert a["P2_margin"] > b["P2_margin"], "peaked must have larger margin"
    assert a["P3_nll"] < b["P3_nll"], "peaked must have lower nll on its argmax"
    assert a["P10_minp_width"] < b["P10_minp_width"], "peaked must have narrower min-p set"
    # excess loss is zero when reference == student
    c = score_all(peaked, 3, lg_ref=peaked)
    assert abs(c["P4_excess_loss"]) < 1e-5, c["P4_excess_loss"]
    # ...and POSITIVE when the current model fits the token worse than the reference does,
    # which is the direction Rho-1 selects. This assert is what B11 lacked.
    e = score_all(flat, 3, lg_ref=peaked)
    assert e["P4_excess_loss"] > 0, e["P4_excess_loss"]
    # KL is zero when teacher == student
    d = score_all(peaked, 3, lg_t=peaked)
    assert abs(d["P5_teacher_kl"]) < 1e-5, d["P5_teacher_kl"]
    print("criteria selftest ok")


if __name__ == "__main__":
    selftest()
