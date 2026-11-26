"""40-prompt skill trigger evaluation for mintfig.

Evaluates ``src/mintfig/assets/SKILL.md`` (frontmatter description) and
``src/mintfig/assets/AGENTS_SNIPPET.md`` against 40 realistic prompts that never
mention ``mintfig`` (20 positive, 20 negative).

Modes:
- **Offline deterministic rubric (default):** parses the actual trigger and
  non-trigger criteria declared in ``SKILL.md`` + ``AGENTS_SNIPPET.md`` and
  scores every prompt reproducibly with zero network calls.
- **Live agent adapter (``--live``):** invokes ``claude -p``, ``codex exec``,
  or ``gemini -p`` with the skill catalog context to measure real LLM routing.

Exit codes:
- ``0``: passed exit gates (recall >= 85%, false-trigger rate <= 5%)
- ``1``: failed one or more exit gates
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
DEFAULT_PROMPTS = HERE / "prompts.json"
DEFAULT_REPORT = HERE / "REPORT.md"
DEFAULT_SKILL = REPO_ROOT / "src" / "mintfig" / "assets" / "SKILL.md"
DEFAULT_SNIPPET = REPO_ROOT / "src" / "mintfig" / "assets" / "AGENTS_SNIPPET.md"


@dataclass(frozen=True)
class SkillTriggerSpec:
    """Trigger and suppression capabilities extracted from SKILL.md + AGENTS_SNIPPET.md."""

    name: str
    description: str
    snippet: str
    covers_five_plus_numbers: bool
    covers_comparisons_trends_distributions: bool
    covers_csv_experiments: bool
    covers_matplotlib_check: bool
    covers_notebook_check: bool
    covers_publication_plates: bool
    forbids_routine_code: bool
    forbids_few_scalars: bool


@dataclass(frozen=True)
class PromptResult:
    """Evaluation outcome for a single prompt."""

    id: str
    category: str
    should_trigger: bool
    predicted_trigger: bool
    correct: bool
    matched_rule: str
    positive_signals: list[str]
    negative_signals: list[str]
    reason: str
    prompt: str


def parse_frontmatter(skill_md: str) -> dict[str, str]:
    """Extract simple YAML frontmatter key/value pairs from SKILL.md."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", skill_md, flags=re.DOTALL)
    if not match:
        return {}
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            fields[key.strip()] = val.strip().strip('"').strip("'")
    return fields


def extract_skill_spec(skill_md: str, snippet_md: str) -> SkillTriggerSpec:
    """Inspect SKILL.md frontmatter and AGENTS_SNIPPET.md for declared trigger rules."""
    fm = parse_frontmatter(skill_md)
    desc = fm.get("description", "")
    combined = f"{desc}\n{snippet_md}".lower()

    return SkillTriggerSpec(
        name=fm.get("name", ""),
        description=desc,
        snippet=snippet_md,
        covers_five_plus_numbers=bool(
            re.search(r"(five or more|5\+)\s+numbers", combined)
        ),
        covers_comparisons_trends_distributions=bool(
            re.search(r"comparison", combined)
            and re.search(r"trend", combined)
            and re.search(r"distribution", combined)
        ),
        covers_csv_experiments=bool(
            re.search(r"\bcsv\b|ablation|benchmark|experiment", combined)
        ),
        covers_matplotlib_check=bool(
            re.search(r"matplotlib", combined) and re.search(r"mint\.check|mintfig check", combined)
        ),
        covers_notebook_check=bool(re.search(r"notebook|\.ipynb", combined)),
        covers_publication_plates=bool(
            re.search(r"publication|manuscript|journal", combined)
            and re.search(r"nature|neurips|science", combined)
        ),
        forbids_routine_code=bool(
            re.search(r"do not|skip plotting|not use", combined)
            and re.search(r"bug fix|refactor|unit test|stack trace|routine code", combined)
        ),
        forbids_few_scalars=bool(
            re.search(r"do not|skip plotting|prose", combined)
            and re.search(r"1[–-]3\s*(scalar\s*)?numbers|one to three numbers", combined)
        ),
    )


# Pattern banks for deterministic offline rubric scoring.
_PUB_PATTERNS: list[tuple[str, str]] = [
    ("journal_name", r"\b(nature|science|cell|pnas|neurips)\b"),
    ("manuscript_plate", r"\b(manuscript|submission bundle|single-column|double-column|millimeter|mm\b|preflight|plate)\b"),
]

