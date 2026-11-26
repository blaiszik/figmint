"""figure-bench: can an agent turn a conversation and a dataset into a clean chat figure, fast?

Each task is a mock agent thread (tasks/NN_name/context.md) plus data
(tasks/NN_name/data/). The agent under test sees only its work folder and
mintfig's SKILL.md, writes a script that calls ``mint.explain(...).save(...)``,
and submits it. Grading is on time and on mintfig's own automated checks.

    python bench.py list
    python bench.py start  01_ablation --run runs/r1     # copies the task, starts the clock
    python bench.py submit 01_ablation --run runs/r1 figure.py --reply reply.md   # renders + checks (max 3)
    python bench.py grade  --run runs/r1                  # results.json + results.md

The clock runs from ``start`` to the end of the first passing ``submit`` (so it
includes the agent's reading and thinking). A task passes when its last
submission passes every check. ``grade`` also scores the takeaway's number
against a hidden answer key; ``submit`` never reveals that score.

``--reply`` hands in the reply the agent would send the person. The delivery check
(``reply_delivers_figure``) passes when the reply carries the figure (its
``deliver.markdown`` image, or its ``deliver.text`` in a fenced block) with at most
60 words of prose outside the image line and code fences. It is reported beside the
figure checks and does not gate the pass; without ``--reply`` it reads "not provided".

``start --arm matplotlib`` runs the same task as a baseline: the agent gets no
SKILL.md, writes plain Matplotlib (numpy and pandas allowed, mintfig not), and
passes on the arm-neutral defect checks only. Every submission in both arms is
also measured by the same neutral audit (``neutral.py``) on the Figure as it was
saved, so ``compare`` can put the two arms side by side.

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
if str(HERE) not in sys.path:  # neutral.py sits beside this file
    sys.path.insert(0, str(HERE))
TASKS = HERE / "tasks"
HELDOUT = HERE / "heldout"  # held-out tasks: never used to tune mintfig or SKILL.md
ANSWERS = HERE / "answers.json"
MAX_ATTEMPTS = 3
TIMEOUT_S = 120
MIN_TEXT_PX = 11.0  # mintfig's floor at the 700 px chat width
CHAT_WIDTH_PX = 700
NARROW_WIDTH_PX = 450  # width="narrow": phones and IDE sidebars
REPLY_MAX_WORDS = 60  # prose around the figure in the reply: one sentence and one caption
DELIVERY_CHECK = "reply_delivers_figure"

_CAPTURE = r"""
import json, os, runpy, sys
from pathlib import Path
script, summary_out, audit_out, arm, bench_dir = sys.argv[1:6]
sys.path.insert(0, bench_dir)
import matplotlib
matplotlib.use("Agg")
import matplotlib as mpl
from matplotlib.figure import Figure
import neutral
target = Path("figure.png").resolve()
calls, audits = [], []
_savefig = Figure.savefig
def _hooked_savefig(self, fname, *a, **k):
    result = _savefig(self, fname, *a, **k)
    try:
        hit = isinstance(fname, (str, os.PathLike)) and Path(fname).resolve() == target
    except OSError:
        hit = False
    if hit:
        try:
            dpi = k.get("dpi") or mpl.rcParams["savefig.dpi"]
            dpi = self.dpi if dpi == "figure" else float(dpi)
            tight = (k.get("bbox_inches") or mpl.rcParams["savefig.bbox"]) == "tight"
            audits.append(neutral.audit_saved_figure(self, target, dpi=dpi, tight=tight))
        except Exception as exc:
            audits.append({"error": f"{type(exc).__name__}: {exc}"})
    return result
Figure.savefig = _hooked_savefig
if arm == "mintfig":
    import mintfig.explainer as ex
    _save = ex.Explanation.save
    def _capturing_save(self, *a, **k):
        summary = _save(self, *a, **k)
        calls.append(json.loads(json.dumps(summary, default=str)))
        return summary
    ex.Explanation.save = _capturing_save
try:
    runpy.run_path(script, run_name="__main__")
