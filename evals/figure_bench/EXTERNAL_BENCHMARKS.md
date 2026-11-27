# External Figure & Plotting Benchmarks (Outside Data for `mintfig`)

To validate `mintfig` and `mint.check` on **unseen, third-party datasets** beyond `figure-bench v0.1`, this guide catalogs the strongest existing open-source figure/plotting benchmarks, explains how each complements `figure-bench`, and shows how to run or audit them with [`external_bridge.py`](external_bridge.py).

---

## 1. Recommended External Benchmarks

| Benchmark | Source / Dataset | Size | Task Format | Native Scoring | Fit for `mintfig` / `mint.check` |
| :--- | :--- | ---: | :--- | :--- | :--- |
| **MatPlotBench** *(MatPlotAgent)* | [`thunlp/MatPlotAgent`](https://github.com/thunlp/MatPlotAgent) (`benchmark_instructions.json` + `benchmark_data/data/{id}/`) | **100** scientific tasks | Natural-language query (`simple` or `expert`) + raw CSV/data files → Python Matplotlib code | GPT-4V visual comparison vs reference plot (0–100) + execution rate | **Highest priority.** Closest external analog to `figure-bench` (raw scientific data → publication plot). Directly importable via `external_bridge.py import-matplotbench`. |
| **PandasPlotBench** | [`JetBrains-Research/PandasPlotBench`](https://github.com/JetBrains-Research/PandasPlotBench) · HF: `JetBrains-Research/PandasPlotBench` | **175** real-world tasks | DataFrame schema/data + natural-language plotting prompt → Matplotlib / Seaborn / Plotly code | Execution rate, visual/VLM faithfulness, code similarity | **High priority.** Great outside test of tabular/pandas coding-agent plotting. Importable via `external_bridge.py import-pandasplotbench`. |
| **VisEval** | [`microsoft/VisEval`](https://github.com/microsoft/VisEval) | **2,524** NL2VIS queries (146 DBs) | Natural-language query + DB tables → visualization code | Automated heterogeneous checkers: **Validity**, **Legality**, **Readability** | **Strong complement.** Automated readability/legality checks pair well with `neutral.py` and `mint.check` on a stratified 100–200 query subset. |
| **ChartMimic** | [`ChartMimic/ChartMimic`](https://github.com/ChartMimic/ChartMimic) · `VLMEvalKit` | **4,800** triplets (`direct_600`, `customized_600`) | Reference arXiv figure image (+ customized data/instruction) → Python Matplotlib code | Execution rate + multi-level automated High/Low-Level visual metrics | **Useful for `mint.check` wild-defect audits** (Customized Mimic also tests data-to-plot generation; Direct Mimic is visual reverse-engineering). |
| **Plot2Code** | [`TencentARC/Plot2Code`](https://github.com/TencentARC/Plot2Code) | **132** Matplotlib plots | Reference plot image / text instruction → pyplot code | Execution pass rate + text/visual similarity | **Good lightweight check** for Matplotlib visual fidelity & defect rates via `external_bridge.py audit-outputs`. |
| **AutoFigure / FigureBench / SciFig** | ICLR 2026 (`AutoFigure`), `SciFig` | 3,300+ pairs | Research paper text → schematic methodology diagram (SVG/XML) | VLM/human structural & aesthetic scoring | **Out of scope for data plotting** (targets conceptual architecture/workflow diagrams rather than quantitative data figures). |

---

## 2. Two Ways to Generate Independent Outside Data

### Workflow A — Run `mintfig` vs Plain Matplotlib on **MatPlotBench** or **PandasPlotBench**

1. **Fetch the upstream benchmark** (outside the repo, e.g., `/tmp/ext_benchmarks/`):
   ```bash
   git clone https://github.com/thunlp/MatPlotAgent.git /tmp/ext_benchmarks/MatPlotAgent
   # or export PandasPlotBench from Hugging Face:
   # python -c "from datasets import load_dataset; load_dataset('JetBrains-Research/PandasPlotBench', split='test').to_json('/tmp/ext_benchmarks/pandasplotbench.jsonl')"
   ```
2. **Import into `figure-bench`-compatible task directories** (each gets `context.md`, `data/`, and `external_meta.json`):
   ```bash
   python evals/figure_bench/external_bridge.py import-matplotbench \
       --src /tmp/ext_benchmarks/MatPlotAgent/benchmark_data \
       --out /tmp/ext_benchmarks/matplotbench_tasks \
       --instruction simple
   ```
   ```bash
   python evals/figure_bench/external_bridge.py import-pandasplotbench \
       --src /tmp/ext_benchmarks/pandasplotbench.jsonl \
       --out /tmp/ext_benchmarks/pandasplotbench_tasks
   ```
3. **Run your model/arms** (e.g., plain Matplotlib, Matplotlib + `mint.check` hook, and `mintfig`), saving each task's `figure.py`, `figure.png`, and optional `timing.json` under `<outputs_dir>/<task_id>/`.
4. **Score with BOTH:**
   - The **external benchmark's own native evaluator** (for external comparability on their leaderboard), AND
   - `external_bridge.py audit-outputs` (below) to measure **display-width legibility, overlaps, line-struck labels, malformed text, rainbow colormaps, CVD/grayscale contrast, truncated bars, and full per-task timing**.

### Workflow B — Audit Any Existing External Benchmark Outputs (Zero Re-Run Required)

If you already have generated scripts or PNG/SVG figures from **MatPlotBench**, **PandasPlotBench**, **ChartMimic**, or **Plot2Code**, you can audit them immediately:

```bash
# Audit rendered PNGs/SVGs (library-agnostic: Matplotlib, Seaborn, Plotly, Altair, ggplot2)
python evals/figure_bench/external_bridge.py audit-outputs /path/to/external_outputs \
    --display-width 700 \
    --out /path/to/external_audit_report.json

# Also execute Matplotlib scripts under the neutral Figure.savefig hook (captures text px,
# overlaps, struck labels, malformed strings, clipped text, truncated bars, and exec timing)
python evals/figure_bench/external_bridge.py audit-outputs /path/to/external_outputs \
    --run-scripts \
    --display-width 700 \
    --out /path/to/external_audit_report.json
```

---

## 3. What `figure-bench` Tests That External Benchmarks Miss

Running **MatPlotBench** + **PandasPlotBench** alongside **figure-bench v0.1 (100 tasks)** gives complementary evidence:

- **External benchmarks** verify broad generalization across third-party prompts, gallery plot types, and DataFrame wrangling tasks written by other teams.
- **`figure-bench v0.1`** specifically stress-tests the failure modes that external benchmarks rarely grade:
  1. **Display-width legibility** (`>= 11 px` at `700 px` chat / `450 px` mobile / `1280 px` slide).
  2. **Epistemic traps & refusals** (18 tasks: overlapping-CI no-effect traps, multiple testing, Simpson's paradox, ecological fallacy, survivorship bias, denominator shift, cherry-picked windows, truncated-bar bait).
  3. **Verified headline numbers** matched against deterministic ground-truth CSVs.
  4. **Multi-turn editing & BYO-Matplotlib repair** (21 tasks).
  5. **End-to-end agent timing** (wall time, think time, script execution, audit latency, and time-to-pass distributions).
