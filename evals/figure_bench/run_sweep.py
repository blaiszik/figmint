"""Parallel, resumable 60-task benchmark sweep harness for figure-bench v0.1.

Spawns one fresh, isolated headless Claude Code (``claude -p``) agent per task
and arm inside each task's ``bench.py start`` working directory, with global
hooks, MCP servers, and slash-command skills disabled so baseline arms
(``matplotlib-plain``, ``matplotlib-hook``) stay completely uncontaminated.

Usage:
    python evals/figure_bench/run_sweep.py \\
        --arms mintfig,matplotlib-plain,matplotlib-hook \\
        --run-prefix evals/figure_bench/runs/v01_sonnet \\
        --split all --model sonnet --workers 6
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
BENCH_PY = HERE / "bench.py"
SKILL_DIR = REPO_ROOT / "src" / "mintfig" / "assets"

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import rubric


def _find_claude(explicit: str | None) -> str:
    if explicit:
        return explicit
    found = shutil.which("claude")
    if found:
        return found
    local = Path.home() / ".local" / "bin" / "claude"
    if local.is_file():
        return str(local)
    raise FileNotFoundError("Could not find `claude` CLI on PATH or at ~/.local/bin/claude.")


def _is_task_complete(work: Path) -> tuple[bool, dict[str, Any] | None]:
    state_path = work / ".bench" / "state.json"
    if not state_path.is_file():
        return False, None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, None
    atts = state.get("attempts") or []
    if not atts:
        return False, state
    done = any(a.get("done", a.get("passed")) for a in atts) or len(atts) >= 3
    return done, state


def _build_prompt(start_output: str, work: Path, arm: str) -> str:
    extra = (
        "IMPORTANT EXECUTION INSTRUCTIONS:\n"
        f"- Your current working directory is {work}.\n"
        "- Work ONLY inside this folder (read context.md and data/; do NOT inspect any other repo files"
        + (" except the SKILL.md path explicitly listed below" if arm == "mintfig" else "")
        + ").\n"
        "- Write your plotting script (e.g. figure.py) and concise reply Markdown (reply.md) inside this folder.\n"
        "- Submit using the exact `bench.py submit` command below. Never render figure.png yourself outside `submit`.\n"
        "- If a submission fails checks and attempts remain, fix the reported issues and submit again.\n"
        "- Stop immediately after the first passing/completed submission.\n\n"
    )
    return extra + start_output.strip() + "\n"


def _run_one_task(
    task: str,
    *,
    arm: str,
    run_dir: Path,
    python_bin: str,
    claude_bin: str,
    model: str,
    timeout_s: int,
    settings_path: Path,
    mcp_path: Path,
    effort: str | None,
    resume: bool,
    library: str | None = None,
    skill: str | None = None,
) -> dict[str, Any]:
    work = run_dir / task
    t0 = time.time()

    if resume:
        done, state = _is_task_complete(work)
        if done and state is not None:
            atts = state.get("attempts") or []
            last = atts[-1]
            return {
                "task": task,
                "arm": arm,
                "status": "skipped",
                "passed": bool(last.get("passed")),
                "done": bool(last.get("done", last.get("passed"))),
                "attempts": len(atts),
                "seconds": round(last["finished"] - state["started"], 1),
            }
        if work.exists():
            shutil.rmtree(work)
    elif work.exists():
        shutil.rmtree(work)

    # 1. bench.py start
    start_cmd = [
        python_bin,
        str(BENCH_PY),
        "start",
        task,
        "--run",
        str(run_dir),
        "--arm",
        arm,
        "--python",
        python_bin,
    ]
    if library:
        start_cmd += ["--library", library]
    if skill:
        start_cmd += ["--skill", skill]
    start_proc = subprocess.run(start_cmd, capture_output=True, text=True, check=False)
    if start_proc.returncode != 0:
        return {
            "task": task,
            "arm": arm,
            "status": "start_error",
            "passed": False,
            "done": False,
            "attempts": 0,
            "seconds": round(time.time() - t0, 1),
            "error": (start_proc.stderr or start_proc.stdout).strip()[:300],
        }

    prompt = _build_prompt(start_proc.stdout, work, arm)
    log_path = work / ".bench" / "agent.log"

    # 2. Launch fresh isolated Claude Code worker
    cmd = [
        claude_bin,
        "-p",
        prompt,
        "--model",
        model,
        "--output-format",
        "json",
        "--no-session-persistence",
        "--disable-slash-commands",
        "--dangerously-skip-permissions",
        "--settings",
        str(settings_path),
        "--strict-mcp-config",
        "--mcp-config",
        str(mcp_path),
        "--tools",
        "Read,Write,Edit,Bash,Glob,Grep",
        "--add-dir",
        str(HERE),
    ]
    if effort:
        cmd += ["--effort", effort]
    if arm == "mintfig":
        cmd += ["--add-dir", str(SKILL_DIR)]
    elif skill:
        cmd += ["--add-dir", str(Path(skill).resolve().parent)]

    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env["MPLCONFIGDIR"] = "/tmp/mpl-figbench"

    timed_out = False
    try:
        proc = subprocess.run(
            cmd,
            cwd=work,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            env=env,
        )
        log_body = proc.stdout + ("\n--- STDERR ---\n" + proc.stderr if proc.stderr else "")
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        out_s = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err_s = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        log_body = f"TIMED OUT after {timeout_s}s\n{out_s}\n--- STDERR ---\n{err_s}"

    log_path.write_text(log_body, encoding="utf-8")

    # 3. Read final task state
    done, state = _is_task_complete(work)
    atts = (state or {}).get("attempts") or []
    last = atts[-1] if atts else None
    passed = bool(last and last.get("passed"))
    elapsed = (
        round(last["finished"] - state["started"], 1)
        if (last and state)
        else round(time.time() - t0, 1)
    )
    return {
        "task": task,
        "arm": arm,
        "status": "timeout" if timed_out and not done else ("done" if done else "incomplete"),
        "passed": passed,
        "done": done,
        "attempts": len(atts),
        "seconds": elapsed,
        "failed_checks": [c["name"] for c in (last.get("checks") or []) if not c.get("passed")] if last else ["no_submission"],
    }


def _run_arm_sweep(
    tasks: list[str],
    *,
    arm: str,
    run_dir: Path,
    python_bin: str,
    claude_bin: str,
    model: str,
    workers: int,
    timeout_s: int,
    settings_path: Path,
    mcp_path: Path,
    effort: str | None,
    resume: bool,
    library: str | None = None,
    skill: str | None = None,
) -> list[dict[str, Any]]:
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n=== Sweeping arm={arm} ({len(tasks)} tasks, workers={workers}, model={model}) -> {run_dir} ===", flush=True)
    results: list[dict[str, Any]] = []
    lock = threading.Lock()
    completed = 0
    t_arm0 = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {
            pool.submit(
                _run_one_task,
                task,
                arm=arm,
                run_dir=run_dir,
                python_bin=python_bin,
                claude_bin=claude_bin,
                model=model,
                timeout_s=timeout_s,
                settings_path=settings_path,
                mcp_path=mcp_path,
                effort=effort,
                resume=resume,
                library=library,
                skill=skill,
            ): task
            for task in tasks
        }
        for fut in concurrent.futures.as_completed(futs):
            res = fut.result()
            with lock:
                completed += 1
                results.append(res)
                tag = "SKIP" if res["status"] == "skipped" else ("PASS" if res["passed"] else ("DONE" if res["done"] else res["status"].upper()))
                fail_str = f" [{', '.join(res.get('failed_checks', [])[:3])}]" if not res["passed"] and res.get("failed_checks") else ""
                print(
                    f"  [{completed:2d}/{len(tasks)}] {arm:16s} {res['task']:26s} {tag:10s} "
                    f"att={res['attempts']} {res['seconds']:5.1f}s{fail_str}",
                    flush=True,
                )

    elapsed_arm = time.time() - t_arm0
    passed_n = sum(1 for r in results if r["passed"])
    done_n = sum(1 for r in results if r["done"])
    print(
        f"=== Finished arm={arm}: passed={passed_n}/{len(tasks)}, done={done_n}/{len(tasks)} in {elapsed_arm:.1f}s ===",
        flush=True,
    )

    # Automatically grade the run folder
    subprocess.run([python_bin, str(BENCH_PY), "grade", "--run", str(run_dir)], check=False)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--arms",
        default="mintfig,matplotlib-plain,matplotlib-hook",
        help="Comma-separated arms to run (default: mintfig,matplotlib-plain,matplotlib-hook).",
    )
    parser.add_argument(
        "--run-prefix",
        required=True,
        help="Run directory prefix; each arm writes to <run-prefix>_<arm_slug> (or exact path if 1 arm & --exact-run).",
    )
    parser.add_argument("--exact-run", action="store_true", help="Use --run-prefix verbatim when running a single arm.")
    parser.add_argument("--split", choices=["all", *rubric.VALID_SPLITS], default="all")
    parser.add_argument("--track", choices=rubric.VALID_TRACKS, default=None)
    parser.add_argument("--tasks", default=None, help="Optional comma-separated subset of task IDs.")
    parser.add_argument("--model", default="sonnet", help="Claude model alias or ID (default: sonnet).")
    parser.add_argument("--effort", default=None, help="Optional Claude --effort level (low, medium, high).")
    parser.add_argument("--workers", type=int, default=6, help="Parallel task workers (default: 6).")
    parser.add_argument("--timeout", type=int, default=240, help="Per-task wall timeout in seconds (default: 240).")
    parser.add_argument("--python", default=sys.executable, help="Python executable for bench.py and scripts.")
    parser.add_argument("--claude", default=None, help="Path to claude CLI.")
    parser.add_argument("--no-resume", action="store_true", help="Re-run even completed tasks.")
    parser.add_argument("--library", default=None, help="Library name for custom arm.")
    parser.add_argument("--skill", default=None, help="Skill file path for custom arm.")
    args = parser.parse_args()

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    claude_bin = _find_claude(args.claude)

    split_arg = None if args.split == "all" else args.split
    all_dirs = rubric.discover_task_dirs(HERE, split=split_arg, track=args.track)
    tasks = [d.name for d in all_dirs]
    if args.tasks:
        wanted = [t.strip() for t in args.tasks.split(",") if t.strip()]
        missing = [t for t in wanted if t not in set(tasks)]
        if missing:
            parser.error(f"Unknown task(s) for split={args.split}: {missing}")
        tasks = wanted

    with tempfile.TemporaryDirectory(prefix="figbench_claude_cfg_") as cfg_dir:
        settings_path = Path(cfg_dir) / "settings.json"
        settings_path.write_text(json.dumps({"disableAllHooks": True}), encoding="utf-8")
        mcp_path = Path(cfg_dir) / "mcp.json"
        mcp_path.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")

        run_dirs: list[Path] = []
        for arm in arms:
            if len(arms) == 1 and args.exact_run:
                run_dir = Path(args.run_prefix).resolve()
            else:
                slug = arm.replace("-", "_")
                run_dir = Path(f"{args.run_prefix}_{slug}").resolve()
            run_dirs.append(run_dir)
            _run_arm_sweep(
                tasks,
                arm=arm,
                run_dir=run_dir,
                python_bin=args.python,
                claude_bin=claude_bin,
                model=args.model,
                workers=args.workers,
                timeout_s=args.timeout,
                settings_path=settings_path,
                mcp_path=mcp_path,
                effort=args.effort,
                resume=not args.no_resume,
                library=args.library,
                skill=args.skill,
            )

        if len(run_dirs) > 1:
            cmp_out = Path(f"{args.run_prefix}_compare.md").resolve()
            subprocess.run(
                [args.python, str(BENCH_PY), "compare", *[str(d) for d in run_dirs], "--out", str(cmp_out)],
                check=False,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
