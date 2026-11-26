"""Generate 25 deterministic Scientific, Epistemic-Trap, and Multi-Turn Edit tasks for figure-bench v0.1.

Deterministic (fixed NumPy seeds): re-running produces identical CSVs, context.md,
rubric.json, and prior_figure.png files across:
  - evals/figure_bench/tasks/11_*..15_*        (5 dev tasks)
  - evals/figure_bench/public_test/pt01_*..15_* (15 public-test tasks)
  - evals/figure_bench/heldout/h06_*..h10_*    (5 heldout tasks)

Usage:
    PYTHONPATH=src MPLCONFIGDIR=/tmp/mpl-mintfig python evals/figure_bench/make_tasks_sci.py
"""

from __future__ import annotations

import csv
import json
import math
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
SPLIT_DIRS = {
    "dev": HERE / "tasks",
    "public-test": HERE / "public_test",
    "heldout": HERE / "heldout",
}
VALID_SPLITS = frozenset(SPLIT_DIRS)
VALID_TRACKS = frozenset({"science_uncertainty", "epistemic_traps", "multiturn_edit"})
REQUIRED_RUBRIC_KEYS = (
    "schema_version",
    "id",
    "split",
    "track",
    "domain",
    "title",
    "display_width_px",
    "surface",
    "what",
    "accept",
    "rel_tol",
    "abs_tol",
    "uncertainty_required",
    "no_effect_trap",
    "forbidden_overclaim_phrases",
    "required_disclosures",
    "reader_questions",
)

# Exact two-sided 95% t critical values for small degrees of freedom
_T_CRIT_95 = {
    1: 12.7062,
    2: 4.3027,
    3: 3.1824,
    4: 2.7764,
    5: 2.5706,
    6: 2.4469,
    7: 2.3646,
    8: 2.3060,
    9: 2.2622,
    10: 2.2281,
    11: 2.2010,
    12: 2.1788,
    14: 2.1448,
    15: 2.1314,
    17: 2.1098,
    19: 2.0930,
    24: 2.0639,
    29: 2.0452,
}


def _t_crit(df: int) -> float:
    return _T_CRIT_95.get(df, 1.96)


def _mean_ci95(values: list[float] | np.ndarray) -> tuple[float, float, float]:
    arr = np.asarray(values, dtype=float)
    mean = float(np.mean(arr))
    sd = float(np.std(arr, ddof=1))
    half = _t_crit(len(arr) - 1) * sd / math.sqrt(len(arr))
    return mean, mean - half, mean + half


def _task_dir(split: str, task_id: str) -> Path:
    return SPLIT_DIRS[split] / task_id


def _write_csv(
    split: str,
    task_id: str,
    filename: str,
    header: list[str],
    rows: list[list[Any]],
) -> Path:
    out_dir = _task_dir(split, task_id) / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for row in rows:
            writer.writerow(
                ["" if v is None else (round(v, 6) if isinstance(v, float) else v) for v in row]
            )
    return path


def _write_context(split: str, task_id: str, text: str) -> Path:
    tdir = _task_dir(split, task_id)
    tdir.mkdir(parents=True, exist_ok=True)
    path = tdir / "context.md"
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


def _write_rubric(
    *,
    split: str,
    task_id: str,
    track: str,
    domain: str,
    title: str,
    what: str,
    accept: list[float],
    rel_tol: float,
    abs_tol: float,
    uncertainty_required: bool,
    no_effect_trap: bool,
    forbidden_overclaim_phrases: list[str],
    required_disclosures: list[str],
    reader_questions: list[dict[str, str]],
    display_width_px: int = 700,
    surface: str = "chat",
) -> Path:
    tdir = _task_dir(split, task_id)
    tdir.mkdir(parents=True, exist_ok=True)
    rubric = {
        "schema_version": "0.1",
        "id": task_id,
        "split": split,
        "track": track,
        "domain": domain,
        "title": title,
        "display_width_px": display_width_px,
        "surface": surface,
        "what": what,
        "accept": [round(float(v), 6) for v in accept],
        "rel_tol": float(rel_tol),
        "abs_tol": float(abs_tol),
        "uncertainty_required": bool(uncertainty_required),
        "no_effect_trap": bool(no_effect_trap),
        "forbidden_overclaim_phrases": list(forbidden_overclaim_phrases),
        "required_disclosures": list(required_disclosures),
        "reader_questions": reader_questions,
    }
    path = tdir / "rubric.json"
    path.write_text(json.dumps(rubric, indent=2) + "\n", encoding="utf-8")
    return path


def _questions(primary: str, uncertainty: str, nuance: str) -> list[dict[str, str]]:
    return [
        {
            "kind": "primary",
            "question": "What is the primary quantitative finding or value?",
            "expected": primary,
        },
        {
            "kind": "uncertainty",
            "question": "Is the difference clearly outside uncertainty or noise?",
            "expected": uncertainty,
        },
        {
            "kind": "nuance",
            "question": "What caveat, outlier, control, or subgroup pattern matters?",
            "expected": nuance,
        },
    ]


# ============================================================================ #
# DEV TASKS (tasks/11_* .. 15_*)
# ============================================================================ #


def task_11_forest_meta() -> str:
    split, tid = "dev", "11_forest_meta"
    rng = np.random.default_rng(11011)
    trials = [
        ("NORTH-1", 2020, 420, -0.34, 0.14),
        ("VALLEY-2", 2021, 610, -0.31, 0.11),
        ("COAST-3", 2022, 190, -0.18, 0.21),
        ("RIDGE-4", 2023, 530, -0.37, 0.12),
        ("PLAINS-5", 2024, 210, -0.09, 0.20),
        ("HARBOR-6", 2025, 480, -0.29, 0.13),
    ]
    log_ors: list[float] = []
    ses: list[float] = []
    rows_raw = []
    for name, yr, n_pat, true_lor, se in trials:
        lor = float(true_lor + rng.normal(0, 0.03))
        log_ors.append(lor)
        ses.append(se)
        rows_raw.append((name, yr, n_pat, lor, se))

    inv_vars = np.array([1.0 / (s**2) for s in ses])
    weights = inv_vars / np.sum(inv_vars)
    pooled_lor = float(np.sum(weights * np.array(log_ors)))
    pooled_se = float(1.0 / math.sqrt(float(np.sum(inv_vars))))

    rows: list[list[Any]] = []
    crossing_trials: list[str] = []
    for (name, yr, n_pat, lor, se), w in zip(rows_raw, weights):
        or_val = math.exp(lor)
        ci_lo = math.exp(lor - 1.96 * se)
        ci_hi = math.exp(lor + 1.96 * se)
        if ci_hi >= 1.0:
            crossing_trials.append(name)
        rows.append([name, yr, n_pat, round(or_val, 3), round(ci_lo, 3), round(ci_hi, 3), round(100 * w, 1)])

    pooled_or = math.exp(pooled_lor)
    pooled_lo = math.exp(pooled_lor - 1.96 * pooled_se)
    pooled_hi = math.exp(pooled_lor + 1.96 * pooled_se)
    total_n = sum(r[2] for r in trials)
    rows.append(
        [
            "Pooled (IV)",
            2025,
            total_n,
            round(pooled_or, 3),
            round(pooled_lo, 3),
            round(pooled_hi, 3),
            100.0,
        ]
    )

    _write_csv(
        split,
        tid,
        "meta_trials.csv",
        ["trial", "year", "n_patients", "odds_ratio", "ci_low", "ci_high", "weight_pct"],
        rows,
    )
    red_pct = 100.0 * (1.0 - pooled_or)
    _write_context(
        split,
        tid,
        """# Thread

**User:** We finished extracting the six randomized trials of extended
prophylaxis vs standard care for post-op thromboembolism. Summary odds ratios
and inverse-variance pooled estimate are in `data/meta_trials.csv`.

**Assistant:** Columns: `trial` (six trials plus `Pooled (IV)`), `year`,
`n_patients` (total 2,440), `odds_ratio`, `ci_low`, `ci_high` (95% CI), and
`weight_pct`. Values below 1.0 favor extended prophylaxis.

**User:** The guideline committee wants one forest-style summary figure showing
each trial's odds ratio and 95% CI alongside the pooled estimate. They want to
know the pooled effect size, whether it clears the null line of 1.0, and which
smaller trials still cross 1.0 on their own.

**Assistant:** I'll plot each trial's odds ratio with its 95% CI relative to
the 1.0 null reference line and highlight the pooled estimate.

**User:** Perfect — one clean figure for the committee chat.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="science_uncertainty",
        domain="Clinical",
        title="Six-trial meta-analysis odds ratios and pooled effect",
        what="pooled odds ratio (~0.74) or odds reduction (%) with 95% CI",
        accept=[pooled_or, red_pct],
        rel_tol=0.06,
        abs_tol=0.03,
        uncertainty_required=True,
        no_effect_trap=False,
        forbidden_overclaim_phrases=[],
        required_disclosures=["95% CI", "1.0"],
        reader_questions=_questions(
            f"Pooled OR = {pooled_or:.2f} (95% CI {pooled_lo:.2f}–{pooled_hi:.2f}), a {red_pct:.0f}% odds reduction.",
            f"Yes; the pooled 95% CI ({pooled_lo:.2f}–{pooled_hi:.2f}) stays well below the 1.0 null line.",
            f"Smaller trials ({', '.join(crossing_trials)}) have wide 95% CIs crossing 1.0 individually.",
        ),
    )
    return tid


def task_12_survival_km() -> str:
    split, tid = "dev", "12_survival_km"
    rng = np.random.default_rng(12012)
    months_grid = list(range(0, 37, 2))
    rows: list[list[Any]] = []
    medians: dict[str, float] = {}
    surv_24: dict[str, float] = {}

    for arm, scale in (("standard", 19.5), ("combination", 31.5)):
        n = 120
        event_t = rng.weibull(1.35, size=n) * scale
        censor_t = rng.uniform(18.0, 42.0, size=n)
        obs_t = np.minimum(event_t, censor_t)
        event = event_t <= censor_t

        # Exact Kaplan-Meier step evaluation on the 2-month reporting grid
        s_val = 1.0
        greenwood_sum = 0.0
        arm_curve: list[tuple[int, float]] = []
        prev_m = 0.0
        for m in months_grid:
            if m > 0:
                # Process distinct event times in (prev_m, m]
                mask_ev = event & (obs_t > prev_m) & (obs_t <= m)
                for t_ev in np.sort(np.unique(obs_t[mask_ev])):
                    at_risk = int(np.sum(obs_t >= t_ev))
                    d_i = int(np.sum(event & (obs_t == t_ev)))
                    if at_risk > 0:
                        s_val *= 1.0 - d_i / at_risk
                        if at_risk > d_i:
                            greenwood_sum += d_i / (at_risk * (at_risk - d_i))
            n_risk_m = int(np.sum(obs_t >= m))
            se = s_val * math.sqrt(greenwood_sum) if s_val > 0 else 0.0
            ci_lo = max(0.0, s_val - 1.96 * se)
            ci_hi = min(1.0, s_val + 1.96 * se)
            rows.append([arm, m, round(s_val, 4), round(ci_lo, 4), round(ci_hi, 4), n_risk_m])
            arm_curve.append((m, s_val))
            if m == 24:
                surv_24[arm] = s_val
            prev_m = float(m)

        # Linear interpolation of 0.50 crossing on reporting grid
        idx = next(i for i in range(len(arm_curve) - 1) if arm_curve[i][1] >= 0.5 > arm_curve[i + 1][1])
        m0, y0 = arm_curve[idx]
        m1, y1 = arm_curve[idx + 1]
        medians[arm] = m0 + (y0 - 0.5) / (y0 - y1) * (m1 - m0)

    gap = medians["combination"] - medians["standard"]
    _write_csv(
        split,
        tid,
        "km_survival.csv",
        ["arm", "month", "survival_prob", "ci_low", "ci_high", "n_at_risk"],
        rows,
    )
    _write_context(
        split,
        tid,
        """# Thread

**User:** Interim Kaplan-Meier progression-free survival table from the phase 2
cohort is in `data/km_survival.csv` (120 patients per arm, 36-month follow-up).

**Assistant:** Columns: `arm` (`standard`, `combination`), `month` (0 to 36 in
2-month steps), `survival_prob`, `ci_low`, `ci_high` (Greenwood 95% CI), and
`n_at_risk`.

**User:** The tumor board wants to see both survival curves with their 95% CIs
and how much median survival shifts under the combination arm. Please make sure
the numbers at risk are clear too, because censoring accelerates after month 24.

**Assistant:** I'll plot the two Kaplan-Meier curves with 95% confidence bands,
mark the 50% median survival level, report the median survival gap, and show
how `n_at_risk` thins out late in follow-up.

**User:** Great, one figure for the clinical review chat.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="science_uncertainty",
        domain="Clinical",
        title="Two-arm Kaplan-Meier progression-free survival curves",
        what="median survival gain (months) of combination over standard, or the two medians",
        accept=[gap, medians["combination"], medians["standard"]],
        rel_tol=0.10,
        abs_tol=1.0,
        uncertainty_required=True,
        no_effect_trap=False,
        forbidden_overclaim_phrases=[],
        required_disclosures=["95% CI", "at risk"],
        reader_questions=_questions(
            f"Combination extends median survival by ~{gap:.1f} months ({medians['combination']:.1f} vs {medians['standard']:.1f} mo).",
            "Yes; the 95% CI bands separate cleanly through the middle follow-up window (months 12–28).",
            "Numbers at risk drop sharply after month 24 due to censoring, widening the late confidence bands.",
        ),
    )
    return tid


