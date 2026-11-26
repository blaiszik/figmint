"""Package C: colour identity across panels, pinned colours, symbols and layout collisions."""

from __future__ import annotations

import itertools
import json

import numpy as np
import pytest
from matplotlib.collections import PathCollection
from matplotlib.colors import to_hex
from matplotlib.patches import Rectangle

import mintfig as mint
from mintfig.themes import THEMES


def _hex(color: object) -> str:
    return to_hex(color).upper()  # type: ignore[arg-type]


def _bar_colours(result: mint.Explanation, key: str) -> dict[str, str]:
    ax = result[key]
    names = [t.get_text() for t in ax.get_yticklabels()]
    bars = sorted(
        (p for p in ax.patches if isinstance(p, Rectangle) and p.get_height() < 1),
        key=lambda p: p.get_y(),
    )
    return {nm: _hex(bar.get_facecolor()) for nm, bar in zip(names, bars, strict=True)}


def _dot_colours(result: mint.Explanation, key: str) -> dict[str, str]:
    """compare() dot plot: one scatter whose points follow the y tick order."""
    ax = result[key]
    names = [t.get_text() for t in ax.get_yticklabels()]
    dots = next(c for c in ax.collections if isinstance(c, PathCollection))
    return {nm: _hex(c) for nm, c in zip(names, dots.get_facecolors(), strict=True)}


def _line_colours(result: mint.Explanation, key: str) -> dict[str, str]:
    return {
        line.get_label(): _hex(line.get_color())
        for line in result[key].get_lines()
        if not line.get_label().startswith("_")
    }


def _row_colours(result: mint.Explanation, key: str, names: list[str]) -> dict[str, str]:
    """distribution(): one scatter per row, in group order."""
    rows = [c for c in result[key].collections if isinstance(c, PathCollection)]
    return {nm: _hex(c.get_facecolors()[0]) for nm, c in zip(names, rows, strict=True)}


def _six(style: str = "mintfig") -> mint.Explanation:
    rng = np.random.default_rng(3)
    return mint.explain(
        "The new catalyst doubles yield without hurting selectivity",
        mint.compare({"new": 82, "ref": 41, "blank": 3}, label="Yield", unit="%", highlight="new"),
        mint.compare({"new": 96, "ref": 97, "blank": 50}, label="Selectivity", unit="%", zero=False),
        mint.trend(
            [0, 1, 2, 4, 8],
            {"new": [0, 30, 55, 75, 82], "ref": [0, 12, 22, 35, 41]},
            label="Yield",
            unit="%",
            x_label="Time (h)",
        ),
        mint.distribution(
            {"new": rng.normal(82, 3, 8), "ref": rng.normal(41, 4, 8)}, label="Yield", unit="%"
        ),
        mint.share({"product": 82, "byproduct A": 10, "unreacted": 8}, label="Mass", unit="%"),
        style=style,
        source="synthetic example data",
    )


@pytest.mark.parametrize("style", list(THEMES))
def test_an_entity_keeps_one_colour_in_every_panel(style: str) -> None:
    theme = THEMES[style]
    result = _six(style)
    new = theme.accent_colors[0].upper()
    a = _bar_colours(result, "a")
    c = _line_colours(result, "c")
    d = _row_colours(result, "d", ["new", "ref"])
    b = _dot_colours(result, "b")
    assert a["new"] == c["new"] == d["new"] == b["new"] == new
    ref = c["ref"]
    assert ref not in {new, theme.context_line.upper(), theme.default_color.upper()}
    assert d["ref"] == b["ref"] == ref
    # highlighted panel: an entity coloured elsewhere keeps its colour, the rest is context
    # grey; unhighlighted panel: non-entities grey
    assert a["ref"] == ref and a["blank"] == theme.context_fill.upper()
    assert b["blank"] != ref and b["blank"] != new
    # the uniform default colour stays the theme default and is not an entity colour
    assert set(_bar_colours(result, "e").values()) == {theme.default_color.upper()}


