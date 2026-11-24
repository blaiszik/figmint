"""fm.explain: last-round fixes found by looking at the renders (package D)."""

from __future__ import annotations

import re

import numpy as np
import pytest
from matplotlib.colors import to_hex
from matplotlib.ticker import NullLocator

import figmint as fm
from figmint import explainer

T = "BX-204 inhibits the kinase near 10 nM, about 100x below the others"
TIMES = "\N{MULTIPLICATION SIGN}"


def _texts(result: fm.Explanation, key: str = "a") -> list[str]:
    return [
        explainer._reader_text(t.get_text())
        for t in result[key].texts
        if t.get_visible() and t.get_text()
    ]


def _two_groups(rng_seed: int = 3) -> tuple[list[float], list[float], list[str]]:
    rng = np.random.default_rng(rng_seed)
    area, speed, label = [], [], []
    for name, slope in {"wild type": 0.030, "knockout": 0.0}.items():
        a = rng.uniform(180, 520, 14)
        area += a.tolist()
        speed += (2.0 + slope * a + rng.normal(0, 0.9, 14)).tolist()
        label += [name] * 14
    return area, speed, label


# 1. Context groups keep a muted direct label --------------------------------- #


def test_relate_context_group_keeps_a_muted_label() -> None:
    x, y, g = _two_groups()
    result = fm.explain(
        T,
        fm.relate(x, y, groups=g, fit=True, highlight="knockout", x_label="a", y_label="s"),
    )
    notes = {t.get_text(): t for t in result["a"].texts}
    assert "wild type" in notes and "knockout" in notes
    assert notes["wild type"].get_color() == result.theme.muted
    assert notes["wild type"].get_fontweight() == "normal"


# 2. Weak-fit warning judged per group ----------------------------------------- #


def test_fit_warning_is_per_group_when_one_group_is_strong() -> None:
    x, y, g = _two_groups()
    panel = fm.relate(x, y, groups=g, fit=True, x_label="a", y_label="s")
    assert not [i for i in panel.issues if i["rule"] == "fit_on_weak_relationship"]


def test_fit_warning_names_every_group_when_all_are_weak() -> None:
    rng = np.random.default_rng(0)
    x = rng.uniform(0, 1, 40)
    y = rng.normal(0, 1, 40)
    g = ["p"] * 20 + ["q"] * 20
    panel = fm.relate(x, y, groups=g, fit=True, x_label="a", y_label="s")
    weak = [i for i in panel.issues if i["rule"] == "fit_on_weak_relationship"]
    assert len(weak) == 1
    assert "p r = " in weak[0]["message"] and "q r = " in weak[0]["message"]


# 3. Reference label avoids the data -------------------------------------------- #


def _dose_panel(**kw) -> fm.Panel:
    doses = [0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1, 3, 10, 30]
    curves = {
        "BX-204": [100 / (1 + (0.011 / d) ** 1.3) for d in doses],
        "BX-101": [100 / (1 + (0.08 / d) ** 1.1) for d in doses],
        "BX-317": [100 / (1 + (0.9 / d) ** 0.9) for d in doses],
    }
    return fm.trend(
        doses,
        curves,
        log_x=True,
        end_values=False,
        label="Kinase inhibition",
        unit="%",
        x_label="Dose (µM)",
        highlight="BX-204",
        reference=(50, "half-maximal"),
        **kw,
    )


def test_reference_label_is_not_struck_through_by_a_line() -> None:
    result = fm.explain(T, _dose_panel(), fm.compare({"a": 1, "b": 2}, label="x"))
    ax = result["a"]
    renderer = result.fig.canvas.get_renderer()
    note = next(t for t in ax.texts if t.get_text() == "half-maximal")
    box = note.get_window_extent(renderer)
    ref_line = next(ln for ln in ax.lines if np.ptp(ln.get_ydata()) == 0)
    paths = explainer._data_paths(ax, [ref_line])
    assert not any(p.intersects_bbox(box, filled=False) for p in paths)
    assert not [i for i in result.issues if i["rule"] == "reference_label_collides"]


# 4. Crossing the reference ---------------------------------------------------- #


def test_trend_facts_state_where_each_series_crosses_the_reference() -> None:
    facts = _dose_panel().facts
    crossing = [f for f in facts if " crosses 50% (half-maximal) at about " in f]
    assert [f.split(" crosses")[0] for f in crossing] == ["BX-204", "BX-101", "BX-317"]
    assert crossing[0].endswith(" µM")  # x unit taken from x_label "... (µM)"
    value = float(crossing[0].rsplit(" ", 2)[1])
    assert 0.009 <= value <= 0.013  # log-space interpolation near the true 0.011


def test_crossing_interpolates_linearly_and_skips_series_that_never_cross() -> None:
    panel = fm.trend(
        [0, 10, 20], {"up": [0, 40, 80], "flat": [10, 10, 10]}, reference=(60, "goal")
    )
    assert "up crosses 60 (goal) at about 15" in panel.facts
    assert not any(f.startswith("flat crosses") for f in panel.facts)


# 5. One notation on a log axis ------------------------------------------------- #


def test_log_compare_uses_scientific_notation_for_every_label_when_one_needs_it() -> None:
    values = {"0": 5.93e-6, "0.5": 6.97e-5, "1": 8.67e-4, "2": 6.34e-3}
    result = fm.explain(T, fm.compare(values, log=True, label="Conductivity", unit="S/cm"))
    labels = [t for t in _texts(result) if any(ch.isdigit() for ch in t) and "×" in t]
    assert len(labels) == 4
    facts = result.panels["a"].facts
    assert f"highest: 2 6.34{TIMES}10⁻³ S/cm" in facts


# 6. Distribution ticks bracket the data --------------------------------------- #


@pytest.mark.parametrize(
    ("center", "spread"),
    [(10.0, 2.5), (60.0, 12.0)],
)
def test_distribution_ticks_bracket_every_observation(center: float, spread: float) -> None:
    rng = np.random.default_rng(3)
    groups = {
        "wild type": (center + rng.normal(0, spread / 2, 9)).tolist(),
        "knockout": (center - spread + rng.normal(0, spread / 2, 8)).tolist(),
    }
    result = fm.explain(
        T,
        fm.distribution(groups, label="Distance", unit="µm"),
        fm.compare({"a": 1, "b": 2}, label="x"),
    )
    ax = result["a"]
    lo = min(min(v) for v in groups.values())
    hi = max(max(v) for v in groups.values())
    v0, v1 = ax.get_xlim()
    ticks = [t for t in ax.xaxis.get_majorticklocs() if v0 - 1e-9 <= t <= v1 + 1e-9]
    labelled = [
        t
        for t, tick in zip(ax.xaxis.get_majorticklocs(), ax.xaxis.get_major_ticks(), strict=False)
        if t in ticks and tick.label1.get_text()
    ]
    assert len(labelled) >= 3
    assert min(labelled) <= lo and max(labelled) >= hi


# 7. Bar growth cap -------------------------------------------------------------- #


def test_bar_row_growth_is_capped_at_1_3() -> None:
    assert explainer._ROW_GROWTH == 1.3


# 8. Strongest off-diagonal -------------------------------------------------------- #


def test_matrix_diverging_reports_strongest_off_diagonal_once() -> None:
    names = ["gap", "density", "volume"]
    corr = [[1.0, 0.3, 0.2], [0.3, 1.0, -0.81], [0.2, -0.81, 1.0]]
    facts = fm.matrix(corr, rows=names, cols=names, diverging=True, label="r").facts
    strongest = [f for f in facts if f.startswith("strongest off-diagonal")]
    assert strongest == ["strongest off-diagonal: density × volume = \N{MINUS SIGN}0.81"]
    assert not any(
        f.startswith("strongest") for f in fm.matrix(corr, rows=names, cols=names).facts
    )


# 9. Editorial inline tick labels stay off the lines ------------------------------- #


def test_editorial_inline_tick_labels_do_not_sit_on_a_data_line() -> None:
    result = fm.explain(
        "Checkout regressed after the deploy",
        fm.trend(
            [1, 2, 3, 4, 5, 6, 7, 8],
            {
                "checkout": [540, 560, 550, 570, 980, 1380, 1680, 1840],
                "search": [440, 460, 450, 455, 450, 445, 460, 455],
            },
            label="p99",
            unit="ms",
            highlight="checkout",
        ),
        style="editorial",
    )
    ax = result["a"]
    renderer = result.fig.canvas.get_renderer()
    inline = ax._figmint_inline_ticks
    paths = [
        p for p in explainer._data_paths(ax, []) if np.ptp(p.vertices[:, 1]) > 0.5
    ]
    for note, carries_unit in inline:
        if not note.get_visible():
            continue
        hit = any(p.intersects_bbox(note.get_window_extent(renderer), filled=False) for p in paths)
        assert not hit or (carries_unit and note.get_zorder() > 5)
    assert sum(1 for t in _texts(result) if t.endswith(" ms")) == 1  # unit kept


# 10. Script sizes reported ------------------------------------------------------- #


def test_script_depth_parser() -> None:
    assert explainer._script_depth("µm$^{2}$") == 1
    assert explainer._script_depth("$e^{x^{2}}$") == 2
    assert explainer._script_depth("plain text") == 0
    assert explainer._script_depth(r"from \$5M to \$8M") == 0


def test_summary_reports_min_script_px() -> None:
    plain = fm.explain(T, fm.compare({"a": 1, "b": 2}, label="x")).summary()
    assert plain["display"]["min_script_px"] is None
    result = fm.explain(
        T,
        fm.relate([1, 2, 3, 4], [2, 3, 5, 4], x_label="Cell area (µm²)", y_label="Speed"),
    )
    display = result.summary()["display"]
    assert display["min_script_px"] is not None
    assert display["min_script_px"] < display["min_text_px"]
    assert display["min_script_px"] == pytest.approx(0.7 * display["min_text_px"], abs=0.3)


# 11. Log axes have no width-dependent minor ticks ------------------------------- #


def test_side_by_side_log_x_panels_have_identical_ticks() -> None:
    result = fm.explain(T, _dose_panel(), _dose_panel(title="again"))
    for key in ("a", "b"):
        assert isinstance(result[key].xaxis.get_minor_locator(), NullLocator)
    assert list(result["a"].xaxis.get_majorticklocs()) == list(
        result["b"].xaxis.get_majorticklocs()
    )


# --------------------------------------------------------------------------- #
# Package E: log scales speak in ratios and slopes
# --------------------------------------------------------------------------- #


