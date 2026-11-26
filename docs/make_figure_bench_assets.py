"""Generate visual benchmark & failure-anatomy assets for ``docs/figure-bench.md``.

Writes deterministic PNGs into ``docs/assets/figure_bench/``:
- ``arms_overview.png``: grouped ``mint.compare`` chart of the real measured
  ``v0.1-initial-15`` agent comparison (``evals/figure_bench/runs/compare_r6_b1_u1.md``).
- ``failure_line_struck_before.png``: rendered directly from the real
  ``pt30_repair_line_struck/data/broken_plot.py`` benchmark task.
- ``failure_line_struck_after.png``: clean ``mint.explain`` render on the exact
  same ``pt30_repair_line_struck/data/throughput.csv`` data.
"""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import mintfig as mint
from mintfig.figcheck import check_script

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "docs" / "assets" / "figure_bench"
PT30_DIR = (
    REPO_ROOT / "evals" / "figure_bench" / "public_test" / "pt30_repair_line_struck" / "data"
)


def render_arms_overview(out_path: Path) -> None:
    """Plot the measured v0.1-initial-15 arm comparison with mintfig."""
    # Exact final/first-try percentages from evals/figure_bench/runs/compare_r6_b1_u1.md
    metrics = {
        "First-try clean": {
            "mintfig (r6)": round(14 / 15 * 100, 1),
            "Matplotlib, told (b1)": round(12 / 15 * 100, 1),
            "Matplotlib, default (u1)": round(2 / 15 * 100, 1),
        },
        "Final clean": {
            "mintfig (r6)": 100.0,
            "Matplotlib, told (b1)": 100.0,
            "Matplotlib, default (u1)": round(2 / 15 * 100, 1),
        },
        "Right headline #": {
            "mintfig (r6)": 100.0,
            "Matplotlib, told (b1)": round(4 / 15 * 100, 1),
            "Matplotlib, default (u1)": round(4 / 15 * 100, 1),
        },
        "Uncertainty named": {
            "mintfig (r6)": 100.0,
            "Matplotlib, told (b1)": 75.0,
            "Matplotlib, default (u1)": 75.0,
        },
    }
    fig = mint.explain(
        "mintfig ships 93% clean on try 1 and 100% right headlines vs 13% and 27% for default Matplotlib",
        mint.compare(
            metrics,
            title="Share of tasks passing each neutral audit check (%)",
            label="Pass rate",
            unit="%",
            baseline="Matplotlib, default (u1)",
            highlight=["mintfig (r6)", "Matplotlib, told (b1)"],
            sort=False,
        ),
        subtitle="figure-bench v0.1 initial-15 baseline (10 dev + 5 held-out tasks, fresh Sonnet 5.5 agent per task)",
        source="evals/figure_bench/runs/compare_r6_b1_u1.md",
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary = fig.save(out_path)
    if not summary["ship"]:
        raise RuntimeError(f"arms_overview.png failed ship: {summary['issues']}")
    print(f"arms_overview.png: ship={summary['ship']} issues={summary['issues']}")


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
    render_pt30_before_after(
        OUT_DIR / "failure_line_struck_before.png",
        OUT_DIR / "failure_line_struck_after.png",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
