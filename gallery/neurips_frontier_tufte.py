"""Tufte-disciplined NeurIPS technical report plate: Frontier model release.

ALL DATA ARE SYNTHETIC. Every scaling curve, benchmark score, inference-time thinking
curve, and training-telemetry trace is generated deterministically from analytical toy
models in this script. Nothing here is a measurement of any real Google or Anthropic
model; the plate demonstrates Edward Tufte's principles (range frames with marginal rug,
paired slopegraph, small multiples with ghosted peer context, and training sparklines)
at exact NeurIPS full width (139.7 mm).

Run through the mintfig contract::

    mintfig run gallery/neurips_frontier_tufte.py --journal neurips \
        --bundle gallery/output/neurips_frontier_tufte --json
"""

from __future__ import annotations

import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import FixedLocator, NullFormatter

import mintfig as mint

CAPTION = (
    "Synthetic frontier-model release technical report engineered with Tufte visual grammar "
    "(NeurIPS full width, 139.7 mm). "
    "(a) Pre-training scaling laws across five parameter scales (1B–400B) with range-framed "
    "spines trimmed to data bounds and marginal checkpoint rug ticks. "
    "(b) Paired evaluation slopegraph from Prior Gen to Frontier-400B across eight reasoning, "
    "coding, and knowledge benchmarks, highlighting the largest agentic leaps. "
    "(c) Shared-axis small multiples for inference-time thinking-token scaling across Math, "
    "Coding, and Science with muted ghost curves of peer domains and dashed Prior Gen baselines. "
    "(d) Frameless training telemetry sparklines with shaded target bands and final values. "
    "All data are synthetic."
)
LABEL = "fig:frontier_tufte"
TAKEAWAY = (
    "Frontier-400B follows a clean C^-0.054 scaling envelope, lifts reasoning benchmarks up to "
    "+50 pts over Prior Gen, scales log-linearly with thinking tokens across domains, and trains "
    "stably within target telemetry bands."
)
PANEL_NOTES = {
    "a": "Range-framed scaling curves (1B–400B) trace L - L_inf ~ C^-0.054 above L_inf = 1.24 nats.",
    "b": "Slopegraph shows broad gains across all 8 benchmarks, led by AIME '25 (+50), SWE-bench (+28), and SimpleQA (+27).",
    "c": "Shared-axis small multiples with ghosted peers isolate log-linear test-time scaling in Math, Coding, and Science.",
    "d": "Four sparklines confirm smooth loss decay (1.71), bounded grad norm (0.42), 54.8% MFU, and 0.018 RLVR KL.",
}

INK = "#1A1D21"
MUTED = "#5D6673"
RULE = "#C8D0DA"
VERMILION = "#C84B31"
NAVY = "#214D82"
SLATE = "#7A8494"

SCALE_CMAP = LinearSegmentedColormap.from_list(
    "tufte_scale_blue",
    ["#B4CBE6", "#7CA5D4", "#457BB9", "#214F8C", "#0D2447"],
)


def _panel_a_range_scaling(ax) -> None:
    """Panel a: Range-framed pre-training scaling curves with marginal checkpoint rug."""
    l_inf = 1.24
    alpha = 0.054
    c0 = 1.2e20

    models = [
        ("1B", 1.0e20, 4.2e22, 2.5e21, 0.00),
        ("8B", 1.2e21, 2.8e23, 2.2e22, 0.25),
        ("32B", 9.0e21, 1.6e24, 1.6e23, 0.50),
        ("110B", 6.5e22, 8.0e24, 1.1e24, 0.75),
        ("400B", 4.5e23, 3.8e25, 8.5e24, 1.00),
    ]

    c_env = np.geomspace(1.0e20, 3.8e25, 240)
    l_env = l_inf + 0.96 * (c0 / c_env) ** alpha

    ax.axhline(l_inf, color=RULE, ls=":", lw=0.6, zorder=1)
    ax.text(1.15e20, l_inf + 0.03, r"$L_\infty = 1.24$", fontsize=6.0, color=MUTED, va="bottom")

    ckpt_c: list[float] = []
    ckpt_l: list[float] = []
    all_c: list[float] = []
    all_l: list[float] = []

    for name, c_lo, c_hi, c_opt, t_col in models:
        c = np.geomspace(c_lo, c_hi, 120)
        log_dev = np.log10(c / c_opt)
        excess = 0.075 * np.where(log_dev < 0, 1.45 * log_dev**2, 0.60 * log_dev**2)
        loss = l_inf + 0.96 * (c0 / c) ** alpha + excess
        col = SCALE_CMAP(t_col)
        ax.plot(c, loss, color=col, lw=1.25 if name == "400B" else 0.85, zorder=3)
        all_c.extend([float(c[0]), float(c[-1])])
        all_l.extend([float(loss.min()), float(loss.max())])
        # Sample 5 evaluation checkpoints per run for the Tufte marginal rug
        idx_rug = np.linspace(10, len(c) - 1, 5, dtype=int)
        ckpt_c.extend(c[idx_rug].tolist())
        ckpt_l.extend(loss[idx_rug].tolist())

        ax.text(
            c_lo * (1.25 if name == "1B" else 1.0),
            float(loss[0]) + 0.035,
            name,
            fontsize=6.0,
            color=col if t_col >= 0.45 else "#3E6B9E",
            fontweight="bold" if name == "400B" else "normal",
            ha="center",
            va="bottom",
        )

    ax.plot(c_env, l_env, color=VERMILION, ls="--", lw=1.05, zorder=4)
    ax.annotate(
        r"$L - L_\infty \propto C^{-0.054}$",
        xy=(4.5e22, float(l_inf + 0.96 * (c0 / 4.5e22) ** alpha)),
        xytext=(2.5e20, 1.48),
        fontsize=6.0,
        color=VERMILION,
        ha="left",
        va="center",
        arrowprops={"arrowstyle": "-", "color": VERMILION, "lw": 0.55, "shrinkA": 2, "shrinkB": 3},
        zorder=5,
    )

    ax.set_xscale("log")
    ax.set_xlim(6.5e19, 6.5e25)
    ax.set_ylim(1.18, 2.62)
    ax.xaxis.set_major_locator(FixedLocator([1e20, 1e22, 1e24]))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_yticks([1.7, 2.0, 2.3])

    # True Tufte range frame: spines trimmed strictly to actual data domain + checkpoint rug
    mint.range_frame(
        ax,
        xdata=np.array(ckpt_c + all_c),
        ydata=np.array(ckpt_l + all_l),
        rug=True,
        rug_color="#9AA4B2",
        rug_frac=0.032,
        rug_lw=0.45,
    )
    ax.set_xlabel(r"Pre-training compute, $C$ (FLOPs)")
    ax.set_ylabel(r"Validation loss, $L$ (nats)")


