# Thread

**User:** We profiled six Triton/CUDA kernels on an H100 (`peak = 989 TFLOP/s`, HBM bandwidth `3.35 TB/s`,
ridge point `~295 FLOP/byte`). Measurements are in `data/roofline_kernels.csv`.

**Assistant:** Columns: `kernel`, `arith_intensity_flop_per_byte`, `achieved_tflops`, `roof_tflops`,
`roof_efficiency_pct`, and `regime`.

**User:** Put these on a log–log Roofline plot so the systems team can see which kernels are hitting the
memory ceiling versus leaving compute headroom on the table (`moe_grouped_gemm` looks suspicious).