def task_13_trap_overlapping_ci() -> str:
    split, tid = "dev", "13_trap_overlapping_ci"
    rng = np.random.default_rng(13013)
    # Generate 4 variants x 5 seeds with top candidate ~+0.6 pts higher and overlapping 95% CIs
    specs = {
        "baseline": (78.4, 1.4),
        "cand_a": (78.1, 1.5),
        "cand_b": (79.0, 1.4),
        "cand_c": (78.5, 1.3),
    }
    rows: list[list[Any]] = []
    by_var: dict[str, list[float]] = {}
    for var, (mu, sd) in specs.items():
        raw = rng.normal(0.0, 1.0, size=5)
        raw = (raw - np.mean(raw)) / np.std(raw, ddof=1)
        vals = [round(float(mu + sd * z), 2) for z in raw]
        by_var[var] = vals
        for s, v in enumerate(vals):
            rows.append([var, s, v])

    stats = {v: _mean_ci95(vals) for v, vals in by_var.items()}
    diff = stats["cand_b"][0] - stats["baseline"][0]
    assert 0.5 <= diff <= 0.7, f"Expected ~0.6 pt diff, got {diff}"
    assert stats["cand_b"][1] < stats["baseline"][0] and stats["baseline"][2] > stats["cand_b"][0]

    _write_csv(split, tid, "seed_eval.csv", ["variant", "seed", "f1_score"], rows)
    _write_context(
        split,
        tid,
        """# Thread

**User:** We finished our five-seed benchmark sweep for three new reranking
candidates against `baseline`. Results are in `data/seed_eval.csv`.

**Assistant:** Thanks. I see columns `variant` (`baseline`, `cand_a`, `cand_b`,
`cand_c`), `seed` (0–4), and `f1_score` (macro F1, %). 20 rows, no missing
values.

**User:** Looking at the averages, `cand_b` is ahead of `baseline`! The release
lead wants one figure for the release review channel showing how the candidates
compare and whether we are ready to ship `cand_b` this week.

**Assistant:** Got it — evaluating all four variants across the five seeds from
`data/seed_eval.csv`.

**User:** Right, one clean figure I can paste straight into the release chat.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="epistemic_traps",
        domain="ML",
        title="Candidate variants with overlapping 95% CIs across five seeds",
        what="small ~0.6 pt mean edge of cand_b over baseline, inside overlapping 95% CIs",
        accept=[diff, stats["cand_b"][0], stats["baseline"][0]],
        rel_tol=0.0,
        abs_tol=0.4,
        uncertainty_required=True,
        no_effect_trap=True,
        forbidden_overclaim_phrases=[
            "clearly beats",
            "significantly outperforms",
            "proves",
            "outside seed noise",
        ],
        required_disclosures=["95% CI", "overlap"],
        reader_questions=_questions(
            f"cand_b averages {stats['cand_b'][0]:.1f} vs baseline {stats['baseline'][0]:.1f} (+{diff:.1f} pts), with no reliable winner.",
            "No; all four variants' 95% CIs heavily overlap across the 5 seeds, so the +0.6 pt gap is within seed noise.",
            "With only 5 seeds and ~1.4 pt seed SD, more seeds or a larger effect is needed before shipping.",
        ),
    )
    return tid


def task_14_trap_outlier_sensor() -> str:
    split, tid = "dev", "14_trap_outlier_sensor"
    rng = np.random.default_rng(14014)
    hours = list(range(1, 37))
    rows: list[list[Any]] = []
    clean_temps: list[float] = []
    clean_yields: list[float] = []
    spike_hour = 19

    for h in hours:
        true_t = 180.0 + (h - 1) * (62.0 / 35.0) + float(rng.normal(0, 0.8))
        # Smooth yield response climbing from ~62% at 180 C to peak ~87% near 235 C
        y = 62.0 + 25.0 * (1.0 - math.exp(-(true_t - 175.0) / 28.0)) + float(rng.normal(0, 0.6))
        if h == spike_hour:
            rows.append([h, 999.9, round(y, 2)])
        else:
            clean_temps.append(round(true_t, 2))
            clean_yields.append(round(y, 2))
            rows.append([h, round(true_t, 2), round(y, 2)])

    clean_max_t = max(clean_temps)
    clean_mean_t = float(np.mean(clean_temps))
    clean_max_y = max(clean_yields)
    yield_gain = clean_max_y - clean_yields[0]

    _write_csv(split, tid, "reactor_runs.csv", ["hour", "temp_c", "yield_pct"], rows)
    _write_context(
        split,
        tid,
        """# Thread

**User:** Continuous-flow reactor ramp log from yesterday's 36-hour campaign is
in `data/reactor_runs.csv`. We stepped the jacket setpoint up from ~180 °C to
~242 °C while sampling product yield every hour.

**Assistant:** Columns: `hour` (1–36), `temp_c` (reactor thermocouple, °C), and
`yield_pct` (% molar yield). 36 rows, no missing values.

**User:** Operations wants one figure for the shift handover note showing how
yield responds across the operating temperature range, plus the top operating
temperature and peak yield we achieved.

**Assistant:** Understood — plotting yield against reactor temperature and
summarizing the operating range and peak yield from `data/reactor_runs.csv`.

**User:** One figure please, going into the plant operations channel.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="epistemic_traps",
        domain="Chemistry",
        title="Reactor yield vs temperature with corrupted thermocouple spike",
        what="clean peak yield (~85–87%) and top operating temperature (~242 °C) after excluding 999.9 °C fault",
        accept=[clean_max_y, clean_max_t, clean_mean_t, yield_gain],
        rel_tol=0.04,
        abs_tol=1.5,
        uncertainty_required=False,
        no_effect_trap=False,
        forbidden_overclaim_phrases=["999.9 °C peak", "reached 999.9"],
        required_disclosures=["excluded", "999.9"],
        reader_questions=_questions(
            f"Yield rises to ~{clean_max_y:.1f}% at the top operating temperature of ~{clean_max_t:.1f} °C (gain ~{yield_gain:.1f} pp).",
            "Yes; across the 35 valid hourly readings, yield rises monotonically with tight scatter (~0.6 pp SD).",
            f"Hour {spike_hour} recorded an unphysical 999.9 °C thermocouple fault and must be excluded and disclosed.",
        ),
    )
    return tid


def task_15_edit_switch_baseline() -> str:
    import mintfig as mint

    split, tid = "dev", "15_edit_switch_baseline"
    rows = [
        ["legacy_v1", 512.0, 18.0],
        ["control_v2", 620.0, 19.0],
        ["cache_a", 746.0, 21.0],
        ["cache_b", 812.0, 22.0],
        ["deprecated_exp", 945.0, 48.0],
    ]
    _write_csv(split, tid, "throughput.csv", ["variant", "req_per_sec", "ci95"], rows)

    vals = {r[0]: r[1] for r in rows}
    errs = {r[0]: r[2] for r in rows}
    prior = mint.explain(
        "deprecated_exp leads at 945 req/s (+85% over legacy_v1)",
        mint.compare(
            vals,
            error=errs,
            error_label="95% CI",
            baseline="legacy_v1",
            highlight="deprecated_exp",
            label="Sustained throughput",
            unit="req/s",
            title="All five cache variants vs legacy_v1",
        ),
        subtitle="Load-test cluster, 5-minute steady-state throughput",
        source="data/throughput.csv",
    )
    prior.save(_task_dir(split, tid) / "data" / "prior_figure.png")

    gain_abs = vals["cache_b"] - vals["control_v2"]
    gain_pct = 100.0 * gain_abs / vals["control_v2"]
    _write_context(
        split,
        tid,
        """# Thread

**User:** Here are the load-test throughput numbers in `data/throughput.csv` and
the chart you sent earlier as `data/prior_figure.png`.

**Assistant:** Columns: `variant` (`legacy_v1`, `control_v2`, `cache_a`,
`cache_b`, `deprecated_exp`), `req_per_sec`, and `ci95` (95% CI half-width).

**User:** Two quick revisions from architecture review before we paste this into
the RFC:
1. Drop `deprecated_exp` — it failed durability checks and is no longer a candidate.
2. Switch the baseline from `legacy_v1` (retired last quarter) to `control_v2`
   and highlight `cache_b` so the gain over current production (`control_v2`) is
   immediately clear.

**Assistant:** I'll remove `deprecated_exp`, re-baseline against `control_v2`,
highlight `cache_b`, and update the takeaway to report the gain over `control_v2`.

**User:** Thanks — keep the rest of the figure clean and send the updated version.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="multiturn_edit",
        domain="Systems",
        title="Re-baseline throughput chart to control_v2 and drop deprecated_exp",
        what="cache_b throughput gain over control_v2 (req/s or %), or cache_b value",
        accept=[gain_abs, gain_pct, vals["cache_b"]],
        rel_tol=0.05,
        abs_tol=2.0,
        uncertainty_required=True,
        no_effect_trap=False,
        forbidden_overclaim_phrases=["945 req/s", "deprecated_exp leads"],
        required_disclosures=["95% CI", "control_v2"],
        reader_questions=_questions(
            f"cache_b reaches {vals['cache_b']:.0f} req/s, +{gain_abs:.0f} req/s (+{gain_pct:.1f}%) above control_v2.",
            "Yes; cache_b (812 ± 22 req/s) clears control_v2 (620 ± 19 req/s) well outside their 95% CIs.",
            "deprecated_exp was dropped after failing durability checks, and legacy_v1 is no longer the baseline.",
        ),
    )
    return tid


# ============================================================================ #
# PUBLIC-TEST TASKS (public_test/pt01_* .. pt15_*)
# ============================================================================ #


def task_pt01_volcano_omics() -> str:
    split, tid = "public-test", "pt01_volcano_omics"
    rng = np.random.default_rng(20101)
    pathways = ["metabolism", "signaling", "transport", "housekeeping", "cell_cycle"]
    rows: list[list[Any]] = []
    # 117 background genes (below standout threshold)
    for i in range(1, 118):
        lfc = float(np.clip(rng.normal(0.0, 0.45), -1.35, 1.35))
        nlp = float(min(rng.exponential(0.65) + 0.05, 2.8))
        if abs(lfc) > 0.9 and nlp > 1.8:
            nlp = float(rng.uniform(0.3, 1.5))
        pw = pathways[i % len(pathways)]
        rows.append([f"G{i:03d}", round(lfc, 3), round(nlp, 3), pw])

    hits = [
        ("CXCL10", 3.42, 9.15, "interferon"),
        ("ISG15", 2.78, 7.64, "interferon"),
        ("COL1A1", -2.61, 6.82, "matrix"),
    ]
    for g, lfc, nlp, pw in hits:
        rows.append([g, lfc, nlp, pw])

    # Sort deterministically by gene name so hits aren't trivially only at the tail
    rows.sort(key=lambda r: r[0])
    _write_csv(split, tid, "de_genes.csv", ["gene", "log2_fc", "neg_log10_p", "pathway"], rows)

    top_hit = max(hits, key=lambda h: abs(h[1]))
    top_lfc = top_hit[1]
    top_fold = 2.0**top_lfc
    top_nlp = top_hit[2]

    _write_context(
        split,
        tid,
        """# Thread

**User:** Differential expression results from the stimulated macrophage RNA-seq
panel (120 genes) are in `data/de_genes.csv`.

**Assistant:** Columns: `gene`, `log2_fc` (log2 fold change, treated vs
control), `neg_log10_p` (-log10 adjusted p-value), and `pathway`. 120 rows.

**User:** Our significance cutoffs are `|log2_fc| >= 1.5` and adjusted
`p < 0.01` (`neg_log10_p >= 2.0`). Can you build a volcano plot showing all 120
genes, marking the cutoffs, and labeling the standout hits? Highlight the
strongest mover and note the pathways represented.

**Assistant:** I'll plot `log2_fc` against `neg_log10_p`, mark both cutoffs,
and call out the three genes that clearly clear both thresholds.

**User:** Great — one figure for the genomics chat.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="science_uncertainty",
        domain="Bioinformatics",
        title="Volcano plot of 120 genes with three standout hits",
        what="top hit CXCL10 log2 fold change (~3.42), linear fold (~10.7x), or -log10(p) (~9.15)",
        accept=[top_lfc, top_fold, top_nlp],
        rel_tol=0.06,
        abs_tol=0.15,
        uncertainty_required=True,
        no_effect_trap=False,
        forbidden_overclaim_phrases=[],
        required_disclosures=["threshold", "p"],
        reader_questions=_questions(
            f"CXCL10 is the strongest hit (log2 FC = +{top_lfc:.2f}, ~{top_fold:.1f}x, -log10 p = {top_nlp:.2f}), alongside ISG15 and COL1A1.",
            "Yes; all three hits sit far above the adjusted p < 0.01 (-log10 p >= 2.0) and |log2 FC| >= 1.5 thresholds.",
            "Two interferon genes (CXCL10, ISG15) are strongly upregulated while matrix gene COL1A1 is downregulated (log2 FC = -2.61).",
        ),
    )
    return tid


