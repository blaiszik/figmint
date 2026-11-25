"""timeline() execution / phase span form for mint.explain.

Answers: "What ran when, how long did each stage take, and what was the bottleneck?"
Draws horizontal [start, end] interval bars (or milestone diamonds when start == end)
along a shared elapsed-time / schedule axis with direct duration labels and automatic
bottleneck & concurrency facts.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from matplotlib.axes import Axes
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter, MaxNLocator

from .._tabular import extract_records, is_tabular
from ..themes import MINTFIG_THEME, Theme
from .core import (
    MAX_COLORED_SERIES,
    PT_TO_MM,
    ExplainError,
    Panel,
    _bare_axes,
    _base_spec,
    _Ctx,
    _formatter,
    _guarded,
    _is_strict,
    _issue,
    _jsonable,
    _Measure,
    _names,
    _plain,
    _record_adjustment,
    _reference_line,
    _Sizes,
    _tick_label,
    _to_float,
    _with_unit,
)

MAX_TIMELINE_SPANS = 20
COMFORTABLE_TIMELINE_SPANS = 12


def _normalize_spans(
    spans: object,
    *,
    name: str | None = None,
    start: str | None = None,
    end: str | None = None,
    group: str | None = None,
) -> list[dict[str, Any]]:
    """Normalize dict, tuple-list, or tidy rows into ``[{"name", "start", "end", "group"}]``."""
    if is_tabular(spans):
        cols, rows = extract_records(spans, what="timeline(spans)")
        if not rows:
            raise ExplainError("timeline(spans) is empty.", fix_hint="Pass at least one span.")
        lower_map = {c.lower(): c for c in cols}
        n_col = name or next((lower_map[k] for k in ("name", "stage", "task", "step", "label") if k in lower_map), None)
        s_col = start or next((lower_map[k] for k in ("start", "t_start", "begin", "from") if k in lower_map), None)
        e_col = end or next((lower_map[k] for k in ("end", "t_end", "finish", "stop", "to") if k in lower_map), None)
        if not (n_col and s_col and e_col):
            shown = ", ".join(repr(c) for c in cols[:8])
            raise ExplainError(
                f"timeline() needs name=, start=, and end= columns for row-shaped data (columns: {shown}).",
                fix_hint='Pass timeline(rows, name="stage", start="start_s", end="end_s").',
            )
        for col, arg in ((n_col, "name"), (s_col, "start"), (e_col, "end")):
            if col not in cols:
                raise ExplainError(
                    f"timeline({arg}={col!r}) column not found.",
                    fix_hint=f"Available columns: {', '.join(map(repr, cols[:10]))}.",
                )
        if group is not None and group not in cols:
            raise ExplainError(
                f"timeline(group={group!r}) column not found.",
                fix_hint=f"Available columns: {', '.join(map(repr, cols[:10]))}.",
            )
        out: list[dict[str, Any]] = []
        for row in rows:
            nm = str(row.get(n_col, "")).strip()
            s_val = _to_float(row.get(s_col), f"timeline(start[{nm!r}])")
            e_val = _to_float(row.get(e_col), f"timeline(end[{nm!r}])")
            g_val = str(row[group]) if (group is not None and row.get(group) is not None) else None
            out.append({"name": nm, "start": s_val, "end": e_val, "group": g_val})
        return out

    if any(a is not None for a in (name, start, end, group)):
        raise ExplainError(
            "timeline(name=/start=/end=/group=) require row-shaped data (list of dicts or DataFrame).",
            fix_hint='Pass rows=[{"stage": "build", "start": 0, "end": 45}, ...] or drop column args.',
        )

    if isinstance(spans, Mapping):
        if not spans:
            raise ExplainError("timeline(spans) is empty.", fix_hint="Pass at least one span.")
        out = []
        for raw_nm, bounds in spans.items():
            nm = str(raw_nm)
            if (
                isinstance(bounds, (str, bytes))
                or not isinstance(bounds, Sequence)
                or len(bounds) not in {2, 3}
            ):
                raise ExplainError(
                    f"timeline(spans[{nm!r}]) must be (start, end) or (start, end, group).",
                    fix_hint='e.g. {"build": (0, 45), "test": (45, 110)}.',
                )
            s_val = _to_float(bounds[0], f"timeline(spans[{nm!r}][0])")
            e_val = _to_float(bounds[1], f"timeline(spans[{nm!r}][1])")
            g_val = str(bounds[2]) if len(bounds) == 3 and bounds[2] is not None else None
            out.append({"name": nm, "start": s_val, "end": e_val, "group": g_val})
        return out

    if isinstance(spans, Sequence) and not isinstance(spans, (str, bytes)):
        if not spans:
            raise ExplainError("timeline(spans) is empty.", fix_hint="Pass at least one span.")
        out = []
        for idx, item in enumerate(spans):
            if (
                isinstance(item, (str, bytes))
                or not isinstance(item, Sequence)
                or len(item) not in {3, 4}
            ):
                raise ExplainError(
                    f"timeline(spans[{idx}]) must be (name, start, end) or (name, start, end, group).",
                    fix_hint='Pass [("build", 0, 45), ("test", 45, 110)] or a dict {name: (start, end)}.',
                )
            nm = str(item[0])
            s_val = _to_float(item[1], f"timeline(spans[{nm!r}].start)")
            e_val = _to_float(item[2], f"timeline(spans[{nm!r}].end)")
            g_val = str(item[3]) if len(item) == 4 and item[3] is not None else None
            out.append({"name": nm, "start": s_val, "end": e_val, "group": g_val})
        return out

    raise ExplainError(
        f"timeline(spans) expected a dict, list of (name, start, end) tuples, or rows; got {type(spans).__name__}.",
        fix_hint='e.g. mint.timeline({"checkout": (0, 12), "build": (12, 142)}).',
    )


def _max_concurrency(records: Sequence[Mapping[str, Any]]) -> int:
    """Compute peak number of overlapping positive-duration spans."""
    events: list[tuple[float, int]] = []
    for rec in records:
        if rec["end"] > rec["start"]:
            events.append((float(rec["start"]), 1))
            events.append((float(rec["end"]), -1))
    # Process end (-1) before start (+1) at identical timestamps (back-to-back is not concurrent)
    events.sort(key=lambda pair: (pair[0], pair[1]))
    cur = peak = 0
    for _t, delta in events:
        cur += delta
        peak = max(peak, cur)
    return peak


@_guarded("timeline")
def timeline(
    spans: (
        Mapping[str, tuple[float, float]]
        | Sequence[tuple[str, float, float]]
        | Sequence[Mapping[str, Any]]
    ),
    *,
    name: str | None = None,
    start: str | None = None,
    end: str | None = None,
    group: str | None = None,
    title: str | None = None,
    label: str | None = None,
    unit: str | None = None,
    x_label: str | None = None,
    highlight: str | Sequence[str] | None = None,
    reference: float | tuple[float, str] | None = None,
    sort: bool = True,
    fmt: str | None = None,
) -> Panel:
    """What ran when, how long did each stage take, and what was the bottleneck?

    ``spans`` accepts ``{stage: (start, end)}`` (or ``(start, end, group)``),
    ``[(stage, start, end), ...]``, or row-shaped data / DataFrame with
    ``name=``, ``start=``, ``end=`` (and optional ``group=`` for lane colour).
    """
    records = _normalize_spans(spans, name=name, start=start, end=end, group=group)
    for rec in records:
        if rec["end"] < rec["start"]:
            raise ExplainError(
                f"timeline() span {rec['name']!r} ends ({rec['end']}) before it starts ({rec['start']}).",
                fix_hint="Ensure end >= start for every span (equal values render as a milestone).",
            )

    if sort:
        records.sort(
            key=lambda r: (
                r["start"],
                0 if r["end"] == r["start"] else 1,
                -(r["end"] - r["start"]),
            )
        )

    if len(records) > MAX_TIMELINE_SPANS:
        if not _is_strict():
            req_hl = (
                [highlight]
                if isinstance(highlight, str)
                else ([str(h) for h in highlight] if highlight is not None else [])
            )
            hl_req_set = set(req_hl)
            must = [i for i, r in enumerate(records) if r["name"] in hl_req_set]
            by_dur = sorted(
                range(len(records)),
                key=lambda i: records[i]["end"] - records[i]["start"],
                reverse=True,
            )
            chosen = list(dict.fromkeys(must))
            for idx in by_dur:
                if len(chosen) >= MAX_TIMELINE_SPANS:
                    break
                if idx not in chosen:
                    chosen.append(idx)
            chosen.sort()
            orig_n = len(records)
            records = [records[i] for i in chosen]
            _record_adjustment(f"timeline(): trimmed {orig_n} spans to {len(records)}")
        else:
            raise ExplainError(
                f"timeline() got {len(records)} spans; beyond {MAX_TIMELINE_SPANS} a timeline is cramped.",
                fix_hint=f"Keep at most {MAX_TIMELINE_SPANS} spans or aggregate sub-steps into phases.",
                rule="too_many_items",
            )

    names_list = [r["name"] for r in records]
    group_names = list(dict.fromkeys(r["group"] for r in records if r["group"] is not None))
    if len(group_names) > MAX_COLORED_SERIES:
        if not _is_strict():
            kept_g = set(group_names[:MAX_COLORED_SERIES])
            for r in records:
                if r["group"] not in kept_g:
                    r["group"] = None
            group_names = group_names[:MAX_COLORED_SERIES]
            _record_adjustment(f"timeline(): limited coloured groups to {MAX_COLORED_SERIES}")
        else:
            raise ExplainError(
                f"timeline() has {len(group_names)} groups; at most {MAX_COLORED_SERIES} group colours are legible.",
                fix_hint=f"Merge into at most {MAX_COLORED_SERIES} groups, or drop group= and use highlight=.",
                rule="too_many_series",
            )

    # highlight may name stages OR groups
    hl_stages: list[str] = []
    hl_groups: list[str] = []
    if highlight is not None:
        wanted = [highlight] if isinstance(highlight, str) else [str(h) for h in highlight]
        if group_names and all(w in group_names for w in wanted):
            hl_groups = _names(wanted, group_names, "timeline(highlight)")
        else:
            hl_stages = _names(wanted, names_list, "timeline(highlight)")

    ref = _reference_line(reference, "timeline(reference)")

    issues: list[dict[str, Any]] = []
    if len(records) > COMFORTABLE_TIMELINE_SPANS:
        issues.append(
            _issue(
                "many_items",
                "warning",
                f"{len(records)} spans is dense for one timeline.",
                "Group minor steps into broader phases if the detail is not needed.",
            )
        )

    t_min = min(r["start"] for r in records)
    t_max = max(r["end"] for r in records)
    wall = t_max - t_min
    durations = [r["end"] - r["start"] for r in records]
    total_work = sum(durations)
    peak_conc = _max_concurrency(records)

    dur_fmt = _formatter([*durations, wall, t_min, t_max], fmt, unit=unit)

    def _u(v: float) -> str:
        return _with_unit(dur_fmt(v), unit)

    longest_idx = int(np.argmax(durations))
    longest = records[longest_idx]
    longest_dur = durations[longest_idx]
    longest_pct = (100.0 * longest_dur / wall) if wall > 0 else 0.0

    facts: list[str] = [
        f"wall span: {_u(t_min)} to {_u(t_max)} ({_u(wall)} total across {len(records)} stages)",
        (
            f"longest stage: {longest['name']} ({_u(longest_dur)}, {longest_pct:.0f}% of wall span, "
            f"{_u(longest['start'])} to {_u(longest['end'])})"
        ),
    ]
    if peak_conc > 1 and wall > 0:
        facts.append(
            f"sum of stage durations: {_u(total_work)} ({total_work / wall:.2g}\N{MULTIPLICATION SIGN} "
            f"wall span; peak {peak_conc} stages overlapping)"
        )
    else:
        facts.append(f"sequential execution: sum of stage durations {_u(total_work)}")

    for nm in hl_stages:
        rec = next(r for r in records if r["name"] == nm)
        d = rec["end"] - rec["start"]
        pct = (100.0 * d / wall) if wall > 0 else 0.0
        facts.append(f"{nm}: {_u(d)} ({pct:.0f}% of wall span, {_u(rec['start'])} to {_u(rec['end'])})")
    if ref is not None:
        diff = t_max - ref[0]
        ref_nm = f" ({ref[1]})" if ref[1] else ""
        if diff > 0:
            facts.append(f"end {_u(t_max)} exceeds reference {_u(ref[0])}{ref_nm} by {_u(diff)}")
        else:
            facts.append(f"end {_u(t_max)} finishes {_u(abs(diff))} under reference {_u(ref[0])}{ref_nm}")

    n_rows = len(records)
    hl_stage_set = set(hl_stages)
    hl_group_set = set(hl_groups)
    focus_mode = bool(hl_stage_set or hl_group_set)
    show_group_key = bool(group_names) and not bool(hl_stage_set)
    effective_x_label = x_label or (f"Elapsed ({unit})" if unit else "Timeline")

    def _wrapped(
        cell_width_mm: float,
        measure: _Measure,
        sizes: _Sizes,
        theme: Theme = MINTFIG_THEME,
    ) -> list[str]:
        cell_pt = cell_width_mm * sizes.scale / PT_TO_MM
        out: list[str] = []
        for nm in names_list:
            weight = "bold" if nm in hl_stage_set else "normal"
            lines = measure.wrap(nm, 0.36 * cell_pt, sizes.body, weight)
            if len(lines) > 2:
                lines = [lines[0], " ".join(lines[1:])]
            out.append("\n".join(lines))
        return out

    def _pitch(wrapped: list[str], tight: bool = False) -> float:
        lines = max(nm.count("\n") + 1 for nm in wrapped)
        if tight:
            return {1: 4.7, 2: 7.2}.get(lines, 9.5)
        return {1: 5.4, 2: 8.2}.get(lines, 10.5)

    def _draw(ctx: _Ctx, ax: Axes) -> None:
        sz = ctx.sizes
        theme = ctx.theme
        y = np.arange(n_rows, dtype=float)
        bar_h = min(theme.bar_height, 0.62)

        group_color: dict[str, str] = {}
        for idx, g in enumerate(group_names):
            if hl_group_set:
                group_color[g] = (
                    ctx.colors.get(g, theme.accent_colors[hl_groups.index(g) % len(theme.accent_colors)])
                    if g in hl_group_set
                    else theme.context_fill
                )
            else:
                group_color[g] = ctx.colors.get(g, theme.series_colors[idx % len(theme.series_colors)])

        def _bar_color(rec: Mapping[str, Any]) -> str:
            nm = rec["name"]
            g = rec["group"]
            if nm in hl_stage_set:
                return ctx.colors.get(nm, theme.accent_colors[hl_stages.index(nm) % len(theme.accent_colors)])
            if hl_stage_set:
                return theme.context_fill
            if g is not None:
                return group_color[g]
            return ctx.colors.get(nm, ctx.default_color)

        lo = float(min(t_min, ref[0] if ref else t_min))
        hi = float(max(t_max, ref[0] if ref else t_max))
        span_x = (hi - lo) or abs(hi) or 1.0
        ax.set_xlim(lo - 0.02 * span_x, hi + 0.20 * span_x)
        top_y = -1.35 if show_group_key else -0.55
        ax.set_ylim(n_rows - 0.45, top_y)

        _bare_axes(ax)
        ax.spines["bottom"].set_visible(True)
        ax.spines["bottom"].set_color(theme.axis)
        ax.spines["bottom"].set_linewidth(theme.axis_lw)
        minus = theme.minus_sign
        ax.xaxis.set_major_locator(MaxNLocator(nbins=5, steps=[1, 2, 2.5, 5, 10]))
        ax.xaxis.set_major_formatter(
            FuncFormatter(lambda v, _p, m=minus, a=ax.xaxis: _tick_label(v, m, a))
        )
        ax.tick_params(
            axis="x",
            length=theme.tick_length,
            width=theme.tick_width,
            color=theme.axis,
            labelsize=sz.small,
            labelcolor=theme.muted,
        )
        ax.set_xlabel(_plain(effective_x_label, theme), fontsize=sz.small, color=theme.muted, labelpad=3)
        if theme.grid_style != "none" and theme.grid_lw > 0:
            ax.grid(axis="x", color=theme.grid, linestyle=theme.grid_style, linewidth=theme.grid_lw)
        ax.set_axisbelow(True)

        value_notes: list[tuple[Any, float]] = []
        for idx, rec in enumerate(records):
            s_v = float(rec["start"])
            e_v = float(rec["end"])
            dur = e_v - s_v
            col = _bar_color(rec)
            is_focus = (
                (rec["name"] in hl_stage_set)
                or (rec["group"] in hl_group_set)
                or not focus_mode
            )
            if dur <= 1e-12:
                ax.scatter(
                    [s_v],
                    [idx],
                    marker="D",
                    s=(4.8 * sz.scale) ** 2,
                    color=col,
                    edgecolor=theme.background,
                    linewidth=0.6,
                    zorder=4,
                )
                d_txt = "milestone"
            else:
                ax.barh(
                    [idx],
                    [dur],
                    left=[s_v],
                    height=bar_h,
                    color=col,
                    edgecolor="none",
                    zorder=3 if is_focus else 2,
                )
                d_txt = _u(dur)

            note = ax.annotate(
                _plain(d_txt, theme),
                (e_v, idx),
                xytext=(5.0, 0.0),
                textcoords="offset points",
                ha="left",
                va="center",
                fontsize=sz.small,
                fontweight="bold" if (rec["name"] in hl_stage_set or rec["group"] in hl_group_set) else "normal",
                color=theme.ink if is_focus else theme.muted,
                annotation_clip=False,
            )
            value_notes.append((note, s_v))

        if ref is not None:
            ax.axvline(
                ref[0],
                color=theme.ink,
                linewidth=0.75,
                linestyle=(0, (3, 2)),
                zorder=4,
            )
            if ref[1]:
                ax.annotate(
                    _plain(ref[1], theme),
                    (ref[0], 1.0),
                    xycoords=("data", "axes fraction"),
                    xytext=(0.0, 2.5),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=sz.small,
                    color=theme.muted,
                    annotation_clip=False,
                )

        # Frameless inline group colour key strip when colour encodes groups
        if show_group_key:
            key_y = top_y + 0.45
            cell_w_pt = max(ctx.cell_width_mm * 0.65 / PT_TO_MM, 80.0)
            cursor_frac = 0.0
            swatch_w = 0.024
            gap_frac = 0.045
            for g in group_names:
                g_focus = (not hl_group_set) or (g in hl_group_set)
                wgt = "bold" if g in hl_group_set else "normal"
                lbl_w_pt = ctx.measure.width_pt(_plain(g, theme), sz.small, wgt)
                ax.add_patch(
                    Rectangle(
                        (cursor_frac, key_y - 0.22),
                        swatch_w,
                        0.44,
                        transform=ax.get_yaxis_transform(),
                        facecolor=group_color[g],
                        edgecolor="none",
                        zorder=5,
                        clip_on=False,
                    )
                )
                ax.text(
                    cursor_frac + swatch_w + 0.012,
                    key_y,
                    _plain(g, theme),
                    transform=ax.get_yaxis_transform(),
                    ha="left",
                    va="center",
                    fontsize=sz.small,
                    fontweight=wgt,
                    color=theme.ink if g_focus else theme.muted,
                    zorder=5,
                    clip_on=False,
                )
                cursor_frac += swatch_w + 0.012 + (lbl_w_pt / cell_w_pt) + gap_frac

        shown_names = _wrapped(ctx.cell_width_mm, ctx.measure, sz, theme)
        ax.set_yticks(y, [_plain(nm, theme) for nm in shown_names])
        ax.tick_params(axis="y", length=0, labelsize=sz.body, labelcolor=theme.ink, pad=5)
        for tick, rec in zip(ax.get_yticklabels(), records, strict=True):
            tick.set_linespacing(1.05)
            if rec["name"] in hl_stage_set:
                tick.set_fontweight("bold")
            elif focus_mode and rec["group"] not in hl_group_set:
                tick.set_color(theme.muted)

        if ref is None:
            return None
        ref_x = ref[0]

        def _clear_reference() -> None:
            renderer = ctx.fig.canvas.get_renderer()
            k = ctx.pt_per_px
            cell = ax.get_tightbbox(renderer)
            frame = ax.get_window_extent(renderer)
            right_limit = max(frame.x1, cell.x1 if cell is not None else frame.x1)
            line_px = float(ax.transData.transform((ref_x, 0.0))[0])
            gap = 3.0 / k
            for note, left_anchor in value_notes:
                box = note.get_window_extent(renderer)
                if not (box.x0 - 1 <= line_px <= box.x1 + 1):
                    continue
                dx, dy = note.xyann
                shift = (line_px + gap - box.x0) * k
                note.set_position((dx + shift, dy))
                moved = note.get_window_extent(renderer)
                if moved.x1 <= right_limit + 1:
                    continue
                note.xy = (left_anchor, note.xy[1])
                note.set_horizontalalignment("right")
                note.set_position((-5.0, dy))

        return _clear_reference

    spec_spans = [
        [r["name"], _jsonable(r["start"]), _jsonable(r["end"]), r["group"]]
        if r["group"] is not None
        else [r["name"], _jsonable(r["start"]), _jsonable(r["end"])]
        for r in records
    ]
    spec = _base_spec(
        title,
        label,
        unit,
        spans=spec_spans,
        x_label=x_label,
        highlight=(hl_groups or hl_stages) or None,
        reference=list(ref) if ref else None,
        sort=sort if not sort else None,
        fmt=fmt,
    )
    describe = (
        f"Timeline of {len(records)} stages"
        + (f" ({label})" if label else "")
        + f" spanning {_u(t_min)} to {_u(t_max)}"
    )
    extra_mm = (7.0 if show_group_key else 1.0) + 9.0 + (4.0 if ref and ref[1] else 0.0)
    return Panel(
        kind="timeline",
        title=title,
        label=label,
        unit=unit if label else None,
        spec=spec,
        facts=facts,
        describe=describe,
        issues=issues,
        _height_mm=lambda w, m, s, t: n_rows * _pitch(_wrapped(w, m, s, t)) + extra_mm,
        _min_height_mm=lambda w, m, s, t: n_rows * _pitch(_wrapped(w, m, s, t), tight=True) + extra_mm * 0.85,
        _draw=_draw,
        color_items=tuple(dict.fromkeys([*group_names, *names_list])),
        color_focus=tuple(hl_groups or hl_stages or group_names),
        color_mode="highlight" if (hl_groups or hl_stages) else ("series" if group_names else "uniform"),
        uses_default=not group_names and not hl_stages,
        alt_facts=facts[: min(3, len(facts))],
    )
