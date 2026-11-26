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

from .epistemic import _HEDGE_RE, claim_numbers, pair_derivations, stated_match

__all__ = ["MIN_TEXT_PX", "WIDTHS", "FigureCheck", "check", "check_script", "format_report"]

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


def _headline(fig: Any, renderer: Any) -> str | None:
    """Where a reader looks for the claim: the largest figure-level text or title, the
    highest one on a tie (a suptitle over a subtitle, a title over a footnote)."""
    cands = [getattr(fig, "_suptitle", None), *fig.texts]
    for ax in fig.axes:
        if ax.get_visible():
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


def _read_bars(ax: Any) -> tuple[dict[str, dict[str, float]], str, list[Any]]:
    """Bar values as {series: {category: value}}, the orientation and the containers."""
    from matplotlib.container import BarContainer

    containers = [c for c in ax.containers if isinstance(c, BarContainer) and len(c.patches)]
    series: dict[str, dict[str, float]] = {}
    orientation = "vertical"
    if not containers:
        return series, orientation, []
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
    return series, orientation, containers


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


def _read_axes(ax: Any, index: int, cands: _Candidates) -> dict[str, Any]:
    from matplotlib.collections import PathCollection, PolyCollection
    from matplotlib.image import AxesImage

    panel: dict[str, Any] = {"axes": index, "kind": "empty", "title": ax.get_title() or None,
                             "x_label": ax.get_xlabel() or None, "y_label": ax.get_ylabel() or None,
                             "values": {}, "facts": []}
    facts: list[str] = panel["facts"]
    kinds: list[str] = []

    bars, orientation, bar_containers = _read_bars(ax)
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
        value_lim = ax.get_ylim() if orientation == "vertical" else ax.get_xlim()
        scale = ax.get_yscale() if orientation == "vertical" else ax.get_xscale()
        allv = [v for vals in bars.values() for v in vals.values()]
        lo_lim = min(value_lim)
        hi_lim = max(value_lim)
        bars_from_zero = all(
            abs(r.get_y() if orientation == "vertical" else r.get_x()) < 1e-12
            for c in bar_containers for r in c.patches
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

    means: dict[str, tuple[float, float]] = {}
    for coll in ax.collections:
        if isinstance(coll, PolyCollection) and not isinstance(coll, PathCollection):
            panel["bands"] = panel.get("bands", 0) + 1
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
            if lo > 0:
                cands.other.append(("highest/lowest cell ratio", hi / lo))
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


def _nearest(val: float, kind: str, cands: _Candidates, text: str = "") -> str | None:
    """The derivation closest to a claimed number that was not found: what the data says.
    Derivations naming something the claim names ("retrieval") come first."""
    pool = [(how, v) for how, v in _derivations(cands, kind)
            if kind == "fold" or not how.startswith("x=") and " at x" not in how.split(":")[0][-6:]]
    pool = [(how, v) for how, v in pool if math.isfinite(v) and v > 0]
    if not pool:
        return None
    pool = [(how, v) for how, v in pool if 0.25 <= v / max(val, 1e-300) <= 4]
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
    seen: dict[str, tuple[str, float, str]] = {}
    for unit in _units(fig):
        for kind, val, raw in claim_numbers(text, unit):
            idx = text.find(raw)
            if idx >= 0 and _COUNT_BEFORE.search(text[:idx]):
                continue
            seen.setdefault(f"{idx}:{raw}", (kind, val, raw))
    hedged = bool(_HEDGE_RE.search(text))
    words = _claim_words(text)
    numbers = []
    for kind, val, raw in seen.values():
        matches = [how for how, cand in _derivations(cands, kind) if _close(val, raw, cand)]
        if kind in {"plain", "points"}:
            crossing = _crossing_match(val, raw, [v for k, v, r in seen.values() if r != raw], cands)
            if crossing is not None:
                matches.insert(0, crossing)
        # Several derivations may give the number: report the one naming what the claim names.
        found = max(matches, key=lambda how: _named(how, words)) if matches else None
        entry = {"text": raw, "value": val, "kind": kind, "found": found is not None,
                 "how": found or ("hedged; not checked" if hedged else None)}
        if found is None:
            nearest = _nearest(val, kind, cands, text)
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
        cands = _Candidates()
        panels = [
            _read_axes(ax, i, cands)
            for i, ax in enumerate(figure.axes)
            if ax.get_visible() and (ax.axison or ax.images)
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
        if "lines" in p["kind"] or "scatter" in p["kind"] or "bars" in p["kind"] or "intervals" in p["kind"]:
            for axis, label in (("x", ax.get_xlabel()), ("y", ax.get_ylabel())):
                ticks = [t for _, t in _tick_names(ax, axis)]
                numeric = ticks and all(_is_numeric_label(t) for t in ticks)
                if numeric and not (label or "").strip() and axis in _value_axes(p, ax):
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
    if "lines" in panel["kind"] or "scatter" in panel["kind"]:
        return {"x", "y"}
    bars = panel["values"].get("bars")
    if bars:
        from matplotlib.container import BarContainer

        c = next((c for c in ax.containers if isinstance(c, BarContainer)), None)
        return {"y"} if (getattr(c, "orientation", "vertical") or "vertical") == "vertical" else {"x"}
    if "intervals" in panel["kind"]:
        return {"x", "y"}
    return set()


def _twin_axes(fig: Any) -> int:
    seen = 0
    axes = [ax for ax in fig.axes if ax.get_visible()]
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


# --------------------------------------------------------------------------- scripts


def check_script(
    path: str | os.PathLike[str],
    *,
    claim: str | None = None,
    width: str | int = "chat",
) -> list[FigureCheck]:
    """Run a plotting script and :func:`check` every figure it saves (or leaves open).

    The script runs with the Agg backend, from its own folder, with ``plt.show()``
    as a no-op. Each figure is checked once, as it was saved (its ``dpi`` and
    ``bbox_inches``), preferring the PNG when it is saved in several formats. The
    report's ``path`` is the file it was saved to (``None`` if it was never saved).
    Exceptions from the script propagate.
    """
    import runpy
    import sys
    from pathlib import Path

    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure

    script = Path(path).resolve()
    if not script.is_file():
        raise FileNotFoundError(f"No such script: {script}")
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
    sys.path.insert(0, str(script.parent))
    try:
        os.chdir(script.parent)
        sys.argv = [str(script)]
        plt.close("all")
        runpy.run_path(str(script), run_name="__main__")
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
        if sys.path and sys.path[0] == str(script.parent):
            sys.path.pop(0)
        plt.close("all")
    return reports


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
