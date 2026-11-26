"""Zero-dependency ingestors for common SWE benchmark, trace, CI, and eval tool outputs.

Auto-detects and normalizes outputs from:
- ``hyperfine --export-json``
- ``pytest-benchmark`` JSON
- ``go test -bench`` text logs (``.txt`` / ``.log`` / ``.out``)
- ``cargo bench`` text logs (``.txt`` / ``.log`` / ``.out``)
- GitHub Actions job/step timing JSON
- Chrome Trace / OpenTelemetry span JSON
- ``k6 --summary-export`` JSON
- ``esbuild`` / ``vite`` bundle metafile JSON
- LLM / Agent evaluation JSON / JSONL tables
"""

from __future__ import annotations

import json
import math
import re
import statistics
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from ._explain.core import ExplainError

__all__ = [
    "SUPPORTED_TOOL_FORMATS",
    "ToolDataset",
    "detect_llm_eval_columns",
    "detect_tool_format",
    "load_tool_output",
    "try_load_tool_output",
]

SUPPORTED_TOOL_FORMATS = (
    "hyperfine",
    "pytest_benchmark",
    "go_bench",
    "cargo_bench",
    "github_actions",
    "chrome_trace",
    "k6",
    "esbuild_metafile",
    "llm_eval",
)

# Go: `BenchmarkFoo-8    10000    1234 ns/op` (optional `128 B/op`, `2 allocs/op`)
_GO_BENCH_RE = re.compile(
    r"^(Benchmark\S+)\s+(\d+)\s+([0-9][0-9,]*(?:\.[0-9]+)?)\s+(ns/op|us/op|µs/op|μs/op|ms/op|s/op)"
    r"(?:\s+([0-9][0-9,]*(?:\.[0-9]+)?)\s+B/op)?"
    r"(?:\s+([0-9][0-9,]*(?:\.[0-9]+)?)\s+allocs/op)?",
    re.MULTILINE,
)

# Rust `cargo bench` (libtest): `test foo ... bench:       1,234 ns/iter (+/- 45)`
_CARGO_BENCH_RE = re.compile(
    r"^test\s+(\S+)\s+\.\.\.\s+bench:\s+([0-9][0-9,]*(?:\.[0-9]+)?)\s+ns/iter"
    r"(?:\s+\(\+/-\s+([0-9][0-9,]*(?:\.[0-9]+)?)\))?",
    re.MULTILINE,
)

_GO_UNIT_TO_NS = {
    "ns/op": 1.0,
    "us/op": 1_000.0,
    "µs/op": 1_000.0,
    "μs/op": 1_000.0,
    "ms/op": 1_000_000.0,
    "s/op": 1_000_000_000.0,
}

_K6_STAT_ORDER = ("min", "med", "avg", "p(90)", "p(95)", "p(99)", "max")
_K6_TREND_KEYS = frozenset({"avg", "med", "p(90)", "p(95)", "p(99)", "max", "min"})

_EVAL_MODEL_HINTS = ("model", "variant", "agent", "system", "config", "prompt", "run", "candidate")
_EVAL_SCORE_HINTS = (
    "score",
    "pass_rate",
    "pass@",
    "passed",
    "accuracy",
    "acc",
    "f1",
    "resolved",
    "gpqa",
    "swe",
    "aime",
    "mmlu",
    "humaneval",
    "quality",
    "win_rate",
    "success",
)
_EVAL_COST_HINTS = (
    "latency",
    "cost",
    "price",
    "usd",
    "dollar",
    "ms",
    "ttft",
    "duration",
    "time",
    "tokens",
    "flops",
    "memory",
)


class ToolDataset(dict):  # type: ignore[type-arg]
    """Normalized SWE tool dataset returned by :func:`load_tool_output`.

    Behaves as a JSON-serializable dict with attribute access for convenience.
    Keys: ``format``, ``rows``, ``meta``, ``recommended_kind``, ``recommended_params``,
    ``recommendations``, ``unit``, ``higher_is_better``, ``name_col``, ``value_col``,
    ``error_col``, ``lo_col``, ``hi_col``, ``error_label``.
    """

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(f"ToolDataset has no attribute {name!r}") from exc


def _is_num(val: Any) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(float(val))


def _parse_float(raw: str) -> float:
    return float(raw.replace(",", ""))


