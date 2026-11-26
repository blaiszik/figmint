"""``mint.check``: audit a Matplotlib figure you already drew, against its own data.

Most figures an agent ships are plain Matplotlib. ``check`` meets them where they
are, without a rewrite:

- **Read the data back.** Bars, lines, error bars, scatter points and images are
  read out of the drawn artists, and the same kind of facts ``mint.explain``
  reports are computed from them (highest, gaps, ratios, start-to-end change,
  whether two intervals overlap, correlation).
- **Check the claim.** Every number the title (or ``claim=``) states is looked up
  among those values and their differences, ratios, percentage changes and shares.
  A number found nowhere is ``claim_number_mismatch``.
- **Measure it as the reader sees it.** The figure is rendered as it would be saved
  and scaled to the width it is shown at (700 px chat column by default), then
  audited for text under 11 px, overlapping or line-struck text, malformed text and
  text past the canvas edge, plus truncated bar baselines and rainbow colormaps.

``report["ship"]`` is true when there is no error, no text defect and every stated
number is found in the data.
"""

from __future__ import annotations

import io
import itertools
import json
import math
import os
import re
import struct
from collections.abc import Mapping, Sequence
from typing import Any

from .epistemic import _HEDGE_RE, claim_numbers, pair_derivations, stated_match, unit_scale_factor

__all__ = [
    "MIN_TEXT_PX",
    "WIDTHS",
    "FigureCheck",
    "check",
    "check_notebook",
    "check_script",
    "format_report",
]

#: Display widths, in CSS pixels, a PNG is scaled down to (never up).
WIDTHS: dict[str, int] = {"narrow": 450, "chat": 700, "slide": 1280}
#: Smallest legible text at display size, the same bar ``mint.explain`` holds.
MIN_TEXT_PX = 11.0
#: Checks whose failure blocks ``ship``, besides any error.
BLOCKING = frozenset(
    {"text_too_small", "text_overlaps", "text_struck_by_line", "text_malformed",
     "text_clipped", "claim_number_mismatch"}
)  # fmt: skip

_BANNED_CMAPS = frozenset({"jet", "rainbow", "hsv", "gist_rainbow", "nipy_spectral", "prism", "flag"})
_UNCERTAINTY_WORDS = re.compile(
    r"(\bCI\b|confidence|interval|\bs\.?d\.?\b|\bSD\b|\bSEM?\b|\bs\.e\.m?\.?|standard (?:deviation|error)"
    r"|±|\bIQR\b|quartile|percentile|\bseeds?\b|replicates?|triplicates?|\bwells?\b|\bn\s*=\s*\d"
    r"|margin of error|\brange\b|\bmin[–-]max\b)",
    re.IGNORECASE,
)
_DOUBLED = re.compile(r"\b(\w+(?:\s+\w+)?)\s+\1\b", re.IGNORECASE)
_ASCII_MINUS = re.compile(r"(?:^|[\s(\[=:,])-\d")
_JUNK = re.compile(r"\b(nan|NaN|None|inf|-inf)\b")
_UNIT_IN_LABEL = re.compile(r"[(\[]([^()\[\]]{1,12})[)\]]\s*$")
_COUNT_BEFORE = re.compile(r"\b[nN]\s*=\s*$")
_MAX_POINTS = 200  # per series: beyond this only summary values become claim candidates


# --------------------------------------------------------------------------- report


class FigureCheck(dict):  # type: ignore[type-arg]
    """What :func:`check` found: a plain dict (``json.dumps`` holds every key).

    Keys: ``ship``, ``claim`` (the text checked and each number with where it was
    found), ``issues`` (rule, severity, message, fix_hint), ``advisories``,
    ``panels`` (per axes: kind, title, values read back, facts) and ``display``
    (PNG size, the width it is shown at, the smallest text in display pixels).
    ``print(report)`` shows a compact view.
    """

    @property
    def ship(self) -> bool:
        return bool(self.get("ship"))

    def compact(self) -> dict[str, Any]:
        claim = self.get("claim") or {}
        return {
            "ship": self.get("ship"),
            "claim": claim.get("text"),
            "numbers": [
                f"{n['text']}: "
                + (n["how"] if n["found"] else "NOT FOUND in the data"
                   + (f"; closest: {n['nearest']}" if n.get("nearest") else ""))
                for n in claim.get("numbers", [])
            ],
            "issues": [f"{i['rule']}: {i['message']}" for i in self.get("issues", [])],
            "advisories": [a["rule"] for a in self.get("advisories", [])],
            "facts": [f for p in self.get("panels", []) for f in p.get("facts", [])][:6],
            "display": {k: (self.get("display") or {}).get(k)
                        for k in ("png_px", "shown_px", "min_text_px")},
        }

    def __str__(self) -> str:
        return json.dumps(self.compact(), indent=2, ensure_ascii=False)


def _issue(rule: str, severity: str, message: str, fix_hint: str, axes: int | None = None) -> dict:
    out = {"rule": rule, "severity": severity, "message": message, "fix_hint": fix_hint}
    if axes is not None:
        out["axes"] = axes
    return out


# --------------------------------------------------------------------------- helpers


def _fmt(v: float) -> str:
    if not math.isfinite(v):
        return str(v)
    a = abs(v)
    if a == 0:
        return "0"
    if a >= 1000:
        return f"{v:,.0f}"
    if a >= 100:
        return f"{v:.0f}" if float(v).is_integer() else f"{v:.1f}"
    return f"{v:.3g}"


def _fmt_pct(v: float) -> str:
    return f"{v:.0f}%" if abs(v) >= 10 else f"{v:.1f}%"


def _finite(values: Any) -> list[float]:
    import numpy as np

    arr = np.ma.filled(np.ma.asarray(values, dtype=float), np.nan).ravel()
    return [float(v) for v in arr if math.isfinite(v)]


def _png_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    w, h = struct.unpack(">II", data[16:24])
    return int(w), int(h)


def _resolve_figure(obj: Any) -> Any:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure, SubFigure

    if obj is None:
        import matplotlib.pyplot as plt

        if not plt.get_fignums():
            raise TypeError("mint.check() found no open figure; pass the Figure or Axes to check.")
        return plt.gcf()
    if isinstance(obj, Axes):
        return obj.get_figure(root=True) if _has_root_kw() else obj.figure
    if isinstance(obj, SubFigure):
        return obj.get_figure(root=True) if _has_root_kw() else obj.figure
    if isinstance(obj, Figure):
        return obj
    if hasattr(obj, "takeaway") and hasattr(obj, "fig"):
        raise TypeError(
            "mint.check() audits plain Matplotlib figures; a mint.explain figure already "
            "carries its checks in fig.save(...) (summary['ship'], summary['issues'])."
        )
    raise TypeError(f"mint.check() takes a Matplotlib Figure or Axes, not {type(obj).__name__}.")


def _has_root_kw() -> bool:
    import inspect

    from matplotlib.artist import Artist

    return "root" in inspect.signature(Artist.get_figure).parameters


class _AggCanvas:
    """Draw with Agg for the audit when the figure lives on a GUI canvas, then put it back."""

    def __init__(self, fig: Any) -> None:
        self.fig = fig
        self.original = None

    def __enter__(self) -> Any:
        from matplotlib.backends.backend_agg import FigureCanvasAgg

        if not isinstance(self.fig.canvas, FigureCanvasAgg):
            self.original = self.fig.canvas
            FigureCanvasAgg(self.fig)
        return self.fig.canvas

    def __exit__(self, *exc: object) -> None:
        if self.original is not None:
            self.fig.set_canvas(self.original)


def _drawn_texts(fig: Any) -> list[Any]:
    from matplotlib.text import Text

    drawn: list[Any] = []
    original = Text.draw

    def _recording_draw(self: Text, renderer: Any) -> Any:
        if self.get_visible() and self.get_text().strip() and self.get_alpha() != 0:
            drawn.append(self)
        return original(self, renderer)

    Text.draw = _recording_draw  # type: ignore[method-assign]
    try:
        fig.canvas.draw()
    finally:
        Text.draw = original  # type: ignore[method-assign]
    return list(dict.fromkeys(drawn))


def _masked(t: Any, legend_texts: set[int]) -> bool:
    """Text on an opaque box (a framed legend or a bbox patch) hides the lines under it."""
    if id(t) in legend_texts:
        return True
    patch = t.get_bbox_patch()
    if patch is None or not patch.get_visible() or not patch.get_fill():
        return False
    alpha = patch.get_facecolor()[3] if patch.get_alpha() is None else patch.get_alpha()
    return alpha >= 0.5


def _is_colorbar_axes(ax: Any) -> bool:
    """True for Matplotlib/Seaborn colorbar axes so they are excluded from panels and axis checks."""
    label = str(ax.get_label() or "")
    if label == "<colorbar>" or label.startswith("<colorbar"):
        return True
    return getattr(ax, "_colorbar", None) is not None


def _headline(fig: Any, renderer: Any) -> str | None:
    """Where a reader looks for the claim: the largest figure-level text or title, the
    highest one on a tie (a suptitle over a subtitle, a title over a footnote)."""
    cands = [getattr(fig, "_suptitle", None), *fig.texts]
    for ax in fig.axes:
        if ax.get_visible() and not _is_colorbar_axes(ax):
            cands += [ax.title, getattr(ax, "_left_title", None), getattr(ax, "_right_title", None)]
    shown = [t for t in cands if t is not None and t.get_visible() and t.get_text().strip()]
    if not shown:
        return None
    best = max(shown, key=lambda t: (round(t.get_fontsize(), 1), t.get_window_extent(renderer).y1))
    return best.get_text().strip()


# --------------------------------------------------------------------------- reading data back


def _tick_names(ax: Any, axis: str) -> list[tuple[float, str]]:
    ticks = ax.get_xticks() if axis == "x" else ax.get_yticks()
    labels = ax.get_xticklabels() if axis == "x" else ax.get_yticklabels()
    out = []
    for loc, lab in zip(ticks, labels):
        text = lab.get_text().strip()
        if text:
            out.append((float(loc), text))
    return out


def _is_numeric_label(text: str) -> bool:
    cleaned = text.replace("\N{MINUS SIGN}", "-").replace(",", "").replace("%", "").strip()
    try:
        float(cleaned)
    except ValueError:
        return False
    return True


def _name_at(pos: float, ticks: list[tuple[float, str]], spacing: float, fallback: str) -> str:
    named = [(abs(loc - pos), text) for loc, text in ticks if not _is_numeric_label(text)]
    if named:
        dist, text = min(named)
        if dist <= spacing / 2 + 1e-9:
            return text
    return fallback


def _spacing(positions: Sequence[float]) -> float:
    ps = sorted(set(positions))
    gaps = [b - a for a, b in itertools.pairwise(ps) if b - a > 0]
    return min(gaps) if gaps else 1.0


def _series_label(artist: Any, fallback: str) -> str:
    lab = artist.get_label()
    return fallback if not lab or str(lab).startswith("_") else str(lab)


def _is_histogram_container(ax: Any, container: Any) -> bool:
    """True when a BarContainer's patches form contiguous histogram bins on a numeric axis."""
    patches = list(container.patches)
    if len(patches) < 4:
        return False
    orientation = getattr(container, "orientation", None) or "vertical"
    bin_axis = "x" if orientation == "vertical" else "y"
    ticks = _tick_names(ax, bin_axis)
    if any(not _is_numeric_label(t) for _, t in ticks):
        return False
    geom: list[tuple[float, float]] = []
    for r in patches:
        start = float(r.get_x() if bin_axis == "x" else r.get_y())
        span = float(r.get_width() if bin_axis == "x" else r.get_height())
        if not (math.isfinite(start) and math.isfinite(span)) or span <= 0:
            return False
        geom.append((start, span))
    geom.sort(key=lambda pair: pair[0])
    touching = 0
    for (s0, w0), (s1, w1) in itertools.pairwise(geom):
        gap = abs(s1 - (s0 + w0))
        if gap <= 0.05 * max(w0, w1, 1e-12):
            touching += 1
    return touching >= max(3, int(0.8 * (len(geom) - 1)))


