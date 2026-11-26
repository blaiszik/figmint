# Mintfig Skill Trigger Evaluation Report

- **Mode:** `offline_rubric`
- **Exit Gate Verdict:** **PASS** (recall >= 85%, false-trigger rate <= 5%)
- **Dataset:** 40 realistic prompts (20 positive, 20 negative; zero mentions of `mintfig`)

## Summary Metrics

| Metric | Value | Gate | Status |
| :--- | ---: | :--- | :---: |
| Recall (TP / Pos) | **100.0%** (20/20) | >= 85% | PASS |
| False-trigger rate (FP / Neg) | **0.0%** (0/20) | <= 5% | PASS |
| Precision | 100.0% (20/20) | — | — |
| Accuracy | 100.0% (40/40) | — | — |
| F1 score | 1.000 | — | — |

## Skill Trigger Criteria Audit (`SKILL.md` + `AGENTS_SNIPPET.md`)

| Criterion | Present |
| :--- | :---: |
| `covers_five_plus_numbers` | yes |
| `covers_comparisons_trends_distributions` | yes |
| `covers_csv_experiments` | yes |
| `covers_matplotlib_check` | yes |
| `covers_notebook_check` | yes |
| `covers_publication_plates` | yes |
| `forbids_routine_code` | yes |
| `forbids_few_scalars` | yes |

## Per-Prompt Diagnostics

