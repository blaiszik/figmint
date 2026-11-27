"""Integration tests for optional mintchip interoperability in mint.brief, mint.notebook, and mint.inline.

All tests run cleanly both WITH ``mintchip`` importable (e.g. ``PYTHONPATH=/path/to/mintchip/src``)
and WITHOUT ``mintchip`` installed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest

import mintfig as mint
from mintfig._chip_bridge import has_mintchip, is_chip, is_table


def _sample_fig(
    takeaway: str = "Retrieval adds 8 points of accuracy",
    values: dict[str, float] | None = None,
) -> mint.Explanation:
    return mint.explain(
        takeaway,
        mint.compare(
            values or {"full": 82.0, "no retrieval": 74.0},
            label="Accuracy",
            unit="%",
            title="Test accuracy",
        ),
        source="ablation runs",
    )


def _hide_mintchip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block ``mintchip`` and its submodules from being imported in this test."""
    for name in list(sys.modules):
        if name == "mintchip" or name.startswith("mintchip."):
            monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.setitem(sys.modules, "mintchip", None)
    monkeypatch.setitem(sys.modules, "mintchip.directives", None)


# --------------------------------------------------------------------------- #
# 1. mint.brief + mintchip (when mintchip is installed)
# --------------------------------------------------------------------------- #


class TestBriefWithMintchip:
    @pytest.fixture
    def mc(self) -> Any:
        return pytest.importorskip("mintchip")

    def test_brief_html_and_markdown_with_chip_table_and_directives(
        self, mc: Any, tmp_path: Path
    ) -> None:
        fig = _sample_fig()
        chip = mc.spark([1.84, 1.32, 0.96, 0.58, 0.44], band=(0.38, 0.48), label="Val loss")
        tbl = mc.table(
            [
                {"model": "full", "acc": 82.0, "delta": mc.ci(8.0, (5.5, 10.5), unit="pp")},
                {"model": "no retrieval", "acc": 74.0, "delta": mc.ci(0.0, (-2.1, 2.1), unit="pp")},
            ],
            title="Ablation scorecard",
        )

        assert is_chip(chip) and not is_table(chip)
        assert is_table(tbl) and not is_chip(tbl)
        assert not is_chip(fig) and not is_table(fig)

        b = mint.brief(
            "Ablation review",
            "Loss fell to {{spark 1.84 1.32 0.96 0.44}} while CI held at {{ci 0.08 0.05:0.11}} & stayed green.",
            chip,
            tbl,
            fig,
            style="dark",
        )

        # HTML: embeds mintchip.css() once, syncs data-mc-scheme="dark", wide table + inline chip + directive
        html_path = tmp_path / "report.html"
        h_meta = b.save(html_path)
        assert h_meta["format"] == "html"
        assert h_meta["figure_count"] == 1
        doc = html_path.read_text(encoding="utf-8")

        assert '<html lang="en" data-mf-scheme="dark" data-mc-scheme="dark">' in doc
        assert doc.count(".mc-table{border-collapse:collapse") == 1
        assert '<div class="mf-mc-wide"><table class="mc-table"' in doc
        assert '<p class="mf-bprose mf-mc-chip"><span class="mc mc-spark">' in doc
        assert "mc-ci" in doc
        assert "&amp; stayed green." in doc
        # Directive prose renders inline inside <p class="mf-bprose">, never a nested <!doctype> or <p>
        assert doc.lower().count("<!doctype html>") == 1
        assert "<p class=\"mf-bprose\"><p>" not in doc
        ids = re.findall(r' id="([^"]+)"', doc)
        assert len(ids) == len(set(ids))

        # Light explicit style pins data-mc-scheme="light"
        light_html = mint.brief("Light brief", tbl, fig, style="paper").to_html()
        assert '<html lang="en" data-mf-scheme="light" data-mc-scheme="light">' in light_html

        # Auto style leaves <html> unpinned so prefers-color-scheme applies
        auto_html = mint.brief("Auto brief", tbl, fig).to_html()
        assert '<html lang="en">' in auto_html
        assert auto_html.count(".mc-table{border-collapse:collapse") == 1

        # Markdown: renders Table.markdown(), Chip.markdown(), and {{...}} directives as code spans
        md_path = tmp_path / "report.md"
        m_meta = b.save(md_path)
        assert m_meta["format"] == "markdown"
        md = md_path.read_text(encoding="utf-8")
        assert "{{spark" not in md
        assert "{{ci" not in md
        assert "`" in md
        assert chip.markdown() in md
        assert tbl.markdown() in md
        assert "![Retrieval adds 8 points of accuracy](report_figures/fig_01.png)" in md

    def test_brief_with_only_mintchip_table_and_session_brief(
        self, mc: Any, tmp_path: Path
    ) -> None:
        tbl = mc.table([{"model": "A", "score": 0.91}, {"model": "B", "score": 0.84}])

        # Table-only briefing works in both HTML and Markdown without creating empty figure dirs
        b = mint.brief("Quick scorecard", "Headline numbers:", tbl)
        assert b.figures == []
        assert b.ship_all is True
        md_out = tmp_path / "table_only.md"
        meta = b.save(md_out)
        assert meta["figure_count"] == 0
        assert meta["assets"] == []
        assert not (tmp_path / "table_only_figures").exists()
        assert tbl.markdown() in md_out.read_text(encoding="utf-8")

        html_out = tmp_path / "table_only.html"
        b.save(html_out)
        assert '<div class="mf-mc-wide"><table class="mc-table"' in html_out.read_text(encoding="utf-8")

        # Session.brief composes mintchip.Table cleanly with session figures
        sess = mint.Session()
        sess.explain(
            "Model A beats B by 7 points",
            mint.compare({"A": 91.0, "B": 84.0}, unit="%"),
        )
        sb = sess.brief("Session + table", tbl)
        assert len(sb.figures) == 1
        s_md = sb.to_markdown()
        assert s_md.index(tbl.markdown()) < s_md.index("## Model A beats B by 7 points")

    def test_brief_non_mintchip_double_braces_stay_literal(self, mc: Any) -> None:
        fig = _sample_fig()
        b = mint.brief("Templates", "Config uses {{unknown_template_var}} verbatim.", fig)
        assert "{{unknown_template_var}}" in b.to_html()
        assert "{{unknown_template_var}}" in b.to_markdown()


