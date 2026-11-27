"""compare() and share() forms for mint.explain."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np
from matplotlib.axes import Axes
from matplotlib.patches import PathPatch, Wedge
from matplotlib.path import Path as MplPath
from matplotlib.ticker import (
    FuncFormatter,
    MaxNLocator,
)

from ..annotations import _relax_positions_pt
from ..themes import (
    MINTFIG_THEME,
    Theme,
    contrast_ratio,
)
from .core import (
    COMFORTABLE_COMPARE_ITEMS,
    MAX_COMPARE_ITEMS,
    PT_TO_MM,
    ExplainError,
    Panel,
    _and_list,
    _bare_axes,
    _base_spec,
    _baseline_name,
    _cover_with_ticks,
    _Ctx,
    _delta_label,
    _diff_with_unit,
    _formatter,
    _guarded,
    _halfwidth,
    _has_items,
    _inline_unit,
    _interval_issue,
    _interval_mode_text,
    _is_number,
    _is_strict,
    _issue,
    _jsonable,
    _Measure,
    _named_values,
    _names,
    _narrow_log_ticks,
    _or_list,
    _pairs,
    _percent_change,
    _plain,
    _range_with_unit,
    _ratio_text,
    _record_adjustment,
    _reference_line,
    _shows_zero,
    _sig_text,
    _signed,
    _Sizes,
    _tick_label,
    _to_float,
    _unsigned,
    _vs_text,
    _with_unit,
)
from .marks import tag_each, tag_points

# --------------------------------------------------------------------------- #
# compare / share
# --------------------------------------------------------------------------- #


def _bar_panel(
    *,
    kind: str,
    names: list[str],
    values: list[float],
    highlight: list[str],
    labels: list[str],
    title: str | None,
    label: str | None,
    unit: str | None,
    spec: dict[str, Any],
    facts: list[str],
    describe: str,
    dots: bool,
    errors: dict[str, tuple[float, float]] | None,
    reference: tuple[float, str] | None,
    muted_names: Sequence[str] = (),
    issues: list[dict[str, Any]] | None = None,
    log: bool = False,
    measure_note: str | None = None,
    baseline: str | None = None,
    counts: Mapping[str, int] | None = None,
    boosts: Sequence[float] | None = None,
    inner_errors: dict[str, tuple[float, float]] | None = None,
    auto_delta: bool = False,
    fmt: str | None = None,
) -> Panel:
    n = len(names)
    hl_index = {name: i for i, name in enumerate(highlight)}
    counts = dict(counts or {})

    def _wrapped(
        cell_width_mm: float,
        measure: _Measure,
        sizes: _Sizes,
        theme: Theme = MINTFIG_THEME,
    ) -> list[str]:
        """Item names wrapped to two lines so long names never squeeze the bars."""
        cell_pt = cell_width_mm * sizes.scale / PT_TO_MM
        ell = theme.ellipsis
        out: list[str] = []
        for name in names:
            weight = "bold" if name in hl_index else "normal"
            lines = measure.wrap(name, 0.42 * cell_pt, sizes.body, weight)
            if len(lines) > 3:  # a long name wraps onto up to three lines before any is cut
                lines = [*lines[:2], " ".join(lines[2:])]
            fitted: list[str] = []
            for line in lines:
                min_len = max(4, len(ell) + 2)
                while (
                    len(line) > min_len
                    and measure.width_pt(line, sizes.body, weight) > 0.5 * cell_pt
                ):
                    if len(ell) == 1:
                        line = line[:-2].rstrip() + ell
                    else:
                        base = line.removesuffix(ell)
                        line = base[:-1].rstrip() + ell
                fitted.append(line)
            out.append("\n".join(fitted))
        return out

    def _truncated(shown: list[str], theme: Theme = MINTFIG_THEME) -> list[str]:
        """Names cut on any of their lines (a long first word is cut too, not only the last)."""
        ell = theme.ellipsis
        return [
            name
            for name, text in zip(names, shown, strict=True)
            if text.replace("\n", " ").count(ell) > name.count(ell)
        ]

    def _pitch(wrapped: list[str], tight: bool = False, compact: bool = False) -> float:
        lines = max(name.count("\n") + 1 for name in wrapped)
        # A count under each name ("n=84") takes about one small line more.
        extra = (2.4 if (tight or compact) else 2.8) if counts else 0.0
        if compact:  # density="compact": names and value labels just clear each other
            return {1: (4.2 if tight else 4.4), 2: 6.8}.get(lines, 9.6) + extra
        if tight:  # the closest pitch at which names and value labels still clear
            return {1: 4.6, 2: 7.2}.get(lines, 10.0) + extra
        return {1: 5.3, 2: 8.2}.get(lines, 11.0) + extra

    def _extras() -> float:
        return (4.0 if reference and reference[1] else 0.0) + (5.0 if (log or errors) else 0.0)

    def _draw(ctx: _Ctx, ax: Axes) -> Callable[[], None] | None:
        sz = ctx.sizes
        theme = ctx.theme
        # Figure-level colours: highlighted names, or (without highlight) names that are
        # coloured elsewhere in the figure; every other item is context grey.
        # The baseline is drawn in ink (or its pinned colour) at normal weight: a
        # reference, not an emphasis, so it never turns the other items grey.
        accent = {
            name: col for name, col in ctx.colors.items() if name in names and name != baseline
        }
        # Bold marks the emphasis: the highlighted names, or (without highlight) the names
        # coloured elsewhere. A name coloured elsewhere keeps its colour, not the emphasis.
        emphasis = set(highlight) if highlight else set(accent)

        def _color(name: str) -> str:
            if name == baseline:
                return ctx.colors.get(name, theme.ink)
            if highlight or accent:
                return accent.get(name, theme.context_fill)
            return theme.context_fill if name in muted_names else ctx.default_color

        y = np.arange(n, dtype=float)
        vals = np.asarray(values, dtype=float)

        def _mark_records() -> list[dict[str, Any]]:
            return [
                {"name": nm, "value": v, "lo": (errors or {}).get(nm, (None, None))[0],
                 "hi": (errors or {}).get(nm, (None, None))[1], "n": counts.get(nm),
                 "unit": unit or ("%" if kind == "share" else None)}
                for nm, v in zip(names, values, strict=True)
            ]
        boost_arr = np.asarray(boosts, dtype=float) if boosts is not None else None
        totals = vals + boost_arr if boost_arr is not None else vals
        colors = [_color(name) for name in names]
        lows = np.array([errors[nm][0] if errors else v for nm, v in zip(names, vals, strict=True)])
        highs = np.array(
            [errors[nm][1] if errors else v for nm, v in zip(names, totals, strict=True)]
        )
        _bare_axes(ax)
        ax.set_ylim(n - 0.5, -0.5)

        if dots:
            lo = float(min(lows.min(), reference[0] if reference else np.inf))
            hi = float(max(highs.max(), reference[0] if reference else -np.inf))
            if log:
                ax.set_xscale("log")
                pad = max((hi / lo) ** 0.05, 1.15)
                ax.set_xlim(
                    *_narrow_log_ticks(
                        ax.xaxis, lo / pad, hi * pad, theme.minus_sign, extend=False, data_hi=hi
                    )
                )
            else:
                if not errors and lo >= 0 and (hi - lo) > 0.6 * hi:
                    lo = 0.0  # the spread already covers most of the way to zero
                span = (hi - lo) or abs(hi) or 1.0
                ax.set_xlim(lo - 0.05 * span, hi + 0.03 * span)
            left = ax.get_xlim()[0]
            stem_color = theme.grid if theme.grid_style != "none" else theme.context_fill
            dot_colors = [c if c != theme.context_fill else theme.axis for c in colors]
            if errors:
                # Thin whiskers with small end caps: the caps stay visible beside the dot,
                # and the value axis below lets the reader measure each interval.
                ax.hlines(y, lows, highs, color=dot_colors, linewidth=0.9 * sz.scale, zorder=2)
                for ends in (lows, highs):
                    ax.vlines(
                        ends,
                        y - 0.16,
                        y + 0.16,
                        color=dot_colors,
                        linewidth=0.9 * sz.scale,
                        zorder=2,
                    )
                if inner_errors is not None:
                    in_lows = np.array([inner_errors[nm][0] for nm in names], dtype=float)
                    in_highs = np.array([inner_errors[nm][1] for nm in names], dtype=float)
                    ax.hlines(
                        y,
                        in_lows,
                        in_highs,
                        color=dot_colors,
                        linewidth=2.6 * sz.scale,
                        capstyle="round",
                        zorder=2.5,
                    )
            else:
                ax.hlines(y, left, vals, color=stem_color, linewidth=0.7, zorder=1)
            dots_art = ax.scatter(
                vals,
                y,
                s=(5.2 * sz.scale) ** 2,
                color=dot_colors,
                edgecolor=theme.background,
                linewidth=0.6,
                zorder=3,
            )
            tag_points(ctx, dots_art, vals, y, _mark_records())
        else:
            lo = float(min(0.0, vals.min(), reference[0] if reference else 0.0))
            hi = float(max(0.0, totals.max(), reference[0] if reference else 0.0))
            if hi == lo:
                hi = lo + 1.0
            ax.set_xlim(lo, hi)
            bar_h = min(theme.bar_height, 0.6) if sz.compact else theme.bar_height
            bar_kw: dict[str, Any] = {
                "height": bar_h,
                "color": colors,
                "linewidth": theme.bar_edge_lw,
                "zorder": 2,
            }
            if theme.bar_edgecolor is not None and theme.bar_edge_lw > 0:
                bar_kw["edgecolor"] = theme.bar_edgecolor
            tag_each(ctx, ax.barh(y, vals, **bar_kw).patches, _mark_records())
            if boost_arr is not None:
                for yi, b_val, b_ext, col, nm in zip(y, vals, boost_arr, colors, names, strict=True):
                    if b_ext <= 0:
                        continue
                    boost_bar = ax.barh(
                        [yi],
                        [b_ext],
                        left=[b_val],
                        height=bar_h,
                        color=col,
                        alpha=0.34,
                        edgecolor=col,
                        linewidth=0.9 * sz.scale,
                        zorder=2,
                    )
                    tag_each(ctx, boost_bar.patches, [{"name": nm, "value": b_val + b_ext, "unit": unit}])
            ax.axvline(0.0, color=theme.zero_line, linewidth=theme.zero_line_lw, zorder=3)

        if log:
            # A log scale must be visible: the reader cannot infer it from the dots.
            ax.tick_params(
                axis="x",
                length=theme.tick_length,
                width=theme.tick_width,
                color=theme.axis,
                labelsize=sz.small,
                labelcolor=theme.muted,
            )
            ax.spines["bottom"].set_visible(True)
            ax.spines["bottom"].set_color(theme.axis)
            ax.spines["bottom"].set_linewidth(theme.axis_lw)
        elif errors:
            # Intervals need a scale to be read: a light value axis like trend's.
            minus = theme.minus_sign
            ax.xaxis.set_major_locator(MaxNLocator(nbins=4, steps=[1, 2, 2.5, 5, 10]))
            ax.xaxis.set_major_formatter(
                FuncFormatter(lambda v, _p, m=minus, a=ax.xaxis: _tick_label(v, m, a))
            )
            ax.tick_params(axis="x", length=0, labelsize=sz.small, labelcolor=theme.muted, pad=3)
            if theme.grid_style != "none" and theme.grid_lw > 0:
                ax.grid(
                    axis="x", color=theme.grid, linestyle=theme.grid_style, linewidth=theme.grid_lw
                )
            ax.set_axisbelow(True)
            cover = (float(lows.min()), float(highs.max()))
            if reference is not None:
                cover = (min(cover[0], reference[0]), max(cover[1], reference[0]))
            ax._mintfig_cover = cover  # type: ignore[attr-defined]
            _cover_with_ticks(ax.xaxis, *cover)
        else:
            ax.xaxis.set_visible(False)
        shown_names = _wrapped(ctx.cell_width_mm, ctx.measure, sz, theme)
        cut = _truncated(shown_names, theme)
        if cut:
            ctx.issues.append(
                _issue(
                    "names_truncated",
                    "warning",
                    f"{len(cut)} item name(s) were cut to fit: {', '.join(map(repr, cut[:3]))}.",
                    "Shorten the names, or give this panel a full-width row with "
                    'layout=[["a"], ["b"]].',
                    panel=ctx.key,
                )
            )
        ax.set_yticks(y, [_plain(nm, theme) for nm in shown_names])
        ax.tick_params(axis="y", length=0, labelsize=sz.body, labelcolor=theme.ink, pad=5)
        for tick, name in zip(ax.get_yticklabels(), names, strict=True):
            tick.set_linespacing(1.05)
            if name in emphasis:
                tick.set_fontweight("bold")
            elif name in muted_names:
                tick.set_color(theme.muted)
            if counts:
                # The name sits just above the mark's centre line, its count just below,
                # as distribution() writes "n=8" under each group name.
                tick.set_verticalalignment("bottom")
        for yi, name in zip(y, names, strict=True):
            if name not in counts:
                continue
            ax.annotate(
                _plain(f"n={counts[name]}", theme),
                (0.0, yi),
                xycoords=("axes fraction", "data"),
                xytext=(-5.0, -1.0),
                textcoords="offset points",
                ha="right",
                va="top",
                fontsize=sz.foot,
                color=theme.muted,
                annotation_clip=False,
            )

        value_notes: list[tuple[Any, float, float, str]] = []
        for yi, name, value, hi_v, lo_v, text, col in zip(
            y, names, vals, highs, lows, labels, colors, strict=True
        ):
            anchor = hi_v if (dots or value >= 0) else 0.0
            value_note = ax.annotate(
                _plain(text, theme),
                (anchor, yi),
                xytext=(5.0 if (dots or value >= 0) else 4.0, 0.0),
                textcoords="offset points",
                ha="left",
                va="center",
                fontsize=sz.small,
                color=theme.muted if name in muted_names else theme.ink,
                fontweight="bold" if name in emphasis else "normal",
                annotation_clip=False,
            )
            # Where the value can go instead: left of the mark (dots, from the low end of
            # an interval) or inside the bar's end (bars).
            value_notes.append((value_note, float(lo_v if dots else value), float(value), col))

        if auto_delta and reference is None and not log and boosts is None:
            _draw_brackets(
                ctx,
                ax,
                names=names,
                values=values,
                anchors=[float(hi_v if (dots or v >= 0) else 0.0) for v, hi_v in zip(vals, highs, strict=True)],
                labels=labels,
                weights=["bold" if nm in emphasis else "normal" for nm in names],
                highlight=highlight,
                baseline=baseline,
                unit=unit,
                fmt=fmt,
            )

        if reference is not None:
            ref_value, ref_text = reference
            ax.axvline(
                ref_value,
                color=theme.ink,
                linewidth=0.7,
                linestyle=(0, (3, 2)),
                zorder=4,
            )
            if ref_text:
                ax.annotate(
                    _plain(ref_text, theme),
                    (ref_value, 1.0),
                    xycoords=("data", "axes fraction"),
                    xytext=(0.0, 2.5),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=sz.small,
                    color=theme.muted,
                    annotation_clip=False,
                )

        if reference is None:
            return None
        ref_x = reference[0]

        def _clear_reference() -> None:
            """A value label the reference line runs through moves past the line, or to the
            other side of its mark when there is no room past it."""
            renderer = ctx.fig.canvas.get_renderer()
            k = ctx.pt_per_px
            cell = ax.get_tightbbox(renderer)
            frame = ax.get_window_extent(renderer)
            right_limit = max(frame.x1, cell.x1 if cell is not None else frame.x1)
            line_px = float(ax.transData.transform((ref_x, 0.0))[0])
            gap = 3.0 / k
            for note, other_anchor, value, col in value_notes:
                box = note.get_window_extent(renderer)
                if not (box.x0 - 1 <= line_px <= box.x1 + 1):
                    continue
                dx, dy = note.xyann
                shift = (line_px + gap - box.x0) * k
                note.set_position((dx + shift, dy))
                moved = note.get_window_extent(renderer)
                if moved.x1 <= right_limit + 1:
                    continue
                note.xy = (other_anchor, note.xy[1])
                note.set_horizontalalignment("right")
                if dots:
                    note.set_position((-5.0, dy))
                else:  # inside the bar's end, in whichever of ink or paper reads on it
                    note.set_position((-3.0, dy))
                    paper = theme.background
                    note.set_color(
                        paper if contrast_ratio(paper, col) >= contrast_ratio(theme.ink, col)
                        else theme.ink
                    )
                    # Printed on its own bar with a contrasting colour, as a matrix cell's
                    # value is: not text lost on data.
                    note._mintfig_heatmap_text = True  # type: ignore[attr-defined]
                flipped = note.get_window_extent(renderer)
                if flipped.x0 - 1 <= line_px <= flipped.x1 + 1 or flipped.x0 < frame.x0 - 1:
                    ctx.issues.append(
                        _issue(
                            "value_label_on_reference",
                            "warning",
                            f"The reference line runs through the value label "
                            f"{note.get_text()!r} on either side of its mark.",
                            "Move the reference to note= (\"dashed line: ...\"), or widen the "
                            'panel with a full-width row, layout=[["a"], ["b"]].',
                            panel=ctx.key,
                        )
                    )

        return _clear_reference

    return Panel(
        kind=kind,
        title=title,
        label=label,
        unit=unit,
        spec=spec,
        facts=facts,
        describe=describe,
        issues=list(issues or []),
        _height_mm=lambda w, measure, sizes, theme: (
            max(
                10.0 if sizes.compact else 14.0,
                _pitch(_wrapped(w, measure, sizes, theme), compact=sizes.compact) * n + 1.0,
            )
            + _extras()
        ),
        _min_height_mm=lambda w, measure, sizes, theme: (
            max(
                10.0 if sizes.compact else 12.0,
                _pitch(_wrapped(w, measure, sizes, theme), tight=True, compact=sizes.compact) * n
                + 1.0,
            )
            + _extras()
        ),
        _draw=_draw,
        measure_note=measure_note,
        color_items=tuple(nm for nm in names if nm not in muted_names),
        color_focus=tuple(highlight),
        color_mode="highlight" if highlight else "uniform",
        uses_default=not highlight,
        color_baseline=baseline,
    )


#: At most this many claimed differences are bracketed in one compare panel.
MAX_BRACKETS = 2


def _bracket_text(
    data: Mapping[str, float],
    a: str,
    b: str,
    how: str,
    ref: str | None,
    unit: str | None,
    fmt: str | None,
) -> str:
    """The bracket's number, in the terms the takeaway used: a ratio ("4.0×"), a relative
    change ("+46%", against ``ref``) or the difference (signed from ``ref`` when known)."""
    other = (b if ref == a else a) if ref else None
    if how == "ratio":
        num, den = (data[other], data[ref]) if ref and other else (max(data[a], data[b]), min(data[a], data[b]))
        return _ratio_text(abs(num / den))
    if how.startswith("relative:"):  # against the value the stated percent is relative to
        base = b if how.endswith(":b") else a
        text = _percent_change(data[base], data[a if base == b else b], precise=True)
        if text:
            return text
    diff = data[other] - data[ref] if ref and other else abs(data[a] - data[b])
    shown = _formatter([diff], fmt, unit=unit)(diff)
    return _delta_label(_signed(shown) if ref else _unsigned(shown), unit)


def _draw_brackets(
    ctx: _Ctx,
    ax: Axes,
    *,
    names: Sequence[str],
    values: Sequence[float],
    anchors: Sequence[float],
    labels: Sequence[str],
    weights: Sequence[str],
    highlight: Sequence[str],
    baseline: str | None,
    unit: str | None,
    fmt: str | None,
) -> None:
    """Bracket two marks whose difference the takeaway states ("costs 8 points").

    A takeaway number is drawn only when exactly one pair of items matches it (under the
    derivations ``claim_number_mismatch`` uses); at most :data:`MAX_BRACKETS`. The
    brackets sit right of the value labels, so they never cross text.
    """
    from matplotlib.lines import Line2D
    from matplotlib.markers import TICKLEFT
    from matplotlib.transforms import offset_copy

    from ..epistemic import claim_numbers, claimed_pairs

    if not ctx.takeaway or len(names) < 2:
        return
    data = dict(zip(names, values, strict=True))
    row = {nm: i for i, nm in enumerate(names)}
    # A takeaway that names two or more items says which ones it compares.
    named = {
        nm
        for nm in names
        if re.search(rf"(?<!\w){re.escape(nm)}(?!\w)", ctx.takeaway, re.IGNORECASE)
    }
    percent_unit = bool(unit) and str(unit).strip().startswith("%")
    chosen: list[tuple[int, int, str]] = []
    for claim in claim_numbers(ctx.takeaway, unit):
        pairs = [
            p
            for p in claimed_pairs(claim, data, percent_unit=percent_unit)
            if len(named) < 2 or {p[0], p[1]} <= named
        ]
        if len(pairs) != 1:
            continue  # nothing matches, or the match is ambiguous
        a, b, how = pairs[0]
        i, j = sorted((row[a], row[b]))
        if any((i, j) == (c[0], c[1]) for c in chosen):
            continue
        ref = baseline if baseline in (a, b) else None
        if ref is None and highlight and ((a in highlight) != (b in highlight)):
            ref = b if a in highlight else a  # "removing X costs 8": X against the other
        chosen.append((i, j, _bracket_text(data, a, b, how, ref, unit, fmt)))
        if len(chosen) == MAX_BRACKETS:
            break
    if not chosen:
        return

    sz, theme, measure = ctx.sizes, ctx.theme, ctx.measure
    tick, gap = 2.5 * sz.scale, 4.0 * sz.scale
    names_pt = max(
        measure.width_pt(line, sz.body, "bold") for nm in names for line in str(nm).split("\n")
    )
    cell_pt = ctx.cell_width_mm * sz.scale / PT_TO_MM
    while chosen:
        rows = sorted({k for i, j, _ in chosen for k in range(i, j + 1)})
        anchor = max(anchors[k] for k in rows)
        widest = max(measure.width_pt(labels[k], sz.small, weights[k]) for k in rows)
        base = 5.0 + widest + gap + tick
        placed: list[tuple[int, int, str, float, float]] = []
        # Inner (shorter) brackets first; one that shares a row goes right of the last label.
        for i, j, text in sorted(chosen, key=lambda c: (c[1] - c[0], c[0])):
            x = base
            for pi, pj, _t, px, pw in placed:
                if not (j < pi or i > pj):
                    x = max(x, px + tick + pw + gap + tick)
            placed.append((i, j, text, x, measure.width_pt(text, sz.small)))
        right = max(x + tick + w for *_, x, w in placed)
        # Keep names, a readable plot (16 mm) and the brackets inside the cell.
        if names_pt + 6.0 + 16.0 * sz.scale / PT_TO_MM + right <= cell_pt:
            break
        chosen = chosen[:-1]  # the claim stated last gives way first
    if not chosen:
        return
    lw = 0.8 * sz.scale
    for i, j, text, x, _w in placed:
        ax.add_line(
            Line2D(
                [anchor, anchor],
                [i, j],
                transform=offset_copy(ax.transData, fig=ctx.fig, x=x, y=0.0, units="points"),
                color=theme.muted,
                linewidth=lw,
                marker=TICKLEFT,
                markersize=tick,
                markeredgewidth=lw,
                clip_on=False,
                zorder=3,
                label="_bracket",
                gid="mintfig-margin-bracket",
            )
        )
        ax.annotate(
            _plain(text, theme),
            (anchor, 0.5 * (i + j)),
            xytext=(x + tick, 0.0),
            textcoords="offset points",
            ha="left",
            va="center",
            fontsize=sz.small,
            color=theme.ink,
            annotation_clip=False,
        )


def _sort_order(sort: object) -> str:
    """``True``/"desc" -> "desc", "asc" -> "asc", ``False``/None -> "given"."""
    if sort is True or (isinstance(sort, str) and sort.lower() in {"desc", "descending"}):
        return "desc"
    if isinstance(sort, str) and sort.lower() in {"asc", "ascending"}:
        return "asc"
    if sort is False or sort is None or (isinstance(sort, str) and sort.lower() == "none"):
        return "given"
    raise ExplainError(
        f"compare(sort={sort!r}) is not a sort order.",
        fix_hint='Use sort=True or "desc" (largest first), "asc" (smallest first, for '
        "lower-is-better measures such as loss or IC50), or False (keep the order given).",
    )


def _compare_intervals(
    error: object, data: dict[str, float], *, arg: str = "error"
) -> tuple[dict[str, tuple[float, float]], set[str]]:
    """Read ``compare(error=...)`` / ``inner_error=``: per item (low, high) or half-width, or one number."""
    names = list(data)
    hint = (
        "Give each item either (low, high) absolute bounds or one number meaning \N{PLUS-MINUS SIGN} "
        f'that much, e.g. {arg}={{"a": (2.8, 3.2), "b": 0.3}}, or {arg}=0.2 for every item.'
    )
    if _is_number(error):
        hw = _halfwidth(error, f"compare({arg})")
        return {nm: (data[nm] - hw, data[nm] + hw) for nm in names}, {"halfwidth"}
    if _has_items(error):
        entries = {str(k): v for k, v in _pairs(error)}
    elif isinstance(error, (Sequence, np.ndarray)) and not isinstance(error, (str, bytes)):
        listed = list(error)
        if len(listed) != len(names):
            raise ExplainError(
                f"compare({arg}) lists {len(listed)} intervals for {len(names)} items.",
                fix_hint=hint + " A list must follow the order of values.",
            )
        entries = dict(zip(names, listed, strict=True))
    else:
        raise ExplainError(
            f"compare({arg}) must be a mapping, a list or one number, got {type(error).__name__}.",
            fix_hint=hint,
        )
    extra = [k for k in entries if k not in data]
    if extra:
        raise ExplainError(
            f"compare({arg}) names {extra[:4]!r}, which are not in values.",
            fix_hint=f"Use names from: {', '.join(map(repr, names[:12]))}.",
        )
    errors: dict[str, tuple[float, float]] = {}
    modes: set[str] = set()
    for name in names:
        if name not in entries:
            raise ExplainError(
                f"compare({arg}) has no entry for {name!r}.",
                fix_hint=hint + f" Every item needs one, or omit `{arg}`.",
            )
        entry = entries[name]
        if _is_number(entry):
            hw = _halfwidth(entry, f"compare({arg}[{name!r}])")
            errors[name] = (data[name] - hw, data[name] + hw)
            modes.add("halfwidth")
            continue
        try:
            pair = [v for v in entry]  # type: ignore[union-attr]
        except TypeError as exc:
            raise ExplainError(
                f"compare({arg}[{name!r}]) = {entry!r} is neither (low, high) nor a number.",
                fix_hint=hint,
            ) from exc
        if len(pair) != 2:
            raise ExplainError(
                f"compare({arg}[{name!r}]) has {len(pair)} numbers; an interval has two.",
                fix_hint=hint,
            )
        low, high = (_to_float(v, f"compare({arg}[{name!r}])") for v in pair)
        if not (math.isfinite(low) and math.isfinite(high)):
            raise ExplainError(
                f"compare({arg}[{name!r}]) = ({low}, {high}) is not finite.",
                fix_hint=hint,
            )
        if not low <= data[name] <= high:
            raise ExplainError(
                f"compare({arg}[{name!r}]) = ({low}, {high}) does not bracket the value "
                f"{data[name]}.",
                fix_hint="Pass absolute (low, high) bounds, not +/- offsets; for a symmetric "
                "interval pass one number, the half-width.",
            )
        errors[name] = (low, high)
        modes.add("bounds")
    return errors, modes


def _ordinal(k: int) -> str:
    """1 -> "1st", 2 -> "2nd", 11 -> "11th"."""
    suffix = "th" if 10 <= k % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(k % 10, "th")
    return f"{k}{suffix}"


def _compare_counts(n: object, names: Sequence[str]) -> dict[str, int]:
    """Read ``compare(n=...)``: {name: count} (or a list in the order of values)."""
    hint = 'Give the number of observations behind each value, e.g. n={"Support": 84, "Legal": 61}.'
    if _has_items(n):
        entries = {str(k): v for k, v in _pairs(n)}
    elif isinstance(n, (Sequence, np.ndarray)) and not isinstance(n, (str, bytes)):
        listed = list(n)
        if len(listed) != len(names):
            raise ExplainError(
                f"compare(n) lists {len(listed)} counts for {len(names)} items.",
                fix_hint=hint + " A list must follow the order of values.",
            )
        entries = dict(zip(names, listed, strict=True))
    else:
        raise ExplainError(
            f"compare(n) must be a mapping or a list of counts, got {type(n).__name__}.",
            fix_hint=hint,
        )
    extra = [k for k in entries if k not in names]
    if extra:
        raise ExplainError(
            f"compare(n) names {extra[:4]!r}, which are not in values.",
            fix_hint=f"Use names from: {', '.join(map(repr, list(names)[:12]))}.",
        )
    counts: dict[str, int] = {}
    for name in names:
        if name not in entries or entries[name] is None:
            continue
        value = entries[name]
        number = _to_float(value, f"compare(n[{name!r}])") if _is_number(value) else math.nan
        if not (math.isfinite(number) and number >= 0 and float(number).is_integer()):
            raise ExplainError(
                f"compare(n[{name!r}]) = {value!r} is not a count.",
                fix_hint=hint + " Each count is a whole number, 0 or more.",
            )
        counts[name] = int(number)
    return counts


def _faceted(
    values: Any,
    *,
    name: str | None,
    group: str | None,
    value: str | None,
    facet: object,
    error: Any,
    unsupported: Mapping[str, bool],
    **options: Any,
) -> Panel:
    """``compare(facet=True)``: the nested form, or tidy rows with ``group=``, as small multiples."""
    from .._tabular import extract_records, is_tabular, resolve_grouped_compare_table
    from .compare_grouped import build_faceted_compare, is_nested_compare

    if facet is not True:
        raise ExplainError(
            f"compare(facet={facet!r}) must be True or False.",
            fix_hint="Pass facet=True with nested values {category: {item: value}} (or tidy rows "
            "with group=): each category becomes one small panel.",
        )
    blocked = [arg for arg, used in unsupported.items() if used]
    if blocked:
        raise ExplainError(
            f"compare(facet=True) cannot be combined with {', '.join(blocked)}: small multiples "
            "draw one value (and error=) per item and category.",
            fix_hint="Drop " + ", ".join(blocked) + ", or draw one single-series compare() per "
            "category to use them.",
        )
    if group is not None:
        nested = resolve_grouped_compare_table(values, name=name, group=group, value=value)
        if isinstance(error, (str, tuple, list)) and is_tabular(values):
            cols, rows = extract_records(values, what="compare(values)")
            picked = [error] if isinstance(error, str) else list(error)
            if not (1 <= len(picked) <= 2 and all(isinstance(c, str) and c in cols for c in picked)):
                raise ExplainError(
                    f"compare(error={error!r}) names no column of the rows.",
                    fix_hint=f"With tidy rows pass a half-width column (error=\"ci\") or (low, high) "
                    f"columns (error=(\"lo\", \"hi\")); columns: {', '.join(map(repr, cols[:8]))}.",
                )
            error = {}
            for row in rows:
                cell = [row.get(c) for c in picked]
                error.setdefault(str(row.get(name, "")), {})[str(row.get(group, ""))] = (
                    cell[0] if len(cell) == 1 else tuple(cell)
                )
    elif is_nested_compare(values):
        nested = values
    else:
        raise ExplainError(
            "compare(facet=True) needs nested values {category: {item: value}} (or tidy rows "
            "with name=, group= and value=); a flat {item: value} mapping has one panel's worth.",
            fix_hint='e.g. mint.compare({"bench A": {"model 1": 0.74, "model 2": 0.69}, '
            '"bench B": {...}}, facet=True), or drop facet=True.',
        )
    sort = options.pop("sort")
    return build_faceted_compare(
        nested, error=error, sort=sort if sort is not True else False, **options
    )


@_guarded("compare", aliases={"measure": "label"})
def compare(
    values: (
        Mapping[str, float]
        | Mapping[str, Mapping[str, float | None]]
        | Sequence[tuple[str, float]]
        | Sequence[Mapping[str, Any]]
    ),
    *,
    name: str | None = None,
    group: str | None = None,
    value: str | None = None,
    title: str | None = None,
    label: str | None = None,
    unit: str | None = None,
    highlight: str | Sequence[str] | None = None,
    baseline: str | None = None,
    sort: bool | str = True,
    zero: bool = True,
    error: Mapping[str, Any] | Sequence[Any] | float | str | None = None,
    error_label: str | None = None,
    inner_error: Mapping[str, Any] | Sequence[Any] | float | str | None = None,
    boost: Mapping[str, float] | str | None = None,
    boost_label: str | None = None,
    reference: float | tuple[float, str] | None = None,
    log: bool = False,
    fmt: str | None = None,
    n: Mapping[str, int] | Sequence[int] | str | None = None,
    show_delta: bool | str = "auto",
    facet: bool = False,
    legend: bool = False,
) -> Panel:
    """How do items differ in size? Sorted horizontal bars, grouped bars, or dot-interval marks.

    ``values`` maps item name to number (a dict, a pandas Series, or row-shaped
    records / DataFrame with ``name=`` and ``value=`` columns). Pass a nested
    mapping ``{category: {series: number}}`` (or tidy rows with ``group=``) for
    a grouped multi-series comparison (e.g. multiple benchmarks × models).
    Pass ``boost={name: extra}`` with ``boost_label=`` to stack a tinted
    non-negative extension on each bar (e.g. standard score + extended thinking).
    Bars start at zero; pass ``zero=False`` when zero is not meaningful (dot plot)
    or ``log=True`` for values spanning decades. ``error`` + ``error_label`` draw
    dot-and-interval marks; pass ``inner_error=`` alongside ``error=`` to draw a
    thicker inner interval (e.g. 50% CI inside 95% CI, Kay & Hullman ggdist).
    ``baseline`` draws a control/incumbent in ink and states gaps against it in
    ``facts``; pass ``show_delta=True`` with ``baseline=`` to append inline signed
    deltas beside each non-baseline value label. ``show_delta="auto"`` (default)
    brackets two items when a number in the takeaway is their difference (at most two
    brackets, none when the match is ambiguous); ``False`` draws neither.
    ``facet=True`` draws the nested form (or tidy rows with ``group=``) as small
    multiples instead of grouped bars: one panel per category (2-12), the same items
    in the same order in each, on one shared value axis; ``error=`` then takes one
    number or ``{category: {item: interval}}`` (a column name, or ``(low, high)``
    columns, with tidy rows).
    """
    from .._tabular import (
        extract_records,
        is_tabular,
        resolve_grouped_compare_table,
        resolve_named_table,
    )
    from .compare_grouped import build_grouped_compare, is_nested_compare

    if not isinstance(legend, bool):
        raise ExplainError(
            f"compare(legend={legend!r}) must be True or False.",
            fix_hint="Pass legend=True on grouped compare() for a frameless legend, or legend=False (default).",
        )
    if not (show_delta is True or show_delta is False or show_delta == "auto"):
        raise ExplainError(
            f"compare(show_delta={show_delta!r}) is not a delta mode.",
            fix_hint='Use show_delta="auto" (bracket a difference the takeaway states), True '
            "(inline deltas against baseline=) or False.",
        )
    if facet is not False and facet is not None:
        return _faceted(
            values,
            name=name,
            group=group,
            value=value,
            facet=facet,
            title=title,
            label=label,
            unit=unit,
            highlight=highlight,
            baseline=baseline,
            sort=sort,
            zero=zero,
            error=error,
            error_label=error_label,
            reference=reference,
            log=log,
            fmt=fmt,
            unsupported={
                "inner_error": inner_error is not None,
                "boost": boost is not None,
                "n": n is not None,
                "show_delta=True": show_delta is True,
            },
        )
    if group is not None:
        if boost is not None or inner_error is not None or show_delta is True:
            raise ExplainError(
                "Grouped compare(group=...) cannot be combined with inner_error=, boost=, or show_delta=True.",
                fix_hint="Use separate compare() panels for boosts/inner intervals/inline deltas, or drop group=.",
            )
        nested = resolve_grouped_compare_table(values, name=name, group=group, value=value)
        resolved_err: Any = error
        resolved_n: Any = n
        if is_tabular(values) and (error is not None or n is not None):
            cols, rows = extract_records(values, what="compare(values)")
            name_col = name or (cols[0] if cols else "")
            if isinstance(error, (str, tuple, list)):
                picked = [error] if isinstance(error, str) else list(error)
                if 1 <= len(picked) <= 2 and all(isinstance(c, str) and c in cols for c in picked):
                    err_map: dict[str, dict[str, Any]] = {}
                    for row in rows:
                        cell = [row.get(c) for c in picked]
                        err_map.setdefault(str(row.get(name_col, "")), {})[
                            str(row.get(group, ""))
                        ] = cell[0] if len(cell) == 1 else tuple(cell)
                    resolved_err = err_map
            if isinstance(n, str) and n in cols:
                n_map: dict[str, dict[str, Any]] = {}
                for row in rows:
                    n_map.setdefault(str(row.get(name_col, "")), {})[
                        str(row.get(group, ""))
                    ] = row.get(n)
                resolved_n = n_map
        return build_grouped_compare(
            nested,
            title=title,
            label=label,
            unit=unit,
            highlight=highlight,
            baseline=baseline,
            sort=sort if sort is not True else False,
            zero=zero,
            error=resolved_err,
            error_label=error_label,
            n=resolved_n,
            reference=reference,
            log=log,
            fmt=fmt,
            legend=legend,
        )

    if is_nested_compare(values):
        if boost is not None or inner_error is not None or show_delta is True:
            raise ExplainError(
                "Grouped compare() with nested dicts cannot be combined with inner_error=, boost=, or show_delta=True.",
                fix_hint="Use single-series compare() for boosts/inner intervals/inline deltas, or drop inner_error=/boost=/show_delta=True.",
            )
        return build_grouped_compare(
            values,  # type: ignore[arg-type]
            title=title,
            label=label,
            unit=unit,
            highlight=highlight,
            baseline=baseline,
            sort=sort if sort is not True else False,
            zero=zero,
            error=error,
            error_label=error_label,
            n=n,
            reference=reference,
            log=log,
            fmt=fmt,
            legend=legend,
        )

    raw_values_obj = values
    tabular = resolve_named_table(
        values,
        "compare(values)",
        name=name,
        value=value,
        error=error,
        n=n,
        boost=boost,
        form="compare",
    )
    if tabular is not None:
        if inner_error is not None and is_tabular(raw_values_obj):
            t_cols, t_rows = extract_records(raw_values_obj, what="compare(values)")
            name_col = name or (t_cols[0] if t_cols else "")
            if isinstance(inner_error, str) and inner_error in t_cols:
                inner_error = {str(r.get(name_col, "")): r.get(inner_error) for r in t_rows}
            elif (
                isinstance(inner_error, (tuple, list))
                and len(inner_error) == 2
                and all(isinstance(c, str) and c in t_cols for c in inner_error)
            ):
                lo_c, hi_c = str(inner_error[0]), str(inner_error[1])
                inner_error = {
                    str(r.get(name_col, "")): (r.get(lo_c), r.get(hi_c)) for r in t_rows
                }
        values, error, n, boost = tabular
    data = _named_values(values, "compare(values)")
    names = list(data)
    order = _sort_order(sort)
    if len(names) > MAX_COMPARE_ITEMS:
        if not _is_strict():
            keep_req: list[str] = []
            if highlight is not None:
                req_hl = [highlight] if isinstance(highlight, str) else [str(h) for h in highlight]
                keep_req.extend(nm for nm in req_hl if nm in data)
            if baseline is not None and str(baseline) in data:
                keep_req.append(str(baseline))
            ranked_all = sorted(
                names, key=lambda nm: data[nm], reverse=(order != "asc")
            )
            chosen: list[str] = list(dict.fromkeys(keep_req))
            for nm in ranked_all:
                if len(chosen) >= MAX_COMPARE_ITEMS:
                    break
                if nm not in chosen:
                    chosen.append(nm)
            chosen_set = set(chosen)
            data = {nm: data[nm] for nm in names if nm in chosen_set}
            _record_adjustment(f"compare(): trimmed {len(names)} items to top {len(data)}")
            names = list(data)
        else:
            raise ExplainError(
                f"compare() got {len(names)} items; a ranked list longer than "
                f"{MAX_COMPARE_ITEMS} is scanned, not read.",
                fix_hint=f"compare() takes at most {MAX_COMPARE_ITEMS} items: show the top 10 (say "
                "so in the title, the rest in note=), use distribution() for the spread of many "
                "values, or matrix() if the items form a grid.",
                rule="too_many_items",
            )
    hl = _names(highlight, names)
    base = _baseline_name(baseline, names, hl, "compare")
    ref = _reference_line(reference, "compare(reference)")
    errors: dict[str, tuple[float, float]] | None = None
    modes: set[str] = set()
    if error is not None:
        errors, modes = _compare_intervals(error, data)
    inner_errors: dict[str, tuple[float, float]] | None = None
    if inner_error is not None:
        if errors is None:
            raise ExplainError(
                "compare(inner_error=...) requires error= for the outer interval.",
                fix_hint="Pass both error= (outer interval, e.g. 95% CI) and inner_error= (inner interval, e.g. 50% CI).",
            )
        inner_errors, _inner_modes = _compare_intervals(inner_error, data, arg="inner_error")
        for nm in names:
            out_lo, out_hi = errors[nm]
            in_lo, in_hi = inner_errors[nm]
            tol = 1e-9 * max(1.0, abs(out_lo), abs(out_hi))
            if in_lo < out_lo - tol or in_hi > out_hi + tol:
                raise ExplainError(
                    f"compare(inner_error[{nm!r}]) = ({in_lo}, {in_hi}) extends outside "
                    f"outer error ({out_lo}, {out_hi}).",
                    fix_hint="Ensure inner_error bounds lie within error bounds (e.g. 50% CI inside 95% CI).",
                )
    if show_delta is True:
        if base is None:
            raise ExplainError(
                "compare(show_delta=True) requires baseline= to compute inline deltas against.",
                fix_hint='Pass baseline="<item>" alongside show_delta=True.',
            )
        if boost is not None:
            raise ExplainError(
                "compare(show_delta=True) cannot be combined with boost=.",
                fix_hint="Drop either show_delta=True or boost= so value labels stay unambiguous.",
            )
    counts = _compare_counts(n, names) if n is not None else {}
    boost_map: dict[str, float] | None = None
    if boost is not None:
        if not zero or log or errors is not None:
            raise ExplainError(
                "compare(boost=...) draws stacked bar extensions and requires zero=True, log=False, and no error=.",
                fix_hint="Remove zero=False / log=True / error= when using boost=.",
            )
        if min(data.values()) < 0:
            raise ExplainError(
                "compare(boost=...) requires non-negative base values.",
                fix_hint="Use compare() without boost= for signed/diverging values.",
            )
        raw_boost = _named_values(boost, "compare(boost)", allow_nan=True)
        extra_b = [k for k in raw_boost if k not in data]
        if extra_b:
            raise ExplainError(
                f"compare(boost) names {extra_b[:4]!r}, which are not in values.",
                fix_hint=f"Use names from: {', '.join(map(repr, names[:12]))}.",
            )
        boost_map = {}
        for nm in names:
            bv = raw_boost.get(nm, 0.0)
            if not math.isfinite(bv):
                bv = 0.0
            if bv < 0:
                raise ExplainError(
                    f"compare(boost[{nm!r}]) = {bv!r} must be >= 0.",
                    fix_hint="boost= adds a non-negative extension to each bar; pass 0 for items with no boost.",
                )
            boost_map[nm] = float(bv)
    if log:
        lows = [errors[nm][0] for nm in names] if errors else []
        if min([*data.values(), *lows, *([ref[0]] if ref else [])]) <= 0:
            raise ExplainError(
                "compare(log=True) needs strictly positive values (and interval bounds and "
                "reference).",
                fix_hint="Drop log=True, or remove the non-positive items and say so in note=.",
            )

    issues: list[dict[str, Any]] = []
    if len(names) > COMFORTABLE_COMPARE_ITEMS:
        issues.append(
            _issue(
                "many_items",
                "warning",
                f"{len(names)} items is a long list for one glance.",
                "Show the top 10 (say so in the title) and pass the rest as a sentence in note=.",
            )
        )
    if zero and not log and errors is None and min(data.values()) > 0:
        lo, hi = min(data.values()), max(data.values())
        if hi > 0 and (hi - lo) / hi < 0.1 and len(names) > 1:
            issues.append(
                _issue(
                    "differences_invisible",
                    "warning",
                    f"All values lie within {100 * (hi - lo) / hi:.0f}% of each other, so "
                    "zero-based bars will look identical.",
                    "If the small differences are the point, pass zero=False (dot plot) and "
                    "say in the title that the differences are small.",
                )
            )
    if errors is not None and not error_label:
        issues.append(_interval_issue("compare", "error", "error_label"))
    if boost_map is not None and not boost_label:
        issues.append(
            _issue(
                "boost_unlabelled",
                "warning",
                "compare(boost=...) draws a tinted bar extension without saying what it represents.",
                'Pass boost_label=, e.g. boost_label="Extended thinking".',
            )
        )

    eff_data = (
        {nm: data[nm] + boost_map[nm] for nm in names} if boost_map is not None else data
    )
    if order == "desc":
        names = sorted(names, key=lambda nm: eff_data[nm], reverse=True)
    elif order == "asc":
        names = sorted(names, key=lambda nm: eff_data[nm])
    vals = [data[nm] for nm in names]
    boost_vals = [boost_map[nm] for nm in names] if boost_map is not None else None
    totals = [eff_data[nm] for nm in names]
    fmt_fn = _formatter([*vals, *totals], fmt, unit=unit, log=log)
    if boost_vals is not None:
        pos_boosts = [b for b in boost_vals if b > 0]
        b_fmt = _formatter(pos_boosts or [0.0], fmt, unit=unit)
        labels = []
        for i, (tot_v, b_v) in enumerate(zip(totals, boost_vals, strict=True)):
            t_txt = _with_unit(fmt_fn(tot_v), unit) if (i == 0 or _inline_unit(unit)) else fmt_fn(tot_v)
            labels.append(f"{t_txt} (+{b_fmt(b_v)})" if b_v > 0 else t_txt)
    elif show_delta is True and base is not None:
        deltas = [data[nm] - data[base] for nm in names if nm != base]
        d_fmt = _formatter(deltas or [0.0], fmt, unit=unit)
        labels = []
        for i, (nm, v) in enumerate(zip(names, vals, strict=True)):
            base_txt = _with_unit(fmt_fn(v), unit) if (i == 0 or _inline_unit(unit)) else fmt_fn(v)
            if nm != base:
                delta = _delta_label(_signed(d_fmt(v - data[base])), unit, with_unit=False)
                labels.append(f"{base_txt} ({delta})")
            else:
                labels.append(base_txt)
    else:
        labels = [
            _with_unit(fmt_fn(v), unit) if (i == 0 or _inline_unit(unit)) else fmt_fn(v)
            for i, v in enumerate(vals)
        ]

    # Values of both signs (changes, differences): positives carry a "+", and the
    # highlighted items are placed against zero, not against their neighbours.
    diverging = min(data.values()) < 0 < max(data.values())
    # zero=False says zero is not meaningful (wavelengths, temperatures, positions):
    # ratios of the values mean nothing there; differences still do. A log axis keeps them.
    ratios = zero or log

    def _u(v: float, f: Callable[[float], str] = fmt_fn) -> str:
        text = f(v)
        return _with_unit(_signed(text) if diverging else text, unit)

    def _nn(name: str) -> str:
        return f" (n={counts[name]})" if name in counts else ""

    descending = sorted(data, key=lambda nm: data[nm], reverse=True)
    ranking = names if order != "given" else descending
    rank_word = "lowest first" if order == "asc" else "highest first"
    top, bottom = descending[0], descending[-1]
    facts = [f"highest: {top} {_u(data[top])}{_nn(top)}"]
    if len(descending) > 1:
        facts.append(f"lowest: {bottom} {_u(data[bottom])}{_nn(bottom)}")
        if ratios and all(v > 0 for v in data.values()):
            facts.append(
                f"highest/lowest ratio: {_ratio_text(data[top] / data[bottom])} "
                "(from unrounded values)"
            )
        else:
            span_fmt = _formatter([data[top] - data[bottom]], fmt, unit=unit)
            # A spread is a width: no sign (even from a signed fmt), in points for "%".
            spread = _diff_with_unit(_unsigned(span_fmt(data[top] - data[bottom])), unit)
            facts.append(f"range: {_u(data[bottom])} to {_u(data[top])} (spread {spread})")
    if ratios and not diverging and len(descending) > 2:
        second = descending[1]
        if data[second] > 0 and data[top] > 0 and data[top] / data[second] >= 1.1:
            facts.append(
                f"{top} is {_ratio_text(data[top] / data[second])} the next highest "
                f"({second} {_u(data[second])})"
            )
    diffs: list[tuple[str, float, str, float]] = []
    for item in hl:
        if ref is not None:
            diffs.append((item, data[item] - ref[0], ref[1] or "reference", ref[0]))
        elif base is None and not diverging:
            # With a baseline every item is stated against it below; with values of both
            # signs each highlighted item is placed against zero instead.
            others = [nm for nm in ranking if nm not in hl]
            if others:
                diffs.append((item, data[item] - data[others[0]], others[0], data[others[0]]))
    diff_fmt = _formatter([d[1] for d in diffs], fmt, unit=unit)

    if errors is not None:
        bound_fmt = _formatter(
            # On a log axis the bounds share the values' notation.
            [*(vals if log else []), *(v for pair in errors.values() for v in pair)],
            fmt,
            unit=unit,
            log=log,
        )

    def _span(nm: str) -> str:
        lo_v, hi_v = errors[nm]  # type: ignore[index]
        return _range_with_unit(bound_fmt(lo_v), bound_fmt(hi_v), unit)

    ref_shown = ref_named = ""
    if ref is not None:
        # The reference as the caller gave it ("1×", not "1.00×" from the values' digits).
        ref_shown = _with_unit(_formatter([ref[0]], log=log)(ref[0]), unit)
        ref_named = f" ({ref[1]})" if ref[1] else ""

    def _vs_reference(nm: str) -> str:
        """Where an interval lies against the reference: "above", "below" or "includes"."""
        lo_v, hi_v = errors[nm]  # type: ignore[index]
        return "above" if lo_v > ref[0] else "below" if hi_v < ref[0] else "includes"  # type: ignore[index]

    below_zero = [nm for nm in reversed(descending) if data[nm] < 0]  # most negative first
    above_zero = [nm for nm in descending if data[nm] > 0]

    def _against_zero(nm: str) -> str:
        """"furthest of the 3 below zero", "2nd furthest of the 9 above zero"."""
        if data[nm] == 0:
            return "at zero"
        group, word = (below_zero, "below") if data[nm] < 0 else (above_zero, "above")
        if len(group) == 1:
            return f"the only one {word} zero"
        k = group.index(nm) + 1
        far = "furthest" if k == 1 else f"{_ordinal(k)} furthest"
        return f"{far} of the {len(group)} {word} zero"

    ci_name = error_label if error_label and len(error_label) <= 24 else "interval"
    # Alt text: the extremes, then each highlighted item (or each item against the baseline).
    alt_facts = [f for f in facts if f.startswith(("highest: ", "lowest: "))]
    for item in hl:
        detail = f"n={counts[item]}; " if item in counts else ""
        text = (
            f"{item}: {_u(data[item])} ({detail}rank {ranking.index(item) + 1} of "
            f"{len(ranking)}, {rank_word})"
        )
        for d_name, d_value, other, other_value in diffs:
            if d_name != item:
                continue
            if log:
                if errors is not None and ref is not None and ref[0] == 1:
                    continue  # the value is already its ratio to 1: the interval says more
                # On a log axis items differ by factors: a ratio, never a signed one
                # ("6.0× no change", "0.39× no change"), not "+6.02× vs no change".
                text += f"; {_ratio_text(data[item] / other_value)} {other} ({_u(other_value)})"
            else:
                text += (
                    f"; {_diff_with_unit(_signed(diff_fmt(d_value)), unit)} vs {other} "
                    f"({_u(other_value)})"
                )
        if diverging and ref is None and base is None:
            text += f"; {_against_zero(item)}"
        if errors is not None and ref is not None:
            side = _vs_reference(item)
            where = (
                f"includes {ref_shown}{ref_named}"
                if side == "includes"
                else f"{side} {ref_shown}{ref_named}"
            )
            text += f"; {ci_name} {_span(item)}, {where}"
        facts.append(text)
        if base is None:
            alt_facts.append(text)
    if diverging and hl:
        rest = [nm for nm in ranking if nm not in hl and nm != base]
        if rest:
            lo_nm = min(rest, key=lambda nm: data[nm])
            hi_nm = max(rest, key=lambda nm: data[nm])
            if len(rest) == 1:
                facts.append(f"the other item, {lo_nm}, is {_u(data[lo_nm])}")
            else:
                facts.append(
                    f"the other {len(rest)} are within {_u(data[lo_nm])} to {_u(data[hi_nm])}"
                )
    if base is not None:
        compared = (hl or [nm for nm in ranking if nm != base])[:6]
        vs_fmt = _formatter([data[nm] - data[base] for nm in compared], fmt, unit=unit)
        for item in compared:
            if log:
                facts.append(
                    f"{item} is {_vs_text(data[item], data[base], unit=unit, diff_fmt=vs_fmt, log=True)} "
                    f"{base} ({_u(data[item])} vs {_u(data[base])})"
                )
            else:
                facts.append(
                    f"{item} {_u(data[item])} vs {base} {_u(data[base])}: "
                    f"{_vs_text(data[item], data[base], unit=unit, diff_fmt=vs_fmt, relative=ratios)}"
                )
            alt_facts.append(facts[-1])
    if errors is not None:
        pairs: list[tuple[str, str]] = []
        if base is not None:
            pairs = [(nm, base) for nm in (hl or [nm for nm in ranking if nm != base])[:6]]
        elif hl and ref is None:
            # Each highlighted interval against every other item's: which overlap it and
            # which do not ("outlier, or the bottom of a spread?").
            for a in hl:
                a_lo, a_hi = errors[a]
                others = [nm for nm in ranking if nm != a]
                over = [nm for nm in others if errors[nm][0] <= a_hi and a_lo <= errors[nm][1]]
                apart = [nm for nm in others if nm not in over]
                listed = [
                    f"overlaps {_and_list([f'{nm} {_span(nm)}' for nm in over])}" if over else "",
                    f"does not overlap {_or_list([f'{nm} {_span(nm)}' for nm in apart])}"
                    if apart
                    else "",
                ]
                facts.append(f"{a} {_span(a)} " + "; ".join(t for t in listed if t))
        elif len(ranking) > 1 and ref is None:
            pairs = [(ranking[1], ranking[0])]
        for a, b in pairs:
            (a_lo, a_hi), (b_lo, b_hi) = errors[a], errors[b]
            verb = "overlaps" if (a_lo <= b_hi and b_lo <= a_hi) else "does not overlap"
            facts.append(f"{a} {_span(a)} {verb} {b} {_span(b)}")
        if ref is not None:
            # Every interval against the reference, not against the first item.
            sides: dict[str, list[str]] = {"above": [], "includes": [], "below": []}
            for nm in ranking:
                sides[_vs_reference(nm)].append(nm)
            parts = [
                f"{phrase} for {_and_list(sides[key])}"
                for key, phrase in (
                    ("above", "entirely above"),
                    ("includes", "include it"),
                    ("below", "entirely below"),
                )
                if sides[key]
            ]
            facts.append(f"intervals against {ref_shown}{ref_named}: " + "; ".join(parts))
        facts.append(_interval_mode_text(modes, "intervals"))

    what = label or "values"
    describe = (
        f"{'Dot plot' if (not zero or errors or log) else 'Bar chart'} of {what} for {len(names)} items"
        + (f", in {unit}" if unit else "")
        + (" on a log scale" if log else "")
        + (f", with intervals ({error_label})" if errors and error_label else "")
        + (" and nested inner interval" if inner_errors is not None else "")
    )
    notes = [
        nt
        for nt in (
            "log scale" if log else None,
            f"intervals: {error_label}" if errors and error_label else None,
            "thick bar: inner interval" if inner_errors is not None else None,
        )
        if nt
    ]
    if boost_map is not None:
        b_label_txt = boost_label or "boost"
        notes.append(f"tinted extension: {b_label_txt}")
        best_tot = max(names, key=lambda nm: eff_data[nm])
        best_gain = max(names, key=lambda nm: boost_map[nm])
        facts.append(
            f"with {b_label_txt}: highest total {best_tot} {_u(eff_data[best_tot])} "
            f"(base {_u(data[best_tot])} + {fmt_fn(boost_map[best_tot])})"
        )
        if boost_map[best_gain] > 0:
            facts.append(
                f"largest {b_label_txt} gain: {best_gain} (+{_diff_with_unit(fmt_fn(boost_map[best_gain]), unit)})"
            )
    panel = _bar_panel(
        kind="compare",
        names=names,
        values=vals,
        highlight=hl,
        labels=labels,
        title=title,
        label=label,
        unit=unit,
        spec=_base_spec(
            title,
            label,
            unit,
            values={nm: data[nm] for nm in data},
            highlight=hl or None,
            baseline=base,
            sort=sort,
            zero=zero,
            error=_jsonable(error) if errors else None,
            error_label=error_label,
            inner_error=_jsonable(inner_error) if inner_errors is not None else None,
            boost={nm: boost_map[nm] for nm in data} if boost_map is not None else None,
            boost_label=boost_label,
            reference=list(ref) if ref else None,
            log=log or None,
            fmt=fmt,
            n=dict(counts) or None,
            show_delta=None if show_delta == "auto" else show_delta,
        ),
        facts=facts,
        describe=describe,
        dots=(not zero) or errors is not None or log,
        errors=errors,
        inner_errors=inner_errors,
        reference=ref,
        issues=issues,
        log=log,
        measure_note="; ".join(notes) or None,
        baseline=base,
        counts=counts,
        boosts=boost_vals,
        auto_delta=show_delta == "auto",
        fmt=fmt,
    )
    panel.alt_facts = alt_facts
    return panel


MAX_PIE_PARTS = 5


def _pie_panel(
    *,
    donut: bool,
    names: list[str],
    values: list[float],
    highlight: list[str],
    labels: list[str],
    total: float,
    total_text: str,
    title: str | None,
    label: str | None,
    unit: str | None,
    spec: dict[str, Any],
    facts: list[str],
    describe: str,
    muted_names: Sequence[str] = (),
    issues: list[dict[str, Any]] | None = None,
) -> Panel:
    """Opt-in pie or donut panel for ``share(kind='pie' | 'donut')`` (at most 5 parts)."""
    inner_r = 0.60 if donut else 0.0
    ring_w = (1.0 - inner_r) if donut else None
    non_muted = [nm for nm in names if nm not in muted_names]

    def _draw(ctx: _Ctx, ax: Axes) -> Callable[[], None]:
        sz = ctx.sizes
        theme = ctx.theme
        accent = {nm: col for nm, col in ctx.colors.items() if nm in names}
        emphasis = set(highlight)

        def _slice_color(nm: str) -> str:
            if nm in muted_names:
                return theme.context_fill
            if highlight:
                return accent.get(nm, theme.context_fill)
            return ctx.colors.get(nm, theme.context_fill)

        colors = [_slice_color(nm) for nm in names]
        _bare_axes(ax)
        ax.xaxis.set_visible(False)
        ax.yaxis.set_visible(False)
        ax.set_aspect("auto")
        ax.set_ylim(-1.30, 1.30)
        ax.set_xlim(-2.20, 2.20)

        val_sum = sum(values) or 1.0
        angle = 90.0
        slices: list[tuple[str, float, str, float, str]] = []
        wedges: list[Any] = []
        records: list[dict[str, Any]] = []
        for nm, pct_v, pct_lbl, col in zip(names, values, labels, colors, strict=True):
            sweep = 360.0 * pct_v / val_sum
            t2 = angle
            t1 = angle - sweep
            mid = 0.5 * (t1 + t2)
            angle = t1
            if sweep > 0:
                wedge = Wedge(
                    (0.0, 0.0),
                    1.0,
                    t1,
                    t2,
                    width=ring_w,
                    facecolor=col,
                    edgecolor=theme.background,
                    linewidth=1.2 * sz.scale,
                    zorder=2,
                )
                ax.add_patch(wedge)
                wedges.append(wedge)
                records.append({"name": nm, "value": pct_v, "unit": "%"})
            slices.append((nm, pct_v, pct_lbl, mid, col))
        tag_each(ctx, wedges, records)

        def _format_slice_label(nm: str, pct_lbl: str, max_pt: float, weight: str) -> str:
            single = f"{nm}  {pct_lbl}"
            if ctx.measure.width_pt(single, sz.small, weight) <= max_pt:
                return single
            wrapped = ctx.measure.wrap(nm, max_pt, sz.small, weight)
            if len(wrapped) == 1:
                return f"{wrapped[0]}\n{pct_lbl}"
            head = wrapped[0]
            tail = " ".join(wrapped[1:])
            ell = theme.ellipsis
            while (
                len(tail) > 4
                and ctx.measure.width_pt(f"{tail}  {pct_lbl}", sz.small, weight) > max_pt
            ):
                tail = tail[:-2].rstrip() + ell if len(ell) == 1 else tail.removesuffix(ell)[:-1].rstrip() + ell
            return f"{head}\n{tail}  {pct_lbl}"

        def _finish() -> None:
            renderer = ctx.fig.canvas.get_renderer()
            box = ax.get_window_extent(renderer)
            k = ctx.pt_per_px
            w_px, h_px = float(box.width), float(box.height)
            if w_px <= 1.0 or h_px <= 1.0:
                return
            w_pt = w_px * k
            max_label_pt = max(44.0, 0.28 * w_pt)

            # Split slices into right (cos >= 0) and left (cos < 0) label columns.
            sides: dict[str, list[tuple[str, str, float, str, str, str]]] = {"right": [], "left": []}
            for nm, _pct_v, pct_lbl, mid_deg, col in slices:
                rad = math.radians(mid_deg)
                side = "right" if math.cos(rad) >= -1e-6 else "left"
                is_emph = nm in emphasis
                is_muted = nm in muted_names or (bool(highlight) and nm not in accent)
                weight = "bold" if is_emph else "normal"
                tcol = theme.muted if is_muted else ctx.text_color(col)
                text = _format_slice_label(nm, pct_lbl, max_label_pt, weight)
                sides[side].append((nm, text, rad, col, weight, tcol))

            widest_pt = max(
                (
                    max(ctx.measure.width_pt(line, sz.small, wt) for line in txt.splitlines())
                    for items in sides.values()
                    for _, txt, _, _, wt, _ in items
                ),
                default=0.0,
            )
            max_side_px = widest_pt / k
            r_px_max_h = h_px / 2.35
            r_px_max_w = max(18.0 / k, (w_px / 2.0 - max_side_px - 8.0) / 1.24)
            r_px = min(r_px_max_h, r_px_max_w)
            half_y = h_px / (2.0 * r_px)
            half_x = w_px / (2.0 * r_px)
            ax.set_ylim(-half_y, half_y)
            ax.set_xlim(-half_x, half_x)

            cy_px = 0.5 * (float(box.y0) + float(box.y1))
            y_lo_pt = float(box.y0) * k + sz.small * 0.8
            y_hi_pt = float(box.y1) * k - sz.small * 0.8

            for side, items in sides.items():
                if not items:
                    continue
                sign = 1.0 if side == "right" else -1.0
                ha = "left" if side == "right" else "right"
                ys_nat = np.array(
                    [cy_px * k + (1.12 * math.sin(rad)) * r_px * k for _, _, rad, _, _, _ in items],
                    dtype=float,
                )
                max_lines = max(txt.count("\n") + 1 for _, txt, _, _, _, _ in items)
                min_gap = (max_lines * sz.small * 1.25) + 3.0
                placed = _relax_positions_pt(ys_nat, min_gap, y_lo_pt, y_hi_pt)
                x_text = sign * 1.22
                x_end = sign * 1.17
                for (_nm, txt, rad, col, weight, tcol), y_pt in zip(items, placed, strict=True):
                    y_data = (float(y_pt) / k - cy_px) / r_px
                    p0 = (1.02 * math.cos(rad), 1.02 * math.sin(rad))
                    elbow_x = 1.11 * math.cos(rad)
                    if sign * elbow_x < 1.04:
                        elbow_x = sign * 1.11
                    elif sign * elbow_x > 1.14:
                        elbow_x = sign * 1.14
                    p1 = (elbow_x, y_data)
                    p2 = (x_end, y_data)
                    leader = PathPatch(
                        MplPath([p0, p1, p2], [MplPath.MOVETO, MplPath.LINETO, MplPath.LINETO]),
                        facecolor="none",
                        edgecolor=theme.axis if col == theme.context_fill else col,
                        linewidth=0.75 * sz.scale,
                        alpha=0.75,
                        zorder=3,
                    )
                    ax.add_patch(leader)
                    ax.text(
                        x_text,
                        y_data,
                        _plain(txt, theme),
                        ha=ha,
                        va="center",
                        fontsize=sz.small,
                        fontweight=weight,
                        color=tcol,
                        linespacing=1.1,
                        zorder=5,
                    )

            if donut:
                hole_pt = 2.0 * inner_r * r_px * k
                max_center_pt = 0.84 * hole_pt
                if unit is not None or abs(total - 100.0) > 1e-6:
                    main_txt = total_text
                    sub_txt = "total"
                    main_col = theme.ink
                elif len(highlight) == 1:
                    h_name = highlight[0]
                    main_txt = labels[names.index(h_name)]
                    sub_txt = h_name
                    main_col = ctx.text_color(accent.get(h_name, theme.ink))
                else:
                    main_txt = labels[0]
                    sub_txt = names[0]
                    main_col = theme.ink

                ell = theme.ellipsis
                while (
                    len(sub_txt) > 3
                    and ctx.measure.width_pt(sub_txt, sz.small, "normal") > max_center_pt
                ):
                    sub_txt = (
                        sub_txt[:-2].rstrip() + ell
                        if len(ell) == 1
                        else sub_txt.removesuffix(ell)[:-1].rstrip() + ell
                    )
                main_size = sz.body if ctx.measure.width_pt(main_txt, sz.body, "bold") <= max_center_pt else sz.small
                if hole_pt >= (main_size + sz.small) * 1.55 and sub_txt:
                    ax.annotate(
                        _plain(main_txt, theme),
                        (0.0, 0.0),
                        xytext=(0.0, 2.0),
                        textcoords="offset points",
                        ha="center",
                        va="bottom",
                        fontsize=main_size,
                        fontweight="bold",
                        color=main_col,
                        zorder=5,
                    )
                    ax.annotate(
                        _plain(sub_txt, theme),
                        (0.0, 0.0),
                        xytext=(0.0, -2.0),
                        textcoords="offset points",
                        ha="center",
                        va="top",
                        fontsize=sz.small,
                        color=theme.muted,
                        zorder=5,
                    )
                elif hole_pt >= main_size * 1.4:
                    ax.text(
                        0.0,
                        0.0,
                        _plain(main_txt, theme),
                        ha="center",
                        va="center",
                        fontsize=main_size,
                        fontweight="bold",
                        color=main_col,
                        zorder=5,
                    )

        return _finish

    return Panel(
        kind="share",
        title=title,
        label=label,
        unit=None,
        spec=spec,
        facts=facts,
        describe=describe,
        issues=list(issues or []),
        _height_mm=lambda w, _m, sz, _t: (
            44.0 if sz.compact else min(60.0, max(48.0, 0.42 * w))
        ),
        _min_height_mm=lambda _w, _m, _sz, _t: 42.0,
        _draw=_draw,
        color_items=tuple(non_muted),
        color_focus=tuple(highlight) if highlight else tuple(non_muted[:4]),
        color_mode="highlight" if highlight else "series",
        uses_default=False,
    )


@_guarded("share", aliases={"share_kind": "kind", "measure": "label"})
def share(
    parts: Mapping[str, float] | Sequence[tuple[str, float]] | Sequence[Mapping[str, Any]],
    *,
    name: str | None = None,
    value: str | None = None,
    title: str | None = None,
    label: str | None = None,
    unit: str | None = None,
    highlight: str | Sequence[str] | None = None,
    top: int = 7,
    fmt: str | None = None,
    kind: str = "bars",
) -> Panel:
    """What makes up the total? Sorted horizontal bars by default; opt-in pie or donut.

    Parts beyond the ``top`` largest are folded into one muted "Other" item.
    ``label`` and ``unit`` describe the total, which is stated above the panel.
    Pass ``kind="pie"`` or ``kind="donut"`` for a part-of-whole ring/pie (at most
    5 parts; use ``top=4`` to fold the rest into Other). Accepts dicts, Series,
    or row-shaped data with ``name=`` and ``value=``.
    """
    from .._tabular import resolve_named_table

    share_kind = kind.strip().lower() if isinstance(kind, str) else None
    if share_kind not in {"bars", "pie", "donut"}:
        raise ExplainError(
            f"share(kind={kind!r}) must be 'bars', 'pie', or 'donut'.",
            fix_hint="Use kind='bars' (default), kind='pie', or kind='donut'.",
        )

    tabular = resolve_named_table(
        parts,
        "share(parts)",
        name=name,
        value=value,
        form="share",
    )
    if tabular is not None:
        parts = tabular[0]
    data = _named_values(parts, "share(parts)")
    if min(data.values()) < 0:
        raise ExplainError(
            "share() needs non-negative parts; a negative part has no share of a total.",
            fix_hint="Use compare() for signed values.",
        )
    total = sum(data.values())
    if total <= 0:
        raise ExplainError("share() parts sum to zero.", fix_hint="Pass positive parts.")
    if top < 2:
        raise ExplainError("share(top) must be at least 2.", fix_hint="Use top=5 or similar.")
    ranked = sorted(data, key=lambda nm: data[nm], reverse=True)
    kept = ranked if len(ranked) <= top + 1 else ranked[:top]
    rest = [nm for nm in ranked if nm not in kept]
    other_name = f"Other ({len(rest)})"
    if highlight is not None and rest:
        req = [highlight] if isinstance(highlight, str) else [str(h) for h in highlight]
        folded = [nm for nm in req if nm in rest]
        if folded:
            needed = max(ranked.index(nm) + 1 for nm in folded)
            if not _is_strict() and needed <= 12:
                top = needed
                kept = ranked if len(ranked) <= top + 1 else ranked[:top]
                rest = [nm for nm in ranked if nm not in kept]
                other_name = f"Other ({len(rest)})"
                _record_adjustment(f"share(): raised top={top} so {folded!r} stays out of Other")
            else:
                raise ExplainError(
                    f"share(highlight) names {folded!r} that were folded into '{other_name}' (top={top}).",
                    fix_hint=f"Increase top={needed} to keep them out of Other, or highlight from: "
                    f"{', '.join(map(repr, kept[:12]))}.",
                )
    hl = _names(highlight, kept, "share(highlight)")

    names = list(kept)
    pct = [100.0 * data[nm] / total for nm in kept]
    if rest:
        names.append(other_name)
        pct.append(100.0 * sum(data[nm] for nm in rest) / total)
    if share_kind in {"pie", "donut"} and len(names) > MAX_PIE_PARTS:
        raise ExplainError(
            f"share(kind={share_kind!r}) got {len(names)} parts; pie and donut charts allow at most "
            f"{MAX_PIE_PARTS} parts.",
            fix_hint="Use kind='bars' for more than 5 parts, or set top=4 to fold the rest into Other.",
            rule="too_many_items",
        )
    if fmt is not None:
        pct_fmt = _formatter(pct, fmt, unit="%")
    else:
        decimals = 0 if max(pct) >= 10 else 1

        def pct_fmt(v: float) -> str:
            text = f"{v:.{decimals}f}"
            return _sig_text(v, 2) if (v != 0 and _shows_zero(text)) else text

    labels = [f"{pct_fmt(v)}%" for v in pct]

    total_fmt = _formatter([total], unit=unit)
    total_text = _with_unit(total_fmt(total), unit)
    # "Share of energy", but a label that already says share is kept: never "Share of Share".
    whole = label if (label and label.strip().lower().startswith("share")) else (
        f"Share of {label or 'total'}"
    )
    measure = f"{whole} ({total_text} in all)"
    cumulative = np.cumsum(pct[: len(kept)])
    facts = [f"total: {total_text}", f"largest: {kept[0]} {labels[0]}"]
    for item in hl:
        part_fmt = _formatter([data[item]], unit=unit)
        facts.append(
            f"{item}: {labels[kept.index(item)]} ({_with_unit(part_fmt(data[item]), unit)})"
        )
    if len(kept) >= 3:
        facts.append(f"top 3 together: {cumulative[2]:.0f}%")
    if rest:
        facts.append(f"{len(rest)} smaller parts folded into Other: {labels[-1]}")
    if len(hl) >= 2:
        together = sum(data[nm] for nm in hl)
        facts.append(
            f"{_and_list(hl)} together: {pct_fmt(100.0 * together / total)}% "
            f"({_with_unit(_formatter([together], unit=unit)(together), unit)})"
        )

    if share_kind in {"pie", "donut"}:
        pie_issues: list[dict[str, Any]] = []
        if len(pct) >= 2:
            adj_pairs = [(i, i + 1) for i in range(len(pct) - 1)]
            if len(pct) > 2:
                adj_pairs.append((len(pct) - 1, 0))
            close = [
                (abs(pct[i] - pct[j]), i, j)
                for i, j in adj_pairs
                if abs(pct[i] - pct[j]) <= 5.0 + 1e-9
            ]
            if close:
                diff, i, j = min(close, key=lambda item: item[0])
                pie_issues.append(
                    _issue(
                        "pie_close_slices",
                        "warning",
                        f"Adjacent slices {names[i]!r} ({labels[i]}) and {names[j]!r} ({labels[j]}) "
                        f"are within {diff:.1f} percentage points; bars compare close values more accurately.",
                        "Use kind='bars' (the default) when comparing similar-sized shares.",
                    )
                )
        noun = "Donut chart" if share_kind == "donut" else "Pie chart"
        return _pie_panel(
            donut=(share_kind == "donut"),
            names=names,
            values=pct,
            highlight=hl,
            labels=labels,
            total=total,
            total_text=total_text,
            title=title,
            label=measure,
            unit=unit,
            spec=_base_spec(
                title,
                label,
                unit,
                parts=dict(data),
                highlight=hl or None,
                top=top,
                fmt=fmt,
                share_kind=share_kind,
            ),
            facts=facts,
            describe=f"{noun} of each part's share of {label or 'the total'} ({len(data)} parts)"
            if whole.startswith("Share of")
            else f"{noun} of {label} by part ({len(data)} parts)",
            muted_names=(other_name,) if rest else (),
            issues=pie_issues,
        )

    return _bar_panel(
        kind="share",
        names=names,
        values=pct,
        highlight=hl,
        labels=labels,
        title=title,
        label=measure,
        unit=None,
        spec=_base_spec(
            title, label, unit, parts=dict(data), highlight=hl or None, top=top, fmt=fmt
        ),
        facts=facts,
        describe=f"Bar chart of each part's share of {label or 'the total'} ({len(data)} parts)"
        if whole.startswith("Share of")
        else f"Bar chart of {label} by part ({len(data)} parts)",
        dots=False,
        errors=None,
        reference=None,
        muted_names=(other_name,) if rest else (),
    )
