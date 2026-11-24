# Thread

**User:** I finished the ablation sweep last night — five variants of the RAG
pipeline, five seeds each, evaluated on the held-out QA set. Results are in
`data/ablation_runs.csv`.

**Assistant:** Thanks. I see columns `variant`, `seed`, `accuracy_pct` (exact-match
accuracy, %). Variants: full model, no retrieval, no reranker, no fine-tuning,
smaller encoder. 25 rows, no missing values.

**User:** Great. My manager keeps asking whether the reranker and the bigger
encoder are worth their inference cost. Retrieval and fine-tuning we already
know we need. Serving numbers for each variant are in `data/variant_latency.csv`.

**Assistant:** That file has `variant`, `p50_latency_ms` and
`gpu_cost_per_1k_usd`. So the question is what each of those two components
buys in accuracy, whether that is more than seed-to-seed noise, and what it
costs in latency.

**User:** Exactly. One figure I can paste into the thread with my manager. Keep
it honest about the noise, and he reads Slack on his phone.
