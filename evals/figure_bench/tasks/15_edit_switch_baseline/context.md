# Thread

**User:** Here are the load-test throughput numbers in `data/throughput.csv` and
the chart you sent earlier as `data/prior_figure.png`.

**Assistant:** Columns: `variant` (`legacy_v1`, `control_v2`, `cache_a`,
`cache_b`, `deprecated_exp`), `req_per_sec`, and `ci95` (95% CI half-width).

**User:** Two quick revisions from architecture review before we paste this into
the RFC:
1. Drop `deprecated_exp` — it failed durability checks and is no longer a candidate.
2. Switch the baseline from `legacy_v1` (retired last quarter) to `control_v2`
   and highlight `cache_b` so the gain over current production (`control_v2`) is
   immediately clear.

**Assistant:** I'll remove `deprecated_exp`, re-baseline against `control_v2`,
highlight `cache_b`, and update the takeaway to report the gain over `control_v2`.

**User:** Thanks — keep the rest of the figure clean and send the updated version.
