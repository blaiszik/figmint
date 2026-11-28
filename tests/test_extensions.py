"""Tests for native Gemini CLI / Antigravity extension, Claude Code MCP wiring, and doc sync."""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    assert match is not None, "Could not find project version in pyproject.toml"
    return match.group(1)


def test_gemini_extension_manifest_structure() -> None:
    ext_path = REPO_ROOT / "gemini-extension.json"
    assert ext_path.is_file()
    data = json.loads(ext_path.read_text(encoding="utf-8"))

    assert data["name"] == "mintfig"
    assert data["version"] == _pyproject_version()
    assert isinstance(data["description"], str) and len(data["description"].strip()) >= 20
    assert data["contextFileName"] == "GEMINI.md"
    assert (REPO_ROOT / data["contextFileName"]).is_file()

    mcp_servers = data["mcpServers"]
    assert isinstance(mcp_servers, dict)
    assert mcp_servers["mintfig"] == {"command": "uvx", "args": ["mintfig", "mcp"]}


def test_gemini_md_context_instructions() -> None:
    gemini_md = REPO_ROOT / "GEMINI.md"
    assert gemini_md.is_file()
    text = gemini_md.read_text(encoding="utf-8")
    assert len(text.strip()) > 200

    for tool_name in ("mint_explain", "mint_check", "mint_plot_file", "mint_card", "mint_chip"):
        assert tool_name in text, f"Missing MCP tool {tool_name} in GEMINI.md"
    for phrase in ("--braille", "mint.explain", "mintchip", "ui://mintfig/figure"):
        assert phrase in text, f"Missing guidance for {phrase} in GEMINI.md"


def test_claude_code_plugin_mcp_config() -> None:
    mcp_path = REPO_ROOT / "plugins" / "claude-code" / ".mcp.json"
    assert mcp_path.is_file()
    data = json.loads(mcp_path.read_text(encoding="utf-8"))

    assert isinstance(data, dict)
    assert "mcpServers" in data
    assert data["mcpServers"]["mintfig"] == {"command": "uvx", "args": ["mintfig", "mcp"]}


def test_version_consistency_across_all_manifests() -> None:
    expected = _pyproject_version()
    assert expected == "0.3.4"

    gemini_ext = json.loads((REPO_ROOT / "gemini-extension.json").read_text(encoding="utf-8"))
    marketplace = json.loads(
        (REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )
    claude_plugin = json.loads(
        (REPO_ROOT / "plugins" / "claude-code" / ".claude-plugin" / "plugin.json").read_text(
            encoding="utf-8"
        )
    )

    assert gemini_ext["version"] == expected
    assert marketplace["metadata"]["version"] == expected
    assert marketplace["plugins"][0]["version"] == expected
    assert claude_plugin["version"] == expected


def test_skill_md_byte_identical_and_documents_new_interfaces() -> None:
    src_skill = REPO_ROOT / "src" / "mintfig" / "assets" / "SKILL.md"
    plugin_skill = REPO_ROOT / "plugins" / "claude-code" / "skills" / "mintfig" / "SKILL.md"

    src_bytes = src_skill.read_bytes()
    plugin_bytes = plugin_skill.read_bytes()
    assert src_bytes == plugin_bytes, "Package SKILL.md and Claude Code plugin SKILL.md differ"

    text = src_bytes.decode("utf-8")
    for token in ("mintfig mcp", "ui://mintfig/figure", "mintfig demo", "mintfig.surface.detect_surface()"):
        assert token in text, f"Missing {token!r} in SKILL.md"


def test_readme_documents_demo_mcp_and_extensions() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    for snippet in (
        "uvx mintfig demo",
        "claude mcp add mintfig -- uvx mintfig mcp",
        "gemini extensions install https://github.com/blaiszik/mintfig",
        "mintfig mcp --install",
    ):
        assert snippet in readme, f"Missing {snippet!r} in README.md"
