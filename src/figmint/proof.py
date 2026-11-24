"""Visual preflight proof-sheet generator with CVD and grayscale verification."""

from __future__ import annotations

import io
import textwrap
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch, Rectangle
from PIL import Image

from .palettes import simulate_cvd
from .preflight import PreflightReport
from .specs import get_spec
from .style import resolved_font_name

# Clean editorial UI palette for the proof sheet
_BG_CANVAS = "#F4F6F9"
_BG_HEADER = "#0F172A"
_BG_CARD = "#FFFFFF"
_BORDER_CARD = "#DCE3EC"
_BORDER_FIG = "#CBD5E1"
_TEXT_DARK = "#0F172A"
_TEXT_MUTED = "#475569"
_TEXT_LIGHT = "#94A3B8"
_DIM_COLOR = "#334155"

_STATUS_STYLES = {
    "pass": {"bg": "#DCFCE7", "fg": "#15803D", "label": "PASS"},
    "warn": {"bg": "#FEF3C7", "fg": "#B45309", "label": "WARN"},
    "fail": {"bg": "#FEE2E2", "fg": "#B91C1C", "label": "FAIL"},
}

# Scorecard row typography (points) and vertical budget per row
_ROW_TITLE_PT = 8.3
_ROW_MSG_PT = 6.9
_ROW_MSG_LINESPACING = 1.18
_ROW_PAD_TOP_PT = 3.0
_ROW_TITLE_BAND_PT = 12.5
_ROW_BADGE_PT = 11.0
_ROW_GAP_PT = 1.5
_ROW_PAD_BOTTOM_PT = 3.5
# Conservative height of one rendered text line relative to its font size
# (ascent + descent); real sans-serif fonts are ~1.15-1.2.
_LINE_EXTENT = 1.3
_ROW_DIVIDER_COLOR = "#EEF2F6"


@dataclass(frozen=True)
class _ScorecardRow:
    """Vertical geometry (normalized canvas units) for one scorecard row."""

    top: float
    bottom: float
    title_y: float
    message_top: float
    badge_h: float
    scale: float
    lines: tuple[str, ...]


def _wrap_check_message(message: str) -> tuple[str, ...]:
    """Wrap a check message to at most two lines for the scorecard."""
    wrapped = textwrap.wrap(message, width=54) or [""]
    if len(wrapped) > 2:
        wrapped = [wrapped[0], wrapped[1][:51].rstrip() + "..."]
    return tuple(wrapped)


def _row_required_pt(n_lines: int) -> float:
    """Height in points a row needs at scale 1 for ``n_lines`` of message text."""
    msg_h = _ROW_MSG_PT * (_LINE_EXTENT + _ROW_MSG_LINESPACING * (n_lines - 1))
    return _ROW_PAD_TOP_PT + _ROW_TITLE_BAND_PT + _ROW_GAP_PT + msg_h + _ROW_PAD_BOTTOM_PT


def _layout_scorecard_rows(
    messages: list[tuple[str, ...]],
    *,
    list_top: float,
    list_bot: float,
    canvas_h_in: float,
) -> list[_ScorecardRow]:
    """Stack scorecard rows top-down so no message reaches its row divider.

    Each row gets the height its own message needs (one- and two-line messages
    differ). If the rows do not fit, all row typography is scaled down
    uniformly; any leftover space is shared equally between rows.
    """
    if not messages:
        return []
    pt = 1.0 / (canvas_h_in * 72.0)  # one point in normalized canvas units
    required = [_row_required_pt(len(m)) for m in messages]
    avail_pt = (list_top - list_bot) / pt
    scale = min(1.0, avail_pt / sum(required))
    extra_pt = max(0.0, avail_pt - scale * sum(required)) / len(messages)

    rows: list[_ScorecardRow] = []
    cursor = list_top
    for lines, req in zip(messages, required):
        height = (req * scale + extra_pt) * pt
        band_top = cursor - (_ROW_PAD_TOP_PT * scale + extra_pt / 2.0) * pt
        title_y = band_top - (_ROW_TITLE_BAND_PT * scale / 2.0) * pt
        message_top = band_top - ((_ROW_TITLE_BAND_PT + _ROW_GAP_PT) * scale) * pt
        rows.append(
            _ScorecardRow(
                top=cursor,
                bottom=cursor - height,
                title_y=title_y,
                message_top=message_top,
                badge_h=_ROW_BADGE_PT * scale * pt,
                scale=scale,
                lines=lines,
            )
        )
        cursor -= height
    return rows


