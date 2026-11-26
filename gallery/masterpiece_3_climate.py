"""Masterpiece 3 — Planetary Climate Dynamics & Tipping-Point Cascades.

Science (AAAS) 3-column full-width plate (184.0 x 122.0 mm), Panels A-D:
  A: Global surface temperature anomaly (1850-2100) with IPCC AR6 scenarios
     and inset 1850-2025 Ed Hawkins warming-stripes strip.
  B: Zonal-altitude atmospheric warming cross-section (90S-90N, 1000-10 hPa)
     in mintfig_div showing stratospheric cooling, tropical hotspot, and Arctic
     amplification with tropopause contour and grayscale-safe ΔT callouts.
  C: Earth energy imbalance / cumulative ocean heat uptake (1970-2025) with
     89% ocean share callout.
  D: Climate tipping-point thresholds (Armstrong McKay et al. Science 2022)
     with Min-Max bars, hollow best-estimate markers, Paris 1.5-2.0 C corridor,
     and redundant color + shape timescale encoding.
"""

from __future__ import annotations

import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

import mintfig as mint

# Cohesive Earth-system editorial palette
CHARCOAL = "#2B3036"
NAVY = "#254F82"
AMBER = "#C98A2E"
CRIMSON = "#C83E2B"
MUTED_INK = "#4B5560"


