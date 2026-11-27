"""An arm-neutral audit of a saved Matplotlib figure, for comparing mintfig with plain Matplotlib.

Both arms of figure-bench end in a ``matplotlib.figure.Figure`` written to
``figure.png``: mintfig's ``Explanation.save`` calls ``Figure.savefig`` like any
script does. This module measures that figure the same way whichever library
drew it, and never imports mintfig, so the Matplotlib arm stays mintfig-free.

``audit_saved_figure`` runs inside the ``savefig`` hook, right after the real
save, so the figure and any active rc context are exactly as saved.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path
from typing import Any

DISPLAY_WIDTH_PX = 700  # a chat column; an image narrower than this shows at its own size
MIN_TEXT_PX = 11.0
BANNED_COLORMAPS = frozenset(
    {"jet", "rainbow", "hsv", "gist_rainbow", "nipy_spectral", "prism", "flag"}
)
# Text naming an interval, a spread or the replicate structure.
UNCERTAINTY_WORDS = re.compile(
    r"(\bCI\b|confidence|interval|\bs\.?d\.?\b|\bSD\b|\bSEM?\b|\bs\.e\.m?\.?|standard (?:deviation|error)"
    r"|±|\bIQR\b|quartile|percentile|\bseeds?\b|replicates?|triplicates?|\bwells?\b|\bn\s*=\s*\d"
    r"|margin of error|\brange\b|\bmin[–-]max\b)",
    re.IGNORECASE,
)

_DOUBLED = re.compile(r"\b(\w+(?:\s+\w+)?)\s+\1\b", re.IGNORECASE)
_ASCII_MINUS = re.compile(r"(?:^|[\s(\[=:,])-\d")
_JUNK = re.compile(r"\b(nan|NaN|None|inf|-inf)\b")


def png_size(path: Path) -> tuple[int, int] | None:
    """Width and height from a PNG's IHDR chunk, without an imaging library."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(24)
    except OSError:
        return None
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    w, h = struct.unpack(">II", head[16:24])
    return int(w), int(h)


def drawn_texts(fig: Any) -> list[Any]:
    """Every text Matplotlib actually draws (visible, non-empty, not fully transparent)."""
    from matplotlib.text import Text

    drawn: list = []
    original = Text.draw

    def _recording_draw(self, renderer):
        if self.get_visible() and self.get_text().strip() and self.get_alpha() != 0:
            drawn.append(self)
        return original(self, renderer)

    Text.draw = _recording_draw
    try:
        fig.canvas.draw()
    finally:
        Text.draw = original
    return list(dict.fromkeys(drawn))


def _masked(t: Any, legend_texts: set[int]) -> bool:
    """A text drawn on an opaque box (a framed legend or a bbox patch) hides lines under it."""
    if id(t) in legend_texts:
        return True
    patch = t.get_bbox_patch()
    if patch is None or not patch.get_visible() or not patch.get_fill():
        return False
    alpha = patch.get_facecolor()[3] if patch.get_alpha() is None else patch.get_alpha()
    return alpha >= 0.5


def text_audit(fig: Any, texts: list[Any], *, skip_masked: bool) -> dict:
    """Overlapping texts, texts crossed by a data or reference line, and malformed text."""
    renderer = fig.canvas.get_renderer()
    out: dict = {"overlaps": [], "struck": [], "text_faults": [], "text_advisories": []}
    shrunk = []
    for t in texts:
        b = t.get_window_extent(renderer)
        pad = 1.5
        if b.width > 2 * pad and b.height > 2 * pad:
            b = b.from_extents(b.x0 + pad, b.y0 + pad, b.x1 - pad, b.y1 - pad)
        shrunk.append((t, b))
    for i, (ti, bi) in enumerate(shrunk):
        for tj, bj in shrunk[i + 1:]:
            if bi.overlaps(bj):
                out["overlaps"].append(f"{ti.get_text()!r} / {tj.get_text()!r}")
    legend_texts: set[int] = set()
    if skip_masked:
        for ax in fig.axes:
            legends = [ax.get_legend(), *getattr(ax, "legends", [])]
            for leg in [*legends, *getattr(fig, "legends", [])]:
                if leg is not None and leg.get_frame_on():
                    legend_texts |= {id(x) for x in leg.get_texts()}
                    legend_texts.add(id(leg.get_title()))
    grid = {id(g) for ax in fig.axes for g in (*ax.get_xgridlines(), *ax.get_ygridlines())}
    lines = [
        ln for ax in fig.axes for ln in ax.lines
        if id(ln) not in grid and ln.get_visible() and len(ln.get_xdata()) >= 2
        and ln.get_linestyle() not in ("None", "", " ") and ln.get_linewidth() > 0
    ]
    for ln in lines:
        path = ln.get_transform().transform_path(ln.get_path())
        dashed = ln.get_linestyle() not in ("-", "solid")
        for t, b in shrunk:
            if t.axes is not None and t.axes is not ln.axes:
                continue
            if skip_masked and _masked(t, legend_texts):
                continue
            if path.intersects_bbox(b, filled=False):
                what = "dashed reference line" if dashed else "data line"
                out["struck"].append(f"{t.get_text()!r} crossed by a {what}")
    for t in texts:
        txt = t.get_text()
        plain = re.sub(r"\$[^$]*\$", "", txt)
        if "%%" in plain:
            out["text_faults"].append(f"doubled %: {txt!r}")
        m = _DOUBLED.search(plain)
        if m and not m.group(1).isdigit():
            out["text_faults"].append(f"repeated words {m.group(0)!r}: {txt!r}")
        if _ASCII_MINUS.search(plain) and not re.search(r"\d{4}-\d{2}", plain):
            out["text_advisories"].append(f"ASCII hyphen as minus sign: {txt!r}")
        if _JUNK.search(plain):
            out["text_faults"].append(f"junk value: {txt!r}")
    return out


