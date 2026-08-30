"""Every figure in the paper, built from figdata.json / figdata_typing.json.

Print figures: no hover layer (the medium has none); identity is carried by
direct labels and position as well as hue, so the palette's sub-3:1 contrast
warning is discharged. Palette is the dataviz reference categorical set,
validated with scripts/validate_palette.js (light mode, all checks pass).
"""
import json, math
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

import os
OUT = os.environ.get("CONSEQ_FIGS") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "paper", "figs") + os.sep

BLUE, ORANGE, AQUA, YELLOW, VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#4a3aa7"
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8880", "#e3e2dd"

mpl.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Latin Modern Roman", "CMU Serif", "DejaVu Serif"],
    "mathtext.fontset": "cm",
    "font.size": 9.8, "axes.labelsize": 9.8, "axes.titlesize": 10.4,
    "xtick.labelsize": 9.2, "ytick.labelsize": 9.2, "legend.fontsize": 9.2,
    "axes.edgecolor": MUTED, "axes.linewidth": 0.6,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "axes.labelcolor": INK2, "text.color": INK,
    "figure.dpi": 200, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
    "pdf.fonttype": 42,
})

def bare(ax, left=True, bottom=True, grid="y"):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    if not left:  ax.spines["left"].set_visible(False)
    if not bottom: ax.spines["bottom"].set_visible(False)
    if grid:
        ax.grid(axis=grid, color=GRID, lw=0.6, zorder=0)
        ax.set_axisbelow(True)

LANGNAME = {"js": "JavaScript", "ts": "TypeScript", "py": "Python", "go": "Go",
            "java": "Java", "rs": "Rust", "rb": "Ruby", "php": "PHP", "pl": "Perl"}


# ---------------------------------------------------------------- figure 1
def fig_instrument():
    """The forced-splice measurement and its four-way verdict."""
    fig, ax = plt.subplots(figsize=(6.6, 1.62))
    ax.set_xlim(0, 100); ax.set_ylim(2.2, 25.6); ax.axis("off")

    toks = ["function", "f", "(", "n", ")", "{", "return", "n", "*", "2", ";", "}"]
    hot = 8                       # the operator; its runner-up is '+'
    alt = "+"
    cw = 0.92                     # width per monospace character, in axis units
    pad = 1.5
    widths = [len(t) * cw + pad for t in toks]

    def row(y, tokens, fade, hot_label):
        x = 2.0
        for i, t in enumerate(tokens):
            w = widths[i]
            on = i == hot
            ax.add_patch(FancyBboxPatch((x, y), w - 0.5, 4.6,
                                        boxstyle="round,pad=0,rounding_size=0.7",
                                        fc=ORANGE if on else "#fbfbfa",
                                        ec=ORANGE if on else GRID, lw=0.8, zorder=2))
            ax.text(x + (w - 0.5) / 2, y + 2.3, hot_label if on else t,
                    ha="center", va="center", zorder=3,
                    color="#ffffff" if on else (MUTED if fade else INK),
                    fontfamily="monospace", fontsize=7.8,
                    fontweight="bold" if on else "normal")
            x += w
        return x

    ytop, ybot = 19.0, 6.0
    right = row(ytop, toks, False, toks[hot])
    row(ybot, toks, True, alt)

    ax.text(2.0, ytop + 5.6, "greedy trajectory, verified to pass its tests",
            fontsize=8.2, color=INK2)
    ax.text(2.0, ybot - 2.6, "suffix held fixed \u2014 one execution, no generation, deterministic",
            fontsize=8.2, color=INK2)

    xs = 2.0 + sum(widths[:hot]) + (widths[hot] - 0.5) / 2
    ax.annotate("", xy=(xs, ybot + 5.0), xytext=(xs, ytop - 0.4),
                arrowprops=dict(arrowstyle="-|>", color=ORANGE, lw=1.0,
                                shrinkA=0, shrinkB=0, mutation_scale=7))
    ax.text(xs - 1.6, (ytop + ybot) / 2 + 2.3,
            r"substitute the model's own" "\n" r"second choice $\tilde{y}_t$",
            fontsize=8.2, color=ORANGE, va="center", ha="right", linespacing=1.5)

    bx = right + 2.0
    ax.annotate("", xy=(bx + 1.4, ybot + 2.3), xytext=(bx - 1.2, ybot + 2.3),
                arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=0.9, mutation_scale=7))
    verdicts = [(r"$K^{\mathrm{syn}}$", "does not parse", BLUE),
                (r"$K^{\mathrm{type}}$", "fails the type checker", AQUA),
                (r"$K^{\mathrm{sem}}$", "runs, fails its tests", ORANGE),
                ("pass", "runs, still passes", MUTED)]
    for j, (k, dsc, c) in enumerate(verdicts):
        yy = ybot + 12.2 - j * 3.6
        ax.add_patch(FancyBboxPatch((bx + 2.4, yy - 1.2), 1.7, 2.4,
                                    boxstyle="round,pad=0,rounding_size=0.4",
                                    fc=c, ec="none", zorder=2))
        ax.text(bx + 5.4, yy, k, fontsize=8.6, va="center", color=INK)
        ax.text(bx + 11.4, yy, dsc, fontsize=8.2, va="center", color=INK2)
    fig.savefig(OUT + "fig1_instrument.pdf")
    plt.close(fig)


