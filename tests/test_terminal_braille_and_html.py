"""Tests for 2x4 Unicode Braille terminal plotting, colored takeaways, and HTML controls."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pytest

matplotlib.use("Agg")

import mintfig as mint
from mintfig.interactive import render_html, render_html_fragment
from mintfig.terminal import BrailleCanvas, render_terminal, show_in_terminal

_BRAILLE_RE = re.compile(r"[\u2801-\u28ff]")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _rgb_seq(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"38;2;{r};{g};{b}m"


def _has_braille(text: str) -> bool:
    return bool(_BRAILLE_RE.search(text))


class TestBrailleCanvas:
    def test_dimensions_and_subpixel_bitmask(self) -> None:
        with pytest.raises(ValueError):
            BrailleCanvas(0, 4)
        with pytest.raises(ValueError):
            BrailleCanvas(4, 0)

        c = BrailleCanvas(1, 1)
        assert (c.px_width, c.px_height) == (2, 4)
        # All 8 sub-pixels on -> full braille cell ⣿ (U+28FF)
        for y in range(4):
            for x in range(2):
                c.set_pixel(x, y)
        assert c.render(color=False) == ["⣿"]

        # Single top-left dot -> ⠁ (U+2801); bottom-right dot -> ⢀ (U+2880)
        c2 = BrailleCanvas(2, 1)
        c2.set_pixel(0, 0)
        c2.set_pixel(3, 3)
        assert c2.render(color=False) == ["⠁⢀"]

    def test_draw_line_step_point_and_truecolor_priority(self) -> None:
        c = BrailleCanvas(12, 4)
        c.draw_hline(8, color="#587067", dashed=True, priority=0)
        c.draw_line(0, 15, 23, 0, color="#38DDA9", priority=2)
        c.draw_point(23, 0, color="#CE62B0", radius=1, priority=3)
        plain = c.render(color=False)
        colored = c.render(color=True)

        assert len(plain) == 4
        assert all(len(row) == 12 for row in plain)
        assert _has_braille("\n".join(plain))
        assert "\x1b[" not in "\n".join(plain)

        joined = "\n".join(colored)
        assert _rgb_seq("#38DDA9") in joined
        assert _rgb_seq("#CE62B0") in joined
        assert _rgb_seq("#587067") in joined
        # Stripping ANSI restores exact character grid
        assert [_ANSI_RE.sub("", r) for r in colored] == plain

        # Step curve (post & pre)
        s = BrailleCanvas(10, 4)
        s.draw_step([0, 6, 14, 19], [15, 10, 4, 0], color="#69B4F8", where="post")
        s_out = "\n".join(s.render(color=True))
        assert _has_braille(s_out)
        assert _rgb_seq("#69B4F8") in s_out


class TestHighResBrailleTerminalCharts:
    def test_trend_braille_with_reference_and_colored_direct_labels(self) -> None:
        exp = mint.explain(
            "Spearmint clears the 0.85 accuracy target while Baseline stalls at 0.72",
            mint.trend(
                [0, 250, 500, 750, 1000, 1500, 2000],
                {
                    "Spearmint": [0.32, 0.58, 0.74, 0.83, 0.88, 0.91, 0.93],
                    "Baseline": [0.31, 0.49, 0.60, 0.66, 0.69, 0.71, 0.72],
                },
                title="Spearmint surpasses target by step 800",
                label="Validation accuracy",
                x_label="Training step",
                highlight="Spearmint",
                reference=(0.85, "target"),
            ),
            style="pine",
        )
        try:
            default_out = render_terminal(exp, width=78, color=False)
            braille_out = render_terminal(exp, width=78, color=True, high_res=True)
            braille_plain = render_terminal(exp, width=78, color=False, high_res=True)
        finally:
            plt.close(exp.fig)

        # Backwards-compatible default stays sparklines (no Braille)
        assert not _has_braille(default_out)
        assert any(ch in default_out for ch in "▁▂▃▄▅▆▇█")

        # High-res Braille renders crisp sub-pixel curves + pine theme true-color ANSI
        assert _has_braille(braille_out)
        assert _has_braille(braille_plain)
        assert "\x1b[" not in braille_plain
        assert "Spearmint" in braille_plain
        assert "Baseline" in braille_plain
        assert "target" in braille_plain
        assert _rgb_seq(exp.theme.series_colors[0]) in braille_out

    def test_ecdf_relate_and_histogram_braille_panels(self) -> None:
        rng = np.random.default_rng(7)
        fast = list(rng.normal(24.0, 4.0, size=60))
        slow = list(rng.normal(52.0, 9.0, size=60))
        xs = list(np.linspace(1.0, 10.0, 30))
        ys = [2.1 * x + float(rng.normal(0, 1.2)) for x in xs]

        exp = mint.explain(
            "Fast path cuts median latency in half while throughput scales linearly",
            mint.distribution(
                {"Fast": fast, "Slow": slow},
                mode="ecdf",
                title="Tail latency ECDF",
                label="Latency",
                unit="ms",
                highlight="Fast",
            ),
            mint.relate(
                xs,
                ys,
                groups=["Batch"] * 15 + ["Stream"] * 15,
                fit=True,
                title="Linear scaling with batch size",
                x_label="Workers",
                y_label="Throughput",
                unit="req/s",
            ),
            mint.histogram(
                fast,
                bins=12,
                title="Fast latency density",
                label="Latency",
                unit="ms",
            ),
            style="mint",
        )
        try:
            out = render_terminal(exp, width=80, color=True, high_res=True)
            plain = render_terminal(exp, width=80, color=False, high_res=True)
        finally:
            plt.close(exp.fig)

        assert _has_braille(out)
        assert "p50" in plain and "p95" in plain and "p99" in plain
        assert "OLS fit" in plain and "r = " in plain
        assert "median=" in plain
        assert _rgb_seq(exp.theme.series_colors[0]) in out
        assert _rgb_seq(exp.theme.series_colors[1]) in out

    def test_show_in_terminal_braille_mode_and_auto_ansi_fallback(self) -> None:
        exp = mint.explain(
            "Alpha rises steadily above Beta across 5 epochs",
            mint.trend(
                [1, 2, 3, 4, 5],
                {"Alpha": [0.4, 0.55, 0.70, 0.82, 0.90], "Beta": [0.4, 0.45, 0.50, 0.52, 0.55]},
                label="Score",
                x_label="Epoch",
            ),
            style="pine",
        )
        try:
            # Explicit mode="braille"
            explicit = show_in_terminal(exp, mode="braille", color=True)
            # Auto fallback on plain ANSI TTY without Kitty/iTerm2 -> automatic Braille!
            auto_ansi = show_in_terminal(exp, mode="auto", color=True, env={"TERM": "xterm-256color"})
            # Auto fallback with color=False stays non-Braille for Markdown/plain pipes
            auto_plain = show_in_terminal(exp, mode="auto", color=False, env={"TERM": "xterm-256color"})
            # Explicit ASCII stays strictly ASCII
            asc = show_in_terminal(exp, mode="ascii", color=False)
        finally:
            plt.close(exp.fig)

        assert _has_braille(explicit) and "\x1b[" in explicit
        assert _has_braille(auto_ansi) and "\x1b[" in auto_ansi
        assert not _has_braille(auto_plain) and "\x1b[" not in auto_plain
        assert asc.isascii()


class TestColoredTakeawayEntityNames:
    def test_entity_names_colored_in_takeaway_and_panel_title(self) -> None:
        exp = mint.explain(
            "Spearmint beats Baseline by 21 points across every step",
            mint.trend(
                [0, 500, 1000],
                {"Spearmint": [0.40, 0.78, 0.93], "Baseline": [0.40, 0.62, 0.72]},
                title="Spearmint pulls ahead of Baseline early",
                label="Accuracy",
                x_label="Step",
                highlight="Spearmint",
            ),
            style="pine",
        )
        try:
            colored = render_terminal(exp, width=78, color=True, color_names=True)
            uncolored_names = render_terminal(exp, width=78, color=True, color_names=False)
            plain = render_terminal(exp, width=78, color=False, color_names=True)
        finally:
            plt.close(exp.fig)

        headline_line = colored.splitlines()[0]
        # Entity names inside the takeaway get 24-bit ANSI RGB matching theme colors
        assert _rgb_seq(exp.theme.series_colors[0]) in headline_line
        assert "Spearmint" in _ANSI_RE.sub("", headline_line)

        # Panel title also gets colored entity names
        title_line = next(ln for ln in colored.splitlines() if "pulls ahead" in ln)
        assert _rgb_seq(exp.theme.series_colors[0]) in title_line

        # Turning off color_names leaves headline plain bold (no 38;2 RGB on headline)
        assert "38;2;" not in uncolored_names.splitlines()[0]
        # Turning off color emits zero ANSI codes anywhere
        assert "\x1b[" not in plain


class TestInteractiveHtmlUpgrades:
    def _sample_exp(self) -> mint.Explanation:
        return mint.explain(
            "Spearmint scales cleanly with training steps and parameter count",
            mint.trend(
                [0, 500, 1000, 1500, 2000],
                {
                    "Spearmint": [0.35, 0.68, 0.82, 0.89, 0.93],
                    "Baseline": [0.35, 0.54, 0.64, 0.70, 0.72],
                },
                title="Validation curve",
                label="Accuracy",
                x_label="Step",
            ),
            mint.relate(
                [10, 25, 50, 100, 200],
                [0.62, 0.74, 0.83, 0.90, 0.94],
                title="Scaling frontier",
                x_label="Params (M)",
                y_label="Accuracy",
            ),
            mint.compare(
                {"Spearmint": 0.93, "Baseline": 0.72},
                title="Final score",
                label="Accuracy",
            ),
        )

    def test_theme_switcher_copy_svg_and_brush_zones_in_html(self) -> None:
        exp = self._sample_exp()
        try:
            doc = render_html(exp)
            static_doc = render_html(exp, interactive=False)
            compact_doc = render_html(exp, compact=True)
        finally:
            plt.close(exp.fig)

        # Quiet corner controls with all 5 themes + Copy SVG button (never uses banned words)
        for pick in ("auto", "light", "dark", "mint", "pine"):
            assert f'data-mf-theme-pick="{pick}"' in doc
        assert 'data-mf-act="copy-svg"' in doc
        assert "Copy SVG" in doc
        assert "toolbar" not in doc and "Critique" not in doc

        # Live CSS custom properties for Mint and Pine themes
        assert '[data-mf-scheme="mint"]' in doc
        assert '[data-mf-scheme="pine"]' in doc
        assert "--mf-bg:#f8fbfa;" in doc
        assert "--mf-bg:#0f1715;" in doc

        # Drag-to-brush zones emitted for trend (a) and relate (b), NOT compare (c)
        assert 'class="mf-brush-zone"' in doc
        assert 'data-mf-panel="a"' in doc
        assert 'data-mf-panel="b"' in doc
        assert 'data-mf-panel="c"' not in doc
        assert "Zoom into X=" in doc and "compare variance" in doc

        # Click-to-cite marks stay intact alongside brush zones
        assert 'data-mf="' in doc
        assert "XMLSerializer" in doc

        # Every embedded SVG remains valid XML
        svgs = re.findall(r"<svg\b.*?</svg>", doc, flags=re.DOTALL)
        assert svgs
        for svg in svgs:
            root = ET.fromstring(svg)
            assert root.tag.endswith("svg")

        # Non-interactive omits controls and script; compact stays lean (<50% of full)
        assert "data-mf-theme-pick" not in static_doc
        assert "<script>" not in static_doc
        assert len(compact_doc) < len(doc) * 0.5

    def test_fragment_explicit_style_keeps_controls_without_prefers_color_scheme(self) -> None:
        exp = mint.explain(
            "Spearmint leads on dark surface",
            mint.trend([1, 2, 3], {"Spearmint": [1, 2, 3]}, label="Score", x_label="Step"),
            style="pine",
        )
        try:
            frag = render_html_fragment(exp)
        finally:
            plt.close(exp.fig)
        assert "prefers-color-scheme" not in frag
        assert 'data-mf-theme-pick="pine"' in frag
        assert 'data-mf-act="copy-svg"' in frag