def _fig_text_y(fig: Any, text_artist: Any) -> float:
    """Return a figure-level Text artist's y coordinate in normalized figure coords [0, 1]."""
    pos = text_artist.get_position()
    try:
        disp = text_artist.get_transform().transform(pos)
        _, fy = fig.transFigure.inverted().transform(disp)
        return float(fy)
    except Exception:  # noqa: BLE001
        return float(pos[1])


def headline_texts(fig: Any) -> list[str]:
    """Title/subtitle figure texts (``y > 0.78``) and axes titles: where a reader looks for the claim."""
    out: list[str] = []
    seen_ids: set[int] = set()
    sup = getattr(fig, "_suptitle", None)
    if sup is not None and sup.get_visible() and sup.get_text().strip():
        out.append(sup.get_text())
        seen_ids.add(id(sup))
    for t in fig.texts:
        if id(t) in seen_ids or not t.get_visible() or not t.get_text().strip():
            continue
        if _fig_text_y(fig, t) > 0.78:
            out.append(t.get_text())
            seen_ids.add(id(t))
    for ax in fig.axes:
        if not ax.get_visible():
            continue
        for title in (ax.title, getattr(ax, "_left_title", None), getattr(ax, "_right_title", None)):
            if title is not None and id(title) not in seen_ids and title.get_visible() and title.get_text().strip():
                out.append(title.get_text())
                seen_ids.add(id(title))
        ax_title = ax.get_title().strip()
        if ax_title and ax_title not in out:
            out.append(ax_title)
    return out


def _colormaps(fig: Any) -> set[str]:
    names = set()
    for ax in fig.axes:
        for art in (*ax.images, *ax.collections):
            cmap = getattr(art, "cmap", None)
            if cmap is not None and getattr(art, "get_array", lambda: None)() is not None:
                names.add(cmap.name.removesuffix("_r"))
    return names


def _truncated_bar_axes(fig: Any) -> list[str]:
    """Return descriptions of visible linear bar-chart axes whose baseline is truncated above 0.

    Only flags clear zero-anchored positive bar charts (all bars share base == 0 with positive
    extent, yet the axis lower limit cuts off more than 5% of the top value). Floating/waterfall
    bars, histograms with non-zero baselines, log axes, and negative-valued bars are skipped.
    """
    from matplotlib.container import BarContainer

    flagged: list[str] = []
    for idx, ax in enumerate(fig.axes):
        if not ax.get_visible() or not ax.axison:
            continue
        bar_containers = [c for c in getattr(ax, "containers", []) if isinstance(c, BarContainer)]
        if not bar_containers:
            continue
        patches = [p for c in bar_containers for p in c.patches if p.get_visible()]
        if len(patches) < 2:
            continue

        # Infer orientation from container metadata or patch geometry
        orient = getattr(bar_containers[0], "orientation", None)
        if orient not in ("vertical", "horizontal"):
            widths = [abs(p.get_width()) for p in patches]
            heights = [abs(p.get_height()) for p in patches]
            bases_y = [p.get_y() for p in patches]
            bases_x = [p.get_x() for p in patches]
            if all(abs(b) < 1e-6 for b in bases_y) and any(h > 0 for h in heights):
                orient = "vertical"
            elif all(abs(b) < 1e-6 for b in bases_x) and any(w > 0 for w in widths):
                orient = "horizontal"
            else:
                continue

        if orient == "vertical":
            if ax.get_yscale() != "linear":
                continue
            bases = [float(p.get_y()) for p in patches]
            heights = [float(p.get_height()) for p in patches]
            if not (all(abs(b) < 1e-6 for b in bases) and all(h > 0 for h in heights)):
                continue
            lo, hi = sorted(ax.get_ylim())
            ymax = max(heights)
            if lo > 0.05 * ymax and lo < hi:
                flagged.append(f"ax{idx} y-axis starts at {lo:.4g} (max bar {ymax:.4g})")
        else:
            if ax.get_xscale() != "linear":
                continue
            bases = [float(p.get_x()) for p in patches]
            widths = [float(p.get_width()) for p in patches]
            if not (all(abs(b) < 1e-6 for b in bases) and all(w > 0 for w in widths)):
                continue
            lo, hi = sorted(ax.get_xlim())
            xmax = max(widths)
            if lo > 0.05 * xmax and lo < hi:
                flagged.append(f"ax{idx} x-axis starts at {lo:.4g} (max bar {xmax:.4g})")
    return flagged


