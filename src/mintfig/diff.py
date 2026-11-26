"""One-command benchmark & evaluation diff engine for mintfig.

Compares ``base`` vs ``head`` runs across any format supported by
:func:`mintfig.inspect_data.load_table_file` (``hyperfine``, ``pytest-benchmark``,
``go test -bench``, ``cargo bench``, ``k6``, ``esbuild``, CSV/TSV/JSON/JSONL),
flags noise via interval overlap, and builds a shippable ``mint.explain`` figure
plus terminal (<=72 col) and GitHub-Flavored Markdown summaries.
"""

from __future__ import annotations

import math
import textwrap
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ._explain.core import ExplainError
from ._tabular import extract_records, is_tabular
from .ingest import ToolDataset, try_load_tool_output
from .inspect_data import load_table_file

__all__ = ["DiffResult", "diff_runs"]

_NAME_COL_HINTS = (
    "name",
    "benchmark",
    "command",
    "model",
    "variant",
    "output",
    "task",
    "test",
    "service",
    "item",
    "stage",
    "id",
    "metric",
)
_AUX_NUM_COLS = frozenset(
    {"stddev", "stddev_s", "std", "err", "se", "ci", "lo", "hi", "min", "max", "n", "rounds", "iterations"}
)
_LOWER_IS_BETTER_HINTS = (
    "ms",
    "ns",
    "us",
    "_s",
    "sec",
    "time",
    "latency",
    "dur",
    "cost",
    "price",
    "usd",
    "loss",
    "err",
    "size",
    "bytes",
    "kb",
    "mb",
    "mem",
    "p50",
    "p90",
    "p95",
    "p99",
    "ttft",
)
_HIGHER_IS_BETTER_HINTS = (
    "score",
    "acc",
    "pass",
    "rate",
    "f1",
    "throughput",
    "rps",
    "qps",
    "tps",
    "ops",
    "speedup",
    "win",
    "gpqa",
    "swe",
    "aime",
    "resolved",
)
_LOWER_IS_BETTER_UNITS = frozenset({"s", "ms", "us", "µs", "ns", "ns/op", "b", "kb", "mb", "gb", "$", "usd"})


class DiffResult(dict):  # type: ignore[type-arg]
    """Result of :func:`diff_runs` (usable as both a dict and an object).

    Keys / attributes:
    ``explanation``, ``takeaway``, ``rows``, ``regressions``, ``improvements``,
    ``within_noise``, ``markdown``, ``text``, ``max_regression_pct``,
    ``metric``, ``unit``, ``higher_is_better``, ``base_label``, ``head_label``,
    ``unmatched_base``, ``unmatched_head``.
    """

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(f"DiffResult has no attribute {name!r}") from exc

    def to_json_dict(self, *, path: str | None = None) -> dict[str, Any]:
        """JSON-serializable summary of the diff (omits the Matplotlib Explanation object)."""
        exp = self.get("explanation")
        return {
            "schema_version": "0.2",
            "ok": bool(exp.ok) if exp is not None else True,
            "ship": bool(exp.ship) if exp is not None else True,
            "path": path or (str(exp.saved_path) if exp is not None and exp.saved_path else None),
            "takeaway": self["takeaway"],
            "metric": self["metric"],
            "unit": self["unit"],
            "higher_is_better": self["higher_is_better"],
            "base_label": self["base_label"],
            "head_label": self["head_label"],
            "max_regression_pct": self["max_regression_pct"],
            "regressions": self["regressions"],
            "improvements": self["improvements"],
            "within_noise": self["within_noise"],
            "unmatched_base": self["unmatched_base"],
            "unmatched_head": self["unmatched_head"],
            "rows": self["rows"],
            "markdown": self["markdown"],
            "text": self["text"],
        }


def _is_num(val: Any) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(float(val))


