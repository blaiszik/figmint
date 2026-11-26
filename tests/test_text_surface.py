"""The text surface obeys the figure's rules: same ranking, named intervals, honest changes."""

from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pytest

matplotlib.use("Agg")

import mintfig as mint
from mintfig import terminal
from mintfig.terminal import audit_text_surface, render_terminal

GALLERY = Path(__file__).resolve().parents[1] / "gallery" / "output"
SPECS = sorted(
    p
    for p in GALLERY.glob("explain*/**/*.json")
    if {"takeaway", "panels"} <= set(json.loads(p.read_text("utf-8")))
)


@pytest.mark.parametrize("path", SPECS, ids=lambda p: str(p.relative_to(GALLERY)))
def test_gallery_specs_pass_the_text_audit(path: Path) -> None:
    exp = mint.load(json.loads(path.read_text("utf-8")))
    try:
        assert audit_text_surface(exp) == []
        assert max(len(line) for line in exp.to_text().splitlines()) <= 72
    finally:
        plt.close(exp.fig)


def _interval_fig() -> mint.Explanation:
    return mint.explain(
        "Removing retrieval costs 8 points of accuracy",
        mint.compare(
            {"full model": 0.82, "no retrieval": 0.74, "no fine-tuning": 0.69},
            error={"full model": (0.80, 0.84), "no retrieval": (0.71, 0.77),
                   "no fine-tuning": (0.66, 0.72)},
            error_label="95% CI, 5 seeds",
            label="Test accuracy",
            highlight="no retrieval",
        ),
    )


def _trend_fig() -> mint.Explanation:
    return mint.explain(
        "The full model ends 13 points above the others",
        mint.trend(
            [0, 500, 1000, 1500, 2000],
            {"full model": [0.02, 0.61, 0.76, 0.80, 0.82],
             "no retrieval": [0.02, 0.52, 0.67, 0.72, 0.74],
             "small": [0.40, 0.42, 0.44, 0.46, 0.48]},
            label="Validation accuracy",
            x_label="Training step",
        ),
    )


def test_compare_with_intervals_prints_dot_and_whisker_rows() -> None:
    exp = _interval_fig()
    try:
        text = exp.to_text()
        ascii_text = exp.to_text(ascii_only=True)
        assert audit_text_surface(exp) == []
    finally:
        plt.close(exp.fig)
    assert "█" not in text
    assert re.search(r"├─+●─+┤ +0\.82 \(0\.80–0\.84\)", text)
    assert "0.69 (0.66–0.72)" in text and "intervals: 95% CI, 5 seeds" in text
    assert re.search(r"\|-+o-+\|", ascii_text) and ascii_text.isascii()
    rows = [line for line in text.splitlines() if "●" in line]
    assert "full model" in rows[0] and "no fine-tuning" in rows[-1]
    assert len({line.index("(") for line in rows}) == 1  # values align on one axis


def test_trend_sparklines_share_one_range_and_colour_each_series() -> None:
    exp = _trend_fig()
    try:
        plain = render_terminal(exp, width=72, color=False)
        coloured = render_terminal(exp, width=72, color=True)
    finally:
        plt.close(exp.fig)
    sparks = {
        name: re.search(rf"{name}  (\S+)  ", plain).group(1)  # type: ignore[union-attr]
        for name in ("full model", "small")
    }
    # Own-range scaling would draw the flat 0.40→0.48 series as a full ramp.
    assert sparks["small"][0] == sparks["small"][-1] or len(set(sparks["small"])) <= 2
    assert sparks["full model"][0] == "▁" and sparks["full model"][-1] == "█"
    series_codes = {
        m.group(1)
        for line in coloured.splitlines()
        if "→" in line and "•" not in line
        for m in [re.search(r"(\x1b\[[0-9;]*38;2;[0-9;]+m)[▁▂▃▄▅▆▇█]", line)]
        if m
    }
    assert len(series_codes) == 3
    assert "\x1b" not in plain


def test_relative_change_from_a_near_zero_start_prints_absolute_change() -> None:
    exp = _trend_fig()
    try:
        text = exp.to_text()
        assert audit_text_surface(exp) == []
    finally:
        plt.close(exp.fig)
    assert "0.02 → 0.82 (+0.80)" in text
    assert "0.4 → 0.48 (+20%)" in text  # a start far from zero keeps its percent
    assert "4000%" not in text


def test_color_false_has_no_escape_codes() -> None:
    exp = _interval_fig()
    try:
        assert "\x1b[" in render_terminal(exp, color=True)
        assert "\x1b" not in render_terminal(exp, color=False)
        assert "\x1b" not in render_terminal(exp, color=False, ascii_only=True)
    finally:
        plt.close(exp.fig)


def test_kind_without_text_form_prints_title_and_top_facts() -> None:
    exp = mint.explain(
        "Beta runs spread twice as wide as Alpha runs",
        mint.distribution(
            {"Alpha": [91, 92, 92.5, 93, 93.5], "Beta": [85, 86, 87, 88, 89]},
            title="Run spread",
            label="Accuracy",
            unit="%",
        ),
    )
    try:
        lines = exp.to_text().splitlines()
        facts = exp.panels["a"].facts
    finally:
        plt.close(exp.fig)
    start = next(i for i, line in enumerate(lines) if line.startswith("Run spread"))
    body = [line for line in lines[start + 1 :] if line.startswith("  •")]
    assert len(body) == min(3, len(facts))
    assert all(line.startswith(("  •", "    ")) for line in lines[start + 1 :] if line.strip())


