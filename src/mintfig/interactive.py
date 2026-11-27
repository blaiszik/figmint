"""Self-contained HTML delivery for mintfig figures.

Emits a zero-dependency, zero-request HTML5 document (or an embeddable fragment for
Jupyter ``_repr_html_()`` and briefings) that earns being HTML:

* **Responsive.** The figure is laid out for small containers (360 px, panels
  stacked), at ``narrow`` (450 px) and at its own width (plus ``chat`` for a slide);
  a container query on the fragment root shows the layout that fits, so text stays
  at or above the 11 px floor wherever the reader's column is at least 360 px wide.
  A figure that cannot be laid out cleanly that small keeps the narrow layout below
  450 px; ``data-mf-layouts`` on the root lists the widths embedded.
* **Light and dark from one file.** For the default style, every colour that changes
  between the light render and a dark twin render becomes
  ``var(--mf-<token>, <light hex>)``; the dark values apply under
  ``prefers-color-scheme: dark`` or a ``data-mf-scheme="dark"`` attribute on the root
  or an ancestor (``"light"`` pins light). When the two renders differ in more than
  colour, the dark render is embedded and switched instead. An explicit style
  (``dark``, ``paper``, ``mono``, ...) keeps its own colours.
* **Details on demand.** Every data mark carries ``data-mf``; one JSON map gives its
  panel, name, x, value, interval and n. Hover or focus shows them; a click copies a
  one-line citation (``ablation.png · b · no retrieval @ 500 = 0.52``).
* **No chrome.** One quiet line under the figure: ``data · svg · spec``.

``render_html_fragment`` also serves pages that hold several figures (``mint.brief``):
``facts=False``, ``caption=`` and, for a static thumbnail, ``responsive=False``.
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

import matplotlib as mpl

from ._explain.core import ExplainError, Panel, _GlyphCapture
from ._explain.layout import Explanation, explain_from_spec
from ._explain.marks import BOX_ATTR, GID_PREFIX, MARKS_ATTR, QUIET_ATTR, tagged
from .themes import THEMES, Theme, relative_luminance

__all__ = ["render_html", "render_html_fragment"]

_XML_DECL_RE = re.compile(r"^\s*<\?xml[^>]*\?>\s*", re.IGNORECASE)
_DOCTYPE_RE = re.compile(r"^\s*<!DOCTYPE[^>]*>\s*", re.IGNORECASE)
_METADATA_RE = re.compile(r"\s*<metadata>.*?</metadata>", re.DOTALL)
_COLOR_RE = re.compile(r"(?<=: )(#[0-9a-fA-F]{6})\b")
_ID_RE = re.compile(r' id="([^"]+)"')
_REF_RE = re.compile(r'(href="#|url\(#)([^")]+)')
_GLOBAL_STYLE = '<style type="text/css">*{'
_MARK_G_RE = re.compile(r'<g id="' + re.escape(GID_PREFIX) + r'([^"]+)"')
#: Fixed salt so clip-path ids are stable: the light and dark renders must match.
_SVG_RC = {"svg.hashsalt": "mintfig"}
#: Colour fields a dark twin takes from the ``dark`` style (fonts and strokes stay).
_COLOUR_FIELDS = (
    "background", "ink", "muted", "axis", "grid", "context_line", "context_fill",
    "zero_line", "series_colors", "accent_colors", "seq_stops", "div_low", "div_high",
    "div_mid", "panel_tag_color",
)
_LAYOUT_PX = {"narrow": 450, "chat": 700, "slide": 1280}
#: The small-container layout: shown at 360 px, 78 mm wide keeps 7 pt text at 11.4 px.
_SMALL_PX = 360
_SMALL_MM = 78.0
_MIN_TEXT_PX = 11.0
#: A relate panel with more points than this gets one mark per group, not one per point.
_MAX_POINT_MARKS = 300
_seen_roots: dict[str, int] = {}


def _ensure_explanation(exp_or_spec: Explanation | Mapping[str, Any]) -> Explanation:
    """Resolve an ``Explanation`` instance or build one from a JSON spec dict."""
    if isinstance(exp_or_spec, Explanation):
        return exp_or_spec
    if isinstance(exp_or_spec, Mapping):
        return explain_from_spec(exp_or_spec)
    raise TypeError(
        "Expected an Explanation or a spec mapping, "
        f"got {type(exp_or_spec).__name__}."
    )


def _safe_json_for_script(obj: Any) -> str:
    """Serialize ``obj`` to compact JSON safe for embedding inside an HTML ``<script>`` tag.

    Replaces ``<``, ``>``, ``&``, and Unicode line separators so untrusted data
    can never terminate a ``<script>`` block or inject HTML comments.
    """
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return (
        raw.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )


def _num(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _js_num(v: Any) -> str:
    """``String(+v.toPrecision(6))`` as the page script writes a value."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return str(v)
    x = float(f"{float(v):.6g}")
    if x == int(x) and abs(x) < 1e21:
        return str(int(x))
    if 1e-6 <= abs(x) < 1e21:
        import numpy as np

        return str(np.format_float_positional(x, trim="-"))
    mant, _, exp = repr(x).partition("e")
    return f"{mant}e{int(exp):+d}".replace("e+-", "e-")


def _mark_text(rec: Mapping[str, Any]) -> str:
    """The tooltip of a mark, which is also its accessible name."""
    head = "" if rec.get("name") is None else str(rec["name"])
    if rec.get("x") is not None:
        head += f" @ {rec['x']}"
    unit = rec.get("unit")
    sep = "" if not unit or re.match(r"^[%\N{DEGREE SIGN}]", str(unit)) else " "
    text = f"{head} = {_js_num(rec.get('value'))}" + (f"{sep}{unit}" if unit else "")
    if rec.get("lo") is not None and rec.get("hi") is not None:
        text += f"  [{_js_num(rec['lo'])}, {_js_num(rec['hi'])}]"
    if rec.get("n") is not None:
        text += f"  n={rec['n']}"
    return text


def _label_attrs(rec: Mapping[str, Any]) -> str:
    return f' role="img" aria-label="{html.escape(_mark_text(rec), quote=True)}"'


def _group_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """One mark for a group of points: median and range of its values, and its size."""
    vals = sorted(float(r["value"]) for r in records if _is_numeric_cell(r.get("value")))
    names = {r.get("name") for r in records}
    name = next(iter(names)) if len(names) == 1 and None not in names else "points"
    out: dict[str, Any] = {"name": name, "x": "median, range", "n": len(records)}
    if vals:
        mid = len(vals) // 2
        med = vals[mid] if len(vals) % 2 else 0.5 * (vals[mid - 1] + vals[mid])
        out.update(value=med, lo=vals[0], hi=vals[-1])
    if records and records[0].get("unit"):
        out["unit"] = records[0]["unit"]
    return out