def test_log_trend_facts_give_log_slope_r2_and_peak_ratios() -> None:
    x = [3.0, 4.0, 5.0, 6.0, 8.0]
    arrhenius = [10 ** (-0.41 * v) for v in x]
    peaked = [1e-5, 1e-3, 6.5e-3, 1e-3, 1.64e-4]
    facts = fm.trend(x, {"2 at.%": arrhenius, "film": peaked}, log=True).facts
    assert "2 at.%: log₁₀ slope −0.41 per unit x, R² = 1.000" in facts
    assert "film: peak is 650× the first value and 40× the last" in facts
    assert not any(f.startswith("2 at.%: peak is") for f in facts)  # peak at an end
    linear = fm.trend(x, {"a": arrhenius}).facts
    assert not any("slope" in f for f in linear)
    log_x = fm.trend(x, {"a": arrhenius}, log=True, log_x=True).facts
    assert not any("log₁₀ slope" in f for f in log_x)


@pytest.mark.parametrize(
    ("ratio", "text"),
    [(63871.2, "63,900×"), (1069.3, "1,070×"), (1200.0, "1,200×"), (62.4, "62×"), (4.04, "4.0×"),
     (0.7226, "0.72×")],
)
def test_ratios_print_to_three_significant_figures(ratio: float, text: str) -> None:
    assert explainer._ratio_text(ratio) == text.replace("×", TIMES)


def test_distribution_log_states_ratios_and_linear_keeps_differences() -> None:
    groups = {"2 at.%": [5.5e17, 5.6e17, 5.7e17], "4 at.%": [3.4e17, 3.9e17, 4.4e17]}
    log_facts = fm.distribution(groups, log=True, stat="mean", highlight="4 at.%").facts
    assert "4 at.% is 0.70× 2 at.% (mean)" in log_facts
    assert not any(" − " in f or "\N{MINUS SIGN} 2 at.%" in f for f in log_facts)
    lin = fm.distribution({"a": [1, 2, 3], "b": [4, 5, 6]}, highlight="b").facts
    assert any(f.startswith("b \N{MINUS SIGN} a: median") for f in lin)


def test_small_n_caution_is_stated_once() -> None:
    groups = {k: [1.0 + i, 2.0 + i, 3.0 + i] for i, k in enumerate("abcde")}
    facts = fm.distribution(groups, stat="mean").facts
    cautions = [f for f in facts if "rough estimate" in f]
    assert cautions == ["every group has n = 3: the s.d. is a rough estimate"]
    mixed = fm.distribution({"a": [1, 2, 3], "b": [1, 2, 3, 4, 5, 6]}).facts
    assert "n < 5 in a (n = 3): quartiles are not meaningful" in mixed


@pytest.mark.parametrize("stat", ["median", "mean"])
def test_distribution_spread_only_drawn_and_captioned_from_n_5(stat: str) -> None:
    small = fm.distribution({"a": [1, 2, 3], "b": [4, 5, 6]}, stat=stat)
    assert small.measure_note == f"tick: {stat}"
    result = fm.explain(T, small)
    assert not result["a"].collections or all(
        type(c).__name__ != "LineCollection" or len(c.get_segments()) == 0
        or np.ptp(c.get_segments()[0][:, 0]) == 0  # vertical centre ticks only
        for c in result["a"].collections
    )
    big = fm.distribution({"a": [1, 2, 3, 4, 5], "b": [4, 5, 6]}, stat=stat)
    assert "line:" in big.measure_note and "(n ≥ 5)" in big.measure_note


def test_relate_groups_with_small_n_get_one_caution() -> None:
    x = [1, 2, 3, 1, 2, 3, 1, 2, 3, 4, 5, 6]
    y = [1, 2, 3, 3, 2, 1, 2, 4, 6, 8, 9, 13]
    g = ["p"] * 3 + ["q"] * 3 + ["r"] * 6
    facts = fm.relate(x, y, groups=g, fit=True, x_label="x", y_label="y").facts
    cautions = [f for f in facts if "rough estimate" in f]
    assert cautions == [
        "n < 5 in p (n = 3), q (n = 3): r is a rough estimate and so is the fitted line"
    ]


def test_scientific_labels_in_a_set_share_significant_figures() -> None:
    fmt = explainer._formatter([1.2e16, 5.6e17, 3.89e17], log=True)
    assert [fmt(v) for v in (1.2e16, 5.6e17, 3.89e17)] == [
        f"1.20{TIMES}10¹⁶",
        f"5.60{TIMES}10¹⁷",
        f"3.89{TIMES}10¹⁷",
    ]
    two = explainer._formatter([1e-2, 3e-4], log=True)
    assert [two(1e-2), two(3e-4)] == [f"1{TIMES}10⁻²", f"3{TIMES}10⁻⁴"]


def _labelled_ticks(axis) -> list[float]:
    lo, hi = sorted(axis.get_view_interval())
    return [
        float(t.get_loc())
        for t in axis.get_major_ticks()
        if lo * (1 - 1e-9) <= t.get_loc() <= hi * (1 + 1e-9) and t.label1.get_text()
    ]


@pytest.mark.parametrize(
    "values",
    [
        {"0": [9.4e15, 1.2e16, 1.46e16], "2": [5.5e17, 5.6e17, 5.74e17]},  # ~1.8 decades
        {"a": [3.1e3, 3.3e3, 3.6e3], "b": [4.0e3, 4.3e3, 4.6e3]},  # well under a decade
    ],
)
def test_log_value_axes_have_two_labels_and_one_above_the_data(values) -> None:
    result = fm.explain(T, fm.distribution(values, log=True, label="n"))
    ticks = _labelled_ticks(result["a"].xaxis)
    top = max(max(v) for v in values.values())
    assert len(ticks) >= 2 and max(ticks) >= top


def test_log_compare_and_trend_axes_reach_a_labelled_tick_above_the_data() -> None:
    result = fm.explain(
        T,
        fm.compare({"a": 1.5e-3, "b": 2e-5, "c": 4e-4}, log=True, label="x"),
        fm.trend([1, 2, 3], {"a": [1e-5, 1e-4, 1.5e-3]}, log=True),
    )
    assert max(_labelled_ticks(result["a"].xaxis)) >= 1.5e-3
    assert max(_labelled_ticks(result["b"].yaxis)) >= 1.5e-3
    assert len(_labelled_ticks(result["b"].yaxis)) >= 2


# Rough edges found by building a figure from SKILL.md alone ------------------ #


def _absorption_curves() -> dict[str, list[float]]:
    t = np.array([0.5, 1, 2, 4, 6, 8, 12, 16, 24])
    return {
        "oral": (14 * 0.35 / 0.17 * (np.exp(-0.18 * t) - np.exp(-0.35 * t))).tolist(),
        "iv": (8 * np.exp(-0.25 * t)).tolist(),
    }


def test_log_slope_is_fitted_on_each_side_of_an_interior_peak() -> None:
    t = [0.5, 1, 2, 4, 6, 8, 12, 16, 24]
    facts = fm.trend(t, _absorption_curves(), log=True, x_label="Time after dose (h)").facts
    oral = [f for f in facts if f.startswith("oral: log₁₀ slope")]
    assert len(oral) == 2
    assert " per h up to the peak at 4 h, R² = " in oral[0]
    assert " per h from the peak at 4 h on, R² = " in oral[1]
    falling = float(oral[1].split("slope ")[1].split(" ")[0].replace("\N{MINUS SIGN}", "-"))
    assert falling < 0
    # A monotone series keeps one slope over the whole range: −0.25/ln 10 per h.
    assert "iv: log₁₀ slope −0.109 per h, R² = 1.000" in facts


def test_log_slope_splits_at_an_interior_trough() -> None:
    x = [0, 1, 2, 3, 4, 5]
    facts = fm.trend(x, {"v": [1e3, 1e2, 1e1, 1e2, 1e3, 1e4]}, log=True).facts
    assert "v: log₁₀ slope −1 per unit x up to the trough at 2, R² = 1.000" in facts
    assert "v: log₁₀ slope 1 per unit x from the trough at 2 on, R² = 1.000" in facts


def test_x_unit_from_x_label_reaches_every_x_in_facts() -> None:
    t = [0.5, 1, 2, 4, 6, 8, 12, 16, 24]
    facts = fm.trend(
        t, _absorption_curves(), log=True, x_label="Time after dose [h]",
        reference=(1.0, "effective"), highlight=["oral", "iv"],
    ).facts
    assert any("from 0.5 h to 24 h" in f for f in facts)
    assert any(f.startswith("at 24 h: oral is ") for f in facts)
    assert any(f.startswith("iv crosses 1 (effective) at about ") and f.endswith(" h") for f in facts)
    plain = fm.trend([1, 2, 3], {"a": [1, 2, 3]}, x_label="Step").facts
    assert any("from 1 to 3" in f for f in plain)


def test_x_unit_parser() -> None:
    assert explainer._x_unit("Time after dose (h)") == "h"
    assert explainer._x_unit("1000 / T (K⁻¹)") == "K⁻¹"
    assert explainer._x_unit("Strain [%]") == "%"
    assert explainer._x_unit("Hours after dose") is None
    assert explainer._x_unit("Dose (log scale) of drug") is None
    assert explainer._with_x_unit("40", "%") == "40%"


def test_log_change_wording_is_the_same_for_every_series() -> None:
    facts = fm.trend(
        [0, 1, 2], {"a": [10.0, 5.0, 2.0], "b": [10.0, 1.0, 0.05]}, log=True
    ).facts
    assert any("(falls 5.0-fold)" in f for f in facts)
    assert any("(falls 200-fold, 2.3 decades)" in f for f in facts)


def test_reference_label_finds_room_inside_a_narrow_panel() -> None:
    t = [0.5, 1, 2, 4, 6, 8, 12, 16, 24]
    result = fm.explain(
        "Oral stays above the effective level until about 19 h",
        fm.trend(t, _absorption_curves(), log=True, x_label="Time after dose (h)",
                 reference=(1.0, "minimum effective"), label="Concentration", unit="mg/L"),
        fm.compare({"oral": 19.0, "iv": 7.0}, label="Hours above level", unit="h"),
    )
    hints = [i["fix_hint"] for i in result.issues if i["rule"] == "reference_label_collides"]
    assert all("layout" not in h for h in hints)  # never a hint that makes the figure too tall


def test_reference_facts_name_series_that_never_cross() -> None:
    facts = fm.trend(
        [0, 1, 2, 3],
        {"a": [100, 95, 90, 85], "b": [100, 90, 80, 70], "c": [100, 85, 75, 60]},
        reference=(80, "end of life"),
    ).facts
    assert "a stays above 80 (end of life) throughout" in facts
    assert any(f.startswith("b crosses 80") for f in facts)
    two = fm.trend([0, 1, 2], {"a": [5, 6, 7], "b": [6, 7, 8], "c": [1, 2, 3]}, reference=4).facts
    assert "a and b stay above 4 throughout" in two
    assert "c stays below 4 throughout" in two


