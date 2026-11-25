"""Layout engine, Explanation, Summary, explain(), load(), and JSON spec entry points."""

from __future__ import annotations

import json
import math
import re
import zlib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from matplotlib import dates as mdates
from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.ticker import (
    FixedLocator,
    FuncFormatter,
    MaxNLocator,
)
from matplotlib.transforms import Bbox

from ..specs import JournalSpec, get_spec, mm_to_in
from ..themes import (
    EXPLAIN_PALETTES,
    MINTFIG_THEME,
    THEME_ALIASES,
    THEMES,
    ExplainPalette,
    Theme,
    apply_accent,
    apply_palette,
    get_theme,
)
from .change import change
from .compare import compare, share
from .core import (
    _ADJUSTMENTS,
    _COL_GAP_MM,
    _HAS_DIGIT,
    _ILLUSTRATIVE_CUE,
    _LINE,
    _MARGIN_MM,
    _ROW_GAP_MM,
    _STRICT,
    _TOPIC_TITLE,
    _VISUAL_DEFECT_RULES,
    COMFORTABLE_PANELS,
    DISPLAY_WIDTH_PX,
    KINDS,
    MAX_PANELS,
    MAX_TITLE_LINES,
    MIN_TEXT_PX,
    PT_TO_MM,
    ExplainError,
    Panel,
    _cover_with_ticks,
    _Ctx,
    _date_formatter,
    _fit_axes,
    _glyph_issue,
    _GlyphCapture,
    _guarded,
    _has_items,
    _is_strict,
    _issue,
    _labels_collide,
    _Measure,
    _measure_text,
    _missing_glyphs,
    _pairs,
    _plain,
    _record_adjustment,
    _Sizes,
    _tick_label,
    _tick_label_boxes,
    _value_axis,
)
from .distribution import distribution, histogram
from .flow import flow
from .matrix import matrix
from .relate import relate
from .timeline import timeline
from .trend import trend
from .waterfall import waterfall

# --------------------------------------------------------------------------- #
# table
# --------------------------------------------------------------------------- #


@_guarded("table")
def table(
    rows: Sequence[Mapping[str, Any]] | Mapping[str, Sequence[Any]] | Sequence[Sequence[Any]],
    *,
    columns: Sequence[str] | None = None,
    title: str | None = None,
    label: str | None = None,
    unit: str | None = None,
    units: Mapping[str, str] | None = None,
    highlight: str | Sequence[str] | None = None,
    baseline: str | None = None,
    bold_best: bool | str | Mapping[str, str] = False,
    sort: str | None = None,
    align: Mapping[str, str] | None = None,
    fmt: str | Mapping[str, str] | None = None,
) -> Panel:
    """Exact lookup table or multi-metric scorecard with booktabs rules and aligned figures."""
    from .._table import table as _build_table

    return _build_table(
        rows,
        columns=columns,
        title=title,
        label=label,
        unit=unit,
        units=units,
        highlight=highlight,
        baseline=baseline,
        bold_best=bold_best,
        sort=sort,
        align=align,
        fmt=fmt,
    )


# --------------------------------------------------------------------------- #
# custom
# --------------------------------------------------------------------------- #


@_guarded("custom")
def custom(
    draw: Callable[[Axes], None],
    *,
    title: str | None = None,
    label: str | None = None,
    unit: str | None = None,
    height_mm: float = 48.0,
    describe: str = "Custom panel",
) -> Panel:
    """Escape hatch: draw anything on a house-styled Axes when no form fits.

    The built-in rules do not apply inside ``draw``; preflight still does.
    """
    if not callable(draw):
        raise ExplainError(
            "custom(draw) must be a function taking an Axes.", fix_hint="Pass def draw(ax): ..."
        )

    def _draw(ctx: _Ctx, ax: Axes) -> None:
        _value_axis(ax, ctx.sizes, ctx.theme)
        draw(ax)

    return Panel(
        kind="custom",
        title=title,
        label=label,
        unit=unit,
        spec={"title": title, "label": label, "unit": unit},
        facts=[],
        describe=describe,
        _height_mm=lambda _w, _m, _s, _t: float(height_mm),
        stretch=True,
        _draw=_draw,
    )


# --------------------------------------------------------------------------- #
# Layout and the Explanation object
# --------------------------------------------------------------------------- #


def _auto_layout(keys: list[str]) -> list[list[str]]:
    n = len(keys)
    if n <= 2:
        return [keys]
    if n == 3:
        return [[keys[0], keys[0]], [keys[1], keys[2]]]
    if n % 2 == 0:
        return [keys[i : i + 2] for i in range(0, n, 2)]
    return [[keys[0], keys[0]], *[keys[i : i + 2] for i in range(1, n, 2)]]


def _validate_layout(layout: Sequence[Sequence[str]], keys: list[str]) -> list[list[str]]:
    rows = [[str(k) for k in row] for row in layout]
    seen: list[str] = []
    for row in rows:
        if not row:
            raise ExplainError(
                "layout has an empty row.", fix_hint='e.g. layout=[["a"], ["b", "c"]].'
            )
        collapsed = [k for i, k in enumerate(row) if i == 0 or row[i - 1] != k]
        if len(set(collapsed)) != len(collapsed):
            raise ExplainError(
                f"layout row {row!r} repeats a panel non-contiguously.",
                fix_hint="Repeat a key only side by side to make that panel wider.",
            )
        for key in collapsed:
            if key in seen:
                raise ExplainError(
                    f"layout places panel {key!r} in more than one row.",
                    fix_hint="Each panel occupies one row; rows are stacked top to bottom.",
                )
            seen.append(key)
    if sorted(seen) != sorted(keys):
        raise ExplainError(
            f"layout uses panels {sorted(seen)!r} but the figure has {sorted(keys)!r}.",
            fix_hint="Panels are keyed a, b, c ... in the order passed; list each exactly once.",
        )
    return rows


#: Named colour slots for ``explain(colors=...)``: an index into the theme's validated
#: series palette, so a pinned colour stays colour-blind and grayscale safe in every style.
COLOR_SLOTS: dict[str, int] = {"blue": 0, "red": 1, "green": 2, "amber": 3}


def _entity_key(name: object) -> str:
    return str(name).strip()


def _pinned_colors(colors: object, theme: Theme) -> dict[str, str]:
    """Read ``explain(colors={name: slot})`` into ``{name: hex}`` from the theme palette."""
    if colors is None:
        return {}
    slots = ", ".join(f'"{s}"' for s in COLOR_SLOTS)
    hint = (
        f"Pass colors={{name: slot}} with slot one of {slots}, e.g. "
        'colors={"no retrieval": "red", "full model": "blue"}. Slots resolve to the style\'s '
        "validated palette (colour-blind and grayscale separated), so arbitrary colours are not "
        "accepted."
    )
    if not _has_items(colors):
        raise ExplainError(
            f"explain(colors=...) must map names to colour slots, got {type(colors).__name__}.",
            fix_hint=hint,
            rule="bad_colors",
        )
    out: dict[str, str] = {}
    used: dict[str, str] = {}
    for name, slot in _pairs(colors):
        key = _entity_key(name)
        word = slot.strip().lower() if isinstance(slot, str) else None
        if word not in COLOR_SLOTS:
            raise ExplainError(
                f"explain(colors[{key!r}]) = {slot!r} is not a colour slot.",
                fix_hint=hint,
                rule="bad_colors",
            )
        if word in used:
            raise ExplainError(
                f"explain(colors=...) gives {used[word]!r} and {key!r} the same slot {word!r}; "
                "one colour must mean one thing.",
                fix_hint=f"Give each pinned name its own slot ({slots}): at most "
                f"{len(COLOR_SLOTS)} pinned names; leave the rest unpinned (they take the "
                "figure's own colours).",
                rule="bad_colors",
            )
        used[word] = key
        out[key] = theme.series_colors[COLOR_SLOTS[word] % len(theme.series_colors)]
    return out


