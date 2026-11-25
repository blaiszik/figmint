"""Surgical one-line editing of existing mintfig figures (``mint.edit``).

Rebuilds an ``Explanation`` from a saved PNG (embedded spec), JSON spec file,
spec dict, or live ``Explanation`` object, applies top-level and panel-level
mutations (including item/series ``drop=`` / ``keep=`` filtering), and returns
the re-rendered, re-audited ``Explanation``.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ._explain.core import ExplainError
from ._explain.layout import Explanation, explain_from_spec, load

__all__ = ["edit"]

_UNSET = object()


def _as_name_list(value: str | Sequence[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]


def _resolve_panel_index(panels: list[dict[str, Any]], panel: str | int) -> int:
    if isinstance(panel, int):
        if 0 <= panel < len(panels):
            return panel
        raise ExplainError(
            f"edit(panel={panel}) out of range for {len(panels)} panel(s).",
            fix_hint=f"Pass a panel key 'a'..'{chr(ord('a') + len(panels) - 1)}' or index 0..{len(panels) - 1}.",
        )
    key = str(panel).strip().lower()
    if len(key) == 1 and "a" <= key <= "z":
        idx = ord(key) - ord("a")
        if 0 <= idx < len(panels):
            return idx
    raise ExplainError(
        f"edit(panel={panel!r}) not found in {len(panels)} panel(s).",
        fix_hint=f"Valid panel keys: {', '.join(repr(chr(ord('a') + i)) for i in range(len(panels)))}.",
    )


def _prune_refs(pspec: dict[str, Any], valid: set[str]) -> None:
    """Keep highlight/baseline/error/inner_error/boost/n consistent after dropping items."""
    hl = pspec.get("highlight")
    if isinstance(hl, str):
        if hl not in valid:
            pspec.pop("highlight", None)
    elif isinstance(hl, list):
        kept_hl = [h for h in hl if str(h) in valid]
        if kept_hl:
            pspec["highlight"] = kept_hl
        else:
            pspec.pop("highlight", None)

    base = pspec.get("baseline")
    if isinstance(base, str) and base not in valid:
        pspec.pop("baseline", None)

    for aux in ("error", "inner_error", "boost", "n", "band"):
        mapping = pspec.get(aux)
        if isinstance(mapping, dict):
            pruned = {k: v for k, v in mapping.items() if k in valid}
            if pruned:
                pspec[aux] = pruned
            else:
                pspec.pop(aux, None)


def _filter_panel_items(
    pspec: dict[str, Any],
    *,
    drop: set[str],
    keep: set[str],
) -> None:
    """Apply ``drop`` / ``keep`` filtering to a panel's normalized JSON spec in place."""
    kind = pspec.get("kind")

    def _keep_key(k: str) -> bool:
        if keep and k not in keep:
            return False
        return k not in drop

    if kind == "compare":
        vals = pspec.get("values")
        if isinstance(vals, dict) and vals:
            first = next(iter(vals.values()))
            if isinstance(first, dict):
                # Grouped compare: check if filtering categories or inner series
                all_cats = set(vals)
                all_series = {sk for sub in vals.values() if isinstance(sub, dict) for sk in sub}
                targets = drop | keep
                if targets & all_series and not (targets & all_cats):
                    new_vals = {
                        cat: {sk: sv for sk, sv in sub.items() if _keep_key(sk)}
                        for cat, sub in vals.items()
                        if isinstance(sub, dict)
                    }
                    pspec["values"] = {c: sub for c, sub in new_vals.items() if sub}
                    _prune_refs(pspec, {sk for sub in pspec["values"].values() for sk in sub})
                else:
                    pspec["values"] = {k: v for k, v in vals.items() if _keep_key(k)}
            else:
                pspec["values"] = {k: v for k, v in vals.items() if _keep_key(k)}
                _prune_refs(pspec, set(pspec["values"]))
        return

    if kind == "share":
        parts = pspec.get("parts")
        if isinstance(parts, dict):
            pspec["parts"] = {k: v for k, v in parts.items() if _keep_key(k)}
            _prune_refs(pspec, set(pspec["parts"]))
        return

    if kind == "change":
        before = pspec.get("before")
        after = pspec.get("after")
        if isinstance(before, dict) and isinstance(after, dict):
            pspec["before"] = {k: v for k, v in before.items() if _keep_key(k)}
            pspec["after"] = {k: v for k, v in after.items() if _keep_key(k)}
            _prune_refs(pspec, set(pspec["before"]) & set(pspec["after"]))
        return

    if kind in {"distribution", "histogram"}:
        gkey = "groups" if "groups" in pspec else "values"
        groups = pspec.get(gkey)
        if isinstance(groups, dict):
            pspec[gkey] = {k: v for k, v in groups.items() if _keep_key(k)}
            _prune_refs(pspec, set(pspec[gkey]))
        return

    if kind == "trend":
        for skey in ("series", "points"):
            ser = pspec.get(skey)
            if isinstance(ser, dict):
                pspec[skey] = {k: v for k, v in ser.items() if _keep_key(k)}
        valid_s = set(pspec.get("series") or {}) | set(pspec.get("points") or {})
        if valid_s:
            _prune_refs(pspec, valid_s)
        return

    if kind == "relate":
        xs = pspec.get("x") or []
        ys = pspec.get("y") or []
        names = pspec.get("names")
        groups = pspec.get("groups")
        targets = drop | keep
        use_groups = bool(groups and (targets & set(groups)) and not (names and (targets & set(names))))
        idxs = []
        for i in range(min(len(xs), len(ys))):
            key_i = str(groups[i]) if use_groups else (str(names[i]) if names else str(i))
            if _keep_key(key_i):
                idxs.append(i)
        pspec["x"] = [xs[i] for i in idxs]
        pspec["y"] = [ys[i] for i in idxs]
        if isinstance(names, list):
            pspec["names"] = [names[i] for i in idxs]
        if isinstance(groups, list):
            pspec["groups"] = [groups[i] for i in idxs]
        valid = set(pspec.get("names") or []) | set(pspec.get("groups") or [])
        _prune_refs(pspec, valid)
        return

    if kind == "matrix":
        rows = pspec.get("rows") or []
        cols = pspec.get("cols") or []
        vals = pspec.get("values") or []
        targets = drop | keep
        if targets & set(cols) and not (targets & set(rows)):
            col_idxs = [j for j, c in enumerate(cols) if _keep_key(str(c))]
            pspec["cols"] = [cols[j] for j in col_idxs]
            pspec["values"] = [[r[j] for j in col_idxs] for r in vals]
        else:
            row_idxs = [i for i, r in enumerate(rows) if _keep_key(str(r))]
            pspec["rows"] = [rows[i] for i in row_idxs]
            pspec["values"] = [vals[i] for i in row_idxs]
        return

    if kind == "table":
        cols = pspec.get("columns") or []
        rows = pspec.get("rows") or []
        targets = drop | keep
        if targets & set(cols) and not (targets & {str(r[0]) for r in rows if r}):
            col_idxs = [j for j, c in enumerate(cols) if _keep_key(str(c))]
            pspec["columns"] = [cols[j] for j in col_idxs]
            pspec["rows"] = [[r[j] for j in col_idxs] for r in rows]
            for map_k in ("units", "align", "fmt", "bold_best"):
                if isinstance(pspec.get(map_k), dict):
                    pspec[map_k] = {k: v for k, v in pspec[map_k].items() if k in pspec["columns"]}
        else:
            pspec["rows"] = [r for r in rows if r and _keep_key(str(r[0]))]
            _prune_refs(pspec, {str(r[0]) for r in pspec["rows"] if r})
        return

    if kind == "waterfall":
        steps = pspec.get("steps")
        if isinstance(steps, dict):
            pspec["steps"] = {k: v for k, v in steps.items() if _keep_key(k)}
            _prune_refs(pspec, set(pspec["steps"]))
        return

    if kind == "timeline":
        spans = pspec.get("spans")
        if isinstance(spans, list):
            pspec["spans"] = [s for s in spans if isinstance(s, list) and s and _keep_key(str(s[0]))]
            valid_t = {str(s[0]) for s in pspec["spans"]} | {
                str(s[3]) for s in pspec["spans"] if len(s) >= 4 and s[3] is not None
            }
            _prune_refs(pspec, valid_t)
        return

    if kind == "flow":
        stages = pspec.get("stages")
        if isinstance(stages, list):
            pspec["stages"] = [s for s in stages if isinstance(s, list) and s and _keep_key(str(s[0]))]
            _prune_refs(pspec, {str(s[0]) for s in pspec["stages"]})


