"""General-purpose PR & release summary cards (``mint.card``).

Builds a publication-grade compact KPI strip (3–5 horizontal tiles with subtle
hairlines, bold values, color-coded deltas, and optional miniature inline
sparklines) above an optional :class:`~mintfig.Panel` (or as a standalone KPI
summary card when ``panel=None``).

Exports:
- :func:`card` — construct a :class:`SummaryCard`
- :class:`SummaryCard` — ``.save()``, ``.save_pair()``, ``.to_markdown()``, ``.to_html()``
- :func:`card_from_json` — build a :class:`SummaryCard` from a JSON spec mapping or file
- :func:`cli_card` — standalone CLI entry point for ``mintfig card``
"""

from __future__ import annotations

import argparse
import html
import io
import json
import math
import numbers
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import to_rgb
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch
from matplotlib.text import Text
from matplotlib.transforms import Bbox

from ._chip_bridge import import_mintchip
from ._explain.core import (
    _LINE,
    _VISUAL_DEFECT_RULES,
    DISPLAY_WIDTH_PX,
    MAX_TITLE_LINES,
    MIN_TEXT_PX,
    PT_TO_MM,
    ExplainError,
    Panel,
    _Ctx,
    _fit_axes,
    _glyph_issue,
    _GlyphCapture,
    _is_number,
    _issue,
    _Measure,
    _measure_text,
    _minus_signs,
    _missing_glyphs,
    _plain,
    _sig_text,
    _Sizes,
    _text_color,
)
from ._explain.layout import (
    _TICK_AXES,
    NARROW_DISPLAY_WIDTH_PX,
    SLIDE_DISPLAY_WIDTH_PX,
    _colour_registry,
    _embed_png_text,
    _fit_ticks,
    _latex_issues,
    _reader_path,
    panel_from_spec,
)
from .specs import JournalSpec, get_spec, mm_to_in
from .themes import (
    EXPLAIN_PALETTES,
    THEME_ALIASES,
    THEMES,
    ExplainPalette,
    Theme,
    apply_accent,
    apply_palette,
    contrast_ratio,
    get_theme,
    relative_luminance,
)

__all__ = [
    "DEFAULT_ACCENT_DARK",
    "DEFAULT_ACCENT_LIGHT",
    "EXAMPLE_CARD_SPEC",
    "SummaryCard",
    "card",
    "card_from_json",
    "cli_card",
]

#: Default crisp mint-emerald accent for light cards (zero yellow).
DEFAULT_ACCENT_LIGHT: str = "#0F8B6D"
#: Default luminous mint-emerald accent for dark cards (WCAG AA on #14181F, zero yellow).
DEFAULT_ACCENT_DARK: str = "#34D399"

_GOOD_LIGHT = "#0F8B6D"
_GOOD_DARK = "#34D399"
_BAD_LIGHT = "#C93B2B"
_BAD_DARK = "#F47E62"

_SPARK_BLOCKS = "▁▂▃▄▅▆▇█"
_SPARK_ASCII = " .:-=+*#"

#: Example JSON specification for ``mintfig card --example``.
EXAMPLE_CARD_SPEC: dict[str, Any] = {
    "takeaway": "PR #418 cuts checkout p99 latency 38% while holding 99.94% availability",
    "subtitle": "checkout-service canary · 7-day window (n = 1.2M requests)",
    "source": "perf-canary 2026-11 · 5 clusters",
    "metrics": [
        {
            "label": "p99 latency",
            "value": "248 ms",
            "delta": "-38%",
            "good": True,
            "spark": [410, 405, 398, 390, 310, 265, 248],
            "note": "vs 400 ms base",
        },
        {
            "label": "Availability",
            "value": "99.94%",
            "delta": "+0.02 pts",
            "good": True,
            "spark": [99.91, 99.92, 99.92, 99.93, 99.93, 99.94, 99.94],
        },
        {
            "label": "Error rate",
            "value": "0.06%",
            "delta": "-0.04 pts",
            "good": True,
            "spark": [0.11, 0.10, 0.10, 0.09, 0.08, 0.07, 0.06],
        },
        {
            "label": "Peak RSS",
            "value": "412 MB",
            "delta": "+18 MB",
            "good": False,
            "spark": [392, 394, 395, 394, 406, 410, 412],
            "note": "cache warm-up",
        },
    ],
    "panel": {
        "kind": "compare",
        "title": "p99 latency by endpoint",
        "label": "p99 latency",
        "unit": "ms",
        "values": {
            "checkout": 248,
            "payment": 195,
            "cart": 142,
            "catalog": 98,
            "health": 24,
        },
        "highlight": "checkout",
    },
}


# --------------------------------------------------------------------------- #
# Colour & formatting helpers
# --------------------------------------------------------------------------- #


def _blend_hex(color_a: str, color_b: str, weight_b: float) -> str:
    """Linearly blend two hex/CSS colors in sRGB space."""
    ra, ga, ba = to_rgb(color_a)
    rb, gb, bb = to_rgb(color_b)
    w = max(0.0, min(1.0, float(weight_b)))
    r = ra * (1.0 - w) + rb * w
    g = ga * (1.0 - w) + gb * w
    b = ba * (1.0 - w) + bb * w
    return f"#{round(r * 255):02X}{round(g * 255):02X}{round(b * 255):02X}"


def _card_tokens(theme: Theme, primary_accent: str) -> dict[str, Any]:
    """Derive WCAG-safe card chrome & semantic tokens from ``theme``."""
    is_dark = relative_luminance(theme.background) < 0.2
    if is_dark:
        tile_bg = _blend_hex(theme.background, "#FFFFFF", 0.055)
        tile_border = _blend_hex(theme.background, "#FFFFFF", 0.14)
        divider = _blend_hex(theme.background, "#FFFFFF", 0.12)
        good_stroke = _GOOD_DARK
        bad_stroke = _BAD_DARK
    else:
        tile_bg = _blend_hex(theme.background, theme.ink, 0.028)
        if theme.grid.lower() != theme.background.lower():
            tile_border = theme.grid
            divider = theme.grid
        else:
            tile_border = _blend_hex(theme.background, theme.ink, 0.14)
            divider = tile_border
        good_stroke = _GOOD_LIGHT
        bad_stroke = _BAD_LIGHT

    accent_stroke = primary_accent
    if contrast_ratio(accent_stroke, tile_bg) < 3.0:
        accent_stroke = _text_color(
            accent_stroke, minimum=3.2, background=tile_bg, ink=theme.ink
        )

    good_text = _text_color(good_stroke, minimum=4.5, background=tile_bg, ink=theme.ink)
    bad_text = _text_color(bad_stroke, minimum=4.5, background=tile_bg, ink=theme.ink)
    neutral_text = _text_color(theme.muted, minimum=4.5, background=tile_bg, ink=theme.ink)
    label_text = _text_color(theme.muted, minimum=4.5, background=tile_bg, ink=theme.ink)

    return {
        "is_dark": is_dark,
        "bg": theme.background,
        "ink": theme.ink,
        "muted": theme.muted,
        "tile_bg": tile_bg,
        "tile_border": tile_border,
        "divider": divider,
        "accent": accent_stroke,
        "good_stroke": good_stroke,
        "bad_stroke": bad_stroke,
        "good_text": good_text,
        "bad_text": bad_text,
        "neutral_text": neutral_text,
        "label_text": label_text,
    }


def _format_metric_value(raw: Any) -> str:
    """Format a KPI metric value cleanly, normalizing minus signs."""
    if isinstance(raw, str):
        text = " ".join(raw.split())
        if not text:
            raise ExplainError(
                "Metric 'value' must not be empty.",
                fix_hint='Pass a non-empty string or number, e.g. value="248 ms" or value=0.94.',
                rule="card_metric_invalid",
            )
        return _minus_signs(text)
    if isinstance(raw, (numbers.Integral, np.integer)) and not isinstance(raw, (bool, np.bool_)):
        iv = int(raw)
        return _minus_signs(f"{iv:,}")
    if _is_number(raw):
        fv = float(raw)
        if not math.isfinite(fv):
            raise ExplainError(
                f"Metric 'value' must be finite, got {raw!r}.",
                fix_hint="Replace NaN/Inf values or pass a string such as '—'.",
                rule="card_metric_invalid",
            )
        if abs(fv) >= 1000 and float(fv).is_integer():
            return _minus_signs(f"{fv:,.0f}")
        return _sig_text(fv)
    raise ExplainError(
        f"Metric 'value' must be a string or number, got {type(raw).__name__}.",
        fix_hint='Pass a string like "99.9%" or a number like 248.',
        rule="card_metric_invalid",
    )


def _format_metric_delta(raw: Any) -> str | None:
    """Format an optional KPI delta with explicit sign and Unicode minus."""
    if raw is None:
        return None
    if isinstance(raw, str):
        text = " ".join(raw.split())
        return _minus_signs(text) if text else None
    if _is_number(raw):
        fv = float(raw)
        if not math.isfinite(fv):
            raise ExplainError(
                f"Metric 'delta' must be finite, got {raw!r}.",
                fix_hint="Pass a finite number or string delta, e.g. delta='-38%' or delta=-12.5.",
                rule="card_metric_invalid",
            )
        if fv == 0:
            return "0"
        body = _sig_text(abs(fv))
        return f"+{body}" if fv > 0 else f"\N{MINUS SIGN}{body}"
    raise ExplainError(
        f"Metric 'delta' must be a string, number, or None; got {type(raw).__name__}.",
        fix_hint='Pass delta="-38%" or delta=-12.4.',
        rule="card_metric_invalid",
    )


