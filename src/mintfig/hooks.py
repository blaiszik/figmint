"""Automatic agent PostToolUse hooks for zero-friction ``mint.check`` auditing."""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shlex
import stat
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .figcheck import BLOCKING, check_script
from .skill import detect_installed_agents

HOOK_TARGETS: tuple[str, ...] = ("claude", "cursor", "codex")
HOOK_COMMAND: str = "mintfig hook run"
HOOK_MATCHER: str = "Bash|Write|Edit"

_WRITE_TOOLS = frozenset({"write", "edit", "multiedit", "write_file", "edit_file"})
_BASH_TOOLS = frozenset({"bash", "shell", "run_command", "terminal"})
_SKIP_RUNNERS = frozenset(
    {"pytest", "py.test", "ruff", "mypy", "flake8", "black", "isort", "mintfig", "pylint"}
)
_EXPLAIN_CALL_RE = re.compile(r"\b(?:mint|mintfig)\.explain\s*\(")
_PLAIN_EXPLAIN_CALL_RE = re.compile(r"\bexplain\s*\(")
_MINTFIG_IMPORT_RE = re.compile(r"\b(?:import\s+mintfig|from\s+mintfig(?:\.\w+)*\s+import)\b")
_SHELL_SPLIT_RE = re.compile(r"(?:&&|\|\||;|\||\n)")
_PY_TOKEN_RE = re.compile(r"""(?:"([^"\n]+\.py)"|'([^'\n]+\.py)'|(\S+\.py))""", re.IGNORECASE)


def _claude_hook_entry() -> dict[str, Any]:
    return {
        "matcher": HOOK_MATCHER,
        "hooks": [
            {
                "type": "command",
                "command": HOOK_COMMAND,
            }
        ],
    }


