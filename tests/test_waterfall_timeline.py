"""Tests for fm.waterfall (attribution bridges) and fm.timeline (execution span timelines)."""

from __future__ import annotations

from pathlib import Path

import pytest

import figmint as fm
from figmint.themes import THEMES

# --------------------------------------------------------------------------- #
# fm.waterfall
# --------------------------------------------------------------------------- #


class TestWaterfallForm:
    def _ablation_steps(self) -> dict[str, float]:
        return {
            "+Retrieval": 8.2,
            "+Reranker": 3.4,
            "+Chain-of-thought": 2.1,
            "int4 quantization": -1.5,
        }

    @pytest.mark.parametrize("style_name", list(THEMES))
    def test_waterfall_renders_clean_across_all_themes(self, style_name: str) -> None:
        fig = fm.explain(
            "Retrieval adds +8.2 points while quantization costs only 1.5 points",
            fm.waterfall(
                self._ablation_steps(),
                start=("Base model", 69.0),
                total_label="Shipped",
                highlight="+Retrieval",
                reference=(80.0, "Release target"),
                title="Ablation bridge from base to shipped",
                label="Accuracy",
                unit="%",
            ),
            source="synthetic ablation suite",
            style=style_name,
        )
        summary = fig.summary()
        assert summary["ok"] is True
        assert summary["ship"] is True
        assert summary["issues"] == []
        facts = " ".join(summary["panels"][0]["facts"])
        assert "Base model" in facts
        assert "81.2" in facts
        assert "+Retrieval" in facts
        assert "int4 quantization" in facts
        assert "Release target" in facts
        # Narrative classifies L1/L2/L3 cleanly
        assert "waterfall" in summary["narrative"]["L1"]
        assert summary["narrative"]["L3"]

    def test_waterfall_tidy_rows_scalar_start_and_no_total(self) -> None:
        rows = [
            {"driver": "Cache warm-up", "delta_ms": -42.0},
            {"driver": "Batching", "delta_ms": -18.5},
            {"driver": "Audit logging", "delta_ms": 6.5},
            {"driver": "No-op check", "delta_ms": 0.0},
        ]
        fig = fm.explain(
            "Cache warm-up and batching cut 54 ms net off p99 latency",
            fm.waterfall(
                rows,
                name="driver",
                value="delta_ms",
                start=180.0,
                show_total=False,
                title="Latency contributions",
                label="p99 latency",
                unit="ms",
            ),
            source="synthetic trace",
        )
        s = fig.summary()
        assert s["ok"] is True
        assert s["ship"] is True
        assert any("126" in f for f in s["panels"][0]["facts"])

    def test_waterfall_without_start_and_negative_only(self) -> None:
        fig = fm.explain(
            "Three regressions together drop throughput by 35 req/s",
            fm.waterfall(
                {"JSON parse": -15.0, "TLS handshake": -12.0, "Extra copy": -8.0},
                title="Throughput regressions",
                label="Delta",
                unit="req/s",
            ),
            source="synthetic benchmark",
        )
        s = fig.summary()
        assert s["ok"] is True
        assert s["ship"] is True
        assert any("35" in f for f in s["panels"][0]["facts"])

    def test_waterfall_lenient_folds_smaller_steps_preserving_exact_total(self) -> None:
        steps = {f"Step {i:02d}": float(i if i % 2 == 0 else -i * 0.5) for i in range(1, 19)}
        expected_total = 100.0 + sum(steps.values())
        with pytest.raises(fm.ExplainError):
            fm.waterfall(steps, start=100.0)
        with fm.lenient():
            fig = fm.explain(
                f"Eighteen adjustments move the score to {expected_total:.1f}",
                fm.waterfall(steps, start=("Base", 100.0), highlight="Step 01", title="All adjustments", label="Score"),
                source="synthetic",
            )
        s = fig.summary()
        assert s["ship"] is True
        assert any("folded" in adj for adj in s.get("adjustments", []))
        spec_steps = fig.to_spec()["panels"][0]["steps"]
        assert any(k.startswith("Other (") for k in spec_steps)
        assert pytest.approx(100.0 + sum(spec_steps.values()), rel=1e-6) == expected_total

    def test_waterfall_roundtrip_html_and_terminal(self, tmp_path: Path) -> None:
        fig = fm.explain(
            "Retrieval drives +8.2 points of the +12.2 point gain",
            fm.waterfall(
                self._ablation_steps(),
                start=("Base", 69.0),
                highlight="+Retrieval",
                title="Accuracy bridge",
                label="Accuracy",
                unit="%",
            ),
            source="synthetic",
        )
        png = tmp_path / "bridge.png"
        fig.save(png)
        reloaded = fm.load(png)
        assert reloaded.to_spec() == fig.to_spec()
        assert fm.explain_from_spec(reloaded.to_spec()).summary()["ship"] is True

        html_out = fig.to_html()
        assert "+Retrieval" in html_out
        assert "Base" in html_out
        assert "81.2" in html_out

        term = fig.to_terminal(color=False)
        assert "+Retrieval" in term
        assert "Total" in term


