"""Cell Press double-column plate: Single-cell CRISPRi perturbation & lineage bifurcation atlas.

ALL DATA ARE SYNTHETIC. Every velocity field, single-cell manifold, transcription-factor
pseudotime profile, and CRISPRi log-odds effect is generated deterministically from a
minimal hematopoiesis bifurcation toy model in this file. Nothing here is an experimental
measurement; the plate showcases the new ``cell`` Press specification (174.0 mm, bold
uppercase A–D) in the mintfig house style.

Run through the mintfig contract::

    mintfig run gallery/cell_lineage_bifurcation.py --journal cell \
        --bundle gallery/output/cell_lineage_bifurcation --json
"""

from __future__ import annotations

import numpy as np
from matplotlib.colors import LinearSegmentedColormap, Normalize

import mintfig as mint

CAPTION = (
    "Synthetic single-cell CRISPRi perturbation and hematopoietic lineage bifurcation atlas "
    "(Cell Press double column, 174.0 mm). "
    "(A) Two-dimensional developmental landscape with velocity stream lines showing progenitor "
    "bifurcation into erythroid and myeloid fates at commitment pseudotime t* = 0.44. "
    "(B) Pseudotime-ordered expression cascade of ten lineage transcription factors (z-scored). "
    "(C) CRISPRi knockdown log-odds shift toward erythroid versus myeloid fate (mean and 95% CI). "
    "(D) Opposing dynamics of GATA1 and SPI1 across pseudotime with single-cell scatter and "
    "smooth 95% confidence ribbons. All data are synthetic."
)
LABEL = "fig:cell_lineage_bifurcation"
TAKEAWAY = (
    "Hematopoietic progenitors bifurcate sharply at t* = 0.44 along an antagonistic GATA1–SPI1 "
    "switch whose perturbation reverses erythroid versus myeloid lineage bias."
)
PANEL_NOTES = {
    "A": "RNA velocity stream lines split progenitors cleanly into erythroid (upper) and myeloid (lower) branches.",
    "B": "Ten master regulators wave sequentially along pseudotime, diverging cleanly past the t* = 0.44 rail.",
    "C": "GATA1/KLF1 knockdown depletes erythroid fate (-1.9 to -1.3 log-odds) whereas SPI1/IRF8 knockdown enriches it.",
    "D": "GATA1 and SPI1 trajectories cross precisely at t* = 0.44 before locking into mutually exclusive states.",
}

INK = "#1A1D21"
MUTED = "#5D6673"
RULE = "#C8D0DA"
ERY = "#C84B31"     # Erythroid branch identity (vermilion)
MYE = "#137E6E"     # Myeloid branch identity (deep teal)
CTRL = "#6D7684"    # Non-targeting control / neutral ink

# Soft background potential ramp (intentionally pale so flowlines & branches lead)
DENSITY_CMAP = LinearSegmentedColormap.from_list(
    "waddington_mist",
    ["#FFFFFF", "#F3F6FA", "#E0E9F3", "#C3D5E8", "#9DBAD6"],
)


