"""Tests for Bet 2a Visual-Science Form Upgrades (quantile dotplots, nested CI, deltas, callouts & regions)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import figmint as fm
from figmint._explain.distribution import _prob_superiority
from figmint.audit import audit_figure
from figmint.explainer import ExplainError

# --------------------------------------------------------------------------- #
# 1. Quantile dotplots & exceedance / superiority probability facts
# --------------------------------------------------------------------------- #


def test_quantile_dotplot_basic_and_roundtrip(tmp_path: Path) -> None:
    rng = np.random.default_rng(42)
    groups = {
        "Baseline": rng.normal(48.0, 6.0, size=60).tolist(),
        "Candidate": rng.normal(58.0, 5.5, size=60).tolist(),
        "Legacy": rng.normal(44.0, 7.0, size=60).tolist(),
    }
    panel = fm.distribution(
        groups,
        title="Candidate shifts latency distribution right",
        label="Throughput",
        unit="req/s",
        baseline="Baseline",
        highlight="Candidate",
        reference=(55.0, "target"),
        mode="quantile",
        quantiles=20,
    )
    assert "quantile dotplot (20 dots/group, 5% each)" in (panel.measure_note or "")
    assert any("of 20 quantiles" in f and "above 55 req/s (target)" in f for f in panel.facts)
    assert any("P(Candidate > Baseline) =" in f for f in panel.facts)

    spec = panel.to_spec()
    assert spec["mode"] == "quantile"
    assert spec["quantiles"] == 20

    exp = fm.explain(
        "Candidate exceeds the 55 req/s target in most quantiles",
        panel,
        source="synthetic benchmark",
    )
    assert exp.ship is True
    assert exp.issues == []
    with exp.theme.rc_context(exp.spec):
        aud = audit_figure(exp.fig)
    assert aud["overlaps"] == []
    assert aud["struck"] == []
    assert aud["text_faults"] == []

    png = tmp_path / "quantile_roundtrip.png"
    exp.save(png)
    reloaded = fm.load(png)
    assert reloaded.ship is True
    assert reloaded.issues == []
    assert reloaded.to_spec()["panels"][0]["mode"] == "quantile"
    assert reloaded.to_spec()["panels"][0]["quantiles"] == 20


def test_distribution_default_spec_omits_mode_and_quantiles() -> None:
    p = fm.distribution(
        {"control": [10, 12, 14, 15, 16], "treated": [18, 20, 21, 23, 25]},
        label="Score",
        baseline="control",
        reference=(17, "cutoff"),
    )
    spec = p.to_spec()
    assert "mode" not in spec
    assert "quantiles" not in spec
    assert any("of observations above 17 (cutoff)" in f for f in p.facts)
    assert any("P(treated > control) = 100%" in f for f in p.facts)


def test_prob_superiority_exact_with_ties() -> None:
    # Pairs: (2,1)->1, (2,2)->0.5, (3,1)->1, (3,2)->1 => 3.5/4 = 0.875
    p = _prob_superiority(np.array([2.0, 3.0]), np.array([1.0, 2.0]))
    assert p == pytest.approx(0.875)
    # Identical distributions => 0.5
    p_eq = _prob_superiority(np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0, 3.0]))
    assert p_eq == pytest.approx(0.5)

    panel = fm.distribution(
        {"ctrl": [1.0, 2.0, 3.0, 4.0], "trt": [2.0, 3.0, 4.0, 5.0]},
        label="Yield",
        baseline="ctrl",
    )
    # Concordant pairs: (2>1, 2=2, 3>1,2, 3=3, 4>1,2,3, 4=4, 5>1,2,3,4) = (1+0.5 + 2+0.5 + 3+0.5 + 4) = 11.5 / 16 = 71.875% -> 72%
    assert any("P(trt > ctrl) = 72%" in f for f in panel.facts)


def test_quantile_dotplot_log_single_and_constant() -> None:
    rng = np.random.default_rng(7)
    exp_log = fm.explain(
        "Log-scale quantile dotplot renders cleanly across decades",
        fm.distribution(
            {
                "Slow": np.exp(rng.normal(2.5, 0.4, 50)).tolist(),
                "Fast": np.exp(rng.normal(1.2, 0.35, 50)).tolist(),
            },
            label="Latency",
            unit="ms",
            log=True,
            stat="mean",
            mode="quantile",
            quantiles=15,
        ),
        source="synthetic",
    )
    assert exp_log.ship is True
    assert exp_log.issues == []
    assert "6.7% each" in (exp_log.panels["a"].measure_note or "")

    exp_const = fm.explain(
        "Constant values stack cleanly in quantile mode",
        fm.distribution([5.0, 5.0, 5.0, 5.0, 5.0], label="Score", mode="quantile", quantiles=10),
        source="synthetic",
    )
    assert exp_const.ship is True
    assert exp_const.issues == []


def test_quantile_dotplot_validation_errors() -> None:
    vals = {"a": [1, 2, 3, 4, 5]}
    with pytest.raises(ExplainError, match="mode"):
        fm.distribution(vals, mode="beeswarm")
    with pytest.raises(ExplainError, match="quantiles"):
        fm.distribution(vals, mode="quantile", quantiles=4)
    with pytest.raises(ExplainError, match="quantiles"):
        fm.distribution(vals, mode="quantile", quantiles=51)
    with pytest.raises(ExplainError, match="quantiles"):
        fm.distribution(vals, mode="quantile", quantiles=True)  # type: ignore[arg-type]
    with pytest.raises(ExplainError, match="bins"):
        fm.distribution(vals, mode="quantile", bins="auto")


# --------------------------------------------------------------------------- #
# 2. Nested multi-level intervals & inline baseline deltas on compare()
# --------------------------------------------------------------------------- #


def test_compare_nested_intervals_and_show_delta_roundtrip(tmp_path: Path) -> None:
    vals = {"Model A": 84.2, "Model B": 74.9, "Model C": 73.5, "Model D": 68.1}
    outer = {
        "Model A": (81.5, 86.9),
        "Model B": (72.1, 77.7),
        "Model C": (70.8, 76.2),
        "Model D": (65.0, 71.2),
    }
    inner = {
        "Model A": (83.2, 85.2),
        "Model B": (73.9, 75.9),
        "Model C": (72.5, 74.5),
        "Model D": (67.0, 69.2),
    }
    panel = fm.compare(
        vals,
        title="Model A leads baseline by +9.3 points",
        label="Accuracy",
        unit="%",
        baseline="Model B",
        highlight="Model A",
        error=outer,
        inner_error=inner,
        error_label="50% / 95% CI",
        show_delta=True,
    )
    assert "thick bar: inner interval" in (panel.measure_note or "")
    spec = panel.to_spec()
    assert spec["inner_error"] is not None
    assert spec["show_delta"] is True

    exp = fm.explain(
        "Model A beats the Model B baseline by +9.3 points with non-overlapping CIs",
        panel,
        source="synthetic eval",
    )
    assert exp.ship is True
    assert exp.issues == []

    # Verify inline signed delta text appears on non-baseline labels (with Unicode minus) and not baseline
    ax = exp["a"]
    texts = [t.get_text() for t in ax.texts]
    assert any("(+9.3)" in t for t in texts)
    assert any("(\N{MINUS SIGN}1.4)" in t for t in texts)
    assert any("(\N{MINUS SIGN}6.8)" in t for t in texts)
    assert any(t.startswith("74.9%") and "(" not in t for t in texts)

    # Verify outer + inner interval collections exist with thicker inner linewidth
    lws = [float(c.get_linewidth()[0]) for c in ax.collections if len(c.get_linewidth())]
    assert any(lw >= 2.2 for lw in lws)

    png = tmp_path / "nested_ci_delta.png"
    exp.save(png)
    reloaded = fm.load(png)
    assert reloaded.ship is True
    assert reloaded.issues == []
    assert reloaded.to_spec()["panels"][0]["show_delta"] is True
    assert reloaded.to_spec()["panels"][0]["inner_error"] is not None


def test_compare_show_delta_on_bars_and_tabular_inner_error() -> None:
    exp_bar = fm.explain(
        "Bars with inline baseline deltas ship cleanly",
        fm.compare(
            {"New": 92.4, "Baseline": 83.1, "Old": 79.5},
            label="Win rate",
            unit="%",
            baseline="Baseline",
            highlight="New",
            show_delta=True,
        ),
        source="synthetic",
    )
    assert exp_bar.ship is True
    assert exp_bar.issues == []

    rows = [
        {"model": "A", "score": 80.0, "ci95": 4.0, "ci50": 1.5},
        {"model": "B", "score": 72.0, "ci95": 3.5, "ci50": 1.2},
        {"model": "C", "score": 68.0, "ci95": 3.0, "ci50": 1.0},
    ]
    exp_tab = fm.explain(
        "Tabular inner_error column resolves cleanly",
        fm.compare(
            rows,
            name="model",
            value="score",
            error="ci95",
            inner_error="ci50",
            error_label="50% / 95% CI",
            label="Score",
        ),
        source="synthetic",
    )
    assert exp_tab.ship is True
    assert exp_tab.issues == []

    # Default compare spec omits inner_error and show_delta
    plain = fm.compare({"A": 10, "B": 5}, label="Count")
    assert "inner_error" not in plain.to_spec()
    assert "show_delta" not in plain.to_spec()


def test_compare_nested_and_delta_validation_errors() -> None:
    vals = {"A": 10.0, "B": 8.0}
    with pytest.raises(ExplainError, match="requires error="):
        fm.compare(vals, inner_error=0.5)
    with pytest.raises(ExplainError, match="extends outside outer error"):
        fm.compare(vals, error=1.0, inner_error=1.5, error_label="CI")
    with pytest.raises(ExplainError, match="extends outside outer error"):
        fm.compare(
            vals,
            error={"A": (9.0, 11.0), "B": (7.0, 9.0)},
            inner_error={"A": (8.5, 10.5), "B": (7.5, 8.5)},
            error_label="CI",
        )
    with pytest.raises(ExplainError, match="requires baseline="):
        fm.compare(vals, show_delta=True)
    with pytest.raises(ExplainError, match="cannot be combined with boost="):
        fm.compare(vals, baseline="B", show_delta=True, boost={"A": 2.0, "B": 1.0}, boost_label="extra")
    with pytest.raises(ExplainError, match="Grouped compare"):
        fm.compare({"Cat1": {"A": 10, "B": 8}, "Cat2": {"A": 12, "B": 9}}, show_delta=True)


# --------------------------------------------------------------------------- #
# 3. Direct callouts & shaded regions on trend() and relate()
# --------------------------------------------------------------------------- #


def test_trend_callouts_and_regions_numeric_and_dates(tmp_path: Path) -> None:
    dates = [
        "2026-01-01",
        "2026-01-15",
        "2026-02-01",
        "2026-02-15",
        "2026-03-01",
        "2026-03-15",
        "2026-04-01",
        "2026-04-15",
    ]
    panel_date = fm.trend(
        dates,
        {
            "API v2": [180, 175, 170, 290, 310, 240, 165, 160],
            "API v1": [210, 215, 208, 212, 218, 214, 210, 212],
        },
        title="Cache incident raised API v2 latency during Feb–Mar",
        label="p95 latency",
        unit="ms",
        highlight="API v2",
        regions=[("2026-02-01", "2026-03-15", "Cache outage")],
        callouts=[
            ("2026-03-01", 310.0, "Peak 310 ms"),
            ("2026-04-01", 165.0, "Fix deployed"),
        ],
    )
    spec = panel_date.to_spec()
    assert spec["regions"] == [["2026-02-01", "2026-03-15", "Cache outage"]]
    assert spec["callouts"] == [["2026-03-01", 310.0, "Peak 310 ms"], ["2026-04-01", 165.0, "Fix deployed"]]

    exp = fm.explain(
        "API v2 spiked to 310 ms during the Feb–Mar cache outage before recovering",
        panel_date,
        source="synthetic telemetry",
    )
    assert exp.ship is True
    assert exp.issues == []
    with exp.theme.rc_context(exp.spec):
        aud = audit_figure(exp.fig)
    assert aud["overlaps"] == []
    assert aud["struck"] == []
    assert aud["text_faults"] == []

    png = tmp_path / "trend_regions_callouts.png"
    exp.save(png)
    reloaded = fm.load(png)
    assert reloaded.ship is True
    assert reloaded.issues == []
    assert reloaded.to_spec()["panels"][0]["regions"] == spec["regions"]
    assert reloaded.to_spec()["panels"][0]["callouts"] == spec["callouts"]


def test_trend_numeric_log_and_facet_with_regions_callouts() -> None:
    exp_num = fm.explain(
        "Training loss drops sharply after warmup",
        fm.trend(
            [1, 2, 4, 8, 16, 32, 64],
            {"Run A": [2.8, 2.4, 1.9, 1.3, 0.9, 0.72, 0.65], "Run B": [2.9, 2.7, 2.4, 2.0, 1.7, 1.5, 1.4]},
            label="Loss",
            x_label="Step (k)",
            log_x=True,
            highlight="Run A",
            regions=[(1, 4, "Warmup")],
            callouts=[(16, 0.9, "LR decay")],
        ),
        source="synthetic",
    )
    assert exp_num.ship is True
    assert exp_num.issues == []

    exp_facet = fm.explain(
        "Faceted trend supports regions and callouts cleanly",
        fm.trend(
            [1, 2, 3, 4, 5, 6],
            {
                "S1": [10, 12, 18, 22, 20, 19],
                "S2": [11, 11, 13, 14, 15, 16],
                "S3": [9, 10, 11, 12, 13, 14],
            },
            label="Rate",
            facet=True,
            regions=[(2, 4, "Window")],
            callouts=[(4, 22, "Peak")],
        ),
        source="synthetic",
    )
    assert exp_facet.ship is True
    assert exp_facet.issues == []


def test_relate_callouts_and_regions_roundtrip(tmp_path: Path) -> None:
    xs = [0.8, 1.5, 2.4, 4.0, 7.5, 12.0, 18.0, 26.0]
    ys = [64.0, 72.5, 79.0, 86.2, 89.5, 91.2, 92.0, 92.3]
    names = ["Tiny", "Small", "Base", "Sweet", "Mid", "Large", "XL", "XXL"]
    panel = fm.relate(
        xs,
        ys,
        x_label="Cost ($/1M tok)",
        y_label="Accuracy (%)",
        names=names,
        highlight=["Sweet"],
        frontier="upper-left",
        regions=[(1.0, 5.5, "Budget sweet spot")],
        callouts=[
            (4.0, 86.2, "Knee: 86.2% at $4"),
            (26.0, 92.3, "Diminishing returns"),
        ],
    )
    spec = panel.to_spec()
    assert spec["regions"] == [[1.0, 5.5, "Budget sweet spot"]]
    assert spec["callouts"] == [[4.0, 86.2, "Knee: 86.2% at $4"], [26.0, 92.3, "Diminishing returns"]]

    exp = fm.explain(
        "Sweet captures 93% of top accuracy inside the $1–$5.5 budget zone",
        panel,
        source="synthetic eval",
    )
    assert exp.ship is True
    assert exp.issues == []
    with exp.theme.rc_context(exp.spec):
        aud = audit_figure(exp.fig)
    assert aud["overlaps"] == []
    assert aud["struck"] == []
    assert aud["text_faults"] == []

    png = tmp_path / "relate_regions_callouts.png"
    exp.save(png)
    reloaded = fm.load(png)
    assert reloaded.ship is True
    assert reloaded.issues == []
    assert reloaded.to_spec()["panels"][0]["regions"] == spec["regions"]
    assert reloaded.to_spec()["panels"][0]["callouts"] == spec["callouts"]


def test_relate_grouped_and_log_x_with_regions_callouts() -> None:
    exp = fm.explain(
        "Grouped log-x scatter places regions and callouts cleanly",
        fm.relate(
            [1, 3, 10, 30, 2, 6, 20, 60],
            [20, 35, 55, 72, 28, 46, 68, 84],
            x_label="Compute (FLOPs)",
            y_label="Score (%)",
            groups=["Dense", "Dense", "Dense", "Dense", "MoE", "MoE", "MoE", "MoE"],
            fit=True,
            log_x=True,
            regions=[(5, 25, "Mid regime")],
            callouts=[(20, 68, "MoE inflection")],
        ),
        source="synthetic",
    )
    assert exp.ship is True
    assert exp.issues == []


def test_callouts_and_regions_validation_errors() -> None:
    xs = [1, 2, 3, 4, 5]
    ys = [10, 20, 30, 40, 50]

    # Too many callouts (> 4)
    too_many = [(1, 10, "a"), (2, 20, "b"), (3, 30, "c"), (4, 40, "d"), (5, 50, "e")]
    with pytest.raises(ExplainError, match="at most 4"):
        fm.trend(xs, ys, callouts=too_many)
    with pytest.raises(ExplainError, match="at most 4"):
        fm.relate(xs, ys, x_label="x", y_label="y", callouts=too_many)

    # Inverted region x0 >= x1
    with pytest.raises(ExplainError, match="strictly less"):
        fm.trend(xs, ys, regions=[(4, 2, "bad")])
    with pytest.raises(ExplainError, match="strictly less"):
        fm.relate(xs, ys, x_label="x", y_label="y", regions=[(4, 4, "bad")])

    # Empty callout note
    with pytest.raises(ExplainError, match="empty note"):
        fm.trend(xs, ys, callouts=[(2, 20, "   ")])
    with pytest.raises(ExplainError, match="empty note"):
        fm.relate(xs, ys, x_label="x", y_label="y", callouts=[(2, 20, "")])

    # Non-positive on log axis
    with pytest.raises(ExplainError, match="positive"):
        fm.trend(xs, ys, log_x=True, regions=[(0, 3, "bad")])
    with pytest.raises(ExplainError, match="positive"):
        fm.relate(xs, ys, x_label="x", y_label="y", log_x=True, regions=[(0, 3, "bad")])
    with pytest.raises(ExplainError, match="positive"):
        fm.relate(xs, ys, x_label="x", y_label="y", log_y=True, callouts=[(2, -1, "bad")])

    # Default specs omit regions and callouts
    t_plain = fm.trend(xs, ys, label="Metric")
    assert "regions" not in t_plain.to_spec()
    assert "callouts" not in t_plain.to_spec()
    r_plain = fm.relate(xs, ys, x_label="x", y_label="y")
    assert "regions" not in r_plain.to_spec()
    assert "callouts" not in r_plain.to_spec()


def test_callout_leader_arrows_avoid_lines_labels_and_bottom_spine() -> None:
    """Regression test: callout arrows must not cross unrelated lines/labels or sit on bottom spine."""
    from figmint._explain.relate import _relate_arrow_segment, _relate_line_paths
    from figmint._explain.trend import _audit_line_paths, _callout_arrow_segment

    exp = fm.explain(
        "Throughput doubled after the Q2 kernel rewrite while staying on the Pareto frontier",
        fm.trend(
            [1, 2, 3, 4, 5, 6, 7, 8],
            {
                "v2 kernel": [48, 52, 55, 79, 96, 104, 109, 112],
                "v1 legacy": [47, 49, 50, 51, 52, 51, 53, 52],
            },
            title="Sustained gain after rollout window",
            label="Throughput",
            unit="req/s",
            x_label="Release week",
            highlight="v2 kernel",
            baseline="v1 legacy",
            regions=[(3.5, 5.5, "Kernel rollout")],
            callouts=[
                (5, 96.0, "FP8 fusion enabled"),
                (8, 112.0, "Peak 112 req/s"),
            ],
        ),
        fm.relate(
            [18, 25, 34, 48, 62, 79, 95, 112],
            [71.0, 75.8, 79.4, 83.1, 84.5, 86.0, 86.4, 87.3],
            title="Accuracy vs throughput trade-off",
            x_label="Throughput",
            y_label="Accuracy (%)",
            names=["m0", "m1", "m2", "m3", "m4", "v2-fast", "v2-pro", "v2-max"],
            highlight=["v2-fast", "v2-pro"],
            regions=[(70, 116, "Target zone")],
            callouts=[
                (48, 83.1, "Legacy prod"),
                (95, 86.4, "Best balance"),
            ],
        ),
        source="Internal serving sweep (May 2026)",
    )
    assert exp.ship is True
    assert exp.issues == []

    renderer = exp.fig.canvas.get_renderer()

    # Panel a (trend): FP8 callout must clear bottom spine and its arrow must not cross any data line
    ax_a = exp["a"]
    frame_a = ax_a.get_window_extent(renderer)
    paths_a = _audit_line_paths(ax_a)
    fp8_texts = [t for t in ax_a.texts if "FP8" in t.get_text()]
    assert len(fp8_texts) == 1
    fp8_bb = fp8_texts[0].get_window_extent(renderer)
    assert fp8_bb.y0 >= frame_a.y0 + 2.0
    ax_px, ay_px = ax_a.transData.transform((5, 96.0))
    _, _, seg_a = _callout_arrow_segment(float(ax_px), float(ay_px), fp8_bb)
    assert seg_a is None or not any(seg_a.intersects_path(p, filled=False) for p in paths_a)

    # Panel b (relate): "Best balance" arrow must not pass through "v2-pro" or "v2-fast"
    ax_b = exp["b"]
    bb_texts = [t for t in ax_b.texts if "Best" in t.get_text()]
    assert len(bb_texts) == 1
    best_bb = bb_texts[0].get_window_extent(renderer)
    other_bbs = [
        t.get_window_extent(renderer)
        for t in ax_b.texts
        if t is not bb_texts[0] and t.get_visible() and t.get_text().strip()
    ]
    bx_px, by_px = ax_b.transData.transform((95, 86.4))
    _, _, seg_b = _relate_arrow_segment(float(bx_px), float(by_px), best_bb)
    assert seg_b is None or not any(seg_b.intersects_bbox(ob, filled=True) for ob in other_bbs)
    assert seg_b is None or not any(seg_b.intersects_path(p, filled=False) for p in _relate_line_paths(ax_b))

