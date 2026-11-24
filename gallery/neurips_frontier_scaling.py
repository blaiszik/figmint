"""NeurIPS-style technical report plate: Frontier model scaling, RLVR, and inference-time compute.

ALL DATA ARE SYNTHETIC. Every scaling curve, RLVR training trajectory, thinking-budget
sweep, and long-context retrieval matrix is generated deterministically from smooth
analytical models in this script. Nothing here represents measurements of any real
Google or Anthropic model; the plate demonstrates a model-release technical paper
layout in the figmint house style.

Run through the figmint contract::

    figmint run gallery/neurips_frontier_scaling.py --journal neurips \
        --bundle gallery/output/neurips_frontier_scaling --json
"""

from __future__ import annotations

import numpy as np
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.ticker import FixedLocator, NullFormatter

import figmint as fm

CAPTION = (
    "Synthetic frontier-model release telemetry (NeurIPS full width, 139.7 mm). "
    "(a) Pre-training validation loss across five parameter scales (1B–400B) and the "
    "compute-optimal power-law frontier. "
    "(b) Reinforcement learning post-training trajectories (mean ± 1 SD across 5 seeds) on "
    "AIME '25, GPQA Diamond, and SWE-bench. "
    "(c) Test-time compute scaling with thinking-token budget versus no-thinking baseline. "
    "(d) Long-context needle retrieval recall from 4k to 1M tokens across document depth. "
    "All data are synthetic."
)
LABEL = "fig:frontier_scaling"
TAKEAWAY = (
    "Compute-optimal pre-training, RLVR post-training, and log-linear inference-time "
    "scaling compound smoothly while preserving >=96% retrieval to 1M context."
)
PANEL_NOTES = {
    "a": "Five model scales (1B–400B) trace a power-law Pareto envelope with alpha = 0.054 above L_inf = 1.24 nats.",
    "b": "RLVR post-training lifts AIME '25 from 38% to 88%, GPQA to 82%, and SWE-bench to 77% over 40k steps.",
    "c": "Scaling thinking tokens from 256 to 64k adds +35 pts on Frontier-400B, outperforming Prior Gen at every budget.",
    "d": "Single-needle recall stays 99–100% through 512k tokens and 96–99% across depths at 1M context.",
}

INK = "#1A1D21"
MUTED = "#5D6673"
RULE = "#C8D0DA"
VERMILION = "#C84B31"
TEAL = "#147D6E"
NAVY = "#214D82"
SLATE = "#7A8494"

# Ordered parameter scale magnitude: single-hue cool blue-slate ramp.
SCALE_CMAP = LinearSegmentedColormap.from_list(
    "scale_slate_blue",
    ["#B4CBE6", "#7CA5D4", "#457BB9", "#214F8C", "#0D2447"],
)


def _panel_pretraining(ax) -> None:
    """Panel a: Log-log pre-training scaling curves and compute-optimal frontier."""
    fm.subtle_grid(ax, axis="y", color="#ECEFF4", lw=0.45)

    l_inf = 1.24
    alpha = 0.054
    c0 = 1.2e20

    # Five model parameter scales with realistic compute ranges and compute-optimal knees
    models = [
        ("1B", 1.8e20, 4.5e22, 2.5e21, 0.00),
        ("8B", 1.2e21, 3.0e23, 2.2e22, 0.25),
        ("32B", 9.0e21, 1.8e24, 1.6e23, 0.50),
        ("110B", 6.5e22, 8.5e24, 1.1e24, 0.75),
        ("400B", 4.5e23, 4.0e25, 8.5e24, 1.00),
    ]

    # Compute-optimal power-law envelope
    c_env = np.geomspace(1.4e20, 4.8e25, 300)
    l_env = l_inf + 0.96 * (c0 / c_env) ** alpha

    # Irreducible entropy floor
    ax.axhline(l_inf, color=RULE, ls=":", lw=0.65, zorder=1)
    ax.text(2.0e20, l_inf + 0.032, r"$L_\infty = 1.24$", fontsize=6.0, color=MUTED, va="bottom")

    for name, c_lo, c_hi, c_opt, t_col in models:
        c = np.geomspace(c_lo, c_hi, 140)
        # U-shaped excess above the Pareto frontier away from c_opt
        log_dev = np.log10(c / c_opt)
        excess = 0.075 * np.where(log_dev < 0, 1.45 * log_dev**2, 0.60 * log_dev**2)
        loss = l_inf + 0.96 * (c0 / c) ** alpha + excess
        col = SCALE_CMAP(t_col)
        lw = 1.25 if name == "400B" else 0.90
        ax.plot(c, loss, color=col, lw=lw, zorder=3)
        # Place model-scale tag cleanly above each curve's top-left start (open whitespace!)
        y_start = float(loss[0])
        ax.text(
            c_lo,
            y_start + 0.035,
            name,
            fontsize=6.0,
            color=col if t_col >= 0.45 else "#3E6B9E",
            fontweight="bold" if name == "400B" else "normal",
            va="bottom",
            ha="center",
        )

    ax.plot(c_env, l_env, color=VERMILION, ls="--", lw=1.05, zorder=4)
    ax.annotate(
        r"Frontier: $L - L_\infty \propto C^{-0.054}$",
        xy=(4.2e22, float(l_inf + 0.96 * (c0 / 4.2e22) ** alpha)),
        xytext=(2.6e20, 1.49),
        fontsize=6.0,
        color=VERMILION,
        ha="left",
        va="center",
        arrowprops={"arrowstyle": "-", "color": VERMILION, "lw": 0.55, "shrinkA": 2, "shrinkB": 3},
        zorder=5,
    )

    ax.set_xscale("log")
    ax.set_xlim(9.0e19, 8.0e25)
    ax.set_ylim(1.18, 2.50)
    ax.xaxis.set_major_locator(FixedLocator([1e20, 1e22, 1e24, 1e26]))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_yticks([1.4, 1.8, 2.2])
    ax.set_xlabel(r"Pre-training compute, $C$ (FLOPs)")
    ax.set_ylabel(r"Validation loss, $L$ (nats)")