def _parse_iso_timestamp(raw: Any) -> float | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def detect_llm_eval_columns(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, str] | None:
    """Return ``{"name", "x", "y"}`` if ``rows`` look like an LLM/agent evaluation table.

    Requires at least 2 rows, a model/variant identifier column, a score/pass_rate
    numeric column, and a distinct latency/cost numeric column.
    """
    if len(rows) < 2:
        return None
    cols = list(dict.fromkeys(str(k) for r in rows for k in r))
    num_cols: list[str] = []
    cat_cols: list[str] = []
    for col in cols:
        vals = [r.get(col) for r in rows if r.get(col) is not None]
        if not vals:
            continue
        if all(_is_num(v) for v in vals):
            num_cols.append(col)
        else:
            cat_cols.append(col)

    if not cat_cols or len(num_cols) < 2:
        return None

    model_col = next(
        (c for c in cat_cols if any(h in c.lower() for h in _EVAL_MODEL_HINTS)),
        None,
    )
    if model_col is None:
        return None
    cost_col = next(
        (c for c in num_cols if any(h in c.lower() for h in _EVAL_COST_HINTS)),
        None,
    )
    score_col = next(
        (c for c in num_cols if c != cost_col and any(h in c.lower() for h in _EVAL_SCORE_HINTS)),
        None,
    )
    if cost_col is None or score_col is None:
        return None
    return {"name": model_col, "x": cost_col, "y": score_col}


def _detect_json_format(payload: Any) -> str | None:
    if isinstance(payload, Mapping):
        # 1. hyperfine --export-json
        results = payload.get("results")
        if (
            isinstance(results, list)
            and results
            and all(
                isinstance(r, Mapping)
                and isinstance(r.get("command"), str)
                and _is_num(r.get("mean"))
                for r in results
            )
        ):
            return "hyperfine"

        # 2. pytest-benchmark JSON
        benchmarks = payload.get("benchmarks")
        if (
            isinstance(benchmarks, list)
            and benchmarks
            and all(
                isinstance(b, Mapping)
                and isinstance(b.get("stats"), Mapping)
                and _is_num(b["stats"].get("mean"))
                and (isinstance(b.get("name"), str) or isinstance(b.get("fullname"), str))
                for b in benchmarks
            )
        ):
            return "pytest_benchmark"

        # 3. GitHub Actions job/step timing JSON
        jobs = payload.get("jobs")
        if (
            isinstance(jobs, list)
            and jobs
            and any(
                isinstance(j, Mapping)
                and isinstance(j.get("name"), str)
                and (
                    (
                        _parse_iso_timestamp(j.get("started_at")) is not None
                        and _parse_iso_timestamp(j.get("completed_at")) is not None
                    )
                    or (
                        isinstance(j.get("steps"), list)
                        and any(
                            isinstance(s, Mapping)
                            and _parse_iso_timestamp(s.get("started_at")) is not None
                            and _parse_iso_timestamp(s.get("completed_at")) is not None
                            for s in j["steps"]
                        )
                    )
                )
                for j in jobs
            )
        ):
            return "github_actions"

        # 4. Chrome Trace / OTEL JSON
        trace_events = payload.get("traceEvents")
        if (
            isinstance(trace_events, list)
            and trace_events
            and any(
                isinstance(ev, Mapping)
                and isinstance(ev.get("name"), str)
                and _is_num(ev.get("ts"))
                and (ev.get("ph") in {"X", "B", "E"} or _is_num(ev.get("dur")))
                for ev in trace_events
            )
        ):
            return "chrome_trace"

        # 5. k6 --summary-export JSON
        metrics = payload.get("metrics")
        if isinstance(metrics, Mapping) and metrics:
            has_k6_trend = False
            for mval in metrics.values():
                if not isinstance(mval, Mapping):
                    continue
                vals = mval.get("values") if isinstance(mval.get("values"), Mapping) else mval
                if not isinstance(vals, Mapping):
                    continue
                numeric_trend_keys = [
                    k for k in _K6_TREND_KEYS if k in vals and _is_num(vals[k])
                ]
                if len(numeric_trend_keys) >= 2:
                    has_k6_trend = True
                    break
            if has_k6_trend:
                return "k6"

        # 6. esbuild / vite metafile JSON
        outputs = payload.get("outputs")
        if (
            isinstance(outputs, Mapping)
            and outputs
            and all(
                isinstance(meta, Mapping) and _is_num(meta.get("bytes"))
                for meta in outputs.values()
            )
        ):
            return "esbuild_metafile"

    elif (
        isinstance(payload, list)
        and payload
        and all(
            isinstance(ev, Mapping)
            and isinstance(ev.get("name"), str)
            and _is_num(ev.get("ts"))
            and isinstance(ev.get("ph"), str)
            for ev in payload
        )
    ):
        # Chrome trace exported as bare event array
        return "chrome_trace"

    return None


def _detect_text_format(raw_text: str) -> str | None:
    if _GO_BENCH_RE.search(raw_text):
        return "go_bench"
    if _CARGO_BENCH_RE.search(raw_text):
        return "cargo_bench"
    return None