def test_distribution_states_whether_ranges_separate_and_each_pair_once() -> None:
    groups = {"ctrl": [70, 71, 72], "A": [79, 81, 82], "B": [91, 92, 93]}
    facts = fm.distribution(groups, highlight=["B", "ctrl"]).facts
    assert "every B value is above every ctrl value (B lowest 91, ctrl highest 72)" in facts
    assert "B \N{MINUS SIGN} ctrl: median +21 (1.3\N{MULTIPLICATION SIGN})" in facts
    assert not any(f.startswith("ctrl \N{MINUS SIGN} B") for f in facts)  # each pair once
    mixed = fm.distribution({"a": [1, 2, 3, 4], "b": [3, 4, 5, 6]}, highlight="b").facts
    assert "b and a overlap: 2 of 4 b values lie within the a range" in mixed


# --------------------------------------------------------------------------- #
# Package F: facts that check the claims agents make
# --------------------------------------------------------------------------- #

MINUS = "\N{MINUS SIGN}"
ARROW = "\N{RIGHTWARDS ARROW}"


# F1. baseline= ---------------------------------------------------------------- #


@pytest.mark.parametrize(
    "build",
    [
        lambda **kw: fm.compare({"ctrl": 1.0, "a": 2.0, "b": 3.0}, **kw),
        lambda **kw: fm.trend([0, 1, 2], {"ctrl": [1, 2, 3], "a": [2, 3, 4], "b": [1, 1, 1]}, **kw),
        lambda **kw: fm.distribution({"ctrl": [1, 2, 3], "a": [2, 3, 4], "b": [5, 6, 7]}, **kw),
    ],
)
def test_baseline_must_be_an_item_and_not_highlighted(build) -> None:
    with pytest.raises(fm.ExplainError) as unknown:
        build(baseline="control")
    assert "'ctrl'" in unknown.value.fix_hint
    with pytest.raises(fm.ExplainError) as both:
        build(baseline="ctrl", highlight=["a", "ctrl"])
    assert "highlight" in str(both.value) and both.value.fix_hint
    with pytest.raises(fm.ExplainError):
        build(baseline=["ctrl"])


def test_baseline_round_trips_through_the_spec_and_the_png(tmp_path) -> None:
    fig = fm.explain(
        "a is 46% above control",
        fm.compare({"ctrl": 26.0, "a": 38.0, "b": 30.0}, unit="ms", baseline="ctrl"),
        fm.trend([0, 1, 2], {"ctrl": [1, 2, 3], "a": [2, 3, 5]}, baseline="ctrl"),
        fm.distribution({"ctrl": [1, 2, 3], "a": [4, 5, 6]}, baseline="ctrl"),
    )
    spec = fig.to_spec()
    assert [p["baseline"] for p in spec["panels"]] == ["ctrl"] * 3
    path = tmp_path / "f.png"
    fig.save(path)
    assert fm.load(path).to_spec() == spec
    assert fm.explain_from_spec(spec).to_spec() == spec


def test_baseline_is_drawn_in_ink_and_takes_no_palette_colour() -> None:
    result = fm.explain(
        T,
        fm.compare({"ctrl": 5.0, "a": 3.0, "b": 2.0}, baseline="ctrl", highlight="a"),
        fm.trend(
            [0, 1, 2],
            {"ctrl": [1, 2, 3], "a": [2, 3, 4], "b": [1, 1, 2], "c": [3, 1, 2], "d": [0, 2, 1]},
            baseline="ctrl",  # four coloured series plus the baseline is allowed
        ),
    )
    ink = result.theme.ink
    bars = {
        tick.get_text(): patch.get_facecolor()
        for tick, patch in zip(result["a"].get_yticklabels(), result["a"].patches, strict=False)
    }
    from matplotlib.colors import to_rgba

    assert bars["ctrl"] == to_rgba(ink)
    assert bars["a"] == to_rgba(result.theme.accent_colors[0])  # the highlight keeps red
    assert bars["b"] == to_rgba(result.theme.context_fill)
    weights = {t.get_text(): t.get_fontweight() for t in result["a"].get_yticklabels()}
    assert weights["ctrl"] == "normal" and weights["a"] == "bold"
    lines = {ln.get_label(): ln.get_color() for ln in result["b"].get_lines()}
    assert lines["ctrl"] == ink
    assert ink not in {lines[k] for k in "abcd"}
    assert "ctrl" not in result.summary()["colors"]


def test_compare_states_items_against_the_baseline() -> None:
    ms = fm.compare({"ctrl": 26.0, "new": 38.0, "old": 30.0}, unit="ms", baseline="ctrl").facts
    assert "new 38 ms vs ctrl 26 ms: +12 ms (+46%)" in ms
    assert "old 30 ms vs ctrl 26 ms: +4 ms (+15%)" in ms
    pct = fm.compare(
        {"ctrl": 79.0, "kd": 46.0, "x": 70.0}, unit="%", baseline="ctrl", highlight="kd"
    ).facts
    assert f"kd 46% vs ctrl 79%: {MINUS}33 points (0.58{TIMES})" in pct
    assert not any(f.startswith("x ") and "vs ctrl" in f for f in pct)  # only the highlight
    logged = fm.compare({"ctrl": 10.0, "a": 47.0}, log=True, baseline="ctrl").facts
    assert any(f.startswith(f"a is 4.7{TIMES} ctrl") for f in logged)


def test_trend_states_series_against_the_baseline_at_the_end_and_as_a_median_gap() -> None:
    facts = fm.trend(
        [0, 1, 2, 3],
        {"ctrl": [10, 10, 10, 10], "a": [11, 12, 13, 15], "b": [10, 9, 8, None]},
        unit="ms",
        baseline="ctrl",
    ).facts
    assert "a vs ctrl: +5.0 ms (+50%) at 3; median gap +2.5 ms (+25%) over 4 shared points" in facts
    assert any(f.startswith("b vs ctrl: ") and " at 2;" in f for f in facts)
    logged = fm.trend([0, 1, 2], {"ctrl": [1, 1, 1], "a": [2, 4, 8]}, log=True, baseline="ctrl")
    assert f"a vs ctrl: 8.0{TIMES} at 2; median ratio 4.0{TIMES} over 3 shared points" in logged.facts


def test_distribution_states_groups_against_the_baseline_only() -> None:
    groups = {"ctrl": [78, 80, 82, 79, 81], "kd": [40, 42, 44, 41, 43], "x": [70, 71, 72, 73, 69]}
    facts = fm.distribution(groups, unit="%", baseline="ctrl", highlight="kd").facts
    assert f"kd vs ctrl: median {MINUS}38 points (0.53{TIMES})" in facts
    assert any(f.startswith("every kd value is below every ctrl value") for f in facts)
    assert not any(f.startswith("kd \N{MINUS SIGN} x") or "x value" in f for f in facts)


# F2. distribution fact volume and robustness ---------------------------------- #


def test_distribution_pairs_only_among_highlights_never_between_context_groups() -> None:
    groups = {k: [i, i + 1.0, i + 2.0] for i, k in enumerate("abcde")}
    two = fm.distribution(groups, highlight=["b", "d"]).facts
    pair_facts = [f for f in two if f" {MINUS} " in f or "overlap" in f or " value" in f]
    assert pair_facts and all("b" in f and "d" in f for f in pair_facts)
    one = fm.distribution(groups, highlight="b").facts
    assert sum(f.startswith(f"b {MINUS} ") for f in one) == 4
    assert not any(f.startswith(("a ", "c ", "d ", "e ")) and MINUS in f[:4] for f in one)
    none = fm.distribution(groups).facts
    assert not any(f" {MINUS} " in f or "overlap" in f for f in none)


def test_one_stray_value_does_not_decide_separation() -> None:
    kd = [41.6, 46.1, 48.3, 42.0, 45.0, 47.0, 44.0, 60.8]
    vim = [8.0, 63.1, 68.0, 68.6, 68.6, 74.7, 78.9, 83.1]
    facts = fm.distribution({"kd": kd, "vim": vim}, highlight="kd").facts
    assert "all but 1 of 8 vim values lie above every kd value (the exception: 8.0)" in facts
    assert "vim: 1 value far from the rest: 8.0 (median 68.6)" in facts
    assert any(f.startswith("vim: median 68.6, middle half") and "range 8.0" in f for f in facts)


def test_far_values_need_n_5_and_a_nonzero_mad() -> None:
    flat = fm.distribution({"a": [5, 5, 5, 5, 5, 50], "b": [1, 2, 30]}).facts
    assert not any("far from the rest" in f for f in flat)
    assert explainer._far_values(np.array([1.0, 2.0, 3.0, 100.0])).size == 0  # n < 5
    rates = np.array([1e-4, 2e-4, 3e-4, 2.5e-4, 1.5e-4, 7e-4])
    assert explainer._far_values(rates).tolist() == [7e-4]
    assert explainer._far_values(rates, log=True).size == 0  # 3x is near on a log axis


# F3. medians before/after an event --------------------------------------------- #


def test_trend_event_states_each_series_median_before_and_from_it_on() -> None:
    x = [f"2026-10-{d:02d}" for d in range(10, 20)]
    series = {
        "west": [100, 102, 98, 101, 99, 150, 148, 152, 149, 151],
        "east": [90, 91, 89, 90, 92, 91, 90, 89, 92, 91],
    }
    facts = fm.trend(x, series, unit="ms", events={"2026-10-15": "config change"}).facts
    assert f"west: median 100 ms before config change {ARROW} 150 ms from it on (+50%)" in facts
    assert any(f.startswith("east: median 90 ms before config change") for f in facts)
    logged = fm.trend(x, series, log=True, events={"2026-10-15": "change"}, highlight="west")
    assert any(f.startswith("west: median") and f"(1.5{TIMES})" in f for f in logged.facts)
    pct = fm.trend([0, 1, 2, 3], {"a": [10, 12, 30, 32]}, unit="%", events={2: "dose"}).facts
    assert f"a: median 11% before dose {ARROW} 31% from it on (+20 points)" in pct


# F4/F5. crossings and comparisons between coloured series ---------------------- #


