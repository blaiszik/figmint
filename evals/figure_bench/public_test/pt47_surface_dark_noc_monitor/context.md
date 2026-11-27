# Thread

**User:** Our NOC wallboard runs in **dark mode** (dark slate/charcoal background, 700 px card). Please
chart edge-PoP TTFB latencies across 12 synthetic probes per PoP from `data/cdn_ttfb_probes.csv`.

**Assistant:** Columns: `edge_pop` (5 CDN PoPs), `probe_id` (1–12), and `ttfb_ms`.

**User:** Make sure it renders on a dark background with high-contrast labels and calls out the outlier
PoP (`gru-sa-east`).
