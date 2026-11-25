"""Generate visual showcase examples for Passes 9 & 10 agent-workflow capabilities.

Outputs cleanly into ``gallery/output/explain_workflows/`` without modifying any
earlier tracked gallery directories:
1. ``01_ablation_waterfall.png`` — ``mint.waterfall`` attribution / delta bridge
2. ``02_ci_timeline.png`` — ``mint.timeline`` grouped execution & milestone trace
3. ``03_cohort_flow.png`` — ``mint.flow`` sequential cohort attrition funnel with reasons
4. ``04_scaling_trend_fit.png`` — ``mint.trend(..., log=True, log_x=True, fit=True)`` + linear fit
5. ``05_corr_matrix_triangle.png`` — ``mint.matrix(..., triangle="lower", mask_diagonal=True)``
6. ``06_session_memory_dark.png`` + ``06_investigation_brief.html`` / ``.md`` —
   ``mint.Session`` prefix colour inheritance + ``mint.brief`` multi-figure briefing
"""

from __future__ import annotations

from pathlib import Path

import mintfig as mint

OUT_DIR = Path(__file__).parent / "output" / "explain_workflows"


def build_all() -> list[tuple[str, mint.Explanation]]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rendered: list[tuple[str, mint.Explanation]] = []

    # 1. Waterfall attribution bridge
    fig_wf = mint.explain(
        "Retrieval adds +8.2 points while int4 quantization costs only 1.5 points",
        mint.waterfall(
            {
                "+Retrieval": 8.2,
                "+Reranker": 3.4,
                "+Chain-of-thought": 2.1,
                "int4 quantization": -1.5,
            },
            start=("Base model", 69.0),
            total_label="Shipped",
            highlight="+Retrieval",
            reference=(80.0, "Release target"),
            title="Ablation bridge from base to shipped candidate",
            label="Benchmark accuracy",
            unit="%",
        ),
        source="Synthetic ablation suite (5 seeds per step)",
    )
    rendered.append(("01_ablation_waterfall", fig_wf))

    # 2. Execution span timeline (grouped phases + bottleneck spotlight)
    ci_spans = [
        ("checkout", 0, 8, "setup"),
        ("deps cache", 8, 22, "setup"),
        ("compile", 22, 68, "build"),
        ("unit tests", 68, 102, "verify"),
        ("integration", 68, 162, "verify"),
        ("canary gate", 162, 162, "release"),
        ("deploy", 162, 178, "release"),
    ]
    fig_tl = mint.explain(
        "Integration tests take 94 s (53% of the 178 s CI run) and push past the 150 s SLA",
        mint.timeline(
            ci_spans,
            reference=(150, "CI SLA"),
            title="Parallel phase trace across four pipeline lanes",
            x_label="Elapsed (s)",
            unit="s",
        ),
        source="Synthetic CI execution trace",
    )
    rendered.append(("02_ci_timeline", fig_tl))

    # 3. Sequential cohort attrition funnel (mint.flow)
    fig_flow = mint.explain(
        "58% of screened patients complete follow-up; eligibility screening causes the largest drop (26%)",
        mint.flow(
            [
                ("Screened", 1240),
                ("Eligible", 912, "missing baseline labs"),
                ("Enrolled", 780, "declined consent"),
                ("Completed", 714, "lost to follow-up"),
            ],
            highlight="Eligible",
            title="Trial cohort attrition from screening to final analysis",
            label="Cohort size",
            unit="patients",
        ),
        source="Synthetic clinical cohort log",
    )
    rendered.append(("03_cohort_flow", fig_flow))

    # 4. Trend with regression fits (power-law scaling + linear throughput)
    compute = [1e18, 3e18, 1e19, 3e19, 1e20, 3e20]
    dense_loss = [2.52, 2.18, 2.14, 1.88, 1.82, 1.61]
    moe_loss = [2.36, 2.02, 1.94, 1.65, 1.59, 1.34]
    workers = [4, 8, 16, 24, 32, 48]
    fig_fit = mint.explain(
        "Sparse routing scales steeper on log-log compute while batching doubles linear worker throughput",
        mint.trend(
            compute,
            {"Sparse MoE": moe_loss, "Dense": dense_loss},
            log=True,
            log_x=True,
            fit=True,
            highlight="Sparse MoE",
            baseline="Dense",
            title="Power-law scaling fit",
            label="Validation loss",
            x_label="Compute (FLOPs)",
        ),
        mint.trend(
            workers,
            {"Batched": [18, 52, 76, 138, 158, 254], "Single": [16, 23, 56, 68, 102, 134]},
            fit="linear",
            highlight="Batched",
            baseline="Single",
            title="Linear throughput fit",
            label="Throughput",
            unit="req/s",
            x_label="Workers",
        ),
        source="Synthetic scaling and serving benchmarks",
    )
    rendered.append(("04_scaling_trend_fit", fig_fit))

    # 5. Lower-triangle masked-diagonal correlation matrix
    metrics = ["Reasoning", "Coding", "Math", "Retrieval", "Latency"]
    corr = [
        [1.00, 0.78, 0.84, 0.52, -0.34],
        [0.78, 1.00, 0.71, 0.44, -0.28],
        [0.84, 0.71, 1.00, 0.39, -0.41],
        [0.52, 0.44, 0.39, 1.00, -0.18],
        [-0.34, -0.28, -0.41, -0.18, 1.00],
    ]
    fig_mat = mint.explain(
        "Reasoning and Math correlate most tightly (r = 0.84) while Latency trades off negatively",
        mint.matrix(
            corr,
            rows=metrics,
            cols=metrics,
            diverging=True,
            center=0.0,
            triangle="lower",
            mask_diagonal=True,
            highlight=[("Math", "Reasoning"), ("Latency", "Math")],
            title="Off-diagonal metric correlation structure (diagonal masked)",
            label="Pearson r",
        ),
        source="Synthetic benchmark suite (n = 24 checkpoints)",
    )
    rendered.append(("05_corr_matrix_triangle", fig_mat))

    # 6. Multi-turn Session prefix colour inheritance + Brief export (dark theme)
    session = mint.Session(style="dark", accent="#D97757")
    turn1 = session.explain(
        "Alpha-3 leads Beta-Pro by 3.2 points and Baseline by 9.3 points on GPQA",
        mint.compare(
            {"Alpha-3": 86.4, "Beta-Pro": 83.2, "Baseline": 77.1},
            highlight=["Alpha-3", "Beta-Pro"],
            baseline="Baseline",
            zero=False,
            show_delta=True,
            title="Turn 1: Full-precision accuracy",
            label="GPQA",
            unit="%",
        ),
        source="Synthetic evaluation suite",
    )
    # Turn 2 uses variant names ("Alpha-3 (int4)", "Beta-Pro (int4)") -> inherits exact colours!
    turn2 = session.explain(
        "Quantized Alpha-3 (int4) retains 85.3% while cutting serving cost by 52%",
        mint.compare(
            {"Alpha-3 (int4)": 85.3, "Beta-Pro (int4)": 81.9, "Baseline": 77.1},
            highlight=["Alpha-3 (int4)", "Beta-Pro (int4)"],
            baseline="Baseline",
            zero=False,
            show_delta=True,
            title="Turn 2: Quantized accuracy (inherited hues)",
            label="GPQA",
            unit="%",
        ),
        mint.waterfall(
            {"int4 weights": -1.10, "KV cache compression": -0.45, "Speculative decode": -0.30, "Router overhead": 0.15},
            start=("Full precision", 3.25),
            total_label="Shipped int4",
            highlight="int4 weights",
            title="Serving cost bridge",
            label="Cost",
            unit="$/M",
        ),
        source="Synthetic serving telemetry",
    )
    rendered.append(("06_session_memory_dark", turn2))

    # Save every figure (PNG + JSON) and assert clean ship gate
    for stem, fig in rendered:
        png = OUT_DIR / f"{stem}.png"
        summary = fig.save(png, write_spec=True)
        print(f"{stem}: ok={summary['ok']} ship={summary['ship']} issues={len(summary['issues'])}")
        assert summary["ok"] and summary["ship"], f"{stem} failed QA: {summary['issues']}"

    # Export a cohesive multi-figure HTML + Markdown briefing showcasing mint.brief
    report = mint.brief(
        "Release Candidate & Pipeline Briefing",
        fig_wf,
        fig_tl,
        fig_flow,
        fig_mat,
        turn1,
        turn2,
        subtitle="Generated with mint.Session + mint.brief (zero-CDN HTML & Markdown)",
        summary=[
            "Retrieval adds +8.2 points while int4 quantization costs only 1.5 points",
            "Integration tests account for 53% of CI wall time and exceed the 150 s SLA",
            "58% of screened patients complete follow-up; eligibility screening is the largest drop",
        ],
        source="Synthetic workflow gallery",
    )
    html_meta = report.save(OUT_DIR / "06_investigation_brief.html")
    md_meta = report.save(OUT_DIR / "06_investigation_brief.md")
    print(f"brief html: {html_meta['figure_count']} figs, ship_all={html_meta['ship_all']}")
    print(f"brief md:   {md_meta['figure_count']} figs, assets={len(md_meta['assets'])}")
    assert html_meta["ship_all"] and md_meta["ship_all"]
    return rendered


if __name__ == "__main__":
    build_all()
