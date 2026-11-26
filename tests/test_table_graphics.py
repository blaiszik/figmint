"""Table-graphics: in-cell bars, dot-and-whisker intervals and sparklines on one scale per column."""

from __future__ import annotations

import re
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest
from matplotlib.patches import Rectangle

import mintfig as mint
from mintfig import terminal
from mintfig._explain.marks import MARKS_ATTR, tagged
from mintfig.interactive import _panel_data_table, _render_svg
from mintfig.terminal import audit_text_surface

ROWS = [
    {"Model": "Alpha-3", "Accuracy": 86.4, "Calibration": 0.74, "Cal lo": 0.71, "Cal hi": 0.77},
    {"Model": "Alpha-2", "Accuracy": 77.1, "Calibration": 0.69, "Cal lo": 0.65, "Cal hi": 0.73},
    {"Model": "Beta-Pro", "Accuracy": 83.2, "Calibration": 0.72, "Cal lo": 0.70, "Cal hi": 0.74},
    {"Model": "Gamma-Fast", "Accuracy": None, "Calibration": 0.61, "Cal lo": 0.55, "Cal hi": 0.67},
]
LATENCY = {
    "Alpha-3": [420, 390, 360, 340, 310, 290],
    "Alpha-2": [380, 385, 390, 388, 392, 395],
    "Beta-Pro": [510, 500, 470, 455, 440, 430],
    "Gamma-Fast": [160, 150, 152, 148, 145, 140],
}


def _scorecard(**kw: Any) -> mint.Panel:
    opts: dict[str, Any] = {
        "units": {"Accuracy": "%", "Latency": "ms"},
        "bold_best": {"Accuracy": "max", "Calibration": "max"},
        "highlight": "Alpha-3",
        "baseline": "Alpha-2",
        "sort": "-Calibration",
        "bars": "Accuracy",
        "interval": {"Calibration": ("Cal lo", "Cal hi")},
        "interval_label": "95% CI, 5 seeds",
        "spark": {"Latency": LATENCY},
        "title": "Model scorecard",
    }
    opts.update(kw)
    return mint.table(ROWS, **opts)


@pytest.fixture()
def fig() -> Any:
    exp = mint.explain(
        "Alpha-3 leads accuracy, and its calibration interval overlaps Beta-Pro's",
        _scorecard(),
        source="synthetic evals",
    )
    yield exp
    plt.close(exp.fig)


def test_scorecard_renders_clean_and_round_trips(fig: mint.Explanation) -> None:
    s = fig.summary()
    assert s["ok"] and s["ship"] and s["issues"] == []
    assert fig.min_text_px >= 11
    facts = fig.panels["a"].facts
    assert facts[0] == "4 rows × 4 columns"  # the bound columns are not shown; Latency is
    assert "Calibration: the intervals of Beta-Pro, Alpha-2 overlap that of the best row, Alpha-3" in facts
    drawn = {t.get_text() for ax in fig.fig.axes for t in ax.texts}
    assert "Cal lo" not in drawn and "Latency (ms)" in drawn and "290" in drawn
    assert "intervals: 95% CI, 5 seeds" in fig.panels["a"].measure_note
    spec = fig.to_spec()
    assert spec["panels"][0]["columns"] == ["Model", "Accuracy", "Calibration", "Cal lo", "Cal hi"]
    rebuilt = mint.load(spec)
    try:
        assert rebuilt.to_spec() == spec
        assert rebuilt.panels["a"].facts == facts
    finally:
        plt.close(rebuilt.fig)


def test_markdown_prints_numbers_only() -> None:
    md = _scorecard().to_markdown()
    assert "0.74 (0.71–0.77)" in md
    assert "Latency (ms)" in md and "290" in md and "Cal lo" not in md
    assert "—" in md  # Gamma-Fast has no accuracy
    assert not re.search(r"[█▁▂▃▄▅▆▇●├┤]", md)


def _graphics(exp: mint.Explanation) -> list[tuple[Any, dict[str, Any]]]:
    return [(a, getattr(a, MARKS_ATTR)[0][1]) for a in tagged(exp.fig) if not hasattr(a, "get_text")]