def _build_panel_a(ax: plt.Axes, rng: np.random.Generator) -> None:
    """Panel A: 1850-2100 Global Temperature Anomaly + 1850-2025 Warming Stripes."""
    years_hist = np.arange(1850, 2026)
    n_hist = len(years_hist)

    # Calibrated historical trajectory relative to 1850-1900 baseline (C)
    t_norm = (years_hist - 1850) / 175.0
    trend = (
        -0.06 * np.exp(-((years_hist - 1905) / 22.0) ** 2)
        + 0.22 * np.exp(-((years_hist - 1943) / 14.0) ** 2)
        + 1.38 * (1.0 / (1.0 + np.exp(-(years_hist - 1998) / 19.0)) - 0.0004)
        - 0.14 * np.exp(-((years_hist - 1966) / 13.0) ** 2)
    )
    # Realistic AR(1) ENSO + volcanic dips (Krakatoa 1883, Agung 1963, Pinatubo 1991)
    ar1 = np.zeros(n_hist)
    eps = rng.normal(0.0, 0.075, size=n_hist)
    for i in range(1, n_hist):
        ar1[i] = 0.42 * ar1[i - 1] + eps[i]
    volc = (
        -0.16 * np.exp(-((years_hist - 1884) / 2.0) ** 2)
        - 0.13 * np.exp(-((years_hist - 1964) / 2.0) ** 2)
        - 0.17 * np.exp(-((years_hist - 1992) / 1.8) ** 2)
    )
    hist_t = trend + ar1 + volc
    # Normalize 1850-1900 mean to 0.0 C and anchor 2025 near +1.36 C
    hist_t = hist_t - hist_t[:51].mean()
    hist_t = hist_t + 0.14 * (t_norm**3)
    hist_end = float(hist_t[-1])

    obs_unc = 0.14 * np.exp(-(years_hist - 1850) / 65.0) + 0.05

    # IPCC AR6 scenarios (2025-2100) smoothly anchored at 2025
    years_proj = np.arange(2025, 2101)
    tau = (years_proj - 2025) / 75.0

    ssp585 = hist_end + 3.05 * (0.62 * tau + 0.38 * tau**1.85)
    ssp585_w = 0.06 + 0.80 * (tau**1.15)

    ssp245 = hist_end + 1.38 * (1.30 * tau - 0.30 * tau**2)
    ssp245_w = 0.06 + 0.50 * (tau**1.05)

    ssp126 = hist_end + 0.48 * np.sin(np.pi * 0.72 * tau) - 0.06 * tau**2
    ssp126_w = 0.06 + 0.36 * (tau**0.95)

    mint.pub.subtle_grid(ax, axis="y")

    # Preindustrial zero baseline & Paris thresholds (terminated cleanly at 2100)
    ax.plot([1850, 2100], [0.0, 0.0], color="#C5CDD6", lw=0.55, zorder=1)
    for thresh, txt in ((1.5, "1.5 °C"), (2.0, "2.0 °C")):
        ax.plot([1850, 2100], [thresh, thresh], color="#737E8A", lw=0.65, ls=":", zorder=1)
        ax.text(
            1853,
            thresh + 0.08,
            txt,
            fontsize=6.0,
            color=MUTED_INK,
            va="bottom",
            ha="left",
        )

    # 2025 Historical / Projection divider (stops neatly above warming stripes)
    ax.plot([2025, 2025], [-0.42, 5.25], color="#9BA5B0", lw=0.65, ls="--", zorder=1)
    ax.text(2019, 5.20, "Historical", fontsize=6.0, color=MUTED_INK, ha="right", va="top")
    ax.text(2031, 5.20, "IPCC AR6", fontsize=6.0, color=MUTED_INK, ha="left", va="top")

    # Plumes & scenario trajectories
    for y_med, y_hw, col, lbl in (
        (ssp585, ssp585_w, CRIMSON, "SSP5-8.5"),
        (ssp245, ssp245_w, AMBER, "SSP2-4.5"),
        (ssp126, ssp126_w, NAVY, "SSP1-2.6"),
    ):
        ax.fill_between(
            years_proj,
            y_med - y_hw,
            y_med + y_hw,
            color=col,
            alpha=0.17,
            linewidth=0.0,
            zorder=2,
        )
        ax.plot(years_proj, y_med, color=col, lw=1.35, label=lbl, zorder=4)

    # Historical observational band & series
    ax.fill_between(
        years_hist,
        hist_t - obs_unc,
        hist_t + obs_unc,
        color=CHARCOAL,
        alpha=0.15,
        linewidth=0.0,
        zorder=3,
    )
    ax.plot(years_hist, hist_t, color=CHARCOAL, lw=1.05, zorder=5)

    # Authentic Ed Hawkins warming-stripes inset strip along bottom band (1850-2025)
    stripe_y0, stripe_y1 = -1.12, -0.60
    ax.imshow(
        hist_t[np.newaxis, :],
        extent=(1850.0, 2025.0, stripe_y0, stripe_y1),
        aspect="auto",
        cmap="mintfig_div",
        vmin=-1.25,
        vmax=1.25,
        interpolation="nearest",
        zorder=3,
    )
    ax.add_patch(
        Rectangle(
            (1850.0, stripe_y0),
            175.0,
            stripe_y1 - stripe_y0,
            fill=False,
            edgecolor="#AEB7C2",
            linewidth=0.45,
            zorder=4,
        )
    )
    ax.text(
        2030,
        0.5 * (stripe_y0 + stripe_y1),
        "Warming stripes\n(1850–2025)",
        fontsize=6.0,
        color=MUTED_INK,
        va="center",
        ha="left",
        linespacing=1.15,
    )

    ax.set_xlim(1850, 2100)
    ax.set_ylim(-1.32, 5.45)
    ax.set_xticks([1850, 1900, 1950, 2000, 2050, 2100])
    ax.set_yticks([0, 1, 2, 3, 4, 5])
    ax.set_xlabel("Year")
    ax.set_ylabel("Global ΔT (°C vs. 1850–1900)")
    ax.set_title("Global surface warming & scenarios")

    # Direct labels placed neatly right of 2100 in open white space
    for txt in mint.pub.direct_labels(ax, pad_pt=4.5, min_sep_pt=8.5, fontsize=6.2):
        txt.set_fontweight("bold")


