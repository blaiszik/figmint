"""GitHub PR figure cards and ``mintfig check`` PR comment formatters.

Provides two workflow helpers for engineering and research teams shipping figures
in pull requests:

- :func:`save_pr_card` renders both light and dark PNG variants of a
  :class:`~mintfig.Explanation` (or saved mintfig PNG / JSON spec) and emits
  ready-to-paste GitHub Markdown using native ``<picture>`` media queries plus
  collapsible computed facts and reproduce commands.
- :func:`format_check_pr_comment` turns one or more ``mintfig check --json``
  reports (Python scripts, Jupyter notebooks, or journal PDF preflights) into a
  compact GitHub PR comment or Actions Step Summary.
"""

from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ._explain.layout import Explanation, _reader_path, load

__all__ = [
    "format_check_pr_comment",
    "save_pr_card",
]


def _normalize_stem(name: str) -> str:
    cleaned = name.strip()
    if cleaned.lower().endswith(".png"):
        cleaned = cleaned[:-4]
    cleaned = cleaned.strip("/\\")
    if not cleaned:
        return "figure"
    return Path(cleaned).name


def _format_ref(path: Path, repo_prefix: str | None) -> str:
    if repo_prefix is None:
        return _reader_path(path)
    prefix = repo_prefix.strip().rstrip("/")
    if not prefix:
        return path.name
    return f"{prefix}/{path.name}"


def _collect_facts(summary: Mapping[str, Any]) -> list[str]:
    panels = summary.get("panels") or []
    multi = len(panels) > 1
    out: list[str] = []
    for panel in panels:
        facts = panel.get("facts") or []
        label = panel.get("title") or (f"Panel {panel.get('key')}" if panel.get("key") else None)
        for fact in facts:
            text = str(fact).strip()
            if not text:
                continue
            if multi and label:
                out.append(f"**{label}:** {text}")
            else:
                out.append(text)
    return out


def _escape_md_cell(value: Any) -> str:
    text = " ".join(str(value).split())
    return text.replace("|", "\\|")