def _has_log_axis(fig: Any) -> bool:
    for ax in fig.axes:
        if not ax.get_visible() or not ax.axison:
            continue
        if ax.get_xscale() in ("log", "symlog") or ax.get_yscale() in ("log", "symlog"):
            return True
    return False


def audit_saved_figure(
    fig: Any,
    png: Path,
    *,
    dpi: float,
    tight: bool,
    display_width_px: int = DISPLAY_WIDTH_PX,
) -> dict:
    """Measure a figure that was just saved to ``png`` at ``dpi``.

    Text size is reported as the reader sees it: the PNG is shown at
    ``min(display_width_px, its own width)``, so a point of text is
    ``dpi / 72 * shown / png_width`` display pixels.
    """
    target_w = display_width_px if display_width_px >= 100 else DISPLAY_WIDTH_PX
    size = png_size(png)
    texts = drawn_texts(fig)
    out: dict[str, Any] = {"png_px": list(size) if size else None, "dpi": dpi, "tight": tight,
                           "texts": len(texts)}
    if size:
        shown = min(target_w, size[0])
        px_per_pt = dpi / 72.0 * shown / size[0]
        out["display_width_px"] = shown
        sizes = sorted(((t.get_fontsize() * px_per_pt, t.get_text()) for t in texts),
                       key=lambda x: x[0])
        out["min_text_px"] = round(sizes[0][0], 1) if sizes else None
        out["small_texts"] = [f"{txt[:40]!r} {px:.1f} px" for px, txt in sizes if px < MIN_TEXT_PX][:6]
        out["small_text_count"] = sum(1 for px, _ in sizes if px < MIN_TEXT_PX)
    out.update(text_audit(fig, texts, skip_masked=True))
    clipped = []
    if not tight:
        renderer = fig.canvas.get_renderer()
        canvas = fig.bbox
        for t in texts:
            b = t.get_window_extent(renderer)
            if b.x0 < canvas.x0 - 1 or b.y0 < canvas.y0 - 1 or b.x1 > canvas.x1 + 1 or b.y1 > canvas.y1 + 1:
                clipped.append(repr(t.get_text()[:40]))
    out["clipped"] = clipped
    all_text_list = [t.get_text() for t in texts if t.get_text().strip()]
    all_text = " ".join(all_text_list)
    out["all_texts"] = all_text_list
    out["uncertainty_named"] = bool(UNCERTAINTY_WORDS.search(all_text))
    out["headlines"] = headline_texts(fig)
    out["panels"] = sum(1 for ax in fig.axes if ax.get_visible() and ax.axison)
    out["legends"] = sum(1 for ax in fig.axes if ax.get_legend() is not None) + len(fig.legends)
    out["banned_colormaps"] = sorted(_colormaps(fig) & BANNED_COLORMAPS)
    out["truncated_bar_axes"] = _truncated_bar_axes(fig)
    out["has_log_axis"] = _has_log_axis(fig)
    return out


NEUTRAL_GATE = ("text_legible", "no_text_overlap", "no_text_struck_by_lines",
                "text_well_formed", "no_text_clipped")


def neutral_checks(audit: dict | None) -> list[dict]:
    """The defect checks both arms share, as {name, passed, detail}."""
    if not audit:
        return [{"name": n, "passed": False, "detail": "no audited figure"} for n in NEUTRAL_GATE]
    min_px = audit.get("min_text_px")
    return [
        {"name": "text_legible", "passed": isinstance(min_px, (int, float)) and min_px >= MIN_TEXT_PX,
         "detail": f"smallest text {min_px} px at {audit.get('display_width_px')} px display"
                   + (f"; {audit.get('small_text_count')} texts under {MIN_TEXT_PX:g} px, e.g. "
                      + ", ".join(audit.get("small_texts", [])[:3]) if audit.get("small_texts") else "")},
        {"name": "no_text_overlap", "passed": not audit["overlaps"], "detail": "; ".join(audit["overlaps"][:4])},
        {"name": "no_text_struck_by_lines", "passed": not audit["struck"], "detail": "; ".join(audit["struck"][:4])},
        {"name": "text_well_formed", "passed": not audit["text_faults"], "detail": "; ".join(audit["text_faults"][:4])},
        {"name": "no_text_clipped", "passed": not audit["clipped"],
         "detail": "texts past the canvas edge: " + ", ".join(audit["clipped"][:4]) if audit["clipped"] else ""},
    ]