def _colour_registry(
    panels: Sequence[Panel], theme: Theme, pinned: Mapping[str, str]
) -> tuple[list[dict[str, str]], str, list[dict[str, Any]]]:
    """One colour per named entity across the whole figure.

    Entities are the names a panel emphasises (highlighted items, then trend series and
    relate groups that are coloured by default) plus ``pinned`` names, each group in
    order of first appearance. Each gets one colour from one pool: the accent order when any panel has a
    highlight, else the series order, with the uniform default colour moved last when some
    panel still draws in it. Returns per-panel ``{name: colour}`` maps (keys are the
    panel's own names), the uniform colour, and issues.
    """
    # Highlighted names first (they are what the takeaway is about and get the warm
    # accent), then names coloured by default (trend series, relate groups); each in
    # order of first appearance across the panels.
    # A baseline (control, "before") is drawn in ink wherever it appears, unless pinned:
    # it never takes a palette colour, so a control is never the red one.
    baselines = {
        _entity_key(p.color_baseline)
        for p in panels
        if p.color_baseline and _entity_key(p.color_baseline) not in pinned
    }
    entities: list[str] = []
    for modes in (("highlight",), ("series",)):
        for panel in panels:
            if panel.color_mode not in modes:
                continue
            for name in panel.color_focus:
                key = _entity_key(name)
                if key and key not in entities and key not in baselines:
                    entities.append(key)
    known = set(entities) | set(pinned)

    def _uniform(panel: Panel) -> bool:
        if not panel.uses_default:
            return False
        if panel.color_mode == "series":
            return True  # an unnamed single series
        return not any(_entity_key(nm) in known for nm in panel.color_items)

    any_highlight = any(p.color_mode == "highlight" for p in panels)
    base = list(theme.accent_colors) if any_highlight else list(theme.series_colors)
    base += [c for c in theme.series_colors if c not in base]
    default = theme.default_color
    pool = [c for c in base if c not in pinned.values()]
    if any(_uniform(p) for p in panels) and default in pool:
        pool = [c for c in pool if c != default] + [default]

    registry: dict[str, str] = dict(pinned)
    registry.update({key: theme.ink for key in baselines})
    known |= baselines
    overflow: list[str] = []
    for key in entities:
        if key in registry:
            continue
        if pool:
            registry[key] = pool.pop(0)
        else:
            overflow.append(key)

    taken = set(registry.values())
    uniform = default
    if default in taken:  # a pinned or fifth entity took it: use a free colour if one is left
        uniform = next((c for c in base if c not in taken), default)

    per_panel: list[dict[str, str]] = []
    for panel in panels:
        colours: dict[str, str] = {}
        if panel.color_mode != "none":
            wanted = (
                list(panel.color_focus)
                if panel.color_mode in {"highlight", "series"}
                else [nm for nm in panel.color_items if _entity_key(nm) in known]
            )
            if panel.color_mode == "series":
                # coloured by default: entities pinned elsewhere keep their colour too
                wanted = list(dict.fromkeys(wanted))
            if panel.color_baseline and panel.color_baseline not in wanted:
                wanted.append(panel.color_baseline)
            for name in wanted:
                key = _entity_key(name)
                if key in registry:
                    colours[name] = registry[key]
            for name in wanted:  # overflow: a colour not used elsewhere in this panel
                if name not in colours and _entity_key(name):
                    free = [c for c in base if c not in colours.values()]
                    colours[name] = free[0] if free else base[0]
        per_panel.append(colours)

    issues: list[dict[str, Any]] = []
    if overflow:
        named = [*list(registry)[: len(base)], *overflow]
        issues.append(
            _issue(
                "colour_reused_across_panels",
                "warning",
                f"{len(named)} names need colour across the panels "
                f"({', '.join(map(repr, named[:8]))}) but the palette has {len(base)} "
                f"colours; {', '.join(map(repr, overflow))} reuse a colour that means "
                "something else in another panel.",
                "Highlight fewer names (the ones the takeaway is about), or split the "
                "argument into two figures.",
            )
        )
    return per_panel, uniform, issues


#: Plot height cap (mm at scale 1) for a full-width trend/relate in a multi-row figure.
_FULL_ROW_STRETCH_MM = 44.0
#: How much a bar-like panel may grow to fill a row set by a taller neighbour.
_ROW_GROWTH = 1.3
#: Narrowest plot area (mm at scale 1) a panel may be left with after its labels fit.
_MIN_PLOT_MM = 20.0


def _check_plot_width(fig: Figure, panel: Panel, ax: Axes, rect: Bbox, scale: float) -> None:
    """Refuse a panel whose labels leave a sliver of plot (end labels in a narrow cell)."""
    if panel.kind in {"matrix", "custom", "table"}:
        return
    px_per_mm = float(fig.dpi) / 25.4
    plot_mm = ax.get_window_extent(fig.canvas.get_renderer()).width / px_per_mm
    # Lines and scatters need room to show a shape; bars, dots and slopes less so.
    least = _MIN_PLOT_MM if panel.stretch or panel.kind == "trend" else 0.4 * _MIN_PLOT_MM
    floor = min(least * scale, 0.42 * rect.width / px_per_mm)
    if plot_mm + 0.05 < floor:
        hint = 'Use fewer columns (e.g. layout=[["a", "a"], ["b", "c"]] gives one panel the full width), shorten the item or series names'
        if panel.kind == "trend":
            hint += ", or pass end_values=False to drop the numbers at the line ends"
        raise ExplainError(
            f"The labels leave only {plot_mm:.0f} mm of plot area (at least {floor:.0f} mm is "
            "needed to read the data).",
            fix_hint=hint + ".",
            rule="panel_too_small",
        )


def _fit_ticks(fig: Figure, ax: Axes, which: str = "xy") -> None:
    """Thin tick labels that would touch ("8001,200 1,600") on every axis of ``ax``.

    Runs after layout, so the decision uses the measured label widths and the final
    axes size. A "nice number" locator gets fewer bins; a date locator fewer ticks;
    fixed ticks (log decades, measured x positions, categories) keep a greedy subset
    counted back from the last label, so the end of the range stays labelled.
    """
    renderer = fig.canvas.get_renderer()
    for axis, horizontal in ((ax.xaxis, True), (ax.yaxis, False)):
        if not axis.get_visible() or axis.axis_name not in which:
            continue
        size = max((t.label1.get_fontsize() for t in axis.get_major_ticks()[:1]), default=8.0)
        gap = 0.55 * size * fig.dpi / 72.0
        for _ in range(8):
            boxes = _tick_label_boxes(axis, renderer)
            if len(boxes) < 2 or not _labels_collide(boxes, horizontal, gap):
                break
            locator = axis.get_major_locator()
            if isinstance(locator, MaxNLocator) and len(boxes) > 2:
                nbins = locator._nbins if isinstance(locator._nbins, int) else len(boxes)
                # Fewer bins on round steps keep both ends labelled ("0 1,000 2,000").
                locator.set_params(nbins=max(1, min(nbins, len(boxes)) - 1), steps=[1, 2, 5, 10])
                continue
            if isinstance(locator, mdates.AutoDateLocator) and len(boxes) > 2:
                fewer = mdates.AutoDateLocator(minticks=2, maxticks=max(2, len(boxes) - 1))
                fewer.set_axis(axis)
                lo_v, hi_v = sorted(axis.get_view_interval())
                # Day-of-month labels ("15 Sep") are wide: when the locator cannot go below
                # the current count, fall through to the greedy subset instead of looping.
                if len(fewer.tick_values(mdates.num2date(lo_v), mdates.num2date(hi_v))) < len(
                    boxes
                ):
                    axis.set_major_locator(fewer)
                    axis.set_major_formatter(_date_formatter(fewer))
                    continue
            # Greedy subset from the end: keep a label when it clears the last one kept.
            ordered = sorted(boxes, key=lambda lb: lb[1].x0 if horizontal else lb[1].y0)
            kept: list[tuple[float, Bbox]] = [ordered[-1]]
            for loc, box in reversed(ordered[:-1]):
                prev = kept[-1][1]
                room = (prev.x0 - box.x1) if horizontal else (prev.y0 - box.y1)
                if room >= gap:
                    kept.append((loc, box))
            keep = [loc for loc, _ in kept]
            old = axis.get_major_formatter()
            span = abs(float(np.diff(axis.get_view_interval())[0])) or 1.0
            # A formatter that labels ticks as a set (concise dates) keeps the labels it
            # gave in context; called one value at a time it would print a bare year.
            shown: dict[float, str] = {}
            if isinstance(old, mdates.ConciseDateFormatter):
                locs = [float(v) for v in axis.get_majorticklocs()]
                shown = dict(zip(locs, old.format_ticks(locs), strict=True))

            def _subset(
                v: float,
                pos: Any,
                old: Any = old,
                keep: list[float] = keep,
                span: float = span,
                shown: dict[float, str] = shown,
            ) -> str:
                for k in keep:
                    if abs(v - k) <= 1e-9 * max(abs(k), span):
                        return shown.get(k) or old(v, pos)
                return ""

            axis.set_major_formatter(FuncFormatter(_subset))
            break
        cover = getattr(ax, "_mintfig_cover", None)
        bracket = getattr(ax, "_mintfig_bracket", None)
        if (
            bracket is not None
            and horizontal
            and axis.get_scale() == "linear"
            and _bracket_with_ticks(fig, axis, *bracket)
        ):
            continue
        if cover is not None and horizontal and axis.get_scale() == "linear":
            _cover_with_ticks(axis, *cover)


