"""Dedicated gallery examples covering each primary ``fm.explain`` form (all data synthetic).

Generates clean reference figures showcasing the core forms and newer capabilities
(named CIs with ``n=`` and ``baseline=``, ISO-date trends with events and gaps,
log-log scaling, ``points_label=``, paired changes, log distributions, grouped and
log-log ``relate``, ``share``, and ``matrix`` with missing cells). Writes PNGs and
reproducible JSON specs to ``gallery/output/explain_forms/``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

import figmint as fm

SOURCE = "synthetic example data"


def compare_intervals() -> fm.Explanation:
    """fm.compare: signed effects with 95% CIs, sample sizes, baseline, and zero reference."""
    return fm.explain(
        "High-dose therapy cuts HbA1c by 1.4 points, 1.6 points below placebo",
        fm.compare(
            {
                "High dose": -1.4,
                "Standard dose": -0.7,
                "Low dose": -0.3,
                "Diet only": -0.1,
                "Placebo": 0.2,
            },
            error={
                "High dose": (-1.7, -1.1),
                "Standard dose": (-1.0, -0.4),
                "Low dose": (-0.6, 0.0),
                "Diet only": (-0.4, 0.2),
                "Placebo": (-0.1, 0.5),
            },
            error_label="95% CI",
            n={
                "High dose": 62,
                "Standard dose": 60,
                "Low dose": 58,
                "Diet only": 55,
                "Placebo": 61,
            },
            reference=(0, "no change"),
            baseline="Placebo",
            highlight="High dose",
            sort="asc",
            label="Change in HbA1c at 24 weeks",
            unit="%",
            fmt="+.1f",
            title="Both active doses stay well below zero",
        ),
        subtitle="24-week randomised cohort; intervals are 95% confidence intervals",
        source=SOURCE,
    )


def trend_dates_events() -> fm.Explanation:
    """fm.trend: ISO dates, event marker, baseline control, and a missing-data gap."""
    dates = [
        "2026-01-04",
        "2026-01-11",
        "2026-01-18",
        "2026-01-25",
        "2026-02-01",
        "2026-02-08",
        "2026-02-15",
        "2026-02-22",
    ]
    return fm.explain(
        "The insulation retrofit cut Lab annex daily power use by 28%; the Gym stayed flat",
        fm.trend(
            dates,
            {
                "Lab annex": [418, 425, 412, None, 298, 304, 295, 301],
                "Library": [360, 355, 362, 358, 296, 291, 298, 294],
                "Gym (control)": [285, 290, 282, 288, 284, 279, 286, 281],
            },
            baseline="Gym (control)",
            highlight=["Lab annex", "Library"],
            events={"2026-01-25": "retrofit"},
            label="Daily electricity use",
            unit="kWh",
            x_label="Week",
            title="Both retrofitted buildings dropped immediately after Jan 25",
        ),
        note="Lab annex meter was offline during the Jan 25 switchover week.",
        source=SOURCE,
    )


def trend_log_log() -> fm.Explanation:
    """fm.trend: log-log scaling curves with automatic power-law exponent facts."""
    rng = np.random.default_rng(19)
    compute = [1e18, 3e18, 1e19, 3e19, 1e20, 3e20, 1e21, 3e21, 1e22]
    arr = np.array(compute)
    curves = {
        "Sparse MoE": (28.0 * arr ** (-0.064) * np.exp(rng.normal(0, 0.004, arr.size)))
        .round(3)
        .tolist(),
        "Dense": (25.0 * arr ** (-0.050) * np.exp(rng.normal(0, 0.004, arr.size)))
        .round(3)
        .tolist(),
        "Recurrent": (18.0 * arr ** (-0.031) * np.exp(rng.normal(0, 0.004, arr.size)))
        .round(3)
        .tolist(),
    }
    return fm.explain(
        "Sparse MoE scales fastest: loss falls as compute^−0.064 vs −0.050 for dense",
        fm.trend(
            compute,
            curves,
            log=True,
            log_x=True,
            highlight="Sparse MoE",
            label="Validation loss",
            unit="nats",
            x_label="Training compute (FLOPs)",
            title="Power-law slopes stay constant across four decades of compute",
        ),
        source=SOURCE,
    )


def trend_points_tasks() -> fm.Explanation:
    """fm.trend: individual observations (points=) with custom points_label=."""
    rng = np.random.default_rng(23)
    stages = ["Baseline", "Pass 1", "Pass 2", "Pass 3"]
    pts = {
        "Core suite": [
            rng.normal(31, 6, 10).clip(16, 48).round(1).tolist(),
            rng.normal(20, 3.5, 10).clip(13, 28).round(1).tolist(),
            rng.normal(20, 3.2, 10).clip(13, 27).round(1).tolist(),
            rng.normal(19.5, 3.0, 10).clip(13, 26).round(1).tolist(),
        ],
        "Held-out suite": [
            [],
            [],
            rng.normal(21, 4.0, 6).clip(13, 29).round(1).tolist(),
            rng.normal(19.8, 3.5, 6).clip(14, 27).round(1).tolist(),
        ],
    }
    return fm.explain(
        "Three fix passes cut mean solve time by 39% (30.9 s to 18.8 s) on core and held-out tasks",
        fm.trend(
            stages,
            points=pts,
            points_label="tasks",
            highlight=["Core suite", "Held-out suite"],
            label="Time to clean figure",
            unit="s",
            title="Held-out tasks match the core suite once introduced in Pass 2",
        ),
        colors={"Core suite": "blue", "Held-out suite": "amber"},
        source=SOURCE,
    )


def distribution_log() -> fm.Explanation:
    """fm.distribution: raw observations on a log scale with baseline and no-change reference."""
    rng = np.random.default_rng(31)
    groups = {
        "p53 targets": rng.lognormal(np.log(2.5), 0.35, 10).round(2).tolist(),
        "Stress response": rng.lognormal(np.log(1.6), 0.30, 10).round(2).tolist(),
        "Housekeeping": rng.lognormal(np.log(1.0), 0.06, 10).round(2).tolist(),
        "Proliferation": rng.lognormal(np.log(0.55), 0.25, 10).round(2).tolist(),
    }
    return fm.explain(
        "Drug treatment activates p53 targets (median 2.75×) and halves proliferation genes",
        fm.distribution(
            groups,
            log=True,
            baseline="Housekeeping",
            highlight=["p53 targets", "Proliferation"],
            reference=(1.0, "no change"),
            label="Expression fold change",
            unit="×",
            title="Every p53 target rises while every proliferation gene falls",
        ),
        subtitle="Bulk RNA-seq, 24 h post-treatment; each dot is one gene",
        source=SOURCE,
    )


def relate_groups_fit() -> fm.Explanation:
    """fm.relate: grouped scatter with per-group linear fits and computed 95% slope CIs."""
    rng = np.random.default_rng(42)
    inv_sqrt_d, yield_mpa, alloy = [], [], []
    params = {
        "Cu–Zn": (95.0, 325.0, 14.0),
        "Al–Mg": (68.0, 185.0, 11.0),
        "Pure Cu": (42.0, 115.0, 9.0),
    }
    for name, (s0, ky, sd) in params.items():
        x = rng.uniform(0.12, 0.55, 12)
        y = s0 + ky * x + rng.normal(0, sd, 12)
        inv_sqrt_d.extend(x.round(3).tolist())
        yield_mpa.extend(y.round(1).tolist())
        alloy.extend([name] * 12)
    return fm.explain(
        "All three alloys follow Hall–Petch; Cu–Zn strengthens 2.3× faster than pure Cu",
        fm.relate(
            inv_sqrt_d,
            yield_mpa,
            groups=alloy,
            fit=True,
            highlight="Cu–Zn",
            x_label="d⁻½ (µm⁻½)",
            y_label="Yield strength (MPa)",
            unit="MPa",
            title="Grain refinement pays off steepest in Cu–Zn (r = 0.97)",
        ),
        source=SOURCE,
    )


def relate_log_allometry() -> fm.Explanation:
    """fm.relate: log-log scatter with fitted line and highlighted named points."""
    return fm.explain(
        "Basal metabolic rate scales as body mass^0.75 across six decades of size",
        fm.relate(
            [0.02, 0.1, 0.5, 2.0, 15.0, 70.0, 400.0, 3000.0],
            [0.05, 0.17, 0.58, 1.7, 7.6, 24.0, 88.0, 410.0],
            x_label="Body mass (kg)",
            y_label="Metabolic rate (W)",
            unit="W",
            fit=True,
            log_x=True,
            log_y=True,
            names=["mouse", "rat", "pigeon", "cat", "dog", "human", "horse", "elephant"],
            highlight=["mouse", "elephant"],
            title="A single 3/4-power line spans mouse to elephant",
        ),
        source=SOURCE,
    )


def matrix_missing() -> fm.Explanation:
    """fm.matrix: rectangular heat table with highlighted cell and missing-value markers."""
    return fm.explain(
        "Model C leads on math (91%) and coding (88%) but has no multimodal score yet",
        fm.matrix(
            [
                [74.0, 78.0, 62.0, 69.0],
                [83.0, 81.0, 77.0, 75.0],
                [91.0, 88.0, np.nan, 84.0],
            ],
            rows=["Model A", "Model B", "Model C"],
            cols=["Math", "Code", "Multimodal", "Long context"],
            label="Benchmark pass rate",
            unit="%",
            highlight=[("Model C", "Math"), ("Model C", "Code")],
            title="Missing evaluations appear as dashes rather than zeros",
        ),
        note="Dash (—) marks an evaluation suite not yet run for that checkpoint.",
        source=SOURCE,
    )


def histogram_bimodal() -> fm.Explanation:
    """fm.histogram: binned single-variable distribution revealing two modes and an SLA threshold."""
    rng = np.random.default_rng(51)
    fast = rng.normal(18.0, 3.2, 145)
    slow = rng.normal(44.0, 4.8, 75)
    latencies = np.concatenate([fast, slow]).clip(6.0, 62.0).round(1).tolist()
    return fm.explain(
        "Request latency splits into two modes near 18 ms and 44 ms; 32% exceed the 35 ms SLA",
        fm.histogram(
            latencies,
            bins=18,
            reference=(35.0, "35 ms SLA"),
            label="Response time",
            unit="ms",
            title="Cache hits cluster around 18 ms while misses peak near 44 ms",
        ),
        subtitle="220 sampled API requests over 1 hour; dashed line marks overall median",
        source=SOURCE,
    )


def histogram_groups() -> fm.Explanation:
    """fm.distribution(..., bins=...): shared-axis stacked histograms comparing two groups."""
    rng = np.random.default_rng(63)
    before = rng.lognormal(np.log(410), 0.32, 180).clip(150, 1150).round(0).tolist()
    after = rng.lognormal(np.log(310), 0.24, 180).clip(140, 1150).round(0).tolist()
    return fm.explain(
        "The new checkout flow cuts median latency by 120 ms and drops >500 ms sessions from 34% to 3%",
        fm.distribution(
            {"Before": before, "After": after},
            bins=16,
            baseline="Before",
            highlight="After",
            reference=(500.0, "500 ms target"),
            label="Session latency",
            unit="ms",
            title="Both the centre and the slow right tail shifted left",
        ),
        subtitle="180 sessions per cohort on identical 60 ms bins",
        source=SOURCE,
    )


EXAMPLES = {
    "compare_intervals": compare_intervals,
    "trend_dates_events": trend_dates_events,
    "trend_log_log": trend_log_log,
    "trend_points_tasks": trend_points_tasks,
    "distribution_log": distribution_log,
    "histogram_bimodal": histogram_bimodal,
    "histogram_groups": histogram_groups,
    "relate_groups_fit": relate_groups_fit,
    "relate_log_allometry": relate_log_allometry,
    "matrix_missing": matrix_missing,
}


def build() -> fm.Explanation:
    """Entry point for ``figmint run gallery/explain_form_gallery.py --journal screen``."""
    return compare_intervals()


if __name__ == "__main__":
    out_dir = Path(__file__).resolve().parent / "output" / "explain_forms"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, make in EXAMPLES.items():
        summary = make().save(out_dir / f"{name}.png", write_spec=True)
        print(f"{name}: ok={summary['ok']} {summary['size_px']} issues={summary['issues']}")
