"""Tests for fm.Session (multi-turn visual memory) and fm.brief (HTML & Markdown briefings)."""

from __future__ import annotations

from pathlib import Path

import pytest

import figmint as fm


class TestSessionVisualMemory:
    def test_session_preserves_colors_and_prefix_matches_variants(self, tmp_path: Path) -> None:
        state_file = tmp_path / "session_state.json"
        session = fm.Session(style="paper", accent="#C8553D", state_path=state_file)

        f1 = session.explain(
            "Alpha-3 leads Beta-Pro by 3.2 points on GPQA",
            fm.compare(
                {"Alpha-3": 86.4, "Beta-Pro": 83.2, "Baseline": 77.1},
                highlight=["Alpha-3", "Beta-Pro"],
                baseline="Baseline",
                title="GPQA accuracy",
                label="Score",
                unit="%",
            ),
            source="synthetic evals",
        )
        assert f1.summary()["ship"] is True
        alpha_slot = f1.entity_colors["Alpha-3"]
        beta_slot = f1.entity_colors["Beta-Pro"]
        assert state_file.exists()

        # Turn 2: variant names "Alpha-3 (int4)" and "Beta-Pro after" inherit base entity slots!
        f2 = session.explain(
            "Alpha-3 (int4) retains 85.3% while Beta-Pro after tuning reaches 83.8%",
            fm.compare(
                {"Alpha-3 (int4)": 85.3, "Beta-Pro after": 83.8, "Baseline": 77.1},
                highlight=["Alpha-3 (int4)", "Beta-Pro after"],
                baseline="Baseline",
                title="Quantized / tuned variants",
                label="Score",
                unit="%",
            ),
            source="synthetic evals",
        )
        assert f2.summary()["ship"] is True
        assert f2.entity_colors["Alpha-3 (int4)"] == alpha_slot
        assert f2.entity_colors["Beta-Pro after"] == beta_slot
        assert f2.to_spec()["style"] == "paper"
        assert f2.to_spec()["accent"] == "#C8553D"

        # Turn 3: fresh Session reloaded from disk preserves ledger and theme
        session2 = fm.Session(state_path=state_file)
        f3 = session2.explain(
            "Alpha-3 stays ahead on SWE-bench at 74.2%",
            fm.compare(
                {"Alpha-3": 74.2, "Beta-Pro": 71.0, "Baseline": 58.6},
                highlight=["Alpha-3", "Beta-Pro"],
                baseline="Baseline",
                title="SWE-bench",
                label="Resolve rate",
                unit="%",
            ),
            source="synthetic evals",
        )
        assert f3.entity_colors["Alpha-3"] == alpha_slot
        assert f3.entity_colors["Beta-Pro"] == beta_slot
        assert f3.to_spec()["style"] == "paper"

    def test_session_edit_and_brief(self, tmp_path: Path) -> None:
        session = fm.Session(style="figmint")
        f1 = session.explain(
            "Checkout p99 is 4x slower than search",
            fm.compare({"checkout": 1840, "search": 460, "auth": 310}, highlight="checkout", unit="ms"),
            source="synthetic",
        )
        session.edit(f1, drop="auth", takeaway="Checkout p99 is 4x slower than search at 1,840 ms")
        assert len(session.figures) == 2

        rep = session.brief(
            "Latency investigation",
            subtitle="Production traces",
            summary=["Checkout accounts for 4x tail latency"],
        )
        html_path = tmp_path / "report.html"
        meta = rep.save(html_path)
        assert meta["format"] == "html"
        assert meta["figure_count"] == 2
        assert meta["ship_all"] is True
        html_text = html_path.read_text(encoding="utf-8")
        assert "Latency investigation" in html_text
        assert 'href="#fig-1"' in html_text
        assert 'href="#fig-2"' in html_text


class TestBriefComposition:
    def test_brief_html_and_markdown_export_from_mixed_inputs(self, tmp_path: Path) -> None:
        f1 = fm.explain(
            "Retrieval drives +8.2 points of the +12.2 point gain",
            fm.waterfall(
                {"+Retrieval": 8.2, "+Reranker": 3.4, "+CoT": 2.1, "Quant": -1.5},
                start=("Base", 69.0),
                highlight="+Retrieval",
                title="Accuracy bridge",
                unit="%",
            ),
            source="synthetic ablation",
        )
        f2 = fm.explain(
            "Alpha-3 leads both GPQA (86.4%) and SWE-bench (74.2%)",
            fm.table(
                [
                    {"Model": "Alpha-3", "GPQA": 86.4, "SWE": 74.2},
                    {"Model": "Alpha-2", "GPQA": 77.1, "SWE": 58.6},
                ],
                units={"GPQA": "%", "SWE": "%"},
                bold_best=True,
                highlight="Alpha-3",
                title="Exact scorecard",
            ),
            source="synthetic evals",
        )
        png1 = tmp_path / "f1.png"
        f1.save(png1)

        # Mix saved PNG path + live Explanation object + XSS-safe title
        b = fm.brief(
            "Release Review <v3>",
            png1,
            f2,
            subtitle="End-to-end evaluation",
            summary=["Retrieval drives the majority of gains", "Alpha-3 tops every metric"],
            source="eval suite",
            style="dark",
        )
        assert b.ship_all is True

        # Self-contained dark HTML
        html_file = tmp_path / "review.html"
        h_meta = b.save(html_file)
        assert h_meta["format"] == "html"
        h_text = html_file.read_text(encoding="utf-8")
        assert "Release Review &lt;v3&gt;" in h_text
        assert "<script src=" not in h_text and "<link " not in h_text  # zero CDN dependencies
        assert "<svg" in h_text
        assert "color-scheme: dark" in h_text

        # Markdown + saved PNG bundle
        md_file = tmp_path / "review.md"
        m_meta = b.save(md_file)
        assert m_meta["format"] == "markdown"
        assert len(m_meta["assets"]) == 2
        assert (tmp_path / "review_figures" / "fig_01.png").exists()
        assert (tmp_path / "review_figures" / "fig_02.png").exists()
        md_text = md_file.read_text(encoding="utf-8")
        assert "# Release Review <v3>" in md_text
        assert "![Retrieval drives +8.2 points of the +12.2 point gain](review_figures/fig_01.png)" in md_text
        assert "| Model" in md_text  # embedded Markdown table from fm.table panel!

    def test_brief_validation_errors(self) -> None:
        with pytest.raises(fm.ExplainError, match="title"):
            fm.brief("   ")
        with pytest.raises(fm.ExplainError, match="at least one figure"):
            fm.brief("Empty brief")