def _read_histograms(
    ax: Any,
    containers: Sequence[Any],
) -> dict[str, dict[str, Any]]:
    """Extract summary statistics from contiguous-edge histogram BarContainers."""
    out: dict[str, dict[str, Any]] = {}
    for k, c in enumerate(containers):
        orientation = getattr(c, "orientation", None) or "vertical"
        bin_axis = "x" if orientation == "vertical" else "y"
        bins: list[tuple[float, float, float, float, float]] = []
        for r in c.patches:
            lo = float(r.get_x() if bin_axis == "x" else r.get_y())
            span = float(r.get_width() if bin_axis == "x" else r.get_height())
            h = float(r.get_height() if bin_axis == "x" else r.get_width())
            if math.isfinite(lo) and math.isfinite(span) and math.isfinite(h) and span > 0:
                bins.append((lo, lo + span, lo + span / 2.0, h, span))
        if not bins:
            continue
        bins.sort(key=lambda b: b[0])
        name = _series_label(c, f"histogram {k + 1}" if len(containers) > 1 else "histogram")
        if name in out:
            name = f"{name} ({k + 1})"
        total_height = sum(b[3] for b in bins)
        weights = [max(0.0, b[3] * b[4]) for b in bins]
        total_w = sum(weights)
        peak = max(bins, key=lambda b: b[3])
        if total_w > 0:
            mean_est = sum(b[2] * w for b, w in zip(bins, weights)) / total_w
            half = 0.5 * total_w
            cum = 0.0
            median_est = peak[2]
            for (lo, hi, center, _h, _w), wt in zip(bins, weights):
                if cum + wt >= half and wt > 0:
                    frac = (half - cum) / wt
                    median_est = lo + frac * (hi - lo)
                    break
                cum += wt
        else:
            mean_est = peak[2]
            median_est = peak[2]
        nonempty = [b for b in bins if b[3] > 0]
        range_lo = nonempty[0][0] if nonempty else bins[0][0]
        range_hi = nonempty[-1][1] if nonempty else bins[-1][1]
        out[name] = {
            "bins": len(bins),
            "total": total_height,
            "peak_center": peak[2],
            "peak_range": [peak[0], peak[1]],
            "peak_height": peak[3],
            "median": median_est,
            "mean": mean_est,
            "range": [range_lo, range_hi],
            "orientation": orientation,
        }
    return out


def _read_bars(ax: Any) -> tuple[dict[str, dict[str, float]], str, list[Any], list[Any]]:
    """Bar values as {series: {category: value}}, orientation, bar containers, and hist containers."""
    from matplotlib.container import BarContainer

    all_containers = [c for c in ax.containers if isinstance(c, BarContainer) and len(c.patches)]
    hist_containers = [c for c in all_containers if _is_histogram_container(ax, c)]
    containers = [c for c in all_containers if c not in hist_containers]
    series: dict[str, dict[str, float]] = {}
    orientation = "vertical"
    if not containers:
        return series, orientation, [], hist_containers
    orientation = getattr(containers[0], "orientation", None) or "vertical"
    cat_axis = "x" if orientation == "vertical" else "y"
    ticks = _tick_names(ax, cat_axis)
    centers = []
    for c in containers:
        for r in c.patches:
            centers.append(r.get_x() + r.get_width() / 2 if cat_axis == "x" else r.get_y() + r.get_height() / 2)
    tick_locs = [loc for loc, _ in ticks]
    spacing = _spacing(tick_locs) if len(tick_locs) > 1 else _spacing(centers)
    for k, c in enumerate(containers):
        name = _series_label(c, f"series {k + 1}" if len(containers) > 1 else "bars")
        vals: dict[str, float] = {}
        datavalues = getattr(c, "datavalues", None)
        for i, r in enumerate(c.patches):
            if datavalues is not None and i < len(datavalues):
                v = float(datavalues[i])
            else:
                v = r.get_height() if cat_axis == "x" else r.get_width()
            center = r.get_x() + r.get_width() / 2 if cat_axis == "x" else r.get_y() + r.get_height() / 2
            cat = _name_at(center, ticks, spacing, _fmt(center))
            if cat in vals:
                cat = f"{cat} ({i + 1})"
            if math.isfinite(v):
                vals[cat] = v
        series[name] = vals
    return series, orientation, containers, hist_containers


def _read_errorbars(ax: Any) -> list[dict[str, Any]]:
    """Each error-bar set as {axis, points: [(pos, value, lo, hi)], label}."""
    from matplotlib.container import ErrorbarContainer

    out = []
    for c in ax.containers:
        if not isinstance(c, ErrorbarContainer):
            continue
        data_line, _caps, barcols = c.lines
        axis = "y" if c.has_yerr else "x"
        if c.has_xerr and c.has_yerr:
            axis = "y"
        xs = _finite(data_line.get_xdata(orig=False)) if data_line is not None else []
        ys = _finite(data_line.get_ydata(orig=False)) if data_line is not None else []
        segs: list[tuple[float, float, float]] = []
        for col in barcols:
            for seg in col.get_segments():
                if len(seg) < 2:
                    continue
                (x0, y0), (x1, y1) = seg[0], seg[-1]
                if axis == "y" and abs(x0 - x1) < 1e-12:
                    segs.append((float(x0), float(min(y0, y1)), float(max(y0, y1))))
                elif axis == "x" and abs(y0 - y1) < 1e-12:
                    segs.append((float(y0), float(min(x0, x1)), float(max(x0, x1))))
        points = []
        for pos, lo, hi in segs:
            value = None
            if xs and ys:
                pairs = list(zip(xs, ys)) if axis == "y" else list(zip(ys, xs))
                near = min(pairs, key=lambda p: abs(p[0] - pos))
                if abs(near[0] - pos) < 1e-9 * max(1.0, abs(pos)):
                    value = near[1]
            points.append((pos, value, lo, hi))
        out.append({"axis": axis, "points": points, "label": _series_label(c, "")})
    return out


def _errorbar_line_ids(ax: Any) -> set[int]:
    from matplotlib.container import ErrorbarContainer

    ids: set[int] = set()
    for c in ax.containers:
        if isinstance(c, ErrorbarContainer):
            data_line, caps, barcols = c.lines
            if data_line is not None:
                ids.add(id(data_line))
            ids |= {id(x) for x in caps}
            ids |= {id(x) for x in barcols}
    return ids


def _is_reference_line(ax: Any, ln: Any) -> tuple[str, float] | None:
    """axhline/axvline: one coordinate in axes space, the other a constant in data space."""
    if ln.get_transform() == ax.transData:
        return None
    xs, ys = _finite(ln.get_xdata(orig=False)), _finite(ln.get_ydata(orig=False))
    if len(ys) >= 2 and len(set(ys)) == 1:
        return ("y", ys[0])
    if len(xs) >= 2 and len(set(xs)) == 1:
        return ("x", xs[0])
    return None


def _crossings(x: Sequence[float], a: Sequence[float], b: Sequence[float]) -> list[float]:
    out = []
    for i in range(1, min(len(x), len(a), len(b))):
        d0, d1 = a[i - 1] - b[i - 1], a[i] - b[i]
        if d1 == 0 and d0 != 0:  # touches exactly at a data point
            out.append(x[i])
            continue
        if d0 == 0 or d0 * d1 >= 0:
            continue
        t = d0 / (d0 - d1)
        out.append(x[i - 1] + t * (x[i] - x[i - 1]))
    return out


class _Candidates:
    """Every number a claim about this figure may state, with how it was derived."""

    def __init__(self) -> None:
        self.levels: list[tuple[str, float]] = []
        self.pairs: list[tuple[str, float, float]] = []  # (how, a, b)
        self.shares: list[tuple[str, float]] = []
        self.other: list[tuple[str, float]] = []  # sums, slopes, r, x positions
        self.series: list[tuple[str, list[float], list[float]]] = []  # for "reaches y at x" claims

    def add_group(self, values: Mapping[str, float], where: str) -> None:
        items = [(k, v) for k, v in values.items() if math.isfinite(v)]
        for k, v in items:
            self.levels.append((f"{k} ({where})" if where else k, v))
        if len(items) <= 60:
            for i, (ka, va) in enumerate(items):
                for kb, vb in items[i + 1:]:
                    self.pairs.append((f"{ka} vs {kb}" + (f" ({where})" if where else ""), va, vb))
        pos = [(k, v) for k, v in items if v > 0]
        total = sum(v for _, v in pos)
        if len(pos) >= 2 and total > 0:
            for k, v in pos:
                self.shares.append((f"{k} share of {where or 'total'} ({_fmt(v)} of {_fmt(total)})",
                                    100.0 * v / total))
            self.other.append((f"total of {where or 'values'}", total))


def _box_bounds_from_verts(verts: Any) -> tuple[float, float, float, float] | None:
    """Return ``(x0, x1, y0, y1)`` if ``verts`` form a closed box/notched-box polygon."""
    import numpy as np

    arr = np.asarray(verts, dtype=float)
    if arr.ndim != 2 or arr.shape[1] != 2 or len(arr) < 4 or len(arr) > 14:
        return None
    if not np.isfinite(arr).all():
        return None
    # Strip trailing closing vertices equal to the start vertex (PathPatch adds CLOSEPOLY duplicate)
    pts = arr
    while len(pts) > 1 and np.allclose(pts[0], pts[-1], atol=1e-9):
        pts = pts[:-1]
    if len(pts) not in {4, 6, 8, 10}:
        return None
    xs, ys = pts[:, 0], pts[:, 1]
    x0, x1 = float(xs.min()), float(xs.max())
    y0, y1 = float(ys.min()), float(ys.max())
    if x1 <= x0 or y1 <= y0:
        return None
    # Standard 4-corner rectangle: every point sits on the bounding box perimeter.
    if len(pts) == 4:
        ux = len({round(float(v), 7) for v in xs})
        uy = len({round(float(v), 7) for v in ys})
        if ux != 2 or uy != 2:
            return None
    return (x0, x1, y0, y1)