def test_repeated_crossings_are_counted_not_called_first() -> None:
    x = list(range(8))
    facts = fm.trend(x, {"a": [1, 3, 1, 3, 1, 3, 3, 3], "b": [2] * 8}).facts
    assert "a and b cross 5 times; a is above b from 5 on" in facts
    assert not any("first crosses" in f for f in facts)
    tangled = fm.trend(x, {"a": [1, 3, 1, 3, 1, 3, 1, 3], "b": [2] * 8}).facts
    assert "a and b cross 7 times; they end tangled" in tangled
    level = fm.trend(x, {"a": [1, 3, 1, 3, 1, 3, 1, 2], "b": [2] * 8}).facts
    assert "a and b cross 6 times; they end level" in level
    once = fm.trend(x, {"a": [0, 0, 1, 1, 3, 3, 3, 3], "b": [2] * 8}).facts  # ties ignored
    assert "a first crosses above b at 4" in once


def test_first_series_is_compared_with_every_other_coloured_series() -> None:
    facts = fm.trend(
        [0, 1], {"a": [1, 5], "b": [1, 2], "c": [1, 3], "d": [1, 4]}, unit="ms"
    ).facts
    assert "at 1: a is 3 ms above b" in facts
    assert "at 1: a is 2 ms above c" in facts
    assert "at 1: a is 1 ms above d" in facts


# F6/F7. change and share --------------------------------------------------------- #


def test_change_facts_give_relative_change_and_cover_the_rest() -> None:
    before = {"a": 1.0, "b": 2.0, "c": 4.0, "d": 5.0, "e": 0.479}
    after = {"a": 1.5, "b": 2.05, "c": 3.9, "d": 5.1, "e": 0.377}
    facts = fm.change(before, after, unit="$", fmt="{:.3f}", highlight="e").facts
    assert f"e: $0.479 {ARROW} $0.377 ({MINUS}$0.102, {MINUS}21%)" in facts
    assert f"largest change: a $1.000 {ARROW} $1.500 (+$0.500, +50%)" in facts
    assert f"the other 3 changed by {MINUS}2.5% to +2.5%" in facts
    pct = fm.change({"a": 50, "b": 60, "c": 40}, {"a": 55, "b": 58, "c": 41}, unit="%").facts
    assert f"largest change: a 50% {ARROW} 55% (+5 points)" in pct
    assert f"the other 2 changed by {MINUS}2 points to +1 point" in pct


def test_share_states_the_combined_share_of_the_highlighted_parts() -> None:
    parts = {"east": 7200.0, "west": 1700.0, "south": 1100.0, "north": 2400.0}
    facts = fm.share(parts, unit="$", highlight=["west", "south"]).facts
    assert "west and south together: 23% ($2,800)" in facts
    assert not any("together: " in f and "west" in f for f in fm.share(parts, highlight="west").facts)


# F8. matrix ----------------------------------------------------------------------- #


def test_correlation_matrix_excludes_its_diagonal_and_reports_highlights() -> None:
    names = ["closure", "speed", "viability"]
    corr = [[1.0, 0.86, 0.53], [0.86, 1.0, 0.40], [0.53, 0.40, 1.0]]
    facts = fm.matrix(
        corr, rows=names, cols=names, diverging=True, highlight=[("closure", "viability"), "speed"]
    ).facts
    assert f"highest: closure {TIMES} speed = 0.86" in facts
    assert "diagonal is 1 throughout (excluded)" in facts
    assert f"closure {TIMES} viability = 0.53" in facts
    assert f"speed row: strongest speed {TIMES} closure = 0.86" in facts
    assert not any(f.startswith(("largest off-diagonal", "strongest off-diagonal")) for f in facts)
    assert any(f.startswith("highest row mean: closure (0.695") for f in facts)


# F9/F10. no font-probe noise; date ticks carry their month ------------------------ #


def test_chat_styles_never_probe_the_cursive_font_stack() -> None:
    from figmint.specs import get_spec
    from figmint.themes import get_theme

    for style in ("figmint", "bold", "editorial", "sketch"):
        params = get_theme(style).rc_params(get_spec("screen"))
        assert params["mathtext.cal"] == params["mathtext.rm"]


def test_date_ticks_give_every_day_of_month_its_month() -> None:
    days = np.datetime64("2026-09-15") + np.arange(60)
    result = fm.explain(T, fm.trend([str(d) for d in days], {"a": np.sin(np.arange(60) / 5.0)}))
    result.fig.canvas.draw()
    labels = [t.get_text() for t in result["a"].get_xticklabels() if t.get_visible() and t.get_text()]
    assert labels == ["15 Sep", "1 Oct", "15 Oct", "1 Nov"]


# G1. benchmark fixes: what cost agents a submission ----------------------------- #

MINUS = "\N{MINUS SIGN}"


def test_fmt_that_writes_the_unit_is_not_given_it_twice() -> None:
    values = {"Lab annex": -29.0, "Library": -18.0, "Gym": -3.0}
    panel = fm.compare(values, unit="%", fmt="{:+.0f}%", baseline="Gym", sort="asc", label="c")
    joined = " | ".join(panel.facts)
    assert "%%" not in joined
    assert f"lowest: Lab annex {MINUS}29%" in panel.facts
    assert f"Lab annex {MINUS}29% vs Gym {MINUS}3%: {MINUS}26 points" in panel.facts
    result = fm.explain(T, panel)
    assert not any("%%" in t for t in _texts(result))
    # Any unit, at a word boundary only: "12 ms" already has "ms", but not "s".
    assert explainer._with_unit("12 ms", "ms") == "12 ms"
    assert explainer._with_unit("12ms", "ms") == "12ms"
    assert explainer._with_unit("12 ms", "s") == "12 ms s"
    assert explainer._with_unit("$12", "$") == "$12"
    assert explainer._signed("+5") == "+5"


def test_sign_hyphens_in_caller_text_are_drawn_as_minus_signs() -> None:
    m = explainer._minus_signs
    assert m("-3 °C at x = -0.4, k·d^(-1/2), [-1], a:-2, 1/-2") == (
        f"{MINUS}3 °C at x = {MINUS}0.4, k·d^({MINUS}1/2), [{MINUS}1], a:{MINUS}2, 1/{MINUS}2"
    )
    for keep in ("2026-01-31", "43-53 nm", "1C-rate", "BX-204", "ab -c"):
        assert m(keep) == keep
    result = fm.explain(
        "Cooling to -40 °C halves the yield",
        fm.compare({"-40 °C": 40, "20 °C": 80}, label="Yield", unit="%", title="At -40 °C"),
        note="Ranges 43-53 nm; dates 2026-01-31",
        source="lab",
    )
    texts = [explainer._reader_text(t.get_text()) for t in result.fig.texts]
    texts += _texts(result) + [t.get_text() for t in result["a"].get_yticklabels()]
    assert any(f"{MINUS}40 °C halves" in t for t in texts)
    assert any(f"At {MINUS}40 °C" in t for t in texts)
    assert any("43-53 nm" in t and "2026-01-31" in t for t in texts)
    assert not any("-40" in t for t in texts)


def test_relate_takes_unit_as_the_y_unit() -> None:
    x, y, _ = _two_groups()
    panel = fm.relate(x, y, x_label="Area", y_label="Speed", unit="µm/min", fit=True)
    assert panel.unit == "µm/min"
    assert panel.to_spec()["unit"] == "µm/min"
    assert any("µm/min per unit x" in f for f in panel.facts)
    result = fm.explain(T, panel)
    assert result.summary()["ok"]
    rebuilt = fm.panel_from_spec(panel.to_spec())
    assert rebuilt.facts == panel.facts
    # A y_label that already ends with the unit is not given it twice.
    assert explainer._measure_text("Yield (MPa)", "MPa") == "Yield (MPa)"


def test_x_unit_comes_only_from_a_unit_like_bracket_or_from_x_unit() -> None:
    assert explainer._x_unit("Time after dose (h)") == "h"
    assert explainer._x_unit("Cycle (1C/1C)") is None
    assert explainer._x_unit("Dose (per 70 kg)") is None
    x = [0, 100, 200, 300]
    series = {"a": [100.0, 92.0, 85.0, 78.0]}
    ref = (80, "end of life")
    facts = fm.trend(x, series, x_label="Cycle (1C/1C)", reference=ref, label="c").facts
    assert any(f.endswith("at about 271") for f in facts), facts
    assert not any("1C/1C" in f for f in facts)
    given = fm.trend(x, series, x_label="Cycle (1C/1C)", x_unit="cycles", reference=ref)
    assert any(f.endswith("at about 271 cycles") for f in given.facts)
    assert given.to_spec()["x_unit"] == "cycles"
    assert fm.panel_from_spec(given.to_spec()).facts == given.facts
    off = fm.trend(x, series, x_label="Time (h)", x_unit="", reference=ref).facts
    assert any(f.endswith("at about 271") for f in off)
    rx = fm.relate([1, 2, 3, 4], [2, 4, 7, 8], x_label="d (µm)", y_label="s", unit="MPa", fit=True)
    assert any("MPa per µm" in f for f in rx.facts)


def _daily(seed: int = 4) -> tuple[list[str], dict[str, list[float]]]:
    rng = np.random.default_rng(seed)
    days = [str(np.datetime64("2026-06-01") + np.timedelta64(i, "D")) for i in range(120)]
    weekly = 15 * np.sin(np.arange(120) * 2 * np.pi / 7)
    series = {
        name: (100 + weekly + rng.normal(0, 6, 120) - drop * (np.arange(120) > 45)).tolist()
        for name, drop in (("Lab annex", 29), ("Library", 18), ("Gym", 3))
    }
    return days, series


def test_reference_label_moves_to_the_end_label_column_when_the_plot_is_full() -> None:
    days, series = _daily()
    result = fm.explain(
        T,
        fm.trend(days, series, reference=(100, "pre-retrofit median"), label="use", unit="%"),
        layout=[["a"]],
    )
    assert not [i for i in result.issues if i["rule"] == "reference_label_collides"]
    ax = result["a"]
    note = next(t for t in ax.texts if "pre-retrofit" in t.get_text())
    renderer = result.fig.canvas.get_renderer()
    box = note.get_window_extent(renderer)
    assert box.x0 > ax.get_window_extent(renderer).x1  # beside the line's end
    ends = [t for t in ax.texts if t is not note and t.get_text().startswith(("Gym", "Lab", "Lib"))]
    assert not any(box.overlaps(t.get_window_extent(renderer)) for t in ends)


