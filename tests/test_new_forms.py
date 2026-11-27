"""Tests for new analytical forms: distribution(mode="ecdf"), matrix(normalize=, show_counts=), and mint.forest()."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest

import mintfig as mint
from mintfig import ExplainError

# --------------------------------------------------------------------------- #
# 1. distribution(mode="ecdf")
# --------------------------------------------------------------------------- #


def _latency_groups() -> dict[str, list[float]]:
    rng = np.random.default_rng(7)
    return {
        "v1 Baseline": np.round(rng.lognormal(mean=4.4, sigma=0.55, size=120), 1).tolist(),
        "v2 Uncached": np.round(rng.lognormal(mean=3.9, sigma=0.45, size=120), 1).tolist(),
        "v2 Cached": np.round(rng.lognormal(mean=3.2, sigma=0.35, size=120), 1).tolist(),
    }


def test_distribution_ecdf_renders_and_ships(tmp_path: Path) -> None:
    groups = _latency_groups()
    panel = mint.distribution(
        groups,
        mode="ecdf",
        log=True,
        baseline="v1 Baseline",
        highlight="v2 Cached",
        reference=(200.0, "SLO 200 ms"),
        label="Latency",
        unit="ms",
    )
    assert panel.kind == "distribution"
    assert panel.spec["mode"] == "ecdf"

    # Facts report p50, p95, p99 for each group and ratios vs baseline.
    joined = "\n".join(panel.facts)
    for name in groups:
        assert f"{name}: p50" in joined
        assert "p95" in joined
        assert "p99" in joined
    assert "v2 Cached vs v1 Baseline:" in joined
    assert "SLO 200 ms" in joined

    exp = mint.explain(
        "Caching cuts tail latency across the entire distribution",
        panel,
        colors={"v2 Cached": "#0F8B6D"},
    )
    out = tmp_path / "ecdf.png"
    summary = exp.save(out)
    try:
        assert out.exists() and out.stat().st_size > 1000
        assert summary["ship"] is True, f"Expected ship=True, got issues={summary['issues']}"
        assert summary["issues"] == []

        # Text and HTML surfaces work cleanly
        txt = exp.to_text()
        assert "p50" in txt and "p95" in txt and "p99" in txt
        assert "v2 Cached" in txt

        html = exp.to_html()
        assert "v2 Cached" in html
        assert "p95" in html

        # Spec round-trip through mint.load
        spec = exp.to_spec()
        reloaded = mint.load(spec)
        try:
            assert reloaded.panels["a"].spec["mode"] == "ecdf"
            assert reloaded.ship is True
        finally:
            plt.close(reloaded.fig)
    finally:
        plt.close(exp.fig)


def test_distribution_ecdf_single_series_and_custom_quantiles(tmp_path: Path) -> None:
    rng = np.random.default_rng(11)
    vals = np.round(rng.normal(loc=50.0, scale=12.0, size=80), 2).tolist()
    panel = mint.distribution(
        vals,
        mode="ecdf",
        quantiles=(0.5, 0.9, 0.99),
        label="Score",
        unit="pts",
    )
    assert panel.spec["quantiles"] == [0.5, 0.9, 0.99]
    joined = "\n".join(panel.facts)
    assert "p50" in joined and "p90" in joined and "p95" in joined and "p99" in joined

    exp = mint.explain("Scores cluster near 50 pts with a tight upper tail", panel)
    out = tmp_path / "ecdf_single.png"
    summary = exp.save(out)
    try:
        assert summary["ship"] is True
        assert summary["issues"] == []
        reloaded = mint.load(exp.to_spec())
        try:
            assert reloaded.panels["a"].spec["quantiles"] == [0.5, 0.9, 0.99]
            assert reloaded.ship is True
        finally:
            plt.close(reloaded.fig)
    finally:
        plt.close(exp.fig)


def test_distribution_ecdf_validation_errors() -> None:
    vals = {"a": [1.0, 2.0, 3.0, 4.0, 5.0]}
    with pytest.raises(ExplainError, match="quantiles"):
        mint.distribution(vals, mode="ecdf", quantiles=(0.0, 0.5))
    with pytest.raises(ExplainError, match="quantiles"):
        mint.distribution(vals, mode="ecdf", quantiles=(0.5, 1.0))
    with pytest.raises(ExplainError, match="bins"):
        mint.distribution(vals, mode="ecdf", bins=10)
    with pytest.raises(ExplainError, match="facet"):
        mint.distribution({"f1": vals, "f2": vals}, mode="ecdf", facet=True)


# --------------------------------------------------------------------------- #
# 2. matrix(normalize=..., show_counts=...)
# --------------------------------------------------------------------------- #


def test_matrix_row_normalized_confusion_ships(tmp_path: Path) -> None:
    classes = ["Bug", "Feature", "Docs", "Security"]
    counts = [
        [84, 9, 4, 3],
        [11, 78, 8, 3],
        [2, 6, 90, 2],
        [5, 2, 1, 42],
    ]
    panel = mint.matrix(
        counts,
        rows=classes,
        cols=classes,
        normalize="row",
        show_counts=True,
        label="Predicted class",
    )
    assert panel.kind == "matrix"
    assert panel.spec["normalize"] == "row"
    assert panel.spec["show_counts"] is True
    # Spec retains raw counts for lossless round-trip!
    assert panel.spec["values"][0][0] == 84.0
    assert panel.spec["values"][3][3] == 42.0

    # Facts report macro diagonal accuracy and top off-diagonal confusion pair.
    joined = "\n".join(panel.facts)
    assert "macro diagonal accuracy:" in joined
    # Macro diagonal = (84 + 78 + 90 + 84) / 4 = 84.0%
    assert "84.0%" in joined
    assert "top off-diagonal confusion: Feature" in joined
    assert "Bug" in joined

    exp = mint.explain(
        "Classifier reaches 84% macro accuracy; Feature-to-Bug is the top error",
        panel,
    )
    out = tmp_path / "confusion.png"
    summary = exp.save(out)
    try:
        assert out.exists() and out.stat().st_size > 1000
        assert summary["ship"] is True, f"Expected ship=True, got issues={summary['issues']}"
        assert summary["issues"] == []

        txt = exp.to_text()
        assert "84%" in txt and "(84)" in txt
        assert "macro diagonal accuracy" in txt

        html = exp.to_html()
        assert "84.0% (84)" in html

        # Spec round-trip preserves raw counts, normalize, show_counts, and facts
        reloaded = mint.load(exp.to_spec())
        try:
            assert reloaded.panels["a"].spec["normalize"] == "row"
            assert reloaded.panels["a"].spec["show_counts"] is True
            assert reloaded.panels["a"].spec["values"][0][0] == 84.0
            assert reloaded.ship is True
        finally:
            plt.close(reloaded.fig)
    finally:
        plt.close(exp.fig)


def test_matrix_col_normalize_and_edge_cases(tmp_path: Path) -> None:
    panel = mint.matrix(
        [[30, 10], [70, 30], [0, 60]],
        rows=["Low", "Med", "High"],
        cols=["Control", "Treated"],
        normalize="col",
        show_counts=False,
        label="Column share",
    )
    assert panel.spec["normalize"] == "col"
    assert panel.spec.get("show_counts") is None
    # Rectangular matrix should not invent confusion-matrix macro diagonal accuracy
    assert not any("macro diagonal accuracy" in f for f in panel.facts)

    exp = mint.explain("Treated shifts 60% of outcomes into the High tier", panel)
    out = tmp_path / "col_norm.png"
    summary = exp.save(out)
    try:
        assert summary["ship"] is True
        assert summary["issues"] == []
    finally:
        plt.close(exp.fig)

    # Zero-sum row does not crash with ZeroDivisionError / NaN
    p_zero = mint.matrix(
        [[0, 0], [5, 15]],
        rows=["Empty", "Active"],
        cols=["A", "B"],
        normalize="row",
        show_counts=True,
    )
    assert p_zero.kind == "matrix"

    # Validation errors
    with pytest.raises(ExplainError, match="normalize"):
        mint.matrix([[1, 2], [3, 4]], rows=["a", "b"], cols=["x", "y"], normalize="diag")
    with pytest.raises(ExplainError, match="non-negative"):
        mint.matrix([[-1, 2], [3, 4]], rows=["a", "b"], cols=["x", "y"], normalize="row")
    with pytest.raises(ExplainError, match="show_counts"):
        mint.matrix(
            [[1, 2], [3, 4]],
            rows=["a", "b"],
            cols=["x", "y"],
            normalize="row",
            show_counts="yes",  # type: ignore[arg-type]
        )


# --------------------------------------------------------------------------- #
# 3. mint.forest(...)
# --------------------------------------------------------------------------- #


def test_forest_ab_test_with_pooled_diamond_ships(tmp_path: Path) -> None:
    data = {
        "Checkout v3": 4.2,
        "Mobile Web": 3.1,
        "Desktop": 2.4,
        "iOS App": 1.9,
        "Android App": 0.6,
        "Enterprise": -0.4,
    }
    cis = {
        "Checkout v3": (2.5, 5.9),
        "Mobile Web": (1.4, 4.8),
        "Desktop": (0.9, 3.9),
        "iOS App": (0.3, 3.5),
        "Android App": (-0.9, 2.1),
        "Enterprise": (-2.2, 1.4),
    }
    counts = {
        "Checkout v3": 4200,
        "Mobile Web": 3800,
        "Desktop": 4600,
        "iOS App": 2900,
        "Android App": 2100,
        "Enterprise": 800,
    }
    panel = mint.forest(
        data,
        error=cis,
        error_label="95% CI",
        reference=0.0,
        pooled={"label": "Pooled", "value": 2.3, "lo": 1.6, "hi": 3.0, "n": 18400},
        n=counts,
        label="Conversion lift",
        unit="pp",
        highlight="Checkout v3",
    )
    assert panel.kind == "forest"
    assert panel.issues == []
    assert "95% CI" in (panel.measure_note or "")

    joined = "\n".join(panel.facts)
    assert "4 of 6 items exclude null" in joined
    assert "largest effect: Checkout v3" in joined
    assert "Pooled:" in joined and "excludes null" in joined

    exp = mint.explain(
        "Checkout v3 leads a +2.3 pp pooled lift across four winning cohorts",
        panel,
        colors={"Checkout v3": "#0F8B6D"},
    )
    out = tmp_path / "forest.png"
    summary = exp.save(out)
    try:
        assert out.exists() and out.stat().st_size > 1000
        assert summary["ship"] is True, f"Expected ship=True, got issues={summary['issues']}"
        assert summary["issues"] == []

        txt = exp.to_text()
        assert "Checkout v3" in txt
        assert "Pooled" in txt
        assert "95% CI" in txt
        assert "n=4,200" in txt

        html = exp.to_html()
        assert "Checkout v3" in html
        assert "Pooled" in html
        assert "Low (95% CI)" in html

        # Spec round-trip through mint.load
        spec = exp.to_spec()
        assert spec["panels"][0]["kind"] == "forest"
        reloaded = mint.load(spec)
        try:
            assert reloaded.panels["a"].kind == "forest"
            assert reloaded.panels["a"].spec["pooled"]["value"] == 2.3
            assert reloaded.ship is True
        finally:
            plt.close(reloaded.fig)
    finally:
        plt.close(exp.fig)


def test_forest_log_odds_ratio_and_tuple_pooled(tmp_path: Path) -> None:
    panel = mint.forest(
        {"Trial A": 1.62, "Trial B": 1.35, "Trial C": 1.08, "Trial D": 0.94},
        error={
            "Trial A": (1.24, 2.12),
            "Trial B": (1.05, 1.74),
            "Trial C": (0.82, 1.42),
            "Trial D": (0.71, 1.24),
        },
        error_label="95% CI",
        reference=(1.0, "No effect"),
        pooled=(1.28, 1.11, 1.48),
        label="Odds ratio",
        log=True,
        sort=False,
    )
    assert panel.spec["log"] is True
    assert panel.spec["pooled"]["label"] == "Pooled"
    assert panel.spec["pooled"]["value"] == 1.28

    exp = mint.explain("Pooled odds ratio reaches 1.28 across four trials", panel)
    out = tmp_path / "forest_or.png"
    summary = exp.save(out)
    try:
        assert summary["ship"] is True
        assert summary["issues"] == []
        reloaded = mint.load(exp.to_spec())
        try:
            assert reloaded.panels["a"].spec["log"] is True
            assert reloaded.ship is True
        finally:
            plt.close(reloaded.fig)
    finally:
        plt.close(exp.fig)


def test_forest_missing_error_label_warns_and_validation() -> None:
    panel = mint.forest(
        {"Arm A": 1.5, "Arm B": 0.4},
        error={"Arm A": (0.7, 2.3), "Arm B": (-0.5, 1.3)},
        error_label=None,
    )
    assert any(iss["rule"] == "interval_unlabelled" for iss in panel.issues)

    with pytest.raises(ExplainError, match="reference=1.0"):
        mint.forest(
            {"A": 1.5, "B": 1.2},
            error={"A": (1.1, 2.0), "B": (0.9, 1.6)},
            error_label="95% CI",
            log=True,
        )
    with pytest.raises(ExplainError, match="bracket"):
        mint.forest(
            {"A": 1.5},
            error={"A": (1.0, 2.0)},
            error_label="95% CI",
            pooled=(3.0, 1.0, 2.0),
        )
    with pytest.raises(ExplainError, match="empty"):
        mint.forest({}, error={}, error_label="95% CI")