def detect_tool_format(
    source: str | Path | None = None,
    *,
    raw_text: str | None = None,
    payload: Any = None,
) -> str | None:
    """Detect whether ``source``, ``raw_text``, or ``payload`` is a supported SWE tool output.

    Returns one of :data:`SUPPORTED_TOOL_FORMATS` or ``None`` for generic tabular data.
    """
    if payload is not None:
        return _detect_json_format(payload)

    text = raw_text
    suffix = ""
    if text is None and source is not None:
        if isinstance(source, Path):
            suffix = source.suffix.lower()
            text = source.read_text(encoding="utf-8-sig")
        else:
            p = Path(source)
            if p.exists() and p.is_file():
                suffix = p.suffix.lower()
                text = p.read_text(encoding="utf-8-sig")
            else:
                text = str(source)
    elif isinstance(source, (str, Path)):
        suffix = Path(source).suffix.lower()

    if text is None or not text.strip():
        return None

    stripped = text.lstrip()
    if suffix == ".json" or stripped.startswith(("{", "[")):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if parsed is not None:
            fmt = _detect_json_format(parsed)
            if fmt is not None:
                return fmt

    if suffix in {".txt", ".log", ".out", ""} or not stripped.startswith(("{", "[")):
        fmt = _detect_text_format(text)
        if fmt is not None:
            return fmt

    return None


def _parse_hyperfine(payload: Mapping[str, Any], *, raw_times: bool = False) -> ToolDataset:
    results = payload["results"]
    seen_names: dict[str, int] = {}
    summary_rows: list[dict[str, Any]] = []
    time_rows: list[dict[str, Any]] = []
    has_stddev = False
    has_minmax = False

    for entry in results:
        cmd = str(entry["command"]).strip()
        params = entry.get("parameters")
        if isinstance(params, Mapping) and params:
            param_tag = ", ".join(f"{k}={v}" for k, v in params.items())
            if param_tag not in cmd:
                cmd = f"{cmd} ({param_tag})"
        count = seen_names.get(cmd, 0) + 1
        seen_names[cmd] = count
        name = cmd if count == 1 else f"{cmd} #{count}"

        mean_s = float(entry["mean"])
        stddev_raw = entry.get("stddev")
        stddev_s = float(stddev_raw) if _is_num(stddev_raw) else None
        min_raw = entry.get("min")
        max_raw = entry.get("max")
        min_s = float(min_raw) if _is_num(min_raw) else None
        max_s = float(max_raw) if _is_num(max_raw) else None
        times = entry.get("times")
        n_runs = len(times) if isinstance(times, list) else None

        if stddev_s is not None and stddev_s > 0:
            has_stddev = True
            lo = max(0.0, mean_s - stddev_s) if mean_s >= 0 else mean_s - stddev_s
            hi = mean_s + stddev_s
        elif min_s is not None and max_s is not None:
            has_minmax = True
            lo, hi = min_s, max_s
        else:
            lo, hi = None, None

        row: dict[str, Any] = {
            "name": name,
            "mean_s": round(mean_s, 9),
            "stddev_s": round(stddev_s, 9) if stddev_s is not None else None,
            "lo": round(lo, 9) if lo is not None else None,
            "hi": round(hi, 9) if hi is not None else None,
            "n": n_runs,
        }
        summary_rows.append(row)

        if isinstance(times, list):
            for t in times:
                if _is_num(t):
                    time_rows.append({"name": name, "time_s": round(float(t), 9)})

    error_label = "±1 s.d." if has_stddev else ("min–max" if has_minmax else None)
    has_err = has_stddev or has_minmax

    if raw_times and time_rows:
        rec_params: dict[str, Any] = {
            "group": "name",
            "value": "time_s",
            "unit": "s",
            "mode": "quantile" if (len(time_rows) / max(len(summary_rows), 1)) >= 15 else "dots",
        }
        recs = [
            {
                "kind": "distribution",
                "reason": f"hyperfine raw timing runs ({len(time_rows)} samples across {len(summary_rows)} commands).",
                "python": 'mint.distribution(rows, group="name", value="time_s", unit="s")',
                "cli_flags": "--group name --value time_s --unit s",
                "params": rec_params,
            }
        ]
        return ToolDataset(
            format="hyperfine",
            rows=time_rows,
            meta={"commands": len(summary_rows), "raw_times": True, "samples": len(time_rows)},
            recommended_kind="distribution",
            recommended_params=rec_params,
            recommendations=recs,
            unit="s",
            higher_is_better=False,
            name_col="name",
            value_col="time_s",
            error_col=None,
            lo_col=None,
            hi_col=None,
            error_label=None,
        )

    rec_params = {
        "name": "name",
        "value": "mean_s",
        "unit": "s",
        "sort": "asc",
    }
    if has_err and error_label:
        rec_params["error"] = ("lo", "hi")
        rec_params["error_label"] = error_label
    err_py = f', error=("lo", "hi"), error_label="{error_label}"' if (has_err and error_label) else ""
    recs = [
        {
            "kind": "compare",
            "reason": f"hyperfine benchmark ({len(summary_rows)} commands, lower is faster"
            + (f", {error_label}" if error_label else "")
            + ").",
            "python": f'mint.compare(rows, name="name", value="mean_s", unit="s", sort="asc"{err_py})',
            "cli_flags": "--name name --value mean_s --unit s --sort asc",
            "params": rec_params,
        }
    ]
    if time_rows:
        recs.append(
            {
                "kind": "distribution",
                "reason": f"Raw hyperfine sample times available ({len(time_rows)} samples); call load_tool_output(path, raw_times=True).",
                "python": 'mint.distribution(load_tool_output(path, raw_times=True)["rows"], group="name", value="time_s", unit="s")',
                "cli_flags": "",
                "params": {"group": "name", "value": "time_s", "unit": "s"},
            }
        )

    return ToolDataset(
        format="hyperfine",
        rows=summary_rows,
        meta={
            "commands": len(summary_rows),
            "raw_times": False,
            "has_raw_times": bool(time_rows),
        },
        recommended_kind="compare",
        recommended_params=rec_params,
        recommendations=recs,
        unit="s",
        higher_is_better=False,
        name_col="name",
        value_col="mean_s",
        error_col="stddev_s" if has_stddev else None,
        lo_col="lo" if has_err else None,
        hi_col="hi" if has_err else None,
        error_label=error_label,
    )