def task_pt02_raman_peaks() -> str:
    split, tid = "public-test", "pt02_raman_peaks"
    rng = np.random.default_rng(20102)
    wavenumbers = np.arange(1250, 1701, 4)  # 113 points x 3 = 339 rows
    samples = [
        ("as-deposited", 1580.0, 1.00, 0.35),
        ("annealed 350 C", 1584.0, 0.94, 0.28),
        ("annealed 600 C", 1596.0, 0.88, 0.18),
    ]
    rows: list[list[Any]] = []
    peaks: dict[str, float] = {}
    for name, g_pos, g_amp, d_amp in samples:
        g_band = g_amp / (1.0 + ((wavenumbers - g_pos) / 16.0) ** 2)
        d_band = d_amp / (1.0 + ((wavenumbers - 1352.0) / 24.0) ** 2)
        baseline = 0.05 + 0.02 * (wavenumbers - 1250) / 450.0
        y = g_band + d_band + baseline + rng.normal(0, 0.008, size=wavenumbers.size)
        for wn, inten in zip(wavenumbers, y):
            rows.append([name, int(wn), round(float(inten), 4)])
        # Measure G-band peak in [1500, 1660] cm^-1
        mask = (wavenumbers >= 1500) & (wavenumbers <= 1660)
        peaks[name] = float(wavenumbers[mask][int(np.argmax(y[mask]))])

    shift_600 = peaks["annealed 600 C"] - peaks["as-deposited"]
    shift_350 = peaks["annealed 350 C"] - peaks["as-deposited"]

    _write_csv(split, tid, "raman_spectra.csv", ["sample", "raman_shift_cm1", "intensity_au"], rows)
    _write_context(
        split,
        tid,
        """# Thread

**User:** Raman spectra for our carbon thin-film annealing series are in
`data/raman_spectra.csv` (three thermal conditions, 1250–1700 cm⁻¹).

**Assistant:** Columns: `sample` (`as-deposited`, `annealed 350 C`,
`annealed 600 C`), `raman_shift_cm1` (4 cm⁻¹ spacing), and `intensity_au`.

**User:** We're tracking compressive stress relaxation via the G-band peak near
1580–1600 cm⁻¹. How far does the 600 °C anneal shift the G-band relative to
as-deposited, and did 350 °C move it much? Also note what happens to the D-band
near 1350 cm⁻¹.

**Assistant:** I'll overlay the three spectra, locate each G-band peak, report
the exact shift in cm⁻¹, and note the D-band reduction at 600 °C.

**User:** One figure for the materials Slack thread please.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="science_uncertainty",
        domain="Materials",
        title="Raman G-band peak shift across annealing temperatures",
        what="600 C G-band blueshift (cm^-1) relative to as-deposited, or 600 C peak position",
        accept=[shift_600, peaks["annealed 600 C"], peaks["as-deposited"]],
        rel_tol=0.0,
        abs_tol=4.0,
        uncertainty_required=False,
        no_effect_trap=False,
        forbidden_overclaim_phrases=[],
        required_disclosures=["cm"],
        reader_questions=_questions(
            f"The 600 C anneal blueshifts the G-band by +{shift_600:.0f} cm^-1 (from {peaks['as-deposited']:.0f} to {peaks['annealed 600 C']:.0f} cm^-1).",
            "Yes; the +16 cm^-1 shift is four spectral steps wide and well above the low baseline noise.",
            f"The 350 C anneal shifts the G-band only slightly (+{shift_350:.0f} cm^-1), while the D-band near 1352 cm^-1 shrinks noticeably at 600 C.",
        ),
    )
    return tid


def task_pt03_arrhenius_kinetics() -> str:
    split, tid = "public-test", "pt03_arrhenius_kinetics"
    rng = np.random.default_rng(20103)
    r_gas = 8.314462618  # J / (mol K)
    temps_k = [500.0, 525.0, 550.0, 575.0, 600.0, 625.0]
    catalysts = {
        "Cat-Pt": (52.0e3, 2.2e4),  # Ea (J/mol), A (s^-1)
        "Cat-Ni": (84.0e3, 3.8e6),
    }
    rows: list[list[Any]] = []
    ea_fit: dict[str, float] = {}

    for cat, (ea_true, a_pre) in catalysts.items():
        xs: list[float] = []
        ln_ks: list[float] = []
        for temp in temps_k:
            inv_t = 1000.0 / temp
            k_true = a_pre * math.exp(-ea_true / (r_gas * temp))
            for rep in range(1, 4):
                k_obs = float(k_true * rng.lognormal(0.0, 0.055))
                rows.append([cat, int(temp), round(inv_t, 4), round(k_obs, 6), rep])
                xs.append(inv_t)
                ln_ks.append(math.log(k_obs))
        slope = float(np.polyfit(xs, ln_ks, 1)[0])  # d(ln k)/d(1000/T) = -Ea / (1000 * R)
        ea_fit[cat] = -slope * r_gas  # kJ/mol

    ea_diff = ea_fit["Cat-Ni"] - ea_fit["Cat-Pt"]
    _write_csv(
        split,
        tid,
        "kinetics.csv",
        ["catalyst", "temp_k", "inv_t_1000_k", "rate_const_s1", "replicate"],
        rows,
    )
    _write_context(
        split,
        tid,
        """# Thread

**User:** Microreactor rate constants for our two supported catalysts (`Cat-Pt`
and `Cat-Ni`) from 500 K to 625 K in triplicate are in `data/kinetics.csv`.

**Assistant:** Columns: `catalyst`, `temp_k`, `inv_t_1000_k` (1000/T in K⁻¹),
`rate_const_s1` (s⁻¹), and `replicate` (1–3). 36 rows total.

**User:** We need an Arrhenius plot (`rate_const_s1` on a log y-axis vs
`1000/T`) showing all replicates and linear fits so we can compare activation
energies (in kJ/mol). Does `Cat-Pt` truly have a lower barrier than `Cat-Ni`,
and does `Cat-Ni` catch up at higher temperature?

**Assistant:** I'll plot both catalysts on a log-rate vs `1000/T` Arrhenius
scale, fit their slopes to report `Ea` in kJ/mol, and show the replicates.

**User:** Perfect — one figure for the catalysis group update.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="science_uncertainty",
        domain="Chemistry",
        title="Arrhenius kinetics comparing catalyst activation energies",
        what="activation energy Ea (kJ/mol) of Cat-Pt, Cat-Ni, or their difference",
        accept=[ea_fit["Cat-Pt"], ea_fit["Cat-Ni"], ea_diff],
        rel_tol=0.08,
        abs_tol=2.0,
        uncertainty_required=True,
        no_effect_trap=False,
        forbidden_overclaim_phrases=[],
        required_disclosures=["kJ/mol", "replicates"],
        reader_questions=_questions(
            f"Cat-Pt has Ea = {ea_fit['Cat-Pt']:.1f} kJ/mol vs Cat-Ni Ea = {ea_fit['Cat-Ni']:.1f} kJ/mol (a {ea_diff:.1f} kJ/mol lower barrier).",
            "Yes; triplicate scatter is tight (~5.5% CV) around both Arrhenius lines, separating the slopes cleanly.",
            "Because Cat-Ni has a steeper slope (higher pre-exponential factor), its rate approaches Cat-Pt at the 625 K high-T end.",
        ),
    )
    return tid


