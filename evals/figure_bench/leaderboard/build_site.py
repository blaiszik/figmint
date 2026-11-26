"""Build the zero-CDN interactive HTML leaderboard & task explorer for figure-bench v0.1.

Reads verified submissions from ``evals/figure_bench/leaderboard/submissions/*.json`` and
emits a single self-contained ``evals/figure_bench/site/index.html`` with no external CDN
requests.

Usage:
    python evals/figure_bench/leaderboard/build_site.py
    python evals/figure_bench/leaderboard/build_site.py --out /tmp/leaderboard.html
"""

from __future__ import annotations

import argparse
import base64
import datetime
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
BENCH_ROOT = HERE.parent
DEFAULT_SUBMISSIONS_DIR = HERE / "submissions"
DEFAULT_OUTPUT_PATH = BENCH_ROOT / "site" / "index.html"

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import verify_submission

# Canonical figure-bench v0.1 track architecture (6 tracks across 60 tasks: 15 dev, 30 public-test, 15 heldout).
TRACK_CATALOG: list[dict[str, Any]] = [
    {
        "id": "science_uncertainty",
        "name": "Science & Uncertainty",
        "total_tasks": 19,
        "splits": {"dev": 6, "public-test": 6, "heldout": 7},
        "summary": "Multi-seed ablations, dose-response, meta-analysis forests, survival curves, spectra, kinetics, and biological replicates.",
    },
    {
        "id": "swe_coding",
        "name": "SWE & Quantitative Coding",
        "total_tasks": 13,
        "splits": {"dev": 3, "public-test": 8, "heldout": 2},
        "summary": "Hyperfine & pytest-benchmark diffs, CI critical paths, k6 p99 deploy regressions, bundle waterfalls, LLM Pareto frontiers, and soak leaks.",
    },
    {
        "id": "epistemic_traps",
        "name": "Epistemic Traps & Refusals",
        "total_tasks": 12,
        "splits": {"dev": 4, "public-test": 6, "heldout": 2},
        "summary": "Overlapping CIs, no-effect traps, Simpson's paradox, small-n replicates, truncated-bar bait, missing controls, and corrupted sensor outliers.",
    },
    {
        "id": "multiturn_edit",
        "name": "Multi-Turn Figure Editing",
        "total_tasks": 6,
        "splits": {"dev": 2, "public-test": 3, "heldout": 1},
        "summary": "Targeted edits to a prior figure: switching baselines, log-scale transforms, adding replicates, fixing misconverted units, and highlighting subsets.",
    },
    {
        "id": "multi_surface",
        "name": "Multi-Surface Delivery",
        "total_tasks": 5,
        "splits": {"dev": 0, "public-test": 4, "heldout": 1},
        "summary": "Legible delivery across narrow 450 px phone/IDE sidebars, 1280 px slides, dark dashboards, and 72-column SSH terminal sessions.",
    },
    {
        "id": "byo_repair",
        "name": "BYO-Matplotlib Repair",
        "total_tasks": 5,
        "splits": {"dev": 0, "public-test": 3, "heldout": 2},
        "summary": "Diagnosing and fixing broken existing Matplotlib scripts with wrong headline numbers, jet colormaps, truncated axes, and struck labels.",
    },
]


def _maybe_encode_png(png_path: Path, max_bytes: int = 450_000) -> str | None:
    if not png_path.is_file() or png_path.stat().st_size > max_bytes:
        return None
    raw = png_path.read_bytes()
    if not raw.startswith(verify_submission.PNG_SIGNATURE):
        return None
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{b64}"


def load_submissions(
    submissions_dir: Path = DEFAULT_SUBMISSIONS_DIR,
    *,
    strict: bool = True,
    embed_images: bool = True,
) -> list[dict[str, Any]]:
    """Load and validate all submission JSON files in ``submissions_dir``."""
    schema = verify_submission.load_schema()
    files = sorted(p for p in submissions_dir.glob("*.json") if p.is_file())
    loaded: list[dict[str, Any]] = []

    for path in files:
        errs = verify_submission.verify_submission_file(path, schema=schema)
        if errs and strict:
            joined = "\n  - ".join(errs)
            raise ValueError(f"Invalid submission {path}:\n  - {joined}")
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_source_file"] = path.name

        # Optionally attach bundled PNG data URIs when artifacts_dir exists.
        artifacts_dir = data.get("artifacts_dir")
        if embed_images and isinstance(artifacts_dir, str) and artifacts_dir.strip():
            root = verify_submission._resolve_artifacts_dir(artifacts_dir, path.parent)
            if root is not None:
                for row in data.get("per_task", []):
                    png = verify_submission._find_task_png(root, row)
                    if png is not None:
                        uri = _maybe_encode_png(png)
                        if uri is not None:
                            row["_figure_data_uri"] = uri

        loaded.append(data)

    loaded.sort(
        key=lambda item: (
            -(item.get("scores", {}).get("composite") or 0.0),
            -(item.get("scores", {}).get("visual_quality") or 0.0),
            item.get("submission_id", ""),
        )
    )
    return loaded


