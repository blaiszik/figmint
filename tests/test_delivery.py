"""The last mile: ``summary["deliver"]``, the compact summary view, show(), to_text() and doctor."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pytest

matplotlib.use("Agg")

import mintfig as mint
from mintfig.cli import main as cli_main
from mintfig.explainer import EXAMPLE_SPEC

TAKEAWAY = "Removing retrieval costs 8 points of accuracy; removing fine-tuning costs 13"


def _ablation(takeaway: str = TAKEAWAY) -> mint.Explanation:
    return mint.explain(
        takeaway,
        mint.compare(
            {"full model": 0.82, "no retrieval": 0.74, "no fine-tuning": 0.69},
            error={"full model": (0.80, 0.84), "no retrieval": (0.71, 0.77),
                   "no fine-tuning": (0.66, 0.72)},
            error_label="95% CI, 5 seeds",
            title="Both losses are outside seed noise",
            label="Test accuracy",
            highlight=["no retrieval", "no fine-tuning"],
        ),
        mint.trend(
            [0, 500, 1000, 1500, 2000],
            {"full model": [0.02, 0.61, 0.76, 0.80, 0.82],
             "no retrieval": [0.02, 0.52, 0.67, 0.72, 0.74],
             "no fine-tuning": [0.01, 0.44, 0.60, 0.66, 0.69]},
            title="The gap opens in the first 500 steps",
            label="Validation accuracy",
            x_label="Training step",
        ),
        source="runs/ablation_2026-11 (5 seeds per variant)",
    )


@pytest.fixture
def fig() -> mint.Explanation:
    exp = _ablation()
    yield exp
    plt.close(exp.fig)


def test_deliver_before_and_after_saving(
    fig: mint.Explanation, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    unsaved = fig.summary()
    assert unsaved["schema_version"] == "0.2"
    assert unsaved["deliver"]["markdown"] is None and unsaved["deliver"]["html"] is None

    summary = fig.save("out/ablation.png")
    deliver = summary["deliver"]
    assert deliver["markdown"] == f"![{TAKEAWAY}](out/ablation.png)"
    assert deliver["html"] is None
    caption = deliver["caption"]
    assert caption.endswith(".") and not caption.startswith("[")
    # the facts that print the takeaway's two gaps (8 and 13 points), in one sentence
    assert "retrieval" in caption and "0.08" in caption and "0.13" in caption
    assert deliver["text"] == fig.to_text()

    summary = fig.save("out/ablation.html")
    assert summary["deliver"]["html"] == "out/ablation.html"
    assert summary["deliver"]["markdown"] == f"![{TAKEAWAY}](out/ablation.png)"

    # Every key that existed before is still there.
    for key in ("ok", "ship", "style", "palette", "path", "size_px", "size_mm", "display",
                "takeaway", "panels", "narrative", "alt_text", "colors", "issues", "rendered"):
        assert key in summary


def test_markdown_path_outside_cwd_is_absolute_and_alt_is_escaped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exp = _ablation("Retrieval [ablated] costs 8 points of accuracy")
    try:
        (tmp_path / "work").mkdir()
        monkeypatch.chdir(tmp_path / "work")
        deliver = exp.save(tmp_path / "elsewhere" / "fig.svg")["deliver"]
        target = (tmp_path / "elsewhere" / "fig.svg").resolve().as_posix()
        assert deliver["markdown"] == f"![Retrieval [ablated\\] costs 8 points of accuracy]({target})"
        assert exp.save(tmp_path / "fig.pdf")["deliver"]["markdown"].endswith("fig.svg)")
    finally:
        plt.close(exp.fig)


def test_pdf_alone_gives_no_markdown(tmp_path: Path) -> None:
    exp = _ablation()
    try:
        assert exp.save(tmp_path / "fig.pdf")["deliver"]["markdown"] is None
    finally:
        plt.close(exp.fig)


def test_display_height_matches_aspect(fig: mint.Explanation) -> None:
    display = fig.summary()["display"]
    expected = round(display["width_px"] * fig.fig.get_figheight() / fig.fig.get_figwidth())
    assert display["height_px"] == expected


def test_compact_view_is_valid_json_and_dict_keeps_everything(
    fig: mint.Explanation, tmp_path: Path
) -> None:
    summary = fig.save(tmp_path / "fig.png")
    compact = json.loads(str(summary))
    assert set(compact) == {"ok", "ship", "path", "takeaway", "deliver", "issues", "panels"}
    for short, full in zip(compact["panels"], summary["panels"], strict=True):
        assert set(short) == {"key", "kind", "title", "facts", "more_facts"}
        assert short["facts"] == full["facts"][:3]
        assert short["more_facts"] == max(0, len(full["facts"]) - 3)
    assert "narrative" in json.loads(json.dumps(summary))
    assert len(str(summary)) < len(json.dumps(summary))


def test_to_text_is_plain_and_narrow(fig: mint.Explanation) -> None:
    text = fig.to_text()
    assert "\x1b" not in text
    assert max(len(line) for line in text.splitlines()) <= 72
    narrow = fig.to_text(width=50, ascii_only=True)
    assert narrow.isascii()
    assert max(len(line) for line in narrow.splitlines()) <= 50


def test_show_prints_text_without_image_protocol(
    fig: mint.Explanation, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for var in ("KITTY_WINDOW_ID", "TERM_PROGRAM", "LC_TERMINAL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    fig.show()
    assert capsys.readouterr().out == fig.to_text() + "\n"


def test_show_sends_inline_png_to_an_image_terminal(
    fig: mint.Explanation, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("KITTY_WINDOW_ID", "1")
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    fig.show()
    assert capsys.readouterr().out.startswith("\x1b_Ga=T,f=100,")


def test_cli_summary_views(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(EXAMPLE_SPEC), encoding="utf-8")
    assert cli_main(["explain", str(spec_path), "--out", str(tmp_path / "a.png")]) == 0
    compact = json.loads(capsys.readouterr().out)
    assert "narrative" not in compact and compact["deliver"]["markdown"].endswith("a.png)")
    assert cli_main(
        ["explain", str(spec_path), "--out", str(tmp_path / "b.png"), "--summary", "full"]
    ) == 0
    full = json.loads(capsys.readouterr().out)
    assert "narrative" in full and full["schema_version"] == "0.2"


def test_doctor_reports_surfaces_and_renders_a_sample(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_main(["doctor", "--json", "--out", str(tmp_path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert set(report["surfaces"]) == {
        "inline_image_protocol", "body_font", "stdout_is_tty", "notebook"
    }
    assert (tmp_path / "example.png").exists() and (tmp_path / "example.html").exists()
    assert report["deliver"]["markdown"].endswith("example.png)")
    assert report["deliver"]["html"].endswith("example.html")

    assert cli_main(["doctor", "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "inline image protocol" in out and "markdown: ![" in out
