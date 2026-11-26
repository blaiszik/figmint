"""Tests for Phase 3 Zero-Rewrite Upgrade Path: mint.style(), mint.explain(takeaway, fig_or_ax), and IPython magic."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pytest

import mintfig as mint
from mintfig.byo import (
    StyleContext,
    auto_check,
    figure_to_panel,
    format_badge,
    load_ipython_extension,
    unload_ipython_extension,
)


@pytest.fixture(autouse=True)
def _close_figures() -> Any:
    plt.close("all")
    yield
    plt.close("all")


# --------------------------------------------------------------------------- #
# B1: mint.style()
# --------------------------------------------------------------------------- #


class TestStyleContext:
    def test_context_manager_does_not_leak_global_state(self) -> None:
        before_figsize = list(mpl.rcParams["figure.figsize"])
        before_top = mpl.rcParams["axes.spines.top"]
        before_cmap = mpl.rcParams["image.cmap"]
        before_cl = mpl.rcParams["figure.constrained_layout.use"]

        ctx = mint.style()
        assert isinstance(ctx, StyleContext)
        with ctx:
            assert tuple(mpl.rcParams["figure.figsize"]) == pytest.approx((6.0, 3.6))
            assert mpl.rcParams["figure.dpi"] == 150
            assert mpl.rcParams["axes.spines.top"] is False
            assert mpl.rcParams["axes.spines.right"] is False
            assert mpl.rcParams["axes.unicode_minus"] is True
            assert mpl.rcParams["image.cmap"] == "viridis"
            assert mpl.rcParams["legend.frameon"] is False
            assert mpl.rcParams["figure.constrained_layout.use"] is True

        assert list(mpl.rcParams["figure.figsize"]) == before_figsize
        assert mpl.rcParams["axes.spines.top"] == before_top
        assert mpl.rcParams["image.cmap"] == before_cmap
        assert mpl.rcParams["figure.constrained_layout.use"] == before_cl

    @pytest.mark.parametrize(
        ("width", "expected_size"),
        [
            ("narrow", (4.5, 3.0)),
            ("chat", (6.0, 3.6)),
            ("slide", (8.5, 4.8)),
        ],
    )
    def test_width_presets_pass_mint_check_text_size(
        self, width: str, expected_size: tuple[float, float]
    ) -> None:
        with mint.style(width=width) as sc:
            assert sc.figsize == pytest.approx(expected_size)
            fig, ax = plt.subplots()
            ax.bar(["Full", "No rerank", "No retrieval"], [0.86, 0.81, 0.74])
            ax.set_ylabel("Accuracy")
            ax.set_title("Removing retrieval costs 12 points")

        report = mint.check(fig, width=width)
        rules = {i["rule"] for i in report["issues"]}
        assert "text_too_small" not in rules
        assert report["display"]["min_text_px"] >= 11.0
        assert report.ship is True

    def test_palette_and_accent_override_prop_cycle(self) -> None:
        rc_tol = mint.style("mintfig", palette="tol").rc_params()
        colors_tol = rc_tol["axes.prop_cycle"].by_key()["color"]
        assert colors_tol == list(mint.themes.EXPLAIN_PALETTES["tol"].series_colors)

        rc_accent = mint.style("mintfig", accent="#D97757").rc_params()
        colors_accent = rc_accent["axes.prop_cycle"].by_key()["color"]
        assert colors_accent[0].upper() == "#D97757"
        assert len(colors_accent) == 4

    def test_dark_theme_rc_params_and_apply_method(self) -> None:
        saved = mpl.rcParams.copy()
        try:
            sc = mint.style("dark", width="narrow")
            rc = sc.rc_params()
            assert rc["figure.facecolor"] == mint.themes.THEMES["dark"].background
            assert rc["text.color"] == mint.themes.THEMES["dark"].ink

            applied = sc.apply()
            assert applied["figure.facecolor"] == rc["figure.facecolor"]
            assert mpl.rcParams["figure.facecolor"] == mint.themes.THEMES["dark"].background
        finally:
            mpl.rcParams.update(saved)

    def test_numeric_width_and_invalid_width(self) -> None:
        sc = mint.style(width=600)
        assert sc.width == 600
        assert 4.0 <= sc.figsize[0] <= 6.5

        with pytest.raises(ValueError, match="Unknown width"):
            mint.style(width="poster")

        with pytest.raises(ValueError, match="positive"):
            mint.style(width=-100)

    def test_legacy_mintfig_style_submodule_still_accessible(self) -> None:
        from mintfig import style as top_style
        from mintfig.style import rc_params as pub_rc_params

        assert callable(top_style)
        assert callable(pub_rc_params)
        assert hasattr(top_style, "resolved_font_name")
        assert hasattr(top_style, "_resolve_font_tuple")
        assert isinstance(top_style.resolved_font_name("screen"), str)


# --------------------------------------------------------------------------- #
# B2: mint.explain(takeaway, fig_or_ax, ...)
# --------------------------------------------------------------------------- #


class TestExplainBYOFigure:
    def test_standalone_figure_and_axes_wrap_and_deliver(self, tmp_path: Path) -> None:
        with mint.style():
            fig, ax = plt.subplots()
            ax.bar(["Full", "No rerank", "No retrieval"], [0.86, 0.81, 0.74])
            ax.set_ylabel("Accuracy")

        exp = mint.explain(
            "Removing retrieval costs 12 points of accuracy (0.74 vs 0.86)",
            fig,
            source="synthetic eval",
        )
        assert exp.ship is True
        assert exp.ok is True
        assert exp.issues == []

        png_path = tmp_path / "ablation.png"
        html_path = tmp_path / "ablation.html"
        s_png = exp.save(png_path)
        s_html = exp.save(html_path)

        assert png_path.is_file() and png_path.stat().st_size > 5_000
        assert html_path.is_file() and "<svg" in html_path.read_text(encoding="utf-8")
        assert s_png["ship"] is True
        assert s_png["panels"][0]["facts"]
        assert s_png["deliver"]["markdown"] is not None
        assert s_png["deliver"]["caption"] is not None
        assert s_png["deliver"]["text"]
        assert s_html["deliver"]["html"] is not None

        text_out = exp.to_text()
        assert "Removing retrieval costs 12 points" in text_out

        # Passing Axes directly works the same way
        exp_ax = mint.explain(
            "Removing retrieval costs 12 points of accuracy (0.74 vs 0.86)",
            ax,
            source="synthetic eval",
        )
        assert exp_ax.ship is True
        assert exp_ax.summary()["panels"][0]["facts"]

    def test_mixed_matplotlib_figure_with_builtin_table_and_brief(self, tmp_path: Path) -> None:
        with mint.style():
            fig, ax = plt.subplots()
            x = [1, 2, 3, 4, 5]
            ax.plot(x, [1.20, 0.82, 0.55, 0.39, 0.28], label="Pre-norm")
            ax.plot(x, [1.22, 1.05, 0.88, 0.75, 0.67], label="Post-norm")
            ax.set_xlabel("Epoch")
            ax.set_ylabel("Validation loss")
            ax.legend()

        tbl = mint.table(
            [
                {"Variant": "Pre-norm", "Final loss": 0.28, "Step time (ms)": 41},
                {"Variant": "Post-norm", "Final loss": 0.67, "Step time (ms)": 43},
            ],
            title="Run summary",
            bold_best={"Final loss": "min", "Step time (ms)": "min"},
        )

        exp = mint.explain(
            "Pre-norm reaches 0.28 loss vs 0.67 for post-norm with similar 41 ms step time",
            fig,
            tbl,
            source="synthetic training benchmark",
        )
        assert exp.ship is True
        summary = exp.summary()
        assert len(summary["panels"]) == 2
        assert summary["panels"][0]["facts"]
        assert summary["panels"][1]["kind"] == "table"

        # Brief composes wrapped-figure Explanations cleanly into HTML & Markdown
        brief_html = tmp_path / "brief.html"
        brief_md = tmp_path / "brief.md"
        b = mint.brief("Training architecture review", exp)
        meta_html = b.save(brief_html)
        meta_md = b.save(brief_md)

        assert meta_html["ship_all"] is True
        assert brief_html.is_file() and "Pre-norm reaches 0.28 loss" in brief_html.read_text(encoding="utf-8")
        assert meta_md["ship_all"] is True
        assert brief_md.is_file() and "Pre-norm reaches 0.28 loss" in brief_md.read_text(encoding="utf-8")

    def test_blocking_mint_check_issues_propagate_to_ship(self) -> None:
        # 1. Tiny text from oversized default canvas -> text_too_small blocks ship
        fig_small, ax_small = plt.subplots(figsize=(14, 6), dpi=100)
        ax_small.bar(["A", "B"], [10, 20])
        ax_small.set_ylabel("Score")
        exp_small = mint.explain("B doubles A at 20 vs 10", fig_small)
        rules_small = {i["rule"] for i in exp_small.issues}
        assert "text_too_small" in rules_small
        assert exp_small.ship is False

        # 2. Truncated bar baseline -> bar_baseline_nonzero blocks ship & ok
        with mint.style():
            fig_trunc, ax_trunc = plt.subplots()
            ax_trunc.bar(["A", "B"], [90, 95])
            ax_trunc.set_ylim(85, 100)
            ax_trunc.set_ylabel("Accuracy (%)")
        exp_trunc = mint.explain("B leads A by 5 points (95 vs 90)", fig_trunc)
        assert "bar_baseline_nonzero" in {i["rule"] for i in exp_trunc.issues}
        assert exp_trunc.ok is False
        assert exp_trunc.ship is False

        # 3. Rainbow colormap -> rainbow_colormap blocks ship & ok
        with mint.style():
            fig_jet, ax_jet = plt.subplots()
            im = ax_jet.imshow(np.arange(16).reshape(4, 4), cmap="jet")
            fig_jet.colorbar(im, ax=ax_jet, label="Intensity")
        exp_jet = mint.explain("Values increase from 0 to 15 across the grid", fig_jet)
        assert "rainbow_colormap" in {i["rule"] for i in exp_jet.issues}
        assert exp_jet.ok is False
        assert exp_jet.ship is False

        # 4. Wrong number in takeaway -> claim_number_mismatch blocks ship
        with mint.style():
            fig_mis, ax_mis = plt.subplots()
            ax_mis.bar(["A", "B"], [10, 20])
            ax_mis.set_ylabel("Count")
        exp_mis = mint.explain("B reaches 999 which is 50x higher than A", fig_mis)
        assert "claim_number_mismatch" in {i["rule"] for i in exp_mis.issues}
        assert exp_mis.ship is False

    def test_heatmap_with_colorbar_and_figure_to_panel_explicit_options(self) -> None:
        rng = np.random.default_rng(7)
        mat = rng.uniform(0.1, 0.9, (4, 4))
        mat[0, 1] = 0.95
        with mint.style():
            fig, ax = plt.subplots()
            im = ax.imshow(mat)
            fig.colorbar(im, ax=ax, label="Weight")
            ax.set_xticks(range(4), ["Q1", "Q2", "Q3", "Q4"])
            ax.set_yticks(range(4), ["K1", "K2", "K3", "K4"])

        panel = figure_to_panel(fig, title="Attention map", describe="4x4 attention heatmap")
        assert panel.title == "Attention map"
        assert panel.describe == "4x4 attention heatmap"
        assert panel.facts

        exp = mint.explain("Attention peaks at 0.95 on K1/Q2", panel)
        assert exp.ship is True


# --------------------------------------------------------------------------- #
# Jupyter / IPython Magic (%load_ext mintfig) & auto_check()
# --------------------------------------------------------------------------- #


class _FakeEvents:
    def __init__(self) -> None:
        self.hooks: dict[str, list[Any]] = {}

    def register(self, event: str, callback: Any) -> None:
        self.hooks.setdefault(event, []).append(callback)

    def unregister(self, event: str, callback: Any) -> None:
        self.hooks.get(event, []).remove(callback)

    def trigger(self, event: str, *args: Any) -> None:
        for cb in list(self.hooks.get(event, [])):
            cb(*args)


class _FakeIPython:
    def __init__(self) -> None:
        self.magics: dict[str, Any] = {}
        self.events = _FakeEvents()

    def register_magic_function(self, func: Any, magic_kind: str = "line", magic_name: str | None = None) -> None:
        name = magic_name or func.__name__
        self.magics[f"{magic_kind}:{name}"] = func


class TestIPythonExtensionAndAutoCheck:
    def test_load_unload_magic_and_post_run_cell(self, capsys: pytest.CaptureFixture[str]) -> None:
        ip = _FakeIPython()
        load_ipython_extension(ip)
        try:
            assert "line:mintfig_check" in ip.magics
            assert len(ip.events.hooks.get("post_run_cell", [])) == 1
            magic = ip.magics["line:mintfig_check"]

            # Status check
            magic("status")
            assert "mintfig check: on (width=chat)" in capsys.readouterr().out

            # Clean styled figure -> SHIP badge
            with mint.style():
                _fig1, ax1 = plt.subplots()
                ax1.bar(["A", "B"], [10, 25])
                ax1.set_ylabel("Score")
                ax1.set_title("B reaches 25 vs 10 for A")
            ip.events.trigger("post_run_cell", None)
            out1 = capsys.readouterr().out
            assert "mintfig check: SHIP" in out1

            # Triggering again without a new figure does not double-print
            ip.events.trigger("post_run_cell", None)
            assert capsys.readouterr().out == ""

            # Oversized broken figure -> FIX FIRST badge with fix_hint
            _fig2, ax2 = plt.subplots(figsize=(14, 6), dpi=100)
            ax2.bar(["A", "B"], [10, 20])
            ax2.set_ylabel("Score")
            ip.events.trigger("post_run_cell", None)
            out2 = capsys.readouterr().out
            assert "FIX FIRST" in out2
            assert "text_too_small" in out2
            assert "Fix:" in out2

            # Toggle off -> no badge printed for new figures
            magic("off")
            assert "mintfig check: off" in capsys.readouterr().out
            _fig3, ax3 = plt.subplots()
            ax3.plot([1, 2], [3, 4])
            ip.events.trigger("post_run_cell", None)
            assert capsys.readouterr().out == ""

            # Change width & re-enable
            magic("on width=narrow")
            assert "mintfig check: on (width=narrow)" in capsys.readouterr().out
        finally:
            unload_ipython_extension(ip)

        assert ip.events.hooks.get("post_run_cell", []) == []

    def test_top_level_extension_entry_points(self) -> None:
        assert mint.load_ipython_extension is load_ipython_extension
        assert mint.unload_ipython_extension is unload_ipython_extension

    def test_auto_check_context_manager(self, capsys: pytest.CaptureFixture[str]) -> None:
        with auto_check(width="chat") as ac, mint.style():
            _fig, ax = plt.subplots()
            ax.plot([1, 2, 3, 4], [10, 14, 19, 25])
            ax.set_xlabel("Step")
            ax.set_ylabel("Throughput (req/s)")
            ax.set_title("Throughput rises from 10 to 25 req/s")

        out = capsys.readouterr().out
        assert len(ac.reports) == 1
        assert ac.reports[0].ship is True
        assert "mintfig check: SHIP" in out

    def test_format_badge_ship_and_fix_first(self) -> None:
        ship_badge = format_badge(
            {"ship": True, "display": {"width_px": 700, "min_text_px": 13.8}, "issues": []}
        )
        assert ship_badge == "mintfig check: SHIP (700 px · min text 13.8 px)"

        fix_badge = format_badge(
            {
                "ship": False,
                "display": {"width_px": 700, "min_text_px": 7.2},
                "issues": [{"rule": "text_too_small", "fix_hint": "Use mint.style()."}],
            },
            label="fig 2",
        )
        assert "mintfig check (fig 2): FIX FIRST" in fix_badge
        assert "text_too_small" in fix_badge
        assert "Use mint.style()." in fix_badge
