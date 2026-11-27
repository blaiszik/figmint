# Thread

**User:** I ran `hyperfine --export-json` on our parser refactor branch
against `main` for both the JSON and YAML parsers (20 timed runs each).
Exports are in `data/main_bench.json` and `data/branch_bench.json`.

**Assistant:** Both files are standard `hyperfine` JSON exports with
`mean`, `stddev`, `median`, and raw per-run `times` (seconds) for
`parse_json` and `parse_yaml`.

**User:** Reviewers want to know if the branch actually sped up both
parsers or only one, and whether the change is bigger than run-to-run
noise.

**Assistant:** I'll compare `main` vs `branch` for both parsers, show
the run-to-run spread (s.d.), and report the percentage speedup.

**User:** One figure I can paste into the PR discussion thread, please.