def test_compare_value_label_is_moved_off_a_reference_line() -> None:
    def _crossed(result: fm.Explanation) -> list[str]:
        ax = result["a"]
        renderer = result.fig.canvas.get_renderer()
        line_x = float(ax.transData.transform((50.0, 0.0))[0])
        return [
            t.get_text()
            for t in ax.texts
            if t.get_text().endswith("%")
            and t.get_window_extent(renderer).x0 - 1 <= line_x <= t.get_window_extent(renderer).x1 + 1
        ]

    room = fm.explain(T, fm.compare({"a": 100, "b": 48, "c": 10}, reference=(50, "target"), unit="%", label="v"))
    assert not _crossed(room)
    tight = fm.explain(T, fm.compare({"a": 48, "b": 30, "c": 10}, reference=(50, "target"), unit="%", label="v"))
    assert not _crossed(tight)  # no room past the line: the value goes inside its bar
    assert tight.summary()["issues"] == []
    dots = fm.explain(
        T, fm.compare({"a": 48, "b": 30, "c": 10}, zero=False, reference=(50, "t"), unit="%", label="v")
    )
    assert not _crossed(dots)
    assert dots.summary()["issues"] == []


def _matrix_and_change() -> tuple[fm.Panel, fm.Panel]:
    rows = ["English", "Spanish", "Japanese", "Hindi", "Arabic", "Swahili"]
    cols = ["QA", "summarise", "translate", "code", "math"]
    grid = [[80.0 - 3 * i + j for j in range(5)] for i in range(6)]
    grid[5][4] = 45.4
    m = fm.matrix(grid, rows=rows, cols=cols, label="Accuracy", unit="%", title="Grid")
    before = {"QA": 59.9, "summarise": 58.7, "translate": 59.9, "code": 64.4, "math": 28.6}
    after = {"QA": 65.0, "summarise": 63.9, "translate": 64.2, "code": 68.3, "math": 45.4}
    c = fm.change(before, after, label="Swahili accuracy", unit="%", highlight="math", title="t")
    return m, c


def test_a_slightly_tall_figure_is_compressed_instead_of_warned() -> None:
    m, c = _matrix_and_change()
    long = "A subtitle long enough to wrap onto a second line in the chat column, " * 2
    result = fm.explain(T, m, c, layout=[["a"], ["b"]], subtitle=long, note=long, source="s")
    assert not [i for i in result.issues if i["rule"] == "too_tall"]
    assert result.summary()["size_mm"][1] <= 135.5
    # At their natural heights the same panels do not fit.
    m._min_height_mm = c._min_height_mm = None
    natural = fm.explain(T, m, c, layout=[["a"], ["b"]], subtitle=long, note=long, source="s")
    assert [i for i in natural.issues if i["rule"] == "too_tall"]


def test_too_tall_names_the_tallest_panel_and_a_concrete_fix() -> None:
    big = fm.compare({f"item {i}": i + 1 for i in range(20)}, label="y", title="Big")
    small = [fm.compare({f"x{i}": i + 1 for i in range(8)}, label="y", title="s") for _ in range(2)]
    result = fm.explain(T, small[0], big, small[1], layout=[["a"], ["b"], ["c"]])
    tall = [i for i in result.issues if i["rule"] == "too_tall"]
    assert len(tall) == 1
    assert "tallest is panel b (compare)" in tall[0]["message"]
    assert "minimum readable height" in tall[0]["message"]
    hint = tall[0]["fix_hint"]
    assert "drop panel b" in hint.lower() and "split the figure into two" in hint


def test_change_in_a_narrow_column_wraps_and_drops_before_raising() -> None:
    _m, slope = _matrix_and_change()
    side = fm.compare({"x": 1.0, "y": 2.0}, label="v", title="t")
    wide = fm.explain(T, side, slope, layout=[["a", "b"]])
    assert "68.3  code (+3.9)" in _texts(wide, "b")
    narrow = fm.explain(T, side, slope, layout=[["a", "a", "b"]])
    texts = _texts(narrow, "b")
    assert "68.3  (+3.9)\ncode" in texts  # the name wraps under its value
    assert "64.4" not in texts  # the left-hand values give way; the facts keep them
    assert any("28.6% → 45.4%" in f for f in slope.facts)
    with pytest.raises(fm.ExplainError) as err:
        fm.explain(T, side, slope, layout=[["a", "a", "a", "b"]])
    assert "need at least a third of the width" in err.value.message
    assert 'layout=[["a", "a", "b"]]' in err.value.fix_hint
    assert err.value.rule == "panel_too_small"


def test_share_label_highlight_fact_and_long_names() -> None:
    parts = {"renewable (wind, solar, hydro)": 177.0, "fossil (gas, coal, oil)": 246.0, "nuclear": 94.0}
    panel = fm.share(parts, label="Share of generation", unit="TWh", highlight="nuclear")
    assert panel.label == "Share of generation (517 TWh in all)"
    assert fm.share(parts, label="generation").label.startswith("Share of generation (")
    assert "nuclear: 18% (94 TWh)" in panel.facts
    long = "Interconnector imports from the neighbouring northern transmission region"
    side = fm.compare({"a": 1.0, "b": 2.0}, label="x", title="t")
    wrapped = fm.explain(T, side, fm.share({**parts, "imports from the north": 12.0}, label="g"))
    assert not [i for i in wrapped.issues if i["rule"] == "names_truncated"]
    assert "imports from the\nnorth" in [t.get_text() for t in wrapped["b"].get_yticklabels()]
    cut = fm.explain(T, side, fm.share({**parts, long: 12.0}, label="g"))
    warned = [i for i in cut.issues if i["rule"] == "names_truncated"]
    assert len(warned) == 1 and long in warned[0]["message"]
    # A long first word is cut on line one: that is reported too, never silent.
    word = fm.explain(T, side, fm.share({**parts, "Supercalifragilisticexpialidocious grid": 9.0}))
    assert [i for i in word.issues if i["rule"] == "names_truncated"]


def test_relate_groups_lead_with_per_group_r_and_slope_cis() -> None:
    x, y, g = _two_groups()
    facts = fm.relate(x, y, groups=g, fit=True, x_label="Area (µm²)", y_label="s", unit="µm/min").facts
    assert facts[0].startswith("wild type: r = ") and facts[1].startswith("knockout: r = ")
    pooled = [i for i, f in enumerate(facts) if f.startswith("pooled across groups: r = ")]
    assert pooled and pooled[0] > 1
    assert facts[pooled[0]].endswith("(mixes groups; see per-group r)")
    assert not any(f.startswith("Pearson r") for f in facts)
    # The slope CI uses t with n - 2 df (14 points per group: 12 df, t = 2.179).
    xs, ys = np.array(x[:14]), np.array(y[:14])
    m, b = np.polyfit(xs, ys, 1)
    se = np.sqrt(((ys - (m * xs + b)) ** 2).sum() / 12 / ((xs - xs.mean()) ** 2).sum())
    lo, hi = m - 2.179 * se, m + 2.179 * se
    ci = next(f for f in facts if f.startswith("wild type: slope"))
    sig = explainer._sig_text
    assert ci == f"wild type: slope {sig(m)} (95% CI {sig(lo)}–{sig(hi)}) µm/min per µm²"


def test_t_quantile_is_exact_to_30_df_and_within_2_percent_beyond() -> None:
    exact = {1: 12.706, 10: 2.228, 30: 2.042, 40: 2.021, 60: 2.000, 120: 1.980, 10_000: 1.960}
    for df, t in exact.items():
        assert abs(explainer._t975(df) - t) / t < 0.002


def test_crossings_within_noise_are_not_reported() -> None:
    x = [0.1, 0.3, 1, 3, 10, 30, 100]
    a = [-1.0, 1.0, 2.0, 20.0, 60.0, 90.0, 99.0]
    b = [1.0, -1.0, 0.5, 3.0, 15.0, 40.0, 80.0]
    facts = fm.trend(x, {"a": a, "b": b}, log_x=True, label="inhibition", unit="%").facts
    assert not any("cross" in f for f in facts), facts
    # A real flip (beyond 3% of the range on both sides) is still reported.
    c = [10.0, -10.0, 0.0, 3.0, 15.0, 40.0, 80.0]
    real = fm.trend(x, {"a": a, "c": c}, log_x=True, label="inhibition", unit="%").facts
    assert any("cross" in f for f in real)
    # Reference crossings: a flat series jittering about the line does not "cross" it.
    flat = fm.trend(x, {"flat": [0.5, -0.5, 0.4, -0.3, 0.2, 0.1, 99.0]}, reference=0.0).facts
    assert not any("crosses 0" in f for f in flat)
    # With replicates, a gap inside the 95% half-width of a difference of means is noise.
    # (Replicate s.d. 3, n = 3: the 95% half-width of a difference of means is 4.8.)
    pts = {
        "p": [[v - 3, v, v + 3] for v in [-1.6, 2.9, 2.7, 18, 47, 70, 92]],
        "q": [[v - 3, v, v + 3] for v in [1.8, -0.8, 0.9, -1.7, 3.9, 15, 40]],
    }
    rep = fm.trend(x, points=pts, log_x=True, label="inhibition", unit="%").facts
    assert not any("first crosses" in f for f in rep), rep
    lone = fm.trend(x, {"p": [-1.6, 2.9, 2.7, 18, 47, 70, 92], "q": [1.8, -0.8, 0.9, -1.7, 3.9, 15, 40]})
    assert any("first crosses" in f for f in lone.facts)  # 3.4 and 3.7 apart: over 3% of 94


def test_a_spike_is_stated_against_the_median_and_on_its_event_day() -> None:
    days = [f"2026-11-{d:02d}" for d in range(1, 22)]
    pay = [8e-5] * 21
    pay[12] = 2.09e-2
    other = [3e-4 + 1e-5 * (i % 3) for i in range(21)]
    panel = fm.trend(
        days, {"payments": pay, "search": other}, log=True, highlight="payments",
        events={"2026-11-13": "spike"}, label="error rate",
    )
    # The event marks the spike: one "usual" level (the median before it), not two.
    assert not any("its median" in f for f in panel.facts)
    unmarked = fm.trend(days, {"payments": pay, "search": other}, log=True, highlight="payments")
    assert f"payments: peak 2.09{TIMES}10⁻² on 2026-11-13, 261{TIMES} its median" in unmarked.facts
    event = next(f for f in panel.facts if "before spike" in f)
    assert event.endswith(f"; on the spike day 2.09{TIMES}10⁻², 261{TIMES} the median before")
    linear = fm.trend([1, 2, 3, 4, 5, 6], {"a": [2.0, 2.1, 1.9, 11.0, 2.0, 2.2]}).facts
    assert f"a: peak 11.0 at 4, 5.4{TIMES} its median" in linear
    assert not any("its median" in f for f in fm.trend([1, 2, 3], {"a": [2.0, 3.0, 4.0]}).facts)