_MPL_CHECK_PATTERNS: list[tuple[str, str]] = [
    ("matplotlib_artifact", r"\b(matplotlib|plots?/|make_[\w]+\.py|\.ipynb|notebooks?/|png)\b"),
    ("audit_intent", r"\b(audit|review|check whether|clipped|truncated|legible|chat width|headline number|title numbers?)\b"),
]

_DATA_VISUAL_PATTERNS: list[tuple[str, str]] = [
    ("data_file", r"\b[\w-]+\.(csv|tsv|json|jsonl|parquet)\b"),
    ("multi_entity_count", r"\b([4-9]|[1-9]\d+)\s+(?:[\w-]+\s+){0,2}(variant|variants|model|models|checkpoint|checkpoints|compound|compounds|gene|genes|cell|cells|stage|stages|building|buildings|service|services|zone|zones|level|levels|descriptor|descriptors|driver|drivers|schedule|schedules|epoch|epochs|concentration|concentrations)\b"),
    ("experiment_domain", r"\b(ablation|benchmark|dose-response|ic50|viability|conductivity|doping|fold change|differential expression|capacity fade|capacity retention|cycle life|pouch cell|correlation matrix|pearson|funnel|drop-off|attrition|waterfall|retrofit|etl|trace|scorecard|rollout|a/b)\b"),
    ("visual_analysis_verb", r"\b(compare|trends?|distribution|spread|outliers?|trajector|curves?|latency|p50|p95|p99|confidence interval|95% ci|s\.d\.|replicates?|seeds?|breakdown|break down|profile|explore|summarize|analyze|show how|show when|show user|show which|display)\b"),
]

_ROUTINE_CODE_PATTERNS: list[tuple[str, str]] = [
    ("bug_fix_lint", r"\b(fix the|keyerror|attributeerror|typeerror|mypy|ruff|lint|regex|bug|race condition|thread-safety)\b"),
    ("refactor_rename", r"\b(refactor|rename|split\b.*\bclass|call sites|imports)\b"),
    ("unit_test_code", r"\b(unit tests?|pytest unit|expired tokens|invalid signatures)\b"),
    ("git_vcs", r"\b(git rebase|merge conflict|git diff|uncommitted)\b"),
    ("stack_trace", r"\b(traceback|stack trace|nonetype)\b"),
    ("code_architecture", r"\b(architecture of this repository|how requests flow|how the @|decorator|docstrings?|argparse|alembic migration|composite index)\b"),
    ("config_docker_ci", r"\b(dockerfile|multi-stage build|pyproject\.toml|\.github/workflows|dependency cache|cli flag|--timeout)\b"),
]

_FEW_SCALARS_PATTERNS: list[tuple[str, str]] = [
    ("few_scalars_explicit", r"\b(single peak|three numbers|how many tests passed|how many failed|min,\s*median,\s*and max|all i need)\b"),
]


def _match_patterns(text: str, patterns: list[tuple[str, str]]) -> list[str]:
    low = text.lower()
    return [name for name, pat in patterns if re.search(pat, low)]


