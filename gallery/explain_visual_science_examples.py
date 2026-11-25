"""Visual-science & harness-adaptive gallery examples for ``fm.explain`` (all data synthetic).

Generates reference figures showcasing:
- Countable quantile dotplots (``mode="quantile"``) paired with nested 50%/95% CIs
  (``inner_error=``) and inline baseline deltas (``show_delta=True``)
- Narrative visual scaffolding with shaded ``regions=`` and collision-checked
  leader-arrow ``callouts=`` across ``trend`` and ``relate``
- Narrow 450 px IDE sidebar preset (``width="narrow"``) with automatic vertical stacking

Writes PNGs and reproducible JSON specs to ``gallery/output/explain_visual_science/``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

import figmint as fm

SOURCE = "synthetic benchmark data"


def uncertainty_quantile_nested_ci() -> fm.Explanation:
    """Quantile dotplots (5% per dot) + nested 50%/95% CIs with inline baseline deltas."""
    rng = np.random.default_rng(7)
    dense = rng.normal(142.0, 14.0, size=80).tolist()
    sparse = rng.normal(104.0, 11.0, size=80).tolist()
    quant = rng.normal(115.0, 15.0, size=80).tolist()

    return fm.explain(
        "Sparse routing cuts mean latency by 38 ms and keeps 95% of queries under 120 ms",
        fm.distribution(
            {
                "Dense baseline": dense,
                "Sparse v2": sparse,
                "Quantized 4-bit": quant,
            },
            mode="quantile",
            quantiles=20,
            baseline="Dense baseline",
            highlight="Sparse v2",
            reference=(120.0, "SLO 120 ms"),
            label="Latency",
            unit="ms",
            title="Each dot is 5% of query latency",
        ),
        fm.compare(
            {
                "Dense baseline": 142.0,
                "Quantized 4-bit": 115.0,
                "Sparse v2": 104.0,
            },
            error={
                "Dense baseline": (131.0, 153.0),
                "Quantized 4-bit": (102.0, 128.0),
                "Sparse v2": (95.0, 113.0),
            },
            inner_error={
                "Dense baseline": (138.0, 146.0),
                "Quantized 4-bit": (110.0, 120.0),
                "Sparse v2": (101.0, 107.0),
            },
            error_label="outer 95% CI, inner 50% CI",
            baseline="Dense baseline",
            highlight="Sparse v2",
            show_delta=True,
            sort="desc",
            label="Mean latency",
            unit="ms",
            title="Mean latency with nested CIs and delta vs baseline",
        ),
        source="synthetic latency benchmark (n=80 queries/model)",
    )


def narrative_callouts_regions() -> fm.Explanation:
    """Shaded regions and leader-arrow callouts bridging mechanism across trend & relate."""
    weeks = [1, 2, 3, 4, 5, 6, 7, 8]
    v2 = [47, 52, 55, 79, 96, 104, 109, 112]
    v1 = [46, 49, 50, 51, 52, 51, 53, 52]

    throughput = [18, 25, 34, 48, 62, 79, 95, 112]
    accuracy = [71.2, 75.8, 79.4, 83.1, 84.5, 86.0, 86.5, 87.2]
    names = [
        "tiny",
        "small",
        "base",
        "legacy",
        "v2-lite",
        "v2-mid",
        "v2-fast",
        "v2-pro",
    ]

    return fm.explain(
        "Throughput doubled after the Q2 kernel rewrite while staying on the Pareto frontier",
        fm.trend(
            weeks,
            {"v2 kernel": v2, "v1 legacy": v1},
            baseline="v1 legacy",
            highlight="v2 kernel",
            regions=[(3.5, 5.5, "Kernel rollout")],
            callouts=[
                (5, 96, "FP8 fusion enabled"),
                (8, 112, "Peak 112 req/s"),
            ],
            x_label="Release week",
            label="Throughput",
            unit="req/s",
            title="Sustained gain after rollout window",
        ),
        fm.relate(
            throughput,
            accuracy,
            names=names,
            highlight=["v2-fast", "v2-pro"],
            regions=[(70, 117, "Target zone")],
            callouts=[
                (95, 86.5, "Best balance"),
                (48, 83.1, "Legacy prod"),
            ],
            x_label="Throughput",
            y_label="Accuracy (%)",
            unit="%",
            title="Accuracy vs throughput trade-off",
        ),
        source="synthetic serving sweep",
    )


def harness_narrow_sidebar() -> fm.Explanation:
    """Narrow 450 px IDE sidebar preset with automatic vertical panel stacking."""
    hours = ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00"]
    return fm.explain(
        "Cache warmup trims cold-start p99 from 410 ms to 125 ms across all regions",
        fm.compare(
            {
                "Cold baseline": 410,
                "ap-south": 134,
                "eu-west": 125,
                "us-east": 118,
            },
            baseline="Cold baseline",
            highlight="eu-west",
            show_delta=True,
            label="p99 latency",
            unit="ms",
            title="Regional p99 latency after warmup",
        ),
        fm.trend(
            hours,
            {
                "Cold": [405, 398, 412, 418, 409, 410],
                "Warm cache": [126, 121, 119, 125, 123, 120],
            },
            baseline="Cold",
            label="p99 latency",
            unit="ms",
            title="24-hour stability",
        ),
        width="narrow",
        source="synthetic edge telemetry (450 px sidebar preset)",
    )


EXAMPLES = (
    ("uncertainty_quantile_nested_ci", uncertainty_quantile_nested_ci),
    ("narrative_callouts_regions", narrative_callouts_regions),
    ("harness_narrow_sidebar", harness_narrow_sidebar),
)


def main() -> None:
    out_dir = Path(__file__).resolve().parent / "output" / "explain_visual_science"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, builder in EXAMPLES:
        fig = builder()
        summary = fig.save(out_dir / f"{name}.png", write_spec=True)
        assert summary["ok"] and summary["ship"] and not summary["issues"], (
            f"{name} failed clean audit: {summary['issues']}"
        )
        print(
            f"OK  {name}.png  {summary['size_px']}  "
            f"display={summary['display']['width_px']}px  "
            f"min_text={summary['display']['min_text_px']}px"
        )


if __name__ == "__main__":
    main()
