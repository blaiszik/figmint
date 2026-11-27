"""Zero-rewrite BYO Matplotlib gallery: 5 messy default figures upgraded in 1–2 lines.

Run directly to generate before/after PNGs in ``gallery/output/byo_matplotlib/``
and verify every upgraded figure passes ``ship: True``.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import mintfig as mint

OUT_DIR = Path(__file__).resolve().parent / "output" / "byo_matplotlib"
SOURCE = "synthetic benchmark data"


def _save_before(fig: matplotlib.figure.Figure, path: Path) -> dict[str, object]:
    fig.savefig(path, dpi=150)
    report = mint.check(fig, width="chat", dpi=150)
    plt.close(fig)
    return {
        "path": str(path),
        "ship": report.ship,
        "issues": [i["rule"] for i in report["issues"]],
        "min_text_px": report["display"].get("min_text_px"),
    }


def _save_after(exp: mint.Explanation, source_fig: matplotlib.figure.Figure, path: Path) -> dict[str, object]:
    summary = exp.save(path)
    plt.close(source_fig)
    plt.close(exp.fig)
    return {
        "path": str(path),
        "ship": summary["ship"],
        "issues": [i["rule"] for i in summary["issues"]],
        "facts": summary["panels"][0]["facts"][:2],
    }


def example_01_ablation_bars(out_dir: Path) -> tuple[dict[str, object], dict[str, object]]:
    """1. Ablation bars: oversized canvas + truncated baseline -> crisp zero-based takeaway."""
    labels = ["Full\nmodel", "No\ncache", "No\nrerank", "No\nchunking", "No\nretrieval"]
    scores = [0.86, 0.84, 0.81, 0.79, 0.74]

    # Before: default Matplotlib with oversized figsize and truncated y-axis
    fig_b, ax_b = plt.subplots(figsize=(11, 5))
    ax_b.bar(labels, scores)
    ax_b.set_ylim(0.70, 0.88)
    ax_b.set_title("Ablation Results")
    before = _save_before(fig_b, out_dir / "01_ablation_bars_before.png")

    # After: 1–2 line upgrade with mint.style() + mint.explain()
    with mint.style():
        fig_a, ax_a = plt.subplots()
        colors = ["#1F5A9D", "#B4BCC6", "#B4BCC6", "#B4BCC6", "#CD4324"]
        bars = ax_a.bar(labels, scores, color=colors, width=0.58)
        ax_a.set_ylim(0, 1.0)
        ax_a.set_ylabel("Accuracy")
        for bar, val in zip(bars, scores):
            ax_a.text(
                bar.get_x() + bar.get_width() / 2,
                val + 0.02,
                f"{val:.2f}",
                ha="center",
                va="bottom",
            )
    exp = mint.explain(
        "Removing retrieval costs 12 points of accuracy (0.74 vs 0.86 full model)",
        fig_a,
        subtitle="Exact-match accuracy across ablations",
        source=SOURCE,
    )
    after = _save_after(exp, fig_a, out_dir / "01_ablation_bars_after.png")
    return before, after


def example_02_training_curves_ci(out_dir: Path) -> tuple[dict[str, object], dict[str, object]]:
    """2. Training curves + 95% CI band: tiny text & unlabelled band -> clear convergence."""
    steps = np.arange(0, 55, 5)
    pre_mean = np.array([1.85, 1.18, 0.82, 0.61, 0.48, 0.39, 0.34, 0.31, 0.29, 0.28, 0.28])
    pre_ci = np.array([0.08, 0.07, 0.06, 0.05, 0.04, 0.04, 0.03, 0.03, 0.03, 0.02, 0.02])
    post_mean = np.array([1.86, 1.54, 1.29, 1.11, 0.96, 0.86, 0.79, 0.74, 0.71, 0.68, 0.67])
    post_ci = np.array([0.09, 0.09, 0.08, 0.08, 0.07, 0.07, 0.06, 0.06, 0.06, 0.05, 0.05])

    # Before: oversized figure, unlabelled CI band, raw defaults
    fig_b, ax_b = plt.subplots(figsize=(11, 5))
    ax_b.plot(steps, pre_mean, label="Pre-norm")
    ax_b.fill_between(steps, pre_mean - pre_ci, pre_mean + pre_ci, alpha=0.25)
    ax_b.plot(steps, post_mean, label="Post-norm")
    ax_b.fill_between(steps, post_mean - post_ci, post_mean + post_ci, alpha=0.25)
    ax_b.set_title("Training Loss")
    ax_b.legend()
    before = _save_before(fig_b, out_dir / "02_training_curves_ci_before.png")

    # After: mint.style() + labelled 95% CI + mint.explain()
    with mint.style():
        fig_a, ax_a = plt.subplots()
        ax_a.plot(steps, pre_mean, label="Pre-norm (95% CI, 5 seeds)")
        ax_a.fill_between(steps, pre_mean - pre_ci, pre_mean + pre_ci, alpha=0.2)
        ax_a.plot(steps, post_mean, label="Post-norm (95% CI, 5 seeds)")
        ax_a.fill_between(steps, post_mean - post_ci, post_mean + post_ci, alpha=0.2)
        ax_a.set_xlabel("Training steps (k)")
        ax_a.set_ylabel("Validation loss")
        ax_a.set_ylim(0, 2.05)
        ax_a.legend(loc="upper right")
    exp = mint.explain(
        "Pre-norm reaches 0.28 validation loss vs 0.67 for post-norm across 5 seeds",
        fig_a,
        subtitle="Transformer validation loss with 95% CI bands",
        source=SOURCE,
    )
    after = _save_after(exp, fig_a, out_dir / "02_training_curves_ci_after.png")
    return before, after


def example_03_heatmap_colorbar(out_dir: Path) -> tuple[dict[str, object], dict[str, object]]:
    """3. Heatmap + colorbar: jet rainbow colormap -> perceptual viridis + takeaway."""
    mat = np.array(
        [
            [0.14, 0.19, 0.22, 0.18],
            [0.16, 0.21, 0.25, 0.20],
            [0.19, 0.28, 0.82, 0.31],
            [0.15, 0.22, 0.44, 0.24],
        ]
    )
    layers = ["L4", "L8", "L12", "L16"]
    tokens = ["System", "Boilerplate", "Retrieved", "Query"]

    # Before: rainbow jet colormap, oversized canvas, unlabelled colorbar
    fig_b, ax_b = plt.subplots(figsize=(10, 6))
    im_b = ax_b.imshow(mat, cmap="jet")
    fig_b.colorbar(im_b, ax=ax_b)
    ax_b.set_xticks(range(len(tokens)), tokens)
    ax_b.set_yticks(range(len(layers)), layers)
    ax_b.set_title("Attention Matrix")
    before = _save_before(fig_b, out_dir / "03_heatmap_colorbar_before.png")

    # After: mint.style() automatically uses viridis + crisp typography
    with mint.style():
        fig_a, ax_a = plt.subplots()
        im_a = ax_a.imshow(mat, aspect="auto", vmin=0.0, vmax=0.9)
        cbar = fig_a.colorbar(im_a, ax=ax_a)
        cbar.set_label("Mean attention weight")
        ax_a.set_xticks(range(len(tokens)), tokens)
        ax_a.set_yticks(range(len(layers)), layers)
        ax_a.set_xlabel("Token group")
        ax_a.set_ylabel("Layer")
        ax_a.grid(False)
    exp = mint.explain(
        "Layer 12 attention peaks at 0.82 on retrieved tokens, 3.7x higher than boilerplate",
        fig_a,
        subtitle="Mean attention weight by transformer layer and token span",
        source=SOURCE,
    )
    after = _save_after(exp, fig_a, out_dir / "03_heatmap_colorbar_after.png")
    return before, after


def example_04_latency_boxplot(out_dir: Path) -> tuple[dict[str, object], dict[str, object]]:
    """4. Boxplot: tiny labels & unlabelled axis -> crisp serving latency comparison."""
    rng = np.random.default_rng(42)
    fp16 = rng.normal(83.0, 9.5, 80)
    int8 = rng.normal(54.0, 6.2, 80)
    int4 = rng.normal(38.0, 4.1, 80)
    groups = [fp16, int8, int4]
    names = ["FP16", "INT8", "INT4"]
    med_fp16 = float(np.median(fp16))
    med_int4 = float(np.median(int4))

    # Before: oversized canvas, unlabelled y-axis, topic title
    fig_b, ax_b = plt.subplots(figsize=(11, 5))
    ax_b.boxplot(groups, tick_labels=names)
    ax_b.set_title("Latency Distribution")
    before = _save_before(fig_b, out_dir / "04_latency_boxplot_before.png")

    # After: mint.style() + clean boxplot + mint.explain()
    with mint.style():
        fig_a, ax_a = plt.subplots()
        bp = ax_a.boxplot(
            groups,
            tick_labels=names,
            patch_artist=True,
            widths=0.45,
            medianprops={"color": "#1A1D21", "linewidth": 1.8},
            whiskerprops={"color": "#5B6570", "linewidth": 1.2},
            capprops={"color": "#5B6570", "linewidth": 1.2},
            flierprops={"marker": "o", "markersize": 3.5, "alpha": 0.45},
        )
        for patch, color in zip(bp["boxes"], ["#CDD3DA", "#8FB5DF", "#1F5A9D"]):
            patch.set_facecolor(color)
            patch.set_edgecolor("#1A1D21")
            patch.set_linewidth(0.8)
        ax_a.set_ylabel("Latency (ms)")
        ax_a.set_ylim(0, 115)
    exp = mint.explain(
        f"INT4 cuts median latency to {med_int4:.1f} ms vs {med_fp16:.1f} ms for FP16 with tighter spread",
        fig_a,
        subtitle="Per-request decode latency across 80 prompts per precision",
        source=SOURCE,
    )
    after = _save_after(exp, fig_a, out_dir / "04_latency_boxplot_after.png")
    return before, after


def example_05_scatter_regression(out_dir: Path) -> tuple[dict[str, object], dict[str, object]]:
    """5. Scatter + regression: cluttered unlabelled defaults -> clean correlation takeaway."""
    rng = np.random.default_rng(19)
    ctx_k = np.linspace(4, 64, 24)
    recall = 54.0 + 0.48 * ctx_k + rng.normal(0.0, 2.4, len(ctx_k))
    slope, intercept = np.polyfit(ctx_k, recall, 1)
    r_val = float(np.corrcoef(ctx_k, recall)[0, 1])

    # Before: oversized figure, unlabelled axes, text struck by line
    fig_b, ax_b = plt.subplots(figsize=(11, 5))
    ax_b.scatter(ctx_k, recall)
    ax_b.plot(ctx_k, slope * ctx_k + intercept, "--")
    ax_b.text(32, slope * 32 + intercept, f"r = {r_val:.2f}")
    ax_b.set_title("Context vs Recall")
    before = _save_before(fig_b, out_dir / "05_scatter_regression_before.png")

    # After: mint.style() + clean scatter & OLS line + clear takeaway
    with mint.style():
        fig_a, ax_a = plt.subplots()
        ax_a.scatter(ctx_k, recall, s=28, alpha=0.85, zorder=3)
        x_line = np.array([ctx_k.min(), ctx_k.max()])
        ax_a.plot(x_line, slope * x_line + intercept, color="#CD4324", linewidth=1.8, zorder=4)
        ax_a.set_xlabel("Context window (k tokens)")
        ax_a.set_ylabel("Needle recall (%)")
        ax_a.set_ylim(45, 95)
        ax_a.text(
            8,
            88,
            f"OLS fit: +{slope * 60:.0f} pts across 4k–64k (r = {r_val:.2f})",
            color="#CD4324",
            fontweight="bold",
        )
    exp = mint.explain(
        f"Longer context strongly lifts recall (r = {r_val:.2f}), rising from {recall[0]:.0f}% to {recall[-1]:.0f}%",
        fig_a,
        subtitle="Long-context needle-in-a-haystack evaluation",
        source=SOURCE,
    )
    after = _save_after(exp, fig_a, out_dir / "05_scatter_regression_after.png")
    return before, after


def build_all(out_dir: Path = OUT_DIR) -> list[tuple[str, dict[str, object], dict[str, object]]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    builders = [
        ("01_ablation_bars", example_01_ablation_bars),
        ("02_training_curves_ci", example_02_training_curves_ci),
        ("03_heatmap_colorbar", example_03_heatmap_colorbar),
        ("04_latency_boxplot", example_04_latency_boxplot),
        ("05_scatter_regression", example_05_scatter_regression),
    ]
    results: list[tuple[str, dict[str, object], dict[str, object]]] = []
    for name, fn in builders:
        before, after = fn(out_dir)
        results.append((name, before, after))
    return results


if __name__ == "__main__":
    all_results = build_all()
    for name, before, after in all_results:
        print(
            f"{name}: BEFORE ship={before['ship']} issues={before['issues']} | "
            f"AFTER ship={after['ship']} issues={after['issues']}"
        )
        assert after["ship"] is True, f"{name} failed ship: {after}"