def _panel_rlvr(ax, rng: np.random.Generator) -> None:
    """Panel b: RLVR post-training trajectories across three benchmarks (5-seed CI)."""
    fm.subtle_grid(ax, axis="y", color="#ECEFF4", lw=0.45)

    steps = np.linspace(0, 40, 81)  # thousands of steps
    # Smooth saturating learning curves + mild KL-decay bump at 15k
    bump = 1.0 / (1.0 + np.exp(-(steps - 15.0) / 2.2))

    def _curve(start: float, gain: float, tau: float, boost: float, noise_sd: float):
        mean = start + gain * (1.0 - np.exp(-steps / tau)) + boost * bump
        # Correlated low-frequency realism without jitter clutter
        wiggle = np.convolve(rng.normal(0.0, noise_sd, size=len(steps) + 6), np.ones(7) / 7, mode="valid")
        mean = mean + wiggle
        sd = 1.4 + 1.1 * np.exp(-steps / 18.0)
        return mean, sd

    aime_m, aime_s = _curve(38.0, 42.0, 11.0, 8.2, 0.9)
    gpqa_m, gpqa_s = _curve(58.0, 20.5, 13.5, 4.0, 0.7)
    swe_m, swe_s = _curve(48.5, 24.0, 15.0, 4.8, 0.8)

    ax.axvline(15.0, color=RULE, ls=":", lw=0.7, zorder=1)
    ax.text(15.8, 36.0, "KL decay", fontsize=6.0, color=MUTED, va="bottom", ha="left")

    specs = [
        ("AIME '25", aime_m, aime_s, VERMILION, "-", "o"),
        ("GPQA", gpqa_m, gpqa_s, NAVY, "-.", "^"),
        ("SWE-bench", swe_m, swe_s, TEAL, "--", "s"),
    ]
    mark_idx = [0, 16, 32, 48, 64, 80]
    for label, mean, sd, col, ls, mk in specs:
        ax.fill_between(steps, mean - sd, mean + sd, color=col, alpha=0.11, lw=0, zorder=2)
        ax.plot(
            steps,
            mean,
            color=col,
            ls=ls,
            lw=1.1,
            marker=mk,
            markevery=mark_idx,
            ms=3.2,
            mfc="white",
            mew=0.85,
            label=label,
            zorder=4,
        )

    fm.direct_labels(ax, pad_pt=4.5, min_sep_pt=9.0, expand_xlim=0.38, fontsize=6.0)

    ax.set_xticks([0, 10, 20, 30, 40])
    ax.set_xticklabels(["0", "10k", "20k", "30k", "40k"])
    ax.set_yticks([40, 60, 80, 100])
    ax.set_ylim(33, 98)
    ax.set_xlabel("RLVR optimization steps")
    ax.set_ylabel("Pass@1 accuracy (%)")