def _panel_landscape(ax, rng: np.random.Generator) -> None:
    """Panel A: Waddington density landscape, RNA velocity flow, and bifurcation paths."""
    gx = np.linspace(-0.2, 4.4, 160)
    gy = np.linspace(-2.4, 2.4, 160)
    X, Y = np.meshgrid(gx, gy)

    # Smooth bifurcating potential landscape: single stem basin -> upper/lower valleys
    def _branch_y(x: np.ndarray) -> np.ndarray:
        return 1.38 * np.maximum(0.0, (x - 1.55) / 2.65) ** 0.78

    y_up = _branch_y(X)
    y_dn = -y_up
    sigma_y = 0.42 + 0.08 * np.clip(X / 4.0, 0.0, 1.0)
    dens = (
        0.95 * np.exp(-((X - 0.65) ** 2 / 0.55 + Y**2 / 0.34))
        + 0.78 * np.exp(-((Y - y_up) ** 2 / (2 * sigma_y**2))) * np.exp(-((X - 2.95) ** 2 / 2.2))
        + 0.78 * np.exp(-((Y - y_dn) ** 2 / (2 * sigma_y**2))) * np.exp(-((X - 2.95) ** 2 / 2.2))
    )

    im = ax.imshow(
        dens,
        extent=[gx[0], gx[-1], gy[0], gy[-1]],
        origin="lower",
        cmap=DENSITY_CMAP,
        aspect="auto",
        zorder=0,
    )
    im.set_visible(True)
    # Mark density underlay as decorative so clarity_metadata does not demand a density colorbar
    ax._mintfig_decorative = True  # type: ignore[attr-defined]

    # Subtle elevation contour lines
    ax.contour(X, Y, dens, levels=[0.22, 0.48, 0.74], colors="#B4C3D4", linewidths=0.4, zorder=1)

    # Synthetic single-cell embedding scatter along progenitor + two branches (2,400 cells)
    n_prog = 700
    x_p = rng.normal(0.75, 0.40, size=n_prog)
    y_p = rng.normal(0.0, 0.28, size=n_prog)
    n_b = 850
    xb1 = rng.uniform(1.45, 4.1, size=n_b)
    yb1 = _branch_y(xb1) + rng.normal(0.0, 0.25, size=n_b)
    xb2 = rng.uniform(1.45, 4.1, size=n_b)
    yb2 = -_branch_y(xb2) + rng.normal(0.0, 0.25, size=n_b)

    ax.scatter(x_p, y_p, s=2.2, color="#7A8EA8", alpha=0.22, linewidths=0, zorder=2)
    ax.scatter(xb1, yb1, s=2.2, color=ERY, alpha=0.18, linewidths=0, zorder=2)
    ax.scatter(xb2, yb2, s=2.2, color=MYE, alpha=0.18, linewidths=0, zorder=2)

    # Smooth velocity vector field guiding progenitors down the two valleys
    sgx = np.linspace(0.05, 4.2, 24)
    sgy = np.linspace(-2.1, 2.1, 20)
    SX, SY = np.meshgrid(sgx, sgy)
    target_y = np.where(SY >= 0, _branch_y(SX), -_branch_y(SX))
    U = 0.85 + 0.15 * np.exp(-((SX - 1.6) ** 2))
    V = 1.35 * (target_y - SY) * np.clip((SX - 0.55) / 1.4, 0.15, 1.0)
    ax.streamplot(
        sgx,
        sgy,
        U,
        V,
        density=0.72,
        color="#6E7C8C",
        linewidth=0.45,
        arrowsize=0.55,
        zorder=3,
    )

    # Foreground principal branch trajectories (distinct linestyle + color)
    xs_stem = np.linspace(0.35, 1.55, 40)
    xs_arm = np.linspace(1.55, 3.95, 80)
    ax.plot(xs_stem, np.zeros_like(xs_stem), color=INK, lw=1.4, zorder=5)
    ax.plot(xs_arm, _branch_y(xs_arm), color=ERY, ls="-", lw=1.55, label="Erythroid", zorder=5)
    ax.plot(xs_arm, -_branch_y(xs_arm), color=MYE, ls="--", lw=1.55, label="Myeloid", zorder=5)
    ax.scatter([1.55], [0.0], s=26, facecolor="white", edgecolor=INK, linewidths=1.1, zorder=6)

    # Clean ink annotations with subtle white halo over velocity stream lines
    halo = {"facecolor": "white", "edgecolor": "none", "alpha": 0.80, "pad": 1.0}
    ax.text(0.10, 0.72, "Progenitor", fontsize=6.2, color=INK, fontweight="bold", bbox=halo, zorder=7)
    ax.annotate(
        r"$t^* = 0.44$",
        xy=(1.55, 0.0),
        xytext=(1.82, -0.02),
        fontsize=6.0,
        color=INK,
        va="center",
        ha="left",
        bbox=halo,
        zorder=7,
    )
    ax.text(3.98, 1.72, "Erythroid", fontsize=6.4, color=ERY, fontweight="bold", ha="right", bbox=halo, zorder=7)
    ax.text(3.98, -1.86, "Myeloid", fontsize=6.4, color=MYE, fontweight="bold", ha="right", bbox=halo, zorder=7)

    ax.set_xlim(-0.15, 4.35)
    ax.set_ylim(-2.25, 2.25)
    ax.set_xticks([0, 2, 4])
    ax.set_yticks([-2, 0, 2])
    ax.set_xlabel("Diffusion component 1")
    ax.set_ylabel("Diffusion component 2")


