"""Tests for mint.load_table_file, mint.inspect_data, mint.edit, and zero-script CLI subcommands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import mintfig as mint
from mintfig.cli import main as cli_main

# --------------------------------------------------------------------------- #
# 1. load_table_file & inspect_data
# --------------------------------------------------------------------------- #


class TestLoadAndInspectData:
    def test_load_csv_tsv_jsonl_and_json_shapes(self, tmp_path: Path) -> None:
        csv_p = tmp_path / "scores.csv"
        csv_p.write_text("model,score,missing_col\nAlpha,86.4%,\nBeta,77.1%,NA\n", encoding="utf-8")
        rows_csv = mint.load_table_file(csv_p)
        assert len(rows_csv) == 2
        assert rows_csv[0] == {"model": "Alpha", "score": 86.4, "missing_col": None}

        tsv_p = tmp_path / "scores.tsv"
        tsv_p.write_text("model\tscore\nAlpha\t86\nBeta\t77\n", encoding="utf-8")
        rows_tsv = mint.load_table_file(tsv_p)
        assert rows_tsv[0]["score"] == 86 and isinstance(rows_tsv[0]["score"], int)

        jsonl_p = tmp_path / "scores.jsonl"
        jsonl_p.write_text('{"model": "A", "score": 1.5}\n{"model": "B", "score": 2.5}\n', encoding="utf-8")
        assert len(mint.load_table_file(jsonl_p)) == 2

        # JSON column-oriented
        col_json = tmp_path / "cols.json"
        col_json.write_text(json.dumps({"model": ["A", "B"], "score": [80, 90]}), encoding="utf-8")
        assert mint.load_table_file(col_json) == [{"model": "A", "score": 80}, {"model": "B", "score": 90}]

        # JSON wrapped
        wrap_json = tmp_path / "wrap.json"
        wrap_json.write_text(json.dumps({"results": [{"model": "A", "score": 80}]}), encoding="utf-8")
        assert mint.load_table_file(wrap_json) == [{"model": "A", "score": 80}]

        # JSON flat dict
        flat_json = tmp_path / "flat.json"
        flat_json.write_text(json.dumps({"Alpha": 86.4, "Beta": 77.1}), encoding="utf-8")
        assert mint.load_table_file(flat_json) == [
            {"name": "Alpha", "value": 86.4},
            {"name": "Beta", "value": 77.1},
        ]

    def test_load_table_file_errors_cleanly(self, tmp_path: Path) -> None:
        with pytest.raises(mint.ExplainError, match="does not exist"):
            mint.load_table_file(tmp_path / "nope.csv")
        bad = tmp_path / "bad.xml"
        bad.write_text("<x/>", encoding="utf-8")
        with pytest.raises(mint.ExplainError, match="Unsupported"):
            mint.load_table_file(bad)

    def test_inspect_data_recommends_appropriate_forms(self, tmp_path: Path) -> None:
        # Timeline
        tl = mint.inspect_data([
            {"stage": "fetch", "start": 0, "end": 10, "lane": "io"},
            {"stage": "build", "start": 10, "end": 60, "lane": "cpu"},
        ])
        assert tl["recommendations"][0]["kind"] == "timeline"

        # Trend with replicates
        tr = mint.inspect_data([
            {"step": 0, "model": "A", "acc": 0.1},
            {"step": 0, "model": "A", "acc": 0.12},
            {"step": 500, "model": "A", "acc": 0.7},
            {"step": 1000, "model": "A", "acc": 0.85},
            {"step": 0, "model": "B", "acc": 0.1},
            {"step": 500, "model": "B", "acc": 0.6},
            {"step": 1000, "model": "B", "acc": 0.72},
        ])
        assert tr["recommendations"][0]["kind"] == "trend"
        assert "replicate" in tr["recommendations"][0]["reason"]

        # Waterfall (signed delta column)
        wf = mint.inspect_data([
            {"step": "+RAG", "delta": 8.0},
            {"step": "+CoT", "delta": 2.5},
            {"step": "Quant", "delta": -1.5},
        ])
        assert wf["recommendations"][0]["kind"] == "waterfall"

        # Distribution (multiple observations per group)
        dist = mint.inspect_data([
            {"group": g, "latency": float(v)}
            for g, vals in (("ctrl", [10, 12, 11, 13]), ("opt", [4, 5, 4.5, 6]))
            for v in vals
        ])
        assert dist["recommendations"][0]["kind"] == "distribution"

        # Multi-metric scorecard table + relate Pareto
        sc_csv = tmp_path / "models.csv"
        sc_csv.write_text(
            "model,cost,score,swe,aime\n"
            "Alpha-3,2.5,86.4,74.2,88.0\n"
            "Alpha-2,3.0,77.1,58.6,64.0\n"
            "Beta-Pro,6.0,83.2,71.0,79.0\n",
            encoding="utf-8",
        )
        sc = mint.inspect_data(sc_csv)
        kinds = [r["kind"] for r in sc["recommendations"]]
        assert "table" in kinds
        assert "relate" in kinds
        assert sc["recommendations"][0]["cli"].startswith("mintfig plot ")


# --------------------------------------------------------------------------- #
# 2. mint.edit
# --------------------------------------------------------------------------- #


class TestEditFunction:
    def test_edit_saved_png_top_level_and_panel_filters(self, tmp_path: Path) -> None:
        fig = mint.explain(
            "Checkout p99 is 4x slower than search",
            mint.compare(
                {"checkout": 1840, "search": 460, "auth": 310, "billing": 290},
                title="Service p99",
                label="Latency",
                unit="ms",
                highlight="checkout",
                baseline="auth",
            ),
            mint.waterfall(
                {"+Cache": -800, "+Index": -400, "Logging": 40},
                start=("Current", 1840),
                title="Planned savings",
                label="Latency",
                unit="ms",
            ),
            subtitle="Production cluster",
            source="traces/q4",
        )
        png = tmp_path / "orig.png"
        fig.save(png)

        out_png = tmp_path / "edited.png"
        edited = mint.edit(
            png,
            takeaway="Checkout p99 leads auth by +1,530 ms",
            subtitle=None,
            style="dark",
            accent="#D97757",
            panel="a",
            drop="billing",
            show_delta=True,
            drop_panel="b",
            out=out_png,
            write_spec=True,
        )
        assert out_png.exists()
        assert out_png.with_suffix(".json").exists()
        spec = edited.to_spec()
        assert spec["style"] == "dark"
        assert spec["accent"] == "#D97757"
        assert "subtitle" not in spec
        assert len(spec["panels"]) == 1
        assert "billing" not in spec["panels"][0]["values"]
        assert spec["panels"][0]["show_delta"] is True
        assert edited.summary()["ship"] is True

    def test_edit_keep_and_drop_across_grouped_trend_table_timeline(self) -> None:
        # Grouped compare: drop an inner series
        gfig = mint.explain(
            "Alpha-3 leads Beta-Pro across both suites",
            mint.compare(
                {
                    "GPQA": {"Alpha-3": 86, "Beta-Pro": 83, "Old": 70},
                    "SWE": {"Alpha-3": 74, "Beta-Pro": 71, "Old": 55},
                },
                highlight="Alpha-3",
                unit="%",
            ),
            source="synthetic",
        )
        g2 = mint.edit(gfig, drop="Old")
        assert all("Old" not in sub for sub in g2.to_spec()["panels"][0]["values"].values())

        # Trend: keep specific series
        tfig = mint.explain(
            "Model A reaches 0.85 while B stays at 0.72",
            mint.trend([0, 1, 2], {"A": [0.1, 0.6, 0.85], "B": [0.1, 0.5, 0.72], "C": [0.1, 0.4, 0.60]}),
            source="synthetic",
        )
        t2 = mint.edit(tfig, keep=["A", "B"])
        assert set(t2.to_spec()["panels"][0]["series"]) == {"A", "B"}

        # Table: drop a row
        tbl = mint.explain(
            "Alpha leads Beta on accuracy",
            mint.table([{"Model": "Alpha", "Acc": 86}, {"Model": "Beta", "Acc": 77}, {"Model": "DropMe", "Acc": 50}]),
            source="synthetic",
        )
        tbl2 = mint.edit(tbl, drop="DropMe")
        assert len(tbl2.to_spec()["panels"][0]["rows"]) == 2

        # Timeline: drop a stage
        tl = mint.explain(
            "Build dominates at 60 s",
            mint.timeline([("setup", 0, 5), ("build", 5, 65), ("cleanup", 65, 68)], unit="s"),
            source="synthetic",
        )
        tl2 = mint.edit(tl, drop="cleanup")
        assert len(tl2.to_spec()["panels"][0]["spans"]) == 2

    def test_edit_drop_prunes_table_graphics_and_sets_density(self) -> None:
        rows = [
            {"Model": "Alpha", "Acc": 86.0, "Cal": 0.74, "lo": 0.71, "hi": 0.77, "Cost": 2.5},
            {"Model": "Beta", "Acc": 77.0, "Cal": 0.69, "lo": 0.65, "hi": 0.73, "Cost": 3.0},
        ]
        tbl = mint.explain(
            "Alpha leads Beta by 9 points of accuracy",
            mint.table(rows, units={"Acc": "%"}, bars=["Acc", "Cost"],
                       interval={"Cal": ("lo", "hi")}, interval_label="95% CI",
                       spark={"Trend": {"Alpha": [1, 2, 3], "Beta": [3, 2, 1]}}),
            source="synthetic",
        )
        no_cal = mint.edit(tbl, drop="Cal").to_spec()["panels"][0]
        assert no_cal["columns"] == ["Model", "Acc", "Cost"]  # its bound columns go with it
        assert no_cal.get("interval") is None and no_cal.get("interval_label") is None
        no_cost = mint.edit(tbl, drop="Cost").to_spec()["panels"][0]
        assert no_cost["bars"] == ["Acc"] and no_cost["interval"] == {"Cal": ["lo", "hi"]}
        kept = mint.edit(tbl, keep=["Model", "Cal"]).to_spec()["panels"][0]
        assert kept["columns"] == ["Model", "Cal", "lo", "hi"] and kept.get("bars") is None
        no_beta = mint.edit(tbl, drop="Beta").to_spec()["panels"][0]
        assert no_beta["spark"] == {"Trend": {"Alpha": [1.0, 2.0, 3.0]}}

        compact = mint.edit(tbl, density="compact", color_names=False)
        assert compact.density == "compact" and compact.color_names is False
        assert compact.to_spec()["density"] == "compact"
        assert compact.to_spec()["color_names"] is False


# --------------------------------------------------------------------------- #
# 3. CLI: mintfig inspect, mintfig plot, mintfig edit
# --------------------------------------------------------------------------- #


class TestZeroScriptCli:
    def test_cli_inspect_plot_and_edit_workflow(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        csv_p = tmp_path / "latency.csv"
        csv_p.write_text(
            "service,p99_ms\ncheckout,1840\nsearch,460\nauth,310\nbilling,290\n",
            encoding="utf-8",
        )

        # 1. mintfig inspect --json
        rc = cli_main(["inspect", str(csv_p), "--json"])
        assert rc == 0
        inspected = json.loads(capsys.readouterr().out)
        assert inspected["rows"] == 4
        assert inspected["recommendations"][0]["kind"] == "compare"

        # 2. mintfig inspect (human text)
        rc = cli_main(["inspect", str(csv_p)])
        assert rc == 0
        txt = capsys.readouterr().out
        assert "latency.csv" in txt and "mintfig plot" in txt

        # 3. mintfig plot -> PNG
        fig_png = tmp_path / "lat.png"
        rc = cli_main([
            "plot",
            str(csv_p),
            "--kind",
            "compare",
            "--name",
            "service",
            "--value",
            "p99_ms",
            "--takeaway",
            "Checkout p99 is 4x slower than search at 1,840 ms",
            "--highlight",
            "checkout",
            "--baseline",
            "auth",
            "--unit",
            "ms",
            "--label",
            "p99 latency",
            "--source",
            "latency.csv",
            "--out",
            str(fig_png),
        ])
        assert rc == 0
        plot_summary = json.loads(capsys.readouterr().out)
        assert plot_summary["ship"] is True
        assert fig_png.exists()

        # 4. mintfig plot --show (no --out needed)
        rc = cli_main([
            "plot",
            str(csv_p),
            "--kind",
            "compare",
            "--takeaway",
            "Checkout p99 is 4x slower than search",
            "--show",
            "--show-mode",
            "ascii",
        ])
        assert rc == 0
        term_out = capsys.readouterr().out
        assert "checkout" in term_out

        # 5. mintfig edit -> HTML
        edited_html = tmp_path / "lat_dark.html"
        rc = cli_main([
            "edit",
            str(fig_png),
            "--style",
            "dark",
            "--drop",
            "billing",
            "--show-delta",
            "--out",
            str(edited_html),
        ])
        assert rc == 0
        edit_summary = json.loads(capsys.readouterr().out)
        assert edit_summary["ship"] is True
        assert edited_html.exists()
        assert "<svg" in edited_html.read_text(encoding="utf-8")
        assert edit_summary["deliver"]["html"].endswith("lat_dark.html")  # written by save()

    def test_cli_density_and_color_name_flags(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        csv_p = tmp_path / "latency.csv"
        csv_p.write_text("service,p99_ms\ncheckout,1840\nsearch,460\nauth,310\n", encoding="utf-8")
        png = tmp_path / "lat.png"
        rc = cli_main(["plot", str(csv_p), "--kind", "compare", "--takeaway",
                       "Checkout p99 is 4x search", "--density", "compact",
                       "--no-color-names", "--out", str(png)])
        assert rc == 0
        capsys.readouterr()
        spec = mint.load(png).to_spec()
        assert spec["density"] == "compact" and spec["color_names"] is False

        regular = tmp_path / "regular.png"
        assert cli_main(["edit", str(png), "--density", "regular", "--out", str(regular)]) == 0
        capsys.readouterr()
        assert "density" not in mint.load(regular).to_spec()

        again = tmp_path / "again.html"
        assert cli_main(["explain", str(regular), "--density", "compact", "--out", str(again)]) == 0
        assert json.loads(capsys.readouterr().out)["deliver"]["html"].endswith("again.html")
        assert '"density":"compact"' in again.read_text(encoding="utf-8")

    def test_cli_plot_waterfall_and_timeline(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        wf_csv = tmp_path / "bridge.csv"
        wf_csv.write_text("step,delta\n+RAG,8.0\n+CoT,2.5\nQuant,-1.5\n", encoding="utf-8")
        wf_png = tmp_path / "wf.png"
        rc = cli_main([
            "plot",
            str(wf_csv),
            "--kind",
            "waterfall",
            "--waterfall-start",
            "Base:69.0",
            "--takeaway",
            "RAG drives +8.0 points of the +9.0 point net gain",
            "--unit",
            "%",
            "--out",
            str(wf_png),
        ])
        assert rc == 0
        assert json.loads(capsys.readouterr().out)["ship"] is True
        assert wf_png.exists()

        tl_csv = tmp_path / "trace.csv"
        tl_csv.write_text("stage,start,end,lane\nfetch,0,8,setup\nbuild,8,54,build\ntest,54,140,verify\n", encoding="utf-8")
        tl_png = tmp_path / "tl.png"
        rc = cli_main([
            "plot",
            str(tl_csv),
            "--kind",
            "timeline",
            "--group",
            "lane",
            "--takeaway",
            "Tests take 86 s of the 140 s pipeline",
            "--unit",
            "s",
            "--out",
            str(tl_png),
        ])
        assert rc == 0
        assert json.loads(capsys.readouterr().out)["ship"] is True
        assert tl_png.exists()
