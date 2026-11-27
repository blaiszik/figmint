# Thread

**User:** We simulated three cache eviction policies (`LRU`, `W-TinyLFU`, `S3-FIFO`) across cache sizes
from 64 MB to 4096 MB over 5 production trace replays (`data/cache_mrc.csv`).

**Assistant:** Columns: `policy`, `cache_mb`, `trace_run` (1–5), and `miss_ratio_pct`.

**User:** Plot the miss-ratio curves on a log cache-size axis with replay spread and call out how much
`S3-FIFO` beats `LRU` at our production 256 MB tier.
