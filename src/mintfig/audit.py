"""Independent drawn-layout and text-quality audit for rendered figures.

Inspects the actual artists Matplotlib draws during rendering:
- Overlapping visible text bounding boxes
- Visible non-grid lines intersecting text bounding boxes
- Text formatting faults (doubled ``%``, repeated words, ASCII hyphen minus,
  raw ``nan``/``None``/``inf`` tokens)

Used by :func:`mintfig.explain` to gate ``summary["ship"]`` and reusable on
saved PNGs via :func:`audit_layout`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from matplotlib.figure import Figure

_DOUBLED = re.compile(r"\b(\w+(?:\s+\w+)?)\s+\1\b", re.IGNORECASE)
_ASCII_MINUS = re.compile(r"(?:^|[\s(\[=:,])-\d")
_JUNK = re.compile(r"\b(nan|NaN|None|inf|-inf)\b")


def audit_figure(
    fig: Figure,
    *,
    pad_px: float = 1.5,
    allow_ascii_minus: bool = False,
) -> dict[str, Any]:
    """Audit a drawn Matplotlib figure for overlaps, struck text, and text faults.

    Must be called while the figure's typography/rc context is active so font
    metrics match the saved output.

    Returns
    -------
    dict
        ``{"overlaps": [...], "struck": [...], "text_faults": [...], "texts": n}``.
    """
    from matplotlib.text import Text

    out: dict[str, Any] = {"overlaps": [], "struck": [], "text_faults": [], "texts": 0}
    drawn: list[Text] = []
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

    renderer = fig.canvas.get_renderer()  # type: ignore[attr-defined]
    texts = list(dict.fromkeys(drawn))
    out["texts"] = len(texts)

    shrunk = []
    for text_artist in texts:
        bbox = text_artist.get_window_extent(renderer).expanded(1.0, 1.0)
        if bbox.width > 2 * pad_px and bbox.height > 2 * pad_px:
            bbox = bbox.from_extents(
                bbox.x0 + pad_px,
                bbox.y0 + pad_px,
                bbox.x1 - pad_px,
                bbox.y1 - pad_px,
            )
        shrunk.append((text_artist, bbox))

    for i, (ti, bi) in enumerate(shrunk):
        for tj, bj in shrunk[i + 1 :]:
            if bi.overlaps(bj):
                out["overlaps"].append(f"{ti.get_text()!r} / {tj.get_text()!r}")

    grid = {id(g) for ax in fig.axes for g in (*ax.get_xgridlines(), *ax.get_ygridlines())}
    lines = [
        ln
        for ax in fig.axes
        for ln in ax.lines
        if id(ln) not in grid
        and ln.get_visible()
        and len(ln.get_xdata()) >= 2
        and ln.get_linestyle() not in ("None", "", " ")
        and ln.get_linewidth() > 0
    ]
    for ln in lines:
        path = ln.get_transform().transform_path(ln.get_path())
        dashed = ln.get_linestyle() not in ("-", "solid")
        for text_artist, bbox in shrunk:
            if text_artist.axes is not None and text_artist.axes is not ln.axes:
                continue
            if path.intersects_bbox(bbox, filled=False):
                what = "dashed reference line" if dashed else "data line"
                out["struck"].append(f"{text_artist.get_text()!r} crossed by a {what}")

    for text_artist in texts:
        txt = text_artist.get_text()
        plain = re.sub(r"\$[^$]*\$", "", txt)
        if "%%" in plain:
            out["text_faults"].append(f"doubled %: {txt!r}")
        match = _DOUBLED.search(plain)
        if match and not match.group(1).isdigit():
            out["text_faults"].append(f"repeated words {match.group(0)!r}: {txt!r}")
        if not allow_ascii_minus and _ASCII_MINUS.search(plain) and not re.search(r"\d{4}-\d{2}", plain):
            out["text_faults"].append(f"ASCII hyphen as minus sign: {txt!r}")
        if _JUNK.search(plain):
            out["text_faults"].append(f"junk value: {txt!r}")

    return out


def audit_layout(png: str | Path) -> dict[str, Any]:
    """Rebuild a mintfig PNG from its embedded spec and run :func:`audit_figure`."""
    from .explainer import load

    exp = load(str(png))
    with exp.theme.rc_context(exp.spec):
        return audit_figure(exp.fig, allow_ascii_minus=(exp.theme.minus_sign == "-"))


def audit_to_issues(
    audit: dict[str, Any],
    *,
    existing_rules: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Translate non-empty :func:`audit_figure` findings into ``explain`` issue dicts."""
    seen = existing_rules or set()
    issues: list[dict[str, Any]] = []

    if audit["overlaps"] and "text_overlaps" not in seen:
        sample = "; ".join(audit["overlaps"][:4])
        issues.append(
            {
                "rule": "text_overlaps",
                "severity": "warning",
                "message": f"Drawn text overlaps: {sample}.",
                "fix_hint": (
                    "Shorten item names, end labels or event text (end_values=False drops "
                    "numbers at line ends), show fewer items/series, or give the panel a "
                    'full-width row with layout=[["a"], ["b"]].'
                ),
            }
        )

    if audit["struck"] and not ({"text_on_data", "value_label_on_reference"} & seen):
        sample = "; ".join(audit["struck"][:4])
        issues.append(
            {
                "rule": "text_struck_by_line",
                "severity": "warning",
                "message": f"Drawn text is crossed by a line: {sample}.",
                "fix_hint": (
                    "Shorten labels, move or drop reference/event labels, name fewer items "
                    'in highlight=, or give the panel a full-width row with layout=[["a"], ["b"]].'
                ),
            }
        )

    if audit["text_faults"]:
        sample = "; ".join(audit["text_faults"][:4])
        issues.append(
            {
                "rule": "text_malformed",
                "severity": "warning",
                "message": f"Malformed drawn text: {sample}.",
                "fix_hint": (
                    "Check unit=/fmt= for doubled '%', repeated label words, raw NaN/None "
                    "values, or ASCII '-' minus signs in custom text."
                ),
            }
        )

    return issues