def _panel_cascade(ax, fig) -> None:
    """Panel B: Pseudotime-ordered transcription factor activation cascade."""
    genes = [
        "GATA2",
        "RUNX1",
        "MYB",
        "FLI1",
        "SPI1",
        "CEBPA",
        "IRF8",
        "GATA1",
        "KLF1",
        "HBB",
    ]
    t = np.linspace(0.0, 1.0, 120)
    peaks = [0.08, 0.16, 0.25, 0.34, 0.56, 0.66, 0.78, 0.58, 0.74, 0.90]
    widths = [0.16, 0.17, 0.18, 0.16, 0.19, 0.17, 0.17, 0.19, 0.18, 0.15]

    mat = np.zeros((len(genes), len(t)), dtype=float)
    for idx, (mu, sd) in enumerate(zip(peaks, widths, strict=True)):
        profile = 3.0 * np.exp(-0.5 * ((t - mu) / sd) ** 2)
        if idx >= 4:
            # Post-bifurcation genes remain off before commitment
            gate = 1.0 / (1.0 + np.exp(-(t - 0.38) / 0.055))
            profile = profile * gate
        mat[idx] = profile

    im = ax.imshow(
        mat,
        cmap="mintfig_navy",
        aspect="auto",
        extent=[0.0, 1.0, len(genes) - 0.5, -0.5],
        norm=Normalize(vmin=0.0, vmax=3.0),
    )

    # Crisp horizontal row separators + subtle branch group divider
    for r in range(len(genes) - 1):
        lw = 1.15 if r in (3, 6) else 0.55
        ax.axhline(r + 0.5, color="#FFFFFF", lw=lw, zorder=3)

    # Bifurcation pseudotime vertical rail
    ax.axvline(0.44, color="#FFFFFF", ls="--", lw=0.85, zorder=4)
    ax.axvline(0.44, color=INK, ls="--", lw=0.55, alpha=0.75, zorder=5)

    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_edgecolor("#D4DCE5")
        spine.set_linewidth(0.45)

    ax.set_yticks(range(len(genes)))
    ax.set_yticklabels(genes, fontstyle="italic")
    ax.tick_params(axis="y", length=0)
    ax.set_xticks([0.0, 0.25, 0.44, 0.75, 1.0])
    ax.set_xticklabels(["0.0", "0.25", r"$t^*$", "0.75", "1.0"])
    ax.set_xlabel(r"Pseudotime, $t$")
    ax.set_ylabel("Transcription factor")

    cbar = fig.colorbar(im, ax=ax, fraction=0.048, pad=0.035, aspect=22)
    cbar.set_ticks([0, 1, 2, 3])
    mint.style_colorbar(cbar, label=r"Expression ($z$)", tick_pt=6.0)


def _panel_crispri(ax) -> None:
    """Panel C: CRISPRi knockdown fate-bias log-odds forest plot."""
    mint.subtle_grid(ax, axis="x", color="#ECEFF4", lw=0.45)

    # (label, mean log-odds shift, half-95% CI, n_cells, group)
    entries = [
        ("sgGATA1", -1.88, 0.24, 412, "ery"),
        ("sgKLF1", -1.34, 0.21, 389, "ery"),
        ("sgTAL1", -0.86, 0.23, 354, "ery"),
        ("sgMYB", -0.42, 0.22, 401, "ery"),
        ("sgControl", 0.04, 0.16, 618, "ctrl"),
        ("sgCEBPA", 0.74, 0.22, 367, "mye"),
        ("sgIRF8", 1.18, 0.23, 342, "mye"),
        ("sgSPI1", 1.72, 0.25, 396, "mye"),
    ]

    ax.axvline(0.0, color=RULE, ls="--", lw=0.75, zorder=1)
    y_pos = np.arange(len(entries))

    style_map = {
        "ery": (ERY, "o"),
        "ctrl": (CTRL, "D"),
        "mye": (MYE, "s"),
    }

    for idx, (_name, est, ci, n_cells, grp) in enumerate(entries):
        col, mk = style_map[grp]
        ax.plot([est - ci, est + ci], [idx, idx], color=col, lw=1.25, solid_capstyle="round", zorder=3)
        ax.scatter(
            [est],
            [idx],
            s=22,
            marker=mk,
            facecolor="white",
            edgecolor=col,
            linewidths=1.05,
            zorder=4,
        )
        ax.text(2.42, idx, f"n={n_cells}", fontsize=6.0, color=MUTED, va="center", ha="left")

    # Subtle directional annotations at top (mathtext arrows avoid missing Helvetica glyphs)
    ax.text(-2.22, -0.78, r"$\leftarrow$ Myeloid bias", fontsize=6.0, color=ERY, ha="left", va="center")
    ax.text(2.22, -0.78, r"Erythroid bias $\rightarrow$", fontsize=6.0, color=MYE, ha="right", va="center")

    ax.set_yticks(y_pos)
    ax.set_yticklabels([e[0] for e in entries])
    ax.invert_yaxis()
    ax.set_xlim(-2.35, 3.05)
    ax.set_ylim(len(entries) - 0.4, -1.25)
    ax.set_xticks([-2, -1, 0, 1, 2])
    ax.set_xlabel(r"Erythroid fate shift, $\Delta\mathrm{logit}\,P$ (95% CI)")
    ax.set_ylabel("CRISPRi target")