def _read_boxplots(
    ax: Any,
    skip_line_ids: set[int],
) -> tuple[dict[str, dict[str, float]], str, set[int]]:
    """Detect Matplotlib/Seaborn boxplot clusters so their lines are not misread as data lines.

    Returns ``(boxes_by_group, orientation, consumed_line_ids)``.
    """
    from matplotlib.container import BarContainer
    from matplotlib.patches import PathPatch, Polygon

    bar_patch_ids = {
        id(r) for c in ax.containers if isinstance(c, BarContainer) for r in c.patches
    }
    raw_boxes: list[tuple[float, float, float, float, int | None]] = []
    # 1. patch_artist=True (and sns.boxplot): PathPatch / Polygon boxes in ax.patches
    for patch in ax.patches:
        if id(patch) in bar_patch_ids or not patch.get_visible():
            continue
        if isinstance(patch, (PathPatch, Polygon)):
            bounds = _box_bounds_from_verts(patch.get_path().vertices)
            if bounds is not None:
                raw_boxes.append((*bounds, None))
    # 2. patch_artist=False (default ax.boxplot): closed 5-point Line2D rectangles in ax.lines
    for ln in ax.lines:
        if id(ln) in skip_line_ids or not ln.get_visible() or _is_reference_line(ax, ln) is not None:
            continue
        xs = _finite(ln.get_xdata(orig=False))
        ys = _finite(ln.get_ydata(orig=False))
        if len(xs) == len(ys) and 5 <= len(xs) <= 12:
            bounds = _box_bounds_from_verts(list(zip(xs, ys)))
            if bounds is not None:
                raw_boxes.append((*bounds, id(ln)))
    if not raw_boxes:
        return {}, "vertical", set()

    # Collect 2-point candidate segments (whiskers, caps, medians) and marker-only lines (fliers).
    segs: list[tuple[int, float, float, float, float]] = []
    flier_lines: list[tuple[int, list[float], list[float]]] = []
    box_line_candidates = {lid for *_, lid in raw_boxes if lid is not None}
    for ln in ax.lines:
        lid = id(ln)
        if lid in skip_line_ids or lid in box_line_candidates or not ln.get_visible():
            continue
        if _is_reference_line(ax, ln) is not None:
            continue
        xs = _finite(ln.get_xdata(orig=False))
        ys = _finite(ln.get_ydata(orig=False))
        if len(xs) != len(ys) or not xs:
            continue
        ls = ln.get_linestyle()
        if ls in ("None", "", " "):
            flier_lines.append((lid, xs, ys))
        elif len(xs) == 2:
            segs.append((lid, xs[0], ys[0], xs[1], ys[1]))

    def _match_orientation(orient: str) -> tuple[list[tuple[float, dict[str, float]]], set[int]]:
        matched: list[tuple[float, dict[str, float]]] = []
        used: set[int] = set()
        for x0, x1, y0, y1, box_lid in raw_boxes:
            if orient == "vertical":
                c0, c1, v0, v1 = x0, x1, y0, y1
            else:
                c0, c1, v0, v1 = y0, y1, x0, x1
            center = 0.5 * (c0 + c1)
            cspan = max(c1 - c0, 1e-12)
            vspan = max(v1 - v0, 1e-12)
            ctol = max(1e-5, 0.12 * cspan)
            vtol = max(1e-5, 1e-3 * vspan)

            medians: list[float] = []
            whisker_lo = v0
            whisker_hi = v1
            has_whisker = False
            local_used: set[int] = set()
            if box_lid is not None:
                local_used.add(box_lid)

            for lid, sx0, sy0, sx1, sy1 in segs:
                if orient == "vertical":
                    sc0, sc1, sv0, sv1 = sx0, sx1, sy0, sy1
                else:
                    sc0, sc1, sv0, sv1 = sy0, sy1, sx0, sx1
                # Whisker: constant category coordinate at center, one endpoint at v0 or v1
                if abs(sc0 - sc1) <= ctol and abs(0.5 * (sc0 + sc1) - center) <= ctol:
                    slo, shi = min(sv0, sv1), max(sv0, sv1)
                    if abs(shi - v0) <= vtol and slo <= v0 + vtol:
                        whisker_lo = min(whisker_lo, slo)
                        has_whisker = True
                        local_used.add(lid)
                        continue
                    if abs(slo - v1) <= vtol and shi >= v1 - vtol:
                        whisker_hi = max(whisker_hi, shi)
                        has_whisker = True
                        local_used.add(lid)
                        continue
                # Median (or mean) line: constant value coordinate inside [v0, v1], spans box width
                if abs(sv0 - sv1) <= vtol and v0 - vtol <= sv0 <= v1 + vtol:
                    smin, smax = min(sc0, sc1), max(sc0, sc1)
                    if smin >= c0 - ctol and smax <= c1 + ctol and (smax - smin) >= 0.25 * cspan:
                        medians.append(0.5 * (sv0 + sv1))
                        local_used.add(lid)
                        continue

            if not medians and not has_whisker:
                continue

            # Collect caps at whisker_lo / whisker_hi centered on `center`
            for lid, sx0, sy0, sx1, sy1 in segs:
                if lid in local_used:
                    continue
                if orient == "vertical":
                    sc0, sc1, sv0, sv1 = sx0, sx1, sy0, sy1
                else:
                    sc0, sc1, sv0, sv1 = sy0, sy1, sx0, sx1
                if abs(sv0 - sv1) <= vtol and abs(0.5 * (sc0 + sc1) - center) <= ctol:
                    v_cap = 0.5 * (sv0 + sv1)
                    if abs(v_cap - whisker_lo) <= vtol or abs(v_cap - whisker_hi) <= vtol:
                        local_used.add(lid)

            # Collect flier marker lines aligned with this box center
            for lid, fxs, fys in flier_lines:
                coords = fxs if orient == "vertical" else fys
                if all(abs(c - center) <= ctol for c in coords):
                    local_used.add(lid)

            med = medians[0] if medians else 0.5 * (v0 + v1)
            matched.append((
                center,
                {
                    "median": float(med),
                    "q1": float(v0),
                    "q3": float(v1),
                    "iqr": float(v1 - v0),
                    "whisker_lo": float(whisker_lo),
                    "whisker_hi": float(whisker_hi),
                },
            ))
            used |= local_used
        return matched, used

    v_matched, v_used = _match_orientation("vertical")
    h_matched, h_used = _match_orientation("horizontal")
    if len(h_matched) > len(v_matched):
        chosen, orient, used = h_matched, "horizontal", h_used
    else:
        chosen, orient, used = v_matched, "vertical", v_used
    if not chosen:
        return {}, "vertical", set()

    chosen.sort(key=lambda item: item[0])
    cat_axis = "x" if orient == "vertical" else "y"
    ticks = _tick_names(ax, cat_axis)
    centers = [pos for pos, _ in chosen]
    spacing = _spacing([loc for loc, _ in ticks]) if len(ticks) > 1 else _spacing(centers)
    out: dict[str, dict[str, float]] = {}
    for k, (pos, stats) in enumerate(chosen):
        name = _name_at(pos, ticks, spacing, f"group {k + 1}")
        if name in out:
            name = f"{name} ({k + 1})"
        out[name] = stats
    return out, orient, used


