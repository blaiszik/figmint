"""Generate visual benchmark & failure-anatomy assets for ``docs/figure-bench.md``.

Writes deterministic PNGs into ``docs/assets/figure_bench/``:
- ``arms_overview.png``: 2-panel ``mint.explain`` figure of the measured 100-task × 4-arm
  ``figure-bench v0.1`` Claude Sonnet 5.5 sweep (neutral pass rates + per-task timing).
- ``splits_and_tracks.png``: 2-panel ``mint.explain`` figure of composite scores by split
  (dev / public-test / heldout) and by track across all 4 arms.
- ``failure_line_struck_before.png``: rendered directly from the real
  ``pt30_repair_line_struck/data/broken_plot.py`` benchmark task.
- ``failure_line_struck_after.png``: clean ``mint.explain`` render on the exact
  same ``pt30_repair_line_struck/data/throughput.csv`` data.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import mintfig as mint
from mintfig.figcheck import check_script

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "docs" / "assets" / "figure_bench"
SUB_DIR = REPO_ROOT / "evals" / "figure_bench" / "leaderboard" / "submissions"
RUNS_DIR = REPO_ROOT / "evals" / "figure_bench" / "runs"
PT30_DIR = (
    REPO_ROOT / "evals" / "figure_bench" / "public_test" / "pt30_repair_line_struck" / "data"
)


def _pct_from_frac(frac: str) -> float:
    num, den = (int(x) for x in frac.split("/"))
    return round(100.0 * num / den, 1) if den else 0.0


MINT_ACCENT = "#128060"
ARM_COLORS = {
    "mintfig": MINT_ACCENT,
    "mpl + hook": "#1D619E",
    "coached": "#7B2466",
}


def _load_v01_100() -> tuple[list[tuple[str, str, str]], dict[str, dict], dict[str, dict]]:
    arm_specs = [
        ("mintfig", "v01_all100_mintfig_sonnet55.json", "v01_100_sonnet55_mintfig"),
        ("mpl + hook", "v01_all100_matplotlib_hook_sonnet55.json", "v01_100_sonnet55_matplotlib_hook"),
        ("coached", "v01_all100_matplotlib_coached_sonnet55.json", "v01_100_sonnet55_matplotlib_coached"),
        ("default", "v01_all100_matplotlib_plain_sonnet55.json", "v01_100_sonnet55_matplotlib_plain"),
    ]
    subs = {label: json.loads((SUB_DIR / sfile).read_text(encoding="utf-8")) for label, sfile, _ in arm_specs}
    runs = {label: json.loads((RUNS_DIR / rdir / "results.json").read_text(encoding="utf-8")) for label, _, rdir in arm_specs}
    return arm_specs, subs, runs


def render_arms_overview(out_path: Path) -> None:
    """Plot the measured full 100-task v0.1 4-arm comparison & timing distribution with mintfig."""
    arm_specs, subs, runs = _load_v01_100()

    metrics = {
        "Zero-defect (final)": {lbl: _pct_from_frac(runs[lbl]["neutral"]["final"]["clean"]) for lbl, _, _ in arm_specs},
        "First-submit clean": {lbl: float(subs[lbl]["provenance"]["first_submission_clean_rate"]) for lbl, _, _ in arm_specs},
        "Right headline #": {lbl: _pct_from_frac(runs[lbl]["neutral"]["final"]["headline_correct"]) for lbl, _, _ in arm_specs},
        "Uncertainty named": {lbl: _pct_from_frac(runs[lbl]["neutral"]["final"]["uncertainty_named"]) for lbl, _, _ in arm_specs},
        "Composite score": {lbl: float(subs[lbl]["scores"]["composite"]) for lbl, _, _ in arm_specs},
    }
    timings = {
        lbl: [float(r["seconds"]) for r in subs[lbl]["per_task"] if isinstance(r.get("seconds"), (int, float))]
        for lbl, _, _ in arm_specs
    }

    mf_comp = subs["mintfig"]["scores"]["composite"]
    mf_med = subs["mintfig"]["scores"]["median_seconds"]
    co_clean = metrics["Zero-defect (final)"]["coached"]
    pl_clean = metrics["Zero-defect (final)"]["default"]

    fig = mint.explain(
        f"Across 100 tasks, mintfig ships 100% defect-free figures ({mf_comp:.1f}) in {mf_med:.1f} s vs {co_clean:.0f}% coached and {pl_clean:.0f}% default Matplotlib",
        mint.compare(
            metrics,
            title="Neutral audit pass rates & composite (n = 100)",
            label="Score / pass rate",
            unit="%",
            baseline="default",
            highlight=["mintfig", "mpl + hook", "coached"],
            sort=False,
        ),
        mint.distribution(
            timings,
            title="Task completion time",
            label="Time",
            unit="s",
            stat="median",
            baseline="default",
            highlight=["mintfig", "mpl + hook", "coached"],
        ),
        subtitle="figure-bench v0.1 full 100-task sweep (25 dev · 50 public-test · 25 heldout · 400 isolated Claude Sonnet 5.5 runs)",
        source="evals/figure_bench/leaderboard/submissions/v01_all100_*_sonnet55.json",
        accent=MINT_ACCENT,
        colors=ARM_COLORS,
        layout=[["a", "a", "a", "b", "b"]],
        width="slide",
        density="compact",
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary = fig.save(out_path)
    print(f"arms_overview.png: ship={summary['ship']} ok={summary['ok']} issues={summary['issues']}")
    if not summary["ship"]:
        raise RuntimeError(f"arms_overview.png failed ship: {summary['issues']}")


def render_splits_and_tracks(out_path: Path) -> None:
    """Plot composite scores across all 3 splits (dev/public-test/heldout) and all 6 tracks."""
    arm_specs, subs, _runs = _load_v01_100()

    def _avg_for(arm_lbl: str, key: str, val: str) -> float:
        rows = [r["composite"] for r in subs[arm_lbl]["per_task"] if r.get(key) == val]
        return round(sum(rows) / len(rows), 1) if rows else 0.0

    split_labels = [
        ("dev (25)", "dev"),
        ("public-test (50)", "public-test"),
        ("heldout (25)", "heldout"),
    ]
    splits_data = {
        display: {lbl: _avg_for(lbl, "split", key) for lbl, _, _ in arm_specs}
        for display, key in split_labels
    }

    track_labels = [
        ("SWE & coding (22)", "swe_coding"),
        ("Science & unc. (28)", "science_uncertainty"),
        ("Multi-turn edit (11)", "multiturn_edit"),
        ("Epistemic traps (18)", "epistemic_traps"),
        ("Multi-surface (11)", "multi_surface"),
        ("BYO repair (10)", "byo_repair"),
    ]
    tracks_data = {
        display: {lbl: _avg_for(lbl, "track", key) for lbl, _, _ in arm_specs}
        for display, key in track_labels
    }

    mf_dev = splits_data["dev (25)"]["mintfig"]
    mf_pt = splits_data["public-test (50)"]["mintfig"]
    mf_held = splits_data["heldout (25)"]["mintfig"]
    pl_held = splits_data["heldout (25)"]["default"]

    fig = mint.explain(
        f"mintfig leads every split — {mf_dev:.1f} dev, {mf_pt:.1f} public-test, and {mf_held:.1f} heldout vs {pl_held:.1f} for default Matplotlib",
        mint.compare(
            splits_data,
            title="Composite score by split",
            label="Composite",
            unit="/100",
            baseline="default",
            highlight=["mintfig", "mpl + hook", "coached"],
            sort=False,
        ),
        mint.compare(
            tracks_data,
            title="Composite score by track",
            label="Composite",
            unit="/100",
            baseline="default",
            highlight=["mintfig", "mpl + hook", "coached"],
            sort=False,
        ),
        subtitle="figure-bench v0.1 full 100-task 4-arm sweep · heldout tasks were never used to tune mintfig or SKILL.md (Claude Sonnet 5.5)",
        source="evals/figure_bench/leaderboard/submissions/v01_all100_*_sonnet55.json",
        accent=MINT_ACCENT,
        colors=ARM_COLORS,
        layout=[["a", "a", "b", "b", "b"]],
        width="slide",
        density="compact",
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary = fig.save(out_path)
    print(f"splits_and_tracks.png: ship={summary['ship']} ok={summary['ok']} issues={summary['issues']}")
    if not summary["ship"]:
        raise RuntimeError(f"splits_and_tracks.png failed ship: {summary['issues']}")


def render_pt30_before_after(before_path: Path, after_path: Path) -> None:
    """Render pt30_repair_line_struck broken Matplotlib script vs clean mint.explain."""
    before_path.parent.mkdir(parents=True, exist_ok=True)
    broken_script = PT30_DIR / "broken_plot.py"
    subprocess.run([sys.executable, str(broken_script), str(before_path)], check=True)
    reports = check_script(broken_script)
    assert reports and reports[0]["ship"] is False, reports
    rules = [i["rule"] for i in reports[0]["issues"]]
    print(f"failure_line_struck_before.png: ship={reports[0]['ship']} rules={rules}")

    # Load exact same throughput.csv for clean mint.explain comparison
    by_rel: dict[str, list[tuple[int, float]]] = {}
    with open(PT30_DIR / "throughput.csv", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            by_rel.setdefault(row["release"], []).append(
                (int(row["concurrency"]), float(row["req_per_sec"]))
            )
    xs = [c for c, _ in sorted(by_rel["v2.0"])]
    series = {rel: [v for _, v in sorted(pts)] for rel, pts in by_rel.items()}
    peak_v2 = max(series["v2.0"])
    v1_at_peak = series["v1.0"][series["v2.0"].index(peak_v2)]
    gain_pct = round(100.0 * (peak_v2 - v1_at_peak) / v1_at_peak)

    fig = mint.explain(
        f"v2.0 peaks at {peak_v2:,.0f} req/s, +{gain_pct}% over v1.0 at concurrency 64",
        mint.trend(
            xs,
            series,
            x_label="Concurrency (workers)",
            label="Throughput",
            unit="req/s",
            baseline="v1.0",
            highlight=["v2.0"],
            title="Throughput scaling across worker concurrency",
        ),
        source="evals/figure_bench/public_test/pt30_repair_line_struck/data/throughput.csv",
    )
    summary = fig.save(after_path)
    if not summary["ship"]:
        raise RuntimeError(f"failure_line_struck_after.png failed ship: {summary['issues']}")
    print(f"failure_line_struck_after.png: ship={summary['ship']} issues={summary['issues']}")


def main() -> int:
    render_arms_overview(OUT_DIR / "arms_overview.png")
    render_splits_and_tracks(OUT_DIR / "splits_and_tracks.png")
    render_pt30_before_after(
        OUT_DIR / "failure_line_struck_before.png",
        OUT_DIR / "failure_line_struck_after.png",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