# ---------------------------------------------------------------- figure 2
def fig_entropy(d):
    """Entropy's recall lift over a random selector, every configuration."""
    cs = sorted(d["configs"], key=lambda x: x["entropy"] - x["budget"])
    lifts = [(x["entropy"] - x["budget"]) * 100 for x in cs]
    labels = [f"{x['family']} {x['params']} \u00b7 {LANGNAME[x['lang']]}" for x in cs]
    under = [x["problems"] < 25 for x in cs]   # the manifest's own criterion

    fig, ax = plt.subplots(figsize=(5.4, 5.0))
    for i, (l, u) in enumerate(zip(lifts, under)):
        c = BLUE if l < 0 else ORANGE
        ax.plot([0, l], [i, i], color=c, lw=1.0, alpha=0.30 if u else 0.85, zorder=2,
                solid_capstyle="round")
        ax.plot([l], [i], "o", ms=4.4, color=c, mec="#ffffff", mew=0.8,
                alpha=0.40 if u else 1.0, zorder=3)
    ax.axvline(0, color=INK2, lw=0.9, zorder=4)
    ax.set_yticks(range(len(cs))); ax.set_yticklabels(labels, fontsize=7.8, color=INK2)
    ax.set_ylim(len(cs) - 0.4, -1.9)          # most negative at the top
    ax.set_xlim(-14.5, 6.2)
    ax.set_xlabel("recall lift over a random selector at matched budget (pp)")
    bare(ax, grid="x")
    ax.spines["left"].set_visible(False); ax.tick_params(axis="y", length=0)
    ax.annotate("entropy finds less than chance", xy=(0.30, 1.012), xycoords="axes fraction",
                fontsize=8.4, color=BLUE, ha="center")
    ax.annotate("more", xy=(0.86, 1.012), xycoords="axes fraction",
                fontsize=8.4, color=ORANGE, ha="center")
    fig.savefig(OUT + "fig2_entropy.pdf")
    plt.close(fig)


# ---------------------------------------------------------------- figure 3
def fig_selector(d):
    """Budget-recall: the role selector against entropy and random."""
    langs = ["js", "ts", "go", "java", "py", "rs"]
    fig, axes = plt.subplots(2, 3, figsize=(6.6, 3.6), sharex=True, sharey=True)
    for ax, lang in zip(axes.ravel(), langs):
        c = d["curves"][lang]
        b = [0] + [v * 100 for v in c["budget"]] + [100]
        r = [0] + [v * 100 for v in c["role"]] + [100]
        e = [0] + [v * 100 for v in c["entropy"]] + [100]
        ax.plot([0, 100], [0, 100], color=MUTED, lw=1.0, ls=(0, (3, 2)), zorder=2)
        ax.plot(b, e, color=AQUA, lw=1.6, zorder=3)
        ax.plot(b, r, color=BLUE, lw=1.8, zorder=4)
        ax.fill_between(b, e, [min(x, y) for x, y in zip(b, e)],
                        color=AQUA, alpha=0.10, zorder=1)
        ax.set_title(LANGNAME[lang], loc="left", color=INK, pad=3)
        ax.set_xlim(0, 100); ax.set_ylim(0, 100)
        ax.set_xticks([0, 50, 100]); ax.set_yticks([0, 50, 100])
        bare(ax, grid=None)
    axes[0, 0].text(8, 88, "role", color=BLUE, fontsize=8.6, fontweight="bold")
    axes[0, 0].text(52, 30, "entropy", color=AQUA, fontsize=8.6, fontweight="bold")
    axes[0, 0].text(46, 62, "random", color=MUTED, fontsize=8.2, rotation=33)
    fig.supxlabel("selection budget (% of positions)", fontsize=9.8, color=INK2, y=0.055)
    fig.supylabel("consequential tokens recovered (%)", fontsize=9.8, color=INK2, x=0.02)
    fig.tight_layout(w_pad=1.1, h_pad=1.0, rect=(0.01, 0.045, 1, 1))
    fig.savefig(OUT + "fig3_selector.pdf")
    plt.close(fig)