def test_matrix_states_column_means_and_the_outlier_cell() -> None:
    m, _c = _matrix_and_change()
    facts = m.facts
    assert any(f.startswith("highest row mean: English") for f in facts)
    assert any(f.startswith("lowest row mean: Swahili") for f in facts)
    assert any(f.startswith("highest column mean: ") for f in facts)
    assert any(f.startswith("lowest column mean: QA (72.5%)") for f in facts)
    outlier = next(f for f in facts if f.startswith("outlier: "))
    assert outlier.startswith(f"outlier: Swahili {TIMES} math = 45.4%, 19.6 points below the next-lowest")
    # No cell stands apart in a smooth grid; a symmetric matrix has no separate column means.
    smooth = fm.matrix([[1, 2, 3], [2, 3, 4], [3, 4, 5]], rows=["a", "b", "c"], cols=["x", "y", "z"])
    assert not any(f.startswith("outlier") for f in smooth.facts)
    names = ["p", "q", "r"]
    corr = fm.matrix([[1, 0.2, 0.3], [0.2, 1, 0.4], [0.3, 0.4, 1]], rows=names, cols=names)
    assert not any("column mean" in f for f in corr.facts)


def test_grey_context_replicates_stay_visible() -> None:
    x = [1, 2, 3, 4]
    pts = {name: [[v - 1, v, v + 1] for v in base] for name, base in
           (("hit", [1, 5, 9, 12]), ("ctrl", [1, 2, 2, 3]), ("other", [2, 2, 3, 3]))}
    result = fm.explain(T, fm.trend(x, points=pts, highlight="hit", label="y"))
    grey = to_hex(result.theme.context_line)
    alphas = [
        c.get_alpha()
        for c in result["a"].collections
        if len(c.get_offsets()) == 12 and to_hex(c.get_facecolor()[0][:3]) == grey
    ]
    assert len(alphas) == 2 and min(alphas) >= 0.6


def _too_many(kind: str) -> None:
    many = {f"i{k}": float(k + 1) for k in range(30)}
    if kind == "compare":
        fm.compare(many)
    elif kind == "highlight":
        fm.compare({"a": 1, "b": 2, "c": 3, "d": 4}, highlight=["a", "b", "c", "d"])
    elif kind == "series":
        fm.trend([1, 2], {f"s{k}": [1.0, 2.0] for k in range(5)})
    elif kind == "facets":
        fm.trend([1, 2], {f"s{k}": [1.0, 2.0] for k in range(13)}, facet=True)
    elif kind == "change":
        fm.change(dict(list(many.items())[:15]), dict(list(many.items())[:15]))
    elif kind == "groups":
        fm.distribution({f"g{k}": [1.0, 2.0, 3.0] for k in range(9)})
    elif kind == "relate":
        fm.relate(list(range(10)), list(range(10)), groups=list("abcde") * 2, x_label="x", y_label="y")
    elif kind == "matrix":
        fm.matrix(np.ones((17, 2)), rows=[f"r{k}" for k in range(17)], cols=["a", "b"])
    elif kind == "panels":
        fm.explain(T, *[fm.compare({"a": 1.0}) for _ in range(7)])


@pytest.mark.parametrize(
    ("kind", "limit"),
    [("compare", "20"), ("highlight", "3"), ("series", "4"), ("facets", "12"), ("change", "14"),
     ("groups", "8"), ("relate", "4"), ("matrix", "16"), ("panels", "6")],
)
def test_every_size_limit_error_names_its_limit_and_an_alternative(kind: str, limit: str) -> None:
    with pytest.raises(fm.ExplainError) as err:
        _too_many(kind)
    hint = err.value.fix_hint
    assert f"at most {limit}" in hint.lower() or f"most {limit}" in hint, hint
    assert ", or " in hint or "; " in hint or ": " in hint


# Cycle 2 (benchmark run 3) --------------------------------------------------- #


def _latency_groups() -> dict[str, list[float]]:
    rng = np.random.default_rng(5)
    return {
        "control": rng.normal(424, 60, 40).tolist(),
        "new flow": rng.normal(341, 60, 40).tolist(),
        "cached": rng.normal(300, 60, 40).tolist(),
    }


def test_alt_text_covers_every_group_not_only_the_baseline() -> None:
    groups = _latency_groups()
    alt = fm.explain(T, fm.distribution(groups, baseline="control", unit="ms")).alt_text
    for name in groups:
        assert f"{name}: median " in alt, alt
    assert "new flow vs control: median " in alt and "cached vs control: median " in alt
    # A highlight with a baseline: the highlighted group and the baseline.
    one = fm.explain(
        T, fm.distribution(groups, baseline="control", highlight="new flow", unit="ms")
    ).alt_text
    assert "control: median " in one and "new flow: median " in one
    assert "cached: median " not in one
    # No highlight, no baseline: every group.
    plain = fm.explain(T, fm.distribution(groups, unit="ms")).alt_text
    assert all(f"{name}: median " in plain for name in groups)


def test_alt_text_of_the_other_forms_names_every_series_or_highlight() -> None:
    x = [1, 2, 3, 4]
    series = {"ctrl": [1.0, 2.0, 3.0, 4.0], "y": [2.0, 2.0, 3.0, 3.0], "z": [1.0, 1.0, 1.0, 2.0]}
    trend_alt = fm.explain(T, fm.trend(x, series, baseline="ctrl", label="v")).alt_text
    assert all(f"{name}: " in trend_alt for name in series)
    cmp_alt = fm.explain(
        T, fm.compare({"ctrl": 3.0, "b": 2.0, "c": 1.0}, baseline="ctrl", highlight="b", unit="ms")
    ).alt_text
    assert "b 2 ms vs ctrl 3 ms" in cmp_alt and "lowest: c 1 ms" in cmp_alt
    xs, ys, gs = _two_groups()
    rel_alt = fm.explain(
        T, fm.relate(xs, ys, groups=gs, x_label="Area", y_label="Speed", fit=True)
    ).alt_text
    assert "wild type: r = " in rel_alt and "knockout: r = " in rel_alt
    assert "pooled across groups" in rel_alt
    chg_alt = fm.explain(
        T, fm.change({"a": 1.0, "b": 2.0, "c": 3.0}, {"a": 2.0, "b": 1.5, "c": 6.0}, highlight="b")
    ).alt_text
    assert "largest change: c" in chg_alt and "b: 2.0 → 1.5" in chg_alt


def test_a_long_unit_is_warned_and_facts_keep_working() -> None:
    days = [f"2026-11-{d:02d}" for d in range(1, 8)]
    result = fm.explain(
        T, fm.trend(days, {"payments": [1e-4, 1e-4, 2e-4, 1e-4, 1e-4, 1e-4, 1e-4]},
                    unit="fraction of requests", label="error rate")
    )
    issue = next(i for i in result.issues if i["rule"] == "unit_is_long")
    assert issue["severity"] == "warning" and issue["panel"] == "a"
    assert "label=" in issue["fix_hint"] and "(ms, %, mg/L)" in issue["fix_hint"]
    assert result.panels["a"].facts and result.ok
    # Symbols and short two-word units are fine.
    for unit in ("ms", "%", "mg/L", "req/s", "kg CO2"):
        assert not any(i["rule"] == "unit_is_long" for i in fm.compare({"a": 1.0}, unit=unit).issues)
    long_chars = fm.compare({"a": 1.0, "b": 2.0}, unit="microsiemens/cm²")
    assert [i["rule"] for i in long_chars.issues] == []  # 16 characters: still a symbol
    assert any(
        i["rule"] == "unit_is_long" for i in fm.compare({"a": 1.0}, unit="kWh per household").issues
    )


def test_an_event_marked_spike_has_one_usual_level() -> None:
    days = [f"2026-11-{d:02d}" for d in range(1, 22)]
    pay = [7.7e-5 + 1e-6 * (i % 4) for i in range(21)]
    pay[12] = 2.09e-2
    facts = fm.trend(
        days, {"payments": pay}, log=True, events={"2026-11-13": "payments spike"},
        label="error rate",
    ).facts
    assert not any("its median" in f for f in facts)
    assert not any("the first value" in f for f in facts)
    spike = [f for f in facts if "the median before" in f]
    assert len(spike) == 1 and "on the payments spike day 2.09" in spike[0]
    # An event elsewhere does not mark the spike: the whole-period line stays.
    elsewhere = fm.trend(
        days, {"payments": pay}, log=True, events={"2026-11-05": "deploy"}, label="error rate"
    ).facts
    assert any("its median" in f for f in elsewhere)


def test_log_compare_states_a_highlight_against_a_reference_as_an_unsigned_ratio() -> None:
    facts = fm.compare(
        {"a": 7.02, "b": 0.39, "c": 2.0}, log=True, reference=(1, "no change"),
        highlight=["a", "b"], unit=TIMES,
    ).facts
    a = next(f for f in facts if f.startswith("a: "))
    b = next(f for f in facts if f.startswith("b: "))
    assert a.endswith(f"; 7.0{TIMES} no change (1{TIMES})"), a
    assert b.endswith(f"; 0.39{TIMES} no change (1{TIMES})"), b
    assert not any("vs no change" in f or f"+6.02{TIMES}" in f for f in facts)
    # Linear compare keeps the signed difference.
    lin = fm.compare({"a": 120, "b": 300}, highlight="b", reference=(100, "limit"), unit="N")
    assert any("+200 N vs limit (100 N)" in f for f in lin.facts)


def test_a_spread_has_no_sign_and_is_in_points_for_percent() -> None:
    pct = fm.compare(
        {"Lab": -29.0, "Lib": -18.1, "Gym": -2.9}, unit="%", fmt="{:+.0f}%"
    ).facts
    assert "range: −29% to −3% (spread 26 points)" in pct
    ms = fm.compare({"a": -29.0, "b": -18.1, "c": -2.9}, unit="ms", fmt="{:+.1f}").facts
    assert any(f.endswith("(spread 26.1 ms)") for f in ms), ms
    # A gap between two trend lines is a width too.
    gap = fm.trend([1, 2], {"a": [1.0, 5.0], "b": [1.0, 2.0]}, unit="ms", fmt="{:+.1f}").facts
    assert any("a is 3.0 ms above b" in f for f in gap), gap


