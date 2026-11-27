"""Render the 8-example Braille & 24-bit True-Color Terminal Showcase Gallery.

Writes crisp, Ghostty/pine-styled PNG previews and raw ANSI ``.txt`` captures into
``gallery/output/terminal/`` using the live ``mintfig`` and ``mintchip`` terminal
renderers:

1. ``01_trend_ci_band`` — Training curves with stippled 95% CI ``band=``, ``reference=``, ``events=``
2. ``02_wide_ecdf_and_swarm`` — Wide 2-panel side-by-side (``width=116``) ECDF + beeswarm briefing
3. ``03_relate_pareto_fit`` — Grouped scatter + OLS ``fit=True`` + ``frontier=True`` Pareto hull
4. ``04_change_slopegraph`` — Paired before/after Braille slopegraph with colored deltas
5. ``05_forest_ab_rollout`` — A/B rollout forest plot with null line, CI whiskers, and pooled ``◆``
6. ``06_matrix_confusion_truecolor`` — 24-bit ANSI background row-normalized confusion matrix
7. ``07_kpi_summary_card`` — PR / Release KPI Summary Card with rounded tiles, sparklines & panel
8. ``08_mintchip_braille_table`` — ``mintchip`` shared-scale table (``spark``, ``hist``, ``bullet``, ``heat``, ``status``)

Braille characters (``U+2800..U+28FF``) are rendered as crisp geometric 2×4 sub-pixel
circles (never depending on ``DejaVu Sans Mono``, which lacks Braille glyphs), and
24-bit ANSI background spans (``\\x1b[48;2;r;g;bm``) are painted as solid cell
rectangles behind foreground glyphs.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import mintfig as mint
from mintfig.terminal import render_terminal

OUT_DIR = Path(__file__).resolve().parent / "output" / "terminal"

# Pine dark terminal palette (harmonized with mintfig style="pine" and mintchip "mint_dark")
TERM_BG = (15, 23, 21)          # #0F1715
TITLEBAR_BG = (22, 35, 31)      # #16231F
BORDER_COL = (42, 66, 58)       # #2A423A
HAIRLINE_COL = (30, 48, 42)     # #1E302A
DEFAULT_FG = (232, 241, 238)    # #E8F1EE
TITLE_FG = (152, 178, 169)      # #98B2A9
BADGE_BG = (28, 46, 40)         # #1C2E28
BADGE_FG = (88, 214, 170)       # #58D6AA
PROMPT_FG = (56, 221, 169)      # #38DDA9

# Standard 16-color ANSI fallback table (pine-tuned)
ANSI_16_COLORS: dict[int, tuple[int, int, int]] = {
    30: (48, 64, 59),
    31: (239, 108, 108),
    32: (82, 209, 138),
    33: (229, 181, 103),
    34: (105, 180, 248),
    35: (206, 98, 176),
    36: (56, 221, 169),
    37: (218, 230, 226),
    90: (116, 140, 131),
    91: (248, 134, 134),
    92: (108, 229, 162),
    93: (242, 203, 128),
    94: (138, 198, 252),
    95: (224, 134, 200),
    96: (98, 235, 194),
    97: (244, 250, 248),
}

_SGR_RE = re.compile(r"\x1b\[([0-9;]*)m")

# Unicode Braille Patterns bit -> (col in {0, 1}, row in {0, 1, 2, 3})
_BRAILLE_BITS: tuple[tuple[int, int, int], ...] = (
    (0x01, 0, 0),
    (0x02, 0, 1),
    (0x04, 0, 2),
    (0x40, 0, 3),
    (0x08, 1, 0),
    (0x10, 1, 1),
    (0x20, 1, 2),
    (0x80, 1, 3),
)


@dataclass(frozen=True)
class _Cell:
    ch: str
    fg: tuple[int, int, int]
    bg: tuple[int, int, int] | None
    bold: bool
    dim: bool


def _blend(
    a: tuple[int, int, int], b: tuple[int, int, int], weight_a: float
) -> tuple[int, int, int]:
    w = max(0.0, min(1.0, weight_a))
    return (
        round(a[0] * w + b[0] * (1.0 - w)),
        round(a[1] * w + b[1] * (1.0 - w)),
        round(a[2] * w + b[2] * (1.0 - w)),
    )


def _load_mono_fonts(size: int) -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    """Load crisp monospace Regular + Bold fonts (prefer Menlo on macOS)."""
    candidates: list[tuple[str, int, str, int]] = [
        ("/System/Library/Fonts/Menlo.ttc", 0, "/System/Library/Fonts/Menlo.ttc", 1),
        ("/System/Library/Fonts/Supplemental/Courier New.ttf", 0,
         "/System/Library/Fonts/Supplemental/Courier New Bold.ttf", 0),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 0,
         "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 0),
    ]
    for reg_path, reg_idx, bold_path, bold_idx in candidates:
        if Path(reg_path).is_file():
            reg = ImageFont.truetype(reg_path, size, index=reg_idx)
            bold = (
                ImageFont.truetype(bold_path, size, index=bold_idx)
                if Path(bold_path).is_file()
                else reg
            )
            return reg, bold
    fallback = ImageFont.load_default()
    return fallback, fallback  # type: ignore[return-value]


def _parse_ansi_grid(text: str) -> list[list[_Cell]]:
    """Parse ANSI SGR escape sequences into a 2-D grid of styled character cells."""
    lines = text.splitlines()
    grid: list[list[_Cell]] = []

    fg = DEFAULT_FG
    bg: tuple[int, int, int] | None = None
    bold = False
    dim = False

    for line in lines:
        row: list[_Cell] = []
        pos = 0
        for m in _SGR_RE.finditer(line):
            start, end = m.span()
            if start > pos:
                for ch in line[pos:start]:
                    row.append(_Cell(ch=ch, fg=fg, bg=bg, bold=bold, dim=dim))
            raw_params = m.group(1)
            codes = [int(p) if p else 0 for p in raw_params.split(";")] if raw_params else [0]
            i = 0
            while i < len(codes):
                code = codes[i]
                if code == 0:
                    fg = DEFAULT_FG
                    bg = None
                    bold = False
                    dim = False
                elif code == 1:
                    bold = True
                elif code == 2:
                    dim = True
                elif code == 22:
                    bold = False
                    dim = False
                elif code == 39:
                    fg = DEFAULT_FG
                elif code == 49:
                    bg = None
                elif code == 38 and i + 4 < len(codes) and codes[i + 1] == 2:
                    fg = (codes[i + 2], codes[i + 3], codes[i + 4])
                    i += 4
                elif code == 48 and i + 4 < len(codes) and codes[i + 1] == 2:
                    bg = (codes[i + 2], codes[i + 3], codes[i + 4])
                    i += 4
                elif code in ANSI_16_COLORS:
                    fg = ANSI_16_COLORS[code]
                elif (code - 10) in ANSI_16_COLORS:
                    bg = ANSI_16_COLORS[code - 10]
                i += 1
            pos = end
        if pos < len(line):
            for ch in line[pos:]:
                row.append(_Cell(ch=ch, fg=fg, bg=bg, bold=bold, dim=dim))
        grid.append(row)
    return grid


def render_ansi_to_png(
    ansi_text: str,
    out_path: Path,
    *,
    title: str,
    badge: str = "24-bit ANSI · 2×4 Braille",
    font_size: int = 20,
    supersample: int = 2,
) -> Path:
    """Render ANSI text (including 24-bit bg spans and Braille dots) to a crisp PNG."""
    grid = _parse_ansi_grid(ansi_text)
    max_cols = max((len(r) for r in grid), default=60)
    n_rows = max(len(grid), 1)

    ss = supersample
    reg_font, bold_font = _load_mono_fonts(font_size * ss)
    title_font, _ = _load_mono_fonts(round(font_size * 0.72) * ss)
    badge_font, _ = _load_mono_fonts(round(font_size * 0.62) * ss)

    cell_w = max(1, round(reg_font.getlength("M")))
    # Measure box-drawing vertical pipe height so rounded borders connect seamlessly
    pipe_bbox = reg_font.getbbox("│")
    cell_h = max(round(font_size * ss * 1.28), int(pipe_bbox[3] - pipe_bbox[1]))

    pad_x = 26 * ss
    pad_top = 18 * ss
    pad_bot = 22 * ss
    titlebar_h = 40 * ss
    outer_margin = 14 * ss
    radius = 14 * ss

    inner_w = max_cols * cell_w + 2 * pad_x
    inner_h = titlebar_h + pad_top + n_rows * cell_h + pad_bot
    total_w = inner_w + 2 * outer_margin
    total_h = inner_h + 2 * outer_margin

    img = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Terminal window frame with crisp rounded border
    win_box = (
        outer_margin,
        outer_margin,
        outer_margin + inner_w - 1,
        outer_margin + inner_h - 1,
    )
    draw.rounded_rectangle(
        win_box,
        radius=radius,
        fill=(*TERM_BG, 255),
        outline=(*BORDER_COL, 255),
        width=max(1, round(1.5 * ss)),
    )

    # Titlebar strip (clipped to rounded top corners via mask)
    tb_layer = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    tb_draw = ImageDraw.Draw(tb_layer)
    tb_draw.rounded_rectangle(win_box, radius=radius, fill=(*TITLEBAR_BG, 255))
    tb_draw.rectangle(
        (
            outer_margin,
            outer_margin + titlebar_h,
            outer_margin + inner_w,
            outer_margin + inner_h,
        ),
        fill=(0, 0, 0, 0),
    )
    img.alpha_composite(tb_layer)
    draw = ImageDraw.Draw(img)

    # Re-stroke outer border over titlebar seam and add subtle titlebar bottom hairline
    draw.rounded_rectangle(
        win_box,
        radius=radius,
        outline=(*BORDER_COL, 255),
        width=max(1, round(1.5 * ss)),
    )
    draw.line(
        (
            outer_margin + ss,
            outer_margin + titlebar_h,
            outer_margin + inner_w - ss,
            outer_margin + titlebar_h,
        ),
        fill=(*HAIRLINE_COL, 255),
        width=max(1, ss),
    )

    # Traffic light dots
    dot_y = outer_margin + titlebar_h // 2
    dot_r = round(5.5 * ss)
    for idx, col in enumerate(((224, 108, 98), (229, 181, 103), (56, 221, 169))):
        cx = outer_margin + 22 * ss + idx * 20 * ss
        draw.ellipse((cx - dot_r, dot_y - dot_r, cx + dot_r, dot_y + dot_r), fill=(*col, 255))

    # Command title in titlebar
    prompt_x = outer_margin + 86 * ss
    tb_bbox = title_font.getbbox("$ " + title)
    tb_text_h = tb_bbox[3] - tb_bbox[1]
    tb_y = dot_y - tb_text_h // 2 - tb_bbox[1]
    draw.text((prompt_x, tb_y), "$", font=title_font, fill=(*PROMPT_FG, 255))
    draw.text(
        (prompt_x + round(title_font.getlength("$ ")), tb_y),
        title,
        font=title_font,
        fill=(*TITLE_FG, 255),
    )

    # Subtle right-side badge pill (only if it has comfortable breathing room)
    badge_w = round(badge_font.getlength(badge)) + 18 * ss
    title_end_x = prompt_x + round(title_font.getlength("$ " + title))
    badge_x0 = outer_margin + inner_w - 18 * ss - badge_w
    if badge and badge_x0 > title_end_x + 24 * ss:
        badge_h = 22 * ss
        badge_y0 = dot_y - badge_h // 2
        draw.rounded_rectangle(
            (badge_x0, badge_y0, badge_x0 + badge_w, badge_y0 + badge_h),
            radius=badge_h // 2,
            fill=(*BADGE_BG, 255),
            outline=(*BORDER_COL, 255),
            width=max(1, ss // 2),
        )
        bb = badge_font.getbbox(badge)
        by = dot_y - (bb[3] - bb[1]) // 2 - bb[1]
        bx = badge_x0 + (badge_w - round(badge_font.getlength(badge))) // 2
        draw.text((bx, by), badge, font=badge_font, fill=(*BADGE_FG, 255))

    # Paint terminal grid cells
    origin_x = outer_margin + pad_x
    origin_y = outer_margin + titlebar_h + pad_top
    dot_radius = min(cell_w * 0.175, cell_h * 0.088)
    dash_bbox = reg_font.getbbox("─")
    horiz_mid_offset = (dash_bbox[1] + dash_bbox[3]) / 2.0

    # First pass: solid 24-bit ANSI background cell rectangles (zero seams between adjacent cells)
    for r_idx, row in enumerate(grid):
        y0 = origin_y + r_idx * cell_h
        y1 = y0 + cell_h
        for c_idx, cell in enumerate(row):
            if cell.bg is not None:
                x0 = origin_x + c_idx * cell_w
                draw.rectangle((x0, y0, x0 + cell_w, y1), fill=(*cell.bg, 255))

    # Second pass: foreground glyphs and crisp geometric 2×4 Braille sub-pixel circles
    for r_idx, row in enumerate(grid):
        y0 = origin_y + r_idx * cell_h
        for c_idx, cell in enumerate(row):
            ch = cell.ch
            if ch == " ":
                continue
            x0 = origin_x + c_idx * cell_w
            bg_ref = cell.bg if cell.bg is not None else TERM_BG
            fg_col = _blend(cell.fg, bg_ref, 0.56) if cell.dim else cell.fg
            code = ord(ch)

            if 0x2800 <= code <= 0x28FF:
                mask = code - 0x2800
                if mask == 0:
                    continue
                rad = dot_radius * (1.12 if cell.bold else 1.0)
                for bit, bcol, brow in _BRAILLE_BITS:
                    if mask & bit:
                        cx = x0 + (0.27 if bcol == 0 else 0.73) * cell_w
                        cy = y0 + (0.14 + brow * 0.24) * cell_h
                        draw.ellipse(
                            (cx - rad, cy - rad, cx + rad, cy + rad),
                            fill=(*fg_col, 255),
                        )
            elif ch == "━":
                # Geometric heavy horizontal bar (Menlo Bold lacks U+2501)
                ym = y0 + horiz_mid_offset
                half_h = max(1.5 * ss, cell_h * 0.085)
                draw.rectangle(
                    (x0, ym - half_h, x0 + cell_w, ym + half_h),
                    fill=(*fg_col, 255),
                )
            elif ch == "┃":
                # Geometric heavy vertical bar (matches U+2503 cleanly)
                xm = x0 + cell_w * 0.5
                half_w = max(1.25 * ss, cell_w * 0.14)
                draw.rectangle(
                    (xm - half_w, y0, xm + half_w, y0 + cell_h),
                    fill=(*fg_col, 255),
                )
            else:
                font = bold_font if cell.bold else reg_font
                draw.text((x0, y0), ch, font=font, fill=(*fg_col, 255))

    if ss > 1:
        img = img.resize((total_w // ss, total_h // ss), Image.Resampling.LANCZOS)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, optimize=True)
    return out_path


# --------------------------------------------------------------------------- #
# The 8 Showcase Examples
# --------------------------------------------------------------------------- #


def example_01_trend_ci_band() -> tuple[str, str, str]:
    steps = list(range(0, 2001, 100))
    xs = np.asarray(steps, dtype=float)
    spearmint = (0.38 + 0.56 * (1.0 - np.exp(-xs / 460.0))).round(3).tolist()
    baseline = (0.37 + 0.39 * (1.0 - np.exp(-xs / 520.0))).round(3).tolist()
    ci_sp = (0.042 * np.exp(-xs / 1400.0) + 0.014).round(3).tolist()
    ci_base = (0.046 * np.exp(-xs / 1800.0) + 0.018).round(3).tolist()

    exp = mint.explain(
        "Spearmint v3 clears the 0.85 target after step 800 with a tight 95% CI",
        mint.trend(
            steps,
            {"Spearmint v3": spearmint, "Baseline": baseline},
            band={"Spearmint v3": ci_sp, "Baseline": ci_base},
            band_label="95% CI (5 seeds)",
            events={800: "LR decay"},
            reference=(0.85, "target"),
            highlight="Spearmint v3",
            title="Validation accuracy across training steps",
            label="Accuracy",
            x_label="Step",
        ),
        kicker="Training Telemetry",
        subtitle="Held-out benchmark suite · 5 seeds per run",
        source="runs/spearmint_v3_2026-11",
        style="pine",
    )
    try:
        ansi = render_terminal(exp, width=84, color=True, high_res=True)
    finally:
        plt.close(exp.fig)
    return (
        ansi,
        "mintfig plot training_runs.csv --braille --style pine",
        "24-bit ANSI · 2×4 Braille",
    )


def example_02_wide_ecdf_and_swarm() -> tuple[str, str, str]:
    rng = np.random.default_rng(19)
    groups = {
        "Cache hit": list(np.clip(rng.normal(185.0, 28.0, size=60), 105.0, 275.0)),
        "Warm miss": list(np.clip(rng.normal(415.0, 48.0, size=60), 295.0, 545.0)),
        "Cold": list(np.clip(rng.normal(760.0, 82.0, size=60), 560.0, 950.0)),
    }
    exp = mint.explain(
        "Cache hits stay 100% under the 350 ms SLO while cold requests top 750 ms",
        mint.distribution(
            groups,
            mode="ecdf",
            highlight="Cache hit",
            reference=(350.0, "SLO"),
            title="Latency ECDF",
            label="Latency",
            unit="ms",
        ),
        mint.distribution(
            groups,
            mode="swarm",
            highlight="Cache hit",
            reference=(350.0, "SLO"),
            title="Latency beeswarm",
            label="Latency",
            unit="ms",
        ),
        layout=[["a", "b"]],
        kicker="Latency Briefing",
        subtitle="60 sampled checkout requests per cache tier · side-by-side 116-col view",
        source="prod-us-east · 1h window",
        style="pine",
    )
    try:
        ansi = render_terminal(exp, width=116, color=True, high_res=True)
    finally:
        plt.close(exp.fig)
    return (
        ansi,
        "mintfig show latency_briefing.png --braille --width 116 --style pine",
        "116-col 2-Panel · Braille",
    )


def example_03_relate_pareto_fit() -> tuple[str, str, str]:
    exp = mint.explain(
        "Four models anchor the upper-left accuracy-latency Pareto frontier above SLA",
        mint.relate(
            [11, 16, 22, 26, 31, 38, 44, 52, 60, 68, 76, 86],
            [77.5, 83.4, 80.2, 87.6, 84.1, 90.4, 86.2, 88.9, 92.8, 90.5, 93.1, 94.6],
            names=[
                "Nano", "Mini", "Std-S", "Edge-Pro", "Std-M", "Mid-Pro",
                "Base-L", "Std-L", "Ultra", "Heavy-A", "Heavy-B", "Max",
            ],
            groups=[
                "Edge", "Edge", "Base", "Edge", "Base", "Edge",
                "Base", "Base", "Cloud", "Base", "Cloud", "Cloud",
            ],
            fit=True,
            frontier=True,
            reference=(85.0, "SLA"),
            highlight="Edge",
            x_label="p95 Latency",
            x_unit="ms",
            y_label="Accuracy",
            unit="%",
            title="Accuracy vs latency with OLS fit and Pareto envelope",
        ),
        kicker="Pareto Frontier",
        subtitle="12 evaluated serving configurations across Edge, Base, and Cloud tiers",
        source="eval/pareto_2026-11",
        style="pine",
    )
    try:
        ansi = render_terminal(exp, width=86, color=True, high_res=True)
    finally:
        plt.close(exp.fig)
    return (
        ansi,
        "mintfig plot models.csv --kind relate --braille --style pine",
        "OLS Fit + Pareto · Braille",
    )


def example_04_change_slopegraph() -> tuple[str, str, str]:
    exp = mint.explain(
        "Connection pooling cuts Checkout p95 by 35% and Auth by 27% in v2.3",
        mint.change(
            {"Checkout": 520, "Auth": 310, "Billing": 280, "Search": 215, "Catalog": 145},
            {"Checkout": 340, "Auth": 225, "Billing": 205, "Search": 224, "Catalog": 122},
            labels=("v2.2", "v2.3"),
            highlight=["Checkout", "Auth"],
            title="Service p95 latency before and after v2.3 rollout",
            label="p95 latency",
            unit="ms",
        ),
        kicker="Release Diff",
        subtitle="Production canary comparison · 24h post-deploy",
        source="telemetry/v2.3-canary",
        style="pine",
    )
    try:
        ansi = render_terminal(exp, width=84, color=True, high_res=True)
    finally:
        plt.close(exp.fig)
    return (
        ansi,
        "mintfig diff v2.2_bench.json v2.3_bench.json --braille --style pine",
        "Slopegraph · 2×4 Braille",
    )


def example_05_forest_ab_rollout() -> tuple[str, str, str]:
    exp = mint.explain(
        "Checkout v3 lifts conversion +2.1 pp pooled across five rollout cohorts",
        mint.forest(
            {
                "US-West": 2.7,
                "EU-Central": 2.2,
                "UK-London": 1.9,
                "APAC": 1.6,
                "Enterprise": 0.6,
            },
            error={
                "US-West": (1.6, 3.8),
                "EU-Central": (1.1, 3.3),
                "UK-London": (0.6, 3.2),
                "APAC": (0.2, 3.0),
                "Enterprise": (-0.6, 1.8),
            },
            error_label="95% CI",
            reference=0.0,
            pooled={"label": "Pooled", "value": 2.1, "lo": 1.5, "hi": 2.7, "n": 54600},
            n={
                "US-West": 18400,
                "EU-Central": 14200,
                "UK-London": 8800,
                "APAC": 7400,
                "Enterprise": 5800,
            },
            highlight="US-West",
            title="Conversion lift by cohort against zero null",
            label="Conversion lift",
            unit="pp",
        ),
        kicker="Experiment Rollout",
        subtitle="Fixed-effects A/B analysis · 14-day exposure window",
        source="ab/checkout_v3 (n = 54,600 sessions)",
        style="pine",
    )
    try:
        ansi = render_terminal(exp, width=72, color=True, high_res=True)
    finally:
        plt.close(exp.fig)
    return (
        ansi,
        "mintfig explain ab_rollout.json --braille --style pine",
        "Forest Plot · 2×4 Braille",
    )


def example_06_matrix_confusion_truecolor() -> tuple[str, str, str]:
    exp = mint.explain(
        "Ticket router hits 86% macro recall; Auth-to-Infra (12%) is the main confusion",
        mint.matrix(
            [
                [88, 5, 4, 3],
                [4, 82, 12, 2],
                [3, 8, 86, 3],
                [2, 3, 5, 90],
            ],
            rows=["Billing", "Auth", "Infra", "Docs"],
            cols=["Billing", "Auth", "Infra", "Docs"],
            normalize="row",
            show_counts=True,
            title="Row-normalized confusion matrix (true class vs predicted)",
            label="Predicted share",
        ),
        kicker="Classifier Audit",
        subtitle="Held-out support routing set · n = 400 tickets",
        source="eval/router_v4_2026-11",
        style="pine",
    )
    try:
        ansi = render_terminal(exp, width=84, color=True, high_res=True)
    finally:
        plt.close(exp.fig)
    return (
        ansi,
        "mintfig show confusion_matrix.png --braille --style pine",
        "24-bit ANSI True-Color",
    )


def example_07_kpi_summary_card() -> tuple[str, str, str]:
    card = mint.card(
        "PR #418 cuts checkout p99 latency 38% while holding 99.94% availability",
        [
            {
                "label": "p99 latency",
                "value": "248 ms",
                "delta": "-38%",
                "good": True,
                "spark": [410, 405, 398, 385, 308, 268, 248],
                "note": "vs 400 ms base",
            },
            {
                "label": "Availability",
                "value": "99.94%",
                "delta": "+0.02 pts",
                "good": True,
                "spark": [99.91, 99.92, 99.92, 99.93, 99.93, 99.94, 99.94],
                "note": "SLO 99.90%",
            },
            {
                "label": "Error rate",
                "value": "0.06%",
                "delta": "-0.04 pts",
                "good": True,
                "spark": [0.11, 0.10, 0.10, 0.09, 0.08, 0.07, 0.06],
                "note": "5xx + timeouts",
            },
            {
                "label": "Peak RSS",
                "value": "412 MB",
                "delta": "+18 MB",
                "good": False,
                "spark": [392, 394, 395, 396, 406, 410, 412],
                "note": "pool warm-up",
            },
        ],
        panel=mint.trend(
            [1, 2, 3, 4, 5, 6, 7],
            {
                "Canary": [405, 398, 390, 308, 276, 258, 248],
                "Control": [402, 408, 399, 404, 401, 405, 400],
            },
            events={4: "PR #418"},
            reference=(300.0, "target"),
            highlight="Canary",
            title="Daily checkout p99 latency",
            label="p99 latency",
            unit="ms",
            x_label="Day",
        ),
        subtitle="checkout-service canary · 7-day window (n = 1.2M requests)",
        source="perf-canary 2026-11 · 5 clusters",
        style="pine",
    )
    ansi = card.to_terminal(width=72, color=True, style="pine")
    return (
        ansi,
        "mintfig card pr418_card.json --terminal --width 72 --style pine",
        "KPI Card · 2×4 Braille",
    )


def _import_mintchip() -> Any:
    try:
        import mintchip as mc
        return mc
    except ModuleNotFoundError:
        sibling = Path(__file__).resolve().parents[2] / "mintchip" / "src"
        if sibling.is_dir() and str(sibling) not in sys.path:
            sys.path.insert(0, str(sibling))
        import mintchip as mc
        return mc


def example_08_mintchip_braille_table() -> tuple[str, str, str]:
    mc = _import_mintchip()
    from mintchip.render.text_base import ansi_theme

    rows = [
        {
            "service": "checkout",
            "loss": [1.84, 1.48, 1.15, 0.88, 0.68, 0.54, 0.46, 0.42],
            "latency": [18, 19, 20, 20, 21, 22, 24, 26, 29, 31],
            "slo": [0.94, 0.90],
            "load": [12, 22, 46, 82, 95, 76, 38, 18],
            "checks": [148, 0, 2],
        },
        {
            "service": "search",
            "loss": [1.92, 1.65, 1.38, 1.16, 0.98, 0.84, 0.74, 0.68],
            "latency": [22, 24, 25, 27, 28, 31, 34, 38, 42, 46],
            "slo": [0.84, 0.90],
            "load": [18, 34, 58, 72, 68, 52, 30, 20],
            "checks": [142, 4, 4],
        },
        {
            "service": "payments",
            "loss": [1.45, 1.24, 1.05, 0.89, 0.76, 0.64, 0.56, 0.51],
            "latency": [16, 17, 18, 19, 19, 20, 22, 23, 25, 28],
            "slo": [0.97, 0.90],
            "load": [10, 16, 28, 44, 52, 40, 22, 14],
            "checks": [150, 0, 0],
        },
        {
            "service": "worker",
            "loss": [2.10, 1.88, 1.66, 1.48, 1.32, 1.18, 1.08, 0.98],
            "latency": [28, 30, 32, 35, 39, 44, 48, 53, 58, 64],
            "slo": [0.68, 0.90],
            "load": [24, 48, 76, 92, 88, 74, 60, 42],
            "checks": [132, 14, 4],
        },
    ]
    cols = {
        "service": {"chip": "text", "header": "Service"},
        "loss": {"chip": "spark", "header": "Loss"},
        "latency": {"chip": "hist", "header": "Latency (ms)", "bins": 8, "unit": "ms"},
        "slo": {"chip": "bullet", "header": "SLO", "ranges": (0.6, 0.85, 1.0)},
        "load": {"chip": "heat", "header": "Load (%)", "unit": "%"},
        "checks": {"chip": "status", "header": "CI checks"},
    }
    tbl = mc.table(
        rows,
        cols,
        title="Production services · shared-scale Braille micro-graphics (mint_dark)",
        highlight=["checkout"],
        baseline="worker",
    )
    with ansi_theme("mint_dark"):
        ansi = tbl.text(braille=True, color=True, width=124)
    return (
        ansi,
        "mintchip table services.json --braille --theme mint_dark --format ansi",
        "mintchip · 24-bit Braille",
    )


EXAMPLES: tuple[tuple[str, Any, int], ...] = (
    ("01_trend_ci_band", example_01_trend_ci_band, 20),
    ("02_wide_ecdf_and_swarm", example_02_wide_ecdf_and_swarm, 17),
    ("03_relate_pareto_fit", example_03_relate_pareto_fit, 20),
    ("04_change_slopegraph", example_04_change_slopegraph, 20),
    ("05_forest_ab_rollout", example_05_forest_ab_rollout, 19),
    ("06_matrix_confusion_truecolor", example_06_matrix_confusion_truecolor, 20),
    ("07_kpi_summary_card", example_07_kpi_summary_card, 20),
    ("08_mintchip_braille_table", example_08_mintchip_braille_table, 18),
)


def build_all(out_dir: Path = OUT_DIR, *, copy_to: Path | None = None) -> list[Path]:
    """Generate all 8 terminal gallery PNGs and raw ANSI ``.txt`` files."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if copy_to is not None:
        copy_to.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for slug, builder, font_size in EXAMPLES:
        ansi_text, cmd_title, badge = builder()
        txt_path = out_dir / f"{slug}.txt"
        png_path = out_dir / f"{slug}.png"
        txt_path.write_text(ansi_text + ("\n" if not ansi_text.endswith("\n") else ""), encoding="utf-8")
        render_ansi_to_png(
            ansi_text,
            png_path,
            title=cmd_title,
            badge=badge,
            font_size=font_size,
        )
        if copy_to is not None:
            shutil.copy2(png_path, copy_to / png_path.name)
        written.append(png_path)
        print(f"Rendered {png_path.relative_to(Path(__file__).resolve().parent.parent)}")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the 8-example Braille & true-color terminal gallery.")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--copy-to", type=Path, default=None)
    args = parser.parse_args(argv)
    build_all(args.out_dir, copy_to=args.copy_to)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
