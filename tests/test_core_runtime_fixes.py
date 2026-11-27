"""Regression tests for core runtime fixes (#3, #9, #14, #15, #20)."""

from __future__ import annotations

import dataclasses
import importlib
import re
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import pytest
from matplotlib.colors import to_hex

import mintfig as mint
from mintfig._chip_bridge import SCHEME_SYNC_CSS
from mintfig.palettes import BANNED_COLORMAPS
from mintfig.plate import Plate, figure
from mintfig.runner import _explanation_figure
from mintfig.themes import MINTFIG_THEME, Theme

pub_style = importlib.import_module("mintfig.style")


# --------------------------------------------------------------------------- #
# Fix #3 & #20: interactive.py SVG minifier, Theme typography, native <details>
# --------------------------------------------------------------------------- #


def test_compact_html_preserves_decimal_text_and_aria_labels() -> None:
    takeaway = "Accuracy drops from 0.825 to 0.698 (p = 0.004)"
    exp = mint.explain(
        takeaway,
        mint.compare(
            {"full model": 0.825, "no retrieval": 0.698},
            label="Accuracy",
            highlight="no retrieval",
            fmt=".3f",
        ),
        source="eval/run.csv",
    )
    compact = exp.to_html(compact=True)
    # Visible SVG <text> and aria-label must keep full 3-decimal precision verbatim
    assert "0.825" in compact
    assert "0.698" in compact
    assert "p = 0.004" in compact
    assert 'aria-label="full model = 0.825"' in compact
    assert 'aria-label="no retrieval = 0.698"' in compact
    # And the full headline must not be mangled into "0.8 to 0.6 (p = 0.0)"
    assert "0.8 to 0.6" not in compact
    assert "p = 0.0)" not in compact


def test_compact_html_preserves_theme_typography() -> None:
    panel = mint.compare({"Alpha": 0.82, "Beta": 0.71}, label="Score")
    for style_name in ("editorial", "paper"):
        exp = mint.explain("Alpha beats Beta by 11 points", panel, style=style_name)
        compact = exp.to_html(compact=True)
        assert "Georgia" in compact

    sketch_exp = mint.explain(
        "Alpha beats Beta by 11 points", panel, style="sketch", note="Illustrative sketch"
    )
    sketch_compact = sketch_exp.to_html(compact=True)
    assert "Humor Sans" in sketch_compact or "Comic" in sketch_compact

    mono_custom = dataclasses.replace(
        Theme(name="custom_mono", description="Mono test"),
        body_family=("Menlo", "Consolas", "DejaVu Sans Mono", "monospace"),
    )
    mono_exp = mint.explain("Alpha beats Beta by 11 points", panel, style=mono_custom)
    mono_compact = mono_exp.to_html(compact=True)
    assert "Menlo" in mono_compact or "monospace" in mono_compact


def test_html_data_drawer_uses_native_zero_js_details() -> None:
    exp = mint.explain(
        "Alpha beats Beta by 11 points",
        mint.compare({"Alpha": 82, "Beta": 71}, label="Score", unit="%"),
    )
    frag = exp._repr_html_()
    assert '<details class="mf-data-details">' in frag
    assert '<summary data-mf-act="data">data</summary>' in frag
    assert '<div class="mf-data">' in frag
    assert '<div class="mf-data" hidden>' not in frag
    # JS should not hijack the native <details> toggle
    assert "a==='data'" not in frag


# --------------------------------------------------------------------------- #
# Fix #9: mathtext.cal + zero global rcParams leakage in Plate / figure / runner
# --------------------------------------------------------------------------- #