@pytest.mark.parametrize(
    ("x_unit", "per"),
    [("µm⁻½", "MPa·µm½"), ("K⁻¹", "MPa·K"), ("s⁻¹", "MPa·s"), ("1/s", "MPa·s"), ("µm", "MPa per µm")],
)
def test_a_slope_against_a_reciprocal_unit_is_the_product(x_unit: str, per: str) -> None:
    xs, ys, gs = _two_groups()
    facts = fm.relate(
        xs, ys, groups=gs, x_label="Grain size", y_label="Yield", unit="MPa", x_unit=x_unit,
        fit=True,
    ).facts
    slopes = [f for f in facts if ": slope " in f]
    assert slopes and all(f.endswith(f") {per}") for f in slopes), slopes
    assert explainer._reciprocal_unit("kJ mol⁻¹") is None  # a compound unit is not one


@pytest.mark.parametrize("unit", [TIMES, "x", "fold", None])
def test_log_distribution_of_fold_changes_reads_as_ratios(unit: str | None) -> None:
    rng = np.random.default_rng(1)
    groups = {"p53": np.exp(rng.normal(0.9, 0.3, 8)), "prolif": np.exp(rng.normal(-0.6, 0.3, 8))}
    panel = fm.distribution(groups, log=True, unit=unit, label="fold change", highlight="p53")
    centre = panel.facts[0]
    assert centre.startswith("p53: median ") and f"{TIMES}, middle half" in centre, centre
    assert f"{TIMES} {TIMES}" not in " ".join(panel.facts) and " fold" not in centre
    result = fm.explain(T, panel)
    assert any(t.endswith(TIMES) for t in _texts(result))
    # The spec keeps the unit as given and renders back the same facts.
    spec = result.to_spec()["panels"][0]
    assert spec.get("unit") == unit
    assert fm.panel_from_spec(spec).facts == panel.facts
    # A log-transformed label is not a raw ratio: no "×".
    logged = fm.distribution(groups, log=True, label="log2 fold change")
    assert TIMES not in logged.facts[0]


# Cycle 3: facts for the claims agents computed by hand ----------------------- #


def _ratios_with_reference() -> fm.Panel:
    return fm.compare(
        {"L1": 1.05, "L2": 0.97, "L3": 1.26, "L4": 1.17, "L5": 1.46},
        error={"L1": (0.87, 1.22), "L2": (0.85, 1.10), "L3": (1.05, 1.42),
               "L4": (1.03, 1.39), "L5": (1.16, 1.73)},
        error_label="95% CI", reference=(1, "same as North"), unit=TIMES, log=True,
        sort=False, highlight=["L3", "L4", "L5"], fmt=".2f",
    )


def test_intervals_with_a_reference_are_stated_against_it() -> None:
    facts = _ratios_with_reference().facts
    l3 = next(f for f in facts if f.startswith("L3: "))
    assert l3.endswith(f"; 95% CI 1.05\N{EN DASH}1.42{TIMES}, above 1{TIMES} (same as North)"), l3
    assert "same as North (1" not in l3  # not "1.3× same as North (1.00×)"
    assert (
        f"intervals against 1{TIMES} (same as North): entirely above for L5, L3 and L4; "
        "include it for L1 and L2"
    ) in facts
    assert not any("overlap" in f for f in facts)  # never against the first item
    lin = fm.compare(
        {"a": 3.0, "b": 1.0}, error=0.5, error_label="CI", reference=(2.0, "limit"),
        highlight="b",
    ).facts
    b = next(f for f in lin if f.startswith("b: "))
    assert "vs limit" in b and b.endswith("; CI 0.5\N{EN DASH}1.5, below 2 (limit)"), b


def test_a_highlighted_interval_names_what_it_overlaps_and_what_not() -> None:
    facts = fm.compare(
        {"Legal": 72, "Sales": 54, "Ops": 55, "Support": 42},
        error={"Legal": (60, 82), "Sales": (46, 62), "Ops": (41, 67), "Support": (32, 52)},
        error_label="95% CI", unit="%", highlight="Support",
    ).facts
    assert (
        "Support 32\N{EN DASH}52% overlaps Ops 41\N{EN DASH}67% and Sales 46\N{EN DASH}62%; "
        "does not overlap Legal 60\N{EN DASH}82%"
    ) in facts
    alone = fm.compare(
        {"a": 10, "b": 1, "c": 2}, error={"a": (9, 11), "b": (0, 3), "c": (1, 4)},
        error_label="CI", highlight="a",
    ).facts
    assert "a 9\N{EN DASH}11 does not overlap c 1\N{EN DASH}4 or b 0\N{EN DASH}3" in alone


def test_compare_n_is_drawn_under_names_in_the_facts_and_in_the_spec() -> None:
    values = {"Support": 42.0, "Legal": 72.0, "Sales": 54.0}
    counts = {"Support": 84, "Legal": 61, "Sales": 146}
    panel = fm.compare(values, n=counts, unit="%", highlight="Support")
    assert "highest: Legal 72% (n=61)" in panel.facts
    assert any(f.startswith("Support: 42% (n=84; rank 3 of 3") for f in panel.facts)
    result = fm.explain(T, panel)
    assert {"n=84", "n=61", "n=146"} <= set(_texts(result))
    assert not result.issues
    spec = result.to_spec()["panels"][0]
    assert spec["n"] == counts
    assert fm.panel_from_spec(spec).facts == panel.facts
    # A list follows the order of values; names stay names.
    listed = fm.compare(values, n=[84, 61, 146], unit="%")
    assert listed.spec["n"] == counts
    with pytest.raises(fm.ExplainError, match="not in values"):
        fm.compare(values, n={"Support (n=84)": 84})
    with pytest.raises(fm.ExplainError, match="not a count"):
        fm.compare(values, n={"Support": 8.5})
    with pytest.raises(fm.ExplainError, match="3 counts for"):
        fm.compare({"a": 1, "b": 2}, n=[1, 2, 3])


def test_values_of_both_signs_are_placed_against_zero() -> None:
    budget = {"Libraries": -18.0, "Parks": -11.0, "Police": -2.0, "Admin": 5.0,
              "Fire": 1.2, "Transit": 3.1, "Housing": 14.1}
    facts = fm.compare(budget, unit="%", highlight=["Libraries", "Parks", "Housing"]).facts
    libraries = next(f for f in facts if f.startswith("Libraries: "))
    assert libraries.endswith("; furthest of the 3 below zero"), libraries
    assert "vs Admin" not in " ".join(facts)  # not against the next unhighlighted item
    assert any(f.startswith("Parks: ") and "2nd furthest of the 3 below zero" in f for f in facts)
    assert any(f.startswith("Housing: +14.1% ") and "furthest of the 4 above zero" in f
               for f in facts)
    assert "the other 4 are within \N{MINUS SIGN}2.0% to +5.0%" in facts
    # One-signed values keep the comparison with the next item.
    same_sign = fm.compare({"a": 5.0, "b": 3.0, "c": 1.0}, highlight="c").facts
    assert any("vs a (5)" in f for f in same_sign), same_sign


def test_zero_false_drops_ratios_and_keeps_differences() -> None:
    peaks = {"reference": 520.1, "200 C": 523.1, "400 C": 541.4}
    facts = fm.compare(peaks, zero=False, unit="nm", fmt=".0f", baseline="reference").facts
    joined = " ".join(facts)
    assert "ratio" not in joined and TIMES not in joined and "%" not in joined, facts
    assert "range: 520 nm to 541 nm (spread 21 nm)" in facts
    assert "400 C 541 nm vs reference 520 nm: +21 nm" in facts
    # A log axis keeps them (ratios are its point).
    assert any("ratio" in f for f in fm.compare(peaks, zero=False, log=True).facts)


def test_log_log_trend_reports_each_power_law_exponent() -> None:
    rng = np.random.default_rng(4)
    flops = np.logspace(18, 22, 9)
    curves = {
        name: 30 * flops ** (-b) * np.exp(rng.normal(0, 0.004, flops.size))
        for name, b in {"moe": 0.063, "dense": 0.050, "recurrent": 0.031}.items()
    }
    facts = fm.trend(flops, curves, log=True, log_x=True, highlight="moe").facts
    powers = [f for f in facts if " \N{PROPORTIONAL TO} x^" in f]
    assert [f.split(":")[0] for f in powers] == ["moe", "dense", "recurrent"]
    m = re.search(
        r"x\^(\S+) \(95% CI (\S+) to (\S+)\), R² = (\S+)", powers[0].replace("\N{MINUS SIGN}", "-")
    )
    assert m, powers[0]
    exp, lo, hi, r2 = map(float, m.groups())
    assert lo < -0.063 < hi and lo < exp < hi and r2 > 0.99
    # A linear x axis keeps the log10(y) slope instead.
    assert not any("\N{PROPORTIONAL TO}" in f for f in fm.trend([1, 2, 3, 4], {"a": [1, 2, 4, 8]},
                                                                  log=True).facts)


def test_highlighted_trend_summarises_its_grey_context_series() -> None:
    days = [f"2026-11-{d:02d}" for d in range(1, 22)]
    pay = [8e-3] * 21
    pay[12] = 2.09
    others = {f"s{k}": [0.03 * (1 + 0.1 * k) * (1.5 if i == 5 else 1.0) for i in range(21)]
              for k in range(4)}
    spiky = fm.trend(days, {"payments": pay, **others}, log=True, highlight="payments",
                     events={"2026-11-13": "spike"}, unit="%").facts
    assert f"the other 4 peak within 1.5{TIMES} of their own medians" in spiky
    calm = fm.trend([1, 2, 3], {"a": [1.0, 2.0, 4.0], "b": [10.0, 10.0, 11.0],
                                "c": [10.0, 10.0, 9.5]}, highlight="a").facts
    assert "the other 2 change by \N{MINUS SIGN}5.0% to +10% from first to last value" in calm
    pts = fm.trend([1, 2], {"a": [1.0, 5.0], "b": [40.0, 42.0]}, unit="%", highlight="a").facts
    assert "the other series, b, changes by +2 points from first to last value" in pts


def test_every_value_in_a_fact_carries_its_unit() -> None:
    days = [f"2026-11-{d:02d}" for d in range(1, 8)]
    trend_facts = fm.trend(days, {"payments": [0.25, 0.3, 2.09, 0.28, 0.26, 0.27, 0.31]},
                           unit="%").facts
    assert any("peak 2.09% on 2026-11-03" in f or "peak 2.09% at 2026-11-03" in f
               for f in trend_facts), trend_facts
    assert trend_facts[0].startswith("payments: 0.25% \N{RIGHTWARDS ARROW} 0.31%"), trend_facts
    crossing = fm.trend([0, 10, 20], {"up": [0, 40, 80]}, reference=(60, "goal"), unit="ms").facts
    assert "up crosses 60 ms (goal) at about 15" in crossing
    dist = fm.distribution(
        {"a": [10, 11, 12, 13, 14, 15, 40], "b": [1, 2, 3, 4, 5]}, unit="ms", highlight="a"
    )
    a = dist.facts[0]
    assert "middle half 11.5\N{EN DASH}14.5 ms" in a and "range 10\N{EN DASH}40 ms" in a, a
    assert any("40 ms (median 13.0 ms)" in f for f in dist.facts), dist.facts
    assert any("lowest 10 ms" in f and "highest 5 ms" in f for f in dist.facts), dist.facts
    money = fm.compare({"a": 1.2, "b": 1.5}, error=0.1, error_label="CI", unit="$").facts
    assert "a $1.1\N{EN DASH}$1.3 does not overlap b $1.4\N{EN DASH}$1.6" in money, money


