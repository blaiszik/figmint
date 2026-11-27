# Thread

**User:** Developers are complaining about CI retries. Weekly flake rates across 8 test modules for
6 weeks (200 CI runs/cell) are in `data/ci_flakes_weekly.csv`.

**Assistant:** Columns: `module`, `week` (W01–W06), `flake_rate_pct`, and `n_ci_runs`.

**User:** Build a heatmap/matrix showing whether flakiness is repo-wide or concentrated in a specific
module and week.
