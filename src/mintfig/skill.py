"""Bundled agent skill and project instruction installers for mintfig."""

from __future__ import annotations

from collections.abc import Sequence
from importlib import resources
from pathlib import Path

VALID_TARGETS: tuple[str, ...] = (
    "claude",
    "antigravity",
    "gemini",
    "cursor",
    "codex",
    "copilot",
    "agents-md",
    "claude-md",
)

GLOBAL_TARGETS: tuple[str, ...] = (
    "claude",
    "antigravity",
    "gemini",
    "cursor",
    "codex",
)

_DEFAULT_LOCAL_TARGETS: tuple[str, ...] = ("claude", "antigravity", "agents-md")
_DEFAULT_GLOBAL_FALLBACK: tuple[str, ...] = ("claude", "antigravity")

_AGENT_HOME_DIRS: tuple[tuple[str, str], ...] = (
    ("claude", ".claude"),
    ("codex", ".codex"),
    ("antigravity", ".gemini"),
    ("gemini", ".gemini"),
    ("cursor", ".cursor"),
)

MARKER_START: str = "<!-- mintfig:start -->"
MARKER_END: str = "<!-- mintfig:end -->"


def detect_installed_agents(home: str | Path | None = None) -> list[str]:
    """Return agent targets whose standard home directory exists under ``home``.

    Checks ``~/.claude`` (``"claude"``), ``~/.codex`` (``"codex"``),
    ``~/.gemini`` (``"antigravity"``, ``"gemini"``), and ``~/.cursor`` (``"cursor"``).
    """
    home_path = Path(home).expanduser() if home is not None else Path.home()
    detected: list[str] = []
    for target, dirname in _AGENT_HOME_DIRS:
        if (home_path / dirname).is_dir():
            detected.append(target)
    return detected


def get_skill_markdown() -> str:
    """Return the bundled mintfig SKILL.md content."""
    return resources.files("mintfig.assets").joinpath("SKILL.md").read_text(encoding="utf-8")


def get_agents_snippet() -> str:
    """Return the bundled marker-wrapped AGENTS.md / CLAUDE.md snippet."""
    return (
        resources.files("mintfig.assets")
        .joinpath("AGENTS_SNIPPET.md")
        .read_text(encoding="utf-8")
    )


def get_skill_references() -> dict[str, str]:
    """Return bundled skill reference markdown files keyed by filename."""
    ref_dir = resources.files("mintfig.assets").joinpath("references")
    if not ref_dir.is_dir():
        return {}
    out: dict[str, str] = {}
    for entry in sorted(ref_dir.iterdir(), key=lambda p: p.name):
        if entry.name.endswith(".md"):
            out[entry.name] = entry.read_text(encoding="utf-8")
    return out


def get_full_skill_bundle() -> str:
    """Return ``SKILL.md`` followed by all bundled ``references/*.md`` with section headers."""
    parts: list[str] = [get_skill_markdown().rstrip()]
    for fname, content in get_skill_references().items():
        header = f"---\n\n# Reference: `references/{fname}`\n\n"
        parts.append(header + content.strip())
    return "\n\n".join(parts) + "\n"


def _strip_yaml_frontmatter(markdown: str) -> str:
    """Remove leading YAML frontmatter block if present."""
    if not markdown.startswith("---\n"):
        return markdown
    end = markdown.find("\n---\n", 4)
    if end == -1:
        return markdown
    return markdown[end + len("\n---\n") :].lstrip("\n")


def _build_cursor_mdc(skill_md: str) -> str:
    """Wrap the skill body with semantic Cursor .mdc rule frontmatter (no globs)."""
    body = _strip_yaml_frontmatter(skill_md).rstrip() + "\n"
    frontmatter = (
        "---\n"
        "description: Explain data with message-first chat figures and tables (mint.explain, mint.table), "
        "or generate publication-ready Nature, Science, Cell, PNAS, and NeurIPS scientific figures with mintfig\n"
        "alwaysApply: false\n"
        "---\n\n"
    )
    return frontmatter + body


def _upsert_marked_block(path: Path, snippet: str) -> Path:
    """Idempotently insert or replace the marker-wrapped snippet inside ``path``."""
    block = snippet.strip()
    if MARKER_START not in block or MARKER_END not in block:
        block = f"{MARKER_START}\n{block}\n{MARKER_END}"

    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(block + "\n", encoding="utf-8")
        return path

    existing = path.read_text(encoding="utf-8")
    start_idx = existing.find(MARKER_START)
    end_idx = existing.find(MARKER_END, start_idx + len(MARKER_START)) if start_idx != -1 else -1

    if start_idx != -1 and end_idx != -1:
        updated = existing[:start_idx] + block + existing[end_idx + len(MARKER_END) :]
    elif not existing.strip():
        updated = block + "\n"
    else:
        sep = "\n\n" if not existing.endswith("\n") else ("\n" if not existing.endswith("\n\n") else "")
        updated = existing + sep + block + "\n"

    path.write_text(updated, encoding="utf-8")
    return path


def _normalize_targets(
    targets: Sequence[str] | None,
    *,
    global_install: bool,
    home_path: Path,
) -> list[str]:
    if targets is None:
        if global_install:
            detected = detect_installed_agents(home_path)
            return detected if detected else list(_DEFAULT_GLOBAL_FALLBACK)
        return list(_DEFAULT_LOCAL_TARGETS)

    expanded: list[str] = []
    for raw in targets:
        key = raw.strip().lower()
        if key == "all":
            expanded.extend(GLOBAL_TARGETS if global_install else VALID_TARGETS)
        else:
            expanded.append(key)

    normalized: list[str] = []
    seen: set[str] = set()
    for key in expanded:
        if key not in VALID_TARGETS:
            valid = ", ".join((*VALID_TARGETS, "all"))
            raise ValueError(f"Unknown skill install target {key!r}. Valid targets: {valid}")
        if key not in seen:
            normalized.append(key)
            seen.add(key)
    return normalized