def _panel_test_time(ax) -> None:
    """Panel c: Log-linear inference-time compute scaling with thinking tokens."""
    fm.subtle_grid(ax, axis="y", color="#ECEFF4", lw=0.45)

    budgets = np.array([256, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65536], dtype=float)
    log_b = np.log2(budgets / 256.0)

    f400 = 56.5 + 4.95 * log_b - 0.08 * log_b**2
    f400_ci = np.full_like(f400, 1.6)
    f32 = 44.0 + 4.85 * log_b - 0.05 * log_b**2
    f32_ci = np.full_like(f32, 1.8)
    prior = 42.5 + 3.45 * log_b - 0.04 * log_b**2
    prior_ci = np.full_like(prior, 1.7)

    # Set log scale BEFORE direct_labels so xlim expansion operates in log space
    ax.set_xscale("log", base=2)
    ax.set_xlim(200, 85000)

    # No-thinking baseline reference placed in clean lower-right whitespace
    ax.axhline(52.0, color=RULE, ls=":", lw=0.75, zorder=1)
    ax.text(65536, 49.5, "No thinking (52%)", fontsize=6.0, color=MUTED, va="top", ha="right")

    series = [
        ("Frontier-400B", f400, f400_ci, VERMILION, "-", "o", 1.2),
        ("Frontier-32B", f32, f32_ci, NAVY, "--", "s", 1.05),
        ("Prior Gen", prior, prior_ci, SLATE, ":", "^", 1.0),
    ]
    for label, y, ci, col, ls, mk, lw in series:
        ax.fill_between(budgets, y - ci, y + ci, color=col, alpha=0.10, lw=0, zorder=2)
        ax.plot(
            budgets,
            y,
            color=col,
            ls=ls,
            lw=lw,
            marker=mk,
            ms=3.3,
            mfc="white",
            mew=0.85,
            label=label,
            zorder=4,
        )

    fm.direct_labels(ax, pad_pt=4.5, min_sep_pt=9.0, expand_xlim=0.45, fontsize=6.0)

    ax.xaxis.set_major_locator(FixedLocator([256, 1024, 4096, 16384, 65536]))
    ax.set_xticklabels(["256", "1k", "4k", "16k", "64k"])
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_yticks([40, 60, 80, 100])
    ax.set_ylim(36, 98)
    ax.set_xlabel("Thinking budget (tokens)")
    ax.set_ylabel("Math accuracy (%)")


def _panel_long_context(ax, fig) -> None:
    """Panel d: Long-context needle retrieval matrix up to 1M tokens (single-hue ramp)."""
    contexts = ["4k", "32k", "128k", "512k", "1M"]
    depths = ["0%", "25%", "50%", "75%", "100%"]

    # Realistic Frontier-class near-saturated recall with slight middle-depth dip at 1M
    recall = np.array(
        [
            [100, 100, 100, 100, 99],
            [100, 100, 100, 99, 98],
            [100, 100, 99, 99, 96],
            [100, 100, 100, 99, 97],
            [100, 100, 100, 100, 99],
        ],
        dtype=int,
    )

    im = ax.imshow(
        recall,
        cmap="figmint_teal",
        aspect="auto",
        norm=Normalize(vmin=90, vmax=100),
    )
    fm.style_heatmap(
        ax,
        im,
        cell_border_color="#FFFFFF",
        cell_border_lw=1.3,
        outer_border_color="#D4DCE5",
        annotate=True,
        fmt="{:d}",
        fontsize=6.0,
    )
    ax.set_xticks(range(len(contexts)))
    ax.set_xticklabels(contexts)
    ax.set_yticks(range(len(depths)))
    ax.set_yticklabels(depths)
    ax.set_xlabel("Context length (tokens)")
    ax.set_ylabel("Needle depth")

    cbar = fig.colorbar(im, ax=ax, fraction=0.055, pad=0.04, aspect=18)
    cbar.set_ticks([90, 95, 100])
    fm.style_colorbar(cbar, label="Recall (%)", tick_pt=6.0)


def build(journal: str = "neurips") -> fm.Plate:
    """Construct the four-panel Frontier model technical report plate."""
    rng = np.random.default_rng(2026)
    plate = fm.Plate(
        journal=journal,
        width="full",
        height_mm=106.0,
        layout=(2, 2),
        width_ratios=[1.05, 1.05],
        height_ratios=[1.0, 1.0],
        gap_mm=(9.5, 9.0),
        palette="nature_muted",
    )
    plate.caption = CAPTION
    plate.set_takeaway(TAKEAWAY)
    for k, note in PANEL_NOTES.items():
        plate.note_panel(k, note)

    _panel_pretraining(plate["a"])
    _panel_rlvr(plate["b"], rng)
    _panel_test_time(plate["c"])
    _panel_long_context(plate["d"], plate.fig)

    plate.label_panels(dx_mm=-7.5, dy_mm=1.6)
    return plate


if __name__ == "__main__":
    p = build()
    res = p.bundle("gallery/output/neurips_frontier_scaling")
    print(res.report.summary())
