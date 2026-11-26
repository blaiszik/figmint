"""Masterpiece 1 — Double-Pendulum Lyapunov Chaos Atlas (Nature 183 x 116 mm).

Computes authentic vectorized RK4 Hamiltonian double-pendulum dynamics:
- Panel a: 180 x 180 Finite-Time Lyapunov Exponent (FTLE) chaos fractal atlas
- Panel b: Phase-space portrait (theta_2, omega_2) of regular torus vs. chaotic sea
- Panel c: Semilog trajectory divergence |Delta theta(t)| with Lyapunov slope fit
- Panel d: Synchronized bifurcation time series showing the Lyapunov horizon t_lambda

Run via:
    MPLCONFIGDIR=/tmp/mpl-mintfig .venv/bin/mintfig run gallery/masterpiece_1_chaos.py \
        --journal nature --bundle gallery/output/masterpiece_1_chaos --json
"""

from __future__ import annotations

import numpy as np

import mintfig as mint

G = 9.81
TEAL = "#0B7A6E"
VERMILION = "#D1492F"
SLATE_DARK = "#25374D"
INK = "#1A1D21"


def _derivs(
    t1: np.ndarray,
    t2: np.ndarray,
    w1: np.ndarray,
    w2: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Exact equations of motion for equal-mass, unit-length double pendulum."""
    delta = t1 - t2
    sin_d = np.sin(delta)
    cos_d = np.cos(delta)
    denom = 3.0 - np.cos(2.0 * delta)

    dw1 = (
        -G * (3.0 * np.sin(t1) + np.sin(t1 - 2.0 * t2))
        - 2.0 * sin_d * (w2 * w2 + w1 * w1 * cos_d)
    ) / denom
    dw2 = (2.0 * sin_d * (2.0 * w1 * w1 + 2.0 * G * np.cos(t1) + w2 * w2 * cos_d)) / denom
    return w1, w2, dw1, dw2


def _rk4_step(
    t1: np.ndarray,
    t2: np.ndarray,
    w1: np.ndarray,
    w2: np.ndarray,
    dt: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Single vectorized fourth-order Runge-Kutta step."""
    k1 = _derivs(t1, t2, w1, w2)
    k2 = _derivs(
        t1 + 0.5 * dt * k1[0],
        t2 + 0.5 * dt * k1[1],
        w1 + 0.5 * dt * k1[2],
        w2 + 0.5 * dt * k1[3],
    )
    k3 = _derivs(
        t1 + 0.5 * dt * k2[0],
        t2 + 0.5 * dt * k2[1],
        w1 + 0.5 * dt * k2[2],
        w2 + 0.5 * dt * k2[3],
    )
    k4 = _derivs(
        t1 + dt * k3[0],
        t2 + dt * k3[1],
        w1 + dt * k3[2],
        w2 + dt * k3[3],
    )
    c = dt / 6.0
    return (
        t1 + c * (k1[0] + 2.0 * k2[0] + 2.0 * k3[0] + k4[0]),
        t2 + c * (k1[1] + 2.0 * k2[1] + 2.0 * k3[1] + k4[1]),
        w1 + c * (k1[2] + 2.0 * k2[2] + 2.0 * k3[2] + k4[2]),
        w2 + c * (k1[3] + 2.0 * k2[3] + 2.0 * k3[3] + k4[3]),
    )


def _compute_ftle_grid(
    n_grid: int = 160,
    total_time: float = 9.6,
    dt: float = 0.04,
    renorm_steps: int = 24,
    eps: float = 1e-5,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute Benettin-renormalized Finite-Time Lyapunov Exponent field on [-pi, pi]^2."""
    grid_1d = np.linspace(-np.pi, np.pi, n_grid)
    t1_0, t2_0 = np.meshgrid(grid_1d, grid_1d)

    t1 = t1_0.copy()
    t2 = t2_0.copy()
    w1 = np.zeros_like(t1)
    w2 = np.zeros_like(t2)

    # Perturbed partner offset along diagonal in angle space
    inv_sqrt2 = 1.0 / np.sqrt(2.0)
    pt1 = t1 + eps * inv_sqrt2
    pt2 = t2 + eps * inv_sqrt2
    pw1 = np.zeros_like(t1)
    pw2 = np.zeros_like(t2)

    n_steps = round(total_time / dt)
    log_sum = np.zeros_like(t1)

    for step in range(1, n_steps + 1):
        t1, t2, w1, w2 = _rk4_step(t1, t2, w1, w2, dt)
        pt1, pt2, pw1, pw2 = _rk4_step(pt1, pt2, pw1, pw2, dt)

        if step % renorm_steps == 0:
            dt1 = pt1 - t1
            dt2 = pt2 - t2
            dw1 = pw1 - w1
            dw2 = pw2 - w2
            dist = np.sqrt(dt1 * dt1 + dt2 * dt2 + dw1 * dw1 + dw2 * dw2)
            dist_safe = np.maximum(dist, 1e-15)
            log_sum += np.log(dist_safe / eps)
            scale = eps / dist_safe
            pt1 = t1 + dt1 * scale
            pt2 = t2 + dt2 * scale
            pw1 = w1 + dw1 * scale
            pw2 = w2 + dw2 * scale

    ftle = np.clip(log_sum / total_time, 0.0, None)
    return grid_1d, ftle


def _integrate_pair(
    theta1_0: float,
    theta2_0: float,
    total_time: float = 14.0,
    dt: float = 0.01,
    eps: float = 1e-5,
) -> dict[str, np.ndarray]:
    """Integrate a trajectory and its eps-perturbed twin with high-accuracy RK4."""
    n_steps = round(total_time / dt)
    times = np.linspace(0.0, total_time, n_steps + 1)

    t1 = np.array([theta1_0, theta1_0 + eps / np.sqrt(2.0)], dtype=np.float64)
    t2 = np.array([theta2_0, theta2_0 + eps / np.sqrt(2.0)], dtype=np.float64)
    w1 = np.zeros(2, dtype=np.float64)
    w2 = np.zeros(2, dtype=np.float64)

    hist_t1 = np.empty((n_steps + 1, 2), dtype=np.float64)
    hist_t2 = np.empty((n_steps + 1, 2), dtype=np.float64)
    hist_w2 = np.empty((n_steps + 1, 2), dtype=np.float64)

    hist_t1[0] = t1
    hist_t2[0] = t2
    hist_w2[0] = w2

    for i in range(1, n_steps + 1):
        t1, t2, w1, w2 = _rk4_step(t1, t2, w1, w2, dt)
        hist_t1[i] = t1
        hist_t2[i] = t2
        hist_w2[i] = w2

    d1 = np.arctan2(np.sin(hist_t1[:, 1] - hist_t1[:, 0]), np.cos(hist_t1[:, 1] - hist_t1[:, 0]))
    d2 = np.arctan2(np.sin(hist_t2[:, 1] - hist_t2[:, 0]), np.cos(hist_t2[:, 1] - hist_t2[:, 0]))
    sep = np.maximum(np.hypot(d1, d2), 1e-12)

    return {
        "t": times,
        "t1": hist_t1[:, 0],
        "t2": hist_t2[:, 0],
        "w2": hist_w2[:, 0],
        "t2_twin": hist_t2[:, 1],
        "w2_twin": hist_w2[:, 1],
        "sep": sep,
    }


def _wrap_with_breaks(theta: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Wrap angles to [-pi, pi] and insert NaNs across +/-pi jumps to avoid streak artifacts."""
    wrapped = (theta + np.pi) % (2.0 * np.pi) - np.pi
    jumps = np.abs(np.diff(wrapped)) > np.pi
    if not np.any(jumps):
        return wrapped, y
    jump_idx = np.flatnonzero(jumps) + 1
    return np.insert(wrapped, jump_idx, np.nan), np.insert(y, jump_idx, np.nan)


def build() -> mint.Plate:
    """Build the Nature 183 x 116 mm Double-Pendulum Lyapunov Chaos Atlas."""
    plate = mint.Plate(
        journal="nature",
        width="double",
        height_mm=116.0,
        layout=[["a", "b"], ["a", "c"], ["d", "d"]],
        width_ratios=[1.22, 1.0],
        height_ratios=[1.0, 1.0, 0.72],
        gap_mm=(9.0, 7.5),
        palette="nature_muted",
    )

    # Selected canonical initial conditions:
    # 1: regular quasi-periodic KAM island near low-energy core
    # 2: chaotic sea with clean exponential divergence and mid-window Lyapunov horizon (~8-9 s)
    pt_reg = (0.72, 0.58)
    pt_cha = (2.28, 1.92)

    _, ftle = _compute_ftle_grid(n_grid=180, total_time=9.6, dt=0.04, renorm_steps=24, eps=1e-5)
    reg_phase = _integrate_pair(*pt_reg, total_time=24.0, dt=0.01, eps=1e-5)
    cha_phase = _integrate_pair(*pt_cha, total_time=24.0, dt=0.01, eps=1e-5)
    reg_div = _integrate_pair(*pt_reg, total_time=14.0, dt=0.01, eps=1e-5)
    cha_div = _integrate_pair(*pt_cha, total_time=14.0, dt=0.01, eps=1e-5)

    # ------------------------------------------------------------------
    # Panel a (Hero): High-resolution FTLE Chaos Fractal Atlas
    # ------------------------------------------------------------------
    ax_a = plate["a"]
    vmax = float(np.percentile(ftle, 99.2))
    im = ax_a.imshow(
        ftle,
        origin="lower",
        extent=[-np.pi, np.pi, -np.pi, np.pi],
        cmap="magma",
        vmin=0.0,
        vmax=vmax,
        interpolation="bilinear",
        aspect="equal",
    )
    ax_a.set_anchor("W")
    for sp in ax_a.spines.values():
        sp.set_visible(True)
        sp.set_linewidth(0.5)
        sp.set_edgecolor("#2B3036")

    pi_ticks = [-np.pi, -0.5 * np.pi, 0.0, 0.5 * np.pi, np.pi]
    pi_labels = [r"$-\pi$", r"$-\pi/2$", "0", r"$\pi/2$", r"$\pi$"]
    ax_a.set_xticks(pi_ticks)
    ax_a.set_xticklabels(pi_labels)
    ax_a.set_yticks(pi_ticks)
    ax_a.set_yticklabels(pi_labels)
    ax_a.set_xlabel(r"Initial angle, $\theta_1$ (rad)")
    ax_a.set_ylabel(r"Initial angle, $\theta_2$ (rad)")

    # Crisp white-ringed markers + high-contrast white pill callouts (100% legible in grayscale)
    for num, (px, py), col, offset in [
        ("1", pt_reg, TEAL, (0.42, -0.45)),
        ("2", pt_cha, VERMILION, (-0.52, 0.45)),
    ]:
        ax_a.scatter(
            [px],
            [py],
            s=30,
            facecolor=col,
            edgecolor="white",
            linewidth=1.1,
            zorder=6,
        )
        ax_a.annotate(
            num,
            xy=(px, py),
            xytext=(px + offset[0], py + offset[1]),
            fontsize=6.2,
            fontweight="bold",
            color=INK,
            ha="center",
            va="center",
            zorder=7,
            bbox={
                "boxstyle": "circle,pad=0.22",
                "facecolor": "white",
                "edgecolor": col,
                "linewidth": 0.9,
            },
            arrowprops={"arrowstyle": "-", "color": "white", "lw": 0.85, "shrinkA": 3, "shrinkB": 3},
        )

    cbar = plate.fig.colorbar(im, ax=ax_a, fraction=0.044, pad=0.028, shrink=0.92)
    mint.pub.style_colorbar(cbar, label=r"FTLE, $\lambda$ ($\mathrm{s}^{-1}$)", tick_pt=5.5)

    # ------------------------------------------------------------------
    # Panel b: Phase-Space Portrait (theta_2, d theta_2 / dt)
    # ------------------------------------------------------------------
    ax_b = plate["b"]
    mint.pub.subtle_grid(ax_b, axis="both")

    t2_twin_w, w2_twin_w = _wrap_with_breaks(cha_phase["t2_twin"], cha_phase["w2_twin"])
    t2_cha_w, w2_cha_w = _wrap_with_breaks(cha_phase["t2"], cha_phase["w2"])
    t2_reg_w, w2_reg_w = _wrap_with_breaks(reg_phase["t2"], reg_phase["w2"])

    ax_b.plot(t2_twin_w, w2_twin_w, color="#9BA6B4", lw=0.45, alpha=0.48, zorder=2)
    ax_b.plot(t2_cha_w, w2_cha_w, color=VERMILION, lw=0.72, alpha=0.86, label="2  Chaotic", zorder=3)
    ax_b.plot(t2_reg_w, w2_reg_w, color=TEAL, lw=1.22, alpha=0.98, label="1  Regular", zorder=4)

    ax_b.set_xlim(-np.pi, np.pi)
    ax_b.set_ylim(-14.2, 14.2)
    ax_b.set_xticks([-np.pi, 0.0, np.pi])
    ax_b.set_xticklabels([r"$-\pi$", "0", r"$\pi$"])
    ax_b.set_yticks([-10, -5, 0, 5, 10])
    ax_b.set_xlabel(r"$\theta_2$ (rad)")
    ax_b.set_ylabel(r"$\dot{\theta}_2$ ($\mathrm{rad\,s^{-1}}$)")
    ax_b.legend(
        loc="upper right",
        frameon=True,
        facecolor="white",
        edgecolor="#DCE2EA",
        framealpha=0.96,
        fontsize=5.5,
        handlelength=1.4,
        borderpad=0.35,
        labelspacing=0.25,
    )

    # ------------------------------------------------------------------
    # Panel c: Log-Scale Trajectory Divergence |Delta theta(t)|
    # ------------------------------------------------------------------
    ax_c = plate["c"]
    mint.pub.subtle_grid(ax_c, axis="y")

    t_div = cha_div["t"]
    sep_cha = cha_div["sep"]
    sep_reg = reg_div["sep"]

    # Fit exponential Lyapunov growth region cleanly between 2e-5 and 0.45 rad
    sat_idx = int(np.argmax(sep_cha >= 0.45)) if np.any(sep_cha >= 0.45) else len(t_div) - 1
    fit_mask = (t_div >= 1.0) & (t_div <= t_div[sat_idx]) & (sep_cha > 2e-5)
    slope_lam, intercept = np.polyfit(t_div[fit_mask], np.log(sep_cha[fit_mask]), 1)
    t_fit = np.linspace(0.8, min(t_div[sat_idx] + 0.35, 13.5), 60)
    y_fit = np.exp(intercept + slope_lam * t_fit)

    # Subtle shaded saturation ceiling bounded strictly to [0, 14] s (clean margin for direct_labels)
    ax_c.fill_between([0.0, 14.0], 1.0, 12.0, color="#EEF2F6", linewidth=0.0, zorder=0)
    ax_c.plot([0.0, 14.0], [1.0, 1.0], color="#AEB7C4", ls=":", lw=0.55, zorder=1)
    ax_c.text(0.4, 3.2, "Saturation", fontsize=5.2, color="#4E5866", va="center", ha="left")

    ax_c.semilogy(t_div, sep_cha, color=VERMILION, lw=1.15, label="2  Chaotic", zorder=4)
    ax_c.semilogy(t_div, sep_reg, color=TEAL, lw=1.15, ls="-", label="1  Regular", zorder=4)
    ax_c.semilogy(t_fit, y_fit, color=SLATE_DARK, lw=0.80, ls="--", zorder=5)

    # Crisp slope callout placed neatly in open space below the rising exponential
    mid_t = float(0.50 * t_fit[0] + 0.50 * t_fit[-1])
    mid_y = float(np.exp(intercept + slope_lam * mid_t))
    ax_c.text(
        mid_t + 1.25,
        mid_y * 0.16,
        rf"$\lambda = {slope_lam:.2f}\;\mathrm{{s}}^{{-1}}$",
        fontsize=5.6,
        fontweight="bold",
        color=SLATE_DARK,
        ha="left",
        va="top",
    )

    ax_c.set_xlim(0.0, 14.0)
    ax_c.set_ylim(2e-6, 10.0)
    ax_c.set_xticks([0, 4, 8, 12])
    ax_c.set_yticks([1e-5, 1e-3, 1e-1, 1e1])
    ax_c.set_xlabel("Time (s)")
    ax_c.set_ylabel(r"$|\Delta\theta(t)|$ (rad)")
    mint.pub.direct_labels(ax_c, pad_pt=4.2, min_sep_pt=8.5, expand_xlim=0.32)
    ax_c.spines["bottom"].set_bounds(0.0, 14.0)

    # ------------------------------------------------------------------
    # Panel d (Full-Width Bottom Strip): Synchronized Bifurcation Series
    # ------------------------------------------------------------------
    ax_d = plate["d"]
    mint.pub.subtle_grid(ax_d, axis="y")

    # Compute exact Lyapunov horizon t_lambda where |Delta theta| crosses 0.25 rad
    hor_idx = int(np.argmax(sep_cha >= 0.25)) if np.any(sep_cha >= 0.25) else len(t_div) // 2
    t_horizon = float(t_div[hor_idx])

    theta_a, time_a = _wrap_with_breaks(cha_div["t2"], t_div)
    theta_b, time_b = _wrap_with_breaks(cha_div["t2_twin"], t_div)

    ax_d.axvspan(t_horizon - 0.30, t_horizon + 0.30, color="#F4E4DF", alpha=0.85, zorder=1)
    ax_d.axvline(t_horizon, color=SLATE_DARK, ls=":", lw=0.75, zorder=2)

    ax_d.plot(
        time_a,
        theta_a,
        color=VERMILION,
        lw=1.15,
        label=r"Trajectory 2 ($\delta_0 = 0$)",
        zorder=3,
    )
    ax_d.plot(
        time_b,
        theta_b,
        color=SLATE_DARK,
        lw=0.92,
        ls=(0, (3.2, 1.8)),
        label=r"Perturbed twin ($\delta_0 = 10^{-5}\,\mathrm{rad}$)",
        zorder=4,
    )

    # Place Lyapunov horizon callout and legend in dedicated curve-free top header band (> pi)
    ax_d.text(
        t_horizon + 0.36,
        3.95,
        rf"Lyapunov horizon $t_\lambda \approx {t_horizon:.1f}\;\mathrm{{s}}$",
        fontsize=5.8,
        fontweight="bold",
        color=INK,
        ha="left",
        va="center",
        zorder=5,
    )

    ax_d.set_xlim(0.0, 14.0)
    ax_d.set_ylim(-np.pi * 1.10, 4.55)
    ax_d.set_xticks([0, 2, 4, 6, 8, 10, 12, 14])
    ax_d.set_yticks([-np.pi, 0.0, np.pi])
    ax_d.set_yticklabels([r"$-\pi$", "0", r"$\pi$"])
    ax_d.set_xlabel("Time (s)")
    ax_d.set_ylabel(r"$\theta_2(t)$ (rad)")
    ax_d.legend(
        loc="upper left",
        ncol=2,
        frameon=False,
        fontsize=5.6,
        handlelength=1.8,
        columnspacing=1.2,
        borderaxespad=0.35,
    )

    plate.label_panels()
    return plate