def _load_input(
    src: str | Path | Sequence[Mapping[str, Any]] | Mapping[str, Any] | Any,
    fallback_label: str,
) -> tuple[list[dict[str, Any]], ToolDataset | None, str]:
    if isinstance(src, (str, Path)):
        p = Path(src)
        tool_ds = try_load_tool_output(p)
        if tool_ds is not None:
            return list(tool_ds["rows"]), tool_ds, p.stem
        rows = load_table_file(p)
        return rows, None, p.stem
    if isinstance(src, Mapping):
        if src and all(_is_num(v) for v in src.values()):
            return [{"name": str(k), "value": float(v)} for k, v in src.items()], None, fallback_label
        raise ExplainError(
            f"diff_runs({fallback_label}) received a dict that is not a flat name->number mapping.",
            fix_hint="Pass a file path, list of row dicts, or {name: value} mapping.",
        )
    if is_tabular(src):
        _, rows = extract_records(src, what=f"diff_runs({fallback_label})")
        return rows, None, fallback_label
    raise ExplainError(
        f"diff_runs({fallback_label}) expected a file path, list of dicts, or mapping; got {type(src).__name__}.",
        fix_hint="Pass two benchmark/eval files or row lists, e.g. diff_runs('base.json', 'head.json').",
    )


def _disambiguate_labels(
    base: Any, head: Any, base_label: str, head_label: str
) -> tuple[str, str]:
    if base_label != head_label:
        return base_label, head_label
    if isinstance(base, (str, Path)) and isinstance(head, (str, Path)):
        bp, hp = Path(base), Path(head)
        if bp.parent.name and hp.parent.name and bp.parent.name != hp.parent.name:
            return bp.parent.name, hp.parent.name
    return "Base", "Head"


def _infer_unit(metric_col: str, tool_ds: ToolDataset | None) -> str | None:
    if tool_ds is not None and tool_ds.get("unit"):
        return str(tool_ds["unit"])
    low = metric_col.lower()
    if low == "ns_per_op" or low.endswith("_ns"):
        return "ns/op"
    if low.endswith("_ms") or low == "ms":
        return "ms"
    if low.endswith("_s") or low in {"sec", "seconds"}:
        return "s"
    if low == "kb" or low.endswith("_kb"):
        return "KB"
    if low == "bytes":
        return "B"
    if low.endswith("_pct") or "pct" in low or "percent" in low:
        return "%"
    return None


def _infer_higher_is_better(
    metric_col: str, unit: str | None, tool_ds: ToolDataset | None
) -> bool:
    if tool_ds is not None and tool_ds.get("higher_is_better") is not None:
        return bool(tool_ds["higher_is_better"])
    low = metric_col.lower()
    if any(h in low for h in _HIGHER_IS_BETTER_HINTS):
        return True
    if any(h in low for h in _LOWER_IS_BETTER_HINTS):
        return False
    return not (unit and unit.strip().lower() in _LOWER_IS_BETTER_UNITS)


