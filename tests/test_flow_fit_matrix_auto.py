"""Tests for fm.flow, trend(fit=), matrix(triangle=/mask_diagonal=), fm.auto_panel, and figmint brief/auto CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import figmint as fm
from figmint.cli import main as cli_main
from figmint.themes import THEMES

# --------------------------------------------------------------------------- #
# 1. fm.flow (attrition / cohort / pipeline funnel)
# --------------------------------------------------------------------------- #


class TestFlowForm:
    def _cohort_stages(self) -> list[tuple[str, float, str | None]]:
        return [
            ("Screened", 1240, None),
            ("Eligible", 912, "missing baseline"),
            ("Enrolled", 780, "declined consent"),
            ("Completed", 714, "lost to follow-up"),
        ]

    @pytest.mark.parametrize("style_name", list(THEMES))
    def test_flow_renders_clean_across_all_themes(self, style_name: str) -> None:
        fig = fm.explain(
            "57.6% of screened patients complete follow-up; eligibility screening accounts for the largest drop (26%)",
            fm.flow(
                self._cohort_stages(),
                highlight="Eligible",
                title="Cohort retention across trial stages",
                label="Cohort size",
                unit="patients",
            ),
            source="synthetic trial cohort",
            style=style_name,
        )
        s = fig.summary()
        assert s["ok"] is True
        assert s["ship"] is True
        assert s["issues"] == []
        facts = " ".join(s["panels"][0]["facts"])
        assert "57.6% retained" in facts
        assert "largest drop" in facts
        assert "\N{MINUS SIGN}26%" in facts
        assert "+26%" not in facts
        assert "missing baseline" in facts
        assert "flow" in s["narrative"]["L1"]

    def test_flow_dict_tidy_lenient_edit_html_terminal_roundtrip(self, tmp_path: Path) -> None:
        # Dict input without reasons
        p_dict = fm.flow({"Raw docs": 4200, "Deduped": 1800, "Filtered": 920}, show_pct=False, label="Docs")
        assert any("4,200" in f for f in p_dict.facts)

        # Tidy rows with auto-inferred columns
        rows = [
            {"stage": "Alerts", "count": 412, "drop_reason": None},
            {"stage": "Deduplicated", "count": 118, "drop_reason": "duplicate bursts"},
            {"stage": "Actionable", "count": 31, "drop_reason": "auto-resolved"},
            {"stage": "P0 incidents", "count": 6, "drop_reason": "non-critical"},
        ]
        fig = fm.explain(
            "Only 6 of 412 alerts (1.5%) reach P0 incident triage",
            fm.flow(rows, title="Alert triage funnel", label="Alert count"),
            source="synthetic on-call log",
        )
        assert fig.summary()["ship"] is True

        # Round-trip via PNG
        png = tmp_path / "funnel.png"
        fig.save(png)
        reloaded = fm.load(png)
        assert reloaded.to_spec() == fig.to_spec()
        assert fm.explain_from_spec(reloaded.to_spec()).summary()["ship"] is True

        # Edit drop stage
        edited = fm.edit(fig, drop="Actionable")
        assert len(edited.to_spec()["panels"][0]["stages"]) == 3

        # HTML & terminal
        html_out = fig.to_html()
        assert "duplicate bursts" in html_out
        term = fig.to_terminal(color=False)
        assert "P0 incidents" in term and "duplicate bursts" in term

        # Lenient trimming >12 stages
        many = [(f"Stage {i:02d}", float(1000 - i * 60)) for i in range(15)]
        with pytest.raises(fm.ExplainError):
            fm.flow(many)
        with fm.lenient():
            fig_len = fm.explain("Fifteen stages shrink from 1,000 to 160", fm.flow(many, label="Items"), source="synthetic")
        assert fig_len.summary()["ship"] is True
        assert len(fig_len.to_spec()["panels"][0]["stages"]) == 12

    def test_flow_validation_errors(self) -> None:
        with pytest.raises(fm.ExplainError, match="at least two"):
            fm.flow({"Only one": 100})
        with pytest.raises(fm.ExplainError, match="negative"):
            fm.flow({"Start": 100, "End": -5})


# --------------------------------------------------------------------------- #
# 2. trend(fit=...)
# --------------------------------------------------------------------------- #


class TestTrendFit:
    def test_trend_linear_log_and_power_fits_and_roundtrip(self, tmp_path: Path) -> None:
        # Linear fit
        x_lin = [0, 10, 20, 30, 40, 50]
        fig_lin = fm.explain(
            "Throughput grows steadily by +2.0 req/s per worker across 50 workers",
            fm.trend(
                x_lin,
                {"Optimized": [12, 31, 53, 71, 92, 112], "Baseline": [10, 20, 29, 41, 50, 61]},
                fit=True,
                x_label="Workers",
                label="Throughput",
                unit="req/s",
                title="Linear scaling with OLS fit",
            ),
            source="synthetic bench",
        )
        s_lin = fig_lin.summary()
        assert s_lin["ok"] is True
        assert s_lin["ship"] is True
        assert s_lin["issues"] == []
        facts = " ".join(s_lin["panels"][0]["facts"])
        assert "linear fit slope" in facts and "R²" in facts

        # Power-law fit (log-log)
        compute = [1e18, 3e18, 1e19, 3e19, 1e20, 3e20]
        dense = [2.45, 2.26, 2.08, 1.92, 1.77, 1.63]
        moe = [2.30, 2.09, 1.88, 1.71, 1.54, 1.39]
        fig_pow = fm.explain(
            "MoE scales steeper than Dense across two orders of magnitude in compute",
            fm.trend(
                compute,
                {"MoE": moe, "Dense": dense},
                log=True,
                log_x=True,
                fit=True,
                highlight="MoE",
                baseline="Dense",
                x_label="Compute (FLOPs)",
                label="Validation loss",
                title="Power-law scaling curves",
            ),
            source="synthetic scaling runs",
        )
        s_pow = fig_pow.summary()
        assert s_pow["ok"] is True
        assert s_pow["ship"] is True
        assert s_pow["issues"] == []

        png = tmp_path / "scaling.png"
        fig_pow.save(png)
        assert fm.load(png).to_spec() == fig_pow.to_spec()

        # Facet with fit=True
        fig_fac = fm.explain(
            "All three variants follow near-linear trajectories over 5 epochs",
            fm.trend(
                [1, 2, 3, 4, 5],
                {"A": [10, 21, 29, 42, 51], "B": [8, 15, 24, 31, 40], "C": [5, 11, 14, 19, 25]},
                facet=True,
                fit="linear",
                x_label="Epoch",
                label="Score",
            ),
            source="synthetic",
        )
        assert fig_fac.summary()["ship"] is True

    def test_trend_fit_rejects_categorical_x(self) -> None:
        with pytest.raises(fm.ExplainError, match="numeric or date"):
            fm.trend(["Q1", "Q2", "Q3"], {"Rev": [10, 20, 30]}, fit=True)


# --------------------------------------------------------------------------- #
# 3. matrix(triangle=..., mask_diagonal=...)
# --------------------------------------------------------------------------- #


class TestMatrixTriangleAndMaskDiagonal:
    def _corr_matrix(self) -> tuple[list[str], list[list[float]]]:
        names = ["Reasoning", "Coding", "Math", "Retrieval", "Latency"]
        vals = [
            [1.00, 0.78, 0.84, 0.52, -0.34],
            [0.78, 1.00, 0.71, 0.44, -0.28],
            [0.84, 0.71, 1.00, 0.39, -0.41],
            [0.52, 0.44, 0.39, 1.00, -0.18],
            [-0.34, -0.28, -0.41, -0.18, 1.00],
        ]
        return names, vals

    @pytest.mark.parametrize("tri", ["lower", "upper"])
    def test_matrix_triangle_and_mask_diagonal_render_clean(self, tri: str, tmp_path: Path) -> None:
        names, vals = self._corr_matrix()
        fig = fm.explain(
            "Reasoning and Math correlate most strongly (r = 0.84) while Latency correlates negatively",
            fm.matrix(
                vals,
                rows=names,
                cols=names,
                diverging=True,
                center=0.0,
                triangle=tri,
                mask_diagonal=True,
                title="Evaluation metric correlations",
                label="Pearson r",
            ),
            source="synthetic eval matrix",
        )
        s = fig.summary()
        assert s["ok"] is True
        assert s["ship"] is True
        assert s["issues"] == []
        facts = " ".join(s["panels"][0]["facts"])
        assert "diagonal masked" in facts
        assert "empty" not in facts  # hidden triangle cells are NOT falsely counted as missing data
        assert f"{tri} triangle" in s["narrative"]["L1"]

        png = tmp_path / f"corr_{tri}.png"
        fig.save(png)
        assert fm.load(png).to_spec() == fig.to_spec()

    def test_matrix_triangle_rejects_rectangular(self) -> None:
        with pytest.raises(fm.ExplainError, match="square"):
            fm.matrix([[1, 2, 3], [4, 5, 6]], rows=["r1", "r2"], cols=["c1", "c2", "c3"], triangle="lower")


# --------------------------------------------------------------------------- #
# 4. fm.auto_panel & CLI (figmint plot --kind auto / flow, figmint brief)
# --------------------------------------------------------------------------- #


class TestAutoPanelAndBriefCli:
    def test_auto_panel_detects_flow_and_compare(self, tmp_path: Path) -> None:
        flow_csv = tmp_path / "cohort.csv"
        flow_csv.write_text(
            "stage,count,drop_reason\n"
            "Screened,1240,\n"
            "Eligible,912,missing baseline\n"
            "Enrolled,780,declined consent\n"
            "Completed,714,lost to follow-up\n",
            encoding="utf-8",
        )
        info = fm.inspect_data(flow_csv)
        assert info["recommendations"][0]["kind"] == "flow"

        panel = fm.auto_panel(flow_csv, title="Cohort funnel", label="Patients")
        assert panel.kind == "flow"
        fig = fm.explain("57.6% of screened patients complete follow-up", panel, source="cohort.csv")
        assert fig.summary()["ship"] is True

    def test_cli_plot_auto_flow_and_brief_end_to_end(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        flow_csv = tmp_path / "funnel.csv"
        flow_csv.write_text(
            "stage,count,reason\n"
            "Raw docs,4200,\n"
            "Deduped,1800,exact & near dupes\n"
            "Quality pass,920,low perplexity\n"
            "Eval clean,640,contamination\n",
            encoding="utf-8",
        )
        fig1 = tmp_path / "fig1.png"
        rc = cli_main([
            "plot",
            str(flow_csv),
            "--kind",
            "auto",
            "--takeaway",
            "Only 15% of raw documents survive filtering; deduplication drops 57%",
            "--title",
            "Corpus filtering funnel",
            "--label",
            "Documents (thousands)",
            "--source",
            "funnel.csv",
            "--out",
            str(fig1),
        ])
        assert rc == 0
        s1 = json.loads(capsys.readouterr().out)
        assert s1["ship"] is True
        assert s1["panels"][0]["kind"] == "flow"

        cmp_csv = tmp_path / "scores.csv"
        cmp_csv.write_text("model,accuracy\nAlpha-3,86.4\nBeta-Pro,83.2\nBaseline,77.1\n", encoding="utf-8")
        fig2 = tmp_path / "fig2.png"
        rc = cli_main([
            "plot",
            str(cmp_csv),
            "--kind",
            "auto",
            "--takeaway",
            "Alpha-3 leads Baseline by 9.3 points on accuracy",
            "--highlight",
            "Alpha-3",
            "--baseline",
            "Baseline",
            "--unit",
            "%",
            "--source",
            "scores.csv",
            "--out",
            str(fig2),
        ])
        assert rc == 0
        assert json.loads(capsys.readouterr().out)["ship"] is True

        # Compose both PNGs into HTML and Markdown briefings via `figmint brief`
        brief_html = tmp_path / "report.html"
        rc = cli_main([
            "brief",
            str(fig1),
            str(fig2),
            "--title",
            "Data & Eval Briefing",
            "--subtitle",
            "End-to-end zero-script CLI pipeline",
            "--summary",
            "Deduplication removes 57% of raw documents",
            "--summary",
            "Alpha-3 leads Baseline by 9.3 points",
            "--out",
            str(brief_html),
        ])
        assert rc == 0
        b_meta = json.loads(capsys.readouterr().out)
        assert b_meta["figure_count"] == 2
        assert b_meta["ship_all"] is True
        assert "<svg" in brief_html.read_text(encoding="utf-8")

        brief_md = tmp_path / "report.md"
        rc = cli_main([
            "brief",
            str(fig1),
            str(fig2),
            "--title",
            "Data & Eval Briefing",
            "--out",
            str(brief_md),
        ])
        assert rc == 0
        md_meta = json.loads(capsys.readouterr().out)
        assert md_meta["format"] == "markdown"
        assert len(md_meta["assets"]) == 2
        assert (tmp_path / "report_figures" / "fig_01.png").exists()
