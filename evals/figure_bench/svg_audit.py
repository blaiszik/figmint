"""Library-agnostic SVG figure auditor (stdlib-only: ``xml.etree.ElementTree``).

Audits SVGs emitted by Altair, Plotly, D3, Vega-Lite, R ``ggplot2``/``svglite``,
Matplotlib (with ``svg.fonttype = 'none'``), or any other vector plotting tool.
Measures text sizes scaled to the target display width (e.g. 700 px chat column),
estimates text bounding boxes for overlap / canvas-edge clipping, detects
``<line>``/``<polyline>``/``<path>`` segments crossing text boxes, checks for
malformed text (``%%``, doubled words, ASCII hyphen as minus, ``nan``/``None``),
and extracts all drawn text strings for headline and uncertainty checks.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DISPLAY_WIDTH_PX = 700
MIN_TEXT_PX = 11.0

UNCERTAINTY_WORDS = re.compile(
    r"(\bCI\b|confidence|interval|\bs\.?d\.?\b|\bSD\b|\bSEM?\b|\bs\.e\.m?\.?|standard (?:deviation|error)"
    r"|±|\bIQR\b|quartile|percentile|\bseeds?\b|replicates?|triplicates?|\bwells?\b|\bn\s*=\s*\d"
    r"|margin of error|\brange\b|\bmin[–-]max\b|\bp\s*[<=>]\s*0?\.\d|\bp-value\b|error bars?)",
    re.IGNORECASE,
)

_DOUBLED = re.compile(r"\b(\w+(?:\s+\w+)?)\s+\1\b", re.IGNORECASE)
_ASCII_MINUS = re.compile(r"(?:^|[\s(\[=:,])-\d")
_JUNK = re.compile(r"\b(nan|NaN|None|inf|-inf)\b")

_UNIT_TO_PX: dict[str, float] = {
    "": 1.0,
    "px": 1.0,
    "pt": 96.0 / 72.0,
    "pc": 16.0,
    "in": 96.0,
    "cm": 96.0 / 2.54,
    "mm": 96.0 / 25.4,
}

_LEN_RE = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([a-zA-Z%]*)\s*$")
_TRANSFORM_RE = re.compile(r"([a-zA-Z]+)\s*\(([^)]*)\)")
_NUM_RE = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
_FONT_SIZE_SHORTHAND_RE = re.compile(
    r"(?:^|\s)(\d+(?:\.\d+)?|\.\d+)(px|pt|em|rem|%)?(?:/[\d.a-zA-Z%]+)?(?=\s|$)"
)
_PATH_TOKEN_RE = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")

_SKIP_CONTAINER_TAGS = frozenset({"defs", "clipPath", "mask", "pattern", "symbol", "marker", "style", "metadata", "title", "desc"})
_GRID_HINT_RE = re.compile(r"(?:^|[\s_-])(grid|gridline|tick|spine|axis|frame|border|background|bg|box)(?:$|[\s_-])", re.IGNORECASE)

# 2D affine matrix (a, b, c, d, e, f):
#   x' = a*x + c*y + e
#   y' = b*x + d*y + f
Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


@dataclass
class _TextBox:
    text: str
    font_px: float
    x0: float
    y0: float
    x1: float
    y1: float
    is_title_hint: bool = False
    masked: bool = False


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _mat_mul(m1: Matrix, m2: Matrix) -> Matrix:
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def _apply(m: Matrix, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


def _mat_scale(m: Matrix) -> float:
    a, b, c, d, _, _ = m
    det = abs(a * d - b * c)
    if det > 0:
        return math.sqrt(det)
    return max(math.hypot(a, b), math.hypot(c, d), 1e-6)


def _parse_transform(raw: str | None) -> Matrix:
    if not raw:
        return IDENTITY
    mat = IDENTITY
    for m in _TRANSFORM_RE.finditer(raw):
        kind = m.group(1)
        nums = [float(x) for x in _NUM_RE.findall(m.group(2))]
        t: Matrix = IDENTITY
        if kind == "translate" and len(nums) >= 1:
            tx = nums[0]
            ty = nums[1] if len(nums) >= 2 else 0.0
            t = (1.0, 0.0, 0.0, 1.0, tx, ty)
        elif kind == "scale" and len(nums) >= 1:
            sx = nums[0]
            sy = nums[1] if len(nums) >= 2 else sx
            t = (sx, 0.0, 0.0, sy, 0.0, 0.0)
        elif kind == "rotate" and len(nums) >= 1:
            rad = math.radians(nums[0])
            cos_a, sin_a = math.cos(rad), math.sin(rad)
            rot: Matrix = (cos_a, sin_a, -sin_a, cos_a, 0.0, 0.0)
            if len(nums) >= 3:
                cx, cy = nums[1], nums[2]
                t = _mat_mul(_mat_mul((1.0, 0.0, 0.0, 1.0, cx, cy), rot), (1.0, 0.0, 0.0, 1.0, -cx, -cy))
            else:
                t = rot
        elif kind == "matrix" and len(nums) >= 6:
            t = (nums[0], nums[1], nums[2], nums[3], nums[4], nums[5])
        elif kind == "skewX" and len(nums) >= 1:
            t = (1.0, 0.0, math.tan(math.radians(nums[0])), 1.0, 0.0, 0.0)
        elif kind == "skewY" and len(nums) >= 1:
            t = (1.0, math.tan(math.radians(nums[0])), 0.0, 1.0, 0.0, 0.0)
        mat = _mat_mul(mat, t)
    return mat


def _parse_length(raw: str | None, *, default: float | None = None, parent: float = 12.0) -> float | None:
    if not raw:
        return default
    m = _LEN_RE.match(raw)
    if not m:
        return default
    val = float(m.group(1))
    unit = m.group(2).lower()
    if unit in ("em", "rem"):
        return val * parent
    if unit == "%":
        return val / 100.0 * parent
    factor = _UNIT_TO_PX.get(unit)
    if factor is None:
        return default
    return val * factor


def _parse_style(raw: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not raw:
        return out
    for part in raw.split(";"):
        if ":" not in part:
            continue
        k, v = part.split(":", 1)
        k = k.strip().lower()
        v = v.strip()
        if k:
            out[k] = v
    return out


def _parse_css_rules(root: ET.Element) -> dict[str, dict[str, str]]:
    """Extract simple selector -> declarations maps from inline ``<style>`` blocks."""
    rules: dict[str, dict[str, str]] = {}
    for elem in root.iter():
        if _local(elem.tag) != "style" or not elem.text:
            continue
        cleaned = re.sub(r"/\*.*?\*/", "", elem.text, flags=re.DOTALL)
        for m in re.finditer(r"([^{}]+)\{([^{}]+)\}", cleaned):
            decls = _parse_style(m.group(2))
            if not decls:
                continue
            for sel in m.group(1).split(","):
                sel_s = sel.strip()
                if sel_s:
                    rules.setdefault(sel_s, {}).update(decls)
    return rules


def _font_size_from_props(props: dict[str, str], parent_size: float) -> float:
    fs = props.get("font-size")
    if fs:
        parsed = _parse_length(fs, default=None, parent=parent_size)
        if parsed is not None and parsed > 0:
            return parsed
    shorthand = props.get("font")
    if shorthand:
        m = _FONT_SIZE_SHORTHAND_RE.search(shorthand)
        if m:
            raw = m.group(1) + (m.group(2) or "")
            parsed = _parse_length(raw, default=None, parent=parent_size)
            if parsed is not None and parsed > 0:
                return parsed
    return parent_size


def _parse_canvas(root: ET.Element) -> tuple[float, float, float, float, float, float]:
    """Return ``(vb_x, vb_y, vb_w, vb_h, nominal_w_px, nominal_h_px)``."""
    vb_raw = root.attrib.get("viewBox") or root.attrib.get("viewbox")
    w_px = _parse_length(root.attrib.get("width"))
    h_px = _parse_length(root.attrib.get("height"))
    if vb_raw:
        nums = [float(x) for x in _NUM_RE.findall(vb_raw)]
        if len(nums) >= 4 and nums[2] > 0 and nums[3] > 0:
            vb_x, vb_y, vb_w, vb_h = nums[:4]
            nom_w = w_px if (w_px and w_px > 0) else vb_w
            nom_h = h_px if (h_px and h_px > 0) else vb_h
            return vb_x, vb_y, vb_w, vb_h, nom_w, nom_h
    nom_w = w_px if (w_px and w_px > 0) else float(DISPLAY_WIDTH_PX)
    nom_h = h_px if (h_px and h_px > 0) else 480.0
    return 0.0, 0.0, nom_w, nom_h, nom_w, nom_h


def _estimate_text_width(text: str, font_size: float) -> float:
    total = 0.0
    for ch in text:
        if ch in "ilI1.,|:;'![]()":
            total += 0.32
        elif ch == " ":
            total += 0.30
        elif ch in "MW@#%&":
            total += 0.82
        elif ch.isupper():
            total += 0.65
        else:
            total += 0.54
    return total * font_size


def _make_text_box(
    text: str,
    x: float,
    y: float,
    font_size_user: float,
    anchor: str,
    baseline: str,
    mat: Matrix,
    display_scale: float,
    *,
    is_title_hint: bool = False,
    masked: bool = False,
) -> _TextBox:
    w = _estimate_text_width(text, font_size_user)
    ascent = 0.78 * font_size_user
    descent = 0.22 * font_size_user

    if anchor == "middle":
        lx0, lx1 = x - w / 2.0, x + w / 2.0
    elif anchor == "end":
        lx0, lx1 = x - w, x
    else:
        lx0, lx1 = x, x + w

    if baseline in ("middle", "central"):
        ly0, ly1 = y - 0.5 * font_size_user, y + 0.5 * font_size_user
    elif baseline in ("hanging", "text-before-edge", "top"):
        ly0, ly1 = y, y + font_size_user
    else:
        # SVG alphabetic baseline: text sits above y (smaller y in SVG coords)
        ly0, ly1 = y - ascent, y + descent

    corners = [
        _apply(mat, lx0, ly0),
        _apply(mat, lx1, ly0),
        _apply(mat, lx1, ly1),
        _apply(mat, lx0, ly1),
    ]
    xs = [p[0] for p in corners]
    ys = [p[1] for p in corners]
    font_px = font_size_user * _mat_scale(mat) * display_scale
    return _TextBox(
        text=text,
        font_px=font_px,
        x0=min(xs),
        y0=min(ys),
        x1=max(xs),
        y1=max(ys),
        is_title_hint=is_title_hint,
        masked=masked,
    )


def _sample_cubic(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    steps: int = 8,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    pts = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1.0 - t
        x = mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0]
        y = mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1]
        pts.append((x, y))
    return [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]


def _sample_quad(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    steps: int = 6,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    pts = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1.0 - t
        x = mt**2 * p0[0] + 2 * mt * t * p1[0] + t**2 * p2[0]
        y = mt**2 * p0[1] + 2 * mt * t * p1[1] + t**2 * p2[1]
        pts.append((x, y))
    return [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]


def _parse_path_segments(d: str) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Parse an SVG ``<path d="...">`` string into line segments."""
    tokens = _PATH_TOKEN_RE.findall(d)
    segs: list[tuple[tuple[float, float], tuple[float, float]]] = []
    idx = 0
    cmd = ""
    cx, cy = 0.0, 0.0
    sx, sy = 0.0, 0.0
    last_ctrl: tuple[float, float] | None = None

    def _is_cmd(tok: str) -> bool:
        return len(tok) == 1 and tok.isalpha()

    def _next_num() -> float | None:
        nonlocal idx
        if idx >= len(tokens) or _is_cmd(tokens[idx]):
            return None
        val = float(tokens[idx])
        idx += 1
        return val

    while idx < len(tokens):
        if _is_cmd(tokens[idx]):
            cmd = tokens[idx]
            idx += 1
        elif not cmd:
            idx += 1
            continue

        if cmd in ("M", "m"):
            x, y = _next_num(), _next_num()
            if x is None or y is None:
                break
            if cmd == "m":
                cx, cy = cx + x, cy + y
            else:
                cx, cy = x, y
            sx, sy = cx, cy
            last_ctrl = None
            cmd = "l" if cmd == "m" else "L"
        elif cmd in ("L", "l"):
            x, y = _next_num(), _next_num()
            if x is None or y is None:
                break
            nx, ny = (cx + x, cy + y) if cmd == "l" else (x, y)
            segs.append(((cx, cy), (nx, ny)))
            cx, cy = nx, ny
            last_ctrl = None
        elif cmd in ("H", "h"):
            x = _next_num()
            if x is None:
                break
            nx = cx + x if cmd == "h" else x
            segs.append(((cx, cy), (nx, cy)))
            cx = nx
            last_ctrl = None
        elif cmd in ("V", "v"):
            y = _next_num()
            if y is None:
                break
            ny = cy + y if cmd == "v" else y
            segs.append(((cx, cy), (cx, ny)))
            cy = ny
            last_ctrl = None
        elif cmd in ("C", "c"):
            vals = [_next_num() for _ in range(6)]
            if any(v is None for v in vals):
                break
            x1, y1, x2, y2, x, y = vals  # type: ignore[misc]
            if cmd == "c":
                p1, p2, p3 = (cx + x1, cy + y1), (cx + x2, cy + y2), (cx + x, cy + y)
            else:
                p1, p2, p3 = (x1, y1), (x2, y2), (x, y)
            segs.extend(_sample_cubic((cx, cy), p1, p2, p3))
            cx, cy = p3
            last_ctrl = p2
        elif cmd in ("S", "s"):
            vals = [_next_num() for _ in range(4)]
            if any(v is None for v in vals):
                break
            x2, y2, x, y = vals  # type: ignore[misc]
            p1 = (2 * cx - last_ctrl[0], 2 * cy - last_ctrl[1]) if last_ctrl else (cx, cy)
            if cmd == "s":
                p2, p3 = (cx + x2, cy + y2), (cx + x, cy + y)
            else:
                p2, p3 = (x2, y2), (x, y)
            segs.extend(_sample_cubic((cx, cy), p1, p2, p3))
            cx, cy = p3
            last_ctrl = p2
        elif cmd in ("Q", "q"):
            vals = [_next_num() for _ in range(4)]
            if any(v is None for v in vals):
                break
            x1, y1, x, y = vals  # type: ignore[misc]
            if cmd == "q":
                p1, p2 = (cx + x1, cy + y1), (cx + x, cy + y)
            else:
                p1, p2 = (x1, y1), (x, y)
            segs.extend(_sample_quad((cx, cy), p1, p2))
            cx, cy = p2
            last_ctrl = p1
        elif cmd in ("T", "t"):
            x, y = _next_num(), _next_num()
            if x is None or y is None:
                break
            p1 = (2 * cx - last_ctrl[0], 2 * cy - last_ctrl[1]) if last_ctrl else (cx, cy)
            p2 = (cx + x, cy + y) if cmd == "t" else (x, y)
            segs.extend(_sample_quad((cx, cy), p1, p2))
            cx, cy = p2
            last_ctrl = p1
        elif cmd in ("A", "a"):
            vals = [_next_num() for _ in range(7)]
            if any(v is None for v in vals):
                break
            x, y = vals[5], vals[6]  # type: ignore[misc]
            nx, ny = (cx + x, cy + y) if cmd == "a" else (x, y)
            segs.append(((cx, cy), (nx, ny)))
            cx, cy = nx, ny
            last_ctrl = None
        elif cmd in ("Z", "z"):
            if (cx, cy) != (sx, sy):
                segs.append(((cx, cy), (sx, sy)))
            cx, cy = sx, sy
            last_ctrl = None
            cmd = ""
        else:
            break
    return segs


