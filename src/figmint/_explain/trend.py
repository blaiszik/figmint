"""trend() form for fm.explain."""

from __future__ import annotations

import functools
import math
from collections.abc import Callable, Collection, Mapping, Sequence
from datetime import date, datetime
from typing import Any

import numpy as np
from matplotlib import dates as mdates
from matplotlib.axes import Axes
from matplotlib.ticker import (
    FixedLocator,
    FuncFormatter,
    MaxNLocator,
    NullFormatter,
)
from matplotlib.transforms import Bbox

from ..annotations import _relax_positions_pt
from ..themes import (
    FIGMINT_THEME,
    Theme,
)
from .core import (
    _ISO_DATE,
    _SCI_LARGE_PHYSICAL,
    MAX_COLORED_SERIES,
    MAX_FACETS,
    MAX_HIGHLIGHTS,
    ExplainError,
    Panel,
    _and_list,
    _apply_inline_y_ticks,
    _base_spec,
    _baseline_name,
    _change_text,
    _clear_inline_ticks,
    _Ctx,
    _data_paths,
    _date_formatter,
    _diff_with_unit,
    _formatter,
    _guarded,
    _halfwidth,
    _has_items,
    _interval_issue,
    _interval_mode_text,
    _is_number,
    _is_one_dimensional,
    _is_strict,
    _issue,
    _jsonable,
    _Measure,
    _names,
    _narrow_log_ticks,
    _pairs,
    _plain,
    _ratio_text,
    _record_adjustment,
    _reference_line,
    _relative_text,
    _resolve_x_unit,
    _sig_text,
    _signed,
    _Sizes,
    _slope_ci,
    _tick_label,
    _tick_label_boxes,
    _to_float,
    _unsigned,
    _value_axis,
    _values_array,
    _vs_text,
    _with_unit,
)

# --------------------------------------------------------------------------- #
# trend
# --------------------------------------------------------------------------- #


def _parse_x(x: Sequence[Any]) -> tuple[str, np.ndarray, list[str]]:
    """Return ``(kind, positions, display strings)`` for numeric, date or ordered-category x."""
    if x is None or isinstance(x, (str, bytes)) or _is_number(x):
        raise ExplainError(
            f"trend(x) must be a list of x positions, got {type(x).__name__}.",
            fix_hint="Pass numbers, dates (ISO strings or date objects) or ordered labels, one "
            "per value of each series.",
        )
    xs = list(x)
    if len(xs) < 2:
        raise ExplainError(
            "trend() needs at least two x positions.",
            fix_hint="Use compare() for a single point in time.",
        )
    if all(_is_number(v) for v in xs):
        arr = np.asarray([float(v) for v in xs], dtype=float)
        if not np.all(np.isfinite(arr)):
            raise ExplainError(
                "trend(x) contains a missing or infinite x value.",
                fix_hint="Drop the positions with no x (and their series values) first.",
            )
        return "number", arr, [_x_text(v) for v in arr]
    if all(isinstance(v, (datetime, date, np.datetime64)) for v in xs) or all(
        isinstance(v, str) and _ISO_DATE.match(v) for v in xs
    ):
        try:
            stamps = np.array([np.datetime64(v) for v in xs], dtype="datetime64[s]")
        except ValueError as exc:
            raise ExplainError(
                f"trend(x) dates could not be read ({exc}).",
                fix_hint="Pass ISO dates such as '2026-01-31' or date/datetime objects.",
            ) from exc
        days = stamps.astype("datetime64[D]")
        if np.all(stamps == days):
            shown = [str(v)[:10] for v in xs]
        else:  # sub-day data: a fact reading "from 2026-01-01 to 2026-01-01" says nothing
            shown = [str(v).replace("T", " ")[:16] for v in stamps]
        return "date", np.asarray(mdates.date2num(stamps), dtype=float), shown
    return "category", np.arange(len(xs), dtype=float), [str(v) for v in xs]


def _with_x_unit(text: str, x_unit: str | None) -> str:
    """An x value with its unit for facts ("19 h", "40%"); unchanged without one."""
    if not x_unit:
        return text
    return f"{text}{x_unit}" if x_unit.startswith("%") else f"{text} {x_unit}"


def _x_text(v: float) -> str:
    """An x value in facts: years plain, others to three significant figures ("3.03")."""
    if v == round(v) and 1000 <= v <= 2200:
        return f"{v:.0f}"
    return _sig_text(float(v), large=_SCI_LARGE_PHYSICAL)


def _series_map(series: object, n: int) -> tuple[dict[str, np.ndarray], bool]:
    """``({name: values}, single)``; a mapping, a pandas DataFrame, or one bare sequence."""
    if series is None:
        return {}, False
    from .._tabular import is_row_records

    if is_row_records(series):
        cols = list(dict.fromkeys(str(k) for row in series for k in row))  # type: ignore[union-attr]
        shown = ", ".join(repr(c) for c in cols[:8])
        raise ExplainError(
            f"trend(series) received row-shaped dicts (columns: {shown}) instead of wide series.",
            fix_hint=(
                'Pass tidy rows via data=: fm.trend("x_col", "series_col", y="y_col", data=rows), '
                'or pivot wide first (e.g. df.pivot(index="x", columns="series", values="y")).'
            ),
        )
    if _has_items(series) and not _is_one_dimensional(series):
        raw = {str(k): v for k, v in _pairs(series)}
        single = False
    else:
        raw = {"": series}
        single = True
    out: dict[str, np.ndarray] = {}
    for name, values in raw.items():
        arr = _values_array(values, f"trend(series[{name!r}])")
        if arr.ndim != 1 or arr.size != n:
            raise ExplainError(
                f"trend(series[{name!r}]) has {arr.size} values but x has {n}.",
                fix_hint="Every series must have one value per x position (None for gaps).",
            )
        out[name] = arr
    if not out:
        raise ExplainError("trend(series) is empty.", fix_hint="Pass at least one series.")
    return out, single


def _replicates(points: object, n: int, names_hint: Sequence[str]) -> dict[str, list[np.ndarray]]:
    """Read ``trend(points=...)``: per series, the raw replicate values at each x."""
    hint = (
        'Pass points={"name": [[replicates at x0], [replicates at x1], ...]} or '
        "{name: 2-D array of shape (n_x, n_replicates)}; use NaN or an empty list where an x "
        "has no measurement."
    )
    if _has_items(points) and not _is_one_dimensional(points):
        raw = {str(k): v for k, v in _pairs(points)}
    elif len(names_hint) <= 1:
        raw = {names_hint[0] if names_hint else "": points}
    else:
        raise ExplainError("trend(points) must map series names to replicates.", fix_hint=hint)
    out: dict[str, list[np.ndarray]] = {}
    for name, rows in raw.items():
        if isinstance(rows, (str, bytes)) or _is_number(rows) or rows is None:
            raise ExplainError(
                f"trend(points[{name!r}]) is not a list of replicates.", fix_hint=hint
            )
        rows_list = list(rows)  # type: ignore[call-overload]
        if len(rows_list) != n:
            raise ExplainError(
                f"trend(points[{name!r}]) has {len(rows_list)} rows but x has {n}.",
                fix_hint=hint,
            )
        per_x: list[np.ndarray] = []
        for row in rows_list:
            if row is None or _is_number(row):
                arr = np.asarray([np.nan if row is None else float(row)], dtype=float)
            else:
                arr = _values_array(row, f"trend(points[{name!r}])")
            per_x.append(arr[np.isfinite(arr)])
        out[name] = per_x
    return out


def _trend_bands(
    band: object, data: dict[str, np.ndarray], n: int
) -> tuple[dict[str, tuple[np.ndarray, np.ndarray]], dict[str, Any], set[str]]:
    """Read ``trend(band=...)``: per series (low, high) sequences, half-width sequence or number.

    Returns the absolute bounds, the per-series normalised spec, and the modes read.
    """
    hint = (
        "Per series pass (low_values, high_values) as absolute bounds, one half-width per x, "
        'or one number for a constant \N{PLUS-MINUS SIGN} band, e.g. band={"a": 0.5}.'
    )
    names = list(data)
    if band is None:
        return {}, {}, set()
    if _has_items(band) and not _is_one_dimensional(band):
        raw = {str(k): v for k, v in _pairs(band)}
    elif len(names) == 1:
        raw = {names[0]: band}
    else:
        raise ExplainError(
            "trend(band) must map series names to bands when there are several series.",
            fix_hint=hint,
        )
    bounds: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    spec: dict[str, Any] = {}
    modes: set[str] = set()
    for name, entry in raw.items():
        if name not in data:
            raise ExplainError(
                f"trend(band) names {name!r}, which is not a series.",
                fix_hint=f"Use one of: {', '.join(map(repr, names))}.",
            )
        values = data[name]
        if _is_number(entry):
            hw = _halfwidth(entry, f"trend(band[{name!r}])")
            bounds[name] = (values - hw, values + hw)
            spec[name] = hw
            modes.add("halfwidth")
            continue
        try:
            arr = np.asarray(
                [[np.nan if v is None else float(v) for v in part] for part in entry]  # type: ignore[union-attr]
                if not isinstance(entry, np.ndarray)
                else entry,
                dtype=float,
            )
        except (TypeError, ValueError):
            try:
                arr = np.asarray(
                    [np.nan if v is None else float(v) for v in entry],  # type: ignore[union-attr]
                    dtype=float,
                )
            except (TypeError, ValueError) as exc:
                raise ExplainError(f"trend(band[{name!r}]) is not numeric.", fix_hint=hint) from exc
        if arr.ndim == 2 and arr.shape == (2, n):
            low, high = arr[0], arr[1]
            ok = np.isfinite(low) & np.isfinite(high) & np.isfinite(values)
            if np.any(low[ok] > high[ok]) or np.any(
                (values[ok] < low[ok] - 1e-12 * np.abs(values[ok]))
                | (values[ok] > high[ok] + 1e-12 * np.abs(values[ok]))
            ):
                raise ExplainError(
                    f"trend(band[{name!r}]) (low, high) does not bracket the series values.",
                    fix_hint="Pass absolute (low, high) bounds, not +/- offsets; for a symmetric "
                    "band pass the half-widths (one sequence) or one number.",
                )
            bounds[name] = (low, high)
            spec[name] = [low.tolist(), high.tolist()]
            modes.add("bounds")
        elif arr.ndim == 1 and arr.size == n:
            if np.any(arr[np.isfinite(arr)] < 0):
                raise ExplainError(
                    f"trend(band[{name!r}]) has a negative half-width.", fix_hint=hint
                )
            bounds[name] = (values - arr, values + arr)
            spec[name] = arr.tolist()
            modes.add("halfwidth")
        else:
            raise ExplainError(
                f"trend(band[{name!r}]) has shape {arr.shape}; with {n} x positions expected "
                f"(2, {n}) bounds, {n} half-widths or one number.",
                fix_hint=hint,
            )
    return bounds, spec, modes


def _r2_text(r2: float) -> str:
    """R² to three decimals, four when it would otherwise read as 1.000."""
    return f"{r2:.4f}" if 0.9995 <= r2 < 1.0 else f"{r2:.3f}"