def _panel_b_slopegraph(ax) -> None:
    """Panel b: Frameless Tufte slopegraph (Prior Gen -> Frontier-400B across 8 evals)."""
    benchmarks = [
        "MATH-500",
        "AIME '25",
        "MMLU-Pro",
        "GPQA",
        "MMMU",
        "SWE-bench",
        "LiveCode",
        "SimpleQA",
    ]
    prior = [79, 38, 74, 61, 68, 49, 44, 31]
    frontier = [95, 88, 86, 82, 81, 77, 74, 58]

    mint.slopegraph(
        ax,
        prior,
        frontier,
        benchmarks,
        left_label="Prior Gen",
        right_label="Frontier-400B",
        highlight={"AIME '25", "SWE-bench", "SimpleQA"},
        highlight_color=VERMILION,
        base_color="#9AA5B4",
        fmt="{:.0f}",
        fontsize=6.0,
        min_sep_pt=9.0,
        show_delta=True,
    )
    ax.set_xlim(-0.42, 2.55)


def _panel_c_small_multiples(ax) -> None:
    """Panel c: Three shared-axis small multiples with ghosted peer curves."""
    ax.set_axis_off()

    budgets = np.array([256, 1024, 4096, 16384, 65536], dtype=float)
    log_b = np.log2(budgets / 256.0)

    domains = [
        ("Math", 56.0 + 4.45 * log_b - 0.04 * log_b**2, 41.0 + 3.20 * log_b),
        ("Coding", 49.0 + 3.85 * log_b - 0.03 * log_b**2, 39.0 + 2.55 * log_b),
        ("Science", 62.0 + 2.75 * log_b - 0.02 * log_b**2, 53.0 + 1.85 * log_b),
    ]

    sub_axes = []
    n = len(domains)
    gap = 0.04
    w = (1.0 - gap * (n - 1)) / n
    for i in range(n):
        sub = ax.inset_axes([i * (w + gap), 0.16, w, 0.72])
        sub_axes.append(sub)

    # First draw muted ghost copies of peer domains across all 3 panels ("Compared to what?")
    mint.ghost_context(
        [(sub_axes[i], budgets, domains[i][1]) for i in range(n)],
        ghost_color="#CFD7E2",
        ghost_lw=0.65,
        ghost_alpha=0.90,
    )

    for i, ((title, y_front, y_prior), sub) in enumerate(zip(domains, sub_axes, strict=True)):
        sub.plot(budgets, y_prior, color=SLATE, ls="--", lw=0.75, zorder=2)
        sub.plot(
            budgets,
            y_front,
            color=VERMILION,
            ls="-",
            lw=1.25,
            marker="o",
            ms=2.6,
            mfc="white",
            mew=0.85,
            zorder=4,
        )
        sub.set_xscale("log", base=2)
        sub.set_xlim(180, 680000)
        sub.set_ylim(34, 102)
        sub.xaxis.set_major_locator(FixedLocator([256, 4096, 65536]))
        sub.set_xticklabels(["256", "4k", "64k"], fontsize=6.0)
        sub.xaxis.set_minor_formatter(NullFormatter())
        sub.set_yticks([40, 70, 100])
        sub.tick_params(labelsize=6.0, length=2.0, pad=1.8)
        sub.spines["top"].set_visible(False)
        sub.spines["right"].set_visible(False)
        sub.spines["bottom"].set_bounds(256.0, 65536.0)
        sub.spines["left"].set_bounds(40.0, 100.0)
        sub.set_title(title, loc="left", fontsize=6.2, fontweight="bold", color=INK, pad=3.0)

        # Tufte right-edge direct endpoint label (strictly clear of curves and ghosts)
        sub.text(
            65536 * 1.48,
            float(y_front[-1]),
            f"{y_front[-1]:.0f}%",
            ha="left",
            va="center",
            fontsize=6.0,
            fontweight="bold",
            color=VERMILION,
        )
        if i == 0:
            sub.set_ylabel("Accuracy (%)", fontsize=6.5, labelpad=2.5)
        else:
            sub.set_yticklabels([])
            sub.spines["left"].set_visible(False)
            sub.tick_params(axis="y", length=0)
        if i == 2:
            # Compact inline key for solid vs dashed in open lower-right corner
            sub.text(65536, 40.5, "dashed: Prior", ha="right", va="bottom", fontsize=6.0, color=MUTED)

    ax.text(
        0.50,
        -0.06,
        "Thinking budget (tokens)",
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=6.8,
        color=INK,
    )


