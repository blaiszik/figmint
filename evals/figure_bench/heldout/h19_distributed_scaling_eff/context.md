# Thread

**User:** Strong-scaling efficiency (1 to 64 nodes, 5 runs each) for three distributed collective
backends (`NCCL`, `MPI-RDMA`, `Gloo-TCP`) is in `data/scaling_efficiency.csv`.

**Assistant:** Columns: `backend`, `nodes` (1–64, powers of 2), `run` (1–5), and `scaling_efficiency_pct`.

**User:** Chart strong-scaling efficiency across node counts (log x-axis) with 5-run spread and compare
`NCCL` vs `Gloo-TCP` at 64 nodes.