# --------------------------------------------------------------------------- #
# fm.timeline
# --------------------------------------------------------------------------- #


class TestTimelineForm:
    def _ci_spans(self) -> list[tuple[str, float, float, str]]:
        return [
            ("checkout", 0, 8, "setup"),
            ("deps cache", 8, 22, "setup"),
            ("compile", 22, 68, "build"),
            ("unit tests", 68, 102, "verify"),
            ("integration", 68, 162, "verify"),
            ("canary gate", 162, 162, "release"),
            ("deploy", 162, 178, "release"),
        ]

    @pytest.mark.parametrize("style_name", list(THEMES))
    def test_timeline_renders_clean_across_all_themes(self, style_name: str) -> None:
        fig = fm.explain(
            "Integration tests take 94 s (53% of the 178 s pipeline) and push past the 150 s SLA",
            fm.timeline(
                self._ci_spans(),
                highlight="integration",
                reference=(150, "CI SLA"),
                title="Build and verification trace",
                x_label="Elapsed (s)",
                unit="s",
            ),
            source="synthetic CI trace",
            style=style_name,
        )
        s = fig.summary()
        assert s["ok"] is True
        assert s["ship"] is True
        assert s["issues"] == []
        facts = " ".join(s["panels"][0]["facts"])
        assert "178" in facts
        assert "integration" in facts
        assert "peak 2 stages overlapping" in facts
        assert "CI SLA" in facts
        assert "timeline" in s["narrative"]["L1"]

    def test_timeline_dict_and_tidy_rows_and_group_highlight(self) -> None:
        # Dict input
        p_dict = fm.timeline(
            {"fetch": (0, 5), "parse": (5, 19), "rank": (19, 31)},
            title="Sequential trace",
            unit="ms",
        )
        assert any("sequential" in f for f in p_dict.facts)

        # Tidy rows with group highlight
        rows = [
            {"stage": "plan", "t0": 0.0, "t1": 2.4, "actor": "coordinator"},
            {"stage": "search", "t0": 2.4, "t1": 6.8, "actor": "worker"},
            {"stage": "fetch", "t0": 2.4, "t1": 9.1, "actor": "worker"},
            {"stage": "synthesize", "t0": 9.1, "t1": 12.0, "actor": "coordinator"},
        ]
        fig = fm.explain(
            "Parallel worker stages run concurrently for 6.7 s of the 12 s trace",
            fm.timeline(
                rows,
                name="stage",
                start="t0",
                end="t1",
                group="actor",
                highlight="worker",
                sort=False,
                title="Agent execution trace",
                unit="s",
            ),
            source="synthetic agent log",
        )
        s = fig.summary()
        assert s["ok"] is True
        assert s["ship"] is True

    def test_timeline_rejects_end_before_start(self) -> None:
        with pytest.raises(fm.ExplainError, match="ends"):
            fm.timeline({"broken": (50, 10)})

    def test_timeline_roundtrip_html_and_terminal(self, tmp_path: Path) -> None:
        fig = fm.explain(
            "Integration tests dominate the 178 s CI run at 94 s",
            fm.timeline(
                self._ci_spans(),
                highlight="integration",
                title="CI trace",
                x_label="Elapsed (s)",
                unit="s",
            ),
            source="synthetic CI",
        )
        png = tmp_path / "trace.png"
        fig.save(png)
        reloaded = fm.load(png)
        assert reloaded.to_spec() == fig.to_spec()
        assert fm.explain_from_spec(reloaded.to_spec()).summary()["ship"] is True

        html_out = fig.to_html()
        assert "integration" in html_out
        assert "canary gate" in html_out

        term = fig.to_terminal(color=False)
        assert "integration" in term
        assert "CI trace" in term
