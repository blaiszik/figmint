"""Tests for SWE dev-tool ingestors, `mintfig diff`, and terminal/Markdown CLI flags."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pytest

import mintfig as mint
from mintfig.cli import main as cli_main
from mintfig.diff import DiffResult, diff_runs
from mintfig.ingest import detect_tool_format, load_tool_output

# --------------------------------------------------------------------------- #
# Sample payloads for all 7+ SWE dev-tool formats
# --------------------------------------------------------------------------- #

HYPERFINE_BASE = {
    "results": [
        {
            "command": "ripgrep",
            "mean": 0.120,
            "stddev": 0.008,
            "min": 0.110,
            "max": 0.135,
            "times": [0.112, 0.118, 0.121, 0.124, 0.125],
        },
        {
            "command": "grep -r",
            "mean": 0.850,
            "stddev": 0.030,
            "min": 0.810,
            "max": 0.890,
            "times": [0.815, 0.840, 0.855, 0.862, 0.878],
        },
        {
            "command": "ag",
            "mean": 0.340,
            "stddev": 0.025,
            "min": 0.305,
            "max": 0.375,
            "times": [0.312, 0.330, 0.342, 0.351, 0.365],
        },
    ]
}

HYPERFINE_HEAD = {
    "results": [
        {
            "command": "ripgrep",
            "mean": 0.122,  # within +/- 0.008 noise overlap with 0.120 +/- 0.008
            "stddev": 0.009,
            "min": 0.112,
            "max": 0.138,
            "times": [0.113, 0.119, 0.122, 0.126, 0.130],
        },
        {
            "command": "grep -r",
            "mean": 1.150,  # clear regression (+35.3%), non-overlapping
            "stddev": 0.025,
            "min": 1.110,
            "max": 1.190,
            "times": [1.120, 1.140, 1.150, 1.165, 1.175],
        },
        {
            "command": "ag",
            "mean": 0.210,  # clear improvement (-38.2%), non-overlapping
            "stddev": 0.015,
            "min": 0.190,
            "max": 0.230,
            "times": [0.195, 0.205, 0.210, 0.215, 0.225],
        },
    ]
}

PYTEST_BENCH_BASE = {
    "benchmarks": [
        {
            "name": "test_parse_json",
            "stats": {
                "mean": 0.0042,
                "stddev": 0.0002,
                "min": 0.0039,
                "max": 0.0046,
                "median": 0.0042,
                "iqr": 0.0002,
                "rounds": 120,
            },
        },
        {
            "name": "test_encode_msgpack",
            "stats": {
                "mean": 0.0018,
                "stddev": 0.0001,
                "min": 0.0016,
                "max": 0.0020,
                "median": 0.0018,
                "iqr": 0.0001,
                "rounds": 200,
            },
        },
    ]
}

PYTEST_BENCH_HEAD = {
    "benchmarks": [
        {
            "name": "test_parse_json",
            "stats": {
                "mean": 0.0055,  # +31% slower
                "stddev": 0.0002,
                "min": 0.0052,
                "max": 0.0059,
                "median": 0.0055,
                "iqr": 0.0002,
                "rounds": 120,
            },
        },
        {
            "name": "test_encode_msgpack",
            "stats": {
                "mean": 0.00185,  # within noise
                "stddev": 0.00012,
                "min": 0.0017,
                "max": 0.0020,
                "median": 0.00185,
                "iqr": 0.0001,
                "rounds": 200,
            },
        },
    ]
}

GO_BENCH_BASE = """\
goos: darwin
goarch: arm64
pkg: example.com/fastjson
BenchmarkDecode-8       500000      2400 ns/op    512 B/op     4 allocs/op
BenchmarkEncode-8      1000000      1250 ns/op    256 B/op     2 allocs/op
BenchmarkValidate-8    2000000       610 ns/op      0 B/op     0 allocs/op
PASS
ok      example.com/fastjson    4.123s
"""

GO_BENCH_HEAD = """\
goos: darwin
goarch: arm64
pkg: example.com/fastjson
BenchmarkDecode-8       500000      1800 ns/op    384 B/op     3 allocs/op
BenchmarkEncode-8      1000000      1500 ns/op    256 B/op     2 allocs/op
BenchmarkValidate-8    2000000       610 ns/op      0 B/op     0 allocs/op
PASS
ok      example.com/fastjson    3.890s
"""

CARGO_BENCH_LOG = """\
running 3 tests
test bench_lexer   ... bench:       1,234 ns/iter (+/- 45)
test bench_parser  ... bench:      12,450 ns/iter (+/- 310)
test bench_codegen ... bench:       6,780 ns/iter (+/- 180)

