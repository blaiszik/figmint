# Thread

**User:** Our earlier mean-only bar chart (`data/prior_figure.png`) made `checkout_v2` and `checkout_v3`
look almost identical (~145 ms mean), yet users keep reporting slow hangs on `checkout_v3`! Raw
measurements (250 requests/version) are in `data/checkout_bimodal.csv`.

**Assistant:** Columns: `service` (`checkout_v2`, `checkout_v3`), `req_id`, and `latency_ms`.

**User:** Revise the figure to show the full latency distribution (or ECDF/percentiles) so the hidden
bimodal tail in `checkout_v3` (p95 around 615 ms!) stands out clearly.
