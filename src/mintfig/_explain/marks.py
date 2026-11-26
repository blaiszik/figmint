"""Name the data marks of an explain figure.

A form calls :func:`tag` on each artist that encodes data (a bar, a dot, a series
line, a cell, a span, a step) with what the mark says: ``name``, ``x``, ``value``,
``lo``/``hi`` (its interval), ``n`` and ``unit``. Tagging gives the artist a ``gid``
(``mf-<panel>-<seq>``) so a vector render can address it, and keeps the fields on the
artist for the HTML surface. It never changes how anything is drawn, and it leaves a
gid that is already set (such as ``annotations.MARGIN_GID``) alone.

:func:`tag_points` is for one artist that carries several marks (the vertices of a
series line, the dots of a scatter): it keeps each mark's data position so the HTML
surface can place a focusable hit target on it.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

#: Prefix of every mark gid; the HTML surface recognises marks by it.
GID_PREFIX = "mf-"
#: Attribute holding ``[(data_xy or None, record), ...]`` on a tagged artist.
MARKS_ATTR = "_mintfig_marks"
#: Attribute holding the data-unit half size ``(dx, dy)`` of each point mark's hit box.
BOX_ATTR = "_mintfig_mark_box"
#: Set (True) on a mark that repeats another mark's data (a table cell's in-cell graphic
#: beside its number): it shows the same tooltip on hover but is not a separate tab stop.
QUIET_ATTR = "_mintfig_mark_quiet"
FIELDS = ("name", "x", "value", "lo", "hi", "n", "unit")


def _plain(value: Any) -> Any:
    """A JSON-ready scalar: numpy scalars unwrapped, non-finite numbers and blanks dropped."""
    if value is None:
        return None
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            value = value.item()
        except (TypeError, ValueError):
            return str(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value if math.isfinite(value) else None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    text = str(value)
    return text or None


def record(**fields: Any) -> dict[str, Any]:
    """The mark fields that exist, in the canonical order."""
    out: dict[str, Any] = {}
    for key in FIELDS:
        val = _plain(fields.get(key))
        if val is not None:
            out[key] = val
    return out


def _claim(ctx: Any, artist: Any) -> bool:
    """Give ``artist`` the next mark gid of its figure; False if it already has a gid."""
    if artist is None or artist.get_gid() is not None:
        return False
    fig = ctx.fig
    seq = getattr(fig, "_mintfig_mark_seq", 0)
    fig._mintfig_mark_seq = seq + 1
    artist.set_gid(f"{GID_PREFIX}{ctx.key}-{seq}")
    return True


def tag(ctx: Any, artist: Any, *, quiet: bool = False, **fields: Any) -> Any:
    """Mark ``artist`` as one data mark of panel ``ctx.key``; returns ``artist``.

    ``quiet=True``: the mark repeats a focusable mark's data (hover only, no tab stop).
    """
    if _claim(ctx, artist):
        setattr(artist, MARKS_ATTR, [(None, record(**fields))])
        if quiet:
            setattr(artist, QUIET_ATTR, True)
    return artist


def tag_each(ctx: Any, artists: Iterable[Any], records: Iterable[Mapping[str, Any]]) -> None:
    """Tag each artist with the matching record (bars of one ``barh`` call, cells, ...)."""
    for artist, fields in zip(artists, records):
        tag(ctx, artist, **fields)


def tag_points(
    ctx: Any,
    artist: Any,
    xs: Sequence[Any],
    ys: Sequence[Any],
    records: Iterable[Mapping[str, Any]],
    *,
    box: tuple[float, float] | None = None,
) -> Any:
    """Tag one artist that draws several marks at data positions ``(xs[i], ys[i])``.

    ``box`` is the half width and height of each mark in data units (a heat-table
    cell); without it each mark is a point.
    """
    points = []
    for x, y, fields in zip(xs, ys, records):
        try:
            fx, fy = float(x), float(y)
        except (TypeError, ValueError):
            continue
        if math.isfinite(fx) and math.isfinite(fy):
            points.append(((fx, fy), record(**fields)))
    if points and _claim(ctx, artist):
        setattr(artist, MARKS_ATTR, points)
        if box is not None:
            setattr(artist, BOX_ATTR, (float(box[0]), float(box[1])))
    return artist


def tagged(fig: Any) -> list[Any]:
    """Every tagged artist of ``fig`` in drawing-tree order."""
    return list(fig.findobj(lambda a: bool(getattr(a, MARKS_ATTR, None))))