def _pick_columns(
    base_rows: Sequence[Mapping[str, Any]],
    head_rows: Sequence[Mapping[str, Any]],
    *,
    name: str | None,
    metric: str | None,
    tool_ds: ToolDataset | None,
) -> tuple[str, str, tuple[str, str] | None, str | None, str | None]:
    base_cols = list(dict.fromkeys(str(k) for r in base_rows for k in r))
    head_cols = {k for r in head_rows for k in r}
    shared_cols = [c for c in base_cols if c in head_cols]
    if not shared_cols:
        raise ExplainError(
            "Base and head inputs have no shared columns.",
            fix_hint=f"Base columns: {base_cols[:8]!r}; Head columns: {sorted(head_cols)[:8]!r}.",
        )

    def _col_numeric(col: str) -> bool:
        vals = [r.get(col) for r in (*base_rows, *head_rows) if r.get(col) is not None]
        return bool(vals) and all(_is_num(v) for v in vals)

    num_cols = [c for c in shared_cols if _col_numeric(c)]
    cat_cols = [c for c in shared_cols if c not in num_cols]

    # Name column
    if name is not None:
        if name not in shared_cols:
            raise ExplainError(
                f"diff_runs(name={name!r}) column not found in both inputs.",
                fix_hint=f"Shared columns: {shared_cols!r}.",
            )
        name_col = name
    elif tool_ds is not None and tool_ds.get("name_col") in shared_cols:
        name_col = str(tool_ds["name_col"])
    else:
        name_col = next(
            (c for c in cat_cols if c.lower() in _NAME_COL_HINTS),
            cat_cols[0] if cat_cols else shared_cols[0],
        )

    # Metric column
    if metric is not None:
        if metric not in shared_cols:
            raise ExplainError(
                f"diff_runs(metric={metric!r}) column not found in both inputs.",
                fix_hint=f"Shared numeric columns: {num_cols!r}.",
            )
        metric_col = metric
    elif tool_ds is not None and tool_ds.get("value_col") in num_cols:
        metric_col = str(tool_ds["value_col"])
    else:
        primary_nums = [
            c for c in num_cols if c != name_col and c.lower() not in _AUX_NUM_COLS
        ]
        # Prefer kb over bytes if both exist
        if "kb" in primary_nums and "bytes" in primary_nums:
            metric_col = "kb"
        elif primary_nums:
            metric_col = primary_nums[0]
        elif num_cols:
            metric_col = num_cols[0]
        else:
            raise ExplainError(
                "No shared numeric metric column found between base and head.",
                fix_hint=f"Shared columns: {shared_cols!r}. Pass metric='<col>' explicitly.",
            )

    # Interval / error columns (only attach when metric matches the tool's primary metric or generic lo/hi)
    lo_hi: tuple[str, str] | None = None
    err_col: str | None = None
    error_label: str | None = None

    use_default_err = metric is None or (tool_ds is not None and metric == tool_ds.get("value_col"))
    if use_default_err:
        if tool_ds is not None and tool_ds.get("lo_col") in shared_cols and tool_ds.get("hi_col") in shared_cols:
            lo_hi = (str(tool_ds["lo_col"]), str(tool_ds["hi_col"]))
            error_label = tool_ds.get("error_label")
        elif "lo" in shared_cols and "hi" in shared_cols:
            lo_hi = ("lo", "hi")
            error_label = "interval"

        if tool_ds is not None and tool_ds.get("error_col") in shared_cols:
            err_col = str(tool_ds["error_col"])
            error_label = error_label or tool_ds.get("error_label") or "±1 s.d."
        else:
            for cand in ("stddev_s", "stddev", "std", "err", "se"):
                if cand in shared_cols and cand != metric_col:
                    err_col = cand
                    error_label = error_label or ("±1 s.d." if "std" in cand else "±err")
                    break

    return name_col, metric_col, lo_hi, err_col, error_label


def _extract_interval(
    row: Mapping[str, Any],
    val: float,
    lo_hi: tuple[str, str] | None,
    err_col: str | None,
) -> tuple[float, float] | None:
    if lo_hi is not None:
        lo_raw, hi_raw = row.get(lo_hi[0]), row.get(lo_hi[1])
        if _is_num(lo_raw) and _is_num(hi_raw):
            lo, hi = float(lo_raw), float(hi_raw)
            if hi > lo:
                return (lo, hi)
    if err_col is not None:
        err_raw = row.get(err_col)
        if _is_num(err_raw) and float(err_raw) > 0:
            e = float(err_raw)
            lo = max(0.0, val - e) if val >= 0 else val - e
            return (lo, val + e)
    return None


def _fmt_num(val: float, unit: str | None = None) -> str:
    mag = abs(val)
    if mag == 0:
        s = "0"
    elif mag >= 1000:
        s = f"{val:,.0f}" if abs(val - round(val)) < 1e-6 else f"{val:,.1f}"
    elif mag >= 10:
        s = f"{val:.1f}".rstrip("0").rstrip(".")
    elif mag >= 1:
        s = f"{val:.2f}".rstrip("0").rstrip(".")
    elif mag >= 0.01:
        s = f"{val:.3f}".rstrip("0").rstrip(".")
    else:
        s = f"{val:.4g}"
    if not unit:
        return s
    if unit == "%":
        return f"{s}%"
    if unit == "$":
        return f"-${s[1:]}" if s.startswith("-") else f"${s}"
    return f"{s} {unit}"


