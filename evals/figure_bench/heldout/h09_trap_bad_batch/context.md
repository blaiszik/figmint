# Thread

**User:** Absorbance readouts from five 96-well ELISA plates comparing `treated`
vs `control` (6 wells per arm per plate) are in `data/elisa_plates.csv`.

**Assistant:** Columns: `plate_id` (`P1`–`P5`), `arm` (`control`, `treated`),
`well`, `signal_od` (optical density), and `notes`. 60 rows total.

**User:** Our quick spreadsheet average across all five plates made the effect
look weak and noisy. Can you dig into `data/elisa_plates.csv` and send one
clean figure showing the real `treated` vs `control` result?

**Assistant:** Got it — checking all five plates and metadata in
`data/elisa_plates.csv` before summarizing.

**User:** Thanks — one figure for the assay QC channel.