def test_audit_catches_bars_misordered_rows_and_near_zero_percent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exp = _interval_fig()
    trend = _trend_fig()
    try:
        monkeypatch.setattr(terminal, "_compare_draws_dots", lambda panel: False)
        assert {i["rule"] for i in audit_text_surface(exp)} == {"text_interval_missing"}
        monkeypatch.undo()

        original = terminal._render_dot_rows
        monkeypatch.setattr(
            terminal,
            "_render_dot_rows",
            lambda panel, items, **kw: original(panel, items[::-1], **kw),
        )
        assert [i["rule"] for i in audit_text_surface(exp)] == ["text_ranking"]
        monkeypatch.undo()

        def _always_percent(first, last, finite, unit):  # type: ignore[no-untyped-def]
            return f" ({(last - first) / abs(first) * 100:+.0f}%)"

        monkeypatch.setattr(terminal, "_change_text", _always_percent)
        rules = [i["rule"] for i in audit_text_surface(trend)]
        assert rules == ["text_relative_from_zero", "text_relative_from_zero"]
    finally:
        plt.close(exp.fig)
        plt.close(trend.fig)


def test_tiny_values_keep_their_magnitude(monkeypatch: pytest.MonkeyPatch) -> None:
    exp = mint.explain(
        "Doping raises conductivity a hundredfold",
        mint.trend([0, 1, 2, 3], {"doped": [1.3e-9, 2e-8, 9e-8, 1.3e-7]},
                   label="Conductivity", unit="S/cm"),
    )
    try:
        text = exp.to_text()
        assert "1.3×10⁻⁹ S/cm → 1.3×10⁻⁷ S/cm" in text and "→ 0" not in text
        assert "1.3x10^-7 S/cm" in exp.to_text(ascii_only=True)
        assert audit_text_surface(exp) == []
        monkeypatch.setattr(terminal, "_fmt_num", lambda val, ascii_only=False: f"{val:.2f}")
        assert [i["rule"] for i in audit_text_surface(exp)] == ["text_zeroed"]
    finally:
        plt.close(exp.fig)


def test_percent_series_change_in_points(monkeypatch: pytest.MonkeyPatch) -> None:
    exp = mint.explain(
        "Adoption rose from 12% to 88% while the pass rate rose 12 points",
        mint.trend([2019, 2020, 2021, 2022], {"teams": [12, 40, 70, 88]},
                   label="Adoption", unit="%"),
        mint.change({"unit": 70, "e2e": 40}, {"unit": 82, "e2e": 41}, label="Pass rate", unit="%"),
    )
    try:
        text = exp.to_text()
        assert audit_text_surface(exp) == []

        def _always_percent(first, last, finite, unit):  # type: ignore[no-untyped-def]
            return f" ({(last - first) / abs(first) * 100:+.0f}%)"

        monkeypatch.setattr(terminal, "_change_text", _always_percent)
        assert [i["rule"] for i in audit_text_surface(exp)] == ["text_percent_of_percent"]
    finally:
        plt.close(exp.fig)
    assert "12% → 88% (+76 pts)" in text and "633%" not in text and "88 %" not in text
    assert "70% → 82% (+12 pts)" in text and "40% → 41% (+1 pt)" in text


def test_boost_prints_base_extension_and_label(monkeypatch: pytest.MonkeyPatch) -> None:
    exp = mint.explain(
        "Extended thinking adds 5 points to A and 3 to B",
        mint.compare({"A": 74, "B": 70, "C": 61}, boost={"A": 5, "B": 3, "C": 0},
                     boost_label="Extended thinking", label="Score", unit="%"),
    )
    try:
        text = exp.to_text()
        assert audit_text_surface(exp) == []
        original = terminal._render_bars_panel
        monkeypatch.setattr(  # totals only, no base + boost and no label
            terminal,
            "_render_bars_panel",
            lambda panel, **kw: [re.sub(r" \(.*\)$", "", line) for line in original(panel, **kw)
                                 if not line.lstrip().startswith("░")],
        )
        assert [i["rule"] for i in audit_text_surface(exp)] == ["text_boost_missing"]
    finally:
        plt.close(exp.fig)
    assert re.search(r"A  █+▊?░+ 79% \(74 \+ 5\)", text)
    assert "73% (70 + 3)" in text and "░ Extended thinking" in text
    assert re.search(r"C  █+[▏▎▍▌▋▊▉]? 61%$", text, re.MULTILINE)


@pytest.mark.parametrize(
    "panel",
    [
        lambda: mint.change({"a": 70, "b": 40}, {"a": 82, "b": 41}, label="Pass rate", unit="%"),
        lambda: mint.waterfall({"+Retrieval": 8.2, "Quant": -1.5}, start=("Base", 69.0), unit="%"),
        lambda: mint.timeline([("build", 0, 4), ("test", 4, 9)], unit="min"),
        lambda: mint.flow([("Visits", 1000), ("Carts", 400), ("Orders", 120)]),
    ],
)
def test_fact_kinds_print_at_most_three_facts(panel, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    exp = mint.explain("Five facts describe this one panel of evidence", panel())
    try:
        exp.panels["a"].facts += ["extra fact one", "extra fact two", "extra fact three"]
        bullets = [line for line in exp.to_text().splitlines() if line.startswith("  • ")]
        assert len(bullets) == 3
        assert audit_text_surface(exp) == []
        monkeypatch.setattr(terminal, "_render_facts_panel", lambda panel, **kw: ["  • fact"] * 5)
        assert [i["rule"] for i in audit_text_surface(exp)] == ["text_too_many_facts"]
    finally:
        plt.close(exp.fig)
