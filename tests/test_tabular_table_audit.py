"""Tests for layout audit in ship, tidy/row-shaped tabular inputs, fm.table, and progressive SKILL.md."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import figmint as fm
from figmint.explainer import _VISUAL_DEFECT_RULES
from figmint.skill import _build_cursor_mdc, get_skill_markdown, get_skill_references, install_skill
from figmint.themes import THEMES

# --------------------------------------------------------------------------- #
# Lightweight duck-typed DataFrame (no pandas required in test env)
# --------------------------------------------------------------------------- #


class _FakeIndex(list):
    def __init__(self, vals: list[Any], name: str | None = None) -> None:
        super().__init__(vals)
        self.name = name


class _FakeDataFrame:
    """Minimal duck-typed DataFrame matching the attributes _tabular.py reads."""

    def __init__(self, records: list[dict[str, Any]], index: _FakeIndex | None = None) -> None:
        self._records = [dict(r) for r in records]
        self.columns = list(dict.fromkeys(k for r in records for k in r))
        self.index = index if index is not None else _FakeIndex(list(range(len(records))))
        self.iloc = self._records

    def to_dict(self, orient: str = "records") -> list[dict[str, Any]]:
        assert orient == "records"
        return [dict(r) for r in self._records]


# --------------------------------------------------------------------------- #
# 1. Audit & ship gate
# --------------------------------------------------------------------------- #


class TestAuditAndShipGate:
    def test_visual_defect_rules_use_real_rule_names(self) -> None:
        assert "text_collision" not in _VISUAL_DEFECT_RULES
        assert {"text_overlaps", "text_struck_by_line", "text_malformed", "line_past_axis"} <= _VISUAL_DEFECT_RULES

    def test_audit_catches_malformed_text_and_blocks_ship(self) -> None:
        def _bad_draw(ax: Any) -> None:
            ax.plot([0, 1], [0, 1])
            ax.text(0.5, 0.5, "Change: -5.0%% (nan)", ha="center", va="center", fontsize=9)

        fig = fm.explain(
            "Custom panel has malformed text of 5 points",
            fm.custom(_bad_draw, title="Bad text"),
            source="synthetic test",
        )
        summary = fig.summary()
        rules = {i["rule"] for i in summary["issues"]}
        assert "text_malformed" in rules
        assert summary["ship"] is False

    def test_audit_catches_text_struck_by_line_and_blocks_ship(self) -> None:
        def _struck_draw(ax: Any) -> None:
            ax.plot([0, 1], [0.5, 0.5], linewidth=2.0)
            ax.text(0.5, 0.5, "StruckLabel", ha="center", va="center", fontsize=10)

        fig = fm.explain(
            "Line runs through label at 0.5",
            fm.custom(_struck_draw, title="Struck panel"),
            source="synthetic test",
        )
        summary = fig.summary()
        rules = {i["rule"] for i in summary["issues"]}
        assert "text_struck_by_line" in rules or "text_on_data" in rules
        assert summary["ship"] is False

    def test_audit_layout_on_saved_png(self, tmp_path: Path) -> None:
        fig = fm.explain(
            "Checkout p99 is 4x the next slowest service",
            fm.compare(
                {"checkout": 1840, "search": 460, "auth": 310},
                title="Checkout leads",
                label="p99 latency",
                unit="ms",
                highlight="checkout",
            ),
            source="synthetic test",
        )
        png = tmp_path / "clean.png"
        summary = fig.save(png)
        assert summary["ok"] is True
        assert summary["ship"] is True
        assert summary["issues"] == []

        audit = fm.audit_layout(png)
        assert audit["overlaps"] == []
        assert audit["struck"] == []
        assert audit["text_faults"] == []
        assert audit["texts"] > 0


# --------------------------------------------------------------------------- #
# 2. Row-shaped & tidy tabular inputs across all forms
# --------------------------------------------------------------------------- #


class TestTidyTabularInputs:
    def test_compare_two_col_rows_auto_infers_no_keyerror(self) -> None:
        rows = [
            {"service": "checkout", "p99": 1840},
            {"service": "search", "p99": 460},
            {"service": "auth", "p99": 310},
        ]
        fig = fm.explain(
            "Checkout is 4x slower than search at 1,840 ms",
            fm.compare(rows, title="p99 latency", label="Latency", unit="ms", highlight="checkout"),
            source="synthetic",
        )
        s = fig.summary()
        assert s["ok"] is True
        assert s["ship"] is True
        assert any("checkout" in f for f in s["panels"][0]["facts"])

    def test_compare_multi_col_rows_without_cols_raises_explain_error_not_keyerror(self) -> None:
        rows = [
            {"model": "A", "score": 0.82, "cost": 3.0},
            {"model": "B", "score": 0.74, "cost": 1.2},
        ]
        with pytest.raises(fm.ExplainError) as exc_info:
            fm.compare(rows)
        msg = str(exc_info.value)
        assert "name=" in msg and "value=" in msg
        assert "'model'" in msg and "'score'" in msg

    def test_compare_rows_with_error_and_n_columns(self) -> None:
        rows = [
            {"model": "Full", "acc": 0.82, "lo": 0.80, "hi": 0.84, "n": 5},
            {"model": "No RAG", "acc": 0.74, "lo": 0.71, "hi": 0.77, "n": 5},
            {"model": "Base", "acc": 0.69, "lo": 0.66, "hi": 0.72, "n": 5},
        ]
        fig = fm.explain(
            "Full model leads Base by 0.13 across 5 seeds",
            fm.compare(
                rows,
                name="model",
                value="acc",
                error=("lo", "hi"),
                error_label="95% CI",
                n="n",
                baseline="Base",
                highlight="Full",
                title="Accuracy with 95% CI",
                label="Accuracy",
            ),
            source="synthetic",
        )
        s = fig.summary()
        assert s["ok"] is True
        assert s["ship"] is True
        assert any("n=5" in f or "5" in f for f in s["panels"][0]["facts"])

    def test_share_tidy_rows(self) -> None:
        rows = [
            {"stage": "compile", "sec": 42, "owner": "core"},
            {"stage": "link", "sec": 18, "owner": "core"},
            {"stage": "test", "sec": 25, "owner": "qa"},
        ]
        fig = fm.explain(
            "Compile takes 49% of the 85 s build",
            fm.share(rows, name="stage", value="sec", title="Build breakdown", label="Build time", unit="s"),
            source="synthetic",
        )
        assert fig.summary()["ship"] is True

    def test_trend_rows_wrong_position_mentions_pivot_and_data(self) -> None:
        rows = [
            {"step": 0, "model": "A", "acc": 0.1},
            {"step": 100, "model": "A", "acc": 0.8},
        ]
        with pytest.raises(fm.ExplainError) as exc_info:
            fm.trend([0, 100], rows)
        msg = str(exc_info.value)
        assert "pivot" in msg.lower()
        assert "data=" in msg

    def test_trend_tidy_data_with_band_and_auto_replicates(self) -> None:
        rows = [
            {"step": 0, "model": "A", "acc": 0.10, "lo": 0.08, "hi": 0.12},
            {"step": 500, "model": "A", "acc": 0.75, "lo": 0.72, "hi": 0.78},
            {"step": 1000, "model": "A", "acc": 0.84, "lo": 0.81, "hi": 0.87},
            {"step": 0, "model": "B", "acc": 0.10, "lo": 0.08, "hi": 0.12},
            {"step": 500, "model": "B", "acc": 0.62, "lo": 0.59, "hi": 0.65},
            {"step": 1000, "model": "B", "acc": 0.71, "lo": 0.68, "hi": 0.74},
        ]
        fig = fm.explain(
            "Model A reaches 0.84 vs 0.71 for B by step 1000",
            fm.trend(
                "step",
                "model",
                y="acc",
                data=rows,
                band=("lo", "hi"),
                band_label="95% CI",
                title="Validation accuracy",
                label="Accuracy",
                x_label="Step",
            ),
            source="synthetic",
        )
        assert fig.summary()["ship"] is True

        # Repeated rows per (x, series) auto-populate points=
        rep_rows = [
            {"dose": 1, "drug": "X", "resp": 10.0},
            {"dose": 1, "drug": "X", "resp": 12.0},
            {"dose": 10, "drug": "X", "resp": 45.0},
            {"dose": 10, "drug": "X", "resp": 49.0},
            {"dose": 100, "drug": "X", "resp": 88.0},
            {"dose": 100, "drug": "X", "resp": 92.0},
        ]
        fig_rep = fm.explain(
            "Drug X rises from 11% to 90% across doses",
            fm.trend(
                "dose",
                "drug",
                y="resp",
                data=rep_rows,
                log_x=True,
                title="Dose response",
                label="Response",
                unit="%",
                x_label="Dose (nM)",
            ),
            source="synthetic",
        )
        assert fig_rep.summary()["ship"] is True
        assert fig_rep.panels["a"].spec.get("points") is not None

    def test_change_distribution_histogram_relate_matrix_tidy_inputs(self, tmp_path: Path) -> None:
        # change
        chg_rows = [
            {"metric": "GPQA", "v1": 72, "v2": 84},
            {"metric": "SWE", "v1": 49, "v2": 71},
            {"metric": "AIME", "v1": 60, "v2": 88},
        ]
        p_chg = fm.change("v1", "v2", data=chg_rows, name="metric", title="Release gains", label="Score", unit="%")
        assert p_chg.spec["labels"] == ["v1", "v2"]

        # distribution & histogram
        dist_rows = [
            {"cond": "ctrl", "val": v} for v in (4.1, 4.3, 3.9, 4.5, 4.0)
        ] + [
            {"cond": "drug", "val": v} for v in (7.8, 8.2, 7.5, 8.0, 8.4)
        ]
        p_dist = fm.distribution(dist_rows, group="cond", value="val", title="Spread", label="Signal", unit="mV")
        p_hist = fm.histogram(dist_rows, group="cond", value="val", title="Histogram", label="Signal", unit="mV")

        # relate
        rel_rows = [
            {"cost": 0.5, "score": 68, "model": "Mini", "family": "A"},
            {"cost": 2.0, "score": 79, "model": "Mid", "family": "A"},
            {"cost": 8.0, "score": 86, "model": "Pro", "family": "A"},
            {"cost": 1.0, "score": 71, "model": "Flash", "family": "B"},
            {"cost": 5.0, "score": 83, "model": "Ultra", "family": "B"},
        ]
        p_rel = fm.relate(
            "cost",
            "score",
            data=rel_rows,
            names="model",
            groups="family",
            log_x=True,
            x_label="Cost ($/M)",
            y_label="Score (%)",
            title="Cost vs score",
        )

        # matrix pivot
        mat_rows = [
            {"model": "M1", "bench": "GPQA", "score": 84},
            {"model": "M1", "bench": "SWE", "score": 72},
            {"model": "M2", "bench": "GPQA", "score": 76},
            {"model": "M2", "bench": "SWE", "score": None},
        ]
        p_mat = fm.matrix(mat_rows, rows="model", cols="bench", value="score", title="Scores", label="Accuracy", unit="%")

        for panel in (p_chg, p_dist, p_hist, p_rel, p_mat):
            fig = fm.explain("Synthetic check with value 84", panel, source="synthetic")
            s = fig.summary()
            assert s["ok"] is True
            assert s["ship"] is True

        # Round-trip a tidy figure through PNG embedded spec
        png = tmp_path / "tidy_rt.png"
        fig_rt = fm.explain("M1 scores 84% on GPQA", p_mat, source="synthetic")
        fig_rt.save(png)
        assert fm.load(png).to_spec() == fig_rt.to_spec()


# --------------------------------------------------------------------------- #
# 3. fm.table form
# --------------------------------------------------------------------------- #


class TestTableForm:
    def _scorecard_rows(self) -> list[dict[str, Any]]:
        return [
            {"Model": "Alpha-3", "GPQA": 86.4, "SWE-bench": 74.2, "Cost": 2.50},
            {"Model": "Alpha-2", "GPQA": 77.1, "SWE-bench": 58.6, "Cost": 3.00},
            {"Model": "Beta-Pro", "GPQA": 83.2, "SWE-bench": 71.0, "Cost": 6.00},
            {"Model": "Gamma-Fast", "GPQA": 71.5, "SWE-bench": None, "Cost": 0.40},
        ]

    @pytest.mark.parametrize("style_name", list(THEMES))
    def test_table_renders_clean_across_all_themes(self, style_name: str) -> None:
        fig = fm.explain(
            "Alpha-3 leads GPQA (86.4%) and SWE-bench (74.2%) at $2.50/M",
            fm.table(
                self._scorecard_rows(),
                units={"GPQA": "%", "SWE-bench": "%", "Cost": "$/M"},
                bold_best={"GPQA": "max", "SWE-bench": "max", "Cost": "min"},
                highlight="Alpha-3",
                baseline="Alpha-2",
                sort="-GPQA",
                fmt={"GPQA": ".1f", "SWE-bench": ".1f", "Cost": "${:.2f}"},
                title="Benchmark scorecard",
            ),
            source="synthetic evals",
            style=style_name,
        )
        s = fig.summary()
        assert s["ok"] is True
        assert s["ship"] is True
        assert s["issues"] == []
        facts = " ".join(s["panels"][0]["facts"])
        assert "Alpha-3" in facts
        assert "Alpha-2" in facts
        assert "empty cell" in facts

    def test_table_accepts_all_input_shapes_and_exports_markdown(self) -> None:
        # Column-oriented dict
        p_dict = fm.table({"Model": ["A", "B"], "Score": [91.2, 84.5]}, bold_best=True)
        md = p_dict.to_markdown()
        assert "| Model" in md and "91.2 |" in md

        # 2-D list + columns
        p_2d = fm.table([["A", 91.2], ["B", 84.5]], columns=["Model", "Score"])
        assert "2 rows" in p_2d.facts[0]

        # Duck-typed DataFrame with named index
        df = _FakeDataFrame(
            [{"GPQA": 86.4, "Cost": 2.5}, {"GPQA": 77.1, "Cost": 3.0}],
            index=_FakeIndex(["Alpha-3", "Alpha-2"], name="Model"),
        )
        p_df = fm.table(df, highlight="Alpha-3", baseline="Alpha-2")
        assert p_df.spec["columns"] == ["Model", "GPQA", "Cost"]

    def test_table_shares_entity_color_with_compare_and_roundtrips(self, tmp_path: Path) -> None:
        rows = self._scorecard_rows()
        fig = fm.explain(
            "Alpha-3 leads GPQA at 86.4% while cutting cost to $2.50/M",
            fm.compare(rows, name="Model", value="GPQA", title="GPQA score", label="Accuracy", unit="%", highlight="Alpha-3", baseline="Alpha-2"),
            fm.table(
                rows,
                units={"GPQA": "%", "SWE-bench": "%", "Cost": "$/M"},
                bold_best={"GPQA": "max", "SWE-bench": "max", "Cost": "min"},
                highlight="Alpha-3",
                baseline="Alpha-2",
                title="Exact metrics",
            ),
            layout=[["a"], ["b"]],
            source="synthetic evals",
        )
        png = tmp_path / "release_card.png"
        s = fig.save(png)
        assert s["ok"] is True
        assert s["ship"] is True
        assert "Alpha-3" in s["colors"]

        loaded = fm.load(png)
        assert loaded.to_spec() == fig.to_spec()
        rebuilt = fm.explain_from_spec(loaded.to_spec())
        assert rebuilt.summary()["ship"] is True

    def test_table_lenient_auto_stacks_when_cramped(self) -> None:
        rows = [
            {"Model": "LongModelName-v3", "GPQA": 86.4, "SWE-bench": 74.2, "AIME": 88.0, "Cost": 2.50},
            {"Model": "LongModelName-v2", "GPQA": 77.1, "SWE-bench": 58.6, "AIME": 64.0, "Cost": 3.00},
        ]
        with fm.lenient():
            fig = fm.explain(
                "v3 beats v2 on all three benchmarks by up to 24 points",
                fm.compare(rows, name="Model", value="GPQA", title="GPQA", label="Score", unit="%"),
                fm.table(rows, title="All metrics"),
                source="synthetic",
            )
        s = fig.summary()
        assert s["ship"] is True
        assert any("stacked panels" in a for a in s.get("adjustments", []))


# --------------------------------------------------------------------------- #
# 4. Progressive SKILL.md & Cursor .mdc rule
# --------------------------------------------------------------------------- #


class TestSkillProgressiveAndCursor:
    def test_skill_is_compact_and_has_install_line(self) -> None:
        md = get_skill_markdown()
        assert "pip install" in md
        assert "fm.table" in md
        chat_part = md[: md.index("## Publication Figures")]
        # Was 23,890 bytes (~6k tokens); should stay lean (<11k bytes)
        assert len(chat_part.encode("utf-8")) < 11_000

        refs = get_skill_references()
        assert "scientific_and_recipes.md" in refs
        assert "publication.md" in refs

    def test_cursor_mdc_covers_chat_and_tables(self) -> None:
        mdc = _build_cursor_mdc(get_skill_markdown())
        frontmatter = mdc.split("\n---\n", 1)[0]
        assert "chat figures" in frontmatter.lower()
        assert "fm.explain" in frontmatter
        assert "fm.table" in frontmatter
        assert "**/*.csv" in frontmatter

    def test_install_skill_copies_references_for_skill_targets(self, tmp_path: Path) -> None:
        written = install_skill(tmp_path, targets=("claude", "antigravity", "codex", "cursor"))
        assert len(written) == 4
        for base in (
            tmp_path / ".claude/skills/figmint",
            tmp_path / ".agents/skills/figmint",
            tmp_path / ".codex/skills/figmint",
        ):
            assert (base / "SKILL.md").exists()
            assert (base / "references/scientific_and_recipes.md").exists()
            assert (base / "references/publication.md").exists()