def _rasterize_figure_rgb(fig: Figure, dpi: int) -> np.ndarray:
    """Render a Matplotlib figure to an HxWx3 uint8 RGB numpy array cleanly."""
    buf = io.BytesIO()
    fig.savefig(
        buf,
        format="png",
        dpi=dpi,
        facecolor="white",
        bbox_inches=None,
    )
    buf.seek(0)
    with Image.open(buf) as img:
        return np.asarray(img.convert("RGB"), dtype=np.uint8)


def _draw_card(
    ax: object,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    facecolor: str = _BG_CARD,
    edgecolor: str = _BORDER_CARD,
    radius: float = 0.008,
    lw: float = 0.9,
) -> None:
    """Draw a clean rounded white card on a normalized [0, 1] canvas axes."""
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        facecolor=facecolor,
        edgecolor=edgecolor,
        linewidth=lw,
        zorder=1,
    )
    ax.add_patch(patch)  # type: ignore[attr-defined]


def _fit_box(
    box_x: float,
    box_y: float,
    box_w: float,
    box_h: float,
    img_w: int,
    img_h: int,
    canvas_w_in: float,
    canvas_h_in: float,
) -> tuple[float, float, float, float]:
    """Center-fit an image inside a normalized box preserving true aspect ratio."""
    box_w_in = box_w * canvas_w_in
    box_h_in = box_h * canvas_h_in
    img_aspect = img_w / max(img_h, 1)
    box_aspect = box_w_in / max(box_h_in, 1e-6)

    if img_aspect >= box_aspect:
        draw_w_in = box_w_in
        draw_h_in = draw_w_in / img_aspect
    else:
        draw_h_in = box_h_in
        draw_w_in = draw_h_in * img_aspect

    draw_w = draw_w_in / canvas_w_in
    draw_h = draw_h_in / canvas_h_in
    draw_x = box_x + (box_w - draw_w) / 2.0
    draw_y = box_y + (box_h - draw_h) / 2.0
    return draw_x, draw_y, draw_w, draw_h