def _log_trend_facts(
    data: Mapping[str, np.ndarray],
    names: Sequence[str],
    xpos: np.ndarray,
    x_kind: str,
    log_x: bool,
    label: str | None,
    x_text: Sequence[str] | None = None,
    x_unit: str | None = None,
    spiked: Collection[str] = (),
    power_names: Sequence[str] | None = None,
) -> list[str]:
    """Facts a log-scale trend is judged by: slopes of log₁₀(y) and peak ratios; on
    log-log axes (``log_x``) the power-law exponent of each of ``power_names`` with its
    95% CI and R².

    The least-squares slope of log₁₀(y) against x (plotted x units, numeric linear x
    only) with its R² lets an agent check an Arrhenius or exponential claim. A series
    that rises then falls (or falls then rises) is fitted on each side of its interior
    peak (or trough), never across it: one line through a rise and a decay describes
    neither (an absorption phase would hide the elimination rate). When the peak is
    not an endpoint, its ratio to the first and last values (unrounded), except for
    ``spiked`` series, whose event-marked spike is stated against the median before it.
    """
    per = f"per {x_unit}" if x_unit else "per unit x"
    log10 = "log\N{SUBSCRIPT ONE}\N{SUBSCRIPT ZERO}"

    def _slope_fact(shown: str, sel: np.ndarray, arr: np.ndarray, where: str) -> str | None:
        lx, ly = xpos[sel].astype(float), np.log10(arr[sel])
        if sel.size < 3 or np.ptp(lx) <= 0:
            return None
        slope, icept = np.polyfit(lx, ly, 1)
        resid = ly - (slope * lx + icept)
        total = float(((ly - ly.mean()) ** 2).sum())
        r2 = 1.0 - float((resid**2).sum()) / total if total > 0 else float("nan")
        return (
            f"{shown}: {log10} slope {_sig_text(float(slope), 3)} {per}{where}"
            + (f", R\N{SUPERSCRIPT TWO} = {_r2_text(r2)}" if math.isfinite(r2) else "")
        )

    def _power_fact(shown: str, sel: np.ndarray, arr: np.ndarray, where: str) -> str | None:
        """Log-log axes: the power-law exponent (slope of log y on log x) with its 95% CI."""
        lx, ly = np.log10(xpos[sel].astype(float)), np.log10(arr[sel])
        if sel.size < 3 or np.ptp(lx) <= 0:
            return None
        slope, icept = np.polyfit(lx, ly, 1)
        resid = ly - (slope * lx + icept)
        total = float(((ly - ly.mean()) ** 2).sum())
        r2 = 1.0 - float((resid**2).sum()) / total if total > 0 else float("nan")
        lo, hi = _slope_ci(lx, ly, float(slope), float(icept))
        ci = ""
        if math.isfinite(lo) and math.isfinite(hi):
            joint = " to " if lo < 0 else "\N{EN DASH}"
            ci = f" (95% CI {_sig_text(lo, 3)}{joint}{_sig_text(hi, 3)})"
        return (
            f"{shown}: y \N{PROPORTIONAL TO} x^{_sig_text(float(slope), 3)}{ci}{where}"
            + (f", R\N{SUPERSCRIPT TWO} = {_r2_text(r2)}" if math.isfinite(r2) else "")
        )

    out: list[str] = []
    if x_kind == "number" and log_x:
        # A straight line on log-log axes is a power law: its exponent is the claim
        # ("loss falls as compute^−0.063"), checkable only with its interval. Every
        # series (``power_names``, grey ones too): "faster than the others" needs theirs.
        for name in names if power_names is None else power_names:
            arr = data[name]
            ok = np.isfinite(arr) & (arr > 0)
            if ok.sum() >= 3:
                fact = _power_fact(name or (label or "value"), np.flatnonzero(ok), arr, "")
                out += [fact] if fact else []
    for name in names:
        arr = data[name]
        ok = np.isfinite(arr) & (arr > 0)
        shown = name or (label or "value")
        if x_kind == "number" and not log_x and ok.sum() >= 3:
            sel = np.flatnonzero(ok)
            vals = arr[sel]
            turn, kind = None, ""
            if 0 < int(np.argmax(vals)) < sel.size - 1:
                turn, kind = int(np.argmax(vals)), "peak"
            elif 0 < int(np.argmin(vals)) < sel.size - 1:
                turn, kind = int(np.argmin(vals)), "trough"
            if turn is None:
                fact = _slope_fact(shown, sel, arr, "")
                out += [fact] if fact else []
            else:
                at = (x_text or [_x_text(float(v)) for v in xpos])[int(sel[turn])]
                for seg, where in (
                    (sel[: turn + 1], f" up to the {kind} at {at}"),
                    (sel[turn:], f" from the {kind} at {at} on"),
                ):
                    fact = _slope_fact(shown, seg, arr, where)
                    out += [fact] if fact else []
        idx = np.flatnonzero(ok)
        if idx.size >= 3 and name not in spiked:
            peak = int(idx[int(np.argmax(arr[idx]))])
            if peak not in (int(idx[0]), int(idx[-1])):
                top = float(arr[peak])
                out.append(
                    f"{shown}: peak is {_ratio_text(top / float(arr[idx[0]]))} the first value "
                    f"and {_ratio_text(top / float(arr[idx[-1]]))} the last"
                )
    return out


def _reference_crossings(
    ref: tuple[float, str],
    names: Sequence[str],
    data: Mapping[str, np.ndarray],
    xpos: np.ndarray,
    x_kind: str,
    x_text: Sequence[str],
    log: bool,
    log_x: bool,
    label: str | None,
    x_unit: str | None = None,
    noise: float = 0.0,
    unit: str | None = None,
) -> list[str]:
    """Where each named series first crosses the reference value.

    Interpolated linearly between the two bracketing measured x positions (in log
    space on a log axis, matching the straight segments drawn there). Series that
    never cross are skipped, and so is a crossing within ``noise`` of the line on
    both sides (a flat series jittering about it).
    """
    value, ref_text = ref
    # The reference as the caller gave it ("50", not "50.0" from the series' digits).
    ref_fmt = _formatter([value], log=log)
    out: list[str] = []
    target = math.log10(value) if log and value > 0 else value
    stays: dict[tuple[str, bool], list[str]] = {
        (side, strict): [] for strict in (True, False) for side in ("above", "below")
    }
    for name in names:
        arr = data[name]
        idx = np.flatnonzero(np.isfinite(arr))
        if idx.size < 2:
            continue
        ys = np.log10(arr[idx]) if log else arr[idx]
        xs = np.log10(xpos[idx]) if log_x else xpos[idx].astype(float)
        diff = ys - target
        where: str | None = None
        for k in range(idx.size):
            if diff[k] == 0:
                if k == 0:
                    continue  # starting on the line is not a crossing
                near = [abs(diff[j]) for j in (k - 1, k + 1) if 0 <= j < idx.size]
                if all(v < noise for v in near):
                    continue
                at = xs[k]
                exact = True
            elif k + 1 < idx.size and diff[k] * diff[k + 1] < 0:
                if abs(diff[k]) < noise and abs(diff[k + 1]) < noise:
                    continue
                t = diff[k] / (diff[k] - diff[k + 1])
                at = xs[k] + t * (xs[k + 1] - xs[k])
                exact = False
            else:
                continue
            if x_kind == "category":
                where = (
                    f"at {x_text[idx[k]]}"
                    if exact
                    else f"between {x_text[idx[k]]} and {x_text[idx[k + 1]]}"
                )
            elif x_kind == "date":
                when = mdates.num2date(float(at)).date().isoformat()
                where = f"at {'' if exact else 'about '}{when}"
            else:
                x_val = 10**at if log_x else at
                where = (
                    f"at {'' if exact else 'about '}"
                    f"{_with_x_unit(_sig_text(float(x_val), 2), x_unit)}"
                )
            break
        shown = name or (label or "value")
        if where is None:
            # Never crosses: say on which side it stays, so "only X stays above the
            # line" can be checked against every series, not only those that cross.
            for side, strict, holds in (
                ("above", True, (diff >= 0).all()),
                ("below", True, (diff <= 0).all()),
                ("above", False, (diff >= -noise).all()),
                ("below", False, (diff <= noise).all()),
            ):
                if holds:
                    stays[(side, strict)].append(shown)
                    break
            continue
        named = f" ({ref_text})" if ref_text else ""
        out.append(f"{shown} crosses {_with_unit(ref_fmt(value), unit)}{named} {where}")
    named = f" ({ref_text})" if ref_text else ""
    for (side, strict), who in stays.items():
        if who:
            verb = "stays" if len(who) == 1 else "stay"
            out.append(
                f"{_and_list(who)} {verb} {side} {_with_unit(ref_fmt(value), unit)}{named} throughout"
                + ("" if strict else " (to within noise)")
            )
    return out


def _crossing_fact(
    a: str, b: str, diff: np.ndarray, x_text: Sequence[str], noise: float = 0.0
) -> str | None:
    """How often ``a`` and ``b`` swap order, ignoring exact ties.

    One swap: "a first crosses above b at x". Several: "a and b cross 4 times; a is
    above b from x on", or "...; they end level/tangled" when the last stretch is
    shorter than two points. A swap where the gap is under ``noise`` on both sides
    (two curves level at ~0%, apart only by assay noise) is not a crossing.
    """
    finite = np.flatnonzero(np.isfinite(diff))
    idxs = np.flatnonzero(np.isfinite(diff) & (diff != 0))
    if idxs.size < 2:
        return None
    signs = np.sign(diff[idxs])
    size = np.abs(diff[idxs])
    swaps = np.flatnonzero(
        (signs[1:] != signs[:-1]) & ~((size[1:] < noise) & (size[:-1] < noise))
    )
    if swaps.size == 0:
        return None
    if swaps.size == 1:
        k = int(idxs[int(swaps[0]) + 1])
        before = signs[int(swaps[0])]
        return f"{a} first crosses {'above' if before < 0 else 'below'} {b} at {x_text[k]}"
    last_start = int(swaps[-1]) + 1
    head = f"{a} and {b} cross {swaps.size} times"
    if idxs.size - last_start >= 2:
        side = "above" if signs[last_start] > 0 else "below"
        return f"{head}; {a} is {side} {b} from {x_text[int(idxs[last_start])]} on"
    level = finite.size and int(finite[-1]) != int(idxs[-1])
    return f"{head}; they end {'level' if level else 'tangled'}"


def _trend_baseline_facts(
    compared: Sequence[str],
    base: str,
    data: Mapping[str, np.ndarray],
    x_text: Sequence[str],
    *,
    unit: str | None,
    fmt: str | None,
    log: bool,
) -> list[str]:
    """Each series against the baseline: at the last shared x and as the median gap over x."""
    rows: list[tuple[str, int, float, float, np.ndarray]] = []
    for name in compared:
        both = np.flatnonzero(np.isfinite(data[name]) & np.isfinite(data[base]))
        if not both.size:
            continue
        idx = int(both[-1])
        rows.append((name, idx, float(data[name][idx]), float(data[base][idx]), both))
    gaps = [
        g
        for name, idx, va, vb, both in rows
        for g in (va - vb, float(np.median(data[name][both] - data[base][both])))
    ]
    diff_fmt = _formatter(gaps or [0.0], fmt, unit=unit)
    out: list[str] = []
    for name, idx, va, vb, both in rows:
        a, b = data[name][both], data[base][both]
        pos = (a > 0) & (b > 0)
        ratio = float(np.median(a[pos] / b[pos])) if pos.sum() == both.size else float("nan")
        shown = name or "series"
        if log:
            out.append(
                f"{shown} vs {base}: {_ratio_text(va / vb)} at {x_text[idx]}; median ratio "
                f"{_ratio_text(ratio)} over {both.size} shared points"
            )
            continue
        gap = float(np.median(a - b))
        median_text = _diff_with_unit(_signed(diff_fmt(gap)), unit)
        rel = _relative_text(ratio, 1.0, unit) if math.isfinite(ratio) else None
        out.append(
            f"{shown} vs {base}: {_vs_text(va, vb, unit=unit, diff_fmt=diff_fmt)} at "
            f"{x_text[idx]}; median gap {median_text}"
            + (f" ({rel})" if rel else "")
            + f" over {both.size} shared points"
        )
    return out


def _event_facts(
    events: Sequence[tuple[float, str]],
    names: Sequence[str],
    data: Mapping[str, np.ndarray],
    xpos: np.ndarray,
    *,
    unit: str | None,
    fmt: str | None,
    log: bool,
    label: str | None,
) -> tuple[list[str], set[str]]:
    """Each series' median before an event and from it on (up to the neighbouring events).

    "us-west: median 1,500 ms before config change → 2,190 ms from it on (+46%)": the
    fact the event marker exists for. Needs >= 2 finite points on each side. Also
    returns the series whose spike an event marks (stated against the median before it).
    """
    cuts = sorted(pos for pos, _ in events)
    rows: list[tuple[str, str, float, float, float | None]] = []
    for pos, text in events:
        k = cuts.index(pos)
        lo = cuts[k - 1] if k > 0 else -np.inf
        hi = cuts[k + 1] if k + 1 < len(cuts) else np.inf
        for name in names:
            arr = data[name]
            ok = np.isfinite(arr)
            before = arr[ok & (xpos >= lo) & (xpos < pos)]
            after = arr[ok & (xpos >= pos) & (xpos < hi)]
            if before.size < 2 or after.size < 2:
                continue
            # The event day holds the series' peak (a spike): its value is the fact.
            peak = int(np.nanargmax(arr))
            spike = float(arr[peak]) if xpos[peak] == pos else None
            rows.append((name, text, float(np.median(before)), float(np.median(after)), spike))
    if not rows:
        return [], set()
    level_fmt = _formatter(
        [v for r in rows for v in (r[2], r[3], *([r[4]] if r[4] is not None else []))],
        fmt,
        unit=unit,
        log=log,
    )
    diff_fmt = _formatter([r[3] - r[2] for r in rows], fmt, unit=unit)
    out: list[str] = []
    spiked: set[str] = set()
    for name, text, mb, ma, spike in rows:
        if log:
            rel: str | None = _ratio_text(ma / mb) if mb > 0 and ma > 0 else None
        elif unit is not None and unit.strip().startswith("%"):
            rel = _diff_with_unit(_signed(diff_fmt(ma - mb)), unit)
        else:
            rel = _relative_text(ma, mb, None)
        day = ""
        if spike is not None and mb > 0 and spike > 0:
            day = (
                f"; on the {text} day {_with_unit(level_fmt(spike), unit)}, "
                f"{_ratio_text(spike / mb)} the median before"
            )
            spiked.add(name)
        out.append(
            f"{name or (label or 'value')}: median {_with_unit(level_fmt(mb), unit)} before {text} "
            f"\N{RIGHTWARDS ARROW} {_with_unit(level_fmt(ma), unit)} from it on"
            + (f" ({rel})" if rel else "")
            + day
        )
    return out, spiked


