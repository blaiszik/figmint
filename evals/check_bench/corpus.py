"""Wild-50 verification corpus for ``mint.check``.

Fifty deterministic, zero-network Matplotlib figures reproducing real-world
Matplotlib and Seaborn artist idioms:

- 25 **clean** figures (expected ``ship=True``): ``QuadMesh`` heatmaps +
  colorbars, ``fill_between`` CI bands, count & density histograms, boxplots,
  violinplots, grouped / horizontal / stacked bars, multi-line date series,
  log-log scaling, scatter + OLS fit, multi-panel subplots, dark theme, framed
  legends, unit conversions, and ML/science headlines with model names,
  precision tags, sample counts, years, and p-values.
- 25 **defective** figures (expected ``ship=False`` with labeled ground-truth
  rules): hallucinated claim numbers across chart types, truncated bar
  baselines, tiny text at 700 px and 450 px, overlapping labels, line-struck
  labels, rainbow colormaps (``jet`` / ``hsv`` / ``rainbow``), malformed text
  (``%%``, ``nan``, ASCII hyphen minus), and canvas-clipped text.

Depends only on Matplotlib, NumPy, and the Python standard library.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

Split = Literal["clean", "defective"]


@dataclass(frozen=True)
class WildCase:
    """One benchmark case in the Wild-50 corpus."""

    case_id: str
    split: Split
    artist_category: str
    defect_category: str | None
    expected_ship: bool
    expected_rules: tuple[str, ...]
    description: str
    builder: Callable[[], Figure]
    claim: str | None = None
    width: str | int = "chat"
    dpi: float = 100.0
    bbox_inches: str | None = None


def _clean_fig(
    nrows: int = 1,
    ncols: int = 1,
    *,
    figsize: tuple[float, float] = (7.0, 4.0),
    sharex: bool = False,
    sharey: bool = False,
) -> tuple[Figure, object]:
    fig, ax = plt.subplots(
        nrows,
        ncols,
        figsize=figsize,
        sharex=sharex,
        sharey=sharey,
        layout="constrained",
    )
    return fig, ax


# ---------------------------------------------------------------------------
# 25 CLEAN REAL-WORLD FIGURES (expected ship=True)
# ---------------------------------------------------------------------------


def _clean_01_quadmesh_heatmap_colorbar() -> Figure:
    """Seaborn heatmap idiom: QuadMesh + colorbar + cell annotations."""
    mat = np.array(
        [
            [1.00, 0.62, 0.41, 0.35],
            [0.62, 1.00, 0.92, 0.48],
            [0.41, 0.92, 1.00, 0.55],
            [0.35, 0.48, 0.55, 1.00],
        ]
    )
    layers = ["L1", "L2", "L3", "L4"]
    fig, ax = _clean_fig(figsize=(6.8, 4.4))
    mesh = ax.pcolormesh(mat, cmap="viridis", vmin=0.0, vmax=1.0, edgecolors="white", lw=0.8)
    cbar = fig.colorbar(mesh, ax=ax)
    cbar.set_label("Cosine similarity", fontsize=10)
    cbar.ax.tick_params(labelsize=10)
    ticks = np.arange(4) + 0.5
    ax.set_xticks(ticks, layers, fontsize=10)
    ax.set_yticks(ticks, layers, fontsize=10)
    ax.set_xlabel("Layer", fontsize=10)
    ax.set_ylabel("Layer", fontsize=10)
    for r in range(4):
        for c in range(4):
            val = mat[r, c]
            ax.text(
                c + 0.5,
                r + 0.5,
                f"{val:.2f}",
                ha="center",
                va="center",
                fontsize=10,
                color="black" if val > 0.7 else "white",
            )
    ax.set_title("In 2026, L2–L3 similarity peaks at 0.92", fontsize=13, loc="left")
    return fig


def _clean_02_quadmesh_diverging_ratio() -> Figure:
    """QuadMesh latency grid with diverging RdBu_r colormap and ratio claim."""
    mat = np.array(
        [
            [12.0, 18.0, 24.0],
            [16.0, 30.0, 36.0],
            [20.0, 42.0, 48.0],
        ]
    )
    fig, ax = _clean_fig(figsize=(6.8, 4.2))
    mesh = ax.pcolormesh(mat, cmap="RdBu_r", vmin=10.0, vmax=50.0, edgecolors="white", lw=0.8)
    cbar = fig.colorbar(mesh, ax=ax)
    cbar.set_label("Latency (ms)", fontsize=10)
    cbar.ax.tick_params(labelsize=10)
    ax.set_xticks([0.5, 1.5, 2.5], ["B1", "B4", "B16"], fontsize=10)
    ax.set_yticks([0.5, 1.5, 2.5], ["S128", "S512", "S2048"], fontsize=10)
    ax.set_xlabel("Batch size", fontsize=10)
    ax.set_ylabel("Sequence length", fontsize=10)
    ax.set_title("Peak cell reaches 48 ms, 4x the minimum cell", fontsize=13, loc="left")
    return fig


def _clean_03_ci_band_fill_between() -> Figure:
    """Seaborn lineplot idiom: mean line + fill_between 95% CI band."""
    epochs = np.arange(0, 11)
    mean = np.array([52, 60, 66, 71, 75, 78, 80, 82, 83, 84, 84], dtype=float)
    ci = np.full_like(mean, 2.5)
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.plot(epochs, mean, color="#2563eb", lw=2.2, label="Llama-3.1 8B")
    ax.fill_between(epochs, mean - ci, mean + ci, color="#2563eb", alpha=0.2, label="95% CI (5 seeds)")
    ax.set_xlabel("Epoch", fontsize=10)
    ax.set_ylabel("Accuracy (%)", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.legend(loc="lower right", fontsize=10, frameon=True)
    ax.set_title("Llama-3.1 8B reaches 84% accuracy across 5 seeds (95% CI)", fontsize=12, loc="left")
    return fig


def _clean_04_ci_band_upper_bound() -> Figure:
    """Two CI bands where headline cites the upper fill_between envelope peak."""
    steps = np.arange(0, 6) * 2
    base = np.array([60.0, 66.0, 70.0, 74.0, 76.0, 78.0])
    tuned = np.array([62.0, 70.0, 76.0, 81.0, 85.0, 88.0])
    sd = np.array([3.0, 3.0, 4.0, 4.0, 5.0, 6.0])
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.plot(steps, base, color="#64748b", lw=2, label="Baseline")
    ax.fill_between(steps, base - 3.0, base + 3.0, color="#64748b", alpha=0.18)
    ax.plot(steps, tuned, color="#0f766e", lw=2.2, label="Tuned (±1 s.d., n = 8)")
    ax.fill_between(steps, tuned - sd, tuned + sd, color="#0f766e", alpha=0.2)
    ax.set_xlabel("Training hours", fontsize=10)
    ax.set_ylabel("Validation score (%)", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.legend(loc="lower right", fontsize=10, frameon=True)
    ax.set_title("Upper 1 s.d. envelope reaches 94% on validation", fontsize=13, loc="left")
    return fig


def _clean_05_hist_counts() -> Figure:
    """Seaborn histplot idiom: count histogram with contiguous BarContainer bins."""
    rng = np.random.default_rng(42)
    # Tight peak around 40 ms so peak bin center is cleanly ~40 ms
    samples = np.concatenate(
        [
            rng.normal(40.0, 3.0, 140),
            rng.normal(55.0, 6.0, 60),
        ]
    )
    bins = np.linspace(25.0, 75.0, 11)  # bin width 5 -> bin [37.5, 42.5] center = 40.0
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.hist(samples, bins=bins, color="#2563eb", edgecolor="white", linewidth=0.8)
    ax.set_xlabel("Latency (ms)", fontsize=10)
    ax.set_ylabel("Requests (count)", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.set_title("Request latency peaks at 40 ms across 200 samples", fontsize=13, loc="left")
    return fig


def _clean_06_hist_density() -> Figure:
    """Density histogram with median reference line and model/precision tokens."""
    rng = np.random.default_rng(7)
    samples = rng.normal(18.0, 2.4, 300)
    samples = samples - (np.median(samples) - 18.0)  # exact median 18.0
    bins = np.linspace(10.0, 26.0, 17)  # bin width 1.0 -> center at 18.0
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.hist(samples, bins=bins, density=True, color="#0d9488", alpha=0.75, edgecolor="white")
    ax.set_xlabel("Inference time (ms)", fontsize=10)
    ax.set_ylabel("Density", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.set_title("ResNet-50 (FP16) median inference time is 18 ms", fontsize=13, loc="left")
    return fig


def _clean_07_boxplot_patch_artist() -> Figure:
    """Seaborn boxplot idiom: patch_artist=True with 4 groups."""
    rng = np.random.default_rng(11)
    targets = [42.0, 51.0, 72.0, 58.0]
    groups = []
    for t in targets:
        g = rng.normal(t, 4.5, 41)
        g = g - (np.median(g) - t)
        groups.append(g)
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    bp = ax.boxplot(
        groups,
        patch_artist=True,
        tick_labels=["Control", "Treat A", "Treat C", "Treat D"],
        medianprops={"color": "#0f172a", "linewidth": 2.0},
    )
    for patch, color in zip(bp["boxes"], ["#94a3b8", "#60a5fa", "#2563eb", "#93c5fd"]):
        patch.set_facecolor(color)
        patch.set_alpha(0.8)
    ax.set_xlabel("Protocol (boxes show IQR)", fontsize=10)
    ax.set_ylabel("Yield (g/L)", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.set_title("Treat C lifts median yield to 72 g/L", fontsize=13, loc="left")
    return fig


def _clean_08_boxplot_classic_lines() -> Figure:
    """Classic Matplotlib line-only boxplot (patch_artist=False) with version token."""
    rng = np.random.default_rng(19)
    targets = [64.0, 70.0, 78.0]
    groups = []
    for t in targets:
        g = rng.normal(t, 3.0, 35)
        g = g - (np.median(g) - t)
        groups.append(g)
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.boxplot(groups, patch_artist=False, tick_labels=["Baseline", "v2.0", "v2.3"])
    ax.set_xlabel("Release", fontsize=10)
    ax.set_ylabel("Score (%)", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.set_title("Model v2.3 beats baseline median by 14 points", fontsize=13, loc="left")
    return fig


def _clean_09_violinplot_medians() -> Figure:
    """Seaborn violinplot idiom with medians and extrema."""
    rng = np.random.default_rng(23)
    targets = [45.0, 65.0, 52.0]
    groups = []
    for t in targets:
        g = rng.normal(t, 5.0, 51)
        g = g - (np.median(g) - t)
        groups.append(g)
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.violinplot(groups, showmedians=True, showextrema=True)
    ax.set_xticks([1, 2, 3], ["Group A", "Group B", "Group C"], fontsize=10)
    ax.set_xlabel("Cohort", fontsize=10)
    ax.set_ylabel("Latency (ms)", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.set_title("Group B median reaches 65 ms across 3 replicates", fontsize=13, loc="left")
    return fig


def _clean_10_grouped_bars_ml_models() -> Figure:
    """Grouped bar chart with exact ML model-name headline from brief."""
    tasks = ["MMLU", "GSM8K", "HumanEval"]
    gpt4 = [80.0, 76.0, 70.0]
    llama = [86.0, 82.0, 76.0]
    x = np.arange(len(tasks))
    w = 0.36
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.bar(x - w / 2, gpt4, width=w, label="GPT-4", color="#94a3b8")
    ax.bar(x + w / 2, llama, width=w, label="Llama-3.1 8B", color="#2563eb")
    ax.set_xticks(x, tasks, fontsize=10)
    ax.set_ylabel("Accuracy (%)", fontsize=10)
    ax.set_ylim(0, 102)
    ax.tick_params(labelsize=10)
    ax.legend(loc="upper right", fontsize=10, frameon=True)
    ax.set_title("Llama-3.1 8B beats GPT-4 by 6 points across 5 seeds", fontsize=12.5, loc="left")
    return fig


def _clean_11_horizontal_bars_precision() -> Figure:
    """Horizontal bar chart with exact ResNet-50 (FP16) headline from brief."""
    models = ["ResNet-50 (FP32)", "ResNet-50 (FP16)", "MobileNet"]
    p95 = [40.0, 30.0, 22.0]  # 40 -> 30 is an exact 25% cut
    fig, ax = _clean_fig(figsize=(7.0, 3.8))
    ax.barh(models, p95, color=["#94a3b8", "#2563eb", "#0d9488"])
    ax.set_xlabel("p95 latency (ms)", fontsize=10)
    ax.set_xlim(0, 46)
    ax.tick_params(labelsize=10)
    ax.set_title("ResNet-50 (FP16) cuts p95 latency 25% in 2026", fontsize=13, loc="left")
    return fig


def _clean_12_stacked_bars_shares() -> Figure:
    """Stacked bar chart where upper bars have non-zero bottom (not truncated)."""
    stages = ["Prefill", "Decode", "Eval"]
    attn = np.array([60.0, 45.0, 30.0])
    mlp = np.array([25.0, 35.0, 40.0])
    comm = np.array([15.0, 20.0, 30.0])
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.bar(stages, attn, label="Attention", color="#2563eb")
    ax.bar(stages, mlp, bottom=attn, label="MLP", color="#60a5fa")
    ax.bar(stages, comm, bottom=attn + mlp, label="Comm", color="#cbd5e1")
    ax.set_ylabel("Step time (ms)", fontsize=10)
    ax.set_ylim(0, 118)
    ax.tick_params(labelsize=10)
    ax.legend(loc="upper right", ncol=3, fontsize=10, frameon=True)
    ax.set_title("Attention accounts for 60% of Prefill step time in 2026", fontsize=12.5, loc="left")
    return fig


def _clean_13_multiline_date_series() -> Figure:
    """Multi-line time series with datetime.date x-axis."""
    days = [dt.date(2026, 3, 1) + dt.timedelta(days=i) for i in range(25)]
    base = np.linspace(50.0, 45.0, 25)
    gpt5 = np.linspace(50.0, 30.0, 25)  # 40% drop
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.plot(days, base, color="#94a3b8", lw=2, label="Baseline")
    ax.plot(days, gpt5, color="#2563eb", lw=2.2, label="GPT-5")
    ax.set_xlabel("Date", fontsize=10)
    ax.set_ylabel("Error rate (%)", fontsize=10)
    ax.tick_params(labelsize=10)
    fig.autofmt_xdate(rotation=20)
    ax.legend(loc="upper right", fontsize=10, frameon=True)
    ax.set_title("GPT-5 error rate fell 40% in 2026", fontsize=13, loc="left")
    return fig


def _clean_14_log_log_scaling() -> Figure:
    """Log-log scaling law curve with 10k steps descriptor."""
    compute = np.array([1e1, 1e2, 1e3, 1e4])
    loss = np.array([4.0, 2.5, 1.6, 1.0])  # 4x drop from 4.0 to 1.0
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.loglog(compute, loss, "o-", color="#2563eb", lw=2.2, markersize=6, label="Chinchilla fit")
    ax.set_xlabel("Compute (FLOPs)", fontsize=10)
    ax.set_ylabel("Cross-entropy loss", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.legend(loc="upper right", fontsize=10, frameon=True)
    ax.set_title("Loss drops 4x as compute scales across 10k steps", fontsize=13, loc="left")
    return fig


def _clean_15_scatter_ols_regplot() -> Figure:
    """Seaborn regplot idiom: scatter + OLS fit + CI band + p < 0.05."""
    rng = np.random.default_rng(101)
    xs = np.linspace(1.0, 10.0, 30)
    noise = rng.normal(0.0, 0.8, 30)
    ys = 2.0 * xs + 5.0 + noise
    slope, intercept = np.polyfit(xs, ys, 1)
    # Adjust ys slightly so fitted slope is exactly 2.0
    ys = ys + (2.0 - slope) * (xs - xs.mean())
    slope, intercept = np.polyfit(xs, ys, 1)
    y_fit = slope * xs + intercept
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.scatter(xs, ys, color="#2563eb", alpha=0.8, s=36, label="Observations")
    ax.plot(xs, y_fit, color="#0f172a", lw=2.0, label="OLS fit")
    ax.fill_between(xs, y_fit - 1.2, y_fit + 1.2, color="#93c5fd", alpha=0.25, label="95% CI")
    ax.set_xlabel("Dose (mg)", fontsize=10)
    ax.set_ylabel("Response (units)", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.legend(loc="upper left", fontsize=10, frameon=True)
    ax.set_title("Response rises 2.0 units per mg (p < 0.05)", fontsize=13, loc="left")
    return fig


def _clean_16_multipanel_2x1() -> Figure:
    """Two-panel comparison (memory + accuracy) with quantization tokens."""
    fig, (ax1, ax2) = _clean_fig(1, 2, figsize=(7.0, 3.8))
    labels = ["FP16", "INT4"]
    ax1.bar(labels, [16.0, 4.0], color=["#94a3b8", "#2563eb"])
    ax1.set_ylabel("Memory (GB)", fontsize=10)
    ax1.set_ylim(0, 19)
    ax1.tick_params(labelsize=10)
    ax1.set_title("Footprint", fontsize=11)

    ax2.bar(labels, [84.0, 82.0], color=["#94a3b8", "#0d9488"])
    ax2.set_ylabel("Accuracy (%)", fontsize=10)
    ax2.set_ylim(0, 100)
    ax2.tick_params(labelsize=10)
    ax2.set_title("Quality", fontsize=11)

    fig.suptitle("INT4 (Q4_K_M) cuts memory 4x while keeping 82% accuracy", fontsize=12.5)
    return fig


def _clean_17_multipanel_2x2_grid() -> Figure:
    """2x2 subplot grid with version & top-5 tokens."""
    x = np.arange(0, 5)
    fig, axes = _clean_fig(2, 2, figsize=(7.0, 5.2), sharex=True)
    series = [
        ("Split A", [60, 65, 70, 74, 75], [60, 68, 76, 84, 90]),
        ("Split B", [55, 60, 64, 68, 70], [55, 64, 72, 80, 85]),
        ("Split C", [50, 54, 58, 62, 65], [50, 58, 66, 74, 80]),
        ("Split D", [58, 61, 65, 69, 72], [58, 66, 73, 81, 87]),
    ]
    for idx, (ax, (title, base, new)) in enumerate(zip(axes.flat, series)):
        ax.plot(x, base, color="#94a3b8", lw=1.8, label="Baseline")
        ax.plot(x, new, color="#2563eb", lw=2.0, label="v2.3")
        ax.set_title(title, fontsize=10.5)
        ax.tick_params(labelsize=9.5)
        ax.set_ylabel("Recall (%)", fontsize=9.5)
        if idx in (2, 3):
            ax.set_xlabel("Stage", fontsize=9.5)
    axes[0, 0].legend(loc="lower right", fontsize=9, frameon=True)
    fig.suptitle("v2.3 beats baseline by 15 points on top-5 recall", fontsize=13)
    return fig


def _clean_18_dark_theme_framed_legend() -> Figure:
    """Dark theme plot with opaque framed legend over data curves."""
    epochs = np.arange(0, 21, 2)
    train = np.linspace(2.0, 1.0, len(epochs))  # 50% fall
    val = np.linspace(2.2, 1.2, len(epochs))
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    fig.patch.set_facecolor("#0f172a")
    ax.set_facecolor("#1e293b")
    ax.plot(epochs, train, color="#38bdf8", lw=2.2, label="Train loss")
    ax.plot(epochs, val, color="#f472b6", lw=2.2, label="Val loss")
    ax.set_xlabel("Epoch", fontsize=10, color="#e2e8f0")
    ax.set_ylabel("Loss", fontsize=10, color="#e2e8f0")
    ax.tick_params(colors="#cbd5e1", labelsize=10)
    for sp in ax.spines.values():
        sp.set_color("#475569")
    leg = ax.legend(loc="center", fontsize=10, frameon=True, facecolor="#0f172a", framealpha=0.95)
    for txt in leg.get_texts():
        txt.set_color("#f8fafc")
    ax.set_title("Train loss falls 50% by epoch 20", fontsize=13, loc="left", color="#f8fafc")
    return fig


def _clean_19_framed_legend_over_lines() -> Figure:
    """Light theme 4-series plot with framed legend centered over lines."""
    epochs = np.arange(0, 51, 5)
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.plot(epochs, np.linspace(40, 82, len(epochs)), lw=2.0, label="Model A")
    ax.plot(epochs, np.linspace(38, 70, len(epochs)), lw=2.0, label="Model B")
    ax.plot(epochs, np.linspace(35, 62, len(epochs)), lw=1.8, label="Model C")
    ax.plot(epochs, np.linspace(30, 54, len(epochs)), lw=1.8, label="Model D")
    ax.set_xlabel("Epoch", fontsize=10)
    ax.set_ylabel("Accuracy (%)", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.legend(loc="center", frameon=True, framealpha=0.95, fontsize=10)
    ax.set_title("Model A leads Model B by 12 points at epoch 50", fontsize=13, loc="left")
    return fig


def _clean_20_unit_scale_seconds_to_ms() -> Figure:
    """Bar chart in seconds where headline states milliseconds (0.08 s -> 80 ms)."""
    models = ["Baseline", "Pruned", "Llama-3.1 70B"]
    lat_s = [0.20, 0.12, 0.08]
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.bar(models, lat_s, color=["#94a3b8", "#60a5fa", "#2563eb"])
    ax.set_ylabel("Latency (s)", fontsize=10)
    ax.set_ylim(0, 0.24)
    ax.tick_params(labelsize=10)
    ax.set_title("Llama-3.1 70B cuts latency to 80 ms (p = 0.01)", fontsize=13, loc="left")
    return fig


def _clean_21_unit_scale_thousands_k() -> Figure:
    """Bar chart in raw counts where headline uses k-suffix (4500 -> 4.5k)."""
    configs = ["B1", "B4", "B16"]
    tps = [1500.0, 3000.0, 4500.0]
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.bar(configs, tps, color=["#94a3b8", "#60a5fa", "#2563eb"])
    ax.set_ylabel("Throughput (tokens/s)", fontsize=10)
    ax.set_ylim(0, 5200)
    ax.tick_params(labelsize=10)
    ax.set_title("Batching lifts peak throughput to 4.5k tokens/s", fontsize=13, loc="left")
    return fig


def _clean_22_unit_scale_fraction_to_pct() -> Figure:
    """Fractional accuracy bars where headline states % gain and level."""
    variants = ["Baseline", "Full"]
    acc = [0.74, 0.82]
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.bar(variants, acc, color=["#94a3b8", "#2563eb"])
    ax.set_ylabel("Accuracy", fontsize=10)
    ax.set_ylim(0, 0.95)
    ax.tick_params(labelsize=10)
    ax.set_title("Retrieval raises accuracy 8% to 82% across 3 replicates", fontsize=12.5, loc="left")
    return fig


def _clean_23_errorbar_categorical() -> Figure:
    """Categorical errorbar point plot without bars + 95% CI + p < 0.05."""
    x = np.arange(3)
    means = [62.0, 70.0, 77.0]
    errs = [2.0, 2.5, 2.0]
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.errorbar(x, means, yerr=errs, fmt="o", markersize=7, capsize=4, lw=2, color="#2563eb")
    ax.set_xticks(x, ["Baseline", "Variant B", "Variant A"], fontsize=10)
    ax.set_xlabel("Method", fontsize=10)
    ax.set_ylabel("Score (95% CI, n = 10)", fontsize=10)
    ax.set_ylim(55, 84)
    ax.tick_params(labelsize=10)
    ax.set_title("Variant A leads baseline by 15 points (95% CI, p < 0.05)", fontsize=12, loc="left")
    return fig


def _clean_24_imshow_cividis_colorbar() -> Figure:
    """AxesImage with cividis colormap and colorbar."""
    arr = np.array(
        [
            [32.0, 48.0, 64.0],
            [40.0, 72.0, 88.0],
            [56.0, 80.0, 96.0],
        ]
    )
    fig, ax = _clean_fig(figsize=(6.8, 4.2))
    im = ax.imshow(arr, cmap="cividis", vmin=30, vmax=100)
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Intensity (a.u.)", fontsize=10)
    cbar.ax.tick_params(labelsize=10)
    ax.set_xticks([0, 1, 2], ["C1", "C2", "C3"], fontsize=10)
    ax.set_yticks([0, 1, 2], ["R1", "R2", "R3"], fontsize=10)
    ax.set_xlabel("Column", fontsize=10)
    ax.set_ylabel("Row", fontsize=10)
    ax.set_title("Peak intensity reaches 96, 3x the minimum cell", fontsize=13, loc="left")
    return fig


def _clean_25_negative_values_unicode_minus() -> Figure:
    """Horizontal diverging bars with zero included and proper Unicode minus."""
    names = ["No cache", "Quant", "Prune", "FlashAttn"]
    deltas = [-12.0, -5.0, 4.0, 18.0]
    colors = ["#dc2626" if v < 0 else "#2563eb" for v in deltas]
    fig, ax = _clean_fig(figsize=(7.0, 3.8))
    ax.barh(names, deltas, color=colors)
    ax.axvline(0.0, color="#0f172a", lw=1.0)
    ax.set_xlabel("Throughput change (%)", fontsize=10)
    ax.set_xlim(-18, 24)
    ax.tick_params(labelsize=10)
    ax.text(-13.0, 0, "\N{MINUS SIGN}12%", va="center", ha="right", fontsize=10)
    ax.text(19.0, 3, "+18%", va="center", ha="left", fontsize=10)
    ax.set_title("FlashAttn improves throughput by 18%", fontsize=13, loc="left")
    return fig


# ---------------------------------------------------------------------------
# 25 DEFECTIVE FIGURES WITH LABELED GROUND-TRUTH INJECTED BUGS (ship=False)
# ---------------------------------------------------------------------------


def _defect_01_claim_mismatch_bars() -> Figure:
    """Hallucinated claim on bar chart: data gap is 8 pts, claim says 15 pts."""
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.bar(["Full", "No retrieval", "No FT"], [0.82, 0.74, 0.69], color="#2563eb")
    ax.set_ylabel("Accuracy", fontsize=10)
    ax.set_ylim(0, 0.95)
    ax.tick_params(labelsize=10)
    ax.set_title("Removing retrieval costs 15 points of accuracy", fontsize=13, loc="left")
    return fig


def _defect_02_claim_mismatch_lines() -> Figure:
    """Hallucinated claim on line chart: actual drop is 25%, claim says 60%."""
    days = np.arange(0, 20)
    load = np.linspace(120.0, 90.0, 20)
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.plot(days, load, color="#2563eb", lw=2.2, label="Load")
    ax.set_xlabel("Day", fontsize=10)
    ax.set_ylabel("Energy (kWh)", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.set_title("Daily energy load fell 60% after retrofit", fontsize=13, loc="left")
    return fig


def _defect_03_claim_mismatch_quadmesh() -> Figure:
    """Hallucinated claim on QuadMesh heatmap: max is 0.85, claim says 0.99."""
    mat = np.array(
        [
            [0.10, 0.30, 0.45],
            [0.30, 0.60, 0.72],
            [0.45, 0.72, 0.85],
        ]
    )
    fig, ax = _clean_fig(figsize=(6.8, 4.2))
    mesh = ax.pcolormesh(mat, cmap="viridis", vmin=0.0, vmax=1.0)
    cbar = fig.colorbar(mesh, ax=ax)
    cbar.set_label("Correlation", fontsize=10)
    cbar.ax.tick_params(labelsize=10)
    ax.set_xticks([0.5, 1.5, 2.5], ["A", "B", "C"], fontsize=10)
    ax.set_yticks([0.5, 1.5, 2.5], ["A", "B", "C"], fontsize=10)
    ax.set_title("Peak cell correlation reaches 0.99", fontsize=13, loc="left")
    return fig


def _defect_04_claim_mismatch_boxplot() -> Figure:
    """Hallucinated claim on boxplot: medians are 40/52/60, claim says 95 ms."""
    rng = np.random.default_rng(31)
    groups = []
    for t in (40.0, 52.0, 60.0):
        g = rng.normal(t, 3.0, 35)
        g = g - (np.median(g) - t)
        groups.append(g)
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.boxplot(groups, patch_artist=True, tick_labels=["Group A", "Group B", "Group C"])
    ax.set_xlabel("Group", fontsize=10)
    ax.set_ylabel("Latency (ms)", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.set_title("Group C median reaches 95 ms", fontsize=13, loc="left")
    return fig


def _defect_05_claim_mismatch_hist() -> Figure:
    """Hallucinated claim on histogram: data in [20, 80], claim says peak 180 ms."""
    rng = np.random.default_rng(43)
    samples = rng.normal(50.0, 8.0, 200)
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.hist(samples, bins=12, color="#2563eb", edgecolor="white")
    ax.set_xlabel("Latency (ms)", fontsize=10)
    ax.set_ylabel("Count", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.set_title("Latency peaks at 180 ms", fontsize=13, loc="left")
    return fig


def _defect_06_truncated_vbar() -> Figure:
    """Truncated vertical bar baseline: bars from 0, y-axis starts at 0.70."""
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.bar(["Model A", "Model B", "Model C"], [0.82, 0.78, 0.75], color="#2563eb")
    ax.set_ylim(0.70, 0.85)
    ax.set_ylabel("Accuracy", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.set_title("Model A leads Model B by 4 points", fontsize=13, loc="left")
    return fig


def _defect_07_truncated_hbar() -> Figure:
    """Truncated horizontal bar baseline: x-axis starts at 80."""
    fig, ax = _clean_fig(figsize=(7.0, 3.8))
    ax.barh(["Old", "Mid", "New"], [86.0, 88.0, 91.0], color="#0d9488")
    ax.set_xlim(80.0, 95.0)
    ax.set_xlabel("Pass rate (%)", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.set_title("New system reaches 91%", fontsize=13, loc="left")
    return fig


def _defect_08_truncated_grouped_bars() -> Figure:
    """Truncated grouped bar baseline: y-axis starts at 65."""
    x = np.arange(2)
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.bar(x - 0.18, [72.0, 76.0], width=0.35, label="v1", color="#94a3b8")
    ax.bar(x + 0.18, [74.0, 79.0], width=0.35, label="v2", color="#2563eb")
    ax.set_xticks(x, ["Task 1", "Task 2"], fontsize=10)
    ax.set_ylim(65.0, 82.0)
    ax.set_ylabel("Score (%)", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.legend(loc="upper left", fontsize=10, frameon=True)
    ax.set_title("v2 leads Task 2 by 3 points", fontsize=13, loc="left")
    return fig


def _defect_09_tiny_text_wide_chat() -> Figure:
    """Oversized 14 in figure shrunk to 700 px chat width -> text < 6 px."""
    fig, ax = plt.subplots(figsize=(14.0, 6.0), layout="constrained")
    ax.bar(["A", "B", "C"], [10.0, 20.0, 30.0], color="#2563eb")
    ax.set_ylabel("Throughput (req/s)", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.set_title("C reaches 30 req/s", fontsize=12, loc="left")
    return fig


def _defect_10_tiny_text_explicit_small_font() -> Figure:
    """Normal figure width but tiny 6 pt labels."""
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.plot([0, 1, 2, 3], [10, 15, 22, 30], color="#2563eb", lw=2)
    ax.set_xlabel("Step", fontsize=6)
    ax.set_ylabel("Score (%)", fontsize=6)
    ax.tick_params(labelsize=6)
    ax.set_title("Score rises to 30%", fontsize=13, loc="left")
    return fig


def _defect_11_tiny_text_narrow_450() -> Figure:
    """7.5 in figure with 10 pt labels read at 450 px narrow width -> ~8.3 px."""
    fig, ax = _clean_fig(figsize=(7.5, 4.0))
    ax.plot([0, 1, 2, 3], [4, 7, 11, 16], color="#2563eb", lw=2)
    ax.set_xlabel("Day", fontsize=10)
    ax.set_ylabel("Active users", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.set_title("Active users reach 16", fontsize=12, loc="left")
    return fig


def _defect_12_tiny_text_multipanel_chat() -> Figure:
    """Wide 1x3 subplot grid (13 in) read at 700 px chat width -> tiny text."""
    fig, axes = plt.subplots(1, 3, figsize=(13.0, 4.0), layout="constrained")
    for idx, ax in enumerate(axes):
        ax.plot([0, 1, 2], [1, 2 + idx, 4 + idx], color="#2563eb", lw=2)
        ax.set_xlabel("Step", fontsize=9)
        ax.set_ylabel("Value", fontsize=9)
        ax.tick_params(labelsize=9)
        ax.set_title(f"Panel {idx + 1}", fontsize=10)
    fig.suptitle("Panel 3 reaches 6", fontsize=12)
    return fig


def _defect_13_overlapping_annotations() -> Figure:
    """Two scatter annotations placed on top of each other."""
    xs = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    ys = np.array([10.0, 18.0, 20.0, 35.0, 40.0])
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.scatter(xs, ys, color="#2563eb", s=40)
    ax.text(3.0, 20.5, "Model Alpha (20)", fontsize=11)
    ax.text(3.05, 20.2, "Model Beta (21)", fontsize=11)
    ax.set_xlabel("Cost ($)", fontsize=10)
    ax.set_ylabel("Score (%)", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.set_title("Top score reaches 40%", fontsize=13, loc="left")
    return fig


def _defect_14_overlapping_xticks() -> Figure:
    """Ten long horizontal x-tick labels that collide."""
    cats = [f"Configuration_{i:02d}" for i in range(10)]
    vals = [12, 15, 18, 22, 25, 29, 31, 35, 38, 42]
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.bar(cats, vals, color="#2563eb")
    ax.set_ylabel("Score (%)", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.set_title("Top configuration reaches 42%", fontsize=13, loc="left")
    return fig


def _defect_15_overlapping_line_end_labels() -> Figure:
    """Two lines ending close together with colliding direct end labels."""
    x = np.arange(0, 6)
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.plot(x, [50, 56, 63, 70, 76, 80], color="#2563eb", lw=2)
    ax.plot(x, [45, 53, 61, 69, 75, 81], color="#dc2626", lw=2)
    ax.text(5.1, 80.0, "Baseline model", fontsize=11, va="center")
    ax.text(5.1, 80.5, "Candidate model", fontsize=11, va="center")
    ax.set_xlim(0, 6.8)
    ax.set_xlabel("Epoch", fontsize=10)
    ax.set_ylabel("Accuracy (%)", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.set_title("Candidate model reaches 81%", fontsize=13, loc="left")
    return fig


def _defect_16_struck_by_data_line() -> Figure:
    """Unboxed text label placed directly across the data line."""
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.plot([0, 1, 2, 3, 4], [0, 10, 20, 30, 40], color="#2563eb", lw=2.2)
    ax.text(2.0, 20.0, "Linear growth", ha="center", va="center", fontsize=12)
    ax.set_xlabel("Hour", fontsize=10)
    ax.set_ylabel("Output (kW)", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.set_title("Output reaches 40 kW", fontsize=13, loc="left")
    return fig


def _defect_17_struck_by_reference_line() -> Figure:
    """Unboxed label crossed by a dashed horizontal reference line."""
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.plot([0, 1, 2, 3, 4], [20, 35, 50, 65, 80], color="#2563eb", lw=2.2)
    ax.axhline(50.0, ls="--", color="#64748b", lw=1.6)
    ax.text(0.8, 50.0, "Target threshold", ha="left", va="center", fontsize=11)
    ax.set_xlabel("Week", fontsize=10)
    ax.set_ylabel("Coverage (%)", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.set_title("Coverage reaches 80%", fontsize=13, loc="left")
    return fig


def _defect_18_struck_frameless_legend() -> Figure:
    """Frameless legend placed directly over plotted data lines."""
    x = np.linspace(0, 10, 20)
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.plot(x, 20 + 6 * x, color="#2563eb", lw=2.2, label="Series Alpha")
    ax.plot(x, 80 - 6 * x, color="#dc2626", lw=2.2, label="Series Beta")
    ax.set_xlabel("Time (s)", fontsize=10)
    ax.set_ylabel("Signal (mV)", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.legend(loc="center", frameon=False, fontsize=11)
    ax.set_title("Series Alpha reaches 80 mV", fontsize=13, loc="left")
    return fig


def _defect_19_rainbow_imshow_jet() -> Figure:
    """AxesImage using banned jet rainbow colormap."""
    arr = np.arange(16.0).reshape(4, 4) * 5.0
    fig, ax = _clean_fig(figsize=(6.8, 4.2))
    im = ax.imshow(arr, cmap="jet")
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Power (W)", fontsize=10)
    cbar.ax.tick_params(labelsize=10)
    ax.set_xticks([0, 1, 2, 3], ["A", "B", "C", "D"], fontsize=10)
    ax.set_yticks([0, 1, 2, 3], ["1", "2", "3", "4"], fontsize=10)
    ax.set_title("Peak cell reaches 75 W", fontsize=13, loc="left")
    return fig


def _defect_20_rainbow_quadmesh_hsv() -> Figure:
    """QuadMesh heatmap using banned hsv rainbow colormap."""
    mat = np.linspace(10.0, 90.0, 9).reshape(3, 3)
    fig, ax = _clean_fig(figsize=(6.8, 4.2))
    mesh = ax.pcolormesh(mat, cmap="hsv")
    cbar = fig.colorbar(mesh, ax=ax)
    cbar.set_label("Phase (deg)", fontsize=10)
    cbar.ax.tick_params(labelsize=10)
    ax.set_xticks([0.5, 1.5, 2.5], ["X", "Y", "Z"], fontsize=10)
    ax.set_yticks([0.5, 1.5, 2.5], ["I", "II", "III"], fontsize=10)
    ax.set_title("Peak cell reaches 90 deg", fontsize=13, loc="left")
    return fig


def _defect_21_rainbow_scatter_rainbow() -> Figure:
    """Color-mapped scatter plot using banned rainbow colormap."""
    rng = np.random.default_rng(55)
    xs = np.linspace(1.0, 10.0, 25)
    ys = 3.0 * xs + rng.normal(0.0, 1.0, 25)
    ys[-1] = 30.0
    fig, ax = _clean_fig(figsize=(6.8, 4.2))
    sc = ax.scatter(xs, ys, c=ys, cmap="rainbow", s=45)
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label("Energy (J)", fontsize=10)
    cbar.ax.tick_params(labelsize=10)
    ax.set_xlabel("Input", fontsize=10)
    ax.set_ylabel("Energy (J)", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.set_title("Energy reaches 30 J", fontsize=13, loc="left")
    return fig


def _defect_22_malformed_doubled_pct() -> Figure:
    """Malformed annotation with doubled percent sign (%%)."""
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.bar(["Before", "After"], [50.0, 62.0], color=["#94a3b8", "#2563eb"])
    ax.text(1, 64.0, "+12%%", ha="center", va="bottom", fontsize=11)
    ax.set_ylabel("Pass rate (%)", fontsize=10)
    ax.set_ylim(0, 76)
    ax.tick_params(labelsize=10)
    ax.set_title("Pass rate rises 12 points", fontsize=13, loc="left")
    return fig


def _defect_23_malformed_nan_junk() -> Figure:
    """Malformed text displaying raw 'nan' value."""
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.plot([0, 1, 2, 3], [10.0, 20.0, 30.0, 40.0], color="#2563eb", lw=2)
    ax.text(0.3, 35.0, "Mean: nan ms", fontsize=11)
    ax.set_xlabel("Step", fontsize=10)
    ax.set_ylabel("Latency (ms)", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.set_title("Latency reaches 40 ms", fontsize=13, loc="left")
    return fig


def _defect_24_malformed_ascii_minus() -> Figure:
    """Malformed negative annotation using ASCII hyphen instead of U+2212."""
    fig, ax = _clean_fig(figsize=(7.0, 4.0))
    ax.bar(["Control", "Drop"], [20.0, 12.0], color=["#94a3b8", "#dc2626"])
    ax.text(1, 13.5, "Delta: -8 pts", ha="center", va="bottom", fontsize=11)
    ax.set_ylabel("Score (%)", fontsize=10)
    ax.set_ylim(0, 26)
    ax.tick_params(labelsize=10)
    ax.set_title("Score falls 8 points", fontsize=13, loc="left")
    return fig


def _defect_25_clipped_right_edge() -> Figure:
    """Text running past the right canvas edge (saved without bbox tight)."""
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    ax.plot([0, 1, 2, 3], [10.0, 18.0, 26.0, 35.0], color="#2563eb", lw=2)
    ax.set_xlabel("Quarter", fontsize=10)
    ax.set_ylabel("Revenue ($M)", fontsize=10)
    ax.tick_params(labelsize=10)
    ax.set_title("Revenue reaches 35", fontsize=13, loc="left")
    fig.text(0.93, 0.5, "Projected trajectory 2026", fontsize=13, va="center")
    return fig


# ---------------------------------------------------------------------------
# CORPUS REGISTRY (25 clean + 25 defective = 50 cases)
# ---------------------------------------------------------------------------

WILD_50: tuple[WildCase, ...] = (
    # ---- 25 clean ----
    WildCase(
        case_id="clean_01_quadmesh_heatmap_colorbar",
        split="clean",
        artist_category="quadmesh",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="Seaborn-style QuadMesh heatmap + colorbar + viridis + year token 2026",
        builder=_clean_01_quadmesh_heatmap_colorbar,
    ),
    WildCase(
        case_id="clean_02_quadmesh_diverging_ratio",
        split="clean",
        artist_category="quadmesh",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="QuadMesh RdBu_r latency heatmap + colorbar with max/min 4x ratio claim",
        builder=_clean_02_quadmesh_diverging_ratio,
    ),
    WildCase(
        case_id="clean_03_ci_band_fill_between",
        split="clean",
        artist_category="ci_band",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="Seaborn lineplot + fill_between 95% CI with Llama-3.1 8B & 5 seeds tokens",
        builder=_clean_03_ci_band_fill_between,
    ),
    WildCase(
        case_id="clean_04_ci_band_upper_bound",
        split="clean",
        artist_category="ci_band",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="Dual fill_between uncertainty bands citing upper 1 s.d. envelope peak (94%)",
        builder=_clean_04_ci_band_upper_bound,
    ),
    WildCase(
        case_id="clean_05_hist_counts",
        split="clean",
        artist_category="histogram",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="Count histogram (contiguous BarContainer) citing peak bin center & sample count",
        builder=_clean_05_hist_counts,
    ),
    WildCase(
        case_id="clean_06_hist_density",
        split="clean",
        artist_category="histogram",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="Density histogram + median line with ResNet-50 (FP16) headline",
        builder=_clean_06_hist_density,
    ),
    WildCase(
        case_id="clean_07_boxplot_patch_artist",
        split="clean",
        artist_category="boxplot",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="Seaborn-style patch_artist boxplot citing highest group median",
        builder=_clean_07_boxplot_patch_artist,
    ),
    WildCase(
        case_id="clean_08_boxplot_classic_lines",
        split="clean",
        artist_category="boxplot",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="Classic line-only boxplot with v2.3 token citing 14-point median lead",
        builder=_clean_08_boxplot_classic_lines,
    ),
    WildCase(
        case_id="clean_09_violinplot_medians",
        split="clean",
        artist_category="violinplot",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="Violinplot with medians citing 65 ms across 3 replicates",
        builder=_clean_09_violinplot_medians,
    ),
    WildCase(
        case_id="clean_10_grouped_bars_ml_models",
        split="clean",
        artist_category="bars_grouped",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="Grouped bars: 'Llama-3.1 8B beats GPT-4 by 6 points across 5 seeds'",
        builder=_clean_10_grouped_bars_ml_models,
    ),
    WildCase(
        case_id="clean_11_horizontal_bars_precision",
        split="clean",
        artist_category="bars_horizontal",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="Horizontal bars: 'ResNet-50 (FP16) cuts p95 latency 25% in 2026'",
        builder=_clean_11_horizontal_bars_precision,
    ),
    WildCase(
        case_id="clean_12_stacked_bars_shares",
        split="clean",
        artist_category="bars_stacked",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="Stacked bars with non-zero upper bottoms citing 60% share in 2026",
        builder=_clean_12_stacked_bars_shares,
    ),
    WildCase(
        case_id="clean_13_multiline_date_series",
        split="clean",
        artist_category="lines_dates",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="Multi-line datetime.date series with GPT-5 token & 40% drop",
        builder=_clean_13_multiline_date_series,
    ),
    WildCase(
        case_id="clean_14_log_log_scaling",
        split="clean",
        artist_category="log_log",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="Log-log scaling curve with 10k steps descriptor and 4x drop",
        builder=_clean_14_log_log_scaling,
    ),
    WildCase(
        case_id="clean_15_scatter_ols_regplot",
        split="clean",
        artist_category="scatter_ols",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="Seaborn regplot (scatter + OLS + CI band) with slope 2.0 and p < 0.05",
        builder=_clean_15_scatter_ols_regplot,
    ),
    WildCase(
        case_id="clean_16_multipanel_2x1",
        split="clean",
        artist_category="multi_panel",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="1x2 multi-panel subplot with INT4 (Q4_K_M) tokens, 4x & 82% claims",
        builder=_clean_16_multipanel_2x1,
    ),
    WildCase(
        case_id="clean_17_multipanel_2x2_grid",
        split="clean",
        artist_category="multi_panel",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="2x2 subplot grid with v2.3 and top-5 tokens & 15-point gain",
        builder=_clean_17_multipanel_2x2_grid,
    ),
    WildCase(
        case_id="clean_18_dark_theme_framed_legend",
        split="clean",
        artist_category="dark_theme",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="Dark theme multi-line plot with opaque framed legend over data lines",
        builder=_clean_18_dark_theme_framed_legend,
    ),
    WildCase(
        case_id="clean_19_framed_legend_over_lines",
        split="clean",
        artist_category="framed_legend",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="4-line plot with opaque framed legend centered over curves",
        builder=_clean_19_framed_legend_over_lines,
    ),
    WildCase(
        case_id="clean_20_unit_scale_seconds_to_ms",
        split="clean",
        artist_category="headline_tokens",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="Unit scale conversion (0.08 s -> 80 ms) with Llama-3.1 70B & p = 0.01",
        builder=_clean_20_unit_scale_seconds_to_ms,
    ),
    WildCase(
        case_id="clean_21_unit_scale_thousands_k",
        split="clean",
        artist_category="headline_tokens",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="Unit scale conversion (4500 -> 4.5k) on throughput bar chart",
        builder=_clean_21_unit_scale_thousands_k,
    ),
    WildCase(
        case_id="clean_22_unit_scale_fraction_to_pct",
        split="clean",
        artist_category="headline_tokens",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="Fraction-to-percent conversion (0.08 -> 8%, 0.82 -> 82%) + 3 replicates",
        builder=_clean_22_unit_scale_fraction_to_pct,
    ),
    WildCase(
        case_id="clean_23_errorbar_categorical",
        split="clean",
        artist_category="errorbar",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="Categorical errorbar point plot with 95% CI, n = 10, and p < 0.05",
        builder=_clean_23_errorbar_categorical,
    ),
    WildCase(
        case_id="clean_24_imshow_cividis_colorbar",
        split="clean",
        artist_category="image_imshow",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="AxesImage with cividis colormap + colorbar citing max & 3x ratio",
        builder=_clean_24_imshow_cividis_colorbar,
    ),
    WildCase(
        case_id="clean_25_negative_values_unicode_minus",
        split="clean",
        artist_category="bars_horizontal",
        defect_category=None,
        expected_ship=True,
        expected_rules=(),
        description="Diverging horizontal bars with zero baseline and Unicode minus sign",
        builder=_clean_25_negative_values_unicode_minus,
    ),
    # ---- 25 defective ----
    WildCase(
        case_id="defect_01_claim_mismatch_bars",
        split="defective",
        artist_category="bars_grouped",
        defect_category="claim_number_mismatch",
        expected_ship=False,
        expected_rules=("claim_number_mismatch",),
        description="Hallucinated bar gap (claims 15 points, actual gap is 8 points)",
        builder=_defect_01_claim_mismatch_bars,
    ),
    WildCase(
        case_id="defect_02_claim_mismatch_lines",
        split="defective",
        artist_category="lines_dates",
        defect_category="claim_number_mismatch",
        expected_ship=False,
        expected_rules=("claim_number_mismatch",),
        description="Hallucinated line drop (claims 60% fall, actual fall is 25%)",
        builder=_defect_02_claim_mismatch_lines,
    ),
    WildCase(
        case_id="defect_03_claim_mismatch_quadmesh",
        split="defective",
        artist_category="quadmesh",
        defect_category="claim_number_mismatch",
        expected_ship=False,
        expected_rules=("claim_number_mismatch",),
        description="Hallucinated QuadMesh peak (claims 0.99, actual max cell is 0.85)",
        builder=_defect_03_claim_mismatch_quadmesh,
    ),
    WildCase(
        case_id="defect_04_claim_mismatch_boxplot",
        split="defective",
        artist_category="boxplot",
        defect_category="claim_number_mismatch",
        expected_ship=False,
        expected_rules=("claim_number_mismatch",),
        description="Hallucinated boxplot median (claims 95 ms, actual max median is 60 ms)",
        builder=_defect_04_claim_mismatch_boxplot,
    ),
    WildCase(
        case_id="defect_05_claim_mismatch_hist",
        split="defective",
        artist_category="histogram",
        defect_category="claim_number_mismatch",
        expected_ship=False,
        expected_rules=("claim_number_mismatch",),
        description="Hallucinated histogram peak (claims 180 ms, data centered at 50 ms)",
        builder=_defect_05_claim_mismatch_hist,
    ),
    WildCase(
        case_id="defect_06_truncated_vbar",
        split="defective",
        artist_category="bars_grouped",
        defect_category="bar_baseline_nonzero",
        expected_ship=False,
        expected_rules=("bar_baseline_nonzero",),
        description="Truncated vertical bar y-axis starting at 0.70",
        builder=_defect_06_truncated_vbar,
    ),
    WildCase(
        case_id="defect_07_truncated_hbar",
        split="defective",
        artist_category="bars_horizontal",
        defect_category="bar_baseline_nonzero",
        expected_ship=False,
        expected_rules=("bar_baseline_nonzero",),
        description="Truncated horizontal bar x-axis starting at 80",
        builder=_defect_07_truncated_hbar,
    ),
    WildCase(
        case_id="defect_08_truncated_grouped_bars",
        split="defective",
        artist_category="bars_grouped",
        defect_category="bar_baseline_nonzero",
        expected_ship=False,
        expected_rules=("bar_baseline_nonzero",),
        description="Truncated grouped bar y-axis starting at 65",
        builder=_defect_08_truncated_grouped_bars,
    ),
    WildCase(
        case_id="defect_09_tiny_text_wide_chat",
        split="defective",
        artist_category="bars_grouped",
        defect_category="text_too_small",
        expected_ship=False,
        expected_rules=("text_too_small",),
        description="14 in wide figure shrunk to 700 px chat column -> text < 6 px",
        builder=_defect_09_tiny_text_wide_chat,
        width="chat",
        dpi=150.0,
    ),
    WildCase(
        case_id="defect_10_tiny_text_explicit_small_font",
        split="defective",
        artist_category="lines_dates",
        defect_category="text_too_small",
        expected_ship=False,
        expected_rules=("text_too_small",),
        description="Explicit 6 pt axis & tick labels at 700 px chat width",
        builder=_defect_10_tiny_text_explicit_small_font,
        width="chat",
        dpi=100.0,
    ),
    WildCase(
        case_id="defect_11_tiny_text_narrow_450",
        split="defective",
        artist_category="lines_dates",
        defect_category="text_too_small",
        expected_ship=False,
        expected_rules=("text_too_small",),
        description="7.5 in figure with 10 pt labels read at 450 px narrow width",
        builder=_defect_11_tiny_text_narrow_450,
        width="narrow",
        dpi=100.0,
    ),
    WildCase(
        case_id="defect_12_tiny_text_multipanel_chat",
        split="defective",
        artist_category="multi_panel",
        defect_category="text_too_small",
        expected_ship=False,
        expected_rules=("text_too_small",),
        description="1x3 13 in wide multi-panel figure shrunk to 700 px chat width",
        builder=_defect_12_tiny_text_multipanel_chat,
        width="chat",
        dpi=120.0,
    ),
    WildCase(
        case_id="defect_13_overlapping_annotations",
        split="defective",
        artist_category="scatter_ols",
        defect_category="text_overlaps",
        expected_ship=False,
        expected_rules=("text_overlaps",),
        description="Colliding direct text annotations on scatter plot",
        builder=_defect_13_overlapping_annotations,
    ),
    WildCase(
        case_id="defect_14_overlapping_xticks",
        split="defective",
        artist_category="bars_grouped",
        defect_category="text_overlaps",
        expected_ship=False,
        expected_rules=("text_overlaps",),
        description="Ten colliding unrotated horizontal x-tick labels",
        builder=_defect_14_overlapping_xticks,
    ),
    WildCase(
        case_id="defect_15_overlapping_line_end_labels",
        split="defective",
        artist_category="lines_dates",
        defect_category="text_overlaps",
        expected_ship=False,
        expected_rules=("text_overlaps",),
        description="Colliding line-end direct labels at y=80 vs y=80.5",
        builder=_defect_15_overlapping_line_end_labels,
    ),
    WildCase(
        case_id="defect_16_struck_by_data_line",
        split="defective",
        artist_category="lines_dates",
        defect_category="text_struck_by_line",
        expected_ship=False,
        expected_rules=("text_struck_by_line",),
        description="Unboxed annotation placed directly on top of a data line",
        builder=_defect_16_struck_by_data_line,
    ),
    WildCase(
        case_id="defect_17_struck_by_reference_line",
        split="defective",
        artist_category="lines_dates",
        defect_category="text_struck_by_line",
        expected_ship=False,
        expected_rules=("text_struck_by_line",),
        description="Unboxed annotation crossed by a dashed reference line",
        builder=_defect_17_struck_by_reference_line,
    ),
    WildCase(
        case_id="defect_18_struck_frameless_legend",
        split="defective",
        artist_category="framed_legend",
        defect_category="text_struck_by_line",
        expected_ship=False,
        expected_rules=("text_struck_by_line",),
        description="Frameless legend placed directly over intersecting data lines",
        builder=_defect_18_struck_frameless_legend,
    ),
    WildCase(
        case_id="defect_19_rainbow_imshow_jet",
        split="defective",
        artist_category="image_imshow",
        defect_category="rainbow_colormap",
        expected_ship=False,
        expected_rules=("rainbow_colormap",),
        description="AxesImage rendered with banned 'jet' rainbow colormap",
        builder=_defect_19_rainbow_imshow_jet,
    ),
    WildCase(
        case_id="defect_20_rainbow_quadmesh_hsv",
        split="defective",
        artist_category="quadmesh",
        defect_category="rainbow_colormap",
        expected_ship=False,
        expected_rules=("rainbow_colormap",),
        description="QuadMesh heatmap rendered with banned 'hsv' colormap",
        builder=_defect_20_rainbow_quadmesh_hsv,
    ),
    WildCase(
        case_id="defect_21_rainbow_scatter_rainbow",
        split="defective",
        artist_category="scatter_ols",
        defect_category="rainbow_colormap",
        expected_ship=False,
        expected_rules=("rainbow_colormap",),
        description="Color-mapped scatter plot using banned 'rainbow' colormap",
        builder=_defect_21_rainbow_scatter_rainbow,
    ),
    WildCase(
        case_id="defect_22_malformed_doubled_pct",
        split="defective",
        artist_category="bars_grouped",
        defect_category="text_malformed",
        expected_ship=False,
        expected_rules=("text_malformed",),
        description="Annotation containing doubled percent sign ('+12%%')",
        builder=_defect_22_malformed_doubled_pct,
    ),
    WildCase(
        case_id="defect_23_malformed_nan_junk",
        split="defective",
        artist_category="lines_dates",
        defect_category="text_malformed",
        expected_ship=False,
        expected_rules=("text_malformed",),
        description="Annotation containing junk 'nan' string",
        builder=_defect_23_malformed_nan_junk,
    ),
    WildCase(
        case_id="defect_24_malformed_ascii_minus",
        split="defective",
        artist_category="bars_grouped",
        defect_category="text_malformed",
        expected_ship=False,
        expected_rules=("text_malformed",),
        description="Negative annotation using ASCII hyphen ('-8') instead of U+2212",
        builder=_defect_24_malformed_ascii_minus,
    ),
    WildCase(
        case_id="defect_25_clipped_right_edge",
        split="defective",
        artist_category="lines_dates",
        defect_category="text_clipped",
        expected_ship=False,
        expected_rules=("text_clipped",),
        description="Figure text extending past the right edge of the canvas",
        builder=_defect_25_clipped_right_edge,
    ),
)

assert len(WILD_50) == 50
assert sum(1 for c in WILD_50 if c.split == "clean") == 25
assert sum(1 for c in WILD_50 if c.split == "defective") == 25
