"""Science-style plate: the transmission spectrum of a warm giant exoplanet.

ALL DATA ARE SYNTHETIC. The light curves, spectrum, posteriors and temperature
profile are generated from the toy model in this file (a limb-darkened transit
plus Gaussian absorption bands). No telescope, instrument or planet is
represented; the plate exists to show the house style on a familiar kind of
figure.

Run through the figmint contract::

    figmint run gallery/science_exoplanet_atmosphere.py --journal science \
        --bundle gallery/output/science_exoplanet_atmosphere --json
"""

from __future__ import annotations

import matplotlib as mpl
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, LogNorm
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator, NullFormatter

import figmint as fm

INK = "#1A1D21"
MUTED = "#5B6470"
FAINT = "#B9C0CA"
RULE = "#D5DAE1"

# Molecule colours, checked for colour-vision separation as a set.
MOLECULE = {
    "H2O": "#2A6DB8",
    "CO2": "#D2492A",
    "CO": "#149B7E",
    "SO2": "#B97A00",
    "CH4": "#8A929D",  # not detected: neutral
}
MOLECULE_LABEL = {
    "H2O": r"H$_2$O",
    "CO2": r"CO$_2$",
    "CO": "CO",
    "SO2": r"SO$_2$",
    "CH4": r"CH$_4$",
}

# Wavelength is a magnitude: one hue, light to dark.
WAVE_CMAP = LinearSegmentedColormap.from_list(
    "wave_violet", ["#B9B2E6", "#8E82D6", "#6656BE", "#45379A", "#2A1F6B"]
)
WAVE_NORM = LogNorm(0.6, 5.2)

BASE_PPM = 21200.0
# (centre in micrometres, width in ln-wavelength, amplitude in ppm, molecule)
BANDS = (
    (0.95, 0.030, 90.0, "H2O"),
    (1.15, 0.040, 150.0, "H2O"),
    (1.40, 0.050, 270.0, "H2O"),
    (1.90, 0.050, 300.0, "H2O"),
    (2.70, 0.075, 390.0, "H2O"),
    (4.05, 0.018, 170.0, "SO2"),
    (4.33, 0.034, 540.0, "CO2"),
    (4.72, 0.045, 150.0, "CO"),
)


# ── Toy model ──────────────────────────────────────────────────────────────
def depth_ppm(wave: np.ndarray) -> np.ndarray:
    """Transit depth versus wavelength: haze slope plus Gaussian bands."""
    out = BASE_PPM + 260.0 * (wave / 0.6) ** -3.0
    for centre, width, amp, _ in BANDS:
        out = out + amp * np.exp(-0.5 * ((np.log(wave) - np.log(centre)) / width) ** 2)
    return out


def transit_flux(t_hours: np.ndarray, depth: float, u1: float = 0.32, u2: float = 0.22) -> np.ndarray:
    """Quadratic limb-darkened transit by direct integration over the planet disc."""
    k = np.sqrt(depth)
    a_over_rs, impact, period_h = 9.2, 0.35, 96.0
    x = a_over_rs * np.sin(2.0 * np.pi * t_hours / period_h)
    z = np.hypot(x, impact)

    rr = (np.arange(14) + 0.5) / 14.0 * k
    th = (np.arange(40) + 0.5) / 40.0 * 2.0 * np.pi
    r_grid, th_grid = np.meshgrid(rr, th)
    d_area = r_grid * (k / 14.0) * (2.0 * np.pi / 40.0)
    px = r_grid * np.cos(th_grid)
    py = r_grid * np.sin(th_grid)

    star = np.pi * (1.0 - u1 / 3.0 - u2 / 6.0)
    flux = np.ones_like(t_hours, dtype=float)
    for i, zi in enumerate(z):
        if zi > 1.0 + k:
            continue
        r_star = np.hypot(px + zi, py)
        inside = r_star < 1.0
        mu = np.sqrt(np.clip(1.0 - r_star**2, 0.0, None))
        intensity = 1.0 - u1 * (1.0 - mu) - u2 * (1.0 - mu) ** 2
        flux[i] = 1.0 - float(np.sum(intensity * d_area * inside)) / star
    return flux