def _segment_intersects_box(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    bx0: float,
    by0: float,
    bx1: float,
    by1: float,
) -> bool:
    """Liang-Barsky segment vs axis-aligned rectangle intersection test."""
    dx = x2 - x1
    dy = y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1 - bx0), (dx, bx1 - x1), (-dy, y1 - by0), (dy, by1 - y1)):
        if abs(p) < 1e-12:
            if q < 0.0:
                return False
        else:
            r = q / p
            if p < 0.0:
                if r > t1:
                    return False
                t0 = max(t0, r)
            else:
                if r < t0:
                    return False
                t1 = min(t1, r)
    return t0 <= t1


def _box_overlaps(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def _is_hidden(props: dict[str, str]) -> bool:
    if props.get("display", "").lower() == "none":
        return True
    if props.get("visibility", "").lower() in ("hidden", "collapse"):
        return True
    for key in ("opacity", "fill-opacity"):
        val = props.get(key)
        if val is not None:
            try:
                if float(val) <= 0.0:
                    return True
            except ValueError:
                pass
    return False


def _is_visible_stroke(props: dict[str, str]) -> bool:
    if props.get("display", "").lower() == "none":
        return False
    if props.get("visibility", "").lower() in ("hidden", "collapse"):
        return False
    stroke = props.get("stroke", "").strip().lower()
    if not stroke or stroke in ("none", "transparent"):
        return False
    for key in ("opacity", "stroke-opacity"):
        val = props.get(key)
        if val is not None:
            try:
                if float(val) <= 0.2:
                    return False
            except ValueError:
                pass
    sw = props.get("stroke-width")
    if sw is not None:
        parsed = _parse_length(sw, default=1.0)
        if parsed is not None and parsed <= 0.0:
            return False
    return True


def _merge_props(elem: ET.Element, parent_props: dict[str, str], css_rules: dict[str, dict[str, str]]) -> dict[str, str]:
    props = dict(parent_props)
    tag = _local(elem.tag)
    if tag in css_rules:
        props.update(css_rules[tag])
    cls = elem.attrib.get("class", "")
    for token in cls.split():
        for sel in (f".{token}", f"{tag}.{token}"):
            if sel in css_rules:
                props.update(css_rules[sel])
    for attr in (
        "font-size",
        "font",
        "text-anchor",
        "dominant-baseline",
        "display",
        "visibility",
        "opacity",
        "fill",
        "fill-opacity",
        "stroke",
        "stroke-opacity",
        "stroke-width",
        "stroke-dasharray",
    ):
        if attr in elem.attrib:
            props[attr] = elem.attrib[attr]
    if "style" in elem.attrib:
        props.update(_parse_style(elem.attrib["style"]))
    return props


def audit_svg(svg_path: str | Path, *, display_width_px: int = DISPLAY_WIDTH_PX) -> dict[str, Any]:
    """Audit an SVG figure neutrally at ``display_width_px``.

    Returns a dictionary compatible with ``neutral.py``'s metrics plus
    ``text_strings`` for library-agnostic headline & uncertainty checks.
    """
    path = Path(svg_path)
    tree = ET.parse(path)
    root = tree.getroot()

    vb_x, vb_y, vb_w, vb_h, nom_w, nom_h = _parse_canvas(root)
    shown_px = min(float(display_width_px), nom_w) if nom_w > 0 else float(display_width_px)
    display_scale = shown_px / vb_w if vb_w > 0 else 1.0

    css_rules = _parse_css_rules(root)
    text_boxes: list[_TextBox] = []
    line_segments: list[tuple[float, float, float, float, bool]] = []  # (x1, y1, x2, y2, dashed)
    opaque_rects: list[tuple[float, float, float, float]] = []
    has_path_text_groups = False

    def _walk(
        elem: ET.Element,
        mat: Matrix,
        parent_props: dict[str, str],
        parent_font: float,
        in_grid_or_axis: bool,
        in_legend: bool,
        in_title: bool,
    ) -> None:
        nonlocal has_path_text_groups
        tag = _local(elem.tag)
        if tag in _SKIP_CONTAINER_TAGS:
            return
        props = _merge_props(elem, parent_props, css_rules)
        if props.get("display", "").lower() == "none":
            return
        local_mat = _mat_mul(mat, _parse_transform(elem.attrib.get("transform")))
        font_size = _font_size_from_props(props, parent_font)

        ident = f"{elem.attrib.get('id', '')} {elem.attrib.get('class', '')}"
        if tag == "g" and re.search(r"\btext_\d+\b", ident):
            has_path_text_groups = True
        grid_here = in_grid_or_axis or bool(_GRID_HINT_RE.search(ident))
        legend_here = in_legend or ("legend" in ident.lower())
        title_here = in_title or bool(re.search(r"title|headline|suptitle|heading", ident, re.IGNORECASE))

        if tag == "rect":
            fill = props.get("fill", "").strip().lower()
            if fill and fill not in ("none", "transparent") and not _is_hidden(props):
                rx = _parse_length(elem.attrib.get("x"), default=0.0) or 0.0
                ry = _parse_length(elem.attrib.get("y"), default=0.0) or 0.0
                rw = _parse_length(elem.attrib.get("width"), default=0.0) or 0.0
                rh = _parse_length(elem.attrib.get("height"), default=0.0) or 0.0
                if rw > 0 and rh > 0 and rw < vb_w * 0.85 and rh < vb_h * 0.85:
                    pts = [
                        _apply(local_mat, rx, ry),
                        _apply(local_mat, rx + rw, ry),
                        _apply(local_mat, rx + rw, ry + rh),
                        _apply(local_mat, rx, ry + rh),
                    ]
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    opaque_rects.append((min(xs), min(ys), max(xs), max(ys)))

        if tag == "text":
            if _is_hidden(props):
                return
            base_x = _parse_length(elem.attrib.get("x"), default=0.0, parent=font_size) or 0.0
            base_y = _parse_length(elem.attrib.get("y"), default=0.0, parent=font_size) or 0.0
            base_x += _parse_length(elem.attrib.get("dx"), default=0.0, parent=font_size) or 0.0
            base_y += _parse_length(elem.attrib.get("dy"), default=0.0, parent=font_size) or 0.0
            anchor = props.get("text-anchor", "start").strip().lower()
            baseline = props.get("dominant-baseline", "alphabetic").strip().lower()

            tspans = [ch for ch in elem if _local(ch.tag) == "tspan"]
            if tspans:
                cur_x, cur_y = base_x, base_y
                if elem.text and elem.text.strip():
                    txt = " ".join(elem.text.split())
                    text_boxes.append(
                        _make_text_box(
                            txt, cur_x, cur_y, font_size, anchor, baseline, local_mat, display_scale,
                            is_title_hint=title_here, masked=legend_here,
                        )
                    )
                for ts in tspans:
                    ts_props = _merge_props(ts, props, css_rules)
                    if _is_hidden(ts_props):
                        continue
                    ts_font = _font_size_from_props(ts_props, font_size)
                    ts_x = _parse_length(ts.attrib.get("x"), default=None, parent=ts_font)
                    ts_y = _parse_length(ts.attrib.get("y"), default=None, parent=ts_font)
                    if ts_x is not None:
                        cur_x = ts_x
                    if ts_y is not None:
                        cur_y = ts_y
                    cur_x += _parse_length(ts.attrib.get("dx"), default=0.0, parent=ts_font) or 0.0
                    cur_y += _parse_length(ts.attrib.get("dy"), default=0.0, parent=ts_font) or 0.0
                    ts_txt = " ".join("".join(ts.itertext()).split())
                    if ts_txt:
                        ts_anchor = ts_props.get("text-anchor", anchor).strip().lower()
                        ts_base = ts_props.get("dominant-baseline", baseline).strip().lower()
                        text_boxes.append(
                            _make_text_box(
                                ts_txt, cur_x, cur_y, ts_font, ts_anchor, ts_base, local_mat, display_scale,
                                is_title_hint=title_here, masked=legend_here,
                            )
                        )
                        cur_x += _estimate_text_width(ts_txt, ts_font)
            else:
                txt = " ".join("".join(elem.itertext()).split())
                if txt:
                    text_boxes.append(
                        _make_text_box(
                            txt, base_x, base_y, font_size, anchor, baseline, local_mat, display_scale,
                            is_title_hint=title_here, masked=legend_here,
                        )
                    )
            return

        if not grid_here and not legend_here and _is_visible_stroke(props):
            dashed = bool(props.get("stroke-dasharray", "").strip() not in ("", "none"))
            if tag == "line":
                x1 = _parse_length(elem.attrib.get("x1"), default=0.0) or 0.0
                y1 = _parse_length(elem.attrib.get("y1"), default=0.0) or 0.0
                x2 = _parse_length(elem.attrib.get("x2"), default=0.0) or 0.0
                y2 = _parse_length(elem.attrib.get("y2"), default=0.0) or 0.0
                p1 = _apply(local_mat, x1, y1)
                p2 = _apply(local_mat, x2, y2)
                if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) * display_scale >= 6.0:
                    line_segments.append((p1[0], p1[1], p2[0], p2[1], dashed))
            elif tag == "polyline":
                nums = [float(v) for v in _NUM_RE.findall(elem.attrib.get("points", ""))]
                pts = [_apply(local_mat, nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
                for i in range(len(pts) - 1):
                    p1, p2 = pts[i], pts[i + 1]
                    if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) * display_scale >= 6.0:
                        line_segments.append((p1[0], p1[1], p2[0], p2[1], dashed))
            elif tag == "path":
                fill = props.get("fill", "").strip().lower()
                # Focus on open/stroked data & reference paths, not filled shapes/bars
                if fill in ("", "none", "transparent"):
                    d = elem.attrib.get("d", "")
                    for p1_raw, p2_raw in _parse_path_segments(d):
                        p1 = _apply(local_mat, p1_raw[0], p1_raw[1])
                        p2 = _apply(local_mat, p2_raw[0], p2_raw[1])
                        if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) * display_scale >= 6.0:
                            line_segments.append((p1[0], p1[1], p2[0], p2[1], dashed))

        for child in elem:
            _walk(child, local_mat, props, font_size, grid_here, legend_here, title_here)

    _walk(root, IDENTITY, {}, 12.0, False, False, False)

    # Mark texts sitting inside an opaque background box (e.g., legend or callout box) as masked
    for tb in text_boxes:
        if tb.masked:
            continue
        for rx0, ry0, rx1, ry1 in opaque_rects:
            if tb.x0 >= rx0 - 2.0 and tb.x1 <= rx1 + 2.0 and tb.y0 >= ry0 - 2.0 and tb.y1 <= ry1 + 2.0:
                tb.masked = True
                break

    # Scale boxes to display px for consistent thresholds with neutral.py
    pad_user = 1.5 / display_scale if display_scale > 0 else 1.5
    shrunk: list[tuple[_TextBox, tuple[float, float, float, float]]] = []
    for tb in text_boxes:
        w = tb.x1 - tb.x0
        h = tb.y1 - tb.y0
        if w > 2 * pad_user and h > 2 * pad_user:
            box = (tb.x0 + pad_user, tb.y0 + pad_user, tb.x1 - pad_user, tb.y1 - pad_user)
        else:
            box = (tb.x0, tb.y0, tb.x1, tb.y1)
        shrunk.append((tb, box))

    overlaps: list[str] = []
    for i, (ti, bi) in enumerate(shrunk):
        for tj, bj in shrunk[i + 1 :]:
            if _box_overlaps(bi, bj):
                overlaps.append(f"{ti.text!r} / {tj.text!r}")

    struck: list[str] = []
    struck_seen: set[tuple[int, str]] = set()
    for x1, y1, x2, y2, dashed in line_segments:
        what = "dashed reference line" if dashed else "data line"
        for idx_t, (tb, box) in enumerate(shrunk):
            if tb.masked:
                continue
            if _segment_intersects_box(x1, y1, x2, y2, box[0], box[1], box[2], box[3]):
                key = (idx_t, what)
                if key not in struck_seen:
                    struck_seen.add(key)
                    struck.append(f"{tb.text!r} crossed by a {what}")

    margin_user = 2.0 / display_scale if display_scale > 0 else 2.0
    clipped: list[str] = []
    for tb in text_boxes:
        if (
            tb.x0 < vb_x - margin_user
            or tb.y0 < vb_y - margin_user
            or tb.x1 > vb_x + vb_w + margin_user
            or tb.y1 > vb_y + vb_h + margin_user
        ):
            clipped.append(repr(tb.text[:40]))

    text_faults: list[str] = []
    for tb in text_boxes:
        txt = tb.text
        plain = re.sub(r"\$[^$]*\$", "", txt)
        if "%%" in plain:
            text_faults.append(f"doubled %: {txt!r}")
        m = _DOUBLED.search(plain)
        if m and not m.group(1).isdigit():
            text_faults.append(f"repeated words {m.group(0)!r}: {txt!r}")
        if _ASCII_MINUS.search(plain) and not re.search(r"\d{4}-\d{2}", plain):
            text_faults.append(f"ASCII hyphen as minus sign: {txt!r}")
        if _JUNK.search(plain):
            text_faults.append(f"junk value: {txt!r}")

    sizes = sorted(((tb.font_px, tb.text) for tb in text_boxes), key=lambda x: x[0])
    min_text_px = round(sizes[0][0], 1) if sizes else None
    small_texts = [f"{txt[:40]!r} {px:.1f} px" for px, txt in sizes if px < MIN_TEXT_PX][:6]
    small_text_count = sum(1 for px, _ in sizes if px < MIN_TEXT_PX)

    text_strings = [tb.text for tb in text_boxes]
    all_text = " ".join(text_strings)

    # Heuristic headlines: explicit title hints, or texts in top 25% of canvas near max font size
    headlines: list[str] = []
    if text_boxes:
        max_font = max(tb.font_px for tb in text_boxes)
        top_cutoff = vb_y + 0.25 * vb_h
        for tb in text_boxes:
            is_head = tb.is_title_hint or (
                tb.y0 <= top_cutoff and tb.font_px >= max_font * 0.85 and len(tb.text) >= 4
            )
            if is_head and tb.text not in headlines:
                headlines.append(tb.text)

    return {
        "svg_px": [round(nom_w, 1), round(nom_h, 1)],
        "viewbox": [round(vb_x, 2), round(vb_y, 2), round(vb_w, 2), round(vb_h, 2)],
        "display_width_px": round(shown_px, 1),
        "texts": len(text_boxes),
        "text_strings": text_strings,
        "headlines": headlines,
        "min_text_px": min_text_px,
        "small_texts": small_texts,
        "small_text_count": small_text_count,
        "overlaps": overlaps,
        "struck": struck,
        "clipped": clipped,
        "text_faults": text_faults,
        "uncertainty_named": bool(UNCERTAINTY_WORDS.search(all_text)),
        "text_as_paths_suspected": (len(text_boxes) == 0 and has_path_text_groups),
    }


