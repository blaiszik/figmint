"""Task rubric v0.1 loader, validator, and 4-dimension library-agnostic scorer.

Supports the canonical ``rubric.json`` v0.1 schema across ``tasks/`` (``dev``),
``public_test/`` (``public-test``), and ``heldout/`` (``heldout``), while
falling back cleanly to ``answers.json`` for the original 15 figure-bench tasks.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent

SCHEMA_VERSION = "0.1"
VALID_SPLITS = ("dev", "public-test", "heldout")
SPLIT_DIRS: dict[str, str] = {
    "dev": "tasks",
    "public-test": "public_test",
    "heldout": "heldout",
}
DIR_TO_SPLIT: dict[str, str] = {v: k for k, v in SPLIT_DIRS.items()}
VALID_TRACKS = (
    "science_uncertainty",
    "swe_coding",
    "epistemic_traps",
    "multiturn_edit",
    "multi_surface",
    "byo_repair",
)
VALID_SURFACES = ("chat", "narrow", "slide", "dark", "html", "terminal")
SURFACE_DEFAULT_WIDTH: dict[str, int] = {
    "chat": 700,
    "narrow": 450,
    "slide": 1280,
    "dark": 700,
    "html": 700,
    "terminal": 72,
}
REPLY_MAX_WORDS = 60

LEGACY_UNCERTAINTY_TASKS = frozenset({"01_ablation", "03_dose_response", "07_gene_change", "h1_survey"})
LEGACY_SWE_TASKS = frozenset({"02_ab_latency", "09_eval_matrix", "10_incident", "h4_scaling"})
LEGACY_DOMAINS: dict[str, str] = {
    "01_ablation": "ML Evaluation",
    "02_ab_latency": "Web Systems",
    "03_dose_response": "Pharmacology",
    "04_battery_fade": "Materials / Energy",
    "05_retrofit": "Building Energy",
    "06_energy_mix": "Climate / Grid",
    "07_gene_change": "Genomics",
    "08_hall_petch": "Materials Science",
    "09_eval_matrix": "ML Evaluation",
    "10_incident": "Site Reliability",
    "h1_survey": "People Analytics",
    "h2_spectra": "Spectroscopy",
    "h3_wait_times": "Healthcare Ops",
    "h4_scaling": "ML Scaling",
    "h5_budget": "Public Finance",
}
LEGACY_READER_QUESTIONS: dict[str, str] = {
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

_SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")
_FENCE = re.compile(r"^ {0,3}(```|~~~)[^\n]*\n(.*?)^ {0,3}\1[ \t]*$", re.MULTILINE | re.DOTALL)
_IMAGE = re.compile(r"!\[((?:[^\]\\]|\\.)*)\]\(\s*(<[^>]*>|[^)\s]+)[^)]*\)")
_HTML_LINK = re.compile(r"\[(?:[^\]\\]|\\.)*\]\(\s*(<[^>]*>|[^)\s]+\.(?:html?|svg|png))[^)]*\)", re.IGNORECASE)
_WORD = re.compile(r"[^\W_]+(?:['\u2019.,\-][^\W_]+)*")

UNCERTAINTY_WORDS = re.compile(
    r"(\bCI\b|confidence|interval|\bs\.?d\.?\b|\bSD\b|\bSEM?\b|\bs\.e\.m?\.?|standard (?:deviation|error)"
    r"|±|\bIQR\b|quartile|percentile|\bseeds?\b|replicates?|triplicates?|\bwells?\b|\bn\s*=\s*\d"
    r"|margin of error|\brange\b|\bmin[–-]max\b|\bp\s*[<=>]\s*0?\.\d|\bp-value\b|error bars?"
    r"|bootstr|credible|posterior|uncertainty|variance|spread|\bnoise\b)",
    re.IGNORECASE,
)

OVERCLAIM_PATTERNS = re.compile(
    r"\b("
    r"clearly\s+(?:beats?|wins?|better|higher|lower|faster|slower|outperforms?|improves?|reduces?|increases?)"
    r"|proves?|proved|proven"
    r"|significantly\s+(?:higher|lower|better|worse|faster|slower|outperforms?|improves?|reduces?|increases?|beats?)"
    r"|statistically\s+significant"
    r"|decisively|unmistakably|conclusively"
    r"|definitely\s+(?:better|higher|lower|faster|beats?|wins?|improves?|outperforms?)"
    r"|outside\s+(?:the\s+)?noise|above\s+(?:the\s+)?noise"
    r"|real\s+effect|clear\s+(?:winner|gain|lift|advantage|effect|improvement)"
    r"|strong\s+(?:improvement|effect|gain|lift)"
    r"|definitive\s+(?:win|winner|gain|effect|improvement)"
    r")\b",
    re.IGNORECASE,
)

_NEGATION_RE = re.compile(
    r"\b(not|no|never|neither|nor|without|cannot|can't|doesn't|does\s+not|didn't|did\s+not"
    r"|don't|do\s+not|isn't|is\s+not|aren't|are\s+not|wasn't|was\s+not|weren't|were\s+not"
    r"|fails?\s+to|unable\s+to|hardly|unlikely\s+to|far\s+from|lack(?:s|ing)?)\b",
    re.IGNORECASE,
)

NULL_HEDGE_WORDS = re.compile(
    r"(\bwithin\s+(?:the\s+)?noise\b"
    r"|\bno\s+(?:clear\s+|significant\s+|statistically\s+significant\s+|reliable\s+|meaningful\s+|real\s+|detectable\s+)?"
    r"(?:effect|difference|gain|improvement|change|winner|advantage|lift|signal)\b"
    r"|\bindistinguishable\b"
    r"|\boverlap(?:s|ping)?\b"
    r"|\bconsistent\s+with\s+(?:zero|no\s+effect|no\s+difference|null|chance|0)\b"
    r"|\binconclusive\b"
    r"|\bnot\s+(?:statistically\s+)?significant\b"
    r"|\bci\s+(?:includes|crosses|spans|contains)\s+(?:0|zero|1)\b"
    r"|\b(?:includes|crosses|spans)\s+(?:0|zero)\b"
    r"|\bcannot\s+conclude\b"
    r"|\bcould\s+be\s+(?:chance|noise|zero)\b"
    r"|\bnull\b"
    r"|\bp\s*[=>]\s*0\.[1-9]"
    r"|\bnoise\b|\buncertain(?:ty)?\b)",
    re.IGNORECASE,
)

_JUNK_TEXT = re.compile(r"\b(nan|NaN|None|inf|-inf)\b")


# --------------------------------------------------------------------------- text & number helpers


def numbers_in(text: str) -> list[float]:
    """Extract numeric values as a reader sees them: 1,200 / 0.58 / 46% / 1.3×10⁻⁷ / 2e-5 / −3."""
    text = text.replace("\N{MINUS SIGN}", "-").replace("\N{EN DASH}", " ")
    out: list[float] = []
    sci = re.compile(r"(-?\d+(?:\.\d+)?)\s*[×x]\s*10([⁻⁺]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+|\^?[-+]?\d+)")
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


def answer_matches(text: str, key: dict[str, Any]) -> tuple[bool, list[float]]:
    """Return ``(matched, found_numbers)`` checking ``text`` against ``key['accept']``.

    Matching is sign-aware: a negative target in ``accept`` (e.g. ``-18.0``) matches
    negative numbers (``-18%`` / ``−18%``) and does not match positive values (``+18%``
    or ``18%``), and vice versa. Tasks where either sign is acceptable list both signs
    explicitly in ``accept``.
    """
    found = numbers_in(text)
    accept = key.get("accept") or []
    for v in found:
        for target in accept:
            t = float(target)
            tol = max(float(key.get("abs_tol", 0.0)), float(key.get("rel_tol", 0.0)) * abs(t))
            if math.isclose(v, t, abs_tol=tol):
                return True, found
    return False, found


def reply_prose(reply: str) -> str:
    """Reply prose outside fenced code blocks and image lines."""
    outside = _FENCE.sub("", reply)
    return "\n".join(ln for ln in outside.splitlines() if not _IMAGE.search(ln))


def _image_target(target: str) -> str:
    target = target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    return target.removeprefix("./")


def _extract_image_alts(reply: str) -> list[str]:
    outside = _FENCE.sub("", reply)
    return [m.group(1).strip() for m in _IMAGE.finditer(outside) if m.group(1).strip()]


# --------------------------------------------------------------------------- loading & discovery


def _load_answers(base_dir: Path | None = None) -> dict[str, Any]:
    root = base_dir or HERE
    ans = root / "answers.json"
    if not ans.exists():
        ans = HERE / "answers.json"
    if ans.exists():
        return json.loads(ans.read_text(encoding="utf-8"))
    return {}


def load_rubric(task_dir: str | Path, *, answers: dict[str, Any] | None = None) -> dict[str, Any]:
    """Load ``rubric.json`` from ``task_dir``, falling back cleanly to legacy ``answers.json``."""
    tdir = Path(task_dir)
    rubric_path = tdir / "rubric.json"
    if rubric_path.exists():
        data = json.loads(rubric_path.read_text(encoding="utf-8"))
        surface = data.get("surface", "chat")
        default_w = SURFACE_DEFAULT_WIDTH.get(surface, 700)
        return {
            "schema_version": str(data.get("schema_version", SCHEMA_VERSION)),
            "id": str(data.get("id", tdir.name)),
            "split": str(data.get("split", DIR_TO_SPLIT.get(tdir.parent.name, "dev"))),
            "track": str(data.get("track", "science_uncertainty")),
            "domain": str(data.get("domain", "General")),
            "title": str(data.get("title", tdir.name)),
            "display_width_px": int(data.get("display_width_px", default_w)),
            "surface": str(surface),
            "what": str(data.get("what", "")),
            "accept": list(data.get("accept", [])),
            "rel_tol": float(data.get("rel_tol", 0.0)),
            "abs_tol": float(data.get("abs_tol", 0.0)),
            "uncertainty_required": bool(data.get("uncertainty_required", False)),
            "no_effect_trap": bool(data.get("no_effect_trap", False)),
            "forbidden_overclaim_phrases": list(data.get("forbidden_overclaim_phrases", [])),
            "required_disclosures": list(data.get("required_disclosures", [])),
            "forbid_truncated_bars": bool(data.get("forbid_truncated_bars", False)),
            "require_log_scale": bool(data.get("require_log_scale", False)),
            "min_panels": int(data.get("min_panels", 0)),
            "reader_questions": list(data.get("reader_questions", [])),
            "_source": "rubric.json",
            "_task_dir": str(tdir),
        }

    # Legacy fallback for the original 15 tasks using answers.json
    ans_map = answers if answers is not None else _load_answers(tdir.parent.parent)
    task_id = tdir.name
    entry = ans_map.get(task_id, {})
    split = DIR_TO_SPLIT.get(tdir.parent.name, "heldout" if task_id.startswith("h") else "dev")
    track = "swe_coding" if task_id in LEGACY_SWE_TASKS else "science_uncertainty"
    q_text = LEGACY_READER_QUESTIONS.get(task_id)
    reader_qs = (
        [{"kind": "primary", "question": q_text, "expected": entry.get("what", "")}]
        if q_text
        else []
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "id": task_id,
        "split": split,
        "track": track,
        "domain": LEGACY_DOMAINS.get(task_id, "General"),
        "title": task_id.replace("_", " ").title(),
        "display_width_px": 700,
        "surface": "chat",
        "what": str(entry.get("what", "")),
        "accept": list(entry.get("accept", [])),
        "rel_tol": float(entry.get("rel_tol", 0.0)),
        "abs_tol": float(entry.get("abs_tol", 0.0)),
        "uncertainty_required": task_id in LEGACY_UNCERTAINTY_TASKS,
        "no_effect_trap": False,
        "forbidden_overclaim_phrases": [],
        "required_disclosures": [],
        "forbid_truncated_bars": False,
        "require_log_scale": False,
        "min_panels": 0,
        "reader_questions": reader_qs,
        "_source": "answers.json" if entry else "default",
        "_task_dir": str(tdir),
    }


def discover_task_dirs(
    base_dir: str | Path | None = None,
    *,
    split: str | None = None,
    track: str | None = None,
) -> list[Path]:
    """Discover task folders across ``tasks/``, ``public_test/``, and ``heldout/``."""
    root = Path(base_dir) if base_dir is not None else HERE
    answers = _load_answers(root)
    if split is not None:
        if split not in SPLIT_DIRS:
            raise ValueError(f"invalid split {split!r}; expected one of {VALID_SPLITS}")
        roots = [root / SPLIT_DIRS[split]]
    else:
        roots = [root / SPLIT_DIRS[s] for s in VALID_SPLITS]

    found: list[Path] = []
    for folder in roots:
        if not folder.is_dir():
            continue
        for child in sorted(folder.iterdir()):
            if not child.is_dir():
                continue
            if not ((child / "context.md").exists() or (child / "rubric.json").exists()):
                continue
            if track is not None:
                rub = load_rubric(child, answers=answers)
                if rub.get("track") != track:
                    continue
            found.append(child)
    return found


# --------------------------------------------------------------------------- validation


def _is_finite_number(val: Any) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(val)


def validate_task_dir(task_dir: str | Path, *, answers: dict[str, Any] | None = None) -> list[str]:
    """Validate a single figure-bench task folder; returns a list of errors (empty = valid)."""
    tdir = Path(task_dir)
    errors: list[str] = []
    if not tdir.is_dir():
        return [f"task path is not a directory: {tdir}"]

    ctx = tdir / "context.md"
    if not ctx.is_file():
        errors.append("missing context.md")
    else:
        ctx_text = ctx.read_text(encoding="utf-8")
        if not ctx_text.strip():
            errors.append("context.md is empty")
        elif re.search(r"\bmintfig\b", ctx_text, re.IGNORECASE):
            errors.append("context.md must not mention 'mintfig' (library-agnostic prompt requirement)")

    data_dir = tdir / "data"
    if data_dir.is_dir():
        data_files = [p for p in data_dir.rglob("*") if p.is_file() and not p.name.startswith(".")]
        if not data_files:
            errors.append("data/ directory exists but contains no files")
    else:
        # Allow byo_repair / multiturn_edit tasks with starter files directly in task_dir
        extras = [
            p
            for p in tdir.iterdir()
            if p.is_file() and p.name not in ("context.md", "rubric.json") and not p.name.startswith(".")
        ]
        if not extras:
            errors.append("missing data/ directory (and no starter data/script files found)")

    rubric_path = tdir / "rubric.json"
    if not rubric_path.is_file():
        ans_map = answers if answers is not None else _load_answers(tdir.parent.parent)
        if tdir.name not in ans_map:
            errors.append("missing rubric.json (and task id not found in legacy answers.json)")
        return errors

    try:
        raw = json.loads(rubric_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return errors + [f"rubric.json failed to parse: {exc}"]

    if not isinstance(raw, dict):
        return errors + ["rubric.json root must be a JSON object"]

    if raw.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}, got {raw.get('schema_version')!r}")

    rid = raw.get("id")
    if not isinstance(rid, str) or not rid.strip():
        errors.append("id must be a non-empty string")
    elif rid != tdir.name:
        errors.append(f"id {rid!r} does not match directory name {tdir.name!r}")

    split = raw.get("split")
    if split not in VALID_SPLITS:
        errors.append(f"split must be one of {VALID_SPLITS}, got {split!r}")
    elif tdir.parent.name in DIR_TO_SPLIT and DIR_TO_SPLIT[tdir.parent.name] != split:
        errors.append(
            f"split {split!r} does not match parent folder {tdir.parent.name!r} "
            f"(expected {DIR_TO_SPLIT[tdir.parent.name]!r})"
        )

    track = raw.get("track")
    if track not in VALID_TRACKS:
        errors.append(f"track must be one of {VALID_TRACKS}, got {track!r}")

    for str_field in ("domain", "title", "what"):
        val = raw.get(str_field)
        if not isinstance(val, str) or not val.strip():
            errors.append(f"{str_field} must be a non-empty string")

    surface = raw.get("surface")
    if surface not in VALID_SURFACES:
        errors.append(f"surface must be one of {VALID_SURFACES}, got {surface!r}")

    dw = raw.get("display_width_px")
    if not isinstance(dw, int) or isinstance(dw, bool) or dw < 40 or dw > 4000:
        errors.append(f"display_width_px must be an int between 40 and 4000, got {dw!r}")

    accept = raw.get("accept")
    no_effect = raw.get("no_effect_trap")
    if not isinstance(accept, list):
        errors.append("accept must be a list of numbers")
    else:
        bad_vals = [v for v in accept if not _is_finite_number(v)]
        if bad_vals:
            errors.append(f"accept contains non-numeric values: {bad_vals!r}")
        if not accept and not no_effect:
            errors.append("accept must be non-empty unless no_effect_trap is true")

    for tol_field in ("rel_tol", "abs_tol"):
        val = raw.get(tol_field)
        if not _is_finite_number(val) or val < 0:
            errors.append(f"{tol_field} must be a non-negative number, got {val!r}")

    for bool_field in ("uncertainty_required", "no_effect_trap"):
        if not isinstance(raw.get(bool_field), bool):
            errors.append(f"{bool_field} must be a boolean, got {raw.get(bool_field)!r}")

    for list_field in ("forbidden_overclaim_phrases", "required_disclosures"):
        if list_field in raw:
            lv = raw[list_field]
            if not isinstance(lv, list) or not all(isinstance(x, str) for x in lv):
                errors.append(f"{list_field} must be a list of strings")
            elif list_field == "required_disclosures":
                for d in lv:
                    alts = [a.strip() for a in d.split("|") if a.strip()]
                    if not alts:
                        errors.append("required_disclosures contains an empty entry")
                    elif all(len(a.split()) > 6 for a in alts):
                        errors.append(
                            f"required_disclosures entry {d!r} looks like an unmatchable prose sentence "
                            "(use concise matchable tokens or pipe-delimited alternatives like 'a|b')"
                        )

    for opt_bool in ("forbid_truncated_bars", "require_log_scale"):
        if opt_bool in raw and not isinstance(raw[opt_bool], bool):
            errors.append(f"{opt_bool} must be a boolean, got {raw[opt_bool]!r}")
    if "min_panels" in raw:
        mp = raw["min_panels"]
        if not isinstance(mp, int) or isinstance(mp, bool) or mp < 0:
            errors.append(f"min_panels must be a non-negative integer, got {mp!r}")

    rqs = raw.get("reader_questions")
    if not isinstance(rqs, list):
        errors.append("reader_questions must be a list")
    else:
        for i, q in enumerate(rqs):
            if not isinstance(q, dict):
                errors.append(f"reader_questions[{i}] must be an object")
                continue
            if not isinstance(q.get("kind"), str) or not q["kind"].strip():
                errors.append(f"reader_questions[{i}].kind must be a non-empty string")
            if not isinstance(q.get("question"), str) or not q["question"].strip():
                errors.append(f"reader_questions[{i}].question must be a non-empty string")
            if "expected" not in q or q["expected"] is None or str(q["expected"]).strip() == "":
                errors.append(f"reader_questions[{i}].expected must be present and non-empty")

    return errors


# --------------------------------------------------------------------------- scoring


def _norm_disclosure_text(text: str) -> str:
    """Normalize punctuation and whitespace for robust disclosure matching."""
    t = text.lower()
    t = t.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-").replace("\u00a0", " ")
    t = re.sub(r"\s+", " ", t)
    return t


def _disclosure_present(spec: str, norm_blob: str) -> bool:
    """Return True if any pipe-delimited alternative in ``spec`` matches ``norm_blob``.

    Normalizes whitespace around ``=`` and ``%`` as well as ``s.d.``/``sd`` so reasonable
    human formatting variations (``n = 3`` vs ``n=3``, ``±1 s.d.`` vs ``±1 SD``) pass cleanly.
    """
    compact_blob = re.sub(r"\s*([=%])\s*", r"\1", norm_blob)
    for alt in spec.split("|"):
        cand = _norm_disclosure_text(alt).strip()
        if not cand:
            continue
        if cand in norm_blob:
            return True
        compact_cand = re.sub(r"\s*([=%])\s*", r"\1", cand)
        if compact_cand in compact_blob:
            return True
    return False


def _detect_overclaims(
    text: str,
    extra_phrases: list[str] | None = None,
    *,
    include_generic: bool = True,
) -> list[str]:
    """Return unnegated overclaim phrases found in ``text``."""
    found: list[str] = []

    def _is_negated(pos: int) -> bool:
        clause_start = max(
            text.rfind(".", 0, pos),
            text.rfind(";", 0, pos),
            text.rfind("!", 0, pos),
            text.rfind("?", 0, pos),
            text.rfind("\n", 0, pos),
        )
        window_start = max(clause_start + 1, pos - 36)
        prefix = text[window_start:pos]
        return bool(_NEGATION_RE.search(prefix))

    if include_generic:
        for m in OVERCLAIM_PATTERNS.finditer(text):
            if not _is_negated(m.start()):
                phrase = m.group(0).strip()
                if phrase not in found:
                    found.append(phrase)

    for phrase in extra_phrases or []:
        p = phrase.strip()
        if not p:
            continue
        for m in re.finditer(re.escape(p), text, re.IGNORECASE):
            if not _is_negated(m.start()):
                if p not in found:
                    found.append(p)
                break
    return found


def _score_terminal_visual(reply_text: str | None, display_width_px: int) -> dict[str, Any]:
    if not reply_text:
        return {"score": 0.0, "passed": False, "source": "terminal", "issues": ["missing reply text"]}
    blocks = [m.group(2) for m in _FENCE.finditer(reply_text) if m.group(2).strip()]
    if not blocks:
        return {
            "score": 0.0,
            "passed": False,
            "source": "terminal",
            "issues": ["no fenced terminal text block found"],
        }
    block = max(blocks, key=len)
    lines = [ln.rstrip() for ln in block.splitlines() if ln.strip()]
    max_cols = max((len(ln) for ln in lines), default=0)
    limit = max(72, display_width_px) if display_width_px <= 140 else 80
    issues: list[str] = []
    score = 100.0
    if max_cols > limit + 8:
        issues.append(f"terminal line width {max_cols} exceeds {limit} cols")
        score -= 25.0
    if _JUNK_TEXT.search(block) or "%%" in block:
        issues.append("malformed text (nan/None/%%) in terminal output")
        score -= 25.0
    if len(lines) < 2:
        issues.append("terminal figure has fewer than 2 non-empty lines")
        score -= 30.0
    score = max(0.0, round(score, 1))
    return {
        "score": score,
        "passed": not issues,
        "source": "terminal",
        "max_cols": max_cols,
        "lines": len(lines),
        "issues": issues,
    }


def _score_visual(
    rubric: dict[str, Any],
    *,
    png_path: Path | None,
    svg_path: Path | None,
    neutral_audit: dict[str, Any] | None,
    reply_text: str | None,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    import neutral
    import pixel_audit
    import svg_audit

    surface = rubric.get("surface", "chat")
    display_w = int(rubric.get("display_width_px", SURFACE_DEFAULT_WIDTH.get(surface, 700)))
    if surface == "terminal":
        return _score_terminal_visual(reply_text, display_w), None, None

    svg_res: dict[str, Any] | None = None
    px_res: dict[str, Any] | None = None

    if svg_path is not None and svg_path.is_file():
        svg_res = svg_audit.audit_svg(svg_path, display_width_px=display_w)
    if png_path is not None and png_path.is_file():
        px_res = pixel_audit.audit_png(png_path, display_width_px=display_w, surface=surface)

    if neutral_audit is None and svg_res is None and px_res is None:
        return (
            {"score": 0.0, "passed": False, "source": "none", "issues": ["missing figure artifact"]},
            svg_res,
            px_res,
        )

    if px_res is not None and px_res.get("empty_canvas"):
        return (
            {
                "score": 0.0,
                "passed": False,
                "source": "pixel_audit",
                "issues": list(px_res.get("issues", ["empty_canvas"])),
                "pixel_audit": px_res,
            },
            svg_res,
            px_res,
        )

    score = 100.0
    issues: list[str] = []
    sources: list[str] = []

    vector_penalties = {
        "text_legible": 25.0,
        "no_text_overlap": 20.0,
        "no_text_struck_by_lines": 15.0,
        "text_well_formed": 15.0,
        "no_text_clipped": 15.0,
    }
    has_vector_audit = False
    banned_penalized = False
    clip_penalized = False

    if neutral_audit is not None:
        has_vector_audit = True
        sources.append("neutral_audit")
        for chk in neutral.neutral_checks(neutral_audit):
            if not chk["passed"]:
                score -= vector_penalties.get(chk["name"], 15.0)
                issues.append(f"{chk['name']}: {chk['detail']}" if chk["detail"] else chk["name"])
                if chk["name"] == "no_text_clipped":
                    clip_penalized = True
        if neutral_audit.get("banned_colormaps"):
            score -= 20.0
            banned_penalized = True
            issues.append(f"banned_colormaps: {', '.join(neutral_audit['banned_colormaps'])}")
        if rubric.get("forbid_truncated_bars") and neutral_audit.get("truncated_bar_axes"):
            score -= 25.0
            issues.append(
                f"truncated_bar_baseline: {'; '.join(neutral_audit['truncated_bar_axes'][:3])}"
            )
        if rubric.get("require_log_scale") and neutral_audit.get("has_log_axis") is False:
            score -= 20.0
            issues.append("missing_log_scale: task requires log/symlog axis")
        min_panels = int(rubric.get("min_panels") or 0)
        if min_panels > 0 and (neutral_audit.get("panels") or 0) < min_panels:
            score -= 15.0
            issues.append(
                f"insufficient_panels: got {neutral_audit.get('panels', 0)}, expected >= {min_panels}"
            )
    elif svg_res is not None and svg_res.get("texts", 0) > 0:
        has_vector_audit = True
        sources.append("svg_audit")
        for chk in svg_audit.svg_checks(svg_res):
            if not chk["passed"]:
                score -= vector_penalties.get(chk["name"], 15.0)
                issues.append(f"{chk['name']}: {chk['detail']}" if chk["detail"] else chk["name"])
                if chk["name"] == "no_text_clipped":
                    clip_penalized = True

    if px_res is not None:
        sources.append("pixel_audit")
        if px_res.get("rainbow_colormap_suspected") and not banned_penalized:
            score -= 20.0
            issues.append("rainbow_colormap_suspected")
        if not px_res.get("cvd_ok", True):
            score -= 15.0
            issues.append("cvd_issue")
        if not px_res.get("grayscale_ok", True):
            score -= 10.0
            issues.append("grayscale_low_contrast")
        if (
            px_res.get("edge_clipped")
            and not clip_penalized
            and (not has_vector_audit or px_res.get("edge_ink_ratio", 0.0) > 0.15)
        ):
            score -= 15.0
            issues.append("edge_clipped")
        if surface == "dark" and not px_res.get("is_dark_background"):
            score -= 15.0
            issues.append("surface_mismatch: dark surface expected")

    score = max(0.0, round(score, 1))
    passed = not issues
    result: dict[str, Any] = {
        "score": score,
        "passed": passed,
        "source": "+".join(sources) if sources else "none",
        "issues": issues,
    }
    if px_res is not None:
        result["png_px"] = px_res["png_px"]
        result["shown_px"] = px_res["shown_px"]
    return result, svg_res, px_res


def _score_claim_accuracy(
    rubric: dict[str, Any],
    *,
    reply_text: str | None,
    neutral_audit: dict[str, Any] | None,
    svg_res: dict[str, Any] | None,
) -> dict[str, Any]:
    headlines: list[str] = []
    if neutral_audit and neutral_audit.get("headlines"):
        headlines = list(neutral_audit["headlines"])
    elif svg_res and svg_res.get("headlines"):
        headlines = list(svg_res["headlines"])

    alt_texts = _extract_image_alts(reply_text) if reply_text else []
    prose = reply_prose(reply_text) if reply_text else ""
    accept = rubric.get("accept") or []

    head_blob = " ".join(headlines)
    reply_blob = " ".join([prose, *alt_texts]).strip()

    if not accept:
        has_any = bool(head_blob.strip() or reply_blob.strip())
        return {
            "score": 100.0 if has_any else 0.0,
            "passed": has_any,
            "headline_match": None,
            "reply_match": None,
            "found_numbers": [],
            "detail": "qualitative task (no numeric accept targets)",
        }

    head_match, head_nums = answer_matches(head_blob, rubric) if head_blob.strip() else (False, [])
    reply_match, reply_nums = answer_matches(reply_blob, rubric) if reply_blob.strip() else (False, [])

    # Also check all drawn SVG text if headlines heuristic missed a numeric callout
    svg_all_match = False
    if svg_res and not head_match and svg_res.get("text_strings"):
        svg_all_match, _ = answer_matches(" ".join(svg_res["text_strings"]), rubric)

    figure_has_headlines = bool(head_blob.strip())
    if figure_has_headlines:
        if head_match and (reply_match or not reply_blob):
            score = 100.0
        elif head_match:
            score = 85.0
        elif reply_match:
            score = 75.0
        elif svg_all_match:
            score = 65.0
        else:
            score = 0.0
    else:
        # PNG-only submissions (Altair/Plotly/ggplot2 via grade-dir) have no extracted figure headline
        if reply_match:
            score = 100.0
        elif svg_all_match:
            score = 80.0
        else:
            score = 0.0

    passed = bool(head_match or reply_match or svg_all_match)
    return {
        "score": round(score, 1),
        "passed": passed,
        "headline_match": head_match if figure_has_headlines else None,
        "reply_match": reply_match if reply_blob else None,
        "found_numbers": list(dict.fromkeys([*head_nums, *reply_nums]))[:12],
        "expected": rubric.get("what", ""),
    }


def _score_uncertainty_calibration(
    rubric: dict[str, Any],
    *,
    reply_text: str | None,
    neutral_audit: dict[str, Any] | None,
    svg_res: dict[str, Any] | None,
) -> dict[str, Any]:
    unc_req = bool(rubric.get("uncertainty_required", False))
    no_effect = bool(rubric.get("no_effect_trap", False))
    forbidden = list(rubric.get("forbidden_overclaim_phrases") or [])
    disclosures = list(rubric.get("required_disclosures") or [])

    figure_parts: list[str] = []
    if neutral_audit:
        if neutral_audit.get("all_texts"):
            figure_parts.extend(neutral_audit["all_texts"])
        elif neutral_audit.get("headlines"):
            figure_parts.extend(neutral_audit["headlines"])
    if svg_res and svg_res.get("text_strings"):
        figure_parts.extend(svg_res["text_strings"])
    prose = reply_prose(reply_text) if reply_text else ""
    alts = _extract_image_alts(reply_text) if reply_text else []

    claim_blob = " ".join([*figure_parts, *alts, prose]).strip()
    all_blob = " ".join([*figure_parts, reply_text or ""]).strip()
    norm_all_blob = _norm_disclosure_text(all_blob)

    unc_named = bool(
        (neutral_audit and neutral_audit.get("uncertainty_named"))
        or (svg_res and svg_res.get("uncertainty_named"))
        or UNCERTAINTY_WORDS.search(all_blob)
    )
    hedged_null = bool(NULL_HEDGE_WORDS.search(all_blob))

    overclaims: list[str] = []
    if no_effect or forbidden:
        overclaims = _detect_overclaims(claim_blob, forbidden, include_generic=no_effect)

    missing_disclosures = [
        d for d in disclosures if d.strip() and not _disclosure_present(d, norm_all_blob)
    ]

    issues: list[str] = []
    score = 100.0

    if no_effect:
        if overclaims:
            score = 0.0
            issues.append(f"overclaim on no-effect trap: {', '.join(overclaims[:4])}")
        elif not (hedged_null or unc_named):
            score = min(score, 40.0)
            issues.append("no-effect trap: neither uncertainty nor null/noise caveat stated")
    elif overclaims:
        score = max(0.0, score - 50.0)
        issues.append(f"forbidden overclaim phrase(s): {', '.join(overclaims[:4])}")

    if unc_req and not unc_named:
        score = max(0.0, score - 50.0)
        issues.append("uncertainty_required: no CI/SD/SE/seeds/replicates/n named")

    if missing_disclosures:
        per = 40.0 / max(1, len(disclosures))
        score = max(0.0, score - per * len(missing_disclosures))
        issues.append(f"missing required disclosure(s): {', '.join(missing_disclosures[:4])}")

    score = round(score, 1)
    passed = not issues
    return {
        "score": score,
        "passed": passed,
        "uncertainty_required": unc_req,
        "uncertainty_named": unc_named,
        "no_effect_trap": no_effect,
        "overclaim_detected": bool(overclaims),
        "overclaims": overclaims,
        "hedged_null": hedged_null,
        "missing_disclosures": missing_disclosures,
        "issues": issues,
    }


def _score_delivery(
    rubric: dict[str, Any],
    *,
    png_path: Path | None,
    svg_path: Path | None,
    reply_text: str | None,
) -> dict[str, Any]:
    if reply_text is None:
        return {
            "score": 0.0,
            "passed": False,
            "status": "not provided",
            "words": 0,
            "detail": "reply not provided",
        }

    surface = rubric.get("surface", "chat")
    blocks = [m.group(2) for m in _FENCE.finditer(reply_text) if m.group(2).strip()]
    outside = _FENCE.sub("", reply_text)
    images = [_image_target(m.group(2)) for m in _IMAGE.finditer(outside)]
    prose = "\n".join(ln for ln in outside.splitlines() if not _IMAGE.search(ln))
    words = len(_WORD.findall(prose))

    shown = ""
    if surface == "terminal":
        if blocks:
            shown = "terminal code block"
    else:
        wanted: set[str] = set()
        if png_path is not None:
            wanted.add(png_path.name)
            wanted.add("figure.png")
        if svg_path is not None:
            wanted.add(svg_path.name)
            wanted.add("figure.svg")
        for got in images:
            if not wanted or Path(got).name in wanted or got in wanted:
                shown = f"image {got}"
                break
        if not shown and surface == "html":
            m_html = _HTML_LINK.search(outside)
            if m_html:
                shown = f"html link {_image_target(m_html.group(1))}"
        if not shown and blocks and png_path is None:
            shown = "code block"

    problems: list[str] = []
    if not shown:
        if surface == "terminal":
            problems.append("no fenced code block with terminal figure")
        else:
            problems.append("no ![...](figure.png) image reference")
    if words > REPLY_MAX_WORDS:
        problems.append(f"{words} words of prose (max {REPLY_MAX_WORDS})")

    if not problems:
        score = 100.0
    elif shown or words <= REPLY_MAX_WORDS:
        score = 50.0
    else:
        score = 0.0

    passed = not problems
    return {
        "score": score,
        "passed": passed,
        "status": "pass" if passed else "fail",
        "words": words,
        "detail": "; ".join(problems) if problems else f"{shown}; {words} words of prose",
    }


def score_submission(
    rubric: dict[str, Any],
    *,
    png_path: str | Path | None,
    reply_text: str | None,
    svg_path: str | Path | None = None,
    neutral_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score a task submission across the 4 figure-bench v0.1 dimensions.

    Dimensions & weights:
    - ``visual_quality`` (35%)
    - ``claim_accuracy`` (30%)
    - ``uncertainty_calibration`` (20%)
    - ``delivery`` (15%)
    """
    png = Path(png_path) if png_path is not None else None
    svg = Path(svg_path) if svg_path is not None else None

    vq, svg_res, _px_res = _score_visual(
        rubric, png_path=png, svg_path=svg, neutral_audit=neutral_audit, reply_text=reply_text
    )
    ca = _score_claim_accuracy(rubric, reply_text=reply_text, neutral_audit=neutral_audit, svg_res=svg_res)
    uc = _score_uncertainty_calibration(rubric, reply_text=reply_text, neutral_audit=neutral_audit, svg_res=svg_res)
    dl = _score_delivery(rubric, png_path=png, svg_path=svg, reply_text=reply_text)

    composite = round(
        0.35 * vq["score"] + 0.30 * ca["score"] + 0.20 * uc["score"] + 0.15 * dl["score"],
        1,
    )
    passed_figure = bool(vq["passed"] and ca["passed"] and uc["passed"])
    passed = bool(passed_figure and dl["passed"])

    return {
        "task_id": rubric.get("id", ""),
        "split": rubric.get("split", "dev"),
        "track": rubric.get("track", "science_uncertainty"),
        "surface": rubric.get("surface", "chat"),
        "composite": composite,
        "passed": passed,
        "passed_figure": passed_figure,
        "visual_quality": vq,
        "claim_accuracy": ca,
        "uncertainty_calibration": uc,
        "delivery": dl,
    }
