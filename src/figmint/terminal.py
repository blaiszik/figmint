"""Terminal-adaptive rendering and inline graphics protocol support for figmint.

Supports:
* Graphics protocol detection (Kitty / Ghostty APC, iTerm2 / WezTerm OSC 1337,
  or rich Unicode fallback).
* Standard Kitty APC and iTerm2 OSC 1337 PNG encoders.
* High-legibility Unicode and ASCII terminal renderings for every ``fm.explain``
  panel form (horizontal bars, box-drawn tables, sparklines, structured facts).
"""

from __future__ import annotations

import base64
import io
import json
import math
import os
import textwrap
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from matplotlib.colors import to_rgb

from ._explain.core import Panel, _GlyphCapture
from ._explain.layout import Explanation, explain_from_spec, read_png_text

__all__ = [
    "detect_graphics_protocol",
    "encode_iterm2_png",
    "encode_kitty_png",
    "render_terminal",
    "show_in_terminal",
]

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_KITTY_CHUNK_SIZE = 4096

_UNICODE_BAR_BLOCKS = (" ", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█")
_UNICODE_SPARK = "▁▂▃▄▅▆▇█"
_ASCII_SPARK = "._-=+*#@"

_ASCII_TRANSLATE = str.maketrans(
    {
        "\N{RIGHTWARDS ARROW}": "->",
        "\N{LEFTWARDS ARROW}": "<-",
        "\N{MINUS SIGN}": "-",
        "\N{EN DASH}": "-",
        "\N{EM DASH}": "--",
        "\N{MULTIPLICATION SIGN}": "x",
        "\N{HORIZONTAL ELLIPSIS}": "...",
        "\N{PLUS-MINUS SIGN}": "+/-",
        "\N{GREEK SMALL LETTER MU}": "u",
        "\N{MICRO SIGN}": "u",
        "\N{DEGREE SIGN}": " deg",
        "\N{BULLET}": "*",
        "\N{MIDDLE DOT}": "*",
        "\N{NO-BREAK SPACE}": " ",
    }
)


def _to_ascii(text: str) -> str:
    """Transliterate typographic Unicode to clean printable ASCII."""
    mapped = text.translate(_ASCII_TRANSLATE)
    return mapped.encode("ascii", errors="replace").decode("ascii")


def _ensure_explanation(exp_or_spec: Explanation | Mapping[str, Any]) -> Explanation:
    if isinstance(exp_or_spec, Explanation):
        return exp_or_spec
    if isinstance(exp_or_spec, Mapping):
        return explain_from_spec(exp_or_spec)
    raise TypeError(
        "Expected an Explanation or a spec mapping, "
        f"got {type(exp_or_spec).__name__}."
    )


def _is_num(val: Any) -> bool:
    if isinstance(val, bool) or val is None:
        return False
    if isinstance(val, (int, float)):
        return math.isfinite(float(val))
    return False


def _fmt_num(val: Any, *, ascii_only: bool = False) -> str:
    if val is None:
        return "-" if ascii_only else "—"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, float):
        if not math.isfinite(val):
            return "-" if ascii_only else "—"
        if abs(val - round(val)) < 1e-9 and abs(val) < 1e12:
            text = f"{round(val):,}"
        else:
            text = f"{val:,.3g}" if abs(val) < 1e6 else f"{val:.3g}"
        return text if ascii_only else text.replace("-", "\N{MINUS SIGN}")
    if isinstance(val, int):
        text = f"{val:,}"
        return text if ascii_only else text.replace("-", "\N{MINUS SIGN}")
    text = str(val)
    return _to_ascii(text) if ascii_only else text


def _ansi_rgb(hex_color: str, *, bold: bool = False) -> str:
    r, g, b = (round(c * 255) for c in to_rgb(hex_color))
    prefix = "1;" if bold else ""
    return f"\x1b[{prefix}38;2;{r};{g};{b}m"