def _parse_pytest_benchmark(payload: Mapping[str, Any]) -> ToolDataset:
    benchmarks = payload["benchmarks"]
    rows: list[dict[str, Any]] = []
    has_stddev = False
    has_minmax = False

    for entry in benchmarks:
        name = str(entry.get("name") or entry.get("fullname") or "benchmark").strip()
        stats = entry["stats"]
        mean_ms = float(stats["mean"]) * 1000.0
        std_raw = stats.get("stddev")
        stddev_ms = float(std_raw) * 1000.0 if _is_num(std_raw) else None
        min_ms = float(stats["min"]) * 1000.0 if _is_num(stats.get("min")) else None
        max_ms = float(stats["max"]) * 1000.0 if _is_num(stats.get("max")) else None
        rounds = int(stats["rounds"]) if _is_num(stats.get("rounds")) else None

        if stddev_ms is not None and stddev_ms > 0:
            has_stddev = True
            lo = max(0.0, mean_ms - stddev_ms) if mean_ms >= 0 else mean_ms - stddev_ms
            hi = mean_ms + stddev_ms
        elif min_ms is not None and max_ms is not None:
            has_minmax = True
            lo, hi = min_ms, max_ms
        else:
            lo, hi = None, None

        rows.append(
            {
                "name": name,
                "mean_ms": round(mean_ms, 6),
                "stddev": round(stddev_ms, 6) if stddev_ms is not None else None,
                "lo": round(lo, 6) if lo is not None else None,
                "hi": round(hi, 6) if hi is not None else None,
                "rounds": rounds,
            }
        )

    error_label = "±1 s.d." if has_stddev else ("min–max" if has_minmax else None)
    has_err = has_stddev or has_minmax
    rec_params: dict[str, Any] = {
        "name": "name",
        "value": "mean_ms",
        "unit": "ms",
        "sort": "asc",
    }
    if has_err and error_label:
        rec_params["error"] = ("lo", "hi")
        rec_params["error_label"] = error_label
    err_py = f', error=("lo", "hi"), error_label="{error_label}"' if (has_err and error_label) else ""
    recs = [
        {
            "kind": "compare",
            "reason": f"pytest-benchmark suite ({len(rows)} benchmarks, lower is faster"
            + (f", {error_label}" if error_label else "")
            + ").",
            "python": f'mint.compare(rows, name="name", value="mean_ms", unit="ms", sort="asc"{err_py})',
            "cli_flags": "--name name --value mean_ms --unit ms --sort asc",
            "params": rec_params,
        }
    ]
    return ToolDataset(
        format="pytest_benchmark",
        rows=rows,
        meta={"benchmarks": len(rows)},
        recommended_kind="compare",
        recommended_params=rec_params,
        recommendations=recs,
        unit="ms",
        higher_is_better=False,
        name_col="name",
        value_col="mean_ms",
        error_col="stddev" if has_stddev else None,
        lo_col="lo" if has_err else None,
        hi_col="hi" if has_err else None,
        error_label=error_label,
    )