def _violin_body_profile(coll: Any) -> tuple[str, float, list[tuple[float, float]]] | None:
    """Return ``(orientation, center_pos, [(val, half_width), ...])`` for a symmetric violin body."""
    import numpy as np

    paths = coll.get_paths()
    if len(paths) != 1:
        return None
    verts = np.asarray(paths[0].vertices, dtype=float)
    if verts.ndim != 2 or verts.shape[1] != 2 or len(verts) < 12 or not np.isfinite(verts).all():
        return None

    for orient, v_idx, c_idx in (("vertical", 1, 0), ("horizontal", 0, 1)):
        vs = verts[:, v_idx]
        cs = verts[:, c_idx]
        c_span = float(cs.max() - cs.min())
        v_span = float(vs.max() - vs.min())
        if c_span <= 0 or v_span <= 0:
            continue
        buckets: dict[float, list[float]] = {}
        scale = 1e5 / max(v_span, 1e-12)
        for v, c in zip(vs, cs):
            key = round(float(v) * scale) / scale
            buckets.setdefault(key, []).append(float(c))
        mids: list[float] = []
        profile: list[tuple[float, float]] = []
        for v_key in sorted(buckets):
            cvals = buckets[v_key]
            lo, hi = min(cvals), max(cvals)
            if hi - lo > 0.02 * c_span:
                mids.append(0.5 * (lo + hi))
            profile.append((v_key, 0.5 * (hi - lo)))
        if len(mids) >= 5 and (max(mids) - min(mids)) <= 0.03 * c_span:
            mids_s = sorted(mids)
            center = mids_s[len(mids_s) // 2]
            return orient, float(center), profile
    return None


def _profile_quantile(
    profile: Sequence[tuple[float, float]],
    weights: Sequence[float],
    total_w: float,
    vmin: float,
    vmax: float,
    q: float,
) -> float:
    if total_w <= 0:
        return vmin + q * (vmax - vmin)
    target = q * total_w
    cum = 0.0
    for (v, _), w in zip(profile, weights):
        cum += w
        if cum >= target:
            return v
    return vmax


def _read_violins(
    ax: Any,
    has_data_lines: bool,
) -> tuple[dict[str, dict[str, float]], str, set[int]]:
    """Detect Matplotlib/Seaborn violinplot bodies and extract per-group stats."""
    from matplotlib.collections import LineCollection, PathCollection, PolyCollection

    candidates: list[tuple[Any, str, float, list[tuple[float, float]]]] = []
    for coll in ax.collections:
        if isinstance(coll, PolyCollection) and not isinstance(coll, PathCollection) and coll.get_visible():
            prof = _violin_body_profile(coll)
            if prof is not None:
                candidates.append((coll, *prof))
    if not candidates:
        return {}, "vertical", set()

    # Collect LineCollection segments (cbars, cmins, cmaxes, cmedians) to confirm violins & read medians.
    line_segs: list[tuple[float, float, float, float]] = []
    for coll in ax.collections:
        if isinstance(coll, LineCollection) and coll.get_visible():
            for seg in coll.get_segments():
                if len(seg) >= 2:
                    (x0, y0), (x1, y1) = seg[0], seg[-1]
                    if all(math.isfinite(float(u)) for u in (x0, y0, x1, y1)):
                        line_segs.append((float(x0), float(y0), float(x1), float(y1)))

    # A single horizontal symmetric band alongside a data line is a fill_between band, not a violin.
    orient = candidates[0][1]
    if orient == "horizontal" and len(candidates) == 1 and has_data_lines and not line_segs:
        return {}, "vertical", set()
    # Require either multiple bodies, vertical orientation, or matching LineCollection bars.
    if len(candidates) == 1 and not line_segs and orient != "vertical":
        return {}, "vertical", set()

    same_orient = [c for c in candidates if c[1] == orient]
    same_orient.sort(key=lambda item: item[2])
    cat_axis = "x" if orient == "vertical" else "y"
    ticks = _tick_names(ax, cat_axis)
    centers = [item[2] for item in same_orient]
    spacing = _spacing([loc for loc, _ in ticks]) if len(ticks) > 1 else _spacing(centers)
    ctol = max(1e-4, 0.08 * spacing)

    out: dict[str, dict[str, float]] = {}
    used_colls: set[int] = set()
    for k, (coll, _o, pos, profile) in enumerate(same_orient):
        used_colls.add(id(coll))
        vals = [v for v, _ in profile]
        vmin, vmax = min(vals), max(vals)
        vtol = max(1e-5, 0.01 * max(vmax - vmin, 1e-12))

        # Estimate Q1, median, Q3 from the violin density profile (width = KDE density)
        weights = [max(0.0, w) for _, w in profile]
        total_w = sum(weights)
        q1 = _profile_quantile(profile, weights, total_w, vmin, vmax, 0.25)
        med = _profile_quantile(profile, weights, total_w, vmin, vmax, 0.50)
        q3 = _profile_quantile(profile, weights, total_w, vmin, vmax, 0.75)

        # Prefer an explicit cmedians segment inside (vmin, vmax) if present
        interior_ticks: list[float] = []
        for x0, y0, x1, y1 in line_segs:
            if orient == "vertical":
                sc0, sc1, sv0, sv1 = x0, x1, y0, y1
            else:
                sc0, sc1, sv0, sv1 = y0, y1, x0, x1
            if abs(sv0 - sv1) <= vtol and abs(0.5 * (sc0 + sc1) - pos) <= ctol:
                vm = 0.5 * (sv0 + sv1)
                if vmin + vtol < vm < vmax - vtol:
                    interior_ticks.append(vm)
        if interior_ticks:
            med = min(interior_ticks, key=lambda v: abs(v - med))

        name = _name_at(pos, ticks, spacing, f"group {k + 1}")
        if name in out:
            name = f"{name} ({k + 1})"
        out[name] = {
            "median": float(med),
            "q1": float(q1),
            "q3": float(q3),
            "min": float(vmin),
            "max": float(vmax),
        }
    return out, orient, used_colls


def _read_band_envelope(coll: Any) -> dict[str, Any] | None:
    """Extract upper/lower envelope summary from a fill_between / CI PolyCollection."""
    import numpy as np

    xs_map: dict[float, list[float]] = {}
    for path in coll.get_paths():
        verts = np.asarray(path.vertices, dtype=float)
        if verts.ndim != 2 or verts.shape[1] != 2 or len(verts) < 4:
            continue
        ok = np.isfinite(verts).all(axis=1)
        pts = verts[ok]
        if len(pts) < 4:
            continue
        x_span = float(pts[:, 0].max() - pts[:, 0].min())
        scale = 1e6 / max(x_span, 1e-12)
        for xv, yv in pts:
            xk = round(float(xv) * scale) / scale
            xs_map.setdefault(xk, []).append(float(yv))
    pairs = [(x, min(ys), max(ys)) for x, ys in sorted(xs_map.items()) if len(ys) >= 2]
    if len(pairs) < 2:
        return None
    los = [p[1] for p in pairs]
    his = [p[2] for p in pairs]
    widths = [h - lo for lo, h in zip(los, his)]
    return {
        "n": len(pairs),
        "lower_range": [min(los), max(los)],
        "upper_range": [min(his), max(his)],
        "peak": max(his),
        "trough": min(los),
        "start_interval": [los[0], his[0]],
        "end_interval": [los[-1], his[-1]],
        "max_width": max(widths),
        "max_half_width": 0.5 * max(widths),
    }


def _read_axes(ax: Any, index: int, cands: _Candidates) -> dict[str, Any]:
    from matplotlib.collections import PathCollection, PolyCollection, QuadMesh
    from matplotlib.image import AxesImage

    panel: dict[str, Any] = {"axes": index, "kind": "empty", "title": ax.get_title() or None,
                             "x_label": ax.get_xlabel() or None, "y_label": ax.get_ylabel() or None,
                             "values": {}, "facts": []}
    facts: list[str] = panel["facts"]
    kinds: list[str] = []

    bars, _orientation, bar_containers, hist_containers = _read_bars(ax)
    if bars:
        kinds.append("bars")
        panel["values"]["bars"] = bars
        for name, vals in bars.items():
            cands.add_group(vals, "" if len(bars) == 1 else name)
            if len(vals) >= 2:
                ranked = sorted(vals.items(), key=lambda kv: kv[1], reverse=True)
                (top, vt), (second, v2) = ranked[0], ranked[1]
                low, vl = ranked[-1]
                prefix = "" if len(bars) == 1 else f"{name}: "
                gap = vt - v2
                fact = f"{prefix}highest {top} {_fmt(vt)}, {_fmt(gap)} above {second} ({_fmt(v2)})"
                if v2 > 0 and vt > 0:
                    fact += f", {vt / v2:.2f}×"
                facts.append(fact + f"; lowest {low} {_fmt(vl)}")
        if len(bars) > 1:  # grouped: the gap between series within each category
            cats = {c for vals in bars.values() for c in vals}
            for cat in sorted(cats):
                row = {s: vals[cat] for s, vals in bars.items() if cat in vals}
                if len(row) >= 2:
                    cands.add_group(row, cat)

    if hist_containers:
        hists = _read_histograms(ax, hist_containers)
        if hists:
            kinds.append("histogram")
            panel["values"]["histogram"] = {
                n: {k: v for k, v in d.items() if k != "orientation"} for n, d in hists.items()
            }
            medians_map: dict[str, float] = {}
            peaks_map: dict[str, float] = {}
            for name, h in hists.items():
                prefix = "" if len(hists) == 1 else f"{name}: "
                plo, phi = h["peak_range"]
                facts.append(
                    f"{prefix}histogram ({h['bins']} bins, total {_fmt(h['total'])}): "
                    f"peak bin {_fmt(plo)}–{_fmt(phi)} (center {_fmt(h['peak_center'])}); "
                    f"median ≈ {_fmt(h['median'])}"
                )
                medians_map[name] = h["median"]
                peaks_map[name] = h["peak_center"]
                cands.add_group(
                    {
                        "peak center": h["peak_center"],
                        "median": h["median"],
                        "mean": h["mean"],
                        "min": h["range"][0],
                        "max": h["range"][1],
                    },
                    name,
                )
                cands.other += [
                    (f"{name} peak bin low", plo),
                    (f"{name} peak bin high", phi),
                    (f"{name} peak height", h["peak_height"]),
                    (f"{name} bin count", float(h["bins"])),
                    (f"{name} total", h["total"]),
                ]
            if len(hists) >= 2:
                cands.add_group(medians_map, "histogram medians")
                cands.add_group(peaks_map, "histogram peaks")

    # Truncated baseline check for both regular bar charts and histograms
    all_bar_containers = [*bar_containers, *hist_containers]
    if all_bar_containers:
        bar_orient = getattr(all_bar_containers[0], "orientation", None) or "vertical"
        value_lim = ax.get_ylim() if bar_orient == "vertical" else ax.get_xlim()
        scale = ax.get_yscale() if bar_orient == "vertical" else ax.get_xscale()
        allv = [
            float(r.get_height() if bar_orient == "vertical" else r.get_width())
            for c in all_bar_containers for r in c.patches
        ]
        allv = [v for v in allv if math.isfinite(v)]
        lo_lim = min(value_lim)
        hi_lim = max(value_lim)
        bars_from_zero = all(
            abs(r.get_y() if bar_orient == "vertical" else r.get_x()) < 1e-12
            for c in all_bar_containers for r in c.patches
        )
        if scale == "linear" and bars_from_zero and allv and (
            (min(allv) >= 0 and lo_lim > 0) or (max(allv) <= 0 and hi_lim < 0)
        ):
            panel["truncated_bars"] = [_fmt(lo_lim), _fmt(hi_lim)]

    intervals: dict[str, tuple[float, float]] = {}
    for eb in _read_errorbars(ax):
        names_axis = "x" if eb["axis"] == "y" else "y"
        ticks = _tick_names(ax, names_axis)
        spacing = _spacing([p[0] for p in eb["points"]] + [loc for loc, _ in ticks])
        for pos, value, lo, hi in eb["points"]:
            name = _name_at(pos, ticks, spacing, f"{eb['label'] or 'point'} at {_fmt(pos)}")
            if eb["label"] and len(_read_errorbars(ax)) > 1:
                name = f"{eb['label']}: {name}"
            intervals[name] = (lo, hi)
            cands.other.append((f"{name} interval low", lo))
            cands.other.append((f"{name} interval high", hi))
            if value is not None and name not in {k for vals in bars.values() for k in vals}:
                panel["values"].setdefault("points", {})[name] = value
    if intervals:
        panel["values"]["intervals"] = {k: [lo, hi] for k, (lo, hi) in intervals.items()}
        kinds.append("intervals")
    if "points" in panel["values"]:
        pts = panel["values"]["points"]
        cands.add_group(pts, "")
        if len(pts) >= 2:
            ranked = sorted(pts.items(), key=lambda kv: kv[1], reverse=True)
            facts.append(f"highest {ranked[0][0]} {_fmt(ranked[0][1])}; lowest {ranked[-1][0]} "
                         f"{_fmt(ranked[-1][1])}")
    # Do the two largest values' intervals overlap?
    level_values = {**{k: v for vals in bars.values() for k, v in vals.items()},
                    **panel["values"].get("points", {})}
    shared = [k for k in level_values if k in intervals]
    if len(shared) >= 2:
        ranked = sorted(shared, key=lambda k: level_values[k], reverse=True)
        a, b = ranked[0], ranked[1]
        (alo, ahi), (blo, bhi) = intervals[a], intervals[b]
        overlap = alo <= bhi and blo <= ahi
        facts.append(f"intervals of {a} ({_fmt(alo)}–{_fmt(ahi)}) and {b} ({_fmt(blo)}–{_fmt(bhi)}) "
                     + ("overlap" if overlap else "do not overlap"))
    elif len(intervals) >= 2 and not level_values:
        ranked = sorted(intervals.items(), key=lambda kv: sum(kv[1]), reverse=True)
        (a, (alo, ahi)), (b, (blo, bhi)) = ranked[0], ranked[1]
        overlap = alo <= bhi and blo <= ahi
        facts.append(f"intervals of {a} and {b} " + ("overlap" if overlap else "do not overlap"))

    skip = _errorbar_line_ids(ax)
    boxes, box_orient, box_line_ids = _read_boxplots(ax, skip)
    skip |= box_line_ids
    if boxes:
        kinds.append("boxplot")
        panel["values"]["boxplot"] = boxes
        panel["_dist_orient"] = box_orient
        meds = {g: d["median"] for g, d in boxes.items()}
        cands.add_group(meds, "boxplot medians")
        for g, d in boxes.items():
            cands.other += [
                (f"{g} Q1", d["q1"]),
                (f"{g} Q3", d["q3"]),
                (f"{g} IQR", d["iqr"]),
                (f"{g} whisker low", d["whisker_lo"]),
                (f"{g} whisker high", d["whisker_hi"]),
            ]
            cands.pairs.append((f"{g} Q3 vs Q1", d["q3"], d["q1"]))
            cands.pairs.append((f"{g} whisker high vs low", d["whisker_hi"], d["whisker_lo"]))
        if len(boxes) >= 2:
            ranked = sorted(boxes.items(), key=lambda kv: kv[1]["median"], reverse=True)
            (top, dt), (second, d2) = ranked[0], ranked[1]
            low, dl = ranked[-1]
            gap = dt["median"] - d2["median"]
            fact = (f"highest median {top} {_fmt(dt['median'])} (IQR {_fmt(dt['q1'])}–{_fmt(dt['q3'])}), "
                    f"{_fmt(gap)} above {second} ({_fmt(d2['median'])})")
            if d2["median"] > 0 and dt["median"] > 0:
                fact += f", {dt['median'] / d2['median']:.2f}×"
            facts.append(fact + f"; lowest {low} {_fmt(dl['median'])}")
        else:
            g, d = next(iter(boxes.items()))
            facts.append(
                f"{g}: median {_fmt(d['median'])}, IQR {_fmt(d['q1'])}–{_fmt(d['q3'])}, "
                f"whiskers {_fmt(d['whisker_lo'])}–{_fmt(d['whisker_hi'])}"
            )

    series: dict[str, tuple[list[float], list[float]]] = {}
    references: list[str] = []
    ref_levels: list[float] = []
    for k, ln in enumerate(ax.lines):
        if id(ln) in skip or not ln.get_visible():
            continue
        ref = _is_reference_line(ax, ln)
        if ref is not None:
            references.append(f"{ref[0]}={_fmt(ref[1])}")
            cands.other.append((f"reference line {ref[0]}={_fmt(ref[1])}", ref[1]))
            if ref[0] == "y":
                ref_levels.append(ref[1])
            continue
        import numpy as np

        x = np.ma.filled(np.ma.asarray(ln.get_xdata(orig=False), dtype=float), np.nan)
        y = np.ma.filled(np.ma.asarray(ln.get_ydata(orig=False), dtype=float), np.nan)
        keep = np.isfinite(x) & np.isfinite(y)
        if keep.sum() < 2:
            continue
        name = _series_label(ln, f"line {len(series) + 1}")
        if name in series:
            name = f"{name} ({k + 1})"
        series[name] = ([float(v) for v in x[keep]], [float(v) for v in y[keep]])
    if references:
        panel["references"] = references
    if series:
        kinds.append("lines")
        panel["values"]["lines"] = {
            n: {"x": xs if len(xs) <= _MAX_POINTS else [xs[0], xs[-1]],
                "y": ys if len(ys) <= _MAX_POINTS else [ys[0], ys[-1]], "n": len(ys)}
            for n, (xs, ys) in series.items()
        }
        ends: dict[str, float] = {}
        peaks_x: dict[str, float] = {}
        for name, (xs, ys) in series.items():
            cands.series.append((name, xs, ys))
            for level in ref_levels:
                for xc in _crossings(xs, ys, [level] * len(ys)):
                    facts.append(f"{name} crosses {_fmt(level)} near x={_fmt(xc)}")
                    cands.other.append((f"{name} crosses {_fmt(level)} at x", xc))
            start, end = ys[0], ys[-1]
            imax = max(range(len(ys)), key=ys.__getitem__)
            imin = min(range(len(ys)), key=ys.__getitem__)
            change = end - start
            fact = f"{name}: {_fmt(start)} at x={_fmt(xs[0])} → {_fmt(end)} at x={_fmt(xs[-1])} ({change:+.3g}"
            if start != 0:
                fact += f", {100 * change / abs(start):+.0f}%"
            fact += ")"
            if imax not in (0, len(ys) - 1):
                fact += f"; peak {_fmt(ys[imax])} at x={_fmt(xs[imax])}"
            facts.append(fact)
            ends[name] = end
            summary_vals = {"start": start, "end": end, "max": ys[imax], "min": ys[imin],
                            "mean": sum(ys) / len(ys)}
            cands.add_group(summary_vals, name)
            cands.other.append((f"{name} peak at x", xs[imax]))
            peaks_x[name] = xs[imax]
            cands.other.append((f"{name} low at x", xs[imin]))
            if len(ys) <= _MAX_POINTS:
                for xv, yv in zip(xs, ys):
                    cands.levels.append((f"{name} at x={_fmt(xv)}", yv))
                    cands.other.append((f"x={_fmt(xv)}", xv))
            if len(xs) >= 2 and xs[-1] != xs[0]:
                cands.other.append((f"{name} slope per x", change / (xs[-1] - xs[0])))
        if len(series) >= 2:
            cands.add_group(ends, "end values")
            peak_names = list(peaks_x)
            for i, a in enumerate(peak_names):
                for b in peak_names[i + 1:]:
                    cands.pairs.append((f"peak x of {a} vs {b}", peaks_x[a], peaks_x[b]))
            names = list(series)
            for i, a in enumerate(names):
                for b in names[i + 1:]:
                    (xa, ya), (xb, yb) = series[a], series[b]
                    if xa == xb:
                        if len(ya) <= _MAX_POINTS:
                            for xv, va, vb in zip(xa, ya, yb):
                                cands.pairs.append((f"{a} vs {b} at x={_fmt(xv)}", va, vb))
                        for xc in _crossings(xa, ya, yb):
                            facts.append(f"{a} and {b} cross near x={_fmt(xc)}")
                            cands.other.append((f"{a}/{b} crossing x", xc))

    violins, violin_orient, violin_coll_ids = _read_violins(ax, bool(series))
    if violins:
        kinds.append("violin")
        panel["values"]["violin"] = violins
        panel.setdefault("_dist_orient", violin_orient)
        vmeds = {g: d["median"] for g, d in violins.items()}
        cands.add_group(vmeds, "violin medians")
        for g, d in violins.items():
            cands.other += [
                (f"{g} Q1", d["q1"]),
                (f"{g} Q3", d["q3"]),
                (f"{g} min", d["min"]),
                (f"{g} max", d["max"]),
            ]
            cands.pairs.append((f"{g} max vs min", d["max"], d["min"]))
        if len(violins) >= 2:
            ranked = sorted(violins.items(), key=lambda kv: kv[1]["median"], reverse=True)
            (top, dt), (low, dl) = ranked[0], ranked[-1]
            facts.append(
                f"highest violin median {top} {_fmt(dt['median'])} (range {_fmt(dt['min'])}–{_fmt(dt['max'])}); "
                f"lowest {low} {_fmt(dl['median'])}"
            )
        else:
            g, d = next(iter(violins.items()))
            facts.append(f"{g}: violin median {_fmt(d['median'])}, range {_fmt(d['min'])}–{_fmt(d['max'])}")

    means: dict[str, tuple[float, float]] = {}
    band_idx = 0
    for coll in ax.collections:
        if id(coll) in violin_coll_ids or not coll.get_visible():
            continue
        if isinstance(coll, QuadMesh) and coll.get_array() is not None:
            import numpy as np

            arr = np.ma.asarray(coll.get_array(), dtype=float)
            vals = _finite(arr)
            if not vals:
                continue
            kinds.append("heatmap")
            lo, hi = min(vals), max(vals)
            mean_v = sum(vals) / len(vals)
            svals = sorted(vals)
            med_v = (
                svals[len(svals) // 2]
                if len(svals) % 2
                else 0.5 * (svals[len(svals) // 2 - 1] + svals[len(svals) // 2])
            )
            panel["values"]["heatmap"] = {
                "cells": len(vals), "min": lo, "max": hi, "mean": mean_v, "median": med_v,
            }
            facts.append(f"heatmap cells span {_fmt(lo)}–{_fmt(hi)} (median {_fmt(med_v)}, {len(vals)} cells)")
            cands.other += [
                ("highest cell", hi), ("lowest cell", lo), ("mean cell", mean_v), ("median cell", med_v),
            ]
            cands.pairs.append(("highest vs lowest cell", hi, lo))
            if lo > 0:
                cands.other.append(("highest/lowest cell ratio", hi / lo))
            if len(vals) <= _MAX_POINTS:
                if arr.ndim == 2 and arr.size <= 64:
                    xticks = _tick_names(ax, "x")
                    yticks = _tick_names(ax, "y")
                    ny, nx = arr.shape
                    cell_map: dict[str, float] = {}
                    for r_i in range(ny):
                        rname = _name_at(r_i + 0.5, yticks, 1.0, f"r{r_i}")
                        for c_i in range(nx):
                            v = float(np.ma.filled(arr[r_i, c_i], np.nan))
                            if math.isfinite(v):
                                cname = _name_at(c_i + 0.5, xticks, 1.0, f"c{c_i}")
                                cell_map[f"{rname}/{cname}"] = v
                    cands.add_group(cell_map, "heatmap")
                else:
                    for v in sorted({round(x, 8) for x in vals}):
                        cands.levels.append(("heatmap cell", v))
            continue
        if isinstance(coll, PolyCollection) and not isinstance(coll, PathCollection):
            panel["bands"] = panel.get("bands", 0) + 1
            band_idx += 1
            env = _read_band_envelope(coll)
            if env is not None:
                bname = _series_label(coll, f"band {band_idx}")
                panel["values"].setdefault("bands", {})[bname] = env
                facts.append(
                    f"{bname} band spans {_fmt(env['trough'])}–{_fmt(env['peak'])} "
                    f"(end {_fmt(env['end_interval'][0])}–{_fmt(env['end_interval'][1])})"
                )
                cands.other += [
                    (f"{bname} band max", env["peak"]),
                    (f"{bname} band min", env["trough"]),
                    (f"{bname} band start low", env["start_interval"][0]),
                    (f"{bname} band start high", env["start_interval"][1]),
                    (f"{bname} band end low", env["end_interval"][0]),
                    (f"{bname} band end high", env["end_interval"][1]),
                    (f"{bname} max band width", env["max_width"]),
                    (f"{bname} max half-width", env["max_half_width"]),
                ]
                cands.pairs.append((f"{bname} band max vs min", env["peak"], env["trough"]))
                cands.pairs.append(
                    (f"{bname} band end high vs low", env["end_interval"][1], env["end_interval"][0])
                )
            continue
        if isinstance(coll, PathCollection):
            import numpy as np

            offsets = np.ma.filled(np.ma.asarray(coll.get_offsets(), dtype=float), np.nan)
            if offsets.ndim != 2 or len(offsets) < 3:
                continue
            ok = np.isfinite(offsets).all(axis=1)
            pts = offsets[ok]
            if len(pts) < 3:
                continue
            kinds.append("scatter")
            xs, ys = pts[:, 0], pts[:, 1]
            name = _series_label(coll, f"points {len(panel['values'].get('scatter', {})) + 1}")
            entry: dict[str, Any] = {"n": len(pts)}
            if xs.std() > 0 and ys.std() > 0:
                r = float(np.corrcoef(xs, ys)[0, 1])
                slope, _ = np.polyfit(xs, ys, 1)
                entry.update(r=round(r, 3), slope=float(slope))
                facts.append(f"{name}: r = {r:.2f} across {len(pts)} points; slope {_fmt(float(slope))} per x unit")
                cands.other += [(f"{name} correlation r", r), (f"{name} slope", float(slope))]
            means[name] = (float(xs.mean()), float(ys.mean()))
            cands.other += [(f"{name} mean x", float(xs.mean())), (f"{name} mean y", float(ys.mean()))]
            entry["x_range"] = [float(xs.min()), float(xs.max())]
            entry["y_range"] = [float(ys.min()), float(ys.max())]
            cands.other += [(f"{name} max y", float(ys.max())), (f"{name} min y", float(ys.min())),
                            (f"{name} max x", float(xs.max())), (f"{name} min x", float(xs.min()))]
            panel["values"].setdefault("scatter", {})[name] = entry

    if len(means) >= 2:  # replicate dots per group: compare the group means
        for axis_i, axis in enumerate(("x", "y")):
            vals = [v[axis_i] for v in means.values()]
            if len({round(v, 12) for v in vals}) > 1:
                names = list(means)
                for i, a in enumerate(names):
                    for b in names[i + 1:]:
                        cands.pairs.append((f"mean {axis} of {a} vs {b}", means[a][axis_i], means[b][axis_i]))

    for img in ax.images:
        if isinstance(img, AxesImage) and img.get_array() is not None:
            vals = _finite(img.get_array())
            if not vals:
                continue
            kinds.append("image")
            lo, hi = min(vals), max(vals)
            panel["values"]["image"] = {"cells": len(vals), "min": lo, "max": hi}
            facts.append(f"cells span {_fmt(lo)}–{_fmt(hi)} ({len(vals)} cells)")
            cands.other += [("highest cell", hi), ("lowest cell", lo)]
            cands.pairs.append(("highest vs lowest cell", hi, lo))
            if lo > 0:
                cands.other.append(("highest/lowest cell ratio", hi / lo))
            if len(vals) <= 64:
                cands.add_group({f"cell {i}": v for i, v in enumerate(vals)}, "image")
    panel["kind"] = "+".join(dict.fromkeys(kinds)) or "empty"
    return panel


# --------------------------------------------------------------------------- claim


def _derivations(cands: _Candidates, kind: str) -> list[tuple[str, float]]:
    """(how, value) pairs a claim of ``kind`` may state."""
    out: list[tuple[str, float]] = []
    if kind in {"plain", "percent", "points"}:
        for how, v in cands.levels + cands.other:
            out.append((f"{how} = {_fmt(v)}", abs(v)))
            if abs(v) <= 1 and kind != "plain":
                out.append((f"{how} = {_fmt(v)} (×100)", abs(v) * 100))
    for how, a, b in cands.pairs:
        for deriv, v in pair_derivations(a, b, "fold" if kind == "fold" else "percent"):
            base = deriv.split(":")[0]
            if kind == "fold" and base != "ratio":
                continue
            if kind == "plain" and base not in {"difference", "ratio"}:
                continue
            if kind == "points" and base not in {"difference", "points"}:
                continue
            if kind == "percent" and base == "difference" and max(abs(a), abs(b)) <= 1:
                continue  # a fraction's difference is stated in points, handled as "points"
            label = {
                "difference": f"{how}: {_fmt(a)} − {_fmt(b)} = {_fmt(abs(a - b))}",
                "points": f"{how}: {_fmt(a)} − {_fmt(b)} = {_fmt(abs(a - b) * 100)} points",
                "ratio": f"{how}: {_fmt(max(abs(a), abs(b)) / max(min(abs(a), abs(b)), 1e-300))}×",
                "relative": f"{how}: {_fmt(v)}% change",
            }[base]
            out.append((label, v))
    if kind == "percent":
        out += [(f"{how} = {_fmt_pct(v)}", v) for how, v in cands.shares]
    if kind == "fold":
        for how, v in cands.levels + cands.other:
            if abs(v) > 1:
                out.append((f"{how} = {_fmt(v)}", abs(v)))
    return out


def _close(claim: float, text: str, candidate: float) -> bool:
    if not math.isfinite(candidate):
        return False
    if stated_match(claim, text, candidate):
        return True
    return candidate != 0 and abs(abs(candidate) - claim) / abs(candidate) <= 0.02


def _units(fig: Any) -> list[str | None]:
    units: list[str | None] = [None]
    for ax in fig.axes:
        for label in (ax.get_xlabel(), ax.get_ylabel()):
            m = _UNIT_IN_LABEL.search(label or "")
            if m and m.group(1).strip() not in units:
                units.append(m.group(1).strip())
    return units


def _claim_words(text: str) -> set[str]:
    return set(re.findall(r"[a-z][a-z0-9-]{3,}", text.lower()))


def _named(how: str, words: set[str]) -> int:
    """How many of the claim's words the derivation's subject names ("Swahili", "retrieval")."""
    subject = how.split(":")[0].split(" = ")[0].lower()
    return sum(1 for w in words if w in subject)


def _claim_scale_factors(kind: str, val: float, raw: str, fig_units: Sequence[str | None]) -> list[tuple[float, str | None]]:
    """Return ``[(factor, claim_unit), ...]`` to scale data candidates into ``raw``'s unit."""
    m = re.match(r"^\d+(?:,\d{3})*(?:\.\d+)?[kK]?\s+(.+)$", raw.strip())
    claim_unit = m.group(1).strip() if m else None
    if claim_unit and kind == "plain":
        factors: list[tuple[float, str | None]] = []
        seen_f: set[float] = set()
        for ax_unit in fig_units:
            if not ax_unit:
                continue
            f = unit_scale_factor(ax_unit, claim_unit)
            if f is not None and f not in seen_f:
                seen_f.add(f)
                factors.append((f, claim_unit))
        if factors:
            return factors
        return [(1.0, claim_unit)]

    factors = [(1.0, None)]
    seen_f = {1.0}
    if kind == "plain":
        if "%" in fig_units and 0 < val <= 1.0:
            factors.append((0.01, None))
            seen_f.add(0.01)
        for ax_unit in fig_units:
            if not ax_unit:
                continue
            f = unit_scale_factor(ax_unit, "")
            if f is not None and f not in seen_f:
                seen_f.add(f)
                factors.append((f, None))
    return factors


def _nearest(
    val: float,
    kind: str,
    cands: _Candidates,
    text: str = "",
    factors: Sequence[tuple[float, str | None]] = ((1.0, None),),
) -> str | None:
    """The derivation closest to a claimed number that was not found: what the data says.
    Derivations naming something the claim names ("retrieval") come first."""
    base_pool = [
        (how, v) for how, v in _derivations(cands, kind)
        if kind == "fold" or not how.startswith("x=") and " at x" not in how.split(":")[0][-6:]
    ]
    pool: list[tuple[str, float]] = []
    for how, v in base_pool:
        if not math.isfinite(v) or v <= 0:
            continue
        for f, c_unit in factors:
            sv = v * f
            if math.isfinite(sv) and sv > 0 and 0.25 <= sv / max(val, 1e-300) <= 4:
                label = f"{how} ({_fmt(sv)} {c_unit})" if f != 1.0 and c_unit else how
                pool.append((label, sv))
    if not pool:
        return None
    words = _claim_words(text)
    best = max(_named(how, words) for how, _ in pool)
    pool = [(how, v) for how, v in pool if _named(how, words) == best]
    how, _ = min(pool, key=lambda hv: abs(math.log(hv[1] / val)) if val > 0 else abs(hv[1]))
    return how


def _crossing_match(val: float, raw: str, others: Sequence[float], cands: _Candidates) -> str | None:
    """"Reaches 80% near cycle 460": the x where a series crosses another number the claim states."""
    for level in others:
        for y in {level, level / 100.0}:
            for name, xs, ys in cands.series:
                for xc in _crossings(xs, ys, [y] * len(ys)):
                    if _close(val, raw, xc):
                        return f"{name} crosses {_fmt(y)} at x = {_fmt(xc)}"
    return None


def _check_claim(text: str, fig: Any, cands: _Candidates) -> dict[str, Any]:
    fig_units = _units(fig)
    seen: dict[str, tuple[str, float, str]] = {}
    for unit in fig_units:
        for kind, val, raw in claim_numbers(text, unit):
            idx = text.find(raw)
            if idx >= 0 and _COUNT_BEFORE.search(text[:idx]):
                continue
            seen.setdefault(f"{idx}:{raw}", (kind, val, raw))
    hedged = bool(_HEDGE_RE.search(text))
    words = _claim_words(text)
    numbers = []
    for kind, val, raw in seen.values():
        factors = _claim_scale_factors(kind, val, raw, fig_units)
        matches: list[str] = []
        for how, cand in _derivations(cands, kind):
            for f, c_unit in factors:
                if _close(val, raw, cand * f):
                    label = f"{how} ({_fmt(cand * f)} {c_unit})" if f != 1.0 and c_unit else how
                    matches.append(label)
                    break
        if kind in {"plain", "points"}:
            crossing = _crossing_match(val, raw, [v for k, v, r in seen.values() if r != raw], cands)
            if crossing is not None:
                matches.insert(0, crossing)
        # Several derivations may give the number: report the one naming what the claim names.
        found = max(matches, key=lambda how: _named(how, words)) if matches else None
        entry = {"text": raw, "value": val, "kind": kind, "found": found is not None,
                 "how": found or ("hedged; not checked" if hedged else None)}
        if found is None:
            nearest = _nearest(val, kind, cands, text, factors)
            if nearest is not None:
                entry["nearest"] = nearest
        numbers.append(entry)
    return {"text": text, "hedged": hedged, "numbers": numbers}


# --------------------------------------------------------------------------- check


def check(
    fig: Any = None,
    claim: str | None = None,
    *,
    width: str | int = "chat",
    dpi: float | None = None,
    bbox_inches: str | None = None,
) -> FigureCheck:
    """Audit a Matplotlib figure against its own data and at the size it will be read.

    Parameters
    ----------
    fig
        A ``Figure``, an ``Axes`` (its figure is checked), or ``None`` for the current
        pyplot figure.
    claim
        The sentence to check against the data; the reply's takeaway. Defaults to the
        figure's headline: the suptitle, else the top figure text, else the first title.
    width
        Where it is read: ``"chat"`` (700 px, default), ``"narrow"`` (450 px, a phone
        or IDE sidebar), ``"slide"`` (1280 px), or a width in pixels. A PNG wider than
        this is scaled down, so its text shrinks.
    dpi, bbox_inches
        How it will be saved; default to Matplotlib's ``savefig`` settings. Pass what
        your ``fig.savefig(...)`` call passes.

    Returns
    -------
    FigureCheck
        A dict: ``ship``, ``claim``, ``issues``, ``advisories``, ``panels`` and
        ``display``. ``print(report)`` shows a compact view.
    """
    import matplotlib as mpl

    figure = _resolve_figure(fig)
    if isinstance(width, str):
        if width not in WIDTHS:
            raise ValueError(f"width= must be one of {sorted(WIDTHS)} or a number of pixels, not {width!r}.")
        width_px = WIDTHS[width]
    else:
        width_px = int(width)
        if width_px <= 0:
            raise ValueError("width= in pixels must be positive.")
    save_dpi = dpi if dpi is not None else mpl.rcParams["savefig.dpi"]
    if save_dpi == "figure":
        save_dpi = figure.dpi
    save_dpi = float(save_dpi)
    bbox = bbox_inches if bbox_inches is not None else mpl.rcParams["savefig.bbox"]
    tight = bbox == "tight"

    with _AggCanvas(figure):
        buf = io.BytesIO()
        figure.savefig(buf, format="png", dpi=save_dpi, bbox_inches="tight" if tight else None)
        size = _png_size(buf.getvalue())
        texts = _drawn_texts(figure)
        renderer = figure.canvas.get_renderer()
        headline = _headline(figure, renderer)
        report = _audit(figure, texts, renderer, size=size, dpi=save_dpi, tight=tight, width_px=width_px)
        from matplotlib.collections import QuadMesh

        cands = _Candidates()
        panels = [
            _read_axes(ax, i, cands)
            for i, ax in enumerate(figure.axes)
            if ax.get_visible()
            and not _is_colorbar_axes(ax)
            and (ax.axison or ax.images or any(isinstance(c, QuadMesh) for c in ax.collections))
        ]

    issues: list[dict] = report.pop("issues")
    advisories: list[dict] = []
    all_text = " ".join(t.get_text() for t in texts)

    for p in panels:
        truncated = p.pop("truncated_bars", None)
        if truncated is not None:
            issues.append(_issue(
                "bar_baseline_nonzero", "error",
                f"Bars start at zero but the value axis runs {truncated[0]}–{truncated[1]}, "
                "so bar lengths overstate the differences.",
                "Let the value axis include 0 (drop set_ylim/set_xlim on it), or draw points "
                "(ax.plot(..., 'o')) if the differences are what matters.",
                p["axes"],
            ))
    if (any("intervals" in p["kind"] or p.get("bands") for p in panels)
            and not _UNCERTAINTY_WORDS.search(all_text)):
        issues.append(_issue(
            "interval_unlabelled", "warning",
            "The figure draws error bars or bands but never says what they are.",
            "Name the interval where it is read: '95% CI, 5 seeds' or '±1 s.d., n = 12' in the "
            "axis label, title or legend.",
        ))
    for p in panels:
        ax = figure.axes[p["axes"]]
        val_axes = _value_axes(p, ax)
        p.pop("_dist_orient", None)
        if val_axes:
            for axis, label in (("x", ax.get_xlabel()), ("y", ax.get_ylabel())):
                ticks = [t for _, t in _tick_names(ax, axis)]
                numeric = ticks and all(_is_numeric_label(t) for t in ticks)
                if numeric and not (label or "").strip() and axis in val_axes:
                    issues.append(_issue(
                        "axis_unlabelled", "warning",
                        f"Axes {p['axes']} has numbers on its {axis} axis but no label saying what they measure.",
                        f"ax.set_{axis}label('Quantity (unit)').",
                        p["axes"],
                    ))
    twins = _twin_axes(figure)
    if twins:
        advisories.append(_issue(
            "dual_axis", "warning",
            f"{twins} panel(s) put two y scales on one plot; readers compare the lines as if they shared one.",
            "Use two stacked panels with a shared x axis (plt.subplots(2, 1, sharex=True)).",
        ))
    claim_text = claim if claim is not None else headline
    claim_report = None
    if claim_text:
        claim_report = _check_claim(claim_text, figure, cands)
        claim_report["source"] = "claim=" if claim is not None else "headline"
        missing = [n["text"] for n in claim_report["numbers"] if not n["found"]]
        if missing and not claim_report["hedged"]:
            listed = ", ".join(repr(m) for m in missing[:3])
            nearest = [f"{n['text']!r} → {n['nearest']}" for n in claim_report["numbers"]
                       if not n["found"] and n.get("nearest")]
            issues.append(_issue(
                "claim_number_mismatch", "warning",
                f"The claim states {listed}, which matches no value, difference, ratio, "
                "percentage change or share in the plotted data."
                + (f" Closest in the data: {'; '.join(nearest[:3])}." if nearest else ""),
                "Recompute the number from the data and fix the claim (or the plot). If it comes "
                "from outside the figure, say where in a note, or hedge it ('about 8').",
            ))
        if not claim_report["numbers"] and claim is None:
            advisories.append(_issue(
                "headline_states_no_number", "warning",
                f"The headline {claim_text!r} names the topic, not the finding.",
                "Make the headline the takeaway with its number, e.g. "
                "fig.suptitle('Removing retrieval costs 8 points of accuracy').",
            ))
    else:
        advisories.append(_issue(
            "no_headline", "warning",
            "The figure has no title, so the reader has to find the point themselves.",
            "fig.suptitle('<the takeaway, with its number>'), or pass claim= to check the reply's sentence.",
        ))
    if report.get("banned_colormaps"):
        names = ", ".join(report["banned_colormaps"])
        issues.append(_issue(
            "rainbow_colormap", "error",
            f"Rainbow colormap ({names}) invents boundaries and fails for colour-blind readers.",
            "Use 'viridis' or 'cividis' for one-sided values, 'RdBu_r' centred on 0 for signed ones.",
        ))
    report.pop("banned_colormaps", None)

    order = {"error": 0, "claim_number_mismatch": 1}
    issues.sort(key=lambda i: order.get(i["severity"], order.get(i["rule"], 2)))
    ship = not any(i["severity"] == "error" for i in issues) and not any(
        i["rule"] in BLOCKING for i in issues
    )
    return FigureCheck(
        ship=ship,
        claim=claim_report,
        issues=issues,
        advisories=advisories,
        panels=panels,
        display=report,
    )


def _value_axes(panel: Mapping[str, Any], ax: Any) -> set[str]:
    kind = panel["kind"]
    if "lines" in kind or "scatter" in kind or "histogram" in kind:
        return {"x", "y"}
    if "boxplot" in kind or "violin" in kind:
        return {"y"} if panel.get("_dist_orient", "vertical") == "vertical" else {"x"}
    bars = panel["values"].get("bars")
    if bars:
        from matplotlib.container import BarContainer

        c = next((c for c in ax.containers if isinstance(c, BarContainer)), None)
        return {"y"} if (getattr(c, "orientation", "vertical") or "vertical") == "vertical" else {"x"}
    if "intervals" in kind:
        return {"x", "y"}
    return set()


def _twin_axes(fig: Any) -> int:
    seen = 0
    axes = [ax for ax in fig.axes if ax.get_visible() and not _is_colorbar_axes(ax)]
    for i, a in enumerate(axes):
        for b in axes[i + 1:]:
            same_box = all(abs(u - v) < 1e-6 for u, v in zip(a.get_position().bounds, b.get_position().bounds))
            if same_box and (a.get_shared_x_axes().joined(a, b)):
                seen += 1
    return seen


def _audit(fig: Any, texts: list[Any], renderer: Any, *, size: tuple[int, int] | None, dpi: float,
           tight: bool, width_px: int) -> dict[str, Any]:
    out: dict[str, Any] = {"png_px": list(size) if size else None, "dpi": dpi,
                           "bbox_inches": "tight" if tight else None, "width_px": width_px}
    issues: list[dict] = []
    if size:
        shown = min(width_px, size[0])
        scale = shown / size[0]
        px_per_pt = dpi / 72.0 * scale
        out["shown_px"] = [shown, round(size[1] * scale)]
        sizes = sorted(((t.get_fontsize() * px_per_pt, t) for t in texts), key=lambda x: x[0])
        out["min_text_px"] = round(sizes[0][0], 1) if sizes else None
        small = [(px, t) for px, t in sizes if px < MIN_TEXT_PX]
        if small:
            need_pt = MIN_TEXT_PX / px_per_pt
            sample = ", ".join(f"{t.get_text()[:30]!r} {px:.1f} px" for px, t in small[:3])
            if scale < 0.999:
                why = (f"The {size[0]} px PNG is shown {shown} px wide, so text shrinks to "
                       f"{scale:.0%} of its saved size.")
                hint = (f"Draw at the size it is read: figsize width ≈ {shown / dpi:.1f} in at dpi={dpi:g} "
                        f"(or the same width at a higher dpi), or set text to at least {need_pt:.0f} pt.")
            else:
                why = f"At dpi={dpi:g}, text under {need_pt:.1f} pt is under {MIN_TEXT_PX:g} px."
                hint = (f"Set text to at least {need_pt:.0f} pt "
                        f"(plt.rcParams['font.size'] = {math.ceil(need_pt)}, and tick/legend sizes).")
            issues.append(_issue(
                "text_too_small", "warning",
                f"{len(small)} text(s) under {MIN_TEXT_PX:g} px as read: {sample}. {why}",
                hint,
            ))

    shrunk = []
    for t in texts:
        b = t.get_window_extent(renderer)
        pad = 1.5
        if b.width > 2 * pad and b.height > 2 * pad:
            b = b.from_extents(b.x0 + pad, b.y0 + pad, b.x1 - pad, b.y1 - pad)
        shrunk.append((t, b))
    overlaps = []
    for i, (ti, bi) in enumerate(shrunk):
        for tj, bj in shrunk[i + 1:]:
            if bi.overlaps(bj):
                overlaps.append(f"{ti.get_text()[:30]!r} / {tj.get_text()[:30]!r}")
    if overlaps:
        issues.append(_issue(
            "text_overlaps", "warning", f"Drawn text overlaps: {'; '.join(overlaps[:4])}.",
            "Shorten or drop labels, or give the panel more room "
            "(fewer categories, a taller figure, or fig.set_layout_engine('constrained')).",
        ))

    legend_texts: set[int] = set()
    legend_count = 0
    for ax in fig.axes:
        for leg in [ax.get_legend(), *getattr(fig, "legends", [])]:
            if leg is not None:
                legend_count += 1
                if leg.get_frame_on():
                    legend_texts |= {id(x) for x in leg.get_texts()}
                    legend_texts.add(id(leg.get_title()))
    grid = {id(g) for ax in fig.axes for g in (*ax.get_xgridlines(), *ax.get_ygridlines())}
    lines = [
        ln for ax in fig.axes for ln in ax.lines
        if id(ln) not in grid and ln.get_visible() and len(ln.get_xdata()) >= 2
        and ln.get_linestyle() not in ("None", "", " ") and ln.get_linewidth() > 0
    ]
    struck = []
    for ln in lines:
        path = ln.get_transform().transform_path(ln.get_path())
        dashed = ln.get_linestyle() not in ("-", "solid")
        for t, b in shrunk:
            if t.axes is not None and t.axes is not ln.axes:
                continue
            if _masked(t, legend_texts):
                continue
            if path.intersects_bbox(b, filled=False):
                what = "dashed reference line" if dashed else "data line"
                struck.append(f"{t.get_text()[:30]!r} crossed by a {what}")
    if struck:
        issues.append(_issue(
            "text_struck_by_line", "warning", f"Drawn text is crossed by a line: {'; '.join(struck[:4])}.",
            "Move the label off the line (ha=/va=, an offset), label line ends instead of the middle, "
            "or put the text on an opaque box (bbox=dict(fc='white', ec='none')).",
        ))

    faults = []
    for t in texts:
        txt = t.get_text()
        plain = re.sub(r"\$[^$]*\$", "", txt)
        if "%%" in plain:
            faults.append(f"doubled %: {txt[:40]!r}")
        m = _DOUBLED.search(plain)
        if m and not m.group(1).isdigit():
            faults.append(f"repeated words {m.group(0)!r}: {txt[:40]!r}")
        if _ASCII_MINUS.search(plain) and not re.search(r"\d{4}-\d{2}", plain):
            faults.append(f"ASCII hyphen as minus sign: {txt[:40]!r}")
        if _JUNK.search(plain):
            faults.append(f"junk value: {txt[:40]!r}")
    if faults:
        issues.append(_issue(
            "text_malformed", "warning", f"Malformed drawn text: {'; '.join(faults[:4])}.",
            "Fix the format string: one '%', no repeated words, '\N{MINUS SIGN}' (U+2212) for negatives, "
            "and drop NaN/None values before labelling.",
        ))

    if not tight:
        canvas = fig.bbox
        clipped = []
        for t in texts:
            b = t.get_window_extent(renderer)
            if b.x0 < canvas.x0 - 1 or b.y0 < canvas.y0 - 1 or b.x1 > canvas.x1 + 1 or b.y1 > canvas.y1 + 1:
                clipped.append(repr(t.get_text()[:40]))
        if clipped:
            issues.append(_issue(
                "text_clipped", "warning", f"Text runs past the canvas edge: {', '.join(clipped[:4])}.",
                "fig.set_layout_engine('constrained') (or fig.tight_layout()) before saving, "
                "or move the text inside the figure.",
            ))

    cmaps = set()
    for ax in fig.axes:
        for art in (*ax.images, *ax.collections):
            cmap = getattr(art, "cmap", None)
            if cmap is not None and getattr(art, "get_array", lambda: None)() is not None:
                cmaps.add(cmap.name.removesuffix("_r"))
    out["banned_colormaps"] = sorted(cmaps & _BANNED_CMAPS)
    out["texts"] = len(texts)
    out["legends"] = legend_count  # a matter of taste: reported, never an issue
    out["issues"] = issues
    return out


# --------------------------------------------------------------------------- scripts & notebooks


def _venv_python(venv_dir: Any) -> Any:
    """Return the Python executable inside a virtualenv / conda prefix, or None."""
    from pathlib import Path

    root = Path(venv_dir)
    for rel in (("bin", "python"), ("bin", "python3"), ("Scripts", "python.exe")):
        cand = root.joinpath(*rel)
        if cand.is_file() and os.access(cand, os.X_OK):
            return cand
    return None


def _is_same_interpreter(candidate: Any) -> bool:
    """True when ``candidate`` points to the running interpreter's environment.

    Avoids following the final symlink so two virtualenvs sharing a base Python
    binary are recognized as distinct interpreters.
    """
    import sys

    abs_cand = os.path.normcase(os.path.abspath(os.fspath(candidate)))
    abs_curr = os.path.normcase(os.path.abspath(sys.executable))
    if abs_cand == abs_curr:
        return True
    prefix = os.path.normcase(os.path.abspath(sys.prefix))
    return abs_cand.startswith(prefix + os.sep)


def _resolve_python(target_path: Any, python: str | os.PathLike[str] | None) -> Any:
    """Resolve the Python interpreter to run a script/notebook with, or None for in-process."""
    import shutil
    from pathlib import Path

    if python is not None:
        raw = os.fspath(python)
        cand = Path(raw)
        if not cand.is_file():
            found = shutil.which(raw)
            if found is None:
                raise FileNotFoundError(f"Python interpreter not found: {python}")
            cand = Path(found)
        return None if _is_same_interpreter(cand) else cand

    target = Path(target_path).resolve()
    search_roots: list[Path] = [target.parent / ".venv"]
    if target.parent.parent != target.parent:
        search_roots.append(target.parent.parent / ".venv")
    search_roots.append(Path.cwd() / ".venv")
    for env_var in ("VIRTUAL_ENV", "CONDA_PREFIX"):
        val = os.environ.get(env_var)
        if val:
            search_roots.append(Path(val))

    for root in search_roots:
        cand = _venv_python(root)
        if cand is not None:
            return None if _is_same_interpreter(cand) else cand
    return None


def _run_via_subprocess(
    interpreter: Any,
    target_path: Any,
    *,
    mode: str,
    claim: str | None,
    width: str | int,
) -> list[FigureCheck]:
    """Execute ``_check_runner.py`` in a subprocess using ``interpreter``."""
    import subprocess
    import tempfile
    from pathlib import Path

    pkg_dir = Path(__file__).resolve().parent
    runner = pkg_dir / "_check_runner.py"
    mintfig_root = pkg_dir.parent

    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    root_str = str(mintfig_root)
    if mintfig_root.name in {"site-packages", "dist-packages"}:
        env["PYTHONPATH"] = f"{existing_pp}{os.pathsep}{root_str}" if existing_pp else root_str
    else:
        env["PYTHONPATH"] = f"{root_str}{os.pathsep}{existing_pp}" if existing_pp else root_str

    with tempfile.NamedTemporaryFile(prefix="mintfig_check_", suffix=".json", delete=False) as tf:
        out_path = Path(tf.name)
    try:
        cmd = [
            os.fspath(interpreter),
            str(runner),
            "--target",
            str(Path(target_path).resolve()),
            "--mode",
            mode,
            "--output",
            str(out_path),
            "--width",
            str(width),
            "--mintfig-root",
            root_str,
        ]
        if claim is not None:
            cmd.extend(["--claim", claim])
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
        raw_out = out_path.read_text(encoding="utf-8") if out_path.is_file() else ""
        if raw_out.strip():
            payload = json.loads(raw_out)
            if payload.get("ok"):
                return [FigureCheck(r) for r in payload.get("reports", [])]
            err_type = payload.get("error_type", "RuntimeError")
            err_msg = payload.get("error", "Script execution failed")
            if err_type == "FileNotFoundError":
                raise FileNotFoundError(err_msg)
            if err_type == "ValueError":
                raise ValueError(err_msg)
            raise RuntimeError(f"{err_type}: {err_msg}")
        stderr = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(
            f"Subprocess check failed (exit {proc.returncode}) with {interpreter}: {stderr}"
        )
    finally:
        if out_path.exists():
            out_path.unlink()


def _run_with_savefig_hook(
    target_path: Any,
    exec_fn: Any,
    *,
    claim: str | None = None,
    width: str | int = "chat",
) -> list[FigureCheck]:
    """Run ``exec_fn()`` under the Agg backend and ``Figure.savefig`` / ``plt.show`` hooks."""
    import sys
    from pathlib import Path

    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure

    target = Path(target_path).resolve()
    saves: dict[int, tuple[Any, str, dict[str, Any]]] = {}
    original_save, original_show = Figure.savefig, plt.show
    busy = False

    def _recording_save(self: Any, fname: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal busy
        out = original_save(self, fname, *args, **kwargs)
        if not busy and isinstance(fname, (str, os.PathLike)):
            name = os.fspath(fname)
            prev = saves.get(id(self))
            if prev is None or (not prev[1].lower().endswith(".png") and name.lower().endswith(".png")):
                saves[id(self)] = (self, name, {"dpi": kwargs.get("dpi"), "bbox_inches": kwargs.get("bbox_inches")})
        return out

    reports: list[FigureCheck] = []
    cwd, argv = os.getcwd(), sys.argv
    Figure.savefig = _recording_save  # type: ignore[method-assign]
    plt.show = lambda *a, **k: None  # type: ignore[assignment]
    sys.path.insert(0, str(target.parent))
    try:
        os.chdir(target.parent)
        sys.argv = [str(target)]
        plt.close("all")
        exec_fn(target)
        busy = True
        for fig, name, kw in saves.values():
            dpi = kw["dpi"] if isinstance(kw["dpi"], (int, float)) else None
            bbox = kw["bbox_inches"] if isinstance(kw["bbox_inches"], str) else None
            report = check(fig, claim, width=width, dpi=dpi, bbox_inches=bbox)
            report["path"] = name
            reports.append(report)
        saved = {id(fig) for fig, _, _ in saves.values()}
        for num in plt.get_fignums():
            fig = plt.figure(num)
            if id(fig) not in saved:
                report = check(fig, claim, width=width)
                report["path"] = None
                reports.append(report)
    finally:
        Figure.savefig = original_save  # type: ignore[method-assign]
        plt.show = original_show  # type: ignore[assignment]
        os.chdir(cwd)
        sys.argv = argv
        if sys.path and sys.path[0] == str(target.parent):
            sys.path.pop(0)
        plt.close("all")
    return reports


def _run_script_in_process(
    path: str | os.PathLike[str],
    *,
    claim: str | None = None,
    width: str | int = "chat",
) -> list[FigureCheck]:
    import runpy
    from pathlib import Path

    script = Path(path).resolve()
    if not script.is_file():
        raise FileNotFoundError(f"No such script: {script}")
    return _run_with_savefig_hook(
        script,
        lambda p: runpy.run_path(str(p), run_name="__main__"),
        claim=claim,
        width=width,
    )


def check_script(
    path: str | os.PathLike[str],
    *,
    claim: str | None = None,
    width: str | int = "chat",
    python: str | os.PathLike[str] | None = None,
) -> list[FigureCheck]:
    """Run a plotting script and :func:`check` every figure it saves (or leaves open).

    The script runs with the Agg backend, from its own folder, with ``plt.show()``
    as a no-op. Each figure is checked once, as it was saved (its ``dpi`` and
    ``bbox_inches``), preferring the PNG when it is saved in several formats. The
    report's ``path`` is the file it was saved to (``None`` if it was never saved).
    Exceptions from the script propagate.

    When ``python`` is given (or a project virtualenv is auto-detected) and differs
    from ``sys.executable``, the script executes in that interpreter via a subprocess
    so scripts importing project-local packages (pandas, seaborn, scipy) work under ``uvx``.
    """
    from pathlib import Path

    script = Path(path).resolve()
    if not script.is_file():
        raise FileNotFoundError(f"No such script: {script}")
    interp = _resolve_python(script, python)
    if interp is not None:
        return _run_via_subprocess(interp, script, mode="script", claim=claim, width=width)
    return _run_script_in_process(script, claim=claim, width=width)


_PYTHON_CELL_MAGICS = frozenset({"time", "capture", "prun"})
_HELP_LOOKUP_RE = re.compile(r"^(?:\?{1,2}[A-Za-z_][\w.]*|[A-Za-z_][\w.]*\?{1,2})\s*$")


def _strip_ipython_magics(source: str) -> str:
    """Strip IPython ``%``/``%%`` magics, ``!`` shell escapes, and ``?`` help queries."""
    lines = source.splitlines()
    first_idx = next((i for i, ln in enumerate(lines) if ln.strip()), None)
    if first_idx is None:
        return ""
    first = lines[first_idx].lstrip()
    if first.startswith("%%"):
        m = re.match(r"%%\s*(\w+)", first)
        if m and m.group(1).lower() in _PYTHON_CELL_MAGICS:
            lines[first_idx] = "# skipped cell magic"
        else:
            return ""
    out: list[str] = []
    for ln in lines:
        stripped = ln.lstrip()
        indent = ln[: len(ln) - len(stripped)]
        if stripped.startswith(("%", "!")) or _HELP_LOOKUP_RE.match(stripped):
            out.append(f"{indent}pass  # skipped magic" if indent else "# skipped magic")
        else:
            out.append(ln)
    return "\n".join(out)


def _run_notebook_in_process(
    path: str | os.PathLike[str],
    *,
    claim: str | None = None,
    width: str | int = "chat",
) -> list[FigureCheck]:
    from pathlib import Path

    nb_path = Path(path).resolve()
    if not nb_path.is_file():
        raise FileNotFoundError(f"No such notebook: {nb_path}")
    data = json.loads(nb_path.read_text(encoding="utf-8"))
    cells = data.get("cells")
    if not isinstance(cells, list):
        raise TypeError(f"Invalid notebook (missing 'cells' list): {nb_path}")

    code_cells: list[tuple[int, str]] = []
    for idx, cell in enumerate(cells):
        if not isinstance(cell, dict) or cell.get("cell_type") != "code":
            continue
        raw_src = cell.get("source", "")
        src = "".join(raw_src) if isinstance(raw_src, list) else str(raw_src)
        cleaned = _strip_ipython_magics(src)
        if cleaned.strip():
            code_cells.append((idx, cleaned))

    def _exec_nb(target: Path) -> None:
        ns: dict[str, Any] = {"__name__": "__main__", "__file__": str(target)}
        for idx, cleaned in code_cells:
            code_obj = compile(cleaned, f"{target.name}#cell-{idx}", "exec")
            exec(code_obj, ns)  # noqa: S102 - executing user notebook cells like runpy

    return _run_with_savefig_hook(nb_path, _exec_nb, claim=claim, width=width)


def check_notebook(
    path: str | os.PathLike[str],
    *,
    claim: str | None = None,
    width: str | int = "chat",
    python: str | os.PathLike[str] | None = None,
) -> list[FigureCheck]:
    """Execute a Jupyter notebook's code cells in order and :func:`check` every figure.

    Zero extra dependencies: parses ``.ipynb`` JSON directly, strips IPython ``%``/``%%``
    magics and ``!`` shell escapes cleanly, and audits every saved or left-open figure
    under the same Agg/``savefig`` hook as :func:`check_script`.
    """
    from pathlib import Path

    nb_path = Path(path).resolve()
    if not nb_path.is_file():
        raise FileNotFoundError(f"No such notebook: {nb_path}")
    interp = _resolve_python(nb_path, python)
    if interp is not None:
        return _run_via_subprocess(interp, nb_path, mode="notebook", claim=claim, width=width)
    return _run_notebook_in_process(nb_path, claim=claim, width=width)


def format_report(report: Mapping[str, Any]) -> str:
    """A terminal view of one :func:`check` report."""
    lines = [f"{report.get('path') or 'figure'}: {'SHIP' if report.get('ship') else 'FIX FIRST'}"]
    disp = report.get("display") or {}
    if disp.get("png_px"):
        lines.append(f"  read at {disp.get('width_px')} px wide; PNG {disp['png_px'][0]}×{disp['png_px'][1]} px; "
                     f"smallest text {disp.get('min_text_px')} px")
    claim = report.get("claim")
    if claim:
        lines.append(f"  claim ({claim.get('source')}): {claim['text']!r}")
        for n in claim["numbers"]:
            mark = "found" if n["found"] else ("not checked" if claim.get("hedged") else "NOT FOUND")
            detail = n["how"] if n["found"] else (f"closest: {n['nearest']}" if n.get("nearest") else "")
            lines.append(f"    {n['text']}: {mark}" + (f" ({detail})" if detail else ""))
    for i in report.get("issues", []):
        lines.append(f"  {i['severity']} {i['rule']}: {i['message']}")
        lines.append(f"    fix: {i['fix_hint']}")
    for a in report.get("advisories", []):
        lines.append(f"  advisory {a['rule']}: {a['message']}")
        lines.append(f"    try: {a['fix_hint']}")
    facts = [f for p in report.get("panels", []) for f in p.get("facts", [])]
    if facts:
        lines.append("  facts read from the plotted data:")
        lines += [f"    - {f}" for f in facts[:8]]
    return "\n".join(lines)
