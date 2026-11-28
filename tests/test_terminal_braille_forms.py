"""Tests for expanded BrailleCanvas, high-res Braille/true-color chart forms, editorial chrome, and side-by-side layout."""

from __future__ import annotations

import os
import re

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pytest

matplotlib.use("Agg")

import mintfig as mint
from mintfig.terminal import (
    BrailleCanvas,
    _visible_len,
    render_terminal,
    show_in_terminal,
)

_BRAILLE_RE = re.compile(r"[\u2801-\u28ff]")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_BG_RGB_RE = re.compile(r"\x1b\[48;2;(\d+);(\d+);(\d+)m")
_FG_RGB_RE = re.compile(r"\x1b\[(?:1;)?38;2;(\d+);(\d+);(\d+)m")


def _rgb_seq(hex_color: str, *, bg: bool = False) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    code = "48" if bg else "38"
    return f"{code};2;{r};{g};{b}m"


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _has_braille(text: str) -> bool:
    return bool(_BRAILLE_RE.search(text))


class TestBrailleCanvasPrimitives:
    def test_draw_band_stipples_below_curve_priority(self) -> None:
        c = BrailleCanvas(16, 6)
        xs = [0.0, 10.0, 20.0, 31.0]
        lo_ys = [20.0, 16.0, 12.0, 8.0]
        hi_ys = [12.0, 8.0, 4.0, 0.0]
        # Draw CI band at priority=0, then main curve at priority=2
        c.draw_band(xs, lo_ys, hi_ys, color="#23765C", priority=0)
        c.draw_line(0, 16, 31, 4, color="#38DDA9", priority=2)

        plain = c.render(color=False)
        colored = c.render(color=True)
        joined_plain = "\n".join(plain)
        joined_colored = "\n".join(colored)

        assert _has_braille(joined_plain)
        # Shaded 24-bit ANSI ribbon background and foreground curve color both appear
        assert "\x1b[48;2;35;118;92m" in joined_colored
        assert _rgb_seq("#38DDA9") in joined_colored
        # Monochrome stipple fallback stays sparse (not solid U+28FF blocks everywhere)
        solid_cells = joined_plain.count("⣿")
        braille_cells = len(_BRAILLE_RE.findall(joined_plain))
        assert braille_cells > 10
        assert solid_cells < braille_cells // 2

        # Handles NaN gaps and narrow bands without error
        c_gap = BrailleCanvas(10, 4)
        c_gap.draw_band(
            [0, 6, float("nan"), 12, 19],
            [10, 9, float("nan"), 6, 5],
            [9, 8, float("nan"), 5, 4],
            color="#69B4F8",
            priority=0,
        )
        assert _has_braille("\n".join(c_gap.render(color=False)))

    def test_draw_rect_and_draw_diamond(self) -> None:
        c = BrailleCanvas(12, 5)
        c.draw_rect(2, 2, 7, 10, color="#38DDA9", fill=True, priority=1)
        c.draw_rect(10, 2, 15, 10, color="#69B4F8", fill=False, priority=1)
        c.draw_diamond(20, 10, 3.0, 3.0, color="#CE62B0", fill=True, priority=2)

        colored = "\n".join(c.render(color=True))
        plain = "\n".join(c.render(color=False))
        assert _has_braille(plain)
        assert _rgb_seq("#38DDA9") in colored
        assert _rgb_seq("#69B4F8") in colored
        assert _rgb_seq("#CE62B0") in colored
        assert [_strip_ansi(r) for r in c.render(color=True)] == c.render(color=False)


