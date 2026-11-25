"""relate() scatter form for fm.explain."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
from matplotlib.axes import Axes
from matplotlib.ticker import (
    FuncFormatter,
    MaxNLocator,
)
from matplotlib.transforms import Bbox

from ..annotations import _relax_positions_pt
from .core import (
    MAX_COLORED_SERIES,
    ExplainError,
    Panel,
    _clean_sign,
    _Ctx,
    _guarded,
    _issue,
    _jsonable,
    _names,
    _narrow_log_ticks,
    _plain,
    _reference_line,
    _resolve_x_unit,
    _sig_text,
    _slope_ci,
    _small_n_caution,
    _tick_label,
    _values_array,
)

# --------------------------------------------------------------------------- #
# relate
# --------------------------------------------------------------------------- #


_SUPER_DIGITS = "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079"  # ⁰¹²³⁴⁵⁶⁷⁸⁹


def _reciprocal_unit(unit: str) -> str | None:
    """The unit a reciprocal one inverts, with the positive power: "µm⁻½" -> "µm½",
    "K⁻¹" -> "K", "s^-1" -> "s", "1/s" -> "s". None unless ``unit`` is one such unit."""
    u = unit.strip()
    m = re.fullmatch(rf"([^\s/·*^]+)\s*\N{{SUPERSCRIPT MINUS}}([{_SUPER_DIGITS}½⅓¼]+)", u)
    if m:
        base, power = m.groups()
        return base if power == "\N{SUPERSCRIPT ONE}" else base + power
    m = re.fullmatch(r"([^\s/·*^]+)\s*\^\s*\(?\s*-\s*([\d./]+)\s*\)?", u)
    if m:
        base, power = m.groups()
        return base if power == "1" else f"{base}^{power}"
    m = re.fullmatch(r"1\s*/\s*([^\s/·*^]+)", u)
    return m.group(1) if m else None


def _line_text(slope: float, intercept: float, x_name: str, y_name: str) -> str:
    """``y = 2.1·x + 3.4`` with Unicode minus and three significant figures."""
    sign = "\N{MINUS SIGN}" if intercept < 0 else "+"
    return f"{y_name} = {_sig_text(slope)}\N{MIDDLE DOT}{x_name} {sign} {_sig_text(abs(intercept))}"


def _strength(r: float) -> str:
    return (
        "no"
        if not math.isfinite(r) or abs(r) < 0.2
        else "weak"
        if abs(r) < 0.5
        else "moderate"
        if abs(r) < 0.8
        else "strong"
    )


def _r_text(r: float) -> str:
    return _clean_sign(f"{r:.2f}") if math.isfinite(r) else "n/a"


_FRONTIER_MODES: dict[str, tuple[int, int]] = {
    "upper-left": (-1, 1),   # lower x, higher y (capability vs cost/latency)
    "upper-right": (1, 1),   # higher x, higher y
    "lower-left": (-1, -1),  # lower x, lower y
    "lower-right": (1, -1),  # higher x, lower y
}
_MAX_LABEL_ALL = 24


def _pareto_indices(xs: np.ndarray, ys: np.ndarray, mode: str) -> list[int]:
    """Return indices of non-dominated Pareto frontier points ordered by ascending x."""
    sx, sy = _FRONTIER_MODES[mode]
    # Point j dominates i if sx*x_j >= sx*x_i and sy*y_j >= sy*y_i with at least one strict.
    n = len(xs)
    keep: list[int] = []
    for i in range(n):
        dominated = False
        for j in range(n):
            if i == j:
                continue
            if (
                sx * xs[j] >= sx * xs[i] - 1e-12
                and sy * ys[j] >= sy * ys[i] - 1e-12
                and (sx * xs[j] > sx * xs[i] + 1e-12 or sy * ys[j] > sy * ys[i] + 1e-12)
            ):
                dominated = True
                break
        if not dominated:
            keep.append(i)
    keep.sort(key=lambda idx: (float(xs[idx]), float(ys[idx])))
    return keep


@_guarded("relate")
def relate(
    x: Sequence[float] | str,
    y: Sequence[float] | str,
    *,
    x_label: str,
    y_label: str,
    data: Any = None,
    title: str | None = None,
    names: Sequence[str] | str | None = None,
    groups: Sequence[str] | str | None = None,
    highlight: str | Sequence[str] | None = None,
    fit: bool = False,
    frontier: bool | str = False,
    label_all: bool = False,
    connect_groups: bool = False,
    log_x: bool = False,
    log_y: bool = False,
    reference: float | tuple[float, str] | None = None,
    unit: str | None = None,
    x_unit: str | None = None,
) -> Panel:
    """Do two measures move together? A scatter with both axes named.

    ``names`` labels the points so ``highlight`` can call out up to three of
    them, or set ``label_all=True`` (with ``names=``, up to 24 points) to label
    every point directly with collision avoidance. ``groups`` gives each point
    a group (at most four), coloured and labelled on the plot; ``highlight``
    may then name a group, and ``connect_groups=True`` draws trajectory lines
    connecting points within each group in x order. Pass ``data=`` (rows or
    DataFrame) to read ``x``, ``y``, ``names``, and ``groups`` by column name.
    ``fit=True`` adds a least-squares line (one per group) and reports r, n,
    slope and intercept. ``frontier=True`` (or ``"upper-left"`` |
    ``"upper-right"`` | ``"lower-left"`` | ``"lower-right"``) draws the exact
    non-dominated Pareto frontier envelope and lists frontier items in ``facts``.
    ``reference=(value, "label")`` draws a horizontal line at that y.
    """
    if not x_label or not y_label:
        raise ExplainError(
            "relate() needs x_label and y_label.",
            fix_hint='Name both measures with their units, e.g. x_label="Batch size", '
            'y_label="Throughput (req/s)".',
        )
    frontier_mode: str | None = None
    if frontier is True:
        frontier_mode = "upper-left"
    elif isinstance(frontier, str):
        key = frontier.strip().lower().replace("_", "-").replace(" ", "-")
        if key not in _FRONTIER_MODES:
            raise ExplainError(
                f"relate(frontier={frontier!r}) is not a valid frontier direction.",
                fix_hint=f"Use True/'upper-left', or one of: {', '.join(_FRONTIER_MODES)}.",
            )
        frontier_mode = key
    elif frontier not in (False, None):
        raise ExplainError(
            f"relate(frontier={frontier!r}) must be a bool or direction string.",
            fix_hint="Use frontier=True (upper-left: high y, low x) or 'upper-right'/'lower-left'/'lower-right'.",
        )
    if data is not None:
        from .._tabular import resolve_relate_table

        x, y, names, groups = resolve_relate_table(
            data,
            x_col=x,
            y_col=y,
            names=names,
            groups=groups,
        )
    xs = _values_array(x, "relate(x)")
    ys = _values_array(y, "relate(y)")
    if xs.shape != ys.shape or xs.ndim != 1:
        raise ExplainError(
            f"relate() got {xs.size} x values and {ys.size} y values.",
            fix_hint="Pass two equal-length lists of numbers.",
        )
    keep = np.isfinite(xs) & np.isfinite(ys)
    n_dropped = int((~keep).sum())
    point_names = [str(nm) for nm in names] if names is not None else None
    if point_names is not None and len(point_names) != xs.size:
        raise ExplainError(
            "relate(names) must have one name per point.",
            fix_hint="Pass names aligned with x and y, or omit names.",
        )
    point_groups = [str(g) for g in groups] if groups is not None else None
    if point_groups is not None and len(point_groups) != xs.size:
        raise ExplainError(
            "relate(groups) must have one group label per point.",
            fix_hint='Pass groups aligned with x and y, e.g. groups=["A", "A", "B", ...].',
        )
    group_names = list(dict.fromkeys(point_groups)) if point_groups is not None else []
    if len(group_names) > MAX_COLORED_SERIES:
        raise ExplainError(
            f"relate(groups) has {len(group_names)} groups; more than {MAX_COLORED_SERIES} "
            "colours cannot be told apart or held in mind.",
            fix_hint=f"relate(groups=) takes at most {MAX_COLORED_SERIES} groups: merge groups, "
            "drop groups= and highlight= the 1-3 points the takeaway names, or use one relate() "
            "panel per set of groups.",
            rule="too_many_series",
        )
    hl_groups: list[str] = []
    hl: list[str] = []
    if highlight is not None:
        wanted = [highlight] if isinstance(highlight, str) else [str(h) for h in highlight]
        if group_names and all(h in group_names for h in wanted):
            hl_groups = _names(wanted, group_names, "relate(highlight)")
        elif point_names is None:
            raise ExplainError(
                "relate(highlight) needs names= (or groups=) to know which points to call out.",
                fix_hint="Pass names=[...] aligned with x and y, or name a group from groups=.",
            )
        else:
            hl = _names(wanted, point_names, "relate(highlight)")
    ref = _reference_line(reference, "relate(reference)")
    spec_points = {
        "x": _jsonable(xs),
        "y": _jsonable(ys),
        "names": point_names,
        "groups": point_groups,
    }
    xs, ys = xs[keep], ys[keep]
    if point_names is not None:
        point_names = [nm for nm, ok in zip(point_names, keep, strict=True) if ok]
    if point_groups is not None:
        point_groups = [g for g, ok in zip(point_groups, keep, strict=True) if ok]
    if label_all:
        if point_names is None:
            raise ExplainError(
                "relate(label_all=True) needs names= to know what to label each point.",
                fix_hint="Pass names=[...] aligned with x and y (or column name with data=).",
            )
        if xs.size > _MAX_LABEL_ALL:
            raise ExplainError(
                f"relate(label_all=True) got {xs.size} points; labelling more than {_MAX_LABEL_ALL} "
                "points creates unreadable clutter.",
                fix_hint=f"Keep at most {_MAX_LABEL_ALL} points with label_all=True, or drop label_all and use highlight= for 1-3 focal points.",
                rule="too_many_items",
            )
    if connect_groups and not group_names:
        raise ExplainError(
            "relate(connect_groups=True) needs groups= to know which points form each trajectory.",
            fix_hint='Pass groups=[...] (or column name with data=), e.g. groups="family".',
        )
    if xs.size < 3:
        raise ExplainError(
            f"relate() has {xs.size} complete points; a relationship needs >= 3.",
            fix_hint="Use compare() for a couple of items.",
        )
    if (log_x and xs.min() <= 0) or (log_y and ys.min() <= 0):
        raise ExplainError(
            "relate() log axes need strictly positive values.",
            fix_hint="Drop log_x/log_y or remove non-positive points.",
        )
    if log_y and ref is not None and ref[0] <= 0:
        raise ExplainError(
            "relate(reference) must be positive on a log y axis.",
            fix_hint="Drop the reference or log_y=True.",
        )
    fx = np.log10(xs) if log_x else xs
    fy = np.log10(ys) if log_y else ys

    def _fit(mask: np.ndarray) -> tuple[float, float, float]:
        gx, gy = fx[mask], fy[mask]
        if gx.size < 2:
            return float("nan"), float("nan"), float("nan")
        r_val = (
            float(np.corrcoef(gx, gy)[0, 1]) if np.ptp(gx) > 0 and np.ptp(gy) > 0 else float("nan")
        )
        if np.ptp(gx) > 0:
            m, b = np.polyfit(gx, gy, 1)
            return r_val, float(m), float(b)
        return r_val, float("nan"), float("nan")

    if unit is not None and not isinstance(unit, str):
        raise ExplainError(
            f"relate(unit={unit!r}) must be a string.",
            fix_hint='Pass the y unit as text, e.g. unit="MPa".',
        )
    y_unit = (unit or "").strip() or None
    x_unit_given = x_unit
    x_unit = _resolve_x_unit(x_unit, x_label, "relate")
    everyone = np.ones(xs.size, bool)
    r, slope, intercept = _fit(everyone)
    strength = _strength(r)
    direction = "" if strength == "no" else (" positive" if r > 0 else " negative")
    space = " in log space" if (log_x or log_y) else ""
    x_sym = "log\N{SUBSCRIPT ONE}\N{SUBSCRIPT ZERO}(x)" if log_x else "x"
    y_sym = "log\N{SUBSCRIPT ONE}\N{SUBSCRIPT ZERO}(y)" if log_y else "y"
    group_masks = {
        g: np.array([pg == g for pg in point_groups], dtype=bool)  # type: ignore[union-attr]
        for g in group_names
    }
    group_fits = {g: _fit(mask) for g, mask in group_masks.items()}

    def _slope_fact(shown: str, mask: np.ndarray, m: float, b: float) -> str | None:
        """A fitted slope with its 95% CI, e.g. "Cu-Zn: slope 327 (95% CI 270–385) MPa per µm".

        A log-space slope is stated per log₁₀ unit, without the axis units.
        """
        lo, hi = _slope_ci(fx[mask], fy[mask], m, b)
        if not (math.isfinite(lo) and math.isfinite(hi)):
            return None
        inverse = _reciprocal_unit(x_unit) if x_unit else None
        if space:
            per = f"{y_sym} per {x_sym}"
        elif inverse:
            # Per a reciprocal unit is times the unit: "MPa·µm½", not "MPa per µm⁻½".
            per = f"{y_unit}\N{MIDDLE DOT}{inverse}" if y_unit else inverse
        else:
            y_part = f"{y_unit} " if y_unit else ""
            per = f"{y_part}per {x_unit}" if x_unit else f"{y_part}per unit x"
        return (
            f"{shown}: slope{space} {_sig_text(m)} (95% CI {_sig_text(lo)}\N{EN DASH}"
            f"{_sig_text(hi)}) {per}"
        )

    pooled = (
        f"Pearson r = {_r_text(r)} (n = {xs.size}): {strength}{direction} linear relationship"
        + space
    )
    facts: list[str] = [] if group_names else [pooled]
    if fit and not group_names and math.isfinite(slope):
        facts.append(
            f"fitted line{space}: {_line_text(slope, intercept, x_sym, y_sym)}"
            + (f" (x = {x_label}, y = {y_label})" if not space else "")
        )
        ci = _slope_fact("fitted line", everyone, slope, intercept)
        if ci:
            facts.append(ci)
    for g in group_names:
        g_r, g_m, g_b = group_fits[g]
        text = f"{g}: r = {_r_text(g_r)}, n = {int(group_masks[g].sum())}"
        if fit and math.isfinite(g_m):
            text += f"; fitted line{space}: {_line_text(g_m, g_b, x_sym, y_sym)}"
        facts.append(text)
    if fit:
        for g in group_names:
            _g_r, g_m, g_b = group_fits[g]
            ci = _slope_fact(g, group_masks[g], g_m, g_b) if math.isfinite(g_m) else None
            if ci:
                facts.append(ci)
    # Alt text: every group's r (and line), then the pooled r; else the pooled r.
    alt_facts = facts[: len(group_names)] if group_names else facts[:1]
    if group_names:
        # Pooled r mixes the groups (Simpson's paradox): stated after the per-group r.
        facts.append(
            f"pooled across groups: r = {_r_text(r)}, n = {xs.size}{space} "
            "(mixes groups; see per-group r)"
        )
        alt_facts.append(facts[-1])
        caution = _small_n_caution(
            {g: int(group_masks[g].sum()) for g in group_names},
            "r is a rough estimate" + (" and so is the fitted line" if fit else ""),
        )
        if caution:
            facts.append(caution)
    frontier_idx: list[int] = (
        _pareto_indices(fx, fy, frontier_mode) if frontier_mode is not None else []
    )
    if frontier_mode is not None and frontier_idx:
        if point_names is not None:
            f_names = ", ".join(point_names[i] for i in frontier_idx)
            facts.append(
                f"Pareto frontier ({frontier_mode}, {len(frontier_idx)} of {xs.size}): {f_names}"
            )
        else:
            facts.append(f"Pareto frontier ({frontier_mode}): {len(frontier_idx)} of {xs.size} points")
    if n_dropped:
        facts.append(
            f"{n_dropped} point{'s' if n_dropped > 1 else ''} with a missing value dropped"
        )
    issues: list[dict[str, Any]] = []
    if fit and group_names:
        # One line per group: judge each drawn fit, and warn only when none is strong
        # enough to carry a line (a flat fit next to a steep one is often the finding).
        drawn = {g: group_fits[g][0] for g in group_names if math.isfinite(group_fits[g][1])}
        if drawn and all(_strength(g_r) in {"no", "weak"} for g_r in drawn.values()):
            listed = ", ".join(f"{g} r = {_r_text(g_r)}" for g, g_r in drawn.items())
            issues.append(
                _issue(
                    "fit_on_weak_relationship",
                    "warning",
                    f"fit=True draws a line through a weak relationship in every group ({listed}).",
                    "Drop fit=True, or say in the title that the relationship is weak.",
                )
            )
    elif fit and strength in {"no", "weak"}:
        issues.append(
            _issue(
                "fit_on_weak_relationship",
                "warning",
                f"fit=True draws a line through a {strength} relationship (r = {_r_text(r)}).",
                "Drop fit=True, or say in the title that the relationship is weak.",
            )
        )

    def _draw(ctx: _Ctx, ax: Axes) -> Callable[[], None] | None:
        sz = ctx.sizes
        theme = ctx.theme
        effects = ctx.line_effects()
        if theme.hide_spines:
            for spine in ax.spines.values():
                spine.set_visible(False)
            if theme.grid_style != "none" and theme.grid_lw > 0:
                ax.grid(
                    axis="both",
                    color=theme.grid,
                    linestyle=theme.grid_style,
                    linewidth=theme.grid_lw,
                )
        else:
            for name in ("top", "right"):
                ax.spines[name].set_visible(False)
            if theme.inline_y_ticks:
                ax.spines["left"].set_visible(False)
                ax.spines["bottom"].set_color(theme.axis)
                ax.spines["bottom"].set_linewidth(theme.axis_lw)
                ax.grid(
                    axis="y",
                    color=theme.grid,
                    linestyle=theme.grid_style,
                    linewidth=theme.grid_lw,
                )
            else:
                for name in ("left", "bottom"):
                    ax.spines[name].set_color(theme.axis)
                    ax.spines[name].set_linewidth(theme.axis_lw)
                ax.grid(False)
        ax.set_axisbelow(True)
        if log_x:
            ax.set_xscale("log")
        if log_y:
            ax.set_yscale("log")
        ax.tick_params(
            length=theme.tick_length,
            width=theme.tick_width,
            color=theme.axis,
            labelsize=sz.small,
            labelcolor=theme.muted,
        )
        if theme.inline_y_ticks:
            ax.tick_params(axis="y", length=0)
        minus = theme.minus_sign
        for axis, is_log in ((ax.xaxis, log_x), (ax.yaxis, log_y)):
            if not is_log:
                axis.set_major_locator(MaxNLocator(nbins=5, steps=[1, 2, 2.5, 5, 10]))
                axis.set_major_formatter(
                    FuncFormatter(lambda v, _p, m=minus, a=axis: _tick_label(v, m, a))
                )
        ax.set_xlabel(_plain(x_label, theme), fontsize=sz.small, color=theme.muted, labelpad=3)
        alpha = 0.9 if xs.size <= 40 else (0.6 if xs.size <= 250 else 0.32)
        # Points called out: highlighted names, or (without highlight) names coloured
        # elsewhere in the figure, so a point keeps its entity's colour.
        called = list(hl)
        if not hl and not group_names and point_names:
            called = [nm for nm in dict.fromkeys(point_names) if nm in ctx.colors]
        is_focus = (
            np.array([(nm in called) for nm in point_names])
            if point_names
            else np.zeros(xs.size, bool)
        )
        group_color: dict[str, str] = {}
        if group_names:
            if hl_groups:
                for i, g in enumerate(hl_groups):
                    group_color[g] = ctx.colors.get(g, theme.accent_colors[i])
                for g in group_names:
                    group_color.setdefault(g, theme.axis)
            else:
                for i, g in enumerate(group_names):
                    group_color[g] = ctx.colors.get(g, theme.series_colors[i])
            order = [g for g in group_names if g not in hl_groups] + hl_groups
            for g in order:
                mask = group_masks[g] & ~is_focus
                focus_group = not hl_groups or g in hl_groups
                if connect_groups and int(group_masks[g].sum()) >= 2:
                    g_idx = np.flatnonzero(group_masks[g])
                    g_idx = g_idx[np.argsort(fx[g_idx], kind="stable")]
                    traj_kw: dict[str, Any] = {
                        "color": group_color[g],
                        "linewidth": (1.25 if focus_group else 0.85) * sz.scale,
                        "alpha": 0.7 if focus_group else 0.4,
                        "zorder": 2,
                        "label": "_trajectory",
                    }
                    if effects is not None:
                        traj_kw["path_effects"] = effects
                    ax.plot(xs[g_idx], ys[g_idx], **traj_kw)
                ax.scatter(
                    xs[mask],
                    ys[mask],
                    s=(4.0 * sz.scale) ** 2,
                    color=group_color[g],
                    alpha=alpha if focus_group else min(alpha, 0.6),
                    edgecolor=theme.background,
                    linewidth=0.4,
                    zorder=3 if focus_group else 2,
                )
        else:
            base_color = theme.axis if called else ctx.default_color
            ax.scatter(
                xs[~is_focus],
                ys[~is_focus],
                s=(4.0 * sz.scale) ** 2,
                color=base_color,
                alpha=alpha,
                edgecolor=theme.background,
                linewidth=0.4,
                zorder=2,
            )
        # Plot highlighted point markers before autoscale_view() so log-axis limits
        # never clip an extreme highlighted point off the canvas.
        called_points: list[tuple[str, int, str]] = []
        for i, name in enumerate(called):
            idx = point_names.index(name)  # type: ignore[union-attr]
            col = ctx.colors.get(name, theme.accent_colors[i % len(theme.accent_colors)])
            ax.scatter(
                [xs[idx]],
                [ys[idx]],
                s=(5.4 * sz.scale) ** 2,
                color=col,
                edgecolor=theme.background,
                linewidth=0.7,
                zorder=5,
            )
            called_points.append((name, idx, col))
        if ref is not None:
            ax.axhline(ref[0], color=theme.ink, linewidth=0.7, linestyle=(0, (3, 2)), zorder=2)
            if ref[1]:
                ax.annotate(
                    _plain(ref[1], theme),
                    (0.0, ref[0]),
                    xycoords=("axes fraction", "data"),
                    xytext=(2.0, 2.5),
                    textcoords="offset points",
                    ha="left",
                    va="bottom",
                    fontsize=sz.small,
                    color=theme.muted,
                    bbox=ctx.halo_bbox(0.1),
                )
        if label_all:
            ax.margins(x=0.10, y=0.14)
        ax.autoscale_view()
        for axis, is_log in ((ax.xaxis, log_x), (ax.yaxis, log_y)):
            if is_log:
                lo_v, hi_v = sorted(axis.get_view_interval())
                data_hi = float((xs if axis is ax.xaxis else ys).max())
                if axis is ax.yaxis and ref is not None:
                    data_hi = max(data_hi, ref[0])
                lims = _narrow_log_ticks(axis, lo_v, hi_v, minus, extend=False, data_hi=data_hi)
                (ax.set_xlim if axis is ax.xaxis else ax.set_ylim)(*lims)

        if frontier_mode is not None and len(frontier_idx) >= 2:
            ax.plot(
                xs[frontier_idx],
                ys[frontier_idx],
                color=theme.ink,
                linewidth=1.05 * sz.scale,
                linestyle=(0, (4, 2.5)),
                alpha=0.72,
                zorder=2,
                label="_frontier",
            )
            ax.scatter(
                xs[frontier_idx],
                ys[frontier_idx],
                s=(6.8 * sz.scale) ** 2,
                facecolors="none",
                edgecolors=theme.ink,
                linewidths=0.75 * sz.scale,
                alpha=0.65,
                zorder=4,
            )

        def _fit_line(mask: np.ndarray, m: float, b: float, color: str, z: int) -> None:
            gx = np.linspace(fx[mask].min(), fx[mask].max(), 50)
            gy = m * gx + b
            fit_kw: dict[str, Any] = {
                "color": color,
                "linewidth": 0.9 * sz.scale,
                "zorder": z,
                "label": "_fit",
            }
            if effects is not None:
                fit_kw["path_effects"] = effects
            ax.plot(10**gx if log_x else gx, 10**gy if log_y else gy, **fit_kw)

        if fit and not group_names and math.isfinite(slope):
            _fit_line(everyone, slope, intercept, theme.ink, 3)
            ax.annotate(
                _plain(f"r = {_r_text(r)}, n = {xs.size}", theme),
                (0.0 if r < 0 else 1.0, 0.0),
                xycoords="axes fraction",
                xytext=(5.0 if r < 0 else -5.0, 5.0),
                textcoords="offset points",
                ha="left" if r < 0 else "right",
                va="bottom",
                fontsize=sz.small,
                color=theme.muted,
                bbox=ctx.halo_bbox(0.15, alpha=0.9),
            )
        point_notes: list[tuple[Any, bool]] = []
        labeled_indices: set[int] = set()
        for name, idx, col in called_points:
            labeled_indices.add(idx)
            right_half = (fx[idx] - fx.min()) > 0.62 * (np.ptp(fx) or 1.0)
            note = ax.annotate(
                _plain(name, theme),
                (xs[idx], ys[idx]),
                xytext=(-6.0 if right_half else 6.0, 5.0),
                textcoords="offset points",
                ha="right" if right_half else "left",
                va="bottom",
                fontsize=sz.small,
                fontweight="bold",
                color=ctx.text_color(col),
                zorder=6,
                bbox=ctx.halo_bbox(0.12),
            )
            point_notes.append((note, right_half))
        if label_all and point_names is not None:
            # Label frontier points first so they claim the cleanest spots, then remaining points.
            ordered_idx = [i for i in frontier_idx if i not in labeled_indices] + [
                i for i in range(xs.size) if i not in labeled_indices and i not in frontier_idx
            ]
            for idx in ordered_idx:
                nm = point_names[idx]
                right_half = (fx[idx] - fx.min()) > 0.62 * (np.ptp(fx) or 1.0)
                if point_groups is not None:
                    g = point_groups[idx]
                    focus_g = not hl_groups or g in hl_groups
                    tcol = ctx.text_color(group_color[g]) if focus_g else theme.muted
                else:
                    tcol = theme.ink if idx in frontier_idx else theme.muted
                note = ax.annotate(
                    _plain(nm, theme),
                    (xs[idx], ys[idx]),
                    xytext=(-6.0 if right_half else 6.0, 4.5),
                    textcoords="offset points",
                    ha="right" if right_half else "left",
                    va="bottom",
                    fontsize=sz.small,
                    fontweight="normal",
                    color=tcol,
                    zorder=5,
                    bbox=ctx.halo_bbox(0.10),
                )
                point_notes.append((note, right_half))

        def _clear_point_notes(extra_boxes: Sequence[Bbox] = ()) -> None:
            if not point_notes:
                return
            renderer = ctx.fig.canvas.get_renderer()
            ax_box = ax.get_window_extent(renderer)
            avoid_paths = [
                ln.get_transform().transform_path(ln.get_path())
                for ln in ax.lines
                if ln.get_visible() and ln.get_label() in {"_fit", "_frontier", "_trajectory"}
            ]
            placed: list[Bbox] = list(extra_boxes)
            for note, right_half in point_notes:
                cands = (
                    (
                        (-6.0, 5.0, "right", "bottom"),
                        (-6.0, -5.0, "right", "top"),
                        (-8.0, 0.0, "right", "center"),
                        (0.0, 9.0, "center", "bottom"),
                        (0.0, -9.0, "center", "top"),
                        (6.0, -5.0, "left", "top"),
                        (6.0, 5.0, "left", "bottom"),
                        (8.0, 0.0, "left", "center"),
                        (-8.0, 11.0, "right", "bottom"),
                        (-8.0, -11.0, "right", "top"),
                        (10.0, -9.0, "left", "top"),
                    )
                    if right_half
                    else (
                        (6.0, 5.0, "left", "bottom"),
                        (6.0, -5.0, "left", "top"),
                        (8.0, 0.0, "left", "center"),
                        (0.0, 9.0, "center", "bottom"),
                        (0.0, -9.0, "center", "top"),
                        (-6.0, 5.0, "right", "bottom"),
                        (-6.0, -5.0, "right", "top"),
                        (-8.0, 0.0, "right", "center"),
                        (8.0, -10.0, "left", "top"),
                        (8.0, 11.0, "left", "bottom"),
                        (-8.0, 11.0, "right", "bottom"),
                    )
                )
                best = cands[0]
                best_score = (999, 999, 999)
                for dx, dy, ha, va in cands:
                    note.set_position((dx, dy))
                    note.set_ha(ha)
                    note.set_va(va)
                    bb = note.get_window_extent(renderer)
                    outside = int(
                        not (
                            bb.x0 >= ax_box.x0 - 2
                            and bb.x1 <= ax_box.x1 + 2
                            and bb.y0 >= ax_box.y0 - 2
                            and bb.y1 <= ax_box.y1 + 2
                        )
                    )
                    n_other = sum(1 for pb in placed if bb.overlaps(pb))
                    n_line = sum(1 for p in avoid_paths if p.intersects_bbox(bb, filled=False))
                    score = (outside, n_other, n_line)
                    if score < best_score:
                        best_score = score
                        best = (dx, dy, ha, va)
                    if score == (0, 0, 0):
                        break
                note.set_position((best[0], best[1]))
                note.set_ha(best[2])
                note.set_va(best[3])
                placed.append(note.get_window_extent(renderer))

        if not group_names:
            return _clear_point_notes if point_notes else None

        # Group names sit at each group's right end (its fit line end when fitted).
        anchors: list[tuple[str, float, float, str, bool]] = []
        for g in group_names:
            mask = group_masks[g]
            _g_r, g_m, g_b = group_fits[g]
            focus_group = not hl_groups or g in hl_groups
            if fit and math.isfinite(g_m):
                _fit_line(mask, g_m, g_b, group_color[g], 4 if focus_group else 3)
                end_x = float(fx[mask].max())
                ax_x = 10**end_x if log_x else end_x
                end_y = g_m * end_x + g_b
                ax_y = 10**end_y if log_y else end_y
            else:
                idx = int(np.flatnonzero(mask)[int(np.argmax(fx[mask]))])
                ax_x, ax_y = float(xs[idx]), float(ys[idx])
            # Context groups keep a direct label in the muted colour, as grey context
            # lines in trend() do, so no cloud on the plot is left unidentified.
            anchors.append((g, ax_x, ax_y, group_color[g], focus_group))
        notes = [
            ax.annotate(
                _plain(g, theme),
                (px, py),
                xytext=(5.0, 0.0),
                textcoords="offset points",
                ha="left",
                va="center",
                fontsize=sz.small,
                fontweight="bold" if focus else "normal",
                color=ctx.text_color(col) if focus else theme.muted,
                zorder=6,
                bbox=ctx.halo_bbox(0.12),
                annotation_clip=False,
            )
            for g, px, py, col, focus in anchors
        ]

        def _finish() -> None:
            renderer = ctx.fig.canvas.get_renderer()
            box = ax.get_window_extent(renderer)
            k = ctx.pt_per_px
            ys_pt = np.array([ax.transData.transform((a[1], a[2]))[1] * k for a in anchors])
            placed = _relax_positions_pt(
                ys_pt, sz.small * 1.22, box.y0 * k + sz.small * 0.4, box.y1 * k - sz.small * 0.4
            )
            for note, y0, y1 in zip(notes, ys_pt, placed, strict=True):
                note.set_position((5.0, float(y1 - y0)))
            if point_notes:
                group_boxes = [n.get_window_extent(renderer) for n in notes]
                _clear_point_notes(extra_boxes=group_boxes)

        return _finish

    return Panel(
        kind="relate",
        alt_facts=alt_facts,
        title=title,
        label=y_label,
        unit=y_unit,
        spec={
            "title": title,
            "unit": unit,
            "x_unit": x_unit_given,
            "x": spec_points["x"],
            "y": spec_points["y"],
            "x_label": x_label,
            "y_label": y_label,
            "names": spec_points["names"],
            "groups": spec_points["groups"],
            "highlight": (hl_groups or hl) or None,
            "fit": fit or None,
            "frontier": frontier_mode,
            "label_all": label_all or None,
            "connect_groups": connect_groups or None,
            "log_x": log_x or None,
            "log_y": log_y or None,
            "reference": list(ref) if ref else None,
        },
        facts=facts,
        describe=f"Scatter plot of {y_label} against {x_label}, {xs.size} points"
        + (f" in {len(group_names)} groups" if group_names else ""),
        issues=issues,
        _height_mm=lambda w, _m, _s, _t: min(62.0, max(40.0, 0.6 * w)),
        _min_height_mm=lambda _w, _m, _s, _t: 34.0,
        stretch=True,
        _draw=_draw,
        color_items=tuple(dict.fromkeys([*group_names, *(point_names or [])])),
        color_focus=tuple(hl_groups or [*group_names, *hl]),
        color_mode="highlight" if (hl_groups or hl) else ("series" if group_names else "uniform"),
        uses_default=not group_names and not hl,
    )
