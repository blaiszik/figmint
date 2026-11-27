"""Generate 20 deterministic SWE/coding, multi-surface, and BYO-repair tasks for figure-bench v0.1.

Deterministic (fixed seeds): re-running rewrites identical data files, context.md,
broken_plot.py scripts, and rubric.json files across:
  - evals/figure_bench/public_test/pt16_* .. pt30_* (15 public-test tasks)
  - evals/figure_bench/heldout/h11_* .. h15_*      (5 heldout tasks)

Usage:
    PYTHONPATH=src python evals/figure_bench/make_tasks_swe.py
"""

from __future__ import annotations

import csv
import json
import math
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
PUBLIC_TEST = HERE / "public_test"
HELDOUT = HERE / "heldout"


def _task_root(task_id: str, split: str) -> Path:
    base = HELDOUT if split == "heldout" else PUBLIC_TEST
    root = base / task_id
    (root / "data").mkdir(parents=True, exist_ok=True)
    return root


def _write_csv(root: Path, filename: str, header: list[str], rows: list[list[Any]]) -> None:
    path = root / "data" / filename
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for row in rows:
            writer.writerow(
                ["" if v is None else (round(v, 6) if isinstance(v, float) else v) for v in row]
            )


def _write_json(root: Path, filename: str, payload: Any) -> None:
    path = root / "data" / filename
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(root: Path, filename: str, records: list[dict[str, Any]]) -> None:
    path = root / "data" / filename
    lines = [json.dumps(rec) for rec in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")


def _write_rubric(
    root: Path,
    *,
    task_id: str,
    split: str,
    track: str,
    domain: str,
    title: str,
    display_width_px: int,
    surface: str,
    what: str,
    accept: list[float],
    rel_tol: float,
    abs_tol: float,
    uncertainty_required: bool,
    no_effect_trap: bool = False,
    forbidden_overclaim_phrases: list[str] | None = None,
    required_disclosures: list[str] | None = None,
    reader_questions: list[dict[str, str]],
    forbid_truncated_bars: bool = False,
    require_log_scale: bool = False,
    min_panels: int = 0,
) -> dict[str, Any]:
    rubric = {
        "schema_version": "0.1",
        "id": task_id,
        "split": split,
        "track": track,
        "domain": domain,
        "title": title,
        "display_width_px": display_width_px,
        "surface": surface,
        "what": what,
        "accept": [round(float(v), 6) for v in accept],
        "rel_tol": float(rel_tol),
        "abs_tol": float(abs_tol),
        "uncertainty_required": bool(uncertainty_required),
        "no_effect_trap": bool(no_effect_trap),
        "forbidden_overclaim_phrases": list(forbidden_overclaim_phrases or []),
        "required_disclosures": list(required_disclosures or []),
        **({"forbid_truncated_bars": True} if forbid_truncated_bars else {}),
        **({"require_log_scale": True} if require_log_scale else {}),
        **({"min_panels": int(min_panels)} if min_panels > 0 else {}),
        "reader_questions": reader_questions,
    }
    (root / "rubric.json").write_text(json.dumps(rubric, indent=2) + "\n", encoding="utf-8")
    return rubric


def _hyperfine_entry(command: str, times: np.ndarray, rng: np.random.Generator) -> dict[str, Any]:
    arr = [round(float(t), 6) for t in times]
    mean = float(np.mean(arr))
    stddev = float(np.std(arr, ddof=1))
    median = float(np.median(arr))
    user = round(mean * float(rng.uniform(0.86, 0.92)), 6)
    system = round(max(0.001, mean - user), 6)
    return {
        "command": command,
        "mean": round(mean, 6),
        "stddev": round(stddev, 6),
        "median": round(median, 6),
        "user": user,
        "system": system,
        "min": round(float(np.min(arr)), 6),
        "max": round(float(np.max(arr)), 6),
        "times": arr,
        "exit_codes": [0] * len(arr),
    }


def _pytest_bench_entry(
    name: str,
    group: str,
    samples: np.ndarray,
) -> dict[str, Any]:
    arr = [round(float(x), 7) for x in samples]
    mean = float(np.mean(arr))
    stddev = float(np.std(arr, ddof=1))
    median = float(np.median(arr))
    q1 = float(np.percentile(arr, 25))
    q3 = float(np.percentile(arr, 75))
    iqr = q3 - q1
    return {
        "group": group,
        "name": name,
        "fullname": f"tests/bench_api.py::{name}",
        "params": None,
        "param": None,
        "options": {"timer": "perf_counter", "warmup": True},
        "stats": {
            "min": round(float(np.min(arr)), 7),
            "max": round(float(np.max(arr)), 7),
            "mean": round(mean, 7),
            "stddev": round(stddev, 7),
            "rounds": len(arr),
            "median": round(median, 7),
            "iqr": round(iqr, 7),
            "q1": round(q1, 7),
            "q3": round(q3, 7),
            "ops": round(1.0 / mean, 3),
            "total": round(float(np.sum(arr)), 7),
            "data": arr,
        },
    }


# ---------------------------------------------------------------------------
# Public-test: SWE & Quantitative Coding (pt16..pt23)
# ---------------------------------------------------------------------------


def pt16_hyperfine_diff() -> dict[str, Any]:
    task_id = "pt16_hyperfine_diff"
    root = _task_root(task_id, "public-test")
    rng = np.random.default_rng(2016)

    main_json = rng.normal(0.186, 0.0055, 20)
    main_yaml = rng.normal(0.242, 0.0115, 20)
    branch_json = rng.normal(0.126, 0.0042, 20)
    branch_yaml = rng.normal(0.239, 0.0110, 20)

    main_res = [
        _hyperfine_entry("./bin/parse_json fixtures/payload_20mb.json", main_json, rng),
        _hyperfine_entry("./bin/parse_yaml fixtures/config_5mb.yaml", main_yaml, rng),
    ]
    branch_res = [
        _hyperfine_entry("./bin/parse_json fixtures/payload_20mb.json", branch_json, rng),
        _hyperfine_entry("./bin/parse_yaml fixtures/config_5mb.yaml", branch_yaml, rng),
    ]
    _write_json(root, "main_bench.json", {"results": main_res})
    _write_json(root, "branch_bench.json", {"results": branch_res})

    m_json, b_json = main_res[0]["mean"], branch_res[0]["mean"]
    m_yaml, b_yaml = main_res[1]["mean"], branch_res[1]["mean"]
    json_speedup_pct = 100.0 * (m_json - b_json) / m_json
    json_saving_ms = 1000.0 * (m_json - b_json)
    yaml_change_pct = 100.0 * (m_yaml - b_yaml) / m_yaml

    _write_text(
        root / "context.md",
        """
        # Thread

        **User:** I ran `hyperfine --export-json` on our parser refactor branch
        against `main` for both the JSON and YAML parsers (20 timed runs each).
        Exports are in `data/main_bench.json` and `data/branch_bench.json`.

        **Assistant:** Both files are standard `hyperfine` JSON exports with
        `mean`, `stddev`, `median`, and raw per-run `times` (seconds) for
        `parse_json` and `parse_yaml`.

        **User:** Reviewers want to know if the branch actually sped up both
        parsers or only one, and whether the change is bigger than run-to-run
        noise.

        **Assistant:** I'll compare `main` vs `branch` for both parsers, show
        the run-to-run spread (s.d.), and report the percentage speedup.

        **User:** One figure I can paste into the PR discussion thread, please.
        """,
    )

    return _write_rubric(
        root,
        task_id=task_id,
        split="public-test",
        track="swe_coding",
        domain="Systems",
        title="Hyperfine parser speedup vs noise",
        display_width_px=700,
        surface="chat",
        what="JSON parser mean runtime speedup (%) or ms saved on branch vs main",
        accept=[json_speedup_pct, json_saving_ms, b_json * 1000.0],
        rel_tol=0.08,
        abs_tol=0.5,
        uncertainty_required=True,
        required_disclosures=[
            "s.d.|sd|±|spread|20 runs|n=20",
            "yaml|within noise|unchanged|no speedup",
        ],
        reader_questions=[
            {
                "kind": "primary",
                "question": "How much faster is the JSON parser on the refactor branch compared to main?",
                "expected": f"About {json_speedup_pct:.1f}% faster ({json_saving_ms:.1f} ms saved, from {m_json * 1000:.1f} ms to {b_json * 1000:.1f} ms).",
            },
            {
                "kind": "uncertainty",
                "question": "Are the JSON and YAML differences outside run-to-run noise?",
                "expected": (
                    f"JSON speedup is well outside ±1 s.d. ({main_res[0]['stddev'] * 1000:.1f} and "
                    f"{branch_res[0]['stddev'] * 1000:.1f} ms); YAML ({yaml_change_pct:.1f}%) is within overlapping ±1 s.d."
                ),
            },
            {
                "kind": "nuance",
                "question": "What happened to the YAML parser on the branch?",
                "expected": f"YAML parser showed no real speedup ({m_yaml * 1000:.1f} ms vs {b_yaml * 1000:.1f} ms, overlapping s.d.).",
            },
        ],
    )


def pt17_pytest_regression() -> dict[str, Any]:
    task_id = "pt17_pytest_regression"
    root = _task_root(task_id, "public-test")
    rng = np.random.default_rng(2017)

    specs = [
        ("test_health_ping", 0.0024, 0.00018, 1.01),
        ("test_auth_token", 0.0092, 0.00055, 0.99),
        ("test_catalog_list", 0.0145, 0.00080, 1.02),
        ("test_cart_update", 0.0118, 0.00065, 0.98),
        ("test_search_query", 0.0186, 0.00095, 1.448),
        ("test_order_summary", 0.0154, 0.00085, 1.015),
    ]
    base_benches, pr_benches = [], []
    for name, mean_s, sd_s, mult in specs:
        base_samples = np.clip(rng.normal(mean_s, sd_s, 40), mean_s * 0.6, None)
        pr_samples = np.clip(rng.normal(mean_s * mult, sd_s * (1.25 if mult > 1.2 else 1.0), 40), mean_s * 0.6, None)
        base_benches.append(_pytest_bench_entry(name, "api_endpoints", base_samples))
        pr_benches.append(_pytest_bench_entry(name, "api_endpoints", pr_samples))

    meta_base = {"machine_info": {"cpu": "8-core x86_64", "python": "3.12.4"}, "commit_info": {"id": "a19f4c2", "branch": "main"}}
    meta_pr = {"machine_info": {"cpu": "8-core x86_64", "python": "3.12.4"}, "commit_info": {"id": "e84b10d", "branch": "feat/query-filters"}}
    _write_json(root, "base.json", {**meta_base, "benchmarks": base_benches})
    _write_json(root, "pr.json", {**meta_pr, "benchmarks": pr_benches})

    base_sq = next(b for b in base_benches if b["name"] == "test_search_query")["stats"]
    pr_sq = next(b for b in pr_benches if b["name"] == "test_search_query")["stats"]
    reg_pct = 100.0 * (pr_sq["mean"] - base_sq["mean"]) / base_sq["mean"]
    reg_ms = 1000.0 * (pr_sq["mean"] - base_sq["mean"])
    pr_ms = 1000.0 * pr_sq["mean"]

    _write_text(
        root / "context.md",
        """
        # Thread

        **User:** CI flagged a potential performance regression on my query-filter
        PR. The `pytest-benchmark` exports for `main` and the PR are in
        `data/base.json` and `data/pr.json`.

        **Assistant:** Both files contain 6 API endpoint benchmarks (`rounds: 40`
        each) with `mean`, `stddev`, `median`, `iqr`, and raw timings in seconds.

        **User:** I need to see which endpoint actually regressed, by how much in
        mean latency, and whether the other five endpoints are just noise.

        **Assistant:** I'll compare all six endpoints between `base` and `pr`
        with their run-to-run spread and highlight the regressed endpoint.

        **User:** One clear figure for the PR review comment, please.
        """,
    )

    return _write_rubric(
        root,
        task_id=task_id,
        split="public-test",
        track="swe_coding",
        domain="Backend",
        title="Pytest-benchmark endpoint latency regression",
        display_width_px=700,
        surface="chat",
        what="test_search_query mean latency regression (%) or ms increase on PR vs base",
        accept=[reg_pct, reg_ms, pr_ms],
        rel_tol=0.08,
        abs_tol=0.5,
        uncertainty_required=True,
        required_disclosures=[
            "40 rounds|40 runs|n=40|s.d.|sd|iqr|±|spread",
            "other 5|five|unchanged|within noise|flat",
        ],
        reader_questions=[
            {
                "kind": "primary",
                "question": "Which endpoint regressed and by how much?",
                "expected": f"test_search_query regressed by +{reg_pct:.1f}% (+{reg_ms:.1f} ms, to {pr_ms:.1f} ms mean).",
            },
            {
                "kind": "uncertainty",
                "question": "Is the regression clearly outside benchmark noise, and what about the other five endpoints?",
                "expected": "Yes, test_search_query shifts well beyond ±1 s.d.; all five other endpoints overlap within ±1 s.d.",
            },
            {
                "kind": "nuance",
                "question": "Did any other endpoint show a meaningful speedup or slowdown?",
                "expected": "No; the remaining five endpoints stayed within roughly ±2% of base.",
            },
        ],
    )


def pt18_ci_pipeline_timeline() -> dict[str, Any]:
    task_id = "pt18_ci_pipeline_timeline"
    root = _task_root(task_id, "public-test")
    t0 = datetime(2026, 10, 18, 16, 0, 0, tzinfo=timezone.utc)

    def _iso(offset_s: int) -> str:
        return (t0 + timedelta(seconds=offset_s)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _job(job_id: int, name: str, start_s: int, steps: list[tuple[str, int]], depends_on: list[str]) -> dict[str, Any]:
        cur = start_s
        step_objs = []
        for idx, (sname, dur) in enumerate(steps, start=1):
            step_objs.append(
                {
                    "number": idx,
                    "name": sname,
                    "status": "completed",
                    "conclusion": "success",
                    "started_at": _iso(cur),
                    "completed_at": _iso(cur + dur),
                    "duration_s": dur,
                }
            )
            cur += dur
        return {
            "id": job_id,
            "name": name,
            "status": "completed",
            "conclusion": "success",
            "depends_on": depends_on,
            "started_at": _iso(start_s),
            "completed_at": _iso(cur),
            "duration_s": cur - start_s,
            "steps": step_objs,
        }

    jobs = [
        _job(101, "checkout-and-build", 0, [("checkout", 18), ("restore-cache", 34), ("compile-service", 98)], []),
        _job(102, "lint-and-typecheck", 150, [("ruff-lint", 38), ("typecheck", 77)], ["checkout-and-build"]),
        _job(103, "unit-tests", 150, [("setup-env", 24), ("pytest-unit", 166)], ["checkout-and-build"]),
        _job(104, "integration-shard-1", 150, [("boot-db", 35), ("seed-fixtures", 40), ("run-shard-1", 170)], ["checkout-and-build"]),
        _job(105, "integration-shard-2", 150, [("boot-db", 34), ("seed-fixtures", 42), ("run-shard-2", 184)], ["checkout-and-build"]),
        _job(106, "integration-shard-3", 150, [("boot-db", 36), ("seed-billing-fixtures", 142), ("run-billing-e2e", 407)], ["checkout-and-build"]),
        _job(107, "integration-shard-4", 150, [("boot-db", 33), ("seed-fixtures", 38), ("run-shard-4", 159)], ["checkout-and-build"]),
        _job(108, "package-artifacts", 735, [("build-wheel", 54), ("sign-and-upload", 51)], ["lint-and-typecheck", "unit-tests", "integration-shard-1", "integration-shard-2", "integration-shard-3", "integration-shard-4"]),
    ]
    total_s = 840
    payload = {
        "workflow_run_id": 9482710,
        "workflow_name": "ci-main-pipeline",
        "run_started_at": _iso(0),
        "run_completed_at": _iso(total_s),
        "total_wall_seconds": total_s,
        "jobs": jobs,
    }
    _write_json(root, "ci_run.json", payload)

    shard3 = next(j for j in jobs if j["name"] == "integration-shard-3")
    other_shards = [j["duration_s"] for j in jobs if j["name"].startswith("integration-shard-") and j["name"] != "integration-shard-3"]
    shard3_s = float(shard3["duration_s"])
    shard3_min = shard3_s / 60.0
    total_min = total_s / 60.0
    idle_wait_min = (shard3_s - max(other_shards)) / 60.0
    share_pct = 100.0 * shard3_s / total_s

    _write_text(
        root / "context.md",
        """
        # Thread

        **User:** Our main CI pipeline is taking 14 minutes even though we split
        integration tests into four parallel shards. The workflow job/step timing
        export is in `data/ci_run.json`.

        **Assistant:** `ci_run.json` contains 8 jobs with `started_at`,
        `completed_at`, `duration_s`, `depends_on`, and per-step timings across
        the 840 s (14.0 min) run.

        **User:** Show the team where the critical path actually sits and which
        job is blocking `package-artifacts` from starting sooner.

        **Assistant:** I'll plot the parallel job timeline across the 14-minute
        build, highlight the critical-path bottleneck, and call out how long the
        other shards sit idle waiting on it.

        **User:** One figure for our build-speed engineering thread, please.
        """,
    )

    return _write_rubric(
        root,
        task_id=task_id,
        split="public-test",
        track="swe_coding",
        domain="DevOps",
        title="CI pipeline critical-path bottleneck",
        display_width_px=700,
        surface="chat",
        what="integration-shard-3 duration (min or s), share of 14-min build, or idle wait over other shards",
        accept=[shard3_min, shard3_s, share_pct, idle_wait_min, total_min],
        rel_tol=0.08,
        abs_tol=0.25,
        uncertainty_required=False,
        reader_questions=[
            {
                "kind": "primary",
                "question": "Which job is the critical-path bottleneck and how long does it run?",
                "expected": f"integration-shard-3 runs {shard3_min:.2f} min ({int(shard3_s)} s), accounting for {share_pct:.1f}% of the {total_min:.1f}-min build.",
            },
            {
                "kind": "uncertainty",
                "question": "Is this a single pipeline run or an average across runs?",
                "expected": "It is a single deterministic workflow run (run 9482710), so timings are exact observed durations.",
            },
            {
                "kind": "nuance",
                "question": "How much faster could the build finish if integration-shard-3 matched the next slowest shard?",
                "expected": f"About {idle_wait_min:.1f} min faster (other shards finish in 3.8–4.3 min, blocking package-artifacts for {idle_wait_min:.1f} min).",
            },
        ],
    )


def pt19_k6_latency_deploy() -> dict[str, Any]:
    task_id = "pt19_k6_latency_deploy"
    root = _task_root(task_id, "public-test")
    rng = np.random.default_rng(2019)

    t0 = datetime(2026, 10, 14, 14, 0, 0, tzinfo=timezone.utc)
    deploy_min = 30
    rows: list[list[Any]] = []
    for m in range(60):
        ts = (t0 + timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%SZ")
        after = m >= deploy_min
        p50 = (44.0 if after else 41.8) * rng.lognormal(0, 0.03)
        p95 = (312.0 if after else 136.0) * rng.lognormal(0, 0.04)
        p99 = (718.0 if after else 256.0) * rng.lognormal(0, 0.05)
        rps = 1420.0 + rng.normal(0, 32.0)
        event = "deploy_v4.12.0" if m == deploy_min else ""
        rows.append([m, ts, round(float(p50), 2), round(float(p95), 2), round(float(p99), 2), round(float(rps), 1), event])

    _write_csv(root, "latency_timeseries.csv", ["minute", "timestamp", "p50_ms", "p95_ms", "p99_ms", "rps", "deploy_event"], rows)

    pre_p99 = float(np.median([r[4] for r in rows if r[0] < deploy_min]))
    post_p99 = float(np.median([r[4] for r in rows if r[0] >= deploy_min]))
    pre_p50 = float(np.median([r[2] for r in rows if r[0] < deploy_min]))
    post_p50 = float(np.median([r[2] for r in rows if r[0] >= deploy_min]))
    ratio = post_p99 / pre_p99
    delta_p99 = post_p99 - pre_p99

    _write_text(
        root / "context.md",
        """
        # Thread

        **User:** Load-test latency metrics around today's 14:30 UTC deployment
        (`deploy_v4.12.0`) are in `data/latency_timeseries.csv`. Our p99 latency
        SLA is 500 ms.

        **Assistant:** The CSV has 60 one-minute buckets (`minute`, `timestamp`,
        `p50_ms`, `p95_ms`, `p99_ms`, `rps`, `deploy_event`), with
        `deploy_v4.12.0` marked at minute 30.

        **User:** The release owner says median latency looks fine so the deploy
        is harmless. Show what actually happened to tail latency versus the
        500 ms SLA.

        **Assistant:** I'll plot p50, p95, and p99 over the 60-minute window with
        the deploy timestamp and 500 ms SLA line marked.

        **User:** One figure I can drop into the rollback decision thread, please.
        """,
    )

    return _write_rubric(
        root,
        task_id=task_id,
        split="public-test",
        track="swe_coding",
        domain="Infrastructure",
        title="Tail latency jump past 500 ms SLA after deploy",
        display_width_px=700,
        surface="chat",
        what="Post-deploy p99 latency multiplier vs pre-deploy, or post-deploy p99 median (ms)",
        accept=[ratio, post_p99, delta_p99],
        rel_tol=0.10,
        abs_tol=0.15,
        uncertainty_required=False,
        required_disclosures=["500 ms|500ms|sla", "p50|median"],
        reader_questions=[
            {
                "kind": "primary",
                "question": "How much did p99 latency jump after deploy_v4.12.0?",
                "expected": f"p99 jumped {ratio:.2f}× from ~{pre_p99:.0f} ms to ~{post_p99:.0f} ms (+{delta_p99:.0f} ms), breaching the 500 ms SLA.",
            },
            {
                "kind": "uncertainty",
                "question": "Was the p99 jump a one-minute blip or sustained?",
                "expected": "Sustained across all 30 post-deploy minutes (every post-deploy minute exceeds the 500 ms SLA).",
            },
            {
                "kind": "nuance",
                "question": "Why did the release owner think the deploy looked harmless?",
                "expected": f"Median (p50) latency barely moved ({pre_p50:.1f} ms to {post_p50:.1f} ms), masking the tail regression.",
            },
        ],
    )


def pt20_bundle_waterfall() -> dict[str, Any]:
    task_id = "pt20_bundle_waterfall"
    root = _task_root(task_id, "public-test")

    before_inputs = {
        "node_modules/ui-core/runtime.js": 148200,
        "node_modules/state-store/index.js": 62400,
        "node_modules/schema-check/index.js": 41800,
        "src/app/router.ts": 54600,
        "src/charts/canvas.ts": 79300,
        "src/features/checkout/promo.ts": 36200,
        "src/features/calendar/picker.ts": 41100,
        "src/legacy/polyfill-grid.ts": 18400,
    }
    after_inputs = {
        "node_modules/ui-core/runtime.js": 148200,
        "node_modules/state-store/index.js": 62400,
        "node_modules/schema-check/index.js": 46600,
        "node_modules/date-locale-pack/all-locales.js": 214200,
        "src/app/router.ts": 54600,
        "src/charts/canvas.ts": 79300,
        "src/features/checkout/promo.ts": 54800,
        "src/features/calendar/picker.ts": 55300,
        "src/legacy/polyfill-grid.ts": 7000,
    }

    def _meta(inputs: dict[str, int]) -> dict[str, Any]:
        total = sum(inputs.values())
        return {
            "inputs": {k: {"bytes": int(v * 1.35), "imports": []} for k, v in inputs.items()},
            "outputs": {
                "dist/app.bundle.js": {
                    "bytes": total,
                    "entryPoint": "src/app/router.ts",
                    "inputs": {k: {"bytesInOutput": v} for k, v in inputs.items()},
                }
            },
        }

    _write_json(root, "before_meta.json", _meta(before_inputs))
    _write_json(root, "after_meta.json", _meta(after_inputs))

    before_kb = sum(before_inputs.values()) / 1000.0
    after_kb = sum(after_inputs.values()) / 1000.0
    net_kb = after_kb - before_kb
    locale_kb = after_inputs["node_modules/date-locale-pack/all-locales.js"] / 1000.0
    locale_share = 100.0 * locale_kb / net_kb

    _write_text(
        root / "context.md",
        """
        # Thread

        **User:** Our web app's production JS bundle jumped noticeably in the
        latest release candidate. The `esbuild`-format metafiles are in
        `data/before_meta.json` and `data/after_meta.json`.

        **Assistant:** Both metafiles describe `dist/app.bundle.js` with total
        output `bytes` and per-module `bytesInOutput` contributions across `src/`
        and `node_modules/`.

        **User:** Show a breakdown of how we got from the previous bundle size to
        the new one so we know what actually caused the bloat before shipping.

        **Assistant:** I'll compute the module-level size deltas and show the
        before-to-after bridge highlighting the main driver.

        **User:** One figure I can attach to the release checklist, please.
        """,
    )

    return _write_rubric(
        root,
        task_id=task_id,
        split="public-test",
        track="swe_coding",
        domain="Frontend",
        title="JS bundle growth driven by transitive date-locale package",
        display_width_px=700,
        surface="chat",
        what="Total bundle growth (kB), date-locale-pack contribution (kB), or its share of net growth (%)",
        accept=[net_kb, locale_kb, locale_share],
        rel_tol=0.08,
        abs_tol=2.0,
        uncertainty_required=False,
        reader_questions=[
            {
                "kind": "primary",
                "question": "How much did the bundle grow overall, and which single package drove most of it?",
                "expected": f"Net bundle grew +{net_kb:.1f} kB ({before_kb:.1f} to {after_kb:.1f} kB), driven by date-locale-pack (+{locale_kb:.1f} kB, {locale_share:.0f}% of net growth).",
            },
            {
                "kind": "uncertainty",
                "question": "Are these measured exact build sizes or estimates?",
                "expected": "Exact deterministic byte counts from the bundler metafiles.",
            },
            {
                "kind": "nuance",
                "question": "Did any module shrink in the same release?",
                "expected": "Yes, src/legacy/polyfill-grid.ts shrank by 11.4 kB, partially offsetting small feature additions.",
            },
        ],
    )


def pt21_llm_pareto_frontier() -> dict[str, Any]:
    task_id = "pt21_llm_pareto_frontier"
    root = _task_root(task_id, "public-test")

    records = [
        {"config_id": "cfg-mini-int4", "model_tier": "small", "quantization": "INT4", "accuracy_pct": 74.2, "accuracy_sd": 1.1, "p50_latency_ms": 140, "cost_per_1k_usd": 0.18, "eval_examples": 500},
        {"config_id": "cfg-mini-fp16", "model_tier": "small", "quantization": "FP16", "accuracy_pct": 73.6, "accuracy_sd": 1.2, "p50_latency_ms": 195, "cost_per_1k_usd": 0.29, "eval_examples": 500},
        {"config_id": "cfg-small-fp16", "model_tier": "small-plus", "quantization": "FP16", "accuracy_pct": 72.8, "accuracy_sd": 1.1, "p50_latency_ms": 225, "cost_per_1k_usd": 0.36, "eval_examples": 500},
        {"config_id": "cfg-mid-fp8", "model_tier": "medium", "quantization": "FP8", "accuracy_pct": 85.4, "accuracy_sd": 0.9, "p50_latency_ms": 315, "cost_per_1k_usd": 0.64, "eval_examples": 500},
        {"config_id": "cfg-mid-int4-v1", "model_tier": "medium", "quantization": "INT4", "accuracy_pct": 78.5, "accuracy_sd": 1.0, "p50_latency_ms": 380, "cost_per_1k_usd": 0.82, "eval_examples": 500},
        {"config_id": "cfg-mid-bf16", "model_tier": "medium", "quantization": "BF16", "accuracy_pct": 84.1, "accuracy_sd": 0.9, "p50_latency_ms": 540, "cost_per_1k_usd": 1.35, "eval_examples": 500},
        {"config_id": "cfg-large-prune", "model_tier": "large", "quantization": "INT4", "accuracy_pct": 82.0, "accuracy_sd": 1.0, "p50_latency_ms": 470, "cost_per_1k_usd": 1.10, "eval_examples": 500},
        {"config_id": "cfg-large-int8", "model_tier": "large", "quantization": "INT8", "accuracy_pct": 84.6, "accuracy_sd": 0.8, "p50_latency_ms": 620, "cost_per_1k_usd": 1.72, "eval_examples": 500},
        {"config_id": "cfg-large-bf16", "model_tier": "large", "quantization": "BF16", "accuracy_pct": 90.8, "accuracy_sd": 0.8, "p50_latency_ms": 790, "cost_per_1k_usd": 2.40, "eval_examples": 500},
        {"config_id": "cfg-xl-bf16", "model_tier": "xl", "quantization": "BF16", "accuracy_pct": 89.4, "accuracy_sd": 0.9, "p50_latency_ms": 1180, "cost_per_1k_usd": 3.90, "eval_examples": 500},
    ]
    _write_jsonl(root, "eval_runs.jsonl", records)

    def _pareto(cost_key: str) -> list[str]:
        front = []
        for r in records:
            dominated = any(
                (o["accuracy_pct"] >= r["accuracy_pct"] and o[cost_key] <= r[cost_key])
                and (o["accuracy_pct"] > r["accuracy_pct"] or o[cost_key] < r[cost_key])
                for o in records
            )
            if not dominated:
                front.append(r["config_id"])
        return front

    front_cost = _pareto("cost_per_1k_usd")
    front_lat = _pareto("p50_latency_ms")
    assert front_cost == front_lat == ["cfg-mini-int4", "cfg-mid-fp8", "cfg-large-bf16"]

    mid_rec = next(r for r in records if r["config_id"] == "cfg-mid-fp8")
    large_rec = next(r for r in records if r["config_id"] == "cfg-large-bf16")

    _write_text(
        root / "context.md",
        """
        # Thread

        **User:** We benchmarked 10 serving configurations for our agent router on
        the 500-example internal eval suite. Results are in `data/eval_runs.jsonl`.

        **Assistant:** Each JSON line has `config_id`, `model_tier`, `quantization`,
        `accuracy_pct`, `accuracy_sd`, `p50_latency_ms`, `cost_per_1k_usd`, and
        `eval_examples`.

        **User:** Leadership wants to prune the catalog down to the Pareto-optimal
        configs across accuracy, cost, and latency. Which configs actually sit on
        the frontier, and which ones are strictly dominated?

        **Assistant:** I'll plot accuracy (with eval uncertainty) against cost and
        latency, highlight the Pareto frontier, and label the frontier configs.

        **User:** One figure for the model-selection review thread, please.
        """,
    )

    return _write_rubric(
        root,
        task_id=task_id,
        split="public-test",
        track="swe_coding",
        domain="ML Systems",
        title="Model configuration Pareto frontier",
        display_width_px=700,
        surface="chat",
        what="Number of Pareto-optimal configs (3) or accuracy/cost of key frontier points (cfg-mid-fp8 / cfg-large-bf16)",
        accept=[float(len(front_cost)), mid_rec["accuracy_pct"], large_rec["accuracy_pct"], mid_rec["cost_per_1k_usd"]],
        rel_tol=0.06,
        abs_tol=0.3,
        uncertainty_required=True,
        required_disclosures=[
            "pareto|frontier|cfg-mid-fp8|dominated",
            "s.d.|sd|±|500|uncertainty|ci",
        ],
        reader_questions=[
            {
                "kind": "primary",
                "question": "Which configurations define the Pareto frontier?",
                "expected": "Exactly 3 configs: cfg-mini-int4 (74.2%, $0.18), cfg-mid-fp8 (85.4%, $0.64), and cfg-large-bf16 (90.8%, $2.40).",
            },
            {
                "kind": "uncertainty",
                "question": "Are the three frontier tiers separated beyond their evaluation s.d.?",
                "expected": "Yes, accuracy gaps (+11.2 pts and +5.4 pts) are well outside ±0.8–1.1 pt s.d.",
            },
            {
                "kind": "nuance",
                "question": "What happens with the most expensive configuration (cfg-xl-bf16)?",
                "expected": "cfg-xl-bf16 ($3.90, 1180 ms, 89.4%) is strictly dominated by cfg-large-bf16 ($2.40, 790 ms, 90.8%).",
            },
        ],
    )


def pt22_signup_funnel() -> dict[str, Any]:
    task_id = "pt22_signup_funnel"
    root = _task_root(task_id, "public-test")

    stages = [
        ("landing", 24000, 18480, "bounced_before_cta"),
        ("account_form", 18480, 15340, "password_rules_exit"),
        ("email_verify", 15340, 8284, "verification_email_delayed"),
        ("profile_setup", 8284, 7207, "org_fields_skipped"),
        ("api_key_created", 7207, 6414, "scope_config_exit"),
        ("first_request", 6414, 5644, "sdk_auth_401"),
    ]
    rows = []
    for idx, (stage, entered, completed, reason) in enumerate(stages, start=1):
        drop = entered - completed
        drop_pct = 100.0 * drop / entered
        rows.append([idx, stage, entered, completed, drop, round(drop_pct, 2), reason])

    _write_csv(
        root,
        "funnel.csv",
        ["stage_order", "stage", "users_entered", "users_completed", "drop_count", "stage_drop_pct", "top_drop_reason"],
        rows,
    )

    email_row = next(r for r in rows if r[1] == "email_verify")
    overall_conv = 100.0 * rows[-1][3] / rows[0][2]

    _write_text(
        root / "context.md",
        """
        # Thread

        **User:** Developer onboarding completion fell this month. The 6-stage
        signup-to-first-API-call funnel for 24,000 visitors is in `data/funnel.csv`.

        **Assistant:** Columns: `stage_order`, `stage`, `users_entered`,
        `users_completed`, `drop_count`, `stage_drop_pct`, and `top_drop_reason`.

        **User:** Growth wants to fix one stage first. Show the full funnel so it's
        obvious where the biggest attrition happens and why users are dropping
        there.

        **Assistant:** I'll show volume and stage-by-stage drop rates across all
        six steps, highlighting the biggest drop and its primary drop reason.

        **User:** One figure I can share in the onboarding triage thread, please.
        """,
    )

    return _write_rubric(
        root,
        task_id=task_id,
        split="public-test",
        track="swe_coding",
        domain="Product",
        title="Developer signup funnel attrition at email verification",
        display_width_px=700,
        surface="chat",
        what="email_verify stage drop rate (%), users dropped at email_verify, or overall completion (%)",
        accept=[float(email_row[5]), float(email_row[4]), overall_conv],
        rel_tol=0.06,
        abs_tol=0.5,
        uncertainty_required=False,
        reader_questions=[
            {
                "kind": "primary",
                "question": "Which funnel stage loses the most users, and how severe is the drop?",
                "expected": f"email_verify loses {email_row[4]:,} users ({email_row[5]:.1f}% of users entering that stage).",
            },
            {
                "kind": "uncertainty",
                "question": "Is the drop at email_verify based on a small sample?",
                "expected": f"No, it is measured across {email_row[2]:,} users entering email_verify (24,000 total funnel entrants).",
            },
            {
                "kind": "nuance",
                "question": "What is the top drop reason at email_verify, and what is the overall funnel completion rate?",
                "expected": f"Top reason is verification_email_delayed; overall landing-to-first_request completion is {overall_conv:.1f}%.",
            },
        ],
    )


def pt23_memory_soak_leak() -> dict[str, Any]:
    task_id = "pt23_memory_soak_leak"
    root = _task_root(task_id, "public-test")
    rng = np.random.default_rng(2023)

    hours = np.arange(0, 49)
    workers = {
        "worker-api": (480.0, 0.05, 9.0),
        "worker-scheduler": (342.0, -0.02, 7.0),
        "worker-notifier": (296.0, 0.03, 6.0),
        "worker-ingest": (420.0, 18.0, 8.0),
    }
    rows: list[list[Any]] = []
    for worker, (base, slope, sd) in workers.items():
        for h in hours:
            sawtooth = (h % 6) * 1.5 if worker != "worker-ingest" else 0.0
            rss = base + slope * h + sawtooth + rng.normal(0, sd)
            rows.append([int(h), worker, round(float(rss), 2)])

    _write_csv(root, "rss_mb.csv", ["hour", "worker", "rss_mb"], rows)

    ingest_y = np.array([r[2] for r in rows if r[1] == "worker-ingest"])
    fit_slope, fit_intercept = np.polyfit(hours, ingest_y, 1)
    oom_cap_mb = 2048.0
    oom_hour = (oom_cap_mb - fit_intercept) / fit_slope
    end_rss = float(ingest_y[-1])

    _write_text(
        root / "context.md",
        """
        # Thread

        **User:** We ran a 48-hour staging soak test across our four background
        workers before cutting the release. Hourly RSS memory readings are in
        `data/rss_mb.csv`. Container OOM limit is 2,048 MB (2 GB).

        **Assistant:** Columns: `hour` (0 to 48), `worker` (`worker-api`,
        `worker-scheduler`, `worker-notifier`, `worker-ingest`), and `rss_mb`.

        **User:** One worker looks suspicious in staging logs. Show all four
        workers over the 48-hour soak, quantify the leak rate, and show how soon
        it will hit the 2,048 MB OOM cap.

        **Assistant:** I'll plot RSS over time for all four workers, fit the linear
        growth rate on the leaking worker, and mark the 2,048 MB cap.

        **User:** One figure for the release blocker ticket, please.
        """,
    )

    return _write_rubric(
        root,
        task_id=task_id,
        split="public-test",
        track="swe_coding",
        domain="Systems",
        title="48-hour soak test linear memory leak in worker-ingest",
        display_width_px=700,
        surface="chat",
        what="worker-ingest linear memory leak rate (MB/h), projected hour to 2048 MB OOM cap, or 48h RSS (MB)",
        accept=[float(fit_slope), float(oom_hour), end_rss],
        rel_tol=0.08,
        abs_tol=0.8,
        uncertainty_required=False,
        required_disclosures=["2048|2 gb|2gb|oom", "flat|stable|other 3|other three|worker-ingest"],
        reader_questions=[
            {
                "kind": "primary",
                "question": "Which worker is leaking memory and at what rate?",
                "expected": f"worker-ingest leaks linearly at ~+{fit_slope:.1f} MB/h, climbing to ~{end_rss:.0f} MB by hour 48.",
            },
            {
                "kind": "uncertainty",
                "question": "Is the growth clearly a trend rather than normal GC fluctuation?",
                "expected": "Yes; it climbs monotonically over 48 hours while the other three workers fluctuate flat around 300–490 MB.",
            },
            {
                "kind": "nuance",
                "question": "When is worker-ingest projected to hit the 2,048 MB OOM limit?",
                "expected": f"Around hour {oom_hour:.0f} (about {oom_hour - 48:.0f} hours after the 48-hour soak ends).",
            },
        ],
    )


# ---------------------------------------------------------------------------
# Public-test: Multi-Surface Delivery (pt24..pt27)
# ---------------------------------------------------------------------------


def pt24_narrow_phone_alert() -> dict[str, Any]:
    task_id = "pt24_narrow_phone_alert"
    root = _task_root(task_id, "public-test")
    rng = np.random.default_rng(2024)

    t0 = datetime(2026, 10, 21, 18, 0, 0, tzinfo=timezone.utc)
    rows: list[list[Any]] = []
    for m in range(36):
        ts = (t0 + timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for region in ("eu-west", "us-east", "ap-south"):
            if region == "eu-west":
                if m < 14:
                    err = 0.18 * rng.lognormal(0, 0.15)
                elif m < 28:
                    bump = 14.4 if m == 19 else (12.2 + 0.35 * math.sin(m))
                    err = bump * rng.lognormal(0, 0.05)
                else:
                    err = (11.0 * math.exp(-0.45 * (m - 27)) + 0.25) * rng.lognormal(0, 0.06)
                rpm = 4200 + rng.normal(0, 90)
            elif region == "us-east":
                err = 0.15 * rng.lognormal(0, 0.14)
                rpm = 5800 + rng.normal(0, 110)
            else:
                err = 0.21 * rng.lognormal(0, 0.16)
                rpm = 2900 + rng.normal(0, 75)
            rows.append([m, ts, region, round(float(err), 3), round(float(rpm), 0)])

    _write_csv(root, "incident_5m.csv", ["minute", "timestamp", "region", "error_rate_pct", "requests_per_min"], rows)

    eu_all = [r[3] for r in rows if r[2] == "eu-west"]
    eu_peak = max(eu_all)
    eu_incident_med = float(np.median([r[3] for r in rows if r[2] == "eu-west" and 14 <= r[0] < 28]))
    other_max = max(r[3] for r in rows if r[2] != "eu-west")

    _write_text(
        root / "context.md",
        """
        # Thread

        **User:** I just got paged while away from my laptop and I'm reading this
        on my phone (450 px wide screen). Per-minute regional error rates from
        18:00–18:35 UTC are in `data/incident_5m.csv`. Alert threshold is 1.0%.

        **Assistant:** Columns: `minute`, `timestamp`, `region` (`eu-west`,
        `us-east`, `ap-south`), `error_rate_pct`, and `requests_per_min`.

        **User:** Tell me fast: is this global or isolated to one region, how high
        did the error rate spike, and did the 18:28 rollback bring it back down?

        **Assistant:** I'll build a compact figure sized specifically for a 450 px
        phone viewport so every label and line is immediately readable without
        pinch-zooming.

        **User:** Perfect — one phone-sized figure for the incident channel.
        """,
    )

    return _write_rubric(
        root,
        task_id=task_id,
        split="public-test",
        track="multi_surface",
        domain="Observability",
        title="Phone-viewport regional error-rate incident alert",
        display_width_px=450,
        surface="narrow",
        what="eu-west peak error rate (%) or incident median error rate (%)",
        accept=[eu_peak, eu_incident_med],
        rel_tol=0.08,
        abs_tol=0.5,
        uncertainty_required=False,
        required_disclosures=["eu-west", "us-east|ap-south|isolated|rollback"],
        reader_questions=[
            {
                "kind": "primary",
                "question": "Which region spiked and how high did its error rate get?",
                "expected": f"eu-west spiked to {eu_peak:.1f}% (median ~{eu_incident_med:.1f}% during the incident), far above the 1.0% alert threshold.",
            },
            {
                "kind": "uncertainty",
                "question": "Were us-east or ap-south affected?",
                "expected": f"No; both stayed below {other_max:.2f}% throughout the window.",
            },
            {
                "kind": "nuance",
                "question": "Did the error rate recover after 18:28 UTC?",
                "expected": "Yes, eu-west decayed rapidly after minute 27–28 back toward baseline (<0.6% by 18:35).",
            },
        ],
    )


def pt25_slide_quarterly_perf() -> dict[str, Any]:
    task_id = "pt25_slide_quarterly_perf"
    root = _task_root(task_id, "public-test")
    rng = np.random.default_rng(2025)

    quarters = ["Q1", "Q2", "Q3", "Q4"]
    profiles = {
        "north-america": ([142, 138, 131, 128], [42.0, 44.5, 47.2, 49.8]),
        "europe": ([168, 162, 154, 151], [31.5, 33.0, 35.1, 36.8]),
        "asia-pacific": ([312, 298, 214, 192], [18.4, 19.6, 24.3, 26.8]),
        "south-america": ([245, 239, 234, 228], [11.2, 11.9, 12.6, 13.1]),
    }
    rows: list[list[Any]] = []
    for region, (lats, tputs) in profiles.items():
        for q, lat, tput in zip(quarters, lats, tputs):
            lat_v = round(float(lat + rng.normal(0, 2.0)), 1)
            lat_sd = round(float(lat * rng.uniform(0.035, 0.05)), 1)
            tput_v = round(float(tput + rng.normal(0, 0.3)), 2)
            tput_sd = round(float(tput * rng.uniform(0.03, 0.045)), 2)
            rows.append([q, region, lat_v, lat_sd, tput_v, tput_sd])

    _write_csv(
        root,
        "quarterly_regions.csv",
        ["quarter", "region", "p95_latency_ms", "p95_sd_ms", "throughput_krps", "throughput_sd_krps"],
        rows,
    )

    apac_q1 = next(r for r in rows if r[1] == "asia-pacific" and r[0] == "Q1")
    apac_q4 = next(r for r in rows if r[1] == "asia-pacific" and r[0] == "Q4")
    lat_drop_pct = 100.0 * (apac_q1[2] - apac_q4[2]) / apac_q1[2]
    lat_drop_ms = apac_q1[2] - apac_q4[2]
    tput_gain_pct = 100.0 * (apac_q4[4] - apac_q1[4]) / apac_q1[4]

    _write_text(
        root / "context.md",
        """
        # Thread

        **User:** I'm putting together a widescreen slide (1280 px wide) for the
        quarterly engineering review. Regional p95 latency and throughput across
        Q1–Q4 are in `data/quarterly_regions.csv`.

        **Assistant:** Columns: `quarter` (Q1–Q4), `region` (`north-america`,
        `europe`, `asia-pacific`, `south-america`), `p95_latency_ms`, `p95_sd_ms`,
        `throughput_krps`, and `throughput_sd_krps`.

        **User:** We rolled out regional edge caching in `asia-pacific` at the end
        of Q2. Show both latency and throughput across all four regions so the
        room can see the impact from the back row.

        **Assistant:** I'll design a clean 1280 px slide figure pairing regional
        p95 latency and throughput with quarterly s.d. uncertainty bands/bars.

        **User:** One widescreen figure ready to drop directly onto a slide, please.
        """,
    )

    return _write_rubric(
        root,
        task_id=task_id,
        split="public-test",
        track="multi_surface",
        domain="Infrastructure",
        title="Quarterly engineering review slide: regional latency & throughput",
        display_width_px=1280,
        surface="slide",
        what="asia-pacific Q1-to-Q4 p95 latency reduction (% or ms), Q4 p95 latency, or throughput gain (%)",
        accept=[lat_drop_pct, lat_drop_ms, apac_q4[2], tput_gain_pct],
        rel_tol=0.08,
        abs_tol=0.8,
        uncertainty_required=True,
        required_disclosures=["s.d.|sd|±|spread|ci", "apac|q4|2025"],
        reader_questions=[
            {
                "kind": "primary",
                "question": "How much did asia-pacific p95 latency improve from Q1 to Q4?",
                "expected": f"Dropped {lat_drop_pct:.1f}% ({lat_drop_ms:.0f} ms, from {apac_q1[2]:.1f} ms to {apac_q4[2]:.1f} ms).",
            },
            {
                "kind": "uncertainty",
                "question": "Is the asia-pacific drop larger than quarter-to-quarter s.d.?",
                "expected": f"Yes; the {lat_drop_ms:.0f} ms drop is far larger than the ±{apac_q1[3]:.1f}/{apac_q4[3]:.1f} ms s.d.",
            },
            {
                "kind": "nuance",
                "question": "What happened to asia-pacific throughput, and which region still has the highest p95 latency in Q4?",
                "expected": f"asia-pacific throughput rose +{tput_gain_pct:.1f}% ({apac_q1[4]:.1f} to {apac_q4[4]:.1f} krps); south-america now has the highest Q4 latency.",
            },
        ],
    )


def pt26_dark_dashboard_card() -> dict[str, Any]:
    task_id = "pt26_dark_dashboard_card"
    root = _task_root(task_id, "public-test")
    rng = np.random.default_rng(2026)

    policies = {
        "S3-FIFO": (89.4, 0.72, 1.42, 0.34),
        "TinyLFU": (85.1, 0.78, 2.88, 0.43),
        "LRU": (80.8, 0.90, 1.15, 0.38),
        "LFU": (79.4, 1.08, 2.45, 0.45),
        "Random": (64.2, 1.25, 0.58, 0.52),
    }
    rows: list[list[Any]] = []
    for pol, (hit_m, hit_sd, cpu_m, p99_m) in policies.items():
        for run in range(1, 9):
            hit = round(float(hit_m + rng.normal(0, hit_sd)), 2)
            cpu = round(float(max(0.2, cpu_m + rng.normal(0, 0.08))), 3)
            p99 = round(float(max(0.1, p99_m + rng.normal(0, 0.02))), 3)
            rows.append([pol, run, hit, cpu, p99])

    _write_csv(root, "cache_policies.csv", ["policy", "run", "hit_rate_pct", "eviction_cpu_us", "p99_get_ms"], rows)

    means = {p: float(np.mean([r[2] for r in rows if r[0] == p])) for p in policies}
    gap_lru = means["S3-FIFO"] - means["LRU"]
    gap_tinylfu = means["S3-FIFO"] - means["TinyLFU"]

    _write_text(
        root / "context.md",
        """
        # Thread

        **User:** We replayed 8 production cache traces across five eviction
        policies (`S3-FIFO`, `TinyLFU`, `LRU`, `LFU`, `Random`). Metrics are in
        `data/cache_policies.csv`.

        **Assistant:** Columns: `policy`, `run` (1–8), `hit_rate_pct`,
        `eviction_cpu_us`, and `p99_get_ms`. 40 rows, no missing values.

        **User:** This goes directly into our dark-theme monitoring dashboard
        (700 px card on a dark charcoal background). Compare hit rates across
        policies with trace-to-trace spread, and note eviction CPU cost.

        **Assistant:** I'll render a dark-surface 700 px dashboard figure comparing
        all five policies with their 8-run spread and CPU tradeoff.

        **User:** One dark-theme figure ready for the dashboard card, please.
        """,
    )

    return _write_rubric(
        root,
        task_id=task_id,
        split="public-test",
        track="multi_surface",
        domain="Systems",
        title="Dark-theme cache eviction policy comparison card",
        display_width_px=700,
        surface="dark",
        what="S3-FIFO mean hit rate (%), gain over default LRU (pts), or gain over TinyLFU (pts)",
        accept=[means["S3-FIFO"], gap_lru, gap_tinylfu],
        rel_tol=0.08,
        abs_tol=0.4,
        uncertainty_required=True,
        required_disclosures=["s3-fifo", "8 runs|8 replay|n=8|s.d.|sd|±|spread"],
        reader_questions=[
            {
                "kind": "primary",
                "question": "Which eviction policy achieves the highest hit rate and by how much over LRU?",
                "expected": f"S3-FIFO leads at {means['S3-FIFO']:.1f}%, beating LRU ({means['LRU']:.1f}%) by +{gap_lru:.1f} percentage points.",
            },
            {
                "kind": "uncertainty",
                "question": "Is S3-FIFO's lead over TinyLFU outside trace-to-trace spread?",
                "expected": f"Yes; S3-FIFO leads TinyLFU ({means['TinyLFU']:.1f}%) by +{gap_tinylfu:.1f} pts, well outside ±0.7–0.8 pt s.d.",
            },
            {
                "kind": "nuance",
                "question": "How does S3-FIFO compare to TinyLFU on eviction CPU overhead?",
                "expected": "S3-FIFO uses roughly half the eviction CPU of TinyLFU (~1.4 µs vs ~2.9 µs), close to LRU (~1.2 µs).",
            },
        ],
    )


def pt27_terminal_only_bench() -> dict[str, Any]:
    task_id = "pt27_terminal_only_bench"
    root = _task_root(task_id, "public-test")
    rng = np.random.default_rng(2027)

    libs = {
        "flatwire": (1180.0, 26.0, 1425.0, 29.0, 148.2),
        "cbor-fast": (840.0, 21.0, 912.0, 22.0, 108.6),
        "msgpack-c": (795.0, 18.0, 786.0, 19.0, 104.1),
        "proto-lite": (620.0, 16.0, 692.0, 17.0, 96.4),
        "json-std": (345.0, 12.0, 310.0, 11.0, 174.5),
    }
    rows: list[list[Any]] = []
    for lib, (enc_m, enc_sd, dec_m, dec_sd, kb) in libs.items():
        for run in range(1, 11):
            enc = round(float(enc_m + rng.normal(0, enc_sd)), 1)
            dec = round(float(dec_m + rng.normal(0, dec_sd)), 1)
            rows.append([lib, run, enc, dec, kb])

    _write_csv(root, "bench.csv", ["library", "run", "encode_mb_s", "decode_mb_s", "payload_kb"], rows)

    dec_means = {lib: float(np.mean([r[3] for r in rows if r[0] == lib])) for lib in libs}
    ratio_json = dec_means["flatwire"] / dec_means["json-std"]
    ratio_cbor = dec_means["flatwire"] / dec_means["cbor-fast"]

    _write_text(
        root / "context.md",
        """
        # Thread

        **User:** I'm connected over plain SSH inside a 72-column terminal — I have
        no image viewer at all, so do NOT rely on a PNG attachment. Serialization
        benchmark runs for five libraries are in `data/bench.csv`.

        **Assistant:** Columns: `library` (`flatwire`, `cbor-fast`, `msgpack-c`,
        `proto-lite`, `json-std`), `run` (1–10), `encode_mb_s`, `decode_mb_s`, and
        `payload_kb`.

        **User:** We care most about decode throughput (MB/s) plus run-to-run
        spread, and whether the fastest decoder bloats payload size compared to
        `proto-lite`.

        **Assistant:** I'll summarize all five libraries directly in a compact
        <=72-column plain-text/Unicode table or bar display with means, s.d., and
        payload sizes.

        **User:** Great — keep every line <=72 columns so nothing wraps in SSH.
        """,
    )

    return _write_rubric(
        root,
        task_id=task_id,
        split="public-test",
        track="multi_surface",
        domain="Systems",
        title="SSH terminal-only serialization benchmark comparison",
        display_width_px=72,
        surface="terminal",
        what="flatwire mean decode throughput (MB/s), speedup ratio vs json-std / cbor-fast / proto-lite, or payload overhead (%)",
        accept=[dec_means["flatwire"], ratio_json, ratio_cbor, dec_means["flatwire"] / dec_means["proto-lite"]],
        rel_tol=0.08,
        abs_tol=0.15,
        uncertainty_required=True,
        required_disclosures=["flatwire", "s.d.|sd|±|10 runs|n=10|spread", "proto-lite|payload"],
        reader_questions=[
            {
                "kind": "primary",
                "question": "Which serialization library decodes fastest and how fast is it?",
                "expected": f"flatwire leads at ~{dec_means['flatwire']:.0f} MB/s ({ratio_json:.1f}× json-std and {ratio_cbor:.2f}× cbor-fast).",
            },
            {
                "kind": "uncertainty",
                "question": "Is flatwire's decode lead outside run-to-run spread?",
                "expected": "Yes; flatwire (~1,425 ± 29 MB/s) is separated by >500 MB/s from runner-up cbor-fast (~912 ± 22 MB/s).",
            },
            {
                "kind": "nuance",
                "question": "What is the payload-size tradeoff of choosing flatwire over proto-lite?",
                "expected": "flatwire payloads are 148.2 kB vs proto-lite's 96.4 kB (+54% larger, though still smaller than json-std at 174.5 kB).",
            },
        ],
    )


# ---------------------------------------------------------------------------
# Public-test: BYO-Matplotlib Repair (pt28..pt30)
# ---------------------------------------------------------------------------


def pt28_repair_ablation_bars() -> dict[str, Any]:
    task_id = "pt28_repair_ablation_bars"
    root = _task_root(task_id, "public-test")
    rng = np.random.default_rng(2028)

    variants = [
        ("full_pipeline", 0.822),
        ("no_rerank", 0.808),
        ("no_chunk_overlap", 0.793),
        ("no_query_rewrite", 0.768),
        ("bm25_only", 0.714),
    ]
    rows: list[list[Any]] = []
    for var, mean in variants:
        for seed in range(1, 7):
            score = round(float(mean + rng.normal(0, 0.0085)), 4)
            rows.append([var, seed, score])

    _write_csv(root, "ablation.csv", ["variant", "seed", "f1_score"], rows)

    means = {v: float(np.mean([r[2] for r in rows if r[0] == v])) for v, _ in variants}
    rewrite_gain_frac = means["full_pipeline"] - means["no_query_rewrite"]
    rewrite_gain_pts = 100.0 * rewrite_gain_frac

    broken_script = '''"""Draft ablation plot (has visual & claim defects to repair)."""

import csv
import sys
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

DATA_DIR = Path(__file__).resolve().parent
OUT_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "pt28_broken.png"

grouped: dict[str, list[float]] = {}
with open(DATA_DIR / "ablation.csv", encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        grouped.setdefault(row["variant"], []).append(float(row["f1_score"]))

names = list(grouped.keys())
means = [float(np.mean(grouped[k])) for k in names]
sds = [float(np.std(grouped[k], ddof=1)) for k in names]

fig, ax = plt.subplots(figsize=(14, 5), dpi=100)
x = np.arange(len(names))
ax.bar(x, means, yerr=sds, capsize=4, color="#3b82f6")
ax.set_xticks(x)
ax.set_xticklabels(names, fontsize=10)
ax.tick_params(axis="y", labelsize=10)
ax.set_ylabel("F1 score", fontsize=10)
ax.set_ylim(0.65, 0.85)
ax.set_title("Query rewrite adds 14.8 points to F1 score", fontsize=12)
fig.savefig(OUT_PATH, dpi=100)
'''
    _write_text(root / "data" / "broken_plot.py", broken_script)

    _write_text(
        root / "context.md",
        """
        # Thread

        **User:** I drafted a quick Matplotlib script (`data/broken_plot.py`) for
        our retrieval ablation results (`data/ablation.csv`, 5 variants × 6 seeds),
        but reviewers flagged multiple problems with both the headline claim and
        how the chart renders in a 700 px chat column.

        **Assistant:** I see `data/ablation.csv` (`variant`, `seed`, `f1_score`)
        and `data/broken_plot.py`. The draft script truncates the bar y-axis to
        0.65–0.85, draws unlabelled error bars on a 14×5 canvas that shrinks text
        under 8 px at 700 px width, and states a wrong headline gain.

        **User:** Please fix the plot cleanly: verify every number directly from
        `data/ablation.csv`, make the baseline honest, label what the error bars
        represent, and size it cleanly for 700 px chat viewing.

        **Assistant:** I'll audit the data, repair all four issues, and produce a
        clean, accurate figure.

        **User:** One repaired figure for the experiment thread, please.
        """,
    )

    return _write_rubric(
        root,
        task_id=task_id,
        split="public-test",
        track="byo_repair",
        domain="ML Evaluation",
        title="Repair ablation bar chart (wrong claim, truncated y-axis, tiny text, unlabelled error bars)",
        display_width_px=700,
        surface="chat",
        what="True F1 gain from query rewrite (percentage points or decimal) or full_pipeline mean F1",
        accept=[rewrite_gain_pts, rewrite_gain_frac, means["full_pipeline"], means["full_pipeline"] * 100.0],
        rel_tol=0.08,
        abs_tol=0.3,
        uncertainty_required=True,
        forbid_truncated_bars=True,
        required_disclosures=["6 seeds|n=6|s.d.|sd|ci|±", "baseline|zero|0"],
        reader_questions=[
            {
                "kind": "primary",
                "question": "How much F1 does query rewrite actually add over no_query_rewrite?",
                "expected": f"About +{rewrite_gain_pts:.1f} points (+{rewrite_gain_frac:.3f} F1, from {means['no_query_rewrite']:.3f} to {means['full_pipeline']:.3f}), not 14.8 points.",
            },
            {
                "kind": "uncertainty",
                "question": "What do the error bars represent and is the query-rewrite gain outside seed noise?",
                "expected": "Error bars show spread across 6 seeds (±1 s.d. or 95% CI); the query-rewrite gain clearly exceeds seed noise.",
            },
            {
                "kind": "nuance",
                "question": "Which ablated component makes the smallest difference to F1?",
                "expected": f"Dropping the reranker (no_rerank: {means['no_rerank']:.3f} vs full_pipeline: {means['full_pipeline']:.3f}) has the smallest impact.",
            },
        ],
    )


def pt29_repair_jet_heatmap() -> dict[str, Any]:
    task_id = "pt29_repair_jet_heatmap"
    root = _task_root(task_id, "public-test")

    classes = ["billing", "auth", "infra", "search", "export"]
    matrix = [
        [156, 12, 11, 10, 11],
        [11, 152, 13, 12, 12],
        [10, 12, 148, 18, 12],
        [10, 11, 46, 122, 11],
        [12, 11, 11, 12, 154],
    ]
    rows: list[list[Any]] = []
    for i, t_lbl in enumerate(classes):
        for j, p_lbl in enumerate(classes):
            rows.append([t_lbl, p_lbl, matrix[i][j]])

    _write_csv(root, "confusion.csv", ["true_label", "pred_label", "count"], rows)

    total = sum(sum(r) for r in matrix)
    diag = sum(matrix[i][i] for i in range(len(classes)))
    acc_pct = 100.0 * diag / total
    acc_frac = diag / total
    worst_offdiag = 46

    broken_script = '''"""Draft confusion matrix heatmap (has colormap, text, and claim bugs)."""

import csv
import sys
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

DATA_DIR = Path(__file__).resolve().parent
OUT_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "pt29_broken.png"

classes = ["billing", "auth", "infra", "search", "export"]
idx = {c: i for i, c in enumerate(classes)}
mat = np.zeros((len(classes), len(classes)), dtype=int)
with open(DATA_DIR / "confusion.csv", encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        mat[idx[row["true_label"]], idx[row["pred_label"]]] = int(row["count"])

fig, ax = plt.subplots(figsize=(13, 9), dpi=100)
im = ax.imshow(mat, cmap="jet")
fig.colorbar(im, ax=ax, label="Tickets")
ax.set_xticks(range(len(classes)))
ax.set_yticks(range(len(classes)))
ax.set_xticklabels(classes, fontsize=8)
ax.set_yticklabels(classes, fontsize=8)
ax.set_xlabel("Predicted queue", fontsize=8)
ax.set_ylabel("True queue", fontsize=8)

for i in range(len(classes)):
    for j in range(len(classes)):
        ax.text(j, i, f"{mat[i, j]}", ha="center", va="center", fontsize=8, color="white")
        ax.text(j, i + 0.04, f"({mat[i, j] / 2:.0f}%)", ha="center", va="center", fontsize=8, color="yellow")

ax.set_title("Ticket router achieves 96.4% overall accuracy", fontsize=12)
fig.savefig(OUT_PATH, dpi=100)
'''
    _write_text(root / "data" / "broken_plot.py", broken_script)

    _write_text(
        root / "context.md",
        """
        # Thread

        **User:** Someone sent me `data/broken_plot.py` to visualize our 5-class
        support-ticket confusion matrix (`data/confusion.csv`, 1,000 tickets).
        It looks unreadable in chat and the headline accuracy doesn't match my
        eval logs.

        **Assistant:** I checked `data/confusion.csv` and `data/broken_plot.py`.
        The script uses the `jet` rainbow colormap, renders tiny 8 pt labels on a
        13×9 canvas, overlaps count and percentage strings inside every cell, and
        claims 96.4% accuracy when the diagonal sum is much lower.

        **User:** Please replace the broken chart with a clean, perceptually
        uniform heatmap whose headline gives the true accuracy and highlights the
        main misrouting error.

        **Assistant:** I'll recompute overall accuracy and per-class errors from
        `data/confusion.csv` and render a clean 700 px figure.

        **User:** One repaired figure for the classifier review thread, please.
        """,
    )

    return _write_rubric(
        root,
        task_id=task_id,
        split="public-test",
        track="byo_repair",
        domain="ML Evaluation",
        title="Repair jet confusion-matrix heatmap (rainbow cmap, overlaps, tiny text, wrong accuracy)",
        display_width_px=700,
        surface="chat",
        what="True overall routing accuracy (%) or fraction, or largest off-diagonal confusion count (46)",
        accept=[acc_pct, acc_frac, float(worst_offdiag)],
        rel_tol=0.06,
        abs_tol=0.5,
        uncertainty_required=False,
        required_disclosures=["73.2%|73%|accuracy", "search|infra|46"],
        reader_questions=[
            {
                "kind": "primary",
                "question": "What is the true overall classification accuracy across the 1,000 tickets?",
                "expected": f"{acc_pct:.1f}% ({diag} of {total} tickets), not 96.4%.",
            },
            {
                "kind": "uncertainty",
                "question": "How large is the evaluation set per class?",
                "expected": "200 tickets per true class (1,000 total).",
            },
            {
                "kind": "nuance",
                "question": "Which class pair has the worst misrouting confusion?",
                "expected": "46 true search tickets (23%) are misrouted into infra.",
            },
        ],
    )


def pt30_repair_line_struck() -> dict[str, Any]:
    task_id = "pt30_repair_line_struck"
    root = _task_root(task_id, "public-test")

    concurrencies = [1, 4, 8, 16, 32, 64, 128]
    curves = {
        "v1.0": [410, 1240, 2080, 2890, 3190, 3260, 3120],
        "v1.1": [430, 1310, 2190, 2940, 3150, 2960, 2520],
        "v2.0": [460, 1520, 2680, 3780, 4490, 4820, 4150],
    }
    rows: list[list[Any]] = []
    for rel, vals in curves.items():
        for conc, rps, base_rps in zip(concurrencies, vals, curves["v1.0"]):
            delta_pct = round(100.0 * (rps - base_rps) / base_rps, 1)
            rows.append([conc, rel, rps, delta_pct])

    _write_csv(root, "throughput.csv", ["concurrency", "release", "req_per_sec", "delta_vs_v1_pct"], rows)

    v2_peak = float(max(curves["v2.0"]))
    v1_at_64 = float(curves["v1.0"][5])
    v2_gain_pct = 100.0 * (v2_peak - v1_at_64) / v1_at_64
    v11_drop_pct = 100.0 * (curves["v1.1"][-1] - curves["v1.0"][-1]) / curves["v1.0"][-1]

    broken_script = '''"""Draft throughput scaling chart (has line-struck, malformed, and clipped text)."""

import csv
import sys
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt

DATA_DIR = Path(__file__).resolve().parent
OUT_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "pt30_broken.png"

series: dict[str, tuple[list[int], list[float]]] = {}
with open(DATA_DIR / "throughput.csv", encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        xs, ys = series.setdefault(row["release"], ([], []))
        xs.append(int(row["concurrency"]))
        ys.append(float(row["req_per_sec"]))

fig, ax = plt.subplots(figsize=(7, 4.4), dpi=100)
colors = {"v1.0": "#64748b", "v1.1": "#d97706", "v2.0": "#2563eb"}
for rel, (xs, ys) in series.items():
    ax.plot(xs, ys, marker="o", linewidth=2.2, color=colors[rel], label=rel)

ax.text(32, 4490, "v2.0 (+48%% at c=64)", fontsize=11, color=colors["v2.0"], ha="center", va="center")
ax.text(64, 2960, "v1.1 (-19% at c=128)", fontsize=11, color=colors["v1.1"], ha="center", va="center")
ax.text(129, 4150, "v2.0 release throughput end", fontsize=11, color=colors["v2.0"], va="center", clip_on=False)

ax.set_xlim(0, 130)
ax.set_ylim(0, 5400)
ax.set_xlabel("Concurrency (workers)", fontsize=11)
ax.set_ylabel("Throughput (req/s)", fontsize=11)
ax.set_title("v2.0 peaks at 4,820 req/s (+48%% over v1.0)", fontsize=12)
fig.savefig(OUT_PATH, dpi=100)
'''
    _write_text(root / "data" / "broken_plot.py", broken_script)

    _write_text(
        root / "context.md",
        """
        # Thread

        **User:** Our load-scaling script (`data/broken_plot.py`) on
        `data/throughput.csv` rendered with several visual glitches: lines slice
        right through the annotations, negative deltas use raw ASCII hyphens,
        there is a `%%` typo in the title/label, and the right-hand label clips
        off the edge of the image.

        **Assistant:** I see `data/throughput.csv` (`concurrency`, `release`,
        `req_per_sec`, `delta_vs_v1_pct`) across releases `v1.0`, `v1.1`, and
        `v2.0` from concurrency 1 to 128, along with `data/broken_plot.py`.

        **User:** Clean up the plot completely so labels sit cleanly off the
        lines, formatting is crisp (proper minus signs, no `%%`), and nothing
        clips at the canvas edge.

        **Assistant:** I'll rebuild the scaling figure cleanly with unobstructed
        labels, accurate deltas, and proper typography at 700 px width.

        **User:** One clean figure for the release notes, please.
        """,
    )

    return _write_rubric(
        root,
        task_id=task_id,
        split="public-test",
        track="byo_repair",
        domain="Systems",
        title="Repair throughput line chart (line-struck, malformed, and clipped text)",
        display_width_px=700,
        surface="chat",
        what="v2.0 peak throughput (req/s), its gain over v1.0 at c=64 (%), or v1.1 regression at c=128 (%)",
        accept=[v2_peak, v2_gain_pct, v11_drop_pct, abs(v11_drop_pct)],
        rel_tol=0.08,
        abs_tol=1.0,
        uncertainty_required=False,
        required_disclosures=["v2.0|v2", "v1.1|concurrency|64"],
        reader_questions=[
            {
                "kind": "primary",
                "question": "Where does v2.0 peak and how much faster is it than v1.0 there?",
                "expected": f"v2.0 peaks at {v2_peak:,.0f} req/s at concurrency 64 (+{v2_gain_pct:.1f}% over v1.0's {v1_at_64:,.0f} req/s).",
            },
            {
                "kind": "uncertainty",
                "question": "Are these single benchmark sweeps per concurrency level?",
                "expected": "Yes, one throughput measurement per (release, concurrency) point.",
            },
            {
                "kind": "nuance",
                "question": "What happens to v1.1 and v2.0 at concurrency 128?",
                "expected": f"Both drop past concurrency 64; v1.1 falls to 2,520 req/s ({v11_drop_pct:.1f}% below v1.0).",
            },
        ],
    )


# ---------------------------------------------------------------------------
# Held-out tasks (h11..h15)
# ---------------------------------------------------------------------------


def h11_chrome_trace_build() -> dict[str, Any]:
    task_id = "h11_chrome_trace_build"
    root = _task_root(task_id, "heldout")

    us = 1_000_000
    events = [
        {"name": "parse_ast", "cat": "frontend", "ph": "X", "ts": 0, "dur": int(8.2 * us), "pid": 1, "tid": 1},
        {"name": "typecheck", "cat": "frontend", "ph": "X", "ts": int(8.2 * us), "dur": int(13.4 * us), "pid": 1, "tid": 1},
        {"name": "ir_optimize", "cat": "middle", "ph": "X", "ts": int(21.6 * us), "dur": int(10.8 * us), "pid": 1, "tid": 1},
        {"name": "codegen_shard_0", "cat": "codegen", "ph": "X", "ts": int(32.4 * us), "dur": int(24.1 * us), "pid": 1, "tid": 1},
        {"name": "codegen_shard_1", "cat": "codegen", "ph": "X", "ts": int(32.4 * us), "dur": int(26.8 * us), "pid": 1, "tid": 2},
        {"name": "codegen_shard_2", "cat": "codegen", "ph": "X", "ts": int(32.4 * us), "dur": int(29.5 * us), "pid": 1, "tid": 3},
        {"name": "codegen_shard_3", "cat": "codegen", "ph": "X", "ts": int(32.4 * us), "dur": int(22.9 * us), "pid": 1, "tid": 4},
        {"name": "lto_link", "cat": "linker", "ph": "X", "ts": int(61.9 * us), "dur": int(51.8 * us), "pid": 1, "tid": 1},
        {"name": "strip_and_sign", "cat": "package", "ph": "X", "ts": int(113.7 * us), "dur": int(4.7 * us), "pid": 1, "tid": 1},
    ]
    payload = {"displayTimeUnit": "ms", "traceEvents": events}
    _write_json(root, "build_trace.json", payload)

    total_s = max(e["ts"] + e["dur"] for e in events) / us
    lto_s = next(e["dur"] for e in events if e["name"] == "lto_link") / us
    lto_share = 100.0 * lto_s / total_s

    _write_text(
        root / "context.md",
        """
        # Thread

        **User:** Our release binary build takes nearly two minutes even with four
        parallel codegen threads. The compiler trace export (`traceEvents` JSON
        with microsecond `ts` and `dur`) is in `data/build_trace.json`.

        **Assistant:** `build_trace.json` records 9 complete (`ph: "X"`) phase
        events across threads `tid` 1–4: `parse_ast`, `typecheck`, `ir_optimize`,
        four parallel `codegen_shard_*` tasks, `lto_link`, and `strip_and_sign`.

        **User:** The team wants to add more codegen threads, but I suspect we're
        hitting a serial bottleneck elsewhere. Show the parallel build timeline
        and identify what dominates wall-clock time.

        **Assistant:** I'll plot the compiler phases by thread over wall-clock
        seconds and quantify the single largest stage's share of total build time.

        **User:** One figure for the compiler build-time thread, please.
        """,
    )

    return _write_rubric(
        root,
        task_id=task_id,
        split="heldout",
        track="swe_coding",
        domain="Compilers",
        title="Compiler trace timeline: serial LTO link bottleneck",
        display_width_px=700,
        surface="chat",
        what="lto_link duration (s), its share of total build time (%), or total build wall time (s)",
        accept=[lto_s, lto_share, total_s],
        rel_tol=0.08,
        abs_tol=0.5,
        uncertainty_required=False,
        reader_questions=[
            {
                "kind": "primary",
                "question": "Which compiler stage is the biggest bottleneck and how much of the build does it take?",
                "expected": f"lto_link takes {lto_s:.1f} s ({lto_share:.1f}% of the {total_s:.1f} s total build), running single-threaded.",
            },
            {
                "kind": "uncertainty",
                "question": "Are the stage durations exact measurements from a single trace?",
                "expected": "Yes, exact microsecond trace timestamps from one profiled release build.",
            },
            {
                "kind": "nuance",
                "question": "Would adding more parallel codegen threads fix the main bottleneck?",
                "expected": "No; all four codegen shards finish within 29.5 s, whereas serial lto_link alone takes 51.8 s.",
            },
        ],
    )


def h12_hyperfine_within_noise() -> dict[str, Any]:
    task_id = "h12_hyperfine_within_noise"
    root = _task_root(task_id, "heldout")
    rng = np.random.default_rng(3012)

    # Construct deterministic samples whose exact mean diff is ~1.8% with overlapping ±1 s.d.
    raw_base = rng.normal(0.0, 1.0, 25)
    raw_base = (raw_base - raw_base.mean()) / raw_base.std(ddof=1)
    base_times = 0.4120 + 0.0185 * raw_base

    raw_cand = rng.normal(0.0, 1.0, 25)
    raw_cand = (raw_cand - raw_cand.mean()) / raw_cand.std(ddof=1)
    cand_times = 0.4046 + 0.0192 * raw_cand

    base_entry = _hyperfine_entry("./bin/hash_index fixtures/corpus_50mb.bin", base_times, rng)
    cand_entry = _hyperfine_entry("./bin/hash_index fixtures/corpus_50mb.bin", cand_times, rng)

    _write_json(root, "baseline_bench.json", {"results": [base_entry]})
    _write_json(root, "candidate_bench.json", {"results": [cand_entry]})

    diff_s = base_entry["mean"] - cand_entry["mean"]
    diff_ms = 1000.0 * diff_s
    diff_pct = 100.0 * diff_s / base_entry["mean"]

    _write_text(
        root / "context.md",
        """
        # Thread

        **User:** I tried replacing our hash-table probing loop with an SIMD
        candidate and benchmarked both binaries with `hyperfine --export-json`
        (25 runs each). Files are `data/baseline_bench.json` and
        `data/candidate_bench.json`.

        **Assistant:** Both files contain a single `hyperfine` result with 25
        per-run timings in seconds, `mean`, `stddev`, and `median`.

        **User:** The candidate's mean came out slightly lower. Can I put in the
        PR description that the SIMD rewrite speeds up indexing, or is this just
        measurement noise?

        **Assistant:** I'll compare the full run distributions and ±1 s.d.
        intervals for baseline and candidate and tell you honestly whether the
        difference clears noise.

        **User:** One figure I can link in the PR to settle the question, please.
        """,
    )

    return _write_rubric(
        root,
        task_id=task_id,
        split="heldout",
        track="swe_coding",
        domain="Systems",
        title="Hyperfine no-effect trap: 1.8% difference inside overlapping s.d.",
        display_width_px=700,
        surface="chat",
        what="Mean difference (~1.8% / ~7.4 ms) is within overlapping ±1 s.d. noise (no reliable speedup)",
        accept=[diff_pct, diff_ms, base_entry["mean"] * 1000.0, cand_entry["mean"] * 1000.0],
        rel_tol=0.25,
        abs_tol=0.6,
        uncertainty_required=True,
        no_effect_trap=True,
        forbidden_overclaim_phrases=[
            "clearly faster",
            "significantly faster",
            "proves speedup",
            "outside noise",
            "definitive speedup",
            "clear win",
            "beats baseline cleanly",
        ],
        required_disclosures=[
            "within noise|noise|overlap|no speedup|not faster|inconclusive",
            "25 runs|n=25|s.d.|sd|±|ci",
        ],
        reader_questions=[
            {
                "kind": "primary",
                "question": "How large is the mean runtime difference between candidate and baseline?",
                "expected": f"Only {diff_pct:.1f}% ({diff_ms:.1f} ms: {base_entry['mean'] * 1000:.1f} ms vs {cand_entry['mean'] * 1000:.1f} ms).",
            },
            {
                "kind": "uncertainty",
                "question": "Is the candidate reliably faster than baseline?",
                "expected": (
                    f"No; the {diff_ms:.1f} ms gap is well inside the ±1 s.d. noise "
                    f"(±{base_entry['stddev'] * 1000:.1f} ms and ±{cand_entry['stddev'] * 1000:.1f} ms) with heavily overlapping runs."
                ),
            },
            {
                "kind": "nuance",
                "question": "Should the PR claim a verified speedup from this benchmark?",
                "expected": "No; there is no evidence of a real speedup beyond measurement noise.",
            },
        ],
    )


def h13_narrow_ide_sidebar() -> dict[str, Any]:
    task_id = "h13_narrow_ide_sidebar"
    root = _task_root(task_id, "heldout")
    rng = np.random.default_rng(3013)

    rows: list[list[Any]] = []
    for mode, mu, sigma in (("serial", math.log(194.0), 0.16), ("parallel_8w", math.log(81.0), 0.21)):
        for i in range(1, 81):
            dur = float(rng.lognormal(mu, sigma))
            if mode == "parallel_8w" and i in (17, 42, 69):
                dur = float(rng.uniform(138.0, 158.0))  # occasional lock-contention tail
            failed = 1 if rng.random() < 0.04 else 0
            rows.append([mode, f"{mode[:3]}-{i:03d}", round(dur, 2), failed])

    _write_csv(root, "test_durations.csv", ["mode", "run_id", "duration_s", "failed_tests"], rows)

    ser = np.array([r[2] for r in rows if r[0] == "serial"])
    par = np.array([r[2] for r in rows if r[0] == "parallel_8w"])
    ser_med = float(np.median(ser))
    par_med = float(np.median(par))
    saving_s = ser_med - par_med
    saving_pct = 100.0 * saving_s / ser_med
    par_p95 = float(np.percentile(par, 95))

    _write_text(
        root / "context.md",
        """
        # Thread

        **User:** I'm inspecting our test-suite parallelization rollout inside a
        450 px wide IDE sidebar pane. Durations for 80 `serial` runs and 80
        `parallel_8w` runs are in `data/test_durations.csv`.

        **Assistant:** Columns: `mode` (`serial`, `parallel_8w`), `run_id`,
        `duration_s`, and `failed_tests`. Both modes are right-skewed.

        **User:** Show the full duration distribution before and after enabling
        8-worker parallel tests, including any slow tail runs, sized so every
        label stays crisp inside a 450 px sidebar.

        **Assistant:** I'll compare the `serial` and `parallel_8w` distributions
        with medians, spread, and tail points tailored to a 450 px narrow width.

        **User:** One compact sidebar-friendly figure, please.
        """,
    )

    return _write_rubric(
        root,
        task_id=task_id,
        split="heldout",
        track="multi_surface",
        domain="DevOps",
        title="IDE sidebar (450 px) test-suite parallelization distribution",
        display_width_px=450,
        surface="narrow",
        what="Median test duration reduction (% or s) or the serial/parallel_8w medians (s)",
        accept=[saving_pct, saving_s, par_med, ser_med],
        rel_tol=0.08,
        abs_tol=1.0,
        uncertainty_required=True,
        required_disclosures=[
            "80 runs|n=80|iqr|s.d.|sd|±|spread|percentile",
            "parallel_8w|parallel|tail|outlier",
        ],
        reader_questions=[
            {
                "kind": "primary",
                "question": "How much faster is the median test-suite run with 8 parallel workers?",
                "expected": f"Median dropped {saving_pct:.1f}% ({saving_s:.0f} s faster, from {ser_med:.0f} s to {par_med:.0f} s).",
            },
            {
                "kind": "uncertainty",
                "question": "Do the bulk distributions of serial and parallel_8w overlap?",
                "expected": "Hardly at all; the IQRs are cleanly separated across the 80 runs per mode.",
            },
            {
                "kind": "nuance",
                "question": "What caveat appears in the upper tail of parallel_8w?",
                "expected": f"A few slow tail runs reach ~140–158 s (p95 ≈ {par_p95:.0f} s), nearly double the parallel median.",
            },
        ],
    )


def h14_repair_boxplot_claim() -> dict[str, Any]:
    task_id = "h14_repair_boxplot_claim"
    root = _task_root(task_id, "heldout")
    rng = np.random.default_rng(3014)

    regions = [
        ("us-east", 48.0, 0.24),
        ("us-west", 62.0, 0.25),
        ("eu-central", 89.0, 0.26),
        ("ap-northeast", 142.0, 0.28),
    ]
    rows: list[list[Any]] = []
    for reg, med, sigma in regions:
        vals = rng.lognormal(math.log(med), sigma, 60)
        for i, v in enumerate(vals, start=1):
            rows.append([reg, f"{reg[:2]}-{i:03d}", round(float(v), 2)])

    _write_csv(root, "latencies.csv", ["region", "request_id", "latency_ms"], rows)

    meds = {reg: float(np.median([r[2] for r in rows if r[0] == reg])) for reg, _, _ in regions}
    ap_med = meds["ap-northeast"]
    ratio = ap_med / meds["us-east"]
    diff = ap_med - meds["us-east"]

    broken_script = '''"""Draft regional latency boxplot (wrong median claim, tiny fonts, unlabelled y-axis)."""

import csv
import sys
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt

DATA_DIR = Path(__file__).resolve().parent
OUT_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "h14_broken.png"

regions = ["us-east", "us-west", "eu-central", "ap-northeast"]
buckets: dict[str, list[float]] = {r: [] for r in regions}
with open(DATA_DIR / "latencies.csv", encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        buckets[row["region"]].append(float(row["latency_ms"]))

fig, ax = plt.subplots(figsize=(14, 5), dpi=100)
ax.boxplot([buckets[r] for r in regions], tick_labels=regions)
ax.tick_params(labelsize=9)
ax.set_title("ap-northeast median latency (ms) reaches 312", fontsize=11)
fig.savefig(OUT_PATH, dpi=100)
'''
    _write_text(root / "data" / "broken_plot.py", broken_script)

    _write_text(
        root / "context.md",
        """
        # Thread

        **User:** A teammate sent `data/broken_plot.py` plotting our regional API
        latency samples (`data/latencies.csv`, 60 requests per region), but the
        headline median looks way too high, the y-axis has no label or units, and
        the text is tiny when pasted into a 700 px chat window.

        **Assistant:** I checked `data/latencies.csv` (`region`, `request_id`,
        `latency_ms`) and `data/broken_plot.py`. The draft uses a 14×5 canvas with
        9 pt ticks, omits the y-axis label, and claims a 312 ms median for
        `ap-northeast` that doesn't match the data.

        **User:** Please fix the plot cleanly so the headline states the true
        `ap-northeast` median (and how it compares to `us-east`), the axis is
        labelled with units, and all text is legible at 700 px.

        **Assistant:** I'll recompute the regional medians and spreads from
        `data/latencies.csv` and produce a clean, readable figure.

        **User:** One repaired figure for the latency review thread, please.
        """,
    )

    return _write_rubric(
        root,
        task_id=task_id,
        split="heldout",
        track="byo_repair",
        domain="Backend",
        title="Repair regional latency boxplot (wrong median claim, tiny text, unlabelled y-axis)",
        display_width_px=700,
        surface="chat",
        what="True ap-northeast median latency (ms), ratio to us-east, or difference vs us-east (ms)",
        accept=[ap_med, ratio, diff],
        rel_tol=0.08,
        abs_tol=1.5,
        uncertainty_required=True,
        required_disclosures=["ap-northeast", "ms", "60|iqr|median|spread|s.d.|sd|n=60"],
        reader_questions=[
            {
                "kind": "primary",
                "question": "What is the true median latency in ap-northeast?",
                "expected": f"About {ap_med:.0f} ms (roughly {ratio:.1f}× us-east's {meds['us-east']:.0f} ms), not 312 ms.",
            },
            {
                "kind": "uncertainty",
                "question": "Is ap-northeast's latency distribution cleanly above us-east?",
                "expected": "Yes; the IQR boxes for ap-northeast and us-east are completely separated across 60 requests each.",
            },
            {
                "kind": "nuance",
                "question": "How do the four regions rank from fastest to slowest median latency?",
                "expected": f"us-east ({meds['us-east']:.0f} ms) < us-west ({meds['us-west']:.0f} ms) < eu-central ({meds['eu-central']:.0f} ms) < ap-northeast ({ap_med:.0f} ms).",
            },
        ],
    )


def h15_repair_multipanel_ci() -> dict[str, Any]:
    task_id = "h15_repair_multipanel_ci"
    root = _task_root(task_id, "heldout")
    rng = np.random.default_rng(3015)

    epochs = np.arange(1, 26)
    rows: list[list[Any]] = []
    # baseline_sgd starts faster (lower loss early) then plateaus; cosine_warmup crosses around epoch 9
    for ep in epochs:
        base_loss = 0.41 + 0.92 * math.exp(-0.26 * ep) + rng.normal(0, 0.006)
        cos_loss = 0.27 + 1.38 * math.exp(-0.24 * ep) + rng.normal(0, 0.006)
        base_loss_sd = round(float(0.022 + 0.015 * math.exp(-0.12 * ep)), 4)
        cos_loss_sd = round(float(0.019 + 0.014 * math.exp(-0.12 * ep)), 4)

        base_acc = 83.6 - 29.0 * math.exp(-0.27 * ep) + rng.normal(0, 0.2)
        cos_acc = 89.1 - 44.0 * math.exp(-0.24 * ep) + rng.normal(0, 0.2)
        base_acc_sd = round(float(0.65 + 0.45 * math.exp(-0.12 * ep)), 3)
        cos_acc_sd = round(float(0.58 + 0.42 * math.exp(-0.12 * ep)), 3)

        rows.append([int(ep), "baseline_sgd", round(float(base_loss), 4), base_loss_sd, round(float(base_acc), 2), base_acc_sd])
        rows.append([int(ep), "cosine_warmup", round(float(cos_loss), 4), cos_loss_sd, round(float(cos_acc), 2), cos_acc_sd])

    _write_csv(
        root,
        "training.csv",
        ["epoch", "model", "val_loss_mean", "val_loss_sd", "val_acc_mean", "val_acc_sd"],
        rows,
    )

    base_rows = [r for r in rows if r[1] == "baseline_sgd"]
    cos_rows = [r for r in rows if r[1] == "cosine_warmup"]
    cross_idx = next(i for i in range(len(epochs)) if cos_rows[i][2] < base_rows[i][2])
    cross_ep = float(epochs[cross_idx])
    final_cos_acc = float(cos_rows[-1][4])
    final_base_acc = float(base_rows[-1][4])
    acc_gain = final_cos_acc - final_base_acc

    broken_script = '''"""Draft 2-panel training curve (unlabelled bands, overlapping text, wrong crossing epoch)."""

import csv
import sys
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

DATA_DIR = Path(__file__).resolve().parent
OUT_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "h15_broken.png"

by_model: dict[str, list[dict[str, float]]] = {}
with open(DATA_DIR / "training.csv", encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        by_model.setdefault(row["model"], []).append(
            {
                "epoch": float(row["epoch"]),
                "loss": float(row["val_loss_mean"]),
                "loss_sd": float(row["val_loss_sd"]),
                "acc": float(row["val_acc_mean"]),
                "acc_sd": float(row["val_acc_sd"]),
            }
        )

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.5, 4.4), dpi=100)
colors = {"baseline_sgd": "#64748b", "cosine_warmup": "#2563eb"}

for name, pts in by_model.items():
    ep = np.array([p["epoch"] for p in pts])
    loss = np.array([p["loss"] for p in pts])
    lsd = np.array([p["loss_sd"] for p in pts])
    acc = np.array([p["acc"] for p in pts])
    asd = np.array([p["acc_sd"] for p in pts])

    ax1.plot(ep, loss, color=colors[name], lw=2, label=name)
    ax1.fill_between(ep, loss - lsd, loss + lsd, color=colors[name], alpha=0.2)
    ax2.plot(ep, acc, color=colors[name], lw=2, label=name)
    ax2.fill_between(ep, acc - asd, acc + asd, color=colors[name], alpha=0.2)

ax1.set_xlabel("Epoch")
ax1.set_ylabel("Validation loss")
ax1.legend(loc="upper right")
ax1.text(17.5, 1.08, "Warmup starts slower", fontsize=11)
ax1.text(17.5, 1.05, "Then overtakes later", fontsize=11)

ax2.set_xlabel("Epoch")
ax2.set_ylabel("Validation accuracy (%)")
ax2.legend(loc="lower right")

fig.suptitle("Cosine warmup overtakes baseline at epoch 42", fontsize=13)
fig.tight_layout()
fig.savefig(OUT_PATH, dpi=100)
'''
    _write_text(root / "data" / "broken_plot.py", broken_script)

    _write_text(
        root / "context.md",
        """
        # Thread

        **User:** Here is my 2-panel validation loss and accuracy script
        (`data/broken_plot.py`) for `data/training.csv` (epochs 1–25, averaged
        across 5 runs with `val_loss_sd` and `val_acc_sd`). Can you fix the bugs?

        **Assistant:** I inspected `data/training.csv` and `data/broken_plot.py`.
        The script shades `fill_between` bands without stating what they measure,
        places two overlapping notes right on top of the legend in panel 1, and
        the headline claims a crossing at epoch 42 even though training only runs
        to epoch 25 and the curves cross much earlier.

        **User:** Fix all three issues: state the true crossover epoch and final
        accuracy gain in the headline, label the shaded ±1 s.d. bands clearly,
        and remove the text overlap.

        **Assistant:** I'll recompute the crossover epoch and final metrics from
        `data/training.csv` and produce a clean 2-panel 700 px figure.

        **User:** One repaired figure for the training-schedule review, please.
        """,
    )

    return _write_rubric(
        root,
        task_id=task_id,
        split="heldout",
        track="byo_repair",
        domain="ML Systems",
        title="Repair 2-panel training curves (unlabelled CI band, text overlap, wrong crossing epoch)",
        display_width_px=700,
        surface="chat",
        what=f"True crossover epoch ({int(cross_ep)}), final cosine_warmup accuracy (%), or final accuracy gain (pts)",
        accept=[cross_ep, final_cos_acc, acc_gain],
        rel_tol=0.12,
        abs_tol=1.0,
        uncertainty_required=True,
        min_panels=2,
        required_disclosures=["s.d.|sd|±|5 seeds|n=5", "epoch 6|crossover|cosine"],
        reader_questions=[
            {
                "kind": "primary",
                "question": "At which epoch does cosine_warmup overtake baseline_sgd?",
                "expected": f"At epoch {int(cross_ep)} (well before epoch 25, not epoch 42).",
            },
            {
                "kind": "uncertainty",
                "question": "What do the shaded bands show and are the final curves separated beyond spread?",
                "expected": f"Bands show ±1 s.d.; by epoch 25 cosine_warmup leads by +{acc_gain:.1f} pts ({final_cos_acc:.1f}% vs {final_base_acc:.1f}%), cleanly outside ±0.6 pt s.d.",
            },
            {
                "kind": "nuance",
                "question": "How does cosine_warmup behave during the earliest epochs?",
                "expected": f"It starts with higher loss / lower accuracy during early warmup (epochs 1–{int(cross_ep) - 1}) before overtaking and finishing clearly ahead.",
            },
        ],
    )


GENERATORS = [
    pt16_hyperfine_diff,
    pt17_pytest_regression,
    pt18_ci_pipeline_timeline,
    pt19_k6_latency_deploy,
    pt20_bundle_waterfall,
    pt21_llm_pareto_frontier,
    pt22_signup_funnel,
    pt23_memory_soak_leak,
    pt24_narrow_phone_alert,
    pt25_slide_quarterly_perf,
    pt26_dark_dashboard_card,
    pt27_terminal_only_bench,
    pt28_repair_ablation_bars,
    pt29_repair_jet_heatmap,
    pt30_repair_line_struck,
    h11_chrome_trace_build,
    h12_hyperfine_within_noise,
    h13_narrow_ide_sidebar,
    h14_repair_boxplot_claim,
    h15_repair_multipanel_ci,
]


def main() -> None:
    rubrics = [fn() for fn in GENERATORS]
    pub = sum(1 for r in rubrics if r["split"] == "public-test")
    held = sum(1 for r in rubrics if r["split"] == "heldout")
    print(f"generated {len(rubrics)} tasks ({pub} public-test, {held} heldout)")


if __name__ == "__main__":
    main()