def _parse_go_bench(raw_text: str) -> ToolDataset:
    grouped: dict[str, list[dict[str, float | int | None]]] = {}
    order: list[str] = []
    for match in _GO_BENCH_RE.finditer(raw_text):
        name = match.group(1)
        iters = int(match.group(2))
        val = _parse_float(match.group(3)) * _GO_UNIT_TO_NS[match.group(4)]
        b_op = _parse_float(match.group(5)) if match.group(5) else None
        allocs = _parse_float(match.group(6)) if match.group(6) else None
        if name not in grouped:
            grouped[name] = []
            order.append(name)
        grouped[name].append({"ns": val, "iters": iters, "b_op": b_op, "allocs": allocs})

    if not order:
        raise ExplainError(
            "No `go test -bench` benchmark lines found.",
            fix_hint="Expected lines like `BenchmarkFoo-8  10000  1234 ns/op`.",
        )

    rows: list[dict[str, Any]] = []
    has_err = False
    for name in order:
        samples = grouped[name]
        ns_vals = [float(s["ns"]) for s in samples]  # type: ignore[arg-type]
        mean_ns = statistics.fmean(ns_vals)
        err = statistics.stdev(ns_vals) if len(ns_vals) >= 2 else None
        if err is not None and err > 0:
            has_err = True
        row: dict[str, Any] = {
            "name": name,
            "ns_per_op": round(mean_ns, 4),
        }
        if err is not None:
            row["err"] = round(err, 4)
            row["lo"] = round(max(0.0, mean_ns - err), 4)
            row["hi"] = round(mean_ns + err, 4)
        rows.append(row)

    rec_params: dict[str, Any] = {
        "name": "name",
        "value": "ns_per_op",
        "unit": "ns/op",
        "sort": "asc",
    }
    error_label = "±1 s.d." if has_err else None
    if has_err and error_label:
        rec_params["error"] = ("lo", "hi")
        rec_params["error_label"] = error_label
    err_py = f', error=("lo", "hi"), error_label="{error_label}"' if (has_err and error_label) else ""
    recs = [
        {
            "kind": "compare",
            "reason": f"go test -bench output ({len(rows)} benchmarks, ns/op).",
            "python": f'mint.compare(rows, name="name", value="ns_per_op", unit="ns/op", sort="asc"{err_py})',
            "cli_flags": '--name name --value ns_per_op --unit "ns/op" --sort asc',
            "params": rec_params,
        }
    ]
    return ToolDataset(
        format="go_bench",
        rows=rows,
        meta={"benchmarks": len(rows)},
        recommended_kind="compare",
        recommended_params=rec_params,
        recommendations=recs,
        unit="ns/op",
        higher_is_better=False,
        name_col="name",
        value_col="ns_per_op",
        error_col="err" if has_err else None,
        lo_col="lo" if has_err else None,
        hi_col="hi" if has_err else None,
        error_label=error_label,
    )


def _parse_cargo_bench(raw_text: str) -> ToolDataset:
    rows: list[dict[str, Any]] = []
    has_err = False
    for match in _CARGO_BENCH_RE.finditer(raw_text):
        name = match.group(1)
        val = _parse_float(match.group(2))
        err = _parse_float(match.group(3)) if match.group(3) else None
        if err is not None and err > 0:
            has_err = True
        row: dict[str, Any] = {"name": name, "ns_per_op": round(val, 4)}
        if err is not None:
            row["err"] = round(err, 4)
            row["lo"] = round(max(0.0, val - err), 4)
            row["hi"] = round(val + err, 4)
        rows.append(row)

    if not rows:
        raise ExplainError(
            "No `cargo bench` benchmark lines found.",
            fix_hint="Expected lines like `test foo ... bench: 1,234 ns/iter (+/- 45)`.",
        )

    rec_params: dict[str, Any] = {
        "name": "name",
        "value": "ns_per_op",
        "unit": "ns/op",
        "sort": "asc",
    }
    error_label = "±range" if has_err else None
    if has_err and error_label:
        rec_params["error"] = ("lo", "hi")
        rec_params["error_label"] = error_label
    err_py = f', error=("lo", "hi"), error_label="{error_label}"' if (has_err and error_label) else ""
    recs = [
        {
            "kind": "compare",
            "reason": f"cargo bench output ({len(rows)} benchmarks, ns/iter).",
            "python": f'mint.compare(rows, name="name", value="ns_per_op", unit="ns/op", sort="asc"{err_py})',
            "cli_flags": '--name name --value ns_per_op --unit "ns/op" --sort asc',
            "params": rec_params,
        }
    ]
    return ToolDataset(
        format="cargo_bench",
        rows=rows,
        meta={"benchmarks": len(rows)},
        recommended_kind="compare",
        recommended_params=rec_params,
        recommendations=recs,
        unit="ns/op",
        higher_is_better=False,
        name_col="name",
        value_col="ns_per_op",
        error_col="err" if has_err else None,
        lo_col="lo" if has_err else None,
        hi_col="hi" if has_err else None,
        error_label=error_label,
    )