def test_ablation_variant_has_the_same_colour_in_dot_plot_and_trend() -> None:
    steps = np.arange(0, 2001, 250)
    series = {
        "full model": 0.82 * (1 - np.exp(-steps / 300)),
        "no retrieval": 0.74 * (1 - np.exp(-steps / 350)),
        "no fine-tune": 0.69 * (1 - np.exp(-steps / 420)),
    }
    result = mint.explain(
        "Removing retrieval costs 8 points of accuracy; removing fine-tuning costs 13",
        mint.compare(
            {"full model": 0.82, "no retrieval": 0.74, "no fine-tune": 0.69, "smaller": 0.78},
            error=0.02,
            error_label="95% CI",
            label="Test accuracy",
            highlight=["no retrieval", "no fine-tune"],
        ),
        mint.trend(steps, series, label="Validation accuracy", x_label="Step"),
    )
    dots = _dot_colours(result, "a")
    lines = _line_colours(result, "b")
    assert dots["no retrieval"] == lines["no retrieval"]
    assert dots["no fine-tune"] == lines["no fine-tune"]
    assert len(set(lines.values())) == 3


def test_single_panel_colours_are_unchanged() -> None:
    theme = THEMES["mintfig"]
    three = {"a": [1, 2, 3], "b": [2, 3, 1], "c": [3, 1, 2]}
    lines = _line_colours(mint.explain("Three series cross twice", mint.trend([1, 2, 3], three)), "a")
    assert [lines[k] for k in "abc"] == [c.upper() for c in theme.series_colors[:3]]
    bars = _bar_colours(
        mint.explain("Two items stand out", mint.compare({"x": 3, "y": 2, "z": 1}, highlight=["z", "x"])),
        "a",
    )
    assert bars["z"] == theme.accent_colors[0].upper()
    assert bars["x"] == theme.accent_colors[1].upper()
    plain = _bar_colours(mint.explain("x is the largest", mint.compare({"x": 3, "y": 2})), "a")
    assert set(plain.values()) == {theme.default_color.upper()}


def test_more_than_four_entities_warn_colour_reused() -> None:
    x = [1, 2, 3]
    result = mint.explain(
        "Five variants across two panels cannot all keep a colour",
        mint.trend(x, {"a": [1, 2, 3], "b": [2, 3, 4], "c": [3, 4, 5]}),
        mint.trend(x, {"d": [1, 2, 3], "e": [2, 3, 4]}),
    )
    issues = [i for i in result.issues if i["rule"] == "colour_reused_across_panels"]
    assert len(issues) == 1 and issues[0]["severity"] == "warning"
    assert "'e'" in issues[0]["message"]
    lines = _line_colours(result, "b")
    assert lines["d"] != lines["e"]  # still distinct within its own panel


def test_pinned_colours_follow_the_theme_palette_and_round_trip() -> None:
    for style, theme in THEMES.items():
        result = mint.explain(
            "No retrieval loses most of its accuracy by step 3",
            mint.trend([1, 2, 3], {"full model": [1, 2, 3], "no retrieval": [1, 1.5, 1.6]}),
            colors={"no retrieval": "green", "full model": "amber"},
            style=style,
        )
        lines = _line_colours(result, "a")
        assert lines["no retrieval"] == theme.series_colors[2].upper()
        assert lines["full model"] == theme.series_colors[3].upper()
    spec = result.to_spec()
    assert spec["colors"] == {"no retrieval": "green", "full model": "amber"}
    again = mint.load(json.loads(json.dumps(spec)))
    assert _line_colours(again, "a") == lines


def test_pinned_name_in_an_unhighlighted_compare_takes_its_colour() -> None:
    result = mint.explain(
        "No retrieval is the slowest variant on every benchmark",
        mint.compare({"no retrieval": 5, "full": 3, "small": 2}),
        colors={"no retrieval": "red"},
    )
    bars = _bar_colours(result, "a")
    assert bars["no retrieval"] == THEMES["mintfig"].series_colors[1].upper()
    assert bars["full"] == bars["small"] == THEMES["mintfig"].context_fill.upper()