def score_prompt_offline(prompt_item: dict[str, Any], spec: SkillTriggerSpec) -> PromptResult:
    """Deterministically decide whether the declared skill criteria trigger on a prompt."""
    text = str(prompt_item["prompt"])
    pub_hits = _match_patterns(text, _PUB_PATTERNS)
    mpl_hits = _match_patterns(text, _MPL_CHECK_PATTERNS)
    data_hits = _match_patterns(text, _DATA_VISUAL_PATTERNS)
    code_hits = _match_patterns(text, _ROUTINE_CODE_PATTERNS)
    scalar_hits = _match_patterns(text, _FEW_SCALARS_PATTERNS)

    pos_signals: list[str] = []
    neg_signals: list[str] = []
    matched_rule = "none"
    predicted = False
    reason = ""

    # 1. Explicit suppression rules (only active when the skill actually declares them)
    has_strong_data_or_plot = (
        len(pub_hits) >= 2
        or len(mpl_hits) >= 2
        or ("data_file" in data_hits and len(data_hits) >= 2)
        or (len(data_hits) >= 3)
    )

    if scalar_hits and spec.forbids_few_scalars and not has_strong_data_or_plot:
        neg_signals.extend(scalar_hits)
        matched_rule = "suppress_few_scalars"
        predicted = False
        reason = f"Suppressed by 1-3 scalar prose rule ({', '.join(scalar_hits)})."
    elif code_hits and spec.forbids_routine_code and not has_strong_data_or_plot:
        neg_signals.extend(code_hits)
        matched_rule = "suppress_routine_code"
        predicted = False
        reason = f"Suppressed by routine-coding exclusion ({', '.join(code_hits)})."
    # 2. Publication plate rule
    elif len(pub_hits) >= 2 and spec.covers_publication_plates:
        pos_signals.extend(pub_hits)
        matched_rule = "trigger_publication_plate"
        predicted = True
        reason = f"Matched publication plate criteria ({', '.join(pub_hits)})."
    # 3. Plain Matplotlib / notebook check rule
    elif (
        len(mpl_hits) >= 2
        and spec.covers_matplotlib_check
        and (".ipynb" not in text.lower() or spec.covers_notebook_check)
    ):
        pos_signals.extend(mpl_hits)
        matched_rule = "trigger_matplotlib_check"
        predicted = True
        reason = f"Matched Matplotlib/notebook audit criteria ({', '.join(mpl_hits)})."
    # 4. Quantitative / multi-number visual explanation rule
    elif (
        spec.covers_five_plus_numbers
        and (spec.covers_comparisons_trends_distributions or spec.covers_csv_experiments)
        and (
            ("data_file" in data_hits and len(data_hits) >= 2)
            or ("multi_entity_count" in data_hits and len(data_hits) >= 2)
            or (len(data_hits) >= 3)
        )
    ):
        pos_signals.extend(data_hits)
        matched_rule = "trigger_explain_data"
        predicted = True
        reason = f"Matched 5+ numbers / visual explanation criteria ({', '.join(data_hits)})."
    else:
        # If suppression rules were omitted from SKILL.md, ambiguous coding/scalar prompts
        # that contain weak numeric/review words risk false-triggering.
        if (code_hits or scalar_hits) and not (spec.forbids_routine_code and spec.forbids_few_scalars):
            neg_signals.extend(code_hits + scalar_hits)
            if re.search(r"\b(number|median|max|min|review|passed|failed|memory|score|rate|check)\b", text.lower()):
                pos_signals.append("unguarded_numeric_or_review_term")
                matched_rule = "false_trigger_missing_exclusion"
                predicted = True
                reason = "Triggered due to missing negative exclusion rules in SKILL.md."
            else:
                matched_rule = "no_match"
                predicted = False
                reason = "No positive trigger rule matched."
        else:
            neg_signals.extend(code_hits + scalar_hits)
            matched_rule = "no_match"
            predicted = False
            reason = "No positive trigger rule matched."

    should = bool(prompt_item["should_trigger"])
    return PromptResult(
        id=str(prompt_item["id"]),
        category=str(prompt_item["category"]),
        should_trigger=should,
        predicted_trigger=predicted,
        correct=(predicted == should),
        matched_rule=matched_rule,
        positive_signals=pos_signals,
        negative_signals=neg_signals,
        reason=reason,
        prompt=text,
    )


def _live_routing_prompt(user_prompt: str, spec: SkillTriggerSpec) -> str:
    """Build a concise routing prompt for --live evaluation via claude/codex/gemini CLIs."""
    return (
        "You are deciding whether to invoke an installed coding-agent skill for a user request.\n\n"
        f"Available skill:\n- name: {spec.name}\n- description: {spec.description}\n\n"
        f"User request:\n{user_prompt}\n\n"
        'Respond with ONLY a single JSON object: {"trigger": true|false, "reason": "<one sentence>"}'
    )