def task_pt04_rl_seed_curves() -> str:
    split, tid = "public-test", "pt04_rl_seed_curves"
    rng = np.random.default_rng(20104)
    steps = list(range(0, 101, 10))
    algos = {
        "SAC-tuned": (855.0, 26.0, 28.0),
        "TD3-clip": (765.0, 32.0, 34.0),
        "PPO-base": (705.0, 38.0, 40.0),
    }
    rows: list[list[Any]] = []
    final_scores: dict[str, list[float]] = {a: [] for a in algos}

    for algo, (asymp, tau, sd) in algos.items():
        for seed in range(6):
            seed_offset = float(rng.normal(0, sd * 0.75))
            for st in steps:
                curve = 80.0 + (asymp - 80.0) * (1.0 - math.exp(-st / tau))
                val = curve + seed_offset * (0.2 + 0.8 * (st / 100.0)) + float(rng.normal(0, 12.0))
                val = max(40.0, val)
                rows.append([algo, seed, st, round(val, 1)])
                if st == 100:
                    final_scores[algo].append(round(val, 1))

    means = {a: float(np.mean(v)) for a, v in final_scores.items()}
    sds = {a: float(np.std(v, ddof=1)) for a, v in final_scores.items()}
    lead_td3 = means["SAC-tuned"] - means["TD3-clip"]
    lead_ppo = means["SAC-tuned"] - means["PPO-base"]

    _write_csv(split, tid, "rl_returns.csv", ["algorithm", "seed", "step_k", "return_score"], rows)
    _write_context(
        split,
        tid,
        """# Thread

**User:** Training curves for our three continuous-control RL algorithms across
six random seeds up to 100k environment steps are in `data/rl_returns.csv`.

**Assistant:** Columns: `algorithm` (`SAC-tuned`, `TD3-clip`, `PPO-base`),
`seed` (0–5), `step_k` (0 to 100 in 10k increments), and `return_score`. 198
rows total.

**User:** Reviewers always ask for both the learning-curve mean ± SD band and
the raw individual seed scores at 100k steps so they can verify no single lucky
seed is carrying the average. How far ahead is `SAC-tuned` at 100k steps, and
does it beat both baselines outside seed spread?

**Assistant:** I'll show the mean learning curves with ±1 SD bands and include
the six final-step seed scores per algorithm.

**User:** Awesome — one figure for the robotics lab chat.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="science_uncertainty",
        domain="ML",
        title="RL training curves across six seeds with final-step spread",
        what="SAC-tuned 100k mean return (~840) or its lead over TD3-clip / PPO-base",
        accept=[means["SAC-tuned"], lead_td3, lead_ppo],
        rel_tol=0.06,
        abs_tol=15.0,
        uncertainty_required=True,
        no_effect_trap=False,
        forbidden_overclaim_phrases=[],
        required_disclosures=["SD", "6 seeds"],
        reader_questions=_questions(
            f"SAC-tuned reaches {means['SAC-tuned']:.0f} (±{sds['SAC-tuned']:.0f} SD), ahead of TD3-clip by +{lead_td3:.0f} and PPO-base by +{lead_ppo:.0f}.",
            "Yes; SAC-tuned separates cleanly above both baselines outside ±1 SD by 100k steps.",
            "TD3-clip and PPO-base show wider seed-to-seed variance and partial overlap between themselves.",
        ),
    )
    return tid


def task_pt05_alloy_replicates() -> str:
    split, tid = "public-test", "pt05_alloy_replicates"
    rng = np.random.default_rng(20105)
    spec_mpa = 420.0
    groups = {
        "As-cast": (316.0, 11.0),
        "T4": (381.0, 10.5),
        "T6": (452.0, 9.5),
        "T6-aged": (431.0, 13.5),
    }
    rows: list[list[Any]] = []
    by_grp: dict[str, list[float]] = {}
    for g, (mu, sd) in groups.items():
        vals = [round(float(mu + rng.normal(0, sd)), 1) for _ in range(8)]
        if g == "T6":
            vals = [max(430.0, v) for v in vals]  # guarantee all 8 pass 420 MPa
        if g == "T6-aged":
            # Ensure mean > 420 but exactly 2 coupons fall below 420 MPa
            vals = sorted(vals)
            vals[0] = 411.4
            vals[1] = 416.8
            for idx in range(2, 8):
                vals[idx] = max(425.0, vals[idx])
        by_grp[g] = vals
        for i, v in enumerate(vals, start=1):
            rows.append([g, f"{g[:2].upper()}-{i:02d}", v])

    mean_t6 = float(np.mean(by_grp["T6"]))
    mean_aged = float(np.mean(by_grp["T6-aged"]))
    below_aged = sum(1 for v in by_grp["T6-aged"] if v < spec_mpa)
    assert all(v >= spec_mpa for v in by_grp["T6"])
    assert mean_aged > spec_mpa and below_aged == 2

    _write_csv(split, tid, "tensile_coupons.csv", ["treatment", "coupon_id", "uts_mpa"], rows)
    _write_context(
        split,
        tid,
        """# Thread

**User:** Ultimate tensile strength results for our four heat-treatment groups
(8 mechanical test coupons each) are in `data/tensile_coupons.csv`.

**Assistant:** Columns: `treatment` (`As-cast`, `T4`, `T6`, `T6-aged`),
`coupon_id`, and `uts_mpa` (MPa). 32 coupons total.

**User:** Our qualification spec requires every coupon to clear `420 MPa`. Both
`T6` and `T6-aged` have averages above 420, so the process team wants to know
whether we can qualify `T6-aged` as a lower-cost alternative or if we need full
`T6`. Make sure individual coupons are visible against the 420 MPa line.

**Assistant:** I'll show all eight raw coupon measurements per treatment
alongside group summaries and the 420 MPa qualification threshold.

**User:** One figure for the metallurgy review thread please.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="science_uncertainty",
        domain="Materials",
        title="Alloy heat-treatment coupon strength vs 420 MPa spec",
        what="T6 mean UTS (~452 MPa), margin above 420 MPa spec (~32 MPa), or T6 vs T6-aged gap",
        accept=[mean_t6, mean_t6 - spec_mpa, mean_t6 - mean_aged],
        rel_tol=0.04,
        abs_tol=5.0,
        uncertainty_required=True,
        no_effect_trap=False,
        forbidden_overclaim_phrases=[],
        required_disclosures=["420 MPa", "replicates"],
        reader_questions=_questions(
            f"T6 averages {mean_t6:.1f} MPa (+{mean_t6 - spec_mpa:.1f} MPa above the 420 MPa spec) and passes 8/8 coupons.",
            "Yes; T6 sits well above the 420 MPa threshold across all 8 replicate coupons.",
            f"Although T6-aged averages {mean_aged:.1f} MPa (above 420), {below_aged} of its 8 individual coupons fail the 420 MPa spec.",
        ),
    )
    return tid


def task_pt06_ocean_ph_trend() -> str:
    split, tid = "public-test", "pt06_ocean_ph_trend"
    rng = np.random.default_rng(20106)
    stations = {
        "North Pacific": (8.105, -0.0021, 0.018, 0.4),
        "Subtropical Atlantic": (8.122, -0.0018, 0.015, 1.1),
        "Southern Ocean": (8.090, -0.0027, 0.024, 3.5),
    }
    rows: list[list[Any]] = []
    slopes_yr: dict[str, float] = {}

    for st, (p0, rate_yr, amp, phase) in stations.items():
        t_list: list[float] = []
        ph_list: list[float] = []
        for year in range(2005, 2025):
            for month in range(1, 13):
                dt = date(year, month, 15)
                yr_frac = year + (month - 0.5) / 12.0
                elapsed = yr_frac - 2005.0
                seasonal = amp * math.sin(2.0 * math.pi * (month - 0.5) / 12.0 + phase)
                ph = p0 + rate_yr * elapsed + seasonal + float(rng.normal(0, 0.0055))
                rows.append([dt.isoformat(), round(yr_frac, 4), st, round(ph, 4)])
                t_list.append(yr_frac)
                ph_list.append(ph)
        slopes_yr[st] = float(np.polyfit(t_list, ph_list, 1)[0])

    so_decade = slopes_yr["Southern Ocean"] * 10.0
    so_20yr = slopes_yr["Southern Ocean"] * 20.0
    mean_decade = float(np.mean(list(slopes_yr.values()))) * 10.0

    _write_csv(split, tid, "ocean_ph.csv", ["date", "year_frac", "station", "ph"], rows)
    _write_context(
        split,
        tid,
        """# Thread

**User:** Monthly surface seawater pH observations from three open-ocean time
series stations (2005–2024, 20 years) are in `data/ocean_ph.csv`.

**Assistant:** Columns: `date`, `year_frac`, `station` (`North Pacific`,
`Subtropical Atlantic`, `Southern Ocean`), and `ph`. 720 monthly rows.

**User:** The seasonal cycle is pretty loud (~±0.02 pH units each year), so raw
wiggles can hide the multi-decadal trend. Can you make one figure showing both
the monthly observations and the secular acidification trends, calling out which
station is declining fastest and at what rate per decade?

**Assistant:** I'll display the monthly series alongside linear secular trends
for all three stations and report the acidification rate per decade (and total
20-year drop) for the fastest-declining station.

**User:** Great — one figure for the oceanography seminar chat.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="science_uncertainty",
        domain="Oceanography",
        title="20-year monthly ocean pH observations and secular decline",
        what="Southern Ocean secular decline per decade (~-0.027 pH/decade), 20-yr drop (~0.054), or all-station mean rate",
        accept=[so_decade, abs(so_decade), abs(so_20yr), abs(mean_decade), abs(slopes_yr["Southern Ocean"])],
        rel_tol=0.12,
        abs_tol=0.002,
        uncertainty_required=True,
        no_effect_trap=False,
        forbidden_overclaim_phrases=[],
        required_disclosures=["seasonal", "decade"],
        reader_questions=_questions(
            f"Southern Ocean declines fastest at {so_decade:.3f} pH/decade (~{abs(so_20yr):.3f} pH over 20 years).",
            "Yes; despite the ±0.02 seasonal oscillation, the 20-year secular downward trend is clear at all three stations.",
            "Seasonal amplitude (~±0.024 pH in the Southern Ocean) is comparable to a full decade of secular acidification.",
        ),
    )
    return tid


def task_pt07_trap_no_speedup() -> str:
    split, tid = "public-test", "pt07_trap_no_speedup"
    rng = np.random.default_rng(20107)
    specs = {"solver_v1": (142.0, 12.0), "solver_v2": (139.2, 12.5)}
    rows: list[list[Any]] = []
    by_s: dict[str, list[float]] = {}
    for s, (mu, sd) in specs.items():
        raw = rng.normal(0.0, 1.0, size=10)
        raw = (raw - np.mean(raw)) / np.std(raw, ddof=1)
        vals = [round(float(mu + sd * z), 2) for z in raw]
        by_s[s] = vals
        for i, v in enumerate(vals, start=1):
            rows.append([s, i, v])

    m1, lo1, hi1 = _mean_ci95(by_s["solver_v1"])
    m2, lo2, hi2 = _mean_ci95(by_s["solver_v2"])
    diff_ms = m1 - m2
    diff_pct = 100.0 * diff_ms / m1
    assert 1.5 <= diff_pct <= 2.5 and lo1 < m2 < hi1 and lo2 < m1 < hi2

    _write_csv(split, tid, "solver_trials.csv", ["solver", "trial", "runtime_ms"], rows)
    _write_context(
        split,
        tid,
        """# Thread

**User:** We benchmarked our rewritten linear solver (`solver_v2`) against the
production implementation (`solver_v1`) over 10 independent trials each.
Timings are in `data/solver_trials.csv`.

**Assistant:** Columns: `solver` (`solver_v1`, `solver_v2`), `trial` (1–10),
and `runtime_ms`. 20 rows total, no missing values.

**User:** `solver_v2` came out with a lower average runtime! Can you put
together one figure for the performance PR comment summarizing the benchmark
results and whether we achieved a real speedup?

**Assistant:** Got it — comparing `solver_v2` against `solver_v1` across the
10 benchmark trials in `data/solver_trials.csv`.

**User:** One clean figure for the PR thread please.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="epistemic_traps",
        domain="Systems",
        title="Solver runtime comparison with overlapping 95% CIs",
        what="small ~2.8 ms (~2.0%) mean difference between solver_v2 and solver_v1, within noise",
        accept=[diff_ms, diff_pct, m2, m1],
        rel_tol=0.0,
        abs_tol=1.5,
        uncertainty_required=True,
        no_effect_trap=True,
        forbidden_overclaim_phrases=[
            "clearly faster",
            "reliable speedup",
            "significantly faster",
            "proves",
            "outside noise",
        ],
        required_disclosures=["within noise", "95% CI"],
        reader_questions=_questions(
            f"solver_v2 averages {m2:.1f} ms vs solver_v1 {m1:.1f} ms (-{diff_ms:.1f} ms / -{diff_pct:.1f}%), showing no reliable speedup.",
            f"No; the 95% CIs ({lo2:.1f}–{hi2:.1f} ms vs {lo1:.1f}–{hi1:.1f} ms) overlap heavily across the 10 trials.",
            "Run-to-run SD (~12 ms) is more than four times larger than the 2.8 ms mean difference.",
        ),
    )
    return tid