def _is_mintfig_claude_entry(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    cmd = entry.get("command")
    if isinstance(cmd, str) and HOOK_COMMAND in cmd:
        return True
    inner = entry.get("hooks")
    if isinstance(inner, list):
        return any(
            isinstance(h, dict)
            and isinstance(h.get("command"), str)
            and HOOK_COMMAND in h["command"]
            for h in inner
        )
    return False


def _normalize_hook_targets(
    targets: Sequence[str] | None,
    *,
    global_install: bool,
    home_path: Path,
    default_all_for_status: bool = False,
) -> list[str]:
    if targets is None:
        if default_all_for_status:
            return list(HOOK_TARGETS)
        if global_install:
            detected = [t for t in detect_installed_agents(home_path) if t in HOOK_TARGETS]
            return detected if detected else ["claude"]
        return ["claude"]

    expanded: list[str] = []
    for raw in targets:
        key = raw.strip().lower()
        if key == "all":
            expanded.extend(HOOK_TARGETS)
        else:
            expanded.append(key)

    normalized: list[str] = []
    seen: set[str] = set()
    for key in expanded:
        if key not in HOOK_TARGETS:
            valid = ", ".join((*HOOK_TARGETS, "all"))
            raise ValueError(f"Unknown hook target {key!r}. Valid targets: {valid}")
        if key not in seen:
            normalized.append(key)
            seen.add(key)
    return normalized


def _hook_base_dir(root_path: Path, home_path: Path, *, global_install: bool) -> Path:
    return home_path if global_install else root_path


def _claude_settings_path(base: Path) -> Path:
    return base / ".claude" / "settings.json"


def _sidecar_hook_paths(base: Path, target: str) -> tuple[Path, Path]:
    hook_dir = base / f".{target}" / "hooks"
    return hook_dir / "mintfig.json", hook_dir / "mintfig-post-tool.sh"


def _load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected a JSON object in {path}, got {type(parsed).__name__}")  # noqa: TRY004
    return parsed


def _write_json_object(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _install_claude_hook(base: Path) -> Path:
    settings_path = _claude_settings_path(base)
    data = _load_json_object(settings_path)

    hooks = data.get("hooks")
    if hooks is None:
        hooks = {}
        data["hooks"] = hooks
    elif not isinstance(hooks, dict):
        raise ValueError(f"Expected 'hooks' to be an object in {settings_path}")

    post_tool = hooks.get("PostToolUse")
    if post_tool is None:
        post_tool = []
        hooks["PostToolUse"] = post_tool
    elif not isinstance(post_tool, list):
        raise ValueError(f"Expected 'hooks.PostToolUse' to be a list in {settings_path}")

    canonical = _claude_hook_entry()
    new_entries: list[Any] = []
    inserted = False
    for entry in post_tool:
        if _is_mintfig_claude_entry(entry):
            if not inserted:
                new_entries.append(canonical)
                inserted = True
        else:
            new_entries.append(entry)
    if not inserted:
        new_entries.append(canonical)

    hooks["PostToolUse"] = new_entries
    _write_json_object(settings_path, data)
    return settings_path


def _uninstall_claude_hook(base: Path) -> bool:
    settings_path = _claude_settings_path(base)
    if not settings_path.exists():
        return False
    data = _load_json_object(settings_path)
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return False
    post_tool = hooks.get("PostToolUse")
    if not isinstance(post_tool, list):
        return False

    kept = [entry for entry in post_tool if not _is_mintfig_claude_entry(entry)]
    if len(kept) == len(post_tool):
        return False

    if kept:
        hooks["PostToolUse"] = kept
    else:
        hooks.pop("PostToolUse", None)
    if not hooks:
        data.pop("hooks", None)

    _write_json_object(settings_path, data)
    return True


def _claude_hook_installed(base: Path) -> bool:
    settings_path = _claude_settings_path(base)
    if not settings_path.exists():
        return False
    try:
        data = _load_json_object(settings_path)
    except ValueError:
        return False
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return False
    post_tool = hooks.get("PostToolUse")
    if not isinstance(post_tool, list):
        return False
    return any(_is_mintfig_claude_entry(entry) for entry in post_tool)


def _install_sidecar_hook(base: Path, target: str) -> Path:
    manifest_path, script_path = _sidecar_hook_paths(base, target)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "managed_by": "mintfig",
        "event": "PostToolUse",
        "matcher": HOOK_MATCHER,
        "command": HOOK_COMMAND,
        "script": script_path.name,
    }
    _write_json_object(manifest_path, manifest)
    script_body = (
        "#!/usr/bin/env sh\n"
        "# Managed by mintfig (uninstall via `mintfig hook --uninstall`).\n"
        "# Audits Matplotlib/Seaborn plotting scripts via PostToolUse stdin JSON.\n"
        "exec mintfig hook run\n"
    )
    script_path.write_text(script_body, encoding="utf-8")
    current_mode = script_path.stat().st_mode
    script_path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return manifest_path


def _uninstall_sidecar_hook(base: Path, target: str) -> bool:
    manifest_path, script_path = _sidecar_hook_paths(base, target)
    removed = False
    for path in (manifest_path, script_path):
        if path.exists():
            path.unlink()
            removed = True
    return removed


def _sidecar_hook_installed(base: Path, target: str) -> bool:
    manifest_path, script_path = _sidecar_hook_paths(base, target)
    return manifest_path.exists() and script_path.exists()


def install_hook(
    root: str | Path = ".",
    *,
    targets: Sequence[str] | None = ("claude",),
    global_install: bool = False,
    home: str | Path | None = None,
) -> list[Path]:
    """Install mintfig PostToolUse hook(s) idempotently without clobbering user config."""
    home_path = Path(home).expanduser() if home is not None else Path.home()
    normalized = _normalize_hook_targets(targets, global_install=global_install, home_path=home_path)
    base = _hook_base_dir(Path(root), home_path, global_install=global_install)

    written: list[Path] = []
    for target in normalized:
        if target == "claude":
            written.append(_install_claude_hook(base))
        else:
            written.append(_install_sidecar_hook(base, target))
    return written


def uninstall_hook(
    root: str | Path = ".",
    *,
    targets: Sequence[str] | None = ("claude",),
    global_install: bool = False,
    home: str | Path | None = None,
) -> list[Path]:
    """Remove mintfig PostToolUse hook(s), preserving all pre-existing user settings."""
    home_path = Path(home).expanduser() if home is not None else Path.home()
    normalized = _normalize_hook_targets(targets, global_install=global_install, home_path=home_path)
    base = _hook_base_dir(Path(root), home_path, global_install=global_install)

    updated: list[Path] = []
    for target in normalized:
        if target == "claude":
            if _uninstall_claude_hook(base):
                updated.append(_claude_settings_path(base))
        else:
            if _uninstall_sidecar_hook(base, target):
                manifest_path, _ = _sidecar_hook_paths(base, target)
                updated.append(manifest_path)
    return updated


def hook_status(
    root: str | Path = ".",
    *,
    targets: Sequence[str] | None = None,
    global_install: bool = False,
    home: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Report hook installation status for each requested target."""
    home_path = Path(home).expanduser() if home is not None else Path.home()
    normalized = _normalize_hook_targets(
        targets,
        global_install=global_install,
        home_path=home_path,
        default_all_for_status=True,
    )
    base = _hook_base_dir(Path(root), home_path, global_install=global_install)
    scope = "global" if global_install else "project"

    status: dict[str, dict[str, Any]] = {}
    for target in normalized:
        if target == "claude":
            cfg_path = _claude_settings_path(base)
            installed = _claude_hook_installed(base)
        else:
            cfg_path, _ = _sidecar_hook_paths(base, target)
            installed = _sidecar_hook_installed(base, target)
        status[target] = {
            "target": target,
            "scope": scope,
            "installed": installed,
            "path": str(cfg_path),
            "command": HOOK_COMMAND,
        }
    return status


# --------------------------------------------------------------------------- hook runtime


def _extract_py_paths_from_bash(command: str) -> list[str]:
    """Extract Python script paths executed by a shell command string."""
    paths: list[str] = []
    for segment in _SHELL_SPLIT_RE.split(command):
        seg = segment.strip()
        if not seg:
            continue
        try:
            tokens = shlex.split(seg)
        except ValueError:
            tokens = seg.split()
        if not tokens:
            continue

        # Strip leading VAR=val assignments
        idx = 0
        while idx < len(tokens) and "=" in tokens[idx] and not tokens[idx].startswith("-"):
            key, _, _ = tokens[idx].partition("=")
            if key.isidentifier():
                idx += 1
            else:
                break
        cmd_tokens = tokens[idx:]
        if not cmd_tokens:
            continue

        head = Path(cmd_tokens[0]).name.lower()
        if head in _SKIP_RUNNERS:
            continue
        # Skip `uv run pytest ...`, `uvx mintfig ...`, `python -m pytest ...`, `python -c ...`
        if any(Path(tok).name.lower() in _SKIP_RUNNERS for tok in cmd_tokens[:4]):
            continue
        if "-c" in cmd_tokens[:4] or "-m" in cmd_tokens[:3]:
            continue

        found_in_seg: list[str] = []
        for tok in cmd_tokens:
            if tok.startswith("-"):
                continue
            if tok.lower().endswith(".py"):
                found_in_seg.append(tok)
                break  # Only audit the executed script, not trailing .py arguments
        if not found_in_seg:
            for m in _PY_TOKEN_RE.finditer(seg):
                cand = m.group(1) or m.group(2) or m.group(3)
                if cand:
                    found_in_seg.append(cand)
                    break
        paths.extend(found_in_seg)
    return paths


def _extract_candidate_scripts(payload: Mapping[str, Any]) -> list[Path]:
    """Return candidate ``.py`` script paths referenced by a PostToolUse payload."""
    tool_name = str(payload.get("tool_name") or "").strip().lower()
    tool_input = payload.get("tool_input")
    input_map: Mapping[str, Any] = tool_input if isinstance(tool_input, Mapping) else {}

    cwd_raw = payload.get("cwd")
    base_dir = Path(cwd_raw) if isinstance(cwd_raw, str) and cwd_raw.strip() else Path.cwd()

    raw_paths: list[str] = []
    if tool_name in _WRITE_TOOLS:
        for key in ("file_path", "path", "Path", "target_file"):
            val = input_map.get(key)
            if isinstance(val, str) and val.strip().lower().endswith(".py"):
                raw_paths.append(val.strip())
                break
    elif tool_name in _BASH_TOOLS:
        for key in ("command", "cmd", "CommandLine"):
            val = input_map.get(key)
            if isinstance(val, str) and val.strip():
                raw_paths.extend(_extract_py_paths_from_bash(val))
                break
    elif not tool_name:
        # Generic / non-Claude fallback payload
        for key in ("script", "file_path", "path"):
            val = payload.get(key) or input_map.get(key)
            if isinstance(val, str) and val.strip().lower().endswith(".py"):
                raw_paths.append(val.strip())
                break

    resolved: list[Path] = []
    seen: set[Path] = set()
    for raw in raw_paths:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = base_dir / p
        if p not in seen:
            resolved.append(p)
            seen.add(p)
    return resolved


def _should_audit_script(script_path: Path) -> bool:
    """Fast pre-filter: only audit existing matplotlib/seaborn scripts that don't self-audit."""
    if not script_path.is_file():
        return False
    try:
        src = script_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False

    if "matplotlib" not in src and "seaborn" not in src:
        return False
    if _EXPLAIN_CALL_RE.search(src):
        return False
    return not (_MINTFIG_IMPORT_RE.search(src) and _PLAIN_EXPLAIN_CALL_RE.search(src))


def _blocking_issues(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    issues = report.get("issues") or []
    blocking = [
        i
        for i in issues
        if isinstance(i, dict)
        and (i.get("severity") == "error" or i.get("rule") in BLOCKING)
    ]
    if blocking:
        return blocking
    return [i for i in issues if isinstance(i, dict)]


def _format_hook_feedback(script_path: Path, failing_reports: Sequence[Mapping[str, Any]]) -> str:
    lines: list[str] = [
        f"mintfig figure check found blocking issues in {script_path.name} (fix before sharing):"
    ]
    for idx, report in enumerate(failing_reports, start=1):
        fig_label = report.get("path") or f"figure {idx}"
        issues = _blocking_issues(report)
        if not issues:
            lines.append(f"- {fig_label}: ship=False")
            continue
        for issue in issues:
            rule = issue.get("rule", "issue")
            msg = issue.get("message", "").strip()
            hint = issue.get("fix_hint", "").strip()
            bullet = f"- [{fig_label}] {rule}: {msg}"
            if hint:
                bullet += f" | fix_hint: {hint}"
            lines.append(bullet)
    return "\n".join(lines)


def _is_claude_payload(payload: Mapping[str, Any]) -> bool:
    return bool(payload.get("tool_name")) or payload.get("hook_event_name") == "PostToolUse"


def run_hook(stdin_text: str | None = None) -> tuple[int, str]:
    """Execute the PostToolUse figure-audit hook.

    Reads a PostToolUse JSON payload from ``stdin_text`` (or ``sys.stdin`` when
    ``None``), pre-filters to plain Matplotlib/Seaborn Python scripts, and runs
    :func:`mintfig.figcheck.check_script`.

    Never raises or returns a non-zero exit code on malformed stdin or script
    failures so an agent session is never disrupted.

    Returns
    -------
    tuple[int, str]
        ``(exit_code, output_text)``. ``output_text`` is empty when there is
        nothing to fix.
    """
    if _env_has_hook_disabled():
        return 0, ""

    if stdin_text is None:
        try:
            if sys.stdin is None or sys.stdin.isatty():
                return 0, ""
            stdin_text = sys.stdin.read()
        except Exception:  # noqa: BLE001
            return 0, ""

    if not stdin_text or not stdin_text.strip():
        return 0, ""

    try:
        payload = json.loads(stdin_text)
    except (json.JSONDecodeError, TypeError):
        return 0, ""

    if not isinstance(payload, Mapping):
        return 0, ""

    candidates = _extract_candidate_scripts(payload)
    if not candidates:
        return 0, ""

    feedback_blocks: list[str] = []
    for script_path in candidates:
        if not _should_audit_script(script_path):
            continue
        try:
            with (
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                reports = check_script(script_path)
        except (Exception, SystemExit):  # noqa: BLE001, S112 - hooks must never crash an agent session
            continue
        failing = [r for r in reports if not r.get("ship", True)]
        if failing:
            feedback_blocks.append(_format_hook_feedback(script_path, failing))

    if not feedback_blocks:
        return 0, ""

    summary = "\n\n".join(feedback_blocks)
    if _is_claude_payload(payload):
        hook_out = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": summary,
            }
        }
        return 0, json.dumps(hook_out, ensure_ascii=False)
    return 0, summary


def format_hook_status(status: Mapping[str, Mapping[str, Any]]) -> str:
    """Format :func:`hook_status` output for human-readable terminal display."""
    lines: list[str] = []
    for target, info in status.items():
        state = "installed" if info["installed"] else "not installed"
        lines.append(f"{target} ({info['scope']}): {state} — {info['path']}")
    return "\n".join(lines)


def _env_has_hook_disabled() -> bool:
    return os.environ.get("MINTFIG_DISABLE_HOOK", "").strip().lower() in {"1", "true", "yes"}
