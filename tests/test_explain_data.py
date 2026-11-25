"""mint.explain data handling: number formatting, accepted inputs, facts, scientific
arguments, self-describing PNGs (package A of the scientific review)."""

from __future__ import annotations

import dataclasses
import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest
from matplotlib.lines import Line2D

import mintfig as mint
from mintfig import explainer, specs
from mintfig.cli import main as cli_main

T = "Doping raises conductivity by three decades at 300 K"
MINUS = "\N{MINUS SIGN}"
TIMES = "\N{MULTIPLICATION SIGN}"


class FakeSeries:
    """Stand-in for a pandas Series: 1-D, iterates values, has .items()."""

    ndim = 1

    def __init__(self, data: dict) -> None:
        self._data = dict(data)

    def items(self):
        return iter(self._data.items())

    def __iter__(self):
        return iter(self._data.values())

    def __len__(self) -> int:
        return len(self._data)


class FakeFrame:
    """Stand-in for a pandas DataFrame: columns are series, .index/.columns/.to_numpy()."""

    ndim = 2

    def __init__(self, columns: dict, index: list) -> None:
        self._cols = {k: list(v) for k, v in columns.items()}
        self.index = list(index)
        self.columns = list(columns)

    def items(self):
        return ((k, FakeSeries(dict(zip(self.index, v, strict=True)))) for k, v in self._cols.items())

    def to_numpy(self) -> np.ndarray:
        return np.array([[self._cols[c][i] for c in self.columns] for i in range(len(self.index))])


def _texts(result: mint.Explanation, key: str = "a") -> list[str]:
    """Drawn text as the reader sees it (super/subscript runs are drawn as mathtext)."""
    return [explainer._reader_text(t.get_text()) for t in result[key].texts]


def _shows_zero(text: str) -> bool:
    return explainer._shows_zero(text.replace("\\", ""))


# --------------------------------------------------------------------------- #
# A1. Numbers never hide magnitude
# --------------------------------------------------------------------------- #


def test_tiny_values_use_scientific_notation_never_zero() -> None:
    panel = mint.compare(
        {"A": 2.1e-9, "B": 3.4e-9, "C": 1.3e-7}, unit="A", label="Leakage", highlight="C"
    )
    assert f"highest: C 1.3{TIMES}10⁻⁷ A" in panel.facts
    result = mint.explain(T, panel)
    labels = _texts(result)
    assert f"1.3{TIMES}10⁻⁷ A" in labels and f"2.1{TIMES}10⁻⁹" in labels
    assert not any(_shows_zero(t) for t in labels)
    assert "e-0" not in " ".join(panel.facts)


@pytest.mark.parametrize(
    ("values", "unit", "expected"),
    [
        ([3.2e15, 5.1e15, 9e14], "cm⁻³", [f"3.2{TIMES}10¹⁵", f"5.1{TIMES}10¹⁵", f"9.0{TIMES}10¹⁴"]),
        ([2_500_000, 900_000], None, ["2.5M", "0.9M"]),
        ([2_500_000, 900_000], "$", ["2.5M", "0.9M"]),
        ([2_500_000, 900_000], "ms", [f"2.5{TIMES}10⁶", f"9.0{TIMES}10⁵"]),
        ([900_000, 450_000], "ms", ["900,000", "450,000"]),
        ([1200.5, 0.004, 35.2], "s⁻¹", ["1,200", "0.004", "35.2"]),
        ([1840, 460], "ms", ["1,840", "460"]),
        ([82, 41, 3], "%", ["82", "41", "3"]),
        ([0.74, 0.69], None, ["0.74", "0.69"]),
        ([0.82, 0.0082], None, ["0.820", "0.008"]),
    ],
)
def test_formatter_keeps_magnitude(values, unit, expected) -> None:
    fmt = explainer._formatter(values, unit=unit)
    assert [fmt(v) for v in values] == expected
    assert "B" not in "".join(fmt(v) for v in values) or unit in (None, "$")


