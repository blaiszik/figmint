# Thread

**User:** We benchmarked our 70B LLM serving cluster across batch sizes 1 to 64 (`data/llm_serving_batch.csv`).
Our interactive chat SLA requires `TTFT p95 <= 200 ms`.

**Assistant:** Columns: `batch_size`, `ttft_p95_ms`, `itl_p95_ms`, and `total_tok_per_s`.

**User:** Show the throughput vs TTFT tradeoff and highlight the highest-throughput batch size that
still meets our 200 ms TTFT SLA.
