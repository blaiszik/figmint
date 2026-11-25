"""Message-first chat figures: mint.explain, its forms, rules, JSON spec and CLI."""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import matplotlib as mpl
import numpy as np
import pytest
from matplotlib.colors import to_rgb
from matplotlib.patches import Rectangle
from matplotlib.text import Text

import mintfig as mint
from mintfig import explainer
from mintfig.cli import main as cli_main
from mintfig.palettes import simulate_cvd

SERVICES = {"checkout": 1840, "search": 460, "auth": 310, "catalog": 280, "cart": 240}
WEEKS = list(range(1, 9))
LATENCY = {
    "checkout": [540, 560, 550, 570, 980, 1400, 1700, 1840],
    "search": [450, 470, 455, 465, 460, 450, 470, 460],
    "auth": [300, 310, 305, 315, 300, 320, 305, 310],
}
TAKEAWAY = "Checkout is the slow service: its p99 is 4x the next worst"


def _rng() -> np.random.Generator:
    return np.random.default_rng(7)


def _all_forms() -> dict[str, mint.Panel]:
    rng = _rng()
    return {
        "compare": mint.compare(SERVICES, label="p99 latency", unit="ms", highlight="checkout"),
        "compare_error": mint.compare(
            {"control": 4.1, "B": 5.2},
            error={"control": (3.8, 4.4), "B": (4.7, 5.7)},
            error_label="95% CI",
            unit="%",
            highlight="B",
        ),
        "share": mint.share(
            {f"stage {i}": v for i, v in enumerate([400, 380, 160, 60, 50, 40, 30, 9, 7])}
        ),
        "trend": mint.trend(WEEKS, LATENCY, unit="ms", x_label="Week", events={4: "v2.3"}),
        "trend_dates": mint.trend(
            ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"],
            {"A": [1, 2, 3, 5], "B": [2, 2, 2, 2]},
            band={"A": ([0.5, 1.5, 2.5, 4], [1.5, 2.5, 3.5, 6])},
            band_label="80% interval",
            reference=(3, "target"),
            label="Active teams",
            unit="thousands",
        ),
        "trend_highlight": mint.trend(
            WEEKS,
            {f"s{i}": rng.normal(i, 1, 8).tolist() for i in range(9)},
            highlight="s3",
            label="Score",
        ),
        "trend_facet": mint.trend(
            WEEKS,
            {f"s{i}": rng.normal(i, 1, 8).tolist() for i in range(6)},
            facet=True,
            label="Score",
        ),
        "change": mint.change(
            {"a": 10, "b": 30, "c": 55}, {"a": 40, "b": 28, "c": 60}, highlight="a", unit="%"
        ),
        "distribution": mint.distribution(
            {"before": rng.lognormal(3, 0.2, 60), "after": rng.lognormal(3.4, 0.5, 60)},
            unit="ms",
            highlight="after",
            reference=(40, "SLO"),
        ),
        "relate": mint.relate(
            np.arange(1.0, 31.0),
            np.arange(1.0, 31.0) * 3 + rng.normal(0, 4, 30),
            x_label="Batch size",
            y_label="Throughput (req/s)",
            names=[f"run{i}" for i in range(30)],
            highlight="run4",
            fit=True,
        ),
        "matrix": mint.matrix(
            rng.uniform(20, 95, (4, 5)).round(0).tolist(),
            rows=["Python", "Go", "Rust", "Java"],
            cols=["bugfix", "refactor", "tests", "docs", "perf"],
            unit="%",
            highlight=[("Rust", "perf")],
        ),
    }


@pytest.mark.parametrize("name", list(_all_forms()))
def test_every_form_renders_clean_at_chat_size(name: str) -> None:
    result = mint.explain(TAKEAWAY, _all_forms()[name], source="synthetic")
    summary = result.summary()
    assert summary["issues"] == []
    assert summary["ok"] is True
    assert result.width_mm == pytest.approx(140.0, abs=0.01)
    assert summary["display"]["min_text_px"] >= explainer.MIN_TEXT_PX
    assert summary["panels"][0]["facts"] or name == "custom"
    assert summary["alt_text"].startswith(TAKEAWAY)


