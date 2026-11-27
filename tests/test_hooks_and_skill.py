"""Comprehensive tests for global skill installation, PostToolUse hooks, and Claude Code plugin."""

from __future__ import annotations

import io
import json
import os
import stat
import sys
from pathlib import Path

import matplotlib
import pytest

matplotlib.use("Agg")

from mintfig.cli import main as cli_main
from mintfig.hooks import (
    HOOK_COMMAND,
    HOOK_TARGETS,
    hook_status,
    install_hook,
    run_hook,
    uninstall_hook,
)
from mintfig.skill import (
    GLOBAL_TARGETS,
    VALID_TARGETS,
    detect_installed_agents,
    get_full_skill_bundle,
    get_skill_markdown,
    get_skill_references,
    install_skill,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- Skill tests


class TestGlobalSkillAndBundle:
    def test_detect_installed_agents_checks_standard_home_dirs(self, tmp_path: Path) -> None:
        assert detect_installed_agents(home=tmp_path) == []

        (tmp_path / ".claude").mkdir()
        (tmp_path / ".cursor").mkdir()
        assert detect_installed_agents(home=tmp_path) == ["claude", "cursor"]

        (tmp_path / ".codex").mkdir()
        (tmp_path / ".gemini").mkdir()
        assert detect_installed_agents(home=tmp_path) == [
            "claude",
            "codex",
            "antigravity",
            "cursor",
        ]

    def test_global_install_auto_detects_or_falls_back(self, tmp_path: Path) -> None:
        # Empty home -> falls back to claude + antigravity
        home_empty = tmp_path / "home_empty"
        home_empty.mkdir()
        written_fallback = install_skill(global_install=True, home=home_empty)
        assert written_fallback == [
            home_empty / ".claude" / "skills" / "mintfig" / "SKILL.md",
            home_empty / ".gemini" / "config" / "skills" / "mintfig" / "SKILL.md",
        ]
        for path in written_fallback:
            assert path.is_file()
            assert (path.parent / "references" / "science.md").is_file()
            assert (path.parent / "references" / "recipes.md").is_file()
            assert (path.parent / "references" / "publication.md").is_file()

        # Home with codex + cursor detected -> installs only codex + cursor
        home_detected = tmp_path / "home_detected"
        (home_detected / ".codex").mkdir(parents=True)
        (home_detected / ".cursor").mkdir(parents=True)
        written_det = install_skill(global_install=True, home=home_detected)
        assert written_det == [
            home_detected / ".codex" / "skills" / "mintfig" / "SKILL.md",
            home_detected / ".cursor" / "rules" / "mintfig.mdc",
        ]
        assert (home_detected / ".codex" / "skills" / "mintfig" / "references" / "science.md").is_file()
        mdc = (home_detected / ".cursor" / "rules" / "mintfig.mdc").read_text(encoding="utf-8")
        assert mdc.startswith("---")
        assert "~/.cursor/rules/mintfig/references/" in mdc
        assert (
            home_detected / ".cursor" / "rules" / "mintfig" / "references" / "publication.md"
        ).is_file()
        assert not (home_detected / ".claude").exists()

    def test_target_all_project_and_global(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        proj = tmp_path / "proj"
        proj.mkdir()
        rc_local = cli_main(
            ["skill", "--install", "--root", str(proj), "--target", "all"]
        )
        out_local = capsys.readouterr().out
        assert rc_local == 0
        assert out_local.count("Installed:") == len(VALID_TARGETS)
        assert (proj / ".claude" / "skills" / "mintfig" / "SKILL.md").is_file()
        assert (proj / ".agents" / "skills" / "mintfig" / "SKILL.md").is_file()
        assert (proj / ".cursor" / "rules" / "mintfig.mdc").is_file()
        assert (proj / ".codex" / "skills" / "mintfig" / "SKILL.md").is_file()
        assert (proj / "AGENTS.md").is_file()
        assert (proj / "CLAUDE.md").is_file()

        home = tmp_path / "home"
        home.mkdir()
        rc_global = cli_main(
            [
                "skill",
                "--install",
                "--global",
                "--home",
                str(home),
                "--target",
                "all",
            ]
        )
        out_global = capsys.readouterr().out
        assert rc_global == 0
        assert out_global.count("Installed:") == len(GLOBAL_TARGETS)
        assert (home / ".claude" / "skills" / "mintfig" / "SKILL.md").is_file()
        assert (home / ".gemini" / "config" / "skills" / "mintfig" / "SKILL.md").is_file()
        assert (home / ".cursor" / "rules" / "mintfig.mdc").is_file()
        assert (home / ".codex" / "skills" / "mintfig" / "SKILL.md").is_file()

    def test_cli_skill_global_auto_detect(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        home = tmp_path / "home"
        (home / ".claude").mkdir(parents=True)
        (home / ".gemini").mkdir(parents=True)
        rc = cli_main(["skill", "--install", "--global", "--home", str(home)])
        out = capsys.readouterr().out
        assert rc == 0
        assert ".claude/skills/mintfig/SKILL.md" in out
        assert ".gemini/config/skills/mintfig/SKILL.md" in out
        assert not (home / ".cursor").exists()

    def test_print_and_print_all_bundle(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc_plain = cli_main(["skill", "--print", "--root", str(tmp_path)])
        out_plain = capsys.readouterr().out
        assert rc_plain == 0
        assert out_plain == get_skill_markdown()

        rc_all = cli_main(["skill", "--print", "--all", "--root", str(tmp_path)])
        out_all = capsys.readouterr().out
        assert rc_all == 0
        assert out_all == get_full_skill_bundle()
        assert get_skill_markdown().strip() in out_all
        for fname, content in get_skill_references().items():
            assert f"references/{fname}" in out_all
            assert content.strip() in out_all

        # Neither print mode modifies disk
        assert list(tmp_path.iterdir()) == []

    def test_invalid_target_rejected(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(ValueError, match="Unknown skill install target"):
            install_skill(tmp_path, targets=("bogus",))
        rc = cli_main(["skill", "--install", "--root", str(tmp_path), "--target", "bogus"])
        err = capsys.readouterr().err
        assert rc == 1
        assert "Unknown skill install target" in err


# --------------------------------------------------------------------------- Hook install / merge / uninstall


class TestHookInstallManage:
    def test_claude_hook_merge_preserves_existing_settings_and_is_idempotent(
        self, tmp_path: Path
    ) -> None:
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        pre_existing = {
            "model": "claude-opus-4-6",
            "permissions": {"allow": ["Bash(pytest:*)"]},
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "echo pre-check"}],
                    }
                ],
                "PostToolUse": [
                    {
                        "matcher": "Write",
                        "hooks": [{"type": "command", "command": "ruff check"}],
                    }
                ],
            },
        }
        settings_path.write_text(json.dumps(pre_existing, indent=2) + "\n", encoding="utf-8")

        # Install once
        written1 = install_hook(root=tmp_path, targets=("claude",))
        assert written1 == [settings_path]
        after1_raw = settings_path.read_text(encoding="utf-8")
        after1 = json.loads(after1_raw)

        # Pre-existing top-level keys and hooks preserved
        assert after1["model"] == "claude-opus-4-6"
        assert after1["permissions"] == {"allow": ["Bash(pytest:*)"]}
        assert after1["hooks"]["PreToolUse"] == pre_existing["hooks"]["PreToolUse"]
        post_hooks = after1["hooks"]["PostToolUse"]
        assert len(post_hooks) == 2
        assert post_hooks[0] == pre_existing["hooks"]["PostToolUse"][0]
        assert post_hooks[1]["matcher"] == "Bash|Write|Edit"
        assert post_hooks[1]["hooks"][0]["command"] == HOOK_COMMAND

        # Idempotent second install -> byte-identical
        install_hook(root=tmp_path, targets=("claude",))
        assert settings_path.read_text(encoding="utf-8") == after1_raw

        # Status reports installed
        st = hook_status(root=tmp_path, targets=("claude",))
        assert st["claude"]["installed"] is True
        assert st["claude"]["scope"] == "project"

        # Uninstall removes only mintfig hook, keeping all pre-existing user config
        removed = uninstall_hook(root=tmp_path, targets=("claude",))
        assert removed == [settings_path]
        after_uninstall = json.loads(settings_path.read_text(encoding="utf-8"))
        assert after_uninstall == pre_existing
        assert hook_status(root=tmp_path, targets=("claude",))["claude"]["installed"] is False

        # Second uninstall is a clean no-op
        assert uninstall_hook(root=tmp_path, targets=("claude",)) == []

    def test_claude_hook_global_and_malformed_json_guard(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        home.mkdir()
        written = install_hook(targets=("claude",), global_install=True, home=home)
        cfg = home / ".claude" / "settings.json"
        assert written == [cfg]
        assert hook_status(targets=("claude",), global_install=True, home=home)["claude"]["installed"] is True

        uninstall_hook(targets=("claude",), global_install=True, home=home)
        assert hook_status(targets=("claude",), global_install=True, home=home)["claude"]["installed"] is False
        assert json.loads(cfg.read_text(encoding="utf-8")) == {}

        # Corrupted JSON must raise ValueError instead of silently overwriting
        cfg.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid JSON"):
            install_hook(targets=("claude",), global_install=True, home=home)

    def test_cursor_and_codex_hooks_install_status_uninstall(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Preserve an unrelated user file in .cursor/hooks/
        user_file = tmp_path / ".cursor" / "hooks" / "my-custom-hook.sh"
        user_file.parent.mkdir(parents=True)
        user_file.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")

        rc_inst = cli_main(
            ["hook", "--install", "--root", str(tmp_path), "--target", "all"]
        )
        out_inst = capsys.readouterr().out
        assert rc_inst == 0
        assert out_inst.count("Installed hook:") == len(HOOK_TARGETS)

        for target in ("cursor", "codex"):
            script = tmp_path / f".{target}" / "hooks" / "mintfig-post-tool.sh"
            manifest = tmp_path / f".{target}" / "hooks" / "mintfig.json"
            assert script.is_file()
            assert manifest.is_file()
            assert script.stat().st_mode & stat.S_IXUSR
            data = json.loads(manifest.read_text(encoding="utf-8"))
            assert data["command"] == HOOK_COMMAND
            assert data["managed_by"] == "mintfig"

        rc_status = cli_main(["hook", "--status", "--root", str(tmp_path), "--json"])
        status_json = json.loads(capsys.readouterr().out)
        assert rc_status == 0
        assert all(status_json[t]["installed"] is True for t in HOOK_TARGETS)

        rc_uninst = cli_main(
            ["hook", "--uninstall", "--root", str(tmp_path), "--target", "all"]
        )
        capsys.readouterr()
        assert rc_uninst == 0
        assert user_file.is_file()  # Untouched
        st_after = hook_status(root=tmp_path)
        assert all(st_after[t]["installed"] is False for t in HOOK_TARGETS)

    def test_cli_hook_global_auto_detect(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        home = tmp_path / "home"
        (home / ".codex").mkdir(parents=True)
        rc = cli_main(["hook", "--install", "--global", "--home", str(home)])
        out = capsys.readouterr().out
        assert rc == 0
        assert ".codex/hooks/mintfig.json" in out
        assert not (home / ".claude").exists()


# --------------------------------------------------------------------------- Hook runtime tests


def _write_clean_plot(path: Path) -> Path:
    path.write_text(
        "import matplotlib\n"
        "matplotlib.use('Agg')\n"
        "import matplotlib.pyplot as plt\n"
        "fig, ax = plt.subplots(figsize=(7.0, 4.2), dpi=150)\n"
        "ax.bar(['A', 'B', 'C'], [10, 20, 30])\n"
        "ax.set_xlabel('Variant', fontsize=12)\n"
        "ax.set_ylabel('Score', fontsize=12)\n"
        "ax.set_title('C scores 30, 3x higher than A', fontsize=14)\n"
        "ax.tick_params(labelsize=11)\n"
        "fig.tight_layout()\n"
        "fig.savefig('clean.png', dpi=150)\n"
        "print('noisy stdout from user script should be suppressed')\n",
        encoding="utf-8",
    )
    return path


def _write_defective_plot(path: Path) -> Path:
    path.write_text(
        "import matplotlib\n"
        "matplotlib.use('Agg')\n"
        "import matplotlib.pyplot as plt\n"
        "import numpy as np\n"
        "fig, ax = plt.subplots(figsize=(10.0, 6.0), dpi=150)\n"
        "ax.bar(['A', 'B', 'C'], [10, 20, 30])\n"
        "ax.set_title('C beats A by 99 points', fontsize=6)\n"
        "ax.tick_params(labelsize=5)\n"
        "fig.savefig('defective.png', dpi=150)\n",
        encoding="utf-8",
    )
    return path


class TestHookRuntime:
    def test_empty_and_broken_stdin_exit_zero_silently(self) -> None:
        assert run_hook("") == (0, "")
        assert run_hook("   \n") == (0, "")
        assert run_hook("{broken json") == (0, "")
        assert run_hook("[1, 2, 3]") == (0, "")
        assert run_hook(json.dumps({"tool_name": "Write", "tool_input": {}})) == (0, "")

    def test_non_plot_and_explain_scripts_are_silent(self, tmp_path: Path) -> None:
        # Plain markdown file
        md = tmp_path / "notes.md"
        md.write_text("# Notes\n", encoding="utf-8")
        assert run_hook(
            json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(md)}})
        ) == (0, "")

        # Non-matplotlib python script
        util = tmp_path / "utils.py"
        util.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        assert run_hook(
            json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(util)}})
        ) == (0, "")

        # Self-auditing mint.explain script (even mentioning matplotlib in a comment)
        exp = tmp_path / "explain_fig.py"
        exp.write_text(
            "# replaces plain matplotlib\n"
            "import mintfig as mint\n"
            "fig = mint.explain('B is 2x A', mint.compare({'A': 10, 'B': 20}))\n",
            encoding="utf-8",
        )
        assert run_hook(
            json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(exp)}})
        ) == (0, "")

    def test_clean_plot_script_silent_exit_zero(self, tmp_path: Path) -> None:
        script = _write_clean_plot(tmp_path / "clean_plot.py")
        for payload in (
            {"tool_name": "Write", "tool_input": {"file_path": str(script)}},
            {
                "tool_name": "Bash",
                "tool_input": {"command": f"python {script.name}"},
                "cwd": str(tmp_path),
            },
        ):
            rc, out = run_hook(json.dumps(payload))
            assert rc == 0
            assert out == ""

    def test_defective_plot_write_edit_and_bash_return_fix_hints(self, tmp_path: Path) -> None:
        script = _write_defective_plot(tmp_path / "bad_plot.py")

        # 1. Claude PostToolUse Write
        payload_write = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(script)},
        }
        rc, out = run_hook(json.dumps(payload_write))
        assert rc == 0
        parsed = json.loads(out)
        assert parsed["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
        ctx = parsed["hookSpecificOutput"]["additionalContext"]
        assert "bad_plot.py" in ctx
        assert "fix_hint:" in ctx
        assert ("claim_number_mismatch" in ctx) or ("text_too_small" in ctx)

        # 2. Claude PostToolUse Edit with relative path + cwd
        payload_edit = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "bad_plot.py"},
            "cwd": str(tmp_path),
        }
        rc_e, out_e = run_hook(json.dumps(payload_edit))
        assert rc_e == 0
        parsed_e = json.loads(out_e)
        assert "fix_hint:" in parsed_e["hookSpecificOutput"]["additionalContext"]

        # 3. Claude PostToolUse Bash running the script
        payload_bash = {
            "tool_name": "Bash",
            "tool_input": {"command": "MPLCONFIGDIR=/tmp/mpl python3 bad_plot.py --fast"},
            "cwd": str(tmp_path),
        }
        rc_b, out_b = run_hook(json.dumps(payload_bash))
        assert rc_b == 0
        parsed_b = json.loads(out_b)
        assert "fix_hint:" in parsed_b["hookSpecificOutput"]["additionalContext"]

        # 4. Non-Claude generic payload -> plain text fallback
        rc_g, out_g = run_hook(json.dumps({"script": str(script)}))
        assert rc_g == 0
        assert not out_g.startswith("{")
        assert "fix_hint:" in out_g

    def test_bash_skips_test_runners_and_mintfig_commands(self, tmp_path: Path) -> None:
        script = _write_defective_plot(tmp_path / "bad_plot.py")
        for cmd in (
            f"pytest {script.name}",
            f"mintfig check {script.name}",
            f"uvx mintfig check {script.name}",
            f"python -m pytest {script.name}",
        ):
            payload = {
                "tool_name": "Bash",
                "tool_input": {"command": cmd},
                "cwd": str(tmp_path),
            }
            assert run_hook(json.dumps(payload)) == (0, "")

    def test_crashing_plot_script_and_disable_env_are_safe(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        crash = tmp_path / "crash_plot.py"
        crash.write_text(
            "import matplotlib.pyplot as plt\n"
            "raise RuntimeError('script blew up')\n",
            encoding="utf-8",
        )
        assert run_hook(
            json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(crash)}})
        ) == (0, "")

        exiter = tmp_path / "exit_plot.py"
        exiter.write_text(
            "import sys\nimport matplotlib.pyplot as plt\nsys.exit(2)\n",
            encoding="utf-8",
        )
        assert run_hook(
            json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(exiter)}})
        ) == (0, "")

        bad = _write_defective_plot(tmp_path / "bad_disabled.py")
        monkeypatch.setenv("MINTFIG_DISABLE_HOOK", "1")
        assert run_hook(
            json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(bad)}})
        ) == (0, "")
        assert os.environ["MINTFIG_DISABLE_HOOK"] == "1"

    def test_cli_hook_run_reads_stdin(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        script = _write_defective_plot(tmp_path / "cli_bad.py")
        payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(script)}})
        monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
        rc = cli_main(["hook", "run"])
        out = capsys.readouterr().out
        assert rc == 0
        parsed = json.loads(out)
        assert "fix_hint:" in parsed["hookSpecificOutput"]["additionalContext"]