class _Style:
    """Minimal ANSI styler that becomes a no-op when ``color=False``."""

    def __init__(self, enabled: bool, *, accent: str = "#CD4324", primary: str = "#1F5A9D") -> None:
        self.enabled = enabled
        self._accent = _ansi_rgb(accent, bold=True) if enabled else ""
        self._primary = _ansi_rgb(primary) if enabled else ""
        self._reset = "\x1b[0m" if enabled else ""

    def bold(self, text: str) -> str:
        return f"\x1b[1m{text}{self._reset}" if self.enabled else text

    def dim(self, text: str) -> str:
        return f"\x1b[2m{text}{self._reset}" if self.enabled else text

    def accent(self, text: str) -> str:
        return f"{self._accent}{text}{self._reset}" if self.enabled else text

    def primary(self, text: str) -> str:
        return f"{self._primary}{text}{self._reset}" if self.enabled else text


def detect_graphics_protocol(env: Mapping[str, str] | None = None) -> str:
    """Detect inline terminal graphics support from environment variables.

    Returns ``"kitty"`` (Kitty / Ghostty), ``"iterm2"`` (iTerm2 / WezTerm), or
    ``"unicode"`` (plain text fallback).
    """
    source = os.environ if env is None else env
    if source.get("KITTY_WINDOW_ID"):
        return "kitty"
    term = str(source.get("TERM", "")).lower()
    term_program = str(source.get("TERM_PROGRAM", "")).lower()
    if "kitty" in term or "ghostty" in term or term_program in {"kitty", "ghostty"}:
        return "kitty"
    lc_terminal = str(source.get("LC_TERMINAL", "")).lower()
    if term_program in {"iterm.app", "wezterm"} or lc_terminal == "iterm2":
        return "iterm2"
    return "unicode"


def encode_kitty_png(png_bytes: bytes) -> str:
    """Encode PNG bytes as a Kitty Graphics Protocol APC escape sequence."""
    if not png_bytes:
        raise ValueError("png_bytes must not be empty.")
    b64 = base64.b64encode(png_bytes).decode("ascii")
    chunks = [b64[i : i + _KITTY_CHUNK_SIZE] for i in range(0, len(b64), _KITTY_CHUNK_SIZE)]
    parts: list[str] = []
    last_idx = len(chunks) - 1
    for idx, chunk in enumerate(chunks):
        more = 1 if idx < last_idx else 0
        if idx == 0:
            parts.append(f"\x1b_Ga=T,f=100,m={more};{chunk}\x1b\\")
        else:
            parts.append(f"\x1b_Gm={more};{chunk}\x1b\\")
    return "".join(parts)


def encode_iterm2_png(png_bytes: bytes) -> str:
    """Encode PNG bytes as an iTerm2 OSC 1337 inline image escape sequence."""
    if not png_bytes:
        raise ValueError("png_bytes must not be empty.")
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return f"\x1b]1337;File=inline=1;size={len(png_bytes)}:{b64}\x07"


def _bar_str(fraction: float, max_chars: int, *, ascii_only: bool) -> str:
    frac = max(0.0, min(1.0, fraction))
    if max_chars <= 0:
        return ""
    if ascii_only:
        count = max(1, round(frac * max_chars)) if frac > 0 else 0
        return "#" * count
    eighths = round(frac * max_chars * 8)
    if frac > 0 and eighths == 0:
        eighths = 1
    full = eighths // 8
    rem = eighths % 8
    return "█" * full + (_UNICODE_BAR_BLOCKS[rem] if rem else "")


def _sparkline(values: Sequence[float | None], *, ascii_only: bool) -> str:
    glyphs = _ASCII_SPARK if ascii_only else _UNICODE_SPARK
    finite = [float(v) for v in values if _is_num(v)]
    if not finite:
        return ""
    lo, hi = min(finite), max(finite)
    span = hi - lo
    out: list[str] = []
    for v in values:
        if not _is_num(v):
            out.append(" ")
            continue
        if span <= 0:
            idx = len(glyphs) // 2
        else:
            idx = round((float(v) - lo) / span * (len(glyphs) - 1))
            idx = max(0, min(len(glyphs) - 1, idx))
        out.append(glyphs[idx])
    return "".join(out)


