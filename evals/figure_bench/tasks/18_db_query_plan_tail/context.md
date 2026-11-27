# Thread

**User:** We added a composite B-tree index on `orders(customer_id, created_at)` and captured
p50/p95/p99 query latencies across 500 sampled queries per endpoint (`data/pg_latency_percentiles.csv`).

**Assistant:** Columns: `endpoint`, `stage` (`before_index`, `after_index`), `n_queries` (500),
`p50_ms`, `p95_ms`, and `p99_ms`.

**User:** Show the DBA team whether the index fixed the `orders_join` p99 tail and flag any write-path
overhead on `order_insert`.
