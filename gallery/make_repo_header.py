"""Generate the flagship 3-panel repo header masterpiece and palette-matching editions.

Combines a log-scale ECDF (panel a), deterministic beeswarm (panel b), and clean
booktabs table-graphics scorecard (panel c) across the pure-white NPG flagship,
its 1:1 116-column 2×4 Braille counterpart, and four curated palette-matching
editions (editorial serif, Nordic emerald & slate, deep pine dark, and warm
monograph ivory).

Outputs:
- ``gallery/output/readme_comparison/repo_header_hero.png``
- ``gallery/output/readme_comparison/repo_header_braille.png``
- ``gallery/output/palette_matching/{npg_editorial_serif,nordic_emerald_slate,pine_obsidian_dark,monograph_ivory_serif}.png``
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

GALLERY_DIR = Path(__file__).resolve().parent
if str(GALLERY_DIR) not in sys.path:
    sys.path.insert(0, str(GALLERY_DIR))

from braille_terminal_gallery import render_ansi_to_png

import mintfig as mint

OUT_PATH = GALLERY_DIR / "output" / "readme_comparison" / "repo_header_hero.png"
BRAILLE_OUT_PATH = GALLERY_DIR / "output" / "readme_comparison" / "repo_header_braille.png"
PALETTE_DIR = GALLERY_DIR / "output" / "palette_matching"


def build_repo_header() -> Path:
    rng = np.random.default_rng(42)

    v2_cached = np.clip(rng.lognormal(mean=np.log(29), sigma=0.30, size=161), 10, 115)
    v2_uncached = np.clip(rng.lognormal(mean=np.log(68), sigma=0.48, size=161), 18, 330)
    v1_baseline = np.clip(rng.lognormal(mean=np.log(98), sigma=0.52, size=161), 25, 520)

    datasets = {
        "v2 Cached": v2_cached,
        "v2 Uncached": v2_uncached,
        "v1 Baseline": v1_baseline,
    }
    p50 = {k: float(np.median(v)) for k, v in datasets.items()}
    p95 = {k: float(np.percentile(v, 95)) for k, v in datasets.items()}
    p99 = {k: float(np.percentile(v, 99)) for k, v in datasets.items()}
    under_slo = {k: round(float(np.mean(v <= 250.0) * 100.0), 1) for k, v in datasets.items()}
    ratio = p95["v1 Baseline"] / p95["v2 Cached"]

    # Quantile-sampled 45-point subset (index 22 == index 80 -> exact median match)
    swarm_idx = np.linspace(0, 160, 45, dtype=int)
    swarm_groups = {k: np.sort(v)[swarm_idx].tolist() for k, v in datasets.items()}

    rows = [
        {
            "Deployment": "v2 Cached",
            "p50": round(p50["v2 Cached"], 1),
            "p95": round(p95["v2 Cached"], 1),
            "lo": round(p95["v2 Cached"] * 0.91, 1),
            "hi": round(p95["v2 Cached"] * 1.09, 1),
            "p99": round(p99["v2 Cached"], 0),
            "Under SLO": under_slo["v2 Cached"],
        },
        {
            "Deployment": "v2 Uncached",
            "p50": round(p50["v2 Uncached"], 1),
            "p95": round(p95["v2 Uncached"], 1),
            "lo": round(p95["v2 Uncached"] * 0.92, 1),
            "hi": round(p95["v2 Uncached"] * 1.08, 1),
            "p99": round(p99["v2 Uncached"], 0),
            "Under SLO": under_slo["v2 Uncached"],
        },
        {
            "Deployment": "v1 Baseline",
            "p50": round(p50["v1 Baseline"], 1),
            "p95": round(p95["v1 Baseline"], 1),
            "lo": round(p95["v1 Baseline"] * 0.92, 1),
            "hi": round(p95["v1 Baseline"] * 1.08, 1),
            "p99": round(p99["v1 Baseline"], 0),
            "Under SLO": under_slo["v1 Baseline"],
        },
    ]

    spark_7d = {
        "v2 Cached": [210, 206, 152, 74, 52, 46, round(p95["v2 Cached"], 1)],
        "v2 Uncached": [208, 204, 174, 162, 158, 155, round(p95["v2 Uncached"], 1)],
        "v1 Baseline": [224, 218, 228, 221, 226, 219, round(p95["v1 Baseline"], 1)],
    }

    ecdf_panel = mint.distribution(
        {k: v.tolist() for k, v in datasets.items()},
        mode="ecdf",
        quantiles=(0.5, 0.95),
        log=True,
        baseline="v1 Baseline",
        highlight=["v2 Cached", "v2 Uncached"],
        reference=(250.0, "SLO 250 ms"),
        label="Request latency",
        unit="ms",
        title="Full latency CDF (log scale)",
    )

    swarm_panel = mint.distribution(
        swarm_groups,
        mode="swarm",
        baseline="v1 Baseline",
        highlight=["v2 Cached", "v2 Uncached"],
        reference=(250.0, "SLO 250 ms"),
        label="Sampled request latency",
        unit="ms",
        fmt=".1f",
        title="Raw trace spread (45 quantile-sampled requests)",
    )

    table_panel = mint.table(
        rows,
        units={"p50": "ms", "p95": "ms", "p99": "ms", "Under SLO": "%"},
        baseline="v1 Baseline",
        highlight=["v2 Cached", "v2 Uncached"],
        bold_best={"p50": "min", "p95": "min", "p99": "min", "Under SLO": "max"},
        interval={"p95": ("lo", "hi")},
        interval_label="95% CI, 5 runs",
        bars="p99",
        spark={"7-day p95": spark_7d},
        fmt={"p50": ".1f", "p95": ".1f", "p99": ".0f", "Under SLO": ".1f"},
        title="Deployment latency scorecard (p50, p95 with 95% CI, p99 bar, and 7-day rollout trend)",
    )

    fig = mint.explain(
        f"v2 Cached cuts p95 latency {ratio:.1f}× and keeps 100% of traffic under the 250\u00a0ms SLO",
        ecdf_panel,
        swarm_panel,
        table_panel,
        layout=[["a", "b"], ["c", "c"]],
        kicker="CHECKOUT LATENCY CANARY",
        subtitle="Production canary telemetry · n = 161 requests per deployment · log-scale ECDF and raw trace spread",
        source="prod/checkout_canary_2026-11 · generated in one mint.explain() call",
        style="prism",
        density="compact",
        width="slide",
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    summary = fig.save(OUT_PATH)
    plt.close(fig.fig)
    print(f"Wrote {OUT_PATH} | ship={summary['ship']} | issues={summary['issues']}")
    assert summary["ship"] is True and summary["issues"] == [], f"Issues: {summary['issues']}"

    # Color-aligned 116-column 3-panel 2×4 dot-matrix terminal counterpart
    braille_fig = mint.explain(
        f"v2 Cached cuts p95 latency {ratio:.1f}× and keeps 100% of traffic under the 250\u00a0ms SLO",
        mint.distribution(
            {k: v.tolist() for k, v in datasets.items()},
            mode="ecdf",
            quantiles=(0.5, 0.95),
            log=True,
            baseline="v1 Baseline",
            highlight=["v2 Cached", "v2 Uncached"],
            reference=(250.0, "SLO 250 ms"),
            label="Request latency",
            unit="ms",
            title="Full latency CDF (log scale)",
        ),
        mint.distribution(
            swarm_groups,
            mode="swarm",
            baseline="v1 Baseline",
            highlight=["v2 Cached", "v2 Uncached"],
            reference=(250.0, "SLO 250 ms"),
            label="Sampled request latency",
            unit="ms",
            fmt=".1f",
            title="Raw trace spread (45 requests)",
        ),
        mint.table(
            rows,
            units={"p50": "ms", "p95": "ms", "p99": "ms", "Under SLO": "%"},
            baseline="v1 Baseline",
            highlight=["v2 Cached", "v2 Uncached"],
            bold_best={"p50": "min", "p95": "min", "p99": "min", "Under SLO": "max"},
            interval={"p95": ("lo", "hi")},
            interval_label="95% CI, 5 runs",
            bars="p99",
            spark={"7-day p95": spark_7d},
            fmt={"p50": ".1f", "p95": ".1f", "p99": ".0f", "Under SLO": ".1f"},
            title="Deployment latency scorecard",
        ),
        layout=[["a", "b"], ["c", "c"]],
        kicker="CHECKOUT LATENCY CANARY",
        subtitle="Production canary telemetry · n = 161 requests per deployment",
        source="prod/checkout_canary_2026-11",
        style="obsidian",
        density="compact",
        width="slide",
    )
    ansi = braille_fig.to_text(mode="matrix", color=True, width=116)
    render_ansi_to_png(
        ansi,
        BRAILLE_OUT_PATH,
        title="mintfig show checkout_canary.png --matrix --width 116",
        badge="116-col 3-Panel · 2×4 Dot-Matrix",
        font_size=18,
        supersample=2,
    )
    plt.close(braille_fig.fig)
    print(f"Wrote {BRAILLE_OUT_PATH}")

    # Curated palette-matching gallery editions (first-class built-in styles)
    palette_editions = {
        "npg_editorial_serif": "folio",
        "nordic_emerald_slate": "nordic",
        "pine_obsidian_dark": "obsidian",
        "monograph_ivory_serif": "monograph",
    }

    PALETTE_DIR.mkdir(parents=True, exist_ok=True)
    for slug, style_name in palette_editions.items():
        ed_fig = mint.explain(
            f"v2 Cached cuts p95 latency {ratio:.1f}× and keeps 100% of traffic under the 250\u00a0ms SLO",
            mint.distribution(
                {k: v.tolist() for k, v in datasets.items()},
                mode="ecdf",
                quantiles=(0.5, 0.95),
                log=True,
                baseline="v1 Baseline",
                highlight=["v2 Cached", "v2 Uncached"],
                reference=(250.0, "SLO 250 ms"),
                label="Request latency",
                unit="ms",
                title="Full latency CDF (log scale)",
            ),
            mint.distribution(
                swarm_groups,
                mode="swarm",
                baseline="v1 Baseline",
                highlight=["v2 Cached", "v2 Uncached"],
                reference=(250.0, "SLO 250 ms"),
                label="Sampled request latency",
                unit="ms",
                fmt=".1f",
                title="Raw trace spread (45 quantile-sampled requests)",
            ),
            mint.table(
                rows,
                units={"p50": "ms", "p95": "ms", "p99": "ms", "Under SLO": "%"},
                baseline="v1 Baseline",
                highlight=["v2 Cached", "v2 Uncached"],
                bold_best={"p50": "min", "p95": "min", "p99": "min", "Under SLO": "max"},
                interval={"p95": ("lo", "hi")},
                interval_label="95% CI, 5 runs",
                bars="p99",
                spark={"7-day p95": spark_7d},
                fmt={"p50": ".1f", "p95": ".1f", "p99": ".0f", "Under SLO": ".1f"},
                title="Deployment latency scorecard (p50, p95 with 95% CI, p99 bar, and 7-day rollout trend)",
            ),
            layout=[["a", "b"], ["c", "c"]],
            kicker="CHECKOUT LATENCY CANARY",
            subtitle="Production canary telemetry · n = 161 requests per deployment · log-scale ECDF and raw trace spread",
            source="prod/checkout_canary_2026-11 · generated in one mint.explain() call",
            style=style_name,
            density="compact",
            width="slide",
        )
        out_ed = PALETTE_DIR / f"{slug}.png"
        ed_summary = ed_fig.save(out_ed)
        plt.close(ed_fig.fig)
        print(f"Wrote {out_ed} | ship={ed_summary['ship']} | issues={ed_summary['issues']}")
        assert ed_summary["ship"] is True and ed_summary["issues"] == [], (
            f"Issues in {slug}: {ed_summary['issues']}"
        )

    return OUT_PATH


if __name__ == "__main__":
    build_repo_header()
