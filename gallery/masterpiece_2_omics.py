"""Masterpiece 2 — Multi-Omics Cancer & Spatial Transcriptomics Atlas (Nature 183 mm)."""

from __future__ import annotations

import numpy as np
from matplotlib.lines import Line2D

import mintfig as mint

# Cohesive Nature Medicine editorial palette
VERMILION = "#C84B31"  # Activated / up / high-risk
SLATE_NAVY = "#2C5F8A"  # Repressed / down / low-risk
TEAL = "#1E8A78"  # Immune / intermediate
MIST = "#C8D1DC"  # Background / NS
INK = "#1A1D21"
MUTED_INK = "#4A525A"


def _kaplan_meier(
    times: np.ndarray,
    events: np.ndarray,
    t_max: float = 60.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Compute exact Kaplan-Meier step curve, Greenwood 95% CI, and censoring points."""
    order = np.argsort(times)
    t_sorted = times[order]
    e_sorted = events[order]

    unique_event_times = np.unique(t_sorted[e_sorted == 1])
    unique_event_times = unique_event_times[unique_event_times <= t_max]

    t_steps = [0.0]
    s_steps = [1.0]
    lo_steps = [1.0]
    hi_steps = [1.0]

    surv = 1.0
    greenwood_sum = 0.0

    for t in unique_event_times:
        at_risk = int(np.sum(t_sorted >= t))
        d = int(np.sum((t_sorted == t) & (e_sorted == 1)))
        if at_risk <= 0:
            break
        surv *= 1.0 - d / at_risk
        if at_risk > d:
            greenwood_sum += d / (at_risk * (at_risk - d))
        se = surv * np.sqrt(greenwood_sum)
        t_steps.append(float(t))
        s_steps.append(float(surv))
        lo_steps.append(float(np.clip(surv - 1.96 * se, 0.0, 1.0)))
        hi_steps.append(float(np.clip(surv + 1.96 * se, 0.0, 1.0)))

    if t_steps[-1] < t_max:
        t_steps.append(t_max)
        s_steps.append(s_steps[-1])
        lo_steps.append(lo_steps[-1])
        hi_steps.append(hi_steps[-1])

    t_arr = np.asarray(t_steps)
    s_arr = np.asarray(s_steps)
    lo_arr = np.asarray(lo_steps)
    hi_arr = np.asarray(hi_steps)

    # Censoring times strictly inside (0, t_max) so right-edge administrative end stays clean
    cens_mask = (e_sorted == 0) & (t_sorted < t_max)
    cens_t = t_sorted[cens_mask]
    cens_idx = np.searchsorted(t_arr, cens_t, side="right") - 1
    cens_idx = np.clip(cens_idx, 0, len(s_arr) - 1)
    cens_s = s_arr[cens_idx]

    return t_arr, s_arr, lo_arr, hi_arr, cens_t, cens_s


def _build_panel_a_volcano(ax, rng: np.random.Generator) -> None:
    """Panel a: Differential expression volcano plot (4,500 genes)."""
    n_ns = 3770
    n_down = 318
    n_up = 412

    # Non-significant gene cloud
    fc_ns = rng.normal(0.0, 0.58, n_ns)
    fc_ns = np.clip(fc_ns, -2.5, 2.5)
    y_ns = rng.exponential(0.55, n_ns) + 0.05
    outside_fc = np.abs(fc_ns) >= 1.0
    y_ns[outside_fc] = np.minimum(y_ns[outside_fc], rng.uniform(0.1, 1.92, outside_fc.sum()))
    y_ns[~outside_fc] = np.minimum(y_ns[~outside_fc], 4.0)

    # Downregulated genes (log2FC <= -1, -log10FDR >= 2)
    fc_down = -(1.04 + rng.gamma(1.65, 0.48, n_down))
    fc_down = np.clip(fc_down, -3.9, -1.04)
    y_down = 2.08 + 1.32 * (np.abs(fc_down) - 1.0) ** 1.12 + rng.exponential(1.18, n_down)
    y_down = np.clip(y_down, 2.08, 12.2)

    # Upregulated genes (log2FC >= 1, -log10FDR >= 2)
    fc_up = 1.04 + rng.gamma(1.7, 0.50, n_up)
    fc_up = np.clip(fc_up, 1.04, 3.95)
    y_up = 2.08 + 1.38 * (fc_up - 1.0) ** 1.12 + rng.exponential(1.25, n_up)
    y_up = np.clip(y_up, 2.08, 12.5)

    # Highlighted canonical genes placed with labels in pure open whitespace
    featured_up = [
        ("STAT3", 3.55, 12.15, (2.40, 13.05), "right"),
        ("MYC", 3.12, 9.75, (4.72, 10.75), "right"),
        ("BCL2", 2.55, 7.15, (4.72, 8.20), "right"),
    ]
    featured_down = [
        ("CDKN1A", -3.45, 11.45, (-1.24, 12.45), "right"),
        ("BAX", -2.78, 8.85, (-4.72, 10.00), "left"),
        ("TP53INP1", -2.30, 6.45, (-4.72, 7.55), "left"),
    ]
    for i, (_, gx, gy, _, _) in enumerate(featured_up):
        fc_up[i], y_up[i] = gx, gy
    for i, (_, gx, gy, _, _) in enumerate(featured_down):
        fc_down[i], y_down[i] = gx, gy

    mint.pub.subtle_grid(ax, axis="y", color="#EEF1F6", lw=0.4)

    # Threshold dashed lines
    ax.axvline(-1.0, color="#8A94A3", lw=0.55, ls="--", zorder=1)
    ax.axvline(1.0, color="#8A94A3", lw=0.55, ls="--", zorder=1)
    ax.axhline(2.0, color="#8A94A3", lw=0.55, ls="--", zorder=1)

    # Scatter layers (NS cloud rasterized for ultra-compact crisp PDF)
    ns_sc = ax.scatter(fc_ns, y_ns, s=3.2, color=MIST, alpha=0.62, linewidths=0, zorder=2)
    ns_sc.set_rasterized(True)

    ax.scatter(
        fc_down[3:], y_down[3:], s=4.8, color=SLATE_NAVY, alpha=0.72, linewidths=0, zorder=3
    )
    ax.scatter(
        fc_up[3:], y_up[3:], s=4.8, color=VERMILION, alpha=0.72, linewidths=0, zorder=3
    )

    # Highlighted dots with white rings + crisp leader lines
    for gene, gx, gy, (tx, ty), ha in featured_up:
        ax.scatter(
            [gx], [gy], s=18, color=VERMILION, edgecolor="white", linewidth=0.55, zorder=6
        )
        ax.annotate(
            gene,
            xy=(gx, gy),
            xytext=(tx, ty),
            fontsize=5.8,
            fontstyle="italic",
            fontweight="bold",
            color=INK,
            ha=ha,
            va="center",
            arrowprops={
                "arrowstyle": "-",
                "color": "#3A424D",
                "lw": 0.45,
                "shrinkA": 1.2,
                "shrinkB": 2.4,
            },
            zorder=7,
        )

    for gene, gx, gy, (tx, ty), ha in featured_down:
        ax.scatter(
            [gx], [gy], s=18, color=SLATE_NAVY, edgecolor="white", linewidth=0.55, zorder=6
        )
        ax.annotate(
            gene,
            xy=(gx, gy),
            xytext=(tx, ty),
            fontsize=5.8,
            fontstyle="italic",
            fontweight="bold",
            color=INK,
            ha=ha,
            va="center",
            arrowprops={
                "arrowstyle": "-",
                "color": "#3A424D",
                "lw": 0.45,
                "shrinkA": 1.2,
                "shrinkB": 2.4,
            },
            zorder=7,
        )

    # Subtle directional counts in upper corners
    ax.text(
        0.02,
        0.97,
        f"Down: {n_down}",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=5.8,
        fontweight="bold",
        color=SLATE_NAVY,
    )
    ax.text(
        0.98,
        0.97,
        f"Up: {n_up}",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=5.8,
        fontweight="bold",
        color=VERMILION,
    )

    ax.set_xlim(-4.85, 4.85)
    ax.set_ylim(-0.35, 14.4)
    ax.set_xticks([-4, -2, 0, 2, 4])
    ax.set_yticks([0, 4, 8, 12])
    ax.set_xlabel(r"$\log_2$ fold change (Tumor / Normal)")
    ax.set_ylabel(r"$-\log_{10}(\mathrm{FDR})$")
    ax.set_title("Differential expression (4,500 genes)", pad=5.0)
    mint.pub.despine(ax)


def _build_panel_b_spatial(ax, fig, rng: np.random.Generator) -> None:
    """Panel b: Spatial transcriptomics tissue section (~1,400 hexagonal spots)."""
    # Build hexagonal Visium-like spot grid over an organic horizontal biopsy section (~3.6 x 2.6 mm)
    pitch = 72.0
    xs_list: list[float] = []
    ys_list: list[float] = []
    row_idx = 0
    y = 140.0
    while y <= 2660.0:
        x_off = 0.5 * pitch if (row_idx % 2 == 1) else 0.0
        x = 120.0 + x_off
        while x <= 3480.0:
            xs_list.append(x)
            ys_list.append(y)
            x += pitch
        y += pitch * np.sqrt(3) / 2.0
        row_idx += 1

    gx = np.asarray(xs_list) + rng.normal(0.0, 4.0, len(xs_list))
    gy = np.asarray(ys_list) + rng.normal(0.0, 4.0, len(ys_list))

    # Organic lobulated ovoid biopsy section centered at (1800, 1380)
    cx, cy = 1800.0, 1380.0
    dx = (gx - cx) / 1.24
    dy = gy - cy
    theta = np.arctan2(dy, dx)
    r = np.hypot(dx, dy)

    r_outer = (
        1180.0
        + 95.0 * np.cos(2.0 * theta - 0.5)
        + 68.0 * np.sin(3.0 * theta + 0.35)
        + 36.0 * np.cos(5.0 * theta - 1.1)
    )
    in_tissue = r <= r_outer
    sx = gx[in_tissue]
    sy = gy[in_tissue]

    # Bilobed tumor core field (high STAT3) + peripheral immune stroma
    d1 = np.hypot((sx - 1480.0) / 600.0, (sy - 1480.0) / 480.0)
    d2 = np.hypot((sx - 2080.0) / 480.0, (sy - 1220.0) / 420.0)
    tumor_field = np.maximum(np.exp(-1.25 * d1**2), 0.88 * np.exp(-1.35 * d2**2))
    d3 = np.hypot((sx - 1150.0) / 260.0, (sy - 960.0) / 230.0)
    tumor_field = np.clip(tumor_field + 0.22 * np.exp(-1.5 * d3**2), 0.0, 1.0)

    expr = 0.22 + 3.85 * (tumor_field**1.25) + rng.normal(0.0, 0.26, len(sx))
    expr = np.clip(expr, 0.0, 4.4)

    # Subtle outer tissue perimeter contour
    th_grid = np.linspace(0, 2 * np.pi, 360)
    r_grid = (
        1205.0
        + 95.0 * np.cos(2.0 * th_grid - 0.5)
        + 68.0 * np.sin(3.0 * th_grid + 0.35)
        + 36.0 * np.cos(5.0 * th_grid - 1.1)
    )
    ax.plot(
        cx + 1.24 * r_grid * np.cos(th_grid),
        cy + r_grid * np.sin(th_grid),
        color="#B8C2CE",
        lw=0.65,
        zorder=1,
    )

    # Spots rendered in mintfig_coral (monotonic luminance -> crisp in grayscale!)
    sc = ax.scatter(
        sx,
        sy,
        c=expr,
        cmap="mintfig_coral",
        vmin=0.0,
        vmax=4.2,
        s=5.8,
        edgecolors="#E6DDD9",
        linewidths=0.15,
        zorder=2,
    )

    # Crisp dashed tumor-margin contour on continuous grid
    xi = np.linspace(120, 3480, 180)
    yi = np.linspace(120, 2680, 160)
    xx, yy = np.meshgrid(xi, yi)
    fd1 = np.hypot((xx - 1480.0) / 600.0, (yy - 1480.0) / 480.0)
    fd2 = np.hypot((xx - 2080.0) / 480.0, (yy - 1220.0) / 420.0)
    field_grid = np.maximum(np.exp(-1.25 * fd1**2), 0.88 * np.exp(-1.35 * fd2**2))

    rr_g = np.hypot((xx - cx) / 1.24, yy - cy)
    th_g = np.arctan2(yy - cy, (xx - cx) / 1.24)
    ro_g = (
        1180.0
        + 95.0 * np.cos(2.0 * th_g - 0.5)
        + 68.0 * np.sin(3.0 * th_g + 0.35)
        + 36.0 * np.cos(5.0 * th_g - 1.1)
    )
    field_grid = np.where(rr_g <= ro_g, field_grid, np.nan)
    ax.contour(
        xx,
        yy,
        field_grid,
        levels=[0.46],
        colors=[INK],
        linewidths=0.85,
        linestyles="--",
        zorder=4,
    )

    # High-contrast pill annotations (100% legible in color & grayscale)
    pill_kw = {
        "boxstyle": "round,pad=0.22",
        "facecolor": "white",
        "edgecolor": "#BAC3CE",
        "linewidth": 0.45,
        "alpha": 0.95,
    }
    ax.annotate(
        "Tumor core",
        xy=(1460.0, 1640.0),
        xytext=(500.0, 2500.0),
        fontsize=5.8,
        fontweight="bold",
        color=INK,
        ha="left",
        va="center",
        bbox=pill_kw,
        arrowprops={"arrowstyle": "-", "color": INK, "lw": 0.55, "shrinkB": 2.0},
        zorder=6,
    )
    ax.annotate(
        "Immune stroma",
        xy=(2620.0, 1860.0),
        xytext=(2660.0, 2550.0),
        fontsize=5.8,
        color=INK,
        ha="center",
        va="center",
        bbox=pill_kw,
        arrowprops={"arrowstyle": "-", "color": MUTED_INK, "lw": 0.5, "shrinkB": 2.0},
        zorder=6,
    )

    ax.set_xlim(120, 3480)
    ax.set_ylim(100, 2760)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    mint.pub.scalebar(
        ax,
        length=500,
        unit="µm",
        pixel_size=1.0,
        location="lower right",
        pad_frac=0.04,
        bar_height_pt=2.0,
        color=INK,
        frameon=False,
        fontsize=5.8,
    )

    cbar = fig.colorbar(sc, ax=ax, fraction=0.042, pad=0.03, aspect=18)
    cbar.set_ticks([0, 1, 2, 3, 4])
    mint.pub.style_colorbar(cbar, label="STAT3 expr. (log1p)", tick_pt=5.8)
    ax.set_title(f"Spatial transcriptomics ({len(sx):,} spots)", pad=5.0)


def _build_panel_c_dotplot(ax, fig) -> None:
    """Panel c: Hallmark pathway enrichment dot plot across 4 treatment arms."""
    pathways = [
        "IL6–JAK–STAT3",
        "MYC targets v1",
        "G2M checkpoint",
        "E2F targets",
        "Inflammatory resp.",
        "Interferon-α",
        "Apoptosis",
        "p53 pathway",
    ]
    arms = ["Vehicle", "Mono-A", "Mono-B", "Combo"]

    nes = np.array(
        [
            [2.25, 0.85, 0.55, -2.28],  # IL6-JAK-STAT3
            [2.10, 0.70, 0.95, -2.05],  # MYC targets v1
            [1.82, 0.45, 0.60, -1.92],  # G2M checkpoint
            [1.68, 0.35, 0.40, -1.75],  # E2F targets
            [-1.35, 0.55, 0.72, 1.98],  # Inflammatory resp.
            [-1.18, 0.42, 0.88, 1.84],  # Interferon-a
            [-1.55, 0.65, 0.78, 2.15],  # Apoptosis
            [-1.42, 0.50, 0.62, 2.02],  # p53 pathway
        ]
    )

    neg_log_fdr = np.array(
        [
            [6.2, 2.1, 1.5, 6.4],
            [5.8, 1.8, 2.4, 5.9],
            [4.9, 1.3, 1.7, 5.4],
            [4.4, 1.1, 1.2, 4.8],
            [3.2, 1.6, 2.2, 5.6],
            [2.8, 1.3, 2.7, 5.1],
            [3.9, 2.0, 2.5, 6.1],
            [3.5, 1.6, 1.9, 5.7],
        ]
    )

    n_rows, n_cols = nes.shape
    xs, ys = np.meshgrid(np.arange(n_cols), np.arange(n_rows))
    sizes = 8.0 + 9.2 * np.clip(neg_log_fdr, 0.5, 6.5)

    mint.pub.subtle_grid(ax, axis="both", color="#ECEFF4", lw=0.45)
    ax.axhline(3.5, color="#CBD3DC", lw=0.6, ls=":", zorder=1)

    sc = ax.scatter(
        xs.ravel(),
        ys.ravel(),
        s=sizes.ravel(),
        c=nes.ravel(),
        cmap="mintfig_div",
        vmin=-2.4,
        vmax=2.4,
        edgecolors="#3A434E",
        linewidths=0.42,
        zorder=3,
    )

    ax.set_xticks(np.arange(n_cols))
    ax.set_xticklabels(arms)
    ax.set_yticks(np.arange(n_rows))
    ax.set_yticklabels(pathways)
    ax.set_xlim(-0.55, n_cols - 0.45)
    ax.set_ylim(n_rows - 0.55, -0.55)
    ax.tick_params(axis="both", length=0)

    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_edgecolor("#D4DBE4")
        spine.set_linewidth(0.45)

    cbar = fig.colorbar(sc, ax=ax, fraction=0.048, pad=0.04, aspect=18)
    cbar.set_ticks([-2, -1, 0, 1, 2])
    mint.pub.style_colorbar(cbar, label="NES", tick_pt=5.8)

    # Single-line inline FDR size key aligned neatly with Panel d's x-axis label
    handles = [
        Line2D([0], [0], linestyle="none", marker="", label="FDR:"),
        *[
            Line2D(
                [0],
                [0],
                marker="o",
                linestyle="none",
                markersize=np.sqrt(8.0 + 9.2 * v),
                markerfacecolor="#D4DCE6",
                markeredgecolor="#3A434E",
                markeredgewidth=0.45,
                label=lbl,
            )
            for v, lbl in [(1.0, r"$10^{-1}$"), (3.0, r"$10^{-3}$"), (6.0, r"$10^{-6}$")]
        ],
    ]
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.46, -0.14),
        ncol=4,
        frameon=False,
        fontsize=5.6,
        handlelength=0.9,
        handletextpad=0.32,
        columnspacing=0.75,
        borderpad=0.0,
    )

    ax.set_title("Hallmark pathway enrichment", pad=5.0)


def _build_panel_d_survival(ax, rng: np.random.Generator) -> None:
    """Panel d: Kaplan-Meier overall survival with 95% CI ribbons & censoring ticks."""
    t_max = 60.0
    cohorts = [
        ("Low-risk (n=72)", 72, 0.0048, SLATE_NAVY, "-", 1.25),
        ("Intermediate (n=84)", 84, 0.0118, TEAL, "--", 1.15),
        ("High-risk (n=68)", 68, 0.0265, VERMILION, "-", 1.35),
    ]

    mint.pub.subtle_grid(ax, axis="y", color="#EEF1F6", lw=0.45)

    for label, n_pat, hazard, color, ls, lw in cohorts:
        event_t = rng.exponential(1.0 / hazard, n_pat)
        # Mostly full 60-month follow-up with ~25% random right-censoring between 18 and 56 months
        random_drop = rng.random(n_pat) < 0.25
        cens_t = np.where(random_drop, rng.uniform(18.0, 56.0, n_pat), 62.0)
        obs_t = np.minimum(event_t, cens_t)
        events = (event_t <= cens_t).astype(int)

        t_arr, s_arr, lo_arr, hi_arr, ct, cs = _kaplan_meier(obs_t, events, t_max=t_max)

        ax.fill_between(
            t_arr,
            lo_arr * 100.0,
            hi_arr * 100.0,
            step="post",
            color=color,
            alpha=0.14,
            linewidth=0,
            zorder=2,
        )
        ax.step(
            t_arr,
            s_arr * 100.0,
            where="post",
            color=color,
            linestyle=ls,
            linewidth=lw,
            label=label,
            zorder=4,
        )
        ax.plot(
            ct,
            cs * 100.0,
            linestyle="none",
            marker="|",
            markersize=3.8,
            markeredgewidth=0.6,
            color=color,
            zorder=5,
        )

    ax.set_xlim(0.0, t_max)
    ax.set_ylim(0.0, 104.0)
    ax.set_xticks([0, 12, 24, 36, 48, 60])
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_xlabel("Time from diagnosis (months)")
    ax.set_ylabel("Overall survival (%)")
    ax.set_title("Patient survival by STAT3 subtype", pad=5.0)
    mint.pub.despine(ax)

    mint.pub.direct_labels(ax, pad_pt=4.5, min_sep_pt=9.5, fontsize=5.8, expand_xlim=0.38)

    # Clean editorial stats callout in open lower-left region
    ax.text(
        2.4,
        5.5,
        "HR = 0.34 (0.21–0.54)\nLog-rank p = 0.0002",
        ha="left",
        va="bottom",
        fontsize=5.8,
        color=INK,
        linespacing=1.35,
    )


def build() -> mint.Plate:
    """Build Masterpiece 2: Nature double-column multi-omics & spatial oncology atlas."""
    rng = np.random.default_rng(42)

    plate = mint.Plate(
        journal="nature",
        width="double",
        height_mm=122.0,
        layout=(2, 2),
        width_ratios=[1.02, 1.15],
        height_ratios=[1.02, 1.0],
        gap_mm=(10.0, 9.5),
        palette="nature_muted",
    )

    _build_panel_a_volcano(plate["a"], rng)
    _build_panel_b_spatial(plate["b"], plate.fig, rng)
    _build_panel_c_dotplot(plate["c"], plate.fig)
    _build_panel_d_survival(plate["d"], rng)

    plate.label_panels()
    return plate


if __name__ == "__main__":
    p = build()
    p.bundle("gallery/output/masterpiece_2_omics", source_path=__file__)