def test_formatter_log_and_mixed_sets_give_each_value_its_own_digits() -> None:
    fmt = explainer._formatter([1e-11, 2e-10, 1.3e-7, 0.5], log=True)
    assert fmt(1.3e-7) == f"1.3{TIMES}10⁻⁷"
    # On a log axis one notation for the set (0.5 joins the scientific values), with
    # one number of significant figures across the set (package E, item 7).
    assert fmt(0.5) == f"5.0{TIMES}10⁻¹"
    mixed = explainer._formatter([1e-11, 2e-10, 1.3e-7, 0.5])
    assert mixed(1.3e-7) == f"1.3{TIMES}10⁻⁷"
    assert mixed(0.5) == "0.5"
    plain_log = explainer._formatter([0.002, 0.5, 30.0], log=True)
    assert plain_log(0.002) == "0.002" and plain_log(30.0) == "30"


@pytest.mark.parametrize("spec", [".2f", "{:.2f}"])
def test_fmt_accepts_spec_and_template(spec: str) -> None:
    panel = mint.compare({"a": 0.1234, "b": 0.5678}, fmt=spec, label="x")
    assert "highest: b 0.57" in panel.facts
    result = mint.explain(T, panel)
    assert ".2f" not in " ".join(_texts(result))


def test_fmt_percent_spec() -> None:
    assert "highest: b 56.8%" in mint.compare({"a": 0.1234, "b": 0.5678}, fmt=".1%").facts


@pytest.mark.parametrize("bad", ["", "abc", "{x}", 5])
def test_unusable_fmt_is_rejected_with_both_shapes_in_the_hint(bad) -> None:
    with pytest.raises(mint.ExplainError) as err:
        mint.compare({"a": 1.0}, fmt=bad)
    assert ".2f" in err.value.fix_hint and "{:.2f}" in err.value.fix_hint


def test_fmt_never_prints_a_nonzero_as_zero_nor_a_signed_zero() -> None:
    fmt = explainer._formatter([0.0], ".1f")
    assert fmt(-0.0) == "0.0"
    assert fmt(-0.004) == f"{MINUS}0.004"
    auto = explainer._formatter([5.0, -0.0])
    assert auto(-0.0) == "0"
    result = mint.explain(T, mint.change({"a": 0.01, "b": 1.0}, {"a": -0.004, "b": 1.2}, fmt=".1f"))
    for text in _texts(result):
        assert not re.search(f"{MINUS}0(\\.0+)?(?![.0-9])", text), text


def test_trend_end_labels_use_three_significant_figures() -> None:
    steps = list(range(0, 2001, 100))
    curve = [0.82 * (1 - np.exp(-s / 300)) + 0.0001 for s in steps]
    result = mint.explain(T, mint.trend(steps, {"full": curve}, label="Accuracy"))
    label = next(t for t in _texts(result) if t.startswith("full"))
    assert label == "full  0.819"  # three significant figures, not "0.8191"


def test_log_trend_facts_state_decades_and_x_is_rounded() -> None:
    panel = mint.trend(
        [2.5, 2.8, 3.0303, 3.3, 3.6],
        {"2 at.%": [1e-2, 4e-3, 2e-3, 8e-4, 3e-4]},
        log=True,
        label="σ",
        unit="S/cm",
    )
    fact = panel.facts[0]
    assert "falls 33-fold, 1.5 decades" in fact and "%" not in fact.split("(")[1]
    assert f"3{TIMES}10⁻⁴ S/cm" in fact
    rounded = mint.trend([1.0, 3.0303, 5.0], {"a": [1, 5, 2]}, label="y").facts[0]
    assert "peak 5 at 3.03" in rounded


# --------------------------------------------------------------------------- #
# A2. Inputs scientists have
# --------------------------------------------------------------------------- #


def test_mapping_like_objects_and_numpy_scalars_are_accepted() -> None:
    series = FakeSeries({"a": np.float32(3.0), "b": np.int64(5), "c": np.array(9.0)})
    panel = mint.compare(series, label="Yield", unit="%")
    assert panel.facts[0] == "highest: c 9%"
    json.dumps(mint.explain(T, panel).to_spec(), allow_nan=False)