def install_chip_skill(
    root: str | Path = ".",
    *,
    targets: Sequence[str] | None = None,
    global_install: bool = False,
    home: str | Path | None = None,
) -> list[Path]:
    """Install the companion ``mintchip`` agent skill when ``mintchip`` is importable.

    Returns an empty list when ``mintchip`` is not installed.
    """
    try:
        from mintchip import skill as chip_skill  # type: ignore[import-not-found]
    except ImportError:
        return []

    chip_valid = set(getattr(chip_skill, "VALID_TARGETS", ()))
    chip_targets: list[str] | None
    if targets is None:
        chip_targets = None
    else:
        raw_list = [t.strip().lower() for t in targets]
        if "all" in raw_list:
            chip_targets = ["all"]
        else:
            chip_targets = [t for t in raw_list if t in chip_valid]
            if not chip_targets:
                return []

    return list(
        chip_skill.install_skill(
            root=root,
            targets=chip_targets,
            global_install=global_install,
            home=home,
        )
    )


def install_skill(
    root: str | Path = ".",
    *,
    targets: Sequence[str] | None = None,
    global_install: bool = False,
    home: str | Path | None = None,
    include_chip: bool = False,
) -> list[Path]:
    """Install mintfig agent skills and/or project instruction snippets.

    Parameters
    ----------
    root:
        Target project root directory (used when ``global_install=False``).
    targets:
        One or more target identifiers from :data:`VALID_TARGETS` or ``"all"``:
        ``"claude"``, ``"antigravity"``, ``"gemini"``, ``"cursor"``, ``"codex"``,
        ``"copilot"``, ``"agents-md"``, ``"claude-md"``.
        When omitted, project-local installs default to
        ``("claude", "antigravity", "agents-md")``; global installs auto-detect
        installed agents via :func:`detect_installed_agents` and fall back to
        ``("claude", "antigravity")``.
    global_install:
        When ``True``, install into user-home agent directories under ``home``
        (default :meth:`pathlib.Path.home`): ``~/.claude/skills/mintfig/``,
        ``~/.codex/skills/mintfig/``, ``~/.gemini/config/skills/mintfig/``,
        ``~/.gemini/skills/mintfig/``, and ``~/.cursor/rules/mintfig.mdc``.
    home:
        Optional home directory override for ``global_install=True``.
    include_chip:
        When ``True`` and ``mintchip`` is importable, also install the companion
        ``mintchip`` skill for the matching targets.

    Returns
    -------
    list[Path]
        Paths created or updated, in the order requested.
    """
    home_path = Path(home).expanduser() if home is not None else Path.home()
    normalized = _normalize_targets(targets, global_install=global_install, home_path=home_path)

    root_path = Path(root)
    skill_md = get_skill_markdown()
    references = get_skill_references()
    snippet = get_agents_snippet()
    written: list[Path] = []

    def _write_skill_dir(dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(skill_md, encoding="utf-8")
        if references:
            ref_root = dest.parent / "references"
            ref_root.mkdir(parents=True, exist_ok=True)
            for fname, content in references.items():
                (ref_root / fname).write_text(content, encoding="utf-8")
        return dest

    for target in normalized:
        if target == "claude":
            base = home_path if global_install else root_path
            written.append(_write_skill_dir(base / ".claude" / "skills" / "mintfig" / "SKILL.md"))
        elif target == "antigravity":
            if global_install:
                dest = home_path / ".gemini" / "config" / "skills" / "mintfig" / "SKILL.md"
            else:
                dest = root_path / ".agents" / "skills" / "mintfig" / "SKILL.md"
            written.append(_write_skill_dir(dest))
        elif target == "gemini":
            base = home_path if global_install else root_path
            written.append(_write_skill_dir(base / ".gemini" / "skills" / "mintfig" / "SKILL.md"))
        elif target == "cursor":
            base = home_path if global_install else root_path
            dest = base / ".cursor" / "rules" / "mintfig.mdc"
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Cursor reads only the .mdc rule, so the reference files go beside it
            # and the rule points at them by path.
            ref_rel = ".cursor/rules/mintfig/references/"
            ref_display = f"~/{ref_rel}" if global_install else ref_rel
            body = skill_md.replace("`references/", f"`{ref_display}")
            dest.write_text(_build_cursor_mdc(body), encoding="utf-8")
            for fname, content in references.items():
                ref_path = base / ref_rel / fname
                ref_path.parent.mkdir(parents=True, exist_ok=True)
                ref_path.write_text(content, encoding="utf-8")
            written.append(dest)
        elif target == "codex":
            base = home_path if global_install else root_path
            written.append(_write_skill_dir(base / ".codex" / "skills" / "mintfig" / "SKILL.md"))
        elif target == "copilot":
            base = home_path if global_install else root_path
            dest = base / ".github" / "copilot-instructions.md"
            written.append(_upsert_marked_block(dest, snippet))
        elif target == "agents-md":
            dest = (home_path / ".codex" / "AGENTS.md") if global_install else (root_path / "AGENTS.md")
            written.append(_upsert_marked_block(dest, snippet))
        elif target == "claude-md":
            dest = (home_path / ".claude" / "CLAUDE.md") if global_install else (root_path / "CLAUDE.md")
            written.append(_upsert_marked_block(dest, snippet))

    if include_chip:
        written.extend(
            install_chip_skill(
                root=root,
                targets=targets,
                global_install=global_install,
                home=home,
            )
        )

    return written