def _context_fact(
    rest: Sequence[str],
    data: Mapping[str, np.ndarray],
    *,
    spikes: bool,
    unit: str | None,
    fmt: str | None,
    log: bool,
) -> str | None:
    """One fact for the grey context series of a highlighted trend, each against itself.

    When a highlighted series spikes: how far the others' peaks rise above their own
    medians ("the other 4 peak within 1.6× of their medians"). Otherwise how they moved
    from first to last value: a fold range on a log axis, points for "%" units, a percent
    change where it is meaningful, else the absolute change.
    """
    rest = list(rest)
    if not rest:
        return None
    one = len(rest) == 1
    who = f"the other series, {rest[0]}," if one else f"the other {len(rest)}"
    if spikes:
        ratios = []
        for nm in rest:
            finite = data[nm][np.isfinite(data[nm])]
            med, top = float(np.median(finite)), float(finite.max())
            if med <= 0 or top <= 0:
                return None
            ratios.append(top / med)
        return (
            f"{who} {'peaks' if one else 'peak'} within {_ratio_text(max(ratios))} of "
            f"{'its own median' if one else 'their own medians'}"
        )
    ends = {nm: (_first_finite(data[nm])[1], _last_finite(data[nm])[1]) for nm in rest}
    if log:
        if any(a <= 0 or b <= 0 for a, b in ends.values()):
            return None
        folds = sorted(b / a for a, b in ends.values())
        shown = [_ratio_text(f) for f in (folds[0], folds[-1])]
        span = shown[0] if one or shown[0] == shown[1] else f"{shown[0]} to {shown[1]}"
        noun = "its first value" if one else "their first values"
        return f"{who} {'ends' if one else 'end'} at {span} {noun}"
    points = unit is not None and unit.strip().startswith("%")
    rels = [None if points else _relative_text(b, a, None) for a, b in ends.values()]
    if not points and all(rels):
        by = sorted(ends, key=lambda nm: (ends[nm][1] - ends[nm][0]) / abs(ends[nm][0]))
        lo_t = _relative_text(ends[by[0]][1], ends[by[0]][0], None)
        hi_t = _relative_text(ends[by[-1]][1], ends[by[-1]][0], None)
    else:
        by = sorted(ends, key=lambda nm: ends[nm][1] - ends[nm][0])
        delta_fmt = _formatter([b - a for a, b in ends.values()], fmt, unit=unit)
        lo_t, hi_t = (
            _diff_with_unit(_signed(delta_fmt(ends[nm][1] - ends[nm][0])), unit)
            for nm in (by[0], by[-1])
        )
    span = lo_t if one or lo_t == hi_t else f"{lo_t} to {hi_t}"
    return f"{who} {'changes' if one else 'change'} by {span} from first to last value"


def _first_finite(arr: np.ndarray) -> tuple[int, float]:
    idx = int(np.flatnonzero(np.isfinite(arr))[0])
    return idx, float(arr[idx])


def _last_finite(arr: np.ndarray) -> tuple[int, float]:
    idx = int(np.flatnonzero(np.isfinite(arr))[-1])
    return idx, float(arr[idx])


def _isolated(arr: np.ndarray) -> np.ndarray:
    """Finite points with no finite neighbour on either side (a line cannot show them)."""
    finite = np.isfinite(arr)
    left = np.concatenate([[False], finite[:-1]])
    right = np.concatenate([finite[1:], [False]])
    return finite & ~left & ~right


def _draw_fit_curve(
    ax: Axes,
    xpos: np.ndarray,
    arr: np.ndarray,
    *,
    fit_mode: str,
    color: str,
    scale: float,
) -> None:
    """Overlay a dashed OLS trendline (linear, log-linear, or power-law) within finite x span."""
    ok = np.isfinite(xpos) & np.isfinite(arr)
    if fit_mode in {"log", "power"}:
        ok = ok & (arr > 0)
    if fit_mode == "power":
        ok = ok & (xpos > 0)
    if int(ok.sum()) < 3:
        return
    xs = xpos[ok].astype(float)
    ys = arr[ok].astype(float)
    if float(np.ptp(xs)) <= 0:
        return

    if fit_mode == "power":
        lx, ly = np.log10(xs), np.log10(ys)
        slope, icept = np.polyfit(lx, ly, 1)
        grid_x = np.geomspace(float(xs.min()), float(xs.max()), 60)
        grid_y = 10.0 ** (slope * np.log10(grid_x) + icept)
    elif fit_mode == "log":
        ly = np.log10(ys)
        slope, icept = np.polyfit(xs, ly, 1)
        grid_x = np.linspace(float(xs.min()), float(xs.max()), 60)
        grid_y = 10.0 ** (slope * grid_x + icept)
    else:
        slope, icept = np.polyfit(xs, ys, 1)
        grid_x = np.linspace(float(xs.min()), float(xs.max()), 2)
        grid_y = slope * grid_x + icept

    ax.plot(
        grid_x,
        grid_y,
        color=color,
        linewidth=1.15 * scale,
        linestyle=(0, (4, 2.5)),
        alpha=0.82,
        zorder=4.5,
        label="_fit",
    )


def _linear_fit_facts(
    names: Sequence[str],
    data: Mapping[str, np.ndarray],
    xpos: np.ndarray,
    *,
    x_kind: str,
    unit: str | None,
    x_unit: str | None,
    label: str | None,
) -> list[str]:
    """Compute linear OLS slope (with 95% CI) and R² facts when ``trend(fit='linear'|True)``."""
    out: list[str] = []
    if x_kind == "category":
        return out
    per = f" per {x_unit}" if x_unit else (" per day" if x_kind == "date" else " per x unit")
    for name in names:
        arr = data[name]
        ok = np.isfinite(xpos) & np.isfinite(arr)
        if int(ok.sum()) < 3:
            continue
        xs = xpos[ok].astype(float)
        ys = arr[ok].astype(float)
        if float(np.ptp(xs)) <= 0:
            continue
        slope, icept = np.polyfit(xs, ys, 1)
        resid = ys - (slope * xs + icept)
        total = float(((ys - ys.mean()) ** 2).sum())
        r2 = 1.0 - float((resid**2).sum()) / total if total > 0 else float("nan")
        lo, hi = _slope_ci(xs, ys, float(slope), float(icept))
        ci = ""
        if math.isfinite(lo) and math.isfinite(hi):
            joint = " to " if lo < 0 else "\N{EN DASH}"
            ci = f" (95% CI {_sig_text(lo, 3)}{joint}{_sig_text(hi, 3)})"
        shown = name or (label or "value")
        slope_txt = _diff_with_unit(_signed(_sig_text(float(slope), 3)), unit)
        r2_txt = f", R\N{SUPERSCRIPT TWO} = {r2:.2f}" if math.isfinite(r2) else ""
        out.append(f"{shown}: linear fit slope {slope_txt}{per}{ci}{r2_txt}")
    return out