def _fmt_signed(val: float, unit: str | None = None) -> str:
    prefix = "+" if val > 0 else ("-" if val < 0 else "")
    body = _fmt_num(abs(val), unit)
    return f"{prefix}{body}"


def _fmt_pct(pct: float | None) -> str:
    if pct is None or not math.isfinite(pct):
        return "n/a"
    if abs(pct) < 0.05:
        return "0.0%"
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.1f}%"


def _auto_takeaway(
    rows: list[dict[str, Any]],
    regressions: list[dict[str, Any]],
    improvements: list[dict[str, Any]],
    within_noise: list[dict[str, Any]],
    *,
    metric_col: str,
    unit: str | None,
    higher_is_better: bool,
    base_label: str,
    head_label: str,
) -> str:
    if regressions:
        worst = regressions[0]
        pct = worst["delta_pct"]
        pct_s = f"{abs(pct):.1f}%" if pct is not None else _fmt_signed(worst["delta"], unit)
        verb = "dropped" if higher_is_better else "regressed"
        extra = ""
        if len(regressions) > 1:
            extra = f" ({len(regressions)} regressions total)"
        elif improvements:
            best = improvements[0]
            bpct = best["delta_pct"]
            bpct_s = f"{abs(bpct):.1f}%" if bpct is not None else _fmt_signed(best["delta"], unit)
            extra = f", while {best['name']} improved {bpct_s}"
        return f"{worst['name']} {verb} {pct_s} from {base_label} to {head_label}{extra}"

    if improvements:
        best = improvements[0]
        pct = best["delta_pct"]
        pct_s = f"{abs(pct):.1f}%" if pct is not None else _fmt_signed(best["delta"], unit)
        verb = "gained" if higher_is_better else "sped up"
        extra = f" across {len(improvements)} improved items" if len(improvements) > 1 else ""
        return f"{best['name']} {verb} {pct_s} in {head_label} vs {base_label}{extra}"

    if within_noise:
        return (
            f"All {len(rows)} items in {head_label} vs {base_label} are within measurement noise"
        )

    return f"No change in {metric_col} between {base_label} and {head_label} ({len(rows)} items)"


def _format_diff_markdown(
    takeaway: str,
    rows: list[dict[str, Any]],
    regressions: list[dict[str, Any]],
    improvements: list[dict[str, Any]],
    within_noise: list[dict[str, Any]],
    *,
    metric_col: str,
    unit: str | None,
    base_label: str,
    head_label: str,
    unmatched_base: list[str],
    unmatched_head: list[str],
) -> str:
    status_display = {
        "regression": "regression",
        "improvement": "improvement",
        "noise": "within noise",
        "unchanged": "unchanged",
    }
    headers = ["Item", base_label, head_label, "Delta", "Delta %", "Status"]
    aligns = ["left", "right", "right", "right", "right", "left"]
    body: list[list[str]] = []
    for r in rows:
        body.append(
            [
                str(r["name"]),
                _fmt_num(r["base"], unit),
                _fmt_num(r["head"], unit),
                _fmt_signed(r["delta"], unit),
                _fmt_pct(r["delta_pct"]),
                status_display.get(r["status"], r["status"]),
            ]
        )

    widths = [max(len(headers[c]), *(len(row[c]) for row in body), 3) for c in range(len(headers))]

    def _pad(val: str, w: int, al: str) -> str:
        return val.rjust(w) if al == "right" else val.ljust(w)

    def _sep(w: int, al: str) -> str:
        return ("-" * (w - 1) + ":") if al == "right" else (":" + "-" * (w - 1))

    lines = [
        f"**{takeaway}**",
        "",
        "| " + " | ".join(_pad(headers[c], widths[c], aligns[c]) for c in range(len(headers))) + " |",
        "| " + " | ".join(_sep(widths[c], aligns[c]) for c in range(len(headers))) + " |",
    ]
    for row in body:
        lines.append(
            "| " + " | ".join(_pad(row[c], widths[c], aligns[c]) for c in range(len(headers))) + " |"
        )

    facts: list[str] = [
        (
            f"Metric: `{metric_col}` ({len(rows)} matched: "
            f"{len(regressions)} regression(s), {len(improvements)} improvement(s), "
            f"{len(within_noise)} within noise)."
        )
    ]
    if regressions:
        w = regressions[0]
        facts.append(
            f"Worst regression: **{w['name']}** "
            f"({_fmt_num(w['base'], unit)} → {_fmt_num(w['head'], unit)}, {_fmt_pct(w['delta_pct'])})."
        )
    if improvements:
        b = improvements[0]
        facts.append(
            f"Largest improvement: **{b['name']}** "
            f"({_fmt_num(b['base'], unit)} → {_fmt_num(b['head'], unit)}, {_fmt_pct(b['delta_pct'])})."
        )
    if unmatched_base or unmatched_head:
        parts = []
        if unmatched_base:
            parts.append(f"{len(unmatched_base)} only in {base_label}")
        if unmatched_head:
            parts.append(f"{len(unmatched_head)} only in {head_label}")
        facts.append("Unmatched items skipped: " + ", ".join(parts) + ".")

    lines.append("")
    lines.extend(f"- {f}" for f in facts)
    return "\n".join(lines)