def _build_panel_b(ax: plt.Axes) -> None:
    """Panel B: Zonal-altitude atmospheric warming cross-section (90S-90N, 1000-10 hPa)."""
    lat = np.linspace(-90.0, 90.0, 181)
    p = np.geomspace(1000.0, 10.0, 120)
    lat_g, p_g = np.meshgrid(lat, p)
    ln_p = np.log(p_g)

    # Physical tropopause pressure: ~100 hPa in tropics, ~285 hPa at poles
    p_trop = 100.0 + 185.0 * (np.sin(np.deg2rad(lat)) ** 2)
    ln_p_trop = np.log(p_trop)[np.newaxis, :]

    # Smooth tropospheric vs stratospheric mask
    trop_frac = 1.0 / (1.0 + np.exp(-3.6 * (ln_p - ln_p_trop)))
    strat_frac = 1.0 - trop_frac

    # Tropospheric baseline + tropical upper-trop hotspot + Arctic surface amplification
    trop_base = 1.85 + 0.35 * np.cos(np.deg2rad(lat_g))
    tropical_hotspot = 2.15 * np.exp(
        -((lat_g / 28.0) ** 2) - ((ln_p - np.log(245.0)) / 0.56) ** 2
    )
    arctic_amp = 2.45 * np.exp(
        -(((lat_g - 84.0) / 26.0) ** 2) - ((ln_p - np.log(920.0)) / 0.42) ** 2
    )
    antarctic_amp = 0.75 * np.exp(
        -(((lat_g + 82.0) / 22.0) ** 2) - ((ln_p - np.log(880.0)) / 0.42) ** 2
    )

    # Stratospheric CO2 radiative cooling intensifying aloft
    strat_alt = np.clip((ln_p_trop - ln_p) / 2.2, 0.0, 1.35)
    strat_cool = -(1.45 + 2.45 * strat_alt + 0.45 * np.sin(np.deg2rad(lat_g)) ** 2)

    dt = trop_frac * (trop_base + tropical_hotspot + arctic_amp + antarctic_amp) + (
        strat_frac * strat_cool
    )

    levels = np.linspace(-4.5, 4.5, 19)
    cf = ax.contourf(lat_g, p_g, dt, levels=levels, cmap="mintfig_div", extend="both")

    # Crisp contour lines: 0 C dashed, +/-2 C solid
    ax.contour(
        lat_g,
        p_g,
        dt,
        levels=[0.0],
        colors=["#3A424C"],
        linewidths=0.65,
        linestyles="--",
    )
    ax.contour(
        lat_g,
        p_g,
        dt,
        levels=[-2.0, 2.0],
        colors=["#3A424C"],
        linewidths=0.45,
        linestyles="-",
        alpha=0.78,
    )

    # Tropopause boundary + clear white-haloed physical sign callouts (grayscale-proof!)
    ax.plot(lat, p_trop, color="#1A1D21", lw=1.0, ls=(0, (3.5, 2.0)), zorder=4)
    white_halo = [pe.withStroke(linewidth=2.3, foreground="white", alpha=0.90)]
    dark_halo = [pe.withStroke(linewidth=1.8, foreground="#162E4D", alpha=0.65)]

    ax.text(
        0.0,
        74.0,
        "Tropopause",
        fontsize=6.0,
        color="#1A1D21",
        ha="center",
        va="bottom",
        path_effects=white_halo,
        zorder=5,
    )
    ax.text(
        0.0,
        19.0,
        "−4 °C",
        fontsize=6.0,
        fontweight="bold",
        color="white",
        ha="center",
        va="center",
        path_effects=dark_halo,
        zorder=5,
    )
    ax.text(
        0.0,
        255.0,
        "+4 °C",
        fontsize=6.0,
        fontweight="bold",
        color="white",
        ha="center",
        va="center",
        path_effects=[pe.withStroke(linewidth=1.8, foreground="#7D1E15", alpha=0.65)],
        zorder=5,
    )

    ax.set_yscale("log")
    ax.set_ylim(1000.0, 10.0)
    ax.set_xlim(-90.0, 90.0)
    ax.set_yticks([1000, 500, 200, 100, 50, 10])
    ax.set_yticklabels(["1000", "500", "200", "100", "50", "10"])
    ax.minorticks_off()
    ax.set_xticks([-90, -45, 0, 45, 90])
    ax.set_xticklabels(["90°S", "45°S", "0°", "45°N", "90°N"])
    ax.set_xlabel("Latitude")
    ax.set_ylabel("Pressure (hPa)")
    ax.set_title("Zonal-altitude ΔT (SSP2-4.5)")

    # Crisp soft box border on all 4 sides (classic Science cross-section)
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(True)
        ax.spines[side].set_color("#AEB7C2" if side in ("top", "right") else "#2B3036")
        ax.spines[side].set_linewidth(0.5)

    cbar = ax.figure.colorbar(cf, ax=ax, pad=0.035, fraction=0.055, aspect=22)
    mint.pub.style_colorbar(cbar, label="ΔT (°C)")
    cbar.set_ticks([-4, -2, 0, 2, 4])