def panel_white_light_curve(ax: mpl.axes.Axes, ax_res: mpl.axes.Axes) -> None:
    rng = np.random.default_rng(21)
    depth = float(np.mean(depth_ppm(np.geomspace(0.6, 5.2, 60)))) * 1e-6
    t = np.linspace(-3.4, 3.4, 520)
    model = transit_flux(t, depth)
    flux = model + rng.normal(0.0, 3.4e-4, t.size)

    edges = np.linspace(-3.4, 3.4, 53)
    centres = 0.5 * (edges[:-1] + edges[1:])
    idx = np.digitize(t, edges) - 1
    binned = np.array([flux[idx == i].mean() for i in range(centres.size)])
    binned_model = np.array([model[idx == i].mean() for i in range(centres.size)])

    ax.scatter(t, flux, s=2.2, color=FAINT, linewidth=0, zorder=1, rasterized=True)
    ax.plot(t, model, color=INK, lw=0.9, zorder=2)
    ax.scatter(centres, binned, s=9, facecolor="white", edgecolor=INK, linewidth=0.6, zorder=3)

    ax.set_xlim(-3.4, 3.4)
    ax.set_ylim(0.9738, 1.0030)
    ax.set_yticks([0.98, 0.99, 1.00])
    ax.set_ylabel("Relative flux")
    ax.tick_params(labelbottom=False)

    # Depth bracket, in the quiet space before ingress.
    y_lo = float(model.min())
    ax.annotate(
        "",
        xy=(-2.75, y_lo),
        xytext=(-2.75, 1.0),
        arrowprops={"arrowstyle": "<->", "color": MUTED, "lw": 0.5, "shrinkA": 0, "shrinkB": 0},
    )
    ax.text(
        -2.55,
        0.5 * (1.0 + y_lo),
        f"Depth {depth * 100:.2f}%",
        fontsize=6.3,
        color=INK,
        ha="left",
        va="center",
        rotation=90,
    )

    resid = (flux - model) * 1e6
    resid_binned = (binned - binned_model) * 1e6
    ax_res.axhline(0.0, color=INK, lw=0.5, zorder=2)
    ax_res.scatter(t, resid, s=2.2, color=FAINT, linewidth=0, zorder=1, rasterized=True)
    ax_res.scatter(centres, resid_binned, s=9, facecolor="white", edgecolor=INK, linewidth=0.6, zorder=3)
    ax_res.set_xlim(-3.4, 3.4)
    ax_res.set_ylim(-1150, 1150)
    ax_res.set_yticks([-800, 0, 800])
    ax_res.set_xticks([-3, -2, -1, 0, 1, 2, 3])
    ax_res.set_xlabel("Time from mid-transit (hours)")
    ax_res.set_ylabel("O − C (ppm)")


def panel_spectrum(ax: mpl.axes.Axes) -> None:
    rng = np.random.default_rng(5)
    wave = np.geomspace(0.6, 5.2, 900)
    model = depth_ppm(wave)

    band = 55.0 + 25.0 * (wave / 5.2) ** 2
    ax.fill_between(wave, model - 2 * band, model + 2 * band, color="#E9ECF0", lw=0, zorder=1)
    ax.fill_between(wave, model - band, model + band, color="#CCD2DA", lw=0, zorder=2)
    ax.plot(wave, model, color=INK, lw=0.9, zorder=4)

    w_short = np.geomspace(0.63, 2.78, 44)
    w_long = np.geomspace(2.88, 5.12, 40)
    for w, marker, err_scale in ((w_short, "o", 1.0), (w_long, "s", 1.35)):
        err = err_scale * (50.0 + 28.0 * rng.random(w.size))
        obs = depth_ppm(w) + rng.normal(0.0, 1.0, w.size) * err * 0.9
        ax.errorbar(w, obs, yerr=err, fmt="none", ecolor=MUTED, elinewidth=0.45, capsize=0, zorder=5)
        ax.scatter(w, obs, s=9, marker=marker, facecolor="white", edgecolor=INK, linewidth=0.6, zorder=6)

    ax.axhline(BASE_PPM, color=MUTED, lw=0.5, ls=(0, (4, 2.5)), zorder=3)
    ax.text(0.605, BASE_PPM - 20, "Flat spectrum", fontsize=6.0, color=MUTED, ha="left", va="top")

    # Absorber key: a coloured bar over each band, named once per molecule.
    y_bar = 22070.0
    labelled: set[str] = set()
    label_at = {"H2O": 1.90, "SO2": 4.05, "CO2": 4.33, "CO": 4.72}
    label_dx = {"H2O": 1.0, "SO2": 0.955, "CO2": 1.0, "CO": 1.035}
    for centre, width, _, mol in BANDS:
        lo, hi = centre * np.exp(-1.25 * width), centre * np.exp(1.25 * width)
        ax.plot([lo, hi], [y_bar, y_bar], color=MOLECULE[mol], lw=2.0, solid_capstyle="butt", zorder=7)
        if mol not in labelled and np.isclose(centre, label_at[mol]):
            ax.text(
                centre * label_dx[mol],
                y_bar + 32,
                MOLECULE_LABEL[mol],
                fontsize=6.3,
                color=INK,
                ha="center",
                va="bottom",
            )
            labelled.add(mol)

    handles = [
        Line2D([], [], marker="o", ls="none", ms=3.2, mfc="white", mec=INK, mew=0.6, label="Short-wave channel"),
        Line2D([], [], marker="s", ls="none", ms=3.0, mfc="white", mec=INK, mew=0.6, label="Long-wave channel"),
        Line2D([], [], color=INK, lw=0.9, label="Best-fit model, 1σ and 2σ"),
    ]
    ax.legend(
        handles=handles,
        loc="upper left",
        ncols=3,
        fontsize=6.0,
        borderaxespad=0.0,
        borderpad=0.1,
        handlelength=1.3,
        handletextpad=0.4,
        columnspacing=1.6,
    )

    ax.set_xscale("log")
    ax.set_xlim(0.58, 5.35)
    ax.set_ylim(20980, 22300)
    ax.xaxis.set_major_locator(FixedLocator([0.6, 0.8, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0]))
    ax.xaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_yticks([21000, 21400, 21800, 22200])
    ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda v, _: f"{v / 1e4:.2f}"))
    ax.set_xlabel(r"Wavelength ($\mu$m)")
    ax.set_ylabel("Transit depth (%)")