def _safe_json_for_html(payload: Any) -> str:
    """Serialize JSON safely for embedding inside an HTML ``<script>`` tag."""
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def render_html(
    submissions: list[dict[str, Any]],
    *,
    generated_at: str | None = None,
) -> str:
    """Render the complete zero-CDN HTML document for the leaderboard & explorer."""
    stamp = generated_at or datetime.date.today().isoformat()
    payload = {
        "bench_version": "0.1",
        "generated_at": stamp,
        "tracks": TRACK_CATALOG,
        "submissions": submissions,
    }
    embedded_json = _safe_json_for_html(payload)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>figure-bench v0.1 — Open Leaderboard &amp; Visual Explorer</title>
<style>
  :root {{
    --bg: #fafbf9;
    --surface: #ffffff;
    --surface-alt: #f3f5f2;
    --ink: #1a1d21;
    --ink-muted: #57606a;
    --border: #d8dee4;
    --accent: #0e7c66;
    --accent-soft: #e6f4f0;
    --accent-ink: #0a5848;
    --warn-bg: #fff6e5;
    --warn-ink: #8a5300;
    --warn-border: #f0d39a;
    --bad-bg: #fdecec;
    --bad-ink: #a61b1b;
    --good-bg: #e7f6ee;
    --good-ink: #146c43;
    --shadow: 0 1px 2px rgba(26, 29, 33, 0.05), 0 4px 16px rgba(26, 29, 33, 0.04);
    --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }}
  [data-theme="dark"] {{
    --bg: #0e1318;
    --surface: #151c23;
    --surface-alt: #1b242e;
    --ink: #e6edf3;
    --ink-muted: #93a1b1;
    --border: #2a3542;
    --accent: #2dd4bf;
    --accent-soft: rgba(45, 212, 191, 0.14);
    --accent-ink: #5eead4;
    --warn-bg: rgba(245, 158, 11, 0.15);
    --warn-ink: #fbbf24;
    --warn-border: rgba(245, 158, 11, 0.35);
    --bad-bg: rgba(239, 68, 68, 0.15);
    --bad-ink: #f87171;
    --good-bg: rgba(34, 197, 94, 0.15);
    --good-ink: #4ade80;
    --shadow: 0 1px 3px rgba(0, 0, 0, 0.35);
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: var(--sans);
    background: var(--bg);
    color: var(--ink);
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .wrap {{ max-width: 1220px; margin: 0 auto; padding: 28px 20px 64px; }}
  header {{
    display: flex;
    flex-wrap: wrap;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 22px;
  }}
  .title-row {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
  h1 {{ margin: 0; font-size: 1.75rem; letter-spacing: -0.02em; font-weight: 700; }}
  .badge {{
    display: inline-flex;
    align-items: center;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.01em;
  }}
  .badge-wip {{
    background: var(--warn-bg);
    color: var(--warn-ink);
    border: 1px solid var(--warn-border);
  }}
  .badge-accent {{ background: var(--accent-soft); color: var(--accent-ink); }}
  .badge-good {{ background: var(--good-bg); color: var(--good-ink); }}
  .badge-bad {{ background: var(--bad-bg); color: var(--bad-ink); }}
  .badge-neutral {{ background: var(--surface-alt); color: var(--ink-muted); border: 1px solid var(--border); }}
  .subtitle {{ margin: 6px 0 0; color: var(--ink-muted); max-width: 720px; font-size: 0.96rem; }}
  .header-actions {{ display: flex; gap: 8px; align-items: center; }}
  button, select, input[type="search"] {{
    font-family: inherit;
    font-size: 0.88rem;
    color: var(--ink);
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 7px 11px;
  }}
  button {{ cursor: pointer; font-weight: 500; }}
  button:hover {{ border-color: var(--accent); }}
  .banner {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-left: 4px solid var(--accent);
    border-radius: 10px;
    padding: 16px 18px;
    margin-bottom: 24px;
    box-shadow: var(--shadow);
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 14px;
    align-items: center;
  }}
  @media (max-width: 760px) {{ .banner {{ grid-template-columns: 1fr; }} }}
  .banner h2 {{ margin: 0 0 4px; font-size: 1rem; }}
  .banner p {{ margin: 0 0 10px; color: var(--ink-muted); font-size: 0.9rem; }}
  .code-line {{
    font-family: var(--mono);
    font-size: 0.82rem;
    background: var(--surface-alt);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px 10px;
    overflow-x: auto;
    white-space: nowrap;
  }}
  .banner-cta {{ display: flex; flex-direction: column; gap: 8px; }}
  .btn-primary {{
    background: var(--accent);
    color: #ffffff;
    border-color: var(--accent);
    text-align: center;
    padding: 9px 14px;
    border-radius: 8px;
    font-weight: 600;
    font-size: 0.88rem;
    display: inline-block;
  }}
  [data-theme="dark"] .btn-primary {{ color: #0b1414; }}
  .btn-primary:hover {{ text-decoration: none; opacity: 0.92; }}
  .section-head {{
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: baseline;
    gap: 12px;
    margin: 28px 0 12px;
  }}
  .section-head h2 {{ margin: 0; font-size: 1.25rem; letter-spacing: -0.01em; }}
  .section-head .hint {{ color: var(--ink-muted); font-size: 0.86rem; }}
  .filters {{
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-bottom: 14px;
    align-items: center;
  }}
  .filters label {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 0.84rem;
    color: var(--ink-muted);
  }}
  .table-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    box-shadow: var(--shadow);
    overflow: hidden;
  }}
  .table-scroll {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.89rem; }}
  th, td {{ padding: 11px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
  th {{
    background: var(--surface-alt);
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--ink-muted);
    white-space: nowrap;
    user-select: none;
  }}
  th.sortable {{ cursor: pointer; }}
  th.sortable:hover {{ color: var(--ink); }}
  th.num, td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  tr.data-row:hover {{ background: var(--surface-alt); }}
  .sub-name {{ font-weight: 600; color: var(--ink); }}
  .sub-meta {{ font-size: 0.8rem; color: var(--ink-muted); margin-top: 2px; }}
  .pill-row {{ display: flex; flex-wrap: wrap; gap: 5px; margin-top: 5px; }}
  .score-cell {{ display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }}
  .bar-track {{
    width: 66px;
    height: 5px;
    background: var(--surface-alt);
    border-radius: 99px;
    overflow: hidden;
    border: 1px solid var(--border);
  }}
  .bar-fill {{ height: 100%; background: var(--accent); border-radius: 99px; }}
  .prov-row td {{
    background: var(--surface-alt);
    font-size: 0.83rem;
    color: var(--ink-muted);
    padding: 12px 16px;
  }}
  .prov-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 10px 18px;
  }}
  .prov-grid strong {{ color: var(--ink); }}
  .compare-panel {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 18px;
    box-shadow: var(--shadow);
  }}
  .compare-controls {{
    display: flex;
    flex-wrap: wrap;
    gap: 10px 14px;
    align-items: center;
    margin-bottom: 16px;
  }}
  .compare-controls label {{ display: flex; align-items: center; gap: 6px; font-size: 0.84rem; color: var(--ink-muted); }}
  .compare-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }}
  @media (max-width: 820px) {{ .compare-grid {{ grid-template-columns: 1fr; }} }}
  .task-card {{
    background: var(--surface-alt);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px 16px;
  }}
  .task-card h3 {{ margin: 0 0 6px; font-size: 0.98rem; display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; }}
  .metric-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    margin: 10px 0 12px;
  }}
  .metric-box {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 10px;
  }}
  .metric-box .k {{ font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--ink-muted); }}
  .metric-box .v {{ font-size: 1.05rem; font-weight: 700; font-variant-numeric: tabular-nums; margin-top: 2px; }}
  .delta {{ font-size: 0.75rem; font-weight: 600; margin-left: 4px; }}
  .delta.pos {{ color: var(--good-ink); }}
  .delta.neg {{ color: var(--bad-ink); }}
  .takeaway-box {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 0.87rem;
    margin-bottom: 10px;
  }}
  .fig-frame {{
    background: var(--surface);
    border: 1px dashed var(--border);
    border-radius: 8px;
    padding: 12px;
    text-align: center;
    overflow-x: auto;
  }}
  .fig-frame img {{ display: block; margin: 0 auto; height: auto; border-radius: 4px; }}
  .fig-placeholder {{ color: var(--ink-muted); font-size: 0.83rem; padding: 18px 8px; }}
  .tracks-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(290px, 1fr));
    gap: 14px;
  }}
  .track-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 15px 16px;
    box-shadow: var(--shadow);
  }}
  .track-card h3 {{ margin: 0 0 6px; font-size: 0.98rem; display: flex; justify-content: space-between; align-items: center; gap: 8px; }}
  .track-card p {{ margin: 0 0 10px; font-size: 0.85rem; color: var(--ink-muted); }}
  .track-splits {{ font-family: var(--mono); font-size: 0.77rem; color: var(--ink-muted); }}
  .track-scores {{ margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--border); font-size: 0.8rem; display: flex; flex-direction: column; gap: 4px; }}
  .track-score-line {{ display: flex; justify-content: space-between; gap: 8px; }}
  footer {{
    margin-top: 38px;
    padding-top: 16px;
    border-top: 1px solid var(--border);
    color: var(--ink-muted);
    font-size: 0.82rem;
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: 8px;
  }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <div class="title-row">
        <h1>figure-bench</h1>
        <span class="badge badge-wip">figure-bench v0.1 (work in progress)</span>
        <span class="badge badge-accent">60 tasks · 6 tracks · library-agnostic</span>
      </div>
      <p class="subtitle">
        Open benchmark measuring whether AI agents and plotting libraries produce <strong>legible, truthful, uncertainty-aware figures</strong> at real display widths (700 px chat, 450 px phone/IDE, 1280 px slides, dark mode, terminal).
      </p>
    </div>
    <div class="header-actions">
      <button id="theme-toggle" type="button" aria-label="Toggle light/dark theme">Toggle theme</button>
    </div>
  </header>

  <section class="banner" aria-label="Compete on figure-bench">
    <div>
      <h2>Bring any model, library, skill, or verifier hook</h2>
      <p>
        Compete with <code>matplotlib</code>, <code>seaborn</code>, <code>altair</code>, <code>plotly</code>, <code>plotnine</code>, <code>ggplot2</code>, <code>d3</code>, or <code>mintfig</code>. Grade an output folder locally with zero mintfig dependency and submit a verified JSON via PR.
      </p>
      <div class="code-line">python evals/figure_bench/bench.py grade-dir my_outputs/ --split public-test --out submission.json</div>
    </div>
    <div class="banner-cta">
      <a class="btn-primary" href="https://github.com/blaiszik/mintfig/pulls" target="_blank" rel="noopener noreferrer">Submit via GitHub PR</a>
      <a href="../CONTRIBUTING.md" style="text-align:center;font-size:0.84rem;">Read CONTRIBUTING.md →</a>
    </div>
  </section>

  <div class="section-head">
    <h2>Open Leaderboard</h2>
    <span class="hint" id="leaderboard-note">Initial seed rows reflect real measured 15-task runs (v0.1-initial-15). Click any column header to sort; click a row for provenance.</span>
  </div>

  <div class="filters">
    <label>Split:
      <select id="filter-split"><option value="all">All splits</option></select>
    </label>
    <label>Library:
      <select id="filter-library"><option value="all">All libraries</option></select>
    </label>
    <label>Hook:
      <select id="filter-hook">
        <option value="all">Any</option>
        <option value="on">Hook ON</option>
        <option value="off">Hook OFF</option>
      </select>
    </label>
    <label>Search:
      <input id="filter-search" type="search" placeholder="model, team, skill...">
    </label>
  </div>

  <div class="table-card">
    <div class="table-scroll">
      <table id="leaderboard-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Submission</th>
            <th>Split</th>
            <th class="num sortable" data-sort="composite">Composite</th>
            <th class="num sortable" data-sort="visual_quality">Visual Quality</th>
            <th class="num sortable" data-sort="claim_accuracy">Claim Accuracy</th>
            <th class="num sortable" data-sort="uncertainty_calibration">Uncertainty</th>
            <th class="num sortable" data-sort="reader_score">Reader Score</th>
            <th class="num sortable" data-sort="delivery_rate">Delivery</th>
            <th class="num sortable" data-sort="median_seconds">Median (s)</th>
          </tr>
        </thead>
        <tbody id="leaderboard-body"></tbody>
      </table>
    </div>
  </div>

  <div class="section-head">
    <h2>Side-by-Side Task Comparison Explorer</h2>
    <span class="hint">Inspect per-task scores, failed checks, takeaways, and bundled PNGs across any two submissions.</span>
  </div>

  <section class="compare-panel" aria-label="Side-by-Side Task Comparison">
    <div class="compare-controls">
      <label>Left (A): <select id="cmp-left"></select></label>
      <label>Right (B): <select id="cmp-right"></select></label>
      <label>Track: <select id="cmp-track"><option value="all">All tracks</option></select></label>
      <label>Task: <select id="cmp-task"></select></label>
      <label><input id="cmp-diffs-only" type="checkbox"> Differences only</label>
    </div>
    <div class="compare-grid" id="compare-grid"></div>
  </section>

  <div class="section-head">
    <h2>Track Breakdown Overview (6 Tracks · 60 Tasks)</h2>
    <span class="hint">15 dev (<code>tasks/</code>) · 30 frozen public-test (<code>public_test/</code>) · 15 held-out (<code>heldout/</code>)</span>
  </div>

  <section class="tracks-grid" id="tracks-grid"></section>

  <footer>
    <span>figure-bench v0.1 (work in progress) · Zero-CDN static build generated <strong id="gen-date"></strong></span>
    <span>Human blind reader study: <a href="../human_study/index.html">human_study/index.html</a> · Schema: <a href="../leaderboard/schema.json">schema.json</a></span>
  </footer>
</div>

<script id="bench-data" type="application/json">{embedded_json}</script>
<script>
(function() {{
  const DATA = JSON.parse(document.getElementById("bench-data").textContent);
  const submissions = DATA.submissions || [];
  const tracks = DATA.tracks || [];
  document.getElementById("gen-date").textContent = DATA.generated_at || "";

  // Theme handling (respects OS preference, persisted in localStorage)
  const rootEl = document.documentElement;
  const savedTheme = (() => {{ try {{ return localStorage.getItem("fb-theme"); }} catch (_) {{ return null; }} }})();
  const initialDark = savedTheme ? savedTheme === "dark" : (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  rootEl.setAttribute("data-theme", initialDark ? "dark" : "light");
  document.getElementById("theme-toggle").addEventListener("click", () => {{
    const next = rootEl.getAttribute("data-theme") === "dark" ? "light" : "dark";
    rootEl.setAttribute("data-theme", next);
    try {{ localStorage.setItem("fb-theme", next); }} catch (_) {{}}
  }});

  // Helpers
  const esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const fmtScore = (v) => (typeof v === "number" && Number.isFinite(v)) ? v.toFixed(1) : "—";
  const fmtSec = (v) => (typeof v === "number" && Number.isFinite(v)) ? v.toFixed(1) + "s" : "—";

  // Populate filter selects
  const splitSel = document.getElementById("filter-split");
  const libSel = document.getElementById("filter-library");
  const hookSel = document.getElementById("filter-hook");
  const searchInp = document.getElementById("filter-search");

  const splits = Array.from(new Set(submissions.map((s) => s.split))).sort();
  splits.forEach((sp) => {{
    const opt = document.createElement("option");
    opt.value = sp; opt.textContent = sp; splitSel.appendChild(opt);
  }});
  const libs = Array.from(new Set(submissions.map((s) => s.library))).sort();
  libs.forEach((lb) => {{
    const opt = document.createElement("option");
    opt.value = lb; opt.textContent = lb; libSel.appendChild(opt);
  }});

  let sortKey = "composite";
  let sortDir = "desc";
  const expandedIds = new Set();

  function getFiltered() {{
    const sp = splitSel.value;
    const lb = libSel.value;
    const hk = hookSel.value;
    const q = searchInp.value.trim().toLowerCase();
    return submissions.filter((s) => {{
      if (sp !== "all" && s.split !== sp) return false;
      if (lb !== "all" && s.library !== lb) return false;
      if (hk === "on" && !s.hook_enabled) return false;
      if (hk === "off" && s.hook_enabled) return false;
      if (q) {{
        const hay = [s.submission_id, s.team, s.model, s.library, s.skill_or_prompt, s.split].join(" ").toLowerCase();
        if (!hay.includes(q)) return false;
      }}
      return true;
    }}).sort((a, b) => {{
      const av = a.scores[sortKey];
      const bv = b.scores[sortKey];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return sortDir === "asc" ? av - bv : bv - av;
    }});
  }}

  function scoreCellHtml(val, emphasize) {{
    if (val == null) return '<td class="num">—</td>';
    const pct = Math.max(0, Math.min(100, val));
    const fw = emphasize ? "font-weight:700;" : "";
    return `<td class="num"><div class="score-cell"><span style="${{fw}}">${{fmtScore(val)}}</span><div class="bar-track"><div class="bar-fill" style="width:${{pct}}%"></div></div></div></td>`;
  }}

  function renderTable() {{
    const rows = getFiltered();
    const tbody = document.getElementById("leaderboard-body");
    document.querySelectorAll("th.sortable").forEach((th) => {{
      const key = th.dataset.sort;
      const base = th.textContent.replace(/ [▲▼]$/, "");
      th.textContent = key === sortKey ? `${{base}} ${{sortDir === "asc" ? "▲" : "▼"}}` : base;
    }});

    if (!rows.length) {{
      tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;color:var(--ink-muted);padding:24px;">No submissions match the current filters.</td></tr>';
      return;
    }}

    tbody.innerHTML = rows.map((s, idx) => {{
      const sc = s.scores || {{}};
      const isOpen = expandedIds.has(s.submission_id);
      const wipBadge = s.work_in_progress ? '<span class="badge badge-wip">WIP</span>' : "";
      const hookBadge = s.hook_enabled
        ? '<span class="badge badge-good">Hook ON</span>'
        : '<span class="badge badge-neutral">Hook OFF</span>';
      const prov = s.provenance || {{}};
      const mainRow = `
        <tr class="data-row" data-sub-id="${{esc(s.submission_id)}}" style="cursor:pointer;">
          <td style="font-weight:600;color:var(--ink-muted);">${{idx + 1}}</td>
          <td>
            <div class="sub-name">${{esc(s.model)}} · <code>${{esc(s.library)}}</code></div>
            <div class="sub-meta">${{esc(s.team)}} — ${{esc(s.skill_or_prompt)}}</div>
            <div class="pill-row">
              <span class="badge badge-accent">${{esc(s.library)}}</span>
              ${{hookBadge}}
              ${{wipBadge}}
              <span class="badge badge-neutral">${{esc(s.date)}}</span>
            </div>
          </td>
          <td>
            <div><strong>${{esc(s.split)}}</strong></div>
            <div class="sub-meta">${{s.task_count}} tasks</div>
          </td>
          ${{scoreCellHtml(sc.composite, true)}}
          ${{scoreCellHtml(sc.visual_quality, false)}}
          ${{scoreCellHtml(sc.claim_accuracy, false)}}
          ${{scoreCellHtml(sc.uncertainty_calibration, false)}}
          ${{scoreCellHtml(sc.reader_score, false)}}
          ${{scoreCellHtml(sc.delivery_rate, false)}}
          <td class="num">${{fmtSec(sc.median_seconds)}}</td>
        </tr>`;
      const provRow = isOpen ? `
        <tr class="prov-row">
          <td colspan="10">
            <div class="prov-grid">
              <div><strong>Submission ID:</strong> <code>${{esc(s.submission_id)}}</code></div>
              <div><strong>Commit / Version:</strong> <code>${{esc(prov.commit)}}</code> (bench v${{esc(prov.bench_version)}})</div>
              <div><strong>First-Submit Defect-Free:</strong> ${{prov.first_submission_clean_rate != null ? prov.first_submission_clean_rate.toFixed(1) + "%" : "—"}}</div>
              <div><strong>Source Report:</strong> <code>${{esc(prov.source_report || "—")}}</code></div>
            </div>
            <div style="margin-top:8px;"><strong>Reproduce:</strong> <code>${{esc(prov.reproduce_command)}}</code></div>
            ${{prov.notes ? `<div style="margin-top:6px;"><strong>Notes:</strong> ${{esc(prov.notes)}}</div>` : ""}}
          </td>
        </tr>` : "";
      return mainRow + provRow;
    }}).join("");

    tbody.querySelectorAll("tr.data-row").forEach((tr) => {{
      tr.addEventListener("click", () => {{
        const id = tr.dataset.subId;
        if (expandedIds.has(id)) expandedIds.delete(id); else expandedIds.add(id);
        renderTable();
      }});
    }});
    renderTracks(rows);
  }}

  document.querySelectorAll("th.sortable").forEach((th) => {{
    th.addEventListener("click", () => {{
      const key = th.dataset.sort;
      if (sortKey === key) {{
        sortDir = sortDir === "desc" ? "asc" : "desc";
      }} else {{
        sortKey = key;
        sortDir = key === "median_seconds" ? "asc" : "desc";
      }}
      renderTable();
    }});
  }});

  [splitSel, libSel, hookSel, searchInp].forEach((el) => el.addEventListener("input", renderTable));

  // Side-by-Side Task Comparison Viewer
  const cmpLeft = document.getElementById("cmp-left");
  const cmpRight = document.getElementById("cmp-right");
  const cmpTrack = document.getElementById("cmp-track");
  const cmpTask = document.getElementById("cmp-task");
  const cmpDiffsOnly = document.getElementById("cmp-diffs-only");

  tracks.forEach((tr) => {{
    const opt = document.createElement("option");
    opt.value = tr.id; opt.textContent = tr.name; cmpTrack.appendChild(opt);
  }});
  submissions.forEach((s, i) => {{
    const label = `${{s.submission_id}} (${{s.library}}, ${{fmtScore(s.scores.composite)}})`;
    const o1 = document.createElement("option"); o1.value = s.submission_id; o1.textContent = label; cmpLeft.appendChild(o1);
    const o2 = document.createElement("option"); o2.value = s.submission_id; o2.textContent = label; cmpRight.appendChild(o2);
    if (i === 0) cmpLeft.value = s.submission_id;
    if (i === Math.min(2, submissions.length - 1)) cmpRight.value = s.submission_id;
  }});

  function subById(id) {{ return submissions.find((s) => s.submission_id === id) || submissions[0]; }}

  function populateTaskDropdown() {{
    const leftSub = subById(cmpLeft.value);
    const rightSub = subById(cmpRight.value);
    if (!leftSub || !rightSub) return;
    const rightMap = new Map((rightSub.per_task || []).map((t) => [t.task_id, t]));
    const leftMap = new Map((leftSub.per_task || []).map((t) => [t.task_id, t]));
    const allIds = Array.from(new Set([...leftMap.keys(), ...rightMap.keys()]));
    const trackFilter = cmpTrack.value;
    const diffsOnly = cmpDiffsOnly.checked;

    const prev = cmpTask.value;
    cmpTask.innerHTML = "";
    allIds.forEach((tid) => {{
      const l = leftMap.get(tid);
      const r = rightMap.get(tid);
      const tr = (l && l.track) || (r && r.track);
      if (trackFilter !== "all" && tr !== trackFilter) return;
      if (diffsOnly && l && r && l.composite === r.composite && l.visual_quality === r.visual_quality && l.claim_accuracy === r.claim_accuracy) return;
      const opt = document.createElement("option");
      opt.value = tid;
      const deltaStr = (l && r) ? ` (Δ ${{(l.composite - r.composite) >= 0 ? "+" : ""}}${{(l.composite - r.composite).toFixed(1)}})` : "";
      opt.textContent = `${{tid}} [${{tr}}]${{deltaStr}}`;
      cmpTask.appendChild(opt);
    }});
    if (Array.from(cmpTask.options).some((o) => o.value === prev)) cmpTask.value = prev;
    renderComparison();
  }}

  function deltaSpan(val, otherVal) {{
    if (val == null || otherVal == null) return "";
    const d = val - otherVal;
    if (Math.abs(d) < 0.05) return "";
    const cls = d > 0 ? "pos" : "neg";
    return `<span class="delta ${{cls}}">${{d > 0 ? "+" : ""}}${{d.toFixed(1)}}</span>`;
  }}

  function renderSideCard(sub, task, otherTask, sideLabel) {{
    if (!sub || !task) {{
      return `<div class="task-card"><h3>${{esc(sideLabel)}}</h3><p class="sub-meta">Task not present in this submission.</p></div>`;
    }}
    const badge = task.passed
      ? '<span class="badge badge-good">Gate PASS</span>'
      : '<span class="badge badge-bad">Gate FAIL</span>';
    const failedList = (task.failed_checks && task.failed_checks.length)
      ? `<div class="sub-meta" style="margin-bottom:8px;"><strong>Failed checks:</strong> <code>${{esc(task.failed_checks.join(", "))}}</code></div>`
      : "";
    const widthPx = task.display_width_px || 700;
    const figHtml = task._figure_data_uri
      ? `<img src="${{task._figure_data_uri}}" alt="${{esc(task.task_id)}} rendered figure" style="width:${{Math.min(widthPx, 520)}}px;max-width:100%;">`
      : `<div class="fig-placeholder">No PNG bundled in this metadata-only submission.<br>Set <code>artifacts_dir</code> and re-run <code>build_site.py</code> to embed side-by-side PNGs (target width: ${{widthPx}} px).</div>`;
    return `
      <div class="task-card">
        <h3>
          <span>${{esc(sideLabel)}}: ${{esc(sub.library)}} · ${{esc(sub.model)}}</span>
          ${{badge}}
        </h3>
        <div class="sub-meta">${{esc(sub.skill_or_prompt)}} · Split: <strong>${{esc(task.split)}}</strong> · Track: <code>${{esc(task.track)}}</code> · Attempts: ${{task.attempts || 1}}</div>
        <div class="metric-grid">
          <div class="metric-box"><div class="k">Composite</div><div class="v">${{fmtScore(task.composite)}}${{deltaSpan(task.composite, otherTask && otherTask.composite)}}</div></div>
          <div class="metric-box"><div class="k">Visual</div><div class="v">${{fmtScore(task.visual_quality)}}${{deltaSpan(task.visual_quality, otherTask && otherTask.visual_quality)}}</div></div>
          <div class="metric-box"><div class="k">Claim</div><div class="v">${{fmtScore(task.claim_accuracy)}}${{deltaSpan(task.claim_accuracy, otherTask && otherTask.claim_accuracy)}}</div></div>
          <div class="metric-box"><div class="k">Uncertainty</div><div class="v">${{fmtScore(task.uncertainty_calibration)}}</div></div>
          <div class="metric-box"><div class="k">Reader</div><div class="v">${{fmtScore(task.reader_score)}}</div></div>
          <div class="metric-box"><div class="k">Time</div><div class="v">${{fmtSec(task.seconds)}}</div></div>
        </div>
        ${{failedList}}
        <div class="takeaway-box">
          <div style="font-size:0.74rem;text-transform:uppercase;letter-spacing:0.04em;color:var(--ink-muted);margin-bottom:3px;">Takeaway / Headline</div>
          <div>${{task.takeaway ? esc(task.takeaway) : '<em style="color:var(--ink-muted);">(no headline stated)</em>'}}</div>
        </div>
        <div class="fig-frame">${{figHtml}}</div>
      </div>`;
  }}

  function renderComparison() {{
    const grid = document.getElementById("compare-grid");
    const leftSub = subById(cmpLeft.value);
    const rightSub = subById(cmpRight.value);
    const tid = cmpTask.value;
    if (!tid) {{
      grid.innerHTML = '<div style="color:var(--ink-muted);padding:12px;">No tasks match the current comparison filters.</div>';
      return;
    }}
    const lt = (leftSub.per_task || []).find((t) => t.task_id === tid);
    const rt = (rightSub.per_task || []).find((t) => t.task_id === tid);
    grid.innerHTML = renderSideCard(leftSub, lt, rt, "Left (A)") + renderSideCard(rightSub, rt, lt, "Right (B)");
  }}

  [cmpLeft, cmpRight, cmpTrack, cmpDiffsOnly].forEach((el) => el.addEventListener("change", populateTaskDropdown));
  cmpTask.addEventListener("change", renderComparison);

  // Track breakdown overview
  function renderTracks(activeSubs) {{
    const container = document.getElementById("tracks-grid");
    container.innerHTML = tracks.map((tr) => {{
      const splitSummary = `dev: ${{tr.splits.dev}} · public-test: ${{tr.splits["public-test"]}} · heldout: ${{tr.splits.heldout}}`;
      const lines = activeSubs.map((s) => {{
        const rows = (s.per_task || []).filter((r) => r.track === tr.id);
        if (!rows.length) {{
          return `<div class="track-score-line"><span>${{esc(s.submission_id)}}</span><span style="color:var(--ink-muted);">not in split</span></div>`;
        }}
        const avg = rows.reduce((acc, r) => acc + r.composite, 0) / rows.length;
        return `<div class="track-score-line"><span>${{esc(s.library)}} (${{rows.length}}t)</span><strong>${{avg.toFixed(1)}}</strong></div>`;
      }}).join("");
      return `
        <article class="track-card">
          <h3><span>${{esc(tr.name)}}</span><span class="badge badge-neutral">${{tr.total_tasks}} tasks</span></h3>
          <p>${{esc(tr.summary)}}</p>
          <div class="track-splits">${{splitSummary}}</div>
          <div class="track-scores">${{lines}}</div>
        </article>`;
    }}).join("");
  }}

  renderTable();
  populateTaskDropdown();
}})();
</script>
</body>
</html>
"""


def build_site(
    submissions_dir: Path = DEFAULT_SUBMISSIONS_DIR,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    *,
    strict: bool = True,
    embed_images: bool = True,
) -> Path:
    """Build the leaderboard site HTML and write it to ``output_path``."""
    submissions = load_submissions(submissions_dir, strict=strict, embed_images=embed_images)
    html = render_html(submissions)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the zero-CDN figure-bench v0.1 leaderboard HTML page."
    )
    parser.add_argument(
        "--submissions",
        type=Path,
        default=DEFAULT_SUBMISSIONS_DIR,
        help="Directory containing verified submission JSON files.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Output HTML file path.",
    )
    parser.add_argument(
        "--no-embed-images",
        action="store_true",
        help="Do not inline bundled artifact PNGs as data URIs.",
    )
    args = parser.parse_args(argv)
    out = build_site(
        submissions_dir=args.submissions,
        output_path=args.out,
        strict=True,
        embed_images=not args.no_embed_images,
    )
    print(f"Built leaderboard site -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
