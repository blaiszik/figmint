"""Tests for the opt-in `.mintfig/` local visual lab notebook."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt

import mintfig as mint
from mintfig.cli import main as cli_main


def _sample_fig(takeaway: str = "Model B gains 6 points over baseline", source: str = "data/eval.csv") -> mint.Explanation:
    return mint.explain(
        takeaway,
        mint.compare(
            {"baseline": 0.74, "model B": 0.80},
            title="Accuracy comparison",
            label="Accuracy",
            highlight="model B",
        ),
        source=source,
    )


def test_opt_in_only_save_never_creates_dot_mintfig_unasked(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "plot.png"
    summary = _sample_fig().save(out)
    assert summary["ship"] is True
    assert out.is_file()
    assert not (tmp_path / ".mintfig").exists()


def test_init_auto_capture_provenance_and_git_exclude(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git" / "info").mkdir(parents=True)
    data_csv = tmp_path / "data" / "eval.csv"
    data_csv.parent.mkdir(parents=True)
    data_csv.write_text("variant,acc\nbaseline,0.74\nmodel B,0.80\n", encoding="utf-8")

    nb = mint.notebook.init(tmp_path)
    assert (nb / "config.json").is_file()
    assert (nb / "index.html").is_file()
    exclude = (tmp_path / ".git" / "info" / "exclude").read_text(encoding="utf-8")
    assert ".mintfig/" in exclude

    # Saving a figure anywhere under the project now logs automatically
    out = tmp_path / "chart.png"
    _sample_fig(source="data/eval.csv").save(out)

    entries = mint.notebook.list_entries(nb)
    assert len(entries) == 1
    e = entries[0]
    assert e["ship"] is True
    assert "6 points" in e["takeaway"]
    assert (nb / e["artifact"]).is_file()
    assert (nb / e["spec_file"]).is_file()
    assert any(s["path"] == "data/eval.csv" and len(s["sha256"]) == 16 for s in e["sources"])
    assert "compare" in e["tags"]
    assert (nb / "session.json").is_file()

    viewer = (nb / "index.html").read_text(encoding="utf-8")
    assert "Model B gains 6 points over baseline" in viewer
    assert "data:image/png;base64," in viewer

    # Opt-out flags suppress capture
    _sample_fig("Skipped via log=False").save(tmp_path / "skip1.png", log=False)
    monkeypatch.setenv("MINTFIG_NO_LOG", "1")
    _sample_fig("Skipped via env").save(tmp_path / "skip2.png")
    assert len(mint.notebook.list_entries(nb)) == 1


def test_log_plain_matplotlib_file_and_cli_roundtrip(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli_main(["log", "--init"]) == 0

    # Auto-log one mintfig figure
    _sample_fig("Retrieval adds 8 points of accuracy").save(tmp_path / "m1.png")

    # Manually log a plain Matplotlib PNG
    fig, ax = plt.subplots()
    ax.bar(["A", "B"], [1, 2])
    plain = tmp_path / "plain.png"
    fig.savefig(plain)
    plt.close(fig)

    assert (
        cli_main([
            "log",
            "--add",
            str(plain),
            "--takeaway",
            "Plain Matplotlib baseline",
            "--source",
            "manual check",
            "--tag",
            "matplotlib",
        ])
        == 0
    )

    capsys.readouterr()
    assert cli_main(["log", "--search", "Retrieval", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 1
    assert "Retrieval" in rows[0]["takeaway"]

    # Compose a briefing from logged spec entries
    brief_out = tmp_path / "weekly_brief.html"
    assert cli_main(["log", "--brief", str(brief_out), "--last", "5"]) == 0
    assert brief_out.is_file()
    assert "Retrieval adds 8 points of accuracy" in brief_out.read_text(encoding="utf-8")