def panel_spectroscopic_curves(ax: mpl.axes.Axes) -> None:
    rng = np.random.default_rng(13)
    channels = [0.8, 1.4, 2.0, 2.7, 3.5, 4.3, 4.9]
    t = np.linspace(-3.0, 3.0, 150)
    step = 0.027
    for i, w in enumerate(channels):
        offset = (len(channels) - 1 - i) * step
        color = WAVE_CMAP(WAVE_NORM(w))
        model = transit_flux(t, float(depth_ppm(np.array([w]))[0]) * 1e-6, u1=0.42 - 0.06 * i, u2=0.2)
        flux = model + rng.normal(0.0, 1.5e-3, t.size)
        ax.scatter(t, flux + offset, s=2.0, color=color, alpha=0.55, linewidth=0, zorder=1, rasterized=True)
        ax.plot(t, model + offset, color=color, lw=0.9, zorder=2)
        ax.text(3.2, 1.0 + offset, f"{w:.1f}", fontsize=6.0, color=INK, ha="left", va="center")
    ax.text(3.2, 1.0 + len(channels) * step - 0.008, r"$\mu$m", fontsize=6.0, color=MUTED, ha="left", va="center")

    # Flux scale bar instead of a y axis: the offsets make absolute values meaningless.
    ax.plot([-2.75, -2.75], [0.978, 0.988], color=INK, lw=0.8, solid_capstyle="butt")
    ax.text(-2.60, 0.983, "1%", fontsize=6.0, color=INK, ha="left", va="center")

    ax.set_xlim(-3.0, 3.9)
    ax.set_ylim(0.972, 1.0 + (len(channels) - 1) * step + 0.009)
    ax.set_xticks([-3, -2, -1, 0, 1, 2, 3])
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_bounds(-3.0, 3.0)
    ax.set_xlabel("Time from mid-transit (hours)")
    ax.set_ylabel("Relative flux + offset")