def _panel_dynamics(ax, rng: np.random.Generator) -> None:
    """Panel D: Opposing GATA1 and SPI1 bifurcation dynamics across pseudotime."""
    mint.subtle_grid(ax, axis="y", color="#ECEFF4", lw=0.45)

    t = np.linspace(0.0, 1.0, 200)
    # Clean sigmoidal activation curves crossing at t* = 0.44
    gata1 = 0.25 + 2.85 / (1.0 + np.exp(-(t - 0.46) / 0.095))
    spi1 = 2.65 - 2.30 / (1.0 + np.exp(-(t - 0.41) / 0.105))
    ci_g = 0.16 + 0.08 * np.sin(np.pi * t)
    ci_s = 0.16 + 0.07 * np.sin(np.pi * t)

    # Faint raw single-cell observations behind GAM fits
    t_pts = rng.uniform(0.02, 0.98, size=180)
    g_pts = np.interp(t_pts, t, gata1) + rng.normal(0.0, 0.28, size=180)
    s_pts = np.interp(t_pts, t, spi1) + rng.normal(0.0, 0.26, size=180)
    ax.scatter(t_pts, np.clip(g_pts, 0.0, 3.65), s=4.0, color=ERY, alpha=0.16, linewidths=0, zorder=2)
    ax.scatter(t_pts, np.clip(s_pts, 0.0, 3.65), s=4.0, color=MYE, alpha=0.16, linewidths=0, zorder=2)

    ax.axvline(0.44, color=RULE, ls="--", lw=0.75, zorder=1)
    ax.text(0.46, 3.35, r"Commitment $t^* = 0.44$", fontsize=6.0, color=MUTED, va="top", ha="left")

    ax.fill_between(t, gata1 - ci_g, gata1 + ci_g, color=ERY, alpha=0.14, lw=0, zorder=3)
    ax.fill_between(t, spi1 - ci_s, spi1 + ci_s, color=MYE, alpha=0.14, lw=0, zorder=3)

    mark_idx = [0, 40, 80, 120, 160, 199]
    ax.plot(
        t,
        gata1,
        color=ERY,
        ls="-",
        lw=1.35,
        marker="o",
        markevery=mark_idx,
        ms=3.4,
        mfc="white",
        mew=0.9,
        label=r"$GATA1$",
        zorder=5,
    )
    ax.plot(
        t,
        spi1,
        color=MYE,
        ls="--",
        lw=1.35,
        marker="s",
        markevery=mark_idx,
        ms=3.2,
        mfc="white",
        mew=0.9,
        label=r"$SPI1$",
        zorder=5,
    )

    mint.direct_labels(ax, pad_pt=4.5, min_sep_pt=9.0, expand_xlim=0.22, fontsize=6.4)

    ax.set_xticks([0.0, 0.25, 0.5, 0.75, 1.0])
    ax.set_yticks([0, 1, 2, 3])
    ax.set_ylim(-0.05, 3.65)
    ax.set_xlabel(r"Pseudotime, $t$")
    ax.set_ylabel(r"Normalized expression ($\mathrm{log1p}$)")


def build(journal: str = "cell") -> mint.Plate:
    """Construct the four-panel Cell Press single-cell bifurcation plate."""
    rng = np.random.default_rng(77)
    plate = mint.Plate(
        journal=journal,
        width="double",
        height_mm=118.0,
        layout=(2, 2),
        width_ratios=[1.05, 1.12],
        height_ratios=[1.04, 1.0],
        gap_mm=(10.5, 9.5),
        palette="nature_muted",
    )
    plate.caption = CAPTION
    plate.set_takeaway(TAKEAWAY)
    for k, note in PANEL_NOTES.items():
        plate.note_panel(k, note)

    _panel_landscape(plate["A"], rng)
    _panel_cascade(plate["B"], plate.fig)
    _panel_crispri(plate["C"])
    _panel_dynamics(plate["D"], rng)

    plate.label_panels(dx_mm=-7.5, dy_mm=1.6)
    return plate


if __name__ == "__main__":
    p = build()
    res = p.bundle("gallery/output/cell_lineage_bifurcation")
    print(res.report.summary())
