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
import shutil
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
from .themes import Theme, contrast_ratio

__all__ = [
    "BrailleCanvas",
    "audit_text_surface",
    "detect_graphics_protocol",
    "encode_iterm2_png",
    "encode_kitty_png",
    "in_notebook",
    "render_terminal",
    "show_in_terminal",
    "wrap_tmux_passthrough",
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


def _ansi_bg_rgb(hex_color: str) -> str:
    r, g, b = (round(c * 255) for c in to_rgb(hex_color))
    return f"\x1b[48;2;{r};{g};{b}m"


def _blend_hex(hex_a: str, hex_b: str, weight_a: float) -> str:
    """Linearly blend two hex colors (``weight_a`` in ``[0, 1]`` for ``hex_a``)."""
    w = max(0.0, min(1.0, float(weight_a)))
    ra, ga, ba = to_rgb(hex_a)
    rb, gb, bb = to_rgb(hex_b)
    r = round((ra * w + rb * (1.0 - w)) * 255)
    g = round((ga * w + gb * (1.0 - w)) * 255)
    b = round((ba * w + bb * (1.0 - w)) * 255)
    return f"#{r:02X}{g:02X}{b:02X}"


def _interp_stops(stops: Sequence[str], t: float) -> str:
    """Interpolate a multi-stop hex color ramp at normalized position ``t`` in ``[0, 1]``."""
    if not stops:
        return "#1F5A9D"
    if len(stops) == 1:
        return stops[0]
    tc = max(0.0, min(1.0, float(t)))
    pos = tc * (len(stops) - 1)
    idx = min(len(stops) - 2, math.floor(pos))
    frac = pos - idx
    return _blend_hex(stops[idx + 1], stops[idx], frac)


def _wcag_fg(bg_hex: str) -> str:
    """Pick high-contrast black (``#111111``) or white (``#F8FAFC``) foreground text."""
    dark_cr = contrast_ratio("#111111", bg_hex)
    light_cr = contrast_ratio("#F8FAFC", bg_hex)
    return "#111111" if dark_cr >= light_cr else "#F8FAFC"


def _visible_len(text: str) -> int:
    """Visible terminal column width ignoring ANSI SGR escape sequences."""
    return len(_ANSI_RE.sub("", text))


def _pad_visible(text: str, target_width: int) -> str:
    """Pad or ANSI-safely clip ``text`` so its visible column width equals ``target_width``."""
    vlen = _visible_len(text)
    if vlen <= target_width:
        return text + " " * (target_width - vlen)
    if target_width <= 0:
        return ""
    out: list[str] = []
    vis = 0
    pos = 0
    has_ansi = False
    for match in _ANSI_RE.finditer(text):
        start, end = match.span()
        chunk = text[pos:start]
        if vis + len(chunk) >= target_width:
            out.append(chunk[: target_width - vis])
            vis = target_width
            break
        out.append(chunk)
        vis += len(chunk)
        out.append(match.group(0))
        has_ansi = True
        pos = end
    if vis < target_width and pos < len(text):
        out.append(text[pos : pos + (target_width - vis)])
    if has_ansi:
        out.append("\x1b[0m")
    return "".join(out)


def _resolve_width(width: int | str) -> int:
    """Resolve an integer width or ``"auto"`` (clamped to 56..132)."""
    if isinstance(width, str):
        token = width.strip().lower()
        if token == "auto":
            cols = shutil.get_terminal_size((80, 24)).columns
            return max(56, min(132, int(cols)))
        try:
            return max(40, int(token))
        except ValueError as exc:
            raise ValueError(
                f"width must be an integer or 'auto', got {width!r}."
            ) from exc
    return max(40, int(width))


def _resolve_color(color: bool | None, *, env: Mapping[str, str] | None = None) -> bool:
    """Resolve explicit ``color`` bool, or consult ``NO_COLOR``/``FORCE_COLOR`` when ``None``."""
    if color is not None:
        return bool(color)
    source = os.environ if env is None else env
    if source.get("NO_COLOR"):
        return False
    force = source.get("FORCE_COLOR")
    if force is not None and str(force).strip() != "":
        return str(force).strip().lower() not in {"0", "false", "no"}
    return True


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


def _all_entity_hex(exp: Explanation) -> dict[str, str]:
    """``{name: hex}`` from ``exp.entity_colors``, plus fallback palette colors for panel series."""
    out = _entity_hex(exp)
    colours = exp.theme.series_colors
    if not colours:
        return out
    used = set(out.values())
    spare = [c for c in colours if c not in used]
    for panel in exp.panels.values():
        spec = panel.spec
        names: list[str] = []
        if panel.kind == "trend":
            names = list(_trend_series(panel).keys())
        elif panel.kind == "distribution":
            grp = spec.get("groups")
            if isinstance(grp, Mapping):
                names = [str(k) for k in grp]
        elif panel.kind == "relate":
            grp = spec.get("groups")
            if isinstance(grp, Sequence) and not isinstance(grp, (str, bytes)):
                seen: set[str] = set()
                for g in grp:
                    sg = str(g)
                    if sg not in seen:
                        seen.add(sg)
                        names.append(sg)
        elif panel.kind == "change":
            before_m = spec.get("before")
            if isinstance(before_m, Mapping):
                hl_c = spec.get("highlight")
                if hl_c:
                    names = [str(h) for h in ([hl_c] if isinstance(hl_c, str) else hl_c)]
                else:
                    names = [str(k) for k in before_m]
        elif panel.kind == "forest":
            data_m = spec.get("data")
            if isinstance(data_m, Mapping):
                hl_f = spec.get("highlight")
                if hl_f:
                    names = [str(h) for h in ([hl_f] if isinstance(hl_f, str) else hl_f)]
        for nm in names:
            if nm and nm not in out:
                if spare:
                    out[nm] = spare.pop(0)
                else:
                    out[nm] = colours[len(out) % len(colours)]
    return out


def _colorize_entity_names(
    text: str,
    colors: Mapping[str, str],
    style: _Style,
    *,
    base_bold: bool = False,
) -> str:
    """Color matching entity names in ``text`` with their 24-bit ANSI RGB series colors."""
    if not style.enabled or not colors or not text:
        return style.bold(text) if base_bold else text
    valid_names = sorted((nm for nm in colors if nm.strip()), key=len, reverse=True)
    if not valid_names:
        return style.bold(text) if base_bold else text
    lookup = {nm.lower(): colors[nm] for nm in valid_names}
    pattern = re.compile(
        r"(?<!\w)(" + "|".join(re.escape(nm) for nm in valid_names) + r")(?!\w)",
        re.IGNORECASE,
    )
    if not pattern.search(text):
        return style.bold(text) if base_bold else text

    parts: list[str] = []
    pos = 0
    for match in pattern.finditer(text):
        start, end = match.span()
        if start > pos:
            seg = text[pos:start]
            parts.append(style.bold(seg) if base_bold else seg)
        hex_c = lookup.get(match.group(1).lower())
        parts.append(style.color(match.group(0), hex_c, bold=True))
        pos = end
    if pos < len(text):
        seg = text[pos:]
        parts.append(style.bold(seg) if base_bold else seg)
    return "".join(parts)


# --------------------------------------------------------------------------- #
# 2x4 Unicode Braille (U+2800..U+28FF) True-Color ANSI Canvas
# --------------------------------------------------------------------------- #

_BRAILLE_BASE = 0x2800
_BRAILLE_BITS: tuple[tuple[int, int], ...] = (
    (0x01, 0x08),  # dy = 0 (left, right)
    (0x02, 0x10),  # dy = 1
    (0x04, 0x20),  # dy = 2
    (0x40, 0x80),  # dy = 3
)


class BrailleCanvas:
    """Zero-dependency 2×4 sub-pixel Unicode Braille canvas with 24-bit ANSI cell colors.

    Each terminal character cell covers a 2 (horizontal) × 4 (vertical) grid of
    Braille dots (``⠀`` through ``⣿``), giving 8× the plotting resolution of standard
    block characters.
    """

    def __init__(self, width_chars: int, height_chars: int) -> None:
        if width_chars < 1 or height_chars < 1:
            raise ValueError(
                f"BrailleCanvas dimensions must be >= 1, got {width_chars}x{height_chars}."
            )
        self.width_chars = int(width_chars)
        self.height_chars = int(height_chars)
        self.px_width = self.width_chars * 2
        self.px_height = self.height_chars * 4
        self._bits: list[list[int]] = [[0] * self.width_chars for _ in range(self.height_chars)]
        self._colors: list[list[str | None]] = [
            [None] * self.width_chars for _ in range(self.height_chars)
        ]
        self._prio: list[list[int]] = [[-1] * self.width_chars for _ in range(self.height_chars)]

    def set_pixel(
        self,
        x: int,
        y: int,
        *,
        color: str | None = None,
        priority: int = 1,
    ) -> None:
        """Turn on sub-pixel ``(x, y)`` where ``(0, 0)`` is top-left."""
        ix, iy = int(x), int(y)
        if not (0 <= ix < self.px_width and 0 <= iy < self.px_height):
            return
        cx, dx = divmod(ix, 2)
        cy, dy = divmod(iy, 4)
        self._bits[cy][cx] |= _BRAILLE_BITS[dy][dx]
        if color is not None and priority >= self._prio[cy][cx]:
            self._colors[cy][cx] = color
            self._prio[cy][cx] = priority

    def draw_point(
        self,
        x: float,
        y: float,
        *,
        color: str | None = None,
        radius: int = 0,
        priority: int = 2,
    ) -> None:
        """Plot a sub-pixel point (or compact disc when ``radius >= 1``)."""
        cx, cy = round(x), round(y)
        if radius <= 0:
            self.set_pixel(cx, cy, color=color, priority=priority)
            return
        r2 = radius * radius
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy <= r2:
                    self.set_pixel(cx + dx, cy + dy, color=color, priority=priority)

    def draw_line(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        *,
        color: str | None = None,
        dashed: bool = False,
        dash_on: int = 3,
        dash_off: int = 2,
        priority: int = 1,
    ) -> None:
        """Draw a crisp integer Bresenham line between two sub-pixel coordinates."""
        ix0, iy0 = round(x0), round(y0)
        ix1, iy1 = round(x1), round(y1)
        dx = abs(ix1 - ix0)
        dy = -abs(iy1 - iy0)
        sx = 1 if ix0 < ix1 else -1
        sy = 1 if iy0 < iy1 else -1
        err = dx + dy
        period = max(1, dash_on + dash_off)
        step = 0
        while True:
            if not dashed or (step % period) < dash_on:
                self.set_pixel(ix0, iy0, color=color, priority=priority)
            if ix0 == ix1 and iy0 == iy1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                ix0 += sx
            if e2 <= dx:
                err += dx
                iy0 += sy
            step += 1

    def draw_step(
        self,
        xs: Sequence[float],
        ys: Sequence[float],
        *,
        color: str | None = None,
        where: str = "post",
        priority: int = 1,
    ) -> None:
        """Draw a step curve through ``(xs[i], ys[i])`` (ideal for ECDFs)."""
        n = min(len(xs), len(ys))
        if n == 0:
            return
        if n == 1:
            self.draw_point(xs[0], ys[0], color=color, priority=priority)
            return
        for i in range(n - 1):
            x0, y0 = xs[i], ys[i]
            x1, y1 = xs[i + 1], ys[i + 1]
            if where == "pre":
                self.draw_line(x0, y0, x0, y1, color=color, priority=priority)
                self.draw_line(x0, y1, x1, y1, color=color, priority=priority)
            else:
                self.draw_line(x0, y0, x1, y0, color=color, priority=priority)
                self.draw_line(x1, y0, x1, y1, color=color, priority=priority)

    def draw_hline(
        self,
        y: float,
        *,
        color: str | None = None,
        dashed: bool = True,
        priority: int = 0,
    ) -> None:
        """Draw a horizontal reference line across the canvas."""
        self.draw_line(
            0,
            y,
            self.px_width - 1,
            y,
            color=color,
            dashed=dashed,
            dash_on=2,
            dash_off=3,
            priority=priority,
        )

    def draw_vline(
        self,
        x: float,
        *,
        color: str | None = None,
        dashed: bool = True,
        priority: int = 0,
    ) -> None:
        """Draw a vertical reference line down the canvas."""
        self.draw_line(
            x,
            0,
            x,
            self.px_height - 1,
            color=color,
            dashed=dashed,
            dash_on=2,
            dash_off=3,
            priority=priority,
        )

    def draw_band(
        self,
        xs: Sequence[float],
        lo_ys: Sequence[float],
        hi_ys: Sequence[float],
        *,
        color: str | None = None,
        priority: int = 0,
    ) -> None:
        """Render a subtle stippled/dithered CI band between ``lo_ys`` and ``hi_ys``.

        Uses a staggered 25% Braille dot dither at ``priority=0`` so main series curves
        drawn at ``priority=1..3`` remain crisp and unobstructed on top.
        """
        n = min(len(xs), len(lo_ys), len(hi_ys))
        if n == 0:
            return

        def _fill_col(px: int, ya: float, yb: float) -> None:
            if not (0 <= px < self.px_width):
                return
            y_top = max(0, math.ceil(min(ya, yb)))
            y_bot = min(self.px_height - 1, math.floor(max(ya, yb)))
            if y_bot < y_top:
                return
            placed = False
            for py in range(y_top, y_bot + 1):
                if (px % 2 == 0 and py % 4 == 0) or (px % 2 == 1 and py % 4 == 2):
                    self.set_pixel(px, py, color=color, priority=priority)
                    placed = True
            # Keep narrow bands (< 3 px tall) softly visible on alternating columns
            if not placed and px % 2 == 0:
                self.set_pixel(px, y_top, color=color, priority=priority)
                if y_bot > y_top:
                    self.set_pixel(px, y_bot, color=color, priority=priority)

        # Group contiguous finite points so missing values leave clean breaks
        segments: list[list[tuple[float, float, float]]] = []
        curr: list[tuple[float, float, float]] = []
        for i in range(n):
            xv, lv, hv = xs[i], lo_ys[i], hi_ys[i]
            if _is_num(xv) and _is_num(lv) and _is_num(hv):
                curr.append((float(xv), float(lv), float(hv)))
            else:
                if curr:
                    segments.append(curr)
                    curr = []
        if curr:
            segments.append(curr)

        for seg in segments:
            if len(seg) == 1:
                _fill_col(round(seg[0][0]), seg[0][1], seg[0][2])
                continue
            for i in range(len(seg) - 1):
                x0, l0, h0 = seg[i]
                x1, l1, h1 = seg[i + 1]
                px0, px1 = round(x0), round(x1)
                if px0 == px1:
                    _fill_col(px0, min(l0, l1), max(h0, h1))
                    continue
                step = 1 if px1 >= px0 else -1
                denom = x1 - x0
                for px in range(px0, px1 + step, step):
                    t = max(0.0, min(1.0, (px - x0) / denom))
                    _fill_col(px, l0 + t * (l1 - l0), h0 + t * (h1 - h0))

    def draw_rect(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        *,
        color: str | None = None,
        fill: bool = True,
        priority: int = 1,
    ) -> None:
        """Draw a filled or outlined sub-pixel rectangle."""
        ix0, ix1 = sorted((round(x0), round(x1)))
        iy0, iy1 = sorted((round(y0), round(y1)))
        if fill:
            for py in range(max(0, iy0), min(self.px_height, iy1 + 1)):
                for px in range(max(0, ix0), min(self.px_width, ix1 + 1)):
                    self.set_pixel(px, py, color=color, priority=priority)
        else:
            self.draw_line(ix0, iy0, ix1, iy0, color=color, priority=priority)
            self.draw_line(ix0, iy1, ix1, iy1, color=color, priority=priority)
            self.draw_line(ix0, iy0, ix0, iy1, color=color, priority=priority)
            self.draw_line(ix1, iy0, ix1, iy1, color=color, priority=priority)

    def draw_diamond(
        self,
        cx: float,
        cy: float,
        rx: float,
        ry: float,
        *,
        color: str | None = None,
        fill: bool = True,
        priority: int = 2,
    ) -> None:
        """Draw a filled or outlined sub-pixel diamond centered at ``(cx, cy)``."""
        rx_f = max(0.5, float(rx))
        ry_f = max(0.5, float(ry))
        if not fill:
            self.draw_line(cx - rx_f, cy, cx, cy - ry_f, color=color, priority=priority)
            self.draw_line(cx, cy - ry_f, cx + rx_f, cy, color=color, priority=priority)
            self.draw_line(cx + rx_f, cy, cx, cy + ry_f, color=color, priority=priority)
            self.draw_line(cx, cy + ry_f, cx - rx_f, cy, color=color, priority=priority)
            return
        x_lo = max(0, math.floor(cx - rx_f))
        x_hi = min(self.px_width - 1, math.ceil(cx + rx_f))
        y_lo = max(0, math.floor(cy - ry_f))
        y_hi = min(self.px_height - 1, math.ceil(cy + ry_f))
        for py in range(y_lo, y_hi + 1):
            for px in range(x_lo, x_hi + 1):
                if abs(px - cx) / rx_f + abs(py - cy) / ry_f <= 1.0 + 1e-6:
                    self.set_pixel(px, py, color=color, priority=priority)

    def render(
        self,
        *,
        color: bool = True,
        default_color: str | None = None,
        blank_braille: bool = True,
    ) -> list[str]:
        """Render the canvas to character rows, batching adjacent cells of identical color."""
        rows: list[str] = []
        empty_ch = chr(_BRAILLE_BASE) if blank_braille else " "
        for cy in range(self.height_chars):
            bits_row = self._bits[cy]
            col_row = self._colors[cy]
            if not color:
                rows.append(
                    "".join(chr(_BRAILLE_BASE | b) if b else empty_ch for b in bits_row)
                )
                continue
            buf: list[str] = []
            active_c: str | None = None
            for b, cell_c in zip(bits_row, col_row, strict=True):
                ch = chr(_BRAILLE_BASE | b) if b else empty_ch
                eff_c = (cell_c or default_color) if b else None
                if eff_c != active_c:
                    if active_c is not None:
                        buf.append("\x1b[0m")
                    if eff_c is not None:
                        buf.append(_ansi_rgb(eff_c))
                    active_c = eff_c
                buf.append(ch)
            if active_c is not None:
                buf.append("\x1b[0m")
            rows.append("".join(buf))
        return rows


def detect_graphics_protocol(env: Mapping[str, str] | None = None) -> str:
    """Detect inline terminal graphics support from environment variables.

    Returns ``"kitty"`` (Kitty / Ghostty), ``"iterm2"`` (iTerm2 / WezTerm), or
    ``"unicode"`` (plain text fallback).
    """
    source = os.environ if env is None else env
    if source.get("KITTY_WINDOW_ID") or source.get("GHOSTTY_RESOURCES_DIR"):
        return "kitty"
    term = str(source.get("TERM", "")).lower()
    term_program = str(source.get("TERM_PROGRAM", "")).lower()
    if "kitty" in term or "ghostty" in term or term_program in {"kitty", "ghostty"}:
        return "kitty"
    lc_terminal = str(source.get("LC_TERMINAL", "")).lower()
    if (
        source.get("ITERM_SESSION_ID")
        or source.get("WEZTERM_EXECUTABLE")
        or source.get("WEZTERM_PANE")
        or term_program in {"iterm.app", "wezterm"}
        or lc_terminal == "iterm2"
    ):
        return "iterm2"
    return "unicode"


def wrap_tmux_passthrough(sequence: str) -> str:
    """Wrap an inline graphics escape sequence for ``tmux`` DCS passthrough.

    Doubles every inner ESC (``\\x1b`` -> ``\\x1b\\x1b``) and encloses the result in
    ``\\x1bPtmux;...\\x1b\\\\`` so outer terminals (Kitty, Ghostty, iTerm2, WezTerm)
    receive the sequence when ``tmux`` has ``allow-passthrough`` enabled.
    """
    if not sequence:
        return ""
    escaped = sequence.replace("\x1b", "\x1b\x1b")
    return f"\x1bPtmux;{escaped}\x1b\\"


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
        norm_mode = spec.get("normalize")
        show_counts = bool(spec.get("show_counts"))
        if cols_lbl and isinstance(vals, Sequence) and len(cols_lbl) <= 6 and len(vals) <= 8:
            raw_nums = [
                [float(v) if _is_num(v) else None for v in rv]
                for rv in vals
                if isinstance(rv, Sequence)
            ]
            col_totals = (
                [
                    sum(r[c] for r in raw_nums if c < len(r) and r[c] is not None)
                    for c in range(len(cols_lbl))
                ]
                if norm_mode == "col"
                else []
            )
            str_rows = []
            for r_idx, rv in enumerate(raw_nums):
                rl = rows_lbl[r_idx] if r_idx < len(rows_lbl) else f"r{r_idx + 1}"
                row_tot = sum(v for v in rv if v is not None) if norm_mode == "row" else 0.0
                cells: list[str] = []
                for c_idx, v in enumerate(rv):
                    if v is None:
                        cells.append("-" if ascii_only else "—")
                    elif norm_mode in {"row", "col"}:
                        denom = row_tot if norm_mode == "row" else (col_totals[c_idx] if c_idx < len(col_totals) else 0.0)
                        pct = (100.0 * v / denom) if denom > 0 else 0.0
                        cell_s = f"{pct:.0f}%"
                        if show_counts:
                            cell_s += f" ({_fmt_num(v, ascii_only=ascii_only)})"
                        cells.append(cell_s)
                    else:
                        cells.append(_fmt_num(v, ascii_only=ascii_only))
                str_rows.append([rl, *cells])
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
    elif panel.kind == "distribution" and panel.spec.get("mode") == "ecdf":
        groups_raw = panel.spec.get("groups")
        u = panel.unit
        if isinstance(groups_raw, Mapping):
            g_items = [(str(k), v) for k, v in groups_raw.items()]
        elif isinstance(groups_raw, Sequence) and not isinstance(groups_raw, (str, bytes)):
            g_items = [(panel.label or "values", groups_raw)]
        else:
            g_items = []
        ecdf_rows: list[list[str]] = []
        for gname, seq in g_items:
            if not isinstance(seq, Sequence) or isinstance(seq, (str, bytes)):
                continue
            nums = sorted(float(v) for v in seq if _is_num(v))
            if not nums:
                continue
            def _q(prob: float, arr: list[float] = nums) -> float:
                pos = prob * (len(arr) - 1)
                lo_i = math.floor(pos)
                hi_i = min(len(arr) - 1, lo_i + 1)
                return arr[lo_i] + (pos - lo_i) * (arr[hi_i] - arr[lo_i])
            ecdf_rows.append([
                gname,
                str(len(nums)),
                _with_unit(_fmt_num(_q(0.5), ascii_only=ascii_only), u),
                _with_unit(_fmt_num(_q(0.95), ascii_only=ascii_only), u),
                _with_unit(_fmt_num(_q(0.99), ascii_only=ascii_only), u),
            ])
        if ecdf_rows:
            lines.extend(
                _render_box_table(
                    ["Group", "n", "p50", "p95", "p99"],
                    ecdf_rows,
                    aligns=["left", "right", "right", "right", "right"],
                    width=width,
                    style=style,
                    ascii_only=ascii_only,
                )
            )
    elif panel.kind == "forest":
        spec = panel.spec
        data_map = spec.get("data")
        err_map = spec.get("error")
        if isinstance(data_map, Mapping) and isinstance(err_map, Mapping) and data_map:
            items = [(str(k), float(v)) for k, v in data_map.items() if _is_num(v)]
            try:
                order = _sort_order(spec.get("sort", True))
            except ExplainError:
                order = "desc"
            if order == "desc":
                items.sort(key=lambda kv: kv[1], reverse=True)
            elif order == "asc":
                items.sort(key=lambda kv: kv[1])
            log = bool(spec.get("log"))
            u = panel.unit
            ref = spec.get("reference")
            ref_v = (
                float(ref[0])
                if isinstance(ref, Sequence) and not isinstance(ref, str) and ref and _is_num(ref[0])
                else None
            )
            counts_map = spec.get("n") if isinstance(spec.get("n"), Mapping) else {}
            pooled_spec = spec.get("pooled") if isinstance(spec.get("pooled"), Mapping) else None

            def _tf_f(x: float) -> float:
                return math.log10(x) if log and x > 0 else x

            bounds_list: list[tuple[str, float, float, float, int | None, bool]] = []
            for nm, est in items:
                pair = err_map.get(nm)
                if isinstance(pair, Sequence) and len(pair) == 2 and _is_num(pair[0]) and _is_num(pair[1]):
                    lo_b, hi_b = float(pair[0]), float(pair[1])
                else:
                    lo_b = hi_b = est
                cnt = int(counts_map[nm]) if nm in counts_map and _is_num(counts_map[nm]) else None
                bounds_list.append((nm, est, lo_b, hi_b, cnt, False))
            if pooled_spec is not None and _is_num(pooled_spec.get("value")):
                p_lbl = str(pooled_spec.get("label") or "Pooled")
                p_est = float(pooled_spec["value"])
                p_lo = float(pooled_spec.get("lo", p_est))
                p_hi = float(pooled_spec.get("hi", p_est))
                p_n = int(pooled_spec["n"]) if _is_num(pooled_spec.get("n")) else None
                bounds_list.append((p_lbl, p_est, p_lo, p_hi, p_n, True))

            span_pts = [
                _tf_f(x)
                for _, est, lo_b, hi_b, _, _ in bounds_list
                for x in (est, lo_b, hi_b)
            ]
            if ref_v is not None:
                span_pts.append(_tf_f(ref_v))
            lo_ax, hi_ax = min(span_pts), max(span_pts)
            if hi_ax <= lo_ax:
                pad = abs(lo_ax) * 0.05 or 1.0
                lo_ax, hi_ax = lo_ax - pad, hi_ax + pad

            all_f_nums = [x for _, est, lo_b, hi_b, _, _ in bounds_list for x in (est, lo_b, hi_b)]
            fmt_fn = _formatter(all_f_nums, spec.get("fmt"), unit=u, log=log)
            signed_z = (not log) and ref_v == 0.0

            def _fe(v: float) -> str:
                s = fmt_fn(v)
                return _signed(s) if signed_z else s

            readouts = []
            for _nm, est, lo_b, hi_b, cnt, _is_p in bounds_list:
                txt = f"{_with_unit(_fe(est), u)} [{_fe(lo_b)}, {_fe(hi_b)}]"
                if cnt is not None:
                    txt += f" (n={cnt:,})"
                readouts.append(txt)

            max_lbl = min(max(len(r[0]) for r in bounds_list), max(12, width // 3))
            val_w = max(len(t) for t in readouts)
            track_w = max(10, width - (4 + max_lbl + 2 + 2 + val_w))

            def _col_f(x: float) -> int:
                pos = (_tf_f(x) - lo_ax) / (hi_ax - lo_ax) * (track_w - 1)
                return max(0, min(track_w - 1, round(pos)))

            if ascii_only:
                l_ch, r_ch, rule_ch, sq_ch, dia_ch, ref_ch = "|", "|", "-", "#", "*", ":"
            else:
                l_ch, r_ch, rule_ch, sq_ch, dia_ch, ref_ch = "├", "┤", "─", "■", "◆", "┊"

            hl_raw = spec.get("highlight") or []
            hl_set = {str(h) for h in ([hl_raw] if isinstance(hl_raw, str) else hl_raw)}
            marker_on = ">" if ascii_only else "▸"
            for (nm, est, lo_b, hi_b, _cnt, is_p), r_txt in zip(bounds_list, readouts, strict=True):
                if is_p:
                    lines.append(style.dim("    " + ("-" if ascii_only else "─") * min(width - 6, max_lbl + 2 + track_w + 2 + val_w)))
                cells = [" "] * track_w
                if ref_v is not None:
                    cells[_col_f(ref_v)] = ref_ch
                a, b = _col_f(lo_b), _col_f(hi_b)
                for c in range(a, b + 1):
                    cells[c] = rule_ch
                if b > a:
                    cells[a], cells[b] = l_ch, r_ch
                cells[_col_f(est)] = dia_ch if is_p else sq_ch
                track = "".join(cells)
                lbl = _clip_label(nm, max_lbl, ascii_only=ascii_only).rjust(max_lbl)
                if is_p or nm in hl_set:
                    mark = marker_on if nm in hl_set else " "
                    lines.append(f"  {style.accent(mark)} {style.bold(lbl)}  {style.bold(track)}  {style.bold(r_txt)}")
                else:
                    lines.append(f"    {lbl}  {style.primary(track)}  {r_txt}")
            err_lbl = spec.get("error_label") or "CI"
            meta = f"  intervals: {err_lbl}"
            if ref_v is not None:
                meta += f"; {ref_ch} null = {_with_unit(fmt_fn(ref_v), u)}"
            if log:
                meta += "; log scale"
            lines.append(style.dim(meta))
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


def _deoverlap_label_rows(targets: list[tuple[int, str]], n_rows: int) -> dict[int, str]:
    """Assign distinct terminal row indices in ``0..n_rows-1`` with minimal vertical shift."""
    if not targets or n_rows <= 0:
        return {}
    ordered = sorted(enumerate(targets), key=lambda it: (it[1][0], it[0]))
    placed: list[tuple[int, str]] = []
    for _, (desired, label) in ordered:
        row = max(0, min(n_rows - 1, desired))
        if placed and row <= placed[-1][0]:
            row = placed[-1][0] + 1
        placed.append((row, label))
    # Pull back up if the bottom overflowed n_rows - 1
    if placed[-1][0] >= n_rows:
        placed[-1] = (n_rows - 1, placed[-1][1])
        for i in range(len(placed) - 2, -1, -1):
            if placed[i][0] >= placed[i + 1][0]:
                placed[i] = (max(0, placed[i + 1][0] - 1), placed[i][1])
    out: dict[int, str] = {}
    for row, label in placed:
        if 0 <= row < n_rows and row not in out:
            out[row] = label
    return out


def _braille_frame(
    canvas: BrailleCanvas,
    *,
    y_ticks: Mapping[int, str],
    x_left: str,
    x_right: str,
    x_label: str | None,
    right_labels: Mapping[int, str],
    style: _Style,
    color: bool,
    default_color: str | None,
) -> list[str]:
    """Wrap a rendered ``BrailleCanvas`` with crisp y-ticks, x-axis rule, and right labels."""
    y_w = max((len(t) for t in y_ticks.values()), default=0)
    y_w = max(y_w, 4)
    rows = canvas.render(color=color, default_color=default_color)
    out: list[str] = []
    for r_idx, row_str in enumerate(rows):
        tick_txt = y_ticks.get(r_idx, "")
        gutter = tick_txt.rjust(y_w)
        axis_ch = "┤" if tick_txt else "│"
        rhs = f" {right_labels[r_idx]}" if r_idx in right_labels else ""
        out.append(f"  {style.dim(gutter)}{style.dim(axis_ch)}{row_str}{rhs}")
    # Bottom x-axis rule
    rule = "└" + "─" * canvas.width_chars
    out.append(f"  {' ' * y_w}{style.dim(rule)}")
    # X tick labels + optional centered x_label
    plot_w = canvas.width_chars
    xl = x_left[: max(1, plot_w // 2)]
    xr = x_right[: max(1, plot_w // 2)]
    gap = plot_w - len(xl) - len(xr)
    if x_label and gap >= len(x_label) + 4:
        left_pad = (gap - len(x_label)) // 2
        right_pad = gap - len(x_label) - left_pad
        x_row = f"{xl}{' ' * left_pad}{x_label}{' ' * right_pad}{xr}"
    else:
        x_row = f"{xl}{' ' * max(1, gap)}{xr}"
    out.append(f"  {' ' * (y_w + 1)}{style.dim(x_row)}")
    return out


def _render_trend_braille(
    panel: Panel,
    *,
    width: int,
    style: _Style,
    colors: Mapping[str, str],
    palette: Sequence[str],
    muted_hex: str,
    context_hex: str,
    bg_hex: str = "#0F1715",
) -> list[str]:
    """High-res 2×4 Braille trend chart with CI bands, events, reference line, and direct labels."""
    spec = panel.spec
    series_map = _trend_series(panel)
    if not series_map:
        return [f"  {fact}" for fact in panel.facts]

    log_y = bool(spec.get("log"))
    log_x = bool(spec.get("log_x"))
    x_raw = spec.get("x") or []
    max_len = max((len(v) for v in series_map.values()), default=0)
    if max_len < 2:
        return _render_trend_panel(
            panel, width=width, style=style, ascii_only=False, colors=colors, palette=palette
        )

    # Build numeric x coordinates
    x_is_num = len(x_raw) >= max_len and all(_is_num(x_raw[i]) for i in range(max_len))
    if x_is_num:
        xs_orig = [float(x_raw[i]) for i in range(max_len)]
        xs_coord = [math.log10(x) if log_x and x > 0 else x for x in xs_orig]
        x_left_lbl = _fmt_num(xs_orig[0])
        x_right_lbl = _fmt_num(xs_orig[-1])
    else:
        xs_coord = [float(i) for i in range(max_len)]
        x_left_lbl = str(x_raw[0]) if x_raw else "0"
        x_right_lbl = str(x_raw[min(len(x_raw) - 1, max_len - 1)]) if x_raw else str(max_len - 1)

    def _tf_y(v: float | None) -> float | None:
        if v is None:
            return None
        if log_y:
            return math.log10(v) if v > 0 else None
        return v

    # Optional confidence / uncertainty bands via trend(band=...)
    band_bounds: dict[str, tuple[list[float | None], list[float | None]]] = {}
    band_raw_bounds: dict[str, tuple[list[float | None], list[float | None]]] = {}
    if spec.get("band") is not None:
        from ._explain.trend import _trend_bands

        try:
            import numpy as np

            data_arr = {
                k: np.array(
                    [np.nan if v is None else v for v in vals] + [np.nan] * (max_len - len(vals))
                )
                for k, vals in series_map.items()
            }
            parsed_bounds, _bspec, _bmodes = _trend_bands(spec["band"], data_arr, max_len)
            for bname, (low_a, high_a) in parsed_bounds.items():
                raw_lo = [float(v) if math.isfinite(v) else None for v in low_a]
                raw_hi = [float(v) if math.isfinite(v) else None for v in high_a]
                band_raw_bounds[bname] = (raw_lo, raw_hi)
                band_bounds[bname] = ([_tf_y(v) for v in raw_lo], [_tf_y(v) for v in raw_hi])
        except (ExplainError, TypeError, ValueError):
            band_bounds = {}

    scaled = {nm: [_tf_y(v) for v in vals] for nm, vals in series_map.items()}
    all_y = [v for vals in scaled.values() for v in vals if v is not None]
    for lo_s, hi_s in band_bounds.values():
        all_y.extend(v for v in lo_s if v is not None)
        all_y.extend(v for v in hi_s if v is not None)

    ref = spec.get("reference")
    ref_v = (
        float(ref[0])
        if isinstance(ref, Sequence) and not isinstance(ref, str) and ref and _is_num(ref[0])
        else None
    )
    ref_y = _tf_y(ref_v) if ref_v is not None else None
    if ref_y is not None:
        all_y.append(ref_y)
    if not all_y:
        return [f"  {fact}" for fact in panel.facts]

    y_lo, y_hi = min(all_y), max(all_y)
    if y_hi <= y_lo:
        pad = abs(y_lo) * 0.1 or 1.0
        y_lo, y_hi = y_lo - pad, y_hi + pad
    else:
        pad = (y_hi - y_lo) * 0.06
        y_lo, y_hi = y_lo - pad, y_hi + pad
    x_lo, x_hi = min(xs_coord), max(xs_coord)
    if x_hi <= x_lo:
        x_hi = x_lo + 1.0

    # Resolve colors per series matching figure registry
    hl_raw = spec.get("highlight") or []
    hl_set = {str(h) for h in ([hl_raw] if isinstance(hl_raw, str) else hl_raw)}
    own = dict(colors)
    spare = [c for c in palette if c not in own.values()]
    series_hex: dict[str, str] = {}
    for nm in series_map:
        if nm in own:
            series_hex[nm] = own[nm]
        elif hl_set:
            series_hex[nm] = context_hex
        else:
            series_hex[nm] = spare.pop(0) if spare else (palette[0] if palette else "#1F5A9D")

    # Format end labels to reserve exact right-side space
    all_raw_y = [v for vals in series_map.values() for v in vals if v is not None]
    fmt_fn = _formatter(all_raw_y, spec.get("fmt"), unit=panel.unit, log=log_y)
    max_lbl_name = min(10 if width < 60 else 14, max(len(nm) for nm in series_map))
    end_val_strs: dict[str, str] = {}
    for nm, vals in series_map.items():
        finite = [v for v in vals if v is not None]
        end_val_strs[nm] = _with_unit(fmt_fn(finite[-1]), panel.unit) if finite else ""
    max_rhs_plain = max(
        len(f"● {_clip_label(nm, max_lbl_name, ascii_only=False)} {end_val_strs[nm]}")
        for nm in series_map
    )

    y_hi_raw = 10**y_hi if log_y else y_hi
    y_mid_raw = 10 ** ((y_lo + y_hi) / 2.0) if log_y else (y_lo + y_hi) / 2.0
    y_lo_raw = 10**y_lo if log_y else y_lo
    y_hi_lbl = fmt_fn(y_hi_raw)
    y_mid_lbl = fmt_fn(y_mid_raw)
    y_lo_lbl = fmt_fn(y_lo_raw)
    y_w = max(4, len(y_hi_lbl), len(y_mid_lbl), len(y_lo_lbl))

    # Layout canvas dimensions inside width
    height_chars = 9 if width >= 64 else 7
    plot_w = max(14, width - 2 - y_w - 1 - 1 - max_rhs_plain)
    canvas = BrailleCanvas(plot_w, height_chars)

    def _px(xv: float) -> float:
        return (xv - x_lo) / (x_hi - x_lo) * (canvas.px_width - 1)

    def _py(yv: float) -> float:
        return (1.0 - (yv - y_lo) / (y_hi - y_lo)) * (canvas.px_height - 1)

    # Subtle reference line (priority 0)
    if ref_y is not None:
        canvas.draw_hline(_py(ref_y), color=muted_hex, dashed=True, priority=0)

    # Vertical event markers (priority 0)
    events = spec.get("events")
    if isinstance(events, Mapping) and events:
        for ev_x in events:
            ex_coord: float | None = None
            if x_is_num:
                fv: float | None = None
                if _is_num(ev_x):
                    fv = float(ev_x)
                elif isinstance(ev_x, str):
                    try:
                        cand = float(ev_x)
                        if math.isfinite(cand):
                            fv = cand
                    except ValueError:
                        fv = None
                if fv is not None:
                    ex_coord = math.log10(fv) if log_x and fv > 0 else fv
            elif x_raw:
                for idx, xr_v in enumerate(x_raw):
                    if str(xr_v) == str(ev_x):
                        ex_coord = float(idx)
                        break
            if ex_coord is not None and x_lo <= ex_coord <= x_hi:
                canvas.draw_vline(_px(ex_coord), color=muted_hex, dashed=True, priority=0)

    # Draw stippled CI bands first (priority 0) so curves stay crisp on top
    draw_order = sorted(series_map.keys(), key=lambda nm: (1 if nm in hl_set else 0))
    drew_band = False
    for nm in draw_order:
        if nm not in band_bounds:
            continue
        lo_s, hi_s = band_bounds[nm]
        b_xs: list[float] = []
        b_lo: list[float] = []
        b_hi: list[float] = []
        for idx in range(min(len(xs_coord), len(lo_s), len(hi_s))):
            lv, hv = lo_s[idx], hi_s[idx]
            if lv is not None and hv is not None:
                b_xs.append(_px(xs_coord[idx]))
                b_lo.append(_py(lv))
                b_hi.append(_py(hv))
            else:
                b_xs.append(float("nan"))
                b_lo.append(float("nan"))
                b_hi.append(float("nan"))
        if any(math.isfinite(v) for v in b_xs):
            band_hex = _blend_hex(series_hex[nm], bg_hex, 0.50)
            canvas.draw_band(b_xs, b_lo, b_hi, color=band_hex, priority=0)
            drew_band = True

    # Draw context series first, then highlighted/foreground series on top
    label_targets: list[tuple[int, str]] = []
    for nm in draw_order:
        vals = scaled[nm]
        hex_c = series_hex[nm]
        is_hl = nm in hl_set
        prio = 3 if is_hl else (1 if hl_set else 2)
        pts: list[tuple[float, float]] = []
        for idx, yv in enumerate(vals):
            if yv is not None and idx < len(xs_coord):
                pts.append((_px(xs_coord[idx]), _py(yv)))
        for i in range(len(pts) - 1):
            canvas.draw_line(
                pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], color=hex_c, priority=prio
            )
        if pts:
            ex, ey = pts[-1]
            canvas.draw_point(ex, ey, color=hex_c, radius=1 if (is_hl or not hl_set) else 0, priority=prio + 1)
            row_idx = max(0, min(height_chars - 1, int(ey // 4)))
            short_nm = _clip_label(nm, max_lbl_name, ascii_only=False)
            dot = style.color("●", hex_c, bold=True)
            lbl_txt = style.color(f"{short_nm} {end_val_strs[nm]}", hex_c, bold=is_hl)
            label_targets.append((row_idx, f"{dot} {lbl_txt}"))

    right_labels = _deoverlap_label_rows(label_targets, height_chars)
    y_ticks = {0: y_hi_lbl, height_chars // 2: y_mid_lbl, height_chars - 1: y_lo_lbl}
    lines = _braille_frame(
        canvas,
        y_ticks=y_ticks,
        x_left=x_left_lbl,
        x_right=x_right_lbl,
        x_label=spec.get("x_label"),
        right_labels=right_labels,
        style=style,
        color=style.enabled,
        default_color=palette[0] if palette else None,
    )

    meta_bits: list[str] = []
    if ref_v is not None:
        ref_lbl = ref[1] if len(ref) > 1 and ref[1] else "reference"  # type: ignore[arg-type,index]
        meta_bits.append(f"┄ {ref_lbl}: {_with_unit(fmt_fn(ref_v), panel.unit)}")
    if drew_band:
        b_lbl = spec.get("band_label") or "CI band"
        meta_bits.append(f"░ {b_lbl}")
    if log_y:
        meta_bits.append("log y")
    if log_x:
        meta_bits.append("log x")
    if isinstance(events, Mapping) and events:
        meta_bits.append("Events: " + ", ".join(f"{k}: {v}" for k, v in events.items()))
    if meta_bits:
        for wline in textwrap.wrap(" | ".join(meta_bits), width=max(20, width - 2)):
            lines.append("  " + style.dim(wline))
    if not drew_band:
        band_note = _band_note(panel, series_map)
        if band_note:
            for wline in textwrap.wrap(band_note, width=max(20, width - 2)):
                lines.append("  " + style.dim(wline))
    return lines


def _render_ecdf_braille(
    panel: Panel,
    *,
    width: int,
    style: _Style,
    colors: Mapping[str, str],
    palette: Sequence[str],
    muted_hex: str,
) -> list[str]:
    """High-res 2×4 Braille step ECDF chart with dashed p50/p95 lines and colored end labels."""
    groups_raw = panel.spec.get("groups")
    if isinstance(groups_raw, Mapping):
        raw_items = [(str(k), v) for k, v in groups_raw.items()]
    elif isinstance(groups_raw, Sequence) and not isinstance(groups_raw, (str, bytes)):
        raw_items = [(panel.label or "values", groups_raw)]
    else:
        return []

    parsed: list[tuple[str, list[float]]] = []
    for nm, seq in raw_items:
        if isinstance(seq, Sequence) and not isinstance(seq, (str, bytes)):
            nums = sorted(float(v) for v in seq if _is_num(v))
            if nums:
                parsed.append((nm, nums))
    if not parsed:
        return []

    log_x = bool(panel.spec.get("log"))
    all_vals = [v for _, arr in parsed for v in arr]
    tf_vals = [math.log10(v) if log_x and v > 0 else v for v in all_vals]
    x_lo, x_hi = min(tf_vals), max(tf_vals)
    if x_hi <= x_lo:
        pad = abs(x_lo) * 0.1 or 1.0
        x_lo, x_hi = x_lo - pad, x_hi + pad

    fmt_fn = _formatter(all_vals, panel.spec.get("fmt"), unit=panel.unit, log=log_x)
    u = panel.unit

    def _q(arr: list[float], p: float) -> float:
        pos = p * (len(arr) - 1)
        lo_i = math.floor(pos)
        hi_i = min(len(arr) - 1, lo_i + 1)
        return arr[lo_i] + (pos - lo_i) * (arr[hi_i] - arr[lo_i])

    hl_raw = panel.spec.get("highlight") or []
    hl_set = {str(h) for h in ([hl_raw] if isinstance(hl_raw, str) else hl_raw)}
    own = dict(colors)
    spare = [c for c in palette if c not in own.values()]
    group_hex: dict[str, str] = {}
    for nm, _ in parsed:
        if nm in own:
            group_hex[nm] = own[nm]
        else:
            group_hex[nm] = spare.pop(0) if spare else (palette[0] if palette else "#1F5A9D")

    max_lbl_name = min(10 if width < 60 else 13, max(len(nm) for nm, _ in parsed))
    rhs_plain: dict[str, str] = {}
    for nm, arr in parsed:
        p50_s = _with_unit(fmt_fn(_q(arr, 0.50)), u)
        rhs_plain[nm] = f"● {_clip_label(nm, max_lbl_name, ascii_only=False)} p50={p50_s}"
    max_rhs = max(len(s) for s in rhs_plain.values())

    height_chars = 9 if width >= 54 else 7
    y_w = 4  # "100%", " p95", " p50", "  0%"
    plot_w = max(14, width - 2 - y_w - 1 - 1 - max_rhs)
    canvas = BrailleCanvas(plot_w, height_chars)

    def _px(v: float) -> float:
        tv = math.log10(v) if log_x and v > 0 else v
        return (tv - x_lo) / (x_hi - x_lo) * (canvas.px_width - 1)

    def _py(prob: float) -> float:
        return (1.0 - prob) * (canvas.px_height - 1)

    # Dashed p50 and p95 horizontal guide lines
    p95_y = _py(0.95)
    p50_y = _py(0.50)
    canvas.draw_hline(p95_y, color=muted_hex, dashed=True, priority=0)
    canvas.draw_hline(p50_y, color=muted_hex, dashed=True, priority=0)

    # Draw ECDF step curves
    label_targets: list[tuple[int, str]] = []
    for idx, (nm, arr) in enumerate(parsed):
        hex_c = group_hex[nm]
        is_hl = nm in hl_set
        prio = 3 if is_hl else 2
        n = len(arr)
        # Subsample cleanly if very large while keeping exact endpoints & quantiles
        xs_px = [_px(arr[0])]
        ys_px = [_py(0.0)]
        step = max(1, n // (canvas.px_width * 2))
        for i in range(0, n, step):
            xs_px.append(_px(arr[i]))
            ys_px.append(_py((i + 1) / n))
        if (n - 1) % step != 0:
            xs_px.append(_px(arr[-1]))
            ys_px.append(_py(1.0))
        canvas.draw_step(xs_px, ys_px, color=hex_c, where="post", priority=prio)
        # Mark p50 on the curve
        p50_v = _q(arr, 0.50)
        canvas.draw_point(_px(p50_v), p50_y, color=hex_c, radius=1, priority=prio + 1)
        desired_row = min(height_chars - 1, idx * 2)
        dot = style.color("●", hex_c, bold=True)
        txt = style.color(rhs_plain[nm][2:], hex_c, bold=is_hl)
        label_targets.append((desired_row, f"{dot} {txt}"))

    p95_row = max(0, min(height_chars - 1, int(p95_y // 4)))
    p50_row = max(0, min(height_chars - 1, int(p50_y // 4)))
    y_ticks: dict[int, str] = {height_chars - 1: "0%"}
    y_ticks[p50_row] = "p50"
    if p95_row != p50_row:
        y_ticks[p95_row] = "p95"
    else:
        y_ticks[0] = "100%"

    x_left_lbl = _with_unit(fmt_fn(10**x_lo if log_x else x_lo), u)
    x_right_lbl = _with_unit(fmt_fn(10**x_hi if log_x else x_hi), u)
    right_labels = _deoverlap_label_rows(label_targets, height_chars)
    lines = _braille_frame(
        canvas,
        y_ticks=y_ticks,
        x_left=x_left_lbl,
        x_right=x_right_lbl,
        x_label=panel.label,
        right_labels=right_labels,
        style=style,
        color=style.enabled,
        default_color=palette[0] if palette else None,
    )
    # Compact quantile summary line per group
    bits: list[str] = []
    for nm, arr in parsed:
        p50 = _with_unit(fmt_fn(_q(arr, 0.50)), u)
        p95 = _with_unit(fmt_fn(_q(arr, 0.95)), u)
        p99 = _with_unit(fmt_fn(_q(arr, 0.99)), u)
        hex_c = group_hex[nm]
        bits.append(f"{style.color(nm, hex_c, bold=True)} p50={p50} p95={p95} p99={p99} (n={len(arr)})")
    for b in bits:
        lines.append(f"  {b}")
    return lines


_PARETO_SIGNS: dict[str, tuple[int, int]] = {
    "upper-left": (-1, 1),
    "upper-right": (1, 1),
    "lower-left": (-1, -1),
    "lower-right": (1, -1),
}


def _pareto_frontier_indices(xs: Sequence[float], ys: Sequence[float], mode: str) -> list[int]:
    """Return non-dominated Pareto frontier indices sorted by ascending ``x``."""
    sx, sy = _PARETO_SIGNS[mode]
    n = min(len(xs), len(ys))
    keep: list[int] = []
    for i in range(n):
        dominated = False
        xi, yi = xs[i], ys[i]
        for j in range(n):
            if i == j:
                continue
            xj, yj = xs[j], ys[j]
            if (
                sx * xj >= sx * xi - 1e-12
                and sy * yj >= sy * yi - 1e-12
                and (sx * xj > sx * xi + 1e-12 or sy * yj > sy * yi + 1e-12)
            ):
                dominated = True
                break
        if not dominated:
            keep.append(i)
    keep.sort(key=lambda idx: (xs[idx], ys[idx]))
    return keep


def _render_relate_braille(
    panel: Panel,
    *,
    width: int,
    style: _Style,
    colors: Mapping[str, str],
    palette: Sequence[str],
    muted_hex: str,
    accent_hex: str,
) -> list[str]:
    """High-res 2×4 Braille scatter cloud with optional OLS regression fit and Pareto frontier."""
    spec = panel.spec
    xs_raw = spec.get("x") or []
    ys_raw = spec.get("y") or []
    groups_raw = spec.get("groups")
    names_raw = spec.get("names")
    log_x = bool(spec.get("log_x"))
    log_y = bool(spec.get("log_y"))

    pts: list[tuple[float, float, str | None, str | None]] = []
    n = min(len(xs_raw), len(ys_raw))
    for i in range(n):
        xv, yv = xs_raw[i], ys_raw[i]
        if not (_is_num(xv) and _is_num(yv)):
            continue
        fx, fy = float(xv), float(yv)
        if (log_x and fx <= 0) or (log_y and fy <= 0):
            continue
        grp = (
            str(groups_raw[i])
            if isinstance(groups_raw, Sequence)
            and not isinstance(groups_raw, (str, bytes))
            and i < len(groups_raw)
            and groups_raw[i] is not None
            else None
        )
        p_nm = (
            str(names_raw[i])
            if isinstance(names_raw, Sequence)
            and not isinstance(names_raw, (str, bytes))
            and i < len(names_raw)
            and names_raw[i] is not None
            else None
        )
        pts.append((fx, fy, grp, p_nm))
    if not pts:
        return []

    tx = [math.log10(x) if log_x else x for x, _, _, _ in pts]
    ty = [math.log10(y) if log_y else y for _, y, _, _ in pts]
    ref = spec.get("reference")
    ref_v = (
        float(ref[0])
        if isinstance(ref, Sequence) and not isinstance(ref, str) and ref and _is_num(ref[0])
        else None
    )
    ref_y = (math.log10(ref_v) if log_y and ref_v > 0 else ref_v) if ref_v is not None else None

    x_lo, x_hi = min(tx), max(tx)
    y_all = [*ty, *([ref_y] if ref_y is not None else [])]
    y_lo, y_hi = min(y_all), max(y_all)
    x_pad = (x_hi - x_lo) * 0.05 if x_hi > x_lo else (abs(x_lo) * 0.1 or 1.0)
    y_pad = (y_hi - y_lo) * 0.06 if y_hi > y_lo else (abs(y_lo) * 0.1 or 1.0)
    x_lo, x_hi = x_lo - x_pad, x_hi + x_pad
    y_lo, y_hi = y_lo - y_pad, y_hi + y_pad

    # Assign group colors
    group_order: list[str] = []
    for _, _, g, _ in pts:
        if g is not None and g not in group_order:
            group_order.append(g)
    own = dict(colors)
    spare = [c for c in palette if c not in own.values()]
    group_hex: dict[str, str] = {}
    for g in group_order:
        if g in own:
            group_hex[g] = own[g]
        else:
            group_hex[g] = spare.pop(0) if spare else (palette[0] if palette else "#1F5A9D")
    base_hex = palette[0] if palette else "#1F5A9D"

    fmt_y = _formatter([y for _, y, _, _ in pts], None, unit=panel.unit, log=log_y)
    fmt_x = _formatter([x for x, _, _, _ in pts], None, unit=spec.get("x_unit"), log=log_x)
    y_hi_lbl = fmt_y(10**y_hi if log_y else y_hi)
    y_mid_lbl = fmt_y(10 ** ((y_lo + y_hi) / 2.0) if log_y else (y_lo + y_hi) / 2.0)
    y_lo_lbl = fmt_y(10**y_lo if log_y else y_lo)
    y_w = max(4, len(y_hi_lbl), len(y_mid_lbl), len(y_lo_lbl))

    rhs_w = min(14 if width < 60 else 18, max((len(g) + 3 for g in group_order), default=0))
    height_chars = 9 if width >= 64 else 7
    plot_w = max(14, width - 2 - y_w - 1 - (rhs_w + 1 if rhs_w else 0))
    canvas = BrailleCanvas(plot_w, height_chars)

    def _px(xv: float) -> float:
        return (xv - x_lo) / (x_hi - x_lo) * (canvas.px_width - 1)

    def _py(yv: float) -> float:
        return (1.0 - (yv - y_lo) / (y_hi - y_lo)) * (canvas.px_height - 1)

    if ref_y is not None:
        canvas.draw_hline(_py(ref_y), color=muted_hex, dashed=True, priority=0)

    # Optional dashed OLS regression line
    r_val: float | None = None
    fit_opt = spec.get("fit")
    if len(tx) >= 3:
        mx = sum(tx) / len(tx)
        my = sum(ty) / len(ty)
        sxx = sum((a - mx) ** 2 for a in tx)
        syy = sum((b - my) ** 2 for b in ty)
        sxy = sum((a - mx) * (b - my) for a, b in zip(tx, ty, strict=True))
        if sxx > 0 and syy > 0:
            r_val = sxy / math.sqrt(sxx * syy)
        if sxx > 0 and fit_opt not in (False, "none"):
            slope = sxy / sxx
            intercept = my - slope * mx
            fx0, fx1 = min(tx), max(tx)
            fy0 = max(y_lo, min(y_hi, slope * fx0 + intercept))
            fy1 = max(y_lo, min(y_hi, slope * fx1 + intercept))
            fit_hex = accent_hex if not group_order else muted_hex
            canvas.draw_line(
                _px(fx0),
                _py(fy0),
                _px(fx1),
                _py(fy1),
                color=fit_hex,
                dashed=True,
                dash_on=3,
                dash_off=2,
                priority=1,
            )

    # Optional Pareto frontier staircase / envelope
    frontier_raw = spec.get("frontier")
    frontier_mode: str | None = None
    if frontier_raw is True:
        frontier_mode = "upper-left"
    elif isinstance(frontier_raw, str):
        cand = frontier_raw.strip().lower().replace("_", "-").replace(" ", "-")
        if cand in _PARETO_SIGNS:
            frontier_mode = cand
    frontier_idx: list[int] = []
    if frontier_mode is not None and pts:
        frontier_idx = _pareto_frontier_indices(tx, ty, frontier_mode)
        if len(frontier_idx) >= 2:
            step_where = "post" if frontier_mode in {"upper-left", "lower-left"} else "pre"
            canvas.draw_step(
                [_px(tx[i]) for i in frontier_idx],
                [_py(ty[i]) for i in frontier_idx],
                color=accent_hex,
                where=step_where,
                priority=2,
            )
        for i in frontier_idx:
            canvas.draw_point(_px(tx[i]), _py(ty[i]), color=accent_hex, radius=1, priority=3)

    # Plot scatter points
    pt_radius = 1 if len(pts) <= 25 else 0
    frontier_set = set(frontier_idx)
    for idx_p, (fx, fy, g) in enumerate(zip(tx, ty, (p[2] for p in pts), strict=True)):
        c_hex = group_hex[g] if g is not None else base_hex
        prio_p = 3 if idx_p in frontier_set else 2
        rad_p = 1 if idx_p in frontier_set else pt_radius
        canvas.draw_point(_px(fx), _py(fy), color=c_hex, radius=rad_p, priority=prio_p)

    right_labels: dict[int, str] = {}
    for idx, g in enumerate(group_order[:height_chars]):
        short_g = _clip_label(g, max(6, rhs_w - 2), ascii_only=False)
        right_labels[idx] = f"{style.color('●', group_hex[g], bold=True)} {style.color(short_g, group_hex[g])}"

    y_ticks = {0: y_hi_lbl, height_chars // 2: y_mid_lbl, height_chars - 1: y_lo_lbl}
    x_left_lbl = _with_unit(fmt_x(10**x_lo if log_x else x_lo), spec.get("x_unit"))
    x_right_lbl = _with_unit(fmt_x(10**x_hi if log_x else x_hi), spec.get("x_unit"))
    lines = _braille_frame(
        canvas,
        y_ticks=y_ticks,
        x_left=x_left_lbl,
        x_right=x_right_lbl,
        x_label=spec.get("x_label"),
        right_labels=right_labels,
        style=style,
        color=style.enabled,
        default_color=base_hex,
    )
    meta = [f"n = {len(pts)}"]
    if r_val is not None:
        meta.append(f"r = {r_val:+.2f}")
    if fit_opt not in (False, "none") and len(tx) >= 3:
        meta.append("┄ OLS fit")
    if frontier_idx:
        f_names = [pts[i][3] for i in frontier_idx if pts[i][3]]
        if f_names and len(f_names) <= 4:
            meta.append(f"─ Pareto frontier: {', '.join(f_names)}")
        else:
            meta.append(f"─ Pareto frontier ({len(frontier_idx)} pts)")
    if ref_v is not None:
        ref_lbl = ref[1] if len(ref) > 1 and ref[1] else "reference"  # type: ignore[arg-type,index]
        meta.append(f"┄ {ref_lbl}: {_with_unit(fmt_y(ref_v), panel.unit)}")
    for wline in textwrap.wrap(" | ".join(meta), width=max(20, width - 2)):
        lines.append("  " + style.dim(wline))
    return lines


def _render_histogram_braille(
    panel: Panel,
    *,
    width: int,
    style: _Style,
    colors: Mapping[str, str],
    palette: Sequence[str],
    muted_hex: str,
) -> list[str]:
    """High-res 2×4 Braille histogram / density distribution chart."""
    spec = panel.spec
    groups_raw = spec.get("groups")
    if isinstance(groups_raw, Mapping):
        # Skip nested faceted mappings gracefully
        if any(isinstance(v, Mapping) for v in groups_raw.values()):
            return []
        raw_items = [(str(k), v) for k, v in groups_raw.items()]
    elif isinstance(groups_raw, Sequence) and not isinstance(groups_raw, (str, bytes)):
        raw_items = [(panel.label or "values", groups_raw)]
    else:
        return []

    parsed: list[tuple[str, list[float]]] = []
    for nm, seq in raw_items:
        if isinstance(seq, Sequence) and not isinstance(seq, (str, bytes)):
            nums = [float(v) for v in seq if _is_num(v)]
            if nums:
                parsed.append((nm, nums))
    if not parsed:
        return []

    all_vals = [v for _, arr in parsed for v in arr]
    lo, hi = min(all_vals), max(all_vals)
    if hi <= lo:
        pad = abs(lo) * 0.1 or 1.0
        lo, hi = lo - pad, hi + pad

    own = dict(colors)
    spare = [c for c in palette if c not in own.values()]
    group_hex: dict[str, str] = {}
    for nm, _ in parsed:
        if nm in own:
            group_hex[nm] = own[nm]
        else:
            group_hex[nm] = spare.pop(0) if spare else (palette[0] if palette else "#1F5A9D")

    height_chars = 8 if width >= 64 else 6
    y_w = 5
    rhs_w = min(18, max((len(nm) + 3 for nm, _ in parsed), default=0)) if len(parsed) > 1 else 0
    plot_w = max(20, width - 2 - y_w - 1 - (rhs_w + 1 if rhs_w else 0))
    canvas = BrailleCanvas(plot_w, height_chars)

    raw_bins = spec.get("bins")
    if isinstance(raw_bins, int) and raw_bins >= 2:
        n_bins = min(raw_bins, canvas.px_width)
    else:
        n_bins = max(8, min(28, canvas.px_width // 3))

    span = hi - lo
    counts_by_group: list[tuple[str, list[int], float]] = []
    max_count = 1
    for nm, arr in parsed:
        bins = [0] * n_bins
        for v in arr:
            idx = int((v - lo) / span * n_bins)
            idx = max(0, min(n_bins - 1, idx))
            bins[idx] += 1
        max_count = max(max_count, max(bins))
        s_arr = sorted(arr)
        mid = len(s_arr) // 2
        med = s_arr[mid] if len(s_arr) % 2 else 0.5 * (s_arr[mid - 1] + s_arr[mid])
        counts_by_group.append((nm, bins, med))

    def _px_x(v: float) -> float:
        return (v - lo) / span * (canvas.px_width - 1)

    def _py_c(c: float) -> float:
        return (1.0 - c / max_count) * (canvas.px_height - 1)

    # Single series: dense filled vertical Braille bars; multi-group: crisp overlaid step curves
    if len(counts_by_group) == 1:
        nm, bins, med = counts_by_group[0]
        hex_c = group_hex[nm]
        canvas.draw_vline(_px_x(med), color=muted_hex, dashed=True, priority=0)
        for b_idx, cnt in enumerate(bins):
            if cnt <= 0:
                continue
            x0 = round(b_idx * canvas.px_width / n_bins)
            x1 = max(x0, round((b_idx + 1) * canvas.px_width / n_bins) - 1)
            y_top = round(_py_c(cnt))
            for px in range(x0, min(canvas.px_width, x1 + 1)):
                for py in range(y_top, canvas.px_height):
                    canvas.set_pixel(px, py, color=hex_c, priority=2)
    else:
        for nm, bins, med in counts_by_group:
            hex_c = group_hex[nm]
            canvas.draw_vline(_px_x(med), color=hex_c, dashed=True, priority=0)
            xs_step: list[float] = []
            ys_step: list[float] = []
            for b_idx, cnt in enumerate(bins):
                bx = (b_idx + 0.5) / n_bins * (canvas.px_width - 1)
                xs_step.append(bx)
                ys_step.append(_py_c(cnt))
            canvas.draw_step(xs_step, ys_step, color=hex_c, where="post", priority=2)

    fmt_x = _formatter(all_vals, spec.get("fmt"), unit=panel.unit)
    u = panel.unit
    y_ticks = {0: str(max_count), height_chars // 2: str(max_count // 2), height_chars - 1: "0"}
    right_labels: dict[int, str] = {}
    if len(counts_by_group) > 1:
        for idx, (nm, _, _) in enumerate(counts_by_group[:height_chars]):
            short_nm = _clip_label(nm, max(6, rhs_w - 2), ascii_only=False)
            right_labels[idx] = f"{style.color('●', group_hex[nm], bold=True)} {style.color(short_nm, group_hex[nm])}"

    lines = _braille_frame(
        canvas,
        y_ticks=y_ticks,
        x_left=_with_unit(fmt_x(lo), u),
        x_right=_with_unit(fmt_x(hi), u),
        x_label=panel.label,
        right_labels=right_labels,
        style=style,
        color=style.enabled,
        default_color=palette[0] if palette else None,
    )
    med_bits = [
        f"{style.color(nm, group_hex[nm], bold=True)} median={_with_unit(fmt_x(med), u)} (n={len(arr)})"
        for (nm, _, med), (_, arr) in zip(counts_by_group, parsed, strict=True)
    ]
    lines.append("  " + "  ".join(med_bits))
    return lines


def _render_swarm_braille(
    panel: Panel,
    *,
    width: int,
    style: _Style,
    colors: Mapping[str, str],
    palette: Sequence[str],
    muted_hex: str,
    context_hex: str,
    ink_hex: str = "#E8F1EE",
) -> list[str]:
    """High-res 2×4 Braille beeswarm with horizontal lanes, median bar, IQR whisker, and tabular readout."""
    spec = panel.spec
    groups_raw = spec.get("groups")
    if isinstance(groups_raw, Mapping):
        if any(isinstance(v, Mapping) for v in groups_raw.values()):
            return []
        raw_items = [(str(k), v) for k, v in groups_raw.items()]
    elif isinstance(groups_raw, Sequence) and not isinstance(groups_raw, (str, bytes)):
        raw_items = [(panel.label or "values", groups_raw)]
    else:
        return []

    log = bool(spec.get("log"))
    stat = str(spec.get("stat") or "median")
    mode = str(spec.get("mode") or "dots")

    parsed: list[tuple[str, list[float]]] = []
    for nm, seq in raw_items:
        if isinstance(seq, Sequence) and not isinstance(seq, (str, bytes)):
            nums = [float(v) for v in seq if _is_num(v) and (not log or float(v) > 0)]
            if nums:
                parsed.append((nm, sorted(nums)))
    if not parsed:
        return []

    def _tf(v: float) -> float:
        return math.log10(v) if log and v > 0 else v

    def _q(arr: list[float], p: float) -> float:
        pos = p * (len(arr) - 1)
        lo_i = math.floor(pos)
        hi_i = min(len(arr) - 1, lo_i + 1)
        return arr[lo_i] + (pos - lo_i) * (arr[hi_i] - arr[lo_i])

    ref = spec.get("reference")
    ref_v = (
        float(ref[0])
        if isinstance(ref, Sequence) and not isinstance(ref, str) and ref and _is_num(ref[0])
        else None
    )
    ref_tf = _tf(ref_v) if (ref_v is not None and (not log or ref_v > 0)) else None

    all_vals = [v for _, arr in parsed for v in arr]
    tf_all = [_tf(v) for v in all_vals]
    if ref_tf is not None:
        tf_all.append(ref_tf)
    x_lo, x_hi = min(tf_all), max(tf_all)
    if x_hi <= x_lo:
        pad = abs(x_lo) * 0.1 or 1.0
        x_lo, x_hi = x_lo - pad, x_hi + pad
    else:
        pad = (x_hi - x_lo) * 0.04
        x_lo, x_hi = x_lo - pad, x_hi + pad

    hl_raw = spec.get("highlight") or []
    hl_set = {str(h) for h in ([hl_raw] if isinstance(hl_raw, str) else hl_raw)}
    own = dict(colors)
    spare = [c for c in palette if c not in own.values()]
    group_hex: dict[str, str] = {}
    for nm, _ in parsed:
        if nm in own:
            group_hex[nm] = own[nm]
        elif hl_set:
            group_hex[nm] = context_hex
        else:
            group_hex[nm] = spare.pop(0) if spare else (palette[0] if palette else "#1F5A9D")

    fmt_x = _formatter(all_vals, spec.get("fmt"), unit=panel.unit, log=log)
    u = panel.unit

    # Per-group summary stats and tabular readouts
    stats: list[tuple[str, list[float], float, float, float, str]] = []
    for nm, arr in parsed:
        if stat == "mean":
            center_v = sum(arr) / len(arr)
            var = sum((v - center_v) ** 2 for v in arr) / max(1, len(arr) - 1) if len(arr) > 1 else 0.0
            sd = math.sqrt(var)
            lo_s = max(arr[0], center_v - sd) if log else center_v - sd
            hi_s = center_v + sd
        else:
            center_v = _q(arr, 0.50)
            lo_s = _q(arr, 0.25)
            hi_s = _q(arr, 0.75)
        readout = _with_unit(fmt_x(center_v), u)
        stats.append((nm, arr, center_v, lo_s, hi_s, readout))

    lbl_w = min(10 if width < 60 else 14, max(len(nm) for nm, _ in parsed))
    val_w = max(len(r[5]) for r in stats)
    plot_w = max(14, width - (2 + lbl_w + 1) - (1 + val_w))

    lane_h = 3 if len(parsed) <= 4 else 2
    total_h = lane_h * len(parsed)
    canvas = BrailleCanvas(plot_w, total_h)

    def _px(v: float) -> float:
        return (_tf(v) - x_lo) / (x_hi - x_lo) * (canvas.px_width - 1)

    if ref_tf is not None:
        canvas.draw_vline(
            (ref_tf - x_lo) / (x_hi - x_lo) * (canvas.px_width - 1),
            color=muted_hex,
            dashed=True,
            priority=0,
        )

    for g_idx, (nm, arr, center_v, lo_s, hi_s, _readout) in enumerate(stats):
        hex_c = group_hex[nm]
        is_hl = nm in hl_set
        y_top_lane = g_idx * lane_h * 4
        lane_px = lane_h * 4
        cy_i = y_top_lane + lane_px // 2
        max_dy = max(1, lane_px // 2 - 1)

        # Sample points for quantile dotplot or cap ultra-dense clouds for crispness
        if mode == "quantile":
            n_q = int(spec.get("quantiles") or 20)
            pts_vals = [_q(arr, (i + 0.5) / n_q) for i in range(n_q)]
        elif len(arr) > 220:
            pts_vals = [_q(arr, i / 199.0) for i in range(200)]
        else:
            pts_vals = arr

        # Deterministic symmetric sub-pixel beeswarm packing
        occupied: set[tuple[int, int]] = set()
        balance = 0
        for v in pts_vals:
            x_px = max(0, min(canvas.px_width - 1, round(_px(v))))
            placed = False
            # Try offsets 0, ±1, ±2, ... favoring the side that keeps vertical balance
            sign_first = 1 if balance <= 0 else -1
            offsets = [0]
            for d in range(1, max_dy + 1):
                offsets.append(sign_first * d)
                offsets.append(-sign_first * d)
            for dy in offsets:
                py = cy_i + dy
                if y_top_lane <= py < y_top_lane + lane_px and (x_px, py) not in occupied:
                    occupied.add((x_px, py))
                    canvas.set_pixel(x_px, py, color=hex_c, priority=1)
                    balance += 1 if dy > 0 else (-1 if dy < 0 else 0)
                    placed = True
                    break
            if not placed:
                py = max(y_top_lane, min(y_top_lane + lane_px - 1, cy_i + sign_first * max_dy))
                canvas.set_pixel(x_px, py, color=hex_c, priority=1)

        # Horizontal IQR / ±1 SD whisker + vertical end ticks
        whisker_c = ink_hex if is_hl else hex_c
        x_lo_s = _px(lo_s)
        x_hi_s = _px(hi_s)
        canvas.draw_line(x_lo_s, cy_i, x_hi_s, cy_i, color=whisker_c, priority=2)
        canvas.draw_line(x_lo_s, cy_i - 1, x_lo_s, cy_i + 1, color=whisker_c, priority=2)
        canvas.draw_line(x_hi_s, cy_i - 1, x_hi_s, cy_i + 1, color=whisker_c, priority=2)

        # Bold vertical median / mean summary bar
        med_x = _px(center_v)
        bar_c = ink_hex if style.enabled else hex_c
        canvas.draw_rect(med_x - 1, cy_i - 2, med_x, cy_i + 2, color=bar_c, fill=True, priority=3)

    rows = canvas.render(color=style.enabled, default_color=palette[0] if palette else None)
    lines: list[str] = []
    for g_idx, (nm, _arr, _c, _lo, _hi, readout) in enumerate(stats):
        hex_c = group_hex[nm]
        is_hl = nm in hl_set
        r0 = g_idx * lane_h
        r_mid = r0 + lane_h // 2
        short_nm = _clip_label(nm, lbl_w, ascii_only=False).rjust(lbl_w)
        r_val = readout.rjust(val_w)
        for r in range(r0, r0 + lane_h):
            if r == r_mid:
                lbl_s = style.color(short_nm, hex_c, bold=is_hl)
                axis_ch = style.dim("┤")
                val_s = style.color(r_val, hex_c, bold=is_hl) if is_hl else style.bold(r_val)
            else:
                lbl_s = " " * lbl_w
                axis_ch = style.dim("│")
                val_s = ""
            rhs = f" {val_s}" if val_s else ""
            lines.append(f"  {lbl_s}{axis_ch}{rows[r]}{rhs}")

    # Bottom x-axis rule & ticks
    rule = "└" + "─" * plot_w
    lines.append(f"  {' ' * lbl_w}{style.dim(rule)}")
    x_left_lbl = _with_unit(fmt_x(10**x_lo if log else x_lo), u)
    x_right_lbl = _with_unit(fmt_x(10**x_hi if log else x_hi), u)
    xl = x_left_lbl[: max(1, plot_w // 2)]
    xr = x_right_lbl[: max(1, plot_w // 2)]
    gap = plot_w - len(xl) - len(xr)
    x_lbl_txt = panel.label
    if x_lbl_txt and gap >= len(x_lbl_txt) + 4:
        lp = (gap - len(x_lbl_txt)) // 2
        rp = gap - len(x_lbl_txt) - lp
        x_row = f"{xl}{' ' * lp}{x_lbl_txt}{' ' * rp}{xr}"
    else:
        x_row = f"{xl}{' ' * max(1, gap)}{xr}"
    lines.append(f"  {' ' * (lbl_w + 1)}{style.dim(x_row)}")

    meta_bits = ["┃ mean  ─ ±1 sd" if stat == "mean" else "┃ median  ─ IQR"]
    if ref_v is not None:
        ref_lbl = ref[1] if len(ref) > 1 and ref[1] else "reference"  # type: ignore[arg-type,index]
        meta_bits.append(f"┄ {ref_lbl}: {_with_unit(fmt_x(ref_v), u)}")
    if log:
        meta_bits.append("log scale")
    lines.append("  " + style.dim(" | ".join(meta_bits)))
    return lines


def _render_change_braille(
    panel: Panel,
    *,
    width: int,
    style: _Style,
    colors: Mapping[str, str],
    palette: Sequence[str],
    muted_hex: str,
    context_hex: str,
    accent_hex: str,
) -> list[str]:
    """High-res 2×4 Braille paired slopegraph connecting Before → After with inline deltas."""
    spec = panel.spec
    before = spec.get("before") or {}
    after = spec.get("after") or {}
    if not isinstance(before, Mapping) or not isinstance(after, Mapping) or not before:
        return []

    items: list[tuple[str, float, float]] = []
    for k, bv in before.items():
        av = after.get(k)
        if _is_num(bv) and _is_num(av):
            items.append((str(k), float(bv), float(av)))
    if not items:
        return []
    items.sort(key=lambda it: it[2], reverse=True)

    u = panel.unit
    all_vals = [v for _, bv, av in items for v in (bv, av)]
    fmt_fn = _formatter(all_vals, spec.get("fmt"), unit=u)
    lo, hi = min(all_vals), max(all_vals)
    span = (hi - lo) or abs(hi) or 1.0
    pad = span * 0.08
    y_lo, y_hi = lo - pad, hi + pad

    hl_raw = spec.get("highlight") or []
    hl_set = {str(h) for h in ([hl_raw] if isinstance(hl_raw, str) else hl_raw)}
    own = dict(colors)
    up_hex = palette[0] if palette else "#0F8B6D"
    down_hex = palette[1] if len(palette) > 1 else accent_hex

    item_hex: dict[str, str] = {}
    for nm, bv, av in items:
        if nm in own:
            item_hex[nm] = own[nm]
        elif hl_set:
            item_hex[nm] = accent_hex if nm in hl_set else context_hex
        elif av > bv:
            item_hex[nm] = up_hex
        elif av < bv:
            item_hex[nm] = down_hex
        else:
            item_hex[nm] = muted_hex

    labels_raw = spec.get("labels") or ("Before", "After")
    left_hdr = str(labels_raw[0]) if len(labels_raw) >= 1 else "Before"
    right_hdr = str(labels_raw[1]) if len(labels_raw) >= 2 else "After"

    prefix_unit = bool(u and u.strip().startswith(("$", "€", "£")))
    left_plain: dict[str, str] = {}
    right_plain: dict[str, str] = {}
    max_name_len = min(10 if width < 60 else 14, max(len(nm) for nm, _, _ in items))
    for nm, bv, av in items:
        b_s = fmt_fn(bv)
        a_s = fmt_fn(av)
        left_plain[nm] = _with_unit(b_s, u)
        delta = av - bv
        if not _is_pct(u) and bv != 0 and abs(bv) >= _MIN_RELATIVE_BASE * span:
            pct = delta / abs(bv) * 100.0
            d_txt = f"+{pct:.0f}%" if pct > 0 else (f"−{abs(pct):.0f}%" if pct < 0 else "0%")
        else:
            d_txt = _delta_text(delta, u, ascii_only=False)
        short_nm = _clip_label(nm, max_name_len, ascii_only=False)
        if width >= 58:
            if u and not prefix_unit:
                pair_txt = f"{b_s} → {_with_unit(a_s, u)}"
            else:
                pair_txt = f"{_with_unit(b_s, u)} → {_with_unit(a_s, u)}"
            right_plain[nm] = f"{short_nm} {pair_txt} ({d_txt})"
        else:
            right_plain[nm] = f"{short_nm} {_with_unit(a_s, u)} ({d_txt})"

    left_w = max(len(left_hdr), *(len(s) for s in left_plain.values()))
    right_w = max(len(right_hdr), *(len(s) for s in right_plain.values()))
    plot_w = max(12, min(32, width - 2 - left_w - 1 - 1 - right_w))
    height_chars = max(7, min(12, len(items) * 2 + 1))
    canvas = BrailleCanvas(plot_w, height_chars)

    def _py(yv: float) -> float:
        return (1.0 - (yv - y_lo) / (y_hi - y_lo)) * (canvas.px_height - 1)

    # Subtle vertical Before / After rails
    canvas.draw_vline(0, color=muted_hex, dashed=True, priority=0)
    canvas.draw_vline(canvas.px_width - 1, color=muted_hex, dashed=True, priority=0)

    # Draw context lines first, highlighted/focus lines on top
    draw_order = sorted(items, key=lambda it: (1 if it[0] in hl_set else 0))
    left_targets: list[tuple[int, str]] = []
    right_targets: list[tuple[int, str]] = []
    for nm, bv, av in draw_order:
        hex_c = item_hex[nm]
        is_hl = nm in hl_set
        prio = 3 if is_hl else (1 if hl_set else 2)
        y0 = _py(bv)
        y1 = _py(av)
        canvas.draw_line(1, y0, canvas.px_width - 2, y1, color=hex_c, priority=prio)
        canvas.draw_point(1, y0, color=hex_c, radius=1 if (is_hl or not hl_set) else 0, priority=prio + 1)
        canvas.draw_point(
            canvas.px_width - 2,
            y1,
            color=hex_c,
            radius=1 if (is_hl or not hl_set) else 0,
            priority=prio + 1,
        )
        r_l = max(0, min(height_chars - 1, int(y0 // 4)))
        r_r = max(0, min(height_chars - 1, int(y1 // 4)))
        l_txt = left_plain[nm].rjust(left_w)
        left_targets.append((r_l, style.color(l_txt, hex_c, bold=is_hl) if is_hl else style.dim(l_txt)))
        right_targets.append((r_r, style.color(right_plain[nm], hex_c, bold=is_hl)))

    left_labels = _deoverlap_label_rows(left_targets, height_chars)
    right_labels = _deoverlap_label_rows(right_targets, height_chars)
    rows = canvas.render(color=style.enabled, default_color=up_hex)

    lines: list[str] = []
    hdr_l = style.dim(left_hdr.rjust(left_w))
    hdr_r = style.bold(right_hdr)
    lines.append(f"  {hdr_l} {' ' * plot_w} {hdr_r}")
    for r_idx, row_str in enumerate(rows):
        lhs = left_labels.get(r_idx, " " * left_w)
        rhs = f" {right_labels[r_idx]}" if r_idx in right_labels else ""
        lines.append(f"  {lhs} {row_str}{rhs}")
    return lines


def _render_forest_braille(
    panel: Panel,
    *,
    width: int,
    style: _Style,
    colors: Mapping[str, str],
    palette: Sequence[str],
    muted_hex: str,
    context_hex: str,
    accent_hex: str,
) -> list[str]:
    """High-res Braille forest plot with null reference line, CI whiskers, pooled diamond, and aligned readouts."""
    spec = panel.spec
    data_map = spec.get("data")
    err_map = spec.get("error")
    if not isinstance(data_map, Mapping) or err_map is None or not data_map:
        return []

    items = [(str(k), float(v)) for k, v in data_map.items() if _is_num(v)]
    if not items:
        return []
    try:
        order = _sort_order(spec.get("sort", True))
    except ExplainError:
        order = "desc"
    if order == "desc":
        items.sort(key=lambda kv: kv[1], reverse=True)
    elif order == "asc":
        items.sort(key=lambda kv: kv[1])

    # Parse intervals robustly via _compare_intervals (handles tuples and half-widths)
    try:
        intervals, _ = _compare_intervals(err_map, dict(items))
    except (ExplainError, KeyError, TypeError, ValueError):
        intervals = {}
        if isinstance(err_map, Mapping):
            for nm, est in items:
                pair = err_map.get(nm)
                if isinstance(pair, Sequence) and len(pair) == 2 and _is_num(pair[0]) and _is_num(pair[1]):
                    intervals[nm] = (float(pair[0]), float(pair[1]))
                else:
                    intervals[nm] = (est, est)

    log = bool(spec.get("log"))
    u = panel.unit
    ref = spec.get("reference")
    ref_v = (
        float(ref[0])
        if isinstance(ref, Sequence) and not isinstance(ref, str) and ref and _is_num(ref[0])
        else (float(ref) if _is_num(ref) else None)
    )
    counts_map = spec.get("n") if isinstance(spec.get("n"), Mapping) else {}
    pooled_spec = spec.get("pooled") if isinstance(spec.get("pooled"), Mapping) else None

    def _tf(x: float) -> float:
        return math.log10(x) if log and x > 0 else x

    rows_data: list[tuple[str, float, float, float, int | None, bool]] = []
    for nm, est in items:
        lo_b, hi_b = intervals.get(nm, (est, est))
        cnt = int(counts_map[nm]) if nm in counts_map and _is_num(counts_map[nm]) else None
        rows_data.append((nm, est, lo_b, hi_b, cnt, False))
    if pooled_spec is not None and _is_num(pooled_spec.get("value")):
        p_lbl = str(pooled_spec.get("label") or "Pooled")
        p_est = float(pooled_spec["value"])
        p_lo = float(pooled_spec.get("lo", p_est))
        p_hi = float(pooled_spec.get("hi", p_est))
        p_n = int(pooled_spec["n"]) if _is_num(pooled_spec.get("n")) else None
        rows_data.append((p_lbl, p_est, p_lo, p_hi, p_n, True))

    span_pts = [_tf(x) for _, est, lo_b, hi_b, _, _ in rows_data for x in (est, lo_b, hi_b)]
    if ref_v is not None and (not log or ref_v > 0):
        span_pts.append(_tf(ref_v))
    lo_ax, hi_ax = min(span_pts), max(span_pts)
    if hi_ax <= lo_ax:
        pad = abs(lo_ax) * 0.1 or 1.0
        lo_ax, hi_ax = lo_ax - pad, hi_ax + pad
    else:
        pad = (hi_ax - lo_ax) * 0.06
        lo_ax, hi_ax = lo_ax - pad, hi_ax + pad

    all_nums = [x for _, est, lo_b, hi_b, _, _ in rows_data for x in (est, lo_b, hi_b)]
    fmt_fn = _formatter(all_nums, spec.get("fmt"), unit=u, log=log)
    signed_z = (not log) and ref_v == 0.0

    def _fe(v: float) -> str:
        s = fmt_fn(v)
        return _signed(s) if signed_z else s

    est_strs: list[str] = []
    n_strs: list[str] = []
    has_n = any(r[4] is not None for r in rows_data)
    for _nm, est, lo_b, hi_b, cnt, _is_p in rows_data:
        est_strs.append(f"{_with_unit(_fe(est), u)} [{_fe(lo_b)}, {_fe(hi_b)}]")
        n_strs.append(f"{cnt:,}" if cnt is not None else "—")

    err_lbl = str(spec.get("error_label") or "CI")
    est_hdr = f"Est [{err_lbl}]"
    max_lbl = min(12 if width <= 76 else 18, max(len(r[0]) for r in rows_data))
    est_w = max(len(est_hdr), *(len(s) for s in est_strs))
    n_w = max(len("n"), *(len(s) for s in n_strs)) if has_n else 0
    n_extra = (2 + n_w) if has_n else 0
    track_w = max(10, width - (4 + max_lbl + 2 + 2 + est_w + n_extra))
    # Clamp label width if track + readout still exceeds target width
    overflow = (4 + max_lbl + 2 + track_w + 2 + est_w + n_extra) - width
    if overflow > 0 and max_lbl > 8:
        trim = min(overflow, max_lbl - 8)
        max_lbl -= trim
        overflow -= trim
    if overflow > 0 and track_w > 8:
        track_w = max(8, track_w - overflow)

    def _px(x: float) -> float:
        return (_tf(x) - lo_ax) / (hi_ax - lo_ax) * (track_w * 2 - 1)

    x_null_px = round(_px(ref_v)) if (ref_v is not None and (not log or ref_v > 0)) else None

    hl_raw = spec.get("highlight") or []
    hl_set = {str(h) for h in ([hl_raw] if isinstance(hl_raw, str) else hl_raw)}
    pos_hex = palette[0] if palette else "#0F8B6D"
    neg_hex = palette[1] if len(palette) > 1 else accent_hex
    pooled_hex = accent_hex

    lines: list[str] = []
    # Column header row
    hdr_n = f"  {'n'.rjust(n_w)}" if has_n else ""
    lines.append(
        style.dim(f"    {' ' * max_lbl}  {' ' * track_w}  {est_hdr.rjust(est_w)}{hdr_n}")
    )

    total_rule_w = min(width - 4, max_lbl + 2 + track_w + 2 + est_w + n_extra)
    for (nm, est, lo_b, hi_b, _cnt, is_p), e_txt, n_txt in zip(
        rows_data, est_strs, n_strs, strict=True
    ):
        if is_p:
            lines.append("    " + style.dim("─" * total_rule_w))

        is_hl = nm in hl_set
        if is_p:
            row_hex = pooled_hex
        elif nm in colors:
            row_hex = colors[nm]
        elif is_hl:
            row_hex = accent_hex
        elif ref_v is not None:
            if lo_b > ref_v:
                row_hex = pos_hex
            elif hi_b < ref_v:
                row_hex = neg_hex
            else:
                row_hex = context_hex
        else:
            row_hex = pos_hex

        row_canvas = BrailleCanvas(track_w, 1)
        if x_null_px is not None:
            row_canvas.set_pixel(x_null_px, 0, color=muted_hex, priority=0)
            row_canvas.set_pixel(x_null_px, 2, color=muted_hex, priority=0)

        x_lo_px = _px(lo_b)
        x_hi_px = _px(hi_b)
        x_est_px = _px(est)
        if is_p:
            rx = max(2.5, (x_hi_px - x_lo_px) / 2.0)
            row_canvas.draw_diamond(
                round(x_est_px), 1.5, rx, 1.75, color=row_hex, fill=True, priority=2
            )
        else:
            row_canvas.draw_line(x_lo_px, 2, x_hi_px, 2, color=row_hex, priority=1)
            row_canvas.set_pixel(round(x_lo_px), 1, color=row_hex, priority=1)
            row_canvas.set_pixel(round(x_hi_px), 1, color=row_hex, priority=1)
            row_canvas.draw_rect(x_est_px - 1, 1, x_est_px + 1, 3, color=row_hex, fill=True, priority=2)

        track_str = row_canvas.render(color=style.enabled, default_color=row_hex)[0]
        lbl = _clip_label(nm, max_lbl, ascii_only=False).rjust(max_lbl)
        e_pad = e_txt.rjust(est_w)
        n_part = f"  {style.dim(n_txt.rjust(n_w)) if not (is_p or is_hl) else style.bold(n_txt.rjust(n_w))}" if has_n else ""

        if is_p:
            mark = style.color("◆", row_hex, bold=True)
            lines.append(
                f"  {mark} {style.color(lbl, row_hex, bold=True)}  {track_str}  {style.color(e_pad, row_hex, bold=True)}{n_part}"
            )
        elif is_hl:
            mark = style.color("▸", row_hex, bold=True)
            lines.append(
                f"  {mark} {style.color(lbl, row_hex, bold=True)}  {track_str}  {style.bold(e_pad)}{n_part}"
            )
        else:
            lines.append(f"    {lbl}  {track_str}  {e_pad}{n_part}")

    # Bottom x-axis rule with optional null tick mark
    axis_chars = ["─"] * track_w
    null_col: int | None = None
    if x_null_px is not None:
        null_col = max(0, min(track_w - 1, x_null_px // 2))
        axis_chars[null_col] = "┴"
    lines.append(f"    {' ' * max_lbl}  {style.dim(''.join(axis_chars))}")

    lo_lbl = _fe(10**lo_ax if log else lo_ax)
    hi_lbl = _fe(10**hi_ax if log else hi_ax)
    tick_buf = [" "] * track_w
    for i, ch in enumerate(lo_lbl[:track_w]):
        tick_buf[i] = ch
    hi_start = max(len(lo_lbl) + 1, track_w - len(hi_lbl))
    for i, ch in enumerate(hi_lbl):
        if hi_start + i < track_w:
            tick_buf[hi_start + i] = ch
    if ref_v is not None and null_col is not None:
        ref_lbl = fmt_fn(ref_v)
        r_start = null_col - len(ref_lbl) // 2
        if r_start > len(lo_lbl) and r_start + len(ref_lbl) < hi_start:
            for i, ch in enumerate(ref_lbl):
                tick_buf[r_start + i] = ch
    lines.append(f"    {' ' * max_lbl}  {style.dim(''.join(tick_buf).rstrip())}")

    meta = [f"intervals: {err_lbl}"]
    if ref_v is not None:
        ref_name = ref[1] if isinstance(ref, Sequence) and not isinstance(ref, str) and len(ref) > 1 and ref[1] else "null"
        meta.append(f"┆ {ref_name} = {_with_unit(fmt_fn(ref_v), u)}")
    if log:
        meta.append("log scale")
    lines.append("  " + style.dim(" | ".join(meta)))
    return lines


def _render_matrix_truecolor(
    panel: Panel,
    *,
    width: int,
    style: _Style,
    theme: Theme,
) -> list[str]:
    """24-bit ANSI true-color heatmap for ``matrix()`` with automatic WCAG-contrast cell text."""
    if not style.enabled:
        return []
    spec = panel.spec
    rows_lbl = [str(r) for r in (spec.get("rows") or [])]
    cols_lbl = [str(c) for c in (spec.get("cols") or [])]
    raw_vals = spec.get("values") or []
    if not rows_lbl or not cols_lbl or not isinstance(raw_vals, Sequence):
        return []

    n_r = len(rows_lbl)
    n_c = len(cols_lbl)
    norm_mode = spec.get("normalize")
    show_counts = bool(spec.get("show_counts"))
    diverging = bool(spec.get("diverging"))
    center = float(spec.get("center")) if _is_num(spec.get("center")) else 0.0
    triangle = spec.get("triangle")
    mask_diagonal = bool(spec.get("mask_diagonal"))

    # Parse raw numeric matrix and apply triangle / diagonal masks
    raw_grid: list[list[float | None]] = []
    visible: list[list[bool]] = []
    for r in range(n_r):
        rv = raw_vals[r] if r < len(raw_vals) and isinstance(raw_vals[r], Sequence) else []
        row_nums: list[float | None] = []
        row_vis: list[bool] = []
        for c in range(n_c):
            v = rv[c] if c < len(rv) else None
            hidden = (
                (triangle == "lower" and c > r)
                or (triangle == "upper" and c < r)
                or (mask_diagonal and r == c)
            )
            row_vis.append(not hidden)
            row_nums.append(float(v) if (not hidden and _is_num(v)) else None)
        raw_grid.append(row_nums)
        visible.append(row_vis)

    # Compute normalized values (if requested) and cell display strings
    color_grid: list[list[float | None]] = [[None] * n_c for _ in range(n_r)]
    text_grid: list[list[str]] = [[""] * n_c for _ in range(n_r)]

    if norm_mode in {"row", "col"}:
        row_totals = [sum(v for v in r_vals if v is not None) for r_vals in raw_grid]
        col_totals = [
            sum(raw_grid[r][c] for r in range(n_r) if raw_grid[r][c] is not None)
            for c in range(n_c)
        ]
        for r in range(n_r):
            for c in range(n_c):
                if not visible[r][c]:
                    continue
                v = raw_grid[r][c]
                if v is None:
                    text_grid[r][c] = "—"
                    continue
                denom = row_totals[r] if norm_mode == "row" else col_totals[c]
                pct = (100.0 * v / denom) if denom > 0 else 0.0
                color_grid[r][c] = pct
                cell_s = f"{pct:.0f}%"
                if show_counts:
                    cell_s += f" ({_fmt_num(v)})"
                text_grid[r][c] = cell_s
        finite_vals = [v for row in color_grid for v in row if v is not None]
        lo_scale, hi_scale = 0.0, 100.0
        lo_disp, hi_disp = "0%", "100%"
    else:
        finite_vals = [v for row in raw_grid for v in row if v is not None]
        if not finite_vals:
            return []
        fmt_fn = _formatter(finite_vals, spec.get("fmt"), unit=panel.unit)
        for r in range(n_r):
            for c in range(n_c):
                if not visible[r][c]:
                    continue
                v = raw_grid[r][c]
                if v is None:
                    text_grid[r][c] = "—"
                    continue
                color_grid[r][c] = v
                text_grid[r][c] = fmt_fn(v)
        lo_scale, hi_scale = min(finite_vals), max(finite_vals)
        lo_disp = _with_unit(fmt_fn(lo_scale), panel.unit)
        hi_disp = _with_unit(fmt_fn(hi_scale), panel.unit)

    if not finite_vals:
        return []

    # Layout column & row label widths inside available width
    row_w = min(14 if width < 64 else 18, max(len(r) for r in rows_lbl))
    natural_cell = max(
        *(len(c) for c in cols_lbl),
        *(len(text_grid[r][c]) for r in range(n_r) for c in range(n_c)),
        3,
    ) + 2
    avail_cells = max(n_c * 4, width - (2 + row_w + 2) - (n_c - 1))
    cell_w = min(natural_cell, max(4, avail_cells // n_c))
    inner_w = max(2, cell_w - 2)

    div_stops = (*theme.div_low, theme.div_mid, *theme.div_high)
    seq_stops = theme.seq_stops

    def _cell_bg(v: float) -> str:
        if diverging:
            half = max(abs(lo_scale - center), abs(hi_scale - center), 1e-12)
            t = 0.5 + 0.5 * max(-1.0, min(1.0, (v - center) / half))
            return _interp_stops(div_stops, t)
        t = (v - lo_scale) / (hi_scale - lo_scale) if hi_scale > lo_scale else 0.5
        return _interp_stops(seq_stops, t)

    lines: list[str] = []
    # Column header row
    hdr_cells = [
        style.bold(_clip_label(c, cell_w, ascii_only=False).center(cell_w)) for c in cols_lbl
    ]
    lines.append(f"  {' ' * row_w}  {' '.join(hdr_cells)}")

    # Matrix body rows
    for r in range(n_r):
        rl = _clip_label(rows_lbl[r], row_w, ascii_only=False).rjust(row_w)
        rendered_cells: list[str] = []
        for c in range(n_c):
            if not visible[r][c]:
                rendered_cells.append(" " * cell_w)
                continue
            v = color_grid[r][c]
            txt = _clip_label(text_grid[r][c], inner_w, ascii_only=False)
            padded = f" {txt.center(inner_w)} "
            if v is None:
                rendered_cells.append(style.dim(padded))
                continue
            bg_hex = _cell_bg(v)
            fg_hex = _wcag_fg(bg_hex)
            is_diag_emphasis = norm_mode in {"row", "col"} and r == c and n_r == n_c
            rendered_cells.append(
                f"{_ansi_bg_rgb(bg_hex)}{_ansi_rgb(fg_hex, bold=is_diag_emphasis)}{padded}\x1b[0m"
            )
        lines.append(f"  {style.bold(rl)}  {' '.join(rendered_cells)}")

    # Compact true-color ramp legend
    n_swatches = 6
    stops = div_stops if diverging else seq_stops
    swatches = "".join(
        f"{_ansi_bg_rgb(_interp_stops(stops, i / (n_swatches - 1)))}  \x1b[0m"
        for i in range(n_swatches)
    )
    meta_parts = [f"{style.dim(lo_disp)} {swatches} {style.dim(hi_disp)}"]
    if norm_mode == "row":
        meta_parts.append(style.dim("row-normalized % (count)" if show_counts else "row-normalized %"))
    elif norm_mode == "col":
        meta_parts.append(style.dim("col-normalized % (count)" if show_counts else "col-normalized %"))
    if triangle:
        meta_parts.append(style.dim(f"{triangle} triangle"))
    lines.append(f"  {' ' * row_w}  " + "  ".join(meta_parts))
    return lines


def _compose_side_by_side(
    left_lines: list[str],
    right_lines: list[str],
    *,
    col_width: int,
    style: _Style,
) -> list[str]:
    """Join two rendered panel blocks side-by-side with an ANSI-aware dim vertical gutter."""
    gutter = style.dim("  │  ")
    n_rows = max(len(left_lines), len(right_lines))
    joined: list[str] = []
    for i in range(n_rows):
        lhs = left_lines[i] if i < len(left_lines) else ""
        rhs = right_lines[i] if i < len(right_lines) else ""
        joined.append(f"{_pad_visible(lhs, col_width)}{gutter}{rhs}")
    return joined


def _has_text_form(panel: Panel, *, high_res: bool = False) -> bool:
    """Kinds the text surface can draw faithfully; the rest print their title and top facts."""
    if panel.kind in {"compare", "share", "table", "trend", "change", "waterfall", "timeline", "flow", "forest"}:
        return True
    if panel.kind == "distribution" and panel.spec.get("mode") == "ecdf":
        return True
    if high_res and panel.kind in {"relate", "distribution", "histogram"}:
        return True
    if panel.kind == "matrix":
        rows = panel.spec.get("values") or []
        cols = panel.spec.get("cols") or []
        max_r, max_c = (12, 10) if high_res else _MAX_TEXT_MATRIX
        return bool(cols) and len(rows) <= max_r and len(cols) <= max_c
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
    high_res: bool = False,
    color_names: bool = False,
    muted_hex: str = "#5B6570",
    context_hex: str = "#8A939E",
    accent_hex: str = "#CD4324",
    theme: Theme | None = None,
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
        styled_title = (
            _colorize_entity_names(f"{prefix}{title_part}", colors, style, base_bold=True)
            if color_names
            else style.bold(f"{prefix}{title_part}")
        )
        out = [styled_title + style.dim(meta_part)]
    else:
        out = [
            _colorize_entity_names(line, colors, style, base_bold=True)
            if color_names
            else style.bold(line)
            for line in textwrap.wrap(header, width=width)
        ]

    use_braille = high_res and not ascii_only
    if not _has_text_form(panel, high_res=use_braille):
        facts = _bullets(panel.facts[:_TOP_FACTS], width=width, bullet=bullet)
        if not facts and panel.describe:
            facts = _bullets([panel.describe], width=width, bullet=bullet)
        return out + facts

    bg_hex = theme.background if theme is not None else "#0F1715"
    ink_hex = theme.ink if theme is not None else "#E8F1EE"
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
        if use_braille:
            out.extend(
                _render_trend_braille(
                    panel,
                    width=width,
                    style=style,
                    colors=colors,
                    palette=palette,
                    muted_hex=muted_hex,
                    context_hex=context_hex,
                    bg_hex=bg_hex,
                )
            )
        else:
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
    elif use_braille and panel.kind == "distribution" and panel.spec.get("mode") == "ecdf":
        ecdf_lines = _render_ecdf_braille(
            panel,
            width=width,
            style=style,
            colors=colors,
            palette=palette,
            muted_hex=muted_hex,
        )
        if ecdf_lines:
            out.extend(ecdf_lines)
            out.extend(first_fact)
        else:
            out.extend(_render_facts_panel(panel, width=width, style=style, ascii_only=ascii_only))
    elif use_braille and (
        panel.kind == "histogram"
        or (panel.kind == "distribution" and panel.spec.get("bins") is not None)
    ):
        hist_lines = _render_histogram_braille(
            panel,
            width=width,
            style=style,
            colors=colors,
            palette=palette,
            muted_hex=muted_hex,
        )
        if hist_lines:
            out.extend(hist_lines)
            out.extend(first_fact)
        else:
            out.extend(_render_facts_panel(panel, width=width, style=style, ascii_only=ascii_only))
    elif use_braille and panel.kind == "distribution":
        swarm_lines = _render_swarm_braille(
            panel,
            width=width,
            style=style,
            colors=colors,
            palette=palette,
            muted_hex=muted_hex,
            context_hex=context_hex,
            ink_hex=ink_hex,
        )
        if swarm_lines:
            out.extend(swarm_lines)
            out.extend(first_fact)
        else:
            out.extend(_render_facts_panel(panel, width=width, style=style, ascii_only=ascii_only))
    elif use_braille and panel.kind == "relate":
        rel_lines = _render_relate_braille(
            panel,
            width=width,
            style=style,
            colors=colors,
            palette=palette,
            muted_hex=muted_hex,
            accent_hex=accent_hex,
        )
        if rel_lines:
            out.extend(rel_lines)
            out.extend(first_fact)
        else:
            out.extend(_render_facts_panel(panel, width=width, style=style, ascii_only=ascii_only))
    elif use_braille and panel.kind == "change":
        chg_lines = _render_change_braille(
            panel,
            width=width,
            style=style,
            colors=colors,
            palette=palette,
            muted_hex=muted_hex,
            context_hex=context_hex,
            accent_hex=accent_hex,
        )
        if chg_lines:
            out.extend(chg_lines)
            out.extend(first_fact)
        else:
            out.extend(_render_facts_panel(panel, width=width, style=style, ascii_only=ascii_only))
    elif use_braille and panel.kind == "forest":
        for_lines = _render_forest_braille(
            panel,
            width=width,
            style=style,
            colors=colors,
            palette=palette,
            muted_hex=muted_hex,
            context_hex=context_hex,
            accent_hex=accent_hex,
        )
        if for_lines:
            out.extend(for_lines)
            out.extend(first_fact)
        else:
            out.extend(_render_facts_panel(panel, width=width, style=style, ascii_only=ascii_only))
    elif use_braille and panel.kind == "matrix" and style.enabled and theme is not None:
        mat_lines = _render_matrix_truecolor(
            panel,
            width=width,
            style=style,
            theme=theme,
        )
        if mat_lines:
            out.extend(mat_lines)
            out.extend(first_fact)
        else:
            out.extend(_render_facts_panel(panel, width=width, style=style, ascii_only=ascii_only))
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
    width: int | str = 78,
    color: bool | None = True,
    ascii_only: bool = False,
    high_res: bool = False,
    color_names: bool = True,
) -> str:
    """Render an ``Explanation`` or spec dict as crisp Unicode, Braille, or ASCII terminal output.

    ``color=False`` output has no escape codes and no line wider than ``width``, so it
    is safe inside a Markdown code block. Pass ``width="auto"`` to size automatically to
    the terminal width (clamped to 56..132), and ``color=None`` to respect ``NO_COLOR``
    and ``FORCE_COLOR``. Pass ``high_res=True`` for 2×4 Unicode Braille sub-pixel charts
    (trend + CI bands, ECDF, beeswarm, scatter + OLS + Pareto frontier, slopegraph,
    forest plot), 24-bit ANSI true-color heatmaps, editorial chrome, and side-by-side
    2-column composition at wide terminals (``width >= 104``).
    """
    exp = _ensure_explanation(exp_or_spec)
    w = _resolve_width(width)
    use_color = _resolve_color(color)
    accent = exp.theme.accent_colors[0] if exp.theme.accent_colors else "#CD4324"
    primary = exp.theme.series_colors[0] if exp.theme.series_colors else "#1F5A9D"
    style = _Style(enabled=use_color, accent=accent, primary=primary)
    rule = ("-" if ascii_only else "─") * w
    colors = _entity_hex(exp)
    name_colors = _all_entity_hex(exp) if (use_color and color_names) else {}

    out: list[str] = []
    if high_res:
        flag_hex = exp.theme.top_flag_color or exp.theme.panel_tag_color or accent
        flag_w = max(4, min(10, w // 9))
        if ascii_only:
            out.append("=" * flag_w + "-" * max(0, w - flag_w))
        else:
            out.append(
                style.color("━" * flag_w, flag_hex, bold=True)
                + style.dim("─" * max(0, w - flag_w))
            )
        kicker_raw = getattr(exp, "kicker", None)
        if kicker_raw and str(kicker_raw).strip():
            kicker_txt = " ".join(str(kicker_raw).split()).upper()
            for kline in textwrap.wrap(kicker_txt, width=w):
                out.append(style.color(kline, flag_hex, bold=True))

    for line in textwrap.wrap(exp.takeaway, width=w):
        if use_color and color_names and name_colors:
            out.append(_colorize_entity_names(line, name_colors, style, base_bold=True))
        else:
            out.append(style.bold(line))
    if exp.subtitle:
        for line in textwrap.wrap(exp.subtitle, width=w):
            out.append(style.dim(line))
    out.append(style.dim(rule))

    multi = len(exp.panels) > 1
    panel_colors = name_colors if (use_color and color_names) else colors

    def _render_one(k: str, target_w: int) -> list[str]:
        return _panel_block(
            k,
            exp.panels[k],
            multi=multi,
            width=target_w,
            style=style,
            ascii_only=ascii_only,
            colors=panel_colors,
            palette=exp.theme.series_colors,
            high_res=high_res,
            color_names=bool(use_color and color_names),
            muted_hex=exp.theme.muted,
            context_hex=exp.theme.context_line,
            accent_hex=accent,
            theme=exp.theme,
        )

    layout_rows = getattr(exp, "layout", None)
    rows_to_render: list[list[str]] = []
    seen_keys: set[str] = set()
    if isinstance(layout_rows, Sequence) and not isinstance(layout_rows, (str, bytes)):
        for row in layout_rows:
            if not isinstance(row, Sequence) or isinstance(row, (str, bytes)):
                continue
            unique_in_row = [
                str(k)
                for k in dict.fromkeys(row)
                if str(k) in exp.panels and str(k) not in seen_keys
            ]
            if unique_in_row:
                rows_to_render.append(unique_in_row)
                seen_keys.update(unique_in_row)
    for k in exp.panels:
        if k not in seen_keys:
            rows_to_render.append([k])
            seen_keys.add(k)

    emitted_any = False
    for row_keys in rows_to_render:
        if high_res and not ascii_only and w >= 104 and len(row_keys) == 2:
            if emitted_any:
                out.append("")
            col_w = (w - 5) // 2
            left_block = _render_one(row_keys[0], col_w)
            right_block = _render_one(row_keys[1], col_w)
            out.extend(_compose_side_by_side(left_block, right_block, col_width=col_w, style=style))
            emitted_any = True
        else:
            for k in row_keys:
                if emitted_any:
                    out.append("")
                out.extend(_render_one(k, w))
                emitted_any = True

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
    if not use_color:
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
    width: int | str = 78,
    color: bool | None = True,
    high_res: bool | None = None,
    env: Mapping[str, str] | None = None,
    passthrough: bool = True,
) -> str:
    """Return a terminal-ready string (inline graphics escape sequence or rich text).

    ``path_or_spec`` may be a PNG path, a JSON spec path, an ``Explanation``, or
    a spec dict. ``mode`` may be ``"auto"``, ``"kitty"``, ``"iterm2"``, ``"braille"``,
    ``"unicode"``, or ``"ascii"``. When ``mode="auto"`` falls back to an ANSI terminal
    without Kitty/iTerm2 and ``color=True``, high-resolution 2×4 Braille plotting is
    enabled automatically (override with ``high_res=False``). Pass ``width="auto"`` to
    fit the current terminal width, ``color=None`` to respect ``NO_COLOR``/``FORCE_COLOR``,
    and ``passthrough=True`` (the default) to wrap Kitty/iTerm2 escape sequences in
    ``tmux`` DCS passthrough when ``TMUX`` is present in ``env``.
    """
    valid_modes = {"auto", "kitty", "iterm2", "braille", "unicode", "ascii"}
    if mode not in valid_modes:
        raise ValueError(
            f"Unknown terminal mode {mode!r}. Choose one of: {', '.join(sorted(valid_modes))}."
        )

    source = os.environ if env is None else env
    resolved = detect_graphics_protocol(source) if mode == "auto" else mode
    use_color = _resolve_color(color, env=source)
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
        seq = encode_kitty_png(png_bytes) if resolved == "kitty" else encode_iterm2_png(png_bytes)
        if passthrough and source.get("TMUX"):
            return wrap_tmux_passthrough(seq)
        return seq

    ascii_only = resolved == "ascii"
    if resolved == "braille":
        use_high_res = True
    elif high_res is not None:
        use_high_res = bool(high_res) and not ascii_only
    else:
        # Automatically enable Braille when mode="auto" falls back to an ANSI TTY without Kitty/iTerm2
        use_high_res = bool(mode == "auto" and use_color and not ascii_only)

    if exp_or_spec is not None:
        return render_terminal(
            exp_or_spec,
            width=width,
            color=use_color,
            ascii_only=ascii_only,
            high_res=use_high_res,
        )

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