def _parse_github_actions(payload: Mapping[str, Any]) -> ToolDataset:
    jobs = payload["jobs"]
    raw_spans: list[tuple[str, float, float, str]] = []
    for job in jobs:
        if not isinstance(job, Mapping):
            continue
        job_name = str(job.get("name") or "job").strip()
        steps = job.get("steps")
        step_spans: list[tuple[str, float, float, str]] = []
        if isinstance(steps, list):
            for step in steps:
                if not isinstance(step, Mapping):
                    continue
                s_ts = _parse_iso_timestamp(step.get("started_at"))
                e_ts = _parse_iso_timestamp(step.get("completed_at"))
                if s_ts is None or e_ts is None:
                    continue
                step_name = str(step.get("name") or "step").strip()
                step_spans.append((step_name, s_ts, max(s_ts, e_ts), job_name))
        if step_spans:
            raw_spans.extend(step_spans)
        else:
            s_ts = _parse_iso_timestamp(job.get("started_at"))
            e_ts = _parse_iso_timestamp(job.get("completed_at"))
            if s_ts is not None and e_ts is not None:
                grp = str(job.get("conclusion") or "job")
                raw_spans.append((job_name, s_ts, max(s_ts, e_ts), grp))

    if not raw_spans:
        raise ExplainError(
            "GitHub Actions JSON contained no jobs or steps with valid timestamps.",
            fix_hint="Ensure jobs or steps carry ISO-8601 started_at and completed_at fields.",
        )

    t0 = min(s[1] for s in raw_spans)
    rows = [
        {
            "name": nm,
            "start_s": round(s - t0, 3),
            "end_s": round(e - t0, 3),
            "group": grp,
        }
        for nm, s, e, grp in raw_spans
    ]
    unique_groups = list(dict.fromkeys(r["group"] for r in rows))
    use_group = "group" if 1 <= len(unique_groups) <= 4 else None
    rec_params: dict[str, Any] = {
        "name": "name",
        "start": "start_s",
        "end": "end_s",
        "unit": "s",
    }
    if use_group:
        rec_params["group"] = use_group
    grp_py = ', group="group"' if use_group else ""
    grp_cli = " --group group" if use_group else ""
    recs = [
        {
            "kind": "timeline",
            "reason": f"GitHub Actions workflow timings ({len(rows)} spans across {len(unique_groups)} job(s)).",
            "python": f'mint.timeline(rows, name="name", start="start_s", end="end_s"{grp_py}, unit="s")',
            "cli_flags": f"--name name --start start_s --end end_s{grp_cli} --unit s",
            "params": rec_params,
        }
    ]
    return ToolDataset(
        format="github_actions",
        rows=rows,
        meta={"spans": len(rows), "jobs": len(jobs)},
        recommended_kind="timeline",
        recommended_params=rec_params,
        recommendations=recs,
        unit="s",
        higher_is_better=False,
        name_col="name",
        value_col="end_s",
        error_col=None,
        lo_col=None,
        hi_col=None,
        error_label=None,
    )


def _parse_chrome_trace(payload: Any) -> ToolDataset:
    events = payload["traceEvents"] if isinstance(payload, Mapping) else payload
    raw_spans: list[tuple[str, float, float, str]] = []

    # Complete events (ph == "X")
    for ev in events:
        if not isinstance(ev, Mapping):
            continue
        if ev.get("ph") == "X" and _is_num(ev.get("ts")) and _is_num(ev.get("dur")):
            nm = str(ev.get("name") or "span").strip()
            ts = float(ev["ts"])
            dur = max(0.0, float(ev["dur"]))
            grp = str(ev.get("cat") or ev.get("pid") or "trace").strip()
            raw_spans.append((nm, ts, ts + dur, grp))

    # Fallback: match B/E pairs if no X events were present
    if not raw_spans:
        stacks: dict[tuple[str, str], list[float]] = {}
        for ev in events:
            if not isinstance(ev, Mapping) or not _is_num(ev.get("ts")):
                continue
            ph = ev.get("ph")
            nm = str(ev.get("name") or "span").strip()
            grp = str(ev.get("cat") or ev.get("pid") or "trace").strip()
            key = (nm, grp)
            if ph == "B":
                stacks.setdefault(key, []).append(float(ev["ts"]))
            elif ph == "E" and stacks.get(key):
                start_ts = stacks[key].pop()
                end_ts = max(start_ts, float(ev["ts"]))
                raw_spans.append((nm, start_ts, end_ts, grp))

    if not raw_spans:
        raise ExplainError(
            "Chrome Trace JSON contained no complete (`ph: 'X'`) or matched `B`/`E` span events.",
            fix_hint="Provide traceEvents with numeric `ts` and `dur` (ph='X').",
        )

    t0 = min(s[1] for s in raw_spans)
    rows = [
        {
            "name": nm,
            "start_ms": round((s - t0) / 1000.0, 3),
            "end_ms": round((e - t0) / 1000.0, 3),
            "group": grp,
        }
        for nm, s, e, grp in raw_spans
    ]
    unique_groups = list(dict.fromkeys(r["group"] for r in rows))
    use_group = "group" if 1 <= len(unique_groups) <= 4 else None
    rec_params: dict[str, Any] = {
        "name": "name",
        "start": "start_ms",
        "end": "end_ms",
        "unit": "ms",
    }
    if use_group:
        rec_params["group"] = use_group
    grp_py = ', group="group"' if use_group else ""
    grp_cli = " --group group" if use_group else ""
    recs = [
        {
            "kind": "timeline",
            "reason": f"Chrome Trace / OTEL spans ({len(rows)} spans in ms).",
            "python": f'mint.timeline(rows, name="name", start="start_ms", end="end_ms"{grp_py}, unit="ms")',
            "cli_flags": f"--name name --start start_ms --end end_ms{grp_cli} --unit ms",
            "params": rec_params,
        }
    ]
    return ToolDataset(
        format="chrome_trace",
        rows=rows,
        meta={"spans": len(rows)},
        recommended_kind="timeline",
        recommended_params=rec_params,
        recommendations=recs,
        unit="ms",
        higher_is_better=False,
        name_col="name",
        value_col="end_ms",
        error_col=None,
        lo_col=None,
        hi_col=None,
        error_label=None,
    )