def _build_panel_c(ax: plt.Axes, rng: np.random.Generator) -> None:
    """Panel C: Cumulative Earth Energy Imbalance / Ocean Heat Uptake (1970-2025)."""
    years = np.arange(1970, 2026)
    tau = (years - 1970) / 55.0
    wobble = np.cumsum(rng.normal(0.0, 1.4, size=len(years)))
    wobble = wobble - np.linspace(wobble[0], wobble[-1], len(years))

    # Calibrated to GCOS / IPCC AR6 cumulative heat gain (~408 ZJ by 2025; 89% ocean)
    upper = np.clip(228.0 * (0.45 * tau + 0.55 * tau**1.75) + 0.6 * wobble, 0.0, None)
    mid = np.clip(105.0 * (0.35 * tau + 0.65 * tau**1.85) + 0.25 * wobble, 0.0, None)
    deep = np.clip(30.0 * (0.25 * tau + 0.75 * tau**1.9), 0.0, None)
    land_ice = np.clip(45.0 * (0.40 * tau + 0.60 * tau**1.7) + 0.15 * wobble, 0.0, None)

    upper[0] = mid[0] = deep[0] = land_ice[0] = 0.0

    # Harmonious high-luminance-separation fills (distinct in grayscale & CVD)
    colors = ["#1F4E79", "#4F86B5", "#8FB9D9", "#D98A4E"]
    labels = ["0–700 m", "700–2000 m", ">2000 m", "Land/ice/atm"]

    mint.pub.subtle_grid(ax, axis="y")

    ax.stackplot(
        years,
        upper,
        mid,
        deep,
        land_ice,
        colors=colors,
        labels=labels,
        edgecolor="white",
        linewidth=0.55,
        zorder=2,
    )

    ocean_top = float(upper[-1] + mid[-1] + deep[-1])
    total_top = float(ocean_top + land_ice[-1])
    ocean_pct = round(100.0 * ocean_top / total_top)

    # Crisp right-edge ocean-share bracket + high-contrast percentage callouts
    bx = 2027.4
    tick_w = 1.6
    ax.plot(
        [bx - tick_w, bx, bx, bx - tick_w],
        [4.0, 4.0, ocean_top - 2.0, ocean_top - 2.0],
        color="#1F4E79",
        lw=0.85,
        zorder=4,
    )
    ax.text(
        bx + 1.8,
        0.5 * ocean_top,
        f"{ocean_pct}%\nocean",
        fontsize=6.2,
        fontweight="bold",
        color="#1F4E79",
        va="center",
        ha="left",
        linespacing=1.12,
    )
    ax.text(
        bx + 1.8,
        ocean_top + 0.5 * float(land_ice[-1]),
        f"{100 - ocean_pct}%",
        fontsize=6.0,
        fontweight="bold",
        color="#7C4316",
        va="center",
        ha="left",
    )

    ax.set_xlim(1970, 2041)
    ax.set_ylim(0, 445)
    ax.set_xticks([1970, 1990, 2010, 2025])
    ax.set_yticks([0, 100, 200, 300, 400])
    ax.set_xlabel("Year")
    ax.set_ylabel("Cumulative heat gain (ZJ)")
    ax.set_title("Earth energy imbalance")
    ax.legend(
        loc="upper left",
        fontsize=6.0,
        handlelength=1.0,
        handletextpad=0.45,
        labelspacing=0.25,
        borderaxespad=0.3,
    )


