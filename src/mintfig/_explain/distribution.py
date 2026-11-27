"""distribution() and histogram() forms for mint.explain."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np
from matplotlib import patheffects
from matplotlib.axes import Axes
from matplotlib.ticker import (
    FuncFormatter,
    MaxNLocator,
)
from matplotlib.transforms import Bbox

from ..themes import (
    Theme,
)
from .core import (
    MAX_COMPARE_ITEMS,
    MAX_FACETS,
    MAX_GROUPS,
    ExplainError,
    Panel,
    _base_spec,
    _baseline_name,
    _cover_with_ticks,
    _Ctx,
    _diff_with_unit,
    _facet_cross_fact,
    _facet_shape,
    _FacetGrid,
    _fold_unit,
    _formatter,
    _guarded,
    _has_items,
    _inline_unit,
    _is_number,
    _is_one_dimensional,
    _is_strict,
    _jsonable,
    _keep_inside_x,
    _measure_text,
    _names,
    _narrow_log_ticks,
    _pairs,
    _plain,
    _range_with_unit,
    _ratio_text,
    _record_adjustment,
    _reference_line,
    _signed,
    _Sizes,
    _small_n_caution,
    _tick_label,
    _value_axis,
    _values_array,
    _vs_text,
    _with_unit,
)
from .marks import tag as tag_mark
from .marks import tag_each

# --------------------------------------------------------------------------- #
# distribution
# --------------------------------------------------------------------------- #


def _far_values(arr: np.ndarray, log: bool = False) -> np.ndarray:
    """Values more than 4 robust s.d. (1.4826·MAD) from the median; groups with n >= 5 only.

    On a log axis the distances are measured in log space, as the reader sees them.
    """
    if arr.size < 5:
        return np.empty(0)
    scaled = np.log10(arr) if log else arr
    med = float(np.median(scaled))
    dist = np.abs(scaled - med)
    mad = float(np.median(dist))
    if mad == 0:
        return np.empty(0)
    far = dist > 4.0 * 1.4826 * mad
    return arr[far][np.argsort(-dist[far])]


def _separation_fact(
    h: str,
    a: np.ndarray,
    other: str,
    b: np.ndarray,
    b_far: np.ndarray,
    value_fmt: Callable[[float], str],
    *,
    stat: str,
) -> str:
    """Whether two groups separate, robust to one stray value.

    Every value beyond every other ("every A value is above every B value"); else all
    but a few (at most max(1, 20% of n)) of one group beyond the other's whole range;
    else how many of ``h``'s values lie within ``other``'s range (without its far values).
    """
    up = (np.median(a) if stat == "median" else a.mean()) >= (
        np.median(b) if stat == "median" else b.mean()
    )
    if (up and a.min() > b.max()) or (not up and a.max() < b.min()):
        edge_a, edge_b = (a.min(), b.max()) if up else (a.max(), b.min())
        return (
            f"every {h} value is {'above' if up else 'below'} every {other} value "
            f"({h} {'lowest' if up else 'highest'} {value_fmt(float(edge_a))}, "
            f"{other} {'highest' if up else 'lowest'} {value_fmt(float(edge_b))})"
        )
    side = "above" if up else "below"
    options = []
    # Groups X, Y with X on ``side`` of Y: X values not beyond all of Y are the exceptions.
    flipped = "below" if up else "above"
    for x_name, x, y_name, y, x_side in ((h, a, other, b, side), (other, b, h, a, flipped)):
        exceptions = x[x <= y.max()] if x_side == "above" else x[x >= y.min()]
        if exceptions.size <= max(1, int(0.2 * x.size)) and exceptions.size < x.size:
            options.append((exceptions.size / x.size, x_name, x, y_name, x_side, exceptions))
    if options:
        _, x_name, x, y_name, x_side, exceptions = min(options, key=lambda o: o[0])
        listed = ", ".join(value_fmt(float(v)) for v in exceptions[:3])
        return (
            f"all but {exceptions.size} of {x.size} {x_name} values lie {x_side} every "
            f"{y_name} value (the exception{'s' if exceptions.size > 1 else ''}: {listed})"
        )
    core = b if not b_far.size else b[~np.isin(b, b_far)]
    inside = int(((a >= core.min()) & (a <= core.max())).sum())
    excluded = (
        f" (without its {b_far.size} far value{'s' if b_far.size > 1 else ''})" if b_far.size else ""
    )
    return (
        f"{h} and {other} overlap: {inside} of {a.size} {h} values lie within "
        f"the {other} range{excluded}"
    )


def _prob_superiority(a: np.ndarray, b: np.ndarray) -> float:
    """Empirical probability of superiority P(A > B) + 0.5 * P(A == B) over all pairs."""
    b_sorted = np.sort(b)
    lo = np.searchsorted(b_sorted, a, side="left")
    hi = np.searchsorted(b_sorted, a, side="right")
    return float((lo.sum() + 0.5 * (hi - lo).sum()) / (a.size * b.size))


def _wilkinson_stack(sorted_vals: np.ndarray, bin_width: float) -> list[tuple[float, int]]:
    """Bin sorted 1-D values into non-overlapping Wilkinson dot columns ``(center, count)``."""
    if sorted_vals.size == 0:
        return []
    bw = max(float(bin_width), 1e-12)
    raw_bins: list[list[float]] = [[float(sorted_vals[0])]]
    anchor = float(sorted_vals[0])
    for v in sorted_vals[1:]:
        fv = float(v)
        if fv - anchor <= bw:
            raw_bins[-1].append(fv)
        else:
            raw_bins.append([fv])
            anchor = fv
    # Merge any adjacent columns whose midpoints still sit closer than bin_width.
    merged: list[list[float]] = [raw_bins[0]]
    for grp in raw_bins[1:]:
        prev = merged[-1]
        c_prev = 0.5 * (prev[0] + prev[-1])
        c_curr = 0.5 * (grp[0] + grp[-1])
        if c_curr - c_prev < bw:
            merged[-1] = prev + grp
        else:
            merged.append(grp)
    return [(0.5 * (grp[0] + grp[-1]), len(grp)) for grp in merged]


_HIST_ESTIMATORS = frozenset({"auto", "fd", "doane", "scott", "stone", "rice", "sturges", "sqrt"})
MAX_HIST_GROUPS = 4


def _histogram_edges(
    everything: np.ndarray,
    bins: int | str | Sequence[float],
    log: bool,
) -> tuple[np.ndarray, int | str | list[float], str]:
    """Validate ``bins`` and return ``(edges, spec_value, width_summary)``."""
    lo, hi = float(everything.min()), float(everything.max())
    if isinstance(bins, bool):
        raise ExplainError(
            "distribution(bins) must be 'auto', an integer count, or a list of bin edges.",
            fix_hint='Pass bins="auto", bins=15, or bins=[0, 10, 20, 50].',
        )
    if isinstance(bins, (int, np.integer)):
        count = int(bins)
        if not 2 <= count <= 60:
            raise ExplainError(
                f"distribution(bins={count}) is outside the readable range (2 to 60).",
                fix_hint='Use between 2 and 60 bins, or bins="auto".',
            )
        if log:
            if hi <= lo:
                edges = np.geomspace(lo * 0.8, hi * 1.25, count + 1)
            else:
                edges = np.geomspace(lo, hi, count + 1)
            return edges, count, f"{count} log-spaced bins"
        if hi <= lo:
            edges = np.linspace(lo - 0.5, hi + 0.5, count + 1)
        else:
            edges = np.linspace(lo, hi, count + 1)
        return edges, count, f"{count} bins"
    if isinstance(bins, str):
        key = bins.strip().lower()
        if key not in _HIST_ESTIMATORS:
            raise ExplainError(
                f"distribution(bins={bins!r}) is not a recognised binning rule.",
                fix_hint=f"Use bins='auto', an integer (2–60), or one of: {', '.join(sorted(_HIST_ESTIMATORS))}.",
            )
        if log:
            log_edges = np.histogram_bin_edges(np.log10(everything), bins=key)
            count = max(5, min(24, len(log_edges) - 1))
            if hi <= lo:
                edges = np.geomspace(lo * 0.8, hi * 1.25, count + 1)
            else:
                edges = np.geomspace(lo, hi, count + 1)
            return edges, key, f"{count} log-spaced bins"
        edges = np.histogram_bin_edges(everything, bins=key)
        if len(edges) - 1 > 28:
            edges = np.linspace(lo, hi, 25)
        elif len(edges) - 1 < 3 and hi > lo:
            edges = np.linspace(lo, hi, 6)
        return edges, key, f"{len(edges) - 1} bins"
    if isinstance(bins, (Sequence, np.ndarray)):
        arr = _values_array(bins, "distribution(bins)")
        if arr.size < 3 or arr.size > 61:
            raise ExplainError(
                f"distribution(bins) needs 3 to 61 edges (2 to 60 bins), got {arr.size}.",
                fix_hint='Pass at least 3 increasing edges, or bins="auto".',
            )
        if not np.all(np.isfinite(arr)) or not np.all(np.diff(arr) > 0):
            raise ExplainError(
                "distribution(bins) edges must be finite and strictly increasing.",
                fix_hint="Sort and deduplicate the bin edges.",
            )
        if log and float(arr.min()) <= 0:
            raise ExplainError(
                "distribution(log=True) needs strictly positive bin edges.",
                fix_hint="Use positive bin edges or drop log=True.",
            )
        spec_edges = [float(v) for v in arr]
        return arr, spec_edges, f"{arr.size - 1} custom bins"
    raise ExplainError(
        f"distribution(bins) got unsupported type {type(bins).__name__}.",
        fix_hint='Pass bins="auto", an integer (2–60), or a sorted list of edges.',
    )


@_guarded("distribution", aliases={"measure": "label"})
def distribution(
    groups: Mapping[str, Sequence[float]] | Sequence[float] | Sequence[Mapping[str, Any]],
    *,
    group: str | None = None,
    value: str | None = None,
    title: str | None = None,
    label: str | None = None,
    unit: str | None = None,
    highlight: str | Sequence[str] | None = None,
    baseline: str | None = None,
    reference: float | tuple[float, str] | None = None,
    log: bool = False,
    stat: str = "median",
    bins: int | str | Sequence[float] | None = None,
    fmt: str | None = None,
    mode: str = "dots",
    quantiles: int = 20,
    facet: bool | str = False,
) -> Panel:
    """How are values spread within groups? Every observation as a dot, quantile dotplot, or histogram.

    ``groups`` maps a group name to its raw observations (or pass one list/array
    for a single variable, or row-shaped data / DataFrame with ``group=`` and
    ``value=``). By default (``mode="dots"``) every observation is drawn as a dot with
    a ``stat="median"`` (median and middle half / IQR) or ``stat="mean"`` (mean
    and \N{PLUS-MINUS SIGN} 1 s.d.) mark. Pass ``mode="quantile"`` (with optional
    ``quantiles=20``, 5–50) for Wilkinson-stacked countable quantile dotplots
    (Kay & Hullman) where each dot represents ``100 / quantiles``% probability.
    Pass ``bins="auto"`` (an integer 2–60, or explicit edges) — or call the alias
    :func:`histogram` — to draw a binned histogram (single panel, or shared-axis
    stacked small multiples for up to 4 groups). ``baseline`` names the reference
    group (a control, "before"): drawn in ink, with every highlighted (or every
    other) group stated against it, including pairwise superiority probability
    ``P(group > baseline)``. ``facet=`` draws small multiples on one shared value axis:
    with dot strips, one panel per facet level showing the same groups (tidy rows with
    ``facet="<column>"``, or ``{facet: {group: [obs]}}`` with ``facet=True``); with
    ``bins=``, ``facet=True`` gives each of 2-12 groups its own histogram on shared bins
    and a shared count axis.
    """
    if stat not in {"median", "mean"}:
        raise ExplainError(
            f"distribution(stat={stat!r}) is not a summary this form draws.",
            fix_hint='Use stat="median" (median and middle half) or stat="mean" (mean and '
            "\N{PLUS-MINUS SIGN} 1 s.d.).",
        )
    if not isinstance(mode, str) or mode not in {"dots", "quantile"}:
        raise ExplainError(
            f"distribution(mode={mode!r}) is not a recognised mode.",
            fix_hint='Use mode="dots" (raw observations) or mode="quantile" (stacked countable quantile dotplot).',
        )
    if (
        isinstance(quantiles, bool)
        or not isinstance(quantiles, (int, np.integer))
        or not (5 <= int(quantiles) <= 50)
    ):
        raise ExplainError(
            f"distribution(quantiles={quantiles!r}) must be an integer between 5 and 50.",
            fix_hint="Pass quantiles=20 (each dot = 5%) or another integer from 5 to 50.",
        )
    q = int(quantiles)
    faceted = facet is not False and facet is not None
    if faceted and bins is None:
        if mode != "dots":
            raise ExplainError(
                'distribution(facet=...) draws dot strips; mode="quantile" has no faceted form.',
                fix_hint='Drop mode="quantile", or drop facet= for one quantile dotplot.',
            )
        return _faceted_strips(
            groups,
            facet=facet,
            group=group,
            value=value,
            title=title,
            label=label,
            unit=unit,
            highlight=highlight,
            baseline=baseline,
            reference=reference,
            log=log,
            stat=stat,
            fmt=fmt,
        )
    if faceted and facet is not True:
        raise ExplainError(
            f"histogram(facet={facet!r}) must be True or False: each group becomes one histogram.",
            fix_hint="Pass facet=True with {group: [observations]} (2-12 groups).",
        )
    if mode == "quantile" and bins is not None:
        raise ExplainError(
            'distribution(mode="quantile") cannot be combined with bins=.',
            fix_hint='Drop bins= to draw a quantile dotplot, or use mode="dots" with bins= for a histogram.',
        )
    from .._tabular import resolve_distribution_table

    tabular = resolve_distribution_table(
        groups,
        group=group,
        value=value,
        form="distribution",
    )
    if tabular is not None:
        groups = tabular
    if _has_items(groups) and not _is_one_dimensional(groups):
        raw = {str(k): v for k, v in _pairs(groups)}
    elif isinstance(groups, (str, bytes)) or _is_number(groups) or groups is None:
        raise ExplainError(
            "distribution(groups) must map group names to lists of observations.",
            fix_hint='e.g. {"control": [4.1, 3.9, 4.4, ...], "treated": [...]}.',
        )
    elif (
        isinstance(groups, Sequence)
        and not isinstance(groups, (str, bytes))
        and groups
        and all(
            isinstance(item, Sequence)
            and not isinstance(item, (str, bytes))
            and len(item) == 2
            and isinstance(item[0], str)
            for item in groups
        )
    ):
        raise ExplainError(
            "distribution(groups) expects a dict mapping group name -> list of observations, got a list of pairs.",
            fix_hint='Pass a dict such as {"control": [4.1, 3.9, 4.4], "treated": [5.2, 5.5, 5.1]}.',
        )
    else:
        raw = {"": groups}
    data: dict[str, np.ndarray] = {}
    dropped: dict[str, int] = {}
    given: dict[str, np.ndarray] = {}
    for name, values in raw.items():
        if _is_number(values) or values is None or isinstance(values, (str, bytes)):
            raise ExplainError(
                f"distribution(groups[{name!r}]) is {values!r}, not a list of observations.",
                fix_hint="distribution() shows raw observations; for one summary number per "
                "group use compare() (with error= for an interval).",
            )
        arr = _values_array(values, f"distribution(groups[{name!r}])")
        given[name] = arr
        dropped[name] = int((~np.isfinite(arr)).sum())
        arr = arr[np.isfinite(arr)]
        if arr.size < 3:
            raise ExplainError(
                f"distribution(groups[{name!r}]) has {arr.size} finite values; a spread needs >= 3.",
                fix_hint="Use compare() for one or two values per item.",
            )
        data[name] = arr
    if not data:
        raise ExplainError("distribution(groups) is empty.", fix_hint="Pass at least one group.")
    names = list(data)
    group_limit = (MAX_FACETS if faceted else MAX_HIST_GROUPS) if bins is not None else MAX_GROUPS
    if len(names) > group_limit:
        if not _is_strict():
            req_hl = (
                [highlight]
                if isinstance(highlight, str)
                else ([str(h) for h in highlight] if highlight is not None else [])
            )
            keep = [nm for nm in req_hl if nm in data]
            if baseline is not None and str(baseline) in data and str(baseline) not in keep:
                keep.append(str(baseline))
            for nm in names:
                if len(keep) >= group_limit:
                    break
                if nm not in keep:
                    keep.append(nm)
            keep_set = set(keep)
            data = {nm: data[nm] for nm in names if nm in keep_set}
            given = {nm: given[nm] for nm in names if nm in keep_set}
            dropped = {nm: dropped[nm] for nm in names if nm in keep_set}
            _record_adjustment(f"distribution(): trimmed {len(names)} groups to {len(data)}")
            names = list(data)
        elif bins is None:
            raise ExplainError(
                f"distribution() got {len(names)} groups; more than {MAX_GROUPS} rows of dots blur together.",
                fix_hint=f"distribution() takes at most {MAX_GROUPS} groups: keep the groups the "
                f"takeaway compares, or compare() their medians (up to {MAX_COMPARE_ITEMS} items, "
                "with error= for an interval).",
                rule="too_many_items",
            )
    hl = _names(highlight, names)
    base = _baseline_name(baseline, names, hl, "distribution")
    ref = _reference_line(reference, "distribution(reference)")
    everything = np.concatenate(list(data.values()))
    given_unit = unit
    # Raw ratios (fold changes) read as ratios: "median 2.46×", not "2.46 fold".
    if _fold_unit(unit, label, log and float(everything.min()) > 0):
        unit = "\N{MULTIPLICATION SIGN}"
    if log and (everything.min() <= 0 or (ref is not None and ref[0] <= 0)):
        raise ExplainError(
            "distribution(log=True) needs strictly positive values.",
            fix_hint="Drop log=True or remove non-positive values.",
        )
    if stat == "mean":
        stats = {}
        for nm, arr in data.items():
            m, sd = float(arr.mean()), float(arr.std(ddof=1))
            stats[nm] = (m - sd, m, m + sd)
    else:
        stats = {
            nm: tuple(float(q) for q in np.percentile(arr, [25, 50, 75]))
            for nm, arr in data.items()
        }
    fmt_fn = _formatter([q for trio in stats.values() for q in trio], fmt, unit=unit, log=log)
    # Ranges, far values and separation edges share the centres' digits (whole numbers
    # stay whole: "lowest 91", not "91.0").
    whole = all(float(v).is_integer() for v in everything)
    range_fmt = _formatter(list(everything), fmt, unit=unit, log=log) if whole else fmt_fn
    facts = []
    for nm in names:
        lo_q, mid, hi_q = stats[nm]
        spread = (
            f"\N{PLUS-MINUS SIGN} 1 s.d. {_range_with_unit(fmt_fn(lo_q), fmt_fn(hi_q), unit)}"
            if stat == "mean"
            else f"middle half {_range_with_unit(fmt_fn(lo_q), fmt_fn(hi_q), unit)}"
        )
        arr = data[nm]
        text = (
            f"{nm or (label or 'values')}: {stat} {_with_unit(fmt_fn(mid), unit)}, {spread}, "
            f"range {_range_with_unit(range_fmt(float(arr.min())), range_fmt(float(arr.max())), unit)}, "
            f"n={arr.size}"
        )
        if dropped[nm]:
            text += f"; {dropped[nm]} missing value{'s' if dropped[nm] > 1 else ''} dropped"
        facts.append(text)
    caution = _small_n_caution(
        {nm or (label or "values"): data[nm].size for nm in names},
        "quartiles are not meaningful" if stat == "median" else "the s.d. is a rough estimate",
    )
    if caution:
        facts.append(caution)
    outliers = {nm: _far_values(data[nm], log) for nm in names}
    for nm in names:
        far = outliers[nm]
        if far.size:
            shown_far = ", ".join(_with_unit(range_fmt(float(v)), unit) for v in far[:5])
            more = f" and {far.size - 5} more" if far.size > 5 else ""
            word = "value" if far.size == 1 else "values"
            facts.append(
                f"{nm or (label or 'values')}: {far.size} {word} far from the rest: "
                f"{shown_far}{more} (median {_with_unit(fmt_fn(float(np.median(data[nm]))), unit)})"
            )
    # Which pairs are stated: each group against the baseline; else among the
    # highlighted groups (each pair once); a lone highlight against every other group.
    pairs: list[tuple[str, str]] = []
    if base is not None:
        pairs = [(nm, base) for nm in (hl or [nm for nm in names if nm != base])][:6]
    elif len(hl) >= 2:
        pairs = [(a, b) for i, a in enumerate(hl) for b in hl[i + 1 :]]
    elif hl:
        pairs = [(hl[0], other) for other in names if other != hl[0]]
    first_pair_fact = len(facts)
    if log:
        # On a log axis groups differ by factors: state ratios, not differences.
        for h, other in pairs:
            ratio = _ratio_text(stats[h][1] / stats[other][1])
            facts.append(f"{h} is {ratio} {other} ({stat})")
    elif pairs:
        diffs = [(h, other, stats[h][1] - stats[other][1]) for h, other in pairs]
        diff_fmt = _formatter([d for _, _, d in diffs], fmt, unit=unit)
        signed_spread = float(everything.min()) < 0 < float(everything.max())
        for h, other, _d in diffs:
            if base is not None:
                vs = _vs_text(
                    stats[h][1],
                    stats[other][1],
                    unit=unit,
                    diff_fmt=diff_fmt,
                    relative=not signed_spread,
                )
                facts.append(f"{h} vs {other}: {stat} {vs}")
                continue
            shown = _diff_with_unit(_signed(diff_fmt(_d)), unit)
            if stats[h][1] > 0 and stats[other][1] > 0:
                shown += f" ({_ratio_text(stats[h][1] / stats[other][1])})"
            facts.append(f"{h} \N{MINUS SIGN} {other}: {stat} {shown}")
    pair_facts = facts[first_pair_fact:]
    # Whether every observation of one group lies beyond every one of the other:
    # the check behind "every treated cell beats every control cell".
    for h, other in pairs:
        facts.append(
            _separation_fact(
                h,
                data[h],
                other,
                data[other],
                outliers[other],
                lambda v: _with_unit(range_fmt(v), unit),
                stat=stat,
            )
        )
    if base is not None:
        for h, other in pairs:
            if data[h].size >= 3 and data[other].size >= 3:
                p_sup = _prob_superiority(data[h], data[other])
                facts.append(f"P({h} > {other}) = {100.0 * p_sup:.0f}%")
    qvals: dict[str, np.ndarray] = {}
    if mode == "quantile":
        probs = (np.arange(q, dtype=float) + 0.5) / q
        qvals = {nm: np.quantile(data[nm], probs) for nm in names}
    if ref is not None and bins is None:
        ref_u = _with_unit(_formatter([ref[0]], log=log)(ref[0]), unit)
        ref_tag = f" ({ref[1]})" if ref[1] else ""
        for nm in names:
            tag = nm or (label or "values")
            if mode == "quantile":
                k_above = int((qvals[nm] > ref[0]).sum())
                facts.append(
                    f"{tag}: {k_above} of {q} quantiles ({100.0 * k_above / q:.0f}%) above "
                    f"{ref_u}{ref_tag}"
                )
            else:
                arr = data[nm]
                above = int((arr > ref[0]).sum())
                facts.append(
                    f"{tag}: {100.0 * above / arr.size:.0f}% of observations above "
                    f"{ref_u}{ref_tag} ({above} of {arr.size})"
                )
    any_spread = any(a.size >= 5 for a in data.values())
    # Alt text: every group's centre (or the highlighted groups and the baseline), then
    # how they compare; never only the first group.
    paired = {nm for pair in pairs for nm in pair} | set(hl)
    told = [nm for nm in names if nm in paired] or names
    alt_facts = [
        f"{nm or (label or 'values')}: {stat} {_with_unit(fmt_fn(stats[nm][1]), unit)}"
        for nm in told
    ]
    alt_facts += pair_facts

    if bins is not None:
        if faceted and not 2 <= len(names) <= MAX_FACETS:
            raise ExplainError(
                f"histogram(facet=True) got {len(names)} group(s); small multiples take 2-{MAX_FACETS}.",
                fix_hint=f"Pass {{group: [observations]}} with 2-{MAX_FACETS} groups, or drop facet=True.",
                rule="too_many_items" if len(names) > MAX_FACETS else "explain_spec",
            )
        if len(names) > MAX_HIST_GROUPS and not faceted:
            raise ExplainError(
                f"Binned distribution() got {len(names)} groups; more than {MAX_HIST_GROUPS} "
                "stacked histograms crowd a chat figure.",
                fix_hint=f"Keep at most {MAX_HIST_GROUPS} groups for histograms, or omit bins= "
                f"for dot strips (up to {MAX_GROUPS} groups).",
                rule="too_many_items",
            )
        edges, bins_spec, bins_desc = _histogram_edges(everything, bins, log)
        hists = {nm: np.histogram(data[nm], bins=edges)[0] for nm in names}
        max_count = max(int(c.max()) for c in hists.values()) if hists else 1
        widths = np.diff(edges)
        uniform_width = (not log) and bool(np.allclose(widths, widths[0], rtol=1e-4))
        edge_fmt = _formatter(list(edges), fmt, unit=unit, log=log)
        if uniform_width:
            w_fmt = _formatter([float(widths[0])], fmt, unit=unit)
            bin_note = f"{len(edges) - 1} bins (width {_with_unit(w_fmt(float(widths[0])), unit)})"
        else:
            bin_note = bins_desc
        facts.append(f"binned into {bin_note}")
        for nm in names:
            counts = hists[nm]
            peak_i = int(np.argmax(counts))
            peak_c = int(counts[peak_i])
            pct = 100.0 * peak_c / max(1, data[nm].size)
            lo_e = edge_fmt(float(edges[peak_i]))
            hi_e = edge_fmt(float(edges[peak_i + 1]))
            bin_span = _range_with_unit(lo_e, hi_e, unit)
            tag = nm or (label or "values")
            facts.append(f"{tag}: peak bin {bin_span} ({peak_c} of {data[nm].size}, {pct:.0f}%)")
            if ref is not None:
                above = int((data[nm] > ref[0]).sum())
                below = int((data[nm] < ref[0]).sum())
                ref_u = _with_unit(_formatter([ref[0]], log=log)(ref[0]), unit)
                ref_tag = f" ({ref[1]})" if ref[1] else ""
                facts.append(
                    f"{tag}: {100.0 * above / data[nm].size:.0f}% above {ref_u}{ref_tag} "
                    f"({above} of {data[nm].size}; {below} below)"
                )

        x_lo = float(edges[0])
        x_hi = float(edges[-1])
        if ref is not None:
            x_lo = min(x_lo, ref[0])
            x_hi = max(x_hi, ref[0])

        def _setup_hist_axes(
            ax_h: Axes,
            sz: _Sizes,
            theme: Theme,
            *,
            show_x: bool,
            nbins_y: int,
            cell_w_mm: float,
        ) -> None:
            if log:
                ax_h.set_xscale("log")
            _value_axis(ax_h, sz, theme, axis="y", nbins=nbins_y)
            ax_h.yaxis.set_major_locator(MaxNLocator(nbins=nbins_y, integer=True))
            ax_h.spines["left"].set_visible(False)
            ax_h.spines["top"].set_visible(False)
            ax_h.spines["right"].set_visible(False)
            ax_h.spines["bottom"].set_visible(not theme.hide_spines)
            if not theme.hide_spines:
                ax_h.spines["bottom"].set_color(theme.axis)
                ax_h.spines["bottom"].set_linewidth(theme.axis_lw)
            ax_h.tick_params(
                axis="x",
                length=theme.tick_length if show_x else 0.0,
                width=theme.tick_width,
                color=theme.axis,
                labelsize=sz.small,
                labelcolor=theme.muted,
                labelbottom=show_x,
            )
            ax_h.set_ylim(0, max(1.0, max_count * 1.14))
            if log:
                ax_h.set_xlim(
                    *_narrow_log_ticks(
                        ax_h.xaxis,
                        x_lo / 1.06,
                        x_hi * 1.06,
                        theme.minus_sign,
                        extend=False,
                        data_hi=x_hi,
                    )
                )
            else:
                span = (x_hi - x_lo) or abs(x_hi) or 1.0
                ax_h.set_xlim(x_lo - 0.02 * span, x_hi + 0.02 * span)
                ax_h.xaxis.set_major_locator(
                    MaxNLocator(nbins=6 if cell_w_mm >= 100 else 4, steps=[1, 2, 2.5, 5, 10])
                )
                ax_h.xaxis.set_major_formatter(
                    FuncFormatter(
                        lambda v, _p, m=theme.minus_sign, a=ax_h.xaxis: _tick_label(v, m, a)
                    )
                )
            if show_x:
                x_title = _measure_text(label, unit)
                if x_title:
                    ax_h.set_xlabel(
                        _plain(x_title, theme),
                        fontsize=sz.small,
                        color=theme.muted,
                        labelpad=3,
                    )

        def _draw_hist_bars(
            ctx: _Ctx, ax_h: Axes, nm: str, accent_map: Mapping[str, str], sz: _Sizes, theme: Theme
        ) -> None:
            if nm == base:
                col = ctx.colors.get(nm, theme.ink)
            else:
                col = accent_map.get(
                    nm, theme.context_fill if (hl or accent_map) else ctx.default_color
                )
            edge_col = theme.bar_edgecolor or theme.background
            edge_lw = theme.bar_edge_lw if theme.bar_edgecolor else 0.65
            bins = ax_h.bar(
                edges[:-1],
                hists[nm],
                width=widths,
                align="edge",
                color=col,
                edgecolor=edge_col,
                linewidth=edge_lw,
                alpha=0.88,
                zorder=2,
            )
            tag_each(ctx, bins.patches, [
                {"name": nm, "x": _with_unit(f"{fmt_fn(a)}\u2013{fmt_fn(b)}", unit), "value": int(c)}
                for a, b, c in zip(edges[:-1], edges[1:], hists[nm])
            ])
            med = stats[nm][1]
            ax_h.axvline(
                med,
                color=theme.ink,
                linewidth=1.1 * sz.scale,
                linestyle="--",
                zorder=4,
            )
            if ref is not None:
                ax_h.axvline(
                    ref[0],
                    color=theme.muted,
                    linewidth=0.85 * sz.scale,
                    linestyle=(0, (3, 2)),
                    zorder=3,
                )

        single_measure = (
            f"Count (n={data[names[0]].size}); {bin_note}; dashed: {stat}"
            if len(names) == 1
            else f"Count per group; {bin_note}; dashed: {stat}"
        )

        if len(names) == 1:
            nm0 = names[0]

            def _draw_single_hist(ctx: _Ctx, ax: Axes) -> Callable[[], None] | None:
                sz = ctx.sizes
                theme = ctx.theme
                accent = {
                    name: col for name, col in ctx.colors.items() if name in names and name != base
                }
                _setup_hist_axes(
                    ax, sz, theme, show_x=True, nbins_y=4, cell_w_mm=ctx.cell_width_mm
                )
                _draw_hist_bars(ctx, ax, nm0, accent, sz, theme)
                med = stats[nm0][1]
                top_notes: list[Any] = []
                med_text = f"{stat} {_with_unit(fmt_fn(med), unit)}"
                med_note = ax.annotate(
                    _plain(med_text, theme),
                    (med, 1.0),
                    xycoords=("data", "axes fraction"),
                    xytext=(0.0, 3.0),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=sz.small,
                    fontweight="bold",
                    color=theme.ink,
                    annotation_clip=False,
                )
                top_notes.append(med_note)
                ref_note = None
                if ref is not None and ref[1]:
                    ref_note = ax.annotate(
                        _plain(ref[1], theme),
                        (ref[0], 1.0),
                        xycoords=("data", "axes fraction"),
                        xytext=(0.0, 3.0),
                        textcoords="offset points",
                        ha="center",
                        va="bottom",
                        fontsize=sz.small,
                        color=theme.muted,
                        annotation_clip=False,
                    )
                    top_notes.append(ref_note)

                def _finish_hist() -> None:
                    for note in top_notes:
                        _keep_inside_x(ctx, ax, note)
                    if ref_note is not None:
                        renderer = ctx.fig.canvas.get_renderer()
                        b0 = med_note.get_window_extent(renderer)
                        b1 = ref_note.get_window_extent(renderer)
                        if b0.overlaps(b1):
                            ref_note.set_position((ref_note.xyann[0], 13.5))

                return _finish_hist

            return Panel(
                kind="distribution",
                title=title,
                label=label,
                unit=unit,
                spec=_base_spec(
                    title,
                    label,
                    given_unit,
                    groups=_jsonable(given.get("", given)),
                    highlight=hl or None,
                    baseline=base,
                    reference=list(ref) if ref else None,
                    log=log or None,
                    stat=stat if stat != "median" else None,
                    bins=bins_spec,
                    fmt=fmt,
                ),
                facts=facts,
                alt_facts=alt_facts,
                describe=(
                    f"Histogram of {label or 'values'}"
                    + (f" ({unit})" if unit else "")
                    + f" across {bin_note} (n={data[nm0].size})"
                ),
                _height_mm=lambda w, _m, _s, _t: min(54.0, max(36.0, 0.40 * w)) + 4.0,
                _min_height_mm=lambda _w, _m, _s, _t: 32.0,
                stretch=True,
                _draw=_draw_single_hist,
                measure_note=single_measure,
                color_items=tuple(nm for nm in names if nm),
                color_focus=tuple(hl),
                color_mode="highlight" if hl else "uniform",
                uses_default=not hl,
                color_baseline=base,
            )

        if faceted:
            return _hist_facet_panel(
                names=names,
                data=data,
                given=given,
                stats=stats,
                hists=hists,
                hl=hl,
                base=base,
                ref=ref,
                stat=stat,
                label=label,
                unit=unit,
                given_unit=given_unit,
                title=title,
                log=log,
                fmt=fmt,
                fmt_fn=fmt_fn,
                bins_spec=bins_spec,
                bin_note=bin_note,
                facts=facts,
                alt_facts=alt_facts,
                setup_axes=_setup_hist_axes,
                draw_bars=_draw_hist_bars,
            )

        def _hist_frames(ctx: _Ctx, ax: Axes, rect: Bbox) -> list[tuple[Axes, Bbox]]:
            sz = ctx.sizes
            theme = ctx.theme
            accent = {
                name: col for name, col in ctx.colors.items() if name in names and name != base
            }
            ax.remove()
            nrows = len(names)
            px_per_mm = float(ctx.fig.dpi) / 25.4
            gap_y = 4.0 * px_per_mm * sz.scale
            cell_h = (rect.height - gap_y * (nrows - 1)) / nrows
            frames: list[tuple[Axes, Bbox]] = []
            top_ref_note: Any = None
            top_child: Axes | None = None
            for idx, nm in enumerate(names):
                y1 = rect.y1 - idx * (cell_h + gap_y)
                sub = Bbox.from_extents(rect.x0, y1 - cell_h, rect.x1, y1)
                child = ctx.fig.add_axes([0.1, 0.1, 0.5, 0.5])
                ctx.tag(child)
                ctx.extra_axes.append(child)
                _setup_hist_axes(
                    child,
                    sz,
                    theme,
                    show_x=(idx == nrows - 1),
                    nbins_y=3,
                    cell_w_mm=ctx.cell_width_mm,
                )
                _draw_hist_bars(ctx, child, nm, accent, sz, theme)
                col = (
                    ctx.colors.get(nm, theme.ink)
                    if nm == base
                    else accent.get(nm, theme.ink if not (hl or accent) else theme.muted)
                )
                med = stats[nm][1]
                title_col = ctx.text_color(col) if nm in accent else theme.ink
                child.set_title(
                    _plain(f"{nm}  ({stat} {_with_unit(fmt_fn(med), unit)}, n={data[nm].size})", theme),
                    loc="left",
                    fontsize=sz.small,
                    fontweight="bold" if (nm in accent or nm == base) else "normal",
                    color=title_col,
                    pad=3.0,
                )
                if idx == 0 and ref is not None and ref[1]:
                    top_child = child
                    top_ref_note = child.annotate(
                        _plain(ref[1], theme),
                        (ref[0], 1.0),
                        xycoords=("data", "axes fraction"),
                        xytext=(3.0, 2.5),
                        textcoords="offset points",
                        ha="left",
                        va="bottom",
                        fontsize=sz.small,
                        color=theme.muted,
                        annotation_clip=False,
                    )
                frames.append((child, sub))

            def _equalize_hist() -> None:
                fig_w = ctx.fig.bbox.width
                left = max(child.get_position().x0 * fig_w for child, _ in frames)
                right = min(child.get_position().x1 * fig_w for child, _ in frames)
                for child, _ in frames:
                    pos = child.get_position()
                    child.set_position([left / fig_w, pos.y0, max(1.0, right - left) / fig_w, pos.height])
                if top_ref_note is not None and top_child is not None:
                    _keep_inside_x(ctx, top_child, top_ref_note)
                    renderer = ctx.fig.canvas.get_renderer()
                    t_title = getattr(top_child, "_left_title", None)
                    if t_title is not None and t_title.get_window_extent(renderer).overlaps(
                        top_ref_note.get_window_extent(renderer)
                    ):
                        top_ref_note.set_position((3.0, -10.0))
                        top_ref_note.set_va("top")

            ctx.finishers.append(_equalize_hist)
            return frames

        return Panel(
            kind="distribution",
            title=title,
            label=label,
            unit=unit,
            spec=_base_spec(
                title,
                label,
                given_unit,
                groups=_jsonable(given),
                highlight=hl or None,
                baseline=base,
                reference=list(ref) if ref else None,
                log=log or None,
                stat=stat if stat != "median" else None,
                bins=bins_spec,
                fmt=fmt,
            ),
            facts=facts,
            alt_facts=alt_facts,
            describe=(
                f"Stacked histograms of {label or 'values'}"
                + (f" ({unit})" if unit else "")
                + f" for {len(names)} groups across {bin_note}"
            ),
            _height_mm=lambda _w, _m, _s, _t: 22.0 * len(names) + 14.0,
            _min_height_mm=lambda _w, _m, _s, _t: 18.0 * len(names) + 12.0,
            _draw=lambda _ctx, _ax: None,
            _frames=_hist_frames,
            measure_note=single_measure,
            color_items=tuple(nm for nm in names if nm),
            color_focus=tuple(hl),
            color_mode="highlight" if hl else "uniform",
            uses_default=not hl,
            color_baseline=base,
        )

    def _draw(ctx: _Ctx, ax: Axes) -> Callable[[], None] | None:
        sz = ctx.sizes
        theme = ctx.theme
        accent = {
            name: col for name, col in ctx.colors.items() if name in names and name != base
        }
        n = len(names)
        if log:
            ax.set_xscale("log")
        _value_axis(ax, sz, theme, axis="x", nbins=5 if ctx.cell_width_mm >= 100 else 3)
        ax.spines["left"].set_visible(False)
        ax.spines["bottom"].set_visible(False)
        if theme.grid_style != "none" and theme.grid_lw > 0:
            ax.grid(
                axis="x",
                color=theme.grid,
                linestyle=theme.grid_style,
                linewidth=theme.grid_lw,
            )
            ax.grid(axis="y", visible=False)
        ax.set_ylim((n - 0.35, -0.65) if mode == "quantile" else (n - 0.45, -0.6))
        lo, hi = float(everything.min()), float(everything.max())
        if ref is not None:
            lo, hi = min(lo, ref[0]), max(hi, ref[0])
        if log:
            ax.set_xlim(
                *_narrow_log_ticks(
                    ax.xaxis, lo / 1.12, hi * 1.12, theme.minus_sign, extend=False, data_hi=hi
                )
            )
        else:
            span = (hi - lo) or abs(hi) or 1.0
            ax.set_xlim(lo - 0.04 * span, hi + 0.04 * span)
            # The value axis covers every dot (re-checked after tick thinning).
            ax._mintfig_cover = (lo, hi)  # type: ignore[attr-defined]
            # After layout: >= 3 round ticks bracketing every dot (_bracket_with_ticks).
            ax._mintfig_bracket = (  # type: ignore[attr-defined]
                lo,
                hi,
                6 if ctx.cell_width_mm >= 100 else 4,
                theme.minus_sign,
            )
            _cover_with_ticks(ax.xaxis, lo, hi)
        ax.set_yticks(range(n), [""] * n)
        ax.tick_params(axis="y", length=0)
        ax.annotate(
            stat,
            (1.0, 1.0),
            xycoords="axes fraction",
            xytext=(6.0, 2.5),
            textcoords="offset points",
            ha="left",
            va="bottom",
            fontsize=sz.small,
            color=theme.muted,
            annotation_clip=False,
        )
        rng = np.random.default_rng(0)
        row_colors: dict[str, str] = {}
        for row, name in enumerate(names):
            arr = data[name]
            if name == base:
                col = ctx.colors.get(name, theme.ink)
            else:
                col = accent.get(name, theme.context_line if (hl or accent) else ctx.default_color)
            row_colors[name] = col
            q1, med, q3 = stats[name]
            if log:
                q1 = max(q1, ax.get_xlim()[0])
            if mode == "dots":
                shown = arr if arr.size <= 600 else rng.choice(arr, size=600, replace=False)
                alpha = 0.8 if shown.size <= 30 else (0.5 if shown.size <= 150 else 0.28)
                jitter = rng.uniform(-0.2, 0.2, size=shown.size)
                tag_mark(ctx, ax.scatter(
                    shown,
                    row + jitter,
                    s=(3.4 * sz.scale) ** 2,
                    color=col,
                    alpha=alpha,
                    linewidth=0,
                    zorder=2,
                ), name=name, value=med, lo=q1, hi=q3, n=arr.size, unit=unit)
                # Summary through the dot row: a thin line for the middle half (or +/- 1 s.d.)
                # and a taller tick for the centre, haloed so it reads over the dots. With
                # fewer than five observations quartiles and s.d. mean little: the centre
                # tick only.
                halo = [
                    patheffects.withStroke(
                        linewidth=2.6 * sz.scale, foreground=theme.background, alpha=0.9
                    )
                ]
                if arr.size >= 5:
                    ax.hlines(
                        row,
                        q1,
                        q3,
                        color=theme.ink,
                        linewidth=1.0 * sz.scale,
                        zorder=4,
                        path_effects=halo,
                    )
                ax.vlines(
                    med,
                    row - 0.3,
                    row + 0.3,
                    color=theme.ink,
                    linewidth=2.0 * sz.scale,
                    zorder=5,
                    path_effects=halo,
                )
            for text, dy, va, size, color, weight in (
                (name, 0.5, "bottom", sz.body, theme.ink, "bold" if name in accent else "normal"),
                (f"n={arr.size}", -1.5, "top", sz.foot, theme.muted, "normal"),
            ):
                ax.annotate(
                    _plain(text, theme),
                    (0.0, row),
                    xycoords=("axes fraction", "data"),
                    xytext=(-7.0, dy),
                    textcoords="offset points",
                    ha="right",
                    va=va,
                    fontsize=size,
                    color=color,
                    fontweight=weight,
                    annotation_clip=False,
                )
            value = (
                _with_unit(fmt_fn(med), unit) if (row == 0 or _inline_unit(unit)) else fmt_fn(med)
            )
            ax.annotate(
                _plain(value, theme),
                (1.0, row),
                xycoords=("axes fraction", "data"),
                xytext=(6.0, 0.0),
                textcoords="offset points",
                ha="left",
                va="center",
                fontsize=sz.small,
                color=theme.ink,
                fontweight="bold" if name in accent else "normal",
                annotation_clip=False,
            )
        ref_note: Any = None
        if ref is not None:
            ax.axvline(ref[0], color=theme.ink, linewidth=0.7, linestyle=(0, (3, 2)), zorder=3)
            if ref[1]:
                ref_note = ax.annotate(
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
        if mode == "quantile":

            def _finish_quantile() -> None:
                if ref_note is not None:
                    _keep_inside_x(ctx, ax, ref_note)
                renderer = ctx.fig.canvas.get_renderer()
                frame = ax.get_window_extent(renderer)
                w_pt = max(30.0, frame.width * ctx.pt_per_px)
                h_pt = max(20.0, frame.height * ctx.pt_per_px)
                row_h_pt = h_pt / max(1, n)
                x0_v, x1_v = sorted(ax.get_xlim())
                x_lo_s = float(np.log10(max(x0_v, 1e-300))) if log else float(x0_v)
                x_hi_s = float(np.log10(max(x1_v, 1e-300))) if log else float(x1_v)
                x_span = (x_hi_s - x_lo_s) or 1.0
                avail_h_pt = 0.72 * row_h_pt
                d_pt = (4.8 if q <= 25 else 3.8) * sz.scale
                binned: dict[str, list[tuple[float, int]]] = {}
                max_stack = 1
                for _ in range(10):
                    bw = (1.26 * d_pt / w_pt) * x_span
                    binned = {
                        nm: _wilkinson_stack(
                            np.log10(qvals[nm]) if log else qvals[nm],
                            bw,
                        )
                        for nm in names
                    }
                    max_stack = max(
                        (cnt for stacks in binned.values() for _, cnt in stacks),
                        default=1,
                    )
                    if max_stack * 1.12 * d_pt <= avail_h_pt:
                        break
                    d_pt = max(1.8 * sz.scale, min(d_pt * 0.88, avail_h_pt / (max_stack * 1.12)))
                dy_data = min((1.12 * d_pt) / max(row_h_pt, 1.0), 0.72 / max(1, max_stack))
                halo = [
                    patheffects.withStroke(
                        linewidth=2.2 * sz.scale, foreground=theme.background, alpha=0.9
                    )
                ]
                for row, name in enumerate(names):
                    col = row_colors[name]
                    y_base = row + 0.32
                    ax.hlines(
                        y_base,
                        float(qvals[name][0]),
                        float(qvals[name][-1]),
                        color=theme.grid,
                        linewidth=0.6 * sz.scale,
                        zorder=1,
                    )
                    dot_xs: list[float] = []
                    dot_ys: list[float] = []
                    for cx_s, count in binned[name]:
                        cx = float(10.0**cx_s) if log else float(cx_s)
                        for k in range(count):
                            dot_xs.append(cx)
                            dot_ys.append(y_base - (k + 0.55) * dy_data)
                    tag_mark(ctx, ax.scatter(
                        dot_xs,
                        dot_ys,
                        s=d_pt**2,
                        color=col,
                        edgecolor=theme.background,
                        linewidth=0.45 * sz.scale,
                        alpha=0.92,
                        zorder=3,
                    ), name=name, value=stats[name][1], lo=stats[name][0], hi=stats[name][2],
                        n=data[name].size, unit=unit)
                    q1, med, q3 = stats[name]
                    if log:
                        q1 = max(q1, ax.get_xlim()[0])
                    mark_y = y_base + 0.055
                    if data[name].size >= 5:
                        ax.hlines(
                            mark_y,
                            q1,
                            q3,
                            color=theme.ink,
                            linewidth=1.25 * sz.scale,
                            alpha=0.72,
                            zorder=4,
                            path_effects=halo,
                        )
                    ax.vlines(
                        med,
                        y_base - 0.05,
                        y_base + 0.14,
                        color=theme.ink,
                        linewidth=1.8 * sz.scale,
                        zorder=5,
                        path_effects=halo,
                    )

            return _finish_quantile
        if ref_note is not None:
            return lambda: _keep_inside_x(ctx, ax, ref_note)
        return None

    pct_each = 100.0 / q
    pct_txt = f"{pct_each:.0f}%" if abs(pct_each - round(pct_each)) < 1e-6 else f"{pct_each:.1f}%"
    if mode == "quantile":
        panel_describe = (
            f"Quantile dotplot ({q} dots/group, {pct_txt} each) of {label or 'values'}"
            + (f" ({unit})" if unit else "")
            + f" for {len(names)} group(s), with {stat} centre mark"
        )
        panel_measure_note = f"quantile dotplot ({q} dots/group, {pct_txt} each); tick: {stat}"
        height_fn = lambda _w, _m, _s, _t: max(26.0, 14.5 * len(names) + 12.0)
        min_height_fn = lambda _w, _m, _s, _t: max(22.0, 11.5 * len(names) + 11.0)
    else:
        panel_describe = (
            f"Dot strips of {label or 'values'}"
            + (f" ({unit})" if unit else "")
            + f" for {len(names)} group(s), each with "
            + (
                f"a {stat} tick"
                if not any_spread
                else "a mean tick and a \N{PLUS-MINUS SIGN} 1 s.d. line"
                if stat == "mean"
                else "a median tick and a line over the middle half (interquartile range)"
            )
        )
        # The spread line is drawn only for groups with n >= 5: caption it only then.
        panel_measure_note = (
            f"tick: {stat}"
            if not any_spread
            else (
                "tick: mean; line: \N{PLUS-MINUS SIGN} 1 s.d."
                if stat == "mean"
                else "tick: median; line: middle half"
            )
            + (
                ""
                if all(a.size >= 5 for a in data.values())
                else " (n \N{GREATER-THAN OR EQUAL TO} 5)"
            )
        )
        height_fn = lambda _w, _m, _s, _t: 8.5 * len(names) + 11.0
        min_height_fn = lambda _w, _m, _s, _t: 6.5 * len(names) + 11.0

    return Panel(
        kind="distribution",
        title=title,
        label=label,
        unit=unit,
        spec=_base_spec(
            title,
            label,
            given_unit,
            groups=_jsonable(given.get("", given)),
            highlight=hl or None,
            baseline=base,
            reference=list(ref) if ref else None,
            log=log or None,
            stat=stat if stat != "median" else None,
            fmt=fmt,
            mode=mode if mode != "dots" else None,
            quantiles=q if mode == "quantile" else None,
        ),
        facts=facts,
        alt_facts=alt_facts,
        describe=panel_describe,
        _height_mm=height_fn,
        _min_height_mm=min_height_fn,
        _draw=_draw,
        measure_note=panel_measure_note,
        color_items=tuple(nm for nm in names if nm),
        color_focus=tuple(hl),
        color_mode="highlight" if hl else "uniform",
        uses_default=not hl,
        color_baseline=base,
    )


@_guarded("histogram", aliases={"measure": "label"})
def histogram(
    values: Mapping[str, Sequence[float]] | Sequence[float] | Sequence[Mapping[str, Any]],
    *,
    group: str | None = None,
    value: str | None = None,
    bins: int | str | Sequence[float] = "auto",
    title: str | None = None,
    label: str | None = None,
    unit: str | None = None,
    highlight: str | Sequence[str] | None = None,
    baseline: str | None = None,
    reference: float | tuple[float, str] | None = None,
    log: bool = False,
    stat: str = "median",
    fmt: str | None = None,
    facet: bool = False,
) -> Panel:
    """How is a continuous variable shaped? Alias for ``distribution(..., bins=bins)``.

    Pass a single list/array of observations for a histogram, a dict of up to
    4 named groups for stacked shared-axis histograms, or row-shaped data /
    DataFrame with ``value=`` (and optional ``group=``). ``bins`` accepts
    ``"auto"`` (default), a bin count (2–60), a numpy binning rule, or explicit
    bin edges. ``facet=True`` gives each of 2-12 groups its own histogram in a grid,
    on shared bins and one shared count axis.
    """
    return distribution(
        values,
        group=group,
        value=value,
        bins=bins,
        title=title,
        label=label,
        unit=unit,
        highlight=highlight,
        baseline=baseline,
        reference=reference,
        log=log,
        stat=stat,
        fmt=fmt,
        facet=facet,
    )


def _facet_levels(
    groups: Any, facet: object, group: str | None, value: str | None
) -> dict[str, dict[str, Any]]:
    """``{facet level: {group: observations}}`` from tidy rows (``facet=`` a column name)
    or a nested mapping (``facet=True``)."""
    from .._tabular import extract_records, is_tabular

    if isinstance(facet, str):
        if not is_tabular(groups):
            raise ExplainError(
                f"distribution(facet={facet!r}) names a column, so it needs row-shaped data "
                f"(a list of dicts or a DataFrame), got {type(groups).__name__}.",
                fix_hint='Pass rows with value= (and group=), e.g. mint.distribution(rows, '
                f'group="arm", value="score", facet="{facet}"), or a nested mapping '
                "{facet: {group: [obs]}} with facet=True.",
            )
        cols, rows = extract_records(groups, what="distribution(groups)")
        missing = [c for c in (facet, value, group) if c is not None and c not in cols]
        if value is None or missing:
            raise ExplainError(
                f"distribution(facet={facet!r}) needs value= and existing columns"
                + (f"; not found: {', '.join(map(repr, missing))}" if missing else "")
                + ".",
                fix_hint=f"Columns: {', '.join(map(repr, cols[:10]))}. Pass value= (the numbers), "
                "group= (the rows inside each facet) and facet= (one small panel per level).",
            )
        nested: dict[str, dict[str, list[Any]]] = {}
        for row in rows:
            level = str(row.get(facet, ""))
            name = str(row.get(group, "")) if group is not None else ""
            nested.setdefault(level, {}).setdefault(name, []).append(row.get(value))
        return nested
    if facet is not True:
        raise ExplainError(
            f"distribution(facet={facet!r}) must be True or a column name.",
            fix_hint="Pass facet=True with {facet: {group: [obs]}}, or facet=\"<column>\" with rows.",
        )
    if group is not None or value is not None:
        raise ExplainError(
            "distribution(facet=True) takes a nested mapping, not group=/value= columns.",
            fix_hint='With rows, name the facet column instead: facet="site".',
        )
    if not (_has_items(groups) and all(_has_items(v) for _k, v in _pairs(groups))):
        raise ExplainError(
            "distribution(facet=True) needs a nested mapping {facet: {group: [observations]}}.",
            fix_hint='e.g. {"site A": {"control": [...], "treated": [...]}, "site B": {...}}; '
            'with rows pass the facet column, facet="site".',
        )
    return {str(k): {str(g): obs for g, obs in _pairs(v)} for k, v in _pairs(groups)}


def _faceted_strips(
    groups: Any,
    *,
    facet: object,
    group: str | None,
    value: str | None,
    title: str | None,
    label: str | None,
    unit: str | None,
    highlight: str | Sequence[str] | None,
    baseline: str | None,
    reference: float | tuple[float, str] | None,
    log: bool,
    stat: str,
    fmt: str | None,
) -> Panel:
    """``distribution(facet=...)``: one small panel of dot strips per facet level, the
    same groups in the same order in each, on one shared value axis."""
    levels = _facet_levels(groups, facet, group, value)
    facets = list(levels)
    if len(facets) > MAX_FACETS:
        if not _is_strict():
            _record_adjustment(
                f"distribution(facet=...): trimmed {len(facets)} facets to first {MAX_FACETS}"
            )
            facets = facets[:MAX_FACETS]
        else:
            raise ExplainError(
                f"distribution(facet=...) got {len(facets)} facet levels; more than {MAX_FACETS} "
                "small multiples is a wall.",
                fix_hint=f"Keep at most {MAX_FACETS} levels (filter the rows), or compare() their "
                "medians with error= for an interval.",
                rule="too_many_items",
            )
    if len(facets) < 2:
        raise ExplainError(
            f"distribution(facet=...) found {len(facets)} facet level; small multiples need 2-{MAX_FACETS}.",
            fix_hint="Drop facet= for one panel of dot strips.",
        )
    names = list(dict.fromkeys(g for f in facets for g in levels[f]))
    if len(names) > MAX_GROUPS:
        raise ExplainError(
            f"distribution(facet=...) has {len(names)} groups per facet; more than {MAX_GROUPS} "
            "rows of dots blur together.",
            fix_hint=f"Keep at most {MAX_GROUPS} groups (the ones the takeaway compares).",
            rule="too_many_items",
        )
    cells: dict[str, dict[str, np.ndarray]] = {}
    given: dict[str, dict[str, Any]] = {}
    for f in facets:
        cells[f], given[f] = {}, {}
        for g in names:
            if g not in levels[f]:
                continue
            obs = levels[f][g]
            if _is_number(obs) or obs is None or isinstance(obs, (str, bytes)):
                raise ExplainError(
                    f"distribution(groups[{f!r}][{g!r}]) is {obs!r}, not a list of observations.",
                    fix_hint="Each facet maps group names to raw observations.",
                )
            arr = _values_array(obs, f"distribution(groups[{f!r}][{g!r}])")
            given[f][g] = arr
            arr = arr[np.isfinite(arr)]
            if arr.size < 3:
                raise ExplainError(
                    f"distribution(groups[{f!r}][{g!r}]) has {arr.size} finite values; a spread needs >= 3.",
                    fix_hint="Drop that group from the facet, or use compare() for one value per group.",
                )
            cells[f][g] = arr
    hl = _names(highlight, names)
    base = _baseline_name(baseline, names, hl, "distribution")
    ref = _reference_line(reference, "distribution(reference)")
    everything = np.concatenate([a for per in cells.values() for a in per.values()])
    if log and (everything.min() <= 0 or (ref is not None and ref[0] <= 0)):
        raise ExplainError(
            "distribution(log=True) needs strictly positive values.",
            fix_hint="Drop log=True or remove non-positive values.",
        )

    def _stats(arr: np.ndarray) -> tuple[float, float, float]:
        if stat == "mean":
            m, sd = float(arr.mean()), float(arr.std(ddof=1))
            return m - sd, m, m + sd
        q1, med, q3 = (float(q) for q in np.percentile(arr, [25, 50, 75]))
        return q1, med, q3

    stats = {f: {g: _stats(a) for g, a in per.items()} for f, per in cells.items()}
    fmt_fn = _formatter(
        [v for per in stats.values() for trio in per.values() for v in trio], fmt, unit=unit, log=log
    )

    def _u(v: float) -> str:
        return _with_unit(fmt_fn(v), unit)

    rankings = {
        f: sorted(stats[f], key=lambda g, f=f: stats[f][g][1], reverse=True) for f in facets
    }
    per_facet: list[str] = []
    for f in facets:
        parts = [
            f"{g or (label or 'values')} {stat} {_u(stats[f][g][1])} (n={cells[f][g].size})"
            for g in names
            if g in cells[f]
        ]
        text = f"{f}: " + ", ".join(parts)
        if base is not None and base in cells[f]:
            for g in (hl or [nm for nm in names if nm != base])[:3]:
                if g in cells[f]:
                    diff = stats[f][g][1] - stats[f][base][1]
                    d_fmt = _formatter([diff], fmt, unit=unit)
                    text += f"; {g} \N{MINUS SIGN} {base} {_diff_with_unit(_signed(d_fmt(diff)), unit)}"
        missing = [g for g in names if g not in cells[f]]
        if missing:
            text += f"; no data for {', '.join(missing)}"
        per_facet.append(text)
    cross = _facet_cross_fact(rankings, what=f"order of {stat}s (highest first)")
    facts = ([cross] if cross else []) + per_facet
    if stat == "median":
        note = "tick: median; line: middle half"
    else:
        note = "tick: mean; line: \N{PLUS-MINUS SIGN} 1 s.d."
    notes = [note, "log scale" if log else None]
    if ref is not None:
        notes.append(f"dashed: {ref[1] or 'reference'} {_u(ref[0])}")
    lo_all, hi_all = float(everything.min()), float(everything.max())
    if ref is not None:
        lo_all, hi_all = min(lo_all, ref[0]), max(hi_all, ref[0])
    k_rows = len(names)

    def _shape(cell_w_mm: float) -> tuple[int, int]:
        return _facet_shape(len(facets), cell_w_mm, min_mm=36.0, balance=True)

    def _each_mm(sizes: _Sizes, tight: bool) -> float:
        return 6.0 + k_rows * (5.6 if (tight or sizes.compact) else 7.0) + 4.0

    def _height_mm(w: float, _m: Any, sizes: _Sizes, _t: Theme) -> float:
        nrows = _shape(w)[0]
        return nrows * _each_mm(sizes, False) + (nrows - 1) * 4.5

    def _min_height_mm(w: float, _m: Any, sizes: _Sizes, _t: Theme) -> float:
        nrows = _shape(w)[0]
        return nrows * _each_mm(sizes, True) + (nrows - 1) * 4.5

    def _frames(ctx: _Ctx, ax: Axes, rect: Bbox) -> list[tuple[Axes, Bbox]]:
        sz = ctx.sizes
        theme = ctx.theme
        _nr, ncols = _shape(ctx.cell_width_mm)
        grid = _FacetGrid(ctx, ax, rect, len(facets), ncols, share="x", rows=True)
        accent = {nm: col for nm, col in ctx.colors.items() if nm in names and nm != base}
        rng = np.random.default_rng(0)
        halo = [patheffects.withStroke(linewidth=2.6 * sz.scale, foreground=theme.background, alpha=0.9)]
        for idx, f in enumerate(facets):
            child, _sub = grid.cell(idx)
            if log and idx == 0:  # the scale and its ticks are shared by every facet
                child.set_xscale("log")
            _value_axis(child, sz, theme, axis="x", nbins=3)
            child.spines["left"].set_visible(False)
            child.spines["bottom"].set_visible(False)
            child.grid(axis="y", visible=False)
            if idx == 0:
                if log:
                    child.set_xlim(*_narrow_log_ticks(
                        child.xaxis, lo_all / 1.12, hi_all * 1.12, theme.minus_sign,
                        extend=False, data_hi=hi_all,
                    ))
                else:
                    span = (hi_all - lo_all) or abs(hi_all) or 1.0
                    child.set_xlim(lo_all - 0.04 * span, hi_all + 0.04 * span)
                    _cover_with_ticks(child.xaxis, lo_all, hi_all)
            child.set_ylim(k_rows - 0.45, -0.6)
            child.set_yticks(range(k_rows), [_plain(g, theme) for g in names])
            child.tick_params(axis="y", length=0, labelsize=sz.body, labelcolor=theme.ink,
                              labelleft=(idx % ncols == 0))
            for tick, g in zip(child.get_yticklabels(), names):
                if g in accent:
                    tick.set_fontweight("bold")
            child.tick_params(axis="x", labelbottom=grid.last_in_column(idx))
            for row, g in enumerate(names):
                if g not in cells[f]:
                    continue
                arr = cells[f][g]
                if g == base:
                    col = ctx.colors.get(g, theme.ink)
                else:
                    col = accent.get(g, theme.context_line if (hl or accent) else ctx.default_color)
                q1, med, q3 = stats[f][g]
                if log:
                    q1 = max(q1, child.get_xlim()[0])
                shown = arr if arr.size <= 400 else rng.choice(arr, size=400, replace=False)
                alpha = 0.8 if shown.size <= 30 else (0.5 if shown.size <= 150 else 0.28)
                tag_mark(ctx, child.scatter(
                    shown, row + rng.uniform(-0.2, 0.2, size=shown.size),
                    s=(3.0 * sz.scale) ** 2, color=col, alpha=alpha, linewidth=0, zorder=2,
                ), name=g or label, x=f, value=med, lo=q1, hi=q3, n=arr.size, unit=unit)
                if arr.size >= 5:
                    child.hlines(row, q1, q3, color=theme.ink, linewidth=1.0 * sz.scale, zorder=4,
                                 path_effects=halo)
                child.vlines(med, row - 0.3, row + 0.3, color=theme.ink, linewidth=2.0 * sz.scale,
                             zorder=5, path_effects=halo)
            if ref is not None:
                child.axvline(ref[0], color=theme.ink, linewidth=0.7, linestyle=(0, (3, 2)), zorder=3)
            child.set_title(_plain(f, theme), loc="left", fontsize=sz.small, fontweight="bold",
                            color=theme.ink, pad=3.0)
        ctx.finishers.append(grid.equalize)
        return grid.frames

    return Panel(
        kind="distribution",
        title=title,
        label=label,
        unit=unit,
        spec=_base_spec(
            title,
            label,
            unit,
            groups={f: {g: _jsonable(given[f][g]) for g in names if g in given[f]} for f in facets},
            facet=True,
            highlight=hl or None,
            baseline=base,
            reference=list(ref) if ref else None,
            log=log or None,
            stat=stat if stat != "median" else None,
            fmt=fmt,
        ),
        facts=facts,
        alt_facts=facts[: min(5, len(facts))],
        describe=(
            f"Small-multiple dot strips of {label or 'values'}"
            + (f" ({unit})" if unit else "")
            + f", one panel per level for {len(facets)} levels, the same {k_rows} group(s) in each "
            f"on one shared scale, each with a {stat} tick"
        ),
        _height_mm=_height_mm,
        _min_height_mm=_min_height_mm,
        _draw=lambda _ctx, _ax: None,
        _frames=_frames,
        measure_note="; ".join(nt for nt in notes if nt),
        color_items=tuple(nm for nm in names if nm),
        color_focus=tuple(hl),
        color_mode="highlight" if hl else "uniform",
        uses_default=not hl,
        color_baseline=base,
    )


def _hist_facet_panel(
    *,
    names: list[str],
    data: Mapping[str, np.ndarray],
    given: Mapping[str, Any],
    stats: Mapping[str, tuple[float, float, float]],
    hists: Mapping[str, np.ndarray],
    hl: list[str],
    base: str | None,
    ref: tuple[float, str] | None,
    stat: str,
    label: str | None,
    unit: str | None,
    given_unit: str | None,
    title: str | None,
    log: bool,
    fmt: str | None,
    fmt_fn: Callable[[float], str],
    bins_spec: Any,
    bin_note: str,
    facts: list[str],
    alt_facts: list[str],
    setup_axes: Callable[..., None],
    draw_bars: Callable[..., None],
) -> Panel:
    """``histogram(facet=True)``: one histogram per group in a grid, on shared bins and one
    shared count axis (the stacked form's axes and bars, laid out as small multiples)."""
    centre = {nm: stats[nm][1] for nm in names}
    top, low = max(names, key=lambda nm: centre[nm]), min(names, key=lambda nm: centre[nm])
    cross = (
        f"{stat} highest in {top} ({_with_unit(fmt_fn(centre[top]), unit)}), lowest in {low} "
        f"({_with_unit(fmt_fn(centre[low]), unit)}); all {len(names)} groups on the same bins"
    )
    facts = [cross, *facts]

    def _shape(cell_w_mm: float) -> tuple[int, int]:
        return _facet_shape(len(names), cell_w_mm, min_mm=36.0, balance=True)

    def _height_mm(w: float, _m: Any, sizes: _Sizes, _t: Theme) -> float:
        nrows = _shape(w)[0]
        each = 22.0 if sizes.compact else 24.0
        return nrows * each + (nrows - 1) * 4.5 + 5.0

    def _min_height_mm(w: float, _m: Any, _s: _Sizes, _t: Theme) -> float:
        nrows = _shape(w)[0]
        return nrows * 21.0 + (nrows - 1) * 4.5 + 5.0

    def _frames(ctx: _Ctx, ax: Axes, rect: Bbox) -> list[tuple[Axes, Bbox]]:
        sz = ctx.sizes
        theme = ctx.theme
        accent = {nm: col for nm, col in ctx.colors.items() if nm in names and nm != base}
        _nr, ncols = _shape(ctx.cell_width_mm)
        grid = _FacetGrid(ctx, ax, rect, len(names), ncols, share="xy", rows=True)
        room_pt = (rect.width * ctx.pt_per_px) / ncols - 6.0
        labelled = False
        for idx, nm in enumerate(names):
            child, _sub = grid.cell(idx)
            show_x = grid.last_in_column(idx)
            setup_axes(child, sz, theme, show_x=show_x, nbins_y=3,
                       cell_w_mm=ctx.cell_width_mm / ncols)
            if show_x and labelled:
                child.set_xlabel("")
            labelled = labelled or show_x
            child.tick_params(axis="y", labelleft=(idx % ncols == 0))
            draw_bars(ctx, child, nm, accent, sz, theme)
            if ref is not None:
                child.axvline(ref[0], color=theme.muted, linewidth=0.85 * sz.scale,
                              linestyle=(0, (3, 2)), zorder=3)
            weight = "bold" if (nm in accent or nm == base) else "normal"
            head = f"{nm}  n={data[nm].size}"
            if ctx.measure.width_pt(head, sz.small, weight) > room_pt:
                head = nm
            col = ctx.colors.get(nm, theme.ink) if nm == base else accent.get(nm, theme.ink)
            child.set_title(_plain(head, theme), loc="left", fontsize=sz.small, fontweight=weight,
                            color=ctx.text_color(col) if nm in accent else theme.ink, pad=5.0)
        ctx.finishers.append(grid.equalize)
        return grid.frames

    notes = [f"Count per group; {bin_note}; dashed: {stat}"]
    if ref is not None:
        notes.append(f"dotted: {ref[1] or 'reference'} {_with_unit(fmt_fn(ref[0]), unit)}")
    return Panel(
        kind="distribution",
        title=title,
        label=label,
        unit=unit,
        spec=_base_spec(
            title,
            label,
            given_unit,
            groups=_jsonable(given),
            facet=True,
            highlight=hl or None,
            baseline=base,
            reference=list(ref) if ref else None,
            log=log or None,
            stat=stat if stat != "median" else None,
            bins=bins_spec,
            fmt=fmt,
        ),
        facts=facts,
        alt_facts=[cross, *alt_facts],
        describe=(
            f"Small-multiple histograms of {label or 'values'}"
            + (f" ({unit})" if unit else "")
            + f", one per group for {len(names)} groups, on shared bins ({bin_note}) and one count axis"
        ),
        _height_mm=_height_mm,
        _min_height_mm=_min_height_mm,
        _draw=lambda _ctx, _ax: None,
        _frames=_frames,
        measure_note="; ".join(notes),
        color_items=tuple(nm for nm in names if nm),
        color_focus=tuple(hl),
        color_mode="highlight" if hl else "uniform",
        uses_default=not hl,
        color_baseline=base,
    )