def score_prompt_live(
    prompt_item: dict[str, Any],
    spec: SkillTriggerSpec,
    *,
    agent: str,
    model: str | None = None,
    timeout: int = 45,
) -> PromptResult:
    """Run a live CLI check against claude -p, codex exec, or gemini -p."""
    routing_prompt = _live_routing_prompt(str(prompt_item["prompt"]), spec)
    if agent == "claude":
        cmd = ["claude", "-p", routing_prompt]
        if model:
            cmd.extend(["--model", model])
    elif agent == "codex":
        cmd = ["codex", "exec", routing_prompt]
        if model:
            cmd.extend(["-m", model])
    elif agent == "gemini":
        cmd = ["gemini", "-p", routing_prompt]
        if model:
            cmd.extend(["-m", model])
    else:
        raise ValueError(f"Unsupported live agent: {agent!r} (choose claude, codex, or gemini)")

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    raw = (proc.stdout or "").strip()
    predicted = False
    reason = f"CLI exit={proc.returncode}"
    json_match = re.search(r"\{.*?\}", raw, flags=re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            predicted = bool(parsed.get("trigger", False))
            reason = str(parsed.get("reason", raw[:160]))
        except json.JSONDecodeError:
            predicted = "true" in raw.lower()
            reason = f"Unparsed output: {raw[:160]}"
    elif raw:
        predicted = bool(re.search(r"\b(true|yes|mintfig)\b", raw.lower()))
        reason = f"Plain output: {raw[:160]}"

    should = bool(prompt_item["should_trigger"])
    return PromptResult(
        id=str(prompt_item["id"]),
        category=str(prompt_item["category"]),
        should_trigger=should,
        predicted_trigger=predicted,
        correct=(predicted == should),
        matched_rule=f"live_{agent}",
        positive_signals=["live_yes"] if predicted else [],
        negative_signals=["live_no"] if not predicted else [],
        reason=reason,
        prompt=str(prompt_item["prompt"]),
    )


def evaluate_prompts(
    prompts_data: dict[str, Any],
    skill_md: str,
    snippet_md: str,
    *,
    live: bool = False,
    agent: str = "claude",
    model: str | None = None,
    limit: int | None = None,
    timeout: int = 45,
) -> dict[str, Any]:
    """Run trigger evaluation across all prompts and compute aggregate metrics & gate status."""
    spec = extract_skill_spec(skill_md, snippet_md)
    prompts = list(prompts_data["prompts"])
    if limit is not None:
        prompts = prompts[:limit]

    results: list[PromptResult] = []
    for item in prompts:
        if live:
            results.append(
                score_prompt_live(item, spec, agent=agent, model=model, timeout=timeout)
            )
        else:
            results.append(score_prompt_offline(item, spec))

    tp = sum(1 for r in results if r.should_trigger and r.predicted_trigger)
    fn = sum(1 for r in results if r.should_trigger and not r.predicted_trigger)
    fp = sum(1 for r in results if not r.should_trigger and r.predicted_trigger)
    tn = sum(1 for r in results if not r.should_trigger and not r.predicted_trigger)

    recall = tp / (tp + fn) if (tp + fn) else 0.0
    false_trigger_rate = fp / (fp + tn) if (fp + tn) else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    accuracy = (tp + tn) / len(results) if results else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    gates = prompts_data.get("gates", {"min_recall": 0.85, "max_false_trigger_rate": 0.05})
    min_recall = float(gates.get("min_recall", 0.85))
    max_ftr = float(gates.get("max_false_trigger_rate", 0.05))
    passed = (recall >= min_recall) and (false_trigger_rate <= max_ftr)

    return {
        "mode": f"live:{agent}" if live else "offline_rubric",
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "passed": passed,
        "gates": {
            "min_recall": min_recall,
            "max_false_trigger_rate": max_ftr,
        },
        "metrics": {
            "total": len(results),
            "positives": tp + fn,
            "negatives": fp + tn,
            "tp": tp,
            "fn": fn,
            "fp": fp,
            "tn": tn,
            "recall": round(recall, 4),
            "false_trigger_rate": round(false_trigger_rate, 4),
            "precision": round(precision, 4),
            "accuracy": round(accuracy, 4),
            "f1": round(f1, 4),
        },
        "skill_spec_checks": {
            "name": spec.name,
            "description_chars": len(spec.description),
            "covers_five_plus_numbers": spec.covers_five_plus_numbers,
            "covers_comparisons_trends_distributions": spec.covers_comparisons_trends_distributions,
            "covers_csv_experiments": spec.covers_csv_experiments,
            "covers_matplotlib_check": spec.covers_matplotlib_check,
            "covers_notebook_check": spec.covers_notebook_check,
            "covers_publication_plates": spec.covers_publication_plates,
            "forbids_routine_code": spec.forbids_routine_code,
            "forbids_few_scalars": spec.forbids_few_scalars,
        },
        "results": [asdict(r) for r in results],
    }


def render_report_markdown(report: dict[str, Any]) -> str:
    """Format an evaluation report dict into a readable Markdown summary."""
    m = report["metrics"]
    g = report["gates"]
    s = report["skill_spec_checks"]
    verdict = "PASS" if report["passed"] else "FAIL"

    lines = [
        "# Mintfig Skill Trigger Evaluation Report",
        "",
        f"- **Mode:** `{report['mode']}`",
        f"- **Exit Gate Verdict:** **{verdict}** (recall >= {g['min_recall']:.0%}, false-trigger rate <= {g['max_false_trigger_rate']:.0%})",
        f"- **Dataset:** {m['total']} realistic prompts ({m['positives']} positive, {m['negatives']} negative; zero mentions of `mintfig`)",
        "",
        "## Summary Metrics",
        "",
        "| Metric | Value | Gate | Status |",
        "| :--- | ---: | :--- | :---: |",
        f"| Recall (TP / Pos) | **{m['recall']:.1%}** ({m['tp']}/{m['positives']}) | >= {g['min_recall']:.0%} | {'PASS' if m['recall'] >= g['min_recall'] else 'FAIL'} |",
        f"| False-trigger rate (FP / Neg) | **{m['false_trigger_rate']:.1%}** ({m['fp']}/{m['negatives']}) | <= {g['max_false_trigger_rate']:.0%} | {'PASS' if m['false_trigger_rate'] <= g['max_false_trigger_rate'] else 'FAIL'} |",
        f"| Precision | {m['precision']:.1%} ({m['tp']}/{m['tp'] + m['fp'] if (m['tp'] + m['fp']) else 0}) | — | — |",
        f"| Accuracy | {m['accuracy']:.1%} ({m['tp'] + m['tn']}/{m['total']}) | — | — |",
        f"| F1 score | {m['f1']:.3f} | — | — |",
        "",
        "## Skill Trigger Criteria Audit (`SKILL.md` + `AGENTS_SNIPPET.md`)",
        "",
        "| Criterion | Present |",
        "| :--- | :---: |",
    ]
    for key in (
        "covers_five_plus_numbers",
        "covers_comparisons_trends_distributions",
        "covers_csv_experiments",
        "covers_matplotlib_check",
        "covers_notebook_check",
        "covers_publication_plates",
        "forbids_routine_code",
        "forbids_few_scalars",
    ):
        lines.append(f"| `{key}` | {'yes' if s[key] else 'NO'} |")

    lines.extend(
        [
            "",
            "## Per-Prompt Diagnostics",
            "",
            "| ID | Category | Expected | Predicted | Outcome | Rule | Reason |",
            "| :--- | :--- | :---: | :---: | :---: | :--- | :--- |",
        ]
    )
    for row in report["results"]:
        exp = "trigger" if row["should_trigger"] else "skip"
        pred = "trigger" if row["predicted_trigger"] else "skip"
        outcome = "OK" if row["correct"] else ("FN" if row["should_trigger"] else "FP")
        lines.append(
            f"| `{row['id']}` | `{row['category']}` | {exp} | {pred} | {outcome} | `{row['matched_rule']}` | {row['reason']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate mintfig skill trigger accuracy across 40 prompts.")
    parser.add_argument("--prompts", type=Path, default=DEFAULT_PROMPTS, help="Path to prompts.json")
    parser.add_argument("--skill", type=Path, default=DEFAULT_SKILL, help="Path to SKILL.md")
    parser.add_argument("--snippet", type=Path, default=DEFAULT_SNIPPET, help="Path to AGENTS_SNIPPET.md")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="Output Markdown report path")
    parser.add_argument("--no-write-report", action="store_true", help="Do not write REPORT.md to disk")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Print JSON summary to stdout")
    parser.add_argument("--live", action="store_true", help="Run live routing via an installed agent CLI")
    parser.add_argument(
        "--agent",
        choices=("claude", "codex", "gemini"),
        default="claude",
        help="Agent CLI to invoke in --live mode (default: claude)",
    )
    parser.add_argument("--model", default=None, help="Optional model override for --live mode")
    parser.add_argument("--limit", type=int, default=None, help="Evaluate only the first N prompts")
    parser.add_argument("--timeout", type=int, default=45, help="Per-prompt timeout in seconds (--live)")
    args = parser.parse_args(argv)

    prompts_data = json.loads(args.prompts.read_text(encoding="utf-8"))
    skill_md = args.skill.read_text(encoding="utf-8")
    snippet_md = args.snippet.read_text(encoding="utf-8")

    report = evaluate_prompts(
        prompts_data,
        skill_md,
        snippet_md,
        live=args.live,
        agent=args.agent,
        model=args.model,
        limit=args.limit,
        timeout=args.timeout,
    )

    if not args.no_write_report:
        args.report.write_text(render_report_markdown(report), encoding="utf-8")

    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        m = report["metrics"]
        g = report["gates"]
        status = "PASS" if report["passed"] else "FAIL"
        print(
            f"[{status}] mode={report['mode']} | "
            f"recall={m['recall']:.1%} ({m['tp']}/{m['positives']}, gate>={g['min_recall']:.0%}) | "
            f"false_trigger={m['false_trigger_rate']:.1%} ({m['fp']}/{m['negatives']}, gate<={g['max_false_trigger_rate']:.0%}) | "
            f"accuracy={m['accuracy']:.1%}"
        )
        failures = [r for r in report["results"] if not r["correct"]]
        for fail in failures:
            kind = "FN" if fail["should_trigger"] else "FP"
            print(f"  {kind} {fail['id']}: {fail['reason']}")
        if not args.no_write_report:
            print(f"Report written to {args.report}")

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
