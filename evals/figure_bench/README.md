# figure-bench

![Progress across three fix cycles](progress.png)

`make_progress.py` draws this with mintfig from `runs/r2`–`r5/results.json`. Run 1 used an earlier, easier task set.

Ten tasks that mimic a real agent thread: a short conversation (`context.md`)
in which a person shares data and asks for one figure, plus the data
(`data/*.csv`). The agent under test sees only its task folder and mintfig's
`SKILL.md`, writes a script that calls `mint.explain(...).save("figure.png")`,
and submits it.

| Task | Domain | What the figure must show |
| :--- | :--- | :--- |
| `01_ablation` | ML | Accuracy of two components against seed noise, weighed against a second table of latency cost |
| `02_ab_latency` | Product | Two latency distributions, medians and tail |
| `03_dose_response` | Pharmacology | Four dose–response curves (one inactive), where each crosses 50% |
| `04_battery_fade` | Batteries | Capacity fade to 80%, with a defective cell to exclude and say so |
| `05_retrofit` | Energy | Daily use before/after a retrofit, with a control building and a gap |
| `06_energy_mix` | Policy | **Edit a returned figure** (`data/sent_figure.png`): fix a wrong definition, keep the rest |
| `07_gene_change` | Genomics | Fold changes of 24 genes read by group, housekeeping flat |
| `08_hall_petch` | Materials | Yield strength vs grain size, per-alloy fits |
| `09_eval_matrix` | ML | Language × task grid against a previous checkpoint: did the gap close? |
| `10_incident` | Ops | Five services' error rates on a log axis, one spike |

Five more **held-out** tasks live in `heldout/` (survey shares, spectra, wait times,
scaling exponents, a signed budget change). They were added after the first fix cycle
and are never used to tune mintfig or SKILL.md; `grade` reports them separately.

## Scoring

- **Time:** from `start` to the end of the first passing `submit`; it
  includes the agent's reading and thinking.
- **Checks** (all must pass): the script runs; exactly one `mint.explain` figure
  saved as `figure.png`; no error-level issue; **no warnings**; smallest text
  >= 11 px at the 700 px chat width; chat width; a number in the takeaway;
  every panel titled; built-in forms only (no `mint.custom`); the PNG's embedded
  spec rebuilds; a `source=`; alt text. At most 3 submissions.
- **Independent layout audit** (does not trust mintfig's own issues): the figure
  is rebuilt from its embedded spec and every text matplotlib actually draws is
  checked: no two texts overlap, no text is crossed by a line, and no malformed
  text ("%%", repeated words such as "Share of Share of", an ASCII hyphen used
  as a minus sign, "nan"/"None").
- **Local renders:** agents are told not to render outside `submit`; images in
  the work folder that `submit` did not make are counted and reported.
- **Answer key** (reported by `grade` only, never by `submit`): a number in
  the takeaway matches the task's key quantity within tolerance
  (`answers.json`). Agents must not read it.

## Running

```bash
python evals/figure_bench/make_data.py            # (re)writes data and answers.json, deterministic
python evals/figure_bench/bench.py list
python evals/figure_bench/bench.py start 01_ablation --run runs/r1 --python <python with mintfig+pandas>
# the agent works in runs/r1/01_ablation/ and submits:
python evals/figure_bench/bench.py submit 01_ablation --run runs/r1 runs/r1/01_ablation/figure_script.py
python evals/figure_bench/bench.py grade --run runs/r1   # writes results.json and results.md
```

Every attempt is kept in `<run>/<task>/.bench/` (script, PNG, summary, checks).
`bench.py recheck --run <run>` re-applies the current checks to a finished run's
figures without re-running the scripts (for calibrating new checks).

Runs live under `runs/` (git-ignored except each run's `results.md`).

### Agent prompt used for runs

> You are an assistant in the middle of a conversation with a person. Run
> `<python> bench.py start <task> --run <run> --python <python>` and follow the
> rules it prints: read `context.md` and `data/` in the work folder and
> mintfig's `SKILL.md` (nothing else in the repository), write one script that
> answers the last request with one `mint.explain` figure saved as `figure.png`,
> and submit it with the printed command. Stop at the first passing submission
> (max 3). Then reply with the takeaway and the one or two sentences you would
> send the person.