def _normalize_spark(raw: Any, index: int) -> list[float] | None:
    """Validate and coerce an optional sparkline sequence to finite floats."""
    if raw is None:
        return None
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        if isinstance(raw, np.ndarray):
            raw = raw.tolist()
        else:
            raise ExplainError(
                f"Metric #{index + 1} 'spark' must be a sequence of numbers, got {type(raw).__name__}.",
                fix_hint="Pass a list of numbers, e.g. spark=[410, 390, 310, 248].",
                rule="card_metric_invalid",
            )
    vals: list[float] = []
    for item in raw:
        if not _is_number(item):
            raise ExplainError(
                f"Metric #{index + 1} 'spark' contains non-numeric entry {item!r}.",
                fix_hint="Every element of spark must be a finite number.",
                rule="card_metric_invalid",
            )
        fv = float(item)
        if math.isfinite(fv):
            vals.append(fv)
    return vals if vals else None


def _normalize_metrics(metrics: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Validate and normalize KPI metric mappings."""
    if isinstance(metrics, (str, bytes, Mapping)) or not isinstance(metrics, Sequence):
        raise ExplainError(
            f"card() 'metrics' must be a sequence of metric dicts, got {type(metrics).__name__}.",
            fix_hint='Pass a list of dicts, e.g. [{"label": "p99", "value": "248 ms", "delta": "-38%", "good": True}].',
            rule="card_metrics_invalid",
        )
    if not metrics:
        raise ExplainError(
            "card() needs at least one metric in 'metrics'.",
            fix_hint='Pass 1–5 metric dicts, e.g. [{"label": "Latency", "value": "248 ms"}].',
            rule="card_metrics_empty",
        )

    out: list[dict[str, Any]] = []
    for idx, item in enumerate(metrics):
        if not isinstance(item, Mapping):
            raise ExplainError(
                f"Metric #{idx + 1} must be a mapping, got {type(item).__name__}.",
                fix_hint='Each metric is a dict with keys: "label", "value", and optional "delta", "good", "spark", "note".',
                rule="card_metric_invalid",
            )
        raw_label = item.get("label")
        if not isinstance(raw_label, str) or not raw_label.strip():
            raise ExplainError(
                f"Metric #{idx + 1} needs a non-empty string 'label'.",
                fix_hint='Add "label": "p99 latency" to each metric dict.',
                rule="card_metric_invalid",
            )
        if "value" not in item or item["value"] is None:
            raise ExplainError(
                f"Metric #{idx + 1} ({raw_label!r}) needs a 'value'.",
                fix_hint='Add "value": "248 ms" (or a number) to the metric dict.',
                rule="card_metric_invalid",
            )
        good = item.get("good")
        if good is not None and not isinstance(good, bool):
            raise ExplainError(
                f"Metric #{idx + 1} ({raw_label!r}) 'good' must be True, False, or None; got {good!r}.",
                fix_hint="Pass good=True for improvement, good=False for regression, or omit/None for neutral.",
                rule="card_metric_invalid",
            )
        raw_note = item.get("note")
        note = " ".join(str(raw_note).split()) if raw_note is not None else None
        if note == "":
            note = None
        if note is not None:
            note = _minus_signs(note)

        out.append(
            {
                "label": _minus_signs(" ".join(raw_label.split())),
                "value": _format_metric_value(item["value"]),
                "raw_value": item["value"],
                "delta": _format_metric_delta(item.get("delta")),
                "good": good,
                "spark": _normalize_spark(item.get("spark"), idx),
                "note": note,
            }
        )
    return out


def _truncate_line(
    measure: _Measure,
    text: str,
    max_pt: float,
    size: float,
    weight: str = "normal",
    ellipsis: str = "\N{HORIZONTAL ELLIPSIS}",
) -> str:
    """Truncate a single line cleanly with an ellipsis when it exceeds ``max_pt``."""
    if measure.width_pt(text, size, weight) <= max_pt:
        return text
    chars = list(text.rstrip())
    while len(chars) > 1:
        chars.pop()
        cand = "".join(chars).rstrip() + ellipsis
        if measure.width_pt(cand, size, weight) <= max_pt:
            return cand
    return (text[:1] + ellipsis) if text else ""


def _wrap_capped(
    measure: _Measure,
    text: str,
    max_pt: float,
    size: float,
    weight: str = "normal",
    max_lines: int = 2,
    ellipsis: str = "\N{HORIZONTAL ELLIPSIS}",
) -> list[str]:
    """Wrap ``text`` to ``max_pt`` and cap at ``max_lines`` with a clean ellipsis."""
    lines = measure.wrap(text, max_pt, size, weight)
    if len(lines) <= max_lines:
        return [_truncate_line(measure, ln, max_pt, size, weight, ellipsis) for ln in lines]
    kept = lines[: max_lines - 1]
    rest = " ".join(lines[max_lines - 1 :])
    kept.append(_truncate_line(measure, rest, max_pt, size, weight, ellipsis))
    return kept


def _unicode_sparkline(values: Sequence[float], *, ascii_only: bool = False) -> str:
    """Render a compact Unicode (or ASCII) inline sparkline for Markdown fallback."""
    if not values:
        return ""
    if not ascii_only:
        import contextlib

        mc = import_mintchip()
        if mc is not None and callable(getattr(mc, "spark", None)):
            with contextlib.suppress(Exception):
                chip = mc.spark(list(values))
                raw = str(chip.text()).strip()
                # Extract just the spark glyph run so Markdown cells stay concise.
                glyphs = "".join(ch for ch in raw if ch in _SPARK_BLOCKS)
                if glyphs:
                    return glyphs

    charset = _SPARK_ASCII if ascii_only else _SPARK_BLOCKS
    lo = min(values)
    hi = max(values)
    span = hi - lo
    if span <= 0:
        mid = charset[len(charset) // 2]
        return mid * len(values)
    last_idx = len(charset) - 1
    return "".join(charset[round((v - lo) / span * last_idx)] for v in values)


def _svg_sparkline(
    values: Sequence[float],
    *,
    stroke_var: str,
    width: int = 120,
    height: int = 30,
) -> str:
    """Render a crisp zero-dependency inline SVG sparkline with area wash and end dot."""
    if not values:
        return ""
    pad_x = 4.0
    pad_top = 4.0
    pad_bot = 4.0
    usable_w = width - 2 * pad_x
    usable_h = height - pad_top - pad_bot
    lo = min(values)
    hi = max(values)
    span = hi - lo
    n = len(values)

    coords: list[tuple[float, float]] = []
    for i, v in enumerate(values):
        x = pad_x + (usable_w * 0.5 if n == 1 else usable_w * i / (n - 1))
        frac = 0.5 if span <= 0 else (v - lo) / span
        y = pad_top + usable_h * (1.0 - frac)
        coords.append((x, y))

    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    last_x, last_y = coords[-1]
    base_y = height - pad_bot + 1.5
    if n >= 2:
        first_x = coords[0][0]
        area_d = (
            f"M {first_x:.1f},{base_y:.1f} "
            + " ".join(f"L {x:.1f},{y:.1f}" for x, y in coords)
            + f" L {last_x:.1f},{base_y:.1f} Z"
        )
        area_el = f'<path d="{area_d}" fill="{stroke_var}" fill-opacity="0.14" stroke="none"/>'
        line_el = (
            f'<polyline points="{pts}" fill="none" stroke="{stroke_var}" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        )
    else:
        area_el = ""
        line_el = ""

    dot_el = (
        f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="3.2" '
        f'fill="{stroke_var}" stroke="var(--mf-card-tile)" stroke-width="1.2"/>'
    )
    return (
        f'<svg class="mf-spark" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="none" aria-hidden="true">'
        f"{area_el}{line_el}{dot_el}</svg>"
    )


def _escape_md_cell(value: Any) -> str:
    text = " ".join(str(value).split())
    return text.replace("|", "\\|")


def _partition_rows(items: list[dict[str, Any]], width_mm: float) -> list[list[dict[str, Any]]]:
    """Split KPI metrics into crisp balanced horizontal rows based on card width."""
    n = len(items)
    if width_mm >= 120.0:
        max_cols = 5
    elif width_mm >= 98.0:
        max_cols = 3
    else:
        max_cols = 2
    if n <= max_cols:
        return [items]
    n_rows = math.ceil(n / max_cols)
    cols = math.ceil(n / n_rows)
    return [items[i : i + cols] for i in range(0, n, cols)]


def _resolve_pair_paths(stem_or_dir: str | Path, name: str = "card") -> tuple[Path, Path]:
    """Resolve ``<stem>_light.png`` and ``<stem>_dark.png`` from a stem path or directory."""
    raw_str = str(stem_or_dir)
    target = Path(stem_or_dir)
    clean_name = name.strip()
    if clean_name.lower().endswith(".png"):
        clean_name = clean_name[:-4]
    clean_name = Path(clean_name).name or "card"

    is_dir = target.is_dir() or raw_str.endswith(("/", "\\"))
    if is_dir:
        target.mkdir(parents=True, exist_ok=True)
        return target / f"{clean_name}_light.png", target / f"{clean_name}_dark.png"

    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    stem = target.name
    if stem.lower().endswith(".png"):
        stem = stem[:-4]
    stem = stem.strip() or clean_name
    return parent / f"{stem}_light.png", parent / f"{stem}_dark.png"


def _format_ref(path: Path, repo_prefix: str | None) -> str:
    if repo_prefix is None:
        return _reader_path(path)
    prefix = repo_prefix.strip().rstrip("/")
    if not prefix:
        return path.name
    return f"{prefix}/{path.name}"


def _render_panel_svg(
    panel: Panel,
    *,
    theme: Theme,
    spec: JournalSpec,
    width_mm: float,
    takeaway: str,
) -> str:
    """Render just the attached panel to a clean inline SVG string for ``to_html()``."""
    with theme.rc_context(spec), _GlyphCapture():
        sizes = _Sizes.from_spec(spec, theme, "regular")
        s = sizes.scale
        measure = _Measure(theme)
        margin_x = 2.0 * s
        margin_y = 2.0 * s
        content_mm = width_mm - 2 * margin_x
        content_pt = content_mm / PT_TO_MM

        def _line_mm(size: float) -> float:
            return size * _LINE * PT_TO_MM

        head_lines = measure.wrap(panel.title, content_pt, sizes.body, "bold") if panel.title else []
        measure_text = _measure_text(panel.label, panel.unit)
        if panel.measure_note:
            measure_text = (
                f"{measure_text}; {panel.measure_note}" if measure_text else panel.measure_note
            )
        measure_lines = measure.wrap(measure_text, content_pt, sizes.small) if measure_text else []
        head_mm = len(head_lines) * _line_mm(sizes.body) + len(measure_lines) * _line_mm(sizes.small)
        if head_mm:
            head_mm += 2.0 * s

        plot_mm = panel._height_mm(content_mm / s, measure, sizes, theme) * s
        if panel.stretch:
            plot_mm = min(plot_mm, 52.0 * s)

        height_mm = margin_y + head_mm + plot_mm + margin_y
        fig = Figure(
            figsize=(mm_to_in(width_mm), mm_to_in(height_mm)),
            dpi=150,
            facecolor=theme.background,
        )
        FigureCanvasAgg(fig)
        px_per_mm = float(fig.dpi) / 25.4

        def _fx(mm: float) -> float:
            return mm / width_mm

        def _fy(mm_from_top: float) -> float:
            return 1.0 - mm_from_top / height_mm

        y_mm = margin_y
        for line in head_lines:
            fig.text(
                _fx(margin_x),
                _fy(y_mm),
                _plain(line, theme),
                ha="left",
                va="top",
                fontsize=sizes.body,
                fontweight="bold",
                color=theme.ink,
            )
            y_mm += _line_mm(sizes.body)
        for line in measure_lines:
            fig.text(
                _fx(margin_x),
                _fy(y_mm + 0.2 * s),
                _plain(line, theme),
                ha="left",
                va="top",
                fontsize=sizes.small,
                color=theme.muted,
            )
            y_mm += _line_mm(sizes.small)

        panel_colors, uniform_color, _ = _colour_registry([panel], theme, {})
        plot_top = margin_y + head_mm
        rect = Bbox.from_extents(
            margin_x * px_per_mm,
            (height_mm - plot_top - plot_mm) * px_per_mm,
            (margin_x + content_mm) * px_per_mm,
            (height_mm - plot_top) * px_per_mm,
        )
        ctx = _Ctx(
            fig=fig,
            sizes=sizes,
            key="a",
            cell_width_mm=content_mm / s,
            measure=measure,
            theme=theme,
            measure_label=measure_text or "(see measure_unnamed)",
            colors=panel_colors[0],
            uniform_color=uniform_color,
            takeaway=takeaway,
        )
        ax = ctx.tag(fig.add_axes([0.1, 0.1, 0.5, 0.5]))
        _fit_axes(fig, ax, rect)
        finish = panel._draw(ctx, ax)
        frames = panel._frames(ctx, ax, rect) if panel._frames else [(ax, rect)]
        for frame_ax, frame_rect in frames:
            _fit_axes(fig, frame_ax, frame_rect)
        if callable(finish):
            finish()
        for extra in ctx.finishers:
            extra()
        which = _TICK_AXES.get(panel.kind, "")
        if which:
            for frame_ax, _ in frames:
                _fit_ticks(fig, frame_ax, which)

        buf = io.StringIO()
        import matplotlib as mpl

        with mpl.rc_context({"svg.fonttype": "none", "svg.hashsalt": "mintfig-card"}):
            fig.savefig(buf, format="svg", facecolor=theme.background, edgecolor="none")
        svg = buf.getvalue()
        # Strip XML preamble/DOCTYPE so it embeds cleanly inside HTML5.
        start = svg.find("<svg")
        if start >= 0:
            svg = svg[start:]
        svg = re.sub(
            r"<svg\b",
            '<svg style="width:100%;height:auto;display:block"',
            svg,
            count=1,
        )
        return svg


# --------------------------------------------------------------------------- #
# SummaryCard object
# --------------------------------------------------------------------------- #


class SummaryCard:
    """A rendered PR / release KPI summary card (with optional attached Panel)."""

    def __init__(
        self,
        *,
        fig: Figure,
        spec: JournalSpec,
        theme: Theme,
        palette: str | None,
        accent: str | None,
        resolved_accent: str,
        takeaway: str,
        metrics: list[dict[str, Any]],
        panel: Panel | None,
        panel_axes: Axes | None,
        subtitle: str | None,
        source: str | None,
        width: str | float,
        issues: list[dict[str, Any]],
    ) -> None:
        self.fig = fig
        self.spec = spec
        self.theme = theme
        self.style = theme.name
        self.palette = palette
        self.accent = accent
        self.resolved_accent = resolved_accent
        self.takeaway = takeaway
        self.metrics = metrics
        self.panel = panel
        self.panel_axes = panel_axes
        self.subtitle = subtitle
        self.source = source
        self.width = width
        self.issues = issues
        self.saved_path: Path | None = None
        self.saved_px: tuple[int, int] | None = None

    @property
    def display_width_px(self) -> int:
        w = self.width.strip().lower() if isinstance(self.width, str) else ""
        if w == "slide":
            return SLIDE_DISPLAY_WIDTH_PX
        if w == "narrow":
            return NARROW_DISPLAY_WIDTH_PX
        return DISPLAY_WIDTH_PX

    @property
    def width_mm(self) -> float:
        return float(self.fig.get_figwidth()) * 25.4

    @property
    def height_mm(self) -> float:
        return float(self.fig.get_figheight()) * 25.4

    @property
    def ok(self) -> bool:
        return not any(issue.get("severity") == "error" for issue in self.issues)

    @property
    def ship(self) -> bool:
        return self.ok and not any(
            issue.get("rule") in _VISUAL_DEFECT_RULES
            or issue.get("rule") in {"text_too_small", "text_clipped"}
            for issue in self.issues
        )

    @property
    def min_text_px(self) -> float:
        """Smallest visible text height in CSS pixels at ``display_width_px``."""
        sizes = [
            float(t.get_fontsize())
            for t in self.fig.findobj(Text)
            if t.get_visible() and t.get_text().strip()
        ]
        px_per_pt = self.display_width_px / (float(self.fig.get_figwidth()) * 72.0)
        return round(min(sizes, default=0.0) * px_per_pt, 1)

    @property
    def alt_text(self) -> str:
        parts = [self.takeaway.rstrip(".") + "."]
        kpi_bits: list[str] = []
        for m in self.metrics:
            bit = f"{m['label']}: {m['value']}"
            if m.get("delta"):
                bit += f" ({m['delta']})"
            kpi_bits.append(bit)
        if kpi_bits:
            parts.append("KPIs: " + "; ".join(kpi_bits) + ".")
        if self.panel is not None:
            body = self.panel.describe
            if self.panel.title:
                body = f"{self.panel.title.rstrip('.')}. {body}"
            if self.panel.facts:
                body += f". {self.panel.facts[0]}"
            parts.append(body.rstrip(".") + ".")
        if self.source:
            parts.append(f"Source: {self.source.rstrip('.')}.")
        return " ".join(parts)

    def to_spec(self) -> dict[str, Any]:
        """Return a JSON-serializable spec dict accepted by :func:`card_from_json`."""
        metrics_spec: list[dict[str, Any]] = []
        for m in self.metrics:
            entry: dict[str, Any] = {
                "label": m["label"],
                "value": m["raw_value"],
            }
            if m.get("delta") is not None:
                entry["delta"] = m["delta"]
            if m.get("good") is not None:
                entry["good"] = m["good"]
            if m.get("spark") is not None:
                entry["spark"] = list(m["spark"])
            if m.get("note") is not None:
                entry["note"] = m["note"]
            metrics_spec.append(entry)

        out: dict[str, Any] = {
            "takeaway": self.takeaway,
            "metrics": metrics_spec,
        }
        if self.panel is not None:
            out["panel"] = self.panel.to_spec()
        if self.subtitle is not None:
            out["subtitle"] = self.subtitle
        if self.source is not None:
            out["source"] = self.source
        if self.theme.name != "mintfig":
            out["style"] = self.theme.name
        if self.palette is not None:
            out["palette"] = self.palette
        if self.accent is not None:
            out["accent"] = self.accent
        if self.width != "chat":
            out["width"] = self.width
        return out

    def summary(self) -> dict[str, Any]:
        """Return structured metadata, QA gate status, and delivery summary."""
        return {
            "ok": self.ok,
            "ship": self.ship,
            "path": str(self.saved_path) if self.saved_path is not None else None,
            "issues": list(self.issues),
            "metrics_count": len(self.metrics),
            "takeaway": self.takeaway,
            "style": self.theme.name,
            "palette": self.palette or "default",
            "accent": self.resolved_accent,
            "has_panel": self.panel is not None,
            "panel_facts": list(self.panel.facts) if self.panel is not None else [],
            "size_px": list(self.saved_px) if self.saved_px is not None else None,
            "size_mm": [round(self.width_mm, 1), round(self.height_mm, 1)],
            "display": {
                "width_px": self.display_width_px,
                "height_px": round(
                    self.display_width_px
                    * float(self.fig.get_figheight())
                    / float(self.fig.get_figwidth())
                ),
                "min_text_px": self.min_text_px,
            },
            "alt_text": self.alt_text,
        }

    def save(
        self,
        path: str | Path,
        *,
        scale: float = 2.0,
        embed: bool = True,
    ) -> dict[str, Any]:
        """Save the card as ``.png``, ``.svg``, ``.pdf``, or ``.html`` and return its summary."""
        from .export import save_figure

        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        suffix = out.suffix.lower()

        if suffix in {".html", ".htm"}:
            out.write_text(self.to_html(), encoding="utf-8")
            self.saved_path = out.resolve()
            self.saved_px = None
            return self.summary()

        dpi = round(self.display_width_px * float(scale) / float(self.fig.get_figwidth()))
        with self.theme.rc_context(self.spec), _GlyphCapture() as glyph_log:
            save_figure(self.fig, out, journal=self.spec, dpi=dpi)
        late = glyph_log.missing()
        if late and not any(i.get("rule") == "glyph_missing" for i in self.issues):
            self.issues.append(_glyph_issue(late))

        self.saved_path = out.resolve()
        if suffix == ".png":
            self.saved_px = (
                round(self.fig.get_figwidth() * dpi),
                round(self.fig.get_figheight() * dpi),
            )
            if embed:
                _embed_png_text(
                    out,
                    {
                        "mintfig:card_spec": json.dumps(self.to_spec(), ensure_ascii=False),
                        "mintfig:takeaway": self.takeaway,
                        "mintfig:alt_text": self.alt_text,
                    },
                )
        else:
            self.saved_px = None
        return self.summary()

    def save_pair(
        self,
        stem_or_dir: str | Path,
        *,
        name: str = "card",
        repo_prefix: str | None = None,
        light_style: str | None = None,
        dark_style: str = "dark",
        scale: float = 2.0,
    ) -> dict[str, Any]:
        """Save ``<stem>_light.png`` + ``<stem>_dark.png`` and return GitHub ``<picture>`` Markdown."""
        import matplotlib.pyplot as plt

        light_path, dark_path = _resolve_pair_paths(stem_or_dir, name=name)

        if light_style is not None:
            resolved_light = light_style
        elif relative_luminance(self.theme.background) < 0.2 or self.theme.name == dark_style:
            resolved_light = "mintfig"
        else:
            resolved_light = self.theme.name

        owned_figs: list[Figure] = []
        try:
            if resolved_light == self.theme.name:
                light_card = self
            else:
                light_card = self._rerender(style=resolved_light)
                owned_figs.append(light_card.fig)

            if dark_style == self.theme.name:
                dark_card = self
            else:
                dark_card = self._rerender(style=dark_style)
                owned_figs.append(dark_card.fig)

            light_summary = light_card.save(light_path, scale=scale)
            dark_summary = dark_card.save(dark_path, scale=scale)

            light_ref = _format_ref(light_path, repo_prefix)
            dark_ref = _format_ref(dark_path, repo_prefix)
            alt_escaped = html.escape(light_card.alt_text, quote=True)
            light_ref_escaped = html.escape(light_ref, quote=True)
            dark_ref_escaped = html.escape(dark_ref, quote=True)

            md_lines = [
                f"**{self.takeaway}**",
                "",
                "<picture>",
                f'  <source media="(prefers-color-scheme: dark)" srcset="{dark_ref_escaped}">',
                f'  <source media="(prefers-color-scheme: light)" srcset="{light_ref_escaped}">',
                f'  <img alt="{alt_escaped}" src="{light_ref_escaped}" width="{self.display_width_px}">',
                "</picture>",
                "",
                "<details>",
                "<summary>KPI metrics (mintfig)</summary>",
                "",
                self._metrics_table_markdown(),
                "</details>",
            ]
            markdown = "\n".join(md_lines)

            return {
                "ok": bool(light_summary["ok"] and dark_summary["ok"]),
                "ship": bool(light_summary["ship"] and dark_summary["ship"]),
                "light": str(light_path.resolve()),
                "dark": str(dark_path.resolve()),
                "light_path": str(light_path.resolve()),
                "dark_path": str(dark_path.resolve()),
                "light_ref": light_ref,
                "dark_ref": dark_ref,
                "light_style": resolved_light,
                "dark_style": dark_style,
                "markdown": markdown,
                "light_summary": light_summary,
                "dark_summary": dark_summary,
                "issues": {
                    "light": list(light_summary["issues"]),
                    "dark": list(dark_summary["issues"]),
                },
            }
        finally:
            for fig in owned_figs:
                plt.close(fig)

    def _rerender(self, *, style: str) -> SummaryCard:
        """Rebuild this card with a different theme style (used by :meth:`save_pair`)."""
        panel_arg: Panel | Mapping[str, Any] | None = (
            self.panel.to_spec() if self.panel is not None else None
        )
        metrics_arg = [
            {
                "label": m["label"],
                "value": m["raw_value"],
                "delta": m["delta"],
                "good": m["good"],
                "spark": list(m["spark"]) if m["spark"] is not None else None,
                "note": m["note"],
            }
            for m in self.metrics
        ]
        return card(
            self.takeaway,
            metrics_arg,
            panel=panel_arg,
            subtitle=self.subtitle,
            source=self.source,
            style=style,
            palette=self.palette,
            accent=self.accent,
            width=self.width,
        )

    def _metrics_table_markdown(self, *, ascii_only: bool = False) -> str:
        """Render the KPI metrics as an aligned GitHub-Flavored Markdown table."""
        has_delta = any(m.get("delta") for m in self.metrics)
        has_spark = any(m.get("spark") for m in self.metrics)
        has_note = any(m.get("note") for m in self.metrics)

        headers = ["Metric", "Value"]
        aligns = [False, True]
        if has_delta:
            headers.append("Delta")
            aligns.append(True)
        if has_spark:
            headers.append("Trend")
            aligns.append(False)
        if has_note:
            headers.append("Note")
            aligns.append(False)

        rows: list[list[str]] = []
        for m in self.metrics:
            row = [_escape_md_cell(m["label"]), f"**{_escape_md_cell(m['value'])}**"]
            if has_delta:
                delta = m.get("delta")
                if delta:
                    if m.get("good") is True:
                        marker = "+ " if ascii_only else "▲ "
                        row.append(f"{marker}{_escape_md_cell(delta)}")
                    elif m.get("good") is False:
                        marker = "! " if ascii_only else "▼ "
                        row.append(f"{marker}{_escape_md_cell(delta)}")
                    else:
                        row.append(_escape_md_cell(delta))
                else:
                    row.append("-" if ascii_only else "—")
            if has_spark:
                spark = m.get("spark")
                row.append(
                    f"`{_unicode_sparkline(spark, ascii_only=ascii_only)}`"
                    if spark
                    else ("-" if ascii_only else "—")
                )
            if has_note:
                row.append(_escape_md_cell(m["note"]) if m.get("note") else ("-" if ascii_only else "—"))
            rows.append(row)

        widths = [
            max(len(headers[i]), *(len(r[i]) for r in rows), 3) for i in range(len(headers))
        ]

        def _pad(text: str, w: int, right: bool) -> str:
            return text.rjust(w) if right else text.ljust(w)

        def _sep(w: int, right: bool) -> str:
            return ("-" * (w - 1) + ":") if right else (":" + "-" * (w - 1))

        lines = [
            "| " + " | ".join(_pad(headers[i], widths[i], aligns[i]) for i in range(len(headers))) + " |",
            "| " + " | ".join(_sep(widths[i], aligns[i]) for i in range(len(headers))) + " |",
        ]
        for r in rows:
            lines.append(
                "| " + " | ".join(_pad(r[i], widths[i], aligns[i]) for i in range(len(headers))) + " |"
            )
        return "\n".join(lines)

    def to_markdown(self, *, ascii_only: bool = False) -> str:
        """Render a crisp GitHub-Flavored Markdown fallback for this summary card."""
        lines: list[str] = [f"**{self.takeaway}**"]
        if self.subtitle:
            lines.extend(["", f"*{self.subtitle}*"])
        lines.extend(["", self._metrics_table_markdown(ascii_only=ascii_only)])
        if self.panel is not None and self.panel.facts:
            lines.append("")
            if self.panel.title:
                lines.append(f"**{self.panel.title}:**")
            for fact in self.panel.facts[:4]:
                lines.append(f"- {fact}")
        if self.source:
            lines.extend(["", f"*Source: {self.source}*"])
        return "\n".join(lines)

    def to_html(self) -> str:
        """Render a self-contained responsive light/dark HTML document for this card."""
        esc = html.escape
        is_explicit_dark = relative_luminance(self.theme.background) < 0.2
        light_theme = get_theme("mintfig") if is_explicit_dark else self.theme
        light_theme, _ = apply_palette(light_theme, self.palette)
        light_accent_arg = self.accent if self.accent is not None else DEFAULT_ACCENT_LIGHT
        light_theme, _ = apply_accent(light_theme, light_accent_arg)
        light_tokens = _card_tokens(light_theme, light_accent_arg)

        dark_theme = self.theme if is_explicit_dark else get_theme("dark")
        dark_theme, _ = apply_palette(dark_theme, self.palette)
        dark_accent_arg = self.accent if self.accent is not None else DEFAULT_ACCENT_DARK
        dark_theme, _ = apply_accent(dark_theme, dark_accent_arg)
        dark_tokens = _card_tokens(dark_theme, dark_theme.accent_colors[0])

        def _vars(tok: dict[str, Any]) -> str:
            return (
                f"--mf-card-bg:{tok['bg']};"
                f"--mf-card-ink:{tok['ink']};"
                f"--mf-card-muted:{tok['muted']};"
                f"--mf-card-tile:{tok['tile_bg']};"
                f"--mf-card-border:{tok['tile_border']};"
                f"--mf-card-divider:{tok['divider']};"
                f"--mf-card-accent:{tok['accent']};"
                f"--mf-card-good:{tok['good_text']};"
                f"--mf-card-good-stroke:{tok['good_stroke']};"
                f"--mf-card-bad:{tok['bad_text']};"
                f"--mf-card-bad-stroke:{tok['bad_stroke']};"
            )

        tiles_html: list[str] = []
        for m in self.metrics:
            good = m.get("good")
            if good is True:
                delta_cls = "mf-delta mf-good"
                spark_var = "var(--mf-card-good-stroke)"
            elif good is False:
                delta_cls = "mf-delta mf-bad"
                spark_var = "var(--mf-card-bad-stroke)"
            else:
                delta_cls = "mf-delta mf-neutral"
                spark_var = "var(--mf-card-accent)"

            delta_html = (
                f'<div class="{delta_cls}">{esc(m["delta"])}</div>' if m.get("delta") else ""
            )
            note_html = (
                f'<div class="mf-note">{esc(m["note"])}</div>' if m.get("note") else ""
            )
            spark_html = (
                f'<div class="mf-spark-wrap">{_svg_sparkline(m["spark"], stroke_var=spark_var)}</div>'
                if m.get("spark")
                else ""
            )
            tiles_html.append(
                '<div class="mf-tile">'
                f'<div class="mf-label">{esc(m["label"])}</div>'
                f'<div class="mf-value">{esc(m["value"])}</div>'
                f"{delta_html}{note_html}{spark_html}"
                "</div>"
            )

        panel_html = ""
        if self.panel is not None:
            panel_w = float(self.spec.resolve_width_mm(self.width))
            svg_light = _render_panel_svg(
                self.panel,
                theme=light_theme,
                spec=self.spec,
                width_mm=panel_w,
                takeaway=self.takeaway,
            )
            svg_dark = _render_panel_svg(
                self.panel,
                theme=dark_theme,
                spec=self.spec,
                width_mm=panel_w,
                takeaway=self.takeaway,
            )
            panel_html = (
                '<div class="mf-panel">'
                f'<div class="mf-panel-light">{svg_light}</div>'
                f'<div class="mf-panel-dark">{svg_dark}</div>'
                "</div>"
            )

        subtitle_html = (
            f'<p class="mf-subtitle">{esc(self.subtitle)}</p>' if self.subtitle else ""
        )
        source_html = (
            f'<footer class="mf-source">Source: {esc(self.source)}</footer>'
            if self.source
            else ""
        )

        root_attr = ' data-theme="dark"' if is_explicit_dark else ""
        max_w = self.display_width_px

        css = (
            "*{box-sizing:border-box}"
            f":root{{{_vars(light_tokens)}}}"
            f"@media (prefers-color-scheme:dark){{:root:not([data-theme='light']){{{_vars(dark_tokens)}}}"
            ".mf-panel-light{display:none}.mf-panel-dark{display:block}}"
            f":root[data-theme='dark']{{{_vars(dark_tokens)}}}"
            ":root[data-theme='dark'] .mf-panel-light{display:none}"
            ":root[data-theme='dark'] .mf-panel-dark{display:block}"
            ":root[data-theme='light'] .mf-panel-light{display:block}"
            ":root[data-theme='light'] .mf-panel-dark{display:none}"
            ".mf-panel-dark{display:none}"
            "html,body{margin:0;padding:0;background:var(--mf-card-bg);color:var(--mf-card-ink);"
            "font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue','Segoe UI',Helvetica,Arial,sans-serif;"
            "-webkit-font-smoothing:antialiased}"
            f".mf-card{{max-width:{max_w}px;margin:0 auto;padding:20px 22px 18px;"
            "background:var(--mf-card-bg);color:var(--mf-card-ink)}"
            ".mf-accent-bar{height:3px;width:100%;background:var(--mf-card-accent);"
            "border-radius:2px;margin-bottom:14px}"
            ".mf-takeaway{margin:0;font-size:1.18rem;line-height:1.28;font-weight:700;"
            "letter-spacing:-0.01em;color:var(--mf-card-ink)}"
            ".mf-subtitle{margin:5px 0 0;font-size:0.88rem;line-height:1.35;color:var(--mf-card-muted)}"
            ".mf-kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(128px,1fr));"
            "gap:10px;margin-top:16px}"
            ".mf-tile{background:var(--mf-card-tile);border:1px solid var(--mf-card-border);"
            "border-radius:8px;padding:11px 12px 10px;display:flex;flex-direction:column;gap:3px}"
            ".mf-label{font-size:0.78rem;font-weight:600;color:var(--mf-card-muted);line-height:1.25}"
            ".mf-value{font-size:1.45rem;font-weight:700;line-height:1.15;color:var(--mf-card-ink);"
            "font-variant-numeric:tabular-nums;margin-top:2px}"
            ".mf-delta{font-size:0.8rem;font-weight:600;line-height:1.25;font-variant-numeric:tabular-nums}"
            ".mf-good{color:var(--mf-card-good)}.mf-bad{color:var(--mf-card-bad)}"
            ".mf-neutral{color:var(--mf-card-muted)}"
            ".mf-note{font-size:0.74rem;color:var(--mf-card-muted);line-height:1.25}"
            ".mf-spark-wrap{margin-top:auto;padding-top:6px}"
            ".mf-spark{width:100%;height:30px;display:block}"
            ".mf-panel{margin-top:16px;padding-top:14px;border-top:1px solid var(--mf-card-divider)}"
            ".mf-source{margin-top:12px;font-size:0.76rem;color:var(--mf-card-muted)}"
        )

        return (
            f'<!DOCTYPE html><html lang="en"{root_attr}><head>'
            '<meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{esc(self.takeaway)}</title>"
            f"<style>{css}</style>"
            "</head><body>"
            f'<article class="mf-card" aria-label="{esc(self.takeaway)}">'
            '<div class="mf-accent-bar" aria-hidden="true"></div>'
            f'<h1 class="mf-takeaway">{esc(self.takeaway)}</h1>'
            f"{subtitle_html}"
            f'<section class="mf-kpi-grid" aria-label="Key metrics">{"".join(tiles_html)}</section>'
            f"{panel_html}"
            f"{source_html}"
            "</article></body></html>"
        )

    def _repr_html_(self) -> str:
        return self.to_html()

    def _repr_png_(self) -> bytes:
        buf = io.BytesIO()
        with self.theme.rc_context(self.spec), _GlyphCapture():
            self.fig.savefig(buf, format="png", dpi=160)
        return buf.getvalue()


# --------------------------------------------------------------------------- #
# Public builder: card()
# --------------------------------------------------------------------------- #


def card(
    takeaway: str,
    metrics: Sequence[Mapping[str, Any]],
    *,
    panel: Panel | Mapping[str, Any] | None = None,
    subtitle: str | None = None,
    source: str | None = None,
    style: str | Theme = "mintfig",
    palette: str | ExplainPalette | None = None,
    accent: str | None = None,
    width: str | float = "chat",
) -> SummaryCard:
    """Build a compact PR / release summary card with KPI tiles and an optional Panel.

    Parameters
    ----------
    takeaway:
        One-sentence headline conclusion shown at the top of the card.
    metrics:
        Sequence of KPI metric dicts. Each dict requires ``label`` (str) and
        ``value`` (str | float), and accepts optional ``delta`` (str | float),
        ``good`` (bool | None), ``spark`` (Sequence[float] | None), and
        ``note`` (str | None).
    panel:
        Optional :class:`~mintfig.Panel` (from ``mint.compare``, ``mint.trend``,
        etc.) or panel JSON spec mapping rendered seamlessly below the KPI strip.
    subtitle:
        Optional muted context line under the takeaway.
    source:
        Optional footer provenance line.
    style:
        Visual theme name or :class:`~mintfig.themes.Theme` (default ``"mintfig"``).
    palette:
        Optional explain color palette override (``"okabe_ito"``, ``"tol"``, etc.).
    accent:
        Optional primary accent hex color. Defaults to mint-emerald ``#0F8B6D``
        when ``accent=None`` and ``style="mintfig"`` (and luminous ``#34D399``
        on ``style="dark"``), with zero yellow.
    width:
        Target display width preset (``"narrow"``, ``"chat"``, ``"slide"``) or
        explicit width in millimeters.
    """
    if not isinstance(takeaway, str) or not takeaway.strip():
        raise ExplainError(
            "card() needs a non-empty takeaway headline string.",
            fix_hint='Pass a one-sentence conclusion, e.g. card("PR #418 cuts p99 latency 38%", [...]).',
            rule="takeaway_missing",
        )
    takeaway_clean = " ".join(takeaway.split())
    norm_metrics = _normalize_metrics(metrics)

    resolved_panel: Panel | None = None
    if panel is not None:
        if isinstance(panel, Panel):
            resolved_panel = panel
        elif isinstance(panel, Mapping):
            resolved_panel = panel_from_spec(panel)
        else:
            raise ExplainError(
                f"card(panel=...) must be a mintfig Panel, a panel spec dict, or None; got {type(panel).__name__}.",
                fix_hint="Pass panel=mint.compare({...}) or panel=mint.trend(...).",
                rule="card_panel_invalid",
            )

    try:
        theme = get_theme(style)
    except (TypeError, ValueError) as exc:
        aliases = ", ".join(sorted(THEME_ALIASES))
        raise ExplainError(
            str(exc),
            fix_hint=f"Use one of: {', '.join(THEMES)} (aliases: {aliases}).",
            rule="unknown_style",
        ) from exc

    try:
        theme, palette_name = apply_palette(theme, palette)
    except (TypeError, ValueError) as exc:
        raise ExplainError(
            str(exc),
            fix_hint=f"Use one of: {', '.join(EXPLAIN_PALETTES)}.",
            rule="unknown_palette",
        ) from exc

    effective_accent: str | None = accent
    if effective_accent is None:
        if theme.name == "mintfig":
            effective_accent = DEFAULT_ACCENT_LIGHT
        elif theme.name == "dark":
            effective_accent = DEFAULT_ACCENT_DARK

    try:
        theme, accent_hex = apply_accent(theme, effective_accent)
    except ValueError as exc:
        raise ExplainError(
            str(exc),
            fix_hint="Pass a valid hex/CSS color string such as accent='#0F8B6D'.",
            rule="invalid_accent",
        ) from exc

    resolved_accent = (
        theme.accent_colors[0]
        if theme.accent_colors
        else (accent_hex or DEFAULT_ACCENT_LIGHT)
    )
    tokens = _card_tokens(theme, resolved_accent)

    spec = get_spec("screen")
    width_mm = float(spec.resolve_width_mm(width))
    w_key = width.strip().lower() if isinstance(width, str) else ""
    disp_px = (
        SLIDE_DISPLAY_WIDTH_PX
        if w_key == "slide"
        else (NARROW_DISPLAY_WIDTH_PX if w_key == "narrow" else DISPLAY_WIDTH_PX)
    )

    issues: list[dict[str, Any]] = []
    panel_map = {"a": resolved_panel} if resolved_panel is not None else {}
    issues.extend(_latex_issues((takeaway_clean, subtitle, source), panel_map))

    with theme.rc_context(spec), _GlyphCapture() as glyph_log:
        sizes = _Sizes.from_spec(spec, theme, "regular")
        if w_key == "narrow":
            sizes = _Sizes(
                scale=sizes.scale,
                title=min(sizes.title, max(sizes.body + 1.5, round(sizes.title * 0.92, 1))),
                body=sizes.body,
                small=sizes.small,
                foot=max(sizes.foot, 7.0),
                density="regular",
            )
        s = sizes.scale
        measure = _Measure(theme)

        margin_x = 4.5 * s
        margin_y = 4.2 * s
        content_mm = width_mm - 2 * margin_x
        content_pt = content_mm / PT_TO_MM

        def _line_mm(size: float) -> float:
            return size * _LINE * PT_TO_MM

        # Header layout
        title_pt = sizes.title
        title_lines = measure.wrap(
            takeaway_clean,
            content_pt,
            title_pt,
            theme.title_weight,
            family=theme.title_family,
        )
        if len(title_lines) > MAX_TITLE_LINES:
            min_title_pt = max(
                sizes.body + 0.5,
                MIN_TEXT_PX * (width_mm / 25.4 * 72.0) / disp_px,
            )
            for step in (0.5, 1.0, 1.5):
                cand = round(title_pt - step, 2)
                if cand < min_title_pt:
                    continue
                cand_lines = measure.wrap(
                    takeaway_clean,
                    content_pt,
                    cand,
                    theme.title_weight,
                    family=theme.title_family,
                )
                if len(cand_lines) <= MAX_TITLE_LINES:
                    title_pt = cand
                    title_lines = cand_lines
                    break

        subtitle_lines = (
            measure.wrap(subtitle.strip(), content_pt, sizes.body)
            if isinstance(subtitle, str) and subtitle.strip()
            else []
        )
        source_line_text = (
            f"Source: {source.strip()}"
            if isinstance(source, str) and source.strip()
            else None
        )
        footer_lines = (
            measure.wrap(source_line_text, content_pt, max(7.0, sizes.foot))
            if source_line_text
            else []
        )

        accent_bar_mm = 0.85 * s
        accent_gap_mm = 2.4 * s
        header_mm = (
            accent_bar_mm
            + accent_gap_mm
            + len(title_lines) * _line_mm(title_pt)
            + (0.5 * s + len(subtitle_lines) * _line_mm(sizes.body) if subtitle_lines else 0.0)
        )
        header_to_kpi_gap = 3.8 * s

        # KPI tile rows layout
        metric_rows = _partition_rows(norm_metrics, width_mm)
        kpi_row_gap = 2.8 * s
        row_layouts: list[dict[str, Any]] = []

        label_pt = max(7.2, sizes.small)
        delta_base_pt = max(7.2, sizes.small)
        note_pt = max(7.0, sizes.foot)
        foot_pt = max(7.0, sizes.foot)

        for row_metrics in metric_rows:
            k = len(row_metrics)
            tile_gap = (2.8 if k <= 3 else (2.4 if k == 4 else 2.0)) * s
            tile_w = (content_mm - tile_gap * (k - 1)) / k
            pad_x = (2.6 if tile_w >= 26.0 else 1.8) * s
            pad_top = 2.3 * s
            pad_bot = 2.2 * s
            inner_mm = max(8.0, tile_w - 2 * pad_x)
            inner_pt = inner_mm / PT_TO_MM
            row_has_spark = any(m["spark"] is not None for m in row_metrics)
            spark_h_mm = 7.6 * s if row_has_spark else 0.0
            spark_gap_mm = 1.8 * s if row_has_spark else 0.0

            base_val_pt = (14.5 if tile_w >= 34.0 else (13.5 if tile_w >= 26.0 else 12.0)) * s
            tile_specs: list[dict[str, Any]] = []
            max_text_h = 0.0
            for idx_in_row, m in enumerate(row_metrics):
                lbl_lines = _wrap_capped(
                    measure,
                    m["label"],
                    inner_pt,
                    label_pt,
                    "normal",
                    max_lines=2,
                    ellipsis=theme.ellipsis,
                )
                val_pt = base_val_pt
                while val_pt > 8.5 * s and measure.width_pt(m["value"], val_pt, "bold") > inner_pt:
                    val_pt = round(val_pt - 0.5, 2)
                val_text = _truncate_line(
                    measure, m["value"], inner_pt, val_pt, "bold", theme.ellipsis
                )

                delta_lines: list[str] = []
                delta_pt = delta_base_pt
                if m["delta"]:
                    if (
                        measure.width_pt(m["delta"], delta_pt, "bold") > inner_pt
                        and measure.width_pt(m["delta"], 7.0, "bold") <= inner_pt
                    ):
                        delta_pt = 7.0
                    delta_lines = _wrap_capped(
                        measure,
                        m["delta"],
                        inner_pt,
                        delta_pt,
                        "bold",
                        max_lines=2,
                        ellipsis=theme.ellipsis,
                    )

                note_lines: list[str] = []
                if m["note"]:
                    note_lines = _wrap_capped(
                        measure,
                        m["note"],
                        inner_pt,
                        note_pt,
                        "normal",
                        max_lines=2,
                        ellipsis=theme.ellipsis,
                    )

                lbl_h = len(lbl_lines) * (label_pt * 1.22 * PT_TO_MM)
                val_h = val_pt * 1.15 * PT_TO_MM
                delta_h = len(delta_lines) * (delta_pt * 1.22 * PT_TO_MM) if delta_lines else 0.0
                note_h = len(note_lines) * (note_pt * 1.22 * PT_TO_MM) if note_lines else 0.0

                text_h = lbl_h + 1.2 * s + val_h
                if delta_lines:
                    text_h += 1.0 * s + delta_h
                if note_lines:
                    text_h += (0.7 if delta_lines else 1.0) * s + note_h

                max_text_h = max(max_text_h, text_h)
                tile_specs.append(
                    {
                        "metric": m,
                        "x": margin_x + idx_in_row * (tile_w + tile_gap),
                        "w": tile_w,
                        "pad_x": pad_x,
                        "lbl_lines": lbl_lines,
                        "lbl_h": lbl_h,
                        "val_text": val_text,
                        "val_pt": val_pt,
                        "val_h": val_h,
                        "delta_lines": delta_lines,
                        "delta_pt": delta_pt,
                        "delta_h": delta_h,
                        "note_lines": note_lines,
                    }
                )

            row_h = pad_top + max_text_h + (spark_gap_mm + spark_h_mm if row_has_spark else 0.0) + pad_bot
            row_layouts.append(
                {
                    "tiles": tile_specs,
                    "h": row_h,
                    "pad_top": pad_top,
                    "pad_bot": pad_bot,
                    "has_spark": row_has_spark,
                    "spark_h": spark_h_mm,
                }
            )

        kpi_total_mm = sum(r["h"] for r in row_layouts) + kpi_row_gap * (len(row_layouts) - 1)

        # Optional attached panel layout
        panel_divider_gap_top = 4.0 * s
        panel_divider_gap_bot = 3.6 * s
        panel_head_lines: list[str] = []
        panel_measure_lines: list[str] = []
        panel_head_mm = 0.0
        panel_plot_mm = 0.0
        panel_total_mm = 0.0
        panel_colors: list[dict[str, str]] = [{}]
        uniform_color = theme.default_color
        panel_measure_text: str | None = None

        if resolved_panel is not None:
            panel_colors, uniform_color, colour_issues = _colour_registry([resolved_panel], theme, {})
            issues.extend(colour_issues)
            panel_head_lines = (
                measure.wrap(resolved_panel.title, content_pt, sizes.body, "bold")
                if resolved_panel.title
                else []
            )
            inline_unit = (
                theme.inline_y_ticks
                and resolved_panel.kind == "trend"
                and not resolved_panel.spec.get("facet")
                and not resolved_panel.spec.get("log")
                and bool(resolved_panel.unit)
            )
            panel_measure_text = (
                resolved_panel.label
                if inline_unit
                else _measure_text(resolved_panel.label, resolved_panel.unit)
            )
            if resolved_panel.measure_note:
                panel_measure_text = (
                    f"{panel_measure_text}; {resolved_panel.measure_note}"
                    if panel_measure_text
                    else resolved_panel.measure_note
                )
            panel_measure_lines = (
                measure.wrap(panel_measure_text, content_pt, sizes.small)
                if panel_measure_text
                else []
            )
            panel_head_mm = (
                len(panel_head_lines) * _line_mm(sizes.body)
                + len(panel_measure_lines) * _line_mm(sizes.small)
            )
            if panel_head_mm:
                panel_head_mm += 2.2 * s
            panel_plot_mm = resolved_panel._height_mm(content_mm / s, measure, sizes, theme) * s
            if resolved_panel.stretch:
                panel_plot_mm = min(panel_plot_mm, 50.0 * s)
            panel_total_mm = (
                panel_divider_gap_top + panel_divider_gap_bot + panel_head_mm + panel_plot_mm
            )

        footer_gap = 3.2 * s if footer_lines else 0.0
        footer_mm = len(footer_lines) * _line_mm(foot_pt)

        height_mm = (
            margin_y
            + header_mm
            + header_to_kpi_gap
            + kpi_total_mm
            + panel_total_mm
            + footer_gap
            + footer_mm
            + margin_y
        )

        # Build Figure
        fig = Figure(
            figsize=(mm_to_in(width_mm), mm_to_in(height_mm)),
            dpi=150,
            facecolor=theme.background,
        )
        FigureCanvasAgg(fig)
        fig._mintfig_journal = spec.name  # type: ignore[attr-defined]
        px_per_mm = float(fig.dpi) / 25.4

        def _fx(mm: float) -> float:
            return mm / width_mm

        def _fy(mm_from_top: float) -> float:
            return 1.0 - mm_from_top / height_mm

        # 1. Top mint-emerald accent stripe (isotropic inch patch for crisp caps)
        cursor = margin_y
        fig.add_artist(
            FancyBboxPatch(
                (mm_to_in(margin_x), mm_to_in(height_mm - cursor - accent_bar_mm)),
                mm_to_in(content_mm),
                mm_to_in(accent_bar_mm),
                boxstyle=f"round,pad=0,rounding_size={mm_to_in(0.4 * s)}",
                facecolor=tokens["accent"],
                edgecolor="none",
                transform=fig.dpi_scale_trans,
                zorder=2,
            )
        )
        cursor += accent_bar_mm + accent_gap_mm

        # 2. Takeaway headline & optional subtitle
        title_kw: dict[str, Any] = {
            "ha": "left",
            "va": "top",
            "fontsize": title_pt,
            "fontweight": theme.title_weight,
            "color": tokens["ink"],
        }
        if theme.title_family is not None:
            title_kw["fontfamily"] = list(theme.title_family)
        for line in title_lines:
            t_art = fig.text(_fx(margin_x), _fy(cursor), _plain(line, theme), **title_kw)
            if theme.allow_serif_title:
                t_art._mintfig_allow_serif = True  # type: ignore[attr-defined]
            cursor += _line_mm(title_pt)

        if subtitle_lines:
            cursor += 0.5 * s
            for line in subtitle_lines:
                fig.text(
                    _fx(margin_x),
                    _fy(cursor),
                    _plain(line, theme),
                    ha="left",
                    va="top",
                    fontsize=sizes.body,
                    color=tokens["muted"],
                )
                cursor += _line_mm(sizes.body)

        cursor += header_to_kpi_gap

        # 3. KPI tile strip
        rounding_in = mm_to_in(1.6 * s)
        for r_idx, row_plan in enumerate(row_layouts):
            row_top = cursor
            row_h = row_plan["h"]
            row_bottom = row_top + row_h
            for tile in row_plan["tiles"]:
                m = tile["metric"]
                tx = tile["x"]
                tw = tile["w"]
                px_pad = tile["pad_x"]

                # Tile surface + crisp hairline border (isotropic inch coordinates)
                fig.add_artist(
                    FancyBboxPatch(
                        (mm_to_in(tx), mm_to_in(height_mm - row_bottom)),
                        mm_to_in(tw),
                        mm_to_in(row_h),
                        boxstyle=f"round,pad=0,rounding_size={rounding_in}",
                        facecolor=tokens["tile_bg"],
                        edgecolor=tokens["tile_border"],
                        linewidth=0.65 * s,
                        transform=fig.dpi_scale_trans,
                        zorder=1,
                    )
                )

                # Text inside tile
                ty = row_top + row_plan["pad_top"]
                for ln in tile["lbl_lines"]:
                    fig.text(
                        _fx(tx + px_pad),
                        _fy(ty),
                        _plain(ln, theme),
                        ha="left",
                        va="top",
                        fontsize=label_pt,
                        fontweight="normal",
                        color=tokens["label_text"],
                        zorder=3,
                    )
                    ty += label_pt * 1.22 * PT_TO_MM

                ty += 1.2 * s
                fig.text(
                    _fx(tx + px_pad),
                    _fy(ty),
                    _plain(tile["val_text"], theme),
                    ha="left",
                    va="top",
                    fontsize=tile["val_pt"],
                    fontweight="bold",
                    color=tokens["ink"],
                    zorder=3,
                )
                ty += tile["val_h"]

                if tile["delta_lines"]:
                    ty += 1.0 * s
                    if m["good"] is True:
                        d_color = tokens["good_text"]
                    elif m["good"] is False:
                        d_color = tokens["bad_text"]
                    else:
                        d_color = tokens["neutral_text"]
                    for ln in tile["delta_lines"]:
                        fig.text(
                            _fx(tx + px_pad),
                            _fy(ty),
                            _plain(ln, theme),
                            ha="left",
                            va="top",
                            fontsize=tile["delta_pt"],
                            fontweight="bold",
                            color=d_color,
                            zorder=3,
                        )
                        ty += tile["delta_pt"] * 1.22 * PT_TO_MM

                if tile["note_lines"]:
                    ty += (0.7 if tile["delta_lines"] else 1.0) * s
                    for ln in tile["note_lines"]:
                        fig.text(
                            _fx(tx + px_pad),
                            _fy(ty),
                            _plain(ln, theme),
                            ha="left",
                            va="top",
                            fontsize=note_pt,
                            color=tokens["neutral_text"],
                            zorder=3,
                        )
                        ty += note_pt * 1.22 * PT_TO_MM

                # Miniature inline sparkline (strictly below text region)
                spark_vals = m.get("spark")
                if spark_vals:
                    spark_h = row_plan["spark_h"]
                    spark_bottom_mm = row_bottom - row_plan["pad_bot"]
                    sp_x0 = _fx(tx + px_pad)
                    sp_w = (tw - 2 * px_pad) / width_mm
                    sp_y0 = 1.0 - spark_bottom_mm / height_mm
                    sp_h = spark_h / height_mm
                    ax_sp = fig.add_axes([sp_x0, sp_y0, sp_w, sp_h])
                    ax_sp.set_facecolor("none")
                    ax_sp.set_axis_off()
                    ax_sp.set_zorder(3)

                    if m["good"] is True:
                        sp_col = tokens["good_stroke"]
                    elif m["good"] is False:
                        sp_col = tokens["bad_stroke"]
                    else:
                        sp_col = tokens["accent"]

                    ys = np.asarray(spark_vals, dtype=float)
                    xs = np.arange(len(ys), dtype=float)
                    y_min = float(np.min(ys))
                    y_max = float(np.max(ys))
                    span = y_max - y_min
                    pad_y = 0.18 * span if span > 0 else max(abs(y_min) * 0.1, 1.0)
                    lo_lim = y_min - pad_y
                    hi_lim = y_max + pad_y

                    if len(ys) >= 2:
                        ax_sp.fill_between(
                            xs,
                            lo_lim,
                            ys,
                            color=sp_col,
                            alpha=0.18 if tokens["is_dark"] else 0.13,
                            linewidth=0.0,
                            zorder=1,
                        )
                        ax_sp.plot(
                            xs,
                            ys,
                            color=sp_col,
                            linewidth=1.35 * s,
                            solid_capstyle="round",
                            solid_joinstyle="round",
                            zorder=2,
                        )
                        x_pad = max(0.25, (len(ys) - 1) * 0.04)
                        ax_sp.set_xlim(-0.08 * (len(ys) - 1), (len(ys) - 1) + x_pad)
                    else:
                        ax_sp.set_xlim(-1.0, 1.0)

                    # Crisp terminal dot highlighting the current value
                    ax_sp.plot(
                        [xs[-1]],
                        [ys[-1]],
                        marker="o",
                        markersize=3.4 * s,
                        markerfacecolor=sp_col,
                        markeredgecolor=tokens["tile_bg"],
                        markeredgewidth=0.65 * s,
                        linestyle="none",
                        zorder=3,
                    )
                    ax_sp.set_ylim(lo_lim, hi_lim)

            cursor = row_bottom + (kpi_row_gap if r_idx < len(row_layouts) - 1 else 0.0)

        # 4. Optional attached mintfig Panel
        panel_axes: Axes | None = None
        if resolved_panel is not None:
            div_y = _fy(cursor + panel_divider_gap_top * 0.55)
            fig.add_artist(
                Line2D(
                    [_fx(margin_x), _fx(width_mm - margin_x)],
                    [div_y, div_y],
                    transform=fig.transFigure,
                    color=tokens["divider"],
                    linewidth=0.65 * s,
                    solid_capstyle="butt",
                    zorder=2,
                )
            )
            cursor += panel_divider_gap_top + panel_divider_gap_bot

            y_mm = cursor
            for line in panel_head_lines:
                fig.text(
                    _fx(margin_x),
                    _fy(y_mm),
                    _plain(line, theme),
                    ha="left",
                    va="top",
                    fontsize=sizes.body,
                    fontweight="bold",
                    color=tokens["ink"],
                )
                y_mm += _line_mm(sizes.body)
            for line in panel_measure_lines:
                fig.text(
                    _fx(margin_x),
                    _fy(y_mm + 0.2 * s),
                    _plain(line, theme),
                    ha="left",
                    va="top",
                    fontsize=sizes.small,
                    color=tokens["muted"],
                )
                y_mm += _line_mm(sizes.small)

            plot_top = cursor + panel_head_mm
            rect = Bbox.from_extents(
                margin_x * px_per_mm,
                (height_mm - plot_top - panel_plot_mm) * px_per_mm,
                (margin_x + content_mm) * px_per_mm,
                (height_mm - plot_top) * px_per_mm,
            )
            ctx = _Ctx(
                fig=fig,
                sizes=sizes,
                key="a",
                cell_width_mm=content_mm / s,
                measure=measure,
                theme=theme,
                measure_label=panel_measure_text or "(see measure_unnamed)",
                colors=panel_colors[0],
                uniform_color=uniform_color,
                takeaway=takeaway_clean,
            )
            ax = ctx.tag(fig.add_axes([0.1, 0.1, 0.5, 0.5]))
            _fit_axes(fig, ax, rect)
            finish = resolved_panel._draw(ctx, ax)
            frames = resolved_panel._frames(ctx, ax, rect) if resolved_panel._frames else [(ax, rect)]
            for frame_ax, frame_rect in frames:
                _fit_axes(fig, frame_ax, frame_rect)
            if callable(finish):
                finish()
            for extra in ctx.finishers:
                extra()
            which = _TICK_AXES.get(resolved_panel.kind, "")
            if which:
                for frame_ax, _ in frames:
                    _fit_ticks(fig, frame_ax, which)

            issues.extend({**iss, "panel": "a"} for iss in (*resolved_panel.issues, *ctx.issues))
            panel_axes = frames[0][0]
            cursor = plot_top + panel_plot_mm

        # 5. Optional footer source line
        if footer_lines:
            y_mm = height_mm - margin_y - footer_mm
            for line in footer_lines:
                fig.text(
                    _fx(margin_x),
                    _fy(y_mm),
                    _plain(line, theme),
                    ha="left",
                    va="top",
                    fontsize=foot_pt,
                    color=tokens["muted"],
                )
                y_mm += _line_mm(foot_pt)

        # 6. Visual & legibility self-audit
        result = SummaryCard(
            fig=fig,
            spec=spec,
            theme=theme,
            palette=palette_name,
            accent=accent_hex if accent is not None else None,
            resolved_accent=resolved_accent,
            takeaway=takeaway_clean,
            metrics=norm_metrics,
            panel=resolved_panel,
            panel_axes=panel_axes,
            subtitle=subtitle.strip() if isinstance(subtitle, str) and subtitle.strip() else None,
            source=source.strip() if isinstance(source, str) and source.strip() else None,
            width=width,
            issues=issues,
        )

        if result.min_text_px < MIN_TEXT_PX:
            issues.append(
                _issue(
                    "small_at_chat_size",
                    "warning",
                    f"The smallest text is {result.min_text_px:.1f} px when shown "
                    f"{result.display_width_px} px wide (floor {MIN_TEXT_PX:.0f} px).",
                    'Use width="chat" (700 px), width="narrow" (450 px), or width="slide" (1280 px).',
                )
            )

        missing = _missing_glyphs(fig)
        for ch in glyph_log.missing():
            missing.setdefault(ch, "")
        if missing:
            issues.append(_glyph_issue(missing))

        from .audit import audit_figure, audit_to_issues

        audit = audit_figure(fig, allow_ascii_minus=(theme.minus_sign == "-"))
        existing_rules = {str(i.get("rule", "")) for i in issues}
        issues.extend(audit_to_issues(audit, existing_rules=existing_rules))

    return result


# --------------------------------------------------------------------------- #
# JSON & CLI helpers
# --------------------------------------------------------------------------- #


def card_from_json(spec_dict: Mapping[str, Any] | str | Path) -> SummaryCard:
    """Build a :class:`SummaryCard` from a JSON spec dict, JSON string, or ``.json`` path."""
    if isinstance(spec_dict, (str, Path)):
        raw_str = str(spec_dict)
        if isinstance(spec_dict, str) and raw_str.lstrip().startswith("{"):
            try:
                parsed = json.loads(raw_str)
            except json.JSONDecodeError as exc:
                raise ExplainError(
                    f"Invalid card JSON: {exc}.",
                    fix_hint="Pass valid JSON or a path to a .json card spec file.",
                    rule="card_spec_invalid",
                ) from exc
        else:
            p = Path(spec_dict)
            if not p.exists():
                raise ExplainError(
                    f"Card spec file {p} does not exist.",
                    fix_hint="Check the path or pass a JSON spec dict directly.",
                    rule="card_spec_missing",
                )
            try:
                parsed = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ExplainError(
                    f"{p} is not valid JSON ({exc}).",
                    fix_hint="Fix the JSON syntax or run `mintfig card --example` to see a valid spec.",
                    rule="card_spec_invalid",
                ) from exc
        if not isinstance(parsed, Mapping):
            raise ExplainError(
                "Card JSON spec must be a JSON object.",
                fix_hint='Expected {"takeaway": "...", "metrics": [...]}.',
                rule="card_spec_invalid",
            )
        options = dict(parsed)
    elif isinstance(spec_dict, Mapping):
        options = dict(spec_dict)
    else:
        raise ExplainError(
            f"card_from_json() expected a dict or JSON path, got {type(spec_dict).__name__}.",
            fix_hint='Pass a mapping like {"takeaway": "...", "metrics": [...]}.',
            rule="card_spec_invalid",
        )

    takeaway = options.pop("takeaway", None)
    metrics = options.pop("metrics", None)
    allowed = {"panel", "subtitle", "source", "style", "palette", "accent", "width"}
    unknown = sorted(set(options) - allowed)
    if unknown:
        raise ExplainError(
            f"Unknown card spec key(s): {unknown!r}.",
            fix_hint=f"Allowed keys: takeaway, metrics, {', '.join(sorted(allowed))}.",
            rule="card_spec_invalid",
        )
    if takeaway is None or metrics is None:
        raise ExplainError(
            'Card spec requires both "takeaway" and "metrics".',
            fix_hint='Pass {"takeaway": "...", "metrics": [{"label": "...", "value": "..."}]}.',
            rule="card_spec_invalid",
        )
    return card(takeaway, metrics, **options)


def _parse_width(raw: str) -> str | float:
    try:
        return float(raw)
    except ValueError:
        return raw


def cli_card(argv: Sequence[str] | None = None) -> int:
    """Standalone CLI entry point for ``mintfig card spec.json --out card.png [--pair]``."""
    parser = argparse.ArgumentParser(
        prog="mintfig card",
        description="Render a PR / release KPI summary card from a JSON spec.",
    )
    parser.add_argument(
        "spec_path",
        nargs="?",
        default=None,
        help="Path to the card JSON spec, or '-' to read JSON from stdin.",
    )
    parser.add_argument(
        "--out",
        "-o",
        type=Path,
        default=None,
        help="Output path (.png, .svg, .pdf, or .html).",
    )
    parser.add_argument(
        "--pair",
        nargs="?",
        const=True,
        default=None,
        metavar="STEM_OR_DIR",
        help=(
            "Save a light + dark PNG pair (<stem>_light.png and <stem>_dark.png) and emit "
            "GitHub <picture> Markdown. Optionally pass a stem path or directory (defaults to --out)."
        ),
    )
    parser.add_argument("--style", default=None, help="Visual theme override.")
    parser.add_argument("--palette", default=None, help="Color palette override.")
    parser.add_argument("--accent", default=None, help="Accent hex color override.")
    parser.add_argument(
        "--width",
        default=None,
        help="Target width preset ('narrow', 'chat', 'slide') or mm.",
    )
    parser.add_argument(
        "--repo-prefix",
        default=None,
        help="Optional repo path or URL prefix for --pair Markdown srcset/src attributes.",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Print a GitHub-Flavored Markdown KPI table to stdout.",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Print a self-contained responsive light/dark HTML card to stdout.",
    )
    parser.add_argument(
        "--example",
        action="store_true",
        help="Print an example card JSON spec to stdout and exit.",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.example:
        print(json.dumps(EXAMPLE_CARD_SPEC, indent=2, ensure_ascii=False))
        return 0

    def _reject(message: str, fix_hint: str, rule: str = "card_cli") -> int:
        payload = {
            "ok": False,
            "rule": rule,
            "error": message,
            "fix_hint": fix_hint,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 2

    if args.spec_path is None:
        return _reject(
            "mintfig card needs a spec.json path (or '-' for stdin).",
            "Run `mintfig card --example` to see the expected JSON format.",
        )

    if args.out is None and args.pair is None and not args.markdown and not args.html:
        return _reject(
            "mintfig card needs --out <path>, --pair [stem_or_dir], --markdown, or --html.",
            "Pass --out card.png, --out card.png --pair, --markdown, or --html.",
        )

    try:
        if args.spec_path == "-":
            raw = json.loads(sys.stdin.read())
        else:
            p = Path(args.spec_path)
            raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            return _reject(
                "Card spec must be a JSON object.",
                "Run `mintfig card --example` for a valid template.",
            )
        spec_dict = dict(raw)
        if args.style is not None:
            spec_dict["style"] = args.style
        if args.palette is not None:
            spec_dict["palette"] = args.palette
        if args.accent is not None:
            spec_dict["accent"] = args.accent
        if args.width is not None:
            spec_dict["width"] = _parse_width(args.width)

        summary_card = card_from_json(spec_dict)
    except (OSError, json.JSONDecodeError, ExplainError, ValueError, TypeError) as exc:
        hint = exc.fix_hint if isinstance(exc, ExplainError) else "Check the JSON spec and flags."
        rule = exc.rule if isinstance(exc, ExplainError) else "card_spec_invalid"
        return _reject(str(exc), hint, rule=rule)

    import matplotlib.pyplot as plt

    try:
        if args.markdown and args.out is None and args.pair is None:
            print(summary_card.to_markdown())
            return 0
        if args.html and args.out is None and args.pair is None:
            print(summary_card.to_html())
            return 0

        if args.pair is not None:
            if args.pair is True:
                pair_target: str | Path = args.out if args.out is not None else Path("card")
            else:
                pair_target = args.pair
            pair_res = summary_card.save_pair(pair_target, repo_prefix=args.repo_prefix)
            if args.out is not None and args.pair is not True:
                summary_card.save(args.out)
            print(json.dumps(pair_res, indent=2, ensure_ascii=False))
            return 0 if pair_res["ok"] else 1

        assert args.out is not None
        res = summary_card.save(args.out)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res["ok"] else 1
    finally:
        plt.close(summary_card.fig)
