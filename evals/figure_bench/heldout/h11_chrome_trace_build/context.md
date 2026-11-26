# Thread

**User:** Our release binary build takes nearly two minutes even with four
parallel codegen threads. The compiler trace export (`traceEvents` JSON
with microsecond `ts` and `dur`) is in `data/build_trace.json`.

**Assistant:** `build_trace.json` records 9 complete (`ph: "X"`) phase
events across threads `tid` 1–4: `parse_ast`, `typecheck`, `ir_optimize`,
four parallel `codegen_shard_*` tasks, `lto_link`, and `strip_and_sign`.

**User:** The team wants to add more codegen threads, but I suspect we're
hitting a serial bottleneck elsewhere. Show the parallel build timeline
and identify what dominates wall-clock time.

**Assistant:** I'll plot the compiler phases by thread over wall-clock
seconds and quantify the single largest stage's share of total build time.

**User:** One figure for the compiler build-time thread, please.