def test_multi_panel_figure_is_clean_and_lettered() -> None:
    forms = _all_forms()
    result = mint.explain(
        TAKEAWAY,
        mint.compare(SERVICES, title="It stands alone", unit="ms", highlight="checkout"),
        mint.trend(
            WEEKS, LATENCY, title="It regressed at the deploy", unit="ms", highlight="checkout"
        ),
        forms["distribution"],
        forms["share"],
        source="synthetic",
    )
    assert result.summary()["issues"] == []
    assert list(result.panels) == ["a", "b", "c", "d"]
    assert result.layout == [["a", "b"], ["c", "d"]]
    letters = [t.get_text() for t in result.fig.texts if getattr(t, "_mintfig_panel_label", False)]
    assert letters == ["a", "b", "c", "d"]
    assert result.height_mm <= result.spec.max_height_mm


def test_png_is_1400_px_wide_and_explain_leaves_rcparams_alone(tmp_path: Path) -> None:
    before = dict(mpl.rcParams)
    result = mint.explain(TAKEAWAY, mint.compare(SERVICES, unit="ms"), out=tmp_path / "fig.png")
    assert dict(mpl.rcParams) == before
    from PIL import Image

    with Image.open(tmp_path / "fig.png") as image:
        assert image.width == 1400
    assert result.summary()["size_px"][0] == 1400
    assert result.summary()["path"] == str((tmp_path / "fig.png").resolve())
    assert json.loads(str(result.summary()))["takeaway"] == TAKEAWAY


# --------------------------------------------------------------------------- #
# Rules applied by construction
# --------------------------------------------------------------------------- #


def _bars(result: mint.Explanation, key: str = "a") -> list[Rectangle]:
    return [p for p in result[key].patches if isinstance(p, Rectangle)]


def test_compare_sorts_descending_starts_at_zero_and_colours_only_the_highlight() -> None:
    shuffled = {"auth": 310, "checkout": 1840, "cart": 240, "search": 460}
    result = mint.explain(TAKEAWAY, mint.compare(shuffled, unit="ms", highlight="checkout"))
    ax = result["a"]
    assert [t.get_text() for t in ax.get_yticklabels()] == ["checkout", "search", "auth", "cart"]
    assert ax.get_xlim()[0] == 0.0
    colours = {tuple(np.round(bar.get_facecolor()[:3], 3)) for bar in _bars(result)}
    assert len(colours) == 2  # one accent, one neutral grey
    assert not ax.xaxis.get_visible()  # values are written on the bars instead


def test_compare_keeps_given_order_when_sort_is_off() -> None:
    result = mint.explain(TAKEAWAY, mint.compare({"18-24": 3, "25-34": 9, "35-44": 5}, sort=False))
    assert [t.get_text() for t in result["a"].get_yticklabels()] == ["18-24", "25-34", "35-44"]


def test_intervals_are_drawn_as_dots_not_bars() -> None:
    result = mint.explain(TAKEAWAY, _all_forms()["compare_error"])
    assert _bars(result) == []


def test_trend_never_colours_more_than_four_series() -> None:
    many = {f"s{i}": [1, 2, 3] for i in range(5)}
    with pytest.raises(mint.ExplainError) as err:
        mint.trend([1, 2, 3], many)
    assert err.value.rule == "too_many_series"
    assert "highlight" in err.value.fix_hint and "facet" in err.value.fix_hint
    mint.trend([1, 2, 3], many, highlight="s1")
    mint.trend([1, 2, 3], many, facet=True)


def test_trend_uses_direct_labels_and_no_legend() -> None:
    result = mint.explain(TAKEAWAY, mint.trend(WEEKS, LATENCY, unit="ms", highlight="checkout"))
    ax = result["a"]
    assert ax.get_legend() is None
    notes = [t.get_text() for t in ax.texts]
    assert "checkout  1,840" in notes and "search" in notes
    assert not ax.get_ylabel()  # the measure is named horizontally above the plot


def test_small_multiples_share_one_scale_and_plot_width() -> None:
    result = mint.explain(TAKEAWAY, _all_forms()["trend_facet"])
    facets = [ax for ax in result.fig.axes if ax.get_title(loc="left")]
    assert len(facets) == 6
    assert len({tuple(np.round(ax.get_ylim(), 6)) for ax in facets}) == 1
    widths = [ax.get_position().width for ax in facets]
    assert max(widths) - min(widths) < 1e-6


