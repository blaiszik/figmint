"""Tests for compact inline HTML embeds and writable MPLCONFIGDIR fallback."""

from __future__ import annotations

import os
from pathlib import Path

import mintfig as mint


def test_to_html_compact_is_much_smaller_and_preserves_interactivity(tmp_path: Path) -> None:
    fig = mint.explain(
        "BX-204 inhibits near 10 nM, 100x below toxicity",
        mint.trend(
            [0.001, 0.01, 0.1, 1.0, 10.0],
            {"BX-204": [8, 49, 95, 99, 97], "BX-101": [1, 11, 58, 93, 99]},
            log_x=True,
            highlight="BX-204",
            title="BX-204 is the most potent",
            label="Kinase inhibition",
            unit="%",
            x_label="Dose (µM)",
            reference=(50, "half-maximal"),
        ),
        source="Simulated kinase panel",
    )

    full_html = fig.to_html()
    compact_html = fig.to_html(compact=True)

    assert len(compact_html) < len(full_html) * 0.5
    assert "background:transparent" in compact_html
    assert "themechange" in compact_html
    assert "data-mf=" in compact_html
    assert 'data-mf-act="data"' in compact_html
    assert 'data-mf-act="svg"' in compact_html
    assert 'data-mf-act="spec"' not in compact_html

    out = tmp_path / "compact.html"
    summary = fig.save(out, compact=True)
    assert summary["ship"] is True
    saved = out.read_text(encoding="utf-8")
    assert "background:transparent" in saved
    assert "themechange" in saved
    assert 'data-mf-act="spec"' not in saved
    assert abs(len(saved) - len(compact_html)) < 200


def test_ensure_writable_mplconfigdir_respects_existing_env(monkeypatch) -> None:
    monkeypatch.setenv("MPLCONFIGDIR", "/tmp/custom-mpl-dir")
    mint._ensure_writable_mplconfigdir()
    assert os.environ["MPLCONFIGDIR"] == "/tmp/custom-mpl-dir"


def test_ensure_writable_mplconfigdir_sets_fallback_when_home_unwritable(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MPLCONFIGDIR", raising=False)
    monkeypatch.setattr(os, "access", lambda *_a, **_k: False)
    monkeypatch.setattr(mint.tempfile, "gettempdir", lambda: str(tmp_path))

    mint._ensure_writable_mplconfigdir()
    expected = tmp_path / "mintfig-mpl"
    assert os.environ["MPLCONFIGDIR"] == str(expected)
    assert expected.is_dir()
