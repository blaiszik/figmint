"""Model-release and scorecard gallery examples for ``mint.explain`` (all data synthetic).

Generates reference figures showcasing:
- Grouped multi-benchmark ``mint.compare`` + stacked ``boost=`` extensions
  (``style="paper"``, custom ``accent=``, ``width="slide"``)
- Pareto frontier ``mint.relate(frontier=True, label_all=True, connect_groups=True)``
  paired with ``mint.table`` (``style="dark"``, custom ``accent=``, ``width="slide"``)
- Chat-width ``mint.compare`` + ``mint.table`` scorecard sharing entity colours

Writes PNGs and reproducible JSON specs to ``gallery/output/explain_release/``.
"""

from __future__ import annotations

from pathlib import Path

import mintfig as mint

SOURCE = "synthetic model evaluation data"


def release_benchmarks_paper() -> mint.Explanation:
    """Grouped multi-benchmark comparison + stacked extended-thinking boost on warm paper."""
    scores = {
        "GPQA Diamond": {"Alpha-3": 86.4, "Beta-Pro": 83.2, "Alpha-2": 77.1},
        "SWE-bench": {"Alpha-3": 74.2, "Beta-Pro": 71.0, "Alpha-2": 58.6},
        "AIME 2026": {"Alpha-3": 88.0, "Beta-Pro": 82.0, "Alpha-2": 64.0},
        "MMMU": {"Alpha-3": 79.5, "Beta-Pro": 77.8, "Alpha-2": 71.0},
    }
    return mint.explain(
        "Alpha-3 leads all 4 frontier benchmarks and gains +10.4 points from extended thinking",
        mint.compare(
            scores,
            highlight="Alpha-3",
            baseline="Alpha-2",
            title="Multi-benchmark head-to-head",
            label="Accuracy",
            unit="%",
        ),
        mint.compare(
            {"Alpha-3": 77.6, "Beta-Pro": 74.0, "Alpha-2": 57.8},
            boost={"Alpha-3": 10.4, "Beta-Pro": 8.0, "Alpha-2": 6.2},
            boost_label="Extended thinking",
            highlight="Alpha-3",
            baseline="Alpha-2",
            title="AIME 2026: base vs extended thinking",
            label="AIME score",
            unit="%",
        ),
        subtitle="Frontier model evaluation suite, Nov 2026",
        source=SOURCE,
        style="paper",
        accent="#D97757",
        width="slide",
    )


def release_frontier_dark() -> mint.Explanation:
    """Capability-vs-cost Pareto frontier with all-point labels, trajectories, and mint.table."""
    frontier_rows = [
        {"model": "Alpha-3 Mini", "family": "Alpha", "cost": 0.35, "score": 76.5},
        {"model": "Alpha-3", "family": "Alpha", "cost": 2.50, "score": 86.4},
        {"model": "Alpha-3 Max", "family": "Alpha", "cost": 9.00, "score": 89.2},
        {"model": "Beta-Lite", "family": "Beta", "cost": 0.60, "score": 72.0},
        {"model": "Beta-Pro", "family": "Beta", "cost": 6.00, "score": 83.2},
        {"model": "Gamma-Fast", "family": "Gamma", "cost": 0.15, "score": 68.0},
        {"model": "Gamma-Large", "family": "Gamma", "cost": 4.50, "score": 80.5},
    ]
    table_rows = [
        {"Model": "Alpha-3 Max", "GPQA": 89.2, "SWE-bench": 76.8, "Cost": 9.00},
        {"Model": "Alpha-3", "GPQA": 86.4, "SWE-bench": 74.2, "Cost": 2.50},
        {"Model": "Beta-Pro", "GPQA": 83.2, "SWE-bench": 71.0, "Cost": 6.00},
        {"Model": "Alpha-3 Mini", "GPQA": 76.5, "SWE-bench": 61.4, "Cost": 0.35},
        {"Model": "Gamma-Fast", "GPQA": 68.0, "SWE-bench": None, "Cost": 0.15},
    ]
    return mint.explain(
        "The Alpha family pushes the capability-cost Pareto frontier across every price tier",
        mint.relate(
            "cost",
            "score",
            data=frontier_rows,
            names="model",
            groups="family",
            highlight="Alpha",
            frontier=True,
            label_all=True,
            connect_groups=True,
            log_x=True,
            x_label="Blended API cost ($/M tokens)",
            y_label="GPQA Diamond (%)",
            unit="%",
            title="Capability vs cost frontier",
        ),
        mint.table(
            table_rows,
            units={"GPQA": "%", "SWE-bench": "%", "Cost": "$/M"},
            bold_best={"GPQA": "max", "SWE-bench": "max", "Cost": "min"},
            highlight="Alpha-3",
            baseline="Beta-Pro",
            fmt={"GPQA": ".1f", "SWE-bench": ".1f", "Cost": "${:.2f}"},
            title="Frontier scorecard",
        ),
        subtitle="Capability-efficiency analysis across 7 models",
        source=SOURCE,
        style="dark",
        accent="#4F9CF9",
        width="slide",
    )


def table_scorecard_chat() -> mint.Explanation:
    """Chat-width mint.compare + mint.table built directly from tidy row records."""
    rows = [
        {"Model": "Alpha-3", "GPQA": 86.4, "SWE-bench": 74.2, "AIME": 88.0, "Cost": 2.50},
        {"Model": "Alpha-2", "GPQA": 77.1, "SWE-bench": 58.6, "AIME": 64.0, "Cost": 3.00},
        {"Model": "Beta-Pro", "GPQA": 83.2, "SWE-bench": 71.0, "AIME": 82.0, "Cost": 6.00},
        {"Model": "Gamma-Fast", "GPQA": 71.5, "SWE-bench": None, "AIME": 55.0, "Cost": 0.40},
    ]
    return mint.explain(
        "Alpha-3 leads every reasoning benchmark while costing 17% less than Alpha-2",
        mint.compare(
            rows,
            name="Model",
            value="GPQA",
            title="GPQA Diamond",
            label="Accuracy",
            unit="%",
            highlight="Alpha-3",
            baseline="Alpha-2",
        ),
        mint.table(
            rows,
            units={"GPQA": "%", "SWE-bench": "%", "AIME": "%", "Cost": "$/M"},
            bold_best={"GPQA": "max", "SWE-bench": "max", "AIME": "max", "Cost": "min"},
            highlight="Alpha-3",
            baseline="Alpha-2",
            sort="-GPQA",
            fmt={"GPQA": ".1f", "SWE-bench": ".1f", "AIME": ".0f", "Cost": "${:.2f}"},
            title="Full benchmark scorecard",
        ),
        layout=[["a"], ["b"]],
        source=SOURCE,
    )


EXAMPLES = (
    ("release_benchmarks_paper", release_benchmarks_paper),
    ("release_frontier_dark", release_frontier_dark),
    ("table_scorecard_chat", table_scorecard_chat),
)


def main() -> None:
    out_dir = Path(__file__).resolve().parent / "output" / "explain_release"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, builder in EXAMPLES:
        fig = builder()
        summary = fig.save(out_dir / f"{name}.png", write_spec=True)
        assert summary["ok"] and summary["ship"] and not summary["issues"], (
            f"{name} failed clean audit: {summary['issues']}"
        )
        print(f"OK  {name}.png  {summary['size_px']}  min_text={summary['display']['min_text_px']}px")


if __name__ == "__main__":
    main()