@pytest.mark.parametrize(
    ("build", "rule"),
    [
        (
            lambda: mint.compare(SERVICES, highlight=["checkout", "search", "auth", "cart"]),
            "too_many_highlights",
        ),
        (lambda: mint.compare({f"i{i}": i for i in range(21)}), "too_many_items"),
        (lambda: mint.compare(SERVICES, highlight="chekout"), "explain_spec"),
        (lambda: mint.compare({"a": 1.0, "b": float("nan")}), "explain_spec"),
        (lambda: mint.compare({"a": "12"}), "explain_spec"),
        (lambda: mint.share({"a": 3, "b": -1}), "explain_spec"),
        (lambda: mint.change({"a": 1}, {"b": 2}), "explain_spec"),
        (lambda: mint.distribution({"a": [1.0, 2.0]}), "explain_spec"),
        (lambda: mint.relate([1, 2, 3], [1, 2, 3], x_label="", y_label="y"), "explain_spec"),
        (lambda: mint.trend([1, 2, 3], {"a": [1, 2]}), "explain_spec"),
        (lambda: mint.explain("", mint.compare(SERVICES)), "takeaway_missing"),
        (lambda: mint.explain("word " * 60, mint.compare(SERVICES)), "takeaway_too_long"),
        (lambda: mint.explain(TAKEAWAY, *[mint.compare(SERVICES)] * 7), "too_many_panels"),
        (lambda: mint.explain(TAKEAWAY), "explain_spec"),
    ],
)
def test_rule_violations_raise_with_a_fix_hint(build, rule: str) -> None:
    with pytest.raises(mint.ExplainError) as err:
        build()
    assert err.value.rule == rule
    assert err.value.fix_hint
    assert "Fix:" in str(err.value)


def test_matrix_refuses_cells_too_small_to_read() -> None:
    wide = mint.matrix(
        np.full((3, 12), 1234.5).tolist(), rows=list("abc"), cols=[f"c{i}" for i in range(12)]
    )
    with pytest.raises(mint.ExplainError) as err:
        mint.explain(TAKEAWAY, wide, mint.compare(SERVICES))
    assert err.value.rule == "matrix_cells_too_small"
    assert "Panel a" in err.value.message


def test_soft_rules_surface_as_warnings_not_errors() -> None:
    topic = mint.explain(
        "Latency by service", mint.compare({"a": 100.0, "b": 101.0, "c": 99.5}, unit="ms")
    )
    rules = {issue["rule"]: issue for issue in topic.issues}
    assert set(rules) == {"takeaway_is_a_topic", "differences_invisible"}
    assert all(issue["severity"] == "warning" and issue["fix_hint"] for issue in topic.issues)
    assert rules["differences_invisible"]["panel"] == "a"
    assert topic.ok is True

    rng = _rng()
    weak = mint.relate(rng.normal(size=40), rng.normal(size=40), x_label="x", y_label="y", fit=True)
    assert [i["rule"] for i in mint.explain(TAKEAWAY, weak).issues] == ["fit_on_weak_relationship"]


def test_a_conclusion_with_a_number_is_not_mistaken_for_a_topic() -> None:
    assert (
        mint.explain(
            "Plan B beat Plan A by 26 points vs last year", mint.compare(SERVICES, unit="ms")
        ).issues
        == []
    )


def test_long_item_names_wrap_and_truncation_is_reported() -> None:
    names = {
        "payments end-to-end regression suite for the checkout flow": 212,
        "notification_delivery_pipeline_contract_tests_nightly": 28,
        "auth": 31,
    }
    result = mint.explain(TAKEAWAY, mint.compare(names, unit="reruns"), mint.compare(SERVICES, unit="ms"))
    shown = [t.get_text() for t in result["a"].get_yticklabels()]
    assert any("\n" in text for text in shown)
    assert [i["rule"] for i in result.issues] == ["names_truncated"]
    assert result.issues[0]["panel"] == "a"


def test_dollar_signs_are_text_not_mathtext() -> None:
    result = mint.explain(
        "Revenue grew from $5M to $8M in a year", mint.compare({"2025": 5.0, "2026": 8.0}, unit="$")
    )
    title = result.fig.texts[0]
    assert title.get_text() == r"Revenue grew from \$5M to \$8M in a year"
    assert "$8" in next(t.get_text().replace("\\", "") for t in result["a"].texts)
    assert result.issues == []