def test_dataframe_like_inputs_for_trend_and_matrix() -> None:
    frame = FakeFrame({"a": [1.0, 2, 3, 4], "b": [2.0, 2, 2, 3]}, index=[1, 2, 3, 4])
    result = mint.explain(T, mint.trend([1, 2, 3, 4], frame, label="y"))
    assert list(result.panels["a"].to_spec()["series"]) == ["a", "b"]
    grid = FakeFrame({"p": [1.0, 2.0], "q": [3.0, 4.0]}, index=["x", "y"])
    panel = mint.matrix(grid, label="z")
    assert panel.spec["rows"] == ["x", "y"] and panel.spec["cols"] == ["p", "q"]
    with pytest.raises(mint.ExplainError, match="rows= and cols="):
        mint.matrix([[1, 2], [3, 4]])


@pytest.mark.parametrize(
    ("error", "mode"),
    [
        (0.2, "\N{PLUS-MINUS SIGN} half-widths"),
        ({"a": 0.2, "b": 0.3}, "\N{PLUS-MINUS SIGN} half-widths"),
        ({"a": (2.8, 3.2), "b": (4.6, 5.4)}, "absolute bounds (low, high)"),
        ({"a": (2.8, 3.2), "b": 0.3}, "for some items"),
        ([0.2, 0.3], "\N{PLUS-MINUS SIGN} half-widths"),
    ],
)
def test_compare_error_forms_and_the_reading_is_stated(error, mode: str) -> None:
    panel = mint.compare({"a": 3.0, "b": 5.0}, error=error, error_label="95% CI", label="y")
    assert any(mode in fact for fact in panel.facts)
    result = mint.explain(T, panel)
    assert result.issues == []
    measure = [t.get_text() for t in result.fig.texts if "95% CI" in t.get_text()]
    assert measure, "error_label belongs in the measure line"


def test_unlabelled_interval_is_a_warning_with_an_actionable_hint() -> None:
    result = mint.explain(T, mint.compare({"a": 3.0, "b": 5.0}, error=0.2, label="y"))
    issue = next(i for i in result.issues if i["rule"] == "interval_unlabelled")
    assert issue["severity"] == "warning" and "error_label=" in issue["fix_hint"]
    band = mint.explain(T, mint.trend([1, 2, 3], {"a": [1, 2, 3]}, band={"a": 0.1}, label="y"))
    assert "band_label=" in band.issues[0]["fix_hint"]


@pytest.mark.parametrize(
    "band",
    [
        {"a": ([0.5, 3.0, 4.0], [1.5, 5.0, 6.0])},
        {"a": [0.5, 1.0, 1.0]},
        {"a": 0.5},
        ([0.5, 3.0, 4.0], [1.5, 5.0, 6.0]),
        [0.5, 1.0, 1.0],
        0.5,
    ],
)
def test_trend_band_forms(band) -> None:
    result = mint.explain(
        T, mint.trend([1, 2, 3], {"a": [1, 4, 5]}, band=band, band_label="95% CI", label="y")
    )
    assert result.issues == []
    assert any(f.startswith("bands read as") for f in result.panels["a"].facts)


def test_trend_band_errors_are_explain_errors() -> None:
    with pytest.raises(mint.ExplainError, match="bracket"):
        mint.trend([1, 2, 3], {"a": [1, 4, 5]}, band={"a": ([0.1, 0.1, 0.1], [0.2, 0.2, 0.2])})
    with pytest.raises(mint.ExplainError, match="map series names"):
        mint.trend([1, 2, 3], {"a": [1, 4, 5], "b": [1, 2, 3]}, band=0.5)