@_guarded("trend")
def trend(
    x: Sequence[Any] | str,
    series: Mapping[str, Sequence[float]] | Sequence[float] | str | None = None,
    *,
    y: str | None = None,
    data: Any = None,
    title: str | None = None,
    label: str | None = None,
    unit: str | None = None,
    x_label: str | None = None,
    x_unit: str | None = None,
    highlight: str | Sequence[str] | None = None,
    baseline: str | None = None,
    facet: bool = False,
    band: Any = None,
    band_label: str | None = None,
    points: Any = None,
    points_label: str | None = None,
    events: Mapping[Any, str] | None = None,
    reference: float | tuple[float, str] | None = None,
    zero: bool = False,
    log: bool = False,
    log_y: bool | None = None,
    log_x: bool = False,
    fit: bool | str = False,
    end_values: bool = True,
    fmt: str | None = None,
    callouts: Sequence[tuple[Any, float, str]] | None = None,
    regions: Sequence[tuple[Any, Any, str]] | None = None,
) -> Panel:
    """How does it change over time or order? Lines labelled at their ends (no legend).

    ``x`` is numbers, ISO dates or ordered labels (numeric and date x are sorted
    with their series; repeated x values are refused). ``series`` maps name to
    values (a dict, a pandas DataFrame, or one sequence). For long/tidy rows or
    DataFrames, pass ``data=rows`` with column names: ``fm.trend("x_col",
    "series_col", y="y_col", data=rows)`` (multiple rows per ``(x, series)``
    automatically become raw ``points=`` replicates). At most four series
    get a hue. With more, name the ones the takeaway is about in ``highlight``
    (the rest become grey context) or pass ``facet=True`` for small multiples
    on a shared scale. ``band`` gives a series an uncertainty ribbon: ``(low,
    high)`` sequences, half-widths per x, or one number; say what it is with
    ``band_label``. ``points`` gives raw replicates per x (the line becomes
    their mean). ``log``/``log_y`` and ``log_x`` make an axis logarithmic.
    ``end_values=False`` keeps the end label's name but drops its value.
    ``baseline`` names the reference series (a control, "before"): drawn in ink,
    with every highlighted (or every other) series stated against it in the facts.
    """
    from .._tabular import is_tabular, resolve_trend_table

    if data is not None:
        if points is not None:
            raise ExplainError(
                "trend() cannot combine data= with an explicit points= mapping.",
                fix_hint="Leave points= out: repeated rows per (x, series) in data= are plotted as points automatically.",
            )
        x, series, points, band = resolve_trend_table(
            data,
            x_col=x,
            y_col=y,
            series_col=series,
            band=band,
        )
    elif y is not None:
        raise ExplainError(
            "trend(y=...) requires data= with row-shaped records or a DataFrame.",
            fix_hint='Pass data=rows, e.g. fm.trend("step", "model", y="acc", data=rows).',
        )
    elif is_tabular(x):
        raise ExplainError(
            "trend() got a table as its first argument without column names.",
            fix_hint='Pass tidy rows via data=: fm.trend("x_col", "series_col", y="y_col", data=rows), '
            'or pass wide data as fm.trend(df.index, df) after df.pivot(...).',
        )
    log = bool(log or log_y)
    x_kind, xpos, x_text = _parse_x(x)
    n = len(xpos)
    data, single = _series_map(series, n)
    reps: dict[str, list[np.ndarray]] = {}
    if points is not None:
        reps = _replicates(points, n, list(data) if data else [""])
        for name, per_x in reps.items():
            means = np.array([float(r.mean()) if r.size else np.nan for r in per_x])
            if name in data:
                given = data[name]
                both = np.isfinite(given) & np.isfinite(means)
                if not np.allclose(given[both], means[both], rtol=1e-6, atol=1e-12) or np.any(
                    np.isfinite(means) != np.isfinite(given)
                ):
                    raise ExplainError(
                        f"trend(series[{name!r}]) differs from the mean of points[{name!r}].",
                        fix_hint="With points=, the line is the mean of the replicates: leave the "
                        "series out of series= (or pass series=None).",
                    )
            data[name] = means
        if not data:
            raise ExplainError("trend(points) is empty.", fix_hint="Pass at least one series.")
        single = single or (list(reps) == [""])
    if not data:
        raise ExplainError(
            "trend() needs series= (or points= with raw replicates).",
            fix_hint='e.g. fm.trend([1, 2, 3], {"a": [3, 4, 6]}).',
        )
    for name, arr in data.items():
        if np.isfinite(arr).sum() < 2:
            raise ExplainError(
                f"trend(series[{name!r}]) has fewer than two finite values.",
                fix_hint="Drop the series or use compare().",
            )

    # Numeric and date x are drawn in x order: sort with the series, refuse repeats.
    if x_kind in {"number", "date"}:
        order = np.argsort(xpos, kind="stable")
        if np.any(np.diff(xpos[order]) == 0):
            dup = x_text[int(order[int(np.flatnonzero(np.diff(xpos[order]) == 0)[0])])]
            raise ExplainError(
                f"trend(x) repeats the x value {dup}; a line needs one value per x.",
                fix_hint="Aggregate replicates first: the mean per x in series=, the spread in "
                "band= (with band_label=), or pass the raw replicates as points={name: "
                "[[values at x0], [values at x1], ...]}.",
            )
        if np.any(order != np.arange(n)):
            xpos = xpos[order]
            x_text = [x_text[i] for i in order]
            x_list = list(x)
            x = [x_list[i] for i in order]
            data = {k: v[order] for k, v in data.items()}
            reps = {k: [v[i] for i in order] for k, v in reps.items()}
            if band is not None:
                band = _reorder_band(band, order, n)

    fit_mode: str | None = None
    if fit is True:
        fit_mode = "power" if (log and log_x) else ("log" if log else "linear")
    elif isinstance(fit, str):
        fit_norm = fit.strip().lower()
        if fit_norm not in {"linear", "log", "power"}:
            raise ExplainError(
                f"trend(fit={fit!r}) must be False, True, 'linear', 'log', or 'power'.",
                fix_hint="Pass fit=True (auto-matches linear/log/log-log axes), fit='linear', or fit='log'.",
            )
        fit_mode = fit_norm
    elif fit is not False and fit is not None:
        raise ExplainError(
            f"trend(fit={fit!r}) must be a bool or 'linear'/'log'/'power'.",
            fix_hint="Pass fit=True or fit='linear'.",
        )
    if fit_mode is not None and x_kind == "category":
        raise ExplainError(
            "trend(fit=...) requires numeric or date x values (cannot fit a regression on categories).",
            fix_hint="Pass numeric/date x values or drop fit=.",
        )
    if log_x:
        if x_kind != "number":
            raise ExplainError(
                "trend(log_x=True) needs numeric x (dose, frequency, 1/T).",
                fix_hint="Pass numbers as x, or drop log_x.",
            )
        if xpos.min() <= 0:
            raise ExplainError(
                "trend(log_x=True) needs strictly positive x values.",
                fix_hint="Drop log_x=True or remove the x positions <= 0.",
            )

    names = list(data)
    hl = _names(highlight, names)
    base = _baseline_name(baseline, names, hl, "trend")
    if len(names) - (base is not None) > MAX_COLORED_SERIES and not hl and not facet:
        if not _is_strict():
            facet = True
            _record_adjustment(f"trend(): enabled facet=True for {len(names)} series")
        else:
            raise ExplainError(
                f"trend() got {len(names)} series and no highlight; more than "
                f"{MAX_COLORED_SERIES} coloured lines cannot be told apart or held in mind.",
                fix_hint=f"At most {MAX_COLORED_SERIES} series get a colour: pass highlight=[...] "
                f"with the 1-{MAX_HIGHLIGHTS} series the takeaway names (others turn grey), or "
                f"facet=True for small multiples (up to {MAX_FACETS}).",
                rule="too_many_series",
            )
    if facet and len(names) > MAX_FACETS:
        if not _is_strict():
            keep = list(dict.fromkeys([*hl, *([base] if base else [])]))
            by_span = sorted(
                names,
                key=lambda nm: float(np.nanmax(data[nm]) - np.nanmin(data[nm])),
                reverse=True,
            )
            for nm in by_span:
                if len(keep) >= MAX_FACETS:
                    break
                if nm not in keep:
                    keep.append(nm)
            keep_set = set(keep)
            data = {nm: data[nm] for nm in names if nm in keep_set}
            reps = {nm: reps[nm] for nm in reps if nm in keep_set}
            _record_adjustment(f"trend(facet=True): trimmed {len(names)} series to top {len(data)}")
            names = list(data)
        else:
            raise ExplainError(
                f"trend(facet=True) got {len(names)} series; more than {MAX_FACETS} small "
                "multiples is a wall.",
                fix_hint=f"facet=True takes at most {MAX_FACETS} series: keep the most relevant "
                f"ones, or drop facet= and highlight 1-{MAX_HIGHLIGHTS} in one panel (any number "
                "of the rest stay grey).",
                rule="too_many_series",
            )
    ref = _reference_line(reference, "trend(reference)")
    bands, band_spec, band_modes = _trend_bands(band, data, n)
    event_items: list[tuple[float, str]] = [
        (_parse_x_point(at, x_kind, x_text, "trend(events) key"), str(text))
        for at, text in (events or {}).items()
    ]
    region_items, regions_spec = _parse_trend_regions(regions, x_kind, x_text, log_x=log_x)
    callout_items, callouts_spec = _parse_trend_callouts(
        callouts, x_kind, x_text, log_x=log_x, log_y=log
    )

    all_values = np.concatenate([v[np.isfinite(v)] for v in data.values()])
    rep_values = np.concatenate([r for per_x in reps.values() for r in per_x] or [np.empty(0)])
    if log and (all_values.min() <= 0 or (rep_values.size and rep_values.min() <= 0)):
        raise ExplainError(
            "trend(log=True) needs strictly positive values.",
            fix_hint="Drop log=True or remove non-positive values.",
        )
    if log and ref is not None and ref[0] <= 0:
        raise ExplainError(
            "trend(reference) must be positive on a log axis.",
            fix_hint="Drop the reference or log=True.",
        )
    fmt_fn = _formatter(list(all_values), fmt, unit=unit, log=log)
    # Crossings closer than this on both sides are noise, not a change of order: 3% of
    # the panel's value range (in decades on a log axis), or with raw replicates the 95%
    # half-width of a difference of two means when that is larger (assay noise at ~0%).
    noise = 0.03 * float(np.ptp(np.log10(all_values) if log else all_values))
    spreads = [
        (float(np.std(np.log10(r) if log else r, ddof=1)), r.size)
        for per_x in reps.values()
        for r in per_x
        if r.size >= 2
    ]
    if spreads:
        sd = float(np.median([sp for sp, _ in spreads]))
        n_rep = float(np.median([k for _, k in spreads]))
        noise = max(noise, 1.96 * sd * math.sqrt(2.0 / n_rep))

    _last = _last_finite
    _first = _first_finite

    colored = hl if hl else ([] if facet else names)
    # Coloured series other than the baseline (which is drawn in ink, not a palette colour).
    focus = [nm for nm in colored if nm != base]
    drawn = [base, *focus] if (base is not None and not facet) else colored
    issues: list[dict[str, Any]] = []
    if bands and not band_label:
        issues.append(_interval_issue("trend", "band", "band_label"))

    # x values in facts carry the unit: x_unit=, else the end of x_label ("4 h", not "4").
    x_unit_given = x_unit
    x_unit = _resolve_x_unit(x_unit, x_label, "trend") if x_kind == "number" else None
    xt = [_with_x_unit(t, x_unit) for t in x_text]
    facts: list[str] = []
    described = list((hl or names)[:6])
    if base is not None and base not in described:
        described.append(base)
    for name in described:
        arr = data[name]
        i0, v0 = _first(arr)
        i1, v1 = _last(arr)
        finite = arr[np.isfinite(arr)]
        moved = _change_text(
            v0,
            v1,
            series_range=float(finite.max() - finite.min()),
            unit=unit,
            diff_fmt=_formatter([v1 - v0], fmt, unit=unit),
            log=log,
        )
        peak = int(np.nanargmax(arr))
        shown = name or (label or "value")
        missing = int((~np.isfinite(arr)).sum())
        facts.append(
            # The unit on both values, as change() writes them: "0.0059% → 0.0062%".
            f"{shown}: {_with_unit(fmt_fn(v0), unit)} \N{RIGHTWARDS ARROW} {_with_unit(fmt_fn(v1), unit)} "
            f"from {xt[i0]} to {xt[i1]}"
            + (f" ({moved})" if moved else "")
            + f"; peak {_with_unit(fmt_fn(float(arr[peak])), unit)} at {xt[peak]}"
            + (f"; {missing} of {n} points missing" if missing else "")
        )
    # Alt text: every described series (highlighted ones and the baseline, or all).
    alt_facts = list(facts)
    event_facts: list[str] = []
    spiked: set[str] = set()
    if event_items and x_kind in {"number", "date"}:
        event_series = list(hl) if hl else (list(names) if len(names) <= MAX_COLORED_SERIES else [])
        if base is not None and base not in event_series:
            event_series.append(base)
        event_facts, spiked = _event_facts(
            event_items, event_series, data, xpos, unit=unit, fmt=fmt, log=log, label=label
        )
    spikes = bool(spiked)
    for name in described:
        if name in spiked:
            # An event marks this spike: it is stated against the median before the
            # event (one "usual" level), not also against the whole period's median.
            continue
        # A spike: the peak far above the series' typical level, stated against its median.
        arr = data[name]
        finite = arr[np.isfinite(arr)]
        med = float(np.median(finite))
        peak = int(np.nanargmax(arr))
        top = float(arr[peak])
        if med > 0 and top > 0 and (
            math.log10(top / med) >= 0.7 if log else top >= 5.0 * med
        ):
            spikes = True
            facts.append(
                f"{name or (label or 'value')}: peak {_with_unit(fmt_fn(top), unit)} "
                f"{'on' if x_kind == 'date' else 'at'} {xt[peak]}, "
                f"{_ratio_text(top / med)} its median"
            )
    if hl:
        context = _context_fact(
            [nm for nm in names if nm not in hl and nm != base],
            data,
            spikes=spikes,
            unit=unit,
            fmt=fmt,
            log=log,
        )
        if context:
            facts.append(context)
    if log:
        facts.extend(
            _log_trend_facts(
                data,
                described,
                xpos,
                x_kind,
                log_x,
                label,
                xt,
                x_unit,
                spiked,
                power_names=[*described, *(nm for nm in names if nm not in described)][:6],
            )
        )
    for name in names:
        if name not in described and (~np.isfinite(data[name])).any():
            facts.append(
                f"{name or 'series'}: {int((~np.isfinite(data[name])).sum())} of {n} points missing"
            )
    if base is not None:
        facts.extend(
            _trend_baseline_facts(
                [nm for nm in (hl or names) if nm != base][:6],
                base,
                data,
                xt,
                unit=unit,
                fmt=fmt,
                log=log,
            )
        )
    elif 2 <= len(colored) <= MAX_COLORED_SERIES:
        a = colored[0]
        for b in colored[1:4]:
            both = np.flatnonzero(np.isfinite(data[a]) & np.isfinite(data[b]))
            if not both.size:
                continue
            idx = int(both[-1])
            va, vb = float(data[a][idx]), float(data[b][idx])
            if log:
                ratio = va / vb
                rel = (
                    f"{_ratio_text(ratio)} {b}"
                    if ratio >= 1
                    else f"{_ratio_text(1 / ratio)} below {b}"
                )
                facts.append(f"at {xt[idx]}: {a} is {rel}")
            else:
                gap_fmt = _formatter([abs(va - vb)], fmt, unit=unit)
                if va == vb:
                    facts.append(f"at {xt[idx]}: {a} equals {b}")
                else:
                    facts.append(
                        f"at {xt[idx]}: {a} is {_diff_with_unit(_unsigned(gap_fmt(abs(va - vb))), unit)} "
                        f"{'above' if va > vb else 'below'} {b}"
                    )
    crossing_pairs: list[tuple[str, str]] = []
    if base is not None:
        crossing_pairs = [(nm, base) for nm in (hl or names) if nm != base][:6]
    elif 2 <= len(colored) <= MAX_COLORED_SERIES:
        crossing_pairs = [(colored[0], other) for other in colored[1:]]
    for a, b in crossing_pairs:
        gap = np.log10(data[a]) - np.log10(data[b]) if log else data[a] - data[b]
        crossed = _crossing_fact(a, b, gap, xt, noise)
        if crossed:
            facts.append(crossed)
    facts.extend(event_facts)
    if ref is not None:
        facts.extend(
            _reference_crossings(
                # Highlighted series first, then the grey context ones: a potency claim
                # ("10x below the others") needs every curve's crossing.
                ref,
                [*hl, *(nm for nm in names if nm not in hl)][:6],
                data,
                xpos,
                x_kind,
                xt,
                log,
                log_x,
                label,
                x_unit,
                noise,
                unit,
            )
        )
    if reps:
        dot_word = (points_label or "").strip() or "replicates"
        for name, per_x in reps.items():
            counts = [r.size for r in per_x]
            measured = [c for c in counts if c]
            lo_n, hi_n = min(measured, default=0), max(measured, default=0)
            facts.append(
                f"{name or (label or 'values')}: line is the mean of n = "
                + (f"{lo_n}" if lo_n == hi_n else f"{lo_n}\N{EN DASH}{hi_n}")
                + f" {dot_word} per x"
            )
    if bands:
        facts.append(_interval_mode_text(band_modes, "bands"))
    if fit_mode == "linear":
        facts.extend(
            _linear_fit_facts(
                colored,
                data,
                xpos,
                x_kind=x_kind,
                unit=unit,
                x_unit=x_unit,
                label=label,
            )
        )

    describe = (
        f"{'Small-multiple line charts' if facet else 'Line chart'} of {label or 'values'}"
        + (f" ({unit})" if unit else "")
        + (" on a log scale" if log else "")
        + f" over {x_label or 'x'}"
        + (" (log scale)" if log_x else "")
        + f" from {x_text[0]} to {x_text[-1]}, {len(names)} series"
        + (f", shaded bands show {band_label}" if bands and band_label else "")
    )
    show_markers = n <= 12

    def _setup_x(
        ax: Axes, sizes: _Sizes, theme: Theme = FIGMINT_THEME, *, sparse: bool = False
    ) -> None:
        minus = theme.minus_sign
        if log_x:
            ax.set_xscale("log")
            ax.set_xlim(float(xpos.min()), float(xpos.max()))
            ax.xaxis.set_minor_formatter(NullFormatter())
            _narrow_log_ticks(ax.xaxis, float(xpos.min()), float(xpos.max()), minus, extend=False)
            return
        ax.set_xlim(float(xpos.min()), float(xpos.max()))
        if x_kind == "date":
            locator = mdates.AutoDateLocator(minticks=2, maxticks=3 if sparse else 6)
            ax.xaxis.set_major_locator(locator)
            ax.xaxis.set_major_formatter(_date_formatter(locator))
        elif x_kind == "category":
            limit = 3 if sparse else 8
            step = max(1, math.ceil(len(xpos) / limit))
            shown = list(range(0, len(xpos), step))
            ax.set_xticks(xpos[shown], [_plain(x_text[i], theme) for i in shown])
        else:
            whole = bool(np.all(xpos == np.round(xpos)))
            years = whole and 1000 <= xpos.min() and xpos.max() <= 2200
            if len(xpos) <= 8:
                # Few measured positions (doping 0, 0.5, 1, 2, 4): tick exactly there;
                # labels that would touch are thinned after layout (_fit_ticks).
                ax.xaxis.set_major_locator(FixedLocator(xpos.tolist()))
            else:
                ax.xaxis.set_major_locator(MaxNLocator(nbins=3 if sparse else 6, integer=whole))
            ax.xaxis.set_major_formatter(
                FuncFormatter(
                    lambda v, _p, m=minus, a=ax.xaxis: f"{v:.0f}" if years else _tick_label(v, m, a)
                )
            )

    def _ylimits() -> tuple[float, float]:
        lows = [all_values.min()] + [np.nanmin(b[0]) for b in bands.values()]
        highs = [all_values.max()] + [np.nanmax(b[1]) for b in bands.values()]
        if rep_values.size:
            lows.append(rep_values.min())
            highs.append(rep_values.max())
        if ref is not None:
            lows.append(ref[0])
            highs.append(ref[0])
        lo, hi = float(min(lows)), float(max(highs))
        if log:
            lo = max(lo, float(all_values.min()) / 10.0) if lo <= 0 else lo
            return lo / 1.15, hi * 1.15
        span = (hi - lo) or abs(hi) or 1.0
        bottom = 0.0 if (zero and lo >= 0) else lo - 0.06 * span
        return bottom, hi + 0.08 * span

    def _decorate(
        ctx: _Ctx, ax: Axes, sizes: _Sizes
    ) -> tuple[list[Any], list[Any], tuple[Any, ...] | None]:
        """Reference and event rules.

        Returns (event labels with their rules, other labels, the reference label
        with its line for :func:`_place_reference_label`, or None).
        """
        theme = ctx.theme
        others: list[Any] = []
        events_drawn: list[Any] = []
        ref_drawn: tuple[Any, ...] | None = None
        for r_x0, r_x1, _r_text in region_items:
            ax.axvspan(
                r_x0,
                r_x1,
                color=theme.context_fill,
                alpha=0.12,
                linewidth=0,
                zorder=0,
            )
        if ref is not None:
            ref_line = ax.axhline(
                ref[0], color=theme.ink, linewidth=0.7, linestyle=(0, (3, 2)), zorder=2
            )
            if ref[1]:
                # Inline-tick styles print tick values at the left edge: label on the right.
                right = theme.inline_y_ticks
                ref_note = ax.annotate(
                    _plain(ref[1], theme),
                    (1.0 if right else 0.0, ref[0]),
                    xycoords=("axes fraction", "data"),
                    xytext=(-2.0 if right else 2.0, 2.5),
                    textcoords="offset points",
                    ha="right" if right else "left",
                    va="bottom",
                    fontsize=sizes.small,
                    color=theme.muted,
                    bbox=ctx.halo_bbox(0.1),
                )
                others.append(ref_note)
                ref_drawn = (ref_note, ref_line, ref[1], right)
        lo_x, hi_x = (
            (math.log10(xpos.min()), math.log10(xpos.max())) if log_x else (xpos.min(), xpos.max())
        )
        for pos, text in event_items:
            rule = ax.axvline(pos, color=theme.axis, linewidth=0.6, zorder=1)
            at = math.log10(pos) if (log_x and pos > 0) else pos
            near_right = at > lo_x + 0.7 * (hi_x - lo_x)
            note = ax.annotate(
                _plain(text, theme),
                (pos, 1.0),
                xycoords=("data", "axes fraction"),
                xytext=(-3.0 if near_right else 3.0, -2.0),
                textcoords="offset points",
                ha="right" if near_right else "left",
                va="top",
                fontsize=sizes.small,
                color=theme.muted,
                bbox=ctx.halo_bbox(0.1),
            )
            events_drawn.append((note, rule, pos, text, near_right))
        return events_drawn, others, ref_drawn

    def _measured_points(
        ax: Axes, name: str, col: str, sizes: _Sizes, theme: Theme, *, context: bool = False
    ) -> None:
        """Replicates as pale dots; a marker at each measurement when x is sparse; lone points."""
        if name in reps:
            rx = np.concatenate([np.full(r.size, xpos[i]) for i, r in enumerate(reps[name])])
            ry = np.concatenate(reps[name])
            ax.scatter(
                rx,
                ry,
                s=(2.4 * sizes.scale) ** 2,
                color=col,
                # Context replicates are pale grey already: at the coloured series' alpha
                # they vanish, so they stay grey but nearly opaque.
                alpha=0.3 if not context else 0.7,
                linewidth=0,
                zorder=3,
                clip_on=False,
            )
        arr = data[name]
        mask = np.isfinite(arr) if show_markers else _isolated(arr)
        if mask.any():
            ax.plot(
                xpos[mask],
                arr[mask],
                linestyle="none",
                marker="o",
                markersize=(2.2 if context else 2.8) * sizes.scale,
                color=col,
                markeredgecolor=theme.background,
                markeredgewidth=0.4,
                zorder=3 if context else 4,
                label="_points",
                clip_on=False,
            )

    # ---- single panel with direct labels --------------------------------- #
    def _draw(ctx: _Ctx, ax: Axes) -> Callable[[], None]:
        sz = ctx.sizes
        theme = ctx.theme
        palette = theme.accent_colors if hl else theme.series_colors
        color_of = {
            name: ctx.colors.get(
                name,
                theme.ink
                if name == base
                else (ctx.default_color if not name else palette[i % len(palette)]),
            )
            for i, name in enumerate(drawn)
        }
        effects = ctx.line_effects()
        if log:
            ax.set_yscale("log")
        _value_axis(ax, sz, theme)
        _setup_x(ax, sz, theme)
        ax.set_ylim(*_ylimits())
        y0, y1 = ax.get_ylim()
        if log:
            y0, y1 = _narrow_log_ticks(ax.yaxis, y0, y1, theme.minus_sign, data_hi=y1 / 1.15)
            ax.set_ylim(y0, y1)
        if theme.hide_spines and not log and y0 <= 0.0 <= y1:
            ax.axhline(0.0, color=theme.zero_line, linewidth=theme.zero_line_lw, zorder=2)
        if theme.inline_y_ticks and not log:
            _apply_inline_y_ticks(ax, sz, theme, unit=unit)
        if x_label:
            ax.set_xlabel(_plain(x_label, theme), fontsize=sz.small, color=theme.muted, labelpad=2)

        context = [nm for nm in names if nm not in color_of]
        for name in context:
            line_kw: dict[str, Any] = {
                "color": theme.context_line,
                "linewidth": theme.context_line_lw * sz.scale,
                "zorder": 2,
                "label": "_context",
            }
            if effects is not None:
                line_kw["path_effects"] = effects
            ax.plot(xpos, data[name], **line_kw)
            _measured_points(ax, name, theme.context_line, sz, theme, context=True)
        for name in drawn:
            col = color_of[name]
            if name in bands:
                ax.fill_between(
                    xpos,
                    bands[name][0],
                    bands[name][1],
                    color=col,
                    alpha=0.14,
                    linewidth=0,
                    zorder=2,
                )
            line_kw = {
                "color": col,
                "linewidth": theme.line_lw * sz.scale,
                "zorder": 4,
                "label": name or "_single",
                "solid_capstyle": theme.line_capstyle,
            }
            if effects is not None:
                line_kw["path_effects"] = effects
            ax.plot(xpos, data[name], **line_kw)
            if fit_mode is not None:
                _draw_fit_curve(ax, xpos, data[name], fit_mode=fit_mode, color=col, scale=sz.scale)
            _measured_points(ax, name, col, sz, theme)
            i1, v1 = _last(data[name])
            ax.plot(
                [xpos[i1]],
                [v1],
                marker="o",
                markersize=3.6 * sz.scale,
                color=col,
                markeredgecolor=theme.background,
                markeredgewidth=0.6,
                zorder=5,
                label="_end",
                clip_on=False,
            )
        events_drawn, other_notes, ref_drawn = _decorate(ctx, ax, sz)

        label_context = bool(context) and len(names) <= 8
        entries: list[tuple[str, float, float, str, str, str]] = []
        for name in drawn:
            i1, v1 = _last(data[name])
            if not name:
                if not end_values:
                    continue
                text = _with_unit(fmt_fn(v1), unit)
            else:
                text = f"{name}  {fmt_fn(v1)}" if end_values else name
            weight = "normal" if name == base else "bold"
            entries.append(
                (text, float(xpos[i1]), v1, ctx.text_color(color_of[name]), weight, color_of[name])
            )
        if label_context:
            for name in context:
                i1, v1 = _last(data[name])
                entries.append(
                    (name, float(xpos[i1]), v1, theme.muted, "normal", theme.context_line)
                )
        elif context:
            mid = sorted(context, key=lambda nm: _last(data[nm])[1])[len(context) // 2]
            i1, v1 = _last(data[mid])
            entries.append(
                (
                    f"{len(context)} others",
                    float(xpos[i1]),
                    v1,
                    theme.muted,
                    "normal",
                    theme.context_line,
                )
            )

        annotations = [
            ax.annotate(
                _plain(text, theme),
                (px, py),
                xytext=(6.0, 0.0),
                textcoords="offset points",
                ha="left",
                va="center",
                fontsize=sz.small,
                color=text_color,
                fontweight=weight,
                annotation_clip=False,
            )
            for text, px, py, text_color, weight, _ in entries
        ]

        def _finish() -> None:
            _relax_end_labels()
            _clear_inline_ticks(ctx, ax)
            _place_reference_label(ctx, ax, ref_drawn, annotations)
            _place_event_labels(ctx, ax, events_drawn, [*annotations, *other_notes])
            if region_items:
                _place_region_labels(ctx, ax, region_items, log_x=log_x)
            if callout_items:
                _place_callouts(ctx, ax, callout_items)

        def _relax_end_labels() -> None:
            if not annotations:
                return
            renderer = ctx.fig.canvas.get_renderer()
            box = ax.get_window_extent(renderer)
            k = ctx.pt_per_px
            ys = np.array([ax.transData.transform((e[1], e[2]))[1] * k for e in entries])
            placed = _relax_positions_pt(
                ys, sz.small * 1.22, box.y0 * k + sz.small * 0.4, box.y1 * k - sz.small * 0.4
            )
            for ann, entry, y0, y1 in zip(annotations, entries, ys, placed, strict=True):
                shift = float(y1 - y0)
                ann.set_position((6.0, shift))
                if abs(shift) > sz.small * 0.75:
                    ax.annotate(
                        "",
                        (entry[1], entry[2]),
                        xytext=(5.0, shift),
                        textcoords="offset points",
                        arrowprops={
                            "arrowstyle": "-",
                            "color": entry[5],
                            "linewidth": 0.5,
                            "shrinkA": 0,
                            "shrinkB": 2.5,
                        },
                        annotation_clip=False,
                    )

        return _finish

    # ---- small multiples -------------------------------------------------- #
    def _facet_grid(cell_width_mm: float) -> tuple[int, int]:
        ncols = max(1, min(len(names), int(cell_width_mm // 30.0), 4))
        return math.ceil(len(names) / ncols), ncols

    def _facet_frames(ctx: _Ctx, ax: Axes, rect: Bbox) -> list[tuple[Axes, Bbox]]:
        sz = ctx.sizes
        theme = ctx.theme
        effects = ctx.line_effects()
        ax.remove()
        nrows, ncols = _facet_grid(ctx.cell_width_mm)
        px_per_mm = float(ctx.fig.dpi) / 25.4
        gap_x, gap_y = 4.0 * px_per_mm * sz.scale, 4.5 * px_per_mm * sz.scale
        cell_w = (rect.width - gap_x * (ncols - 1)) / ncols
        cell_h = (rect.height - gap_y * (nrows - 1)) / nrows
        ylim = _ylimits()
        frames: list[tuple[Axes, Bbox]] = []
        facet_events: list[tuple[Axes, list[Any], list[Any]]] = []
        first: Axes | None = None
        for idx, name in enumerate(names):
            r, c = divmod(idx, ncols)
            x0 = rect.x0 + c * (cell_w + gap_x)
            y1 = rect.y1 - r * (cell_h + gap_y)
            sub = Bbox.from_extents(x0, y1 - cell_h, x0 + cell_w, y1)
            child = ctx.fig.add_axes([0.1, 0.1, 0.5, 0.5], sharey=first)
            first = first or child
            ctx.tag(child)
            ctx.extra_axes.append(child)
            if log:
                child.set_yscale("log")
            _value_axis(child, sz, theme, nbins=3)
            _setup_x(child, sz, theme, sparse=True)
            child.set_ylim(*ylim)
            if log:
                child.set_ylim(
                    *_narrow_log_ticks(
                        child.yaxis,
                        ylim[0],
                        ylim[1],
                        theme.minus_sign,
                        max_ticks=4,
                        data_hi=ylim[1] / 1.15,
                    )
                )
            if name == base:
                col = ctx.colors.get(name, theme.ink)
            else:
                col = theme.accent_colors[hl.index(name)] if name in hl else theme.default_color
            ghost_col = theme.context_fill
            for other in names:
                if other != name:
                    child.plot(
                        xpos,
                        data[other],
                        color=ghost_col,
                        linewidth=0.7 * sz.scale,
                        zorder=1,
                        label="_ghost",
                    )
            if name in bands:
                child.fill_between(
                    xpos,
                    bands[name][0],
                    bands[name][1],
                    color=col,
                    alpha=0.14,
                    linewidth=0,
                    zorder=2,
                )
            line_kw: dict[str, Any] = {
                "color": col,
                "linewidth": theme.facet_line_lw * sz.scale,
                "zorder": 3,
                "label": "_series",
                "solid_capstyle": theme.line_capstyle,
            }
            if effects is not None:
                line_kw["path_effects"] = effects
            child.plot(xpos, data[name], **line_kw)
            if fit_mode is not None:
                _draw_fit_curve(child, xpos, data[name], fit_mode=fit_mode, color=col, scale=sz.scale)
            _measured_points(child, name, col, sz, theme)
            i1, v1 = _last(data[name])
            child.plot(
                [xpos[i1]],
                [v1],
                marker="o",
                markersize=3.2 * sz.scale,
                color=col,
                markeredgecolor=theme.background,
                markeredgewidth=0.6,
                zorder=4,
                clip_on=False,
                label="_end",
            )
            child_events, child_notes, child_ref = _decorate(ctx, child, sz)
            facet_events.append((child, child_events, child_notes, child_ref))
            child.set_title(
                _plain(f"{name}  {fmt_fn(v1)}" if end_values else name, theme),
                loc="left",
                fontsize=sz.small,
                fontweight="bold",
                color=ctx.text_color(col) if name in hl else theme.ink,
                pad=3.0,
            )
            child.tick_params(axis="y", labelleft=(c == 0))
            last_in_column = idx + ncols >= len(names)
            child.tick_params(axis="x", labelbottom=last_in_column)
            frames.append((child, sub))

        def _equalize() -> None:
            """Give every small multiple the same plot width (only column one has y labels)."""
            fig_w = ctx.fig.bbox.width
            gutter = frames[0][0].get_position().x0 * fig_w - rect.x0
            plot_w = (rect.width - gutter - gap_x * (ncols - 1)) / ncols
            for idx, (child, _sub) in enumerate(frames):
                pos = child.get_position()
                left = rect.x0 + gutter + (idx % ncols) * (plot_w + gap_x)
                child.set_position([left / fig_w, pos.y0, plot_w / fig_w, pos.height])

        ctx.finishers.append(_equalize)
        for idx_f, (child, child_events, child_notes, child_ref) in enumerate(facet_events):
            if child_ref is not None:
                ctx.finishers.append(
                    functools.partial(
                        _place_reference_label,
                        ctx,
                        child,
                        child_ref,
                        [getattr(child, "_left_title", None)],
                    )
                )
            if child_events:
                ctx.finishers.append(
                    functools.partial(
                        _place_event_labels,
                        ctx,
                        child,
                        child_events,
                        [*child_notes, getattr(child, "_left_title", None)],
                    )
                )
            if idx_f == 0 and region_items:
                ctx.finishers.append(
                    functools.partial(_place_region_labels, ctx, child, region_items, log_x=log_x)
                )
            if idx_f == 0 and callout_items:
                ctx.finishers.append(functools.partial(_place_callouts, ctx, child, callout_items))
        return frames

    series_spec: Any
    if single:
        series_spec = None if "" in reps else data[""]
    else:
        series_spec = {k: v for k, v in data.items() if k not in reps} or None
    spec = _base_spec(
        title,
        label,
        unit,
        x=[
            (int(v) if float(v) == int(v) else float(v))
            if _is_number(v)
            else (v if isinstance(v, str) else _jsonable(v))
            for v in x
        ],
        series=_jsonable(series_spec),
        x_label=x_label,
        x_unit=x_unit_given,
        highlight=hl or None,
        baseline=base,
        facet=facet or None,
        band=band_spec or None,
        band_label=band_label,
        points={k: [r.tolist() for r in v] for k, v in reps.items()} or None,
        points_label=points_label,
        events={str(_jsonable(k)): str(v) for k, v in (events or {}).items()} or None,
        regions=regions_spec or None,
        callouts=callouts_spec or None,
        reference=list(ref) if ref else None,
        zero=zero or None,
        log=log or None,
        log_x=log_x or None,
        fit=fit if fit else None,
        end_values=None if end_values else False,
        fmt=fmt,
    )
    dot_label = (points_label or "").strip() or "replicates"
    fit_note = (
        f"dashed: { {'linear': 'linear fit', 'log': 'log-linear fit', 'power': 'power-law fit'}[fit_mode] }"
        if fit_mode is not None
        else None
    )
    notes = [
        nt
        for nt in (
            f"band: {band_label}" if bands and band_label else None,
            f"dots: {dot_label}" if reps else None,
            fit_note,
        )
        if nt
    ]

    if facet:

        def _facet_height(
            cell_width_mm: float, _m: _Measure, _s: _Sizes, _t: Theme = FIGMINT_THEME
        ) -> float:
            nrows, _ = _facet_grid(cell_width_mm)
            return nrows * 27.0 + (nrows - 1) * 4.5 + (4.0 if x_label else 0.0)

        return Panel(
            kind="trend",
            title=title,
            label=label,
            unit=unit,
            spec=spec,
            facts=facts,
            describe=describe,
            issues=issues,
            _height_mm=_facet_height,
            _min_height_mm=lambda w, _m, _s, _t: (
                _facet_grid(w)[0] * 22.0 + (_facet_grid(w)[0] - 1) * 4.5 + (4.0 if x_label else 0.0)
            ),
            _draw=lambda _ctx, _ax: None,
            _frames=_facet_frames,
            measure_note="; ".join(notes) or None,
            alt_facts=alt_facts,
        )

    return Panel(
        kind="trend",
        title=title,
        label=label,
        unit=unit,
        spec=spec,
        facts=facts,
        describe=describe,
        issues=issues,
        _height_mm=lambda w, _m, _s, _t: min(54.0, max(36.0, 0.40 * w)) + (4.0 if x_label else 0.0),
        _min_height_mm=lambda _w, _m, _s, _t: 30.0 + (4.0 if x_label else 0.0),
        stretch=True,
        _draw=_draw,
        measure_note="; ".join(notes) or None,
        alt_facts=alt_facts,
        color_items=tuple(nm for nm in names if nm),
        color_focus=tuple(nm for nm in focus if nm),
        color_mode="highlight" if hl else "series",
        uses_default="" in colored,
        color_baseline=base,
    )


def _place_event_labels(ctx: _Ctx, ax: Axes, events: Sequence[Any], avoid: Sequence[Any]) -> None:
    """Move each event label to a spot where it covers no line, marker or other label.

    Tries the top of the rule on its preferred side, then the other side, then just
    under the top gridline, then the bottom of the plot. When every spot is taken the
    first is kept and an ``event_label_collides`` warning says to shorten the label.
    """
    if not events:
        return
    renderer = ctx.fig.canvas.get_renderer()
    frame = ax.get_window_extent(renderer)
    rules = [rule for _note, rule, _pos, _text, _right in events]
    paths = _data_paths(ax, rules)
    taken = [
        t.get_window_extent(renderer)
        for t in [*avoid, *ctx.fig.texts]
        if t is not None and t.get_visible() and t.get_text()
    ]
    taken += [box for axis in (ax.xaxis, ax.yaxis) for _, box in _tick_label_boxes(axis, renderer)]
    # A label may reach left over the empty top of the y-tick gutter, never past it.
    gutter = ax.yaxis.get_tightbbox(renderer)
    left_limit = min(frame.x0, gutter.x0) if gutter is not None else frame.x0
    y0, y1 = ax.get_ylim()
    ticks = [float(t) for t in ax.yaxis.get_majorticklocs() if min(y0, y1) < t < max(y0, y1)]
    upper = sorted(ticks, reverse=y1 > y0)
    frac_top = None
    if upper:
        top_tick = upper[0]
        display = ax.transData.transform((ax.get_xlim()[0], top_tick))
        frac_top = float(ax.transAxes.inverted().transform(display)[1])
    for note, _rule, pos, text, near_right in events:
        sides = [near_right, not near_right]
        spots = [(1.0, "top", side) for side in sides]
        if frac_top is not None and 0.2 < frac_top < 0.98:
            spots += [(frac_top, "top", side) for side in sides]
        spots += [(0.0, "bottom", side) for side in sides]
        # Last resort before warning: just above the plot frame, beside the rule's top.
        spots += [(1.0, "above", side) for side in sides]
        chosen = None
        for frac, va, right in spots:
            note.xy = (pos, frac)
            note.set_verticalalignment("bottom" if va == "above" else va)
            note.set_horizontalalignment("right" if right else "left")
            dy = -2.0 if va == "top" else (2.0 if va == "bottom" else 1.0)
            note.set_position((-3.0 if right else 3.0, dy))
            box = note.get_window_extent(renderer).expanded(1.0, 1.0)
            inside = box.x0 >= left_limit - 1 and box.x1 <= frame.x1 + 1
            if va == "above":
                inside = inside and box.y1 <= ctx.fig.bbox.y1
            clear = not any(box.overlaps(other) for other in taken)
            free = not any(path.intersects_bbox(box, filled=False) for path in paths)
            if inside and clear and free:
                chosen = box
                break
        if chosen is None:
            frac, va, right = spots[0]
            note.xy = (pos, frac)
            note.set_verticalalignment(va)
            note.set_horizontalalignment("right" if right else "left")
            note.set_position((-3.0 if right else 3.0, -2.0))
            chosen = note.get_window_extent(renderer)
            ctx.issues.append(
                _issue(
                    "event_label_collides",
                    "warning",
                    f"The event label {text!r} covers a line or another label wherever it is "
                    "placed in this panel.",
                    "Shorten the event label (one or two words, e.g. 'v2.3'), move the detail "
                    'to note=, or give the panel a full-width row with layout=[["a"], ["b"]].',
                    panel=ctx.key,
                )
            )
        taken.append(chosen)


def _reference_in_margin(
    ctx: _Ctx,
    ax: Axes,
    note: Any,
    text: str,
    y_value: float,
    avoid: Sequence[Any],
    taken: Sequence[Bbox],
    paths: Sequence[Any],
) -> bool:
    """Put a reference label in the end-label column right of the plot, beside the line.

    The column is as wide as the end labels already make it (the panel's cell is
    sized to them), so the label never reaches into a neighbouring panel. Returns
    False, leaving ``note`` to the caller, when no spot there is free.
    """
    renderer = ctx.fig.canvas.get_renderer()
    frame = ax.get_window_extent(renderer)
    ends = [
        t.get_window_extent(renderer).x1
        for t in avoid
        if t is not None and t.get_visible() and t.get_text()
    ]
    col_right = max([frame.x1, *ends])
    k = ctx.pt_per_px
    dx = 6.0
    room_pt = (col_right - frame.x1) * k - dx
    if room_pt <= 0:
        return False
    size = float(note.get_fontsize())
    shown = [text]
    wrapped = ctx.measure.wrap(text, room_pt, size)
    if len(wrapped) == 2:
        shown.append("\n".join(wrapped))
    for candidate in shown:
        note.set_text(_plain(candidate, ctx.theme))
        note.xy = (1.0, y_value)
        note.set_horizontalalignment("left")
        for va, dy in (("center", 0.0), ("bottom", 1.5), ("top", -1.5)):
            note.set_verticalalignment(va)
            note.set_position((dx, dy))
            box = note.get_window_extent(renderer)
            inside = (
                box.x1 <= col_right + 1
                and box.y0 >= frame.y0 - 1
                and box.y1 <= frame.y1 + 0.5 * ctx.sizes.small / k
            )
            clear = not any(box.overlaps(other) for other in taken)
            free = not any(path.intersects_bbox(box, filled=False) for path in paths)
            if inside and clear and free:
                return True
    return False


def _place_reference_label(ctx: _Ctx, ax: Axes, ref: Any, avoid: Sequence[Any]) -> None:
    """Move a reference-line label to a spot where it covers no line, marker or label.

    ``ref`` is ``(note, line, text, prefer_right)``. Tries the preferred end above the
    line, the other end above it, both ends below it, then the middle, one third and
    two thirds along it (above, then below). Dense lines (daily data) leave none of
    those free: the label then goes in the right margin beside the line's end, in the
    column the end labels use (on one line or wrapped onto two), if that is free of
    them. Only when that fails too is the first spot kept and a
    ``reference_label_collides`` warning says what to change.
    """
    if ref is None:
        return
    note, line, text, prefer_right = ref
    renderer = ctx.fig.canvas.get_renderer()
    frame = ax.get_window_extent(renderer)
    paths = _data_paths(ax, [line])
    taken = [
        t.get_window_extent(renderer)
        for t in [*avoid, *ax.texts, *ctx.fig.texts]
        if t is not None and t is not note and t.get_visible() and t.get_text()
    ]
    taken += [box for axis in (ax.xaxis, ax.yaxis) for _, box in _tick_label_boxes(axis, renderer)]
    # Spots as (x as a fraction of the axes, above the line?): the ends first, then
    # inside the span, where a crowded narrow panel often still has room.
    ends = [1.0 if prefer_right else 0.0, 0.0 if prefer_right else 1.0]
    spots = [(at, above) for above in (True, False) for at in ends]
    spots += [(at, above) for at in (0.5, 1 / 3, 2 / 3) for above in (True, False)]
    y_value = note.xy[1]

    def _put(at: float, above: bool) -> None:
        note.xy = (at, y_value)
        note.set_horizontalalignment("right" if at == 1.0 else "left" if at == 0.0 else "center")
        note.set_verticalalignment("bottom" if above else "top")
        dx = -2.0 if at == 1.0 else 2.0 if at == 0.0 else 0.0
        note.set_position((dx, 2.5 if above else -2.5))

    for at, above in spots:
        _put(at, above)
        box = note.get_window_extent(renderer)
        inside = (
            box.x0 >= frame.x0 - 1
            and box.x1 <= frame.x1 + 1
            and box.y0 >= frame.y0 - 1
            and box.y1 <= frame.y1 + 1
        )
        clear = not any(box.overlaps(other) for other in taken)
        free = not any(path.intersects_bbox(box, filled=False) for path in paths)
        if inside and clear and free:
            return
    if _reference_in_margin(ctx, ax, note, text, y_value, avoid, taken, paths):
        return
    note.set_text(_plain(text, ctx.theme))
    _put(spots[0][0], True)
    ctx.issues.append(
        _issue(
            "reference_label_collides",
            "warning",
            f"The reference label {text!r} covers a line or another label wherever it is "
            "placed in this panel.",
            "Shorten the reference label to one or two words, or pass the reference as a "
            'bare number (reference=1.0) and name the line in note= ("dashed line: ...").',
            panel=ctx.key,
        )
    )


def _reorder_band(band: Any, order: np.ndarray, n: int) -> Any:
    """Apply the x sort to a band given in any accepted form (numbers stay as they are)."""

    def _one(entry: Any) -> Any:
        if _is_number(entry):
            return entry
        try:
            arr = np.asarray(
                [[np.nan if v is None else float(v) for v in part] for part in entry]
                if not isinstance(entry, np.ndarray)
                else entry,
                dtype=float,
            )
        except (TypeError, ValueError):
            try:
                arr = np.asarray([np.nan if v is None else float(v) for v in entry], dtype=float)
            except (TypeError, ValueError):
                return entry  # reported by _trend_bands
        if arr.ndim == 2 and arr.shape == (2, n):
            return arr[:, order]
        if arr.ndim == 1 and arr.size == n:
            return arr[order]
        return entry

    if _has_items(band) and not _is_one_dimensional(band):
        return {k: _one(v) for k, v in _pairs(band)}
    return _one(band)


MAX_CALLOUTS = 4


def _parse_x_point(val: Any, x_kind: str, x_text: Sequence[str], what: str) -> float:
    """Parse a single x coordinate for events, regions, or callouts on trend()."""
    if x_kind == "number":
        try:
            pos = _to_float(float(val) if isinstance(val, str) else val, what)
        except ValueError as exc:
            raise ExplainError(
                f"{what} {val!r} is not a number on this numeric x axis.",
                fix_hint="Use a numeric x value matching the x axis.",
            ) from exc
        if not math.isfinite(pos):
            raise ExplainError(
                f"{what} {val!r} must be finite.",
                fix_hint="Use a finite numeric x value.",
            )
        return pos
    if x_kind == "date":
        try:
            pos = float(mdates.date2num(np.datetime64(val)))
        except (ValueError, TypeError) as exc:
            raise ExplainError(
                f"{what} {val!r} is not a valid date.",
                fix_hint="Use an ISO date such as '2026-03-01' or a date/datetime object.",
            ) from exc
        return pos
    if str(val) not in x_text:
        raise ExplainError(
            f"{what} {val!r} is not one of the x labels.",
            fix_hint="Use an x value exactly as it appears in x.",
        )
    return float(x_text.index(str(val)))


def _parse_trend_regions(
    regions: Sequence[tuple[Any, Any, str]] | None,
    x_kind: str,
    x_text: Sequence[str],
    *,
    log_x: bool,
) -> tuple[list[tuple[float, float, str]], list[list[Any]]]:
    """Validate ``trend(regions=[(x0, x1, label), ...])``."""
    if regions is None:
        return [], []
    if isinstance(regions, (str, bytes, Mapping)) or not isinstance(regions, Sequence):
        raise ExplainError(
            f"trend(regions) must be a list of (x0, x1, label) tuples, got {type(regions).__name__}.",
            fix_hint='e.g. regions=[(2, 5, "warmup")] or regions=[("2026-01-01", "2026-03-01", "Q1")].',
        )
    parsed: list[tuple[float, float, str]] = []
    spec_out: list[list[Any]] = []
    for idx, item in enumerate(regions):
        if isinstance(item, (str, bytes, Mapping)) or not isinstance(item, Sequence) or len(item) != 3:
            raise ExplainError(
                f"trend(regions[{idx}]) must be a (x0, x1, label) 3-tuple, got {item!r}.",
                fix_hint='Pass (x0, x1, "short label") for each shaded region.',
            )
        raw0, raw1, label = item
        p0 = _parse_x_point(raw0, x_kind, x_text, f"trend(regions[{idx}]) start")
        p1 = _parse_x_point(raw1, x_kind, x_text, f"trend(regions[{idx}]) end")
        if p0 >= p1:
            raise ExplainError(
                f"trend(regions[{idx}]) start {raw0!r} must be strictly less than end {raw1!r}.",
                fix_hint="Order each region tuple as (x0, x1, label) with x0 < x1.",
            )
        if log_x and p0 <= 0:
            raise ExplainError(
                f"trend(regions[{idx}]) requires positive x bounds on a log_x axis.",
                fix_hint="Use positive x0 and x1 values when log_x=True.",
            )
        text = str(label).strip()
        parsed.append((p0, p1, text))
        spec_out.append([_jsonable(raw0), _jsonable(raw1), text])
    return parsed, spec_out


def _parse_trend_callouts(
    callouts: Sequence[tuple[Any, float, str]] | None,
    x_kind: str,
    x_text: Sequence[str],
    *,
    log_x: bool,
    log_y: bool,
) -> tuple[list[tuple[float, float, str]], list[list[Any]]]:
    """Validate ``trend(callouts=[(x, y, note), ...])`` (max 4)."""
    if callouts is None:
        return [], []
    if isinstance(callouts, (str, bytes, Mapping)) or not isinstance(callouts, Sequence):
        raise ExplainError(
            f"trend(callouts) must be a list of (x, y, note) tuples, got {type(callouts).__name__}.",
            fix_hint='e.g. callouts=[(5, 1200, "peak load")].',
        )
    if len(callouts) > MAX_CALLOUTS:
        raise ExplainError(
            f"trend(callouts) got {len(callouts)} callouts; at most {MAX_CALLOUTS} stay legible.",
            fix_hint=f"Keep at most {MAX_CALLOUTS} callouts for the most important points.",
        )
    parsed: list[tuple[float, float, str]] = []
    spec_out: list[list[Any]] = []
    for idx, item in enumerate(callouts):
        if isinstance(item, (str, bytes, Mapping)) or not isinstance(item, Sequence) or len(item) != 3:
            raise ExplainError(
                f"trend(callouts[{idx}]) must be an (x, y, note) 3-tuple, got {item!r}.",
                fix_hint='Pass (x, y, "short note") for each callout.',
            )
        raw_x, raw_y, note = item
        px = _parse_x_point(raw_x, x_kind, x_text, f"trend(callouts[{idx}]) x")
        py = _to_float(raw_y, f"trend(callouts[{idx}]) y")
        if not math.isfinite(py):
            raise ExplainError(
                f"trend(callouts[{idx}]) y={raw_y!r} must be finite.",
                fix_hint="Pass a finite numeric y coordinate for the callout anchor.",
            )
        if log_x and px <= 0:
            raise ExplainError(
                f"trend(callouts[{idx}]) x must be positive on a log_x axis.",
                fix_hint="Use positive x values when log_x=True.",
            )
        if log_y and py <= 0:
            raise ExplainError(
                f"trend(callouts[{idx}]) y must be positive on a log y axis.",
                fix_hint="Use positive y values when log=True.",
            )
        text = str(note).strip()
        if not text:
            raise ExplainError(
                f"trend(callouts[{idx}]) has an empty note.",
                fix_hint='Pass a short descriptive note, e.g. (5, 1200, "v2.3 regression").',
            )
        parsed.append((px, py, text))
        spec_out.append([_jsonable(raw_x), float(py), text])
    return parsed, spec_out


def _visible_text_boxes(ctx: _Ctx, exclude: Any = None) -> list[Bbox]:
    """Window bounding boxes of all visible non-empty Text artists on the figure."""
    from matplotlib.text import Text

    renderer = ctx.fig.canvas.get_renderer()
    return [
        t.get_window_extent(renderer)
        for t in ctx.fig.findobj(Text)
        if t is not exclude and t.get_visible() and t.get_text().strip() and t.get_alpha() != 0
    ]


def _audit_line_paths(ax: Axes) -> list[Any]:
    """Display-space paths of visible non-grid lines on ``ax`` (matching audit_figure)."""
    grid = {id(g) for g in (*ax.get_xgridlines(), *ax.get_ygridlines())}
    return [
        ln.get_transform().transform_path(ln.get_path())
        for ln in ax.lines
        if id(ln) not in grid
        and ln.get_visible()
        and len(ln.get_xdata()) >= 2
        and ln.get_linestyle() not in ("None", "", " ")
        and ln.get_linewidth() > 0
    ]


def _pad_bbox(bb: Bbox, pad: float = 1.5) -> Bbox:
    return Bbox.from_extents(bb.x0 - pad, bb.y0 - pad, bb.x1 + pad, bb.y1 + pad)


def _place_region_labels(
    ctx: _Ctx,
    ax: Axes,
    regions: Sequence[tuple[float, float, str]],
    *,
    log_x: bool = False,
) -> None:
    """Place muted top labels centered inside shaded regions, avoiding lines and text."""
    sz = ctx.sizes
    theme = ctx.theme
    renderer = ctx.fig.canvas.get_renderer()
    frame = ax.get_window_extent(renderer)
    fig_box = ctx.fig.bbox
    paths = _audit_line_paths(ax)
    taken = _visible_text_boxes(ctx)
    x_lo, x_hi = sorted(ax.get_xlim())
    for r0, r1, text in regions:
        if not text:
            continue
        vis0 = max(r0, x_lo)
        vis1 = min(r1, x_hi)
        if vis0 >= vis1:
            vis0, vis1 = r0, r1
        mid_x = math.sqrt(vis0 * vis1) if (log_x and vis0 > 0 and vis1 > 0) else 0.5 * (vis0 + vis1)
        note = ax.annotate(
            _plain(text, theme),
            (mid_x, 1.0),
            xycoords=("data", "axes fraction"),
            xytext=(0.0, -3.0),
            textcoords="offset points",
            ha="center",
            va="top",
            fontsize=sz.small,
            color=theme.muted,
            zorder=6,
            bbox=ctx.halo_bbox(0.08, alpha=0.82),
            annotation_clip=False,
        )
        cands = [
            (mid_x, 1.0, "center", "top", 0.0, -3.0, True),
            (mid_x, 0.88, "center", "top", 0.0, 0.0, True),
            (mid_x, 0.0, "center", "bottom", 0.0, 3.0, True),
            (vis0, 1.0, "left", "top", 3.0, -3.0, True),
            (vis1, 1.0, "right", "top", -3.0, -3.0, True),
            (vis0, 0.0, "left", "bottom", 3.0, 3.0, True),
            (vis1, 0.0, "right", "bottom", -3.0, 3.0, True),
            (mid_x, 0.72, "center", "top", 0.0, 0.0, True),
            (mid_x, 0.50, "center", "center", 0.0, 0.0, True),
            (mid_x, 0.25, "center", "bottom", 0.0, 0.0, True),
            (mid_x, 1.0, "center", "bottom", 0.0, 2.5, False),
        ]
        best = cands[0]
        best_score = (999, 999, 999, 999)
        for cx, yfrac, ha, va, dx, dy, inside_pref in cands:
            note.xy = (cx, yfrac)
            note.set_ha(ha)
            note.set_va(va)
            note.set_position((dx, dy))
            bb = note.get_window_extent(renderer)
            pbb = _pad_bbox(bb, 1.5)
            out_fig = int(
                not (
                    bb.x0 >= fig_box.x0 + 2
                    and bb.x1 <= fig_box.x1 - 2
                    and bb.y0 >= fig_box.y0 + 2
                    and bb.y1 <= fig_box.y1 - 2
                )
            )
            out_frame = int(
                not (
                    bb.x0 >= frame.x0 - 2
                    and bb.x1 <= frame.x1 + 2
                    and bb.y0 >= frame.y0 - 2
                    and bb.y1 <= frame.y1 + 2
                )
            )
            n_line = sum(1 for p in paths if p.intersects_bbox(bb, filled=False))
            n_text = sum(1 for tb in taken if pbb.overlaps(tb))
            score = (out_fig, n_line, n_text, out_frame if inside_pref else out_frame + 1)
            if score < best_score:
                best_score = score
                best = (cx, yfrac, ha, va, dx, dy, inside_pref)
            if score == (0, 0, 0, 0):
                break
        note.xy = (best[0], best[1])
        note.set_ha(best[2])
        note.set_va(best[3])
        note.set_position((best[4], best[5]))
        taken.append(note.get_window_extent(renderer))


def _callout_arrow_segment(
    ax_px: float, ay_px: float, bb: Bbox
) -> tuple[float, float, Any | None]:
    """Return ``(start_x_px, start_y_px, trimmed_path)`` from nearest edge of ``bb`` to anchor."""
    from matplotlib.path import Path as MplPath

    px = min(max(ax_px, bb.x0), bb.x1)
    py = min(max(ay_px, bb.y0), bb.y1)
    vx, vy = ax_px - px, ay_px - py
    seg_len = math.hypot(vx, vy)
    if seg_len < 7.0:
        return px, py, None
    t0 = min(0.35, 3.0 / seg_len)
    t1 = max(t0 + 0.05, 1.0 - 7.5 / seg_len)
    s0 = (px + t0 * vx, py + t0 * vy)
    s1 = (px + t1 * vx, py + t1 * vy)
    return px, py, MplPath([s0, s1])


def _two_line_wrap(text: str) -> str | None:
    """Split a multi-word callout near its middle onto two lines; None for single words."""
    words = text.split()
    if len(words) < 2 or "\n" in text:
        return None
    best_i = min(
        range(1, len(words)),
        key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))),
    )
    return " ".join(words[:best_i]) + "\n" + " ".join(words[best_i:])


def _place_callouts(
    ctx: _Ctx,
    ax: Axes,
    callouts: Sequence[tuple[float, float, str]],
) -> None:
    """Place direct callout annotations with leader arrows, avoiding lines, text, and arrow crossings."""
    sz = ctx.sizes
    theme = ctx.theme
    renderer = ctx.fig.canvas.get_renderer()
    frame = ax.get_window_extent(renderer)
    fig_box = ctx.fig.bbox
    paths = _audit_line_paths(ax)
    taken = _visible_text_boxes(ctx)
    k = ctx.pt_per_px
    arrow_kw = {
        "arrowstyle": "-|>,head_length=0.35,head_width=0.2",
        "color": theme.muted,
        "linewidth": 0.75 * sz.scale,
        "shrinkA": 2.0,
        "shrinkB": 3.5,
    }
    base_offsets = [
        # Tier 1: short clean offsets
        (12.0, 14.0, "left", "bottom"),
        (-12.0, 14.0, "right", "bottom"),
        (12.0, -14.0, "left", "top"),
        (-12.0, -14.0, "right", "top"),
        (0.0, 18.0, "center", "bottom"),
        (0.0, -18.0, "center", "top"),
        (18.0, 0.0, "left", "center"),
        (-18.0, 0.0, "right", "center"),
        # Tier 2: medium & shifted-center offsets
        (20.0, 22.0, "left", "bottom"),
        (-20.0, 22.0, "right", "bottom"),
        (20.0, -22.0, "left", "top"),
        (-20.0, -22.0, "right", "top"),
        (14.0, -22.0, "center", "top"),
        (-14.0, -22.0, "center", "top"),
        (14.0, 22.0, "center", "bottom"),
        (-14.0, 22.0, "center", "bottom"),
        (0.0, 28.0, "center", "bottom"),
        (0.0, -28.0, "center", "top"),
        (28.0, 10.0, "left", "bottom"),
        (-28.0, 10.0, "right", "bottom"),
        (28.0, -10.0, "left", "top"),
        (-28.0, -10.0, "right", "top"),
        # Tier 3: wider fallback offsets
        (0.0, 42.0, "center", "bottom"),
        (0.0, -42.0, "center", "top"),
        (32.0, 34.0, "left", "bottom"),
        (-32.0, 34.0, "right", "bottom"),
        (32.0, -34.0, "left", "top"),
        (-32.0, -34.0, "right", "top"),
        (44.0, 0.0, "left", "center"),
        (-44.0, 0.0, "right", "center"),
        (0.0, 56.0, "center", "bottom"),
        (0.0, -56.0, "center", "top"),
    ]
    for cx, cy, text in callouts:
        disp = ax.transData.transform((cx, cy))
        ax_px, ay_px = float(disp[0]), float(disp[1])
        fx, fy = ax.transAxes.inverted().transform(disp)
        note = ax.annotate(
            _plain(text, theme),
            xy=(cx, cy),
            xycoords="data",
            xytext=(12.0, 14.0),
            textcoords="offset points",
            ha="left",
            va="bottom",
            fontsize=sz.small,
            color=theme.ink,
            zorder=7,
            bbox=ctx.halo_bbox(0.16, alpha=0.92),
            annotation_clip=False,
        )
        # Prefer pointing inward away from the nearest plot edges.
        prefer_dx = -1.0 if fx > 0.55 else 1.0
        prefer_dy = -1.0 if fy > 0.60 else 1.0
        ordered = sorted(
            base_offsets,
            key=lambda c: (
                int(math.hypot(c[0], c[1]) // 18),
                0 if c[0] * prefer_dx >= 0 else 1,
                0 if c[1] * prefer_dy >= 0 else 1,
                math.hypot(c[0], c[1]),
            ),
        )
        text_variants = [text]
        wrapped = _two_line_wrap(text)
        if wrapped is not None:
            text_variants.append(wrapped)

        best_variant = text
        best = ordered[0]
        best_score: tuple[int, int, int, int, int, int, int, float] = (
            999,
            999,
            999,
            999,
            999,
            999,
            999,
            1e9,
        )
        for v_idx, variant in enumerate(text_variants):
            note.set_text(_plain(variant, theme))
            for dx, dy, ha, va in ordered:
                note.set_position((dx, dy))
                note.set_ha(ha)
                note.set_va(va)
                bb = note.get_window_extent(renderer)
                pbb = _pad_bbox(bb, 1.5)
                out_fig = int(
                    not (
                        bb.x0 >= fig_box.x0 + 3
                        and bb.x1 <= fig_box.x1 - 3
                        and bb.y0 >= fig_box.y0 + 3
                        and bb.y1 <= fig_box.y1 - 3
                    )
                )
                out_frame = int(
                    not (
                        bb.x0 >= frame.x0 + 1
                        and bb.x1 <= frame.x1 - 1
                        and bb.y0 >= frame.y0 + 3.5
                        and bb.y1 <= frame.y1 - 1
                    )
                )
                n_line = sum(1 for p in paths if p.intersects_bbox(bb, filled=False))
                n_text = sum(1 for tb in taken if pbb.overlaps(tb))
                _, _, seg_path = _callout_arrow_segment(ax_px, ay_px, bb)
                if seg_path is not None:
                    n_arrow_text = sum(
                        1 for tb in taken if seg_path.intersects_bbox(_pad_bbox(tb, 1.0), filled=True)
                    )
                    n_arrow_line = sum(1 for p in paths if seg_path.intersects_path(p, filled=False))
                else:
                    n_arrow_text = 0
                    n_arrow_line = 0
                score = (
                    out_fig,
                    n_line,
                    n_text,
                    n_arrow_text,
                    n_arrow_line,
                    out_frame,
                    v_idx,
                    math.hypot(dx, dy),
                )
                if score < best_score:
                    best_score = score
                    best = (dx, dy, ha, va)
                    best_variant = variant
                if score[:6] == (0, 0, 0, 0, 0, 0):
                    break
            if best_score[:6] == (0, 0, 0, 0, 0, 0):
                break
        note.set_text(_plain(best_variant, theme))
        note.set_position((best[0], best[1]))
        note.set_ha(best[2])
        note.set_va(best[3])
        final_bb = note.get_window_extent(renderer)
        start_px, start_py, _ = _callout_arrow_segment(ax_px, ay_px, final_bb)
        ax.annotate(
            "",
            xy=(cx, cy),
            xycoords="data",
            xytext=((start_px - ax_px) * k, (start_py - ay_px) * k),
            textcoords="offset points",
            arrowprops=arrow_kw,
            zorder=6,
            annotation_clip=False,
        )
        taken.append(final_bb)