def _render_svg(exp: Explanation, *, interactive: bool = True) -> tuple[str, dict[str, Any]]:
    """Export ``exp.fig`` as inline ``<svg>`` plus the data of each tagged mark.

    Element marks (a bar, a cell, a span) get ``data-mf="<key>"``; marks that share
    one artist (line vertices, scatter dots, heat-table cells) get a transparent,
    focusable hit target. ``interactive=False`` drops the tags and returns no data.
    """
    buf = io.BytesIO()
    with exp.theme.rc_context(exp.spec), mpl.rc_context(_SVG_RC), _GlyphCapture():
        exp.fig.savefig(
            buf,
            format="svg",
            facecolor=exp.theme.background,
            edgecolor=exp.theme.background,
        )
    svg = buf.getvalue().decode("utf-8")
    svg = _METADATA_RE.sub("", _DOCTYPE_RE.sub("", _XML_DECL_RE.sub("", svg))).strip()
    # Matplotlib writes the pieces of a coloured headline ("Only ", "retrieval", " gets ...")
    # as separate <text> elements; SVG collapses their edge spaces unless told not to.
    svg = svg.replace('<text style="', '<text style="white-space: pre; ')
    if not interactive:
        return svg, {}
    marks: dict[str, Any] = {}
    hits: list[str] = []
    fig = exp.fig
    k = 72.0 / float(fig.dpi)
    w_pt, h_pt = float(fig.get_figwidth()) * 72.0, float(fig.get_figheight()) * 72.0
    artists = tagged(fig)
    # A dense scatter gets one mark per group (its artist), not a hit target per point.
    points: dict[str, int] = {}
    for artist in artists:
        items = getattr(artist, MARKS_ATTR)
        if items[0][0] is not None and getattr(artist, BOX_ATTR, None) is None:
            panel = str(artist.get_gid())[len(GID_PREFIX):].rsplit("-", 1)[0]
            points[panel] = points.get(panel, 0) + len(items)
    dense = {
        p for p, n in points.items()
        if n > _MAX_POINT_MARKS and p in exp.panels and exp.panels[p].kind == "relate"
    }
    quiet: set[str] = set()
    for artist in artists:
        key = str(artist.get_gid())[len(GID_PREFIX):]
        panel = key.rsplit("-", 1)[0]
        items = getattr(artist, MARKS_ATTR)
        if getattr(artist, QUIET_ATTR, False):
            quiet.add(key)
        if items[0][0] is None or (panel in dense and getattr(artist, BOX_ATTR, None) is None):
            if f'<g id="{GID_PREFIX}{key}"' in svg:
                rec = items[0][1] if items[0][0] is None else _group_summary([r for _, r in items])
                marks[key] = {"panel": panel, **rec}
            continue
        if not artist.get_visible():
            continue
        get_offsets = getattr(artist, "get_offset_transform", None)
        tr = get_offsets() if get_offsets is not None else artist.get_transform()
        box = getattr(artist, BOX_ATTR, None)
        for i, (xy, rec) in enumerate(items):
            x, y = tr.transform(xy)
            cx, cy = x * k, h_pt - y * k
            if not (-1 <= cx <= w_pt + 1 and -1 <= cy <= h_pt + 1):
                continue
            mk = f"{key}.{i}"
            marks[mk] = {"panel": panel, **rec}
            if box is None:
                hits.append(
                    f'<circle cx="{_num(cx)}" cy="{_num(cy)}" r="6" data-mf="{mk}" tabindex="0"'
                    f"{_label_attrs(rec)}/>"
                )
                continue
            (x0, y0), (x1, y1) = tr.transform([(xy[0] - box[0], xy[1] - box[1]),
                                               (xy[0] + box[0], xy[1] + box[1])])
            rx, ry = min(x0, x1) * k, h_pt - max(y0, y1) * k
            hits.append(
                f'<rect x="{_num(rx)}" y="{_num(ry)}" width="{_num(abs(x1 - x0) * k)}" '
                f'height="{_num(abs(y1 - y0) * k)}" data-mf="{mk}" tabindex="0"'
                f"{_label_attrs(rec)}/>"
            )
    def _open_g(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in marks:
            return "<g"
        if key in quiet:  # same data as a focusable mark beside it: hover only
            return f'<g data-mf="{key}"'
        return f'<g data-mf="{key}" tabindex="0"{_label_attrs(marks[key])}'

    svg = _MARK_G_RE.sub(_open_g, svg)
    zones: list[str] = []
    axes_map = getattr(exp, "axes", {}) or {}
    for pkey, panel in exp.panels.items():
        ax = axes_map.get(pkey)
        if panel.kind not in {"trend", "relate"} or ax is None:
            continue
        if not ax.get_visible():
            continue
        bbox = ax.bbox
        bx = bbox.x0 * k
        by = h_pt - bbox.y1 * k
        bw = (bbox.x1 - bbox.x0) * k
        bh = (bbox.y1 - bbox.y0) * k
        if bw <= 0 or bh <= 0:
            continue
        xlim = ax.get_xlim()
        xscale = str(ax.get_xscale() or "linear")
        xlabel = str(panel.spec.get("x_label") or "X")
        zones.append(
            f'<rect class="mf-brush-zone" x="{_num(bx)}" y="{_num(by)}" '
            f'width="{_num(bw)}" height="{_num(bh)}" '
            f'data-mf-panel="{html.escape(str(pkey), quote=True)}" '
            f'data-mf-x0="{xlim[0]:.10g}" data-mf-x1="{xlim[1]:.10g}" '
            f'data-mf-xscale="{html.escape(xscale, quote=True)}" '
            f'data-mf-xlabel="{html.escape(xlabel, quote=True)}" '
            'fill="none" pointer-events="none"/>'
        )
    extras = ""
    if zones:
        extras += '<g class="mf-brush-zones" pointer-events="none">' + "".join(zones) + "</g>"
    if hits:
        extras += '<g class="mf-hits" fill="none" pointer-events="all">' + "".join(hits) + "</g>"
    if extras:
        cut = svg.rstrip().rfind("</svg>")
        svg = svg[:cut] + extras + svg[cut:]
    return svg, marks


def _scope_ids(svg: str, prefix: str) -> str:
    """Renumber the ids other elements reference as ``<prefix><n>``; drop the rest.

    Ids stay unique when several SVGs share a page, and two renders that differ only
    in colour get identical ids (Matplotlib hashes marker style into its ids).
    """
    refs = {m.group(2) for m in _REF_RE.finditer(svg)}
    names: dict[str, str] = {}

    def _rename(m: re.Match[str]) -> str:
        if m.group(1) not in refs:
            return ""
        names[m.group(1)] = f"{prefix}{len(names)}"
        return f' id="{names[m.group(1)]}"'

    svg = _ID_RE.sub(_rename, svg)
    svg = _REF_RE.sub(lambda m: m.group(1) + names.get(m.group(2), m.group(2)), svg)
    # Matplotlib's global "*{stroke-linejoin...}" rule would restyle the host page:
    # scope it to this SVG (which keeps it when the SVG is saved on its own).
    if _GLOBAL_STYLE in svg:
        svg = svg.replace("<svg ", f'<svg id="{prefix}svg" ', 1)
        svg = svg.replace(_GLOBAL_STYLE, _GLOBAL_STYLE.replace("*{", f"#{prefix}svg *{{"), 1)
    return svg


def _theme_tokens(theme: Theme) -> list[tuple[str, str]]:
    """``(token, hex)`` for every colour a theme defines, in naming priority."""
    out = [
        ("bg", theme.background), ("ink", theme.ink), ("muted", theme.muted),
        ("axis", theme.axis), ("grid", theme.grid), ("context", theme.context_line),
        ("context-fill", theme.context_fill), ("zero", theme.zero_line),
        ("tag", theme.resolved_panel_tag_color), ("div-mid", theme.div_mid),
    ]
    for prefix, seq in (("s", theme.series_colors), ("a", theme.accent_colors),
                        ("seq", theme.seq_stops), ("div-lo", theme.div_low),
                        ("div-hi", theme.div_high)):
        out.extend((f"{prefix}{i}", c) for i, c in enumerate(seq))
    return [(name, c.lower()) for name, c in out]


class _Palette:
    """CSS custom properties shared by every layout of one fragment."""

    def __init__(self, light: Theme, dark: Theme) -> None:
        self.by_pair: dict[tuple[str, str], str] = {}
        for (name, lo), (_, dk) in zip(_theme_tokens(light), _theme_tokens(dark), strict=True):
            self.by_pair.setdefault((lo, dk), name)
        self._mint: dict[str, str] = dict(_theme_tokens(THEMES["mint"]))
        self._pine: dict[str, str] = dict(_theme_tokens(THEMES["pine"]))
        self.used: dict[str, tuple[str, str]] = {}

    def themed(self, light_svg: str, dark_svg: str) -> str | None:
        """``light_svg`` with each colour that changes in ``dark_svg`` as a CSS variable.

        Returns None when the renders differ in anything but colour.
        """
        lp, dp = _COLOR_RE.split(light_svg), _COLOR_RE.split(dark_svg)
        if len(lp) != len(dp) or lp[::2] != dp[::2]:
            return None
        out = lp[:]
        derived = sum(1 for n in self.used if n.startswith("c") and n[1:].isdigit())
        for i in range(1, len(lp), 2):
            lo, dk = lp[i].lower(), dp[i].lower()
            if lo == dk:
                continue
            name = self.by_pair.get((lo, dk))
            if name is None:
                name = f"c{derived}"
                derived += 1
                self.by_pair[(lo, dk)] = name
            self.used[name] = (lo, dk)
            out[i] = f"var(--mf-{name}, {lp[i]})"
        return "".join(out)

    def css(self, scheme: str) -> str:
        if scheme == "mint":
            return "".join(
                f"--mf-{n}:{self._mint.get(n, pair[0])};" for n, pair in self.used.items()
            )
        if scheme == "pine":
            return "".join(
                f"--mf-{n}:{self._pine.get(n, pair[1])};" for n, pair in self.used.items()
            )
        idx = 1 if scheme == "dark" else 0
        return "".join(f"--mf-{n}:{pair[idx]};" for n, pair in self.used.items())


def _dark_twin_style() -> Theme:
    """The default style with the ``dark`` style's colours (and nothing else) swapped in."""
    dark = THEMES["dark"]
    return replace(
        THEMES["mintfig"],
        **{f: getattr(dark, f) for f in _COLOUR_FIELDS},
        extra_rc={"xtick.color": dark.axis, "ytick.color": dark.axis},
    )


def _rebuild(exp: Explanation, **changes: Any) -> Explanation | None:
    """The same figure with ``changes`` applied to its spec, or None if it cannot be rebuilt.

    A new width first keeps the figure's panel layout, then lets ``explain`` choose
    one (two side-by-side panels stack at ``narrow``).
    """
    spec = {**exp.to_spec(), **changes}
    tries = [spec, {k: v for k, v in spec.items() if k != "layout"}] if "width" in changes else [spec]
    for attempt in tries:
        try:
            return explain_from_spec(attempt, strict=exp.strict)
        except (ExplainError, TypeError, ValueError, KeyError):
            continue
    return None


#: Layout name of a figure laid out at a width given in mm (``width=110``).
_OWN = "own"


def _own_px(exp: Explanation) -> int:
    """CSS px the figure's own layout is shown at: its preset's display width, or for a
    width in mm the same px per mm as ``chat`` (so its text keeps the chat sizes)."""
    if isinstance(exp.width, str) or exp.spec.name != "screen":
        return exp.display_width_px
    chat_mm = float(exp.spec.resolve_width_mm("chat"))
    return round(float(exp.width) * _LAYOUT_PX["chat"] / chat_mm)


def _layout_widths(exp: Explanation) -> list[str]:
    """The layouts to embed, narrowest first ("small" is the 360 px container layout).

    A figure with a width in mm embeds its own layout (``"own"``) plus every smaller one.
    """
    w = exp.width.strip().lower() if isinstance(exp.width, str) else ""
    if exp.spec.name != "screen":
        return [w or "chat"]
    if not isinstance(exp.width, str):
        own = _own_px(exp)
        smaller = [name for name in ("narrow", "chat") if _LAYOUT_PX[name] < own]
        return (["small"] if _SMALL_PX < own else []) + smaller + [_OWN]
    if w == "narrow":
        return ["small", "narrow"]
    if w == "slide":
        return ["small", "narrow", "chat", "slide"]
    return ["small", "narrow", w or "chat"]


def _small_layout(exp: Explanation) -> Explanation | None:
    """The figure stacked at 78 mm for 360 px containers, or None when that is not clean.

    Clean means it ships and its smallest text is at least 11 px at 360 px; otherwise
    the narrow layout is shown below 450 px (``data-mf-layouts`` then omits 360).
    """
    from matplotlib.text import Text

    small = _rebuild(exp, width=_SMALL_MM, layout=[[k] for k in exp.panels])
    if small is None or not small.ship:
        return None
    sizes = [
        float(t.get_fontsize())
        for t in small.fig.findobj(Text)
        if t.get_visible() and t.get_text().strip()
    ]
    px_per_pt = _SMALL_PX / (float(small.fig.get_figwidth()) * 72.0)
    return small if min(sizes, default=0.0) * px_per_pt >= _MIN_TEXT_PX else None


def _ui_tokens(theme: Theme) -> dict[str, str]:
    """Colours for the text around the figure (data line, tooltip, data tables)."""
    return {
        "bg": theme.background,
        "ink": theme.ink,
        "muted": theme.muted,
        "line": theme.grid if theme.grid.lower() != theme.background.lower() else theme.axis,
    }


def _citation_file(exp: Explanation) -> str:
    if exp.saved_path is not None:
        return exp.saved_path.name
    words = exp.takeaway.split()
    return " ".join(words[:5]) + ("\N{HORIZONTAL ELLIPSIS}" if len(words) > 5 else "")


def _root_id(spec: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(
        json.dumps(spec, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()[:10]
    n = _seen_roots.get(digest, 0)
    _seen_roots[digest] = n + 1
    return f"mf-{digest}" if n == 0 else f"mf-{digest}-{n}"


def _fmt_cell(val: Any) -> str:
    """Format a scalar cell cleanly for data-drawer tables."""
    if val is None:
        return "—"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, float):
        if not math.isfinite(val):
            return "—"
        if abs(val - round(val)) < 1e-9 and abs(val) < 1e12:
            return f"{round(val):,}"
        return f"{val:.4g}"
    if isinstance(val, int):
        return f"{val:,}"
    return str(val)


def _is_numeric_cell(val: Any) -> bool:
    if isinstance(val, bool) or val is None:
        return False
    if isinstance(val, (int, float)):
        return math.isfinite(float(val))
    return False


def _panel_data_table(panel: Panel) -> tuple[list[str], list[list[str]], list[bool], str | None]:
    """Extract ``(headers, rows, numeric_flags, note)`` from a panel's spec."""
    spec = panel.spec
    kind = panel.kind
    unit_suffix = f" ({panel.unit})" if panel.unit else ""

    if kind == "compare":
        values = spec.get("values")
        if isinstance(values, Mapping) and values:
            first_val = next(iter(values.values()))
            if isinstance(first_val, Mapping):
                series_names: list[str] = []
                for sub in values.values():
                    if isinstance(sub, Mapping):
                        for sk in sub:
                            if str(sk) not in series_names:
                                series_names.append(str(sk))
                headers = ["Item", *[f"{s}{unit_suffix}" for s in series_names]]
                rows = [
                    [
                        str(item),
                        *[_fmt_cell(sub.get(s) if isinstance(sub, Mapping) else None) for s in series_names],
                    ]
                    for item, sub in values.items()
                ]
                return headers, rows, [False, *([True] * len(series_names))], None
            items = list(values.items())
            if spec.get("sort", True):
                items.sort(
                    key=lambda kv: float(kv[1]) if _is_numeric_cell(kv[1]) else float("-inf"),
                    reverse=True,
                )
            val_col = (panel.label or "Value") + unit_suffix
            headers = ["Item", val_col]
            rows = [[str(k), _fmt_cell(v)] for k, v in items]
            return headers, rows, [False, True], None

    if kind == "share":
        parts = spec.get("parts")
        if isinstance(parts, Mapping) and parts:
            items = sorted(
                parts.items(),
                key=lambda kv: float(kv[1]) if _is_numeric_cell(kv[1]) else float("-inf"),
                reverse=True,
            )
            total = sum(float(v) for _, v in items if _is_numeric_cell(v))
            val_col = (panel.label or "Value") + unit_suffix
            headers = ["Part", val_col, "Share"]
            rows = []
            for k, v in items:
                pct = f"{(float(v) / total * 100.0):.1f}%" if total > 0 and _is_numeric_cell(v) else "—"
                rows.append([str(k), _fmt_cell(v), pct])
            return headers, rows, [False, True, True], None

    if kind == "table":
        cols = [str(c) for c in (spec.get("columns") or [])]
        raw_rows = spec.get("rows") or []
        if cols and isinstance(raw_rows, Sequence):
            num_flags = []
            for c_idx in range(len(cols)):
                col_vals = [r[c_idx] for r in raw_rows if isinstance(r, Sequence) and c_idx < len(r)]
                num_flags.append(bool(col_vals) and all(_is_numeric_cell(v) or v is None for v in col_vals))
            rows = [
                [_fmt_cell(r[c]) if c < len(r) else "—" for c in range(len(cols))]
                for r in raw_rows
                if isinstance(r, Sequence)
            ]
            # Intervals given per row ({col: {row: (lo, hi)}}) list their bounds beside the
            # column; bounds given as two columns of rows are already listed.
            iv = spec.get("interval") if isinstance(spec.get("interval"), Mapping) else {}
            for col, per_row in iv.items():
                if not isinstance(per_row, Mapping) or str(col) not in cols:
                    continue
                at = cols.index(str(col)) + 1
                cols[at:at] = [f"{col} low", f"{col} high"]
                num_flags[at:at] = [True, True]
                for out, r in zip(rows, (r for r in raw_rows if isinstance(r, Sequence))):
                    pair = per_row.get(str(r[0])) if r else None
                    ok = isinstance(pair, Sequence) and len(pair) == 2
                    out[at:at] = [_fmt_cell(pair[0]), _fmt_cell(pair[1])] if ok else ["—", "—"]
            return cols, rows, num_flags, None

    if kind == "trend":
        x_vals = spec.get("x") or []
        series = spec.get("series")
        x_hdr = str(spec.get("x_label") or "x")
        if isinstance(series, Mapping) and series:
            names = [str(k) for k in series]
            headers = [x_hdr, *[f"{n}{unit_suffix}" for n in names]]
            n_rows = max((len(v) for v in series.values() if isinstance(v, Sequence)), default=0)
            max_show = 40
            rows = []
            for idx in range(min(n_rows, max_show)):
                xv = _fmt_cell(x_vals[idx]) if idx < len(x_vals) else str(idx)
                row = [xv]
                for n in names:
                    seq = series.get(n)
                    val = seq[idx] if isinstance(seq, Sequence) and idx < len(seq) else None
                    row.append(_fmt_cell(val))
                rows.append(row)
            note = f"Showing first {max_show} of {n_rows} points." if n_rows > max_show else None
            return headers, rows, [False, *([True] * len(names))], note
        if isinstance(series, Sequence) and not isinstance(series, (str, bytes)):
            val_col = (panel.label or "Value") + unit_suffix
            headers = [x_hdr, val_col]
            max_show = 40
            rows = [
                [_fmt_cell(x_vals[i]) if i < len(x_vals) else str(i), _fmt_cell(series[i])]
                for i in range(min(len(series), max_show))
            ]
            note = f"Showing first {max_show} of {len(series)} points." if len(series) > max_show else None
            return headers, rows, [False, True], note
        points = spec.get("points")
        if isinstance(points, Mapping) and points:
            raw_names = [str(k) for k in points]
            disp_names = [n if n else (panel.label or "Value") for n in raw_names]
            headers = [x_hdr, *[f"{dn}{unit_suffix}" for dn in disp_names]]
            n_rows = max(
                (len(v) for v in points.values() if isinstance(v, Sequence)),
                default=0,
            )
            max_show = 40
            rows = []
            for idx in range(min(n_rows, max_show)):
                xv = _fmt_cell(x_vals[idx]) if idx < len(x_vals) else str(idx)
                row = [xv]
                for rname in raw_names:
                    buckets = points.get(rname)
                    mean_val: float | None = None
                    if isinstance(buckets, Sequence) and idx < len(buckets):
                        bucket = buckets[idx]
                        if isinstance(bucket, Sequence) and not isinstance(bucket, (str, bytes)):
                            nums = [float(v) for v in bucket if _is_numeric_cell(v)]
                            if nums:
                                mean_val = sum(nums) / len(nums)
                        elif _is_numeric_cell(bucket):
                            mean_val = float(bucket)
                    row.append(_fmt_cell(mean_val))
                rows.append(row)
            note = (
                f"Showing per-x replicate means (first {max_show} of {n_rows} points)."
                if n_rows > max_show
                else "Values show per-x replicate means."
            )
            return headers, rows, [False, *([True] * len(raw_names))], note

    if kind == "matrix":
        r_labels = [str(r) for r in (spec.get("rows") or [])]
        c_labels = [str(c) for c in (spec.get("cols") or [])]
        vals = spec.get("values") or []
        norm_mode = spec.get("normalize")
        show_counts = bool(spec.get("show_counts"))
        if c_labels and isinstance(vals, Sequence):
            headers = ["", *c_labels]
            raw_rows = [
                [float(v) if _is_numeric_cell(v) else None for v in rv]
                for rv in vals
                if isinstance(rv, Sequence)
            ]
            col_totals = (
                [
                    sum(r[c] for r in raw_rows if c < len(r) and r[c] is not None)
                    for c in range(len(c_labels))
                ]
                if norm_mode == "col"
                else []
            )
            rows = []
            for r_idx, row_vals in enumerate(raw_rows):
                rl = r_labels[r_idx] if r_idx < len(r_labels) else f"r{r_idx + 1}"
                row_tot = sum(v for v in row_vals if v is not None) if norm_mode == "row" else 0.0
                fmt_cells: list[str] = []
                for c_idx, v in enumerate(row_vals):
                    if v is None:
                        fmt_cells.append("—")
                    elif norm_mode in {"row", "col"}:
                        denom = row_tot if norm_mode == "row" else (col_totals[c_idx] if c_idx < len(col_totals) else 0.0)
                        pct = (100.0 * v / denom) if denom > 0 else 0.0
                        cell_s = f"{pct:.1f}%"
                        if show_counts:
                            cell_s += f" ({_fmt_cell(v)})"
                        fmt_cells.append(cell_s)
                    else:
                        fmt_cells.append(_fmt_cell(v))
                rows.append([rl, *fmt_cells])
            note = f"{norm_mode.title()}-normalized percentages" + (" with raw counts." if show_counts else ".") if norm_mode in {"row", "col"} else None
            return headers, rows, [False, *([True] * len(c_labels))], note

    if kind == "change":
        before = spec.get("before") or {}
        after = spec.get("after") or {}
        labels = spec.get("labels") or ["Before", "After"]
        lbl_b = str(labels[0]) if len(labels) >= 1 else "Before"
        lbl_a = str(labels[1]) if len(labels) >= 2 else "After"
        if isinstance(before, Mapping) and isinstance(after, Mapping):
            headers = ["Item", f"{lbl_b}{unit_suffix}", f"{lbl_a}{unit_suffix}", f"Delta{unit_suffix}"]
            rows = []
            for item, bv in before.items():
                av = after.get(item)
                if _is_numeric_cell(bv) and _is_numeric_cell(av):
                    delta = float(av) - float(bv)
                    delta_str = f"{delta:+.4g}" if abs(delta) < 1e12 else _fmt_cell(delta)
                else:
                    delta_str = "—"
                rows.append([str(item), _fmt_cell(bv), _fmt_cell(av), delta_str])
            return headers, rows, [False, True, True, True], None

    if kind == "distribution":
        groups = spec.get("groups")
        nested = (
            isinstance(groups, Mapping)
            and spec.get("facet")
            and spec.get("bins") is None
            and all(isinstance(v, Mapping) for v in groups.values())
        )
        if nested:
            headers = [
                "Facet",
                "Group",
                "n",
                f"Min{unit_suffix}",
                f"Median{unit_suffix}",
                f"Max{unit_suffix}",
            ]
            rows = []
            for fname, level in groups.items():
                for gname, vals in level.items():
                    nums = sorted(float(v) for v in vals if _is_numeric_cell(v))
                    if nums:
                        mid = len(nums) // 2
                        med = nums[mid] if len(nums) % 2 else 0.5 * (nums[mid - 1] + nums[mid])
                        rows.append(
                            [
                                str(fname),
                                str(gname),
                                str(len(nums)),
                                _fmt_cell(nums[0]),
                                _fmt_cell(med),
                                _fmt_cell(nums[-1]),
                            ]
                        )
            return headers, rows, [False, False, True, True, True, True], None
        if isinstance(groups, Mapping):
            if spec.get("mode") == "ecdf":
                headers = ["Group", "n", f"p50{unit_suffix}", f"p95{unit_suffix}", f"p99{unit_suffix}"]
                rows = []
                for gname, vals in groups.items():
                    nums = sorted(float(v) for v in vals if _is_numeric_cell(v))
                    if nums:
                        def _qp(p: float, a: list[float] = nums) -> float:
                            pos = p * (len(a) - 1)
                            lo_i = math.floor(pos)
                            hi_i = min(len(a) - 1, lo_i + 1)
                            return a[lo_i] + (pos - lo_i) * (a[hi_i] - a[lo_i])
                        rows.append([str(gname), str(len(nums)), _fmt_cell(_qp(0.5)), _fmt_cell(_qp(0.95)), _fmt_cell(_qp(0.99))])
                return headers, rows, [False, True, True, True, True], None
            headers = ["Group", "n", f"Min{unit_suffix}", f"Median{unit_suffix}", f"Max{unit_suffix}"]
            rows = []
            for gname, vals in groups.items():
                nums = sorted(float(v) for v in vals if _is_numeric_cell(v))
                if nums:
                    mid = len(nums) // 2
                    med = nums[mid] if len(nums) % 2 else 0.5 * (nums[mid - 1] + nums[mid])
                    rows.append([str(gname), str(len(nums)), _fmt_cell(nums[0]), _fmt_cell(med), _fmt_cell(nums[-1])])
            return headers, rows, [False, True, True, True, True], None
        if isinstance(groups, Sequence) and not isinstance(groups, (str, bytes)):
            nums = sorted(float(v) for v in groups if _is_numeric_cell(v))
            if nums:
                if spec.get("mode") == "ecdf":
                    def _qp1(p: float) -> float:
                        pos = p * (len(nums) - 1)
                        lo_i = math.floor(pos)
                        hi_i = min(len(nums) - 1, lo_i + 1)
                        return nums[lo_i] + (pos - lo_i) * (nums[hi_i] - nums[lo_i])
                    headers = ["Series", "n", f"p50{unit_suffix}", f"p95{unit_suffix}", f"p99{unit_suffix}"]
                    rows = [[panel.label or "Values", str(len(nums)), _fmt_cell(_qp1(0.5)), _fmt_cell(_qp1(0.95)), _fmt_cell(_qp1(0.99))]]
                    return headers, rows, [False, True, True, True, True], None
                mid = len(nums) // 2
                med = nums[mid] if len(nums) % 2 else 0.5 * (nums[mid - 1] + nums[mid])
                headers = ["Series", "n", f"Min{unit_suffix}", f"Median{unit_suffix}", f"Max{unit_suffix}"]
                rows = [[panel.label or "Values", str(len(nums)), _fmt_cell(nums[0]), _fmt_cell(med), _fmt_cell(nums[-1])]]
                return headers, rows, [False, True, True, True, True], None

    if kind == "relate":
        xs = spec.get("x") or []
        ys = spec.get("y") or []
        names = spec.get("names")
        groups = spec.get("groups")
        xh = str(spec.get("x_label") or "x")
        yh = str(spec.get("y_label") or panel.label or "y") + unit_suffix
        headers = []
        num_flags = []
        if names:
            headers.append("Name")
            num_flags.append(False)
        headers.extend([xh, yh])
        num_flags.extend([True, True])
        if groups:
            headers.append("Group")
            num_flags.append(False)
        n = min(len(xs), len(ys))
        max_show = 40
        rows = []
        for i in range(min(n, max_show)):
            row = []
            if names:
                row.append(str(names[i]) if i < len(names) else "")
            row.extend([_fmt_cell(xs[i]), _fmt_cell(ys[i])])
            if groups:
                row.append(str(groups[i]) if i < len(groups) else "")
            rows.append(row)
        note = f"Showing first {max_show} of {n} observations." if n > max_show else None
        return headers, rows, num_flags, note

    if kind == "waterfall":
        steps = spec.get("steps") or {}
        if isinstance(steps, Mapping) and steps:
            rows = []
            running = 0.0
            start_val = spec.get("start")
            if isinstance(start_val, Sequence) and not isinstance(start_val, (str, bytes)) and len(start_val) == 2:
                running = float(start_val[1])
                rows.append([str(start_val[0]), "—", _fmt_cell(running)])
            for step_nm, delta in steps.items():
                d_val = float(delta)
                running += d_val
                sign = "+" if d_val > 0 else ""
                rows.append([str(step_nm), f"{sign}{_fmt_cell(d_val)}", _fmt_cell(running)])
            if spec.get("show_total", True):
                rows.append([str(spec.get("total_label") or "Total"), "—", _fmt_cell(running)])
            return (
                ["Step", f"Delta{unit_suffix}", f"Cumulative{unit_suffix}"],
                rows,
                [False, True, True],
                None,
            )

    if kind == "timeline":
        spans = spec.get("spans") or []
        if isinstance(spans, Sequence) and spans:
            has_group = any(isinstance(s, Sequence) and len(s) >= 4 and s[3] is not None for s in spans)
            headers = ["Stage", f"Start{unit_suffix}", f"End{unit_suffix}", f"Duration{unit_suffix}"]
            num_flags = [False, True, True, True]
            if has_group:
                headers.append("Group")
                num_flags.append(False)
            rows = []
            for sp in spans:
                if not isinstance(sp, Sequence) or len(sp) < 3:
                    continue
                dur = float(sp[2]) - float(sp[1])
                row = [str(sp[0]), _fmt_cell(sp[1]), _fmt_cell(sp[2]), _fmt_cell(dur)]
                if has_group:
                    row.append(str(sp[3]) if len(sp) >= 4 and sp[3] is not None else "—")
                rows.append(row)
            return headers, rows, num_flags, None

    if kind == "flow":
        stages = spec.get("stages") or []
        if isinstance(stages, Sequence) and stages:
            has_reason = any(isinstance(s, Sequence) and len(s) >= 3 and s[2] for s in stages[1:])
            headers = ["Stage", f"Remaining{unit_suffix}", "% of start", "Step change"]
            num_flags = [False, True, True, True]
            if has_reason:
                headers.append("Reason")
                num_flags.append(False)
            rows = []
            start_v = float(stages[0][1]) if isinstance(stages[0], Sequence) and len(stages[0]) >= 2 else 1.0
            prev_v: float | None = None
            for idx_s, st in enumerate(stages):
                if not isinstance(st, Sequence) or len(st) < 2:
                    continue
                val = float(st[1])
                pct = f"{(100.0 * val / start_v):.1f}%" if start_v > 0 else "—"
                if prev_v is None:
                    chg = "—"
                else:
                    d = val - prev_v
                    sign = "+" if d > 0 else ""
                    chg = f"{sign}{_fmt_cell(d)}"
                row = [str(st[0]), _fmt_cell(val), pct, chg]
                if has_reason:
                    row.append(str(st[2]) if idx_s > 0 and len(st) >= 3 and st[2] else "—")
                rows.append(row)
                prev_v = val
            return headers, rows, num_flags, None

    if kind == "forest":
        data_map = spec.get("data")
        err_map = spec.get("error") if isinstance(spec.get("error"), Mapping) else {}
        counts_map = spec.get("n") if isinstance(spec.get("n"), Mapping) else {}
        pooled_spec = spec.get("pooled") if isinstance(spec.get("pooled"), Mapping) else None
        if isinstance(data_map, Mapping) and data_map:
            err_lbl = spec.get("error_label") or "CI"
            has_n = bool(counts_map) or (pooled_spec is not None and pooled_spec.get("n") is not None)
            headers = [
                "Item",
                (panel.label or "Estimate") + unit_suffix,
                f"Low ({err_lbl})",
                f"High ({err_lbl})",
            ]
            num_flags = [False, True, True, True]
            if has_n:
                headers.append("n")
                num_flags.append(True)
            items = list(data_map.items())
            sort_opt = spec.get("sort", True)
            if sort_opt is True or (isinstance(sort_opt, str) and sort_opt.lower() in {"desc", "descending"}):
                items.sort(key=lambda kv: float(kv[1]) if _is_numeric_cell(kv[1]) else float("-inf"), reverse=True)
            elif isinstance(sort_opt, str) and sort_opt.lower() in {"asc", "ascending"}:
                items.sort(key=lambda kv: float(kv[1]) if _is_numeric_cell(kv[1]) else float("inf"))
            rows = []
            for k, v in items:
                pair = err_map.get(k)
                lo_v = pair[0] if isinstance(pair, Sequence) and len(pair) == 2 else None
                hi_v = pair[1] if isinstance(pair, Sequence) and len(pair) == 2 else None
                row = [str(k), _fmt_cell(v), _fmt_cell(lo_v), _fmt_cell(hi_v)]
                if has_n:
                    row.append(_fmt_cell(counts_map.get(k)))
                rows.append(row)
            if pooled_spec is not None:
                row = [
                    str(pooled_spec.get("label") or "Pooled"),
                    _fmt_cell(pooled_spec.get("value")),
                    _fmt_cell(pooled_spec.get("lo")),
                    _fmt_cell(pooled_spec.get("hi")),
                ]
                if has_n:
                    row.append(_fmt_cell(pooled_spec.get("n")))
                rows.append(row)
            return headers, rows, num_flags, None

    return [], [], [], None


def _render_table_html(
    headers: list[str],
    rows: list[list[str]],
    num_flags: list[bool],
    note: str | None = None,
) -> str:
    if not headers or not rows:
        return ""
    th_cells = "".join(
        ('<th class="mf-num">' if num_flags[i] else "<th>") + f"{html.escape(h, quote=True)}</th>"
        for i, h in enumerate(headers)
    )
    body_rows = []
    for row in rows:
        td_cells = "".join(
            ('<td class="mf-num">' if i < len(num_flags) and num_flags[i] else "<td>")
            + f"{html.escape(cell, quote=True)}</td>"
            for i, cell in enumerate(row)
        )
        body_rows.append(f"<tr>{td_cells}</tr>")
    note_html = (
        f'<p class="mf-table-note">{html.escape(note, quote=True)}</p>' if note else ""
    )
    return (
        '<div class="mf-table-wrap">'
        '<table class="mf-data-table">'
        f"<thead><tr>{th_cells}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table>"
        f"{note_html}"
        "</div>"
    )


def _vars(tokens: Mapping[str, str], palette: _Palette | None, scheme: str) -> str:
    ui = "".join(f"--mf-ui-{k}:{v};" for k, v in tokens.items())
    return ui + (palette.css(scheme) if palette is not None else "")


def _css_block(
    root_id: str,
    light: Mapping[str, str],
    dark: Mapping[str, str] | None,
    palette: _Palette | None,
    breakpoints: Sequence[int],
    max_width_px: int,
    swaps: bool,
) -> str:
    r = f"#{root_id}"
    out = [
        (
            f"{r}{{{_vars(light, palette, 'light')}container:{root_id}/inline-size;"
            f"width:100%;max-width:{max_width_px}px;margin:0 auto;position:relative;"
            "color:var(--mf-ui-ink);background:var(--mf-ui-bg);"
            'font:13px/1.45 system-ui,-apple-system,"Segoe UI",Helvetica,Arial,sans-serif}'
        ),
        f"{r} svg{{display:block;width:100%;height:auto}}",
        f"{r} .mf-v{{display:none}}{r} .mf-v0{{display:block}}",
        f"{r} .mf-dark{{display:none}}",
    ]
    for i, px in enumerate(breakpoints[1:], 1):
        out.append(
            f"@container {root_id} (min-width:{px}px){{{r} .mf-v{i - 1}{{display:none}}"
            f"{r} .mf-v{i}{{display:block}}}}"
        )
    if dark is not None:
        show_dark = f"{r} .mf-light{{display:none}}{r} .mf-dark{{display:block}}" if swaps else ""
        show_light = f"{r} .mf-light{{display:block}}{r} .mf-dark{{display:none}}" if swaps else ""
        dark_sel = f'{r}[data-mf-scheme="dark"],[data-mf-scheme="dark"] {r}'
        light_sel = f'{r}[data-mf-scheme="light"],[data-mf-scheme="light"] {r}'
        mint_sel = f'{r}[data-mf-scheme="mint"],[data-mf-scheme="mint"] {r}'
        pine_sel = f'{r}[data-mf-scheme="pine"],[data-mf-scheme="pine"] {r}'
        mint_ui = _ui_tokens(THEMES["mint"])
        pine_ui = _ui_tokens(THEMES["pine"])
        out.append(
            f"@media (prefers-color-scheme:dark){{{r}{{{_vars(dark, palette, 'dark')}}}"
            f"{show_dark}}}"
        )
        out.append(f"{dark_sel}{{{_vars(dark, palette, 'dark')}}}")
        out.append(f"{light_sel}{{{_vars(light, palette, 'light')}}}")
        out.append(f"{mint_sel}{{{_vars(mint_ui, palette, 'mint')}}}")
        out.append(f"{pine_sel}{{{_vars(pine_ui, palette, 'pine')}}}")
        if swaps:
            for sel, rule in (
                (dark_sel, show_dark),
                (light_sel, show_light),
                (mint_sel, show_light),
                (pine_sel, show_dark),
            ):
                for part in sel.split(","):
                    out.append(rule.replace(f"{r} ", f"{part} "))
    else:
        for scheme_name, th_key in (
            ("light", "mintfig"),
            ("dark", "dark"),
            ("mint", "mint"),
            ("pine", "pine"),
        ):
            sel = f'{r}[data-mf-scheme="{scheme_name}"],[data-mf-scheme="{scheme_name}"] {r}'
            out.append(f"{sel}{{{_vars(_ui_tokens(THEMES[th_key]), None, scheme_name)}}}")
    out.append(
        f"{r} .mf-ctrl{{display:flex;justify-content:flex-end;align-items:center;"
        "flex-wrap:wrap;gap:6px;margin:0 0 4px;font-size:11px;color:var(--mf-ui-muted)}"
        f"{r} .mf-schemes{{display:inline-flex;align-items:center;gap:2px;"
        "padding:1px 3px;border:1px solid var(--mf-ui-line);border-radius:999px}"
        f"{r} .mf-ctrl button{{all:unset;cursor:pointer;padding:1px 6px;border-radius:999px;"
        "color:inherit;line-height:1.5;transition:background .12s,color .12s}"
        f"{r} .mf-ctrl button:hover,{r} .mf-ctrl button:focus-visible{{color:var(--mf-ui-ink)}}"
        f'{r} .mf-schemes button[aria-pressed="true"]{{background:var(--mf-ui-ink);'
        "color:var(--mf-ui-bg);font-weight:600}"
        f"{r} .mf-ctrl-btn{{border:1px solid var(--mf-ui-line)!important;padding:1px 8px!important}}"
        f"{r} .mf-brush-sel{{fill:#0f8b6d;fill-opacity:.18;stroke:#0f8b6d;"
        "stroke-width:1;stroke-dasharray:3 2;pointer-events:none}"
        f"{r} [data-mf]{{cursor:pointer;outline:none}}"
        f"{r} .mf-hits [data-mf]:hover,{r} .mf-hits [data-mf]:focus-visible"
        "{stroke:var(--mf-ui-ink);stroke-width:1.2}"
        f"{r} g[data-mf]:focus-visible{{opacity:.75}}"
        f"{r} .mf-tip{{position:absolute;z-index:2;pointer-events:none;max-width:90%;"
        "padding:3px 7px;border-radius:4px;background:var(--mf-ui-ink);color:var(--mf-ui-bg);"
        "font-size:12px;font-variant-numeric:tabular-nums}"
        f"{r} .mf-cap{{margin:8px 0 0;font-size:15px;line-height:1.5}}"
        f"{r} .mf-foot{{margin:4px 0 0;font-size:12px;color:var(--mf-ui-muted);"
        "display:flex;flex-wrap:wrap;align-items:baseline}"
        f"{r} .mf-data-details{{display:inline}}"
        f"{r} .mf-data-details[open]{{flex:1 0 100%}}"
        f"{r} .mf-data-details>summary{{list-style:none;cursor:pointer;color:inherit;"
        "text-decoration:underline dotted;text-underline-offset:2px;display:inline}"
        f"{r} .mf-data-details>summary::-webkit-details-marker{{display:none}}"
        f"{r} .mf-data-details>summary:hover,{r} .mf-data-details>summary:focus-visible"
        "{color:var(--mf-ui-ink)}"
        f"{r} .mf-foot button{{all:unset;cursor:pointer;color:inherit;"
        "text-decoration:underline dotted;text-underline-offset:2px}"
        f"{r} .mf-foot button:hover,{r} .mf-foot button:focus-visible{{color:var(--mf-ui-ink)}}"
        f"{r} .mf-note{{margin-left:8px}}"
        f"{r} .mf-data{{margin-top:8px;font-size:12.5px;color:var(--mf-ui-ink)}}"
        f"{r} .mf-data h3{{margin:10px 0 2px;font-size:12.5px}}"
        f"{r} .mf-data ul{{margin:2px 0 6px;padding-left:18px}}"
        f"{r} .mf-table-wrap{{overflow-x:auto}}"
        f"{r} .mf-data-table{{border-collapse:collapse;font-size:12px;"
        "font-variant-numeric:tabular-nums}"
        f"{r} .mf-data-table th,{r} .mf-data-table td{{text-align:left;padding:2px 10px 2px 0;"
        "border-bottom:1px solid var(--mf-ui-line)}"
        f"{r} .mf-data-table th{{color:var(--mf-ui-muted);font-weight:600}}"
        f"{r} .mf-data-table .mf-num{{text-align:right}}"
        f"{r} .mf-table-note,{r} .mf-meta{{margin:2px 0;color:var(--mf-ui-muted)}}"
        f"{r} .mf-sr-only{{position:absolute;width:1px;height:1px;overflow:hidden;"
        "clip:rect(0,0,0,0);white-space:nowrap}"
    )
    return "<style>\n" + "\n".join(out) + "\n</style>"


_JS = """(function(){
var R=document.getElementById(%(id)s);if(!R)return;
var M=%(marks)s,SPEC=%(spec)s,FILE=%(file)s;
var tip=R.querySelector('.mf-tip'),note=R.querySelector('.mf-note');
function f(v){return typeof v==='number'?String(+v.toPrecision(6)):String(v);}
function u(r){return r.unit?(/^[%%\\u00b0]/.test(r.unit)?'':' ')+r.unit:'';}
function head(r){var h=r.name!=null?String(r.name):'';return r.x!=null?h+' @ '+r.x:h;}
function line(r){return head(r)+' = '+f(r.value)+u(r);}
function cite(r){return FILE+' \\u00b7 '+r.panel+' \\u00b7 '+line(r);}
function mark(t){var el=t&&t.closest?t.closest('[data-mf]'):null;
  return el&&M[el.getAttribute('data-mf')]?el:null;}
function say(msg){if(!note)return;note.textContent=msg;clearTimeout(say.t);
  say.t=setTimeout(function(){note.textContent='';},3500);}
function show(el){var r=M[el.getAttribute('data-mf')],t=el.getAttribute('aria-label');
  if(!t){t=line(r);if(r.lo!=null&&r.hi!=null)t+='  ['+f(r.lo)+', '+f(r.hi)+']';
    if(r.n!=null)t+='  n='+r.n;}
  tip.textContent=t;tip.hidden=false;
  var b=el.getBoundingClientRect(),o=R.getBoundingClientRect();
  var x=b.left-o.left+b.width/2-tip.offsetWidth/2,y=b.top-o.top-tip.offsetHeight-6;
  tip.style.left=Math.max(0,Math.min(x,R.clientWidth-tip.offsetWidth))+'px';
  tip.style.top=(y<0?b.bottom-o.top+6:y)+'px';}
function hide(){tip.hidden=true;}
function copy(text,msg){var done=function(){say(msg);};
  if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(text).then(done,function(){say(text);});}
  else say(text);}
function act(el){var r=M[el.getAttribute('data-mf')];copy(cite(r),'copied: '+cite(r));}
function visibleSvg(){return [].filter.call(R.querySelectorAll('.mf-v svg'),
  function(n){return n.getClientRects().length;})[0]||null;}
function setTheme(name){
  var btns=R.querySelectorAll('[data-mf-theme-pick]');
  for(var i=0;i<btns.length;i++){
    btns[i].setAttribute('aria-pressed',btns[i].getAttribute('data-mf-theme-pick')===name?'true':'false');}
  if(name==='auto'){R.removeAttribute('data-mf-scheme');document.documentElement.removeAttribute('data-mf-scheme');}
  else{R.setAttribute('data-mf-scheme',name);document.documentElement.setAttribute('data-mf-scheme',name);}
  say('theme: '+name);}
function svgPt(svg,cx,cy){var ctm=svg.getScreenCTM();if(!ctm)return null;
  var pt=svg.createSVGPoint();pt.x=cx;pt.y=cy;return pt.matrixTransform(ctm.inverse());}
function dataX(z,sx){var zx=+z.getAttribute('x'),zw=+z.getAttribute('width');
  var frac=Math.max(0,Math.min(1,(sx-zx)/zw));
  var x0=+z.getAttribute('data-mf-x0'),x1=+z.getAttribute('data-mf-x1');
  if(z.getAttribute('data-mf-xscale')==='log'&&x0>0&&x1>0){
    var l0=Math.log10(x0),l1=Math.log10(x1);return Math.pow(10,l0+frac*(l1-l0));}
  return x0+frac*(x1-x0);}
function fmtRange(v){if(!isFinite(v))return String(v);
  return Math.abs(v)>=10?String(Math.round(v)):String(+v.toPrecision(3));}
var brush=null,skipClick=false;
function clearBrush(){var old=R.querySelectorAll('.mf-brush-sel');
  for(var i=0;i<old.length;i++)old[i].remove();}
R.addEventListener('pointerdown',function(e){
  if(e.button!==0||e.target.closest('.mf-ctrl,.mf-foot'))return;
  var svg=e.target.closest?e.target.closest('svg'):null;if(!svg)return;
  var pt=svgPt(svg,e.clientX,e.clientY);if(!pt)return;
  var zones=svg.querySelectorAll('.mf-brush-zone'),hit=null;
  for(var i=0;i<zones.length;i++){var z=zones[i],zx=+z.getAttribute('x'),zy=+z.getAttribute('y'),
    zw=+z.getAttribute('width'),zh=+z.getAttribute('height');
    if(pt.x>=zx&&pt.x<=zx+zw&&pt.y>=zy&&pt.y<=zy+zh){hit=z;break;}}
  if(!hit)return;
  brush={svg:svg,z:hit,x0:pt.x,x1:pt.x,moved:false,rect:null};});
window.addEventListener('pointermove',function(e){if(!brush)return;
  var pt=svgPt(brush.svg,e.clientX,e.clientY);if(!pt)return;
  var zx=+brush.z.getAttribute('x'),zw=+brush.z.getAttribute('width');
  var cx=Math.max(zx,Math.min(zx+zw,pt.x));
  if(!brush.moved&&Math.abs(cx-brush.x0)<6)return;
  if(!brush.moved){brush.moved=true;clearBrush();
    var r=document.createElementNS('http://www.w3.org/2000/svg','rect');
    r.setAttribute('class','mf-brush-sel');
    r.setAttribute('y',brush.z.getAttribute('y'));
    r.setAttribute('height',brush.z.getAttribute('height'));
    brush.svg.appendChild(r);brush.rect=r;}
  brush.x1=cx;var a=Math.min(brush.x0,brush.x1),b=Math.max(brush.x0,brush.x1);
  brush.rect.setAttribute('x',String(a));brush.rect.setAttribute('width',String(b-a));
  var d0=fmtRange(dataX(brush.z,a)),d1=fmtRange(dataX(brush.z,b));
  var pnl=brush.z.getAttribute('data-mf-panel')||'a';
  tip.textContent='panel '+pnl+' \\u00b7 X='+d0+'..'+d1;tip.hidden=false;
  var o=R.getBoundingClientRect();
  tip.style.left=Math.max(0,Math.min(e.clientX-o.left-tip.offsetWidth/2,R.clientWidth-tip.offsetWidth))+'px';
  tip.style.top=Math.max(0,e.clientY-o.top-tip.offsetHeight-10)+'px';});
window.addEventListener('pointerup',function(){if(!brush)return;var b=brush;brush=null;
  if(!b.moved)return;skipClick=true;hide();
  var lo=Math.min(b.x0,b.x1),hi=Math.max(b.x0,b.x1);
  var d0=fmtRange(dataX(b.z,lo)),d1=fmtRange(dataX(b.z,hi));
  var pnl=b.z.getAttribute('data-mf-panel')||'a';
  var prompt='Zoom into X='+d0+'..'+d1+' on panel '+pnl+' and compare variance';
  copy(prompt,'copied prompt: '+prompt);});
R.addEventListener('pointerover',function(e){if(brush&&brush.moved)return;
  var el=mark(e.target);el?show(el):hide();});
R.addEventListener('pointerleave',function(){if(!brush)hide();});
R.addEventListener('focusin',function(e){var el=mark(e.target);if(el)show(el);});
R.addEventListener('focusout',hide);
R.addEventListener('keydown',function(e){var el=mark(e.target);
  if(el&&(e.key==='Enter'||e.key===' ')){e.preventDefault();act(el);}});
R.addEventListener('click',function(e){
  if(skipClick){skipClick=false;return;}
  var tp=e.target.closest?e.target.closest('[data-mf-theme-pick]'):null;
  if(tp){setTheme(tp.getAttribute('data-mf-theme-pick'));return;}
  var el=mark(e.target);if(el)return act(el);
  var b=e.target.closest?e.target.closest('[data-mf-act]'):null;
  if(!b){clearBrush();return;}
  var a=b.getAttribute('data-mf-act');
  if(a==='spec')copy(JSON.stringify(SPEC,null,2),'copied spec JSON');
  else if(a==='copy-svg'){var cs=visibleSvg();if(!cs)return;
    copy(new XMLSerializer().serializeToString(cs),'copied SVG');}
  else if(a==='svg'){var s=visibleSvg();if(!s)return;
    var url=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(s)],
      {type:'image/svg+xml'}));
    var l=document.createElement('a');l.href=url;
    l.download=(/\\.\\w+$/.test(FILE)?FILE.replace(/\\.\\w+$/,''):'figure')+'.svg';
    document.body.appendChild(l);l.click();l.remove();URL.revokeObjectURL(url);}});
})();"""


def _data_section(exp: Explanation, *, facts: bool = True) -> str:
    """Facts and the data table of every panel, plus source and note (inside native <details>)."""
    parts: list[str] = []
    for key, panel in exp.panels.items():
        title = html.escape(panel.title or panel.describe, quote=True)
        parts.append(f"<h3>{html.escape(key, quote=True)} \N{MIDDLE DOT} {title}</h3>")
        if facts and panel.facts:
            items = "".join(f"<li>{html.escape(fact, quote=True)}</li>" for fact in panel.facts)
            parts.append(f'<ul class="mf-facts">{items}</ul>')
        parts.append(_render_table_html(*_panel_data_table(panel)))
    for label, value in (("Source", exp.source), ("Note", exp.note)):
        if value:
            parts.append(f'<p class="mf-meta">{label}: {html.escape(value, quote=True)}</p>')
    return '<div class="mf-data">' + "".join(parts) + "</div>"


_ROTATE_ZERO_RE = re.compile(r' transform="rotate\(-?0(?:\.0+)? [^)]+\)"')
_FONT_FAMILY_RE = re.compile(r"font-family:\s*([^;\"<>]+);?\s*")
_WHITE_SPACE_PRE_RE = re.compile(r"white-space:\s*pre;?\s*")
_LONG_FLOAT_RE = re.compile(r"(\d+\.\d)\d+")
_GEOM_ATTR_RE = re.compile(
    r'\b(d|points|x|y|dx|dy|cx|cy|r|rx|ry|x1|y1|x2|y2|width|height|viewBox|transform)="([^"]*)"'
)
_INLINE_STYLE_RE = re.compile(r'style="([^"]+)"')
_PLAIN_GROUP_RE = re.compile(r"<g>((?:(?!</?g\b).)*)</g>")


def _css_font_stack(families: Sequence[str] | None, *, fallback: str = "sans-serif") -> str:
    if not families:
        return f"Helvetica,Arial,{fallback}"
    generics = {"sans-serif", "serif", "monospace", "cursive", "fantasy", "system-ui"}
    parts: list[str] = []
    for fam in families:
        clean = fam.strip()
        if not clean:
            continue
        if clean.lower() in generics or re.fullmatch(r"[A-Za-z0-9-]+", clean):
            parts.append(clean)
        else:
            parts.append(f"'{clean}'")
    if not any(p.lower() in generics for p in parts):
        parts.append(fallback)
    return ",".join(parts)


def _minify_svg(raw: str, theme: Theme | None = None) -> str:
    """Compact Matplotlib SVG markup for fast inline chat embeds (~50% smaller, visually identical).

    Restricts coordinate rounding strictly to numeric geometric attributes so visible
    ``<text>`` nodes and ``aria-label`` values remain 100% verbatim, and preserves the
    active :class:`Theme` typography (including serif headlines or sketch/mono stacks).
    """
    out = _ROTATE_ZERO_RE.sub("", raw)

    # Identify the dominant body font-family rendered in the SVG; hoist only that one
    # to the base text{} rule so distinct families (e.g. Georgia serif titles on
    # editorial/paper) remain intact on their elements.
    fam_counts: dict[str, int] = {}
    for m in _FONT_FAMILY_RE.finditer(out):
        fam = m.group(1).strip()
        fam_counts[fam] = fam_counts.get(fam, 0) + 1
    if fam_counts:
        dominant_fam = max(fam_counts.items(), key=lambda kv: kv[1])[0]
        body_font_css = re.sub(r"\s*,\s*", ",", dominant_fam)

        def _strip_dominant_font(match: re.Match[str]) -> str:
            return "" if match.group(1).strip() == dominant_fam else match.group(0)

        out = _FONT_FAMILY_RE.sub(_strip_dominant_font, out)
    else:
        body_font_css = _css_font_stack(theme.body_family if theme is not None else None)

    out = _WHITE_SPACE_PRE_RE.sub("", out)
    # Round coordinate precision ONLY on numeric geometric attributes, never <text> or aria-label!
    def _round_geom_attr(match: re.Match[str]) -> str:
        rounded = _LONG_FLOAT_RE.sub(r"\1", match.group(2))
        return f'{match.group(1)}="{rounded}"'

    out = _GEOM_ATTR_RE.sub(_round_geom_attr, out)
    out = re.sub(r"\s*\n\s*", " ", out)
    out = re.sub(r">\s+<", "><", out)
    out = out.replace("<g/>", "")
    for _ in range(4):
        nxt = _PLAIN_GROUP_RE.sub(r"\1", out)
        if nxt == out:
            break
        out = nxt
    counts: dict[str, int] = {}
    for m in _INLINE_STYLE_RE.finditer(out):
        st = m.group(1).strip()
        counts[st] = counts.get(st, 0) + 1
    cls_map: dict[str, str] = {}
    rules: list[str] = []
    for idx, (st, n) in enumerate(sorted(counts.items(), key=lambda kv: -kv[1] * len(kv[0]))):
        if n >= 2 and len(st) > 10:
            cname = f"m{idx}"
            cls_map[st] = cname
            rules.append(f".{cname}{{{st}}}")

    def _repl(match: re.Match[str]) -> str:
        st = match.group(1).strip()
        return f'class="{cls_map[st]}"' if st in cls_map else match.group(0)

    out = _INLINE_STYLE_RE.sub(_repl, out)
    out = out.replace("xlink:href=", "href=")
    extra = f"text{{white-space:pre;font-family:{body_font_css}}}" + "".join(rules)
    return re.sub(r"(<style[^>]*>)", lambda m: m.group(1) + extra, out, count=1)


_THEME_SYNC_JS = (
    "(function(){var H=document.documentElement;"
    "function sync(){"
    "var c=H.classList;"
    "if(c.contains('light')){H.setAttribute('data-mf-scheme','light');}"
    "else if(c.contains('dark')){H.setAttribute('data-mf-scheme','dark');}"
    "else if(window.matchMedia){"
    "H.setAttribute('data-mf-scheme',window.matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');}"
    "}"
    "sync();"
    "window.addEventListener('themechange',sync);"
    "if(window.matchMedia){"
    "var mq=window.matchMedia('(prefers-color-scheme:dark)');"
    "if(mq.addEventListener)mq.addEventListener('change',sync);}"
    "})();"
)


def render_html_fragment(
    exp_or_spec: Explanation | Mapping[str, Any],
    *,
    interactive: bool = True,
    facts: bool = True,
    responsive: bool = True,
    caption: str | None = None,
    compact: bool = False,
) -> str:
    """Render a self-contained embeddable HTML fragment (for Jupyter ``_repr_html_()``).

    Contains zero external references; all CSS, SVG and vanilla JS are inlined and
    scoped to a unique root container id, so several fragments can share a page.

    ``facts=False`` leaves the facts out of the data drawer (its data table stays), for a
    page that lists them elsewhere. ``responsive=False`` embeds only the figure's own
    layout (still light and dark): a static thumbnail with ``interactive=False``.
    ``compact=True`` emits a single minified SVG with transparent flush background and
    omits the full ``spec`` JSON blob (~80% smaller, designed for fast inline chat embeds).
    ``caption`` is shown under the figure, above the ``data · svg · spec`` line.
    """
    exp = _ensure_explanation(exp_or_spec)
    spec_dict = exp.to_spec()
    root_id = _root_id(spec_dict)
    auto = exp.theme.name == "mintfig"
    twin_style = _dark_twin_style() if auto else None

    use_responsive = responsive and not compact
    own = _layout_widths(exp) if use_responsive else [_OWN]
    own_name = own[-1]
    variants: list[tuple[int, Explanation, Explanation | None]] = []
    for name in own:
        if name == "small":
            light = _small_layout(exp)
        else:
            light = exp if name == own_name else _rebuild(exp, width=name)
        if light is None:
            continue
        dark = _rebuild(light, style=twin_style) if twin_style is not None else None
        if name == "small":
            px = _SMALL_PX
        else:
            px = _own_px(exp) if light is exp else _LAYOUT_PX.get(name, light.display_width_px)
        variants.append((px, light, dark))

    palette = _Palette(exp.theme, variants[0][2].theme) if auto and variants[0][2] else None
    marks: dict[str, Any] = {}
    blocks: list[str] = []
    swaps = False
    for i, (_, light, dark) in enumerate(variants):
        light_svg, light_marks = _render_svg(light, interactive=interactive)
        # A layout that tagged its marks in another order gets its own key namespace.
        ns = f"{i}/" if any(marks.get(k, v) != v for k, v in light_marks.items()) else ""
        light_svg = light_svg.replace(' data-mf="', f' data-mf="{ns}')
        marks.update({f"{ns}{k}": v for k, v in light_marks.items()})
        body = _scope_ids(light_svg, f"{root_id}-{i}-")
        if dark is not None and palette is not None:
            dark_svg = _render_svg(dark, interactive=interactive)[0]
            dark_svg = dark_svg.replace(' data-mf="', f' data-mf="{ns}')
            themed = palette.themed(body, _scope_ids(dark_svg, f"{root_id}-{i}-"))
            if themed is not None:
                body = themed
            else:
                swaps = True
                body = (
                    f'<div class="mf-light">{body}</div><div class="mf-dark">'
                    f'{_scope_ids(dark_svg, f"{root_id}-{i}d-")}</div>'
                )
        if compact:
            body = _minify_svg(body, theme=exp.theme)
        blocks.append(f'<div class="mf-v mf-v{i}">{body}</div>')

    light_ui = _ui_tokens(exp.theme)
    dark_ui = _ui_tokens(variants[0][2].theme) if auto and variants[0][2] else None
    css = _css_block(
        root_id,
        light_ui,
        dark_ui,
        palette,
        [px for px, _, _ in variants],
        max(px for px, _, _ in variants),
        swaps,
    )
    if compact:
        compact_css = (
            f"#{root_id}{{background:transparent;--mf-bg:transparent}}"
            f'#{root_id}[data-mf-scheme="dark"],[data-mf-scheme="dark"] #{root_id}'
            f"{{background:transparent;--mf-bg:transparent}}"
            f'#{root_id}[data-mf-scheme="light"],[data-mf-scheme="light"] #{root_id}'
            f"{{background:transparent;--mf-bg:transparent}}"
        )
        css = css.replace("</style>", f"\n{compact_css}\n</style>", 1)
    mode = "dark" if relative_luminance(exp.theme.background) < 0.2 else "light"
    escaped_alt = html.escape(exp.alt_text, quote=True)
    stage = (
        f'<div class="mf-stage" role="{"group" if interactive else "img"}" '
        f'aria-label="{escaped_alt}">{"".join(blocks)}</div>'
        f'<figcaption class="mf-sr-only">{html.escape(exp.takeaway, quote=True)}</figcaption>'
    )
    if caption:
        stage += f'<p class="mf-cap">{html.escape(caption, quote=True)}</p>'
    layouts = " ".join(str(px) for px, _, _ in variants)
    open_tag = (
        f'<figure id="{root_id}" class="mf-root" '
        f'data-mf-theme="{html.escape(exp.theme.name, quote=True)}" data-mf-mode="{mode}" '
        f'data-mf-layouts="{layouts}">'
    )
    if not interactive:
        return f"{css}\n{open_tag}{stage}</figure>"

    data_drawer = (
        '<details class="mf-data-details">'
        '<summary data-mf-act="data">data</summary>'
        f"{_data_section(exp, facts=facts)}"
        "</details>"
    )
    if compact:
        actions = (
            '<span class="mf-foot-acts"> \N{MIDDLE DOT} '
            '<button type="button" data-mf-act="svg">svg</button>'
            '<span class="mf-note" role="status" aria-live="polite"></span></span>'
        )
    else:
        actions = (
            '<span class="mf-foot-acts"> \N{MIDDLE DOT} '
            '<button type="button" data-mf-act="svg">svg</button>'
            " \N{MIDDLE DOT} "
            '<button type="button" data-mf-act="spec">spec</button>'
            '<span class="mf-note" role="status" aria-live="polite"></span></span>'
        )
    foot = f'<div class="mf-foot">{data_drawer}{actions}</div>'
    ctrl = ""
    if not compact:
        active_pick = "auto" if auto else (exp.theme.name if exp.theme.name in {"dark", "mint", "pine"} else "light")
        pills = "".join(
            f'<button type="button" data-mf-theme-pick="{key}" '
            f'aria-pressed="{"true" if key == active_pick else "false"}">{lbl}</button>'
            for key, lbl in (
                ("auto", "Auto"),
                ("light", "Light"),
                ("dark", "Dark"),
                ("mint", "Mint"),
                ("pine", "Pine"),
            )
        )
        ctrl = (
            '<div class="mf-ctrl" role="group" aria-label="Figure controls">'
            f'<span class="mf-schemes" role="group" aria-label="Theme">{pills}</span>'
            '<button type="button" class="mf-ctrl-btn" data-mf-act="copy-svg">Copy SVG</button>'
            "</div>"
        )
    js = _JS % {
        "id": json.dumps(root_id),
        "marks": _safe_json_for_script(marks),
        "spec": "{}" if compact else _safe_json_for_script(spec_dict),
        "file": _safe_json_for_script(_citation_file(exp)),
    }
    return (
        f"{css}\n{open_tag}{ctrl}{stage}"
        '<div class="mf-tip" role="tooltip" hidden></div>'
        f"{foot}</figure>\n<script>\n{js}\n</script>"
    )


def render_html(
    exp_or_spec: Explanation | Mapping[str, Any],
    *,
    interactive: bool = True,
    compact: bool = False,
) -> str:
    """Render a standalone, self-contained HTML5 document for an ``Explanation`` or spec dict.

    When ``compact=True``, emits a lean, single-layout minified SVG document with a
    transparent flush background and live host theme sync (``themechange`` / ``.light``
    / ``.dark`` / ``prefers-color-scheme``), ideal for inline chat embeds.
    """
    exp = _ensure_explanation(exp_or_spec)
    fragment = render_html_fragment(exp, interactive=interactive, compact=compact)
    light = _ui_tokens(exp.theme)
    if compact:
        page = f"html,body{{margin:0;padding:0;background:transparent;color:{light['ink']}}}"
        page += "body{padding:4px 0}"
        scheme = "light dark"
        if exp.theme.name == "mintfig":
            dark = _ui_tokens(THEMES["dark"])
            page += (
                f"@media (prefers-color-scheme:dark){{html,body{{color:{dark['ink']}}}}}"
                f'html[data-mf-scheme="dark"],html[data-mf-scheme="dark"] body{{color:{dark["ink"]}}}'
                f'html[data-mf-scheme="light"],html[data-mf-scheme="light"] body{{color:{light["ink"]}}}'
            )
        else:
            scheme = "dark" if relative_luminance(exp.theme.background) < 0.2 else "light"
        sync_tag = f"\n<script>{_THEME_SYNC_JS}</script>" if exp.theme.name == "mintfig" else ""
        return (
            "<!DOCTYPE html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<meta name="color-scheme" content="{scheme}">\n'
            f"<title>{html.escape(exp.takeaway, quote=True)}</title>\n"
            f"<style>\n{page}\n</style>\n"
            "</head>\n"
            "<body>\n"
            f"{fragment}{sync_tag}\n"
            "</body>\n"
            "</html>\n"
        )

    page = f"html,body{{margin:0;background:{light['bg']};color:{light['ink']}}}"
    page += "body{padding:16px}@media (max-width:480px){body{padding:8px 4px}}"
    scheme = "light dark"
    if exp.theme.name == "mintfig":
        dark = _ui_tokens(THEMES["dark"])
        mint_t = _ui_tokens(THEMES["mint"])
        pine_t = _ui_tokens(THEMES["pine"])
        dark_body = f"background:{dark['bg']};color:{dark['ink']}"
        mint_body = f"background:{mint_t['bg']};color:{mint_t['ink']}"
        pine_body = f"background:{pine_t['bg']};color:{pine_t['ink']}"
        page += (
            f"@media (prefers-color-scheme:dark){{html,body{{{dark_body}}}}}"
            f'html[data-mf-scheme="dark"],html[data-mf-scheme="dark"] body{{{dark_body}}}'
            f'html[data-mf-scheme="light"],html[data-mf-scheme="light"] body'
            f"{{background:{light['bg']};color:{light['ink']}}}"
            f'html[data-mf-scheme="mint"],html[data-mf-scheme="mint"] body{{{mint_body}}}'
            f'html[data-mf-scheme="pine"],html[data-mf-scheme="pine"] body{{{pine_body}}}'
        )
    else:
        scheme = "dark" if relative_luminance(exp.theme.background) < 0.2 else "light"
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta name="color-scheme" content="{scheme}">\n'
        f"<title>{html.escape(exp.takeaway, quote=True)}</title>\n"
        f"<style>\n{page}\n</style>\n"
        "</head>\n"
        "<body>\n"
        f"{fragment}\n"
        "</body>\n"
        "</html>\n"
    )