# --------------------------------------------------------------------------- #
# 2. mint.brief fallback when mintchip is absent or unused
# --------------------------------------------------------------------------- #


class TestBriefWithoutMintchip:
    def test_prose_directives_pass_through_untouched_when_mintchip_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _hide_mintchip(monkeypatch)
        assert has_mintchip() is False

        fig = _sample_fig()
        prose = "Loss {{spark 1.8 1.2 0.4}} stayed flat & safe."
        b = mint.brief("Fallback brief", prose, fig, style="dark")

        doc = b.to_html()
        assert "Loss {{spark 1.8 1.2 0.4}} stayed flat &amp; safe." in doc
        assert '<html lang="en" data-mf-scheme="dark">' in doc
        assert "data-mc-scheme" not in doc
        assert ".mc-table{" not in doc

        md = b.to_markdown()
        assert prose in md

    def test_plain_brief_does_not_inject_mintchip_css(self) -> None:
        fig = _sample_fig()
        doc = mint.brief("Plain brief", "No directives here.", fig, style="dark").to_html()
        assert '<html lang="en" data-mf-scheme="dark">' in doc
        assert "data-mc-scheme" not in doc
        assert ".mc-table{" not in doc


# --------------------------------------------------------------------------- #
# 3. .mintfig/ lab notebook status strip (with and without mintchip)
# --------------------------------------------------------------------------- #


class TestNotebookMintchipStrip:
    def _populate_notebook(self, tmp_path: Path, ships: list[bool]) -> Path:
        nb = mint.notebook.init(tmp_path)
        for idx, ok in enumerate(ships):
            p = tmp_path / f"fig_{idx}.png"
            _sample_fig(f"Finding {idx + 1} improves score").save(p, log=False)
            mint.notebook.log_file(
                p,
                takeaway=f"Finding {idx + 1}",
                ship=ok,
                notebook_dir=nb,
                rebuild_html=False,
            )
        return nb

    def test_notebook_renders_mintchip_strip_when_available_and_ge_2_entries(
        self, tmp_path: Path
    ) -> None:
        pytest.importorskip("mintchip")
        nb = self._populate_notebook(tmp_path, [True, False, True])
        html_path = mint.notebook.build_index_html(nb)
        doc = html_path.read_text(encoding="utf-8")

        assert 'id="nb-strip"' in doc
        assert "mc-strip" in doc
        assert "2/3 pass" in doc
        assert "Recent ship history" in doc
        assert ".mc{white-space:nowrap" in doc
        assert 'data-mc-scheme' in doc

    def test_notebook_omits_strip_for_single_entry(self, tmp_path: Path) -> None:
        nb = self._populate_notebook(tmp_path, [True])
        doc = mint.notebook.build_index_html(nb).read_text(encoding="utf-8")
        assert 'id="nb-strip"' not in doc
        assert "mc-strip" not in doc

    def test_notebook_falls_back_to_plain_badge_when_mintchip_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _hide_mintchip(monkeypatch)
        nb = self._populate_notebook(tmp_path, [True, False, True])
        doc = mint.notebook.build_index_html(nb).read_text(encoding="utf-8")

        assert 'id="nb-strip"' in doc
        assert "mc-strip" not in doc
        assert ".mc{white-space:nowrap" not in doc
        assert '<span class="badge fix">2/3 ship</span>' in doc


# --------------------------------------------------------------------------- #
# 4. inline migration bridge & pyproject optional dependency
# --------------------------------------------------------------------------- #


def test_inline_migration_bridge_and_optional_dep(monkeypatch: pytest.MonkeyPatch) -> None:
    note = mint.inline.mintchip_migration_note()
    assert "mintchip" in note and "mintfig[chip]" in note
    assert mint.inline.MINTCHIP_MIGRATION["mint.inline.spark"] == "mintchip.spark"
    assert mint.inline.MINTCHIP_MIGRATION["mint.inline.strip"] == "mintchip.strip"

    # Base dependencies remain free of mintchip; optional extra `chip` pins mintchip>=0.2
    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    deps_match = re.search(r"(?ms)^dependencies\s*=\s*\[(.*?)\]", pyproject)
    assert deps_match is not None
    assert "mintchip" not in deps_match.group(1).lower()
    opt_match = re.search(
        r"(?ms)^\[project\.optional-dependencies\].*?^chip\s*=\s*\[(.*?)\]", pyproject
    )
    assert opt_match is not None
    assert '"mintchip>=0.2"' in opt_match.group(1)

    _hide_mintchip(monkeypatch)
    assert mint.inline.has_mintchip() is False
