"""Message-first chat figures made with ``mint.explain`` (all data synthetic).

Each example is one takeaway sentence plus the panels that prove it, rendered at
chat size (1400 px wide, shown ~700 px). Run directly to write PNGs and their
reproducible JSON specs to ``gallery/output/explain/``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

import mintfig as mint

SOURCE = "synthetic example data"


def latency_regression() -> mint.Explanation:
    """A two-step argument: what is wrong, then since when."""
    return mint.explain(
        "Checkout is the slow service: its p99 is 4x the next worst",
        mint.compare(
            {
                "checkout": 1840,
                "search": 460,
                "auth": 310,
                "catalog": 280,
                "cart": 240,
                "profile": 120,
            },
            title="Checkout stands alone",
            label="p99 latency",
            unit="ms",
            highlight="checkout",
        ),
        mint.trend(
            list(range(1, 9)),
            {
                "checkout": [540, 560, 550, 570, 980, 1400, 1700, 1840],
                "search": [450, 470, 455, 465, 460, 450, 470, 460],
                "auth": [300, 310, 305, 315, 300, 320, 305, 310],
            },
            title="It regressed after the v2.3 deploy",
            label="p99 latency",
            unit="ms",
            x_label="Week",
            highlight="checkout",
            events={4: "v2.3 deploy"},
        ),
        subtitle="API latency by service, week of 16 Nov",
        source=SOURCE,
    )


def build_time() -> mint.Explanation:
    """Part-to-whole without a pie."""
    return mint.explain(
        "Three stages take 82% of the build: compile, integration tests and image push",
        mint.share(
            {
                "compile": 412,
                "integration tests": 388,
                "image push": 160,
                "lint": 61,
                "unit tests": 58,
                "checkout": 41,
                "cache restore": 33,
                "notify": 9,
                "cleanup": 7,
                "sbom": 6,
            },
            label="build time",
            unit="s",
            highlight=["compile", "integration tests", "image push"],
            top=6,
        ),
        source=SOURCE,
    )


def benchmark_gains() -> mint.Explanation:
    """Paired before/after across items."""
    before = {
        "MATH-500": 79,
        "AIME": 38,
        "MMLU-Pro": 74,
        "GPQA": 61,
        "SWE-bench": 49,
        "SimpleQA": 31,
    }
    after = {
        "MATH-500": 95,
        "AIME": 88,
        "MMLU-Pro": 86,
        "GPQA": 82,
        "SWE-bench": 77,
        "SimpleQA": 58,
    }
    return mint.explain(
        "The new model gains most where the old one was weakest: +50 points on AIME",
        mint.change(
            before, after, labels=("Prior", "New"), label="Accuracy", unit="%", highlight="AIME"
        ),
        source=SOURCE,
    )


def agent_matrix() -> mint.Explanation:
    """Two categorical dimensions: colour for the pattern, a number in every cell."""
    rng = np.random.default_rng(3)
    values = rng.uniform(48, 95, (5, 5)).round(0)
    values[2, 4] = 22
    return mint.explain(
        "Rust performance work is the one cell where the agent fails most tasks",
        mint.matrix(
            values.tolist(),
            rows=["Python", "Go", "Rust", "TypeScript", "Java"],
            cols=["bugfix", "refactor", "tests", "docs", "perf"],
            label="Tasks solved",
            unit="%",
            highlight=[("Rust", "perf")],
        ),
        source=SOURCE,
    )


def regional_orders() -> mint.Explanation:
    """More than four series with no single focus: small multiples on one scale."""
    rng = np.random.default_rng(11)
    weeks = [f"W{i}" for i in range(1, 13)]
    regions = ["NA", "EMEA", "APAC", "LATAM", "ANZ", "India"]
    series = {}
    for region in regions:
        path = 100 + np.cumsum(rng.normal(0.4, 1.6, 12))
        path[4:7] -= 9
        if region == "EMEA":
            path[7:] -= 14
        series[region] = path.round(1).tolist()
    return mint.explain(
        "Every region dipped in weeks 5-7, but only EMEA failed to recover",
        mint.trend(
            weeks, series, label="Orders, indexed to week 0 = 100", facet=True, highlight="EMEA"
        ),
        source=SOURCE,
    )


def checkout_story() -> mint.Explanation:
    """Four panels, one argument: size, onset, spread, consequence."""
    rng = np.random.default_rng(5)
    return mint.explain(
        "Checkout regressed after v2.3: slower, more variable, and now most of the wait",
        mint.compare(
            {"checkout": 1840, "search": 460, "auth": 310, "catalog": 280},
            title="It is 4x slower than anything else",
            label="p99",
            unit="ms",
            highlight="checkout",
        ),
        mint.trend(
            list(range(1, 9)),
            {
                "checkout": [540, 560, 550, 570, 980, 1400, 1700, 1840],
                "search": [450, 470, 455, 465, 460, 450, 470, 460],
            },
            title="The jump starts at the deploy",
            label="p99",
            unit="ms",
            x_label="Week",
            highlight="checkout",
            events={4: "v2.3"},
        ),
        mint.distribution(
            {
                "before": rng.lognormal(6.2, 0.2, 80).round(0).tolist(),
                "after": rng.lognormal(7.2, 0.5, 80).round(0).tolist(),
            },
            title="The tail got longer, not just the middle",
            label="Request time",
            unit="ms",
            highlight="after",
        ),
        mint.share(
            {"checkout": 61, "search": 14, "auth": 9, "catalog": 8, "other": 8},
            title="It is now most of the time users wait",
            label="request time",
            unit="%",
            highlight="checkout",
        ),
        source=SOURCE,
    )


EXAMPLES = {
    "latency_regression": latency_regression,
    "build_time": build_time,
    "benchmark_gains": benchmark_gains,
    "agent_matrix": agent_matrix,
    "regional_orders": regional_orders,
    "checkout_story": checkout_story,
}


def build() -> mint.Explanation:
    """Entry point for ``mintfig run gallery/explain_chat_examples.py --journal screen``."""
    return latency_regression()


if __name__ == "__main__":
    out_dir = Path(__file__).resolve().parent / "output" / "explain"
    for name, make in EXAMPLES.items():
        summary = make().save(out_dir / f"{name}.png", write_spec=True)
        print(f"{name}: ok={summary['ok']} {summary['size_px']} issues={summary['issues']}")