def test_numeric_x_is_sorted_with_its_series_and_repeats_are_refused() -> None:
    panel = mint.trend([3, 1, 2], {"a": [30, 10, 20]}, band={"a": [3, 1, 2]}, label="y")
    assert panel.spec["x"] == [1, 2, 3] and panel.spec["series"]["a"] == [10, 20, 30]
    assert panel.spec["band"]["a"] == [1, 2, 3]
    assert panel.facts[0].startswith("a: 10 \N{RIGHTWARDS ARROW} 30 from 1 to 3")
    with pytest.raises(mint.ExplainError) as err:
        mint.trend([1, 1, 2], {"a": [3, 1, 2]})
    assert "points=" in err.value.fix_hint and "band=" in err.value.fix_hint


@pytest.mark.parametrize("name", ["x_scale", "log_x_axis", "xscale", "x_log", "logx"])
def test_unknown_arguments_name_the_valid_ones(name: str) -> None:
    with pytest.raises(mint.ExplainError) as err:
        mint.trend([1, 2], {"a": [1, 2]}, **{name: True})
    assert err.value.rule == "unknown_argument"
    assert "log_x" in err.value.fix_hint and "Valid arguments of trend()" in err.value.fix_hint


def test_unknown_arguments_point_to_sibling_forms_and_explain() -> None:
    with pytest.raises(mint.ExplainError, match="order you give"):
        mint.distribution({"a": [1, 2, 3]}, sort=False)
    for name in ("note", "source"):
        with pytest.raises(mint.ExplainError) as err:
            mint.compare({"a": 1}, **{name: "x"})
        assert "mint.explain(" in err.value.fix_hint
    with pytest.raises(mint.ExplainError, match="note="):
        mint.explain(T, mint.compare({"a": 1}), footnote="x")
    with pytest.raises(mint.ExplainError, match="label="):
        mint.compare({"a": 1}, labels="y")
    with pytest.raises(mint.ExplainError, match="unknown_argument|keyword"):
        mint.compare({"a": 1}, "extra")


# --------------------------------------------------------------------------- #
# A3. Facts
# --------------------------------------------------------------------------- #


def test_percent_change_is_omitted_when_meaningless() -> None:
    near_zero = mint.trend([1, 2, 3], {"a": [0.0082, 0.4, 0.82]}, label="y").facts[0]
    assert "%" not in near_zero
    sign_change = mint.trend([1, 2, 3], {"a": [-0.05, 1.0, 1.85]}, label="y").facts[0]
    assert "%" not in sign_change
    points = mint.trend([1, 2, 3], {"a": [3, 50, 97]}, unit="%", label="y").facts[0]
    assert "(+94 points)" in points and "2905" not in points
    kept = mint.trend([1, 2, 3], {"a": [540, 900, 1840]}, unit="ms").facts[0]
    assert "(+241%)" in kept


def test_compare_facts_are_neutral_and_checkable() -> None:
    facts = mint.compare(
        {"a": 2e-6, "b": 3.1e-4, "c": 2.4e-3}, unit="S/cm", log=True, highlight="b"
    ).facts
    assert f"highest/lowest ratio: 1,200{TIMES} (from unrounded values)" in facts
    # On a log axis the highlight is stated as a ratio to the next item, never a signed one.
    assert any(f.startswith("b: ") and "rank 2 of 3" in f and f"0.13{TIMES} c (" in f for f in facts)
    close = mint.compare({"a": 1.0, "b": 1.05, "c": 0.5}).facts
    assert not any("the next highest" in f for f in close)
    signed = mint.compare({"a": -3.0, "b": 5.0, "c": 1.0}, unit="kJ/mol").facts
    assert any(f.startswith("range: ") for f in signed)
    asc = mint.compare({"A": 3.2, "B": 0.8, "C": 12.0}, sort="asc", highlight="B").facts
    assert any("rank 1 of 3, lowest first" in f for f in asc)
    ref = mint.compare({"a": 120, "b": 300}, highlight="b", reference=(100, "limit"), unit="N")
    assert any("+200 N vs limit (100 N)" in f for f in ref.facts)