def edit(
    figure: str | Path | Explanation | Mapping[str, Any],
    *,
    takeaway: str | None = None,
    subtitle: Any = _UNSET,
    source: Any = _UNSET,
    note: Any = _UNSET,
    style: str | None = None,
    palette: Any = _UNSET,
    accent: Any = _UNSET,
    width: str | float | None = None,
    layout: Any = _UNSET,
    colors: Any = _UNSET,
    panel: str | int = "a",
    title: Any = _UNSET,
    label: Any = _UNSET,
    unit: Any = _UNSET,
    highlight: Any = _UNSET,
    baseline: Any = _UNSET,
    sort: Any = _UNSET,
    reference: Any = _UNSET,
    show_delta: Any = _UNSET,
    drop: str | Sequence[str] | None = None,
    keep: str | Sequence[str] | None = None,
    drop_panel: str | int | None = None,
    strict: bool = True,
    out: str | Path | None = None,
    write_spec: bool = False,
) -> Explanation:
    """Apply surgical edits to an existing mintfig figure (PNG, JSON spec, or ``Explanation``).

    Returns the freshly rendered and audited :class:`Explanation`. Pass ``out=``
    to save directly to PNG, SVG, PDF, or interactive HTML.
    """
    if isinstance(figure, Explanation):
        spec = copy.deepcopy(figure.to_spec())
    elif isinstance(figure, Mapping):
        spec = copy.deepcopy(dict(figure))
    elif isinstance(figure, (str, Path)):
        spec = copy.deepcopy(load(figure).to_spec())
    else:
        raise ExplainError(
            f"edit() expected a PNG/JSON path, Explanation, or spec dict; got {type(figure).__name__}.",
            fix_hint='Pass a path like mint.edit("fig.png", style="dark", out="fig_dark.png").',
        )

    # Top-level edits
    if takeaway is not None:
        spec["takeaway"] = takeaway
    for key, val in (
        ("subtitle", subtitle),
        ("source", source),
        ("note", note),
        ("palette", palette),
        ("accent", accent),
        ("layout", layout),
        ("colors", colors),
    ):
        if val is _UNSET:
            continue
        if val is None:
            spec.pop(key, None)
        else:
            spec[key] = val
    if style is not None:
        spec["style"] = style
    if width is not None:
        spec["width"] = width

    panels = spec.get("panels")
    if not isinstance(panels, list) or not panels:
        raise ExplainError("Spec has no panels to edit.", fix_hint="Provide a valid mintfig spec.")

    # Optional whole-panel removal
    if drop_panel is not None:
        if len(panels) <= 1:
            raise ExplainError(
                "Cannot drop the only remaining panel in a figure.",
                fix_hint="Build a new figure instead of dropping its sole panel.",
            )
        rm_idx = _resolve_panel_index(panels, drop_panel)
        del panels[rm_idx]
        if layout is _UNSET:
            spec.pop("layout", None)

    # Panel-level edits
    has_panel_edits = any(
        val is not _UNSET
        for val in (title, label, unit, highlight, baseline, sort, reference, show_delta)
    ) or drop is not None or keep is not None

    if has_panel_edits:
        p_idx = _resolve_panel_index(panels, panel)
        pspec = panels[p_idx]
        if drop is not None or keep is not None:
            _filter_panel_items(
                pspec,
                drop=set(_as_name_list(drop)),
                keep=set(_as_name_list(keep)),
            )
        for pkey, pval in (
            ("title", title),
            ("label", label),
            ("unit", unit),
            ("highlight", highlight),
            ("baseline", baseline),
            ("sort", sort),
            ("reference", reference),
            ("show_delta", show_delta),
        ):
            if pval is _UNSET:
                continue
            if pval is None:
                pspec.pop(pkey, None)
            else:
                pspec[pkey] = pval

    result = explain_from_spec(spec, strict=strict)
    if out is not None:
        result.save(out, write_spec=write_spec)
    return result
