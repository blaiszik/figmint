# Thread

**User:** I'm inspecting our test-suite parallelization rollout inside a
450 px wide IDE sidebar pane. Durations for 80 `serial` runs and 80
`parallel_8w` runs are in `data/test_durations.csv`.

**Assistant:** Columns: `mode` (`serial`, `parallel_8w`), `run_id`,
`duration_s`, and `failed_tests`. Both modes are right-skewed.

**User:** Show the full duration distribution before and after enabling
8-worker parallel tests, including any slow tail runs, sized so every
label stays crisp inside a 450 px sidebar.

**Assistant:** I'll compare the `serial` and `parallel_8w` distributions
with medians, spread, and tail points tailored to a 450 px narrow width.

**User:** One compact sidebar-friendly figure, please.
