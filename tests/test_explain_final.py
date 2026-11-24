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
    value = float(crossing[0].rsplit(" ", 1)[1])
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
