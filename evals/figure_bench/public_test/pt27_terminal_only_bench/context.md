# Thread

**User:** I'm connected over plain SSH inside a 72-column terminal — I have
no image viewer at all, so do NOT rely on a PNG attachment. Serialization
benchmark runs for five libraries are in `data/bench.csv`.

**Assistant:** Columns: `library` (`flatwire`, `cbor-fast`, `msgpack-c`,
`proto-lite`, `json-std`), `run` (1–10), `encode_mb_s`, `decode_mb_s`, and
`payload_kb`.

**User:** We care most about decode throughput (MB/s) plus run-to-run
spread, and whether the fastest decoder bloats payload size compared to
`proto-lite`.

**Assistant:** I'll summarize all five libraries directly in a compact
<=72-column plain-text/Unicode table or bar display with means, s.d., and
payload sizes.

**User:** Great — keep every line <=72 columns so nothing wraps in SSH.