def _bracket_with_ticks(
    fig: Figure, axis: Any, lo: float, hi: float, max_ticks: int, minus: str
) -> bool:
    """Round ticks that bracket [lo, hi]: at least three, the lowest at or below every
    observation and the highest at or above it, on the finest nice step whose labels
    fit (so the axis is widened as little as possible). Returns False when no step
    fits, leaving the caller's fallback in charge."""
    span = (hi - lo) or abs(hi) or 1.0
    renderer = fig.canvas.get_renderer()
    size = max((t.label1.get_fontsize() for t in axis.get_major_ticks()[:1]), default=8.0)
    gap = 0.55 * size * fig.dpi / 72.0
    base = 10.0 ** math.floor(math.log10(span / max_ticks))
    steps = [m * base * 10**k for k in (-1, 0, 1, 2) for m in (1, 2, 2.5, 5)]
    set_lim = axis.axes.set_xlim if axis.axis_name == "x" else axis.axes.set_ylim
    old_lim = axis.get_view_interval()
    old_locator, old_formatter = axis.get_major_locator(), axis.get_major_formatter()
    for step in sorted(steps):
        k0 = math.floor(lo / step + 1e-9)
        k1 = math.ceil(hi / step - 1e-9)
        if k1 - k0 + 1 > max_ticks:
            continue
        while k1 - k0 + 1 < 3:  # one more round tick on the side with the less widening
            if (lo - k0 * step) <= (k1 * step - hi) or (k0 - 1) * step < 0 <= lo:
                k1 += 1
            else:
                k0 -= 1
        count = k1 - k0 + 1
        ticks = [float(f"{k * step:.12g}") for k in range(k0, k1 + 1)]
        axis.set_major_locator(FixedLocator(ticks))
        axis.set_major_formatter(
            FuncFormatter(lambda v, _p, m=minus, a=axis: _tick_label(v, m, a))
        )
        # Dots on an end tick stay whole: the view reaches 3% of the span past the data.
        margin = 0.03 * span
        set_lim(min(ticks[0], lo - margin), max(ticks[-1], hi + margin))
        boxes = _tick_label_boxes(axis, renderer)
        if len(boxes) == count and not _labels_collide(boxes, True, gap):
            return True
    axis.set_major_locator(old_locator)
    axis.set_major_formatter(old_formatter)
    set_lim(*old_lim)
    return False


#: Which tick labels of each form are numbers or dates that may be thinned (never names).
_TICK_AXES = {
    "trend": "xy",
    "relate": "xy",
    "distribution": "x",
    "compare": "x",
    "timeline": "x",
}


#: Mathtext draws a superscript or subscript at this fraction of its parent's size.
_SCRIPT_SHRINK = 0.7


def _script_depth(text: str) -> int:
    """Deepest superscript/subscript nesting inside the ``$...$`` parts of ``text``.

    ``"µm$^{2}$"`` is 1, ``"$e^{x^{2}}$"`` is 2, plain text (or escaped ``\\$``) is 0.
    """
    parts = re.split(r"(?<!\\)\$", text)
    deepest = 0
    for math_part in parts[1::2]:
        stack: list[int] = []  # depth of each open brace group
        depth = 0
        pending = False  # the next token or group is a script
        for ch in math_part:
            if ch in "^_":
                pending = True
                continue
            if ch == "{":
                stack.append(depth)
                if pending:
                    depth += 1
                    deepest = max(deepest, depth)
                pending = False
                continue
            if ch == "}":
                depth = stack.pop() if stack else 0
                continue
            if pending and not ch.isspace():
                deepest = max(deepest, depth + 1)
                pending = False
    return deepest


class Summary(dict):  # type: ignore[type-arg]
    """What :meth:`Explanation.save` returns: a plain dict that prints as indented JSON.

    Keys: ``schema_version``, ``ok``, ``style``, ``path``, ``size_px``, ``size_mm``,
    ``display``, ``takeaway``, ``panels`` (key, kind, title, facts), ``narrative``
    (L1–L4 semantic narrative), ``alt_text``, ``colors``, ``issues`` and ``rendered``. ``display`` holds ``width_px`` (the chat
    width the sizes refer to), ``min_text_px`` (smallest font size at that width,
    counting each text at its own size) and ``min_script_px``: the smallest
    mathtext superscript or subscript at that width (drawn at about 70% of its
    label's size, 49% when nested), or ``None`` when the figure has no scripts.
    The ``min_text_px`` floor does not apply to scripts.
    """

    def __str__(self) -> str:
        return json.dumps(self, indent=2, ensure_ascii=False)


#: Target display width (CSS px) when rendering for a narrow IDE sidebar (Cursor / VS Code).
NARROW_DISPLAY_WIDTH_PX = 450
#: Target display width (CSS px) when rendering a presentation / blog-hero slide.
SLIDE_DISPLAY_WIDTH_PX = 1280