finally:
    with open(summary_out, "w") as fh:
        json.dump(calls, fh, ensure_ascii=False)
    with open(audit_out, "w") as fh:
        json.dump({"audits": audits, "mintfig_imported": "mintfig" in sys.modules}, fh,
                  ensure_ascii=False, default=str)
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
- Write the reply you would send the person as a Markdown file and hand it in with
  each submit. It must show the figure: the image line ![<takeaway>](figure.png)
  (submit prints it as deliver.markdown), or deliver.text in a ``` block where images
  do not render. At most {max_words} words of prose outside the image line and code
  blocks: one sentence, the figure, one caption.
- Submit with:  {python} {bench} submit {task} --run {run} <your_script.py> --reply <your_reply.md>
  Submit runs a copy of your script with this folder as the working directory, so
  open data with paths like "data/x.csv", not paths built from __file__.
  Each submit renders your script and reports mintfig's summary, its facts and
  the checks (mintfig's own checks plus an independent layout audit), then the
  delivery check on your reply.
  You have {max_attempts} submissions; stop at the first one that passes.
- The clock started now and stops when a submission passes.
"""

AGENT_RULES_MATPLOTLIB = """\
Rules for this task:
- Read context.md and the files in data/ in this folder.
  Do not read anything else in the repository.
- Answer the last request in the thread with ONE figure made with Matplotlib
  (numpy and pandas are available; do not use mintfig). Your script must save it
  as figure.png in this folder. The person sees it in a chat app that shows
  images at most {display_px} px wide.
- Do not render figures yourself (no savefig runs of your own): submit is your
  renderer. Images found in this folder that submit did not make are counted as
  local renders. Plain data analysis (numpy/pandas) is fine.
- Write the reply you would send the person as a Markdown file and hand it in with
  each submit. It must show the figure with the image line ![<one-line summary>](figure.png).
  At most {max_words} words of prose outside the image line and code blocks:
  one sentence, the figure, one caption.
- Submit with:  {python} {bench} submit {task} --run {run} <your_script.py> --reply <your_reply.md>
  Submit runs a copy of your script with this folder as the working directory, so
  open data with paths like "data/x.csv", not paths built from __file__.
  Each submit runs your script and checks the saved figure: the smallest text is
  at least {min_px:g} px as displayed at {display_px} px wide, no two texts overlap,
  no text is crossed by a line, no text runs past the canvas edge, and no text is
  malformed ("%%", repeated words, "nan"/"None", an ASCII hyphen as a minus sign).
  Then it runs the delivery check on your reply.
  You have {max_attempts} submissions; stop at the first one that passes.
- The clock started now and stops when a submission passes.
"""

AGENT_RULES_MATPLOTLIB_PLAIN = """\
Rules for this task:
- Read context.md and the files in data/ in this folder.
  Do not read anything else in the repository.
- Answer the last request in the thread with ONE figure made with Matplotlib
  (numpy and pandas are available; do not use mintfig). Your script must save it
  as figure.png in this folder.
- Do not render figures yourself (no savefig runs of your own): submit is your
  renderer. Plain data analysis (numpy/pandas) is fine.
- Write the reply you would send the person as a Markdown file and hand it in with
  your submit. It must show the figure with the image line ![<one-line summary>](figure.png).
  At most {max_words} words of prose outside the image line and code blocks:
  one sentence, the figure, one caption.
- Submit with:  {python} {bench} submit {task} --run {run} <your_script.py> --reply <your_reply.md>
  Submit runs a copy of your script with this folder as the working directory, so
  open data with paths like "data/x.csv", not paths built from __file__.
  Submit runs your script and tells you whether it ran and saved figure.png. If it
  did, the task is over. If not, fix the error and submit again ({max_attempts} at most).
- The clock started now and stops when a submission saves the figure.
"""

ARMS = ("mintfig", "matplotlib", "matplotlib-plain")
_PLAIN_SHOWN = ("script_runs", "one_figure_saved", "no_mintfig")

# One question per task for blind readers, who see only the figure. Scored with the
# task's answer key (answers.json), like the takeaway.
READER_QUESTIONS = {
    "01_ablation": "How many points of accuracy does the model lose when the reranker is removed?",
    "02_ab_latency": "By how much did the new checkout flow change median latency (in ms or %)?",
    "03_dose_response": "What is the IC50 (the concentration giving 50% inhibition) of the most potent compound, in nM?",
    "04_battery_fade": "At about which cycle number does the baseline electrolyte reach 80% capacity retention?",
    "05_retrofit": "By what percentage did the Lab annex's daily electricity use fall after the retrofit?",
    "06_energy_mix": "What share of generation is renewable when only wind, solar and hydro count (biomass excluded), in %?",
    "07_gene_change": "What is the fold change of CDKN1A, or the typical fold change of the p53 target genes?",
    "08_hall_petch": "What is the Hall–Petch slope for the Cu-Zn alloy, in MPa·µm½?",
    "09_eval_matrix": "What is the new checkpoint's accuracy on Swahili math, in %?",
    "10_incident": "What was the peak error rate of the payments service?",
    "h1_survey": "What share of Support staff are satisfied or very satisfied, in %?",
    "h2_spectra": "By how many nm does the 400 °C sample's absorption peak shift relative to the unannealed sample?",
    "h3_wait_times": "At triage level 3, how many minutes longer is the median wait at South than at North?",
    "h4_scaling": "What is the mixture-of-experts scaling exponent (the log–log slope of loss against compute)?",
    "h5_budget": "By what percentage is the Libraries department's budget cut?",
}
# Tasks whose data carries seed, replicate or sampling error the figure should name.
UNCERTAINTY_TASKS = {"01_ablation", "03_dose_response", "07_gene_change", "h1_survey"}

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
    add("chat_width", display.get("width_px") in (CHAT_WIDTH_PX, NARROW_WIDTH_PX),
        f"display width {display.get('width_px')} px (expected {CHAT_WIDTH_PX}, or "
        f"{NARROW_WIDTH_PX} for phones)")
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


def run_checks_matplotlib(work: Path, meta: dict, returncode: int, stderr: str) -> list[dict]:
    """The Matplotlib arm's gate: the script runs, saves figure.png without mintfig, and
    the saved figure passes the arm-neutral defect checks."""
    import neutral

    checks: list[dict] = []
    png = work / "figure.png"
    tail = stderr.strip().splitlines()[-1] if stderr.strip() else ""
    audits = [x for x in meta.get("audits", []) if "error" not in x]
    checks.append({"name": "script_runs", "passed": returncode == 0,
                   "detail": "" if returncode == 0 else f"exit {returncode}: {tail}"})
    checks.append({"name": "one_figure_saved", "passed": bool(audits) and png.exists(),
                   "detail": f"{len(meta.get('audits', []))} save(s) to figure.png; "
                             f"figure.png {'found' if png.exists() else 'missing'}"})
    checks.append({"name": "no_mintfig", "passed": not meta.get("mintfig_imported"),
                   "detail": "mintfig was imported" if meta.get("mintfig_imported") else ""})
    if audits and png.exists():
        checks += neutral.neutral_checks(audits[-1])
    return checks


def reply_prose(reply: str) -> str:
    """The reply's prose: no code fences and no image lines."""
    outside = _FENCE.sub("", reply)
    return "\n".join(ln for ln in outside.splitlines() if not _IMAGE.search(ln))


_FENCE = re.compile(r"^ {0,3}(```|~~~)[^\n]*\n(.*?)^ {0,3}\1[ \t]*$", re.MULTILINE | re.DOTALL)
_IMAGE = re.compile(r"!\[(?:[^\]\\]|\\.)*\]\(\s*(<[^>]*>|[^)\s]+)[^)]*\)")
_WORD = re.compile(r"[^\W_]+(?:['\u2019.,\-][^\W_]+)*")