def render_proof_sheet(
    fig: Figure,
    report: PreflightReport,
    out_path: str | Path,
    *,
    dpi: int = 220,
) -> Path:
    """Render a publication-grade preflight proof sheet PNG with CVD & print checks."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    spec = get_spec(report.journal)
    font_name = resolved_font_name(spec)

    # Render source figure & compute CVD + grayscale simulations
    rgb = _rasterize_figure_rgb(fig, dpi=dpi)
    rgb_deut = simulate_cvd(rgb, "deuteranopia")
    rgb_prot = simulate_cvd(rgb, "protanopia")
    rgb_gray = simulate_cvd(rgb, "grayscale")
    img_h, img_w = rgb.shape[:2]

    # Proof sheet dimensions (wide editorial landscape layout)
    canvas_w_in = 14.0
    canvas_h_in = 9.4

    proof_fig = Figure(figsize=(canvas_w_in, canvas_h_in), dpi=dpi, facecolor=_BG_CANVAS)
    FigureCanvasAgg(proof_fig)

    # Full-bleed normalized [0, 1] layout layer
    ui_ax = proof_fig.add_axes((0.0, 0.0, 1.0, 1.0))
    ui_ax.set_xlim(0.0, 1.0)
    ui_ax.set_ylim(0.0, 1.0)
    ui_ax.set_axis_off()
    ui_ax.set_facecolor(_BG_CANVAS)

    # ── 1. HEADER BANNER ────────────────────────────────────────────────────
    header_h = 0.088
    header_y = 1.0 - header_h
    ui_ax.add_patch(
        Rectangle(
            (0.0, header_y),
            1.0,
            header_h,
            facecolor=_BG_HEADER,
            edgecolor="none",
            zorder=2,
        )
    )
    # Thin accent strip beneath banner
    accent_color = "#16A34A" if report.passed else "#DC2626"
    ui_ax.add_patch(
        Rectangle(
            (0.0, header_y - 0.0035),
            1.0,
            0.0035,
            facecolor=accent_color,
            edgecolor="none",
            zorder=3,
        )
    )

    ui_ax.text(
        0.025,
        header_y + header_h * 0.62,
        "FIGMINT PREFLIGHT PROOF",
        color="#FFFFFF",
        fontsize=14.5,
        fontweight="bold",
        fontfamily=font_name,
        va="center",
        ha="left",
        zorder=4,
    )

    n_pass = sum(1 for c in report.checks if c.status == "pass")
    n_warn = len(report.warnings)
    n_fail = len(report.failures)
    meta_parts = [
        spec.display_name,
        f"{report.width_mm:.1f} × {report.height_mm:.1f} mm",
        f"{n_pass}/{len(report.checks)} passed",
    ]
    if n_warn:
        meta_parts.append(f"{n_warn} warn")
    if n_fail:
        meta_parts.append(f"{n_fail} fail")

    ui_ax.text(
        0.025,
        header_y + header_h * 0.26,
        "  |  ".join(meta_parts),
        color="#CBD5E1",
        fontsize=9.2,
        fontfamily=font_name,
        va="center",
        ha="left",
        zorder=4,
    )

    # Status pill badge on top right
    pill_w = 0.088
    pill_h = 0.044
    pill_x = 1.0 - 0.025 - pill_w
    pill_y = header_y + (header_h - pill_h) / 2.0
    pill_bg = "#16A34A" if report.passed else "#DC2626"
    pill_text = "PASS" if report.passed else "FAIL"
    ui_ax.add_patch(
        FancyBboxPatch(
            (pill_x, pill_y),
            pill_w,
            pill_h,
            boxstyle="round,pad=0,rounding_size=0.010",
            facecolor=pill_bg,
            edgecolor="none",
            zorder=4,
        )
    )
    ui_ax.text(
        pill_x + pill_w / 2.0,
        pill_y + pill_h / 2.0,
        pill_text,
        color="#FFFFFF",
        fontsize=11.5,
        fontweight="bold",
        fontfamily=font_name,
        va="center",
        ha="center",
        zorder=5,
    )

    # ── 2. MIDDLE ROW: PRIMARY FIGURE + SCORECARD ───────────────────────────
    pad_x = 0.022
    gap_x = 0.018
    mid_top = header_y - 0.022
    mid_bot = 0.325
    mid_h = mid_top - mid_bot

    left_w = 0.605
    left_x = pad_x
    right_x = left_x + left_w + gap_x
    right_w = 1.0 - pad_x - right_x

    # Left card: Primary figure preview with mm dimension rules
    _draw_card(ui_ax, left_x, mid_bot, left_w, mid_h)
    ui_ax.text(
        left_x + 0.016,
        mid_top - 0.024,
        "FULL-COLOR PROOF",
        color=_TEXT_DARK,
        fontsize=9.2,
        fontweight="bold",
        fontfamily=font_name,
        va="center",
        ha="left",
        zorder=3,
    )
    ui_ax.text(
        left_x + left_w - 0.016,
        mid_top - 0.024,
        f"Exact physical aspect · {dpi} DPI raster check",
        color=_TEXT_MUTED,
        fontsize=7.8,
        fontfamily=font_name,
        va="center",
        ha="right",
        zorder=3,
    )

    # Reserve space inside left card for top & right millimeter callout rulers
    fig_box_x = left_x + 0.022
    fig_box_y = mid_bot + 0.020
    fig_box_w = left_w - 0.068
    fig_box_h = mid_h - 0.095
    fx, fy, fw, fh = _fit_box(
        fig_box_x, fig_box_y, fig_box_w, fig_box_h, img_w, img_h, canvas_w_in, canvas_h_in
    )

    # Render main figure inset axes
    main_ax = proof_fig.add_axes((fx, fy, fw, fh))
    main_ax.imshow(rgb, interpolation="antialiased")
    main_ax.set_xticks([])
    main_ax.set_yticks([])
    for spine in main_ax.spines.values():
        spine.set_edgecolor(_BORDER_FIG)
        spine.set_linewidth(0.8)

    # Top width millimeter callout rule
    rule_y = fy + fh + 0.015
    tick_h = 0.006
    ui_ax.plot(
        [fx, fx + fw], [rule_y, rule_y], color=_DIM_COLOR, lw=0.85, zorder=4
    )
    ui_ax.plot(
        [fx, fx], [rule_y - tick_h, rule_y + tick_h], color=_DIM_COLOR, lw=0.85, zorder=4
    )
    ui_ax.plot(
        [fx + fw, fx + fw],
        [rule_y - tick_h, rule_y + tick_h],
        color=_DIM_COLOR,
        lw=0.85,
        zorder=4,
    )
    ui_ax.text(
        fx + fw / 2.0,
        rule_y + 0.003,
        f" {report.width_mm:.1f} mm ",
        color=_DIM_COLOR,
        fontsize=8.2,
        fontweight="bold",
        fontfamily=font_name,
        va="bottom",
        ha="center",
        bbox={"facecolor": _BG_CARD, "edgecolor": "none", "pad": 1.0},
        zorder=5,
    )

    # Right height millimeter callout rule
    rule_x = fx + fw + 0.012
    tick_w = 0.0045
    ui_ax.plot(
        [rule_x, rule_x], [fy, fy + fh], color=_DIM_COLOR, lw=0.85, zorder=4
    )
    ui_ax.plot(
        [rule_x - tick_w, rule_x + tick_w], [fy, fy], color=_DIM_COLOR, lw=0.85, zorder=4
    )
    ui_ax.plot(
        [rule_x - tick_w, rule_x + tick_w],
        [fy + fh, fy + fh],
        color=_DIM_COLOR,
        lw=0.85,
        zorder=4,
    )
    ui_ax.text(
        rule_x + 0.006,
        fy + fh / 2.0,
        f"{report.height_mm:.1f} mm",
        color=_DIM_COLOR,
        fontsize=8.2,
        fontweight="bold",
        fontfamily=font_name,
        va="center",
        ha="left",
        rotation=90,
        zorder=5,
    )

    # Right card: Compliance Scorecard
    _draw_card(ui_ax, right_x, mid_bot, right_w, mid_h)
    ui_ax.text(
        right_x + 0.016,
        mid_top - 0.024,
        "COMPLIANCE SCORECARD",
        color=_TEXT_DARK,
        fontsize=9.2,
        fontweight="bold",
        fontfamily=font_name,
        va="center",
        ha="left",
        zorder=3,
    )
    ui_ax.plot(
        [right_x + 0.014, right_x + right_w - 0.014],
        [mid_top - 0.044, mid_top - 0.044],
        color=_BORDER_CARD,
        lw=0.75,
        zorder=3,
    )

    checks = report.checks
    list_top = mid_top - 0.056
    list_bot = mid_bot + 0.052
    rows = _layout_scorecard_rows(
        [_wrap_check_message(c.message) for c in checks],
        list_top=list_top,
        list_bot=list_bot,
        canvas_h_in=canvas_h_in,
    )

    badge_w = 0.044
    text_x = right_x + 0.016 + badge_w + 0.010

    for idx, (check, row) in enumerate(zip(checks, rows)):
        style = _STATUS_STYLES[check.status]

        # Pill badge
        ui_ax.add_patch(
            FancyBboxPatch(
                (right_x + 0.015, row.title_y - row.badge_h / 2.0),
                badge_w,
                row.badge_h,
                boxstyle="round,pad=0,rounding_size=0.004",
                facecolor=style["bg"],
                edgecolor="none",
                zorder=3,
            )
        )
        ui_ax.text(
            right_x + 0.015 + badge_w / 2.0,
            row.title_y,
            style["label"],
            color=style["fg"],
            fontsize=7.2 * row.scale,
            fontweight="bold",
            fontfamily=font_name,
            va="center",
            ha="center",
            zorder=4,
        )

        # Rule name
        rule_label = check.rule.replace("_", " ")
        ui_ax.text(
            text_x,
            row.title_y,
            rule_label,
            color=_TEXT_DARK,
            fontsize=_ROW_TITLE_PT * row.scale,
            fontweight="bold",
            fontfamily=font_name,
            va="center",
            ha="left",
            zorder=4,
        )

        # Concise wrapped detail (at most 2 lines), sized so it ends above the divider
        ui_ax.text(
            text_x,
            row.message_top,
            "\n".join(row.lines),
            color=_TEXT_MUTED,
            fontsize=_ROW_MSG_PT * row.scale,
            fontfamily=font_name,
            va="top",
            ha="left",
            linespacing=_ROW_MSG_LINESPACING,
            zorder=4,
        )

        # Subtle row divider at the bottom edge of the row's reserved band
        if idx < len(rows) - 1:
            ui_ax.plot(
                [right_x + 0.014, right_x + right_w - 0.014],
                [row.bottom, row.bottom],
                color=_ROW_DIVIDER_COLOR,
                lw=0.6,
                zorder=2,
            )

    # Scorecard footer spec line
    ui_ax.plot(
        [right_x + 0.014, right_x + right_w - 0.014],
        [mid_bot + 0.040, mid_bot + 0.040],
        color=_BORDER_CARD,
        lw=0.75,
        zorder=3,
    )
    spec_footer = (
        f"Spec: {spec.font_min_pt:.0f}–{spec.font_max_pt:.0f} pt sans-serif  ·  "
        f"min stroke {spec.min_linewidth_pt:.2f} pt  ·  "
        f"max H {spec.max_height_mm:.0f} mm"
    )
    ui_ax.text(
        right_x + right_w / 2.0,
        mid_bot + 0.020,
        spec_footer,
        color=_TEXT_MUTED,
        fontsize=7.3,
        fontfamily=font_name,
        va="center",
        ha="center",
        zorder=4,
    )

    # ── 3. BOTTOM 3-COLUMN ACCESSIBILITY & PRINT STRIP ─────────────────────
    bot_top = mid_bot - 0.020
    bot_y = 0.022
    bot_h = bot_top - bot_y
    col_gap = 0.016
    col_w = (1.0 - 2.0 * pad_x - 2.0 * col_gap) / 3.0

    cvd_panels = [
        ("DEUTERANOPIA", "Red-green CVD (~6% male)", rgb_deut),
        ("PROTANOPIA", "Red-blind CVD (~2% male)", rgb_prot),
        ("GRAYSCALE PRINT", "Rec. 709 luminance check", rgb_gray),
    ]

    for idx, (title, subtitle, sim_rgb) in enumerate(cvd_panels):
        cx = pad_x + idx * (col_w + col_gap)
        _draw_card(ui_ax, cx, bot_y, col_w, bot_h)

        ui_ax.text(
            cx + 0.014,
            bot_top - 0.021,
            title,
            color=_TEXT_DARK,
            fontsize=8.4,
            fontweight="bold",
            fontfamily=font_name,
            va="center",
            ha="left",
            zorder=3,
        )
        ui_ax.text(
            cx + col_w - 0.014,
            bot_top - 0.021,
            subtitle,
            color=_TEXT_LIGHT,
            fontsize=7.1,
            fontfamily=font_name,
            va="center",
            ha="right",
            zorder=3,
        )

        sx, sy, sw, sh = _fit_box(
            cx + 0.014,
            bot_y + 0.014,
            col_w - 0.028,
            bot_h - 0.052,
            img_w,
            img_h,
            canvas_w_in,
            canvas_h_in,
        )
        sub_ax = proof_fig.add_axes((sx, sy, sw, sh))
        sub_ax.imshow(sim_rgb, interpolation="antialiased")
        sub_ax.set_xticks([])
        sub_ax.set_yticks([])
        for spine in sub_ax.spines.values():
            spine.set_edgecolor(_BORDER_FIG)
            spine.set_linewidth(0.75)

    proof_fig.savefig(str(out), format="png", dpi=dpi, facecolor=_BG_CANVAS)
    return out
