# Skill Trigger Evaluation (`evals/trigger_eval/`)

Measures whether coding agents activate the `mintfig` skill when a user asks for a quantitative explanation, Matplotlib audit, or journal plate — and stay silent during routine coding tasks where plotting would be spam.

## Dataset (`prompts.json`)

40 realistic developer and scientist prompts that **never mention `mintfig`**:

- **20 positive (`should_trigger: true`)**: ML ablations, multi-benchmark checkpoint comparisons, noisy CSV exploration, dose-response pharmacology, materials doping curves, genomics fold changes, reviewing plain Matplotlib scripts and `.ipynb` notebooks, Nature and NeurIPS manuscript plates, CI latency spikes, A/B rollout distributions, correlation matrices, funnels, timelines, waterfalls, and scorecards.
- **20 negative (`should_trigger: false`)**: bug fixes, module refactors, unit tests, git rebase/merge conflicts, stack traces, architecture explanations, Dockerfile/CI/config edits, SQL migrations, docstrings, regex checks, and 1–3 scalar number lookups.

## Exit Gates

- **Recall >= 85%** on positive prompts (`>= 17 / 20`)
- **False-trigger rate <= 5%** on negative prompts (`<= 1 / 20`)

## Usage

Run the deterministic offline rubric scorer (parses the live `src/mintfig/assets/SKILL.md` frontmatter and `src/mintfig/assets/AGENTS_SNIPPET.md` trigger criteria and writes `REPORT.md`):

```bash
PYTHONPATH=src python evals/trigger_eval/eval_triggers.py
```

Run live routing against an installed agent CLI (`claude`, `codex`, or `gemini`):

```bash
PYTHONPATH=src python evals/trigger_eval/eval_triggers.py --live --agent claude --report evals/trigger_eval/REPORT_live.md
PYTHONPATH=src python evals/trigger_eval/eval_triggers.py --live --agent codex --limit 10 --no-write-report
PYTHONPATH=src python evals/trigger_eval/eval_triggers.py --live --agent gemini --json
```

See [REPORT.md](REPORT.md) for the latest offline run results.
