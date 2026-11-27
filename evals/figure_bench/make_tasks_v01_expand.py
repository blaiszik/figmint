"""Upgrade the 15 legacy tasks to canonical rubric.json v0.1 and generate 40 new deterministic tasks
to bring figure-bench v0.1 from 60 to 100 tasks (25 dev / 50 public-test / 25 heldout).

Deterministic (fixed NumPy seeds per task). Re-running produces identical data files,
prior_figure.png / broken_plot.py assets, context.md threads, and rubric.json files.

New task inventory (40 tasks):
  - dev (10):          16_..25_  (1 sci, 2 swe, 2 trap, 2 edit, 2 surface, 1 repair)
  - public-test (20):  pt31_..pt50_ (4 sci, 4 swe, 4 trap, 3 edit, 2 surface, 3 repair)
  - heldout (10):      h16_..h25_ (2 sci, 2 swe, 2 trap, 1 edit, 2 surface, 1 repair)

Usage:
    PYTHONPATH=src MPLCONFIGDIR=/tmp/mpl-mintfig python evals/figure_bench/make_tasks_v01_expand.py
"""

from __future__ import annotations

import csv
import json
import math
import textwrap
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
SPLIT_DIRS = {
    "dev": HERE / "tasks",
    "public-test": HERE / "public_test",
    "heldout": HERE / "heldout",
}


def _task_dir(split: str, task_id: str) -> Path:
    d = SPLIT_DIRS[split] / task_id
    (d / "data").mkdir(parents=True, exist_ok=True)
    return d


def _write_csv(root: Path, filename: str, header: list[str], rows: list[list[Any]]) -> Path:
    path = root / "data" / filename
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for row in rows:
            w.writerow(["" if v is None else (round(v, 6) if isinstance(v, float) else v) for v in row])
    return path


def _write_json(root: Path, filename: str, payload: Any) -> Path:
    path = root / "data" / filename
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _write_context(root: Path, text: str) -> Path:
    path = root / "context.md"
    path.write_text(textwrap.dedent(text).strip() + "\n", encoding="utf-8")
    return path


def _write_script(root: Path, filename: str, text: str) -> Path:
    path = root / filename
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    return path


