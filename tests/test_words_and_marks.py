"""Words tied to marks: entity names in their colour, brackets for claimed gaps, one colour
per entity across panels, percentage points, and a caption that prints the claim."""

from __future__ import annotations

import json

import matplotlib
import pytest
from matplotlib.collections import PathCollection
from matplotlib.colors import to_hex
from matplotlib.text import Text

matplotlib.use("Agg")

import mintfig as mint
from mintfig._explain.core import _text_color

TAKEAWAY = "Removing retrieval costs 8 points of accuracy; removing fine-tuning costs 13"
ACCURACY = {"full model": 0.82, "no retrieval": 0.74, "no fine-tuning": 0.69}
DROPS = ["no retrieval", "no fine-tuning"]
LAYOUT_RULES = {"text_overlaps", "text_struck_by_line", "canvas_clipping", "text_on_data",
                "line_past_axis"}


def _readme(**kw: object) -> mint.Explanation:
    return mint.explain(
        TAKEAWAY,
        mint.compare(
            ACCURACY,
            error={"full model": (0.80, 0.84), "no retrieval": (0.71, 0.77),
                   "no fine-tuning": (0.66, 0.72)},
            error_label="95% CI, 5 seeds",
            title="Both losses are outside seed noise",
            label="Test accuracy",
            highlight=DROPS,
        ),
        mint.trend(
            [0, 500, 1000, 1500, 2000],
            {"full model": [0.02, 0.61, 0.76, 0.80, 0.82],
             "no retrieval": [0.02, 0.52, 0.67, 0.72, 0.74],
             "no fine-tuning": [0.01, 0.44, 0.60, 0.66, 0.69]},
            title="The gap opens in the first 500 steps",
            label="Validation accuracy",
            x_label="Training step",
        ),
        source="runs/ablation_2026-11 (5 seeds per variant)",
        **kw,
    )


def _brackets(result: mint.Explanation, key: str = "a") -> list[str]:
    """Texts of the bracket labels (the annotations right of each bracket line)."""
    ax = result[key]
    if not [ln for ln in ax.get_lines() if ln.get_label() == "_bracket"]:
        return []
    values = {t.get_text() for t in ax.texts}
    return sorted(t for t in values if t.startswith(("\N{MINUS SIGN}", "+")) or t.endswith("\N{MULTIPLICATION SIGN}"))


def _hex(color: object) -> str:
    return to_hex(color).upper()  # type: ignore[arg-type]


def _layout_issues(result: mint.Explanation) -> list[str]:
    return [i["rule"] for i in result.issues if i["rule"] in LAYOUT_RULES]


def test_an_entity_coloured_in_one_panel_keeps_that_colour_beside_a_highlight() -> None:
    result = _readme()
    ax = result["a"]
    names = [t.get_text() for t in ax.get_yticklabels()]
    dots = next(c for c in ax.collections if isinstance(c, PathCollection))
    dot = {nm: _hex(c) for nm, c in zip(names, dots.get_facecolors(), strict=True)}
    line = {ln.get_label(): _hex(ln.get_color()) for ln in result["b"].get_lines()
            if not ln.get_label().startswith("_")}
    for name in ACCURACY:
        assert dot[name] == line[name]
    weights = {t.get_text(): t.get_fontweight() for t in ax.get_yticklabels()}
    assert weights == {"full model": "normal", "no retrieval": "bold", "no fine-tuning": "bold"}
    slots = result.summary()["colors"]
    palette = {slot: _hex(result.theme.series_colors[i]) for slot, i in
               (("blue", 0), ("red", 1), ("green", 2), ("amber", 3))}
    assert {name: palette[slot] for name, slot in slots.items()} == line
    assert result.ship


def test_a_baseline_is_ink_in_every_panel() -> None:
    result = mint.explain(
        "Both variants beat the control by step 2",
        mint.compare({"ctrl": 3.0, "a": 5.0, "b": 4.0}, highlight="a", label="Score"),
        mint.trend([0, 1, 2], {"ctrl": [1, 2, 3], "a": [1, 3, 5], "b": [1, 2.5, 4]},
                   baseline="ctrl", label="Score"),
    )
    bars = {t.get_text(): _hex(p.get_facecolor())
            for t, p in zip(result["a"].get_yticklabels(), result["a"].patches, strict=False)}
    assert bars["ctrl"] == _hex(result.theme.ink)
    assert "ctrl" not in result.summary()["colors"]


def test_claimed_gaps_are_bracketed_and_pass_the_layout_audit() -> None:
    result = mint.explain(TAKEAWAY, mint.compare(ACCURACY, label="Accuracy", highlight=DROPS))
    assert _brackets(result) == ["\N{MINUS SIGN}0.08", "\N{MINUS SIGN}0.13"]
    assert _layout_issues(result) == [] and result.ship
    # the README panel is half width: the gap stated first is kept
    assert _brackets(_readme()) == ["\N{MINUS SIGN}0.08"]