def test_style_rc_params_sets_mathtext_cal_and_plate_does_not_leak_rcparams(tmp_path: Path) -> None:
    rc = pub_style.rc_params("nature")
    assert rc["mathtext.cal"] == rc["mathtext.rm"]

    before = dict(mpl.rcParams)
    plate = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
    try:
        assert dict(mpl.rcParams) == before
        ax = plate["a"]
        ax.plot([1, 10, 100], [1, 10, 100])
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("Dose")
        ax.set_ylabel("Response")
        plate.label_panels()
        assert dict(mpl.rcParams) == before
        plate.preflight()
        assert dict(mpl.rcParams) == before
        plate.save(tmp_path / "plate.pdf")
        assert dict(mpl.rcParams) == before
    finally:
        plt.close(plate.fig)

    fig, ax2 = figure(journal="nature", width="single", height_mm=65.0)
    try:
        assert dict(mpl.rcParams) == before
        ax2.semilogy([1, 2, 3], [1, 10, 100])
        fig.canvas.draw()
    finally:
        plt.close(fig)

    exp = mint.explain(
        "Alpha beats Beta by 11 points",
        mint.compare({"Alpha": 82, "Beta": 71}, label="Score", unit="%"),
    )
    _explanation_figure(exp)
    assert dict(mpl.rcParams) == before

    # Explicit context manager scopes rcParams inside `with` and restores on exit
    with Plate(journal="nature", width="single", height_mm=65.0) as scoped:
        assert mpl.rcParams["font.size"] == pytest.approx(scoped.spec.body_pt)
        plt.close(scoped.fig)
    assert dict(mpl.rcParams) == before


# --------------------------------------------------------------------------- #
# Fix #14: ExplainError smoothing, measure=, grouped n=/error=, matrix angling,
#          #HEX colors, 4-line takeaway nudge, Explanation.save_pr_card
# --------------------------------------------------------------------------- #


def test_non_mapping_inputs_raise_explain_error_with_fix_hint() -> None:
    bad_calls = [
        lambda: mint.compare([1, 2, 3]),
        lambda: mint.trend([1, 2], [("A", [1, 2]), ("B", [3, 4])]),
        lambda: mint.trend([1, 2], {"A": [1, 2]}, events=[(1, "deploy")]),
        lambda: mint.distribution([("A", [1, 2, 3]), ("B", [4, 5, 6])]),
        lambda: mint.table([{"A": 1}], units=["ms"]),  # type: ignore[arg-type]
    ]
    for call in bad_calls:
        with pytest.raises(mint.ExplainError) as err:
            call()
        assert err.value.fix_hint


def test_measure_alias_accepted_across_forms() -> None:
    p_cmp = mint.compare({"A": 80, "B": 65}, measure="Accuracy", unit="%")
    assert p_cmp.label == "Accuracy"
    p_tr = mint.trend([1, 2, 3], {"A": [1, 2, 3]}, measure="Loss")
    assert p_tr.label == "Loss"
    p_sh = mint.share({"A": 60, "B": 40}, measure="Share")
    assert p_sh.label is not None and p_sh.label.startswith("Share")
    p_mat = mint.matrix([[1.0, 2.0], [3.0, 4.0]], rows=["r1", "r2"], cols=["c1", "c2"], measure="Score")
    assert p_mat.label == "Score"


def test_grouped_compare_supports_n_error_and_roundtrip() -> None:
    values = {"GPQA": {"Alpha": 86.0, "Beta": 77.0}, "SWE": {"Alpha": 74.0, "Beta": 58.0}}
    errors = {
        "GPQA": {"Alpha": (83.5, 88.5), "Beta": (74.0, 80.0)},
        "SWE": {"Alpha": (71.0, 77.0), "Beta": (54.5, 61.5)},
    }
    counts = {"GPQA": 198, "SWE": 500}
    exp = mint.explain(
        "Alpha leads Beta on both GPQA and SWE benchmarks",
        mint.compare(
            values,
            label="Accuracy",
            unit="%",
            highlight="Alpha",
            error=errors,
            error_label="95% CI",
            n=counts,
            show_delta="auto",
        ),
        source="eval/suite.json",
    )
    assert exp.ship is True
    assert any("n=198" in f for f in exp.panels["a"].facts)
    assert any("intervals" in f for f in exp.panels["a"].facts)
    rebuilt = mint.load(exp.to_spec())
    assert rebuilt.ship is True
    assert rebuilt.to_spec()["panels"][0]["n"] == counts