def _format_diff_text(
    takeaway: str,
    rows: list[dict[str, Any]],
    regressions: list[dict[str, Any]],
    improvements: list[dict[str, Any]],
    within_noise: list[dict[str, Any]],
    *,
    metric_col: str,
    unit: str | None,
    base_label: str,
    head_label: str,
    max_width: int = 72,
) -> str:
    """Compact <=72-col Unicode terminal diff summary."""
    status_short = {
        "regression": "REGR",
        "improvement": "IMPR",
        "noise": "noise",
        "unchanged": "same",
    }
    b_hdr = base_label[:10]
    h_hdr = head_label[:10]
    formatted = [
        (
            str(r["name"]),
            _fmt_num(r["base"], unit),
            _fmt_num(r["head"], unit),
            _fmt_pct(r["delta_pct"]),
            status_short.get(r["status"], r["status"]),
        )
        for r in rows
    ]
    w_b = max(len(b_hdr), *(len(x[1]) for x in formatted))
    w_h = max(len(h_hdr), *(len(x[2]) for x in formatted))
    w_p = max(len("Delta"), *(len(x[3]) for x in formatted))
    w_s = max(len("Stat"), *(len(x[4]) for x in formatted))
    # Columns separated by 2 spaces (4 gaps = 8 chars)
    fixed = w_b + w_h + w_p + w_s + 8
    w_name = max(10, min(max(len("Item"), *(len(x[0]) for x in formatted)), max_width - fixed))

    def _clip(text: str, width: int) -> str:
        if len(text) <= width:
            return text
        return text[: max(1, width - 1)] + "…"

    lines: list[str] = []
    lines.extend(textwrap.wrap(takeaway, width=max_width) or [takeaway[:max_width]])
    rule_len = min(max_width, w_name + fixed)
    lines.append("─" * rule_len)
    hdr_line = (
        f"{_clip('Item', w_name):<{w_name}}  "
        f"{b_hdr:>{w_b}}  {h_hdr:>{w_h}}  {'Delta':>{w_p}}  {'Stat':<{w_s}}"
    )
    lines.append(hdr_line[:max_width])
    for nm, b_s, h_s, p_s, st_s in formatted:
        row_line = (
            f"{_clip(nm, w_name):<{w_name}}  "
            f"{b_s:>{w_b}}  {h_s:>{w_h}}  {p_s:>{w_p}}  {st_s:<{w_s}}"
        )
        lines.append(row_line[:max_width])
    lines.append("─" * rule_len)
    footer = (
        f"{len(regressions)} regr · {len(improvements)} impr · "
        f"{len(within_noise)} noise ({metric_col})"
    )
    lines.extend(textwrap.wrap(footer, width=max_width))
    return "\n".join(lines)