def test_interval_overlap_is_stated_in_plain_words() -> None:
    facts = mint.compare(
        {"full model": 0.82, "no retrieval": 0.74, "no augmentation": 0.80},
        error={
            "full model": (0.80, 0.84),
            "no retrieval": (0.71, 0.77),
            "no augmentation": (0.78, 0.82),
        },
        error_label="95% CI",
        highlight="no retrieval",
    ).facts
    assert (
        "no retrieval 0.71\N{EN DASH}0.77 does not overlap full model 0.80\N{EN DASH}0.84 or "
        "no augmentation 0.78\N{EN DASH}0.82" in facts
    )
    assert not any("significant" in f for f in facts)
    no_hl = mint.compare(
        {"a": 0.82, "b": 0.80}, error={"a": (0.8, 0.84), "b": (0.78, 0.82)}, error_label="CI"
    ).facts
    assert any(f.startswith("b ") and " overlaps a " in f for f in no_hl)


def test_trend_facts_gap_crossing_and_missing() -> None:
    facts = mint.trend(
        [1, 2, 3, 4], {"a": [1, 2, 4, 6], "b": [3, 3, 3, None]}, label="y", unit="mV"
    ).facts
    assert "at 3: a is 1 mV above b" in facts
    assert "a first crosses above b at 3" in facts
    assert any("b: " in f and "1 of 4 points missing" in f for f in facts)


def test_distribution_facts_differences_small_n_and_dropped() -> None:
    facts = mint.distribution(
        {"wt": [10, 12, 11, 13, 12, 11], "ko": [6, 7, 5, float("nan")]},
        highlight="ko",
        unit="µm",
    ).facts
    assert any(f.startswith("ko \N{MINUS SIGN} wt: median") for f in facts)
    assert "n < 5 in ko (n = 3): quartiles are not meaningful" in facts
    assert any("1 missing value dropped" in f for f in facts)


def test_relate_facts_give_the_fitted_line() -> None:
    x = np.arange(1.0, 11.0)
    facts = mint.relate(x, 2 * x + 1, x_label="x", y_label="y", fit=True).facts
    assert any("fitted line: y = 2\N{MIDDLE DOT}x + 1" in f for f in facts)
    logged = mint.relate(x, 3 * x**2, x_label="x", y_label="y", fit=True, log_x=True, log_y=True)
    assert any("in log space" in f and "log₁₀(y) = 2\N{MIDDLE DOT}log₁₀(x)" in f for f in logged.facts)
    nan = mint.relate([1, 2, np.nan, 4], [2, 4, 5, 9], x_label="x", y_label="y").facts
    assert "1 point with a missing value dropped" in nan


def test_matrix_facts_off_diagonal_row_mean_and_empty_cells() -> None:
    facts = mint.matrix(
        [[50, 3, 1], [4, 40, 9], [0, 12, None]], rows=list("xyz"), cols=list("xyz")
    ).facts
    assert f"largest off-diagonal: z {TIMES} y = 12" in facts
    assert "1 of 9 cells empty (no value)" in facts
    # A constant diagonal is left out of the row means and said once (was "a (0.333").
    eye = mint.matrix(np.eye(3), rows=list("abc"), cols=list("abc")).facts
    assert "diagonal is 1 throughout (excluded)" in eye
    assert "highest row mean: a (0)" in eye


# --------------------------------------------------------------------------- #
# A4. Scientific arguments
# --------------------------------------------------------------------------- #


def test_compare_sort_options() -> None:
    values = {"A": 3.2, "B": 0.8, "C": 12.0}
    for sort, order in (("asc", ["B", "A", "C"]), ("desc", ["C", "A", "B"]), (False, list(values))):
        result = mint.explain(T, mint.compare(values, sort=sort, label="IC50"))
        assert [t.get_text() for t in result["a"].get_yticklabels()] == order
    with pytest.raises(mint.ExplainError, match="asc"):
        mint.compare(values, sort="up")