test result: ok. 0 passed; 0 failed; 0 ignored; 3 measured; 0 filtered out
"""

GHA_TIMINGS = {
    "jobs": [
        {
            "name": "build-and-test",
            "started_at": "2026-05-01T10:00:00Z",
            "completed_at": "2026-05-01T10:02:10Z",
            "steps": [
                {
                    "name": "Checkout",
                    "started_at": "2026-05-01T10:00:00Z",
                    "completed_at": "2026-05-01T10:00:08Z",
                },
                {
                    "name": "Install deps",
                    "started_at": "2026-05-01T10:00:08Z",
                    "completed_at": "2026-05-01T10:00:42Z",
                },
                {
                    "name": "Run pytest",
                    "started_at": "2026-05-01T10:00:42Z",
                    "completed_at": "2026-05-01T10:02:10Z",
                },
            ],
        }
    ]
}

CHROME_TRACE = {
    "traceEvents": [
        {"name": "dns_lookup", "cat": "net", "ph": "X", "ts": 1_000_000, "dur": 12_500},
        {"name": "tls_handshake", "cat": "net", "ph": "X", "ts": 1_012_500, "dur": 28_000},
        {"name": "db_query", "cat": "db", "ph": "X", "ts": 1_040_500, "dur": 94_000},
        {"name": "render_json", "cat": "app", "ph": "X", "ts": 1_134_500, "dur": 18_500},
    ]
}

K6_SUMMARY = {
    "metrics": {
        "http_reqs": {"type": "counter", "values": {"count": 12000, "rate": 200.0}},
        "http_req_duration": {
            "type": "trend",
            "values": {
                "min": 4.2,
                "med": 32.5,
                "avg": 41.8,
                "p(90)": 78.4,
                "p(95)": 112.6,
                "max": 340.1,
            },
        },
    }
}

ESBUILD_METAFILE = {
    "inputs": {"src/index.ts": {"bytes": 4200}},
    "outputs": {
        "dist/vendor.js": {"bytes": 245_760},
        "dist/app.js": {"bytes": 81_920},
        "dist/styles.css": {"bytes": 24_576},
        "dist/worker.js": {"bytes": 12_288},
    },
}

LLM_EVAL_ROWS = [
    {"model": "Alpha-Mini", "cost_usd": 0.40, "pass_rate": 72.5, "latency_ms": 420},
    {"model": "Alpha-Pro", "cost_usd": 1.80, "pass_rate": 86.2, "latency_ms": 980},
    {"model": "Beta-Fast", "cost_usd": 0.65, "pass_rate": 79.0, "latency_ms": 510},
    {"model": "Gamma-XL", "cost_usd": 4.50, "pass_rate": 87.1, "latency_ms": 1950},
]


# --------------------------------------------------------------------------- #
# 1. Native SWE Dev-Tool Ingestors + inspect_data / auto_panel integration
# --------------------------------------------------------------------------- #


class TestSweIngestors:
    def test_hyperfine_ingest_and_raw_times(self, tmp_path: Path) -> None:
        p = tmp_path / "hyperfine.json"
        p.write_text(json.dumps(HYPERFINE_BASE), encoding="utf-8")

        assert detect_tool_format(p) == "hyperfine"
        ds = load_tool_output(p)
        assert ds["format"] == "hyperfine"
        assert ds["error_label"] == "±1 s.d."
        assert len(ds["rows"]) == 3
        assert {"name", "mean_s", "stddev_s", "lo", "hi", "n"} <= set(ds["rows"][0])
        assert ds["rows"][0]["n"] == 5

        # load_table_file & inspect_data & auto_panel seamlessly work
        rows = mint.load_table_file(p)
        assert len(rows) == 3
        info = mint.inspect_data(p)
        assert info["tool_format"] == "hyperfine"
        assert info["recommendations"][0]["kind"] == "compare"
        assert info["recommendations"][0]["params"]["error_label"] == "±1 s.d."

        panel = mint.auto_panel(p)
        fig = mint.explain("ripgrep is 7x faster than grep -r", panel, source="hyperfine.json")
        try:
            assert fig.ship is True
        finally:
            plt.close(fig.fig)

        # Raw times mode -> distribution
        raw_ds = load_tool_output(p, raw_times=True)
        assert raw_ds["recommended_kind"] == "distribution"
        assert len(raw_ds["rows"]) == 15
        assert {"name", "time_s"} == set(raw_ds["rows"][0])

    def test_pytest_benchmark_ingest(self, tmp_path: Path) -> None:
        p = tmp_path / "pytest_bench.json"
        p.write_text(json.dumps(PYTEST_BENCH_BASE), encoding="utf-8")

        assert detect_tool_format(p) == "pytest_benchmark"
        ds = load_tool_output(p)
        assert ds["format"] == "pytest_benchmark"
        assert len(ds["rows"]) == 2
        assert ds["rows"][0]["name"] == "test_parse_json"
        assert ds["rows"][0]["mean_ms"] == pytest.approx(4.2)
        assert ds["rows"][0]["rounds"] == 120

        info = mint.inspect_data(p)
        assert info["tool_format"] == "pytest_benchmark"
        assert info["recommendations"][0]["kind"] == "compare"
        assert info["recommendations"][0]["params"]["error"] == ("lo", "hi")

        panel = mint.auto_panel(p)
        fig = mint.explain("Msgpack encoding is faster than JSON parsing", panel, source="pytest")
        try:
            assert fig.ship is True
        finally:
            plt.close(fig.fig)

    def test_go_bench_and_cargo_bench_ingest(self, tmp_path: Path) -> None:
        go_p = tmp_path / "go_bench.txt"
        go_p.write_text(GO_BENCH_BASE, encoding="utf-8")
        assert detect_tool_format(go_p) == "go_bench"
        go_rows = mint.load_table_file(go_p)
        assert len(go_rows) == 3
        assert go_rows[0]["name"] == "BenchmarkDecode-8"
        assert go_rows[0]["ns_per_op"] == pytest.approx(2400.0)
        assert mint.inspect_data(go_p)["recommendations"][0]["kind"] == "compare"

        cargo_p = tmp_path / "cargo_bench.log"
        cargo_p.write_text(CARGO_BENCH_LOG, encoding="utf-8")
        assert detect_tool_format(cargo_p) == "cargo_bench"
        cargo_rows = mint.load_table_file(cargo_p)
        assert len(cargo_rows) == 3
        assert cargo_rows[0]["name"] == "bench_lexer"
        assert cargo_rows[0]["ns_per_op"] == pytest.approx(1234.0)
        assert cargo_rows[0]["err"] == pytest.approx(45.0)
        info = mint.inspect_data(cargo_p)
        assert info["tool_format"] == "cargo_bench"
        assert info["recommendations"][0]["kind"] == "compare"

    def test_github_actions_and_chrome_trace_timelines(self, tmp_path: Path) -> None:
        gha_p = tmp_path / "gha_jobs.json"
        gha_p.write_text(json.dumps(GHA_TIMINGS), encoding="utf-8")
        assert detect_tool_format(gha_p) == "github_actions"
        gha_rows = mint.load_table_file(gha_p)
        assert len(gha_rows) == 3
        assert gha_rows[0] == {
            "name": "Checkout",
            "start_s": 0.0,
            "end_s": 8.0,
            "group": "build-and-test",
        }
        assert gha_rows[-1]["end_s"] == pytest.approx(130.0)
        assert mint.inspect_data(gha_p)["recommendations"][0]["kind"] == "timeline"
        gha_fig = mint.explain("Pytest dominates the 130 s workflow", mint.auto_panel(gha_p), source="CI")
        try:
            assert gha_fig.ship is True
        finally:
            plt.close(gha_fig.fig)

        ct_p = tmp_path / "trace.json"
        ct_p.write_text(json.dumps(CHROME_TRACE), encoding="utf-8")
        assert detect_tool_format(ct_p) == "chrome_trace"
        ct_rows = mint.load_table_file(ct_p)
        assert len(ct_rows) == 4
        assert ct_rows[0] == {"name": "dns_lookup", "start_ms": 0.0, "end_ms": 12.5, "group": "net"}
        assert ct_rows[2]["name"] == "db_query"
        assert ct_rows[2]["end_ms"] - ct_rows[2]["start_ms"] == pytest.approx(94.0)
        assert mint.inspect_data(ct_p)["recommendations"][0]["kind"] == "timeline"
        ct_fig = mint.explain("db_query takes 94 ms of the request trace", mint.auto_panel(ct_p), source="trace")
        try:
            assert ct_fig.ship is True
        finally:
            plt.close(ct_fig.fig)

    def test_k6_summary_ingest(self, tmp_path: Path) -> None:
        k6_p = tmp_path / "k6_summary.json"
        k6_p.write_text(json.dumps(K6_SUMMARY), encoding="utf-8")
        assert detect_tool_format(k6_p) == "k6"
        rows = mint.load_table_file(k6_p)
        assert [r["name"] for r in rows] == ["min", "med", "avg", "p(90)", "p(95)", "max"]
        info = mint.inspect_data(k6_p)
        assert info["tool_format"] == "k6"
        kinds = [r["kind"] for r in info["recommendations"]]
        assert kinds[0] == "compare" and "table" in kinds

    def test_esbuild_metafile_ingest(self, tmp_path: Path) -> None:
        mf_p = tmp_path / "meta.json"
        mf_p.write_text(json.dumps(ESBUILD_METAFILE), encoding="utf-8")
        assert detect_tool_format(mf_p) == "esbuild_metafile"
        rows = mint.load_table_file(mf_p)
        assert len(rows) == 4
        assert rows[0]["output"] == "dist/vendor.js"
        assert rows[0]["bytes"] == 245_760
        assert rows[0]["kb"] == pytest.approx(240.0)
        info = mint.inspect_data(mf_p)
        assert info["tool_format"] == "esbuild_metafile"
        kinds = [r["kind"] for r in info["recommendations"]]
        assert "share" in kinds and "compare" in kinds
        fig = mint.explain("dist/vendor.js makes up two thirds of the bundle", mint.auto_panel(mf_p), source="esbuild")
        try:
            assert fig.ship is True
        finally:
            plt.close(fig.fig)

    def test_llm_eval_jsonl_recognized(self, tmp_path: Path) -> None:
        ev_p = tmp_path / "evals.jsonl"
        ev_p.write_text("\n".join(json.dumps(r) for r in LLM_EVAL_ROWS) + "\n", encoding="utf-8")
        info = mint.inspect_data(ev_p)
        assert info["tool_format"] == "llm_eval"
        kinds = [r["kind"] for r in info["recommendations"]]
        assert kinds[0] == "relate"
        assert info["recommendations"][0]["params"]["frontier"] is True
        assert "table" in kinds

    def test_generic_json_remains_backwards_compatible(self, tmp_path: Path) -> None:
        generic = tmp_path / "generic.json"
        generic.write_text(json.dumps({"results": [{"model": "A", "score": 80}]}), encoding="utf-8")
        assert detect_tool_format(generic) is None
        assert mint.load_table_file(generic) == [{"model": "A", "score": 80}]


# --------------------------------------------------------------------------- #
# 2. diff_runs() & CLI `mintfig diff`
# --------------------------------------------------------------------------- #


class TestDiffRunsAndCli:
    def test_diff_hyperfine_noise_suppression_and_shippable_figure(self, tmp_path: Path) -> None:
        b = tmp_path / "base.json"
        h = tmp_path / "head.json"
        b.write_text(json.dumps(HYPERFINE_BASE), encoding="utf-8")
        h.write_text(json.dumps(HYPERFINE_HEAD), encoding="utf-8")

        res = diff_runs(b, h)
        assert isinstance(res, DiffResult)
        assert isinstance(res, dict)
        assert res.higher_is_better is False
        assert [r["name"] for r in res.regressions] == ["grep -r"]
        assert [r["name"] for r in res.improvements] == ["ag"]
        assert [r["name"] for r in res.within_noise] == ["ripgrep"]
        assert res.max_regression_pct == pytest.approx(35.29, abs=0.1)

        # Terminal text strictly <= 72 cols
        assert all(len(line) <= 72 for line in res.text.splitlines())
        assert "REGR" in res.text and "IMPR" in res.text and "noise" in res.text

        # Markdown has bold takeaway + GFM table + bullets
        assert res.markdown.startswith("**")
        assert "| Item" in res.markdown
        assert "within noise" in res.markdown

        # Figure ships cleanly
        try:
            assert res.explanation.ship is True
        finally:
            plt.close(res.explanation.fig)

    def test_diff_pytest_benchmark_and_go_bench(self, tmp_path: Path) -> None:
        pb = tmp_path / "base_pytest.json"
        ph = tmp_path / "head_pytest.json"
        pb.write_text(json.dumps(PYTEST_BENCH_BASE), encoding="utf-8")
        ph.write_text(json.dumps(PYTEST_BENCH_HEAD), encoding="utf-8")
        pres = diff_runs(pb, ph)
        try:
            assert [r["name"] for r in pres.regressions] == ["test_parse_json"]
            assert [r["name"] for r in pres.within_noise] == ["test_encode_msgpack"]
            assert pres.explanation.ship is True
        finally:
            plt.close(pres.explanation.fig)

        gb = tmp_path / "base_go.txt"
        gh = tmp_path / "head_go.txt"
        gb.write_text(GO_BENCH_BASE, encoding="utf-8")
        gh.write_text(GO_BENCH_HEAD, encoding="utf-8")
        gres = diff_runs(gb, gh)
        try:
            assert [r["name"] for r in gres.regressions] == ["BenchmarkEncode-8"]
            assert [r["name"] for r in gres.improvements] == ["BenchmarkDecode-8"]
            assert gres.explanation.ship is True
        finally:
            plt.close(gres.explanation.fig)

    def test_diff_cli_flags_and_fail_on_regression(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        b = tmp_path / "base.json"
        h = tmp_path / "head.json"
        b.write_text(json.dumps(HYPERFINE_BASE), encoding="utf-8")
        h.write_text(json.dumps(HYPERFINE_HEAD), encoding="utf-8")

        # --text (no PNG)
        rc = cli_main(["diff", str(b), str(h), "--text"])
        assert rc == 0
        txt = capsys.readouterr().out
        assert "grep -r" in txt and all(len(line) <= 72 for line in txt.splitlines())

        # --markdown (no PNG)
        rc = cli_main(["diff", str(b), str(h), "--markdown"])
        assert rc == 0
        md = capsys.readouterr().out
        assert md.startswith("**") and "| Item" in md

        # --json + --fail-on-regression 10 -> exits 1 (35.3% > 10%)
        rc = cli_main(["diff", str(b), str(h), "--json", "--fail-on-regression", "10"])
        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["max_regression_pct"] > 30.0
        assert len(payload["within_noise"]) == 1

        # --fail-on-regression 50 -> exits 0 (35.3% <= 50%)
        rc = cli_main(["diff", str(b), str(h), "--text", "--fail-on-regression", "50"])
        assert rc == 0
        capsys.readouterr()

        # --out diff.png + --out diff.html
        out_png = tmp_path / "diff.png"
        rc = cli_main(["diff", str(b), str(h), "--out", str(out_png)])
        assert rc == 0
        summary = json.loads(capsys.readouterr().out)
        assert summary["ship"] is True
        assert out_png.exists()

        out_html = tmp_path / "diff.html"
        rc = cli_main(["diff", str(b), str(h), "--out", str(out_html)])
        assert rc == 0
        capsys.readouterr()
        assert out_html.exists() and "<svg" in out_html.read_text(encoding="utf-8")

    def test_diff_noise_only_does_not_fail_ci_gate(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        base_noise = {
            "results": [
                {"command": "alpha", "mean": 1.00, "stddev": 0.10},
                {"command": "beta", "mean": 2.00, "stddev": 0.15},
            ]
        }
        head_noise = {
            "results": [
                {"command": "alpha", "mean": 1.08, "stddev": 0.10},  # overlaps [0.90, 1.10] vs [0.98, 1.18]
                {"command": "beta", "mean": 2.12, "stddev": 0.15},   # overlaps [1.85, 2.15] vs [1.97, 2.27]
            ]
        }
        b = tmp_path / "b.json"
        h = tmp_path / "h.json"
        b.write_text(json.dumps(base_noise), encoding="utf-8")
        h.write_text(json.dumps(head_noise), encoding="utf-8")

        rc = cli_main(["diff", str(b), str(h), "--json", "--fail-on-regression", "1"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["regressions"] == []
        assert len(payload["within_noise"]) == 2
        assert payload["max_regression_pct"] == 0.0

    def test_diff_csv_higher_is_better_override(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        b = tmp_path / "eval_v1.csv"
        h = tmp_path / "eval_v2.csv"
        b.write_text("task,pass_rate\nmath,80.0\ncode,70.0\n", encoding="utf-8")
        h.write_text("task,pass_rate\nmath,88.0\ncode,60.0\n", encoding="utf-8")

        rc = cli_main([
            "diff",
            str(b),
            str(h),
            "--higher-is-better",
            "--fail-on-regression",
            "5",
            "--json",
        ])
        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert [r["name"] for r in payload["regressions"]] == ["code"]
        assert [r["name"] for r in payload["improvements"]] == ["math"]


# --------------------------------------------------------------------------- #
# 3. Terminal-first (--text) & Markdown-first (--markdown) flags on `mintfig plot`
# --------------------------------------------------------------------------- #


class TestPlotTextAndMarkdownFlags:
    def test_plot_text_and_markdown_require_no_out(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = tmp_path / "hyperfine.json"
        p.write_text(json.dumps(HYPERFINE_BASE), encoding="utf-8")

        # --text without --out
        rc = cli_main([
            "plot",
            str(p),
            "--kind",
            "auto",
            "--takeaway",
            "ripgrep is 7x faster than grep -r",
            "--text",
        ])
        assert rc == 0
        txt = capsys.readouterr().out
        assert "ripgrep" in txt
        assert "grep -r" in txt

        # --markdown without --out
        rc = cli_main([
            "plot",
            str(p),
            "--kind",
            "auto",
            "--takeaway",
            "ripgrep is 7x faster than grep -r",
            "--markdown",
        ])
        assert rc == 0
        md = capsys.readouterr().out
        assert md.startswith("**ripgrep is 7x faster than grep -r**")
        assert "| name" in md and "| :---" in md
        assert "- " in md

    def test_diff_single_item_unmatched_and_cargo_bench(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Single-item diff with intervals
        b1 = tmp_path / "b1.json"
        h1 = tmp_path / "h1.json"
        b1.write_text(
            json.dumps({"results": [{"command": "build", "mean": 10.0, "stddev": 0.4}]}),
            encoding="utf-8",
        )
        h1.write_text(
            json.dumps({"results": [{"command": "build", "mean": 12.5, "stddev": 0.5}]}),
            encoding="utf-8",
        )
        res1 = diff_runs(b1, h1)
        try:
            assert res1.explanation.ship is True
            assert [r["name"] for r in res1.regressions] == ["build"]
            assert res1.max_regression_pct == pytest.approx(25.0)
        finally:
            plt.close(res1.explanation.fig)

        # Cargo bench diff (text logs with (+/- err))
        cb = tmp_path / "cargo_base.txt"
        ch = tmp_path / "cargo_head.txt"
        cb.write_text(CARGO_BENCH_LOG, encoding="utf-8")
        ch.write_text(
            "test bench_lexer   ... bench:       1,250 ns/iter (+/- 40)\n"
            "test bench_parser  ... bench:      15,000 ns/iter (+/- 200)\n"
            "test bench_new     ... bench:       3,000 ns/iter (+/- 50)\n",
            encoding="utf-8",
        )
        cres = diff_runs(cb, ch)
        try:
            assert cres.explanation.ship is True
            assert [r["name"] for r in cres.regressions] == ["bench_parser"]
            assert [r["name"] for r in cres.within_noise] == ["bench_lexer"]
            assert cres.unmatched_base == ["bench_codegen"]
            assert cres.unmatched_head == ["bench_new"]
            assert "Unmatched items skipped" in cres.markdown
        finally:
            plt.close(cres.explanation.fig)

        # Error exit code 2 when no shared items match
        disjoint = tmp_path / "disjoint.csv"
        disjoint.write_text("name,val\nfoo,1\n", encoding="utf-8")
        disjoint2 = tmp_path / "disjoint2.csv"
        disjoint2.write_text("name,val\nbar,2\n", encoding="utf-8")
        rc = cli_main(["diff", str(disjoint), str(disjoint2), "--json"])
        assert rc == 2
        err_payload = json.loads(capsys.readouterr().out)
        assert err_payload["ok"] is False

    def test_go_bench_multirun_and_k6_multi_metric_and_chrome_be(self, tmp_path: Path) -> None:
        # go test -bench -count=3 aggregates mean + stddev
        go_multi = tmp_path / "go_multi.out"
        go_multi.write_text(
            "BenchmarkHash-8   100000   100 ns/op\n"
            "BenchmarkHash-8   100000   110 ns/op\n"
            "BenchmarkHash-8   100000   120 ns/op\n",
            encoding="utf-8",
        )
        ds = load_tool_output(go_multi)
        assert ds["format"] == "go_bench"
        assert len(ds["rows"]) == 1
        assert ds["rows"][0]["ns_per_op"] == pytest.approx(110.0)
        assert ds["rows"][0]["err"] == pytest.approx(10.0)

        # k6 multi-metric trend export
        k6_multi = tmp_path / "k6_multi.json"
        k6_multi.write_text(
            json.dumps({
                "metrics": {
                    "http_req_duration": {"values": {"avg": 40.0, "med": 35.0, "p(95)": 110.0, "max": 250.0}},
                    "http_req_waiting": {"values": {"avg": 30.0, "med": 28.0, "p(95)": 88.0, "max": 200.0}},
                }
            }),
            encoding="utf-8",
        )
        k6_rows = mint.load_table_file(k6_multi)
        assert len(k6_rows) == 2
        assert k6_rows[0]["name"] == "http_req_duration"
        assert k6_rows[0]["p95_ms"] == pytest.approx(110.0)

        # Chrome trace B/E pairs
        be_trace = tmp_path / "trace_be.json"
        be_trace.write_text(
            json.dumps({
                "traceEvents": [
                    {"name": "compile", "cat": "build", "ph": "B", "ts": 500_000},
                    {"name": "compile", "cat": "build", "ph": "E", "ts": 545_000},
                    {"name": "link", "cat": "build", "ph": "B", "ts": 545_000},
                    {"name": "link", "cat": "build", "ph": "E", "ts": 560_000},
                ]
            }),
            encoding="utf-8",
        )
        be_rows = mint.load_table_file(be_trace)
        assert len(be_rows) == 2
        assert be_rows[0] == {"name": "compile", "start_ms": 0.0, "end_ms": 45.0, "group": "build"}
        assert be_rows[1] == {"name": "link", "start_ms": 45.0, "end_ms": 60.0, "group": "build"}