def _build_diff_explanation(
    *,
    takeaway: str,
    rows: list[dict[str, Any]],
    regressions: list[dict[str, Any]],
    improvements: list[dict[str, Any]],
    within_noise: list[dict[str, Any]],
    metric_col: str,
    unit: str | None,
    base_label: str,
    head_label: str,
    has_intervals: bool,
    error_label: str | None,
    source: str | None,
    style: str,
    width: str | float,
) -> Any:
    from . import explainer as fm_exp

    # Trim to top 10 movers if > 10 items so figures stay crisp and ship cleanly
    display_rows = rows
    extra_note: str | None = None
    if len(rows) > 10:
        ranked = sorted(
            rows,
            key=lambda r: abs(r["delta_pct"]) if r["delta_pct"] is not None else abs(r["delta"]),
            reverse=True,
        )
        display_rows = ranked[:10]
        extra_note = f"Showing top 10 of {len(rows)} items by largest relative change."

    hl_names = [r["name"] for r in regressions[:2]] or [r["name"] for r in improvements[:2]]
    hl_names = [nm for nm in hl_names if any(r["name"] == nm for r in display_rows)]

    # Single-item comparison: compare base vs head directly
    if len(display_rows) == 1:
        r = display_rows[0]
        vals = {base_label: r["base"], head_label: r["head"]}
        err_map: dict[str, tuple[float, float]] | None = None
        if r["base_lo"] is not None and r["head_lo"] is not None:
            err_map = {
                base_label: (r["base_lo"], r["base_hi"]),
                head_label: (r["head_lo"], r["head_hi"]),
            }
        panel = fm_exp.compare(
            vals,
            title=r["name"],
            label=metric_col,
            unit=unit,
            baseline=base_label,
            highlight=head_label,
            sort=False,
            error=err_map,
            error_label=(error_label or "interval") if err_map else None,
        )
        with fm_exp.lenient():
            return fm_exp.explain(
                takeaway,
                panel,
                source=source or f"{base_label} vs {head_label}",
                note=extra_note,
                style=style,
                width=width,
                strict=False,
            )

    # Multi-item comparison:
    # Build percentage-delta compare panel + exact scorecard table when intervals or >5 items exist,
    # or slopegraph (change) + scorecard when clean 2..6 items without intervals on comparable scale.
    pct_values = {
        r["name"]: round(float(r["delta_pct"]), 1)
        for r in display_rows
        if r["delta_pct"] is not None and math.isfinite(float(r["delta_pct"]))
    }
    all_vals = [v for r in display_rows for v in (r["base"], r["head"]) if v > 0]
    scale_ratio = (max(all_vals) / min(all_vals)) if len(all_vals) >= 2 and min(all_vals) > 0 else 1.0
    all_zero_delta = all(abs(r["delta"]) == 0 for r in display_rows)

    status_short = {
        "regression": "regression",
        "improvement": "improvement",
        "noise": "noise",
        "unchanged": "same",
    }
    table_rows = [
        {
            "Item": r["name"],
            base_label: round(r["base"], 4),
            head_label: round(r["head"], 4),
            "Delta %": round(float(r["delta_pct"]), 1) if r["delta_pct"] is not None else None,
            "Status": status_short.get(r["status"], r["status"]),
        }
        for r in display_rows
    ]
    tbl_units: dict[str, str] = {"Delta %": "%"}
    if unit:
        tbl_units[base_label] = unit
        tbl_units[head_label] = unit

    with fm_exp.lenient():
        if not has_intervals and 2 <= len(display_rows) <= 6 and scale_ratio <= 15.0 and not all_zero_delta:
            p_change = fm_exp.change(
                {r["name"]: r["base"] for r in display_rows},
                {r["name"]: r["head"] for r in display_rows},
                labels=(base_label, head_label),
                title=f"{metric_col} ({base_label} to {head_label})",
                label=metric_col,
                unit=unit,
                highlight=hl_names or None,
            )
            return fm_exp.explain(
                takeaway,
                p_change,
                source=source or f"{base_label} vs {head_label}",
                note=extra_note,
                style=style,
                width=width,
                strict=False,
            )

        panels: list[Any] = []
        if len(pct_values) == len(display_rows) and any(v != 0.0 for v in pct_values.values()):
            p_delta = fm_exp.compare(
                pct_values,
                title=f"Relative change ({head_label} vs {base_label})",
                label="Change",
                unit="%",
                highlight=hl_names or None,
                sort="desc",
                reference=(0.0, "no change"),
            )
            panels.append(p_delta)

        p_table = fm_exp.table(
            table_rows,
            title="Scorecard",
            units=tbl_units,
            highlight=hl_names or None,
            fmt={"Delta %": "+.1f"},
        )
        panels.append(p_table)

        note_parts = [p for p in (extra_note, f"Intervals checked ({error_label})" if has_intervals and error_label else None) if p]
        layout = [["a"], ["b"]] if len(panels) == 2 else [["a"]]
        return fm_exp.explain(
            takeaway,
            *panels,
            layout=layout,
            source=source or f"{base_label} vs {head_label}",
            note="; ".join(note_parts) or None,
            style=style,
            width=width,
            strict=False,
        )