def _parse_k6(payload: Mapping[str, Any]) -> ToolDataset:
    metrics = payload["metrics"]
    trend_metrics: list[tuple[str, dict[str, float]]] = []
    for mname, mobj in metrics.items():
        if not isinstance(mobj, Mapping):
            continue
        vals = mobj.get("values") if isinstance(mobj.get("values"), Mapping) else mobj
        if not isinstance(vals, Mapping):
            continue
        extracted = {
            k: float(vals[k]) for k in _K6_STAT_ORDER if k in vals and _is_num(vals[k])
        }
        if len(extracted) >= 2:
            trend_metrics.append((str(mname), extracted))

    if not trend_metrics:
        raise ExplainError(
            "k6 summary JSON contained no latency/trend metrics with percentile values.",
            fix_hint="Expected metrics like `http_req_duration` with `values: {avg, med, p(90), p(95), max}`.",
        )

    # Single trend metric (or http_req_duration alone): one row per percentile stat
    if len(trend_metrics) == 1:
        mname, stats = trend_metrics[0]
        rows = [{"name": stat, "ms": round(val, 4)} for stat, val in stats.items()]
        rec_params: dict[str, Any] = {
            "name": "name",
            "value": "ms",
            "unit": "ms",
            "sort": False,
        }
        recs = [
            {
                "kind": "compare",
                "reason": f"k6 latency percentiles for {mname!r} ({len(rows)} stats in ms).",
                "python": 'mint.compare(rows, name="name", value="ms", unit="ms", sort=False)',
                "cli_flags": "--name name --value ms --unit ms --sort false",
                "params": rec_params,
            },
            {
                "kind": "table",
                "reason": f"Exact k6 latency summary table for {mname!r}.",
                "python": "mint.table(rows)",
                "cli_flags": "",
                "params": {},
            },
        ]
        return ToolDataset(
            format="k6",
            rows=rows,
            meta={"metric": mname, "stats": len(rows)},
            recommended_kind="compare",
            recommended_params=rec_params,
            recommendations=recs,
            unit="ms",
            higher_is_better=False,
            name_col="name",
            value_col="ms",
            error_col=None,
            lo_col=None,
            hi_col=None,
            error_label=None,
        )

    # Multiple trend metrics: multi-metric scorecard rows
    stat_keys = [k for k in _K6_STAT_ORDER if any(k in stats for _, stats in trend_metrics)]
    rows = []
    for mname, stats in trend_metrics:
        row: dict[str, Any] = {"name": mname}
        for sk in stat_keys:
            col = sk.replace("(", "").replace(")", "") + "_ms"
            row[col] = round(stats[sk], 4) if sk in stats else None
        rows.append(row)

    primary_col = next(
        (c for c in ("p95_ms", "avg_ms", "med_ms", "max_ms") if c in rows[0]),
        next(k for k in rows[0] if k != "name"),
    )
    recs = [
        {
            "kind": "compare",
            "reason": f"k6 summary across {len(rows)} latency metrics (ranked by {primary_col!r}).",
            "python": f'mint.compare(rows, name="name", value="{primary_col}", unit="ms")',
            "cli_flags": f"--name name --value {primary_col} --unit ms",
            "params": {"name": "name", "value": primary_col, "unit": "ms"},
        },
        {
            "kind": "table",
            "reason": f"k6 multi-metric percentile table ({len(rows)} metrics).",
            "python": f'mint.table(rows, bold_best="min", sort="-{primary_col}")',
            "cli_flags": f"--sort -{primary_col}",
            "params": {"bold_best": "min", "sort": f"-{primary_col}"},
        },
    ]
    return ToolDataset(
        format="k6",
        rows=rows,
        meta={"metrics": len(rows)},
        recommended_kind="compare",
        recommended_params={"name": "name", "value": primary_col, "unit": "ms"},
        recommendations=recs,
        unit="ms",
        higher_is_better=False,
        name_col="name",
        value_col=primary_col,
        error_col=None,
        lo_col=None,
        hi_col=None,
        error_label=None,
    )