def panel_abundances(ax: mpl.axes.Axes) -> None:
    rng = np.random.default_rng(8)
    grid = np.linspace(-9.5, -1.0, 500)
    # (molecule, centre, sigma, skew) for log10 volume mixing ratio
    rows = (
        ("H2O", -3.15, 0.34, 0.0),
        ("CO2", -4.55, 0.40, 0.0),
        ("CO", -3.70, 0.75, 0.0),
        ("SO2", -5.60, 0.48, 0.0),
        ("CH4", -7.90, 0.95, 0.0),
    )
    height = 0.82
    for i, (mol, mu, sigma, _) in enumerate(rows):
        base = len(rows) - 1 - i
        samples = rng.normal(mu, sigma, 6000)
        if mol == "CH4":
            samples = samples[samples < -6.2]  # upper limit: only the low tail survives
        kde = np.exp(-0.5 * ((grid[:, None] - samples[None, ::12]) / 0.16) ** 2).sum(axis=1)
        kde = kde / kde.max() * height
        color = MOLECULE[mol]
        ax.fill_between(grid, base, base + kde, color=color, alpha=0.30, lw=0, zorder=2)
        ax.plot(grid, base + kde, color=color, lw=0.9, zorder=3)
        ax.plot([grid[0], grid[-1]], [base, base], color=RULE, lw=0.5, zorder=1)
        if mol == "CH4":
            limit = float(np.quantile(samples, 0.95))
            ax.annotate(
                "",
                xy=(limit - 1.25, base + 0.34),
                xytext=(limit, base + 0.34),
                arrowprops={"arrowstyle": "-|>", "color": INK, "lw": 0.6, "mutation_scale": 5},
            )
            ax.plot([limit, limit], [base + 0.16, base + 0.52], color=INK, lw=0.7, zorder=4)
            ax.text(limit + 0.22, base + 0.34, "95% upper limit", fontsize=6.0, color=INK, ha="left", va="center")
        else:
            lo, med, hi = np.quantile(samples, [0.16, 0.5, 0.84])
            ax.plot([lo, hi], [base + 0.10, base + 0.10], color=INK, lw=0.8, zorder=4, solid_capstyle="butt")
            ax.scatter([med], [base + 0.10], s=9, facecolor="white", edgecolor=INK, linewidth=0.6, zorder=5)

    ax.set_xlim(-9.5, -1.0)
    ax.set_ylim(-0.12, len(rows) - 0.05)
    ax.set_xticks([-9, -7, -5, -3, -1])
    ax.set_yticks([len(rows) - 1 - i + 0.10 for i in range(len(rows))])
    ax.set_yticklabels([MOLECULE_LABEL[r[0]] for r in rows])
    ax.tick_params(axis="y", length=0, pad=3)
    ax.spines["left"].set_visible(False)
    ax.set_xlabel(r"log$_{10}$ volume mixing ratio")


def panel_temperature_profile(ax: mpl.axes.Axes) -> None:
    log_p = np.linspace(-6.0, 2.0, 300)
    temp = 930.0 + 520.0 * 0.5 * (1.0 + np.tanh((log_p + 1.2) / 1.15))
    sigma = 42.0 + 30.0 * np.sqrt((log_p + 2.2) ** 2 + 0.6)
    pressure = 10.0**log_p

    ax.axhspan(1e-4, 1e-1, color="#F1F3F6", lw=0, zorder=0)
    ax.text(1810, 3.2e-3, "Probed in\ntransmission", fontsize=6.0, color=MUTED, ha="right", va="center", linespacing=1.05)
    ax.fill_betweenx(pressure, temp - 2 * sigma, temp + 2 * sigma, color="#E1E5EA", lw=0, zorder=1)
    ax.fill_betweenx(pressure, temp - sigma, temp + sigma, color="#BFC6D0", lw=0, zorder=2)
    ax.plot(temp, pressure, color=INK, lw=0.9, zorder=3)

    ax.set_yscale("log")
    ax.set_ylim(1e2, 1e-6)
    ax.set_xlim(520, 1850)
    ax.set_xticks([800, 1200, 1600])
    ax.yaxis.set_major_locator(FixedLocator([1e2, 1e0, 1e-2, 1e-4, 1e-6]))
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_xlabel("Temperature (K)")
    ax.set_ylabel("Pressure (bar)")


CAPTION = (
    "Transmission spectrum of a warm giant exoplanet (synthetic data from a toy model, for "
    "illustration only). (A) White-light transit, with the best-fit model and binned points; "
    "residuals below. (B) Transit depth against wavelength from two detector channels, with the "
    "best-fit model and its 1σ and 2σ intervals; coloured bars mark absorption bands and the dashed line is a flat spectrum (no atmosphere). "
    "(C) Spectroscopic light curves, offset for clarity and labelled by wavelength. "
    "(D) Retrieved abundances; bars show the median and 68% interval. (E) Retrieved "
    "temperature-pressure profile with 1σ and 2σ intervals."
)


def build(journal: str = "science") -> fm.Plate:
    plate = fm.Plate(
        journal=journal,
        width="full",
        height_mm=122.0,
        layout=[
            ["A", "A", "B", "B", "B", "B"],
            ["R", "R", "B", "B", "B", "B"],
            ["C", "C", "D", "D", "E", "E"],
        ],
        height_ratios=[2.05, 0.85, 3.0],
        gap_mm=5.0,
    )
    plate["R"].sharex(plate["A"])
    panel_white_light_curve(plate["A"], plate["R"])
    panel_spectrum(plate["B"])
    panel_spectroscopic_curves(plate["C"])
    panel_abundances(plate["D"])
    panel_temperature_profile(plate["E"])
    plate.label_panels(labels={"R": ""})
    return plate


if __name__ == "__main__":
    build().bundle(
        "gallery/output/science_exoplanet_atmosphere",
        source_path=__file__,
        caption=CAPTION,
        label="fig:transmission-spectrum",
    )
