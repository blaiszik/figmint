# Thread

**User:** We benchmarked 10 serving configurations for our agent router on
the 500-example internal eval suite. Results are in `data/eval_runs.jsonl`.

**Assistant:** Each JSON line has `config_id`, `model_tier`, `quantization`,
`accuracy_pct`, `accuracy_sd`, `p50_latency_ms`, `cost_per_1k_usd`, and
`eval_examples`.

**User:** Leadership wants to prune the catalog down to the Pareto-optimal
configs across accuracy, cost, and latency. Which configs actually sit on
the frontier, and which ones are strictly dominated?

**Assistant:** I'll plot accuracy (with eval uncertainty) against cost and
latency, highlight the Pareto frontier, and label the frontier configs.

**User:** One figure for the model-selection review thread, please.