def _build_panel_d(ax: plt.Axes) -> None:
    """Panel D: Climate Tipping-Point Thresholds (McKay et al. Science 2022)."""
    elements = [
        ("Tropical coral reefs", 1.0, 1.5, 2.0, "Decadal"),
        ("Boreal permafrost", 1.0, 1.5, 2.3, "Centennial"),
        ("Greenland ice sheet", 0.8, 1.5, 3.0, "Multi-centennial"),
        ("West Antarctic ice", 1.0, 1.5, 3.0, "Multi-centennial"),
        ("Amazon dieback", 2.0, 3.5, 6.0, "Centennial"),
        ("AMOC collapse", 1.4, 4.0, 8.0, "Decadal"),
    ]

    style_map = {
        "Decadal": (CRIMSON, "o"),
        "Centennial": (AMBER, "s"),
        "Multi-centennial": (NAVY, "D"),
    }

    mint.pub.subtle_grid(ax, axis="x")

    y_pos = np.arange(len(elements))
    y_bottom = len(elements) - 0.35
    corridor_top = -0.42

    # Paris 1.5-2.0 C shaded corridor stopping cleanly below the Paris header label
    ax.add_patch(
        Rectangle(
            (1.5, corridor_top),
            0.5,
            y_bottom - corridor_top,
            facecolor="#E7EDF5",
            edgecolor="none",
            alpha=0.95,
            zorder=0,
        )
    )
    ax.plot([1.5, 1.5], [corridor_top, y_bottom], color="#68737E", lw=0.65, ls=":", zorder=1)
    ax.plot([2.0, 2.0], [corridor_top, y_bottom], color="#68737E", lw=0.65, ls=":", zorder=1)
    ax.text(
        1.75,
        corridor_top - 0.12,
        "Paris 1.5–2 °C",
        fontsize=6.0,
        fontweight="bold",
        color="#374556",
        ha="center",
        va="bottom",
    )

    for y, (_name, lo, best, hi, tscale) in zip(y_pos, elements, strict=True):
        col, marker = style_map[tscale]
        ax.axhline(y, color="#F0F3F7", lw=0.45, zorder=0)
        ax.plot([lo, hi], [y, y], color=col, lw=4.8, alpha=0.26, solid_capstyle="round", zorder=2)
        ax.plot([lo, hi], [y, y], color=col, lw=1.25, solid_capstyle="round", zorder=3)
        ax.plot(
            best,
            y,
            marker=marker,
            markersize=5.6,
            markerfacecolor="white",
            markeredgecolor=col,
            markeredgewidth=1.45,
            linestyle="none",
            zorder=5,
        )

    ax.set_yticks(y_pos)
    ax.set_yticklabels([row[0] for row in elements])
    ax.invert_yaxis()
    ax.set_xlim(0.4, 8.4)
    ax.set_ylim(y_bottom, -1.05)
    ax.set_xticks([1, 2, 3, 4, 5, 6, 7, 8])
    ax.set_xlabel("Global warming threshold (°C vs. 1850–1900)")
    ax.set_title("Climate tipping-point thresholds & timescales")

    # Frameless editorial legend in open upper-right quadrant (redundant color + shape)
    handles = [
        Line2D(
            [0],
            [0],
            color=col,
            lw=1.25,
            marker=mk,
            markersize=5.0,
            markerfacecolor="white",
            markeredgecolor=col,
            markeredgewidth=1.35,
            label=lbl,
        )
        for lbl, (col, mk) in style_map.items()
    ]
    leg = ax.legend(
        handles=handles,
        title="Transition timescale",
        title_fontsize=6.0,
        fontsize=6.0,
        loc="upper right",
        frameon=False,
        handlelength=1.6,
        labelspacing=0.35,
        borderaxespad=0.4,
    )
    leg.get_title().set_fontweight("bold")
    leg.get_title().set_color("#2B3036")


def build() -> mint.Plate:
    """Construct Masterpiece 3 as a Science 3-column full-width Plate."""
    rng = np.random.default_rng(2025)
    plate = mint.Plate(
        journal="science",
        width="full",
        height_mm=122.0,
        layout=[["A", "A", "B"], ["C", "D", "D"]],
        width_ratios=[1.05, 0.72, 1.15],
        height_ratios=[1.05, 1.0],
        gap_mm=(10.0, 9.5),
        palette="nature_muted",
    )

    _build_panel_a(plate["A"], rng)
    _build_panel_b(plate["B"])
    _build_panel_c(plate["C"], rng)
    _build_panel_d(plate["D"])

    plate.label_panels()
    return plate


if __name__ == "__main__":
    p = build()
    res = p.bundle("gallery/output/masterpiece_3_climate", source_path=__file__)
    print(res.report.summary())
    plt.close(p.fig)
