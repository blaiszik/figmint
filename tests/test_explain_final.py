"""fm.explain: last-round fixes found by looking at the renders (package D)."""

from __future__ import annotations

import numpy as np
import pytest
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
    crossing = [f for f in facts if " crosses 50 (half-maximal) at about " in f]
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