def test_number_formatting_is_consistent_within_a_set() -> None:
    fmt = explainer._formatter
    assert [fmt([1840, 460])(v) for v in (1840, 460)] == ["1,840", "460"]
    assert [fmt([12.5, 3.0])(v) for v in (12.5, 3.0)] == ["12.5", "3.0"]
    assert fmt([2_500_000, 900_000])(2_500_000) == "2.5M"
    assert fmt([-3.2, 1.0])(-3.2) == "\N{MINUS SIGN}3.2"
    assert fmt([0.0], "{:+.2f}")(-0.0) == "0.00"  # never a signed zero
    assert fmt([0.001], "{:+.2f}")(-0.001) == "\N{MINUS SIGN}0.001"  # never a non-zero as 0
    assert explainer._with_unit("12", "%") == "12%"
    assert explainer._with_unit("12", "ms") == "12 ms"
    assert explainer._with_unit("\N{MINUS SIGN}5", "$") == "\N{MINUS SIGN}$5"


def test_series_palette_separates_in_grayscale_and_colour_blindness() -> None:
    rgb = np.array([to_rgb(c) for c in explainer.SERIES_COLORS])[np.newaxis]
    gray = simulate_cvd(rgb, "grayscale")[0, :, 0]
    deutan = simulate_cvd(rgb, "deuteranopia")[0]
    protan = simulate_cvd(rgb, "protanopia")[0]
    for i, j in itertools.combinations(range(len(explainer.SERIES_COLORS)), 2):
        assert abs(gray[i] - gray[j]) >= 0.05
        assert (
            min(np.linalg.norm(deutan[i] - deutan[j]), np.linalg.norm(protan[i] - protan[j]))
            >= 0.12
        )
    assert set(explainer.ACCENT_COLORS) <= set(explainer.SERIES_COLORS)


def test_facts_report_the_numbers_a_takeaway_would_claim() -> None:
    facts = mint.compare(SERVICES, unit="ms", highlight="checkout").facts
    assert "highest: checkout 1,840 ms" in facts
    assert any("4.0\N{MULTIPLICATION SIGN} the next highest (search 460 ms)" in f for f in facts)
    trend_facts = mint.trend(WEEKS, LATENCY, unit="ms", highlight="checkout").facts
    assert trend_facts == [
        "checkout: 540 ms \N{RIGHTWARDS ARROW} 1,840 ms from 1 to 8 (+241%); peak 1,840 ms at 8",
        "the other 2 change by +2.2% to +3.3% from first to last value",
    ]
    share_facts = mint.share({"a": 50, "b": 30, "c": 20}).facts
    assert "top 3 together: 100%" in share_facts


def test_layout_can_be_given_and_is_validated() -> None:
    panels = [mint.compare(SERVICES), mint.compare(SERVICES), mint.compare(SERVICES)]
    assert mint.explain(TAKEAWAY, *panels).layout == [["a", "a"], ["b", "c"]]
    stacked = mint.explain(TAKEAWAY, *panels[:2], layout=[["a"], ["b"]])
    assert stacked["a"].get_position().y0 > stacked["b"].get_position().y1
    with pytest.raises(mint.ExplainError):
        mint.explain(TAKEAWAY, *panels[:2], layout=[["a"], ["a", "b"]])
    with pytest.raises(mint.ExplainError):
        mint.explain(TAKEAWAY, *panels[:2], layout=[["a"]])


def test_wider_canvas_is_flagged_because_chat_scales_it_back_down() -> None:
    result = mint.explain(TAKEAWAY, mint.compare(SERVICES, unit="ms"), width="wide")
    assert [i["rule"] for i in result.issues] == ["small_at_chat_size"]


def test_no_text_is_rotated() -> None:
    result = mint.explain(TAKEAWAY, *list(_all_forms().values())[:6])
    rotated = [
        t.get_text()
        for t in result.fig.findobj(Text)
        if t.get_visible() and t.get_text().strip() and t.get_rotation() not in (0.0, 360.0)
    ]
    assert rotated == []


# --------------------------------------------------------------------------- #
# JSON spec, CLI and runner
# --------------------------------------------------------------------------- #


