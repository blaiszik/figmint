"""figure-bench: can an agent turn a conversation and a dataset into a clean chat figure, fast?

Each task is a mock agent thread (tasks/NN_name/context.md) plus data
(tasks/NN_name/data/). The agent under test sees only its work folder and
mintfig's SKILL.md, writes a script that calls ``mint.explain(...).save(...)``,
and submits it. Grading is on time and on mintfig's own automated checks.

    python bench.py list
    python bench.py start  01_ablation --run runs/r1     # copies the task, starts the clock
    python bench.py submit 01_ablation --run runs/r1 figure.py   # renders + checks (max 3)
    python bench.py grade  --run runs/r1                  # results.json + results.md

The clock runs from ``start`` to the end of the first passing ``submit`` (so it
includes the agent's reading and thinking). A task passes when its last
submission passes every check. ``grade`` also scores the takeaway's number
against a hidden answer key; ``submit`` never reveals that score.

Submissions run with the Python that runs this file (``--python`` to change
it); it needs mintfig, and pandas if the agent uses it.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASKS = HERE / "tasks"
HELDOUT = HERE / "heldout"  # held-out tasks: never used to tune mintfig or SKILL.md
ANSWERS = HERE / "answers.json"
MAX_ATTEMPTS = 3
TIMEOUT_S = 120
MIN_TEXT_PX = 11.0  # mintfig's floor at the 700 px chat width
CHAT_WIDTH_PX = 700

_CAPTURE = r"""
import json, runpy, sys
import mintfig.explainer as ex
calls = []
_save = ex.Explanation.save
def _capturing_save(self, *a, **k):
    summary = _save(self, *a, **k)
    calls.append(json.loads(json.dumps(summary, default=str)))
    return summary
ex.Explanation.save = _capturing_save
try:
    runpy.run_path(sys.argv[1], run_name="__main__")
finally:
    with open(sys.argv[2], "w") as fh:
        json.dump(calls, fh, ensure_ascii=False)
"""

AGENT_RULES = """\
Rules for this task:
- Read context.md and the files in data/ in this folder, and mintfig's SKILL.md:
  {skill}
  Do not read mintfig's source code or anything else in the repository.
- Answer the last request in the thread with ONE chat figure made with mint.explain.
  Your script must save it as figure.png in this folder: fig.save("figure.png").
- Do not render figures yourself (no fig.save / mint.explain runs of your own):
  submit is your renderer. Images found in this folder that submit did not make
  are counted as local renders. Plain data analysis (numpy/pandas) is fine.