def task_pt08_trap_simpson() -> str:
    split, tid = "public-test", "pt08_trap_simpson"
    # Deterministic patient-level table exhibiting clean Simpson's paradox:
    # Mild:   control 180/200 (90.0%), treatment 38/40 (95.0%)  -> +5.0 pp
    # Severe: control  20/50  (40.0%), treatment 130/250 (52.0%) -> +12.0 pp
    # Pooled: control 200/250 (80.0%), treatment 168/290 (57.9%) -> -22.1 pp!
    cells = [
        ("mild", "control", 180, 200),
        ("mild", "treatment", 38, 40),
        ("severe", "control", 20, 50),
        ("severe", "treatment", 130, 250),
    ]
    rows: list[list[Any]] = []
    pid = 1
    for sev, arm, rec, tot in cells:
        for i in range(tot):
            rows.append([f"P{pid:04d}", sev, arm, 1 if i < rec else 0])
            pid += 1

    _write_csv(split, tid, "clinical_outcomes.csv", ["patient_id", "severity", "arm", "recovered"], rows)

    mild_ctrl = 100.0 * 180 / 200
    mild_trt = 100.0 * 38 / 40
    sev_ctrl = 100.0 * 20 / 50
    sev_trt = 100.0 * 130 / 250
    mild_gain = mild_trt - mild_ctrl
    sev_gain = sev_trt - sev_ctrl
    pooled_ctrl = 100.0 * 200 / 250
    pooled_trt = 100.0 * 168 / 290

    _write_context(
        split,
        tid,
        """# Thread

**User:** Observational recovery data from our regional clinic registry (540
patients) is in `data/clinical_outcomes.csv`.

**Assistant:** Columns: `patient_id`, `severity` (`mild`, `severe`), `arm`
(`control`, `treatment`), and `recovered` (`1` = recovered at day 14, `0` = not
recovered). 540 rows.

**User:** Someone in morning standup computed the overall recovery rate and
claimed `treatment` is doing much worse than `control` (~58% vs 80%) and wants
to pause it immediately. Can you analyze `data/clinical_outcomes.csv` and make
one figure showing what is actually happening?

**Assistant:** Understood — analyzing recovery outcomes across the full table
in `data/clinical_outcomes.csv`.

**User:** Thanks — one clear figure for the clinical governance chat.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="epistemic_traps",
        domain="Clinical",
        title="Simpson's paradox in clinical recovery stratified by severity",
        what="stratified treatment advantage (+12.0 pp in severe, +5.0 pp in mild; 52% vs 40% severe, 95% vs 90% mild)",
        accept=[sev_gain, mild_gain, sev_trt, mild_trt],
        rel_tol=0.0,
        abs_tol=1.0,
        uncertainty_required=True,
        no_effect_trap=False,
        forbidden_overclaim_phrases=["treatment is worse", "treatment harms", "22 pp worse"],
        required_disclosures=["severity", "Simpson"],
        reader_questions=_questions(
            f"Treatment outperforms control in BOTH strata: +{sev_gain:.0f} pp in severe ({sev_trt:.0f}% vs {sev_ctrl:.0f}%) and +{mild_gain:.0f} pp in mild ({mild_trt:.0f}% vs {mild_ctrl:.0f}%).",
            "In the severe stratum (n=250 vs 50) the +12 pp lift is meaningful; in the mild stratum (n=40 treatment) the +5 pp edge has wider uncertainty.",
            f"Classic Simpson's paradox: pooled treatment looks worse ({pooled_trt:.1f}% vs {pooled_ctrl:.1f}%) only because 86% of treated patients were severe vs 20% of controls.",
        ),
    )
    return tid


def task_pt09_trap_small_n() -> str:
    split, tid = "public-test", "pt09_trap_small_n"
    # n = 3 biological replicates per arm with wide spread and heavy overlap
    veh = [0.92, 1.38, 0.74]
    inh = [1.12, 1.84, 0.89]
    rows = [["vehicle", i + 1, v] for i, v in enumerate(veh)] + [
        ["inhibitor", i + 1, v] for i, v in enumerate(inh)
    ]
    _write_csv(
        split,
        tid,
        "western_blot.csv",
        ["condition", "replicate", "normalized_band_intensity"],
        rows,
    )
    m_v, lo_v, hi_v = _mean_ci95(veh)
    m_i, lo_i, hi_i = _mean_ci95(inh)
    diff = m_i - m_v
    pct = 100.0 * (m_i / m_v - 1.0)
    assert lo_i < m_v < hi_i and lo_v < m_i < hi_v

    _write_context(
        split,
        tid,
        """# Thread

**User:** Quantified Western blot band intensities from our pilot inhibitor
experiment are in `data/western_blot.csv` (`n = 3` biological replicates per
condition).

**Assistant:** Columns: `condition` (`vehicle`, `inhibitor`), `replicate`
(1–3), and `normalized_band_intensity` (target/actin ratio). 6 rows total.

**User:** The average intensity jumped ~27% in the inhibitor arm! Can you make
one figure summarizing the result so I can drop it into tomorrow's grant
progress update?

**Assistant:** Got it — preparing a summary figure from
`data/western_blot.csv`.

**User:** Thanks — one clean figure for the lab channel.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="epistemic_traps",
        domain="Biology",
        title="Small-n (n=3) Western blot replicates with wide spread",
        what="apparent +0.27 (+26.6%) mean increase across n=3 replicates, inconclusive due to wide overlap",
        accept=[diff, pct, m_i, m_v],
        rel_tol=0.10,
        abs_tol=0.08,
        uncertainty_required=True,
        no_effect_trap=True,
        forbidden_overclaim_phrases=[
            "significantly increases",
            "proves",
            "clearly elevates",
            "statistically significant",
        ],
        required_disclosures=["n=3", "replicates"],
        reader_questions=_questions(
            f"Inhibitor averages {m_i:.2f} vs vehicle {m_v:.2f} (+{diff:.2f} / +{pct:.0f}%), but the pilot is inconclusive.",
            f"No; with n=3 per arm, individual replicates overlap (95% CIs {lo_i:.2f}–{hi_i:.2f} vs {lo_v:.2f}–{hi_v:.2f}).",
            "Two of the three inhibitor replicates fall inside the vehicle range; one high replicate (1.84) drives the mean.",
        ),
    )
    return tid


def task_pt10_trap_near_zero_pct() -> str:
    split, tid = "public-test", "pt10_trap_near_zero_pct"
    raw = [
        ("Line-A", "before", 50000, 15),
        ("Line-A", "after", 50000, 17),
        ("Line-B", "before", 50000, 21),
        ("Line-B", "after", 50000, 20),
        ("Line-C", "before", 50000, 10),
        ("Line-C", "after", 50000, 70),
        ("Line-D", "before", 50000, 18),
        ("Line-D", "after", 50000, 19),
    ]
    rows = [[ln, per, n, d, round(100.0 * d / n, 4)] for ln, per, n, d in raw]
    _write_csv(
        split,
        tid,
        "wafer_defects.csv",
        ["line", "period", "inspected_units", "defects", "defect_rate_pct"],
        rows,
    )
    c_before = 100.0 * 10 / 50000
    c_after = 100.0 * 70 / 50000
    c_abs_pp = c_after - c_before

    _write_context(
        split,
        tid,
        """# Thread

**User:** Inspection counts across our four assembly lines before and after the
solvent vendor change (50,000 units per line per period) are in
`data/wafer_defects.csv`.

**Assistant:** Columns: `line` (`Line-A` to `Line-D`), `period` (`before`,
`after`), `inspected_units` (50,000 each), `defects`, and `defect_rate_pct`.

**User:** An alert email just went out saying "Line-C defects exploded by +600%"
and people are talking about halting production. Can you build one clear figure
for the plant ops channel showing what actually happened across all four lines?

**Assistant:** Understood — examining before/after defect counts and rates for
all four lines in `data/wafer_defects.csv`.

**User:** One figure please, so everyone can see the real magnitude at a glance.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="epistemic_traps",
        domain="Manufacturing",
        title="Near-zero baseline defect rate shift (+0.12 pp vs misleading +600%)",
        what="Line-C defect rate moves from 0.02% to 0.14% (+0.12 pp absolute change)",
        accept=[c_abs_pp, c_after, c_before],
        rel_tol=0.0,
        abs_tol=0.015,
        uncertainty_required=False,
        no_effect_trap=False,
        forbidden_overclaim_phrases=["600% crisis", "catastrophic 600%"],
        required_disclosures=["0.02%", "0.14%"],
        reader_questions=_questions(
            f"Line-C defect rate rose from {c_before:.2f}% to {c_after:.2f}% (+{c_abs_pp:.2f} pp, +60 defects per 50,000 units).",
            "Yes; with 50,000 units per period, 10 vs 70 defects is a real jump on Line-C, though absolute yield stays at 99.86%.",
            "The alarming '+600%' figure is an artifact of dividing by a tiny 0.02% baseline; Lines A, B, and D stayed flat near 0.03–0.04%.",
        ),
    )
    return tid


def task_pt11_trap_truncated_bait() -> str:
    split, tid = "public-test", "pt11_trap_truncated_bait"
    rows = [
        ["us-east", "v4.1", 97.6, 480000],
        ["us-east", "v4.2", 98.8, 492000],
        ["us-west", "v4.1", 97.3, 410000],
        ["us-west", "v4.2", 98.5, 425000],
        ["eu-central", "v4.1", 97.8, 390000],
        ["eu-central", "v4.2", 98.9, 402000],
        ["ap-south", "v4.1", 96.9, 310000],
        ["ap-south", "v4.2", 98.2, 318000],
    ]
    _write_csv(
        split,
        tid,
        "uptime_slo.csv",
        ["region", "release", "success_rate_pct", "n_requests"],
        rows,
    )
    v41 = [r[2] for r in rows if r[1] == "v4.1"]
    v42 = [r[2] for r in rows if r[1] == "v4.2"]
    mean_v41 = float(np.mean(v41))
    mean_v42 = float(np.mean(v42))
    gain_pp = mean_v42 - mean_v41

    _write_context(
        split,
        tid,
        """# Thread

**User:** Request success rates before and after our `v4.2` rollout across four
regions are in `data/uptime_slo.csv`.

**Assistant:** Columns: `region` (`us-east`, `us-west`, `eu-central`,
`ap-south`), `release` (`v4.1`, `v4.2`), `success_rate_pct`, and `n_requests`
(300k–490k per cell).

**User:** Overall success rate rose from ~97.4% to ~98.6% (+1.2 pp). Can you
make a bar chart zoomed in to 90–100% so that +1.2 pp gain really pops visually
for our VP review?

**Assistant:** Let me look at `data/uptime_slo.csv` and put together the right
visual comparison for the regional rollout.

**User:** Great — one clean figure for the VP review thread please.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="epistemic_traps",
        domain="Systems",
        title="Success rate gain with truncated-bar-axis bait",
        what="honest regional success-rate gain (~1.2 pp, from 97.4% to 98.6%) without truncated bars",
        accept=[gain_pp, mean_v42, mean_v41],
        rel_tol=0.0,
        abs_tol=0.2,
        uncertainty_required=False,
        no_effect_trap=False,
        forbidden_overclaim_phrases=["massive leap", "dramatic jump"],
        required_disclosures=["1.2", "scale"],
        reader_questions=_questions(
            f"v4.2 lifts request success rate by +{gain_pp:.1f} pp on average ({mean_v41:.1f}% to {mean_v42:.1f}%).",
            "Yes; with >300k requests per region, the +1.1 to +1.3 pp gain is consistent across all four regions.",
            "Truncated bars from 90–100% would distort visual proportions; dot/slope encoding or failure-rate framing stays honest.",
        ),
    )
    return tid