def _image_target(target: str) -> str:
    target = target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    return target.removeprefix("./")


def _plain_lines(text: str) -> list[str]:
    lines = [ln.rstrip() for ln in text.strip("\n").splitlines()]
    return [ln for ln in lines if ln.strip()]


def check_reply(reply: str | None, summary: dict, work: Path | None = None) -> dict:
    """The delivery check on the agent's final reply.

    Passes when the reply shows the figure (an image whose target is the one in
    ``summary["deliver"]["markdown"]``, or ``deliver.text`` inside a fenced block) and
    has at most ``REPLY_MAX_WORDS`` words of prose outside image lines and code fences.
    ``reply=None`` (no ``--reply``) gives status "not provided", which is not a failure.
    Returns {name, status: "pass" | "fail" | "not provided", passed, detail}.
    """
    if reply is None:
        return {"name": DELIVERY_CHECK, "status": "not provided", "passed": None, "detail": ""}
    deliver = summary.get("deliver") or {}
    blocks = [m.group(2) for m in _FENCE.finditer(reply)]
    outside = _FENCE.sub("", reply)
    images = [_image_target(m.group(1)) for m in _IMAGE.finditer(outside)]
    prose = "\n".join(ln for ln in outside.splitlines() if not _IMAGE.search(ln))
    words = len(_WORD.findall(prose))

    shown = ""
    md = deliver.get("markdown")
    expected = _IMAGE.search(md) if md else None
    if expected is not None:
        want = _image_target(expected.group(1))
        for got in images:
            same = got == want or (
                work is not None and (work / got).resolve() == (work / want).resolve()
            )
            if same:
                shown = f"image {want}"
                break
    text = deliver.get("text")
    if not shown and text:
        want_lines = _plain_lines(text)
        for block in blocks:
            got_lines = _plain_lines(block)
            n = len(want_lines)
            if any(got_lines[i:i + n] == want_lines for i in range(len(got_lines) - n + 1)):
                shown = "deliver.text in a code block"
                break
    problems = []
    if not shown:
        target = _image_target(expected.group(1)) if expected is not None else "the figure"
        problems.append(f"no ![...]({target}) image and no code block with deliver.text")
    if words > REPLY_MAX_WORDS:
        problems.append(f"{words} words of prose (max {REPLY_MAX_WORDS})")
    detail = "; ".join(problems) if problems else f"{shown}; {words} words of prose"
    passed = not problems
    return {"name": DELIVERY_CHECK, "status": "pass" if passed else "fail", "passed": passed,
            "detail": detail}


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
    state = {"task": a.task, "arm": a.arm, "started": time.time(), "python": a.python,
             "attempts": []}
    _save_state(run, a.task, state)
    print(f"Task {a.task} started. Work folder: {work}\n")
    rules = {"matplotlib": AGENT_RULES_MATPLOTLIB, "matplotlib-plain": AGENT_RULES_MATPLOTLIB_PLAIN}.get(
        a.arm, AGENT_RULES)
    print(rules.format(skill=_skill_path(), python=a.python, bench=Path(__file__).resolve(),
                       task=a.task, run=run, max_attempts=MAX_ATTEMPTS,
                       max_words=REPLY_MAX_WORDS, display_px=CHAT_WIDTH_PX,
                       min_px=MIN_TEXT_PX))


