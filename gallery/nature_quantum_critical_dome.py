"""Nature-style plate: a superconducting dome at a pressure-tuned quantum critical point.

ALL DATA ARE SYNTHETIC. Every curve and marker is generated from the toy model
in this file (a charge-density-wave line that is suppressed at ``P_C``, a
superconducting dome centred on it, and a resistivity exponent that falls from
2 to 1 in a fan above it). Nothing here is a measurement of a real material;
the plate exists to show the house style on a familiar kind of figure.

Run through the figmint contract::

    figmint run gallery/nature_quantum_critical_dome.py --journal nature \
        --bundle gallery/output/nature_quantum_critical_dome --json
"""

from __future__ import annotations

import matplotlib as mpl
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.lines import Line2D
from matplotlib.ticker import NullFormatter

import figmint as fm

INK = "#1A1D21"
MUTED = "#5B6470"
RULE = "#C9D0D9"
TEAL = "#149B7E"  # charge-density-wave boundary
NAVY = "#12305C"  # superconducting dome outline

P_C = 22.0  # critical pressure (GPa)
P_MAX = 48.0

# Pressure is a magnitude: one hue, light to dark. Starts dark enough to hold a
# 0.9 pt line on white.
PRESSURE_CMAP = LinearSegmentedColormap.from_list(
    "pressure_blue", ["#A9C9EC", "#6FA3DC", "#3B7BC4", "#1F559C", "#12305C", "#0A1B38"]
)
PRESSURE_NORM = Normalize(0.0, P_MAX)

# Exponent map: pale where the metal is a Fermi liquid (n = 2), saturated amber
# in the strange-metal fan (n = 1). Reversed so the colourbar reads 1 -> 2.
STRANGE_CMAP = LinearSegmentedColormap.from_list(
    "strange_amber", ["#C9801C", "#E2A748", "#F1CD8C", "#F9EAD0", "#FBF8F2"]
)


def pressure_color(p: float) -> tuple[float, float, float, float]:
    return PRESSURE_CMAP(PRESSURE_NORM(p))


# ── Toy model ──────────────────────────────────────────────────────────────
def t_cdw(p: np.ndarray | float) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    return np.where(p < P_C, 125.0 * np.clip(1.0 - p / P_C, 0.0, None) ** 0.55, 0.0)


def t_c(p: np.ndarray | float) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    return np.clip(38.0 * (1.0 - ((p - 23.0) / 17.0) ** 2), 0.0, None)