def _parse_esbuild_metafile(payload: Mapping[str, Any]) -> ToolDataset:
    outputs = payload["outputs"]
    rows: list[dict[str, Any]] = []
    for out_path, meta in outputs.items():
        b = round(float(meta["bytes"]))
        rows.append(
            {
                "output": str(out_path),
                "bytes": b,
                "kb": round(b / 1024.0, 2),
            }
        )
    rows.sort(key=lambda r: r["bytes"], reverse=True)

    total_kb = round(sum(r["kb"] for r in rows), 2)
    share_params = {"name": "output", "value": "kb", "unit": "KB"}
    compare_params = {"name": "output", "value": "kb", "unit": "KB", "sort": "desc"}
    recs = [
        {
            "kind": "share",
            "reason": f"Bundle size breakdown across {len(rows)} outputs ({total_kb:.1f} KB total).",
            "python": 'mint.share(rows, name="output", value="kb", unit="KB")',
            "cli_flags": "--name output --value kb --unit KB",
            "params": share_params,
        },
        {
            "kind": "compare",
            "reason": f"Ranked bundle output sizes in KB ({len(rows)} outputs).",
            "python": 'mint.compare(rows, name="output", value="kb", unit="KB")',
            "cli_flags": "--name output --value kb --unit KB",
            "params": compare_params,
        },
    ]
    return ToolDataset(
        format="esbuild_metafile",
        rows=rows,
        meta={"outputs": len(rows), "total_bytes": sum(r["bytes"] for r in rows), "total_kb": total_kb},
        recommended_kind="share",
        recommended_params=share_params,
        recommendations=recs,
        unit="KB",
        higher_is_better=False,
        name_col="output",
        value_col="kb",
        error_col=None,
        lo_col=None,
        hi_col=None,
        error_label=None,
    )


def try_load_tool_output(
    source: str | Path,
    *,
    raw_text: str | None = None,
    raw_times: bool = False,
) -> ToolDataset | None:
    """Attempt to detect and parse ``source`` as a SWE dev-tool output.

    Returns a :class:`ToolDataset` if recognized, or ``None`` for standard tabular files.
    """
    src = Path(source)
    if raw_text is None:
        if not src.exists():
            raise ExplainError(
                f"Data file {src} does not exist.",
                fix_hint="Check the file path and pass a supported data or tool output file.",
            )
        raw_text = src.read_text(encoding="utf-8-sig")

    fmt = detect_tool_format(src, raw_text=raw_text)
    if fmt is None:
        return None

    if fmt == "go_bench":
        return _parse_go_bench(raw_text)
    if fmt == "cargo_bench":
        return _parse_cargo_bench(raw_text)

    payload = json.loads(raw_text)
    if fmt == "hyperfine":
        return _parse_hyperfine(payload, raw_times=raw_times)
    if fmt == "pytest_benchmark":
        return _parse_pytest_benchmark(payload)
    if fmt == "github_actions":
        return _parse_github_actions(payload)
    if fmt == "chrome_trace":
        return _parse_chrome_trace(payload)
    if fmt == "k6":
        return _parse_k6(payload)
    if fmt == "esbuild_metafile":
        return _parse_esbuild_metafile(payload)
    return None


def load_tool_output(
    source: str | Path,
    *,
    raw_times: bool = False,
) -> ToolDataset:
    """Load and normalize a SWE dev-tool output file into tidy rows + metadata.

    Raises :class:`ExplainError` if the file does not exist or is not a recognized
    SWE tool output format.
    """
    ds = try_load_tool_output(source, raw_times=raw_times)
    if ds is None:
        raise ExplainError(
            f"Could not recognize {Path(source).name} as a supported SWE tool output.",
            fix_hint=(
                "Supported tool formats: hyperfine JSON, pytest-benchmark JSON, "
                "go test -bench / cargo bench logs, GitHub Actions job timings, "
                "Chrome Trace JSON, k6 summary JSON, and esbuild metafile JSON."
            ),
        )
    return ds
