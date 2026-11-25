"""Tests for Step 3: grouped & boost compare, Pareto/label_all/trajectories on relate, accent & slide mode."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import figmint as fm
from figmint.cli import main as cli_main


class TestGroupedAndBoostCompare:
    def test_grouped_compare_nested_dict_renders_clean_and_roundtrips(self, tmp_path: Path) -> None:
        scores = {
            "GPQA Diamond": {"Alpha-3": 86.4, "Alpha-2": 77.1, "Beta-Pro": 83.2},
            "SWE-bench": {"Alpha-3": 74.2, "Alpha-2": 58.6, "Beta-Pro": 71.0},
            "AIME 2026": {"Alpha-3": 88.0, "Alpha-2": 64.0, "Beta-Pro": 82.0},
            "MMMU": {"Alpha-3": 79.5, "Alpha-2": 71.0, "Beta-Pro": 77.8},
        }
        fig = fm.explain(
            "Alpha-3 leads all 4 frontier benchmarks over Alpha-2 and Beta-Pro",
            fm.compare(
                scores,
                highlight="Alpha-3",
                baseline="Alpha-2",
                title="Frontier benchmark comparison",
                label="Accuracy",
                unit="%",
            ),
            source="synthetic model release",
        )
        png = tmp_path / "grouped_compare.png"
        s = fig.save(png)
        assert s["ok"] is True
        assert s["ship"] is True
        assert s["issues"] == []
        facts = " ".join(s["panels"][0]["facts"])
        assert "Alpha-3 leads 4 of 4 categories" in facts
        assert "Alpha-3 vs Alpha-2" in facts

        loaded = fm.load(png)
        assert loaded.to_spec() == fig.to_spec()
        assert fm.explain_from_spec(loaded.to_spec()).summary()["ship"] is True

    def test_grouped_compare_tidy_rows_with_group_col(self) -> None:
        rows = [
            {"bench": "GPQA", "model": "Alpha-3", "score": 86.4},
            {"bench": "GPQA", "model": "Alpha-2", "score": 77.1},
            {"bench": "SWE", "model": "Alpha-3", "score": 74.2},
            {"bench": "SWE", "model": "Alpha-2", "score": 58.6},
            {"bench": "AIME", "model": "Alpha-3", "score": 88.0},
            {"bench": "AIME", "model": "Alpha-2", "score": None},
        ]
        fig = fm.explain(
            "Alpha-3 leads Alpha-2 across all 3 benchmarks by up to 15.6 points",
            fm.compare(
                rows,
                name="bench",
                group="model",
                value="score",
                highlight="Alpha-3",
                baseline="Alpha-2",
                title="Tidy grouped bars",
                label="Accuracy",
                unit="%",
            ),
            source="synthetic",
        )
        s = fig.summary()
        assert s["ok"] is True
        assert s["ship"] is True

    def test_boost_stacked_compare_renders_clean_and_warns_when_unlabelled(
        self, tmp_path: Path
    ) -> None:
        base_scores = {"Alpha-3": 76.0, "Beta-Pro": 74.0, "Alpha-2": 64.0}
        thinking_gain = {"Alpha-3": 10.4, "Beta-Pro": 8.0, "Alpha-2": 6.2}
        fig = fm.explain(
            "Extended thinking lifts Alpha-3 from 76.0% to 86.4% (+10.4 points)",
            fm.compare(
                base_scores,
                boost=thinking_gain,
                boost_label="Extended thinking",
                highlight="Alpha-3",
                baseline="Alpha-2",
                title="AIME 2026: base vs extended thinking",
                label="Accuracy",
                unit="%",
            ),
            source="synthetic evals",
        )
        png = tmp_path / "boost_compare.png"
        s = fig.save(png)
        assert s["ok"] is True
        assert s["ship"] is True
        assert s["issues"] == []
        facts = " ".join(s["panels"][0]["facts"])
        assert "Extended thinking" in facts
        assert "86.4%" in facts
        assert fm.load(png).to_spec() == fig.to_spec()

        # Unlabelled boost triggers advisory warning
        fig_unlabelled = fm.explain(
            "Alpha-3 reaches 86.4% with boost",
            fm.compare(base_scores, boost=thinking_gain, label="Accuracy", unit="%"),
            source="synthetic",
        )
        assert any(i["rule"] == "boost_unlabelled" for i in fig_unlabelled.summary()["issues"])

    def test_boost_from_tidy_row_column(self) -> None:
        rows = [
            {"model": "Alpha-3", "std": 76.0, "think": 10.4},
            {"model": "Alpha-2", "std": 64.0, "think": 6.2},
            {"model": "Beta-Pro", "std": 74.0, "think": 8.0},
        ]
        fig = fm.explain(
            "Alpha-3 reaches 86.4% with extended thinking",
            fm.compare(
                rows,
                name="model",
                value="std",
                boost="think",
                boost_label="Extended thinking",
                highlight="Alpha-3",
                title="AIME 2026",
                label="Accuracy",
                unit="%",
            ),
            source="synthetic",
        )
        assert fig.summary()["ship"] is True


class TestRelateParetoAndLabels:
    def _frontier_rows(self) -> list[dict[str, object]]:
        return [
            {"model": "Alpha-3 Mini", "family": "Alpha", "cost": 0.35, "score": 76.5},
            {"model": "Alpha-3", "family": "Alpha", "cost": 2.50, "score": 86.4},
            {"model": "Alpha-3 Max", "family": "Alpha", "cost": 9.00, "score": 89.2},
            {"model": "Beta-Lite", "family": "Beta", "cost": 0.60, "score": 72.0},
            {"model": "Beta-Pro", "family": "Beta", "cost": 6.00, "score": 83.2},
            {"model": "Gamma-Fast", "family": "Gamma", "cost": 0.15, "score": 68.0},
            {"model": "Gamma-Large", "family": "Gamma", "cost": 4.50, "score": 80.5},
        ]

    def test_relate_pareto_frontier_label_all_and_trajectories(self, tmp_path: Path) -> None:
        fig = fm.explain(
            "Alpha-3 defines the upper-left capability-cost frontier at 86.4% for $2.50/M",
            fm.relate(
                "cost",
                "score",
                data=self._frontier_rows(),
                names="model",
                groups="family",
                highlight="Alpha",
                frontier=True,
                label_all=True,
                connect_groups=True,
                log_x=True,
                x_label="Blended cost ($/M tokens)",
                y_label="GPQA Diamond (%)",
                unit="%",
                title="Capability vs cost frontier",
            ),
            source="synthetic pricing & evals",
        )
        png = tmp_path / "frontier.png"
        s = fig.save(png)
        assert s["ok"] is True
        assert s["ship"] is True
        facts = " ".join(s["panels"][0]["facts"])
        assert "Pareto frontier (upper-left" in facts
        assert "Alpha-3" in facts
        assert "Gamma-Fast" in facts
        assert "Beta-Pro" not in facts.split("Pareto frontier")[1]

        loaded = fm.load(png)
        assert loaded.to_spec() == fig.to_spec()

    def test_relate_validation_errors(self) -> None:
        with pytest.raises(fm.ExplainError):
            fm.relate([1, 2, 3], [4, 5, 6], x_label="X", y_label="Y", label_all=True)
        with pytest.raises(fm.ExplainError):
            fm.relate([1, 2, 3], [4, 5, 6], x_label="X", y_label="Y", connect_groups=True)
        with pytest.raises(fm.ExplainError):
            fm.relate([1, 2, 3], [4, 5, 6], x_label="X", y_label="Y", frontier="sideways")


class TestReleaseCardAccentAndSlideWidth:
    def test_accent_and_slide_width_ship_clean_without_small_at_chat_warning(
        self, tmp_path: Path
    ) -> None:
        rows = [
            {"Model": "Alpha-3", "GPQA": 86.4, "SWE-bench": 74.2, "Cost": 2.50},
            {"Model": "Alpha-2", "GPQA": 77.1, "SWE-bench": 58.6, "Cost": 3.00},
            {"Model": "Beta-Pro", "GPQA": 83.2, "SWE-bench": 71.0, "Cost": 6.00},
        ]
        fig = fm.explain(
            "Alpha-3 sets a new frontier at 86.4% GPQA and 74.2% SWE-bench",
            fm.compare(
                {
                    "GPQA": {"Alpha-3": 86.4, "Alpha-2": 77.1, "Beta-Pro": 83.2},
                    "SWE-bench": {"Alpha-3": 74.2, "Alpha-2": 58.6, "Beta-Pro": 71.0},
                },
                highlight="Alpha-3",
                baseline="Alpha-2",
                title="Head-to-head benchmarks",
                label="Accuracy",
                unit="%",
            ),
            fm.table(
                rows,
                units={"GPQA": "%", "SWE-bench": "%", "Cost": "$/M"},
                bold_best={"GPQA": "max", "SWE-bench": "max", "Cost": "min"},
                highlight="Alpha-3",
                baseline="Alpha-2",
                title="Release scorecard",
            ),
            width="slide",
            style="paper",
            accent="#D97757",
            source="synthetic release evals",
        )
        png = tmp_path / "release_slide.png"
        s = fig.save(png)
        assert s["ok"] is True
        assert s["ship"] is True
        assert s["display"]["width_px"] == 1280
        assert not any(i["rule"] == "small_at_chat_size" for i in s["issues"])
        assert fig.to_spec()["accent"] == "#D97757"
        assert fm.load(png).to_spec() == fig.to_spec()

    def test_cli_accent_override(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        spec_path = tmp_path / "spec.json"
        out_png = tmp_path / "out.png"
        spec_path.write_text(
            json.dumps(
                {
                    "takeaway": "Alpha-3 scores 86.4% vs 77.1% for Alpha-2",
                    "source": "synthetic",
                    "panels": [
                        {
                            "kind": "compare",
                            "title": "GPQA",
                            "label": "Accuracy",
                            "unit": "%",
                            "values": {"Alpha-3": 86.4, "Alpha-2": 77.1},
                            "highlight": "Alpha-3",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        rc = cli_main(["explain", str(spec_path), "--accent", "#10A37F", "--out", str(out_png)])
        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert out["ship"] is True
        assert fm.load(out_png).to_spec()["accent"] == "#10A37F"