def _panel_d_sparklines(ax, rng: np.random.Generator) -> None:
    """Panel d: Four aligned Tufte training-run telemetry sparklines."""
    ax.set_axis_off()
    steps = np.linspace(0, 100, 90)

    # 1. Pre-training loss
    loss_y = 1.66 + 0.68 * np.exp(-steps / 26.0) + rng.normal(0.0, 0.012, size=len(steps))
    loss_y[-1] = 1.71
    # 2. Gradient norm (one early transient spike quickly damped)
    grad_y = 0.42 + 0.06 * np.sin(steps / 9.0) + 0.34 * np.exp(-((steps - 24.0) / 3.0) ** 2) + rng.normal(0.0, 0.025, size=len(steps))
    grad_y[-1] = 0.42
    # 3. Hardware utilization MFU (%)
    mfu_y = 51.0 + 4.0 * (1.0 - np.exp(-steps / 16.0)) + rng.normal(0.0, 0.45, size=len(steps))
    mfu_y[-1] = 54.8
    # 4. RLVR KL divergence
    kl_y = 0.008 + 0.012 * (1.0 - np.exp(-steps / 22.0)) + 0.004 * np.exp(-((steps - 42.0) / 10.0) ** 2) + rng.normal(0.0, 0.0008, size=len(steps))
    kl_y[-1] = 0.018

    specs = [
        ("Train loss (nats)", loss_y, (1.65, 1.80), "{:.2f}"),
        ("Grad norm", grad_y, (0.28, 0.58), "{:.2f}"),
        ("MFU (%)", mfu_y, (50.0, 58.0), "{:.1f}%"),
        ("RLVR KL", kl_y, (0.012, 0.024), "{:.3f}"),
    ]

    # 2x2 frameless grid of sparklines across the full-width bottom strip
    coords = [
        (0.00, 0.56, 0.46, 0.38),
        (0.52, 0.56, 0.46, 0.38),
        (0.00, 0.10, 0.46, 0.38),
        (0.52, 0.10, 0.46, 0.38),
    ]
    for (lbl, vals, band, fmt_s), box in zip(specs, coords, strict=True):
        sub = ax.inset_axes(list(box))
        mint.sparkline(
            sub,
            steps,
            vals,
            label=lbl,
            color=INK,
            lw=0.85,
            normal_band=band,
            band_color="#E7EEF6",
            show_minmax=True,
            end_color=VERMILION,
            end_fmt=fmt_s,
            fontsize=6.0,
        )

    ax.text(
        0.99,
        -0.02,
        r"Training horizon: $0 \rightarrow 15\mathrm{T}$ tokens  |  shaded band = target range  |  dot = final",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=6.0,
        color=MUTED,
    )


def build(journal: str = "neurips") -> mint.Plate:
    """Construct the Tufte-redesigned Frontier model release technical report plate."""
    rng = np.random.default_rng(2026)
    plate = mint.Plate(
        journal=journal,
        width="full",
        height_mm=124.0,
        layout=[["a", "b"], ["c", "b"], ["d", "d"]],
        width_ratios=[1.16, 0.90],
        height_ratios=[1.12, 1.04, 0.66],
        gap_mm=(8.5, 8.5),
        palette="nature_muted",
    )
    plate.caption = CAPTION
    plate.set_takeaway(TAKEAWAY)
    for k, note in PANEL_NOTES.items():
        plate.note_panel(k, note)

    _panel_a_range_scaling(plate["a"])
    _panel_b_slopegraph(plate["b"])
    _panel_c_small_multiples(plate["c"])
    _panel_d_sparklines(plate["d"], rng)

    plate.label_panels(dx_mm=-7.0, dy_mm=1.6)
    return plate


if __name__ == "__main__":
    p = build()
    res = p.bundle("gallery/output/neurips_frontier_tufte")
    print(res.report.summary())