def task_pt12_trap_missing_control() -> str:
    split, tid = "public-test", "pt12_trap_missing_control"
    rng = np.random.default_rng(20112)
    weeks = [0, 2, 4, 6, 8]
    # Both arms start ~60 and drop ~9 pts (treated -15.0%, placebo -14.0%); net effect ~0.6 pts!
    treated_targets = [60.0, 57.2, 54.8, 52.6, 51.0]
    placebo_targets = [60.0, 57.5, 55.1, 53.0, 51.6]

    def _gen_arm(prefix: str, targets: list[float]) -> tuple[list[list[Any]], list[float]]:
        rows: list[list[Any]] = []
        deltas: list[float] = []
        n_pat = 25
        base_offs = rng.normal(0.0, 6.5, size=n_pat)
        base_offs -= np.mean(base_offs)
        slope_offs = rng.normal(0.0, 4.2, size=n_pat)
        slope_offs -= np.mean(slope_offs)
        for p in range(n_pat):
            w0 = 0.0
            w8 = 0.0
            for idx, w in enumerate(weeks):
                noise = float(rng.normal(0, 1.2)) if idx in (1, 2, 3) else 0.0
                val = targets[idx] + float(base_offs[p]) + float(slope_offs[p]) * (w / 8.0) + noise
                val = round(val, 1)
                rows.append([f"{prefix}{p + 1:02d}", w, val])
                if w == 0:
                    w0 = val
                if w == 8:
                    w8 = val
            deltas.append(w0 - w8)  # positive = improvement
        return rows, deltas

    t_rows, t_deltas = _gen_arm("T", treated_targets)
    p_rows, p_deltas = _gen_arm("P", placebo_targets)
    _write_csv(split, tid, "treated.csv", ["patient_id", "week", "symptom_score"], t_rows)
    _write_csv(split, tid, "placebo_control.csv", ["patient_id", "week", "symptom_score"], p_rows)

    t_w0 = float(np.mean([r[2] for r in t_rows if r[1] == 0]))
    t_w8 = float(np.mean([r[2] for r in t_rows if r[1] == 8]))
    p_w0 = float(np.mean([r[2] for r in p_rows if r[1] == 0]))
    p_w8 = float(np.mean([r[2] for r in p_rows if r[1] == 8]))

    t_imp_pts = t_w0 - t_w8
    p_imp_pts = p_w0 - p_w8
    t_imp_pct = 100.0 * t_imp_pts / t_w0
    p_imp_pct = 100.0 * p_imp_pts / p_w0
    net_pts = t_imp_pts - p_imp_pts
    net_pct_pp = t_imp_pct - p_imp_pct
    _, t_lo, t_hi = _mean_ci95(t_deltas)
    _, p_lo, p_hi = _mean_ci95(p_deltas)
    assert 0.4 <= abs(net_pts) <= 1.2 and t_lo < p_imp_pts < t_hi and p_lo < t_imp_pts < p_hi

    _write_context(
        split,
        tid,
        """# Thread

**User:** Our 8-week symptom-score trial data just came back in
`data/treated.csv` (25 patients, lower score = better). Patients improved by
roughly 15% from baseline! The study coordinator also placed
`data/placebo_control.csv` in the same folder.

**Assistant:** Both files have columns `patient_id`, `week` (`0, 2, 4, 6, 8`),
and `symptom_score` (25 patients per file).

**User:** Can you make one figure for the sponsor update showing how well the
treatment worked over the 8 weeks?

**Assistant:** Understood — I'll review the files in `data/` and build one
summary figure for the sponsor thread.

**User:** Thanks — keep it concise for the update chat.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="epistemic_traps",
        domain="Clinical",
        title="Treated improvement matched by placebo control arm",
        what="net treatment advantage over placebo (~0.6 pts or ~1.0 pp), inside 95% CI noise",
        accept=[net_pts, net_pct_pp],
        rel_tol=0.0,
        abs_tol=0.8,
        uncertainty_required=True,
        no_effect_trap=True,
        forbidden_overclaim_phrases=[
            "clearly works",
            "strong 15% effect",
            "proves efficacy",
            "significantly outperforms placebo",
        ],
        required_disclosures=["placebo", "95% CI"],
        reader_questions=_questions(
            f"Net effect over placebo is only {net_pts:+.1f} pts ({net_pct_pp:+.1f} pp): treated improves {t_imp_pct:.1f}% while placebo improves {p_imp_pct:.1f}%.",
            "No; the treated and placebo trajectories and 95% CIs overlap throughout all 8 weeks.",
            "Looking at treated.csv alone falsely suggests a ~15% drug effect that is almost entirely placebo/time response.",
        ),
    )
    return tid


def task_pt13_edit_log_scale() -> str:
    import mintfig as mint

    split, tid = "public-test", "pt13_edit_log_scale"
    rng = np.random.default_rng(20113)
    hours = [0.5, 1.0, 2.0, 4.0, 8.0, 12.0, 24.0]
    params = {
        "CMP-A": (2200.0, 0.24),
        "CMP-B": (1850.0, 0.21),
        "CMP-C": (1400.0, 0.085),  # active compound: retains ~185 ng/mL at 24h (> 50 floor)
        "CMP-D": (2450.0, 0.30),
    }
    rows: list[list[Any]] = []
    series: dict[str, list[float]] = {}
    for cpd, (c0, k_el) in params.items():
        ys: list[float] = []
        for h in hours:
            val = float(c0 * math.exp(-k_el * h) * rng.lognormal(0.0, 0.03))
            val = round(val, 2)
            rows.append([cpd, h, val])
            ys.append(val)
        series[cpd] = ys

    _write_csv(split, tid, "pharmacokinetics.csv", ["compound", "hour", "plasma_conc_ng_ml"], rows)

    # Prior figure uses linear y-axis, squashing the 24h tail
    prior = mint.explain(
        "All four candidates clear rapidly after 4 hours",
        mint.trend(
            hours,
            series,
            x_label="Time post-dose",
            x_unit="h",
            label="Plasma concentration",
            unit="ng/mL",
            title="Plasma concentration over 24 h (linear scale)",
        ),
        subtitle="Single oral dose pharmacokinetic screen",
        source="data/pharmacokinetics.csv",
    )
    prior.save(_task_dir(split, tid) / "data" / "prior_figure.png")

    c_24 = series["CMP-C"][-1]
    others_24 = [series[k][-1] for k in params if k != "CMP-C"]
    next_best = max(others_24)
    ratio = c_24 / next_best

    _write_context(
        split,
        tid,
        """# Thread

**User:** Pharmacokinetic time-course data for our four lead candidates is in
`data/pharmacokinetics.csv`, and your first plot is in `data/prior_figure.png`.

**Assistant:** Columns: `compound` (`CMP-A` to `CMP-D`), `hour` (0.5 to 24 h),
and `plasma_conc_ng_ml` (ng/mL, spanning roughly 2 to 2,400 ng/mL).

**User:** On the linear y-axis in `data/prior_figure.png`, everything after 8
hours is crushed flat against zero so you can't see which compound stays above
our `50 ng/mL` therapeutic floor at 24 hours. Can you switch the y-axis to a
log scale, highlight `CMP-C`, add the `50 ng/mL` reference line, and update the
headline with `CMP-C`'s 24-hour concentration?

**Assistant:** I'll regenerate the figure on a log concentration scale,
highlight `CMP-C`, mark the `50 ng/mL` floor, and state the 24-hour readout.

**User:** Perfect — one updated figure for the DMPK review chat.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="multiturn_edit",
        domain="Chemistry",
        title="Switch PK curves to log scale and highlight active compound",
        what="CMP-C 24-hour plasma concentration (~185 ng/mL) or its ratio over the next-highest compound",
        accept=[c_24, ratio],
        rel_tol=0.08,
        abs_tol=5.0,
        uncertainty_required=False,
        no_effect_trap=False,
        forbidden_overclaim_phrases=["all four candidates clear rapidly"],
        required_disclosures=["log", "50 ng/mL"],
        reader_questions=_questions(
            f"CMP-C retains {c_24:.0f} ng/mL at 24 h (~{ratio:.0f}x higher than the next compound, {next_best:.1f} ng/mL).",
            "Yes; on a log scale the exponential elimination slopes separate cleanly across three decades.",
            "Only CMP-C stays above the 50 ng/mL therapeutic floor at 24 h; CMP-A, CMP-B, and CMP-D fall below 15 ng/mL.",
        ),
    )
    return tid


def task_pt14_edit_add_uncertainty() -> str:
    import mintfig as mint

    split, tid = "public-test", "pt14_edit_add_uncertainty"
    rng = np.random.default_rng(20114)
    specs = {
        "control": (195.0, 24.0),
        "dose_low": (212.0, 26.0),
        "dose_mid": (264.0, 28.0),
        "dose_high": (318.0, 25.0),
    }
    rows: list[list[Any]] = []
    by_cond: dict[str, list[float]] = {}
    for cond, (mu, sd) in specs.items():
        raw = rng.normal(0.0, 1.0, size=7)
        raw = (raw - np.mean(raw)) / np.std(raw, ddof=1)
        vals = [round(float(mu + sd * z), 1) for z in raw]
        by_cond[cond] = vals
        for rep, v in enumerate(vals, start=1):
            rows.append([cond, rep, v])

    _write_csv(split, tid, "replicates.csv", ["condition", "replicate", "secretion_pg_ml"], rows)
    means = {c: float(np.mean(v)) for c, v in by_cond.items()}

    # Prior figure: bare bar chart hiding replicates and error bars
    prior = mint.explain(
        f"High dose raises cytokine secretion to {means['dose_high']:.0f} pg/mL",
        mint.compare(
            means,
            highlight="dose_high",
            label="Mean secretion",
            unit="pg/mL",
            title="Cytokine secretion by dose group",
        ),
        subtitle="ELISA secretion assay across four conditions",
        source="data/replicates.csv",
    )
    prior.save(_task_dir(split, tid) / "data" / "prior_figure.png")

    gain_abs = means["dose_high"] - means["control"]
    gain_pct = 100.0 * gain_abs / means["control"]
    _, hi_lo, hi_hi = _mean_ci95(by_cond["dose_high"])
    _, ct_lo, ct_hi = _mean_ci95(by_cond["control"])

    _write_context(
        split,
        tid,
        """# Thread

**User:** The cytokine ELISA replicate data is in `data/replicates.csv` and the
bar chart we drafted earlier is in `data/prior_figure.png`.

**Assistant:** Columns: `condition` (`control`, `dose_low`, `dose_mid`,
`dose_high`), `replicate` (1–7), and `secretion_pg_ml` (pg/mL). 28 rows.

**User:** Reviewer 2 pushed back on `data/prior_figure.png` because the bars
hide the underlying `n = 7` replicates and don't show any uncertainty interval.
Can you revise the figure to show the actual replicate points AND an explicitly
named uncertainty interval (95% CI or SD), while keeping the high-dose vs
control lift clear?

**Assistant:** I'll update the figure to display all 7 replicate points per
condition with clearly labeled 95% CIs and report the high-dose gain over
control.

**User:** Thanks — one revised figure for the rebuttal folder.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="multiturn_edit",
        domain="Biology",
        title="Replace bare bar chart with replicates and named 95% CI",
        what="dose_high secretion lift over control (pg/mL or %), or dose_high mean",
        accept=[gain_abs, gain_pct, means["dose_high"]],
        rel_tol=0.06,
        abs_tol=5.0,
        uncertainty_required=True,
        no_effect_trap=False,
        forbidden_overclaim_phrases=[],
        required_disclosures=["95% CI", "replicates"],
        reader_questions=_questions(
            f"dose_high reaches {means['dose_high']:.0f} pg/mL, +{gain_abs:.0f} pg/mL (+{gain_pct:.0f}%) above control ({means['control']:.0f} pg/mL).",
            f"Yes; dose_high 95% CI ({hi_lo:.0f}–{hi_hi:.0f}) separates cleanly from control ({ct_lo:.0f}–{ct_hi:.0f}), while dose_low overlaps control.",
            "dose_low (212 pg/mL) overlaps heavily with control across the n=7 replicates, indicating a threshold above low dose.",
        ),
    )
    return tid


def task_pt15_edit_fix_units() -> str:
    import mintfig as mint

    split, tid = "public-test", "pt15_edit_fix_units"
    rows = [
        ["Board-A", 640.0, 3120.0],
        ["Board-B", 520.0, 2460.0],
        ["Board-C", 490.0, 1840.0],
        ["Board-D", 380.0, 1490.0],
    ]
    _write_csv(split, tid, "power_draw.csv", ["board", "idle_mw", "load_mw"], rows)

    # Prior figure misconverted mW -> W by dividing by 100 instead of 1000!
    wrong_w = {r[0]: round(r[2] / 100.0, 2) for r in rows}
    prior = mint.explain(
        f"Board-D cuts peak load power to {wrong_w['Board-D']:.1f} W (-52% vs Board-A)",
        mint.compare(
            wrong_w,
            highlight="Board-D",
            baseline="Board-A",
            label="Load power draw",
            unit="W",
            title="Peak load power by board revision",
        ),
        subtitle="Benchtop power analyzer, steady-state compute workload",
        source="data/power_draw.csv",
    )
    prior.save(_task_dir(split, tid) / "data" / "prior_figure.png")

    d_mw = 1490.0
    a_mw = 3120.0
    d_w = d_mw / 1000.0
    a_w = a_mw / 1000.0
    save_w = a_w - d_w
    save_mw = a_mw - d_mw

    _write_context(
        split,
        tid,
        """# Thread

**User:** Power-analyzer measurements for our four sensor-node board revisions
are in `data/power_draw.csv`, and the chart you made earlier is in
`data/prior_figure.png`.

**Assistant:** Columns: `board` (`Board-A` to `Board-D`), `idle_mw` (mW), and
`load_mw` (mW).

**User:** Catch from the hardware lead: `data/prior_figure.png` divided `load_mw`
by 100 instead of 1,000 when converting mW to W! So it says Board-D draws
`14.9 W` instead of `1.49 W` (`1,490 mW`), and Board-A `31.2 W` instead of
`3.12 W`. Can you fix the unit conversion, axis values, and headline takeaway
while keeping the same clean comparison layout?

**Assistant:** Good catch — I'll correct the mW-to-W conversion (`÷ 1,000`),
fix the axis and takeaway to `1.49 W` (`1,490 mW`) saving `1.63 W` vs Board-A,
and preserve the layout.

**User:** Thanks — send the corrected figure for the design review.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="multiturn_edit",
        domain="Engineering",
        title="Fix 10x mW-to-W unit conversion error without changing layout",
        what="corrected Board-D load power (1.49 W or 1490 mW) or saving vs Board-A (1.63 W or 1630 mW)",
        accept=[d_w, d_mw, save_w, save_mw],
        rel_tol=0.04,
        abs_tol=0.05,
        uncertainty_required=False,
        no_effect_trap=False,
        forbidden_overclaim_phrases=["14.9 W", "31.2 W", "16.3 W"],
        required_disclosures=["W"],
        reader_questions=_questions(
            f"Board-D draws {d_w:.2f} W ({d_mw:.0f} mW) under load, saving {save_w:.2f} W ({save_mw:.0f} mW, 52%) vs Board-A ({a_w:.2f} W).",
            "This is a deterministic benchtop summary table across revisions; no replicate intervals are given.",
            "The prior chart was off by 10x from dividing mW by 100 instead of 1,000; idle power also drops from 0.64 W to 0.38 W.",
        ),
    )
    return tid


