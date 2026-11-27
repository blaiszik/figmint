# figure-bench v0.1 — Human Blind Reader Study App

`index.html` is a single-file, zero-CDN web app for running blinded human comprehension and
reading-speed studies on **figure-bench v0.1** figures.

## Why Display-Width Locking Matters

In the initial 15-task evaluation (`evals/figure_bench/runs/compare_r6_b1_u1.md`), blind VLM
readers viewed PNGs at full native resolution (e.g., 1400–2400 px wide), masking tiny 8–10 px
fonts and cramped labels that fail when displayed inside a real 700 px chat column or 450 px
phone/IDE sidebar.

This app locks every blinded PNG to its exact target reading width (`display_width_px`:
`700 px` for `chat`/`dark`, `450 px` for `narrow`, etc.), disables zooming/dragging, times
each trial accurately with `performance.now()` (excluding tab-away idle time), asks all
three structured rubric questions (`primary`, `uncertainty`, `nuance`) plus a 1–5 confidence
rating, and exports an anonymized JSON results file.

## Quick Start

1. Open `evals/figure_bench/human_study/index.html` directly in any modern browser (`file://`
   works with zero web server and zero network access).
2. Click **Launch Built-In 3-Figure Sample Study** to try the flow immediately, **or** load a
   real `readers-prepare` batch manifest JSON (and optionally attach its local PNG files).

## Preparing a Real Blind Batch

Generate display-width-locked, metadata-stripped reader batches using `bench.py`:

```bash
python evals/figure_bench/bench.py readers-prepare runs/r6 runs/b1 runs/u1 \
    --out evals/figure_bench/readers/study_01 \
    --per-reader 6 \
    --display-width 700
```

Create a batch `manifest.json` referencing the blinded folder IDs (never include `key.json`!):

```json
{
  "study_id": "study_01_batch_01",
  "items": [
    {
      "folder_id": "a1b2c3",
      "display_width_px": 700,
      "surface": "chat",
      "image_url": "a1b2c3/figure.png",
      "questions": {
        "primary": "How many points of accuracy does the reranker add?",
        "uncertainty": "Is the bigger encoder gain outside seed noise?",
        "nuance": "What latency cost accompanies the reranker?"
      }
    }
  ]
}
```

## Exporting & Scoring Results

When the reader finishes, the app provides two zero-PII JSON downloads:

- **Download Anonymized Study JSON**: full study record including `participant_id` (random hex),
  `elapsed_ms`, `hidden_ms`, `display_width_px`, `confidence`, and all three rubric answers.
- **Download `bench.py answers.json`**: drop-in batch file compatible with:

```bash
python evals/figure_bench/bench.py readers-score evals/figure_bench/readers/study_01
```