class TestHighResBrailleChartForms:
    def test_trend_with_ci_band_events_and_reference(self) -> None:
        exp = mint.explain(
            "Spearmint clears the 0.85 target with a tight 95% CI after warmup",
            mint.trend(
                [0, 200, 400, 600, 800, 1000],
                {
                    "Spearmint": [0.42, 0.64, 0.78, 0.86, 0.91, 0.94],
                    "Baseline": [0.41, 0.55, 0.63, 0.69, 0.72, 0.74],
                },
                band={
                    "Spearmint": [0.05, 0.04, 0.035, 0.03, 0.025, 0.02],
                    "Baseline": [0.04, 0.04, 0.04, 0.035, 0.035, 0.03],
                },
                band_label="95% CI",
                events={400: "LR decay"},
                reference=(0.85, "target"),
                highlight="Spearmint",
                title="Validation accuracy across steps",
                label="Accuracy",
                x_label="Step",
            ),
            style="pine",
        )
        try:
            colored = render_terminal(exp, width=82, color=True, high_res=True)
            plain = render_terminal(exp, width=82, color=False, high_res=True)
        finally:
            plt.close(exp.fig)

        assert _has_braille(colored)
        assert "Spearmint" in plain and "Baseline" in plain
        assert "95% CI" in plain
        assert "not shown" not in plain
        assert "LR decay" in plain
        assert "target" in plain
        assert _rgb_seq(exp.theme.series_colors[0]) in colored

    def test_relate_scatter_fit_and_pareto_frontier(self) -> None:
        exp = mint.explain(
            "Three models define the upper-left accuracy-latency Pareto frontier",
            mint.relate(
                [12, 18, 25, 32, 45, 58, 72, 90],
                [76, 84, 81, 89, 86, 93, 91, 95],
                names=["Nano", "Mini", "Std-A", "Pro", "Std-B", "Ultra", "Heavy", "Max"],
                groups=["Edge", "Edge", "Base", "Edge", "Base", "Cloud", "Base", "Cloud"],
                fit=True,
                frontier=True,
                reference=(85.0, "SLA"),
                x_label="Latency",
                x_unit="ms",
                y_label="Accuracy",
                unit="%",
                title="Accuracy vs latency Pareto frontier",
            ),
            style="pine",
        )
        try:
            colored = render_terminal(exp, width=82, color=True, high_res=True)
            plain = render_terminal(exp, width=82, color=False, high_res=True)
        finally:
            plt.close(exp.fig)

        assert _has_braille(colored)
        assert "OLS fit" in plain
        assert "r = " in plain
        assert "Pareto frontier" in plain
        assert "SLA" in plain
        assert "Edge" in plain and "Cloud" in plain
        assert _rgb_seq(exp.theme.accent_colors[0]) in colored

    @pytest.mark.parametrize("mode", ["swarm", "dots", "quantile"])
    def test_distribution_braille_beeswarm_modes(self, mode: str) -> None:
        rng = np.random.default_rng(42)
        groups = {
            "Cache hit": list(rng.normal(444.0, 55.0, size=45)),
            "Warm miss": list(rng.normal(736.0, 90.0, size=45)),
            "Cold start": list(rng.normal(1174.0, 140.0, size=45)),
        }
        exp = mint.explain(
            "Cache hits stay well below the 600 ms SLA while cold starts exceed 1,100 ms",
            mint.distribution(
                groups,
                mode=mode,
                reference=(600.0, "SLA"),
                highlight="Cache hit",
                title="Service latency by cache tier",
                label="Latency",
                unit="ms",
            ),
            style="pine",
        )
        try:
            colored = render_terminal(exp, width=82, color=True, high_res=True)
            plain = render_terminal(exp, width=82, color=False, high_res=True)
        finally:
            plt.close(exp.fig)

        assert _has_braille(colored)
        assert "Cache hit" in plain
        assert "Warm miss" in plain
        assert "Cold start" in plain
        assert "ms" in plain
        assert "median" in plain and "IQR" in plain
        assert "SLA" in plain
        assert _rgb_seq(exp.theme.series_colors[0]) in colored

    def test_change_braille_slopegraph(self) -> None:
        exp = mint.explain(
            "Auth latency dropped 23% after connection pooling while Search held flat",
            mint.change(
                {"Auth": 310, "Checkout": 520, "Search": 215, "Profile": 140},
                {"Auth": 240, "Checkout": 410, "Search": 220, "Profile": 125},
                labels=("v2.2", "v2.3"),
                highlight="Auth",
                title="p95 latency before and after v2.3",
                label="p95 latency",
                unit="ms",
            ),
            style="pine",
        )
        try:
            colored = render_terminal(exp, width=82, color=True, high_res=True)
            plain = render_terminal(exp, width=82, color=False, high_res=True)
        finally:
            plt.close(exp.fig)

        assert _has_braille(colored)
        assert "v2.2" in plain and "v2.3" in plain
        assert "Auth 310 → 240 ms (−23%)" in plain
        assert "Checkout" in plain
        assert "\x1b[" in colored
        assert "\x1b[" not in plain

    def test_forest_braille_with_null_line_pooled_diamond_and_n_column(self) -> None:
        exp = mint.explain(
            "Checkout redesign lifts conversion +2.1 pp pooled across all four cohorts",
            mint.forest(
                {"US-West": 2.6, "EU-Central": 2.1, "APAC": 1.8, "Enterprise": 0.7},
                error={
                    "US-West": (1.5, 3.7),
                    "EU-Central": (1.0, 3.2),
                    "APAC": (0.4, 3.2),
                    "Enterprise": (-0.6, 2.0),
                },
                error_label="95% CI",
                reference=0.0,
                pooled={"label": "Pooled", "value": 2.1, "lo": 1.4, "hi": 2.8, "n": 48200},
                n={"US-West": 18400, "EU-Central": 14200, "APAC": 9600, "Enterprise": 6000},
                highlight="US-West",
                title="Conversion lift by cohort",
                label="Conversion lift",
                unit="pp",
            ),
            style="pine",
        )
        try:
            colored = render_terminal(exp, width=88, color=True, high_res=True)
            plain = render_terminal(exp, width=88, color=False, high_res=True)
        finally:
            plt.close(exp.fig)

        assert _has_braille(colored)
        assert "◆" in plain
        assert "Pooled" in plain
        assert "US-West" in plain
        assert "18,400" in plain
        assert "48,200" in plain
        assert "95% CI" in plain
        assert "null" in plain
        assert "─" in plain

    def test_matrix_truecolor_confusion_diverging_triangle_and_plain_fallback(self) -> None:
        # 1. Row-normalized confusion matrix with counts in 24-bit ANSI true-color
        exp_cm = mint.explain(
            "Classifier reaches 84% recall on Billing with main confusion into Account",
            mint.matrix(
                [
                    [84, 10, 6],
                    [7, 88, 5],
                    [4, 9, 87],
                ],
                rows=["Billing", "Account", "Tech"],
                cols=["Billing", "Account", "Tech"],
                normalize="row",
                show_counts=True,
                title="Ticket classifier confusion matrix",
                label="Predicted share",
            ),
            style="pine",
        )
        try:
            colored_cm = render_terminal(exp_cm, width=82, color=True, high_res=True)
            plain_cm = render_terminal(exp_cm, width=82, color=False, high_res=True)
        finally:
            plt.close(exp_cm.fig)

        assert _BG_RGB_RE.search(colored_cm) is not None
        assert _FG_RGB_RE.search(colored_cm) is not None
        # Automatic WCAG black (#111111) or white (#F8FAFC) cell text
        assert _rgb_seq("#111111") in colored_cm or _rgb_seq("#F8FAFC") in colored_cm
        assert "84% (84)" in _strip_ansi(colored_cm)
        assert "88% (88)" in _strip_ansi(colored_cm)
        # Clean box-table fallback when color=False
        assert "\x1b[" not in plain_cm
        assert "┌" in plain_cm and "│" in plain_cm and "└" in plain_cm
        assert "84% (84)" in plain_cm

        # 2. Diverging lower-triangle correlation matrix
        exp_div = mint.explain(
            "Latency correlates strongly negatively with Throughput (−0.84)",
            mint.matrix(
                [
                    [1.00, -0.84, 0.52],
                    [-0.84, 1.00, -0.35],
                    [0.52, -0.35, 1.00],
                ],
                rows=["Latency", "Throughput", "CPU"],
                cols=["Latency", "Throughput", "CPU"],
                diverging=True,
                center=0.0,
                triangle="lower",
                title="Metric correlations (lower triangle)",
                label="r",
            ),
            style="mint",
        )
        try:
            colored_div = render_terminal(exp_div, width=82, color=True, high_res=True)
        finally:
            plt.close(exp_div.fig)

        stripped_div = _strip_ansi(colored_div)
        assert _BG_RGB_RE.search(colored_div) is not None
        assert "lower triangle" in stripped_div
        # Upper-triangle duplicate should be masked (only one -0.84 cell in the matrix body rows)
        matrix_lines = [
            ln
            for ln in stripped_div.splitlines()
            if ln.startswith("  ") and any(k in ln for k in ("Latency", "Throughput", "CPU"))
        ]
        assert sum(ln.count("0.84") for ln in matrix_lines) == 1