| ID | Category | Expected | Predicted | Outcome | Rule | Reason |
| :--- | :--- | :---: | :---: | :---: | :--- | :--- |
| `pos_01_ml_ablation` | `ml_ablation` | trigger | trigger | OK | `trigger_explain_data` | Matched 5+ numbers / visual explanation criteria (data_file, experiment_domain, visual_analysis_verb). |
| `pos_02_benchmark_suite` | `benchmark_run` | trigger | trigger | OK | `trigger_explain_data` | Matched 5+ numbers / visual explanation criteria (data_file, multi_entity_count, visual_analysis_verb). |
| `pos_03_noisy_csv_explore` | `csv_exploration` | trigger | trigger | OK | `trigger_explain_data` | Matched 5+ numbers / visual explanation criteria (data_file, multi_entity_count, visual_analysis_verb). |
| `pos_04_dose_response` | `pharmacology` | trigger | trigger | OK | `trigger_explain_data` | Matched 5+ numbers / visual explanation criteria (multi_entity_count, experiment_domain, visual_analysis_verb). |
| `pos_05_materials_doping` | `materials_science` | trigger | trigger | OK | `trigger_explain_data` | Matched 5+ numbers / visual explanation criteria (multi_entity_count, experiment_domain, visual_analysis_verb). |
| `pos_06_genomics_fold_change` | `genomics` | trigger | trigger | OK | `trigger_explain_data` | Matched 5+ numbers / visual explanation criteria (data_file, multi_entity_count, visual_analysis_verb). |
| `pos_07_review_matplotlib_script` | `matplotlib_review` | trigger | trigger | OK | `trigger_matplotlib_check` | Matched Matplotlib/notebook audit criteria (matplotlib_artifact, audit_intent). |
| `pos_08_nature_manuscript_plate` | `publication_plate` | trigger | trigger | OK | `trigger_publication_plate` | Matched publication plate criteria (journal_name, manuscript_plate). |
| `pos_09_neurips_scaling_figure` | `publication_plate` | trigger | trigger | OK | `trigger_publication_plate` | Matched publication plate criteria (journal_name, manuscript_plate). |
| `pos_10_ci_latency_spike` | `ops_latency` | trigger | trigger | OK | `trigger_explain_data` | Matched 5+ numbers / visual explanation criteria (data_file, visual_analysis_verb). |
| `pos_11_ab_rollout_distribution` | `ab_experiment` | trigger | trigger | OK | `trigger_explain_data` | Matched 5+ numbers / visual explanation criteria (data_file, visual_analysis_verb). |
| `pos_12_training_curves_hyperparams` | `ml_training` | trigger | trigger | OK | `trigger_explain_data` | Matched 5+ numbers / visual explanation criteria (data_file, multi_entity_count, visual_analysis_verb). |
| `pos_13_battery_capacity_fade` | `materials_science` | trigger | trigger | OK | `trigger_explain_data` | Matched 5+ numbers / visual explanation criteria (data_file, multi_entity_count, experiment_domain, visual_analysis_verb). |
| `pos_14_descriptor_correlation` | `scientific_analysis` | trigger | trigger | OK | `trigger_explain_data` | Matched 5+ numbers / visual explanation criteria (data_file, multi_entity_count, experiment_domain, visual_analysis_verb). |
| `pos_15_funnel_attrition` | `product_analytics` | trigger | trigger | OK | `trigger_explain_data` | Matched 5+ numbers / visual explanation criteria (data_file, multi_entity_count, experiment_domain, visual_analysis_verb). |
| `pos_16_pipeline_timeline` | `profiling` | trigger | trigger | OK | `trigger_explain_data` | Matched 5+ numbers / visual explanation criteria (data_file, experiment_domain, visual_analysis_verb). |
| `pos_17_cost_waterfall` | `attribution` | trigger | trigger | OK | `trigger_explain_data` | Matched 5+ numbers / visual explanation criteria (data_file, multi_entity_count, visual_analysis_verb). |
| `pos_18_retrofit_before_after` | `before_after` | trigger | trigger | OK | `trigger_explain_data` | Matched 5+ numbers / visual explanation criteria (data_file, multi_entity_count, experiment_domain, visual_analysis_verb). |
| `pos_19_check_notebook_figures` | `matplotlib_review` | trigger | trigger | OK | `trigger_matplotlib_check` | Matched Matplotlib/notebook audit criteria (matplotlib_artifact, audit_intent). |
| `pos_20_model_scorecard_table` | `benchmark_scorecard` | trigger | trigger | OK | `trigger_explain_data` | Matched 5+ numbers / visual explanation criteria (data_file, multi_entity_count, experiment_domain, visual_analysis_verb). |
| `neg_01_fix_keyerror_bug` | `bug_fix` | skip | skip | OK | `suppress_routine_code` | Suppressed by routine-coding exclusion (bug_fix_lint). |
| `neg_02_refactor_module` | `refactor` | skip | skip | OK | `suppress_routine_code` | Suppressed by routine-coding exclusion (refactor_rename). |
| `neg_03_write_unit_tests` | `unit_tests` | skip | skip | OK | `suppress_routine_code` | Suppressed by routine-coding exclusion (unit_test_code). |
| `neg_04_git_rebase_conflict` | `git_ops` | skip | skip | OK | `suppress_routine_code` | Suppressed by routine-coding exclusion (git_vcs). |
| `neg_05_read_stack_trace` | `stack_trace` | skip | skip | OK | `suppress_routine_code` | Suppressed by routine-coding exclusion (bug_fix_lint, stack_trace). |
| `neg_06_explain_architecture` | `architecture` | skip | skip | OK | `suppress_routine_code` | Suppressed by routine-coding exclusion (code_architecture). |
| `neg_07_update_dockerfile` | `config_docker` | skip | skip | OK | `suppress_routine_code` | Suppressed by routine-coding exclusion (config_docker_ci). |
| `neg_08_two_scalar_numbers` | `few_scalars` | skip | skip | OK | `suppress_few_scalars` | Suppressed by 1-3 scalar prose rule (few_scalars_explicit). |
| `neg_09_single_scalar_lookup` | `few_scalars` | skip | skip | OK | `suppress_few_scalars` | Suppressed by 1-3 scalar prose rule (few_scalars_explicit). |
| `neg_10_three_scalar_numbers` | `few_scalars` | skip | skip | OK | `suppress_few_scalars` | Suppressed by 1-3 scalar prose rule (few_scalars_explicit). |
| `neg_11_rename_symbol` | `refactor` | skip | skip | OK | `suppress_routine_code` | Suppressed by routine-coding exclusion (refactor_rename). |
| `neg_12_sql_migration` | `code_edit` | skip | skip | OK | `suppress_routine_code` | Suppressed by routine-coding exclusion (code_architecture). |
| `neg_13_pr_diff_review` | `code_review` | skip | skip | OK | `suppress_routine_code` | Suppressed by routine-coding exclusion (bug_fix_lint, git_vcs). |
| `neg_14_fix_ruff_mypy` | `bug_fix` | skip | skip | OK | `suppress_routine_code` | Suppressed by routine-coding exclusion (bug_fix_lint). |
| `neg_15_add_cli_flag` | `code_edit` | skip | skip | OK | `suppress_routine_code` | Suppressed by routine-coding exclusion (code_architecture). |
| `neg_16_debug_ci_workflow` | `config_docker` | skip | skip | OK | `suppress_routine_code` | Suppressed by routine-coding exclusion (config_docker_ci). |
| `neg_17_explain_python_decorator` | `code_explanation` | skip | skip | OK | `suppress_routine_code` | Suppressed by routine-coding exclusion (code_architecture). |
| `neg_18_update_pyproject` | `config_docker` | skip | skip | OK | `suppress_routine_code` | Suppressed by routine-coding exclusion (config_docker_ci). |
| `neg_19_write_docstrings` | `code_edit` | skip | skip | OK | `suppress_routine_code` | Suppressed by routine-coding exclusion (code_architecture). |
| `neg_20_check_regex` | `bug_fix` | skip | skip | OK | `suppress_routine_code` | Suppressed by routine-coding exclusion (bug_fix_lint). |