def test_trend_log_x_and_log_y_alias() -> None:
    dose = np.logspace(-2, 2, 9)
    result = mint.explain(
        "Inhibition saturates above 10 µM",
        mint.trend(dose, {"A": 100 / (1 + 1 / dose)}, log_x=True, log_y=True, label="I", unit="%"),
    )
    ax = result["a"]
    assert ax.get_xscale() == "log" and ax.get_yscale() == "log"
    assert result.issues == []
    with pytest.raises(mint.ExplainError, match="positive"):
        mint.trend([0, 1, 2], {"a": [1, 2, 3]}, log_x=True)
    with pytest.raises(mint.ExplainError, match="numeric x"):
        mint.trend(["a", "b"], {"a": [1, 2]}, log_x=True)


def test_trend_points_are_replicates_and_the_line_is_their_mean() -> None:
    reps = [[1.0, 2.0, 3.0], [2.0, 4.0], [5.0, 5.0, 5.0, 5.0]]
    panel = mint.trend([0, 1, 2], points={"a": reps}, label="OD")
    assert panel.spec["points"]["a"] == reps
    assert "a: line is the mean of n = 2\N{EN DASH}4 replicates per x" in panel.facts
    assert panel.facts[0].startswith("a: 2 \N{RIGHTWARDS ARROW} 5")
    mint.explain(T, panel)
    array = mint.trend([0, 1], {"a": [1.5, 3.5]}, points={"a": np.array([[1.0, 2.0], [3.0, 4.0]])})
    assert array.spec["series"] is None
    with pytest.raises(mint.ExplainError, match="mean of points"):
        mint.trend([0, 1], {"a": [9, 9]}, points={"a": [[1.0, 2.0], [3.0, 4.0]]})


def test_sparse_trends_mark_measurements_and_isolated_points_stay_visible() -> None:
    sparse = mint.explain(T, mint.trend([1, 2, 3, 4, 5], {"a": [1, 2, 3, 4, 5]}, label="y"))
    marked = [ln for ln in sparse["a"].lines if ln.get_label() == "_points"]
    assert marked and len(marked[0].get_xdata()) == 5
    gappy = [float(v) for v in range(20)]
    gappy[2] = gappy[4] = float("nan")
    dense = mint.explain(T, mint.trend(list(range(20)), {"a": gappy}, label="y"))
    lone = [ln for ln in dense["a"].lines if ln.get_label() == "_points"]
    assert lone and list(lone[0].get_xdata()) == [3.0]
    assert any("2 of 20 points missing" in f for f in dense.panels["a"].facts)


def test_relate_groups_are_coloured_labelled_and_fitted_per_group() -> None:
    rng = np.random.default_rng(1)
    x = rng.uniform(2, 5, 20)
    groups = ["A"] * 10 + ["B"] * 10
    y = np.where(np.arange(20) < 10, 10 * x, 20 * x)
    result = mint.explain(
        T,
        mint.relate(x, y, groups=groups, fit=True, x_label="d", y_label="E", reference=(60, "target")),
    )
    ax = result["a"]
    assert ax.get_legend() is None
    texts = _texts(result)
    assert "A" in texts and "B" in texts and "target" in texts
    assert len([ln for ln in ax.lines if ln.get_label() == "_fit"]) == 2
    facts = result.panels["a"].facts
    assert any(f.startswith("B: r = 1.00, n = 10; fitted line: y = 20") for f in facts)
    with pytest.raises(mint.ExplainError) as err:
        mint.relate([1, 2, 3, 4, 5], [1, 2, 3, 4, 5], groups=list("abcde"), x_label="x", y_label="y")
    assert err.value.rule == "too_many_series"
    highlighted = mint.explain(
        T, mint.relate(x, y, groups=groups, highlight="B", x_label="d", y_label="E")
    )
    # The grey context group keeps a direct label, in the muted colour.
    assert "B" in _texts(highlighted) and "A" in _texts(highlighted)


def test_reference_on_every_value_form() -> None:
    for panel in (
        mint.compare({"a": 1, "b": 2}, reference=(1.5, "goal")),
        mint.trend([1, 2], {"a": [1, 2]}, reference=(1.5, "goal")),
        mint.distribution({"a": [1, 2, 3]}, reference=(1.5, "goal")),
        mint.relate([1, 2, 3], [1, 2, 3], x_label="x", y_label="y", reference=(1.5, "goal")),
    ):
        assert "goal" in _texts(mint.explain(T, panel))