class TestEditorialChromeSideBySideAndEnv:
    def test_editorial_chrome_kicker_and_top_accent_flag(self) -> None:
        exp = mint.explain(
            "Spearmint reaches 0.93 accuracy while Baseline stalls at 0.72",
            mint.trend(
                [0, 500, 1000],
                {"Spearmint": [0.40, 0.78, 0.93], "Baseline": [0.40, 0.62, 0.72]},
                label="Accuracy",
                x_label="Step",
                highlight="Spearmint",
            ),
            kicker="Model Evaluation",
            subtitle="Held-out benchmark suite, n = 5 seeds",
            source="internal eval harness",
            note="shaded bands show ±1 sd",
            style="mint",
        )
        try:
            high_color = render_terminal(exp, width=78, color=True, high_res=True)
            high_plain = render_terminal(exp, width=78, color=False, high_res=True)
            compat_color = render_terminal(exp, width=78, color=True, high_res=False)
        finally:
            plt.close(exp.fig)

        high_lines = _strip_ansi(high_color).splitlines()
        # Top accent flag bar on line 0 + uppercase kicker on line 1
        assert high_lines[0].startswith("━━━━") and "─" in high_lines[0]
        assert "MODEL EVALUATION" in high_lines[1]
        assert _rgb_seq(exp.theme.top_flag_color or exp.theme.accent_colors[0]) in high_color.splitlines()[0]
        assert "Note: shaded bands" in high_plain
        assert "Source: internal eval harness" in high_plain

        # Backwards-compatible default (high_res=False) keeps takeaway on line 0
        assert "Spearmint reaches 0.93" in _strip_ansi(compat_color.splitlines()[0])

    def test_side_by_side_two_column_composer_and_narrow_fallback(self) -> None:
        rng = np.random.default_rng(11)
        data = {
            "Cache hit": list(rng.normal(440.0, 45.0, size=50)),
            "Warm miss": list(rng.normal(730.0, 80.0, size=50)),
            "Cold start": list(rng.normal(1170.0, 130.0, size=50)),
        }
        exp = mint.explain(
            "Cache hits stay under 600 ms on both ECDF and beeswarm views",
            mint.distribution(
                data,
                mode="ecdf",
                title="Latency ECDF",
                label="Latency",
                unit="ms",
                highlight="Cache hit",
            ),
            mint.distribution(
                data,
                mode="swarm",
                title="Latency beeswarm",
                label="Latency",
                unit="ms",
                highlight="Cache hit",
            ),
            layout=[["a", "b"]],
            style="pine",
        )
        try:
            wide_color = render_terminal(exp, width=116, color=True, high_res=True)
            wide_plain = render_terminal(exp, width=116, color=False, high_res=True)
            narrow_plain = render_terminal(exp, width=84, color=False, high_res=True)
        finally:
            plt.close(exp.fig)

        # Wide terminal joins [a] and [b] side-by-side with dim vertical gutter "  │  " at col_w
        wide_lines = _strip_ansi(wide_color).splitlines()
        col_w = (116 - 5) // 2
        gutter_lines = [ln for ln in wide_lines if ln[col_w : col_w + 5] == "  │  "]
        assert len(gutter_lines) >= 12
        # Both panel titles share the exact same header row!
        assert any("[a] Latency ECDF" in ln and "[b] Latency beeswarm" in ln for ln in gutter_lines)
        # Plain wide output stays strictly within width=116 and has zero ANSI
        assert "\x1b[" not in wide_plain
        assert all(_visible_len(ln) <= 116 for ln in wide_plain.splitlines())

        # Narrow terminal (< 104) falls back to vertical stack
        narrow_lines = narrow_plain.splitlines()
        assert not any("[a] Latency ECDF" in ln and "[b] Latency beeswarm" in ln for ln in narrow_lines)
        assert any("[a] Latency ECDF" in ln for ln in narrow_lines)
        assert any("[b] Latency beeswarm" in ln for ln in narrow_lines)

    def test_auto_width_and_no_color_force_color_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        exp = mint.explain(
            "Alpha outperforms Beta by 20 points",
            mint.compare({"Alpha": 92, "Beta": 72}, label="Score", unit="pts", highlight="Alpha"),
            style="pine",
        )
        try:
            # Clamp small terminal (30 cols) -> 56
            monkeypatch.setattr("shutil.get_terminal_size", lambda fallback=(80, 24): os.terminal_size((30, 24)))
            out_min = render_terminal(exp, width="auto", color=False, high_res=True)
            assert _visible_len(out_min.splitlines()[0]) == 56

            # Mid terminal (96 cols) -> 96
            monkeypatch.setattr("shutil.get_terminal_size", lambda fallback=(80, 24): os.terminal_size((96, 24)))
            out_mid = render_terminal(exp, width="auto", color=False, high_res=True)
            assert _visible_len(out_mid.splitlines()[0]) == 96

            # Ultra-wide terminal (240 cols) -> clamped to 132
            monkeypatch.setattr("shutil.get_terminal_size", lambda fallback=(80, 24): os.terminal_size((240, 24)))
            out_max = render_terminal(exp, width="auto", color=False, high_res=True)
            assert _visible_len(out_max.splitlines()[0]) == 132

            # NO_COLOR disables color when color=None
            monkeypatch.setenv("NO_COLOR", "1")
            monkeypatch.delenv("FORCE_COLOR", raising=False)
            out_no_color = render_terminal(exp, width=78, color=None, high_res=True)
            assert "\x1b[" not in out_no_color

            # Explicit color=True overrides NO_COLOR
            out_explicit = render_terminal(exp, width=78, color=True, high_res=True)
            assert "\x1b[" in out_explicit

            # FORCE_COLOR=1 enables color when NO_COLOR unset and color=None
            monkeypatch.delenv("NO_COLOR", raising=False)
            monkeypatch.setenv("FORCE_COLOR", "1")
            out_force = render_terminal(exp, width=78, color=None, high_res=True)
            assert "\x1b[" in out_force

            # Explicit color=False overrides FORCE_COLOR
            out_explicit_off = render_terminal(exp, width=78, color=False, high_res=True)
            assert "\x1b[" not in out_explicit_off

            # show_in_terminal also supports width="auto" and color=None with NO_COLOR
            show_no_color = show_in_terminal(
                exp, mode="braille", width="auto", color=None, env={"NO_COLOR": "1"}
            )
            assert "\x1b[" not in show_no_color
        finally:
            plt.close(exp.fig)
