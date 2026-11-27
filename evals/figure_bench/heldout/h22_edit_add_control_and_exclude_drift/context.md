# Thread

**User:** Our first figure (`data/prior_figure.png`) omitted `sham_control` and accidentally included
`R07` (`qc_status = temp_drift_fault`, 41.5 a.u.) from `data/assay_runs.csv`!

**Assistant:** Columns: `run_id` (R01–R09), `arm` (`sham_control`, `treated`), `qc_status`, and
`response_au`.

**User:** Please revise the figure to include `sham_control`, exclude `R07` with an explicit QC
disclosure, show individual valid runs + uncertainty, and report the corrected net lift.