# --------------------------------------------------------------------------- #
# A5. Self-describing PNGs
# --------------------------------------------------------------------------- #


def _decoded(path: Path) -> np.ndarray:
    from PIL import Image

    with Image.open(path) as image:
        return np.asarray(image.convert("RGBA"))


def test_png_carries_its_spec_and_loads_back(tmp_path: Path) -> None:
    original = mint.explain(
        T,
        mint.compare({"a": 2e-6, "b": 3e-4}, log=True, label="σ", unit="S/cm"),
        mint.trend([3, 1, 2], points={"r": [[1, 2], [2, 3], [3, 4]]}, end_values=False, label="z"),
        note="synthetic",
    )
    original.save(tmp_path / "one.png")
    chunks = explainer.read_png_text(tmp_path / "one.png")
    assert set(chunks) == {"mintfig:spec", "mintfig:takeaway", "mintfig:alt_text"}
    assert chunks["mintfig:takeaway"] == T
    rebuilt = mint.load(tmp_path / "one.png")
    rebuilt.save(tmp_path / "two.png")
    assert np.array_equal(_decoded(tmp_path / "one.png"), _decoded(tmp_path / "two.png"))
    assert rebuilt.summary()["panels"] == original.summary()["panels"]

    original.save(tmp_path / "bare.png", embed=False)
    assert np.array_equal(_decoded(tmp_path / "one.png"), _decoded(tmp_path / "bare.png"))
    with pytest.raises(mint.ExplainError) as err:
        mint.load(tmp_path / "bare.png")
    assert "write_spec" in err.value.fix_hint
    original.save(tmp_path / "spec.png", write_spec=True)
    assert isinstance(mint.load(tmp_path / "spec.json"), mint.Explanation)