def exponent_map(p: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Local resistivity exponent n(P, T): 1 inside a fan above P_C, 2 outside."""
    return 2.0 - np.exp(-(((p - P_C) / (2.2 + 0.105 * t)) ** 2))


def rho_norm(t: np.ndarray, p: float) -> np.ndarray:
    """Resistivity normalised to 300 K for pressure ``p``."""
    n = 2.0 - 0.95 * np.exp(-(((p - P_C) / 9.0) ** 2))
    rho0 = 0.07 + 0.11 * np.exp(-(((p - P_C) / 9.0) ** 2))
    rho = rho0 + (1.0 - rho0) * (t / 300.0) ** n
    tcdw = float(t_cdw(p))
    if tcdw > 0.0:
        gap = 0.5 * (1.0 - np.tanh((t - tcdw) / (0.035 * tcdw + 1.5)))
        rho = rho * (
            1.0 + 0.42 * (1.0 - p / P_C) * gap * np.exp(-(((tcdw - t) / (0.9 * tcdw)) ** 2))
        )
    tc = float(t_c(p))
    if tc > 0.0:
        rho = rho * 0.5 * (1.0 + np.tanh((t - tc) / (0.022 * tc + 0.35)))
    return rho


def panel_resistivity(ax: mpl.axes.Axes) -> None:
    t = np.linspace(1.5, 300.0, 1400)
    pressures = [0.0, 5.0, 10.0, 15.0, 19.0, 22.0, 26.0, 31.0, 37.0, 46.0]
    for p in pressures:
        ax.plot(t, rho_norm(t, p), color=pressure_color(p), lw=0.95)

    ax.set_xlim(0, 300)
    ax.set_ylim(0, 1.04)
    ax.set_xticks([0, 100, 200, 300])
    ax.set_yticks([0, 0.5, 1.0])
    ax.set_xlabel("Temperature (K)")
    ax.set_ylabel(r"$\mathit{\rho}\,/\,\mathit{\rho}_{300\,\mathrm{K}}$")

    # Mark the density-wave kink on the ambient-pressure curve.
    tk = float(t_cdw(0.0))
    ax.annotate(
        r"$\mathit{T}_{\mathrm{CDW}}$",
        xy=(tk, float(rho_norm(np.array([tk]), 0.0)[0])),
        xytext=(tk + 34, 0.30),
        fontsize=6.0,
        color=INK,
        ha="left",
        va="center",
        arrowprops={"arrowstyle": "-", "color": MUTED, "lw": 0.5, "shrinkA": 1, "shrinkB": 2},
    )

    # Low-temperature zoom: the superconducting transitions.
    inset = ax.inset_axes([0.175, 0.62, 0.29, 0.35])
    t_lo = np.linspace(1.5, 60.0, 900)
    for p in pressures:
        inset.plot(t_lo, rho_norm(t_lo, p), color=pressure_color(p), lw=0.9)
    inset.set_xlim(0, 60)
    inset.set_ylim(0, 0.42)
    inset.set_xticks([0, 30, 60])
    inset.set_yticks([0, 0.2, 0.4])
    inset.tick_params(labelsize=5.6, length=1.8, pad=1.5)
    for side in ("top", "right"):
        inset.spines[side].set_visible(False)
    inset.set_facecolor("white")
    inset.set_xlabel(r"$\mathit{T}$ (K)", fontsize=5.6, labelpad=0.5)

    # Pressure key: a slim colour ramp in the empty lower-right corner.
    cax = ax.inset_axes([0.60, 0.115, 0.34, 0.032])
    sm = mpl.cm.ScalarMappable(norm=PRESSURE_NORM, cmap=PRESSURE_CMAP)
    sm.set_array(np.array(pressures))
    cbar = ax.figure.colorbar(sm, cax=cax, orientation="horizontal")
    cbar.set_ticks([0, 16, 32, 48])
    cbar.outline.set_visible(False)
    cax.tick_params(labelsize=5.6, length=1.6, pad=1.5, width=0.4)
    cax.set_title("Pressure (GPa)", fontsize=5.8, pad=2.5, color=INK)


def panel_phase_diagram(ax: mpl.axes.Axes) -> None:
    p = np.linspace(0.0, P_MAX, 360)
    t = np.linspace(0.0, 150.0, 300)
    pp, tt = np.meshgrid(p, t)
    mesh = ax.imshow(
        exponent_map(pp, tt),
        extent=(0.0, P_MAX, 0.0, 150.0),
        origin="lower",
        aspect="auto",
        cmap=STRANGE_CMAP,
        vmin=1.0,
        vmax=2.0,
        interpolation="bilinear",
        rasterized=True,
        zorder=0,
    )

    # Charge-density-wave phase: tinted region with its boundary.
    p_cdw = np.linspace(0.0, P_C, 200)
    ax.fill_between(p_cdw, 0.0, t_cdw(p_cdw), color=TEAL, alpha=0.13, lw=0, zorder=1)
    ax.plot(p_cdw, t_cdw(p_cdw), color=TEAL, lw=1.0, zorder=2)

    # Superconducting dome: carved out in white so it reads against the fan.
    p_sc = np.linspace(6.0, 40.0, 300)
    ax.fill_between(p_sc, 0.0, t_c(p_sc), color="white", lw=0, zorder=3)
    ax.plot(p_sc, t_c(p_sc), color=NAVY, lw=1.0, zorder=4)

    rng = np.random.default_rng(7)
    p_rho = np.array([8.0, 10.0, 13.0, 15.0, 17.0, 19.0, 22.0, 24.0, 26.0, 29.0, 31.0, 34.0, 37.0])
    p_chi = np.array([11.0, 16.0, 20.5, 23.0, 27.5, 32.5, 36.0])
    p_kink = np.array([0.0, 3.0, 5.0, 8.0, 10.0, 13.0, 15.0, 17.0, 19.0])
    tc_rho = t_c(p_rho) + rng.normal(0.0, 0.7, p_rho.size)
    tc_chi = t_c(p_chi) - 1.4 + rng.normal(0.0, 0.6, p_chi.size)
    tk = t_cdw(p_kink) + rng.normal(0.0, 2.0, p_kink.size)

    ax.errorbar(p_kink, tk, yerr=3.5, fmt="none", ecolor=TEAL, elinewidth=0.5, capsize=0, zorder=5)
    ax.scatter(
        p_kink,
        tk,
        s=13,
        marker="D",
        facecolor="white",
        edgecolor=TEAL,
        linewidth=0.8,
        zorder=6,
        clip_on=False,
    )
    ax.errorbar(
        p_rho, tc_rho, yerr=1.6, fmt="none", ecolor=NAVY, elinewidth=0.5, capsize=0, zorder=5
    )
    ax.scatter(
        p_rho,
        tc_rho,
        s=15,
        marker="o",
        c=[pressure_color(v) for v in p_rho],
        edgecolor="white",
        linewidth=0.5,
        zorder=6,
    )
    ax.scatter(
        p_chi, tc_chi, s=13, marker="s", facecolor="white", edgecolor=NAVY, linewidth=0.8, zorder=6
    )

    ax.plot(
        [P_C, P_C], [float(t_c(P_C)) + 3.0, 150.0], color=INK, lw=0.5, ls=(0, (1, 2.5)), zorder=2
    )
    ax.text(
        P_C + 0.7,
        143.0,
        r"$\mathit{P}_{\mathrm{c}}$",
        fontsize=6.2,
        color=INK,
        ha="left",
        va="center",
    )

    ax.text(
        4.3, 44.0, "CDW", fontsize=6.6, fontweight="bold", color="#0C6A56", ha="center", va="center"
    )
    ax.text(23.0, 15.5, "SC", fontsize=6.6, fontweight="bold", color=NAVY, ha="center", va="center")
    ax.text(
        24.5,
        96.0,
        "Strange\nmetal",
        fontsize=6.4,
        color=INK,
        ha="center",
        va="center",
        linespacing=1.05,
    )
    ax.text(
        42.0,
        30.0,
        "Fermi\nliquid",
        fontsize=6.4,
        color=INK,
        ha="center",
        va="center",
        linespacing=1.05,
    )

    handles = [
        Line2D(
            [],
            [],
            marker="D",
            ls="none",
            ms=3.4,
            mfc="white",
            mec=TEAL,
            mew=0.8,
            label=r"$\mathit{T}_{\mathrm{CDW}}$, $\mathit{\rho}$ kink",
        ),
        Line2D(
            [],
            [],
            marker="o",
            ls="none",
            ms=3.8,
            mfc=pressure_color(26.0),
            mec="white",
            mew=0.5,
            label=r"$\mathit{T}_{\mathrm{c}}$, $\mathit{\rho} = 0$",
        ),
        Line2D(
            [],
            [],
            marker="s",
            ls="none",
            ms=3.4,
            mfc="white",
            mec=NAVY,
            mew=0.8,
            label=r"$\mathit{T}_{\mathrm{c}}$, $\mathit{\chi}$ onset",
        ),
    ]
    leg = ax.legend(
        handles=handles,
        loc="upper right",
        fontsize=5.8,
        frameon=True,
        borderpad=0.5,
        handletextpad=0.3,
        labelspacing=0.35,
        borderaxespad=0.6,
    )
    leg.get_frame().set(facecolor="white", edgecolor="none", alpha=0.92)

    ax.set_xlim(0, P_MAX)
    ax.set_ylim(0, 150)
    ax.set_xticks([0, 10, 20, 30, 40])
    ax.set_yticks([0, 50, 100, 150])
    ax.set_xlabel("Pressure (GPa)")
    ax.set_ylabel("Temperature (K)")

    cbar = ax.figure.colorbar(mesh, ax=ax, fraction=0.045, pad=0.025, aspect=22)
    fm.style_colorbar(cbar, label=r"Resistivity exponent, $\mathit{n}$")
    cbar.set_ticks([1.0, 1.5, 2.0])
    cbar.ax.invert_yaxis()


HIGHLIGHT = ((12.0, "o"), (22.0, "s"), (31.0, "^"))
# Horizontal nudge (K) and anchor for the onset labels in the susceptibility panel.
LABEL_SHIFT = {12.0: (1.6, "right"), 31.0: (1.0, "center"), 22.0: (-0.6, "left")}


def panel_upper_critical_field(ax: mpl.axes.Axes) -> None:
    rng = np.random.default_rng(11)
    for p, marker in HIGHLIGHT:
        tc = float(t_c(p))
        h0 = 0.69 * tc * (0.95 + 0.012 * tc)  # steeper slope near the critical point
        t_fit = np.linspace(0.0, tc, 200)
        h_fit = h0 * (1.0 - (t_fit / tc) ** 2) / (1.0 + (t_fit / tc) ** 2)
        t_dat = np.linspace(0.07 * tc, 0.97 * tc, 9)
        h_dat = h0 * (1.0 - (t_dat / tc) ** 2) / (1.0 + (t_dat / tc) ** 2)
        h_dat = h_dat * (1.0 + rng.normal(0.0, 0.025, t_dat.size))
        color = pressure_color(p)
        ax.plot(t_fit, h_fit, color=color, lw=0.9)
        ax.scatter(
            t_dat,
            h_dat,
            s=13,
            marker=marker,
            facecolor="white",
            edgecolor=color,
            linewidth=0.8,
            zorder=3,
        )
        ax.text(0.9, h0 + 1.0, f"{p:.0f} GPa", fontsize=5.8, color=INK, ha="left", va="bottom")

    ax.set_xlim(0, 42)
    ax.set_ylim(0, 44)
    ax.set_xticks([0, 10, 20, 30, 40])
    ax.set_yticks([0, 20, 40])
    ax.set_xlabel("Temperature (K)")
    ax.set_ylabel(r"$\mathit{\mu}_0 \mathit{H}_{\mathrm{c2}}$ (T)")


def panel_susceptibility(ax: mpl.axes.Axes) -> None:
    t = np.linspace(2.0, 50.0, 500)
    for p, marker in HIGHLIGHT:
        tc = float(t_c(p))
        color = pressure_color(p)
        zfc = -0.5 * (1.0 - np.tanh((t - 0.93 * tc) / (0.035 * tc + 0.5)))
        fc = 0.32 * zfc
        ax.plot(t, fc, color=color, lw=0.7, ls=(0, (3, 1.6)))
        ax.plot(t, zfc, color=color, lw=0.95)
        t_mark = np.linspace(4.0, 48.0, 12)
        z_mark = -0.5 * (1.0 - np.tanh((t_mark - 0.93 * tc) / (0.035 * tc + 0.5)))
        ax.scatter(
            t_mark,
            z_mark,
            s=11,
            marker=marker,
            facecolor="white",
            edgecolor=color,
            linewidth=0.8,
            zorder=3,
        )

        ax.text(
            0.93 * tc + LABEL_SHIFT[p][0],
            0.045,
            f"{p:.0f} GPa",
            fontsize=5.8,
            color=INK,
            ha=LABEL_SHIFT[p][1],
            va="bottom",
        )

    ax.axhline(0.0, color=RULE, lw=0.5, zorder=0)
    ax.text(3.0, -0.93, "ZFC", fontsize=5.8, color=INK, ha="left", va="center")
    ax.text(3.0, -0.25, "FC", fontsize=5.8, color=INK, ha="left", va="center")
    ax.set_xlim(0, 50)
    ax.set_ylim(-1.08, 0.17)
    ax.set_xticks([0, 10, 20, 30, 40, 50])
    ax.set_yticks([-1.0, -0.5, 0.0])
    ax.set_xlabel("Temperature (K)")
    ax.set_ylabel(r"$4\pi\mathit{\chi}$")


def panel_mass_divergence(ax: mpl.axes.Axes) -> None:
    rng = np.random.default_rng(3)

    def a_model(q: np.ndarray) -> np.ndarray:
        return 0.0021 * (np.abs(q - P_C) / P_C) ** -1.0 + 0.0012

    p_dat = np.array(
        [2.0, 5.0, 8.0, 11.0, 14.0, 16.5, 18.5, 26.0, 28.0, 30.5, 34.0, 37.0, 40.0, 43.0, 46.0]
    )
    a_dat = a_model(p_dat) * np.exp(rng.normal(0.0, 0.07, p_dat.size))

    ax.axvline(P_C, color=INK, lw=0.5, ls=(0, (1, 2.5)))
    ax.text(
        P_C + 1.0,
        0.068,
        r"$\mathit{P}_{\mathrm{c}}$",
        fontsize=6.2,
        color=INK,
        ha="left",
        va="center",
    )
    for lo, hi in ((0.0, 20.4), (23.6, P_MAX)):
        p_fit = np.linspace(lo, hi, 200)
        ax.plot(p_fit, a_model(p_fit), color=MUTED, lw=0.8)
    ax.errorbar(
        p_dat, a_dat, yerr=0.11 * a_dat, fmt="none", ecolor=MUTED, elinewidth=0.5, capsize=0
    )
    ax.scatter(
        p_dat,
        a_dat,
        s=15,
        c=[pressure_color(v) for v in p_dat],
        edgecolor="white",
        linewidth=0.5,
        zorder=3,
    )
    ax.text(
        30.5,
        0.021,
        r"$\mathit{A} \propto |\mathit{P} - \mathit{P}_{\mathrm{c}}|^{-1}$",
        fontsize=5.9,
        color=INK,
        ha="left",
        va="center",
    )

    ax.set_yscale("log")
    ax.set_xlim(0, P_MAX)
    ax.set_ylim(1e-3, 1e-1)
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_xticks([0, 10, 20, 30, 40])
    ax.set_xlabel("Pressure (GPa)")
    ax.set_ylabel(r"$\mathit{A}$ ($\mu\Omega$ cm K$^{-2}$)")


CAPTION = (
    "Superconductivity at a pressure-tuned charge-density-wave quantum critical point "
    "(synthetic data from a toy model, for illustration only). "
    "a, Resistivity normalised to 300 K at ten pressures; the inset shows the superconducting "
    "transitions. b, Temperature-pressure phase diagram; colour is the local resistivity "
    "exponent n. c, Upper critical field at three pressures with fits. d, Zero-field-cooled "
    "(solid) and field-cooled (dashed) susceptibility. e, Fermi-liquid coefficient A, which "
    "diverges on approaching the critical pressure."
)


def build(journal: str = "nature") -> fm.Plate:
    plate = fm.Plate(
        journal=journal,
        width="double",
        height_mm=126.0,
        # a sits exactly above c, and b above d + e, so panel edges share rails.
        layout=[
            ["a", "a", "b", "b", "b", "b"],
            ["c", "c", "d", "d", "e", "e"],
        ],
        height_ratios=[1.28, 1.0],
        gap_mm=5.0,
    )
    panel_resistivity(plate["a"])
    panel_phase_diagram(plate["b"])
    panel_upper_critical_field(plate["c"])
    panel_susceptibility(plate["d"])
    panel_mass_divergence(plate["e"])
    plate.label_panels()
    return plate


if __name__ == "__main__":
    build().bundle(
        "gallery/output/nature_quantum_critical_dome",
        source_path=__file__,
        caption=CAPTION,
        label="fig:qcp-dome",
    )