def test_a_fold_claim_is_bracketed_as_a_ratio() -> None:
    result = mint.explain(
        "Checkout is 4x slower than the next service at p99",
        mint.compare({"checkout": 1840, "search": 460, "auth": 310}, label="p99", unit="ms",
                     highlight="checkout"),
    )
    assert _brackets(result) == ["4.0\N{MULTIPLICATION SIGN}"]
    assert result.ship


@pytest.mark.parametrize(
    ("takeaway", "kw"),
    [
        ("A leads B and C by 10 ms each", {}),  # two pairs match: ambiguous
        ("A is 30 ms, the slowest", {}),  # a level, not a gap
        ("A leads C by 10 ms", {"show_delta": False}),
        ("A leads C by 10 ms", {"show_delta": True, "baseline": "C"}),
    ],
)
def test_no_bracket_when_the_match_is_ambiguous_or_switched_off(takeaway: str, kw: dict) -> None:
    result = mint.explain(takeaway, mint.compare({"A": 30, "B": 20, "C": 20}, unit="ms",
                                                 label="Latency", **kw))
    assert not [ln for ln in result["a"].get_lines() if ln.get_label() == "_bracket"]


def test_show_delta_modes_round_trip_and_grouped_compare_takes_the_default() -> None:
    assert "show_delta" not in mint.compare({"a": 1, "b": 2}).to_spec()
    assert mint.compare({"a": 1, "b": 2}, show_delta=False).to_spec()["show_delta"] is False
    grouped = mint.explain("Model A leads on both tasks by 2 points",
                           mint.compare({"t1": {"A": 10, "B": 8}, "t2": {"A": 12, "B": 10}}))
    assert not [ln for ln in grouped["a"].get_lines() if ln.get_label() == "_bracket"]
    with pytest.raises(mint.ExplainError, match="show_delta"):
        mint.compare({"a": 1, "b": 2}, show_delta="yes")


def test_entity_names_in_the_takeaway_and_titles_take_their_colour() -> None:
    def build(**kw: object) -> mint.Explanation:
        return mint.explain(
            "Checkout is 4x slower than search",
            mint.compare({"checkout": 1840, "search": 460}, label="p99", unit="ms",
                         highlight="checkout", title="checkout stands alone"),
            mint.trend([1, 2, 3], {"checkout": [500, 900, 1840], "search": [450, 460, 460]},
                       label="p99", unit="ms", highlight="checkout"),
            **kw,
        )

    result = build()
    red = _text_color(result.theme.accent_colors[0], background=result.theme.background,
                      ink=result.theme.ink)
    texts = {t.get_text(): _hex(t.get_color()) for t in result.fig.findobj(Text)}
    assert texts["Checkout"] == texts["checkout"] == red.upper()
    assert texts[" is 4x slower than search"] == _hex(result.theme.ink)  # "search" is grey context
    assert not _layout_issues(result) and result.ship

    plain = build(color_names=False)
    assert "Checkout is 4x slower than search" in {t.get_text() for t in plain.fig.texts}
    spec = plain.to_spec()
    assert spec["color_names"] is False
    assert mint.load(json.loads(json.dumps(spec))).to_spec() == spec


def test_deltas_on_a_percent_quantity_are_in_points() -> None:
    bridge = mint.explain(
        "Retrieval adds 8.2 points; the shipped model reaches 77.2%",
        mint.waterfall({"Retrieval": 8.2, "Prompt cleanup": -1.0}, start=("Base", 70.0),
                       unit="%", label="Accuracy"),
    )
    drawn = {t.get_text() for t in bridge["a"].texts}
    assert {"+8.2 pts", "\N{MINUS SIGN}1.0 pts", "70.0%", "77.2%"} <= drawn
    assert any("+8.2 points" in f for f in bridge.panels["a"].facts)

    inline = mint.explain(
        "The new model is 6.5 points more accurate than the baseline",
        mint.compare({"baseline": 71.0, "new": 77.5}, unit="%", label="Accuracy",
                     baseline="baseline", show_delta=True),
    )
    assert "77.5% (+6.5 pts)" in {t.get_text() for t in inline["a"].texts}
    bracket = mint.explain(
        "The new model is 6.5 points more accurate than the baseline",
        mint.compare({"baseline": 71.0, "new": 77.5, "small": 73.2}, unit="%",
                     label="Accuracy", baseline="baseline"),
    )
    assert _brackets(bracket) == ["+6.5 pts"]


def test_caption_prints_the_takeaway_numbers() -> None:
    caption = _readme().summary()["deliver"]["caption"]
    assert caption == (
        "No retrieval \N{MINUS SIGN}0.08 vs full model (0.82); "
        "no fine-tuning \N{MINUS SIGN}0.13 vs full model (0.82)."
    )