def diff_runs(
    base: str | Path | Sequence[Mapping[str, Any]] | Mapping[str, Any],
    head: str | Path | Sequence[Mapping[str, Any]] | Mapping[str, Any],
    *,
    metric: str | None = None,
    name: str | None = None,
    higher_is_better: bool | None = None,
    takeaway: str | None = None,
    source: str | None = None,
    style: str = "mintfig",
    width: str | float = "chat",
) -> DiffResult:
    """Compare two benchmark or evaluation runs (``base`` vs ``head``).

    Supports any format understood by :func:`load_table_file` (including
    ``hyperfine``, ``pytest-benchmark``, ``go test -bench``, ``cargo bench``,
    ``k6``, ``esbuild`` metafile, CSV, TSV, JSON, and JSONL) as well as
    in-memory row lists or ``{name: value}`` mappings.
    """
    base_rows, base_tool, raw_b_label = _load_input(base, "base")
    head_rows, head_tool, raw_h_label = _load_input(head, "head")
    if not base_rows:
        raise ExplainError("Base input contains no rows.", fix_hint="Provide a non-empty base run.")
    if not head_rows:
        raise ExplainError("Head input contains no rows.", fix_hint="Provide a non-empty head run.")

    base_label, head_label = _disambiguate_labels(base, head, raw_b_label, raw_h_label)
    tool_ds = base_tool or head_tool
    name_col, metric_col, lo_hi, err_col, error_label = _pick_columns(
        base_rows,
        head_rows,
        name=name,
        metric=metric,
        tool_ds=tool_ds,
    )
    unit = _infer_unit(metric_col, tool_ds)
    hib = (
        bool(higher_is_better)
        if higher_is_better is not None
        else _infer_higher_is_better(metric_col, unit, tool_ds)
    )

    base_map: dict[str, Mapping[str, Any]] = {}
    for r in base_rows:
        nm = str(r.get(name_col, "")).strip()
        if nm and _is_num(r.get(metric_col)):
            base_map[nm] = r
    head_map: dict[str, Mapping[str, Any]] = {}
    for r in head_rows:
        nm = str(r.get(name_col, "")).strip()
        if nm and _is_num(r.get(metric_col)):
            head_map[nm] = r

    shared = [nm for nm in base_map if nm in head_map]
    unmatched_base = [nm for nm in base_map if nm not in head_map]
    unmatched_head = [nm for nm in head_map if nm not in base_map]
    if not shared:
        raise ExplainError(
            f"No matching items found between {base_label!r} and {head_label!r} using name column {name_col!r}.",
            fix_hint=(
                f"Base items: {list(base_map)[:5]!r}; Head items: {list(head_map)[:5]!r}. "
                "Pass name='<col>' if item names live in another column."
            ),
        )

    diff_rows: list[dict[str, Any]] = []
    has_intervals = False
    for nm in shared:
        b_row = base_map[nm]
        h_row = head_map[nm]
        b_val = float(b_row[metric_col])
        h_val = float(h_row[metric_col])
        delta = h_val - b_val
        if b_val != 0:
            delta_pct: float | None = round((delta / abs(b_val)) * 100.0, 2)
        elif h_val == 0:
            delta_pct = 0.0
        else:
            delta_pct = None

        b_iv = _extract_interval(b_row, b_val, lo_hi, err_col)
        h_iv = _extract_interval(h_row, h_val, lo_hi, err_col)
        overlaps = False
        if b_iv is not None and h_iv is not None:
            has_intervals = True
            overlaps = max(b_iv[0], h_iv[0]) <= min(b_iv[1], h_iv[1])

        if overlaps:
            is_noise = True
            status = "noise"
        elif abs(delta) <= 1e-12 * max(1.0, abs(b_val)):
            is_noise = False
            status = "unchanged"
        else:
            is_noise = False
            is_reg = (delta < 0) if hib else (delta > 0)
            status = "regression" if is_reg else "improvement"

        diff_rows.append(
            {
                "name": nm,
                "base": b_val,
                "head": h_val,
                "delta": round(delta, 9),
                "delta_pct": delta_pct,
                "base_lo": b_iv[0] if b_iv else None,
                "base_hi": b_iv[1] if b_iv else None,
                "head_lo": h_iv[0] if h_iv else None,
                "head_hi": h_iv[1] if h_iv else None,
                "within_noise": is_noise,
                "status": status,
            }
        )

    regressions = sorted(
        [r for r in diff_rows if r["status"] == "regression"],
        key=lambda r: abs(r["delta_pct"]) if r["delta_pct"] is not None else abs(r["delta"]),
        reverse=True,
    )
    improvements = sorted(
        [r for r in diff_rows if r["status"] == "improvement"],
        key=lambda r: abs(r["delta_pct"]) if r["delta_pct"] is not None else abs(r["delta"]),
        reverse=True,
    )
    within_noise = [r for r in diff_rows if r["within_noise"]]
    max_reg_pct = round(
        max((abs(float(r["delta_pct"])) for r in regressions if r["delta_pct"] is not None), default=0.0),
        2,
    )

    final_takeaway = (
        takeaway.strip()
        if isinstance(takeaway, str) and takeaway.strip()
        else _auto_takeaway(
            diff_rows,
            regressions,
            improvements,
            within_noise,
            metric_col=metric_col,
            unit=unit,
            higher_is_better=hib,
            base_label=base_label,
            head_label=head_label,
        )
    )

    md_text = _format_diff_markdown(
        final_takeaway,
        diff_rows,
        regressions,
        improvements,
        within_noise,
        metric_col=metric_col,
        unit=unit,
        base_label=base_label,
        head_label=head_label,
        unmatched_base=unmatched_base,
        unmatched_head=unmatched_head,
    )
    term_text = _format_diff_text(
        final_takeaway,
        diff_rows,
        regressions,
        improvements,
        within_noise,
        metric_col=metric_col,
        unit=unit,
        base_label=base_label,
        head_label=head_label,
    )

    explanation = _build_diff_explanation(
        takeaway=final_takeaway,
        rows=diff_rows,
        regressions=regressions,
        improvements=improvements,
        within_noise=within_noise,
        metric_col=metric_col,
        unit=unit,
        base_label=base_label,
        head_label=head_label,
        has_intervals=has_intervals,
        error_label=error_label,
        source=source,
        style=style,
        width=width,
    )

    return DiffResult(
        explanation=explanation,
        takeaway=final_takeaway,
        rows=diff_rows,
        regressions=regressions,
        improvements=improvements,
        within_noise=within_noise,
        markdown=md_text,
        text=term_text,
        max_regression_pct=max_reg_pct,
        metric=metric_col,
        unit=unit,
        higher_is_better=hib,
        base_label=base_label,
        head_label=head_label,
        unmatched_base=unmatched_base,
        unmatched_head=unmatched_head,
    )