- Submit with:  {python} {bench} submit {task} --run {run} <your_script.py>
  Each submit renders your script and reports mintfig's summary, its facts and
  the checks (mintfig's own checks plus an independent layout audit).
  You have {max_attempts} submissions; stop at the first one that passes.
- The clock started now and stops when a submission passes.
"""

_IMAGE_SUFFIXES = {".png", ".svg", ".pdf", ".jpg", ".jpeg"}


def _local_images(work: Path, state: dict) -> list[str]:
    """Images in the work folder that no submission produced (data/ and .bench/ excluded)."""
    known = set(state.get("produced", []))
    found = []
    for f in work.rglob("*"):
        rel = f.relative_to(work)
        if rel.parts[0] in ("data", ".bench") or f.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        sig = f"{rel}:{f.stat().st_mtime_ns}"
        if sig not in known:
            found.append(sig)
    return found


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _all_tasks() -> list[Path]:
    return [t for root in (TASKS, HELDOUT) if root.exists()
            for t in sorted(root.iterdir()) if (t / "context.md").exists()]


def _task_dir(task: str) -> Path:
    for path in _all_tasks():
        if path.name == task:
            return path
    names = ", ".join(t.name for t in _all_tasks())
    sys.exit(f"unknown task {task!r}; tasks: {names}")


def _work(run: Path, task: str) -> Path:
    return run / task


def _state_path(run: Path, task: str) -> Path:
    return _work(run, task) / ".bench" / "state.json"


def _load_state(run: Path, task: str) -> dict:
    path = _state_path(run, task)
    if not path.exists():
        sys.exit(f"task {task} was not started in {run}; run `bench.py start {task} --run {run}`")
    return json.loads(path.read_text())


def _save_state(run: Path, task: str, state: dict) -> None:
    _state_path(run, task).write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")


def _skill_path() -> Path:
    return HERE.parents[1] / "src" / "mintfig" / "assets" / "SKILL.md"


# --------------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------------- #


def _spec_of(png: Path) -> dict | None:
    try:
        import mintfig as mint

        return mint.load(str(png)).to_spec()
    except Exception:  # noqa: BLE001 - any failure means the spec is not usable
        return None


_DOUBLED = re.compile(r"\b(\w+(?:\s+\w+)?)\s+\1\b", re.IGNORECASE)
_ASCII_MINUS = re.compile(r"(?:^|[\s(\[=:,])-\d")
_JUNK = re.compile(r"\b(nan|NaN|None|inf|-inf)\b")


def audit_layout(png: Path) -> dict:
    """Independent audit of the drawn figure, rebuilt from the PNG's embedded spec.

    Does not trust mintfig's own issue list: it draws the figure and inspects every
    visible text artist and line. Returns {"overlaps": [...], "struck": [...],
    "text_faults": [...], "texts": n}.
    """
    from matplotlib.text import Text

    import mintfig as mint

    exp = mint.load(str(png))
    out: dict = {"overlaps": [], "struck": [], "text_faults": [], "texts": 0}
    with exp.theme.rc_context(exp.spec):
        fig = exp.fig
        drawn: list = []
        original = Text.draw

        def _recording_draw(self, renderer):  # only texts matplotlib actually draws
            if self.get_visible() and self.get_text().strip() and self.get_alpha() != 0:
                drawn.append(self)
            return original(self, renderer)

        Text.draw = _recording_draw
        try:
            fig.canvas.draw()
        finally:
            Text.draw = original
        renderer = fig.canvas.get_renderer()
        texts = list(dict.fromkeys(drawn))
        out["texts"] = len(texts)
        boxes = [(t, t.get_window_extent(renderer).expanded(1.0, 1.0)) for t in texts]
        shrunk = []
        for t, b in boxes:
            pad = 1.5
            if b.width > 2 * pad and b.height > 2 * pad:
                b = b.from_extents(b.x0 + pad, b.y0 + pad, b.x1 - pad, b.y1 - pad)
            shrunk.append((t, b))
        for i, (ti, bi) in enumerate(shrunk):
            for tj, bj in shrunk[i + 1:]:
                if bi.overlaps(bj):
                    out["overlaps"].append(f"{ti.get_text()!r} / {tj.get_text()!r}")
        grid = {id(g) for ax in fig.axes for g in (*ax.get_xgridlines(), *ax.get_ygridlines())}
        lines = [
            ln for ax in fig.axes for ln in ax.lines
            if id(ln) not in grid and ln.get_visible() and len(ln.get_xdata()) >= 2
            and ln.get_linestyle() not in ("None", "", " ") and ln.get_linewidth() > 0
        ]
        for ln in lines:
            path = ln.get_transform().transform_path(ln.get_path())
            dashed = ln.get_linestyle() not in ("-", "solid")
            for t, b in shrunk:
                if t.axes is not None and t.axes is not ln.axes:
                    continue
                if path.intersects_bbox(b, filled=False):
                    what = "dashed reference line" if dashed else "data line"
                    out["struck"].append(f"{t.get_text()!r} crossed by a {what}")
        for t in texts:
            txt = t.get_text()
            plain = re.sub(r"\$[^$]*\$", "", txt)
            if "%%" in plain:
                out["text_faults"].append(f"doubled %: {txt!r}")
            m = _DOUBLED.search(plain)
            if m and not m.group(1).isdigit():
                out["text_faults"].append(f"repeated words {m.group(0)!r}: {txt!r}")
            if _ASCII_MINUS.search(plain) and not re.search(r"\d{4}-\d{2}", plain):
                out["text_faults"].append(f"ASCII hyphen as minus sign: {txt!r}")
            if _JUNK.search(plain):
                out["text_faults"].append(f"junk value: {txt!r}")
    return out


def run_checks(work: Path, calls: list[dict], returncode: int, stderr: str) -> list[dict]:
    """Every automated check, in order. Each: {name, passed, detail}."""
    checks: list[dict] = []

    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    png = work / "figure.png"
    tail = stderr.strip().splitlines()[-1] if stderr.strip() else ""
    add("script_runs", returncode == 0, "" if returncode == 0 else f"exit {returncode}: {tail}")
    add("one_figure_saved", len(calls) == 1 and png.exists(),
        f"{len(calls)} mint.explain save call(s); figure.png {'found' if png.exists() else 'missing'}")
    if not calls or not png.exists():
        return checks
    s = calls[-1]
    issues = s.get("issues", [])
    errors = [i for i in issues if i.get("severity") == "error"]
    add("no_errors", s.get("ok") is True and not errors,
        "; ".join(f"{i['rule']}: {i['message']}" for i in errors))
    add("no_warnings", not issues, "; ".join(f"{i['rule']}" for i in issues))
    display = s.get("display", {})
    min_px = display.get("min_text_px")
    add("text_legible", isinstance(min_px, (int, float)) and min_px >= MIN_TEXT_PX,
        f"smallest text {min_px} px at chat width (floor {MIN_TEXT_PX})")
    add("chat_width", display.get("width_px") == CHAT_WIDTH_PX,
        f"display width {display.get('width_px')} px (expected {CHAT_WIDTH_PX})")
    takeaway = str(s.get("takeaway") or "")
    add("takeaway_has_number", bool(re.search(r"\d", takeaway)), takeaway)
    panels = s.get("panels", [])
    untitled = [p.get("key") for p in panels if not (p.get("title") or "").strip()]
    add("panels_titled", bool(panels) and not untitled,
        f"{len(panels)} panel(s)" + (f"; untitled: {untitled}" if untitled else ""))
    kinds = [p.get("kind") for p in panels]
    add("forms_only", "custom" not in kinds, f"forms: {kinds}")
    spec = _spec_of(png)
    add("spec_roundtrip", spec is not None, "mint.load(figure.png) rebuilds the spec")
    source = (spec or {}).get("source") or ""
    add("source_given", bool(str(source).strip()), str(source))
    add("alt_text", bool(str(s.get("alt_text") or "").strip()), "")
    if spec is not None:
        try:
            audit = audit_layout(png)
        except Exception as exc:  # noqa: BLE001
            add("layout_audit_ran", False, f"{type(exc).__name__}: {exc}")
            return checks
        add("no_text_overlap", not audit["overlaps"], "; ".join(audit["overlaps"][:4]))
        add("no_text_struck_by_lines", not audit["struck"], "; ".join(audit["struck"][:4]))
        add("text_well_formed", not audit["text_faults"], "; ".join(audit["text_faults"][:4]))
    return checks


# --------------------------------------------------------------------------- #
# answer key (grade only)
# --------------------------------------------------------------------------- #

_SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")


def numbers_in(text: str) -> list[float]:
    """Numbers as a reader sees them: 1,200 / 0.58 / 46% / 1.3×10⁻⁷ / 2e-5 / −3."""
    text = text.replace("\N{MINUS SIGN}", "-").replace("\N{EN DASH}", " ")
    out: list[float] = []
    sci = re.compile(r"(\d+(?:\.\d+)?)\s*[×x]\s*10([⁻⁺]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+|\^?[-+]?\d+)")
    for m in sci.finditer(text):
        exp = m.group(2).translate(_SUP).lstrip("^")
        out.append(float(m.group(1)) * 10 ** int(exp))
    text = sci.sub(" ", text)
    for m in re.finditer(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?", text):
        try:
            out.append(float(m.group(0).replace(",", "")))
        except ValueError:
            continue
    return out


def answer_matches(takeaway: str, key: dict) -> tuple[bool, list[float]]:
    found = numbers_in(takeaway)
    for v in found:
        for target in key["accept"]:
            tol = max(key.get("abs_tol", 0.0), key.get("rel_tol", 0.0) * abs(target))
            for cand in (v, abs(v)):
                if math.isclose(cand, target, abs_tol=tol) or math.isclose(cand, abs(target), abs_tol=tol):
                    return True, found
    return False, found


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #


def cmd_list(_: argparse.Namespace) -> None:
    for t in _all_tasks():
        lines = (t / "context.md").read_text().split("**User:**")
        ask = " ".join(lines[1].split("**Assistant:**")[0].split()) if len(lines) > 1 else ""
        print(f"{t.name:18s} {ask[:96]}")


def cmd_start(a: argparse.Namespace) -> None:
    src = _task_dir(a.task)
    run = Path(a.run).resolve()
    work = _work(run, a.task)
    if work.exists():
        sys.exit(f"{work} already exists; use a new --run folder for a new run")
    work.mkdir(parents=True)
    shutil.copy(src / "context.md", work / "context.md")
    shutil.copytree(src / "data", work / "data")
    (work / ".bench").mkdir()
    state = {"task": a.task, "started": time.time(), "python": a.python, "attempts": []}
    _save_state(run, a.task, state)
    print(f"Task {a.task} started. Work folder: {work}\n")
    print(AGENT_RULES.format(skill=_skill_path(), python=a.python, bench=Path(__file__).resolve(),
                             task=a.task, run=run, max_attempts=MAX_ATTEMPTS))


def cmd_submit(a: argparse.Namespace) -> None:
    run = Path(a.run).resolve()
    state = _load_state(run, a.task)
    work = _work(run, a.task)
    if any(x["passed"] for x in state["attempts"]):
        sys.exit("this task already passed; further submissions are not counted")
    if len(state["attempts"]) >= MAX_ATTEMPTS:
        sys.exit(f"no submissions left ({MAX_ATTEMPTS} used)")
    script = Path(a.script).resolve()
    if not script.exists():
        sys.exit(f"{script} not found")
    n = len(state["attempts"]) + 1
    local = _local_images(work, state)
    state.setdefault("local_renders", [])
    state["local_renders"] += [x for x in local if x not in state["local_renders"]]
    kept = work / ".bench" / f"attempt{n}.py"
    shutil.copy(script, kept)
    for stale in ("figure.png", "figure.json"):
        (work / stale).unlink(missing_ok=True)
    capture = work / ".bench" / "capture.py"
    capture.write_text(_CAPTURE)
    calls_path = work / ".bench" / f"attempt{n}_summary.json"
    t0 = time.time()
    try:
        proc = subprocess.run(
            [state["python"], str(capture), str(kept), str(calls_path)],
            cwd=work, capture_output=True, text=True, timeout=TIMEOUT_S, check=False,
            env={**__import__("os").environ, "MPLCONFIGDIR": "/tmp/mpl-figbench"},
        )
        rc, err, out = proc.returncode, proc.stderr, proc.stdout
    except subprocess.TimeoutExpired:
        rc, err, out = -1, f"timed out after {TIMEOUT_S} s", ""
    render_s = time.time() - t0
    calls = json.loads(calls_path.read_text()) if calls_path.exists() else []
    checks = run_checks(work, calls, rc, err)
    passed = all(c["passed"] for c in checks)
    if (work / "figure.png").exists():
        shutil.copy(work / "figure.png", work / ".bench" / f"attempt{n}.png")
    attempt = {"n": n, "submitted": t0, "finished": time.time(), "render_s": round(render_s, 2),
               "passed": passed, "checks": checks}
    state["produced"] = [
        f"{f.relative_to(work)}:{f.stat().st_mtime_ns}"
        for f in work.rglob("*")
        if f.suffix.lower() in _IMAGE_SUFFIXES and f.relative_to(work).parts[0] not in ("data", ".bench")
    ]
    state["attempts"].append(attempt)
    _save_state(run, a.task, state)

    if out.strip():
        print("--- your script's stdout (last 20 lines) ---")
        print("\n".join(out.strip().splitlines()[-20:]))
    if calls:
        s = calls[-1]
        print("--- mintfig summary ---")
        print(json.dumps({k: s.get(k) for k in ("ok", "issues", "display")}, indent=1,
                         ensure_ascii=False))
        for p in s.get("panels", []):
            print(f"panel {p.get('key')} ({p.get('kind')}): {p.get('title')}")
            for f in p.get("facts", []):
                print(f"   - {f}")
    print(f"--- checks (attempt {n} of {MAX_ATTEMPTS}) ---")
    for c in checks:
        print(f"[{'PASS' if c['passed'] else 'FAIL'}] {c['name']}" + (f": {c['detail']}" if c["detail"] else ""))
    elapsed = attempt["finished"] - state["started"]
    if passed:
        print(f"\nPASSED in {elapsed:.0f} s from start. Task complete; stop here.")
    elif n < MAX_ATTEMPTS:
        print(f"\nNot passed. {MAX_ATTEMPTS - n} submission(s) left.")
    else:
        print("\nNot passed and no submissions left. Task over.")


def cmd_grade(a: argparse.Namespace) -> None:
    run = Path(a.run).resolve()
    answers = json.loads(ANSWERS.read_text())
    rows = []
    for work in sorted(p for p in run.iterdir() if (p / ".bench" / "state.json").exists()):
        state = json.loads((work / ".bench" / "state.json").read_text())
        att = state["attempts"]
        last = att[-1] if att else None
        passed = bool(last and last["passed"])
        t_pass = (last["finished"] - state["started"]) if passed else None
        t_last = (last["finished"] - state["started"]) if last else None
        takeaway, correct = "", None
        summ = work / ".bench" / f"attempt{last['n']}_summary.json" if last else None
        if summ and summ.exists():
            calls = json.loads(summ.read_text())
            if calls:
                takeaway = calls[-1].get("takeaway", "")
        if state["task"] in answers and takeaway:
            correct, _found = answer_matches(takeaway, answers[state["task"]])
        failed = [c["name"] for c in (last["checks"] if last else []) if not c["passed"]]
        local_n = len(state.get("local_renders", [])) + len(_local_images(work, state))
        rows.append({"task": state["task"], "passed": passed, "attempts": len(att),
                     "local_renders": local_n,
                     "seconds_to_pass": round(t_pass, 1) if t_pass is not None else None,
                     "seconds_total": round(t_last, 1) if t_last is not None else None,
                     "render_s": [x["render_s"] for x in att], "failed_checks": failed,
                     "answer_correct": correct, "answer_expected": answers.get(state["task"], {}).get("what"),
                     "takeaway": takeaway})
    def _split(rs: list[dict]) -> dict:
        ts = [r["seconds_to_pass"] for r in rs if r["seconds_to_pass"] is not None]
        return {"tasks": len(rs), "passed": sum(r["passed"] for r in rs),
                "passed_first_try": sum(1 for r in rs if r["passed"] and r["attempts"] == 1),
                "answers_correct": sum(1 for r in rs if r["answer_correct"]),
                "median_seconds_to_pass": round(statistics.median(ts), 1) if ts else None}

    core = [r for r in rows if not r["task"].startswith("h")]
    held = [r for r in rows if r["task"].startswith("h")]
    times = [r["seconds_to_pass"] for r in rows if r["seconds_to_pass"] is not None]
    first_try = sum(1 for r in rows if r["passed"] and r["attempts"] == 1)
    summary = {
        "run": str(run), "tasks": len(rows), "passed": sum(r["passed"] for r in rows),
        "passed_first_try": first_try,
        "local_renders": sum(r["local_renders"] for r in rows),
        "answers_correct": sum(1 for r in rows if r["answer_correct"]),
        "median_seconds_to_pass": round(statistics.median(times), 1) if times else None,
        "total_seconds_to_pass": round(sum(times), 1) if times else None,
        "core": _split(core),
        "heldout": _split(held) if held else None,
        "tasks_detail": rows,
    }
    (run / "results.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    lines = [
        f"# figure-bench results: {run.name}", "",
        (f"- Passed: **{summary['passed']} / {summary['tasks']}** "
         f"({first_try} on the first submission); renders outside submit: {summary['local_renders']}"),
        f"- Takeaway number matches the answer key: {summary['answers_correct']} / {summary['tasks']}",
        (f"- Time to pass: median {summary['median_seconds_to_pass']} s, "
         f"total {summary['total_seconds_to_pass']} s"),
        *([f"- Core tasks: {summary['core']}", f"- Held-out tasks: {summary['heldout']}"]
          if held else []), "",
        "| Task | Pass | Attempts | Local renders | Time to pass (s) | Answer | Failed checks | Takeaway |",
        "| :--- | :---: | :---: | :---: | ---: | :---: | :--- | :--- |",
    ]
    for r in rows:
        ans = "—" if r["answer_correct"] is None else ("yes" if r["answer_correct"] else "no")
        lines.append(
            f"| {r['task']} | {'yes' if r['passed'] else 'no'} | {r['attempts']} | {r['local_renders']} | "
            f"{r['seconds_to_pass'] if r['seconds_to_pass'] is not None else '—'} | {ans} | "
            f"{', '.join(r['failed_checks']) or '—'} | {r['takeaway'].replace('|', '/')} |"
        )
    (run / "results.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def cmd_recheck(a: argparse.Namespace) -> None:
    """Re-run today's checks on each task's last submitted figure (no re-execution)."""
    run = Path(a.run).resolve()
    for work in sorted(p for p in run.iterdir() if (p / ".bench" / "state.json").exists()):
        state = json.loads((work / ".bench" / "state.json").read_text())
        if not state["attempts"]:
            continue
        n = state["attempts"][-1]["n"]
        calls = json.loads((work / ".bench" / f"attempt{n}_summary.json").read_text())
        png = work / ".bench" / f"attempt{n}.png"
        tmp = work / ".bench" / "recheck"
        tmp.mkdir(exist_ok=True)
        if png.exists():
            shutil.copy(png, tmp / "figure.png")
        failed = [c for c in run_checks(tmp, calls, 0, "") if not c["passed"]]
        print(f"{state['task']:18s} " + ("all checks pass" if not failed else
              "; ".join(f"{c['name']}: {c['detail']}" for c in failed)))


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    s = sub.add_parser("start")
    s.add_argument("task")
    s.add_argument("--run", required=True)
    s.add_argument("--python", default=sys.executable)
    s.set_defaults(fn=cmd_start)
    s = sub.add_parser("submit")
    s.add_argument("task")
    s.add_argument("script")
    s.add_argument("--run", required=True)
    s.set_defaults(fn=cmd_submit)
    s = sub.add_parser("recheck")
    s.add_argument("--run", required=True)
    s.set_defaults(fn=cmd_recheck)
    s = sub.add_parser("grade")
    s.add_argument("--run", required=True)
    s.set_defaults(fn=cmd_grade)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
