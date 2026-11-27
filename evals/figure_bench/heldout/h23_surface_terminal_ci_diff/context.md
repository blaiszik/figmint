# Thread

**User:** I'm over a 72-column SSH terminal with no image support. Compression codec benchmarks (8 runs
each) are in `data/codec_bench.csv`.

**Assistant:** Columns: `codec` (`lz4-fast`, `zstd-3`, `brotli-4`, `gzip-6`), `run` (1–8),
`decompress_mb_s`, and `compression_ratio`.

**User:** Return a <=72-column plain-text/Unicode comparison table or bar chart showing decompression
throughput (± SD across 8 runs) alongside compression ratio so we can choose between `lz4-fast` and
`zstd-3`.