# --------------------------------------------------------------------------- Claude Code Plugin tests


class TestClaudeCodePluginPackage:
    def test_plugin_manifest_hooks_command_and_readme(self) -> None:
        plugin_root = REPO_ROOT / "plugins" / "claude-code"
        manifest_path = plugin_root / ".claude-plugin" / "plugin.json"
        hooks_path = plugin_root / "hooks" / "hooks.json"
        cmd_path = plugin_root / "commands" / "check.md"
        readme_path = plugin_root / "README.md"

        assert manifest_path.is_file()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["name"] == "mintfig"
        assert manifest["version"] == "0.3.0"
        assert manifest["license"] == "MIT"
        assert manifest["repository"] == "https://github.com/blaiszik/mintfig"
        assert manifest["author"]["name"] == "Ben Blaiszik"
        assert manifest["skills"]
        assert manifest["hooks"]
        assert manifest["commands"]

        assert hooks_path.is_file()
        hooks_cfg = json.loads(hooks_path.read_text(encoding="utf-8"))
        post_entries = hooks_cfg["hooks"]["PostToolUse"]
        assert len(post_entries) == 1
        assert post_entries[0]["matcher"] == "Bash|Write|Edit"
        assert post_entries[0]["hooks"][0]["command"] == "mintfig hook run"

        assert cmd_path.is_file()
        cmd_text = cmd_path.read_text(encoding="utf-8")
        assert "mintfig check" in cmd_text

        assert readme_path.is_file()
        readme_text = readme_path.read_text(encoding="utf-8")
        assert "claude plugin install" in readme_text

    def test_plugin_skill_assets_in_sync_with_package_assets(self) -> None:
        src_assets = REPO_ROOT / "src" / "mintfig" / "assets"
        plugin_skill = REPO_ROOT / "plugins" / "claude-code" / "skills" / "mintfig"

        assert (plugin_skill / "SKILL.md").read_text(encoding="utf-8") == (
            src_assets / "SKILL.md"
        ).read_text(encoding="utf-8")

        src_refs = sorted(p.name for p in (src_assets / "references").glob("*.md"))
        plugin_refs = sorted(p.name for p in (plugin_skill / "references").glob("*.md"))
        assert src_refs == ["publication.md", "recipes.md", "science.md"]
        assert plugin_refs == src_refs
        for name in src_refs:
            assert (plugin_skill / "references" / name).read_text(encoding="utf-8") == (
                src_assets / "references" / name
            ).read_text(encoding="utf-8")