# ---------------------------------------------------------------- figure 4
def fig_typing(t):
    """Where a wrong token surfaces, by the language's typing discipline."""
    order = ["rb", "pl", "php", "py", "js", "ts", "go", "java", "rs"]
    disc = {"rb": "dynamic", "pl": "dynamic", "php": "dynamic", "py": "dynamic",
            "js": "dynamic", "ts": "gradual", "go": "static", "java": "static", "rs": "static"}
    fig, ax = plt.subplots(figsize=(6.3, 2.9))
    fig.subplots_adjust(left=0.20)
    ys, gap = [], 0
    for i, k in enumerate(order):
        if i and disc[k] != disc[order[i - 1]]:
            gap += 0.55
        ys.append(i + gap)
    for k, y in zip(order, ys):
        v = t[k]
        segs = [(v["K_syn"] * 100, BLUE, r"$K^{\mathrm{syn}}$"),
                (v["K_type"] * 100, AQUA, r"$K^{\mathrm{type}}$"),
                (v["K_sem"] * 100, ORANGE, r"$K^{\mathrm{sem}}$")]
        left = 0
        for w, c, _ in segs:
            if w <= 0:
                continue
            ax.barh(y, w - 0.35, left=left, height=0.62, color=c, zorder=3)  # 2px surface gap
            left += w
        ax.text(left + 1.2, y, f"{v['K_sem']*100:.1f}%", va="center", fontsize=8.4,
                color=ORANGE, fontweight="bold")
    ax.set_yticks(ys); ax.set_yticklabels([LANGNAME[k] for k in order], color=INK)
    ax.invert_yaxis()
    ax.set_xlabel("share of positions where the substitution is consequential (%)")
    ax.set_xlim(0, 76)
    bare(ax, grid="x"); ax.spines["left"].set_visible(False); ax.tick_params(axis="y", length=0)
    import matplotlib.transforms as mtr
    tf = mtr.blended_transform_factory(ax.transAxes, ax.transData)
    groups = [("dynamic", ys[0], ys[4]), ("gradual", ys[5], ys[5]), ("static", ys[6], ys[8])]
    for lab, y0, y1 in groups:
        ax.plot([-0.235, -0.235], [y0 - 0.32, y1 + 0.32], transform=tf,
                color=GRID, lw=1.4, clip_on=False, solid_capstyle="butt", zorder=1)
        ax.text(-0.255, (y0 + y1) / 2, lab, transform=tf, fontsize=8.2, color=MUTED,
                va="center", ha="right", clip_on=False)
    hs = [plt.Rectangle((0, 0), 1, 1, color=c) for c in (BLUE, AQUA, ORANGE)]
    ax.legend(hs, ["does not parse", "fails the type checker", "runs, fails its tests"],
              frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.16),
              labelcolor=INK2, handlelength=1.1, handleheight=0.9, columnspacing=1.4)
    fig.savefig(OUT + "fig4_typing.pdf")
    plt.close(fig)