class Explanation:
    """A rendered message-first figure plus what an agent needs to hand it over."""

    def __init__(
        self,
        *,
        fig: Figure,
        spec: JournalSpec,
        theme: Theme = MINTFIG_THEME,
        palette: str | None = None,
        accent: str | None = None,
        takeaway: str,
        subtitle: str | None,
        source: str | None,
        note: str | None,
        panels: dict[str, Panel],
        axes: dict[str, Axes],
        layout: list[list[str]],
        width: str | float,
        issues: list[dict[str, Any]],
        colors: dict[str, str] | None = None,
        strict: bool = True,
        adjustments: Sequence[str] = (),
        advisories: Sequence[dict[str, Any]] = (),
    ) -> None:
        self.fig = fig
        self.colors = colors
        #: Colour slot of every named entity in the figure ({"no retrieval": "red"}); pass
        #: it as ``colors=`` to the next figure to keep the same colours.
        self.entity_colors: dict[str, str] = {}
        self.spec = spec
        self.theme = theme
        self.palette = palette
        self.accent = accent
        self.takeaway = takeaway
        self.subtitle = subtitle
        self.source = source
        self.note = note
        self.panels = panels
        self.axes = axes
        self.layout = layout
        self.width = width
        self.issues = issues
        self.strict = strict
        self.adjustments = list(adjustments)
        self.advisories = list(advisories)
        self.saved_path: Path | None = None
        self.saved_px: tuple[int, int] | None = None

    @property
    def display_width_px(self) -> int:
        w = self.width.strip().lower() if isinstance(self.width, str) else ""
        if w == "slide":
            return SLIDE_DISPLAY_WIDTH_PX
        if w == "narrow":
            return NARROW_DISPLAY_WIDTH_PX
        return DISPLAY_WIDTH_PX

    def __getitem__(self, key: str) -> Axes:
        return self.axes[key]

    @property
    def width_mm(self) -> float:
        return float(self.fig.get_figwidth()) * 25.4

    @property
    def height_mm(self) -> float:
        return float(self.fig.get_figheight()) * 25.4

    @property
    def ok(self) -> bool:
        return not any(issue["severity"] == "error" for issue in self.issues)

    @property
    def ship(self) -> bool:
        """True when the figure has no errors and no visual/legibility defects.

        Advisory polish warnings (e.g. ``many_items``, ``too_tall``,
        ``fit_on_weak_relationship``) do not block ``ship``.
        """
        return self.ok and not any(issue["rule"] in _VISUAL_DEFECT_RULES for issue in self.issues)

    @property
    def min_text_px(self) -> float:
        """Smallest text height in pixels when the figure is shown at ``display_width_px``."""
        from matplotlib.text import Text

        sizes = [
            float(t.get_fontsize())
            for t in self.fig.findobj(Text)
            if t.get_visible() and t.get_text().strip()
        ]
        px_per_pt = self.display_width_px / (float(self.fig.get_figwidth()) * 72.0)
        return round(min(sizes, default=0.0) * px_per_pt, 1)

    @property
    def min_script_px(self) -> float | None:
        """Smallest mathtext superscript/subscript height in pixels at display width."""
        from matplotlib.text import Text

        sizes = [
            float(t.get_fontsize()) * _SCRIPT_SHRINK**depth
            for t in self.fig.findobj(Text)
            if t.get_visible() and (depth := _script_depth(t.get_text()))
        ]
        if not sizes:
            return None
        px_per_pt = self.display_width_px / (float(self.fig.get_figwidth()) * 72.0)
        return round(min(sizes) * px_per_pt, 1)

    @property
    def alt_text(self) -> str:
        parts = [self.takeaway.rstrip(".") + "."]
        for key, panel in self.panels.items():
            lead = f"Panel {key}: " if len(self.panels) > 1 else ""
            body = panel.describe
            if panel.title:
                body = f"{panel.title.rstrip('.')}. {body}"
            said = panel.alt_facts if panel.alt_facts is not None else panel.facts[:1]
            if said:
                body += "".join(f". {fact}" for fact in said)
            parts.append(f"{lead}{body}.")
        if self.source:
            parts.append(f"Source: {self.source.rstrip('.')}.")
        return " ".join(parts)

    def to_spec(self) -> dict[str, Any]:
        """JSON-serialisable spec that ``mintfig explain`` renders back to the same figure."""
        out: dict[str, Any] = {"takeaway": self.takeaway}
        for key in ("subtitle", "source", "note"):
            if getattr(self, key):
                out[key] = getattr(self, key)
        if self.theme.name != "mintfig":
            out["style"] = self.theme.name
        if self.palette:
            out["palette"] = self.palette
        if self.accent:
            out["accent"] = self.accent
        if self.spec.name != "screen":
            out["target"] = self.spec.name
        if self.width != "chat":
            out["width"] = self.width
        if self.colors:
            out["colors"] = dict(self.colors)
        out["layout"] = self.layout
        out["panels"] = [panel.to_spec() for panel in self.panels.values()]
        return out

    def summary(self) -> Summary:
        """What to check before showing the figure: facts to verify the claim, and issues to fix."""
        from ..epistemic import build_narrative

        out: dict[str, Any] = {
            "schema_version": "0.2",
            "ok": self.ok,
            "ship": self.ship,
            "style": self.theme.name,
            "palette": self.palette or "default",
            "path": str(self.saved_path) if self.saved_path else None,
            "size_px": list(self.saved_px) if self.saved_px else None,
            "size_mm": [round(self.width_mm, 1), round(self.height_mm, 1)],
            "display": {
                "width_px": self.display_width_px,
                "min_text_px": self.min_text_px,
                "min_script_px": self.min_script_px,
            },
            "takeaway": self.takeaway,
            "panels": [
                {"key": key, "kind": p.kind, "title": p.title, "facts": p.facts}
                for key, p in self.panels.items()
            ],
            "narrative": build_narrative(
                self.takeaway,
                self.panels,
                subtitle=self.subtitle,
                source=self.source,
            ),
            "alt_text": self.alt_text,
            "colors": dict(self.entity_colors),
            "issues": self.issues,
            "rendered": self.saved_path is not None,
        }
        if not self.strict:
            out["strict"] = False
            out["adjustments"] = list(self.adjustments)
            out["advisories"] = list(self.advisories)
        return Summary(out)

    def save(
        self,
        path: str | Path,
        *,
        scale: float = 2.0,
        write_spec: bool = False,
        embed: bool = True,
    ) -> Summary:
        """Write the figure (PNG, SVG or PDF by suffix) and return :meth:`summary`.

        PNGs for the screen target are ``DISPLAY_WIDTH_PX * scale`` pixels wide
        (1400 px by default: crisp on high-density displays at chat width).
        ``write_spec=True`` also writes ``<name>.json``, the reproducible spec.
        A PNG carries its own spec, takeaway and alt text as text chunks
        (``mintfig:spec``, ``mintfig:takeaway``, ``mintfig:alt_text``) so
        :func:`load` can rebuild it later; ``embed=False`` leaves them out.
        The figure is written even when ``ok`` is false (``rendered`` says so).
        """
        from ..export import save_figure

        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.suffix.lower() in {".html", ".htm"}:
            out.write_text(self.to_html(interactive=True), encoding="utf-8")
            self.saved_path = out.resolve()
            self.saved_px = None
            if write_spec:
                out.with_suffix(".json").write_text(
                    json.dumps(self.to_spec(), indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
            return self.summary()
        if self.spec.name == "screen":
            dpi = round(self.display_width_px * float(scale) / float(self.fig.get_figwidth()))
        else:
            dpi = int(self.spec.dpi_combo)
        with self.theme.rc_context(self.spec), _GlyphCapture() as glyph_log:
            save_figure(self.fig, out, journal=self.spec, dpi=dpi)
        late = glyph_log.missing()
        if late and not any(i["rule"] == "glyph_missing" for i in self.issues):
            self.issues.append(_glyph_issue(late))
        self.saved_path = out.resolve()
        if out.suffix.lower() == ".png":
            self.saved_px = (
                round(self.fig.get_figwidth() * dpi),
                round(self.fig.get_figheight() * dpi),
            )
            if embed:
                _embed_png_text(
                    out,
                    {
                        "mintfig:spec": json.dumps(self.to_spec(), ensure_ascii=False),
                        "mintfig:takeaway": self.takeaway,
                        "mintfig:alt_text": self.alt_text,
                    },
                )
        else:
            self.saved_px = None
        if write_spec:
            out.with_suffix(".json").write_text(
                json.dumps(self.to_spec(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        return self.summary()

    def preflight(self) -> Any:
        """Run mintfig's full preflight on the figure under the target's style."""
        from ..preflight import preflight_figure

        with self.theme.rc_context(self.spec), _GlyphCapture():
            return preflight_figure(self.fig, self.spec)

    def bundle(self, out_dir: str | Path, **kwargs: Any) -> Any:
        """Export the full manuscript bundle (PDF, SVG, proof sheet, sidecar) for this figure."""
        from ..bundle import bundle_figure

        kwargs.setdefault("takeaway", self.takeaway)
        kwargs.setdefault("takeaway_subtitle", self.subtitle)
        kwargs.setdefault(
            "panel_notes", {k: p.title for k, p in self.panels.items() if p.title} or None
        )
        kwargs.setdefault("caption", self.alt_text)
        with self.theme.rc_context(self.spec):
            return bundle_figure(self.fig, out_dir, journal=self.spec, **kwargs)

    def to_html(self, interactive: bool = True) -> str:
        """Render a self-contained interactive HTML document for this figure."""
        from ..interactive import render_html

        return render_html(self, interactive=interactive)

    def to_terminal(
        self,
        width: int = 78,
        color: bool = True,
        ascii_only: bool = False,
    ) -> str:
        """Render a terminal-friendly Unicode or ASCII view of this figure."""
        from ..terminal import render_terminal

        return render_terminal(self, width=width, color=color, ascii_only=ascii_only)

    def _repr_html_(self) -> str:
        """Rich interactive HTML fragment for Jupyter and notebook outputs."""
        from ..interactive import render_html_fragment

        return render_html_fragment(self)

    def _repr_png_(self) -> bytes:
        import io

        buffer = io.BytesIO()
        with self.theme.rc_context(self.spec), _GlyphCapture():
            self.fig.savefig(buffer, format="png", dpi=160)
        return buffer.getvalue()


#: Preflight checks phrase their hints for the publication path (Plate, rcParams).
#: On an explain figure the agent can only change explain arguments, so say those.
_EXPLAIN_PREFLIGHT_HINTS: dict[str, str] = {
    "font_sizes": "Text sizes are fixed by mint.explain; this comes from a custom() panel: set "
    "fontsize >= 7 in its draw function, or use a built-in form.",
    "font_family": "Fonts come from style=; use the default style='mintfig', or set the "
    "fontfamily inside a custom() panel to a sans-serif font.",
    "text_overlaps": "Two labels in this panel touch. Shorten the item names, end labels or "
    "event text (end_values=False drops the numbers at line ends); show fewer items or "
    'series; give the panel a full-width row with layout=[["a"], ["b", "c"]]; or drop a panel '
    "and move it to a second figure.",
    "canvas_clipping": "Text runs off the image edge. Shorten the longest name or label (or "
    'end_values=False on a trend); give the panel a full-width row with layout=[["a"], ["b"]]; '
    "or drop a panel so the rest get more width.",
    "hairline_strokes": "This comes from a custom() panel: draw lines at linewidth >= 0.5.",
    "colormaps": "Use matrix() for a heat table, or a perceptual colormap such as 'viridis' "
    "inside custom().",
    "layout_collapse": "Give the panel more room: a full-width row via layout=, fewer panels, "
    "or shorter names.",
    "color_separation": "Name fewer series in highlight= (others turn grey), or pass facet=True.",
    "clarity_metadata": "Name what is measured with label= and unit= (and x_label= on trend), "
    'e.g. label="p99 latency", unit="ms".',
    "bar_baseline_nonzero": "Bars must start at zero: use compare() (zero=True), or zero=False "
    "for a dot plot.",
    "chartjunk_hints": "Built-in forms label the data directly; remove legends, frames and 3-D "
    "effects from custom() panels.",
    "text_on_data": "Shorten labels, name fewer items in highlight=, or give the panel a "
    'full-width row with layout=[["a"], ["b"]].',
    "vector_fonts": "Save as .png for chat; for print use target= with a journal name.",
    "file_size": "Save as .png for chat; reduce points in custom() panels.",
}


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    if not data.startswith(_PNG_SIGNATURE):
        raise ExplainError(
            "The file is not a PNG.",
            fix_hint="Pass a PNG written by Explanation.save(), or a .json spec.",
        )
    chunks: list[tuple[bytes, bytes]] = []
    pos = len(_PNG_SIGNATURE)
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos : pos + 4], "big")
        kind = data[pos + 4 : pos + 8]
        chunks.append((kind, data[pos + 8 : pos + 8 + length]))
        pos += 12 + length
        if kind == b"IEND":
            break
    return chunks


def _embed_png_text(path: Path, entries: Mapping[str, str]) -> None:
    """Insert uncompressed iTXt chunks before IEND; image data (IDAT) is left byte-identical."""
    data = path.read_bytes()
    end = data.rfind(b"IEND") - 4
    if end < len(_PNG_SIGNATURE):
        return
    extra = b""
    for key, text in entries.items():
        body = key.encode("latin-1") + b"\x00\x00\x00" + b"\x00" + b"\x00" + text.encode("utf-8")
        chunk_type = b"iTXt"
        crc = zlib.crc32(chunk_type + body) & 0xFFFFFFFF
        extra += len(body).to_bytes(4, "big") + chunk_type + body + crc.to_bytes(4, "big")
    path.write_bytes(data[:end] + extra + data[end:])


def read_png_text(path: str | Path) -> dict[str, str]:
    """The ``mintfig:*`` text chunks of a PNG written by :meth:`Explanation.save`."""
    out: dict[str, str] = {}
    for kind, body in _png_chunks(Path(path).read_bytes()):
        if kind == b"iTXt":
            key, _, rest = body.partition(b"\x00")
            # compression flag, method, then language tag and translated keyword (NUL-ended)
            flag = rest[0:1]
            rest = rest[2:]
            _lang, _, rest = rest.partition(b"\x00")
            _tkey, _, text = rest.partition(b"\x00")
            if flag == b"\x01":
                text = zlib.decompress(text)
            out[key.decode("latin-1")] = text.decode("utf-8")
        elif kind == b"tEXt":
            key, _, text = body.partition(b"\x00")
            out[key.decode("latin-1")] = text.decode("latin-1")
    return {k: v for k, v in out.items() if k.startswith("mintfig:")}


def load(path: str | Path) -> Explanation:
    """Rebuild an :class:`Explanation` from a PNG saved by mintfig or from a ``.json`` spec."""
    source = Path(path)
    if not source.exists():
        raise ExplainError(
            f"{source} does not exist.",
            fix_hint="Pass the path of a PNG written by Explanation.save() or a .json spec.",
        )
    if source.suffix.lower() == ".json":
        try:
            spec = json.loads(source.read_text("utf-8"))
        except json.JSONDecodeError as exc:
            raise ExplainError(
                f"{source} is not valid JSON ({exc}).",
                fix_hint="Fix the JSON, or pass the PNG the figure was saved as.",
            ) from exc
        return explain_from_spec(spec)
    text = read_png_text(source)
    if "mintfig:spec" not in text:
        raise ExplainError(
            f"{source.name} carries no mintfig spec.",
            fix_hint="Only PNGs written by Explanation.save() (embed=True, the default) carry "
            "their spec; otherwise load the .json written with save(..., write_spec=True).",
        )
    return explain_from_spec(json.loads(text["mintfig:spec"]))


_LATEX_DOLLAR = re.compile(r"\$[^$\n]*(?:\\[A-Za-z]+|[\^_])[^$\n]*\$")


def _latex_issues(
    texts: Sequence[str | None], panel_map: Mapping[str, Panel]
) -> list[dict[str, Any]]:
    """Warn when caller text contains Matplotlib-style $...$ LaTeX markup."""
    hits: list[str] = []
    for text in texts:
        if isinstance(text, str):
            hits.extend(_LATEX_DOLLAR.findall(text))
    for panel in panel_map.values():
        for val in (
            panel.title,
            panel.label,
            panel.unit,
            panel.spec.get("x_label"),
            panel.spec.get("y_label"),
        ):
            if isinstance(val, str):
                hits.extend(_LATEX_DOLLAR.findall(val))
    if not hits:
        return []
    shown = ", ".join(repr(h) for h in list(dict.fromkeys(hits))[:3])
    return [
        _issue(
            "latex_markup",
            "warning",
            f"Literal LaTeX math ({shown}) is drawn as plain characters in mint.explain.",
            "Write Unicode directly (e.g. R², µm, ×10⁻³, °C, χ²); $...$ is not parsed as math.",
        )
    ]


def _takeaway_issues(takeaway: str) -> list[dict[str, Any]]:
    words = takeaway.split()
    if len(words) < 4 or (_TOPIC_TITLE.search(takeaway) and not _HAS_DIGIT.search(takeaway)):
        return [
            _issue(
                "takeaway_is_a_topic",
                "warning",
                f"The takeaway {takeaway!r} reads like a topic, not a conclusion.",
                'State what the reader should conclude, with the number: "Checkout p99 tripled '
                'after the v2.3 deploy", not "Latency by service".',
            )
        ]
    return []


def _too_tall_issue(
    row_plans: Sequence[Mapping[str, Any]],
    panel_map: Mapping[str, Panel],
    height_mm: float,
    min_mm: float,
    width_mm: float,
    spec: JournalSpec,
) -> dict[str, Any]:
    """The ``too_tall`` warning: the tallest panel, and one concrete way to fit."""
    px = DISPLAY_WIDTH_PX / width_mm
    heights = {
        c["key"]: (plan["head_mm"] + c["plot_mm"], plan["head_mm"] + c["min_mm"])
        for plan in row_plans
        for c in plan["cells"]
    }
    tallest = max(heights, key=lambda k: heights[k][0])
    kind = panel_map[tallest].kind
    over = min_mm - spec.max_height_mm
    message = (
        f"The figure is {height_mm:.0f} mm tall (about {height_mm * px:.0f} px at chat width); "
        f"even with every panel at its minimum readable height it needs {min_mm:.0f} mm, "
        f"more than fits on one screen ({spec.max_height_mm:.0f} mm). The tallest is panel "
        f"{tallest} ({kind}), {heights[tallest][0]:.0f} mm."
    )
    keys = [[c["key"] for c in plan["cells"]] for plan in row_plans]
    layout_now = [list(row) for row in keys]
    options: list[str] = []
    # Two stacked single-panel rows side by side save the shorter one's height.
    pairs = [
        (min(heights[keys[i][0]][1], heights[keys[i + 1][0]][1]), i)
        for i in range(len(keys) - 1)
        if len(keys[i]) == 1 and len(keys[i + 1]) == 1
    ]
    if pairs:
        saved, i = max(pairs)
        if saved >= over:
            merged = [*layout_now[:i], [keys[i][0], keys[i + 1][0]], *layout_now[i + 2 :]]
            options.append(f"put panels {keys[i][0]} and {keys[i + 1][0]} side by side: layout={merged!r}")
    if len(panel_map) > 1:
        options.append(
            f"drop panel {tallest} and state its key numbers in note=, or split the figure "
            "into two, each with its own takeaway (e.g. "
            + ", ".join(k for k in panel_map if k != tallest)
            + f" in one, {tallest} in the other)"
        )
    else:
        options.append(
            "shorten it: fewer items or rows, a shorter takeaway, subtitle and note, or show the "
            "top 10 and say so in the title"
        )
    hint = "; or ".join(options)
    return _issue("too_tall", "warning", message, hint[0].upper() + hint[1:] + ".")


@_guarded("explain")
def explain(
    takeaway: str,
    *panels: Panel | Mapping[str, Any],
    subtitle: str | None = None,
    source: str | None = None,
    note: str | None = None,
    layout: Sequence[Sequence[str]] | None = None,
    target: str | JournalSpec = "screen",
    width: str | float = "chat",
    style: str | Theme = "mintfig",
    palette: str | ExplainPalette | None = None,
    accent: str | None = None,
    colors: Mapping[str, str] | None = None,
    strict: bool = True,
    out: str | Path | None = None,
) -> Explanation:
    """Build a message-first figure: one takeaway sentence and the panels that prove it.

    Parameters
    ----------
    takeaway:
        The conclusion, as a sentence, ideally with its number. It becomes the title.
    panels:
        One to six panels from :func:`compare`, :func:`trend`, :func:`change`,
        :func:`distribution`, :func:`relate`, :func:`share`, :func:`matrix` or
        :func:`custom` (or their dict specs). Use several only when the argument
        has steps; panels are keyed ``a``, ``b``, ``c`` in order.
    subtitle:
        Optional context line under the title (scope, period, population).
    source, note:
        Footer lines: where the numbers came from, and any caveat (synthetic,
        estimated, n, what an interval means).
    layout:
        Rows of panel keys, e.g. ``[["a"], ["b", "c"]]``; repeat a key within a
        row to widen it. Defaults: two panels side by side, three as one wide
        row above two, four as a 2x2.
    target, width:
        Spec and width preset. The default (``"screen"``, ``"chat"``) is sized
        for a ~700 px chat column; pass a journal name for print.
    style:
        Visual surface theme: ``"mintfig"`` (default), ``"bold"``, ``"editorial"``, ``"sketch"``,
        or a custom :class:`Theme`. Changes surface aesthetics only, never rules.
    colors:
        Pin a name to a colour slot so it keeps its colour across figures in one
        conversation: ``{"no retrieval": "red"}``. Slots are ``"blue"``, ``"red"``,
        ``"green"`` and ``"amber"``, resolved from the style's validated palette.
        Within one figure a name always has one colour; pinned names are fixed
        entries of that registry.
    out:
        If given, the figure is saved there immediately.
    """
    effective_strict = bool(strict) and _is_strict()
    local_adjustments: list[str] = list(_ADJUSTMENTS.get() or [])
    if not effective_strict:
        tok_s = _STRICT.set(False)
        tok_a = _ADJUSTMENTS.set(local_adjustments)
        try:
            return _explain_impl(
                takeaway,
                *panels,
                subtitle=subtitle,
                source=source,
                note=note,
                layout=layout,
                target=target,
                width=width,
                style=style,
                palette=palette,
                accent=accent,
                colors=colors,
                strict=False,
                adjustments=local_adjustments,
                out=out,
            )
        finally:
            _STRICT.reset(tok_s)
            _ADJUSTMENTS.reset(tok_a)
    return _explain_impl(
        takeaway,
        *panels,
        subtitle=subtitle,
        source=source,
        note=note,
        layout=layout,
        target=target,
        width=width,
        style=style,
        palette=palette,
        accent=accent,
        colors=colors,
        strict=True,
        adjustments=local_adjustments,
        out=out,
    )


def _explain_impl(
    takeaway: str,
    *panels: Panel | Mapping[str, Any],
    subtitle: str | None = None,
    source: str | None = None,
    note: str | None = None,
    layout: Sequence[Sequence[str]] | None = None,
    target: str | JournalSpec = "screen",
    width: str | float = "chat",
    style: str | Theme = "mintfig",
    palette: str | ExplainPalette | None = None,
    accent: str | None = None,
    colors: Mapping[str, str] | None = None,
    strict: bool = True,
    adjustments: list[str] | None = None,
    out: str | Path | None = None,
) -> Explanation:
    adj = adjustments if adjustments is not None else []
    try:
        theme = get_theme(style)
    except (TypeError, ValueError) as exc:
        if not strict:
            theme = MINTFIG_THEME
            _record_adjustment(f"explain(style={style!r}): fell back to 'mintfig'")
        else:
            aliases = ", ".join(sorted(THEME_ALIASES))
            raise ExplainError(
                str(exc),
                fix_hint=f"Use one of: {', '.join(THEMES)} (aliases: {aliases}).",
                rule="unknown_style",
            ) from exc
    try:
        theme, palette_name = apply_palette(theme, palette)
    except (TypeError, ValueError) as exc:
        if not strict:
            palette_name = None
            _record_adjustment(f"explain(palette={palette!r}): fell back to 'default'")
        else:
            raise ExplainError(
                str(exc),
                fix_hint=f"Use one of: {', '.join(EXPLAIN_PALETTES)}.",
                rule="unknown_palette",
            ) from exc
    try:
        theme, accent_hex = apply_accent(theme, accent)
    except ValueError as exc:
        if not strict:
            accent_hex = None
            _record_adjustment(f"explain(accent={accent!r}): ignored invalid accent color")
        else:
            raise ExplainError(
                str(exc),
                fix_hint="Pass a valid hex/CSS color string such as accent='#D97757'.",
                rule="invalid_accent",
            ) from exc

    built: list[Panel] = []
    for item in panels:
        if isinstance(item, Panel):
            built.append(item)
        elif isinstance(item, Mapping):
            built.append(panel_from_spec(item))
        else:
            raise ExplainError(
                f"explain() panels must come from mint.compare/trend/..., got {type(item).__name__}.",
                fix_hint="e.g. mint.explain('...', mint.compare({...}), mint.trend(x, {...})).",
            )
    if not built:
        raise ExplainError(
            "explain() needs at least one panel.",
            fix_hint="Add evidence, e.g. mint.compare({'a': 3, 'b': 1}).",
        )
    if len(built) > MAX_PANELS:
        if not strict:
            _record_adjustment(f"explain(): trimmed {len(built)} panels to first {MAX_PANELS}")
            built = built[:MAX_PANELS]
        else:
            raise ExplainError(
                f"explain() got {len(built)} panels; more than {MAX_PANELS} cannot be read in one figure.",
                fix_hint=f"explain() takes at most {MAX_PANELS} panels ({COMFORTABLE_PANELS} read "
                "comfortably): split the argument into two figures, each with its own takeaway, or "
                "fold related panels into one (trend(facet=True), a matrix()).",
                rule="too_many_panels",
            )
    if not isinstance(takeaway, str) or not takeaway.strip():
        if not strict:
            fallback = next(
                (p.title for p in built if p.title),
                next((p.facts[0] for p in built if p.facts), "Summary"),
            )
            takeaway = str(fallback)
            _record_adjustment("explain(): used first panel title/fact as takeaway")
        else:
            raise ExplainError(
                "explain() needs a takeaway sentence as its first argument.",
                fix_hint="Write the one thing the reader should conclude, then choose panels that show it.",
                rule="takeaway_missing",
            )
    takeaway = " ".join(takeaway.split())

    pinned = _pinned_colors(colors, theme)
    panel_colors, uniform_color, colour_issues = _colour_registry(built, theme, pinned)

    spec = get_spec(target)
    keys = [chr(ord("a") + i) for i in range(len(built))]
    panel_map = dict(zip(keys, built, strict=True))
    is_narrow = isinstance(width, str) and width.strip().lower() == "narrow"
    if layout is not None:
        rows = _validate_layout(layout, keys)
    elif is_narrow and len(keys) > 1:
        rows = [[k] for k in keys]
    else:
        rows = _auto_layout(keys)

    issues: list[dict[str, Any]] = list(_takeaway_issues(takeaway))
    issues.extend(_latex_issues((takeaway, subtitle, source, note), panel_map))
    issues.extend(colour_issues)
    if len(built) > COMFORTABLE_PANELS:
        issues.append(
            _issue(
                "many_panels",
                "warning",
                f"{len(built)} panels is a lot for one glance in a conversation.",
                "Keep the panels the takeaway needs; move the rest to a follow-up figure.",
            )
        )
    if theme.warn_unless_illustrative:
        provenance = " ".join(t for t in (source, note) if t)
        if not _ILLUSTRATIVE_CUE.search(provenance):
            issues.append(
                _issue(
                    "sketch_on_measured_data",
                    "warning",
                    "style='sketch' signals a conceptual sketch, but source/note does not mark "
                    "these numbers as illustrative or synthetic.",
                    "Use style='mintfig', 'editorial', or 'bold' for measured data, or note in "
                    "source=/note= that the values are illustrative or synthetic.",
                )
            )

    with theme.rc_context(spec), _GlyphCapture() as glyph_log:
        sizes = _Sizes.from_spec(spec, theme)
        if is_narrow and spec.name == "screen":
            # Keep smallest text >= 12 px at 450 px sidebar width while tightening
            # the headline slightly so takeaways wrap cleanly within 92 mm.
            sizes = _Sizes(
                scale=sizes.scale,
                title=min(sizes.title, max(sizes.body + 1.5, round(sizes.title * 0.92, 1))),
                body=sizes.body,
                small=sizes.small,
                foot=max(sizes.foot, 7.0),
            )
        s = sizes.scale
        measure = _Measure(theme)
        width_mm = float(spec.resolve_width_mm(width))
        margin = _MARGIN_MM * s
        content_mm = width_mm - 2 * margin
        content_pt = content_mm / PT_TO_MM

        def _line_mm(size: float) -> float:
            return size * _LINE * PT_TO_MM

        title_lines = measure.wrap(
            takeaway,
            content_pt,
            sizes.title,
            theme.title_weight,
            family=theme.title_family,
        )
        if len(title_lines) > MAX_TITLE_LINES:
            if not strict:
                if len(title_lines) > MAX_TITLE_LINES + 2:
                    ell = theme.ellipsis
                    title_lines = [*title_lines[: MAX_TITLE_LINES + 1], title_lines[MAX_TITLE_LINES + 1] + ell]
                _record_adjustment(
                    f"explain(): wrapped long takeaway onto {len(title_lines)} lines"
                )
            else:
                raise ExplainError(
                    f"The takeaway is {len(takeaway)} characters and wraps to {len(title_lines)} lines.",
                    fix_hint=f"The takeaway may wrap to at most {MAX_TITLE_LINES} lines: cut it to "
                    "one sentence (about 100 characters); move scope and caveats to subtitle= and "
                    "note=.",
                    rule="takeaway_too_long",
                )
        subtitle_lines = measure.wrap(subtitle, content_pt, sizes.body) if subtitle else []
        footer_text = [t for t in (note, f"Source: {source}" if source else None) if t]
        footer_lines = [ln for t in footer_text for ln in measure.wrap(t, content_pt, sizes.foot)]

        top_rule_pad = 2.2 * s if theme.top_rule else 0.0
        header_mm = (
            top_rule_pad
            + len(title_lines) * _line_mm(sizes.title)
            + len(subtitle_lines) * _line_mm(sizes.body)
        )
        header_gap = 4.0 * s
        footer_rule_pad = 2.0 * s if (theme.footer_rule and footer_lines) else 0.0
        footer_mm = footer_rule_pad + len(footer_lines) * _line_mm(sizes.foot)
        footer_gap = 3.5 * s if footer_lines else 0.0

        multi = len(built) > 1
        letter_pt = measure.width_pt("a", sizes.body, "bold") + sizes.body * 0.75 if multi else 0.0

        # Per-row geometry (mm)
        row_plans: list[dict[str, Any]] = []
        for row in rows:
            order = [k for i, k in enumerate(row) if i == 0 or row[i - 1] != k]
            unit_mm = (content_mm - _COL_GAP_MM * s * (len(row) - 1)) / len(row)
            cells: list[dict[str, Any]] = []
            x_mm = margin
            for key in order:
                span = row.count(key)
                cell_w = unit_mm * span + _COL_GAP_MM * s * (span - 1)
                panel = panel_map[key]
                head_lines = (
                    measure.wrap(panel.title, cell_w / PT_TO_MM - letter_pt, sizes.body, "bold")
                    if panel.title
                    else ([""] if multi else [])
                )
                inline_unit_panel = (
                    theme.inline_y_ticks
                    and panel.kind == "trend"
                    and not panel.spec.get("facet")
                    and not panel.spec.get("log")
                    and bool(panel.unit)
                )
                measure_text = (
                    panel.label if inline_unit_panel else _measure_text(panel.label, panel.unit)
                )
                if panel.measure_note:
                    measure_text = (
                        f"{measure_text}; {panel.measure_note}"
                        if measure_text
                        else panel.measure_note
                    )
                measure_lines = (
                    measure.wrap(measure_text, cell_w / PT_TO_MM - letter_pt, sizes.small)
                    if measure_text
                    else []
                )
                head_mm = len(head_lines) * _line_mm(sizes.body) + len(measure_lines) * _line_mm(
                    sizes.small
                )
                if head_mm:
                    head_mm += 2.2 * s
                cells.append(
                    {
                        "key": key,
                        "x": x_mm,
                        "w": cell_w,
                        "head_lines": head_lines,
                        "measure_lines": measure_lines,
                        "head_mm": head_mm,
                        "plot_mm": panel._height_mm(cell_w / s, measure, sizes, theme) * s,
                    }
                )
                floor = panel._min_height_mm
                cells[-1]["min_mm"] = min(
                    cells[-1]["plot_mm"],
                    floor(cell_w / s, measure, sizes, theme) * s if floor else cells[-1]["plot_mm"],
                )
                x_mm += cell_w + _COL_GAP_MM * s
            if len(rows) > 1 and len(cells) == 1 and panel_map[cells[0]["key"]].stretch:
                # A full-width line or scatter panel in a multi-row figure would set the
                # tallest row of the figure; cap it so three panels stay on one screen.
                cells[0]["plot_mm"] = min(cells[0]["plot_mm"], _FULL_ROW_STRETCH_MM * s)
                cells[0]["min_mm"] = min(cells[0]["min_mm"], cells[0]["plot_mm"])
            row_plans.append(
                {
                    "cells": cells,
                    "head_mm": max(c["head_mm"] for c in cells),
                    "plot_mm": max(c["plot_mm"] for c in cells),
                }
            )

        def _height_at(squeeze: float) -> float:
            """Figure height with every panel ``squeeze`` (0..1) of the way to its minimum."""
            body = sum(
                r["head_mm"]
                + max(c["plot_mm"] - squeeze * (c["plot_mm"] - c["min_mm"]) for c in r["cells"])
                for r in row_plans
            ) + _ROW_GAP_MM * s * (len(row_plans) - 1)
            return margin + header_mm + header_gap + body + footer_gap + footer_mm + margin

        natural_mm = _height_at(0.0)
        height_mm = natural_mm
        squeeze = 0.0
        limit_mm = spec.max_height_mm
        if natural_mm > limit_mm + 0.5 and _height_at(1.0) <= limit_mm + 0.5:
            # Too tall for one screen at natural size, but it fits with the panels nearer
            # their minimum readable height: compress just enough, not a warning.
            lo, hi = 0.0, 1.0
            for _ in range(24):
                mid = 0.5 * (lo + hi)
                lo, hi = (lo, mid) if _height_at(mid) <= limit_mm else (mid, hi)
            squeeze = hi
            for plan in row_plans:
                for cell in plan["cells"]:
                    cell["plot_mm"] -= squeeze * (cell["plot_mm"] - cell["min_mm"])
                plan["plot_mm"] = max(c["plot_mm"] for c in plan["cells"])
            height_mm = _height_at(0.0)

        fig = Figure(
            figsize=(mm_to_in(width_mm), mm_to_in(height_mm)),
            dpi=150,
            facecolor=theme.background,
        )
        FigureCanvasAgg(fig)
        fig._mintfig_journal = spec.name  # type: ignore[attr-defined]
        px_per_mm = float(fig.dpi) / 25.4

        def _fx(mm: float) -> float:
            return mm / width_mm

        def _fy(mm_from_top: float) -> float:
            return 1.0 - mm_from_top / height_mm

        cursor = margin
        if theme.top_rule:
            rule_y = _fy(cursor + 0.3 * s)
            fig.add_artist(
                Line2D(
                    [_fx(margin), _fx(width_mm - margin)],
                    [rule_y, rule_y],
                    transform=fig.transFigure,
                    color=theme.top_rule_color or theme.ink,
                    linewidth=theme.top_rule_lw * s,
                    solid_capstyle="butt",
                )
            )
            cursor += top_rule_pad

        for line in title_lines:
            title_kw: dict[str, Any] = {
                "ha": "left",
                "va": "top",
                "fontsize": sizes.title,
                "fontweight": theme.title_weight,
                "color": theme.ink,
            }
            if theme.title_family is not None:
                title_kw["fontfamily"] = list(theme.title_family)
            t_art = fig.text(_fx(margin), _fy(cursor), _plain(line, theme), **title_kw)
            if theme.allow_serif_title:
                t_art._mintfig_allow_serif = True  # type: ignore[attr-defined]
            cursor += _line_mm(sizes.title)
        for line in subtitle_lines:
            fig.text(
                _fx(margin),
                _fy(cursor + 0.3 * s),
                _plain(line, theme),
                ha="left",
                va="top",
                fontsize=sizes.body,
                color=theme.muted,
            )
            cursor += _line_mm(sizes.body)
        cursor += header_gap

        axes: dict[str, Axes] = {}
        finishers: list[tuple[str, Panel, Callable[[], None]]] = []
        tick_axes: list[tuple[Axes, str]] = []
        contexts: list[tuple[str, _Ctx, int]] = []
        for plan in row_plans:
            row_top = cursor
            for cell in plan["cells"]:
                key = cell["key"]
                panel = panel_map[key]
                text_x = cell["x"] + letter_pt * PT_TO_MM
                y_mm = row_top
                if multi:
                    tag = fig.text(
                        _fx(cell["x"]),
                        _fy(y_mm),
                        key,
                        ha="left",
                        va="top",
                        fontsize=sizes.body,
                        fontweight="bold",
                        color=theme.resolved_panel_tag_color,
                    )
                    tag._mintfig_panel_label = True  # type: ignore[attr-defined]
                for line in cell["head_lines"]:
                    if line:
                        fig.text(
                            _fx(text_x),
                            _fy(y_mm),
                            _plain(line, theme),
                            ha="left",
                            va="top",
                            fontsize=sizes.body,
                            fontweight="bold",
                            color=theme.ink,
                        )
                    y_mm += _line_mm(sizes.body)
                for line in cell["measure_lines"]:
                    fig.text(
                        _fx(text_x),
                        _fy(y_mm + 0.2 * s),
                        _plain(line, theme),
                        ha="left",
                        va="top",
                        fontsize=sizes.small,
                        color=theme.muted,
                    )
                    y_mm += _line_mm(sizes.small)

                plot_top = row_top + plan["head_mm"]
                # Bar-like panels keep their own pitch instead of fattening to
                # match a taller neighbour in the same row.
                plot_mm = (
                    plan["plot_mm"]
                    if panel.stretch
                    else min(plan["plot_mm"], cell["plot_mm"] * _ROW_GROWTH)
                )
                rect = Bbox.from_extents(
                    cell["x"] * px_per_mm,
                    (height_mm - plot_top - plot_mm) * px_per_mm,
                    (cell["x"] + cell["w"]) * px_per_mm,
                    (height_mm - plot_top) * px_per_mm,
                )
                ctx = _Ctx(
                    fig=fig,
                    sizes=sizes,
                    key=key,
                    cell_width_mm=cell["w"] / s,
                    measure=measure,
                    theme=theme,
                    measure_label=_measure_text(panel.label, panel.unit) or "(see measure_unnamed)",
                    colors=panel_colors[keys.index(key)],
                    uniform_color=uniform_color,
                )
                ax = ctx.tag(fig.add_axes([0.1, 0.1, 0.5, 0.5]))
                _fit_axes(fig, ax, rect)
                try:
                    finish = panel._draw(ctx, ax)
                    frames = panel._frames(ctx, ax, rect) if panel._frames else [(ax, rect)]
                    for frame_ax, frame_rect in frames:
                        _fit_axes(fig, frame_ax, frame_rect)
                        _check_plot_width(fig, panel, frame_ax, frame_rect, s)
                except ExplainError as exc:
                    if (
                        not strict
                        and layout is None
                        and len(built) > 1
                        and rows != [[k] for k in keys]
                        and exc.rule in {"panel_too_small", "matrix_cells_too_small", "table_too_wide"}
                    ):
                        _record_adjustment(
                            "layout: stacked panels into full-width rows so every label fits"
                        )
                        return _explain_impl(
                            takeaway,
                            *built,
                            subtitle=subtitle,
                            source=source,
                            note=note,
                            layout=[[k] for k in keys],
                            target=target,
                            width=width,
                            style=style,
                            palette=palette,
                            accent=accent,
                            colors=colors,
                            strict=False,
                            adjustments=adj,
                            out=out,
                        )
                    raise ExplainError(
                        f"Panel {key} ({panel.kind}): {exc.message}",
                        fix_hint=exc.fix_hint,
                        rule=exc.rule,
                    ) from exc
                which = _TICK_AXES.get(panel.kind, "")
                if which:
                    tick_axes.extend((frame_ax, which) for frame_ax, _ in frames)
                if callable(finish):
                    finishers.append((key, panel, finish))
                finishers.extend((key, panel, extra) for extra in ctx.finishers)
                issues.extend({**issue, "panel": key} for issue in (*panel.issues, *ctx.issues))
                contexts.append((key, ctx, len(ctx.issues)))
                has_measure = bool(
                    panel.label
                    or panel.unit
                    or (
                        panel.kind == "timeline"
                        and (panel.spec.get("x_label") or panel.spec.get("unit"))
                    )
                )
                if panel.kind in KINDS and panel.kind != "table" and not has_measure:
                    issues.append(
                        _issue(
                            "measure_unnamed",
                            "warning",
                            f"Panel {key} ({panel.kind}) does not say what is measured.",
                            'Pass label= and unit=, e.g. label="p99 latency", unit="ms".',
                            panel=key,
                        )
                    )
                axes[key] = frames[0][0]
            cursor = row_top + plan["head_mm"] + plan["plot_mm"] + _ROW_GAP_MM * s

        y_mm = height_mm - margin - footer_mm
        if theme.footer_rule and footer_lines:
            frule_y = _fy(y_mm + 0.3 * s)
            fig.add_artist(
                Line2D(
                    [_fx(margin), _fx(width_mm - margin)],
                    [frule_y, frule_y],
                    transform=fig.transFigure,
                    color=theme.footer_rule_color or theme.grid,
                    linewidth=theme.footer_rule_lw * s,
                    solid_capstyle="butt",
                )
            )
            y_mm += footer_rule_pad
        for line in footer_lines:
            fig.text(
                _fx(margin),
                _fy(y_mm),
                _plain(line, theme),
                ha="left",
                va="top",
                fontsize=sizes.foot,
                color=theme.muted,
            )
            y_mm += _line_mm(sizes.foot)

        for key, panel, finish in finishers:
            try:
                finish()
            except ExplainError as exc:
                if (
                    not strict
                    and layout is None
                    and len(built) > 1
                    and rows != [[k] for k in keys]
                    and exc.rule in {"panel_too_small", "matrix_cells_too_small", "table_too_wide"}
                ):
                    _record_adjustment(
                        "layout: stacked panels into full-width rows so every label fits"
                    )
                    return _explain_impl(
                        takeaway,
                        *built,
                        subtitle=subtitle,
                        source=source,
                        note=note,
                        layout=[[k] for k in keys],
                        target=target,
                        width=width,
                        style=style,
                        palette=palette,
                        accent=accent,
                        colors=colors,
                        strict=False,
                        adjustments=adj,
                        out=out,
                    )
                raise ExplainError(
                    f"Panel {key} ({panel.kind}): {exc.message}",
                    fix_hint=exc.fix_hint,
                    rule=exc.rule,
                ) from exc
        for tick_ax, which in tick_axes:
            _fit_ticks(fig, tick_ax, which)
        for key, ctx, seen in contexts:  # warnings raised while finishing the layout
            issues.extend({**issue, "panel": key} for issue in ctx.issues[seen:])

        result = Explanation(
            fig=fig,
            spec=spec,
            theme=theme,
            palette=palette_name,
            accent=accent_hex,
            takeaway=takeaway,
            subtitle=subtitle,
            source=source,
            note=note,
            panels=panel_map,
            axes=axes,
            layout=rows,
            width=width,
            issues=issues,
            colors={k: str(v) for k, v in _pairs(colors)} if colors else None,
            strict=strict,
            adjustments=adj,
        )
        slot_of = {theme.series_colors[i]: slot for slot, i in COLOR_SLOTS.items()}
        for panel_map_colors in panel_colors:
            for name, col in panel_map_colors.items():
                key = _entity_key(name)
                used = set(result.entity_colors.values())
                if col in slot_of and key not in result.entity_colors and slot_of[col] not in used:
                    result.entity_colors[key] = slot_of[col]  # overflow reuse is left out

        if height_mm > spec.max_height_mm + 0.5:
            issues.append(
                _too_tall_issue(row_plans, panel_map, height_mm, _height_at(1.0), width_mm, spec)
            )
        if spec.name == "screen" and result.min_text_px < MIN_TEXT_PX:
            issues.append(
                _issue(
                    "small_at_chat_size",
                    "warning",
                    f"The smallest text is {result.min_text_px:.1f} px when shown "
                    f"{result.display_width_px} px wide (floor {MIN_TEXT_PX:.0f} px).",
                    'Use width="chat" for a 700 px chat column, width="narrow" for a 450 px IDE sidebar, or width="slide" for a 1280 px presentation/blog hero.',
                )
            )

        missing = _missing_glyphs(fig)
        for ch in glyph_log.missing():
            missing.setdefault(ch, "")
        if missing:
            issues.append(_glyph_issue(missing))

        from ..audit import audit_figure, audit_to_issues
        from ..preflight import preflight_figure

        report = preflight_figure(fig, spec)
        for check in report.issues:
            if check.rule == "dimensions":
                continue  # height is reported above as too_tall, in chat terms
            issues.append(
                {
                    "rule": check.rule,
                    "severity": "error" if check.status == "fail" else "warning",
                    "panel": check.panel,
                    "message": check.message,
                    "fix_hint": _EXPLAIN_PREFLIGHT_HINTS.get(check.rule, check.fix_hint),
                }
            )
        audit = audit_figure(fig, allow_ascii_minus=(theme.minus_sign == "-"))
        existing_rules = {str(i.get("rule", "")) for i in issues}
        issues.extend(audit_to_issues(audit, existing_rules=existing_rules))

        from ..epistemic import audit_epistemic

        issues.extend(audit_epistemic(takeaway, panel_map))
        if not strict:
            actionable = [
                i
                for i in issues
                if i["severity"] == "error" or i["rule"] in _VISUAL_DEFECT_RULES
            ]
            advisory = [i for i in issues if i not in actionable]
            result.issues = actionable
            result.advisories = advisory

    if out is not None:
        result.save(out)
    return result


# --------------------------------------------------------------------------- #
# JSON spec entry points
# --------------------------------------------------------------------------- #

_BUILDERS: dict[str, Callable[..., Panel]] = {
    "compare": compare,
    "trend": trend,
    "change": change,
    "distribution": distribution,
    "histogram": histogram,
    "relate": relate,
    "share": share,
    "matrix": matrix,
    "table": table,
    "waterfall": waterfall,
    "timeline": timeline,
    "flow": flow,
}
_POSITIONAL: dict[str, tuple[str, ...]] = {
    "compare": ("values",),
    "trend": ("x",),  # series may be replaced by points=
    "change": ("before", "after"),
    "distribution": ("groups",),
    "histogram": ("values",),
    "relate": ("x", "y"),
    "share": ("parts",),
    "matrix": ("values",),
    "table": ("rows",),
    "waterfall": ("steps",),
    "timeline": ("spans",),
    "flow": ("stages",),
}


def panel_from_spec(spec: Mapping[str, Any]) -> Panel:
    """Build one panel from its dict form, e.g. ``{"kind": "compare", "values": {...}}``."""
    options = dict(spec)
    kind = options.pop("kind", None)
    if kind == "histogram" and "values" not in options and "groups" in options:
        options["values"] = options.pop("groups")
    if kind not in _BUILDERS:
        raise ExplainError(
            f"Unknown panel kind {kind!r}.",
            fix_hint=f"Use one of: {', '.join(KINDS)}.",
        )
    missing = [name for name in _POSITIONAL[kind] if name not in options]
    if missing:
        raise ExplainError(
            f"A {kind} panel needs {', '.join(map(repr, missing))}.",
            fix_hint=f"Required keys for {kind}: {', '.join(_POSITIONAL[kind])}.",
        )
    try:
        return _BUILDERS[kind](**options)
    except TypeError as exc:
        raise ExplainError(
            f"Invalid options for a {kind} panel: {exc}.",
            fix_hint=f"See `mintfig explain --example` or help(mintfig.{kind}).",
        ) from exc


def explain_from_spec(
    spec: Mapping[str, Any],
    *,
    out: str | Path | None = None,
    strict: bool = True,
) -> Explanation:
    """Render a whole figure from its JSON spec (the inverse of :meth:`Explanation.to_spec`)."""
    options = dict(spec)
    takeaway = options.pop("takeaway", "")
    panels = options.pop("panels", None)
    if not isinstance(panels, Sequence) or isinstance(panels, (str, bytes)) or not panels:
        raise ExplainError(
            'The spec needs a "panels" list.',
            fix_hint='e.g. {"takeaway": "...", "panels": [{"kind": "compare", "values": {...}}]}.',
        )
    allowed = {
        "subtitle",
        "source",
        "note",
        "layout",
        "target",
        "width",
        "style",
        "palette",
        "accent",
        "colors",
        "strict",
    }
    unknown = sorted(set(options) - allowed)
    if unknown:
        if not (strict and _is_strict()):
            for k in unknown:
                options.pop(k, None)
        else:
            raise ExplainError(
                f"Unknown top-level key(s) {unknown!r}.",
                fix_hint=f"Allowed: takeaway, panels, {', '.join(sorted(allowed))}.",
            )
    spec_strict = options.pop("strict", strict)
    effective_strict = bool(spec_strict) and bool(strict) and _is_strict()
    return explain(takeaway, *panels, out=out, strict=effective_strict, **options)


EXAMPLE_SPEC: dict[str, Any] = {
    "takeaway": "Checkout is the slow service: its p99 is 4x the next worst",
    "subtitle": "API p99 latency by service, week of 16 Nov",
    "source": "synthetic example data",
    "panels": [
        {
            "kind": "compare",
            "title": "Checkout stands alone",
            "label": "p99 latency",
            "unit": "ms",
            "values": {
                "checkout": 1840,
                "search": 460,
                "auth": 310,
                "catalog": 280,
                "cart": 240,
                "profile": 120,
            },
            "highlight": "checkout",
        },
        {
            "kind": "trend",
            "title": "It regressed after the v2.3 deploy",
            "label": "p99 latency",
            "unit": "ms",
            "x_label": "Week",
            "x": [1, 2, 3, 4, 5, 6, 7, 8],
            "series": {
                "checkout": [540, 560, 550, 570, 980, 1400, 1700, 1840],
                "search": [450, 470, 455, 465, 460, 450, 470, 460],
                "auth": [300, 310, 305, 315, 300, 320, 305, 310],
            },
            "highlight": "checkout",
            "events": {"4": "v2.3 deploy"},
        },
    ],
}
