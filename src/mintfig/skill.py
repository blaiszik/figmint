"""Bundled agent skill and project instruction installers for mintfig."""

from __future__ import annotations

from collections.abc import Sequence
from importlib import resources
from pathlib import Path

VALID_TARGETS: tuple[str, ...] = (
    "claude",
    "antigravity",
    "cursor",
    "codex",
    "agents-md",
    "claude-md",
)

MARKER_START: str = "<!-- mintfig:start -->"
MARKER_END: str = "<!-- mintfig:end -->"


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


def _strip_yaml_frontmatter(markdown: str) -> str:
    """Remove leading YAML frontmatter block if present."""
    if not markdown.startswith("---\n"):
        return markdown
    end = markdown.find("\n---\n", 4)
    if end == -1:
        return markdown
    return markdown[end + len("\n---\n") :].lstrip("\n")


def _build_cursor_mdc(skill_md: str) -> str:
    """Wrap the skill body with valid Cursor .mdc rule frontmatter."""
    body = _strip_yaml_frontmatter(skill_md).rstrip() + "\n"
    frontmatter = (
        "---\n"
        "description: Explain data with message-first chat figures and tables (mint.explain, mint.table), "
        "or generate publication-ready Nature, Science, Cell, PNAS, and NeurIPS scientific figures with mintfig\n"
        "globs:\n"
        '  - "**/*.py"\n'
        '  - "**/*.csv"\n'
        '  - "**/*.json"\n'
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


def install_skill(
    root: str | Path = ".",
    *,
    targets: Sequence[str] = ("claude", "antigravity", "agents-md"),
) -> list[Path]:
    """Install mintfig agent skills and/or project instruction snippets under ``root``.

    Parameters
    ----------
    root:
        Target project root directory.
    targets:
        One or more target identifiers from :data:`VALID_TARGETS`:
        ``"claude"``, ``"antigravity"``, ``"cursor"``, ``"codex"``,
        ``"agents-md"``, ``"claude-md"``.

    Returns
    -------
    list[Path]
        Paths created or updated, in the order requested.
    """
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in targets:
        key = raw.strip().lower()
        if key not in VALID_TARGETS:
            valid = ", ".join(VALID_TARGETS)
            raise ValueError(f"Unknown skill install target {raw!r}. Valid targets: {valid}")
        if key not in seen:
            normalized.append(key)
            seen.add(key)

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
            written.append(_write_skill_dir(root_path / ".claude" / "skills" / "mintfig" / "SKILL.md"))
        elif target == "antigravity":
            written.append(_write_skill_dir(root_path / ".agents" / "skills" / "mintfig" / "SKILL.md"))
        elif target == "cursor":
            dest = root_path / ".cursor" / "rules" / "mintfig.mdc"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(_build_cursor_mdc(skill_md), encoding="utf-8")
            written.append(dest)
        elif target == "codex":
            written.append(_write_skill_dir(root_path / ".codex" / "skills" / "mintfig" / "SKILL.md"))
        elif target == "agents-md":
            written.append(_upsert_marked_block(root_path / "AGENTS.md", snippet))
        elif target == "claude-md":
            written.append(_upsert_marked_block(root_path / "CLAUDE.md", snippet))

    return written