def cmd_submit(a: argparse.Namespace) -> None:
    run = Path(a.run).resolve()
    state = _load_state(run, a.task)
    work = _work(run, a.task)
    if any(x.get("done", x["passed"]) for x in state["attempts"]):
        sys.exit("this task is complete; further submissions are not counted")
    if len(state["attempts"]) >= MAX_ATTEMPTS:
        sys.exit(f"no submissions left ({MAX_ATTEMPTS} used)")
    script = Path(a.script).resolve()
    if not script.exists():
        sys.exit(f"{script} not found")
    reply_path = Path(a.reply).resolve() if a.reply else None
    if reply_path is not None and not reply_path.exists():
        sys.exit(f"{reply_path} not found")
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
    audit_path = work / ".bench" / f"attempt{n}_audit.json"
    arm = state.get("arm", "mintfig")
    t0 = time.time()
    try:
        proc = subprocess.run(
            [state["python"], str(capture), str(kept), str(calls_path), str(audit_path), arm,
             str(HERE)],
            cwd=work, capture_output=True, text=True, timeout=TIMEOUT_S, check=False,
            env={**__import__("os").environ, "MPLCONFIGDIR": "/tmp/mpl-figbench"},
        )
        rc, err, out = proc.returncode, proc.stderr, proc.stdout
    except subprocess.TimeoutExpired:
        rc, err, out = -1, f"timed out after {TIMEOUT_S} s", ""
    render_s = time.time() - t0
    calls = json.loads(calls_path.read_text()) if calls_path.exists() else []
    meta = json.loads(audit_path.read_text()) if audit_path.exists() else {}
    audits = [x for x in meta.get("audits", []) if "error" not in x]
    audit = audits[-1] if audits else None
    if arm in ("matplotlib", "matplotlib-plain"):
        checks = run_checks_matplotlib(work, meta, rc, err)
    else:
        checks = run_checks(work, calls, rc, err)
    passed = all(c["passed"] for c in checks)
    # The uninstructed arm gets no defect feedback: it is done once the figure is saved.
    shown = [c for c in checks if c["name"] in _PLAIN_SHOWN] if arm == "matplotlib-plain" else checks
    done = all(c["passed"] for c in shown)
    reply = None
    if reply_path is not None:
        reply = reply_path.read_text(encoding="utf-8")
        (work / ".bench" / f"attempt{n}_reply.md").write_text(reply, encoding="utf-8")
    if arm in ("matplotlib", "matplotlib-plain"):
        reply_summary = {"deliver": {"markdown": "![figure](figure.png)"}}
    else:
        reply_summary = calls[-1] if calls else {}
    delivery = check_reply(reply, reply_summary, work)
    if (work / "figure.png").exists():
        shutil.copy(work / "figure.png", work / ".bench" / f"attempt{n}.png")
    attempt = {"n": n, "submitted": t0, "finished": time.time(), "render_s": round(render_s, 2),
               "passed": passed, "done": done, "checks": checks, "delivery": delivery,
               "audit": audit, "audit_errors": [x["error"] for x in meta.get("audits", []) if "error" in x]}
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
        deliver = s.get("deliver") or {}
        for key in ("markdown", "caption"):
            if deliver.get(key):
                print(f"deliver.{key}: {deliver[key]}")
        for p in s.get("panels", []):
            print(f"panel {p.get('key')} ({p.get('kind')}): {p.get('title')}")
            for f in p.get("facts", []):
                print(f"   - {f}")
    print(f"--- checks (attempt {n} of {MAX_ATTEMPTS}) ---")
    for c in shown:
        print(f"[{'PASS' if c['passed'] else 'FAIL'}] {c['name']}" + (f": {c['detail']}" if c["detail"] else ""))
    print("--- delivery (reported beside the checks; does not decide the pass) ---")
    mark = {"pass": "PASS", "fail": "FAIL"}.get(delivery["status"], "----")
    print(f"[{mark}] {delivery['name']}: " + (delivery["detail"] or delivery["status"]))
    elapsed = attempt["finished"] - state["started"]
    if arm == "matplotlib-plain" and done:
        print(f"\nSubmitted in {elapsed:.0f} s from start. Task complete; stop here.")
    elif passed:
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
        arm = state.get("arm", "mintfig")
        key = answers.get(state["task"])
        neutral_rows = {}
        for label, att_i in (("first", att[0] if att else None), ("final", last)):
            neutral_rows[label] = _neutral_row(work, state["task"], att_i, key)
        if arm in ("matplotlib", "matplotlib-plain"):
            heads = (neutral_rows["final"] or {}).get("headlines") or []
            takeaway = heads[0] if heads else ""
            correct = (neutral_rows["final"] or {}).get("headline_correct")
        local_n = len(state.get("local_renders", [])) + len(_local_images(work, state))
        delivery = (last or {}).get("delivery") or check_reply(None, {})  # runs before --reply
        rows.append({"task": state["task"], "arm": arm, "passed": passed, "attempts": len(att),
                     "neutral": neutral_rows,
                     "local_renders": local_n,
                     "delivery": delivery["status"], "delivery_detail": delivery["detail"],
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
                "replies_deliver": sum(1 for r in rs if r["delivery"] == "pass"),
                "median_seconds_to_pass": round(statistics.median(ts), 1) if ts else None}

    core = [r for r in rows if not r["task"].startswith("h")]
    held = [r for r in rows if r["task"].startswith("h")]
    times = [r["seconds_to_pass"] for r in rows if r["seconds_to_pass"] is not None]
    first_try = sum(1 for r in rows if r["passed"] and r["attempts"] == 1)
    arms = sorted({r["arm"] for r in rows})
    summary = {
        "run": str(run), "arm": arms[0] if len(arms) == 1 else arms, "tasks": len(rows),
        "neutral": {"first": _neutral_totals(rows, "first"), "final": _neutral_totals(rows, "final")}, "passed": sum(r["passed"] for r in rows),
        "passed_first_try": first_try,
        "local_renders": sum(r["local_renders"] for r in rows),
        "answers_correct": sum(1 for r in rows if r["answer_correct"]),
        "replies_provided": sum(1 for r in rows if r["delivery"] != "not provided"),
        "replies_deliver": sum(1 for r in rows if r["delivery"] == "pass"),
        "median_seconds_to_pass": round(statistics.median(times), 1) if times else None,
        "total_seconds_to_pass": round(sum(times), 1) if times else None,
        "core": _split(core),
        "heldout": _split(held) if held else None,
        "tasks_detail": rows,
    }
    (run / "results.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    lines = [
        f"# figure-bench results: {run.name} ({summary['arm']} arm)", "",
        (f"- Passed: **{summary['passed']} / {summary['tasks']}** "
         f"({first_try} on the first submission); renders outside submit: {summary['local_renders']}"),
        f"- Takeaway number matches the answer key: {summary['answers_correct']} / {summary['tasks']}",
        (f"- Reply delivers the figure (<= {REPLY_MAX_WORDS} words of prose): "
         f"{summary['replies_deliver']} / {summary['replies_provided']} replies "
         f"({summary['tasks'] - summary['replies_provided']} not provided)"),
        (f"- Time to pass: median {summary['median_seconds_to_pass']} s, "
         f"total {summary['total_seconds_to_pass']} s"),
        *([f"- Core tasks: {summary['core']}", f"- Held-out tasks: {summary['heldout']}"]
          if held else []),
        f"- Neutral audit, first submission: {summary['neutral']['first']}",
        f"- Neutral audit, final submission: {summary['neutral']['final']}", "",
        "| Task | Pass | Attempts | Local renders | Time to pass (s) | Answer | Delivery | Failed checks | Takeaway |",
        "| :--- | :---: | :---: | :---: | ---: | :---: | :---: | :--- | :--- |",
    ]
    for r in rows:
        ans = "—" if r["answer_correct"] is None else ("yes" if r["answer_correct"] else "no")
        lines.append(
            f"| {r['task']} | {'yes' if r['passed'] else 'no'} | {r['attempts']} | {r['local_renders']} | "
            f"{r['seconds_to_pass'] if r['seconds_to_pass'] is not None else '—'} | {ans} | "
            f"{r['delivery']} | "
            f"{', '.join(r['failed_checks']) or '—'} | {r['takeaway'].replace('|', '/')} |"
        )
    (run / "results.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def cmd_recheck(a: argparse.Namespace) -> None:
    """Re-run today's checks on each task's last submitted figure (no re-execution)."""
    run = Path(a.run).resolve()
    for work in sorted(p for p in run.iterdir() if (p / ".bench" / "state.json").exists()):
        state = json.loads((work / ".bench" / "state.json").read_text())
        if not state["attempts"] or state.get("arm", "mintfig") != "mintfig":
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


def _neutral_row(work: Path, task: str, attempt: dict | None, key: dict | None) -> dict | None:
    """Arm-neutral measures of one submission: defects, claim accuracy, named uncertainty."""
    import neutral

    if attempt is None:
        return None
    audit = attempt.get("audit")
    checks = {c["name"]: c["passed"] for c in neutral.neutral_checks(audit)}
    heads = (audit or {}).get("headlines") or []
    head_text = " ".join(heads)
    reply_file = work / ".bench" / f"attempt{attempt['n']}_reply.md"
    reply = reply_file.read_text(encoding="utf-8") if reply_file.exists() else None
    row = {
        "saved": audit is not None,
        "clean": audit is not None and all(checks.values()),
        **{name: (passed if audit is not None else None) for name, passed in checks.items()},
        "min_text_px": (audit or {}).get("min_text_px"),
        "small_text_count": (audit or {}).get("small_text_count"),
        "headlines": heads,
        "headline_has_number": bool(re.search(r"\d", head_text)) if audit else None,
        "headline_correct": answer_matches(head_text, key)[0] if (key and head_text) else (False if audit else None),
        "reply_correct": answer_matches(reply_prose(reply), key)[0] if (key and reply) else None,
        "uncertainty_named": (audit or {}).get("uncertainty_named") if task in UNCERTAINTY_TASKS else None,
        "legends": (audit or {}).get("legends"),
        "panels": (audit or {}).get("panels"),
        "banned_colormaps": (audit or {}).get("banned_colormaps"),
    }
    return row


_NEUTRAL_RATES = ("saved", "clean", "text_legible", "no_text_overlap", "no_text_struck_by_lines",
                  "text_well_formed", "no_text_clipped", "headline_has_number", "headline_correct",
                  "reply_correct", "uncertainty_named")


def _neutral_totals(rows: list[dict], which: str) -> dict:
    """Counts of each neutral measure over the tasks where it applies, as "k/n"."""
    out: dict = {}
    entries = [r["neutral"][which] for r in rows if r.get("neutral", {}).get(which)]
    for name in _NEUTRAL_RATES:
        vals = [e[name] for e in entries if e.get(name) is not None]
        out[name] = f"{sum(bool(v) for v in vals)}/{len(vals)}"
    px = [e["min_text_px"] for e in entries if isinstance(e.get("min_text_px"), (int, float))]
    out["median_min_text_px"] = round(statistics.median(px), 1) if px else None
    out["with_legend"] = sum(1 for e in entries if (e.get("legends") or 0) > 0)
    return out


def cmd_compare(a: argparse.Namespace) -> None:
    """Side-by-side table of graded runs (one column per run), from each results.json."""
    labels = {
        "passed": "Passed the arm's gate", "passed_first_try": "Passed on the first submission",
        "median_seconds_to_pass": "Median seconds to pass",
        "answers_correct": "Takeaway/headline number matches the answer key (final)",
        "replies_deliver": "Reply delivers the figure",
        "saved": "Figure saved", "clean": "No layout or text defect (all five below)",
        "text_legible": "Smallest text >= 11 px at display width", "no_text_overlap": "No overlapping text",
        "no_text_struck_by_lines": "No text crossed by a line", "text_well_formed": "No malformed text",
        "no_text_clipped": "No text past the canvas edge",
        "headline_has_number": "Headline states a number",
        "headline_correct": "Headline number matches the answer key",
        "reply_correct": "Reply prose number matches the answer key",
        "uncertainty_named": "Uncertainty named (tasks with seeds, replicates or sampling)",
        "median_min_text_px": "Median smallest text (px)", "with_legend": "Figures with a legend",
    }
    results = []
    for run in a.runs:
        path = Path(run).resolve() / "results.json"
        if not path.exists():
            sys.exit(f"{path} not found; run `bench.py grade --run {run}` first")
        results.append(json.loads(path.read_text()))
    heads = [f"{Path(r['run']).name} ({r['arm']})" for r in results]
    lines = ["# figure-bench: arms compared", "",
             "Neutral rows are measured the same way in every arm, on the Figure as saved (`neutral.py`).", ""]
    for which in ("first", "final"):
        lines += [f"## {'First' if which == 'first' else 'Final'} submission", "",
                  "| Measure | " + " | ".join(heads) + " |", "| :--- |" + " ---: |" * len(heads)]
        for key in ("saved", "clean", "text_legible", "no_text_overlap", "no_text_struck_by_lines",
                    "text_well_formed", "no_text_clipped", "headline_has_number", "headline_correct",
                    "reply_correct", "uncertainty_named", "median_min_text_px", "with_legend"):
            vals = [str(r["neutral"][which].get(key)) for r in results]
            lines.append(f"| {labels[key]} | " + " | ".join(vals) + " |")
        lines.append("")
    reader_rows = []
    for r in results:
        rp = Path(r["run"]) / "readers.json"
        rows_r = json.loads(rp.read_text()) if rp.exists() else {}
        reader_rows.append(rows_r)
    if any(reader_rows):
        lines += ["## Blind readers (the figure alone, final submission)", "",
                  "| Measure | " + " | ".join(heads) + " |", "| :--- |" + " ---: |" * len(heads)]
        for label, field in (("Reader answers the task's question correctly", "correct"),
                             ("Reader says the answer is not shown", "not_shown")):
            vals = [f"{sum(x[field] for x in rr.values())}/{len(rr)}" if rr else "—" for rr in reader_rows]
            lines.append(f"| {label} | " + " | ".join(vals) + " |")
        lines.append("")
    lines += ["## Gate and time (each arm's own gate)", "",
              "| Measure | " + " | ".join(heads) + " |", "| :--- |" + " ---: |" * len(heads)]
    for key in ("passed", "passed_first_try", "median_seconds_to_pass", "replies_deliver"):
        vals = [f"{r[key]}/{r['tasks']}" if key in ("passed", "passed_first_try") else str(r[key])
                for r in results]
        lines.append(f"| {labels[key]} | " + " | ".join(vals) + " |")
    text = "\n".join(lines) + "\n"
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)


def _final_png(work: Path, state: dict) -> Path | None:
    att = state.get("attempts") or []
    if not att:
        return None
    png = work / ".bench" / f"attempt{att[-1]['n']}.png"
    return png if png.exists() else None


READER_RULES = """\
You are reading figures that other people were sent in a chat. Each folder below
holds one figure.png and one question.md. For each folder, look at the figure
(open the image) and answer its question from what the figure shows. Look at
the image only: do not inspect the file's bytes or metadata, compute anything
from other sources, or open anything outside this batch folder. If the figure
does not show the answer, say "not shown".

Write answers.json in this batch folder:
{{"<folder id>": {{"answer": "<number with unit, or not shown>",
                  "where": "<where in the figure you read it, a few words>"}}, ...}}

Folders: {ids}
"""


def strip_png_text(src: Path, dst: Path) -> None:
    """Copy a PNG without its text chunks (mintfig embeds the takeaway and alt text there)."""
    import struct


    data = src.read_bytes()
    out, pos = [data[:8]], 8
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        chunk = data[pos:pos + 12 + length]
        if kind not in (b"tEXt", b"iTXt", b"zTXt"):
            out.append(chunk)
        pos += 12 + length
    dst.write_bytes(b"".join(out))



def cmd_readers_prepare(a: argparse.Namespace) -> None:
    """Blind reader batches: each figure with its question, under a random id; no task twice per batch."""
    import random

    rng = random.Random(a.seed)
    out = Path(a.out).resolve()
    if out.exists():
        sys.exit(f"{out} already exists; use a new --out folder")
    items = []
    for run in a.runs:
        run = Path(run).resolve()
        for work in sorted(p for p in run.iterdir() if (p / ".bench" / "state.json").exists()):
            state = json.loads((work / ".bench" / "state.json").read_text())
            png = _final_png(work, state)
            if png is not None and state["task"] in READER_QUESTIONS:
                items.append({"run": str(run), "task": state["task"], "arm": state.get("arm", "mintfig"),
                              "png": str(png)})
    rng.shuffle(items)
    batches: list[list[dict]] = []
    for item in items:
        open_batches = [b for b in batches if len(b) < a.per_reader and all(x["task"] != item["task"] for x in b)]
        if open_batches:
            min(open_batches, key=len).append(item)
        else:
            batches.append([item])
    key = {}
    for k, batch in enumerate(batches, 1):
        bdir = out / f"batch_{k:02d}"
        ids = []
        for item in batch:
            fid = f"{rng.randrange(16**6):06x}"
            fdir = bdir / fid
            fdir.mkdir(parents=True)
            strip_png_text(Path(item["png"]), fdir / "figure.png")
            (fdir / "question.md").write_text(READER_QUESTIONS[item["task"]] + "\n", encoding="utf-8")
            key[fid] = {**item, "batch": bdir.name}
            ids.append(fid)
        (bdir / "README.md").write_text(READER_RULES.format(ids=", ".join(ids)), encoding="utf-8")
    (out / "key.json").write_text(json.dumps(key, indent=2) + "\n")
    print(f"{len(items)} figures in {len(batches)} batches under {out} (key.json maps ids; readers must not see it)")


def cmd_readers_score(a: argparse.Namespace) -> None:
    """Score every batch's answers.json against the answer key; write <run>/readers.json per run."""
    out = Path(a.set).resolve()
    key = json.loads((out / "key.json").read_text())
    answers_key = json.loads(ANSWERS.read_text())
    per_run: dict[str, dict] = {}
    missing = 0
    for fid, item in key.items():
        path = out / item["batch"] / "answers.json"
        got = json.loads(path.read_text()).get(fid) if path.exists() else None
        if got is None:
            missing += 1
            continue
        text = str(got.get("answer", "")) if isinstance(got, dict) else str(got)
        not_shown = "not shown" in text.lower()
        correct = (not not_shown) and answer_matches(text, answers_key[item["task"]])[0]
        per_run.setdefault(item["run"], {})[item["task"]] = {
            "answer": text, "where": got.get("where") if isinstance(got, dict) else None,
            "correct": bool(correct), "not_shown": not_shown, "arm": item["arm"]}
    for run, rows in per_run.items():
        (Path(run) / "readers.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
        n = len(rows)
        ok = sum(r["correct"] for r in rows.values())
        ns = sum(r["not_shown"] for r in rows.values())
        print(f"{Path(run).name}: reader correct {ok}/{n}, not shown {ns}/{n}")
    if missing:
        print(f"{missing} figure(s) have no answer yet")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    s = sub.add_parser("start")
    s.add_argument("task")
    s.add_argument("--run", required=True)
    s.add_argument("--python", default=sys.executable)
    s.add_argument("--arm", choices=ARMS, default="mintfig",
                   help="mintfig (SKILL.md, mint.explain); matplotlib (told the display width and checks); "
                        "matplotlib-plain (told neither, no defect feedback)")
    s.set_defaults(fn=cmd_start)
    s = sub.add_parser("submit")
    s.add_argument("task")
    s.add_argument("script")
    s.add_argument("--run", required=True)
    s.add_argument("--reply", default=None,
                   help="Markdown file with the reply you would send the person (delivery check)")
    s.set_defaults(fn=cmd_submit)
    s = sub.add_parser("recheck")
    s.add_argument("--run", required=True)
    s.set_defaults(fn=cmd_recheck)
    s = sub.add_parser("grade")
    s.add_argument("--run", required=True)
    s.set_defaults(fn=cmd_grade)
    s = sub.add_parser("readers-prepare")
    s.add_argument("runs", nargs="+")
    s.add_argument("--out", required=True)
    s.add_argument("--per-reader", type=int, default=5)
    s.add_argument("--seed", type=int, default=0)
    s.set_defaults(fn=cmd_readers_prepare)
    s = sub.add_parser("readers-score")
    s.add_argument("set")
    s.set_defaults(fn=cmd_readers_score)
    s = sub.add_parser("compare")
    s.add_argument("runs", nargs="+", help="graded run folders, one column each")
    s.add_argument("--out", default=None, help="write the Markdown table here too")
    s.set_defaults(fn=cmd_compare)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