def test_bars_share_one_scale_and_negatives_draw_left_of_zero() -> None:
    exp = mint.explain(
        "Retrieval adds the most; quantisation costs 1.5 points",
        mint.table(
            [{"Change": "+Retrieval", "Delta": 8.2}, {"Change": "+Reranker", "Delta": 3.4},
             {"Change": "Quant", "Delta": -1.5}],
            bars="Delta", highlight="Quant",
        ),
    )
    try:
        bars = {rec["name"]: a for a, rec in _graphics(exp) if isinstance(a, Rectangle)}
        widths = {name: bar.get_width() for name, bar in bars.items()}
        assert widths["+Retrieval"] / widths["+Reranker"] == pytest.approx(8.2 / 3.4, rel=1e-6)
        assert widths["Quant"] / widths["+Retrieval"] == pytest.approx(1.5 / 8.2, rel=1e-6)
        zero = bars["+Retrieval"].get_x()
        assert bars["Quant"].get_x() + bars["Quant"].get_width() == pytest.approx(zero)
        assert bars["Quant"].get_facecolor() != bars["+Retrieval"].get_facecolor()
        assert exp.ship
    finally:
        plt.close(exp.fig)


def test_missing_interval_label_warns() -> None:
    panel = _scorecard(interval_label=None)
    assert [i["rule"] for i in panel.issues] == ["interval_unlabelled"]


@pytest.mark.parametrize(
    ("kw", "named"),
    [
        ({"bars": "Nope"}, "'Accuracy'"),
        ({"bars": "Model"}, "'Calibration'"),
        ({"interval": {"Accuracy": {"Delta-9": (1, 2)}}}, "'Beta-Pro'"),
        ({"interval": {"Accuracy": ("lo", "hi")}}, "'Cal lo'"),
        ({"spark": {"Trend": {"Delta-9": [1, 2]}}}, "'Gamma-Fast'"),
        ({"bars": "Accuracy", "spark": {"Accuracy": LATENCY}}, "bars="),
    ],
)
def test_invalid_names_raise_with_the_valid_ones(kw: dict[str, Any], named: str) -> None:
    with pytest.raises(mint.ExplainError) as err:
        _scorecard(**{"bars": None, "interval": None, "spark": None, "units": None, **kw})
    assert named in (err.value.fix_hint or "") + str(err.value)


def test_column_limit_counts_sparkline_columns() -> None:
    rows = [{f"c{i}": i for i in range(7)} | {"c0": "row"}]
    mint.table(rows, spark={"t1": {"row": [1, 2]}})  # 8 columns: fine
    with pytest.raises(mint.ExplainError) as err:
        mint.table(rows, spark={"t1": {"row": [1, 2]}, "t2": {"row": [2, 1]}})
    assert err.value.rule == "too_many_items"


def test_text_surface_draws_graphics_on_shared_scales(
    fig: mint.Explanation, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = fig.to_text()
    assert audit_text_surface(fig) == []
    assert max(len(line) for line in text.splitlines()) <= 72
    assert "0.74 (0.71–0.77)" in text and "intervals: 95% CI, 5 seeds" in text
    assert re.search(r"86\.4 █+", text) and "●" in text
    assert re.search(r"[▁▂▃▄▅▆▇█]{6} +290", text)
    assert fig.to_text(ascii_only=True).isascii()

    original = terminal._cell_bar
    monkeypatch.setattr(  # each row on its own scale: every bar full
        terminal, "_cell_bar", lambda v, lo, hi, w, ascii_only: original(v, 0, v or 1, w, ascii_only=ascii_only)
    )
    assert [i["rule"] for i in audit_text_surface(fig)] == ["text_table_scale"]


def test_html_tags_graphic_cells_with_their_data(fig: mint.Explanation) -> None:
    _svg, data = _render_svg(fig)
    cal = [rec for rec in data.values() if rec.get("x") == "Calibration" and rec["name"] == "Alpha-3"]
    assert cal and all(rec["lo"] == 0.71 and rec["hi"] == 0.77 for rec in cal)
    assert any(rec.get("x") == "Latency" and rec["value"] == 290 for rec in data.values())
    headers, rows, _flags, _note = _panel_data_table(fig.panels["a"])
    assert {"Cal lo", "Cal hi"} <= set(headers)

    per_row = mint.table(ROWS, columns=["Model", "Calibration"],
                         interval={"Calibration": {"Alpha-3": (0.71, 0.77)}}, interval_label="95% CI")
    headers, rows, _flags, _note = _panel_data_table(per_row)
    assert headers == ["Model", "Calibration", "Calibration low", "Calibration high"]
    assert rows[0][2:] == ["0.71", "0.77"] and rows[1][2:] == ["—", "—"]


def test_baseline_difference_of_a_percent_column_is_in_points() -> None:
    panel = _scorecard(bars=None, interval=None, spark=None, units={"Accuracy": "%"})
    assert "Accuracy: Alpha-3 vs Alpha-2 is +9.3 points" in panel.facts