def _render_bars_panel(
    panel: Panel,
    *,
    width: int,
    style: _Style,
    ascii_only: bool,
) -> list[str]:
    spec = panel.spec
    is_share = panel.kind == "share"
    raw_map = spec.get("parts") if is_share else spec.get("values")
    if not isinstance(raw_map, Mapping) or not raw_map:
        return [f"  {fact}" for fact in panel.facts]

    first_val = next(iter(raw_map.values()))
    if isinstance(first_val, Mapping):
        # Grouped compare: render as a crisp table of item x series
        series_names: list[str] = []
        for sub in raw_map.values():
            if isinstance(sub, Mapping):
                for sk in sub:
                    if str(sk) not in series_names:
                        series_names.append(str(sk))
        headers = ["Item", *series_names]
        rows = [
            [
                str(item),
                *[_fmt_num(sub.get(s) if isinstance(sub, Mapping) else None, ascii_only=ascii_only) for s in series_names],
            ]
            for item, sub in raw_map.items()
        ]
        return _render_box_table(
            headers,
            rows,
            aligns=["left", *(["right"] * len(series_names))],
            width=width,
            style=style,
            ascii_only=ascii_only,
        )

    items = [(str(k), float(v)) for k, v in raw_map.items() if _is_num(v)]
    if not items:
        return []
    if is_share or spec.get("sort", True):
        items.sort(key=lambda kv: kv[1], reverse=True)

    hl_raw = spec.get("highlight") or []
    hl_set = {str(h) for h in ([hl_raw] if isinstance(hl_raw, str) else hl_raw)}
    total = sum(v for _, v in items) if is_share else 0.0
    max_abs = max((abs(v) for _, v in items), default=1.0) or 1.0
    unit = f" {panel.unit}" if panel.unit and not is_share else ""

    formatted_vals: list[str] = []
    for _, v in items:
        if is_share and total > 0:
            formatted_vals.append(f"{v / total * 100.0:.1f}% ({_fmt_num(v, ascii_only=ascii_only)})")
        else:
            formatted_vals.append(f"{_fmt_num(v, ascii_only=ascii_only)}{unit}")

    max_lbl = min(max(len(k) for k, _ in items), max(12, width // 3))
    max_val_w = max(len(s) for s in formatted_vals)
    # 2 indent + 2 marker + lbl + 2 gap + bar + 1 space + val
    bar_w = max(8, width - (4 + max_lbl + 2 + 1 + max_val_w))

    lines: list[str] = []
    marker_on = ">" if ascii_only else "▸"
    for (name, val), val_str in zip(items, formatted_vals, strict=True):
        is_hl = name in hl_set
        disp_name = name if len(name) <= max_lbl else name[: max_lbl - 1] + ("." if ascii_only else "…")
        padded_lbl = disp_name.rjust(max_lbl)
        bar = _bar_str(abs(val) / max_abs, bar_w, ascii_only=ascii_only)
        marker = marker_on if is_hl else " "
        if is_hl:
            line = f"  {style.accent(marker)} {style.bold(padded_lbl)}  {style.accent(bar)} {style.bold(val_str)}"
        else:
            line = f"  {marker} {padded_lbl}  {style.primary(bar)} {val_str}"
        lines.append(line)
    return lines


def _render_box_table(
    headers: list[str],
    rows: list[list[str]],
    *,
    aligns: list[str],
    width: int,
    style: _Style,
    ascii_only: bool,
    highlight_rows: set[str] | None = None,
) -> list[str]:
    if not headers:
        return []
    n_cols = len(headers)
    col_w = [
        max(len(headers[c]), *(len(r[c]) for r in rows if c < len(r)), 1)
        for c in range(n_cols)
    ]
    # Fit within width if needed
    overhead = 3 * n_cols + 1
    avail = max(n_cols * 4, width - overhead)
    if sum(col_w) > avail:
        scale = avail / sum(col_w)
        col_w = [max(4, int(w * scale)) for w in col_w]

    def _clip(text: str, w: int) -> str:
        if len(text) <= w:
            return text
        return text[: max(1, w - 1)] + ("." if ascii_only else "…")

    def _pad(text: str, w: int, al: str) -> str:
        clipped = _clip(text, w)
        if al == "right":
            return clipped.rjust(w)
        if al == "center":
            return clipped.center(w)
        return clipped.ljust(w)

    if ascii_only:
        tl, tm, tr, h, v = "+", "+", "+", "-", "|"
        ml, mm, mr = "+", "+", "+"
        bl, bm, br = "+", "+", "+"
    else:
        tl, tm, tr, h, v = "┌", "┬", "┐", "─", "│"
        ml, mm, mr = "├", "┼", "┤"
        bl, bm, br = "└", "┴", "┘"

    top = tl + tm.join(h * (w + 2) for w in col_w) + tr
    mid = ml + mm.join(h * (w + 2) for w in col_w) + mr
    bot = bl + bm.join(h * (w + 2) for w in col_w) + br

    hdr_cells = [style.bold(_pad(headers[c], col_w[c], aligns[c])) for c in range(n_cols)]
    lines = [top, f"{v} " + f" {v} ".join(hdr_cells) + f" {v}", mid]
    hl = highlight_rows or set()
    for row in rows:
        row_key = row[0] if row else ""
        is_hl = row_key in hl
        cells = []
        for c in range(n_cols):
            val = row[c] if c < len(row) else ""
            padded = _pad(val, col_w[c], aligns[c])
            cells.append(style.accent(padded) if is_hl and c == 0 else padded)
        lines.append(f"{v} " + f" {v} ".join(cells) + f" {v}")
    lines.append(bot)
    return lines


def _render_table_panel(
    panel: Panel,
    *,
    width: int,
    style: _Style,
    ascii_only: bool,
) -> list[str]:
    spec = panel.spec
    headers = [str(c) for c in (spec.get("columns") or [])]
    raw_rows = spec.get("rows") or []
    if not headers or not isinstance(raw_rows, Sequence):
        return [f"  {fact}" for fact in panel.facts]

    align_map = spec.get("align") if isinstance(spec.get("align"), Mapping) else {}
    aligns: list[str] = []
    for c_idx, col_name in enumerate(headers):
        if col_name in align_map:
            aligns.append(str(align_map[col_name]))
        else:
            col_vals = [r[c_idx] for r in raw_rows if isinstance(r, Sequence) and c_idx < len(r)]
            is_num_col = bool(col_vals) and all(_is_num(v) or v is None for v in col_vals)
            aligns.append("right" if is_num_col else "left")

    str_rows = [
        [_fmt_num(r[c], ascii_only=ascii_only) if c < len(r) else "" for c in range(len(headers))]
        for r in raw_rows
        if isinstance(r, Sequence)
    ]
    hl_raw = spec.get("highlight") or []
    hl_set = {str(h) for h in ([hl_raw] if isinstance(hl_raw, str) else hl_raw)}
    return _render_box_table(
        headers,
        str_rows,
        aligns=aligns,
        width=width,
        style=style,
        ascii_only=ascii_only,
        highlight_rows=hl_set,
    )


def _render_trend_panel(
    panel: Panel,
    *,
    width: int,
    style: _Style,
    ascii_only: bool,
) -> list[str]:
    spec = panel.spec
    series_raw = spec.get("series")
    x_vals = spec.get("x") or []
    unit = f" {panel.unit}" if panel.unit else ""
    arrow = "->" if ascii_only else "→"

    series_map: dict[str, list[float | None]] = {}
    if isinstance(series_raw, Mapping):
        for name, vals in series_raw.items():
            if isinstance(vals, Sequence):
                series_map[str(name)] = [float(v) if _is_num(v) else None for v in vals]
    elif isinstance(series_raw, Sequence) and not isinstance(series_raw, (str, bytes)):
        series_map[panel.label or "series"] = [float(v) if _is_num(v) else None for v in series_raw]
    elif isinstance(spec.get("points"), Mapping):
        for name, buckets in spec["points"].items():
            if isinstance(buckets, Sequence):
                disp_name = str(name) or panel.label or "series"
                means: list[float | None] = []
                for bucket in buckets:
                    if isinstance(bucket, Sequence) and not isinstance(bucket, (str, bytes)):
                        nums = [float(v) for v in bucket if _is_num(v)]
                        means.append(sum(nums) / len(nums) if nums else None)
                    elif _is_num(bucket):
                        means.append(float(bucket))
                    else:
                        means.append(None)
                series_map[disp_name] = means

    if not series_map:
        return [f"  {fact}" for fact in panel.facts]

    hl_raw = spec.get("highlight") or []
    hl_set = {str(h) for h in ([hl_raw] if isinstance(hl_raw, str) else hl_raw)}
    max_lbl = min(max(len(k) for k in series_map), max(12, width // 4))
    lines: list[str] = []
    marker_on = ">" if ascii_only else "▸"

    for name, vals in series_map.items():
        spark = _sparkline(vals, ascii_only=ascii_only)
        finite = [v for v in vals if v is not None]
        if finite:
            first, last = finite[0], finite[-1]
            if first != 0:
                pct = (last - first) / abs(first) * 100.0
                sign = "+" if pct > 0 else ""
                delta_str = f" ({sign}{pct:.0f}%)"
            else:
                delta_str = ""
            summary = f"{_fmt_num(first, ascii_only=ascii_only)}{unit} {arrow} {_fmt_num(last, ascii_only=ascii_only)}{unit}{delta_str}"
        else:
            summary = "no finite values"
        disp = name if len(name) <= max_lbl else name[: max_lbl - 1] + ("." if ascii_only else "…")
        padded = disp.rjust(max_lbl)
        is_hl = name in hl_set
        if is_hl:
            lines.append(
                f"  {style.accent(marker_on)} {style.bold(padded)}  {style.accent(spark)}  {style.bold(summary)}"
            )
        else:
            lines.append(f"    {padded}  {style.primary(spark)}  {summary}")

    meta_bits: list[str] = []
    if len(x_vals) >= 2:
        x_lbl = spec.get("x_label") or "x"
        meta_bits.append(f"{x_lbl}: {x_vals[0]} {arrow} {x_vals[-1]}")
    events = spec.get("events")
    if isinstance(events, Mapping) and events:
        ev_str = ", ".join(f"{k}: {v}" for k, v in events.items())
        meta_bits.append(f"Events: {ev_str}")
    if meta_bits:
        lines.append("  " + style.dim(" | ".join(meta_bits)))
    return lines


def _render_facts_panel(
    panel: Panel,
    *,
    width: int,
    style: _Style,
    ascii_only: bool,
) -> list[str]:
    bullet = "-" if ascii_only else "•"
    lines: list[str] = []
    if panel.kind == "matrix":
        spec = panel.spec
        rows_lbl = [str(r) for r in (spec.get("rows") or [])]
        cols_lbl = [str(c) for c in (spec.get("cols") or [])]
        vals = spec.get("values") or []
        if cols_lbl and isinstance(vals, Sequence) and len(cols_lbl) <= 6 and len(vals) <= 8:
            str_rows = []
            for r_idx, rv in enumerate(vals):
                rl = rows_lbl[r_idx] if r_idx < len(rows_lbl) else f"r{r_idx + 1}"
                if isinstance(rv, Sequence):
                    str_rows.append([rl, *[_fmt_num(v, ascii_only=ascii_only) for v in rv]])
            lines.extend(
                _render_box_table(
                    ["", *cols_lbl],
                    str_rows,
                    aligns=["left", *(["right"] * len(cols_lbl))],
                    width=width,
                    style=style,
                    ascii_only=ascii_only,
                )
            )
    elif panel.kind == "change":
        spec = panel.spec
        before = spec.get("before") or {}
        after = spec.get("after") or {}
        unit = f" {panel.unit}" if panel.unit else ""
        arrow = "->" if ascii_only else "→"
        if isinstance(before, Mapping) and isinstance(after, Mapping) and before:
            max_lbl = min(max(len(str(k)) for k in before), max(12, width // 3))
            for item, bv in before.items():
                av = after.get(item)
                if _is_num(bv) and _is_num(av):
                    delta = float(av) - float(bv)
                    sign = "+" if delta > 0 else ""
                    lines.append(
                        f"  {str(item).rjust(max_lbl)}  "
                        f"{_fmt_num(bv, ascii_only=ascii_only)}{unit} {arrow} "
                        f"{_fmt_num(av, ascii_only=ascii_only)}{unit} "
                        f"({sign}{_fmt_num(delta, ascii_only=ascii_only)}{unit})"
                    )

    if panel.facts:
        for fact in panel.facts:
            wrapped = textwrap.wrap(fact, width=max(30, width - 4))
            for idx, wline in enumerate(wrapped):
                prefix = f"  {bullet} " if idx == 0 else "    "
                lines.append(prefix + wline)
    elif not lines and panel.describe:
        lines.append(f"  {bullet} {panel.describe}")
    return lines


def render_terminal(
    exp_or_spec: Explanation | Mapping[str, Any],
    *,
    width: int = 78,
    color: bool = True,
    ascii_only: bool = False,
) -> str:
    """Render an ``Explanation`` or spec dict as crisp Unicode or ASCII terminal output."""
    exp = _ensure_explanation(exp_or_spec)
    w = max(40, int(width))
    accent = exp.theme.accent_colors[0] if exp.theme.accent_colors else "#CD4324"
    primary = exp.theme.series_colors[0] if exp.theme.series_colors else "#1F5A9D"
    style = _Style(enabled=color, accent=accent, primary=primary)
    rule = ("-" if ascii_only else "─") * w

    out: list[str] = []
    for line in textwrap.wrap(exp.takeaway, width=w):
        out.append(style.bold(line))
    if exp.subtitle:
        for line in textwrap.wrap(exp.subtitle, width=w):
            out.append(style.dim(line))
    out.append(style.dim(rule))

    multi = len(exp.panels) > 1
    bullet = "-" if ascii_only else "•"
    for p_idx, (key, panel) in enumerate(exp.panels.items()):
        if p_idx > 0:
            out.append("")
        title_part = panel.title or panel.label or panel.kind
        meta_part = ""
        if panel.label and panel.unit:
            meta_part = f" [{panel.label}, {panel.unit}]"
        elif panel.unit:
            meta_part = f" [{panel.unit}]"
        elif panel.label and panel.label != title_part:
            meta_part = f" [{panel.label}]"
        prefix = f"[{key}] " if multi else ""
        out.append(style.bold(f"{prefix}{title_part}") + style.dim(meta_part))

        if panel.kind in {"compare", "share"}:
            out.extend(_render_bars_panel(panel, width=w, style=style, ascii_only=ascii_only))
            if panel.facts:
                out.append(style.dim(f"  {bullet} {panel.facts[0]}"))
        elif panel.kind == "table":
            out.extend(_render_table_panel(panel, width=w, style=style, ascii_only=ascii_only))
            if panel.facts:
                out.append(style.dim(f"  {bullet} {panel.facts[0]}"))
        elif panel.kind == "trend":
            out.extend(_render_trend_panel(panel, width=w, style=style, ascii_only=ascii_only))
            if panel.facts:
                out.append(style.dim(f"  {bullet} {panel.facts[0]}"))
        else:
            out.extend(_render_facts_panel(panel, width=w, style=style, ascii_only=ascii_only))

    footer_lines: list[str] = []
    if exp.note:
        footer_lines.extend(textwrap.wrap(f"Note: {exp.note}", width=w))
    if exp.source:
        footer_lines.extend(textwrap.wrap(f"Source: {exp.source}", width=w))
    if footer_lines:
        out.append(style.dim(rule))
        for fl in footer_lines:
            out.append(style.dim(fl))

    rendered = "\n".join(out)
    return _to_ascii(rendered) if ascii_only else rendered


def _explanation_to_png_bytes(exp: Explanation) -> bytes:
    buf = io.BytesIO()
    dpi = round(exp.display_width_px * 2.0 / float(exp.fig.get_figwidth()))
    with exp.theme.rc_context(exp.spec), _GlyphCapture():
        exp.fig.savefig(
            buf,
            format="png",
            dpi=dpi,
            facecolor=exp.theme.background,
            edgecolor=exp.theme.background,
        )
    return buf.getvalue()


def show_in_terminal(
    path_or_spec: str | Path | Explanation | Mapping[str, Any],
    *,
    mode: str = "auto",
    width: int = 78,
    color: bool = True,
    env: Mapping[str, str] | None = None,
) -> str:
    """Return a terminal-ready string (inline graphics escape sequence or rich text).

    ``path_or_spec`` may be a PNG path, a JSON spec path, an ``Explanation``, or
    a spec dict. ``mode`` may be ``"auto"``, ``"kitty"``, ``"iterm2"``,
    ``"unicode"``, or ``"ascii"``.
    """
    valid_modes = {"auto", "kitty", "iterm2", "unicode", "ascii"}
    if mode not in valid_modes:
        raise ValueError(
            f"Unknown terminal mode {mode!r}. Choose one of: {', '.join(sorted(valid_modes))}."
        )

    resolved = detect_graphics_protocol(env) if mode == "auto" else mode
    png_bytes: bytes | None = None
    exp_or_spec: Explanation | Mapping[str, Any] | None = None
    raw_png_path: Path | None = None

    if isinstance(path_or_spec, (Explanation, Mapping)):
        exp_or_spec = path_or_spec
    elif isinstance(path_or_spec, (str, Path)):
        path = Path(path_or_spec)
        raw = path.read_bytes()
        if raw.startswith(_PNG_SIGNATURE):
            png_bytes = raw
            raw_png_path = path
            embedded = read_png_text(path)
            if "figmint:spec" in embedded:
                exp_or_spec = json.loads(embedded["figmint:spec"])
        else:
            spec = json.loads(raw.decode("utf-8"))
            if not isinstance(spec, Mapping):
                raise ValueError("JSON spec must be an object.")
            exp_or_spec = spec
    else:
        raise TypeError(
            "path_or_spec must be a Path, str, Explanation, or spec mapping, "
            f"got {type(path_or_spec).__name__}."
        )

    if resolved in {"kitty", "iterm2"}:
        if png_bytes is None:
            assert exp_or_spec is not None
            exp = _ensure_explanation(exp_or_spec)
            png_bytes = _explanation_to_png_bytes(exp)
        return encode_kitty_png(png_bytes) if resolved == "kitty" else encode_iterm2_png(png_bytes)

    ascii_only = resolved == "ascii"
    if exp_or_spec is not None:
        return render_terminal(exp_or_spec, width=width, color=color, ascii_only=ascii_only)

    # Plain PNG with no embedded figmint spec in text-only mode: return clean summary
    from PIL import Image

    assert png_bytes is not None
    with Image.open(io.BytesIO(png_bytes)) as img:
        img_w, img_h = img.size
    name = raw_png_path.name if raw_png_path else "image.png"
    msg = (
        f"{name} ({img_w}x{img_h} px PNG, no embedded figmint spec for text rendering; "
        "use --mode kitty or --mode iterm2 for inline image display)"
    )
    return _to_ascii(msg) if ascii_only else msg