def test_spec_round_trip_reproduces_the_same_pixels(tmp_path: Path) -> None:
    forms = _all_forms()
    original = mint.explain(
        TAKEAWAY,
        forms["trend_dates"],
        forms["compare"],
        forms["change"],
        forms["matrix"],
        subtitle="Week of 16 Nov",
        note="Synthetic.",
        source="tests",
    )
    original.save(tmp_path / "one.png", write_spec=True)
    spec = json.loads((tmp_path / "one.json").read_text("utf-8"))
    assert spec["takeaway"] == TAKEAWAY and len(spec["panels"]) == 4
    mint.explain_from_spec(spec, out=tmp_path / "two.png")
    assert (tmp_path / "one.png").read_bytes() == (tmp_path / "two.png").read_bytes()


def test_spec_errors_name_the_valid_choices() -> None:
    with pytest.raises(mint.ExplainError, match="compare, trend, change"):
        mint.explain_from_spec({"takeaway": TAKEAWAY, "panels": [{"kind": "pie"}]})
    with pytest.raises(mint.ExplainError, match="'values'"):
        mint.explain_from_spec({"takeaway": TAKEAWAY, "panels": [{"kind": "compare"}]})
    with pytest.raises(mint.ExplainError, match="unexpected keyword"):
        mint.panel_from_spec({"kind": "compare", "values": {"a": 1}, "colour": "red"})
    with pytest.raises(mint.ExplainError, match="Unknown top-level"):
        mint.explain_from_spec(
            {
                "takeaway": TAKEAWAY,
                "panels": [{"kind": "compare", "values": {"a": 1}}],
                "theme": "x",
            }
        )


def test_cli_explain_example_renders_and_rejects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_main(["explain", "--example"]) == 0
    example = capsys.readouterr().out
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(example, encoding="utf-8")

    assert cli_main(["explain", str(spec_path), "--out", str(tmp_path / "fig.png")]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["ok"] is True and summary["issues"] == []
    assert Path(summary["path"]).exists()
    assert [p["kind"] for p in summary["panels"]] == ["compare", "trend"]

    spec_path.write_text('{"takeaway": "x", "panels": [{"kind": "pie"}]}', encoding="utf-8")
    assert cli_main(["explain", str(spec_path), "--out", str(tmp_path / "bad.png")]) == 2
    rejected = json.loads(capsys.readouterr().out)
    assert rejected["ok"] is False and rejected["stage"] == "spec" and rejected["fix_hint"]
    assert not (tmp_path / "bad.png").exists()

    spec_path.write_text("{not json", encoding="utf-8")
    assert cli_main(["explain", str(spec_path), "--out", str(tmp_path / "bad.png")]) == 2
    assert cli_main(["explain"]) == 2


def test_mintfig_run_accepts_a_script_that_returns_an_explanation(tmp_path: Path) -> None:
    script = tmp_path / "plot.py"
    script.write_text(
        "import mintfig as mint\n"
        "def build():\n"
        "    return mint.explain('Checkout p99 is 4x the next worst service',\n"
        "        mint.compare({'checkout': 1840, 'search': 460}, unit='ms', highlight='checkout'))\n",
        encoding="utf-8",
    )
    # The runner restores the backend name with different capitalisation; compare the rest.
    before = {k: v for k, v in mpl.rcParams.items() if k != "backend"}
    result = mint.run_script(script, journal="screen", bundle_dir=tmp_path / "out")
    assert {k: v for k, v in mpl.rcParams.items() if k != "backend"} == before
    assert result.ok and result.exit_code == 0
    assert result.report is not None and not result.report.issues
    assert (tmp_path / "out" / "figure.pdf").exists()


def test_hidden_axis_is_not_reported_as_an_unlabeled_scale() -> None:
    """Regression: tick labels of a hidden axis are never drawn but still report visible."""
    fig, ax = mint.figure("screen", width="chat", height_mm=50)
    ax.barh(["a", "b"], [3, 1])
    ax.xaxis.set_visible(False)
    report = mint.preflight_figure(fig, "screen")
    assert "clarity_metadata" not in {issue.rule for issue in report.issues}


def test_a_panel_that_does_not_name_its_measure_is_flagged() -> None:
    result = mint.explain(TAKEAWAY, mint.trend(WEEKS, LATENCY, highlight="checkout"))
    assert [(i["rule"], i["panel"]) for i in result.issues] == [("measure_unnamed", "a")]
    assert "label=" in result.issues[0]["fix_hint"]