@pytest.mark.parametrize(
    "colors",
    [{"a": "#FF0000"}, {"a": "purple"}, ["a"], {"a": "red", "b": "red"}],
)
def test_bad_colour_pins_are_explain_errors(colors: object) -> None:
    with pytest.raises(mint.ExplainError) as err:
        mint.explain("a rises fastest of all", mint.trend([1, 2], {"a": [1, 2]}), colors=colors)
    assert err.value.rule == "bad_colors"
    assert "blue" in err.value.fix_hint and "amber" in err.value.fix_hint


def test_colour_hint_on_a_form_mentions_pinning() -> None:
    with pytest.raises(mint.ExplainError) as err:
        mint.compare({"a": 1}, color="red")
    assert "colors=" in err.value.fix_hint


# --------------------------------------------------------------------------- #
# C2: scientific symbols
# --------------------------------------------------------------------------- #

SYMBOL_TAKEAWAY = "At 10¹⁷ cm⁻³ µ-mobility of H₂O films is ≈2× higher (ℏω ∝ T, Δ ≥ 5 Å)"


def _symbol_figure(style: str = "mintfig") -> mint.Explanation:
    return mint.explain(
        SYMBOL_TAKEAWAY,
        mint.compare(
            {"H₂O anneal": 5.2e-7, "N₂ anneal": 2.4e-7, "as grown (25 °C)": 1.1e-7},
            label="Conductivity σ",
            unit="µS/cm",
            highlight="H₂O anneal",
            title="Water anneal → 2× σ",
        ),
        mint.trend(
            [0, 1, 2, 4, 8],
            {"α phase": [1, 2, 4, 6, 7], "β′ phase": [1, 1.5, 2, 2.2, 2.4]},
            label="Rate k",
            unit="K⁻¹ s⁻¹",
            x_label="Dose (10¹⁵ cm⁻²)",
            title="α outpaces β′ (±0.3, ≤ 5%)",
        ),
        note="Errors ±1σ; T = 300 K; λ = 532 nm; 5′ and 3″ arcs; ∞ → limit; a·b ≤ c",
        source="synthetic example",
        style=style,
    )


def _drawn(result: mint.Explanation) -> list[str]:
    from matplotlib.text import Text

    return [t.get_text() for t in result.fig.findobj(Text) if t.get_text().strip()]