def test_relate_log_axes_keep_highlighted_extreme_points_in_view() -> None:
    fig = fm.explain(
        "Rate scales as mass^0.75 across six decades",
        fm.relate(
            [0.002, 0.02, 0.2, 2.0, 20.0],
            [0.005, 0.05, 0.5, 5.0, 50.0],
            x_label="Conc (µM)",
            y_label="Signal",
            log_x=True,
            log_y=True,
            fit=True,
            names=["p1", "p2", "p3", "p4", "p5"],
            highlight=["p1", "p5"],
            title="Both extremes stay visible",
        ),
        source="synthetic",
    )
    ax = fig["a"]
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    assert x0 <= 0.002 and x1 >= 20.0, (x0, x1)
    assert y0 <= 0.005 and y1 >= 50.0, (y0, y1)
    assert fig.summary()["ok"] is True


def test_latex_dollar_markup_warns_without_flagging_currency() -> None:
    bad = fm.explain(
        r"Slope fits cleanly ($R^2 = 0.99$) across $\mu\mathrm{M}$ doses",
        fm.compare({"a": 1.0, "b": 2.0}, label="Rate", unit="µM/s", title="Linear"),
    )
    rules = [i["rule"] for i in bad.issues]
    assert "latex_markup" in rules
    money = fm.explain(
        "Revenue grew from $10M to $25M after launch",
        fm.compare({"before": 10.0, "after": 25.0}, label="Revenue", unit="$", title="Up 2.5×"),
    )
    assert "latex_markup" not in [i["rule"] for i in money.issues]


def test_share_highlight_explains_items_folded_into_other() -> None:
    parts = {f"Cat {i}": 20 - i for i in range(1, 10)} | {"Tiny Z": 1}
    with pytest.raises(fm.ExplainError) as err:
        fm.share(parts, top=5, highlight="Tiny Z")
    assert "folded into 'Other (5)'" in err.value.message
    assert "top=10" in err.value.fix_hint


def test_signed_compare_and_distribution_avoid_misleading_ratios_and_negative_dashes() -> None:
    cmp = fm.compare(
        {"search": -190.0, "checkout": -15.0, "billing": 1.0, "auth": 2.0},
        error={"search": (-200.0, -180.0), "checkout": (-20.0, -10.0), "billing": (0.0, 2.0), "auth": (1.0, 3.0)},
        error_label="95% CI",
        unit="ms",
        highlight="search",
    )
    assert not any("next highest" in f for f in cmp.facts), cmp.facts
    assert any("\N{MINUS SIGN}200 to \N{MINUS SIGN}180 ms" in f for f in cmp.facts), cmp.facts
    dist = fm.distribution(
        {
            "Control": [-0.2, -0.1, 0.0, 0.1, 0.2, 0.3],
            "Variant": [-3.0, 1.2, 4.5, 7.8, 12.0, 2.1],
        },
        baseline="Control",
        highlight="Variant",
        unit="pts",
    )
    vs = next(f for f in dist.facts if f.startswith("Variant vs Control:"))
    assert "%" not in vs, vs


def test_trend_points_label_customises_subtitle_facts_and_spec_roundtrip(tmp_path) -> None:
    fig = fm.explain(
        "Average solve time fell from 30 s to 18 s",
        fm.trend(
            ["r1", "r2"],
            points={"agent": [[25, 32, 33], [16, 18, 20]]},
            points_label="tasks",
            label="Solve time",
            unit="s",
            title="Each dot is one task",
        ),
        source="synthetic",
    )
    assert any("3 tasks per x" in f for f in fig.summary()["panels"][0]["facts"])
    assert any("dots: tasks" in t.get_text() for t in fig.fig.texts)
    out = tmp_path / "tasks.png"
    fig.save(out)
    assert fm.load(out).to_spec()["panels"][0]["points_label"] == "tasks"


def test_matrix_nan_cells_show_em_dash_marker() -> None:
    fig = fm.explain(
        "Model C leads on math (91%) and has no multimodal score",
        fm.matrix(
            [[78.0, 64.0], [91.0, np.nan]],
            rows=["A", "C"],
            cols=["math", "multimodal"],
            label="Score",
            unit="%",
            title="Scores",
        ),
        source="synthetic",
    )
    assert "\N{EM DASH}" in [t.get_text() for t in fig["a"].texts]


def test_histogram_alias_facts_spec_roundtrip_and_validation(tmp_path) -> None:
    rng = np.random.default_rng(12)
    single_vals = np.concatenate([rng.normal(20, 3, 60), rng.normal(42, 4, 40)]).tolist()
    fig = fm.explain(
        "Response times split into two modes around 20 ms and 42 ms",
        fm.histogram(
            single_vals,
            bins=14,
            label="Response time",
            unit="ms",
            reference=(35, "SLA"),
            title="Two distinct latency peaks",
        ),
        source="synthetic",
    )
    summary = fig.summary()
    assert summary["ok"] is True and summary["issues"] == []
    facts = summary["panels"][0]["facts"]
    assert any("binned into 14 bins" in f for f in facts), facts
    assert any("peak bin" in f for f in facts), facts
    assert any("above 35 ms (SLA)" in f for f in facts), facts

    out = tmp_path / "hist.png"
    fig.save(out, write_spec=True)
    spec = fm.load(out).to_spec()
    assert spec["panels"][0]["bins"] == 14
    assert fm.explain_from_spec(spec).summary()["ok"] is True

    # JSON spec with kind="histogram" also works directly
    hist_spec = {
        "takeaway": "Scores cluster near 75 pts",
        "panels": [
            {
                "kind": "histogram",
                "values": rng.normal(75, 8, 80).tolist(),
                "bins": "auto",
                "label": "Score",
                "unit": "pts",
                "title": "Single peak",
            }
        ],
    }
    assert fm.explain_from_spec(hist_spec).summary()["ok"] is True

    # Validation checks
    with pytest.raises(fm.ExplainError):
        fm.histogram(single_vals, bins=1)
    with pytest.raises(fm.ExplainError):
        fm.histogram({f"g{i}": rng.normal(i, 1, 20).tolist() for i in range(5)}, bins=10)


def test_summary_ship_distinguishes_advisories_from_visual_defects() -> None:
    # Advisory-only warning (many_items on 14 bars) is still ship=True
    good = fm.explain(
        "Item 13 is highest at 14 ms across 14 services",
        fm.compare({f"svc_{i}": float(i + 1) for i in range(14)}, label="Latency", unit="ms"),
        source="synthetic",
    )
    s_good = good.summary()
    assert s_good["ok"] is True
    assert any(i["rule"] == "many_items" for i in s_good["issues"])
    assert s_good["ship"] is True

    # Real visual defect (latex_markup) sets ship=False
    bad = fm.explain(
        r"Slope fits cleanly ($R^2 = 0.99$) with $\mu\mathrm{M}$ units",
        fm.compare({"a": 1.0, "b": 2.0}, label="Rate", unit="µM/s"),
        source="synthetic",
    )
    s_bad = bad.summary()
    assert s_bad["ok"] is True
    assert s_bad["ship"] is False


def test_lenient_mode_auto_recovers_soft_limits_and_separates_advisories(tmp_path) -> None:
    # Inside fm.lenient(): >4 trend series auto-facets, >20 compare items trims to 20,
    # >3 highlights trims to 3, baseline-in-highlight resolves, NaN drops, long takeaway wraps,
    # and narrow side-by-side matrix auto-stacks into full-width rows.
    with fm.lenient():
        p_trend = fm.trend(
            [1, 2, 3, 4],
            {f"s{i}": [i + 1, i + 2, i + 2.5, i + 4] for i in range(6)},
            label="Score",
            unit="%",
            title="Six series auto-faceted",
        )
        p_cmp = fm.compare(
            {**{f"item_{i}": float(i + 1) for i in range(25)}, "bad": float("nan")},
            highlight=["item_24", "item_23", "item_22", "item_21", "item_0"],
            baseline="item_0",
            label="Latency",
            unit="ms",
            title="Top 20 kept",
        )
        fig = fm.explain(
            "This is a deliberately verbose takeaway sentence with extra detail " * 3,
            p_trend,
            p_cmp,
            source="synthetic",
        )
    s = fig.summary()
    assert s["ok"] is True
    assert s["ship"] is True
    assert s["strict"] is False
    assert s["issues"] == []  # advisories separated out
    assert len(s["adjustments"]) >= 4
    assert any("facet=True" in a for a in s["adjustments"])
    assert any("trimmed 25 items" in a for a in s["adjustments"])

    # Auto-stacking narrow side-by-side matrix in strict=False
    vals = [[10, 20, 30, 40], [50, 60, 70, 80]]
    stacked = fm.explain(
        "Matrix auto-stacks to full width when side-by-side headers would collide",
        fm.matrix(
            vals,
            rows=["x", "y"],
            cols=["HotpotQAextended", "TriviaQAextended", "NaturalQuestions", "SciFactBench"],
            label="Accuracy",
            unit="%",
        ),
        fm.compare({"a": 1.0, "b": 2.0}, label="Count"),
        strict=False,
    )
    st_sum = stacked.summary()
    assert st_sum["ok"] is True and st_sum["ship"] is True
    assert stacked.layout == [["a"], ["b"]]
    assert any("stacked panels" in a for a in st_sum["adjustments"])

    # CLI --lenient renders a non-strict JSON spec with exit code 0
    import json

    from figmint.cli import main as cli_main

    spec_path = tmp_path / "messy.json"
    spec_path.write_text(
        json.dumps(
            {
                "takeaway": "",
                "panels": [
                    {
                        "kind": "trend",
                        "x": [1, 2, 3],
                        "series": {f"s{i}": [1 + i, 2 + i, 3 + i] for i in range(6)},
                        "title": "Six curves",
                        "label": "Score",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    out_png = tmp_path / "lenient.png"
    assert cli_main(["explain", str(spec_path), "--lenient", "--out", str(out_png)]) == 0
    assert out_png.exists()
