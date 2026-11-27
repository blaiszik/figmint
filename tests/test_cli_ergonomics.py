"""Tests for CLI version flag, hash-seed gating, writable MPLCONFIGDIR fallback, and packaging."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import pytest

import mintfig as mint
from mintfig import _ensure_writable_mplconfigdir
from mintfig.cli import _needs_fixed_hash_seed
from mintfig.cli import main as cli_main

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_cli_version_flags(capsys: pytest.CaptureFixture[str]) -> None:
    for flag in ("--version", "-V"):
        with pytest.raises(SystemExit) as exc:
            cli_main([flag])
        assert exc.value.code == 0
        out = capsys.readouterr().out.strip()
        assert out == f"mintfig {mint.__version__}"


def test_needs_fixed_hash_seed_only_for_run_or_pdf() -> None:
    assert _needs_fixed_hash_seed(argparse.Namespace(command="run", out=None)) is True
    assert _needs_fixed_hash_seed(argparse.Namespace(command="explain", out=Path("a.pdf"))) is True
    assert _needs_fixed_hash_seed(argparse.Namespace(command="plot", out=Path("a.PDF"))) is True
    assert _needs_fixed_hash_seed(argparse.Namespace(command="edit", out=Path("a.pdf"))) is True

    assert _needs_fixed_hash_seed(argparse.Namespace(command="explain", out=Path("a.png"))) is False
    assert _needs_fixed_hash_seed(argparse.Namespace(command="plot", out=Path("a.html"))) is False
    assert _needs_fixed_hash_seed(argparse.Namespace(command="plot", out=None)) is False
    assert _needs_fixed_hash_seed(argparse.Namespace(command="edit", out=Path("a.png"))) is False
    assert _needs_fixed_hash_seed(argparse.Namespace(command="diff", out=Path("a.pdf"))) is False


def test_ensure_writable_mplconfigdir_falls_back_through_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MPLCONFIGDIR", raising=False)
    fake_home = tmp_path / "ro_home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(os, "access", lambda *_a, **_k: False)

    blocked_tmp = tmp_path / "blocked_tmp"
    blocked_tmp.mkdir()
    blocked_tmp.chmod(0o555)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(blocked_tmp))
    try:
        _ensure_writable_mplconfigdir()
        assert os.environ.get("MPLCONFIGDIR") == "/tmp/mintfig-mpl"
    finally:
        blocked_tmp.chmod(0o755)


def test_py_typed_and_pages_workflow_and_pyproject_metadata() -> None:
    assert (REPO_ROOT / "src" / "mintfig" / "py.typed").is_file()
    pages_yml = REPO_ROOT / ".github" / "workflows" / "pages.yml"
    assert pages_yml.is_file()
    pages_text = pages_yml.read_text(encoding="utf-8")
    assert "evals/figure_bench/site/index.html" in pages_text
    assert "actions/deploy-pages@v4" in pages_text

    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'all = [' in pyproject
    assert '"mintfig[pub,chip]"' in pyproject
    assert '"CHANGELOG.md"' in pyproject
    for key in ("Homepage", "Documentation", "Repository", "Issues", "Changelog"):
        assert f"{key} =" in pyproject


def test_cli_version_subprocess() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "mintfig.cli", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert proc.stdout.strip() == f"mintfig {mint.__version__}"