def save_pr_card(
    exp_or_path: Explanation | str | Path | Mapping[str, Any],
    out_dir: str | Path,
    *,
    name: str = "figure",
    repo_prefix: str | None = None,
    light_style: str | None = None,
    dark_style: str = "dark",
    include_facts: bool = True,
    include_reproduce: bool = True,
) -> dict[str, Any]:
    """Render light + dark PNGs and ready-to-paste GitHub PR Markdown.

    Parameters
    ----------
    exp_or_path:
        A live :class:`~mintfig.Explanation`, a path to a mintfig PNG (with
        embedded ``mintfig:spec``) or JSON spec file, or a spec mapping.
    out_dir:
        Output directory where ``<name>.light.png``, ``<name>.dark.png``, and
        ``<name>.md`` are written.
    name:
        Base filename stem (default ``"figure"``).
    repo_prefix:
        Optional URL or repository-relative directory prefix used in Markdown
        ``srcset`` / ``src`` attributes (e.g. ``"docs/figures"`` or
        ``"https://raw.githubusercontent.com/org/repo/main/docs/figures"``).
    light_style:
        Style for the light PNG. Defaults to the input figure's style, or
        ``"mintfig"`` when the input figure is already using ``dark_style`` /
        ``"dark"``.
    dark_style:
        Style for the dark PNG (default ``"dark"``).
    include_facts:
        Include computed per-panel facts inside the ``<details>`` block.
    include_reproduce:
        Include copy-paste ``mintfig explain`` reproduce commands inside the
        ``<details>`` block.

    Returns
    -------
    dict[str, Any]
        Structured result containing ``ok``, ``ship``, paths, refs, ready-to-paste
        ``markdown``, and the underlying ``light`` / ``dark`` summaries.
    """
    import matplotlib.pyplot as plt

    owned_figs: list[Any] = []
    try:
        if isinstance(exp_or_path, Explanation):
            base_exp = exp_or_path
        else:
            base_exp = load(exp_or_path)
            owned_figs.append(base_exp.fig)

        base_spec = base_exp.to_spec()
        base_style = base_exp.theme.name or "mintfig"
        if light_style is not None:
            resolved_light_style = light_style
        elif base_style in {"dark", dark_style}:
            resolved_light_style = "mintfig"
        else:
            resolved_light_style = base_style

        if resolved_light_style == base_style:
            light_exp = base_exp
        else:
            light_spec = {**base_spec, "style": resolved_light_style}
            light_exp = load(light_spec, strict=base_exp.strict)
            owned_figs.append(light_exp.fig)

        dark_spec = {**base_spec, "style": dark_style}
        dark_exp = load(dark_spec, strict=base_exp.strict)
        owned_figs.append(dark_exp.fig)

        target_dir = Path(out_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        stem = _normalize_stem(name)
        light_path = target_dir / f"{stem}.light.png"
        dark_path = target_dir / f"{stem}.dark.png"
        md_path = target_dir / f"{stem}.md"

        light_summary = light_exp.save(light_path)
        dark_summary = dark_exp.save(dark_path)

        light_ref = _format_ref(light_path, repo_prefix)
        dark_ref = _format_ref(dark_path, repo_prefix)

        takeaway = light_exp.takeaway
        alt_text = light_exp.alt_text
        caption = (light_summary.get("deliver") or {}).get("caption")
        display_width = int(light_exp.display_width_px)

        alt_escaped = html.escape(alt_text, quote=True)
        light_ref_escaped = html.escape(light_ref, quote=True)
        dark_ref_escaped = html.escape(dark_ref, quote=True)

        md_parts: list[str] = [
            f"**{takeaway}**",
            "",
            "<picture>",
            f'  <source media="(prefers-color-scheme: dark)" srcset="{dark_ref_escaped}">',
            f'  <source media="(prefers-color-scheme: light)" srcset="{light_ref_escaped}">',
            f'  <img alt="{alt_escaped}" src="{light_ref_escaped}" width="{display_width}">',
            "</picture>",
        ]
        if caption:
            md_parts.extend(["", f"*{caption}*"])

        facts = _collect_facts(light_summary) if include_facts else []
        repro_target = (
            light_path.name if light_ref.startswith(("http://", "https://")) else light_ref
        )

        if include_facts or include_reproduce:
            if include_facts and include_reproduce:
                summary_label = "Numbers &amp; reproduce (mintfig)"
            elif include_facts:
                summary_label = "Numbers (mintfig)"
            else:
                summary_label = "Reproduce (mintfig)"

            details_lines: list[str] = ["", "<details>", f"<summary>{summary_label}</summary>", ""]
            if include_facts:
                if facts:
                    details_lines.append("**Computed facts:**")
                    details_lines.extend(f"- {fact}" for fact in facts)
                else:
                    details_lines.append("_No numeric panel facts computed._")
                if light_exp.source:
                    details_lines.extend(["", f"**Source:** {light_exp.source}"])
            if include_reproduce:
                if include_facts:
                    details_lines.append("")
                details_lines.extend(
                    [
                        "**Reproduce from embedded `mintfig:spec`:**",
                        "```bash",
                        f"mintfig explain {repro_target} --show-spec",
                        f"mintfig explain {repro_target} --out {stem}.light.png",
                        f"mintfig explain {repro_target} --style {dark_style} --out {stem}.dark.png",
                        "```",
                    ]
                )
            details_lines.append("</details>")
            md_parts.extend(details_lines)

        markdown = "\n".join(md_parts)
        md_path.write_text(markdown + "\n", encoding="utf-8")

        return {
            "ok": bool(light_summary["ok"] and dark_summary["ok"]),
            "ship": bool(light_summary["ship"] and dark_summary["ship"]),
            "name": stem,
            "takeaway": takeaway,
            "caption": caption,
            "alt_text": alt_text,
            "light_path": str(light_path.resolve()),
            "dark_path": str(dark_path.resolve()),
            "markdown_path": str(md_path.resolve()),
            "light_ref": light_ref,
            "dark_ref": dark_ref,
            "light_style": resolved_light_style,
            "dark_style": dark_style,
            "markdown": markdown,
            "light": dict(light_summary),
            "dark": dict(dark_summary),
            "issues": {
                "light": list(light_summary.get("issues", [])),
                "dark": list(dark_summary.get("issues", [])),
            },
        }
    finally:
        for fig in owned_figs:
            plt.close(fig)


def _flatten_reports(reports: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Normalize raw ``mintfig check --json`` wrappers, FigureChecks, and PDF preflights."""
    flattened: list[dict[str, Any]] = []
    for item in reports:
        if not isinstance(item, Mapping):
            continue
        figures = item.get("figures")
        if isinstance(figures, Sequence) and not isinstance(figures, (str, bytes)):
            parent_target = item.get("target") or item.get("source") or item.get("path")
            for fig_rep in figures:
                if not isinstance(fig_rep, Mapping):
                    continue
                entry = dict(fig_rep)
                if not entry.get("path") and parent_target:
                    entry["path"] = str(parent_target)
                elif parent_target and "source" not in entry:
                    entry["source"] = str(parent_target)
                flattened.append(entry)
        else:
            flattened.append(dict(item))
    return flattened


def _report_passed(report: Mapping[str, Any]) -> bool:
    if report.get("error"):
        return False
    if "ship" in report:
        return bool(report["ship"])
    if "passed" in report:
        return bool(report["passed"])
    if "ok" in report:
        return bool(report["ok"])
    return not bool(report.get("issues"))


def _format_display_cell(report: Mapping[str, Any]) -> str:
    disp = report.get("display")
    if isinstance(disp, Mapping) and disp:
        shown = disp.get("shown_px")
        width_px = disp.get("width_px")
        min_text = disp.get("min_text_px")
        parts: list[str] = []
        if isinstance(shown, Sequence) and len(shown) == 2:
            parts.append(f"{shown[0]}×{shown[1]} px")
        elif width_px is not None:
            parts.append(f"{width_px} px")
        if min_text is not None:
            parts.append(f"min text {min_text} px")
        if parts:
            return " · ".join(parts)

    dims = report.get("dimensions_mm")
    if isinstance(dims, Mapping) and "width" in dims and "height" in dims:
        journal = report.get("journal")
        size = f"{dims['width']}×{dims['height']} mm"
        return f"{size} ({journal})" if journal else size
    if "width_mm" in report and "height_mm" in report:
        journal = report.get("journal")
        size = f"{report['width_mm']:.1f}×{report['height_mm']:.1f} mm"
        return f"{size} ({journal})" if journal else size
    return "—"


def _claim_mismatches(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    claim = report.get("claim")
    if not isinstance(claim, Mapping):
        return []
    if claim.get("hedged"):
        return []
    return [
        num
        for num in claim.get("numbers") or []
        if isinstance(num, Mapping) and not num.get("found")
    ]


def _format_claims_cell(report: Mapping[str, Any]) -> str:
    claim = report.get("claim")
    if not isinstance(claim, Mapping) or not claim:
        return "—"
    numbers = [n for n in (claim.get("numbers") or []) if isinstance(n, Mapping)]
    if not numbers:
        return "no numbers"
    if claim.get("hedged"):
        return f"{len(numbers)} hedged"
    mismatches = [n for n in numbers if not n.get("found")]
    if not mismatches:
        return f"{len(numbers)}/{len(numbers)} matched"
    preview = ", ".join(f"`{m.get('text', '?')}`" for m in mismatches[:2])
    extra = f" +{len(mismatches) - 2}" if len(mismatches) > 2 else ""
    return f"{len(mismatches)} mismatch ({preview}{extra})"


def _format_issues_cell(report: Mapping[str, Any]) -> str:
    if report.get("error"):
        return "`script_error`"
    issues = [i for i in (report.get("issues") or []) if isinstance(i, Mapping)]
    if not issues:
        return "0"
    rules = list(dict.fromkeys(str(i.get("rule", "issue")) for i in issues))
    preview = ", ".join(f"`{r}`" for r in rules[:3])
    extra = f" +{len(rules) - 3}" if len(rules) > 3 else ""
    return f"{len(issues)} ({preview}{extra})"


def format_check_pr_comment(
    reports: Sequence[Mapping[str, Any]],
    *,
    title: str = "mintfig check",
) -> str:
    """Format ``mintfig check --json`` reports into a compact GitHub PR Markdown comment.

    Accepts a sequence of individual :class:`~mintfig.figcheck.FigureCheck` dicts,
    raw ``mintfig check --json`` wrapper objects (``{"figures": [...]}``), PDF
    preflight report dicts, or script-error records.
    """
    entries = _flatten_reports(reports)
    if not entries:
        return f"### {title}\n\nNo figures checked."

    passed_count = sum(1 for r in entries if _report_passed(r))
    failed_count = len(entries) - passed_count
    total_issues = sum(
        len(r.get("issues") or []) + (1 if r.get("error") else 0) for r in entries
    )

    lines: list[str] = [f"### {title}", ""]
    if failed_count == 0 and total_issues == 0:
        noun = "figure" if len(entries) == 1 else "figures"
        lines.append(f"✅ **All {len(entries)} {noun} ready to ship** — 0 issues found.")
    elif failed_count == 0:
        noun = "figure" if len(entries) == 1 else "figures"
        lines.append(
            f"✅ **All {len(entries)} {noun} ready to ship** "
            f"({total_issues} non-blocking warning{'s' if total_issues != 1 else ''})."
        )
    else:
        lines.append(
            f"❌ **{failed_count} of {len(entries)} "
            f"{'figure needs' if failed_count == 1 else 'figures need'} fixes before shipping** "
            f"({passed_count} `SHIP`, {failed_count} `FIX FIRST`)."
        )

    lines.extend(
        [
            "",
            "| Figure | Status | Display / Size | Claims | Issues |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
    )

    detail_blocks: list[list[str]] = []
    for idx, report in enumerate(entries, start=1):
        label = str(
            report.get("path")
            or report.get("target")
            or report.get("source")
            or f"figure {idx}"
        )
        ok = _report_passed(report)
        badge = "✅ `SHIP`" if ok else "❌ `FIX FIRST`"
        display_cell = _format_display_cell(report)
        claims_cell = _format_claims_cell(report)
        issues_cell = _format_issues_cell(report)

        lines.append(
            f"| `{_escape_md_cell(label)}` | {badge} | "
            f"{_escape_md_cell(display_cell)} | {claims_cell} | {issues_cell} |"
        )

        mismatches = _claim_mismatches(report)
        issues = [i for i in (report.get("issues") or []) if isinstance(i, Mapping)]
        err_msg = report.get("error")
        if mismatches or issues or err_msg:
            block: list[str] = [f"#### `{label}` — {'SHIP' if ok else 'FIX FIRST'}"]
            if err_msg:
                block.append(f"- **Error:** {err_msg}")
            if mismatches:
                claim = report.get("claim") or {}
                claim_text = claim.get("text")
                if claim_text:
                    block.append(f"- **Claim:** _{claim_text}_")
                for num in mismatches:
                    nearest = num.get("nearest")
                    closest_part = f" — closest in data: `{nearest}`" if nearest else ""
                    block.append(
                        f"  - Mismatch: **`{num.get('text', '?')}`** not found in plotted data"
                        f"{closest_part}"
                    )
            for issue in issues:
                rule = issue.get("rule", "issue")
                severity = issue.get("severity", "warning")
                message = issue.get("message", "")
                fix_hint = issue.get("fix_hint")
                block.append(f"- **`{rule}`** ({severity}): {message}")
                if fix_hint:
                    block.append(f"  - **Fix:** {fix_hint}")
            detail_blocks.append(block)

    if detail_blocks:
        lines.extend(["", "---", ""])
        for i, block in enumerate(detail_blocks):
            if i > 0:
                lines.append("")
            lines.extend(block)

    return "\n".join(lines)