@pytest.mark.parametrize("style", list(THEMES))
def test_scientific_symbols_render_without_missing_glyphs(
    style: str, recwarn: pytest.WarningsRecorder, tmp_path: object
) -> None:
    result = _symbol_figure(style)
    summary = result.save(tmp_path / "sym.png")  # type: ignore[operator]
    assert not [i for i in summary["issues"] if i["rule"] == "glyph_missing"], summary["issues"]
    assert not [w for w in recwarn if "missing from" in str(w.message)]
    drawn = _drawn(result)
    # the micro sign is drawn as the upright Greek mu; script runs are one mathtext run
    assert not any("\N{MICRO SIGN}" in t for t in drawn)
    assert any("\N{GREEK SMALL LETTER MU}S/cm" in t for t in drawn)
    assert not any(ch in t for t in drawn for ch in "₀₁₂₃⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def test_scientific_symbols_with_only_dejavu_sans(monkeypatch: pytest.MonkeyPatch) -> None:
    import dataclasses

    from mintfig import specs

    monkeypatch.setitem(
        specs.JOURNALS,
        "screen",
        dataclasses.replace(specs.JOURNALS["screen"], font_family=("DejaVu Sans",)),
    )
    result = _symbol_figure()
    assert not [i for i in result.issues if i["rule"] == "glyph_missing"]


def test_script_runs_read_back_as_unicode() -> None:
    from mintfig import explainer

    drawn = explainer._plain("1.3×10⁻⁷ A in H₂O, cost $5", mint.themes.MINTFIG_THEME)
    assert "$^{" in drawn and "$_{" in drawn
    assert explainer._reader_text(drawn) == "1.3×10⁻⁷ A in H₂O, cost $5"
    # sketch keeps ASCII exponents (its font has no superscripts)
    assert explainer._plain("1.3×10⁻⁷ cm⁻³", mint.themes.SKETCH_THEME) == "1.3x10^-7 cm^-3"


def test_a_glyph_no_font_has_is_reported_not_printed(
    recwarn: pytest.WarningsRecorder, tmp_path: object
) -> None:
    result = mint.explain(
        "Sample 漢 leaks the most current of the three",
        mint.compare({"漢": 3.0, "B": 1.0, "C": 0.5}, label="Leakage", unit="nA"),
    )
    issues = [i for i in result.issues if i["rule"] == "glyph_missing"]
    assert len(issues) == 1 and issues[0]["severity"] == "warning"
    assert "U+6F22" in issues[0]["message"]
    assert "Replace" in issues[0]["fix_hint"]
    result.save(tmp_path / "g.png")  # type: ignore[operator]
    assert not [w for w in recwarn if "missing from" in str(w.message)]


def test_wrapped_title_with_scripts_fits_the_canvas() -> None:
    long = "Doping at 10¹⁷ cm⁻³ raises H₂O uptake 3× and K⁻¹ s⁻¹ rates in every film we grew"
    result = mint.explain(long, mint.compare({"a": 3, "b": 1}, label="Rate", unit="K⁻¹"))
    renderer = result.fig.canvas.get_renderer()
    width = result.fig.bbox.width
    for text in result.fig.texts:
        box = text.get_window_extent(renderer)
        assert box.x1 <= width - 1, text.get_text()


# --------------------------------------------------------------------------- #
# C3 / C5 / C7: collisions fixed by construction or reported
# --------------------------------------------------------------------------- #


def _visible_tick_boxes(result: mint.Explanation, key: str, axis: str = "x") -> list[object]:
    from mintfig import explainer

    ax = result[key]
    target = ax.xaxis if axis == "x" else ax.yaxis
    return explainer._tick_label_boxes(target, result.fig.canvas.get_renderer())


def _no_overlap(boxes: list[object], horizontal: bool = True) -> bool:
    spans = sorted(((b.x0, b.x1) if horizontal else (b.y0, b.y1)) for _, b in boxes)  # type: ignore[attr-defined]
    return all(nxt[0] >= cur[1] for cur, nxt in itertools.pairwise(spans))


def test_half_width_trend_x_ticks_never_touch_and_keep_the_end() -> None:
    steps = np.arange(0, 2001, 50)
    result = mint.explain(
        "The gap between variants opens in the first 500 steps",
        mint.compare({"full": 0.82, "no retrieval": 0.74}, label="Accuracy"),
        mint.trend(steps, {"full": 0.8 * (1 - np.exp(-steps / 300))}, label="Acc", x_label="Step"),
    )
    boxes = _visible_tick_boxes(result, "b")
    assert len(boxes) >= 2 and _no_overlap(boxes)
    labels = [t.get_text() for t in result["b"].get_xticklabels() if t.get_text()]
    assert "2,000" in labels


def test_few_measured_x_positions_are_the_ticks() -> None:
    doping = [0, 0.5, 1, 2, 4]
    result = mint.explain(
        "Mobility peaks at 2 at.% and collapses at 4 at.%",
        mint.trend(doping, {"mobility": [3, 5, 18, 72, 2.6]}, label="Mobility", x_label="Li (at.%)"),
    )
    ax = result["a"]
    assert [float(v) for v in ax.get_xticks()] == doping
    shown = [t.get_text() for t in ax.get_xticklabels()]
    assert shown == ["0", "0.5", "1", "2", "4"]
    # in a third-width cell the same labels are thinned, never overlapped
    narrow = mint.explain(
        "Mobility peaks at 2 at.% and collapses at 4 at.%",
        mint.trend(doping, {"m": [3, 5, 18, 72, 2.6]}, label="Mobility", end_values=False),
        mint.compare({"a": 1, "b": 2}, label="x"),
        mint.compare({"a": 1, "b": 2}, label="y"),
        layout=[["a", "b", "c"]],
    )
    assert _no_overlap(_visible_tick_boxes(narrow, "a"))


def test_log_trend_labels_the_top_of_the_data_in_the_body_font() -> None:
    temps = [100, 150, 200, 250, 300, 350]
    result = mint.explain(
        "Sample C conducts four decades better than A at 350 K",
        mint.trend(
            temps,
            {"C": [1e-6, 1e-5, 1e-4, 1e-3, 5e-3, 1e-2], "A": [1e-9, 1e-8, 1e-7, 1e-6, 1e-5, 2e-5]},
            log=True,
            label="Conductivity",
            unit="S/cm",
            highlight="C",
        ),
    )
    ax = result["a"]
    shown = list(_visible_tick_boxes(result, "a", "y"))
    assert max(loc for loc, _ in shown) >= 1e-2 * 0.999
    texts = [t.get_text() for t in ax.get_yticklabels() if t.get_text()]
    assert texts and not any("mathdefault" in t for t in texts)
    assert all("mathregular" in t for t in texts)  # superscripts in the body font
    assert not [i for i in result.issues if i["rule"] == "canvas_clipping"]


def test_event_labels_avoid_lines_and_end_labels() -> None:
    dose = [0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1, 3, 10, 30]
    result = mint.explain(
        "BX-204 inhibits the kinase at nanomolar doses",
        mint.trend(
            dose,
            {
                "BX-204": [3, 17, 47, 77, 90, 103, 97, 97, 96, 97],
                "BX-101": [2, 2, 9, 29, 61, 78, 92, 100, 101, 103],
                "BX-317": [2, 0, 2, 6, 15, 28, 50, 79, 89, 95],
            },
            log_x=True,
            highlight="BX-204",
            label="Inhibition",
            unit="%",
            events={0.01: "IC50 10 nM"},
        ),
        mint.compare({"a": 1, "b": 2}, label="x"),
    )
    ax = result["a"]
    renderer = result.fig.canvas.get_renderer()
    event = next(t for t in ax.texts if t.get_text() == "IC50 10 nM")
    box = event.get_window_extent(renderer)
    data_lines = [
        line.get_transform().transform_path(line.get_path())
        for line in ax.get_lines()
        if line.get_label() in {"BX-204", "_context"}
    ]
    assert len(data_lines) == 3  # the panel has lines to avoid
    assert not any(p.intersects_bbox(box, filled=False) for p in data_lines)
    others = [t for t in ax.texts if t is not event and t.get_text()]
    assert not any(box.overlaps(t.get_window_extent(renderer)) for t in others)
    assert not [i for i in result.issues if i["rule"] == "event_label_collides"]


def test_an_event_label_with_no_free_spot_is_reported() -> None:
    x = list(range(12))
    rng = np.random.default_rng(1)
    series = {f"s{i}": list(rng.uniform(0, 10, 12)) for i in range(4)}
    result = mint.explain(
        "Four noisy series fill the whole panel with crossing lines",
        mint.trend(x, series, label="Signal", events={5: "a very long event label that cannot fit anywhere in a half-width panel"}),
        mint.compare({"a": 1, "b": 2}, label="x"),
        mint.compare({"a": 1, "b": 2}, label="y"),
    )
    issues = [i for i in result.issues if i["rule"] == "event_label_collides"]
    assert issues and issues[0]["severity"] == "warning" and issues[0]["panel"] == "a"
    assert "Shorten" in issues[0]["fix_hint"]


def test_explain_preflight_hints_name_explain_arguments() -> None:
    from mintfig import explainer

    for rule in ("text_overlaps", "canvas_clipping"):
        hint = explainer._EXPLAIN_PREFLIGHT_HINTS[rule]
        assert "layout=" in hint and "drop a panel" in hint
        assert "direct_labels" not in hint and "ylim" not in hint


def test_relate_x_label_is_muted_like_trend() -> None:
    result = mint.explain(
        "Throughput rises with batch size up to 64",
        mint.relate([1, 2, 3, 4], [2, 4, 5, 8], x_label="Batch size", y_label="Throughput"),
    )
    assert _hex(result["a"].xaxis.label.get_color()) == THEMES["mintfig"].muted.upper()


def _summary_lines(ax: object) -> list[object]:
    from matplotlib.collections import LineCollection

    return [c for c in ax.collections if isinstance(c, LineCollection)]  # type: ignore[attr-defined]


def test_distribution_summary_reads_as_median_and_middle_half() -> None:
    result = mint.explain(
        "Knocking out the gene cuts migration distance by about 40%",
        mint.distribution(
            {"wild type": [11, 12, 13, 12.5, 11.8, 12.2], "knockout": [6, 7, 7.5, 6.5]},
            label="Migration",
            unit="µm",
        ),
    )
    ax = result["a"]
    lines = _summary_lines(ax)
    horizontal = [c for c in lines if np.ptp(c.get_segments()[0][:, 1]) == 0]
    vertical = [c for c in lines if np.ptp(c.get_segments()[0][:, 0]) == 0]
    # n=6 gets a middle-half line through its dot row; n=4 only a median tick
    assert len(horizontal) == 1 and len(vertical) == 2
    assert horizontal[0].get_segments()[0][0, 1] == 0.0  # through the dots, not under them
    assert "middle half" in result.panels["a"].measure_note


def test_distribution_axis_covers_every_dot_and_reference_clears_header() -> None:
    result = mint.explain(
        "No-reranker seeds straddle the full model",
        mint.distribution(
            {"full": [67.5, 68.0, 68.2, 67.9, 66.9], "no reranker": [66.1, 66.3, 66.6, 67.4, 68.8]},
            label="Accuracy",
            unit="%",
            highlight="no reranker",
            reference=(67.7, "full-model mean 67.7"),
        ),
        mint.compare({"a": 1, "b": 2}, label="x"),
    )
    ax = result["a"]
    labelled = [loc for loc, _ in _visible_tick_boxes(result, "a")]
    assert max(labelled) >= 68.8 and min(labelled) <= 66.1
    renderer = result.fig.canvas.get_renderer()
    ref = next(t for t in ax.texts if t.get_text().startswith("full-model"))
    header = next(t for t in ax.texts if t.get_text() == "median")
    assert not ref.get_window_extent(renderer).overlaps(header.get_window_extent(renderer))


def test_matrix_headers_wrap_or_refuse() -> None:
    values = [[1.0, 2.0, 3.0, 4.0], [2.0, 3.0, 4.0, 5.0]]
    wrapped = mint.explain(
        "Long benchmark names wrap instead of colliding",
        mint.matrix(values, rows=["x", "y"], cols=["Natural Questions", "Trivia QA", "Hotpot QA", "Sci Fact"]),
        mint.compare({"a": 1, "b": 2}, label="x"),
        layout=[["a", "b"]],
    )
    headers = [t.get_text() for t in wrapped["a"].get_xticklabels()]
    assert any("\n" in h for h in headers)
    with pytest.raises(mint.ExplainError) as err:
        mint.explain(
            "Long single-word headers cannot fit a half-width matrix",
            mint.matrix(
                values,
                rows=["x", "y"],
                cols=["HotpotQAextended", "TriviaQAextended", "NaturalQuestions", "SciFactBench"],
            ),
            mint.compare({"a": 1, "b": 2}, label="x"),
        )
    assert err.value.rule == "matrix_cells_too_small"
    assert "layout=" in err.value.fix_hint


def test_compare_intervals_get_thin_whiskers_and_a_value_axis() -> None:
    result = mint.explain(
        "Removing retrieval costs 8 points of accuracy",
        mint.compare(
            {"full": 0.82, "no retrieval": 0.74, "no fine-tune": 0.69},
            error={"full": (0.80, 0.84), "no retrieval": (0.71, 0.77), "no fine-tune": (0.66, 0.72)},
            error_label="95% CI",
            label="Accuracy",
        ),
    )
    ax = result["a"]
    assert ax.xaxis.get_visible()
    labelled = [loc for loc, _ in _visible_tick_boxes(result, "a")]
    assert 2 <= len(labelled) <= 5
    assert max(labelled) >= 0.84 and min(labelled) <= 0.66
    lines = _summary_lines(ax)
    assert all(max(c.get_linewidths()) <= 1.2 for c in lines)
    caps = [c for c in lines if np.ptp(c.get_segments()[0][:, 0]) == 0]
    assert len(caps) == 2  # low and high end caps


def test_a_short_bar_panel_grows_beside_a_taller_trend() -> None:
    result = mint.explain(
        "Checkout is slow and got slower after the deploy",
        mint.compare({"checkout": 1840, "search": 460, "auth": 310}, label="p99", unit="ms"),
        mint.trend([1, 2, 3, 4], {"checkout": [500, 520, 1400, 1840]}, label="p99", unit="ms"),
    )
    renderer = result.fig.canvas.get_renderer()
    bars = result["a"].get_window_extent(renderer).height
    lines = result["b"].get_window_extent(renderer).height
    # grows up to 1.3x its natural pitch (the trend is banked up to 1.15x); tops aligned
    assert bars >= 0.5 * lines


def test_narrow_trend_cell_is_refused_with_a_useful_hint() -> None:
    with pytest.raises(mint.ExplainError) as err:
        mint.explain(
            "Every variant converges, but the extended-context model is slowest",
            mint.trend(
                [1, 2, 3],
                {"extended-context retrieval model": [1, 2, 3.33333], "baseline model": [1, 1.5, 2]},
                label="Accuracy",
            ),
            mint.compare({"a": 1, "b": 2}, label="x"),
            mint.compare({"a": 1, "b": 2}, label="y"),
            layout=[["a", "b", "c"]],
        )
    assert err.value.rule == "panel_too_small"
    assert "end_values=False" in err.value.fix_hint and "layout=" in err.value.fix_hint


def test_full_width_trend_row_is_capped_in_a_multi_row_figure() -> None:
    x = list(range(10))
    result = mint.explain(
        "Leakage diverges above 200 K while the others stay flat",
        mint.trend(x, {"C": [10.0**-(9 - i / 2) for i in x]}, log=True, label="I", unit="A"),
        mint.compare({"A": 1, "B": 2, "C": 40}, label="I", unit="nA"),
        mint.compare({"A": 1, "B": 2, "C": 3}, label="R", unit="Ω"),
    )
    renderer = result.fig.canvas.get_renderer()
    px_per_mm = result.fig.dpi / 25.4
    cell_mm = result["a"].get_tightbbox(renderer).height / px_per_mm
    assert cell_mm <= 44.0 * 8.5 / 8.5 + 1.0
    assert result.height_mm <= 150


@pytest.mark.parametrize("style", list(THEMES))
def test_grey_context_lines_stay_inside_the_value_axis(style: str) -> None:
    x = list(range(1, 9))
    series = {
        "focus": [1, 2, 3, 4, 5, 6, 7, 8],
        "high context": [2, 4, 9, 14, 20, 25, 30, 41],
        "low context": [0.5, 0.2, -3, -6, -2, 0, 1, 2],
    }
    result = mint.explain(
        "Only the focus series grows steadily",
        mint.trend(x, series, highlight="focus", label="Signal"),
        style=style,
    )
    lo, hi = sorted(result["a"].get_ylim())
    for line in result["a"].get_lines():
        ys = np.asarray(line.get_ydata(), dtype=float)
        if line.get_label() in {"_context", "focus"}:
            assert ys[np.isfinite(ys)].min() >= lo and ys[np.isfinite(ys)].max() <= hi


def test_a_superscript_run_is_one_script_in_one_font() -> None:
    from mintfig import explainer

    drawn = explainer._plain("n = 3×10¹⁷ cm⁻³", mint.themes.MINTFIG_THEME)
    # Latin-1 ¹ and the superscript-block ⁷ end up in one mathtext script run
    assert r"$^{\mathregular{17}}$" in drawn
    assert r"$^{\mathregular{{-}3}}$" in drawn


def test_summary_lists_entity_colour_slots_for_the_next_figure() -> None:
    first = _six()
    slots = first.summary()["colors"]
    assert slots["new"] == "red" and slots["ref"] in {"blue", "green", "amber"}
    second = mint.explain(
        "The reference catalyst is the slower of the two at every temperature",
        mint.trend([1, 2, 3], {"ref": [1, 2, 3], "new": [2, 4, 6]}, label="Yield"),
        colors=slots,
    )
    lines = _line_colours(second, "a")
    c = _line_colours(first, "c")
    assert lines["new"] == c["new"] and lines["ref"] == c["ref"]