# ---------------------------------------------------------------- figure 5
def fig_counterfactual():
    """Consequence mass moves down the pipeline when the alternative must parse."""
    data = {  # measured: o_cfjs / o_cfts / o_cfgo against matched top-2 positions
        "JavaScript": {"top-2": (29.7, 0.0, 24.7), "parse": (5.0, 0.0, 38.8)},
        "TypeScript": {"top-2": (31.6, 18.3, 9.6), "parse": (4.3, 29.6, 12.5)},
        "Go":         {"top-2": (30.0, 14.6, 13.2), "parse": (5.1, 24.1, 16.1)},
    }
    keys = [(r"$K^{\mathrm{syn}}$", 0, BLUE), (r"$K^{\mathrm{type}}$", 1, AQUA),
            (r"$K^{\mathrm{sem}}$", 2, ORANGE)]
    fig, axes = plt.subplots(1, 3, figsize=(6.6, 2.6), sharey=True)
    for ax, (lang, dd) in zip(axes, data.items()):
        for name, idx, c in keys:
            a, b = dd["top-2"][idx], dd["parse"][idx]
            if a == 0 and b == 0:
                continue
            ax.plot([0, 1], [a, b], color=c, lw=1.7, zorder=3, solid_capstyle="round")
            ax.plot([0, 1], [a, b], "o", ms=5.0, color=c, mec="#ffffff", mew=0.9, zorder=4)
            dy = 0.0
            if lang == "Go" and idx == 2:      # 13.2 sits under 14.6; separate them
                dy = -1.5
            ax.text(-0.07, a + dy, f"{a:.1f}", ha="right", va="center", fontsize=8.0, color=c)
            ax.text(1.07, b, f"{b:.1f}", ha="left", va="center", fontsize=8.0, color=c,
                    fontweight="bold")
        ax.set_xlim(-0.42, 1.42); ax.set_ylim(0, 44)
        ax.set_xticks([0, 1]); ax.set_xticklabels(["2nd\nchoice", "must\nparse"], fontsize=8.4)
        ax.set_title(lang, loc="left", color=INK, pad=4)
        bare(ax, grid="y"); ax.spines["bottom"].set_visible(False)
        ax.tick_params(axis="x", length=0)
    axes[0].set_ylabel("share of positions (%)")
    axes[0].text(0.06, 41.0, r"$K^{\mathrm{syn}}$", color=BLUE, fontsize=8.8)
    axes[0].text(0.72, 41.0, r"$K^{\mathrm{sem}}$", color=ORANGE, fontsize=8.8)
    axes[1].text(0.72, 41.0, r"$K^{\mathrm{type}}$", color=AQUA, fontsize=8.8)
    fig.tight_layout(w_pad=1.6)
    fig.savefig(OUT + "fig5_counterfactual.pdf")
    plt.close(fig)


# ---------------------------------------------------------------- figure 6
def fig_boundary():
    """Composition holds on a fixed sequence; nothing transfers off it."""
    m = [1, 2, 3, 5, 8, 12, 20, 32]
    passr = [100.0, 100.0, 100.0, 99.5, 100.0, 99.4, 94.6, 92.3]
    # phase C decoding arms: mean paired difference vs random, with t on 44 problems
    arms = [("Greedy (commit everywhere)", 0.144, 3.50),
            ("Entropy-selected commits", 0.068, 1.85),
            ("Oracle (measured ground truth)", 0.023, 0.53),
            ("Role-selected commits", -0.053, -1.02)]
    tcrit = 2.017  # two-sided 95%, df = 43

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.6, 3.1),
                                 gridspec_kw={"width_ratios": [1, 1.28]})
    xi = range(len(m))                      # even spacing: the levels are a design, not a scale
    a1.plot(xi, passr, color=BLUE, lw=1.8, zorder=3)
    a1.plot(xi, passr, "o", ms=4.6, color=BLUE, mec="#ffffff", mew=0.8, zorder=4)
    a1.set_xticks(list(xi)); a1.set_xticklabels(m, fontsize=8.6)
    a1.set_ylim(88, 101.6)
    a1.set_yticks([90, 92, 94, 96, 98, 100])
    a1.set_xlabel("simultaneous harmless edits $m$")
    a1.set_ylabel("programs still passing (%)")
    bare(a1)

    XMIN, XMAX = -20, 27
    for i, (name, dmean, t) in enumerate(arms):
        se = abs(dmean / t) if t else 0
        lo, hi = (dmean - tcrit * se) * 100, (dmean + tcrit * se) * 100
        sig = lo > 0 or hi < 0
        c = BLUE if sig else MUTED
        a2.plot([lo, hi], [i, i], color=c, lw=1.5, solid_capstyle="round", zorder=3)
        a2.plot([dmean * 100], [i], "o", ms=5.4, color=c, mec="#ffffff", mew=0.9, zorder=4)
        a2.text(XMIN + 0.8, i - 0.34, name, fontsize=8.0, color=INK2, va="bottom", zorder=5)
    a2.axvline(0, color=INK2, lw=0.9, zorder=2)
    a2.set_yticks([]); a2.set_ylim(len(arms) - 0.45, -0.75)
    a2.set_xlim(XMIN, XMAX)
    a2.set_xlabel("pass@1 difference vs. random selection (pp)")
    bare(a2, grid="x"); a2.spines["left"].set_visible(False)
    a2.text(13.6, 2.0, "$t = 0.53$", fontsize=7.8, color=MUTED, va="center")
    fig.tight_layout(w_pad=1.8)
    fig.savefig(OUT + "fig6_boundary.pdf", bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)


if __name__ == "__main__":
    d = json.load(open("figdata.json"))
    t = json.load(open("figdata_typing.json"))
    fig_instrument(); fig_entropy(d); fig_selector(d); fig_typing(t)
    fig_counterfactual(); fig_boundary()
    print("wrote 6 figures to", OUT)
