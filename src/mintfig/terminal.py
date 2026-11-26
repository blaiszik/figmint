"""Terminal-adaptive rendering and inline graphics protocol support for mintfig.

Supports:
* Graphics protocol detection (Kitty / Ghostty APC, iTerm2 / WezTerm OSC 1337,
  or rich Unicode fallback).
* Standard Kitty APC and iTerm2 OSC 1337 PNG encoders.
* High-legibility Unicode and ASCII terminal renderings for every ``mint.explain``
  panel form (horizontal bars, box-drawn tables, sparklines, structured facts).
"""

from __future__ import annotations

import base64
import dataclasses
import io
import json
import math
import os
import re
import sys
import textwrap
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from matplotlib.colors import to_rgb

from ._explain.compare import _compare_intervals, _sort_order
from ._explain.core import (
    _SCI_LARGE,
    _SCI_SMALL,
    ExplainError,
    Panel,
    _ascii_sci,
    _diff_with_unit,
    _formatter,
    _GlyphCapture,
    _issue,
    _range_with_unit,
    _shows_zero,
    _sig_text,
    _signed,
    _with_unit,
)
from ._explain.layout import COLOR_SLOTS, Explanation, explain_from_spec, read_png_text

__all__ = [
    "audit_text_surface",
    "detect_graphics_protocol",
    "encode_iterm2_png",
    "encode_kitty_png",
    "in_notebook",
    "render_terminal",
    "show_in_terminal",
]

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
#: A relative change is only printed when the start is at least this share of the series range.
_MIN_RELATIVE_BASE = 0.1
#: Facts a panel with no faithful text form prints under its title.
_TOP_FACTS = 3
#: Matrix panels larger than this print as title and top facts.
_MAX_TEXT_MATRIX = (8, 6)

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
    mapped = _ascii_sci(text).translate(_ASCII_TRANSLATE)
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
    if isinstance(val, (int, float)) and val != 0 and math.isfinite(val):
        mag = abs(float(val))
        # Scientific as in the figure ("1.3×10⁻⁷"); a non-zero value never prints as 0.
        if mag < _SCI_SMALL or mag >= _SCI_LARGE or (mag >= 1e6 and val != round(val)):
            text = _sig_text(float(val))
            return _ascii_sci(text).replace("\N{MINUS SIGN}", "-") if ascii_only else text
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

    def color(self, text: str, hex_color: str | None, *, bold: bool = False) -> str:
        if not self.enabled or not hex_color:
            return self.bold(text) if bold else text
        return f"{_ansi_rgb(hex_color, bold=bold)}{text}{self._reset}"


def in_notebook() -> bool:
    """True inside a Jupyter-style kernel (rich HTML/PNG display is available)."""
    ipython = sys.modules.get("IPython")
    if ipython is None:
        return False
    try:
        shell = ipython.get_ipython()  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - any failure means "not a notebook"
        return False
    if shell is None:
        return False
    return type(shell).__name__ == "ZMQInteractiveShell" or "IPKernelApp" in getattr(
        shell, "config", {}
    )


def _entity_hex(exp: Explanation) -> dict[str, str]:
    """``{name: hex}`` for every named entity, from the figure's own colour registry."""
    colours = exp.theme.series_colors
    out: dict[str, str] = {}
    for name, slot in exp.entity_colors.items():
        idx = COLOR_SLOTS.get(str(slot))
        if idx is not None and colours:
            out[name] = colours[idx % len(colours)]
    return out


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


def _sparkline(
    values: Sequence[float | None],
    *,
    ascii_only: bool,
    lo: float | None = None,
    hi: float | None = None,
) -> str:
    """One glyph per value; ``lo``/``hi`` set a range shared with the panel's other series."""
    glyphs = _ASCII_SPARK if ascii_only else _UNICODE_SPARK
    finite = [float(v) for v in values if _is_num(v)]
    if not finite:
        return ""
    lo = min(finite) if lo is None else lo
    hi = max(finite) if hi is None else hi
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


def _clip_label(name: str, max_len: int, *, ascii_only: bool) -> str:
    if len(name) <= max_len:
        return name
    return name[: max_len - 1] + ("." if ascii_only else "…")


def _ranked_items(panel: Panel) -> list[tuple[str, float]]:
    """The items of a single-series ``compare``/``share`` in the order the figure draws them."""
    spec = panel.spec
    is_share = panel.kind == "share"
    raw_map = spec.get("parts") if is_share else spec.get("values")
    if not isinstance(raw_map, Mapping):
        return []
    items = [(str(k), float(v)) for k, v in raw_map.items() if _is_num(v)]
    if is_share:
        return sorted(items, key=lambda kv: kv[1], reverse=True)
    try:
        order = _sort_order(spec.get("sort", True))
    except ExplainError:
        order = "desc"
    boost = spec.get("boost") if isinstance(spec.get("boost"), Mapping) else {}

    def _key(kv: tuple[str, float]) -> float:
        extra = boost.get(kv[0])
        return kv[1] + (float(extra) if _is_num(extra) else 0.0)

    if order == "desc":
        return sorted(items, key=_key, reverse=True)
    if order == "asc":
        return sorted(items, key=_key)
    return items


def _compare_draws_dots(panel: Panel) -> bool:
    """Mirror of ``compare()``: dots when zero is off, intervals are given, or the axis is log."""
    spec = panel.spec
    return spec.get("zero", True) is False or spec.get("error") is not None or bool(spec.get("log"))


def _compare_errors(
    panel: Panel, values: dict[str, float]
) -> tuple[dict[str, tuple[float, float]] | None, dict[str, tuple[float, float]] | None]:
    spec = panel.spec
    if spec.get("error") is None:
        return None, None
    try:
        errors, _ = _compare_intervals(spec["error"], values)
    except (ExplainError, KeyError, TypeError, ValueError):
        return None, None
    inner: dict[str, tuple[float, float]] | None = None
    if spec.get("inner_error") is not None:
        try:
            inner, _ = _compare_intervals(spec["inner_error"], values, arg="inner_error")
        except (ExplainError, KeyError, TypeError, ValueError):
            inner = None
    return errors, inner