def svg_checks(audit: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return standard defect checks (same contract as ``neutral.neutral_checks``)."""
    gate = (
        "text_legible",
        "no_text_overlap",
        "no_text_struck_by_lines",
        "text_well_formed",
        "no_text_clipped",
    )
    if not audit:
        return [{"name": n, "passed": False, "detail": "no audited SVG"} for n in gate]
    min_px = audit.get("min_text_px")
    legible = isinstance(min_px, (int, float)) and min_px >= MIN_TEXT_PX
    return [
        {
            "name": "text_legible",
            "passed": legible,
            "detail": (
                f"smallest text {min_px} px at {audit.get('display_width_px')} px display"
                + (
                    f"; {audit.get('small_text_count')} texts under {MIN_TEXT_PX:g} px, e.g. "
                    + ", ".join(audit.get("small_texts", [])[:3])
                    if audit.get("small_texts")
                    else ""
                )
            ),
        },
        {"name": "no_text_overlap", "passed": not audit.get("overlaps"), "detail": "; ".join(audit.get("overlaps", [])[:4])},
        {"name": "no_text_struck_by_lines", "passed": not audit.get("struck"), "detail": "; ".join(audit.get("struck", [])[:4])},
        {"name": "text_well_formed", "passed": not audit.get("text_faults"), "detail": "; ".join(audit.get("text_faults", [])[:4])},
        {
            "name": "no_text_clipped",
            "passed": not audit.get("clipped"),
            "detail": (
                "texts past the canvas edge: " + ", ".join(audit.get("clipped", [])[:4])
                if audit.get("clipped")
                else ""
            ),
        },
    ]