def _write_rubric(
    root: Path,
    *,
    task_id: str,
    split: str,
    track: str,
    domain: str,
    title: str,
    what: str,
    accept: list[float],
    rel_tol: float,
    abs_tol: float,
    uncertainty_required: bool,
    no_effect_trap: bool = False,
    forbidden_overclaim_phrases: list[str] | None = None,
    required_disclosures: list[str] | None = None,
    reader_questions: list[dict[str, str]],
    display_width_px: int = 700,
    surface: str = "chat",
    forbid_truncated_bars: bool = False,
    require_log_scale: bool = False,
    min_panels: int = 0,
) -> Path:
    rub = {
        "schema_version": "0.1",
        "id": task_id,
        "split": split,
        "track": track,
        "domain": domain,
        "title": title,
        "display_width_px": int(display_width_px),
        "surface": surface,
        "what": what,
        "accept": [round(float(v), 6) for v in accept],
        "rel_tol": float(rel_tol),
        "abs_tol": float(abs_tol),
        "uncertainty_required": bool(uncertainty_required),
        "no_effect_trap": bool(no_effect_trap),
        "forbidden_overclaim_phrases": list(forbidden_overclaim_phrases or []),
        "required_disclosures": list(required_disclosures or []),
        **({"forbid_truncated_bars": True} if forbid_truncated_bars else {}),
        **({"require_log_scale": True} if require_log_scale else {}),
        **({"min_panels": int(min_panels)} if min_panels > 0 else {}),
        "reader_questions": reader_questions,
    }
    path = root / "rubric.json"
    path.write_text(json.dumps(rub, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _rqs(primary_q: str, primary_a: str, unc_q: str, unc_a: str, nuance_q: str, nuance_a: str) -> list[dict[str, str]]:
    return [
        {"kind": "primary", "question": primary_q, "expected": primary_a},
        {"kind": "uncertainty", "question": unc_q, "expected": unc_a},
        {"kind": "nuance", "question": nuance_q, "expected": nuance_a},
    ]


# ===========================================================================
# PART 0: Upgrade the 15 legacy tasks to canonical rubric.json v0.1 files
# ===========================================================================


def upgrade_legacy_15_rubrics() -> int:
    """Write canonical rubric.json files for the 15 original tasks, preserving answers.json ground truth."""
    answers = json.loads((HERE / "answers.json").read_text(encoding="utf-8"))
    specs: dict[str, dict[str, Any]] = {
        "01_ablation": {
            "split": "dev", "track": "science_uncertainty", "domain": "ML Evaluation",
            "title": "RAG pipeline 5-seed ablation sweep",
            "uncertainty_required": True,
            "required_disclosures": ["5 seeds|n=5|seed|s.d.|sd|±|ci"],
            "reader_questions": _rqs(
                "How many points of accuracy does the model lose when the reranker is removed?",
                "About 1.6 points (from ~82.1% down to ~80.5%).",
                "How is run-to-run variability represented?",
                "Across 5 seeds (individual seed points and/or mean ± SD/CI).",
                "Which component causes the largest drop when removed?",
                "Dropping retrieval causes the largest drop, whereas the bigger encoder adds only ~0.5 points.",
            ),
        },
        "02_ab_latency": {
            "split": "dev", "track": "swe_coding", "domain": "Web Systems",
            "title": "Checkout A/B right-skewed latency comparison",
            "uncertainty_required": False,
            "required_disclosures": ["median|p50", "tail|p95|p99|skew|iqr"],
            "reader_questions": _rqs(
                "By how much did the new checkout flow change median latency (in ms or %)?",
                "Median latency fell by ~83.5 ms (~19.7%, from ~424 ms to ~341 ms).",
                "What spread or tail information is shown across the 400 sessions per arm?",
                "Distribution spread (IQR / percentiles / tail points across 400 sessions per arm).",
                "Why are medians emphasized over means?",
                "Checkout latencies are right-skewed with a long upper tail.",
            ),
        },
        "03_dose_response": {
            "split": "dev", "track": "science_uncertainty", "domain": "Pharmacology",
            "title": "Kinase panel 4-compound dose–response curves",
            "uncertainty_required": True,
            "require_log_scale": True,
            "required_disclosures": ["ic50|ic_50|50%", "triplicate|3 replicate|n=3|s.d.|sd|±|ci"],
            "reader_questions": _rqs(
                "What is the IC50 (the concentration giving 50% inhibition) of the most potent compound, in nM?",
                "About 12 nM (11.6 nM).",
                "How are replicate measurements represented?",
                "Triplicates (n = 3 per concentration) shown via points and/or error bars.",
                "Why is concentration plotted on a logarithmic axis?",
                "Concentrations span 0.1 to 3000 nM in half-log steps across 4+ orders of magnitude.",
            ),
        },
        "04_battery_fade": {
            "split": "dev", "track": "science_uncertainty", "domain": "Materials / Energy",
            "title": "Electrolyte additive coin-cell cycle-life retention",
            "uncertainty_required": False,
            "required_disclosures": ["80%|eol|end of life"],
            "reader_questions": _rqs(
                "At about which cycle number does the baseline electrolyte reach 80% capacity retention?",
                "Around cycle 458 (~450–460 cycles).",
                "How many cells per electrolyte are summarized?",
                "4 coin cells per electrolyte (BL-1..4, FEC-1..4, VC-1..4).",
                "How do the FEC and VC additives compare to baseline?",
                "Both additives extend cycle life well past baseline's 80% end-of-life threshold.",
            ),
        },
        "05_retrofit": {
            "split": "dev", "track": "science_uncertainty", "domain": "Building Energy",
            "title": "Campus HVAC retrofit daily electricity savings",
            "uncertainty_required": False,
            "required_disclosures": ["gym|control|comparison", "2026-07-16|jul 16|july 16|retrofit"],
            "reader_questions": _rqs(
                "By what percentage did the Lab annex's daily electricity use fall after the retrofit?",
                "About 29% (~1,491 kWh/day saved).",
                "How is the 4-day Gym meter gap handled?",
                "Shown as a gap/missing data without fake zero interpolation.",
                "What did the unretrofitted Gym show over the same period?",
                "The Gym stayed roughly flat, confirming the Lab annex drop was due to the retrofit rather than weather.",
            ),
        },
        "06_energy_mix": {
            "split": "dev", "track": "science_uncertainty", "domain": "Climate / Grid",
            "title": "Regional 2025 grid generation mix excluding biomass",
            "uncertainty_required": False,
            "required_disclosures": ["biomass", "wind|solar|hydro|renewable"],
            "reader_questions": _rqs(
                "What share of generation is renewable when only wind, solar and hydro count (biomass excluded), in %?",
                "33.7% (about 34%).",
                "Which generation sources make up the non-biomass renewable share?",
                "Wind, solar, and hydro combined.",
                "Why did the figure have to be revised from the prior draft?",
                "The prior draft counted biomass as renewable, inflating the renewable share.",
            ),
        },
        "07_gene_change": {
            "split": "dev", "track": "science_uncertainty", "domain": "Genomics",
            "title": "RNA-seq 24 h p53 target vs proliferation fold change",
            "uncertainty_required": True,
            "required_disclosures": ["p53", "replicate|n=3|triplicate|s.d.|sd|±|ci|tpm"],
            "reader_questions": _rqs(
                "What is the fold change of CDKN1A, or the typical fold change of the p53 target genes?",
                "CDKN1A rises ~7.0×; p53 targets rise ~2.5× median while proliferation genes fall to ~0.55×.",
                "How many biological replicates back each gene?",
                "3 replicates per condition (vehicle vs drug 24h).",
                "How did housekeeping genes behave?",
                "Housekeeping genes stayed near 1× (no change), validating normalization.",
            ),
        },
        "08_hall_petch": {
            "split": "dev", "track": "science_uncertainty", "domain": "Materials Science",
            "title": "Hall–Petch grain-refinement yield strength scaling",
            "uncertainty_required": False,
            "required_disclosures": ["cu-zn", "hall|d^-1/2|d⁻¹/²|d^(-1/2)|slope|r²|r2"],
            "reader_questions": _rqs(
                "What is the Hall–Petch slope for the Cu-Zn alloy, in MPa·µm½?",
                "About 327 MPa·µm½ (r ≈ 0.97, R² ≈ 0.94).",
                "How many tensile specimens per alloy are plotted?",
                "12 specimens per alloy family across Al-Mg, Cu-Zn, and Ni-Cr.",
                "Do all three alloys follow linear Hall–Petch scaling in d⁻¹/²?",
                "Yes, with Cu-Zn showing the steepest Hall–Petch strengthening slope.",
            ),
        },
        "09_eval_matrix": {
            "split": "dev", "track": "swe_coding", "domain": "ML Evaluation",
            "title": "Multilingual 6×5 checkpoint evaluation matrix",
            "uncertainty_required": False,
            "required_disclosures": ["swahili", "math"],
            "reader_questions": _rqs(
                "What is the new checkpoint's accuracy on Swahili math, in %?",
                "45.4% (+16.8 points up from 28.6%).",
                "How are gains over the previous checkpoint shown?",
                "Comparing new vs previous checkpoint across all 30 language × task cells.",
                "Did the new checkpoint regress on any language-task cell?",
                "No major regression; Swahili math had the biggest gain from the previous blocker.",
            ),
        },
        "10_incident": {
            "split": "dev", "track": "swe_coding", "domain": "Site Reliability",
            "title": "Mid-November pager storm log-scale error rates",
            "uncertainty_required": False,
            "require_log_scale": True,
            "required_disclosures": ["payments", "log|orders of magnitude|271|spike"],
            "reader_questions": _rqs(
                "What was the peak error rate of the payments service?",
                "About 2.1% (0.0209, ~271× its baseline rate).",
                "Why is a logarithmic y-axis used?",
                "Normal baseline error rates span two orders of magnitude (1e-5 to 1e-3) across the five services.",
                "Which service triggered the incident versus remaining near baseline?",
                "Payments spiked dramatically while the other four services remained near their normal baselines.",
            ),
        },
        "h1_survey": {
            "split": "heldout", "track": "science_uncertainty", "domain": "People Analytics",
            "title": "Employee engagement survey satisfaction by department",
            "uncertainty_required": True,
            "required_disclosures": ["support", "n=|respondent|ci|margin|interval|40|160"],
            "reader_questions": _rqs(
                "What share of Support staff are satisfied or very satisfied, in %?",
                "41.7% (~42%).",
                "How is sampling uncertainty across varying department sizes communicated?",
                "Sample sizes (n ≈ 40–160) and/or 95% binomial confidence intervals.",
                "Is Support's low satisfaction outside sampling noise?",
                "Yes, Support sits clearly below the other departments even accounting for sample size.",
            ),
        },
        "h2_spectra": {
            "split": "heldout", "track": "science_uncertainty", "domain": "Spectroscopy",
            "title": "UV-vis absorption peak shift across annealing temperatures",
            "uncertainty_required": False,
            "required_disclosures": ["400", "200|reference|unannealed|nm"],
            "reader_questions": _rqs(
                "By how many nm does the 400 °C sample's absorption peak shift relative to the unannealed sample?",
                "Red-shifted by +25 nm (peak at ~545 nm vs ~520 nm reference).",
                "What wavelengths and resolution were measured?",
                "400–700 nm in 5 nm steps across three samples.",
                "Did the 200 °C anneal shift the peak?",
                "No meaningful shift at 200 °C; the red shift only appears at 400 °C.",
            ),
        },
        "h3_wait_times": {
            "split": "heldout", "track": "science_uncertainty", "domain": "Healthcare Ops",
            "title": "Emergency department wait times by hospital and triage level",
            "uncertainty_required": False,
            "required_disclosures": ["south", "north", "triage"],
            "reader_questions": _rqs(
                "At triage level 3, how many minutes longer is the median wait at South than at North?",
                "About 10.3 minutes longer (~49.3 min at South vs ~39.0 min at North).",
                "How is wait-time skewness represented?",
                "Medians with IQR/spread rather than means alone.",
                "Is South slower across all triage levels?",
                "No — urgent triage levels 1–2 are similar; South is slower only for less urgent levels 3–5.",
            ),
        },
        "h4_scaling": {
            "split": "heldout", "track": "swe_coding", "domain": "ML Scaling",
            "title": "Log–log compute scaling laws across architecture families",
            "uncertainty_required": False,
            "require_log_scale": True,
            "required_disclosures": ["mixture-of-experts|moe", "log|exponent|slope|power"],
            "reader_questions": _rqs(
                "What is the mixture-of-experts scaling exponent (the log–log slope of loss against compute)?",
                "About −0.0625 (or 0.063 magnitude).",
                "What compute range is fitted?",
                "9 compute budgets from 1e18 to 1e22 training FLOPs per architecture family.",
                "How do dense and recurrent architectures compare?",
                "Mixture-of-experts has the steepest loss decay with compute, outscaling both dense and recurrent models.",
            ),
        },
        "h5_budget": {
            "split": "heldout", "track": "science_uncertainty", "domain": "Public Finance",
            "title": "City FY2025 to FY2026 departmental budget changes",
            "uncertainty_required": False,
            "required_disclosures": ["libraries"],
            "reader_questions": _rqs(
                "By what percentage is the Libraries department's budget cut?",
                "About −18.0%.",
                "How are the 12 departments compared?",
                "Percentage or dollar change from FY2025 to FY2026 across all 12 departments.",
                "Did most departments change drastically or stay roughly flat?",
                "Most departments stayed roughly flat, with Libraries taking the steepest percentage cut.",
            ),
        },
    }

    written = 0
    for tid, meta in specs.items():
        ans = answers[tid]
        root = SPLIT_DIRS[meta["split"]] / tid
        _write_rubric(
            root,
            task_id=tid,
            split=meta["split"],
            track=meta["track"],
            domain=meta["domain"],
            title=meta["title"],
            what=ans["what"],
            accept=ans["accept"],
            rel_tol=ans["rel_tol"],
            abs_tol=ans["abs_tol"],
            uncertainty_required=meta["uncertainty_required"],
            required_disclosures=meta["required_disclosures"],
            reader_questions=meta["reader_questions"],
            require_log_scale=meta.get("require_log_scale", False),
        )
        written += 1
    return written


# ===========================================================================
# PART 1: 10 new DEV tasks (16_..25_)
# ===========================================================================


def make_16_calibration_reliability() -> None:
    tid, split = "16_calibration_reliability", "dev"
    root = _task_dir(split, tid)
    rng = np.random.default_rng(1601)
    bins = np.linspace(0.05, 0.95, 10)
    rows = []
    ece_map: dict[str, float] = {}
    for model, bias_fn in [
        ("uncalibrated_resnet", lambda p: np.clip(0.5 + 0.62 * (p - 0.5) - 0.06 * np.sin(np.pi * p), 0.02, 0.98)),
        ("temp_scaled", lambda p: np.clip(p + rng.normal(0.0, 0.012), 0.02, 0.98)),
    ]:
        total_n = 0
        weighted_err = 0.0
        for b in bins:
            n = int(rng.integers(140, 320))
            true_p = float(bias_fn(b))
            k = int(rng.binomial(n, true_p))
            emp = k / n
            se = math.sqrt(max(emp * (1.0 - emp), 1e-6) / n)
            ci95 = 1.96 * se
            total_n += n
            weighted_err += n * abs(emp - b)
            rows.append([model, round(float(b), 2), n, k, round(emp, 4), round(ci95, 4)])
        ece_map[model] = 100.0 * weighted_err / total_n

    ece_raw = ece_map["uncalibrated_resnet"]
    ece_cal = ece_map["temp_scaled"]
    ece_drop = ece_raw - ece_cal
    _write_csv(root, "calibration_bins.csv", ["model", "mean_pred_prob", "n_samples", "n_positive", "empirical_freq", "ci95_half"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** We evaluated temperature scaling on our fraud classifier (`data/calibration_bins.csv`).
        Both models have the exact same AUROC (0.91), so accuracy alone won't show why calibration matters.

        **Assistant:** Columns: `model` (`uncalibrated_resnet`, `temp_scaled`), `mean_pred_prob` (10 decile bins),
        `n_samples`, `n_positive`, `empirical_freq`, and `ci95_half` (binomial 95% CI half-width).

        **User:** Can you plot a reliability diagram comparing both models against the perfect-calibration diagonal
        and quantify how much temperature scaling cuts Expected Calibration Error (ECE)?
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="science_uncertainty", domain="ML Calibration",
        title="Classifier reliability diagram and ECE reduction",
        what=f"Temperature scaling cuts ECE from {ece_raw:.1f}% to {ece_cal:.1f}% (drop {ece_drop:.1f} pp)",
        accept=[ece_cal, ece_raw, ece_drop, ece_raw / max(ece_cal, 1e-6)],
        rel_tol=0.12, abs_tol=0.4, uncertainty_required=True,
        required_disclosures=["ece|calibration error", "95% ci|ci|n=|binomial|error bar|±"],
        reader_questions=_rqs(
            "How much does temperature scaling reduce Expected Calibration Error (ECE)?",
            f"From {ece_raw:.1f}% down to {ece_cal:.1f}% (a {ece_drop:.1f} pp reduction).",
            "How is bin-level sampling uncertainty shown?",
            "95% binomial confidence intervals (and sample counts per bin).",
            "Where is the uncalibrated model most overconfident?",
            "In the high-probability tail (0.75–0.95) where empirical positive rates fall well below the diagonal.",
        ),
    )


def make_17_gpu_roofline_kernels() -> None:
    tid, split = "17_gpu_roofline_kernels", "dev"
    root = _task_dir(split, tid)
    peak_tflops = 989.0
    bw_tbs = 3.35
    ridge = peak_tflops / bw_tbs  # ~295.2 FLOP/byte
    kernels = [
        ("rmsnorm_v1", 2.4, 5.1, "memory"),
        ("softmax_fused", 5.8, 16.4, "memory"),
        ("rope_apply", 1.9, 5.4, "memory"),
        ("flash_attn_fwd", 118.0, 342.0, "memory"),
        ("gemm_fp16_tile", 420.0, 792.0, "compute"),
        ("moe_grouped_gemm", 340.0, 488.0, "compute"),
    ]
    rows = []
    for name, ai, achieved, regime in kernels:
        roof = min(peak_tflops, bw_tbs * ai)
        eff = 100.0 * achieved / roof
        rows.append([name, ai, achieved, round(roof, 2), round(eff, 1), regime])
    _write_csv(root, "roofline_kernels.csv", ["kernel", "arith_intensity_flop_per_byte", "achieved_tflops", "roof_tflops", "roof_efficiency_pct", "regime"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** We profiled six Triton/CUDA kernels on an H100 (`peak = 989 TFLOP/s`, HBM bandwidth `3.35 TB/s`,
        ridge point `~295 FLOP/byte`). Measurements are in `data/roofline_kernels.csv`.

        **Assistant:** Columns: `kernel`, `arith_intensity_flop_per_byte`, `achieved_tflops`, `roof_tflops`,
        `roof_efficiency_pct`, and `regime`.

        **User:** Put these on a log–log Roofline plot so the systems team can see which kernels are hitting the
        memory ceiling versus leaving compute headroom on the table (`moe_grouped_gemm` looks suspicious).
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="swe_coding", domain="GPU Systems",
        title="H100 kernel Roofline plot (log–log memory vs compute ceiling)",
        what="moe_grouped_gemm achieves 488 TFLOP/s (49.3% of 989 TFLOP/s ceiling) while gemm_fp16_tile hits 792 TFLOP/s (80.1%); ridge point 295 FLOP/byte",
        accept=[488.0, 49.3, 792.0, 80.1, ridge],
        rel_tol=0.06, abs_tol=2.0, uncertainty_required=False,
        require_log_scale=True,
        required_disclosures=["moe_grouped_gemm|moe", "roofline|ridge|295|989|memory|compute"],
        reader_questions=_rqs(
            "What throughput and roof efficiency does moe_grouped_gemm achieve?",
            "488 TFLOP/s (49.3% of the 989 TFLOP/s compute roof).",
            "At what arithmetic intensity does the H100 transition from memory-bound to compute-bound?",
            "At the ridge point of ~295 FLOP/byte.",
            "Which kernels are near the memory bandwidth ceiling?",
            "rmsnorm_v1, softmax_fused, rope_apply, and flash_attn_fwd sit close to the 3.35 TB/s memory roof.",
        ),
    )


def make_18_db_query_plan_tail() -> None:
    tid, split = "18_db_query_plan_tail", "dev"
    root = _task_dir(split, tid)
    rng = np.random.default_rng(1801)
    endpoints = [
        ("orders_join", (28.0, 0.72), (12.0, 0.34)),
        ("user_profile", (8.5, 0.30), (8.2, 0.31)),
        ("invoice_search", (22.0, 0.55), (11.5, 0.35)),
        ("audit_export", (41.0, 0.40), (39.5, 0.41)),
        ("order_insert", (6.8, 0.28), (11.0, 0.30)),
    ]
    rows = []
    p99_before: dict[str, float] = {}
    p99_after: dict[str, float] = {}
    p50_ins_diff = 0.0
    for ep, (mu_b, s_b), (mu_a, s_a) in endpoints:
        b = rng.lognormal(math.log(mu_b), s_b, size=500)
        a = rng.lognormal(math.log(mu_a), s_a, size=500)
        p99_before[ep] = float(np.percentile(b, 99))
        p99_after[ep] = float(np.percentile(a, 99))
        if ep == "order_insert":
            p50_ins_diff = float(np.median(a) - np.median(b))
        for stage, arr in (("before_index", b), ("after_index", a)):
            rows.append([
                ep, stage, 500,
                round(float(np.percentile(arr, 50)), 2),
                round(float(np.percentile(arr, 95)), 2),
                round(float(np.percentile(arr, 99)), 2),
            ])
    ratio_join = p99_before["orders_join"] / p99_after["orders_join"]
    drop_join = p99_before["orders_join"] - p99_after["orders_join"]
    _write_csv(root, "pg_latency_percentiles.csv", ["endpoint", "stage", "n_queries", "p50_ms", "p95_ms", "p99_ms"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** We added a composite B-tree index on `orders(customer_id, created_at)` and captured
        p50/p95/p99 query latencies across 500 sampled queries per endpoint (`data/pg_latency_percentiles.csv`).

        **Assistant:** Columns: `endpoint`, `stage` (`before_index`, `after_index`), `n_queries` (500),
        `p50_ms`, `p95_ms`, and `p99_ms`.

        **User:** Show the DBA team whether the index fixed the `orders_join` p99 tail and flag any write-path
        overhead on `order_insert`.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="swe_coding", domain="Databases",
        title="PostgreSQL composite index p99 tail gain vs write overhead",
        what=f"orders_join p99 drops {ratio_join:.1f}x ({p99_before['orders_join']:.0f} -> {p99_after['orders_join']:.0f} ms, -{drop_join:.0f} ms) while order_insert adds +{p50_ins_diff:.1f} ms p50",
        accept=[ratio_join, drop_join, p99_after["orders_join"], p99_before["orders_join"], p50_ins_diff],
        rel_tol=0.08, abs_tol=0.5, uncertainty_required=False,
        required_disclosures=["orders_join", "order_insert|write", "p99|500"],
        reader_questions=_rqs(
            "By how much did the composite index cut orders_join p99 latency?",
            f"About {ratio_join:.1f}× (from {p99_before['orders_join']:.0f} ms down to {p99_after['orders_join']:.0f} ms).",
            "How many queries per endpoint back each percentile?",
            "500 queries per endpoint per stage.",
            "What tradeoff appeared on the write path?",
            f"order_insert latency rose by ~+{p50_ins_diff:.1f} ms at p50 due to index maintenance.",
        ),
    )


def make_19_trap_dual_axis_spurious() -> None:
    tid, split = "19_trap_dual_axis_spurious", "dev"
    root = _task_dir(split, tid)
    rng = np.random.default_rng(1901)
    years = np.arange(2012, 2026)
    t = np.arange(len(years), dtype=float)
    # Two completely independent series sharing only a secular upward drift
    solar_gw = 12.0 + 9.4 * t + rng.normal(0.0, 4.5, size=len(years))
    avocado_tons = 180.0 + 21.0 * t + rng.normal(0.0, 14.0, size=len(years))
    raw_r = float(np.corrcoef(solar_gw, avocado_tons)[0, 1])
    # Detrended (first-difference or linear residual) correlation near zero
    res_s = solar_gw - np.polyval(np.polyfit(t, solar_gw, 1), t)
    res_a = avocado_tons - np.polyval(np.polyfit(t, avocado_tons, 1), t)
    detrend_r = float(np.corrcoef(res_s, res_a)[0, 1])
    diff_r = float(np.corrcoef(np.diff(solar_gw), np.diff(avocado_tons))[0, 1])
    rows = [[int(y), round(float(s), 2), round(float(a), 1)] for y, s, a in zip(years, solar_gw, avocado_tons)]
    _write_csv(root, "trends_2012_2025.csv", ["year", "grid_solar_gw", "regional_avocado_imports_kt"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** Look at `data/trends_2012_2025.csv` — regional solar capacity and avocado imports have
        raw Pearson `r > 0.95`! Can you plot them on overlapping dual y-axes so I can show how tightly
        coupled consumer demand is with solar deployment?

        **Assistant:** Columns: `year` (2012–2025), `grid_solar_gw`, and `regional_avocado_imports_kt`.
        Let me inspect the raw trend vs detrended / year-over-year changes first.

        **User:** Sure, send one clean figure for the newsletter.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="epistemic_traps", domain="Statistical Literacy",
        title="Dual-axis spurious trend correlation trap",
        what=f"Raw r = {raw_r:.2f} is driven by shared time drift; detrended correlation collapses to r = {detrend_r:.2f} (YoY diff r = {diff_r:.2f})",
        accept=[detrend_r, abs(detrend_r), diff_r, abs(diff_r), raw_r],
        rel_tol=0.15, abs_tol=0.08, uncertainty_required=False,
        no_effect_trap=True,
        forbidden_overclaim_phrases=["tightly coupled", "drives solar", "causes", "real link", "strong causal"],
        required_disclosures=["spurious|detrend|trend|drift|independent|no relationship|coincid", "r =|r=|corr"],
        reader_questions=_rqs(
            "What is the correlation after removing the shared time trend?",
            f"Near zero (detrended r = {detrend_r:.2f}, YoY difference r = {diff_r:.2f}).",
            "Why was the raw correlation so high?",
            f"Both series grew steadily over 2012–2025, inflating raw r to {raw_r:.2f} without any real link.",
            "Should a dual y-axis chart be used to claim coupling?",
            "No; overlapping dual axes visually manufacture a spurious link between independent upward trends.",
        ),
    )


def make_20_trap_survivorship_bias() -> None:
    tid, split = "20_trap_survivorship_bias", "dev"
    root = _task_dir(split, tid)
    rng = np.random.default_rng(2001)
    active_scores = rng.normal(84.2, 6.2, size=36).clip(62, 98)
    churned_scores = rng.normal(38.5, 9.5, size=24).clip(15, 65)
    active_mean = float(np.mean(active_scores))
    all_scores = np.concatenate([active_scores, churned_scores])
    true_mean = float(np.mean(all_scores))
    bias_gap = active_mean - true_mean
    _write_csv(
        root, "active_accounts.csv", ["account_id", "status", "nps_score"],
        [[f"ACT-{i+1:03d}", "active", round(float(v), 1)] for i, v in enumerate(active_scores)],
    )
    _write_csv(
        root, "churned_accounts.csv", ["account_id", "status", "nps_score"],
        [[f"CHN-{i+1:03d}", "churned", round(float(v), 1)] for i, v in enumerate(churned_scores)],
    )
    _write_context(
        root,
        """
        # Thread

        **User:** Customer Success exported our Q3 satisfaction survey to `data/active_accounts.csv` (36 active
        accounts) and also dropped `data/churned_accounts.csv` (24 accounts that cancelled during Q3) in the
        same folder.

        **Assistant:** Both files have `account_id`, `status`, and `nps_score` (0–100).

        **User:** Can you plot our Q3 customer satisfaction score so leadership can see how happy the cohort is?
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="epistemic_traps", domain="Product Analytics",
        title="Survivorship bias trap with churned cohort file",
        what=f"Including 24 churned accounts drops cohort mean from {active_mean:.1f} to {true_mean:.1f} (-{bias_gap:.1f} pts survivorship inflation)",
        accept=[true_mean, bias_gap, active_mean, float(np.mean(churned_scores))],
        rel_tol=0.06, abs_tol=1.5, uncertainty_required=True,
        no_effect_trap=False,
        forbidden_overclaim_phrases=["all customers are happy", "uniformly high satisfaction"],
        required_disclosures=["churn|survivor|cancelled|dropped", "24|60|n=|s.d.|sd|ci|±"],
        reader_questions=_rqs(
            "What is the true full-cohort mean NPS once churned accounts are included?",
            f"About {true_mean:.1f} (vs {active_mean:.1f} for active-only — a {bias_gap:.1f}-point survivorship inflation).",
            "How many churned vs active accounts are in the cohort?",
            "24 churned accounts (40% of the cohort) and 36 active accounts (60 total).",
            "Why would plotting only active_accounts.csv mislead leadership?",
            "It omits the 24 unhappy accounts that cancelled during Q3 (mean ~38.5).",
        ),
    )


def make_21_edit_normalize_per_capita() -> None:
    tid, split = "21_edit_normalize_per_capita", "dev"
    root = _task_dir(split, tid)
    counties = [
        ("Metro-North", 920_000, 412),
        ("Riverdale", 640_000, 310),
        ("Pine-Ridge", 85_000, 118),
        ("Oak-Valley", 145_000, 162),
        ("Harbor-Bay", 410_000, 198),
        ("Cedar-Flats", 62_000, 96),
    ]
    rows = []
    rates = {}
    for c, pop, adm in counties:
        rate = 100_000.0 * adm / pop
        ci95 = 1.96 * math.sqrt(adm) * 100_000.0 / pop
        rates[c] = rate
        rows.append([c, pop, adm, round(rate, 2), round(ci95, 2)])
    _write_csv(root, "county_admissions.csv", ["county", "population", "admissions", "rate_per_100k", "ci95_half"], rows)

    # Render misleading prior figure (raw counts only)
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    ax.barh([c[0] for c in counties], [c[2] for c in counties], color="#4e79a7")
    ax.set_xlabel("Raw respiratory admissions")
    ax.set_title("Metro-North has the most admissions (412)")
    fig.tight_layout()
    fig.savefig(root / "data" / "prior_figure.png", dpi=110)
    plt.close(fig)

    top_rate = rates["Cedar-Flats"]
    metro_rate = rates["Metro-North"]
    ratio = top_rate / metro_rate
    _write_context(
        root,
        """
        # Thread

        **User:** Here is `data/county_admissions.csv` and the draft figure (`data/prior_figure.png`) showing
        raw hospital admissions by county.

        **Assistant:** In `data/prior_figure.png`, Metro-North leads on raw count (412 admissions).

        **User:** Wait — Metro-North has 920k residents while Cedar-Flats has only 62k! Please revise the
        figure to normalize per 100,000 residents with 95% Poisson confidence intervals so we allocate mobile
        clinics to the highest-risk counties.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="multiturn_edit", domain="Public Health",
        title="Revise raw county admissions to per-100k rate with 95% Poisson CI",
        what=f"Cedar-Flats leads at {top_rate:.1f}/100k ({ratio:.1f}x Metro-North's {metro_rate:.1f}/100k)",
        accept=[top_rate, ratio, rates["Pine-Ridge"], metro_rate],
        rel_tol=0.06, abs_tol=1.5, uncertainty_required=True,
        forbidden_overclaim_phrases=["Metro-North has the highest rate"],
        required_disclosures=["100k|100,000|per capita", "95% ci|poisson|ci|±"],
        reader_questions=_rqs(
            "Which county has the highest per-capita admission rate and what is it?",
            f"Cedar-Flats at {top_rate:.1f} per 100k residents (followed by Pine-Ridge at {rates['Pine-Ridge']:.1f}/100k).",
            "How is count uncertainty represented for small rural counties?",
            "95% Poisson confidence intervals showing wider bars for smaller populations.",
            "How does the ranking change compared to the prior raw-count figure?",
            f"Metro-North drops from #1 in raw counts to the lowest per-capita rate ({metro_rate:.1f}/100k).",
        ),
    )


def make_22_edit_split_confounder() -> None:
    tid, split = "22_edit_split_confounder", "dev"
    root = _task_dir(split, tid)
    rng = np.random.default_rng(2201)
    steps = np.arange(0, 85_000, 5_000)
    rows = []
    bf16_end, fp8_end = [], []
    for run_id, prec in [("R1", "BF16"), ("R2", "BF16"), ("R3", "BF16"), ("R4", "FP8"), ("R5", "FP8"), ("R6", "FP8")]:
        for s in steps:
            base = 3.4 - 1.45 * (1.0 - math.exp(-s / 24_000.0))
            drift = 0.0 if prec == "BF16" else (0.0 if s <= 40_000 else 0.0000095 * (s - 40_000))
            loss = base + drift + float(rng.normal(0.0, 0.025))
            rows.append([run_id, prec, int(s), round(loss, 4)])
            if s == 80_000:
                (bf16_end if prec == "BF16" else fp8_end).append(loss)
    gap = float(np.mean(fp8_end) - np.mean(bf16_end))
    _write_csv(root, "training_runs.csv", ["run_id", "precision", "step", "val_loss"], rows)

    # Prior pooled figure hiding precision confounder
    arr_steps = sorted({r[2] for r in rows})
    pooled = [np.mean([r[3] for r in rows if r[2] == st]) for st in arr_steps]
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    ax.plot(np.array(arr_steps) / 1000.0, pooled, color="#4e79a7", lw=2)
    ax.set_xlabel("Step (k)")
    ax.set_ylabel("Validation loss")
    ax.set_title("Validation loss plateaus around 2.15 (6 runs pooled)")
    fig.tight_layout()
    fig.savefig(root / "data" / "prior_figure.png", dpi=110)
    plt.close(fig)

    _write_context(
        root,
        """
        # Thread

        **User:** In `data/prior_figure.png`, we averaged all 6 pretraining runs together (`data/training_runs.csv`)
        and it looked like loss just stalled around step 40k.

        **Assistant:** Columns: `run_id` (R1–R6), `precision` (`BF16` vs `FP8`, 3 runs each), `step` (0–80k), `val_loss`.

        **User:** Oh! Half of those runs used FP8! Please revise the figure to split by `precision` (showing the 3
        runs/spread per group) and call out where FP8 diverges from BF16.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="multiturn_edit", domain="ML Training",
        title="Split pooled training curve by BF16 vs FP8 precision",
        what=f"FP8 diverges after step 40k, ending +{gap:.2f} loss higher than BF16 ({np.mean(fp8_end):.2f} vs {np.mean(bf16_end):.2f})",
        accept=[gap, float(np.mean(fp8_end)), float(np.mean(bf16_end)), 40.0, 40000.0],
        rel_tol=0.08, abs_tol=0.05, uncertainty_required=True,
        required_disclosures=["fp8", "bf16", "40k|40,000|40000", "3 run|3 seed|n=3|s.d.|sd|±|ci|individual"],
        reader_questions=_rqs(
            "By how much does FP8 validation loss exceed BF16 at step 80k?",
            f"About +{gap:.2f} loss ({np.mean(fp8_end):.2f} vs {np.mean(bf16_end):.2f}).",
            "How many runs per precision group are plotted?",
            "3 runs per precision (R1–R3 BF16, R4–R6 FP8).",
            "At what step do FP8 and BF16 diverge?",
            "Right after step 40k, where FP8 turns upward while BF16 keeps improving.",
        ),
    )


def make_23_surface_narrow_oncall() -> None:
    tid, split = "23_surface_narrow_oncall", "dev"
    root = _task_dir(split, tid)
    services = [
        ("checkout-api", 100.0, 21.4, 78.6),
        ("auth-edge", 100.0, 88.2, 11.8),
        ("search-rank", 100.0, 91.5, 8.5),
        ("billing-sync", 100.0, 64.0, 36.0),
    ]
    rows = [[s, b, rem, burn] for s, b, rem, burn in services]
    _write_csv(root, "error_budgets.csv", ["service", "monthly_budget_pct", "remaining_pct", "burned_pct"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** I'm paging through Slack on my phone (450 px mobile column). Can you chart our 30-day SLO
        error budget remaining from `data/error_budgets.csv`?

        **Assistant:** Columns: `service` (4 services), `monthly_budget_pct` (100%), `remaining_pct`, and `burned_pct`.

        **User:** Make sure every label stays readable at 450 px phone width and highlight which service is
        dangerously close to exhausting its monthly budget (< 25% remaining).
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="multi_surface", domain="SRE / Mobile",
        title="450 px mobile on-call SLO error budget triage",
        what="checkout-api has only 21.4% error budget remaining (78.6% burned), below the 25% alert floor",
        accept=[21.4, 78.6],
        rel_tol=0.05, abs_tol=0.5, uncertainty_required=False,
        display_width_px=450, surface="narrow",
        required_disclosures=["checkout-api|checkout", "25%|budget|slo"],
        reader_questions=_rqs(
            "Which service is below the 25% remaining error budget alert threshold and how much is left?",
            "checkout-api with 21.4% remaining (78.6% burned).",
            "What display width constraint applies?",
            "Narrow 450 px mobile chat width (all labels >= 11 px at 450 px).",
            "How healthy are the other three services?",
            "billing-sync has 64.0% remaining while auth-edge (88.2%) and search-rank (91.5%) have ample headroom.",
        ),
    )


def make_24_surface_html_interactive_report() -> None:
    tid, split = "24_surface_html_interactive_report", "dev"
    root = _task_dir(split, tid)
    rng = np.random.default_rng(2401)
    months = ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
    slices = {
        "us_web": [0.892, 0.890, 0.888, 0.887, 0.889, 0.886],
        "eu_web": [0.881, 0.879, 0.880, 0.876, 0.878, 0.875],
        "ios_app": [0.874, 0.872, 0.870, 0.871, 0.869, 0.868],
        "android_app": [0.868, 0.862, 0.848, 0.824, 0.798, 0.774],
    }
    rows = []
    for sl, vals in slices.items():
        for m, v in zip(months, vals):
            ci = round(float(rng.uniform(0.008, 0.013)), 4)
            rows.append([m, sl, round(v * 100.0, 2), round(ci * 100.0, 2), 2000])
    drop_and = (slices["android_app"][0] - slices["android_app"][-1]) * 100.0
    end_and = slices["android_app"][-1] * 100.0
    _write_csv(root, "model_drift_monthly.csv", ["month", "slice", "f1_pct", "ci95_half_pct", "n_eval"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** We're embedding a 6-month ML monitoring chart into our internal HTML engineering report
        (700 px article column). Data is in `data/model_drift_monthly.csv`.

        **Assistant:** Columns: `month` (2026-05..2026-10), `slice` (`us_web`, `eu_web`, `ios_app`, `android_app`),
        `f1_pct`, `ci95_half_pct` (95% CI half-width), and `n_eval` (2,000/month/slice).

        **User:** Show which traffic slice is drifting and by how many points since May, with 95% CI bands so
        reviewers can tell real degradation from eval noise.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="multi_surface", domain="ML Monitoring",
        title="HTML report 6-month model drift across traffic slices",
        what=f"android_app F1 fell -{drop_and:.1f} pp from May to October (to {end_and:.1f}%), while web/iOS stayed flat within 95% CI",
        accept=[drop_and, -drop_and, end_and],
        rel_tol=0.06, abs_tol=0.5, uncertainty_required=True,
        display_width_px=700, surface="html",
        required_disclosures=["android", "95% ci|ci|±|2,000|2000"],
        reader_questions=_rqs(
            "Which slice suffered F1 drift and how many points did it drop from May to October?",
            f"android_app dropped {drop_and:.1f} percentage points (from 86.8% down to {end_and:.1f}%).",
            "How is evaluation uncertainty shown?",
            "95% confidence bands across n = 2,000 samples per slice-month.",
            "How did the other three slices behave?",
            "us_web, eu_web, and ios_app stayed flat within ~1 point.",
        ),
    )


def make_25_repair_truncated_and_rainbow() -> None:
    tid, split = "25_repair_truncated_and_rainbow", "dev"
    root = _task_dir(split, tid)
    rows = [
        ["v1.0_base", 80.2, 0.9, 5],
        ["v1.1_norm", 81.4, 0.8, 5],
        ["v1.2_aug", 83.1, 0.7, 5],
        ["v1.3_distill", 85.0, 0.8, 5],
    ]
    gain = 85.0 - 80.2
    _write_csv(root, "release_scores.csv", ["release", "top1_acc_pct", "sd_pct", "n_seeds"], rows)
    _write_script(
        root,
        "broken_plot.py",
        """
        import csv
        import matplotlib.pyplot as plt
        import numpy as np

        with open("data/release_scores.csv", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        releases = [r["release"] for r in rows]
        acc = [float(r["top1_acc_pct"]) for r in rows]
        sd = [float(r["sd_pct"]) for r in rows]
        fig, ax = plt.subplots(figsize=(12, 5))
        colors = plt.cm.rainbow(np.linspace(0, 1, len(rows)))
        ax.bar(releases, acc, yerr=sd, color=colors)
        ax.set_ylim(78, 87)  # truncated bar axis exaggerating gain!
        ax.set_title("v1.3_distill jumps +14.0%% over baseline!", fontsize=7)
        ax.tick_params(labelsize=6)
        fig.savefig("figure.png", dpi=100)
        """,
    )
    _write_context(
        root,
        """
        # Thread

        **User:** Someone pushed `broken_plot.py` (reading `data/release_scores.csv`) to our release review.
        It has a truncated bar y-axis, rainbow colors, tiny unreadable labels, a `%%` typo, AND a wrong
        headline number (+14%?!).

        **Assistant:** I'll inspect `data/release_scores.csv` and `broken_plot.py`, recompute the true gain from
        the CSV, and produce a clean repaired figure with an honest scale, colorblind-safe palette, and named
        seed uncertainty.

        **User:** Perfect — save the repaired figure as `figure.png`.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="byo_repair", domain="ML Evaluation",
        title="Repair truncated bar axis, rainbow palette, tiny text, and wrong claim",
        what=f"True v1.3_distill gain over v1.0_base is +{gain:.1f} pp (80.2% -> 85.0%), not +14%",
        accept=[gain, 85.0, 80.2],
        rel_tol=0.05, abs_tol=0.3, uncertainty_required=True,
        forbid_truncated_bars=True,
        forbidden_overclaim_phrases=["14.0%", "+14%"],
        required_disclosures=["5 seeds|n=5|s.d.|sd|±|ci", "v1.3|85.0|4.8"],
        reader_questions=_rqs(
            "What is the true Top-1 accuracy gain of v1.3_distill over v1.0_base?",
            f"+{gain:.1f} percentage points (from 80.2% to 85.0%).",
            "What uncertainty is reported?",
            "±1 SD across 5 seeds.",
            "What visual defects from broken_plot.py were fixed?",
            "Removed the truncated bar axis, rainbow palette, tiny text, %% typo, and false +14% claim.",
        ),
    )


# ===========================================================================
# PART 2: 20 new PUBLIC-TEST tasks (pt31_..pt50_)
# ===========================================================================


def make_pt31_bland_altman() -> None:
    tid, split = "pt31_bland_altman", "public-test"
    root = _task_dir(split, tid)
    rng = np.random.default_rng(3101)
    n = 60
    ref = rng.uniform(82.0, 99.0, size=n)
    # Device overreads by +1.8% on average, with wider spread below 90% SpO2
    noise_sd = np.where(ref < 90.0, 2.2, 0.85)
    bias_shift = np.where(ref < 90.0, 2.6, 1.3)
    dev = np.clip(ref + bias_shift + rng.normal(0.0, noise_sd), 75.0, 100.0)
    diffs = dev - ref
    means = 0.5 * (dev + ref)
    mean_bias = float(np.mean(diffs))
    sd_diff = float(np.std(diffs, ddof=1))
    loa_hi = mean_bias + 1.96 * sd_diff
    loa_lo = mean_bias - 1.96 * sd_diff
    rows = [[f"P{i+1:02d}", round(float(r), 2), round(float(d), 2), round(float(m), 2), round(float(df), 2)]
            for i, (r, d, m, df) in enumerate(zip(ref, dev, means, diffs))]
    _write_csv(root, "spo2_agreement.csv", ["patient_id", "arterial_sao2_pct", "wearable_spo2_pct", "pair_mean_pct", "diff_wearable_minus_ref_pct"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** We validated a wearable pulse oximeter against arterial blood gas SaO2 across 60 clinical
        readings (`data/spo2_agreement.csv`).

        **Assistant:** Columns: `patient_id`, `arterial_sao2_pct`, `wearable_spo2_pct`, `pair_mean_pct`, and
        `diff_wearable_minus_ref_pct`.

        **User:** Make a Bland–Altman agreement figure showing the mean bias and 95% limits of agreement
        (±1.96 SD), and call out whether error worsens in the hypoxic range (< 90% SaO2).
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="science_uncertainty", domain="Biomedical Devices",
        title="Pulse oximeter Bland–Altman bias and 95% limits of agreement",
        what=f"Mean bias +{mean_bias:.2f}% SpO2 (95% LoA {loa_lo:.1f}% to +{loa_hi:.1f}%), with wider positive bias below 90% SaO2",
        accept=[mean_bias, loa_hi, abs(loa_lo), sd_diff],
        rel_tol=0.10, abs_tol=0.25, uncertainty_required=True,
        required_disclosures=["bias|mean diff", "loa|limits of agreement|1.96|95%|sd|s.d.|±", "90%|hypox"],
        reader_questions=_rqs(
            "What is the wearable oximeter's mean bias vs arterial SaO2?",
            f"About +{mean_bias:.2f}% SpO2 (95% limits of agreement {loa_lo:.1f}% to +{loa_hi:.1f}%).",
            "How is agreement spread quantified?",
            "95% limits of agreement (±1.96 SD) across n = 60 paired readings.",
            "Does error behave uniformly across oxygenation levels?",
            "No — error and overestimation widen noticeably below 90% SaO2.",
        ),
    )


def make_pt32_xrd_phase_shift() -> None:
    tid, split = "pt32_xrd_phase_shift", "public-test"
    root = _task_dir(split, tid)
    rng = np.random.default_rng(3201)
    two_theta = np.round(np.arange(36.0, 44.01, 0.05), 3)
    peak_centers = {"unstrained": 39.85, "strain_2pct": 40.18, "strain_4pct": 40.55}
    rows = []
    measured_peaks = {}
    for cond, ctr in peak_centers.items():
        rep_peaks = []
        for rep in range(1, 4):
            c_rep = ctr + float(rng.normal(0.0, 0.015))
            intens = 120.0 + 2800.0 * np.exp(-0.5 * ((two_theta - c_rep) / 0.22) ** 2) + rng.normal(0.0, 22.0, size=len(two_theta))
            rep_peaks.append(float(two_theta[int(np.argmax(intens))]))
            for tt, val in zip(two_theta, intens):
                rows.append([cond, rep, float(tt), round(float(max(0.0, val)), 2)])
        measured_peaks[cond] = float(np.mean(rep_peaks))
    shift_4 = measured_peaks["strain_4pct"] - measured_peaks["unstrained"]
    _write_csv(root, "xrd_scans.csv", ["condition", "scan_rep", "two_theta_deg", "intensity_cps"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** Here are triplicate X-ray diffraction (XRD) scans around the (111) peak for an unstrained thin
        film and two compressive-strain levels (`data/xrd_scans.csv`).

        **Assistant:** Columns: `condition` (`unstrained`, `strain_2pct`, `strain_4pct`), `scan_rep` (1–3),
        `two_theta_deg` (36–44°), and `intensity_cps`.

        **User:** Show the peak shift under 4% compressive strain (Δ2θ in degrees) with replicate scan uncertainty.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="science_uncertainty", domain="Materials Characterization",
        title="XRD (111) peak shift under compressive strain",
        what=f"4% strain shifts the (111) peak by +{shift_4:.2f}° (from {measured_peaks['unstrained']:.2f}° to {measured_peaks['strain_4pct']:.2f}°)",
        accept=[shift_4, measured_peaks["strain_4pct"], measured_peaks["unstrained"]],
        rel_tol=0.08, abs_tol=0.08, uncertainty_required=True,
        required_disclosures=["2θ|two_theta|deg|°", "3 scan|triplicate|replicate|n=3|s.d.|sd|±|ci"],
        reader_questions=_rqs(
            "By how many degrees 2θ does the (111) peak shift at 4% strain?",
            f"About +{shift_4:.2f}° (from {measured_peaks['unstrained']:.2f}° to {measured_peaks['strain_4pct']:.2f}°).",
            "How many replicate XRD scans back each curve?",
            "3 replicate scans per condition.",
            "What physical change does shifting to higher 2θ indicate?",
            "Lattice d-spacing contraction under compressive strain.",
        ),
    )


def make_pt33_crispr_screen_rank() -> None:
    tid, split = "pt33_crispr_screen_rank", "public-test"
    root = _task_dir(split, tid)
    rng = np.random.default_rng(3301)
    genes = [f"GENE{i:03d}" for i in range(1, 51)]
    lfcs = rng.normal(0.0, 0.35, size=50)
    sds = rng.uniform(0.12, 0.25, size=50)
    fdrs = rng.uniform(0.18, 0.95, size=50)
    # Plant 4 strong essential dropouts (hits)
    hits = [
        (0, "PRMT5", -3.45, 0.21, 0.0004),
        (1, "WRN", -2.92, 0.19, 0.0012),
        (2, "POLQ", -2.38, 0.22, 0.0065),
        (3, "AURKB", -1.96, 0.18, 0.0190),
    ]
    for idx, name, lfc, sd, fdr in hits:
        genes[idx], lfcs[idx], sds[idx], fdrs[idx] = name, lfc, sd, fdr
    rows = [[g, round(float(l), 3), round(float(s), 3), round(float(f), 5), 4] for g, l, s, f in zip(genes, lfcs, sds, fdrs)]
    _write_csv(root, "crispr_lfc.csv", ["gene", "log2_fc", "sd_lfc", "fdr", "n_guides"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** Our 50-gene CRISPR synthetic-lethality screen is summarized in `data/crispr_lfc.csv` (4 sgRNAs
        per gene).

        **Assistant:** Columns: `gene`, `log2_fc`, `sd_lfc` (across 4 guides), `fdr`, and `n_guides`.

        **User:** Make a rank-order figure highlighting all hits passing `FDR < 0.05` and calling out the
        strongest synthetic-lethal dropout (`PRMT5`) with its guide-level spread.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="science_uncertainty", domain="Functional Genomics",
        title="CRISPR synthetic-lethality rank-order screen with guide SD",
        what="4 hits pass FDR < 0.05; PRMT5 is the top dropout at log2FC = -3.45 (±0.21 SD across 4 guides)",
        accept=[-3.45, 3.45, 4.0],
        rel_tol=0.06, abs_tol=0.15, uncertainty_required=True,
        required_disclosures=["prmt5", "fdr|0.05", "4 guide|n=4|s.d.|sd|±"],
        reader_questions=_rqs(
            "Which gene is the top synthetic-lethal hit and what is its log2 fold change?",
            "PRMT5 at log2FC = −3.45 (with 4 total genes passing FDR < 0.05).",
            "How is sgRNA variability reported?",
            "Guide-level SD across 4 sgRNAs per gene.",
            "Which other three genes pass FDR < 0.05?",
            "WRN (−2.92), POLQ (−2.38), and AURKB (−1.96).",
        ),
    )


def make_pt34_climate_ensemble_fan() -> None:
    tid, split = "pt34_climate_ensemble_fan", "public-test"
    root = _task_dir(split, tid)
    rng = np.random.default_rng(3401)
    years = np.arange(2025, 2101, 5)
    rows = []
    end_vals: dict[str, list[float]] = {"SSP1-2.6": [], "SSP3-7.0": []}
    for scen, rate, cur_sd in [("SSP1-2.6", 0.008, 0.22), ("SSP3-7.0", 0.038, 0.42)]:
        for m in range(1, 13):
            model_offset = float(rng.normal(0.0, cur_sd))
            for y in years:
                frac = (y - 2025) / 75.0
                if scen == "SSP1-2.6":
                    anom = 1.25 + 0.55 * math.sin(0.5 * math.pi * min(1.0, frac * 1.25)) + model_offset * (0.3 + 0.7 * frac) + float(rng.normal(0.0, 0.05))
                else:
                    anom = 1.25 + 2.85 * (frac ** 1.15) + model_offset * (0.3 + 0.9 * frac) + float(rng.normal(0.0, 0.06))
                rows.append([scen, f"M{m:02d}", int(y), round(anom, 3)])
                if y == 2100:
                    end_vals[scen].append(anom)
    med_hi = float(np.median(end_vals["SSP3-7.0"]))
    med_lo = float(np.median(end_vals["SSP1-2.6"]))
    gap_2100 = med_hi - med_lo
    _write_csv(root, "cmip_ensemble.csv", ["scenario", "model_id", "year", "temp_anomaly_c"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** We extracted a 12-model climate ensemble (`data/cmip_ensemble.csv`) comparing `SSP1-2.6` and
        `SSP3-7.0` global mean temperature anomalies (°C above pre-industrial) from 2025 to 2100.

        **Assistant:** Columns: `scenario`, `model_id` (M01–M12), `year` (2025–2100), and `temp_anomaly_c`.

        **User:** Plot the ensemble medians with 10th–90th percentile (or SD/IQR) spread envelopes and state the
        2100 warming gap between the two scenarios.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="science_uncertainty", domain="Climate Science",
        title="12-model climate ensemble fan (SSP1-2.6 vs SSP3-7.0)",
        what=f"By 2100 SSP3-7.0 median reaches +{med_hi:.2f} °C vs +{med_lo:.2f} °C under SSP1-2.6 (+{gap_2100:.2f} °C gap across 12 models)",
        accept=[gap_2100, med_hi, med_lo],
        rel_tol=0.07, abs_tol=0.15, uncertainty_required=True,
        required_disclosures=["12 model|ensemble|n=12|percentile|iqr|s.d.|sd|±|10th|90th", "ssp3|ssp1|2100"],
        reader_questions=_rqs(
            "What is the 2100 median warming gap between SSP3-7.0 and SSP1-2.6?",
            f"About +{gap_2100:.2f} °C ({med_hi:.2f} °C vs {med_lo:.2f} °C).",
            "How is inter-model uncertainty shown?",
            "Shaded envelope (10th–90th percentile / IQR / SD) across 12 climate models.",
            "When do the two scenario envelopes clearly separate?",
            "Around mid-century (2045–2055), after which SSP1-2.6 stabilizes below 2 °C while SSP3-7.0 accelerates.",
        ),
    )


def make_pt35_cache_eviction_hitrate() -> None:
    tid, split = "pt35_cache_eviction_hitrate", "public-test"
    root = _task_dir(split, tid)
    rng = np.random.default_rng(3501)
    sizes = [64, 128, 256, 512, 1024, 2048, 4096]
    curves = {
        "LRU": [0.382, 0.314, 0.258, 0.205, 0.162, 0.128, 0.104],
        "W-TinyLFU": [0.326, 0.264, 0.212, 0.169, 0.134, 0.108, 0.091],
        "S3-FIFO": [0.294, 0.236, 0.188, 0.149, 0.121, 0.099, 0.085],
    }
    rows = []
    at_256: dict[str, list[float]] = {k: [] for k in curves}
    for algo, vals in curves.items():
        for sz, base in zip(sizes, vals):
            for rep in range(1, 6):
                mr = max(0.01, base + float(rng.normal(0.0, 0.006)))
                rows.append([algo, sz, rep, round(mr * 100.0, 2)])
                if sz == 256:
                    at_256[algo].append(mr * 100.0)
    gap_256 = float(np.mean(at_256["LRU"]) - np.mean(at_256["S3-FIFO"]))
    s3_256 = float(np.mean(at_256["S3-FIFO"]))
    _write_csv(root, "cache_mrc.csv", ["policy", "cache_mb", "trace_run", "miss_ratio_pct"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** We simulated three cache eviction policies (`LRU`, `W-TinyLFU`, `S3-FIFO`) across cache sizes
        from 64 MB to 4096 MB over 5 production trace replays (`data/cache_mrc.csv`).

        **Assistant:** Columns: `policy`, `cache_mb`, `trace_run` (1–5), and `miss_ratio_pct`.

        **User:** Plot the miss-ratio curves on a log cache-size axis with replay spread and call out how much
        `S3-FIFO` beats `LRU` at our production 256 MB tier.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="swe_coding", domain="Storage Systems",
        title="Cache miss-ratio curves (LRU vs W-TinyLFU vs S3-FIFO)",
        what=f"At 256 MB, S3-FIFO cuts miss ratio by -{gap_256:.1f} pp vs LRU ({s3_256:.1f}% vs {np.mean(at_256['LRU']):.1f}%)",
        accept=[gap_256, s3_256, float(np.mean(at_256["LRU"]))],
        rel_tol=0.08, abs_tol=0.5, uncertainty_required=True,
        require_log_scale=True,
        required_disclosures=["s3-fifo", "256", "5 trace|5 run|n=5|s.d.|sd|±|ci"],
        reader_questions=_rqs(
            "How much lower is S3-FIFO's miss ratio than LRU at 256 MB?",
            f"About {gap_256:.1f} percentage points lower ({s3_256:.1f}% vs {np.mean(at_256['LRU']):.1f}%).",
            "How is trace-to-trace spread represented?",
            "Spread (SD/CI/points) across 5 trace replays per cache size.",
            "Does S3-FIFO's advantage hold across all sizes or shrink at large caches?",
            "It wins at every size, with the largest gains at small/medium caches (64–512 MB) and narrowing at 4 GB.",
        ),
    )


def make_pt36_token_throughput_batch() -> None:
    tid, split = "pt36_token_throughput_batch", "public-test"
    root = _task_dir(split, tid)
    batches = [1, 2, 4, 8, 16, 32, 64]
    ttft_ms = [42.0, 51.0, 68.0, 102.0, 168.0, 294.0, 540.0]
    itl_ms = [11.2, 12.1, 13.8, 16.5, 21.4, 30.8, 49.5]
    tok_s = [round(1000.0 * b / itl, 1) for b, itl in zip(batches, itl_ms)]
    rows = [[b, t, i, tp] for b, t, i, tp in zip(batches, ttft_ms, itl_ms, tok_s)]
    _write_csv(root, "llm_serving_batch.csv", ["batch_size", "ttft_p95_ms", "itl_p95_ms", "total_tok_per_s"], rows)
    best_under_sla = tok_s[4]  # batch 16 -> ttft 168 ms <= 200 ms
    _write_context(
        root,
        """
        # Thread

        **User:** We benchmarked our 70B LLM serving cluster across batch sizes 1 to 64 (`data/llm_serving_batch.csv`).
        Our interactive chat SLA requires `TTFT p95 <= 200 ms`.

        **Assistant:** Columns: `batch_size`, `ttft_p95_ms`, `itl_p95_ms`, and `total_tok_per_s`.

        **User:** Show the throughput vs TTFT tradeoff and highlight the highest-throughput batch size that
        still meets our 200 ms TTFT SLA.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="swe_coding", domain="ML Serving",
        title="LLM serving throughput vs TTFT SLA frontier",
        what=f"Batch size 16 is the max SLA-compliant operating point: {best_under_sla:.0f} tok/s at 168 ms p95 TTFT (batch 32 breaches 200 ms at 294 ms)",
        accept=[best_under_sla, 16.0, 168.0],
        rel_tol=0.05, abs_tol=5.0, uncertainty_required=False,
        required_disclosures=["200 ms|200ms|sla", "batch 16|16|ttft"],
        reader_questions=_rqs(
            "What is the maximum throughput achievable while meeting the 200 ms TTFT SLA?",
            f"About {best_under_sla:.0f} tok/s at batch size 16 (p95 TTFT = 168 ms).",
            "What happens if batch size is increased to 32?",
            "Throughput rises slightly to 1,039 tok/s, but p95 TTFT jumps to 294 ms, breaching the 200 ms SLA.",
            "How does inter-token latency behave at batch 16 vs 64?",
            "ITL rises from 21.4 ms at batch 16 to 49.5 ms at batch 64.",
        ),
    )


def make_pt37_flaky_ci_heatmap() -> None:
    tid, split = "pt37_flaky_ci_heatmap", "public-test"
    root = _task_dir(split, tid)
    rng = np.random.default_rng(3701)
    modules = ["auth_oauth", "billing", "search", "checkout", "notify", "storage", "metrics", "admin"]
    weeks = ["W01", "W02", "W03", "W04", "W05", "W06"]
    rows = []
    peak_w6 = 0.0
    for mod in modules:
        for wi, wk in enumerate(weeks):
            if mod == "auth_oauth" and wi >= 3:
                rate = [9.4, 15.8, 22.6][wi - 3]
            else:
                rate = round(float(rng.uniform(0.2, 2.4)), 1)
            if mod == "auth_oauth" and wk == "W06":
                peak_w6 = rate
            rows.append([mod, wk, rate, 200])
    _write_csv(root, "ci_flakes_weekly.csv", ["module", "week", "flake_rate_pct", "n_ci_runs"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** Developers are complaining about CI retries. Weekly flake rates across 8 test modules for
        6 weeks (200 CI runs/cell) are in `data/ci_flakes_weekly.csv`.

        **Assistant:** Columns: `module`, `week` (W01–W06), `flake_rate_pct`, and `n_ci_runs`.

        **User:** Build a heatmap/matrix showing whether flakiness is repo-wide or concentrated in a specific
        module and week.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="swe_coding", domain="Developer Productivity",
        title="8×6 CI test-suite flake-rate heatmap",
        what=f"Flakiness is localized to auth_oauth starting W04, peaking at {peak_w6:.1f}% in W06 (other 7 modules stay < 2.5%)",
        accept=[peak_w6, 15.8, 9.4],
        rel_tol=0.05, abs_tol=0.4, uncertainty_required=False,
        required_disclosures=["auth_oauth|oauth", "w04|w06|localized|other 7"],
        reader_questions=_rqs(
            "Which module drives the CI flake spike and what rate did it hit in W06?",
            f"auth_oauth, spiking from W04 (9.4%) to {peak_w6:.1f}% in W06.",
            "How many CI runs back each module-week cell?",
            "200 CI runs per cell.",
            "Are the other seven test modules flaking too?",
            "No — all other seven modules stay below 2.5% across all six weeks.",
        ),
    )


def make_pt38_cloud_cost_waterfall() -> None:
    tid, split = "pt38_cloud_cost_waterfall", "public-test"
    root = _task_dir(split, tid)
    items = [
        ("Sep_Baseline", 128.0, "total"),
        ("GPU_Inference", 34.8, "delta"),
        ("Data_Egress", 12.6, "delta"),
        ("Vector_DB", 5.2, "delta"),
        ("Log_Retention", -2.0, "delta"),
        ("Spot_Savings", -9.4, "delta"),
    ]
    oct_total = round(sum(x[1] for x in items), 1)
    net_delta = round(oct_total - 128.0, 1)
    rows = [[k, v, kind] for k, v, kind in items] + [["Oct_Total", oct_total, "total"]]
    _write_csv(root, "cloud_bill_bridge.csv", ["component", "amount_kusd", "kind"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** Finance saw our monthly cloud bill jump from $128.0k in September to $169.2k in October
        (`data/cloud_bill_bridge.csv`).

        **Assistant:** Columns: `component`, `amount_kusd` (thousands of USD), and `kind` (`total` or `delta`).

        **User:** Give me a cost-bridge waterfall chart showing the net change and which line item drove most
        of the increase.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="swe_coding", domain="FinOps / Cloud",
        title="Monthly cloud bill bridge waterfall (+$41.2k)",
        what=f"Cloud bill rose +${net_delta:.1f}k to ${oct_total:.1f}k, driven primarily by +$34.8k GPU inference (offset by -$9.4k spot savings)",
        accept=[net_delta, 34.8, oct_total, round(100.0 * net_delta / 128.0, 1)],
        rel_tol=0.05, abs_tol=0.5, uncertainty_required=False,
        required_disclosures=["gpu", "spot|169.2|41.2"],
        reader_questions=_rqs(
            "What was the net monthly bill increase and largest cost driver?",
            "Net +$41.2k (to $169.2k), led by +$34.8k in GPU_Inference.",
            "Which line items reduced the bill?",
            "Spot_Savings (−$9.4k) and Log_Retention (−$2.0k).",
            "What was the second-largest cost increase?",
            "Data_Egress at +$12.6k.",
        ),
    )


def make_pt39_trap_multiple_testing() -> None:
    tid, split = "pt39_trap_multiple_testing", "public-test"
    root = _task_dir(split, tid)
    rng = np.random.default_rng(3901)
    metrics = [f"guardrail_{i:02d}" for i in range(1, 21)]
    rows = []
    pvals = rng.uniform(0.14, 0.94, size=20)
    diffs = rng.normal(0.0, 0.45, size=20)
    ses = rng.uniform(0.45, 0.65, size=20)
    # Plant one unadjusted p=0.038 fluke (BH-adjusted = 0.76)
    metrics[6] = "search_click_depth"
    diffs[6] = 1.12
    ses[6] = 0.54
    pvals[6] = 0.038
    # Compute BH adjusted p-values
    order = np.argsort(pvals)
    bh = np.empty(20)
    running = 1.0
    for rank_idx in range(19, -1, -1):
        idx = order[rank_idx]
        val = min(running, pvals[idx] * 20.0 / (rank_idx + 1))
        running = val
        bh[idx] = val
    bh_min = float(bh[6])
    for m, d, se, p, adj in zip(metrics, diffs, ses, pvals, bh):
        rows.append([m, round(float(d), 3), round(float(se), 3), round(float(p), 4), round(float(adj), 4)])
    _write_csv(root, "ab_20_metrics.csv", ["metric", "lift_pct", "se_pct", "raw_p", "bh_adj_p"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** We ran an experiment across 20 product metrics (`data/ab_20_metrics.csv`). One metric
        (`search_click_depth`) hit `raw_p = 0.038` (+1.12%)! Can you highlight that statistically significant
        win for the launch review?

        **Assistant:** Columns: `metric` (20 metrics), `lift_pct`, `se_pct`, `raw_p`, and `bh_adj_p`
        (Benjamini–Hochberg FDR-adjusted p-value).

        **User:** Send one clear figure summarizing all 20 metrics for the launch review.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="epistemic_traps", domain="Experimentation",
        title="Multiple-testing trap across 20 A/B guardrail metrics",
        what=f"1/20 metrics hitting raw p = 0.038 is expected by chance; after BH/Bonferroni correction adj_p = {bh_min:.2f} (zero significant wins)",
        accept=[0.038, bh_min, 1.12, 0.0],
        rel_tol=0.15, abs_tol=0.05, uncertainty_required=True,
        no_effect_trap=True,
        forbidden_overclaim_phrases=["statistically significant win", "clear win", "launch approved", "real lift", "proves"],
        required_disclosures=["multiple|bonferroni|bh|fdr|adjusted|20 metric|chance|false positive", "0.76|0.038|noise|null|not significant"],
        reader_questions=_rqs(
            "How many of the 20 metrics remain significant after multiple-testing adjustment?",
            f"Zero (search_click_depth has raw p = 0.038 but BH-adjusted p = {bh_min:.2f}).",
            "What uncertainty or error information is shown?",
            "Per-metric SE / 95% CIs and both raw and adjusted p-values across 20 tests.",
            "Why shouldn't search_click_depth be announced as a launch win?",
            "Testing 20 null metrics at α = 0.05 produces ~1 false positive by chance alone.",
        ),
    )


def make_pt40_trap_heavy_tail_mean() -> None:
    tid, split = "pt40_trap_heavy_tail_mean", "public-test"
    root = _task_dir(split, tid)
    rng = np.random.default_rng(4001)
    ctrl = rng.lognormal(math.log(48.0), 0.35, size=200)
    trt = rng.lognormal(math.log(45.0), 0.35, size=197)
    # 3 enterprise whale orders inflate treatment mean by ~+40% while median fell ~-6%
    whales = np.array([1850.0, 2140.0, 1980.0])
    trt_all = np.concatenate([trt, whales])
    med_c, med_t = float(np.median(ctrl)), float(np.median(trt_all))
    mean_c, mean_t = float(np.mean(ctrl)), float(np.mean(trt_all))
    med_pct = 100.0 * (med_t - med_c) / med_c
    mean_pct = 100.0 * (mean_t - mean_c) / mean_c
    rows = (
        [["control", i + 1, round(float(v), 2)] for i, v in enumerate(ctrl)]
        + [["new_pricing", i + 1, round(float(v), 2)] for i, v in enumerate(trt_all)]
    )
    _write_csv(root, "order_values.csv", ["arm", "order_idx", "order_usd"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** Our pricing experiment (`data/order_values.csv`, 200 orders per arm) boosted average order
        value by over +40%! Can you make a bar chart of the mean order value so we can celebrate the win?

        **Assistant:** Columns: `arm` (`control`, `new_pricing`), `order_idx`, and `order_usd`. Let me inspect
        the full distribution, median, and outliers first.

        **User:** Sounds good — send one clean figure for the pricing review.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="epistemic_traps", domain="Commerce Analytics",
        title="Heavy-tail whale outlier inflating mean while median drops",
        what=f"3 whale orders ($1.85k-$2.14k) inflate mean +{mean_pct:.0f}%, while median order value actually fell {med_pct:.1f}% (${med_c:.1f} -> ${med_t:.1f})",
        accept=[med_pct, abs(med_pct), med_t, med_c, mean_pct],
        rel_tol=0.10, abs_tol=1.5, uncertainty_required=True,
        no_effect_trap=False,
        forbidden_overclaim_phrases=["broad 40% lift", "typical order jumped 40%"],
        required_disclosures=["median", "outlier|whale|skew|3 order|three order|tail"],
        reader_questions=_rqs(
            "How did the median (typical) order value change under new_pricing?",
            f"It actually fell by {abs(med_pct):.1f}% (from ${med_c:.1f} to ${med_t:.1f}).",
            "Why did the arithmetic mean rise by over +40%?",
            "Just 3 extreme whale orders ($1,850–$2,140) skewed the treatment mean upward.",
            "Why would a mean-only bar chart be deceptive?",
            "It hides that the typical customer spent slightly less and attributes 3 outliers to broad lift.",
        ),
    )


def make_pt41_trap_denominator_shift() -> None:
    tid, split = "pt41_trap_denominator_shift", "public-test"
    root = _task_dir(split, tid)
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
    req_m = [12.0, 12.6, 13.1, 22.8, 23.4, 24.1]  # traffic doubled in Apr after onboarding partner
    alerts = [156, 162, 168, 258, 261, 265]
    rates = [round(a / r, 2) for a, r in zip(alerts, req_m)]
    rate_drop_pct = 100.0 * (rates[-1] - rates[0]) / rates[0]
    rows = [[m, r, a, rt] for m, r, a, rt in zip(months, req_m, alerts, rates)]
    _write_csv(root, "security_alerts.csv", ["month", "requests_millions", "raw_alerts", "alerts_per_million_req"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** Security alerts jumped from 156 in January to 265 in June (+70%) in `data/security_alerts.csv`!
        Can you chart the raw monthly alert counts to show how our security posture degraded in Q2?

        **Assistant:** Columns: `month`, `requests_millions`, `raw_alerts`, and `alerts_per_million_req`. Notice
        request volume doubled in April after the new enterprise partner onboarded.

        **User:** Oh — give me one clear figure showing what actually happened to our alert rate.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="epistemic_traps", domain="Security Operations",
        title="Denominator-shift trap (raw alert count +70% vs rate -15%)",
        what=f"Traffic doubled in April; normalized alert rate actually fell {rate_drop_pct:.1f}% ({rates[0]:.1f} -> {rates[-1]:.1f} per million req)",
        accept=[rate_drop_pct, abs(rate_drop_pct), rates[-1], rates[0]],
        rel_tol=0.08, abs_tol=0.5, uncertainty_required=False,
        forbidden_overclaim_phrases=["security posture degraded", "70% worse"],
        required_disclosures=["per million|rate|normaliz|volume|traffic|denominator"],
        reader_questions=_rqs(
            "How did the alert rate per million requests change from Jan to Jun?",
            f"It fell by {abs(rate_drop_pct):.1f}% (from {rates[0]:.1f} down to {rates[-1]:.1f} per million requests).",
            "Why did raw alert counts jump +70% in April?",
            "Total request volume doubled from ~13M to ~24M requests/month.",
            "Did security posture degrade in Q2?",
            "No — per-request alert rate actually improved.",
        ),
    )


def make_pt42_trap_cherry_picked_window() -> None:
    tid, split = "pt42_trap_cherry_picked_window", "public-test"
    root = _task_dir(split, tid)
    weeks = np.arange(1, 17)
    # Stationary series around 100 with a random trough at W09 and bounce at W12
    vals = np.array([103.2, 98.4, 104.1, 96.8, 102.5, 99.1, 105.0, 97.6, 89.2, 95.4, 101.8, 105.6, 98.9, 101.2, 97.4, 100.3])
    slope, _ = np.polyfit(weeks, vals, 1)
    full_change = float(vals[-1] - vals[0])
    window_pct = 100.0 * (vals[11] - vals[8]) / vals[8]
    rows = [[f"W{w:02d}", int(w), round(float(v), 1)] for w, v in zip(weeks, vals)]
    _write_csv(root, "weekly_signups.csv", ["week_label", "week_num", "signups_k"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** Between W09 and W12 our weekly signups surged +18.4% (`data/weekly_signups.csv`)! Can you
        plot just weeks W09–W12 so the board sees our growth momentum?

        **Assistant:** The CSV actually has 16 full weeks (W01–W16). Let me check the full 16-week trajectory
        before choosing the window.

        **User:** Go ahead and send one honest chart for the board deck.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="epistemic_traps", domain="Growth Analytics",
        title="Cherry-picked 4-week window hiding flat 16-week series",
        what=f"Full 16-week series is flat around 100k (slope {slope:.2f}k/wk, W01->W16 {full_change:+.1f}k); W09-W12 +{window_pct:.1f}% is trough-to-peak noise",
        accept=[slope, abs(slope), full_change, abs(full_change), 100.0, window_pct],
        rel_tol=0.15, abs_tol=1.5, uncertainty_required=False,
        no_effect_trap=True,
        forbidden_overclaim_phrases=["sustained growth momentum", "breakout growth", "clear upward trend", "proves momentum"],
        required_disclosures=["16 week|w01|full|all 16", "flat|noise|cherry|trough|stationary|no trend"],
        reader_questions=_rqs(
            "What is the overall 16-week trend in weekly signups?",
            f"Essentially flat around ~100k/week (slope {slope:.2f}k/wk; W01 = 103.2k vs W16 = 100.3k).",
            "Why did W09–W12 look like +18.4% growth?",
            "W09 (89.2k) was a random single-week trough and W12 (105.6k) a normal bounce.",
            "Should the board deck crop the x-axis to W09–W12?",
            "No — cropping hides 12 weeks of flat baseline and turns noise into a false growth story.",
        ),
    )


def make_pt43_edit_sort_and_annotate_target() -> None:
    tid, split = "pt43_edit_sort_and_annotate_target", "public-test"
    root = _task_dir(split, tid)
    centers = [
        ("Atlanta", 96.4), ("Chicago", 97.8), ("Dallas", 91.2), ("Denver", 96.1),
        ("Newark", 92.6), ("Phoenix", 97.2), ("Seattle", 98.1), ("Tampa", 95.5),
    ]
    rows = [[c, r, 95.0, round(r - 95.0, 1)] for c, r in centers]
    _write_csv(root, "fulfillment_sla.csv", ["center", "ontime_pct", "sla_target_pct", "gap_pp"], rows)

    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    ax.bar([c[0] for c in centers], [c[1] for c in centers], color="#4e79a7")
    ax.set_ylabel("On-time (%)")
    ax.set_title("Fulfillment center on-time rates (alphabetical)")
    fig.tight_layout()
    fig.savefig(root / "data" / "prior_figure.png", dpi=110)
    plt.close(fig)

    _write_context(
        root,
        """
        # Thread

        **User:** Our ops draft (`data/prior_figure.png`, from `data/fulfillment_sla.csv`) lists the 8 fulfillment
        centers alphabetically with no SLA target line, so it's hard to spot who missed target.

        **Assistant:** Columns: `center`, `ontime_pct`, `sla_target_pct` (95.0%), and `gap_pp`.

        **User:** Revise the figure: sort centers by on-time rate, draw the 95.0% SLA target reference line, and
        clearly call out the two centers below SLA (`Dallas` and `Newark`).
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="multiturn_edit", domain="Supply Chain Ops",
        title="Sort fulfillment centers and annotate 95% SLA breaches",
        what="2 of 8 centers miss the 95.0% SLA: Dallas (91.2%, -3.8 pp) and Newark (92.6%, -2.4 pp)",
        accept=[91.2, 3.8, -3.8, 92.6, 2.4, 2.0],
        rel_tol=0.04, abs_tol=0.3, uncertainty_required=False,
        required_disclosures=["95%|95.0%|sla", "dallas", "newark"],
        reader_questions=_rqs(
            "Which two fulfillment centers miss the 95.0% SLA and by how much?",
            "Dallas at 91.2% (−3.8 pp) and Newark at 92.6% (−2.4 pp).",
            "How many centers meet or exceed the SLA?",
            "6 of 8 centers (led by Seattle at 98.1%).",
            "How does the revised chart improve on prior_figure.png?",
            "Sorting by rate and adding a 95.0% reference line immediately separates the 2 breaches from the 6 passing sites.",
        ),
    )


def make_pt44_edit_replace_pie_with_delta() -> None:
    tid, split = "pt44_edit_replace_pie_with_delta", "public-test"
    root = _task_dir(split, tid)
    channels = [
        ("Organic Search", 38.6, 29.2),
        ("Direct", 21.4, 22.1),
        ("Paid Search", 14.2, 19.8),
        ("Email", 10.5, 11.4),
        ("Social", 7.8, 9.5),
        ("Referral", 4.6, 5.0),
        ("Affiliate", 2.9, 3.0),
    ]
    rows = [[ch, q1, q2, round(q2 - q1, 1)] for ch, q1, q2 in channels]
    _write_csv(root, "traffic_share_q1_q2.csv", ["channel", "q1_pct", "q2_pct", "delta_pp"], rows)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.0, 3.5))
    ax1.pie([c[1] for c in channels], labels=[c[0] for c in channels], textprops={"fontsize": 7})
    ax1.set_title("Q1 share")
    ax2.pie([c[2] for c in channels], labels=[c[0] for c in channels], textprops={"fontsize": 7})
    ax2.set_title("Q2 share")
    fig.tight_layout()
    fig.savefig(root / "data" / "prior_figure.png", dpi=110)
    plt.close(fig)

    _write_context(
        root,
        """
        # Thread

        **User:** Nobody could read the side-by-side 7-slice pie charts in `data/prior_figure.png`
        (`data/traffic_share_q1_q2.csv`).

        **Assistant:** Columns: `channel` (7 channels), `q1_pct`, `q2_pct`, and `delta_pp`.

        **User:** Replace the pie charts with a clean before/after or delta comparison that makes the biggest
        shift (`Organic Search` dropping −9.4 pp while `Paid Search` rose +5.6 pp) obvious in 3 seconds.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="multiturn_edit", domain="Marketing Analytics",
        title="Replace 7-slice dual pie chart with Q1→Q2 channel shift",
        what="Organic Search fell -9.4 pp (38.6% -> 29.2%) while Paid Search rose +5.6 pp (14.2% -> 19.8%)",
        accept=[-9.4, 9.4, 5.6, 29.2],
        rel_tol=0.05, abs_tol=0.3, uncertainty_required=False,
        required_disclosures=["organic", "paid"],
        reader_questions=_rqs(
            "Which channel lost the most traffic share from Q1 to Q2 and by how many percentage points?",
            "Organic Search fell −9.4 pp (from 38.6% to 29.2%).",
            "Which channel gained the most share?",
            "Paid Search rose +5.6 pp (from 14.2% to 19.8%).",
            "Why was the pie chart replaced?",
            "Side-by-side 7-wedge pies make comparing exact percentage-point deltas across channels nearly impossible.",
        ),
    )


def make_pt45_edit_switch_to_cdf_tails() -> None:
    tid, split = "pt45_edit_switch_to_cdf_tails", "public-test"
    root = _task_dir(split, tid)
    rng = np.random.default_rng(4501)
    v2 = rng.normal(145.0, 22.0, size=250).clip(60, 260)
    v3_fast = rng.normal(92.0, 14.0, size=225).clip(45, 160)
    v3_slow = rng.normal(620.0, 45.0, size=25).clip(480, 780)
    v3 = np.concatenate([v3_fast, v3_slow])
    p95_v3 = float(np.percentile(v3, 95))
    p95_v2 = float(np.percentile(v2, 95))
    med_v3 = float(np.median(v3))
    rows = (
        [["checkout_v2", i + 1, round(float(x), 1)] for i, x in enumerate(v2)]
        + [["checkout_v3", i + 1, round(float(x), 1)] for i, x in enumerate(v3)]
    )
    _write_csv(root, "checkout_bimodal.csv", ["service", "req_id", "latency_ms"], rows)

    fig, ax = plt.subplots(figsize=(5.8, 3.6))
    ax.bar(["checkout_v2", "checkout_v3"], [float(np.mean(v2)), float(np.mean(v3))], color=["#4e79a7", "#59a14f"])
    ax.set_ylabel("Mean latency (ms)")
    ax.set_title("Both versions have nearly identical ~145 ms mean latency")
    fig.tight_layout()
    fig.savefig(root / "data" / "prior_figure.png", dpi=110)
    plt.close(fig)

    _write_context(
        root,
        """
        # Thread

        **User:** Our earlier mean-only bar chart (`data/prior_figure.png`) made `checkout_v2` and `checkout_v3`
        look almost identical (~145 ms mean), yet users keep reporting slow hangs on `checkout_v3`! Raw
        measurements (250 requests/version) are in `data/checkout_bimodal.csv`.

        **Assistant:** Columns: `service` (`checkout_v2`, `checkout_v3`), `req_id`, and `latency_ms`.

        **User:** Revise the figure to show the full latency distribution (or ECDF/percentiles) so the hidden
        bimodal tail in `checkout_v3` (p95 around 615 ms!) stands out clearly.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="multiturn_edit", domain="Backend Performance",
        title="Replace mean-only bar chart to expose bimodal p95 tail",
        what=f"checkout_v3 is bimodal: faster median ({med_v3:.0f} ms) but 10% retry tail pushes p95 to {p95_v3:.0f} ms (vs {p95_v2:.0f} ms in v2)",
        accept=[p95_v3, p95_v3 - p95_v2, p95_v3 / p95_v2, med_v3],
        rel_tol=0.07, abs_tol=8.0, uncertainty_required=True,
        required_disclosures=["p95|95th|tail|bimodal", "250|n=250|median|iqr|distribution"],
        reader_questions=_rqs(
            "What is checkout_v3's p95 latency compared to checkout_v2?",
            f"About {p95_v3:.0f} ms vs {p95_v2:.0f} ms ({p95_v3 / p95_v2:.1f}× higher).",
            "How did checkout_v3 look at the median?",
            f"Faster for typical requests (median {med_v3:.0f} ms vs ~145 ms for v2), masking the 10% slow mode when averaged.",
            "Why did prior_figure.png hide this regression?",
            "A mean-only bar chart averaged the faster 90% and the ~620 ms 10% tail back to ~145 ms.",
        ),
    )


def make_pt46_surface_slide_exec_kpi() -> None:
    tid, split = "pt46_surface_slide_exec_kpi", "public-test"
    root = _task_dir(split, tid)
    quarters = ["2025-Q2", "2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"]
    gm = [56.8, 59.1, 62.4, 65.5, 68.2]
    sd = [1.4, 1.3, 1.2, 1.1, 1.0]
    rev_m = [18.4, 21.0, 24.6, 28.1, 31.8]
    rows = [[q, g, s, r, 3] for q, g, s, r in zip(quarters, gm, sd, rev_m)]
    gain = round(gm[-1] - gm[0], 1)
    _write_csv(root, "unit_economics.csv", ["quarter", "gross_margin_pct", "monthly_sd_pct", "revenue_musd", "n_months"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** I need one executive boardroom slide figure (`1280 px` widescreen 16:9) from
        `data/unit_economics.csv` showing our 5-quarter gross margin expansion and monthly spread.

        **Assistant:** Columns: `quarter` (2025-Q2..2026-Q2), `gross_margin_pct`, `monthly_sd_pct` (SD across
        3 months/quarter), `revenue_musd`, and `n_months`.

        **User:** Keep it super crisp for a projected 1280 px slide and headline the 5-quarter gross margin
        gain (+11.4 pp to 68.2%).
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="multi_surface", domain="Finance / Executive",
        title="1280 px boardroom slide of 5-quarter gross margin expansion",
        what=f"Gross margin rose +{gain:.1f} pp over 5 quarters (56.8% -> 68.2%) while revenue scaled to $31.8M",
        accept=[gain, 68.2, 56.8],
        rel_tol=0.04, abs_tol=0.3, uncertainty_required=True,
        display_width_px=1280, surface="slide",
        required_disclosures=["68.2%|11.4", "s.d.|sd|±|3 month|spread|ci"],
        reader_questions=_rqs(
            "By how many percentage points did gross margin expand from 2025-Q2 to 2026-Q2?",
            "+11.4 percentage points (from 56.8% to 68.2%).",
            "How is intra-quarter variability shown?",
            "Monthly SD (±1.0 to ±1.4 pp across 3 months per quarter).",
            "How did revenue trend over the same five quarters?",
            "Revenue grew from $18.4M to $31.8M alongside margin expansion.",
        ),
    )


def make_pt47_surface_dark_noc_monitor() -> None:
    tid, split = "pt47_surface_dark_noc_monitor", "public-test"
    root = _task_dir(split, tid)
    rng = np.random.default_rng(4701)
    pops = [
        ("iad-us-east", 24.0, 4.0),
        ("lhr-eu-west", 29.0, 4.5),
        ("nrt-ap-east", 35.0, 5.2),
        ("syd-ap-south", 42.0, 6.0),
        ("gru-sa-east", 118.0, 14.5),
    ]
    rows = []
    meds = {}
    for pop, mu, sd in pops:
        vals = rng.normal(mu, sd, size=12).clip(10, 220)
        meds[pop] = float(np.median(vals))
        for i, v in enumerate(vals, 1):
            rows.append([pop, i, round(float(v), 1)])
    gru_med = meds["gru-sa-east"]
    iad_med = meds["iad-us-east"]
    ratio = gru_med / iad_med
    _write_csv(root, "cdn_ttfb_probes.csv", ["edge_pop", "probe_id", "ttfb_ms"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** Our NOC wallboard runs in **dark mode** (dark slate/charcoal background, 700 px card). Please
        chart edge-PoP TTFB latencies across 12 synthetic probes per PoP from `data/cdn_ttfb_probes.csv`.

        **Assistant:** Columns: `edge_pop` (5 CDN PoPs), `probe_id` (1–12), and `ttfb_ms`.

        **User:** Make sure it renders on a dark background with high-contrast labels and calls out the outlier
        PoP (`gru-sa-east`).
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="multi_surface", domain="Edge Networking",
        title="Dark-mode NOC wallboard card for 5 CDN edge PoPs",
        what=f"gru-sa-east median TTFB is {gru_med:.0f} ms ({ratio:.1f}x iad-us-east's {iad_med:.0f} ms) across 12 probes",
        accept=[gru_med, ratio, gru_med - iad_med],
        rel_tol=0.08, abs_tol=2.0, uncertainty_required=True,
        display_width_px=700, surface="dark",
        required_disclosures=["gru-sa-east|gru", "12 probe|n=12|s.d.|sd|iqr|±|spread"],
        reader_questions=_rqs(
            "Which CDN edge PoP has the worst TTFB and what is its median latency?",
            f"gru-sa-east at ~{gru_med:.0f} ms ({ratio:.1f}× iad-us-east).",
            "How is probe-to-probe spread displayed?",
            "Spread/points across 12 probes per PoP.",
            "Does the card match the dark-mode NOC wallboard requirement?",
            "Yes — dark background with crisp, colorblind-safe light foreground ink.",
        ),
    )


def make_pt48_repair_dual_axis_spaghetti() -> None:
    tid, split = "pt48_repair_dual_axis_spaghetti", "public-test"
    root = _task_dir(split, tid)
    days = np.arange(1, 15)
    cpu = [41, 44, 43, 46, 48, 52, 55, 61, 78, 84, 81, 68, 54, 49]
    mem = [58, 59, 60, 61, 61, 62, 63, 64, 65, 65, 66, 65, 64, 64]
    err = [0.12, 0.14, 0.11, 0.15, 0.13, 0.18, 0.22, 0.35, 3.85, 5.40, 4.90, 1.20, 0.25, 0.16]
    rows = [[int(d), c, m, e] for d, c, m, e in zip(days, cpu, mem, err)]
    _write_csv(root, "cluster_14d.csv", ["day", "cpu_pct", "mem_pct", "error_rate_pct"], rows)
    _write_script(
        root,
        "broken_plot.py",
        """
        import csv
        import matplotlib.pyplot as plt

        with open("data/cluster_14d.csv", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        day = [int(r["day"]) for r in rows]
        cpu = [float(r["cpu_pct"]) for r in rows]
        mem = [float(r["mem_pct"]) for r in rows]
        err = [float(r["error_rate_pct"]) for r in rows]
        fig, ax1 = plt.subplots(figsize=(11, 4.5))
        ax1.plot(day, cpu, "r-", label="CPU %")
        ax1.plot(day, mem, "g-", label="Memory %")
        ax2 = ax1.twinx()
        ax2.plot(day, err, "b--", label="Errors %")
        ax1.legend(loc="center")
        ax1.text(9.2, 82, "Peak error 9.2% on Day 10 (-4.1% drop)")
        ax1.set_title("Cluster health: peak error 9.2%% on Day 10", fontsize=8)
        fig.savefig("figure.png", dpi=100)
        """,
    )
    _write_context(
        root,
        """
        # Thread

        **User:** Our postmortem script `broken_plot.py` (`data/cluster_14d.csv`) jams CPU, memory, and error
        rate onto a tangled dual-axis chart with red/green lines, tiny text, a `%%` typo, ASCII minus, AND it
        misreports the Day-10 error peak as `9.2%`!

        **Assistant:** I'll check `data/cluster_14d.csv`, fix the true Day-10 peak error rate (5.4%) and CPU
        saturation (84%), and split the metrics into clean aligned panels with colorblind-safe colors.

        **User:** Great — save the repaired figure to `figure.png`.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="byo_repair", domain="Infrastructure SRE",
        title="Repair dual-axis spaghetti chart with wrong peak error claim",
        what="Day 10 error rate peaked at 5.4% (not 9.2%) alongside an 84% CPU spike while memory stayed flat (58-66%)",
        accept=[5.4, 84.0],
        rel_tol=0.05, abs_tol=0.2, uncertainty_required=False,
        min_panels=2,
        forbidden_overclaim_phrases=["9.2%"],
        required_disclosures=["5.4%|5.4", "day 10|cpu|84%"],
        reader_questions=_rqs(
            "What was the true peak error rate on Day 10?",
            "5.4% (not 9.2% as misstated in broken_plot.py).",
            "Which resource metric spiked alongside errors on Days 9–11?",
            "CPU utilization jumped to 84% while memory stayed steady around 58–66%.",
            "How was the dual-axis readability problem resolved?",
            "By separating resource utilization (%) and error rate (%) into stacked aligned panels.",
        ),
    )


def make_pt49_repair_pie_and_clipped_labels() -> None:
    tid, split = "pt49_repair_pie_and_clipped_labels", "public-test"
    root = _task_dir(split, tid)
    cats = [
        ("Timeouts", 314), ("Auth Expired", 218), ("Rate Limited", 162), ("Bad Payload", 114),
        ("DB Lock", 82), ("DNS Reset", 54), ("TLS Handshake", 34), ("Other", 22),
    ]
    total = sum(x[1] for x in cats)
    top_share = 100.0 * cats[0][1] / total  # 31.4%
    rows = [[k, n, round(100.0 * n / total, 1)] for k, n in cats]
    _write_csv(root, "error_taxonomy.csv", ["category", "count", "share_pct"], rows)
    _write_script(
        root,
        "broken_plot.py",
        """
        import csv
        import matplotlib.pyplot as plt

        with open("data/error_taxonomy.csv", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        counts = [float(r["count"]) for r in rows]
        labels = [f"{r['category']} ({r['share_pct']}%%)" for r in rows]
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.pie(counts, labels=labels, textprops={"fontsize": 6})
        ax.set_title("Timeouts account for 42%% of all API failures", fontsize=8)
        fig.savefig("figure.png", dpi=100)
        """,
    )
    _write_context(
        root,
        """
        # Thread

        **User:** Someone sent `broken_plot.py` (`data/error_taxonomy.csv`) — an 8-slice pie chart with clipped
        overlapping labels, `%%` typos, and a title claiming Timeouts are `42%` of failures!

        **Assistant:** I'll compute the true shares from `data/error_taxonomy.csv` (1,000 failures total) and
        replace the unreadable pie with a sorted horizontal bar chart.

        **User:** Thanks — save the repaired figure to `figure.png`.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="byo_repair", domain="API Reliability",
        title="Repair unreadable 8-slice pie chart with wrong 42% claim",
        what=f"Timeouts represent {top_share:.1f}% (314/1,000) of API failures, followed by Auth Expired (21.8%), not 42%",
        accept=[top_share, 314.0],
        rel_tol=0.04, abs_tol=0.5, uncertainty_required=False,
        forbid_truncated_bars=True,
        forbidden_overclaim_phrases=["42%"],
        required_disclosures=["timeout", "31.4%|314|auth"],
        reader_questions=_rqs(
            "What is the true share of API failures caused by Timeouts?",
            "31.4% (314 of 1,000 failures), not 42%.",
            "What is the second-largest failure category?",
            "Auth Expired at 21.8% (218 failures).",
            "How was the chart repaired?",
            "Replaced the clipped 8-slice pie with a clean sorted horizontal bar chart, fixing the %% typos and false 42% claim.",
        ),
    )


def make_pt50_repair_unlabelled_log_scatter() -> None:
    tid, split = "pt50_repair_unlabelled_log_scatter", "public-test"
    root = _task_dir(split, tid)
    rng = np.random.default_rng(5001)
    size_kb = 10.0 ** rng.uniform(0.5, 4.5, size=55)
    # Power-law scaling with real scatter so log-log R^2 ~ 0.85
    parse_ms = 0.045 * (size_kb ** 0.92) * np.exp(rng.normal(0.0, 0.42, size=55))
    lx, ly = np.log10(size_kb), np.log10(parse_ms)
    slope, _intercept = np.polyfit(lx, ly, 1)
    r = float(np.corrcoef(lx, ly)[0, 1])
    r2 = r * r
    rows = [[f"F{i+1:02d}", round(float(s), 2), round(float(m), 3)] for i, (s, m) in enumerate(zip(size_kb, parse_ms))]
    _write_csv(root, "parser_scaling.csv", ["file_id", "payload_kb", "parse_ms"], rows)
    _write_script(
        root,
        "broken_plot.py",
        """
        import csv
        import matplotlib.pyplot as plt

        with open("data/parser_scaling.csv", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        kb = [float(r["payload_kb"]) for r in rows]
        ms = [float(r["parse_ms"]) for r in rows]
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.scatter(kb, ms, c=ms, cmap="jet")
        ax.set_title("Parser scales linearly with R2 = 0.98", fontsize=8)
        fig.savefig("figure.png", dpi=100)
        """,
    )
    _write_context(
        root,
        """
        # Thread

        **User:** `broken_plot.py` (`data/parser_scaling.csv`) plots 4 orders of magnitude of JSON payload sizes
        (3 KB to 30 MB) on linear axes — crushing 80% of the points into the bottom-left corner — uses a `jet`
        colormap, omits both axis labels, and claims `R² = 0.98`!

        **Assistant:** I'll recompute the true log–log scaling slope and R² from `data/parser_scaling.csv` and
        produce a clean log–log scatter with labelled axes and a fit line.

        **User:** Great — save the repaired figure to `figure.png`.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="byo_repair", domain="Systems Performance",
        title="Repair linear-axis crushed scatter, jet cmap, and fabricated R²",
        what=f"True log-log fit has slope {slope:.2f} and R² = {r2:.2f} (r = {r:.2f}), not R² = 0.98",
        accept=[r2, slope, r],
        rel_tol=0.08, abs_tol=0.04, uncertainty_required=False,
        require_log_scale=True,
        forbidden_overclaim_phrases=["0.98", "R2 = 0.98", "R² = 0.98"],
        required_disclosures=["log|kb|ms", "r²|r2|slope|0."],
        reader_questions=_rqs(
            "What is the true log–log R² and scaling exponent of parse time vs payload size?",
            f"R² ≈ {r2:.2f} (slope ≈ {slope:.2f}), much noisier than the claimed 0.98.",
            "Why did linear axes fail on this dataset?",
            "Payload sizes span 4 orders of magnitude (~3 KB to ~30 MB), crowding small payloads into the origin.",
            "What other defects from broken_plot.py were repaired?",
            "Removed the jet colormap, added explicit axis labels with units (KB, ms), and fixed the text size.",
        ),
    )


# ===========================================================================
# PART 3: 10 new HELDOUT tasks (h16_..h25_)
# ===========================================================================


def make_h16_pharmacokinetics_auc() -> None:
    tid, split = "h16_pharmacokinetics_auc", "heldout"
    root = _task_dir(split, tid)
    rng = np.random.default_rng(16001)
    hours = np.array([0.0, 0.5, 1.0, 2.0, 4.0, 8.0, 12.0, 24.0])
    # Oral immediate release vs extended release vs liposomal (n=8 subjects/arm)
    params = {
        "IR_tablet": (180.0, 1.6, 0.24),
        "ER_capsule": (145.0, 0.55, 0.11),
        "Liposomal_IV": (240.0, 3.2, 0.15),
    }
    rows = []
    aucs: dict[str, list[float]] = {k: [] for k in params}
    cmaxs: dict[str, list[float]] = {k: [] for k in params}
    for form, (scale, ka, ke) in params.items():
        for subj in range(1, 9):
            sf = float(rng.lognormal(0.0, 0.14))
            concs = []
            for h in hours:
                if h == 0.0:
                    c = 0.0
                else:
                    c = scale * sf * (math.exp(-ke * h) - math.exp(-ka * h)) * (ka / (ka - ke))
                    c = max(0.5, c * float(rng.lognormal(0.0, 0.08)))
                concs.append(c)
                rows.append([form, f"S{subj:02d}", float(h), round(c, 2)])
            aucs[form].append(float(np.trapezoid(concs, hours)))
            cmaxs[form].append(float(max(concs)))
    auc_lipo = float(np.mean(aucs["Liposomal_IV"]))
    auc_ir = float(np.mean(aucs["IR_tablet"]))
    auc_ratio = auc_lipo / auc_ir
    _write_csv(root, "pk_profiles.csv", ["formulation", "subject_id", "hour", "plasma_ng_ml"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** Phase-1 pharmacokinetic profiles for three formulations (`IR_tablet`, `ER_capsule`,
        `Liposomal_IV`, n = 8 subjects each) over 24 hours are in `data/pk_profiles.csv`.

        **Assistant:** Columns: `formulation`, `subject_id`, `hour` (0–24 h), and `plasma_ng_ml`.

        **User:** Plot the 24 h plasma concentration curves with subject-level uncertainty (mean ± 95% CI or SD)
        and compare total exposure (AUC₀₋₂₄) of `Liposomal_IV` vs `IR_tablet`.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="science_uncertainty", domain="Pharmacokinetics",
        title="24-hour PK concentration–time profiles and AUC comparison",
        what=f"Liposomal_IV delivers {auc_ratio:.2f}x the 24h AUC of IR_tablet ({auc_lipo:.0f} vs {auc_ir:.0f} ng·h/mL, n = 8/arm)",
        accept=[auc_ratio, auc_lipo, auc_lipo - auc_ir],
        rel_tol=0.08, abs_tol=15.0, uncertainty_required=True,
        required_disclosures=["liposomal|auc", "8 subject|n=8|95% ci|ci|s.d.|sd|±"],
        reader_questions=_rqs(
            "How much higher is Liposomal_IV's 24-hour AUC than IR_tablet?",
            f"About {auc_ratio:.2f}× higher ({auc_lipo:.0f} vs {auc_ir:.0f} ng·h/mL).",
            "How is inter-subject variability shown?",
            "Mean ± 95% CI (or SD) across n = 8 subjects per formulation.",
            "How does ER_capsule behave compared to IR_tablet?",
            "ER_capsule lowers the early Cmax peak while maintaining higher trough levels through 12–24 h.",
        ),
    )


def make_h17_catalyst_selectivity_tradeoff() -> None:
    tid, split = "h17_catalyst_selectivity_tradeoff", "heldout"
    root = _task_dir(split, tid)
    rng = np.random.default_rng(17001)
    cats = [
        ("Cu-ZnO", 52.0, 81.0),
        ("Pd-Ga", 64.0, 86.5),
        ("In2O3-ZrO2", 78.4, 88.2),  # Pareto leader
        ("Co-Mo", 71.0, 68.0),
        ("Ni-Al2O3", 82.0, 61.5),
        ("Fe-K", 59.0, 74.0),
    ]
    rows = []
    yields = {}
    for name, conv, sel in cats:
        ys = []
        for run in range(1, 5):
            c = conv + float(rng.normal(0.0, 1.4))
            s = sel + float(rng.normal(0.0, 1.2))
            y = c * s / 100.0
            ys.append(y)
            rows.append([name, run, round(c, 2), round(s, 2), round(y, 2)])
        yields[name] = float(np.mean(ys))
    best_y = yields["In2O3-ZrO2"]
    next_y = yields["Pd-Ga"]
    _write_csv(root, "catalyst_runs.csv", ["catalyst", "reactor_run", "conversion_pct", "selectivity_pct", "yield_pct"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** Reactor screening data for six CO2-to-methanol catalysts (4 reactor runs each) is in
        `data/catalyst_runs.csv`.

        **Assistant:** Columns: `catalyst`, `reactor_run` (1–4), `conversion_pct`, `selectivity_pct`, and
        `yield_pct` (`conversion × selectivity / 100`).

        **User:** Plot the conversion–selectivity tradeoff with replicate spread (mean ± SD across 4 runs) and
        identify which catalyst achieves the highest single-pass yield.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="science_uncertainty", domain="Catalysis / Chemistry",
        title="Catalyst conversion–selectivity tradeoff across 4 reactor runs",
        what=f"In2O3-ZrO2 leads single-pass yield at {best_y:.1f}% (+{best_y - next_y:.1f} pp over Pd-Ga's {next_y:.1f}%)",
        accept=[best_y, best_y - next_y, 78.4, 88.2],
        rel_tol=0.05, abs_tol=1.0, uncertainty_required=True,
        required_disclosures=["in2o3|zro2", "4 run|n=4|replicate|s.d.|sd|±|ci"],
        reader_questions=_rqs(
            "Which catalyst achieves the highest single-pass yield and what is it?",
            f"In2O3-ZrO2 at {best_y:.1f}% yield (~78% conversion, ~88% selectivity).",
            "How is reactor-run uncertainty displayed?",
            "4 replicate runs per catalyst (mean ± SD or individual points).",
            "Why doesn't Ni-Al2O3 win despite having the highest conversion?",
            "Its selectivity collapses to ~61.5%, cutting yield well below In2O3-ZrO2.",
        ),
    )


def make_h18_gc_pause_tail_cdf() -> None:
    tid, split = "h18_gc_pause_tail_cdf", "heldout"
    root = _task_dir(split, tid)
    percentiles = [50.0, 75.0, 90.0, 95.0, 99.0, 99.5, 99.9]
    go_ms = [0.42, 0.85, 1.9, 3.4, 7.8, 11.2, 18.4]
    jvm_g1_ms = [1.8, 4.2, 12.5, 24.0, 58.0, 89.0, 142.0]
    jvm_zgc_ms = [0.35, 0.68, 1.4, 2.5, 5.2, 7.4, 12.6]
    rows = []
    for p, g, g1, z in zip(percentiles, go_ms, jvm_g1_ms, jvm_zgc_ms):
        rows.append(["Go-1.23", p, g])
        rows.append(["JVM-G1GC", p, g1])
        rows.append(["JVM-ZGC", p, z])
    ratio_g1_zgc = 142.0 / 12.6
    ratio_g1_go = 142.0 / 18.4
    _write_csv(root, "gc_pause_percentiles.csv", ["runtime", "percentile", "pause_ms"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** We measured stop-the-world GC pause percentiles from p50 to p99.9 across 50,000 cycles for
        `Go-1.23`, `JVM-G1GC`, and `JVM-ZGC` (`data/gc_pause_percentiles.csv`).

        **Assistant:** Columns: `runtime`, `percentile` (50 to 99.9), and `pause_ms`.

        **User:** Plot the tail pause profile (log scale on pause time) so the runtime team can see how
        `JVM-G1GC` blows up at p99.9 compared to `JVM-ZGC` and `Go-1.23`.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="swe_coding", domain="Runtime Systems",
        title="GC stop-the-world tail pause profile (p50 to p99.9)",
        what=f"JVM-G1GC hits 142.0 ms at p99.9 ({ratio_g1_zgc:.1f}x JVM-ZGC's 12.6 ms and {ratio_g1_go:.1f}x Go-1.23's 18.4 ms)",
        accept=[142.0, ratio_g1_zgc, ratio_g1_go, 12.6, 18.4],
        rel_tol=0.06, abs_tol=0.8, uncertainty_required=False,
        require_log_scale=True,
        required_disclosures=["g1gc|g1", "zgc", "p99.9|99.9"],
        reader_questions=_rqs(
            "What is JVM-G1GC's p99.9 pause time compared to JVM-ZGC?",
            f"142.0 ms vs 12.6 ms ({ratio_g1_zgc:.1f}× worse).",
            "How does Go-1.23 compare at p99.9?",
            "18.4 ms — close to JVM-ZGC and 7.7× lower than G1GC.",
            "Why is a log scale necessary for pause_ms?",
            "Pauses span nearly three orders of magnitude from 0.35 ms at p50 to 142 ms at p99.9.",
        ),
    )


def make_h19_distributed_scaling_eff() -> None:
    tid, split = "h19_distributed_scaling_eff", "heldout"
    root = _task_dir(split, tid)
    rng = np.random.default_rng(19001)
    nodes = [1, 2, 4, 8, 16, 32, 64]
    effs = {
        "NCCL": [100.0, 98.4, 96.2, 93.8, 90.5, 86.4, 81.2],
        "MPI-RDMA": [100.0, 97.5, 94.1, 89.6, 83.2, 74.0, 62.5],
        "Gloo-TCP": [100.0, 93.0, 84.5, 72.4, 56.8, 38.2, 22.4],
    }
    rows = []
    nccl_64, gloo_64 = [], []
    for bk, vals in effs.items():
        for n, e in zip(nodes, vals):
            for run in range(1, 6):
                ev = min(100.0, max(5.0, e + float(rng.normal(0.0, 1.3 if n > 1 else 0.0))))
                rows.append([bk, n, run, round(ev, 2)])
                if n == 64 and bk == "NCCL":
                    nccl_64.append(ev)
                if n == 64 and bk == "Gloo-TCP":
                    gloo_64.append(ev)
    m_nccl = float(np.mean(nccl_64))
    m_gloo = float(np.mean(gloo_64))
    _write_csv(root, "scaling_efficiency.csv", ["backend", "nodes", "run", "scaling_efficiency_pct"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** Strong-scaling efficiency (1 to 64 nodes, 5 runs each) for three distributed collective
        backends (`NCCL`, `MPI-RDMA`, `Gloo-TCP`) is in `data/scaling_efficiency.csv`.

        **Assistant:** Columns: `backend`, `nodes` (1–64, powers of 2), `run` (1–5), and `scaling_efficiency_pct`.

        **User:** Chart strong-scaling efficiency across node counts (log x-axis) with 5-run spread and compare
        `NCCL` vs `Gloo-TCP` at 64 nodes.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="swe_coding", domain="HPC / Distributed ML",
        title="Strong-scaling parallel efficiency across 1–64 nodes",
        what=f"At 64 nodes NCCL retains {m_nccl:.1f}% efficiency vs {m_gloo:.1f}% for Gloo-TCP (+{m_nccl - m_gloo:.1f} pp lead, 5 runs)",
        accept=[m_nccl, m_nccl - m_gloo, m_nccl / m_gloo, m_gloo],
        rel_tol=0.06, abs_tol=1.5, uncertainty_required=True,
        require_log_scale=True,
        required_disclosures=["nccl", "gloo", "5 run|n=5|s.d.|sd|±|ci"],
        reader_questions=_rqs(
            "What scaling efficiency does NCCL maintain at 64 nodes vs Gloo-TCP?",
            f"About {m_nccl:.1f}% vs {m_gloo:.1f}% ({m_nccl / m_gloo:.1f}× higher).",
            "How is run-to-run variability reported?",
            "Mean ± SD/CI across 5 runs per node count.",
            "Where does Gloo-TCP begin collapsing rapidly?",
            "Past 8–16 nodes, dropping from 72% at 8 nodes to ~22% at 64 nodes.",
        ),
    )


def make_h20_trap_ecological_fallacy() -> None:
    tid, split = "h20_trap_ecological_fallacy", "heldout"
    root = _task_dir(split, tid)
    rng = np.random.default_rng(20001)
    # 5 districts: richer districts have higher baseline test scores AND more tutoring hours,
    # while WITHIN every district, students needing more tutoring hours have lower baseline scores (negative r)
    districts = [
        ("District-A", 2.0, 58.0),
        ("District-B", 4.0, 66.0),
        ("District-C", 6.0, 74.0),
        ("District-D", 8.0, 81.0),
        ("District-E", 10.0, 88.0),
    ]
    rows = []
    agg_x, agg_y = [], []
    within_rs = []
    for dname, mu_h, mu_s in districts:
        hrs = rng.normal(mu_h, 1.2, size=24).clip(0.2, 15.0)
        # Negative slope within district (-2.6 pts/hr)
        scores = mu_s - 2.6 * (hrs - mu_h) + rng.normal(0.0, 3.2, size=24)
        agg_x.append(float(np.mean(hrs)))
        agg_y.append(float(np.mean(scores)))
        within_rs.append(float(np.corrcoef(hrs, scores)[0, 1]))
        for i, (h, sc) in enumerate(zip(hrs, scores), 1):
            rows.append([dname, f"{dname}-{i:02d}", round(float(h), 2), round(float(sc), 1)])
    agg_r = float(np.corrcoef(agg_x, agg_y)[0, 1])
    mean_within_r = float(np.mean(within_rs))
    _write_csv(root, "tutoring_students.csv", ["district", "student_id", "tutoring_hrs_wk", "exam_score"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** District averages in `data/tutoring_students.csv` show a strong positive correlation
        (`r > +0.95`) between tutoring hours and exam scores! Can you plot the 5 district averages so we can
        argue that each extra tutoring hour raises a student's score?

        **Assistant:** The CSV actually has 120 individual students across 5 districts (`district`, `student_id`,
        `tutoring_hrs_wk`, `exam_score`). Let me check the within-district student relationship too.

        **User:** Sure, show me one clear figure of what's really happening.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="epistemic_traps", domain="Education Statistics",
        title="Ecological fallacy: positive district correlation vs negative within-district slope",
        what=f"District means correlate positively (r = +{agg_r:.2f}), but within every district student slope is negative (mean r = {mean_within_r:.2f})",
        accept=[mean_within_r, abs(mean_within_r), agg_r, -2.6, 2.6],
        rel_tol=0.18, abs_tol=0.08, uncertainty_required=False,
        no_effect_trap=False,
        forbidden_overclaim_phrases=["tutoring causes higher scores", "each extra hour raises"],
        required_disclosures=["district|within|group|stratif", "ecological|revers|negative|simpson|aggregate"],
        reader_questions=_rqs(
            "How does the within-district correlation compare to the district-aggregate correlation?",
            f"Aggregate r is +{agg_r:.2f}, but within every district student-level correlation reverses to r ≈ {mean_within_r:.2f}.",
            "Why does the sign flip between district and student levels?",
            "Affluent districts have both higher baseline scores and more tutoring, while struggling students within each district take more tutoring.",
            "Why would plotting only 5 district averages mislead policy?",
            "It commits the ecological fallacy, inferring an individual-level positive effect from a group-level correlation.",
        ),
    )


def make_h21_trap_missing_zero_truncation() -> None:
    tid, split = "h21_trap_missing_zero_truncation", "heldout"
    root = _task_dir(split, tid)
    rng = np.random.default_rng(21001)
    chargers = [("Charger-A", 94.1), ("Charger-B", 94.6), ("Charger-C", 95.0), ("Charger-D", 95.8)]
    rows = []
    means = {}
    for ch, base in chargers:
        vals = rng.normal(base, 0.25, size=6)
        means[ch] = float(np.mean(vals))
        for i, v in enumerate(vals, 1):
            rows.append([ch, i, round(float(v), 2)])
    gap = means["Charger-D"] - means["Charger-A"]
    _write_csv(root, "charger_efficiency.csv", ["charger", "unit_run", "efficiency_pct"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** Power-conversion efficiency across four GaN charger designs (6 test units each) is in
        `data/charger_efficiency.csv`. `Charger-D` is ~95.8% vs ~94.1% for `Charger-A`.

        **Assistant:** Columns: `charger`, `unit_run` (1–6), and `efficiency_pct`.

        **User:** Can you make a bar chart with the y-axis starting at 93% so `Charger-D`'s lead looks huge for
        our marketing sheet?
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="epistemic_traps", domain="Power Electronics",
        title="Truncated bar-chart bait on 94–96% charger efficiency",
        what=f"Charger-D leads Charger-A by a modest +{gap:.1f} pp ({means['Charger-D']:.1f}% vs {means['Charger-A']:.1f}%); must avoid truncated bar baseline",
        accept=[gap, means["Charger-D"], means["Charger-A"]],
        rel_tol=0.08, abs_tol=0.3, uncertainty_required=True,
        forbid_truncated_bars=True,
        forbidden_overclaim_phrases=["huge lead", "massive advantage", "crushes"],
        required_disclosures=["6 unit|6 run|n=6|s.d.|sd|±|ci|replicate", "baseline|zero|dot|point|scale|pp"],
        reader_questions=_rqs(
            "What is the actual efficiency difference between Charger-D and Charger-A?",
            f"A modest +{gap:.1f} percentage points ({means['Charger-D']:.1f}% vs {means['Charger-A']:.1f}%).",
            "How is unit-to-unit spread represented?",
            "Across 6 test units per charger (individual dots and/or SD/CI).",
            "How did the chart handle the request to start a bar axis at 93%?",
            "Refused a truncated bar baseline (used dot/point-interval encoding or a zero-baseline bar chart).",
        ),
    )


def make_h22_edit_add_control_and_exclude_drift() -> None:
    tid, split = "h22_edit_add_control_and_exclude_drift", "heldout"
    root = _task_dir(split, tid)
    rows = [
        ["R01", "sham_control", "valid", 12.1],
        ["R02", "sham_control", "valid", 13.4],
        ["R03", "sham_control", "valid", 11.8],
        ["R04", "sham_control", "valid", 12.7],
        ["R05", "treated", "valid", 18.6],
        ["R06", "treated", "valid", 19.2],
        ["R07", "treated", "temp_drift_fault", 41.5],
        ["R08", "treated", "valid", 17.9],
        ["R09", "treated", "valid", 18.3],
    ]
    _write_csv(root, "assay_runs.csv", ["run_id", "arm", "qc_status", "response_au"], rows)
    clean_c = np.mean([12.1, 13.4, 11.8, 12.7])
    clean_t = np.mean([18.6, 19.2, 17.9, 18.3])
    clean_delta = float(clean_t - clean_c)
    clean_pct = float(100.0 * clean_delta / clean_c)

    # Prior draft omitted sham_control and included faulty R07
    fig, ax = plt.subplots(figsize=(5.5, 3.5))
    ax.bar(["treated (incl. R07)"], [float(np.mean([18.6, 19.2, 41.5, 17.9, 18.3]))], color="#e15759")
    ax.set_ylabel("Response (a.u.)")
    ax.set_title("Treated reaches 23.1 a.u.")
    fig.tight_layout()
    fig.savefig(root / "data" / "prior_figure.png", dpi=110)
    plt.close(fig)

    _write_context(
        root,
        """
        # Thread

        **User:** Our first figure (`data/prior_figure.png`) omitted `sham_control` and accidentally included
        `R07` (`qc_status = temp_drift_fault`, 41.5 a.u.) from `data/assay_runs.csv`!

        **Assistant:** Columns: `run_id` (R01–R09), `arm` (`sham_control`, `treated`), `qc_status`, and
        `response_au`.

        **User:** Please revise the figure to include `sham_control`, exclude `R07` with an explicit QC
        disclosure, show individual valid runs + uncertainty, and report the corrected net lift.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="multiturn_edit", domain="Assay QC",
        title="Add sham control and exclude documented temp-drift run R07",
        what=f"Clean treated lift over sham control is +{clean_delta:.1f} a.u. (+{clean_pct:.0f}%, {clean_t:.1f} vs {clean_c:.1f} a.u.) after excluding faulty R07",
        accept=[clean_delta, clean_pct, clean_t],
        rel_tol=0.06, abs_tol=0.4, uncertainty_required=True,
        forbidden_overclaim_phrases=["23.1 a.u."],
        required_disclosures=["r07", "exclud|drift|fault|qc|omitted", "sham|control", "n=4|4 run|s.d.|sd|ci|±"],
        reader_questions=_rqs(
            "What is the corrected net lift of treated over sham control after excluding R07?",
            f"+{clean_delta:.1f} a.u. (+{clean_pct:.0f}%, from {clean_c:.1f} to {clean_t:.1f} a.u.).",
            "How many valid runs remain per arm?",
            "4 valid runs per arm (R07 excluded due to temp_drift_fault).",
            "How did R07 distort the prior figure?",
            "Its 41.5 a.u. fault inflated the treated mean from 18.5 to 23.1 a.u.",
        ),
    )


def make_h23_surface_terminal_ci_diff() -> None:
    tid, split = "h23_surface_terminal_ci_diff", "heldout"
    root = _task_dir(split, tid)
    rng = np.random.default_rng(23001)
    codecs = [
        ("lz4-fast", 1840.0, 48.0, 2.15),
        ("zstd-3", 920.0, 26.0, 3.42),
        ("brotli-4", 415.0, 14.0, 3.68),
        ("gzip-6", 295.0, 11.0, 2.98),
    ]
    rows = []
    means = {}
    for name, mu, sd, ratio in codecs:
        vals = rng.normal(mu, sd, size=8)
        means[name] = float(np.mean(vals))
        for r, v in enumerate(vals, 1):
            rows.append([name, r, round(float(v), 1), ratio])
    speedup_zstd = means["lz4-fast"] / means["zstd-3"]
    speedup_gzip = means["lz4-fast"] / means["gzip-6"]
    _write_csv(root, "codec_bench.csv", ["codec", "run", "decompress_mb_s", "compression_ratio"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** I'm over a 72-column SSH terminal with no image support. Compression codec benchmarks (8 runs
        each) are in `data/codec_bench.csv`.

        **Assistant:** Columns: `codec` (`lz4-fast`, `zstd-3`, `brotli-4`, `gzip-6`), `run` (1–8),
        `decompress_mb_s`, and `compression_ratio`.

        **User:** Return a <=72-column plain-text/Unicode comparison table or bar chart showing decompression
        throughput (± SD across 8 runs) alongside compression ratio so we can choose between `lz4-fast` and
        `zstd-3`.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="multi_surface", domain="Systems / CLI",
        title="72-col SSH terminal compression codec benchmark",
        what=f"lz4-fast decompresses at {means['lz4-fast']:.0f} MB/s ({speedup_zstd:.1f}x zstd-3, {speedup_gzip:.1f}x gzip-6) but zstd-3 compresses 3.42x vs 2.15x",
        accept=[means["lz4-fast"], speedup_zstd, speedup_gzip, 3.42],
        rel_tol=0.06, abs_tol=15.0, uncertainty_required=True,
        display_width_px=72, surface="terminal",
        required_disclosures=["lz4", "zstd", "s.d.|sd|±|8 run|n=8"],
        reader_questions=_rqs(
            "Which codec decompresses fastest and how fast is it vs zstd-3?",
            f"lz4-fast at ~{means['lz4-fast']:.0f} MB/s ({speedup_zstd:.1f}× faster than zstd-3).",
            "How is run-to-run variability reported?",
            "Mean ± SD across 8 runs per codec.",
            "What is the compression-ratio tradeoff?",
            "zstd-3 achieves 3.42× compression vs 2.15× for lz4-fast.",
        ),
    )


def make_h24_surface_narrow_pr_comment() -> None:
    tid, split = "h24_surface_narrow_pr_comment", "heldout"
    root = _task_dir(split, tid)
    rng = np.random.default_rng(24001)
    workloads = [
        ("ast_parse", 412.0, 248.0),
        ("type_check", 685.0, 410.0),
        ("ir_lower", 318.0, 206.0),
        ("codegen", 520.0, 344.0),
    ]
    rows = []
    tc_drop_pct = 0.0
    tc_drop_mb = 0.0
    for wl, b_mu, a_mu in workloads:
        b = rng.normal(b_mu, 11.0, size=10)
        a = rng.normal(a_mu, 9.0, size=10)
        if wl == "type_check":
            tc_drop_mb = float(np.mean(b) - np.mean(a))
            tc_drop_pct = 100.0 * tc_drop_mb / float(np.mean(b))
        for stage, arr in (("main", b), ("arena_pr", a)):
            for i, v in enumerate(arr, 1):
                rows.append([wl, stage, i, round(float(v), 1)])
    _write_csv(root, "arena_memory.csv", ["workload", "branch", "run", "peak_rss_mb"], rows)
    _write_context(
        root,
        """
        # Thread

        **User:** I'm pasting one compact figure into a GitHub PR comment that reviewers often read on mobile
        (450 px wide). Peak RSS memory across 4 compiler workloads (10 runs each) before and after our arena
        allocator refactor is in `data/arena_memory.csv`.

        **Assistant:** Columns: `workload`, `branch` (`main`, `arena_pr`), `run` (1–10), and `peak_rss_mb`.

        **User:** Keep every label legible at 450 px width, include 10-run spread, and headline the biggest
        memory savings (`type_check`).
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="multi_surface", domain="Compiler Engineering",
        title="450 px narrow PR comment figure for arena allocator RSS drop",
        what=f"Arena allocator cuts type_check peak RSS by -{tc_drop_mb:.0f} MB (-{tc_drop_pct:.1f}%) across 10 runs (all 4 workloads drop ~35-40%)",
        accept=[tc_drop_mb, tc_drop_pct, 410.0],
        rel_tol=0.06, abs_tol=3.0, uncertainty_required=True,
        display_width_px=450, surface="narrow",
        required_disclosures=["type_check|arena", "10 run|n=10|s.d.|sd|±|ci"],
        reader_questions=_rqs(
            "How much peak RSS does the arena allocator save on type_check?",
            f"About {tc_drop_mb:.0f} MB (−{tc_drop_pct:.1f}%, from ~685 MB down to ~410 MB).",
            "How is run-to-run variability reported?",
            "Across 10 runs per workload-branch (SD/CI/points).",
            "Did any of the four compiler workloads regress in memory?",
            "No — all four workloads dropped ~34–40% in peak RSS.",
        ),
    )


def make_h25_repair_ci_and_wrong_p() -> None:
    tid, split = "h25_repair_ci_and_wrong_p", "heldout"
    root = _task_dir(split, tid)
    # Two arms with heavily overlapping 95% CIs (true delta ~ +2.8%, inside noise)
    ctrl = np.array([62.4, 71.8, 58.2, 69.5, 64.0, 66.1, 60.5, 73.2])
    trt = np.array([64.5, 73.9, 61.4, 71.0, 67.8, 68.5, 62.1, 75.0])
    mc, mt = float(np.mean(ctrl)), float(np.mean(trt))
    diff = mt - mc
    pct = 100.0 * diff / mc
    rows = (
        [["control", i + 1, float(v)] for i, v in enumerate(ctrl)]
        + [["variant_x", i + 1, float(v)] for i, v in enumerate(trt)]
    )
    _write_csv(root, "experiment_scores.csv", ["arm", "run", "score"], rows)
    _write_script(
        root,
        "broken_plot.py",
        """
        import csv
        import math
        import matplotlib.pyplot as plt
        import numpy as np

        groups = {}
        with open("data/experiment_scores.csv", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                groups.setdefault(r["arm"], []).append(float(r["score"]))
        names = list(groups.keys())
        means = [float(np.mean(groups[k])) for k in names]
        sems = [float(np.std(groups[k], ddof=1)) / math.sqrt(len(groups[k])) for k in names]
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.bar(names, means, yerr=sems, color=["#e15759", "#59a14f"])
        ax.set_ylim(58, 74)
        ax.set_title("variant_x significantly outperforms control by +12.5% (95% CI)", fontsize=7)
        fig.savefig("figure.png", dpi=100)
        """,
    )
    _write_context(
        root,
        """
        # Thread

        **User:** Someone submitted `broken_plot.py` (`data/experiment_scores.csv`, 8 runs per arm) claiming
        `variant_x significantly outperforms control by +12.5% (95% CI)` — even though the script actually
        plotted ±1 SEM, truncated the y-axis at 58, and got the percentage wrong!

        **Assistant:** I'll recompute the true means and 95% CIs from `data/experiment_scores.csv` and repair
        the script with an honest scale, proper 95% CI (plus individual points), and an accurate conclusion.

        **User:** Thanks — save the repaired figure to `figure.png`.
        """,
    )
    _write_rubric(
        root, task_id=tid, split=split, track="byo_repair", domain="Experimental Statistics",
        title="Repair mislabelled SEM error bars, truncated axis, and false +12.5% overclaim",
        what=f"True difference is only +{diff:.1f} pts (+{pct:.1f}%), well within overlapping 95% CIs across n = 8 runs (no reliable effect)",
        accept=[diff, pct, mt, mc],
        rel_tol=0.15, abs_tol=0.5, uncertainty_required=True,
        no_effect_trap=True,
        forbid_truncated_bars=True,
        forbidden_overclaim_phrases=["12.5%", "significantly outperforms", "proves", "clearly beats"],
        required_disclosures=["95% ci|confidence interval|ci", "overlap|noise|not significant|inconclusive|no reliable|n=8|8 run"],
        reader_questions=_rqs(
            "What is the actual mean difference between variant_x and control?",
            f"Only +{diff:.1f} points (+{pct:.1f}%: {mt:.1f} vs {mc:.1f}), not +12.5%.",
            "Do the 95% confidence intervals separate the two arms?",
            "No — the 95% CIs across n = 8 runs overlap heavily; the difference sits within noise.",
            "What mistakes in broken_plot.py were repaired?",
            "Fixed the mislabelled SEM bars to true 95% CI, removed y-axis truncation, fixed tiny text, and replaced the false overclaim.",
        ),
    )


def main() -> None:
    n_legacy = upgrade_legacy_15_rubrics()
    generators = [
        # 10 new dev tasks (16_..25_)
        make_16_calibration_reliability,
        make_17_gpu_roofline_kernels,
        make_18_db_query_plan_tail,
        make_19_trap_dual_axis_spurious,
        make_20_trap_survivorship_bias,
        make_21_edit_normalize_per_capita,
        make_22_edit_split_confounder,
        make_23_surface_narrow_oncall,
        make_24_surface_html_interactive_report,
        make_25_repair_truncated_and_rainbow,
        # 20 new public-test tasks (pt31_..pt50_)
        make_pt31_bland_altman,
        make_pt32_xrd_phase_shift,
        make_pt33_crispr_screen_rank,
        make_pt34_climate_ensemble_fan,
        make_pt35_cache_eviction_hitrate,
        make_pt36_token_throughput_batch,
        make_pt37_flaky_ci_heatmap,
        make_pt38_cloud_cost_waterfall,
        make_pt39_trap_multiple_testing,
        make_pt40_trap_heavy_tail_mean,
        make_pt41_trap_denominator_shift,
        make_pt42_trap_cherry_picked_window,
        make_pt43_edit_sort_and_annotate_target,
        make_pt44_edit_replace_pie_with_delta,
        make_pt45_edit_switch_to_cdf_tails,
        make_pt46_surface_slide_exec_kpi,
        make_pt47_surface_dark_noc_monitor,
        make_pt48_repair_dual_axis_spaghetti,
        make_pt49_repair_pie_and_clipped_labels,
        make_pt50_repair_unlabelled_log_scatter,
        # 10 new heldout tasks (h16_..h25_)
        make_h16_pharmacokinetics_auc,
        make_h17_catalyst_selectivity_tradeoff,
        make_h18_gc_pause_tail_cdf,
        make_h19_distributed_scaling_eff,
        make_h20_trap_ecological_fallacy,
        make_h21_trap_missing_zero_truncation,
        make_h22_edit_add_control_and_exclude_drift,
        make_h23_surface_terminal_ci_diff,
        make_h24_surface_narrow_pr_comment,
        make_h25_repair_ci_and_wrong_p,
    ]
    for fn in generators:
        fn()
    print(f"Upgraded {n_legacy} legacy rubrics and generated {len(generators)} new tasks (total target: 100).")


if __name__ == "__main__":
    main()
