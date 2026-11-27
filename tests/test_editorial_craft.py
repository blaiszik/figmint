"""Tests for Economist / NYTimes editorial micro-typography craft polish."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import matplotlib
import numpy as np
import pytest
from matplotlib import font_manager
from matplotlib.colors import to_hex
from matplotlib.patches import Rectangle

matplotlib.use("Agg")

import mintfig as mint
from mintfig import explainer
from mintfig._explain.core import _Measure
from mintfig.style import (
    EDITORIAL_SANS_FONTS,
    EDITORIAL_SERIF_FONTS,
    _resolve_font_tuple,
    rc_params,
    register_local_fonts,
)
from mintfig.themes import EDITORIAL_THEME, MINT_THEME, THEMES, Theme, contrast_ratio

# --------------------------------------------------------------------------- #
# 1. Balanced headline wrapping (text-wrap: balance)
# --------------------------------------------------------------------------- #


class TestBalancedHeadlineWrapping:
    def test_checkout_story_headline_eliminates_two_word_widow(self) -> None:
        text = "Checkout regressed after v2.3: slower, more variable, and now most of the wait"
        with MINT_THEME.rc_context(mint.specs.get_spec("screen")):
            measure = _Measure(MINT_THEME)
            max_pt = (140.0 - 8.0) / explainer.PT_TO_MM
            greedy = measure.wrap(text, max_pt, 11.0, "bold", balance=False)
            balanced = measure.wrap(text, max_pt, 11.0, "bold", balance=True)

            assert len(greedy) == 2
            assert len(balanced) == len(greedy)
            assert " ".join(balanced) == text
            # Greedy leaves a 2-word widow ("the wait"); balanced splits ~50/50.
            assert len(greedy[-1].split()) <= 2
            assert len(balanced[-1].split()) >= 4
            widths = [measure.width_pt(line, 11.0, "bold") for line in balanced]
            assert all(w <= max_pt + 1e-6 for w in widths)
            assert min(widths) / max(widths) >= 0.72

    def test_retriever_headline_balances_in_editorial_serif(self) -> None:
        text = "Retriever B lifts accuracy by 9 points while keeping latency steady across loads"
        with EDITORIAL_THEME.rc_context(mint.specs.get_spec("screen")):
            measure = _Measure(EDITORIAL_THEME)
            max_pt = (140.0 - 8.0) / explainer.PT_TO_MM
            greedy = measure.wrap(
                text, max_pt, 12.0, "bold", family=EDITORIAL_THEME.title_family, balance=False
            )
            balanced = measure.wrap(
                text, max_pt, 12.0, "bold", family=EDITORIAL_THEME.title_family, balance=True
            )

            assert len(balanced) == len(greedy) == 2
            assert " ".join(balanced) == text
            assert len(balanced[-1].split()) >= 4
            widths = [
                measure.width_pt(line, 12.0, "bold", family=EDITORIAL_THEME.title_family)
                for line in balanced
            ]
            assert all(w <= max_pt + 1e-6 for w in widths)
            assert min(widths) / max(widths) >= 0.70

    def test_three_line_headline_balances_without_adding_lines(self) -> None:
        text = (
            "Checkout p99 latency tripled after the v2.3 rollout while search, auth, "
            "catalog, and cart stayed flat across all eight weeks of observation"
        )
        with MINT_THEME.rc_context(mint.specs.get_spec("screen")):
            measure = _Measure(MINT_THEME)
            max_pt = 260.0
            greedy = measure.wrap(text, max_pt, 11.0, "bold", balance=False)
            balanced = measure.wrap(text, max_pt, 11.0, "bold", balance=True)

            assert len(greedy) == 3
            assert len(balanced) == 3
            assert " ".join(balanced) == text
            assert len(balanced[-1].split()) >= 4
            g_widths = [measure.width_pt(line, 11.0, "bold") for line in greedy]
            b_widths = [measure.width_pt(line, 11.0, "bold") for line in balanced]
            assert all(w <= max_pt + 1e-6 for w in b_widths)
            # Balanced reduces width spread compared to greedy
            assert (max(b_widths) - min(b_widths)) < (max(g_widths) - min(g_widths))

    def test_single_line_and_greedy_default_unchanged(self) -> None:
        short = "Checkout p99 is 4x higher than search"
        with MINT_THEME.rc_context(mint.specs.get_spec("screen")):
            measure = _Measure(MINT_THEME)
            assert measure.wrap(short, 400.0, 11.0, "bold", balance=True) == [short]
            assert measure.wrap("", 400.0, 11.0, "bold", balance=True) == [""]

    def test_explain_balances_takeaway_and_panel_titles(self) -> None:
        result = mint.explain(
            "Checkout regressed after v2.3: slower, more variable, and now most of the wait",
            mint.compare(
                {"checkout": 1840, "search": 460, "auth": 310, "catalog": 280},
                title="Checkout is four times slower than every other service in production now",
                label="p99 latency",
                unit="ms",
                highlight="checkout",
            ),
            mint.compare(
                {"before": 470, "after": 1260},
                title="Median request latency more than doubled right after release day",
                label="Median",
                unit="ms",
                highlight="after",
            ),
            source="synthetic example data",
        )
        assert result.ok is True
        assert result.ship is True
        assert result.issues == []
        # Headline lines should not end with a 1-2 word orphan ("the wait")
        drawn_texts = [t.get_text() for t in result.fig.texts]
        assert "the wait" not in drawn_texts


# --------------------------------------------------------------------------- #
# 2. Editorial kicker= + Economist / FT top accent flag
# --------------------------------------------------------------------------- #


class TestKickerAndTopFlag:
    @pytest.mark.parametrize("style_name", ["mintfig", "mint", "editorial", "pine", "paper"])
    def test_kicker_renders_uppercase_above_headline_and_roundtrips(
        self, style_name: str, tmp_path: Path
    ) -> None:
        kicker_in = "Performance · Checkout Service"
        fig = mint.explain(
            "Checkout regressed after v2.3: slower, more variable, and now most of the wait",
            mint.compare(
                {"checkout": 1840, "search": 460, "auth": 310, "catalog": 280},
                label="p99 latency",
                unit="ms",
                highlight="checkout",
            ),
            kicker=kicker_in,
            subtitle="API latency by service, week of 16 Nov",
            source="synthetic example data",
            style=style_name,
        )
        summary = fig.summary()
        assert summary["ok"] is True
        assert summary["ship"] is True
        assert summary["issues"] == []
        assert summary["display"]["min_text_px"] >= explainer.MIN_TEXT_PX

        kicker_artists = [t for t in fig.fig.texts if getattr(t, "_mintfig_kicker", False)]
        assert len(kicker_artists) == 1
        k_art = kicker_artists[0]
        assert k_art.get_text() == kicker_in.upper()
        assert k_art.get_fontweight() == "bold"
        # Kicker sits visually above the headline (higher figure y)
        headline_y = fig.fig.texts[1].get_position()[1]
        assert k_art.get_position()[1] > headline_y
        # Kicker color passes WCAG AA contrast on the theme's background
        assert contrast_ratio(to_hex(k_art.get_color()), THEMES[style_name].background) >= 4.5

        # Spec & embedded PNG round-trip
        spec = fig.to_spec()
        assert spec["kicker"] == kicker_in
        out_png = tmp_path / f"kicker_{style_name}.png"
        fig.save(out_png, write_spec=True)
        reloaded_png = mint.load(out_png)
        assert reloaded_png.kicker == kicker_in
        assert reloaded_png.to_spec() == spec

        spec_json = json.loads(out_png.with_suffix(".json").read_text(encoding="utf-8"))
        assert spec_json["kicker"] == kicker_in
        reloaded_json = mint.load(spec_json)
        assert reloaded_json.kicker == kicker_in
        out_png2 = tmp_path / f"kicker_{style_name}_2.png"
        reloaded_json.save(out_png2)
        assert out_png.read_bytes() == out_png2.read_bytes()

    def test_kicker_on_panel_gives_helpful_explain_hint(self) -> None:
        with pytest.raises(mint.ExplainError) as exc_info:
            mint.compare({"a": 1, "b": 2}, kicker="SECTION")  # type: ignore[call-arg]
        assert "mint.explain" in exc_info.value.fix_hint

    def test_top_flag_defaults_and_enabled_on_mint_and_editorial(self) -> None:
        default_theme = Theme(name="plain", description="plain")
        assert default_theme.top_flag is False
        assert default_theme.top_flag_color is None
        assert default_theme.top_flag_width_mm == pytest.approx(14.0)
        assert default_theme.top_flag_lw == pytest.approx(3.2)

        assert MINT_THEME.top_flag is True
        assert MINT_THEME.top_flag_color == "#0F8B6D"
        assert EDITORIAL_THEME.top_flag is True
        assert EDITORIAL_THEME.top_flag_color == "#CD4324"

        for style_name, expected_hex in (("mint", "#0F8B6D"), ("editorial", "#CD4324")):
            res = mint.explain(
                "Checkout p99 is 4x higher than search",
                mint.compare({"checkout": 1840, "search": 460}, label="p99", unit="ms"),
                source="synthetic",
                style=style_name,
            )
            flags = [p for p in res.fig.patches if getattr(p, "_mintfig_top_flag", False)]
            assert len(flags) == 1
            flag = flags[0]
            assert isinstance(flag, Rectangle)
            assert to_hex(flag.get_facecolor()).upper() == expected_hex
            assert flag.get_width() > 0.05
            assert flag.get_height() > 0.0
            # Top rule Line2D still lives in fig.artists (2 total with footer rule)
            assert len(res.fig.artists) == 2

    def test_custom_theme_with_top_flag_without_top_rule(self) -> None:
        custom = Theme(
            name="flag_only",
            description="Custom flag-only theme",
            top_rule=False,
            top_flag=True,
            top_flag_color="#1F5A9D",
            top_flag_width_mm=18.0,
            top_flag_lw=3.6,
        )
        res = mint.explain(
            "Checkout p99 is 4x higher than search",
            mint.compare({"checkout": 1840, "search": 460}, label="p99", unit="ms"),
            style=custom,
        )
        assert res.ok is True
        assert res.issues == []
        flags = [p for p in res.fig.patches if getattr(p, "_mintfig_top_flag", False)]
        assert len(flags) == 1
        assert to_hex(flags[0].get_facecolor()).upper() == "#1F5A9D"


# --------------------------------------------------------------------------- #
# 3. Editorial inline y-ticks (_apply_inline_y_ticks / _clear_inline_ticks)
# --------------------------------------------------------------------------- #


class TestEditorialInlineYTicks:
    def test_all_editorial_y_ticks_remain_visible_with_halo_and_zero_crossings(self) -> None:
        res = mint.explain(
            "Retriever B lifts accuracy by 9 points while keeping latency steady across loads",
            mint.compare(
                {"Retriever B": 86, "Retriever A": 77, "Hybrid": 81, "BM25": 68},
                error={
                    "Retriever B": (84, 88),
                    "Retriever A": (75, 79),
                    "Hybrid": (79, 83),
                    "BM25": (66, 70),
                },
                error_label="95% CI",
                baseline="BM25",
                highlight=["Retriever B", "Hybrid"],
                label="Top-5 recall",
                unit="%",
                title="Retriever B leads outside noise",
            ),
            mint.trend(
                [10, 25, 50, 100, 200],
                {
                    "Retriever B": [42, 46, 51, 58, 66],
                    "Hybrid": [48, 56, 68, 86, 112],
                    "BM25": [28, 30, 33, 37, 42],
                },
                baseline="BM25",
                highlight=["Retriever B", "Hybrid"],
                label="p95 latency",
                unit="ms",
                x_label="Queries per second",
                title="Hybrid slows sharply past 100 QPS",
            ),
            style="editorial",
            source="synthetic example data",
        )
        assert res.ok is True
        assert res.ship is True
        assert res.issues == []

        ax = res["b"]
        inline = ax._mintfig_inline_ticks
        visible_notes = [note for note, _ in inline if note.get_visible()]
        visible_labels = [note.get_text() for note in visible_notes]
        # Previously 50 and 25 silently disappeared — all four must now appear!
        assert len(visible_notes) == len(inline)
        assert visible_labels == ["25", "50", "75", "100 ms"]

        renderer = res.fig.canvas.get_renderer()
        paths = [
            p for p in explainer._data_paths(ax, []) if len(p.vertices) and np.ptp(p.vertices[:, 1]) > 0.5
        ]
        for note in visible_notes:
            # Every inline y-tick carries a subtle theme.background halo
            patch = note.get_bbox_patch()
            assert patch is not None
            assert to_hex(patch.get_facecolor()).upper() == EDITORIAL_THEME.background.upper()
            assert (patch.get_alpha() or 1.0) >= 0.90
            # No data curve cuts across any inline y-tick label
            box = note.get_window_extent(renderer)
            assert not any(p.intersects_bbox(box, filled=False) for p in paths)

    def test_editorial_inline_y_ticks_keeps_zero_baseline_tick(self) -> None:
        res = mint.explain(
            "Throughput rose 3x over five checkpoints from a zero baseline",
            mint.trend(
                [1, 2, 3, 4, 5],
                {"Model A": [18, 34, 49, 62, 74], "Baseline": [12, 16, 19, 22, 24]},
                baseline="Baseline",
                highlight="Model A",
                label="Throughput",
                unit="req/s",
                x_label="Checkpoint",
                zero=True,
            ),
            style="editorial",
            source="synthetic",
        )
        assert res.ok is True
        assert res.ship is True
        assert res.issues == []
        ax = res["a"]
        visible_labels = [note.get_text() for note, _ in ax._mintfig_inline_ticks if note.get_visible()]
        assert visible_labels[0] == "0"
        assert visible_labels[-1].endswith(" req/s")
        assert len(visible_labels) == len(ax._mintfig_inline_ticks)


# --------------------------------------------------------------------------- #
# 4. Font stack upgrade + local font auto-registration
# --------------------------------------------------------------------------- #


class TestFontStackAndAutoRegistration:
    def test_editorial_sans_and_serif_font_priority(self) -> None:
        assert EDITORIAL_SANS_FONTS[:4] == ("Inter", "IBM Plex Sans", "Source Sans 3", "Helvetica Neue")
        assert EDITORIAL_SANS_FONTS[-2:] == ("Liberation Sans", "DejaVu Sans")
        assert EDITORIAL_SERIF_FONTS[:4] == ("Newsreader", "Source Serif 4", "Georgia", "Charter")
        assert "DejaVu Serif" in EDITORIAL_SERIF_FONTS

        # Screen rc_params includes the upgraded sans & serif stacks
        rc = rc_params("screen")
        for fam in ("Inter", "IBM Plex Sans", "Source Sans 3", "Helvetica Neue", "DejaVu Sans"):
            assert fam in rc["font.sans-serif"]
        for fam in ("Newsreader", "Source Serif 4", "Georgia", "Charter", "DejaVu Serif"):
            assert fam in rc["font.serif"]

        # Themes use the upgraded stacks
        assert MINT_THEME.body_family == EDITORIAL_SANS_FONTS
        assert EDITORIAL_THEME.body_family == EDITORIAL_SANS_FONTS
        assert EDITORIAL_THEME.title_family == EDITORIAL_SERIF_FONTS

    def test_register_local_fonts_adds_ttf_and_ignores_invalid_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Copy a real bundled DejaVu font into a fresh temp directory alongside junk files
        dejavu_path = Path(
            font_manager.findfont(font_manager.FontProperties(family="DejaVu Sans"))
        )
        local_ttf = tmp_path / "LocalTestSans.ttf"
        shutil.copy2(dejavu_path, local_ttf)
        (tmp_path / "corrupt.otf").write_bytes(b"not a real font")
        (tmp_path / "README.txt").write_text("ignore me", encoding="utf-8")

        added_paths: list[str] = []
        orig_addfont = font_manager.fontManager.addfont

        def _spy_addfont(path: str | Path) -> None:
            added_paths.append(str(path))
            orig_addfont(path)

        monkeypatch.setattr(font_manager.fontManager, "addfont", _spy_addfont)
        # Snapshot ttflist so this test leaves global FontManager state clean
        orig_ttflist = list(font_manager.fontManager.ttflist)
        try:
            registered = register_local_fonts(tmp_path)
            assert local_ttf in registered
            assert str(local_ttf.resolve()) in added_paths
            # Second call is idempotent (already in ttflist)
            assert register_local_fonts(tmp_path) == []
        finally:
            font_manager.fontManager.ttflist[:] = orig_ttflist
            _resolve_font_tuple.cache_clear()

    def test_resolve_font_tuple_require_bold_skips_regular_only_family(self) -> None:
        resolved = _resolve_font_tuple(EDITORIAL_SANS_FONTS, require_bold=True)
        assert resolved in EDITORIAL_SANS_FONTS
        # Verify the chosen font actually has a bold face available (or fell back cleanly)
        entries = [
            e for e in font_manager.fontManager.ttflist if e.name.lower() == resolved.lower()
        ]
        if entries:
            assert any(
                (isinstance(e.weight, (int, float)) and float(e.weight) >= 600)
                or "bold" in str(e.weight).lower()
                for e in entries
            )