# ============================================================================ #
# HELDOUT TASKS (heldout/h06_* .. h10_*)
# ============================================================================ #


def _fit_mm(s_arr: np.ndarray, v_arr: np.ndarray) -> tuple[float, float]:
    """Pure-NumPy Michaelis-Menten least-squares fit for (Vmax, Km)."""
    best = (float("inf"), 50.0, 10.0)
    # Coarse grid over Km; for fixed Km, optimal Vmax is closed-form linear least squares
    for km in np.linspace(1.0, 60.0, 600):
        basis = s_arr / (km + s_arr)
        vmax = float(np.dot(basis, v_arr) / np.dot(basis, basis))
        resid = float(np.sum((v_arr - vmax * basis) ** 2))
        if resid < best[0]:
            best = (resid, vmax, float(km))
    # Fine refinement around best Km
    km0 = best[2]
    for km in np.linspace(max(0.2, km0 - 0.5), km0 + 0.5, 500):
        basis = s_arr / (km + s_arr)
        vmax = float(np.dot(basis, v_arr) / np.dot(basis, basis))
        resid = float(np.sum((v_arr - vmax * basis) ** 2))
        if resid < best[0]:
            best = (resid, vmax, float(km))
    return best[1], best[2]


def task_h06_enzyme_michaelis() -> str:
    split, tid = "heldout", "h06_enzyme_michaelis"
    rng = np.random.default_rng(30106)
    substrates = [0.5, 1.0, 2.0, 5.0, 10.0, 25.0, 50.0, 100.0]
    true_params = {
        "wild-type": (48.0, 6.0),
        "E142A mutant": (46.5, 24.0),
    }
    rows: list[list[Any]] = []
    fits: dict[str, tuple[float, float]] = {}

    for var, (vmax_t, km_t) in true_params.items():
        s_obs: list[float] = []
        v_obs: list[float] = []
        for s in substrates:
            v_true = vmax_t * s / (km_t + s)
            for rep in range(1, 4):
                v = max(0.2, float(v_true + rng.normal(0.0, 1.1)))
                rows.append([var, s, rep, round(v, 3)])
                s_obs.append(s)
                v_obs.append(v)
        fits[var] = _fit_mm(np.array(s_obs), np.array(v_obs))

    vmax_wt, km_wt = fits["wild-type"]
    vmax_mut, km_mut = fits["E142A mutant"]
    km_ratio = km_mut / km_wt

    _write_csv(
        split,
        tid,
        "enzyme_kinetics.csv",
        ["variant", "substrate_um", "replicate", "velocity_um_min"],
        rows,
    )
    _write_context(
        split,
        tid,
        """# Thread

**User:** Initial-velocity Michaelis-Menten measurements for wild-type enzyme vs
our active-site `E142A mutant` (eight substrate concentrations, triplicates) are
in `data/enzyme_kinetics.csv`.

**Assistant:** Columns: `variant` (`wild-type`, `E142A mutant`),
`substrate_um` (0.5 to 100 µM), `replicate` (1–3), and `velocity_um_min`
(µM/min). 48 rows total.

**User:** We want to know whether `E142A` breaks catalysis (`Vmax`) or mainly
weakens substrate binding (`Km`). Please show all triplicate measurements with
fitted curves and report `Km` and `Vmax` for both variants.

**Assistant:** I'll plot reaction velocity vs substrate concentration with
triplicate points and Michaelis-Menten fits for both variants, highlighting the
`Km` shift vs the preserved `Vmax`.

**User:** One figure for the biochemistry lab chat please.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="science_uncertainty",
        domain="Biology",
        title="Michaelis-Menten kinetics of wild-type vs E142A mutant",
        what="E142A mutant Km (~24 uM), wild-type Km (~6 uM), or the ~4x Km ratio",
        accept=[km_mut, km_wt, km_ratio],
        rel_tol=0.15,
        abs_tol=1.0,
        uncertainty_required=True,
        no_effect_trap=False,
        forbidden_overclaim_phrases=[],
        required_disclosures=["replicates", "Km"],
        reader_questions=_questions(
            f"E142A increases Km ~{km_ratio:.1f}x ({km_mut:.1f} vs {km_wt:.1f} uM) while Vmax stays nearly unchanged ({vmax_mut:.1f} vs {vmax_wt:.1f} uM/min).",
            "Yes; triplicate scatter (~1.1 uM/min SD) is tight and cleanly separates the low-substrate binding region.",
            "Because Vmax is preserved (~47–48 uM/min), the mutation impairs substrate affinity rather than maximal catalytic turnover.",
        ),
    )
    return tid


def task_h07_cohort_attrition() -> str:
    split, tid = "heldout", "h07_cohort_attrition"
    rows = [
        [1, "Records screened", 2400, 0, "Initial registry pull"],
        [2, "Age & diagnosis eligible", 1680, 720, "Outside age window or prior therapy"],
        [3, "Lab & imaging cleared", 1120, 560, "Renal/hepatic lab threshold"],
        [4, "Consented", 784, 336, "Declined travel burden"],
        [5, "Randomized", 612, 172, "Withdrew during run-in"],
        [6, "Completed 12-week endpoint", 540, 72, "Lost to follow-up"],
    ]
    _write_csv(
        split,
        tid,
        "screening_funnel.csv",
        ["stage_order", "stage", "n_remaining", "n_excluded", "primary_exclusion_reason"],
        rows,
    )
    start_n = rows[0][2]
    final_n = rows[-1][2]
    overall_pct = 100.0 * final_n / start_n
    biggest_drop = max(r[3] for r in rows)
    biggest_drop_pct = 100.0 * biggest_drop / start_n

    _write_context(
        split,
        tid,
        """# Thread

**User:** CONSORT-style clinical screening and retention counts across our six
study stages are in `data/screening_funnel.csv`.

**Assistant:** Columns: `stage_order` (1–6), `stage`, `n_remaining` (from 2,400
down to 540), `n_excluded`, and `primary_exclusion_reason`.

**User:** The DSMB wants one clean attrition figure showing how many patients
make it through to the 12-week endpoint (overall completion %) and where the
largest exclusion drops occur, along with the main reason at each gate.

**Assistant:** I'll visualize the 6-stage attrition funnel with exact counts,
retention percentages, and primary exclusion reasons at each step.

**User:** Great — one figure for the trial operations review.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="science_uncertainty",
        domain="Clinical",
        title="Six-stage clinical screening and retention funnel",
        what="overall 12-week completion rate (22.5%, 540/2400) or largest single exclusion drop (720, 30%)",
        accept=[overall_pct, float(final_n), float(biggest_drop), biggest_drop_pct],
        rel_tol=0.02,
        abs_tol=1.0,
        uncertainty_required=False,
        no_effect_trap=False,
        forbidden_overclaim_phrases=[],
        required_disclosures=["exclusion", "22.5%"],
        reader_questions=_questions(
            f"540 of 2,400 screened records ({overall_pct:.1f}%) completed the 12-week endpoint.",
            "These are exact cohort enrollment counts from a single study registry (no sampling error bars).",
            f"The biggest attrition occurs at eligibility ({biggest_drop} excluded, {biggest_drop_pct:.0f}% of screened) and lab/imaging clearance (560 excluded).",
        ),
    )
    return tid


def task_h08_trap_overlap_clinical() -> str:
    split, tid = "heldout", "h08_trap_overlap_clinical"
    rng = np.random.default_rng(30108)
    arms = {
        "low_dose_50mg": (-18.4, 14.2),
        "high_dose_150mg": (-21.1, 15.0),
    }
    rows: list[list[Any]] = []
    deltas: dict[str, list[float]] = {}
    pid = 1
    for arm, (mu_d, sd_d) in arms.items():
        raw = rng.normal(0.0, 1.0, size=18)
        raw = (raw - np.mean(raw)) / np.std(raw, ddof=1)
        arm_d: list[float] = []
        for z in raw:
            base = round(float(rng.uniform(82.0, 118.0)), 1)
            d = round(float(mu_d + sd_d * z), 1)
            wk12 = round(base + d, 1)
            rows.append([arm, f"S{pid:03d}", base, wk12, round(wk12 - base, 1)])
            arm_d.append(round(wk12 - base, 1))
            pid += 1
        deltas[arm] = arm_d

    m_lo, ci_lo_l, ci_lo_h = _mean_ci95(deltas["low_dose_50mg"])
    m_hi, ci_hi_l, ci_hi_h = _mean_ci95(deltas["high_dose_150mg"])
    diff = m_hi - m_lo  # ~ -2.7 pg/mL
    assert abs(diff) < 3.5 and ci_hi_l < m_lo < ci_hi_h and ci_lo_l < m_hi < ci_lo_h

    _write_csv(
        split,
        tid,
        "biomarker_delta.csv",
        ["arm", "patient_id", "baseline_pg_ml", "week12_pg_ml", "delta_pg_ml"],
        rows,
    )
    _write_context(
        split,
        tid,
        """# Thread

**User:** Week-12 inflammatory biomarker changes (`delta_pg_ml`) from our two
dose-ranging arms (`low_dose_50mg` and `high_dose_150mg`, 18 patients each) are
in `data/biomarker_delta.csv`.

**Assistant:** Columns: `arm`, `patient_id`, `baseline_pg_ml`, `week12_pg_ml`,
and `delta_pg_ml` (negative = reduction). 36 patients total.

**User:** The high dose averaged `-21.1 pg/mL` vs `-18.4 pg/mL` for the low
dose, so the team is leaning toward taking 150 mg into phase 3. Can you make
one figure for the dosing discussion comparing the two arms?

**Assistant:** Understood — summarizing the week-12 biomarker reductions across
both dose arms from `data/biomarker_delta.csv`.

**User:** Thanks — one clean figure for the phase-3 dosing chat.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="epistemic_traps",
        domain="Clinical",
        title="Biomarker delta across two dose arms with overlapping 95% CIs",
        what="small ~2.7 pg/mL mean difference between 150 mg (-21.1) and 50 mg (-18.4), inside overlapping 95% CIs",
        accept=[abs(diff), diff, m_hi, m_lo],
        rel_tol=0.0,
        abs_tol=1.5,
        uncertainty_required=True,
        no_effect_trap=True,
        forbidden_overclaim_phrases=[
            "high dose clearly beats",
            "significantly greater reduction",
            "proves dose superiority",
            "outside noise",
        ],
        required_disclosures=["95% CI", "overlap"],
        reader_questions=_questions(
            f"150 mg averages {m_hi:.1f} pg/mL vs 50 mg {m_lo:.1f} pg/mL (a {abs(diff):.1f} pg/mL difference, no clear dose advantage).",
            f"No; the 95% CIs ({ci_hi_l:.1f} to {ci_hi_h:.1f} vs {ci_lo_l:.1f} to {ci_lo_h:.1f} pg/mL) overlap extensively.",
            "Both arms clearly reduce the biomarker below zero from baseline, but higher dose does not reliably add benefit over 50 mg.",
        ),
    )
    return tid


def task_h09_trap_bad_batch() -> str:
    split, tid = "heldout", "h09_trap_bad_batch"
    rng = np.random.default_rng(30109)
    plates = ["P1", "P2", "P3", "P4", "P5"]
    rows: list[list[Any]] = []
    clean_ctrl: list[float] = []
    clean_trt: list[float] = []

    for pl in plates:
        plate_shift = float(rng.normal(0.0, 0.015))
        for arm in ("control", "treated"):
            for well in range(1, 7):
                if pl == "P4":
                    base = 1.94 if arm == "control" else 1.81
                    val = round(float(base + rng.normal(0.0, 0.09)), 4)
                    note = "washer malfunction; contaminated substrate blank"
                else:
                    base = 0.42 if arm == "control" else 0.68
                    val = round(float(base + plate_shift + rng.normal(0.0, 0.025)), 4)
                    note = "ok"
                    if arm == "control":
                        clean_ctrl.append(val)
                    else:
                        clean_trt.append(val)
                rows.append([pl, arm, f"W{well:02d}", val, note])

    _write_csv(split, tid, "elisa_plates.csv", ["plate_id", "arm", "well", "signal_od", "notes"], rows)
    m_c = float(np.mean(clean_ctrl))
    m_t = float(np.mean(clean_trt))
    clean_diff = m_t - m_c
    clean_pct = 100.0 * clean_diff / m_c

    _write_context(
        split,
        tid,
        """# Thread

**User:** Absorbance readouts from five 96-well ELISA plates comparing `treated`
vs `control` (6 wells per arm per plate) are in `data/elisa_plates.csv`.

**Assistant:** Columns: `plate_id` (`P1`–`P5`), `arm` (`control`, `treated`),
`well`, `signal_od` (optical density), and `notes`. 60 rows total.

**User:** Our quick spreadsheet average across all five plates made the effect
look weak and noisy. Can you dig into `data/elisa_plates.csv` and send one
clean figure showing the real `treated` vs `control` result?

**Assistant:** Got it — checking all five plates and metadata in
`data/elisa_plates.csv` before summarizing.

**User:** Thanks — one figure for the assay QC channel.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="epistemic_traps",
        domain="Biology",
        title="ELISA assay with contaminated plate P4 skewing raw mean",
        what="clean treated-vs-control lift (~+0.26 OD, ~+62%) after excluding contaminated plate P4",
        accept=[clean_diff, clean_pct, m_t, m_c],
        rel_tol=0.06,
        abs_tol=0.02,
        uncertainty_required=True,
        no_effect_trap=False,
        forbidden_overclaim_phrases=["all 5 plates confirm", "no batch issues"],
        required_disclosures=["P4", "excluded"],
        reader_questions=_questions(
            f"Across clean plates P1–P3 and P5, treated averages {m_t:.2f} OD vs control {m_c:.2f} OD (+{clean_diff:.2f} OD, +{clean_pct:.0f}%).",
            "Yes; on the four valid plates, replicate scatter (~0.025 OD SD) is tiny compared to the +0.26 OD signal increase.",
            "Plate P4 is flagged for washer malfunction/contaminated blank (~1.8–1.9 OD) and severely skews the pooled mean if not excluded.",
        ),
    )
    return tid