def test_cli_reads_a_png_as_spec_and_shows_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mint.explain(T, mint.compare({"a": 1, "b": 2}, label="y")).save(tmp_path / "fig.png")
    assert cli_main(["explain", "--show-spec", str(tmp_path / "fig.png")]) == 0
    assert json.loads(capsys.readouterr().out)["takeaway"] == T
    assert cli_main(["explain", str(tmp_path / "fig.png"), "--out", str(tmp_path / "new.png")]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["ok"] and summary["rendered"] is True


def test_to_spec_is_plain_json_for_numpy_dates_and_new_arguments() -> None:
    import datetime as dt

    days = [dt.date(2026, 1, 1) + dt.timedelta(days=i) for i in range(4)]
    result = mint.explain(
        T,
        mint.trend(
            np.array(days, dtype="datetime64[D]"),
            {"a": np.array([1.0, np.nan, 3.0, 4.0])},
            band={"a": np.float64(0.2)},
            band_label="sd",
            events={days[2]: "switch"},
            label="y",
        ),
        mint.matrix(np.eye(2), rows=["a", "b"], cols=["a", "b"], highlight=("a", "b")),
        mint.distribution({"g": np.array([1.0, 2.0, 3.0])}, stat="mean"),
    )
    text = json.dumps(result.to_spec(), allow_nan=False)
    assert mint.explain_from_spec(json.loads(text)).summary()["panels"] == result.summary()["panels"]


# --------------------------------------------------------------------------- #
# A6. Correctness
# --------------------------------------------------------------------------- #


def test_summary_says_rendered(tmp_path: Path) -> None:
    result = mint.explain(T, mint.compare({"a": 1, "b": 2}, label="y"))
    assert result.summary()["rendered"] is False
    assert result.save(tmp_path / "f.png")["rendered"] is True


def test_reference_set_is_clean_with_only_dejavu_sans(monkeypatch: pytest.MonkeyPatch) -> None:
    """Approximates a Linux host with no Helvetica/Arial."""
    monkeypatch.setitem(
        specs.JOURNALS,
        "screen",
        dataclasses.replace(specs.JOURNALS["screen"], font_family=("DejaVu Sans",)),
    )
    gallery = str(Path(__file__).resolve().parents[1] / "gallery")
    monkeypatch.syspath_prepend(gallery)
    sys.modules.pop("explain_chat_examples", None)
    import explain_chat_examples as examples

    for name, make in examples.EXAMPLES.items():
        result = make()
        assert result.ok, name
        assert result.issues == [], (name, result.issues)
        assert result.min_text_px >= 11, name


# --------------------------------------------------------------------------- #
# A7 / A8
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("highlight", "outlines"),
    [
        (("Rust", "perf"), 1),
        ([("Rust", "perf"), ("Go", "docs")], 2),
        ("Rust", 1),
        ("perf", 1),
        ([("Rust", "perf"), "Go"], 2),
    ],
)
def test_matrix_highlight_shapes(highlight, outlines: int) -> None:
    result = mint.explain(
        T,
        mint.matrix(
            [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
            rows=["Python", "Go", "Rust"],
            cols=["bugfix", "docs", "perf"],
            highlight=highlight,
        ),
    )
    boxes = [ln for ln in result["a"].lines if isinstance(ln, Line2D) and ln.get_label() == "_cell"]
    assert len(boxes) == outlines


@pytest.mark.parametrize("bad", [[("Rust", "perf", "x")], "Cobol", 3.5j, [["Rust"]]])
def test_matrix_bad_highlight_is_an_explain_error(bad) -> None:
    with pytest.raises(mint.ExplainError) as err:
        mint.matrix([[1, 2], [3, 4]], rows=["Rust", "Go"], cols=["perf", "docs"], highlight=bad)
    assert "highlight=" in err.value.fix_hint


def test_distribution_stat_mean() -> None:
    panel = mint.distribution({"a": [62, 64, 61, 66, 63]}, stat="mean", unit="%")
    assert panel.facts[0].startswith("a: mean 63.2%, \N{PLUS-MINUS SIGN} 1 s.d.")
    result = mint.explain(T, panel)
    assert "mean" in _texts(result) and "median" not in _texts(result)
    with pytest.raises(mint.ExplainError, match="stat="):
        mint.distribution({"a": [1, 2, 3]}, stat="mode")


def test_compare_log_is_a_dot_plot_on_a_visible_log_axis() -> None:
    result = mint.explain(T, mint.compare({"a": 2e-6, "b": 3e-4, "c": 1e-2}, log=True, label="σ"))
    ax = result["a"]
    assert ax.get_xscale() == "log" and ax.xaxis.get_visible()
    assert not [p for p in ax.patches if p.get_width() > 0]
    assert result.issues == []
    with pytest.raises(mint.ExplainError, match="positive"):
        mint.compare({"a": 0.0, "b": 1.0}, log=True)


def test_trend_end_values_false_keeps_names_only() -> None:
    result = mint.explain(
        T, mint.trend([1, 2, 3], {"a": [1, 2, 3], "b": [2, 1, 0.5]}, end_values=False, label="y")
    )
    assert {"a", "b"} <= set(_texts(result))
    assert not any(t.startswith("a ") for t in _texts(result))


def test_alt_text_keeps_the_case_of_user_text() -> None:
    result = mint.explain(T, mint.compare({"σ at 300 K": 2.0, "b": 1.0}, label="σ"))
    assert "highest: σ at 300 K" in result.alt_text and "Σ" not in result.alt_text


def test_a_tall_figure_is_a_warning_not_a_dimensions_error() -> None:
    panels = [mint.compare({f"item {i}": i + 1 for i in range(12)}, label="y") for _ in range(3)]
    result = mint.explain(T, *panels, layout=[["a"], ["b"], ["c"]])
    rules = {i["rule"] for i in result.issues}
    assert "too_tall" in rules and "dimensions" not in rules
    assert result.ok


def test_every_issue_hint_speaks_explain_arguments() -> None:
    assert all(
        "Plate" not in hint and "height_mm" not in hint
        for hint in explainer._EXPLAIN_PREFLIGHT_HINTS.values()
    )