def test_hex_colors_accepted_and_roundtrip() -> None:
    exp = mint.explain(
        "Alpha rises above Beta across all steps",
        mint.trend([1, 2, 3], {"Alpha": [1, 2, 4], "Beta": [1, 1.5, 2]}, label="Score"),
        colors={"Alpha": "#1F5A9D", "Beta": "#d97757"},
    )
    lines = {
        ln.get_label(): to_hex(ln.get_color()).upper()
        for ln in exp["a"].get_lines()
        if not ln.get_label().startswith("_")
    }
    assert lines["Alpha"] == "#1F5A9D"
    assert lines["Beta"] == "#D97757"
    assert exp.summary()["colors"]["Beta"] == "#D97757"
    rebuilt = mint.load(exp.to_spec())
    rebuilt_lines = {
        ln.get_label(): to_hex(ln.get_color()).upper()
        for ln in rebuilt["a"].get_lines()
        if not ln.get_label().startswith("_")
    }
    assert rebuilt_lines == lines


def test_four_line_takeaway_auto_nudges_font_size_within_floor() -> None:
    # ~185 chars wraps to 4 lines at default title size (11 pt) on 140 mm chat width,
    # but fits cleanly on 3 lines after a 0.5-1.0 pt nudge while keeping min_text_px >= 11.
    borderline = (
        "Enabling semantic retrieval raises test accuracy by 8.4 points across all six "
        "evaluation benchmarks while keeping p99 latency under 45 ms on every production "
        "serving cluster node"
    )
    exp = mint.explain(
        borderline,
        mint.compare({"Full": 82.4, "No retrieval": 74.0}, label="Accuracy", unit="%"),
    )
    assert exp.ship is True
    assert exp.min_text_px >= 11.0
    # Genuinely huge takeaways still raise takeaway_too_long
    with pytest.raises(mint.ExplainError) as err:
        mint.explain("word " * 60, mint.compare({"A": 1, "B": 2}, label="x"))
    assert err.value.rule == "takeaway_too_long"


def test_explanation_save_pr_card(tmp_path: Path) -> None:
    exp = mint.explain(
        "Alpha beats Beta by 11 points",
        mint.compare({"Alpha": 82, "Beta": 71}, label="Score", unit="%", highlight="Alpha"),
    )
    card = exp.save_pr_card(tmp_path, name="ablation")
    assert card["ok"] is True
    assert (tmp_path / "ablation.light.png").is_file()
    assert (tmp_path / "ablation.dark.png").is_file()
    assert (tmp_path / "ablation.md").is_file()
    assert "<picture>" in card["markdown"]


# --------------------------------------------------------------------------- #
# Fix #15 & #20: cobalt-blue accent, SCHEME_SYNC_CSS, turbo ban, notebook dark,
#                STABILITY_POLICY
# --------------------------------------------------------------------------- #


def test_mintfig_theme_cobalt_blue_accent_and_scheme_sync_css() -> None:
    assert MINTFIG_THEME.accent_colors == ("#1F5A9D", "#CD4324", "#0F9478")
    assert ":root{--mc-paper:#FFFFFF;" in SCHEME_SYNC_CSS
    assert "@media (prefers-color-scheme: dark){:root{--mc-paper:#14181F;" in SCHEME_SYNC_CSS
    assert "turbo" in BANNED_COLORMAPS


def test_notebook_preview_uses_theme_card_var_and_stability_policy_updated(tmp_path: Path) -> None:
    nb = mint.notebook.init(tmp_path)
    doc = (nb / "index.html").read_text(encoding="utf-8")
    assert re.search(r"\.preview\s*\{[^}]*background:\s*var\(--card\)", doc)

    policy = (Path(__file__).resolve().parents[1] / "docs" / "STABILITY_POLICY.md").read_text(
        encoding="utf-8"
    )
    assert "mint.notebook" in policy and "mintfig.notebook" in policy
    assert "Deprecated" in policy and "mint.inline" in policy