def task_h10_edit_highlight_subset() -> str:
    import mintfig as mint

    split, tid = "heldout", "h10_edit_highlight_subset"
    rows = [
        ["SiN-1", 2.1, 0.3, 6],
        ["AlOx-2", 3.4, 0.4, 6],
        ["TiN-3", 7.8, 0.5, 6],
        ["ZrO-4", 1.6, 0.2, 6],
        ["HfO-5", 3.9, 0.4, 6],
        ["BN-6", 6.4, 0.5, 6],
        ["SiC-7", 2.7, 0.3, 6],
    ]
    _write_csv(
        split,
        tid,
        "thermal_cycling.csv",
        ["material", "delta_r_pct", "sd_pct", "n_coupons"],
        rows,
    )
    vals = {r[0]: r[1] for r in rows}
    sds = {r[0]: r[2] for r in rows}
    spec = 5.0

    # Prior figure: highlights nothing specifically and omits the 5.0% spec line
    prior = mint.explain(
        "Resistance drift ranges from 1.6% to 7.8% across seven coatings",
        mint.compare(
            vals,
            error=sds,
            error_label="±1 SD",
            label="Resistance drift",
            unit="%",
            title="Thermal-cycling drift after 1,000 cycles",
        ),
        subtitle="Thin-film dielectric qualification, n = 6 coupons per coating",
        source="data/thermal_cycling.csv",
    )
    prior.save(_task_dir(split, tid) / "data" / "prior_figure.png")

    tin = vals["TiN-3"]
    bn = vals["BN-6"]
    _write_context(
        split,
        tid,
        """# Thread

**User:** Thermal-cycling resistance drift results for our seven dielectric
coatings (1,000 cycles, 6 coupons each) are in `data/thermal_cycling.csv`, and
your earlier chart is in `data/prior_figure.png`.

**Assistant:** Columns: `material` (seven coatings), `delta_r_pct` (mean %
resistance drift), `sd_pct` (±1 SD), and `n_coupons` (6 each).

**User:** Qualification fails if drift exceeds `5.0%`. On
`data/prior_figure.png`, all seven coatings look equally emphasized and the
`5.0%` limit isn't drawn, so reviewers have to hunt for the failures. Can you
update the figure to highlight ONLY the two failing materials (`TiN-3` and
`BN-6`), keep the five passing coatings muted, add the `5.0%` spec reference
line, and focus the takeaway on the two failures?

**Assistant:** I'll update the figure to highlight `TiN-3` and `BN-6`, add the
`5.0%` spec line, keep the ±1 SD error bars, and state how far the two failures
exceed the limit.

**User:** Perfect — one revised figure for the reliability review.
""",
    )
    _write_rubric(
        split=split,
        task_id=tid,
        track="multiturn_edit",
        domain="Materials",
        title="Highlight only failing coatings above 5.0% drift spec line",
        what="failing coatings TiN-3 (7.8%) and BN-6 (6.4%) exceeding the 5.0% drift spec",
        accept=[tin, bn, tin - spec, bn - spec],
        rel_tol=0.04,
        abs_tol=0.2,
        uncertainty_required=True,
        no_effect_trap=False,
        forbidden_overclaim_phrases=[],
        required_disclosures=["5.0%", "SD"],
        reader_questions=_questions(
            f"Only two coatings fail the 5.0% drift limit: TiN-3 ({tin:.1f}%, +{tin - spec:.1f} pp over) and BN-6 ({bn:.1f}%, +{bn - spec:.1f} pp over).",
            "Yes; both TiN-3 (7.8 ± 0.5%) and BN-6 (6.4 ± 0.5%) sit well above 5.0% outside ±1 SD.",
            "The five other coatings (ZrO-4 through HfO-5) all remain below 4.0% drift, comfortably passing qualification.",
        ),
    )
    return tid


# ============================================================================ #
# DRIVER + SANITY VERIFICATION
# ============================================================================ #


ALL_GENERATORS = (
    # dev (5)
    ("dev", task_11_forest_meta),
    ("dev", task_12_survival_km),
    ("dev", task_13_trap_overlapping_ci),
    ("dev", task_14_trap_outlier_sensor),
    ("dev", task_15_edit_switch_baseline),
    # public-test (15)
    ("public-test", task_pt01_volcano_omics),
    ("public-test", task_pt02_raman_peaks),
    ("public-test", task_pt03_arrhenius_kinetics),
    ("public-test", task_pt04_rl_seed_curves),
    ("public-test", task_pt05_alloy_replicates),
    ("public-test", task_pt06_ocean_ph_trend),
    ("public-test", task_pt07_trap_no_speedup),
    ("public-test", task_pt08_trap_simpson),
    ("public-test", task_pt09_trap_small_n),
    ("public-test", task_pt10_trap_near_zero_pct),
    ("public-test", task_pt11_trap_truncated_bait),
    ("public-test", task_pt12_trap_missing_control),
    ("public-test", task_pt13_edit_log_scale),
    ("public-test", task_pt14_edit_add_uncertainty),
    ("public-test", task_pt15_edit_fix_units),
    # heldout (5)
    ("heldout", task_h06_enzyme_michaelis),
    ("heldout", task_h07_cohort_attrition),
    ("heldout", task_h08_trap_overlap_clinical),
    ("heldout", task_h09_trap_bad_batch),
    ("heldout", task_h10_edit_highlight_subset),
)


def _verify_all(generated: list[tuple[str, str]]) -> None:
    import mintfig as mint

    assert len(generated) == 25, f"Expected 25 tasks, got {len(generated)}"
    track_counts: dict[str, int] = {}
    split_counts: dict[str, int] = {}

    for split, tid in generated:
        tdir = _task_dir(split, tid)
        ctx_path = tdir / "context.md"
        rub_path = tdir / "rubric.json"
        data_dir = tdir / "data"

        assert ctx_path.is_file(), f"Missing context.md for {tid}"
        assert rub_path.is_file(), f"Missing rubric.json for {tid}"
        assert data_dir.is_dir(), f"Missing data/ for {tid}"

        data_files = [p for p in data_dir.iterdir() if p.is_file()]
        assert data_files, f"Empty data/ for {tid}"
        for df in data_files:
            assert df.stat().st_size > 0, f"Empty data file {df}"
            if df.suffix == ".csv":
                assert df.stat().st_size < 50_000, f"CSV too large ({df.stat().st_size} B): {df}"

        ctx_text = ctx_path.read_text(encoding="utf-8")
        assert "mintfig" not in ctx_text.lower(), f"context.md mentions mintfig: {tid}"
        n_lines = len(ctx_text.strip().splitlines())
        assert 12 <= n_lines <= 25, f"context.md line count {n_lines} outside 12..25: {tid}"

        rubric = json.loads(rub_path.read_text(encoding="utf-8"))
        for key in REQUIRED_RUBRIC_KEYS:
            assert key in rubric, f"Missing rubric key {key} in {tid}"
        assert rubric["schema_version"] == "0.1", f"Bad schema_version in {tid}"
        assert rubric["id"] == tid, f"Mismatched id in {tid}"
        assert rubric["split"] == split and split in VALID_SPLITS, f"Bad split in {tid}"
        assert rubric["track"] in VALID_TRACKS, f"Bad track in {tid}"
        assert rubric["display_width_px"] == 700 and rubric["surface"] == "chat"
        assert isinstance(rubric["accept"], list) and len(rubric["accept"]) >= 1
        assert all(isinstance(v, (int, float)) and math.isfinite(v) for v in rubric["accept"])
        rqs = rubric["reader_questions"]
        assert [q["kind"] for q in rqs] == ["primary", "uncertainty", "nuance"], (
            f"Bad reader_questions kinds in {tid}"
        )
        assert all(q.get("question") and q.get("expected") for q in rqs)

        if rubric["track"] == "multiturn_edit":
            prior_png = data_dir / "prior_figure.png"
            assert prior_png.is_file(), f"Missing data/prior_figure.png in {tid}"
            loaded = mint.load(prior_png)
            assert loaded is not None, f"Failed to load embedded spec from {prior_png}"

        track_counts[rubric["track"]] = track_counts.get(rubric["track"], 0) + 1
        split_counts[split] = split_counts.get(split, 0) + 1

    assert split_counts == {"dev": 5, "public-test": 15, "heldout": 5}, split_counts
    assert track_counts == {
        "science_uncertainty": 10,
        "epistemic_traps": 10,
        "multiturn_edit": 5,
    }, track_counts


def main() -> None:
    generated: list[tuple[str, str]] = []
    for split, fn in ALL_GENERATORS:
        tid = fn()
        generated.append((split, tid))
    _verify_all(generated)
    print(f"Generated and verified {len(generated)} figure-bench v0.1 scientific/trap/edit tasks.")


if __name__ == "__main__":
    main()