def _render_dot_rows(
    panel: Panel,
    items: list[tuple[str, float]],
    *,
    width: int,
    style: _Style,
    ascii_only: bool,
    colors: Mapping[str, str],
    span: tuple[float, float] | None = None,
    axis_line: bool = True,
    notes_line: bool = True,
) -> list[str]:
    """Dot (and interval) rows on one shared value axis, as the figure draws them.

    ``span`` fixes the axis (in drawn units: log10 on a log axis) for facets that share it."""
    spec = panel.spec
    values = dict(items)
    errors, inner = _compare_errors(panel, values)
    log = bool(spec.get("log"))
    unit = panel.unit
    bounds = [b for pair in (errors or {}).values() for b in pair]
    fmt_fn = _formatter([*values.values(), *bounds], spec.get("fmt"), unit=unit, log=log)

    texts: list[str] = []
    for name, val in items:
        text = _with_unit(fmt_fn(val), unit)
        if errors and name in errors:
            lo_b, hi_b = errors[name]
            text += f" ({_range_with_unit(fmt_fn(lo_b), fmt_fn(hi_b), unit)})"
        texts.append(text)

    ref = spec.get("reference")
    ref_v = (
        float(ref[0])
        if isinstance(ref, Sequence) and not isinstance(ref, str) and ref and _is_num(ref[0])
        else None
    )

    def _tf(x: float) -> float:
        return math.log10(x) if log and x > 0 else x

    fixed = span
    span = [_tf(x) for x in [*values.values(), *bounds, *([ref_v] if ref_v is not None else [])]]
    lo_ax, hi_ax = (min(span), max(span)) if fixed is None else fixed
    if hi_ax <= lo_ax:
        pad = abs(lo_ax) * 0.05 or 1.0
        lo_ax, hi_ax = lo_ax - pad, hi_ax + pad

    max_lbl = min(max(len(n) for n in values), max(12, width // 3))
    val_w = max(len(t) for t in texts)
    track_w = width - (4 + max_lbl + 2 + 2 + val_w)
    if track_w < 12:
        max_lbl = max(6, max_lbl - (12 - track_w))
        track_w = max(12, width - (4 + max_lbl + 2 + 2 + val_w))

    def _col(x: float) -> int:
        pos = (_tf(x) - lo_ax) / (hi_ax - lo_ax) * (track_w - 1)
        return max(0, min(track_w - 1, round(pos)))

    if ascii_only:
        left, right, rule, thick, dot, ref_ch = "|", "|", "-", "=", "o", ":"
    else:
        left, right, rule, thick, dot, ref_ch = "├", "┤", "─", "━", "●", "┊"

    hl_raw = spec.get("highlight") or []
    hl_set = {str(h) for h in ([hl_raw] if isinstance(hl_raw, str) else hl_raw)}
    marker_on = ">" if ascii_only else "▸"
    lines: list[str] = []
    for (name, val), text in zip(items, texts, strict=True):
        cells = [" "] * track_w
        if ref_v is not None:
            cells[_col(ref_v)] = ref_ch
        if errors and name in errors:
            a, b = _col(errors[name][0]), _col(errors[name][1])
            for c in range(a, b + 1):
                cells[c] = rule
            if inner and name in inner:
                for c in range(_col(inner[name][0]), _col(inner[name][1]) + 1):
                    cells[c] = thick
            if b > a:
                cells[a], cells[b] = left, right
        cells[_col(val)] = dot
        track = "".join(cells)
        label = _clip_label(name, max_lbl, ascii_only=ascii_only).rjust(max_lbl)
        if name in hl_set:
            hex_c = colors.get(name)
            mark = style.color(marker_on, hex_c) if hex_c else style.accent(marker_on)
            body = style.color(track, hex_c, bold=True) if hex_c else style.accent(track)
            lines.append(f"  {mark} {style.bold(label)}  {body}  {style.bold(text)}")
        else:
            body = style.dim(track) if hl_set else style.primary(track)
            lines.append(f"    {label}  {body}  {text}")

    lo_lbl = fmt_fn(10**lo_ax if log else lo_ax)
    hi_lbl = fmt_fn(10**hi_ax if log else hi_ax)
    gap = max(1, track_w - len(lo_lbl) - len(hi_lbl))
    if axis_line:
        lines.append(style.dim(f"    {' ' * max_lbl}  {lo_lbl}{' ' * gap}{hi_lbl}"))
    if not notes_line:
        return lines

    notes: list[str] = []
    if log:
        notes.append("log scale")
    if errors:
        label_txt = spec.get("error_label")
        notes.append(f"intervals: {label_txt}" if label_txt else "intervals: unlabelled")
        if inner:
            notes.append(f"{thick}: inner interval")
    elif spec.get("error") is not None:
        notes.append("intervals not shown")
    if ref_v is not None:
        ref_name = ref[1] if len(ref) > 1 and ref[1] else "reference"  # type: ignore[arg-type,index]
        notes.append(f"{ref_ch} {ref_name} {_with_unit(fmt_fn(ref_v), unit)}")
    if notes:
        lines.append(style.dim("  " + "; ".join(notes)))
    return lines


def _facet_panels(panel: Panel) -> list[tuple[str, Panel]]:
    """One single-series compare panel per category of a ``compare(facet=True)`` panel,
    items in the figure's (given) order."""
    spec = panel.spec
    nested = spec.get("values")
    error = spec.get("error")
    out: list[tuple[str, Panel]] = []
    if not isinstance(nested, Mapping):
        return out
    for cat, sub in nested.items():
        if not isinstance(sub, Mapping):
            continue
        present = {str(k): v for k, v in sub.items() if _is_num(v)}
        err = error.get(cat) if isinstance(error, Mapping) else error
        if isinstance(err, Mapping):
            err = {k: v for k, v in err.items() if str(k) in present}
        sub_spec = {**spec, "values": present, "sort": False, "facet": None, "error": err}
        out.append((str(cat), dataclasses.replace(panel, spec=sub_spec, issues=[])))
    return out


def _render_compare_facets(
    panel: Panel,
    *,
    width: int,
    style: _Style,
    ascii_only: bool,
    colors: Mapping[str, str],
) -> list[str]:
    """``compare(facet=True)``: one block per category, every block on the same scale."""
    facets = _facet_panels(panel)
    if not facets:
        return []
    lines: list[str] = []
    if _compare_draws_dots(panel):
        log = bool(panel.spec.get("log"))

        def _tf(x: float) -> float:
            return math.log10(x) if log and x > 0 else x

        marks: list[float] = []
        for _cat, sub in facets:
            vals = {k: float(v) for k, v in sub.spec["values"].items()}
            errors, _inner = _compare_errors(sub, vals)
            marks.extend(_tf(v) for v in vals.values())
            marks.extend(_tf(b) for pair in (errors or {}).values() for b in pair)
        ref = panel.spec.get("reference")
        if isinstance(ref, Sequence) and not isinstance(ref, str) and ref and _is_num(ref[0]):
            marks.append(_tf(float(ref[0])))
        span = (min(marks), max(marks))
        for i, (cat, sub) in enumerate(facets):
            lines.append(style.bold(f"  {cat}"))
            last = i == len(facets) - 1
            lines.extend(
                _render_dot_rows(
                    sub,
                    [(k, float(v)) for k, v in sub.spec["values"].items()],
                    width=width,
                    style=style,
                    ascii_only=ascii_only,
                    colors=colors,
                    span=span,
                    axis_line=last,
                    notes_line=last,
                )
            )
        return lines
    top = max(
        (abs(float(v)) for _c, sub in facets for v in sub.spec["values"].values()), default=1.0
    )
    for cat, sub in facets:
        lines.append(style.bold(f"  {cat}"))
        lines.extend(
            _render_bars_panel(
                sub, width=width, style=style, ascii_only=ascii_only, colors=colors, scale_max=top
            )
        )
    lines.append(style.dim("  one scale for every category"))
    return lines


def _render_bars_panel(
    panel: Panel,
    *,
    width: int,
    style: _Style,
    ascii_only: bool,
    colors: Mapping[str, str] | None = None,
    scale_max: float | None = None,
) -> list[str]:
    spec = panel.spec
    is_share = panel.kind == "share"
    raw_map = spec.get("parts") if is_share else spec.get("values")
    if not isinstance(raw_map, Mapping) or not raw_map:
        return [f"  {fact}" for fact in panel.facts]

    first_val = next(iter(raw_map.values()))
    if isinstance(first_val, Mapping) and spec.get("facet"):
        return _render_compare_facets(
            panel, width=width, style=style, ascii_only=ascii_only, colors=colors or {}
        )
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

    items = _ranked_items(panel)
    if not items:
        return []
    if not is_share and _compare_draws_dots(panel):
        return _render_dot_rows(
            panel, items, width=width, style=style, ascii_only=ascii_only, colors=colors or {}
        )

    hl_raw = spec.get("highlight") or []
    hl_set = {str(h) for h in ([hl_raw] if isinstance(hl_raw, str) else hl_raw)}
    total = sum(v for _, v in items) if is_share else 0.0
    unit = None if is_share else panel.unit
    # compare(boost=): the base bar plus a shaded extension, as the figure stacks them.
    boost = _boosts(panel)
    max_abs = scale_max or max((abs(v) + boost.get(k, 0.0) for k, v in items), default=1.0) or 1.0

    def _num(v: float) -> str:
        return _fmt_num(v, ascii_only=ascii_only)

    formatted_vals: list[str] = []
    for name, v in items:
        extra = boost.get(name, 0.0)
        if is_share and total > 0:
            formatted_vals.append(f"{v / total * 100.0:.1f}% ({_num(v)})")
        elif extra > 0:
            formatted_vals.append(f"{_with_unit(_num(v + extra), unit)} ({_num(v)} + {_num(extra)})")
        else:
            formatted_vals.append(_with_unit(_num(v), unit))

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
        if boost.get(name, 0.0) > 0:
            ends = round((abs(val) + boost[name]) / max_abs * bar_w)
            bar += ("=" if ascii_only else "░") * max(1, ends - len(bar))
        marker = marker_on if is_hl else " "
        hex_c = (colors or {}).get(name)
        if is_hl and hex_c:
            line = f"  {style.color(marker, hex_c)} {style.bold(padded_lbl)}  {style.color(bar, hex_c, bold=True)} {style.bold(val_str)}"
        elif is_hl:
            line = f"  {style.accent(marker)} {style.bold(padded_lbl)}  {style.accent(bar)} {style.bold(val_str)}"
        else:
            line = f"  {marker} {padded_lbl}  {style.primary(bar)} {val_str}"
        lines.append(line)
    if boost:
        label = spec.get("boost_label") or "boost (unlabelled)"
        lines.append(style.dim(f"  {'=' if ascii_only else '░'} {label}"))
    return lines


def _boosts(panel: Panel) -> dict[str, float]:
    """``{name: extension}`` of a ``compare(boost=...)`` panel (empty without one)."""
    raw = panel.spec.get("boost") if panel.kind == "compare" else None
    if not isinstance(raw, Mapping):
        return {}
    return {str(k): float(v) for k, v in raw.items() if _is_num(v)}


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
    head_lines = [h.split("\n") for h in headers]
    col_w = [
        max(*(len(line) for line in head_lines[c]), *(len(r[c]) for r in rows if c < len(r)), 1)
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

    lines = [top]
    for i in range(max(len(h) for h in head_lines)):
        hdr_cells = [
            style.bold(_pad(head_lines[c][i] if i < len(head_lines[c]) else "", col_w[c], aligns[c]))
            for c in range(n_cols)
        ]
        lines.append(f"{v} " + f" {v} ".join(hdr_cells) + f" {v}")
    lines.append(mid)
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


#: Width of an in-cell text graphic (characters), most and least.
_CELL_GRAPHIC_MAX = 10
_CELL_GRAPHIC_MIN = 3


def _table_view(panel: Panel) -> dict[str, Any] | None:
    """The drawn table (cells, scales) when it has in-cell graphics; None otherwise."""
    view = getattr(panel, "_table_view", None)
    return view if isinstance(view, dict) and view.get("graphics") else None


def _cell_text(view: Mapping[str, Any], r: int, c: int) -> str:
    """A cell's number, with its interval bounds as numbers when it has one."""
    text = str(view["cells"][r][c])
    g = view["graphics"].get(c)
    if g and g["kind"] == "interval" and g["bounds_text"][r]:
        text += f" ({g['bounds_text'][r]})"
    return text


def _split_header(text: str) -> str:
    """A multi-word header on two balanced lines."""
    words = text.split()
    if len(words) < 2:
        return text
    cuts = [(" ".join(words[:i]), " ".join(words[i:])) for i in range(1, len(words))]
    top, bot = min(cuts, key=lambda tb: max(len(tb[0]), len(tb[1])))
    return f"{top}\n{bot}"


def _table_text_layout(
    view: Mapping[str, Any], width: int
) -> tuple[list[str], list[int], list[int]]:
    """``(headers, graphic width, text width)`` per column so the box table fits ``width``.

    Headers wider than their column split onto two lines first; then the graphics
    shrink from 10 to 3 characters. A graphic also fills the room under a wide header.
    """
    headers = list(view["headers"])
    n_cols, n_rows = len(headers), len(view["cells"])
    text_w = [max((len(_cell_text(view, r, c)) for r in range(n_rows)), default=1) for c in range(n_cols)]
    graphic = view["graphics"]

    def _head_w(c: int) -> int:
        return max(len(line) for line in headers[c].split("\n"))

    def _widths(g_min: int) -> list[int]:
        g_w = [
            max(g_min, _head_w(c) - text_w[c] - 1) if c in graphic else 0 for c in range(n_cols)
        ]
        return g_w

    def _total(g_w: Sequence[int]) -> int:
        cols = [
            max(_head_w(c), text_w[c] + (1 + g_w[c] if c in graphic else 0)) for c in range(n_cols)
        ]
        return sum(cols) + 3 * n_cols + 1

    if _total(_widths(_CELL_GRAPHIC_MIN)) > width:
        headers = [
            _split_header(h) if len(h) > text_w[c] + (1 + _CELL_GRAPHIC_MIN if c in graphic else 0)
            else h
            for c, h in enumerate(headers)
        ]
    g_min = _CELL_GRAPHIC_MAX
    while g_min > _CELL_GRAPHIC_MIN and _total(_widths(g_min)) > width:
        g_min -= 1
    return headers, _widths(g_min), text_w


def _cell_bar(v: float | None, lo: float, hi: float, g_w: int, *, ascii_only: bool) -> str:
    """A bar from zero on the column's scale; a column with negatives gets a zero mark."""
    if v is None or hi <= lo:
        return " " * g_w
    if lo >= 0:
        return _bar_str(v / hi, g_w, ascii_only=ascii_only).ljust(g_w)
    zero = ":" if ascii_only else "┊"
    neg_w = round((g_w - 1) * -lo / (hi - lo))
    pos_w = g_w - 1 - neg_w
    if v >= 0:
        right = _bar_str(v / hi, pos_w, ascii_only=ascii_only) if hi > 0 else ""
        return " " * neg_w + zero + right.ljust(pos_w)
    length = -v / -lo * neg_w
    full = int(length)
    half = length - full >= 0.5 and full < neg_w
    fill = "#" if ascii_only else "█"
    left = ((("#" if ascii_only else "▐") if half else "") + fill * full) or fill
    return left.rjust(neg_w) + zero + " " * pos_w


def _cell_whisker(
    v: float | None, bounds: Sequence[float] | None, lo: float, hi: float, g_w: int, *,
    ascii_only: bool,
) -> str:
    """Dot and whisker on the column's one scale."""
    if v is None:
        return " " * g_w
    left, right, rule, dot = ("|", "|", "-", "o") if ascii_only else ("├", "┤", "─", "●")
    track = [" "] * g_w

    def _col(x: float) -> int:
        pos = (x - lo) / (hi - lo) * (g_w - 1) if hi > lo else (g_w - 1) / 2
        return max(0, min(g_w - 1, round(pos)))

    if bounds:
        a, b = _col(bounds[0]), _col(bounds[1])
        for i in range(a, b + 1):
            track[i] = rule
        if b > a:
            track[a], track[b] = left, right
    track[_col(v)] = dot
    return "".join(track)


def _render_table_graphics(
    view: Mapping[str, Any], *, width: int, style: _Style, ascii_only: bool
) -> list[str]:
    """The box table with in-cell bars, whiskers and sparklines on one scale per column."""
    headers, g_ws, text_w = _table_text_layout(view, width)
    graphics = view["graphics"]
    rows: list[list[str]] = []
    for r in range(len(view["cells"])):
        row: list[str] = []
        for c in range(len(view["headers"])):
            text = _cell_text(view, r, c)
            g = graphics.get(c)
            if g is None:
                row.append(text)
                continue
            lo, hi, g_w = float(g["lo"]), float(g["hi"]), g_ws[c]
            if g["kind"] == "bars":
                art = _cell_bar(g["values"][r], lo, hi, g_w, ascii_only=ascii_only)
            elif g["kind"] == "interval":
                art = _cell_whisker(g["values"][r], g["bounds"][r], lo, hi, g_w, ascii_only=ascii_only)
            else:
                series = g["series"][r]
                art = (
                    _sparkline(_resample(list(series), g_w), ascii_only=ascii_only, lo=lo, hi=hi)
                    if series else ""
                ).ljust(g_w)
            num = text.rjust(text_w[c])
            row.append(f"{num} {art}" if g["lead"] else f"{art} {num}")
        rows.append(row)
    aligns = ["left" if c in graphics else al for c, al in enumerate(view["aligns"])]
    lines = _render_box_table(
        headers,
        rows,
        aligns=aligns,
        width=width,
        style=style,
        ascii_only=ascii_only,
        highlight_rows=set(view["highlight"]),
    )
    if any(g["kind"] == "interval" for g in graphics.values()):
        label = view.get("interval_label") or "unlabelled"
        whisker = "|-o-|" if ascii_only else "├─●─┤"
        lines.append(style.dim(f"  {whisker} intervals: {label}"))
    return lines


def _render_table_panel(
    panel: Panel,
    *,
    width: int,
    style: _Style,
    ascii_only: bool,
) -> list[str]:
    view = _table_view(panel)
    if view is not None:
        return _render_table_graphics(view, width=width, style=style, ascii_only=ascii_only)
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


def _trend_series(panel: Panel) -> dict[str, list[float | None]]:
    """Each trend series as drawn: values per x (replicate means for ``points=``)."""
    spec = panel.spec
    series_raw = spec.get("series")
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
    return series_map


def _is_pct(unit: str | None) -> bool:
    return unit is not None and unit.strip().startswith("%")


def _points(text: str) -> str:
    """A difference of percentages, in points ("+76 pts"): never a percent of a percent."""
    bare = text.lstrip("+-\N{MINUS SIGN}")
    return f"{text} {'pt' if bare == '1' else 'pts'}"


def _delta_text(delta: float, unit: str | None, *, ascii_only: bool) -> str:
    """A signed difference with its unit, in points for a "%" unit."""
    text = _fmt_num(delta, ascii_only=ascii_only)
    if delta > 0:
        text = "+" + text
    return _points(text) if _is_pct(unit) else _with_unit(text, unit)


def _relative_ok(first: float, finite: Sequence[float]) -> bool:
    """A percent change is honest only when the start is not near zero for this series."""
    rng = max(finite) - min(finite)
    return first != 0 and abs(first) >= _MIN_RELATIVE_BASE * rng


def _change_text(first: float, last: float, finite: Sequence[float], unit: str | None) -> str:
    if not _is_pct(unit) and _relative_ok(first, finite):
        pct = (last - first) / abs(first) * 100.0
        sign = "+" if pct > 0 else ""
        return f" ({sign}{pct:.0f}%)"
    delta = last - first
    if delta == 0:
        return ""
    fmt_fn = _formatter([first, last, delta], unit=unit)
    if _is_pct(unit):
        return f" ({_points(_signed(fmt_fn(delta)))})"
    return f" ({_diff_with_unit(_signed(fmt_fn(delta)), unit)})"


def _resample(values: list[float | None], n: int) -> list[float | None]:
    """Bucket means so a long series fits ``n`` glyphs."""
    if len(values) <= n:
        return values
    out: list[float | None] = []
    for i in range(n):
        lo = i * len(values) // n
        hi = max(lo + 1, (i + 1) * len(values) // n)
        nums = [v for v in values[lo:hi] if v is not None]
        out.append(sum(nums) / len(nums) if nums else None)
    return out


def _render_trend_panel(
    panel: Panel,
    *,
    width: int,
    style: _Style,
    ascii_only: bool,
    colors: Mapping[str, str] | None = None,
    palette: Sequence[str] = (),
) -> list[str]:
    spec = panel.spec
    x_vals = spec.get("x") or []
    arrow = "->" if ascii_only else "→"
    log = bool(spec.get("log"))

    series_map = _trend_series(panel)
    if not series_map:
        return [f"  {fact}" for fact in panel.facts]

    # One y range for every series in the panel, as on the figure's shared axis.
    def _tf(v: float | None) -> float | None:
        if v is None:
            return None
        if log:
            return math.log10(v) if v > 0 else None
        return v

    scaled = {name: [_tf(v) for v in vals] for name, vals in series_map.items()}
    every = [v for vals in scaled.values() for v in vals if v is not None]
    y_lo, y_hi = (min(every), max(every)) if every else (None, None)

    hl_raw = spec.get("highlight") or []
    hl_set = {str(h) for h in ([hl_raw] if isinstance(hl_raw, str) else hl_raw)}
    # Each series keeps its figure colour; any without one takes an unused palette colour.
    own = dict(colors or {})
    spare = [c for c in palette if c not in own.values()]
    series_hex: dict[str, str | None] = {}
    for name in series_map:
        if name in own:
            series_hex[name] = own[name]
        elif hl_set:
            series_hex[name] = None  # context series: grey on the figure, dim here
        else:
            series_hex[name] = spare.pop(0) if spare else None

    max_lbl = min(max(len(k) for k in series_map), max(12, width // 4))
    summaries: dict[str, str] = {}
    for name, vals in series_map.items():
        finite = [v for v in vals if v is not None]
        if finite:
            first, last = finite[0], finite[-1]
            summaries[name] = (
                f"{_with_unit(_fmt_num(first, ascii_only=ascii_only), panel.unit)} {arrow} "
                f"{_with_unit(_fmt_num(last, ascii_only=ascii_only), panel.unit)}"
                f"{_change_text(first, last, finite, panel.unit)}"
            )
        else:
            summaries[name] = "no finite values"
    sum_w = max(len(s) for s in summaries.values())
    n_points = max(len(v) for v in scaled.values())
    spark_w = max(8, min(n_points, width - (4 + max_lbl + 2 + 2 + sum_w)))
    wrap_summary = 4 + max_lbl + 2 + spark_w + 2 + sum_w > width

    lines: list[str] = []
    marker_on = ">" if ascii_only else "▸"
    for name, vals in scaled.items():
        spark = _sparkline(_resample(vals, spark_w), ascii_only=ascii_only, lo=y_lo, hi=y_hi)
        summary = summaries[name]
        padded = _clip_label(name, max_lbl, ascii_only=ascii_only).rjust(max_lbl)
        hex_c = series_hex[name]
        is_hl = name in hl_set
        if is_hl:
            mark = style.color(marker_on, hex_c) if hex_c else style.accent(marker_on)
            body = style.color(spark, hex_c, bold=True) if hex_c else style.accent(spark)
            head, tail = f"  {mark} {style.bold(padded)}  {body}", style.bold(summary)
        else:
            body = style.color(spark, hex_c) if hex_c else style.dim(spark)
            head, tail = f"    {padded}  {body}", summary
        if wrap_summary:
            lines.extend([head, f"    {' ' * max_lbl}  {tail}"])
        else:
            lines.append(f"{head}  {tail}")

    meta_bits: list[str] = []
    if len(x_vals) >= 2:
        x_lbl = spec.get("x_label") or "x"
        meta_bits.append(f"{x_lbl}: {x_vals[0]} {arrow} {x_vals[-1]}")
    if log:
        meta_bits.append("log scale")
    events = spec.get("events")
    if isinstance(events, Mapping) and events:
        ev_str = ", ".join(f"{k}: {v}" for k, v in events.items())
        meta_bits.append(f"Events: {ev_str}")
    if meta_bits:
        for wline in textwrap.wrap(" | ".join(meta_bits), width=max(20, width - 2)):
            lines.append("  " + style.dim(wline))
    band_note = _band_note(panel, series_map)
    if band_note:
        for wline in textwrap.wrap(band_note, width=max(20, width - 2)):
            lines.append("  " + style.dim(wline))
    return lines


def _band_note(panel: Panel, series_map: Mapping[str, list[float | None]]) -> str | None:
    """Text cannot draw a band: say so, and give each band's bounds at the last x."""
    spec = panel.spec
    if spec.get("band") is None:
        return None
    from ._explain.trend import _trend_bands

    label = spec.get("band_label") or "unlabelled"
    note = f"band ({label}) not shown"
    try:
        import numpy as np

        n = max(len(v) for v in series_map.values())
        data = {
            k: np.array([np.nan if v is None else v for v in vals] + [np.nan] * (n - len(vals)))
            for k, vals in series_map.items()
        }
        bounds, _spec, _modes = _trend_bands(spec["band"], data, n)
    except (ExplainError, TypeError, ValueError):
        return note
    x_vals = spec.get("x") or []
    parts: list[str] = []
    for name, (low, high) in bounds.items():
        ok = [i for i in range(len(low)) if math.isfinite(low[i]) and math.isfinite(high[i])]
        if not ok:
            continue
        i = ok[-1]
        fmt_fn = _formatter([float(low[i]), float(high[i])], spec.get("fmt"), unit=panel.unit)
        at = f" at {x_vals[i]}" if i < len(x_vals) else ""
        parts.append(
            f"{name} {_range_with_unit(fmt_fn(float(low[i])), fmt_fn(float(high[i])), panel.unit)}{at}"
        )
    return f"{note}; {', '.join(parts)}" if parts else note


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
        u = panel.unit
        arrow = "->" if ascii_only else "→"
        if isinstance(before, Mapping) and isinstance(after, Mapping) and before:
            max_lbl = min(max(len(str(k)) for k in before), max(12, width // 3))
            for item, bv in before.items():
                av = after.get(item)
                if _is_num(bv) and _is_num(av):
                    delta = float(av) - float(bv)
                    lines.append(
                        f"  {str(item).rjust(max_lbl)}  "
                        f"{_with_unit(_fmt_num(bv, ascii_only=ascii_only), u)} {arrow} "
                        f"{_with_unit(_fmt_num(av, ascii_only=ascii_only), u)} "
                        f"({_delta_text(delta, u, ascii_only=ascii_only)})"
                    )
    elif panel.kind == "waterfall":
        spec = panel.spec
        steps = spec.get("steps") or {}
        u = panel.unit
        if isinstance(steps, Mapping) and steps:
            rows_wf: list[list[str]] = []
            running = 0.0
            st = spec.get("start")
            if isinstance(st, Sequence) and not isinstance(st, (str, bytes)) and len(st) == 2:
                running = float(st[1])
                rows_wf.append([str(st[0]), "-", _with_unit(_fmt_num(running, ascii_only=ascii_only), u)])
            for nm, dv in steps.items():
                val = float(dv)
                running += val
                rows_wf.append(
                    [
                        str(nm),
                        _delta_text(val, u, ascii_only=ascii_only),
                        _with_unit(_fmt_num(running, ascii_only=ascii_only), u),
                    ]
                )
            if spec.get("show_total", True):
                rows_wf.append(
                    [
                        str(spec.get("total_label") or "Total"),
                        "-",
                        _with_unit(_fmt_num(running, ascii_only=ascii_only), u),
                    ]
                )
            lines.extend(
                _render_box_table(
                    ["Step", "Delta", "Cumulative"],
                    rows_wf,
                    aligns=["left", "right", "right"],
                    width=width,
                    style=style,
                    ascii_only=ascii_only,
                )
            )
    elif panel.kind == "timeline":
        spans = panel.spec.get("spans") or []
        if isinstance(spans, Sequence) and spans:
            valid = [s for s in spans if isinstance(s, Sequence) and len(s) >= 3]
            if valid:
                t0 = min(float(s[1]) for s in valid)
                t1 = max(float(s[2]) for s in valid)
                wall = (t1 - t0) or 1.0
                max_lbl = min(max(len(str(s[0])) for s in valid), max(12, width // 3))
                bar_w = max(12, width - max_lbl - 18)
                fill_ch = "#" if ascii_only else "█"
                empty_ch = "." if ascii_only else "·"
                for sp in valid:
                    nm = str(sp[0])[:max_lbl].rjust(max_lbl)
                    s_v, e_v = float(sp[1]), float(sp[2])
                    c0 = max(0, min(bar_w - 1, round((s_v - t0) / wall * bar_w)))
                    c1 = max(c0 + 1, min(bar_w, round((e_v - t0) / wall * bar_w)))
                    bar = empty_ch * c0 + fill_ch * (c1 - c0) + empty_ch * (bar_w - c1)
                    dur_s = _fmt_num(e_v - s_v, ascii_only=ascii_only)
                    lines.append(f"  {nm}  {style.primary(bar)}  {_with_unit(dur_s, panel.unit)}")
    elif panel.kind == "flow":
        stages = panel.spec.get("stages") or []
        u = panel.unit
        if isinstance(stages, Sequence) and stages:
            valid = [s for s in stages if isinstance(s, Sequence) and len(s) >= 2]
            if valid:
                max_v = max(float(s[1]) for s in valid) or 1.0
                start_v = float(valid[0][1]) or 1.0
                max_lbl = min(max(len(str(s[0])) for s in valid), max(12, width // 3))
                val_w = max(
                    len(f"{_with_unit(_fmt_num(float(s[1]), ascii_only=ascii_only), u)} (100%)")
                    for s in valid
                )
                bar_w = max(10, width - max_lbl - 6 - val_w)
                fill_ch = "#" if ascii_only else "█"
                arrow = "v" if ascii_only else "↓"
                prev_v: float | None = None
                for idx_f, st in enumerate(valid):
                    nm = str(st[0])[:max_lbl].rjust(max_lbl)
                    val = float(st[1])
                    if prev_v is not None:
                        delta = val - prev_v
                        sp = (100.0 * delta / prev_v) if prev_v > 0 else 0.0
                        rsn = f" · {st[2]}" if len(st) >= 3 and st[2] else ""
                        lines.append(
                            f"  {' ' * max_lbl}  {arrow} "
                            f"{_with_unit(_fmt_num(delta, ascii_only=ascii_only), u)} ({sp:+.0f}%){rsn}"
                        )
                    filled = max(1 if val > 0 else 0, round(val / max_v * bar_w))
                    pct = 100.0 * val / start_v
                    lines.append(
                        f"  {nm}  {style.primary(fill_ch * filled)}  "
                        f"{_with_unit(_fmt_num(val, ascii_only=ascii_only), u)} ({pct:.0f}%)"
                    )
                    prev_v = val

    if panel.facts:
        for fact in panel.facts[:_TOP_FACTS]:
            wrapped = textwrap.wrap(fact, width=max(30, width - 4))
            for idx, wline in enumerate(wrapped):
                prefix = f"  {bullet} " if idx == 0 else "    "
                lines.append(prefix + wline)
    elif not lines and panel.describe:
        lines.append(f"  {bullet} {panel.describe}")
    return lines


def _bullets(facts: Sequence[str], *, width: int, bullet: str) -> list[str]:
    lines: list[str] = []
    for fact in facts:
        for idx, wline in enumerate(textwrap.wrap(fact, width=max(30, width - 4))):
            lines.append((f"  {bullet} " if idx == 0 else "    ") + wline)
    return lines


def _has_text_form(panel: Panel) -> bool:
    """Kinds the text surface can draw faithfully; the rest print their title and top facts."""
    if panel.kind in {"compare", "share", "table", "trend", "change", "waterfall", "timeline", "flow"}:
        return True
    if panel.kind == "matrix":
        rows = panel.spec.get("values") or []
        cols = panel.spec.get("cols") or []
        return bool(cols) and len(rows) <= _MAX_TEXT_MATRIX[0] and len(cols) <= _MAX_TEXT_MATRIX[1]
    return False


def _panel_block(
    key: str,
    panel: Panel,
    *,
    multi: bool,
    width: int,
    style: _Style,
    ascii_only: bool,
    colors: Mapping[str, str],
    palette: Sequence[str],
) -> list[str]:
    """One panel: its header line, then its rows (or its top facts when text cannot draw it)."""
    bullet = "-" if ascii_only else "•"
    title_part = panel.title or panel.label or panel.kind
    meta_part = ""
    if panel.label and panel.unit:
        meta_part = f" [{panel.label}, {panel.unit}]"
    elif panel.unit:
        meta_part = f" [{panel.unit}]"
    elif panel.label and panel.label != title_part:
        meta_part = f" [{panel.label}]"
    prefix = f"[{key}] " if multi else ""
    header = f"{prefix}{title_part}{meta_part}"
    if len(header) <= width:
        out = [style.bold(f"{prefix}{title_part}") + style.dim(meta_part)]
    else:
        out = [style.bold(line) for line in textwrap.wrap(header, width=width)]

    if not _has_text_form(panel):
        facts = _bullets(panel.facts[:_TOP_FACTS], width=width, bullet=bullet)
        if not facts and panel.describe:
            facts = _bullets([panel.describe], width=width, bullet=bullet)
        return out + facts

    first_fact = [style.dim(line) for line in _bullets(panel.facts[:1], width=width, bullet=bullet)]
    if panel.kind in {"compare", "share"}:
        out.extend(
            _render_bars_panel(
                panel, width=width, style=style, ascii_only=ascii_only, colors=colors
            )
        )
        out.extend(first_fact)
    elif panel.kind == "table":
        out.extend(_render_table_panel(panel, width=width, style=style, ascii_only=ascii_only))
        out.extend(first_fact)
    elif panel.kind == "trend":
        out.extend(
            _render_trend_panel(
                panel,
                width=width,
                style=style,
                ascii_only=ascii_only,
                colors=colors,
                palette=palette,
            )
        )
        out.extend(first_fact)
    else:
        out.extend(_render_facts_panel(panel, width=width, style=style, ascii_only=ascii_only))
    return out


def _fit_width(lines: list[str], width: int) -> list[str]:
    """Hard-wrap any plain line still wider than ``width`` (box tables with many columns)."""
    out: list[str] = []
    for line in lines:
        if len(line) <= width:
            out.append(line)
            continue
        out.extend(
            textwrap.wrap(
                line,
                width=width,
                subsequent_indent="    ",
                drop_whitespace=False,
                break_long_words=True,
                break_on_hyphens=False,
            )
            or [line[:width]]
        )
    return [ln.rstrip() if len(ln) > width else ln for ln in out]


def render_terminal(
    exp_or_spec: Explanation | Mapping[str, Any],
    *,
    width: int = 78,
    color: bool = True,
    ascii_only: bool = False,
) -> str:
    """Render an ``Explanation`` or spec dict as crisp Unicode or ASCII terminal output.

    ``color=False`` output has no escape codes and no line wider than ``width``, so it
    is safe inside a Markdown code block.
    """
    exp = _ensure_explanation(exp_or_spec)
    w = max(40, int(width))
    accent = exp.theme.accent_colors[0] if exp.theme.accent_colors else "#CD4324"
    primary = exp.theme.series_colors[0] if exp.theme.series_colors else "#1F5A9D"
    style = _Style(enabled=color, accent=accent, primary=primary)
    rule = ("-" if ascii_only else "─") * w
    colors = _entity_hex(exp)

    out: list[str] = []
    for line in textwrap.wrap(exp.takeaway, width=w):
        out.append(style.bold(line))
    if exp.subtitle:
        for line in textwrap.wrap(exp.subtitle, width=w):
            out.append(style.dim(line))
    out.append(style.dim(rule))

    multi = len(exp.panels) > 1
    for p_idx, (key, panel) in enumerate(exp.panels.items()):
        if p_idx > 0:
            out.append("")
        out.extend(
            _panel_block(
                key,
                panel,
                multi=multi,
                width=w,
                style=style,
                ascii_only=ascii_only,
                colors=colors,
                palette=exp.theme.series_colors,
            )
        )

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
    if ascii_only:
        rendered = _to_ascii(rendered)
    if not color:
        rendered = "\n".join(_fit_width(rendered.split("\n"), w))
    return rendered


def audit_text_surface(exp: Explanation, *, width: int = 72) -> list[dict[str, Any]]:
    """Check the plain-text rendering against the panel data it claims to show.

    Rules: ``text_ranking`` (rows in the figure's order), ``text_interval_missing``
    (a panel with intervals shows each bound and names the interval, never as bars),
    ``text_relative_from_zero`` (no percent change from a near-zero start),
    ``text_percent_of_percent`` (a "%" series changes in points), ``text_zeroed``
    (a non-zero start or end never prints as 0), ``text_table_scale`` (in-cell bars,
    whiskers and sparklines on one scale per column), ``text_boost_missing`` (a boost
    prints its base, extension and label), ``text_too_many_facts`` (at most three) and
    ``text_ansi`` (plain mode carries no escape codes).
    """
    issues: list[dict[str, Any]] = []
    plain = render_terminal(exp, width=width, color=False)
    if "\x1b" in plain:
        issues.append(
            _issue(
                "text_ansi",
                "error",
                "The plain text rendering contains terminal escape codes.",
                "Render with color=False (fig.to_text()) for Markdown and chat replies.",
            )
        )
    style = _Style(enabled=False)
    colors = _entity_hex(exp)
    multi = len(exp.panels) > 1
    for key, panel in exp.panels.items():
        if not _has_text_form(panel):
            continue
        block = _panel_block(
            key,
            panel,
            multi=multi,
            width=max(40, width),
            style=style,
            ascii_only=False,
            colors=colors,
            palette=exp.theme.series_colors,
        )
        text = "\n".join(block)
        if panel.kind in {"compare", "share"}:
            issues.extend(_audit_ranked_rows(key, panel, block, width=max(40, width)))
        if panel.kind == "compare":
            issues.extend(_audit_intervals(key, panel, block))
            issues.extend(_audit_boost(key, panel, text))
            for _cat, sub in _facet_panels(panel) if panel.spec.get("facet") else []:
                issues.extend(_audit_intervals(key, sub, block))
        if panel.kind == "trend":
            issues.extend(_audit_trend(key, panel, block, text, width=max(40, width)))
        if panel.kind in {"trend", "change"}:
            issues.extend(_audit_ends(key, panel, block))
        if panel.kind == "table":
            issues.extend(_audit_table(key, panel, block, width=max(40, width)))
        n_facts = sum(1 for line in block if line.startswith("  • "))
        if n_facts > _TOP_FACTS:
            issues.append(
                _issue(
                    "text_too_many_facts",
                    "error",
                    f"Panel {key} prints {n_facts} facts under its rows.",
                    f"Print at most {_TOP_FACTS} facts per panel; the rest stay in the summary.",
                    panel=key,
                )
            )
    return issues


def _audit_boost(key: str, panel: Panel, text: str) -> list[dict[str, Any]]:
    boost = _boosts(panel)
    values = panel.spec.get("values")
    if not boost or not isinstance(values, Mapping) or _compare_draws_dots(panel):
        return []
    label = panel.spec.get("boost_label") or "boost (unlabelled)"
    missing = [
        name for name, extra in boost.items()
        if extra > 0 and _is_num(values.get(name))
        and f"({_fmt_num(float(values[name]))} + {_fmt_num(extra)})" not in text
    ]
    if missing or str(label) not in text:
        return [
            _issue(
                "text_boost_missing",
                "error",
                f"Panel {key}: the text does not show each base and boost "
                f"({', '.join(missing[:3]) or 'label'}).",
                "Print the base and the boost extension of each bar, and the boost label.",
                panel=key,
            )
        ]
    return []


_NUM_RE = re.compile(r"[−+-]?\$?\d[\d,.]*(?:×10[⁻⁰¹²³⁴⁵⁶⁷⁸⁹]+)?")


def _audit_ends(key: str, panel: Panel, block: Sequence[str]) -> list[dict[str, Any]]:
    """Every start and end value the figure draws as non-zero keeps a non-zero digit."""
    if panel.kind == "trend":
        ends = [
            (f[0], f[-1])
            for vals in _trend_series(panel).values()
            if (f := [v for v in vals if v is not None])
        ]
    else:
        before = panel.spec.get("before") or {}
        after = panel.spec.get("after") or {}
        ends = [
            (float(bv), float(after[k]))
            for k, bv in (before.items() if isinstance(before, Mapping) else [])
            if isinstance(after, Mapping) and _is_num(bv) and _is_num(after.get(k))
        ]
    shown: list[tuple[str, str]] = []
    for line in block:
        left, arrow, right = line.partition(" → ")
        before_nums, after_nums = _NUM_RE.findall(left), _NUM_RE.findall(right)
        if arrow and before_nums and after_nums:
            shown.append((before_nums[-1], after_nums[0]))
    for (a, b), (ta, tb) in zip(ends, shown):
        if (a != 0 and _shows_zero(ta)) or (b != 0 and _shows_zero(tb)):
            return [
                _issue(
                    "text_zeroed",
                    "error",
                    f"Panel {key}: a non-zero value prints as zero ({ta} → {tb}).",
                    "Keep about three significant figures (1.3×10⁻⁷), as the figure does.",
                    panel=key,
                )
            ]
    return []


def _row_index(block: Sequence[str], label: str) -> int | None:
    pattern = re.compile(rf"^  [ ▸>] +{re.escape(label)}  ")
    return next((i for i, line in enumerate(block) if pattern.match(line)), None)


def _audit_ranked_rows(
    key: str, panel: Panel, block: Sequence[str], *, width: int
) -> list[dict[str, Any]]:
    values = panel.spec.get("parts") if panel.kind == "share" else panel.spec.get("values")
    if not isinstance(values, Mapping) or not values:
        return []
    if isinstance(next(iter(values.values())), Mapping):
        return []  # grouped compare prints a table in the given order
    expected = _ranked_items(panel)
    max_lbl = min(max(len(n) for n, _ in expected), max(12, width // 3))
    positions: list[int] = []
    for name, _ in expected:
        idx = None
        for cut in [max_lbl, *range(max_lbl - 1, 5, -1)]:  # dot rows may shorten labels
            idx = _row_index(block, _clip_label(name, cut, ascii_only=False))
            if idx is not None:
                break
        if idx is None:
            return [
                _issue(
                    "text_ranking",
                    "error",
                    f"Panel {key}: item {name!r} has no row in the text rendering.",
                    "Every item the figure draws needs one text row.",
                    panel=key,
                )
            ]
        positions.append(idx)
    if positions != sorted(positions):
        return [
            _issue(
                "text_ranking",
                "error",
                f"Panel {key}: text rows are not in the figure's order "
                f"({', '.join(n for n, _ in expected)}).",
                "Order text rows with the panel's sort= rule, as the figure does.",
                panel=key,
            )
        ]
    return []


def _audit_intervals(key: str, panel: Panel, block: Sequence[str]) -> list[dict[str, Any]]:
    values = panel.spec.get("values")
    if not isinstance(values, Mapping) or panel.spec.get("error") is None:
        return []
    items = [(str(k), float(v)) for k, v in values.items() if _is_num(v)]
    errors, _inner = _compare_errors(panel, dict(items))
    issues: list[dict[str, Any]] = []
    text = "\n".join(block)
    if errors is None:
        return issues
    if "█" in text or "▉" in text:
        issues.append(
            _issue(
                "text_interval_missing",
                "error",
                f"Panel {key} has intervals but its text rendering draws bars.",
                "Draw dot-and-whisker rows on one shared axis for compare(error=...).",
                panel=key,
            )
        )
    fmt_fn = _formatter(
        [v for _, v in items] + [b for pair in errors.values() for b in pair],
        panel.spec.get("fmt"),
        unit=panel.unit,
        log=bool(panel.spec.get("log")),
    )
    missing = [
        name
        for name, (lo_b, hi_b) in errors.items()
        if _range_with_unit(fmt_fn(lo_b), fmt_fn(hi_b), panel.unit) not in text
    ]
    if missing:
        issues.append(
            _issue(
                "text_interval_missing",
                "error",
                f"Panel {key}: the text omits the interval bounds of {missing[:4]!r}.",
                "Print each item's interval as numbers beside its value.",
                panel=key,
            )
        )
    label = panel.spec.get("error_label")
    if label and str(label) not in text:
        issues.append(
            _issue(
                "text_interval_missing",
                "error",
                f"Panel {key}: the text does not say what the intervals are ({label}).",
                "Print the interval label (error_label=) under the rows.",
                panel=key,
            )
        )
    return issues


_EIGHTHS = {ch: i for i, ch in enumerate(_UNICODE_BAR_BLOCKS) if i} | {"▐": 4}


def _audit_table(key: str, panel: Panel, block: Sequence[str], *, width: int) -> list[dict[str, Any]]:
    """In-cell graphics sit on one scale per column, and intervals keep bounds and label."""
    view = _table_view(panel)
    if view is None:
        return []
    top = next((i for i, line in enumerate(block) if line.startswith("┌")), None)
    if top is None:
        return []
    headers, g_ws, text_w = _table_text_layout(view, width)
    first = top + 3 + max(h.count("\n") for h in headers)
    issues: list[dict[str, Any]] = []
    text = "\n".join(block)

    def _scale_issue(col: str, what: str) -> dict[str, Any]:
        return _issue(
            "text_table_scale",
            "error",
            f"Panel {key}: the {what} in column {col!r} are not drawn on one scale.",
            "Draw every cell of a column against the column's shared range.",
            panel=key,
        )

    for c, g in view["graphics"].items():
        col = headers[c].replace("\n", " ")
        lo, hi, g_w = float(g["lo"]), float(g["hi"]), g_ws[c]
        bad = bounds_missing = False
        for r in range(len(view["cells"])):
            line = block[first + r] if first + r < len(block) else ""
            cells = line.split("│")[1:-1]
            if c >= len(cells):
                bad = True
                break
            body = cells[c][1:-1]
            art = body[text_w[c] + 1 : text_w[c] + 1 + g_w] if g["lead"] else body[:g_w]
            if g["kind"] == "bars":
                v = g["values"][r]
                if v is None or hi <= lo:
                    continue
                cells_w = g_w - (1 if lo < 0 else 0)
                drawn = sum(8 if ch == "█" else _EIGHTHS.get(ch, 0) for ch in art)
                bad = bad or abs(drawn - abs(v) / (hi - lo) * cells_w * 8) > 4
            elif g["kind"] == "interval":
                v = g["values"][r]
                if v is None or "●" not in art:
                    bad = bad or v is not None
                    continue
                want = (v - lo) / (hi - lo) * (g_w - 1) if hi > lo else (g_w - 1) / 2
                bad = bad or abs(art.index("●") - want) > 1
                bounds_text = g["bounds_text"][r]
                bounds_missing = bounds_missing or bool(bounds_text and bounds_text not in body)
            else:
                series = g["series"][r]
                if not series:
                    continue
                for ch, v in zip(art, _resample(list(series), g_w)):
                    if v is None or ch == " ":
                        continue
                    want = (v - lo) / (hi - lo) * (len(_UNICODE_SPARK) - 1) if hi > lo else 3.5
                    if ch not in _UNICODE_SPARK or abs(_UNICODE_SPARK.index(ch) - want) > 1:
                        bad = True
        if bad:
            what = {"bars": "bars", "interval": "intervals", "spark": "sparklines"}[g["kind"]]
            issues.append(_scale_issue(col, what))
        if bounds_missing:
            issues.append(
                _issue(
                    "text_interval_missing",
                    "error",
                    f"Panel {key}: the text omits the interval bounds in column {col!r}.",
                    "Print each cell's interval as numbers beside its value.",
                    panel=key,
                )
            )
        if g["kind"] == "interval" and g.get("label") and str(g["label"]) not in text:
            issues.append(
                _issue(
                    "text_interval_missing",
                    "error",
                    f"Panel {key}: the text does not say what the intervals are ({g['label']}).",
                    "Print the interval label (interval_label=) under the table.",
                    panel=key,
                )
            )
    return issues


_PCT_RE = re.compile(r"\(([+\-−]?[\d,]+)%\)")


def _audit_trend(
    key: str, panel: Panel, block: Sequence[str], text: str, *, width: int
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    series = _trend_series(panel)
    max_lbl = min(max((len(k) for k in series), default=1), max(12, width // 4))
    pct_unit = _is_pct(panel.unit)
    for name, vals in series.items():
        finite = [v for v in vals if v is not None]
        if not finite or (_relative_ok(finite[0], finite) and not pct_unit):
            continue
        row = _row_index(block, _clip_label(name, max_lbl, ascii_only=False))
        if row is None:
            continue
        summary = block[row]
        wrapped = block[row + 1] if row + 1 < len(block) else ""
        if wrapped.startswith(" " * (4 + max_lbl + 2)):  # the summary sits on its own line
            summary += wrapped
        if _PCT_RE.search(summary) and pct_unit:
            issues.append(
                _issue(
                    "text_percent_of_percent",
                    "error",
                    f"Panel {key}: {name!r} is in % but prints its change as a percent.",
                    "Print a change of percentages in points (+76 pts).",
                    panel=key,
                )
            )
        elif _PCT_RE.search(summary):
            issues.append(
                _issue(
                    "text_relative_from_zero",
                    "error",
                    f"Panel {key}: {name!r} prints a percent change from a start below "
                    f"{_MIN_RELATIVE_BASE:.0%} of its range.",
                    "Print the absolute change when the start is near zero.",
                    panel=key,
                )
            )
    if panel.spec.get("band") is not None and "band" not in text:
        issues.append(
            _issue(
                "text_interval_missing",
                "error",
                f"Panel {key} draws a band the text never mentions.",
                "Say the band is not shown and print its bounds.",
                panel=key,
            )
        )
    return issues


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
            if "mintfig:spec" in embedded:
                exp_or_spec = json.loads(embedded["mintfig:spec"])
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

    # Plain PNG with no embedded mintfig spec in text-only mode: return clean summary
    from PIL import Image

    assert png_bytes is not None
    with Image.open(io.BytesIO(png_bytes)) as img:
        img_w, img_h = img.size
    name = raw_png_path.name if raw_png_path else "image.png"
    msg = (
        f"{name} ({img_w}x{img_h} px PNG, no embedded mintfig spec for text rendering; "
        "use --mode kitty or --mode iterm2 for inline image display)"
    )
    return _to_ascii(msg) if ascii_only else msg
