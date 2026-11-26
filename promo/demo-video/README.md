# mintfig demo video (Remotion)

A 40-second social clip for `mint.check`: the figure an agent ships today, `mintfig check`
catching its wrong number and unreadable text, the fixed figure, `mint.explain`, and the
figure-bench numbers. 1920×1080 (`MintCheck`) and 1080×1080 (`MintCheckSquare`), 30 fps, silent.

Everything on screen is real: `make_assets.py` draws the figures with Matplotlib and mintfig
and runs `mint.check` on them (the terminal text in `src/Video.tsx` is that output, lightly
trimmed to fit). The bench numbers are the final-submission rows of
`evals/figure_bench/runs/compare_r6_b1_u1.md` (u1 plain Matplotlib vs r6 mintfig).

```bash
npm install
npm run assets          # re-render public/*.png and src/assets.json with mintfig's venv
npm run studio          # preview
npm run render          # out/mintfig-check-16x9.mp4
npm run render:square   # out/mintfig-check-1x1.mp4
```

`remotion.config.ts` points the renderer at the system Google Chrome: on the Mac this was
built on, Remotion's bundled chrome-headless-shell never fires `requestAnimationFrame`
and every render hangs at "Waiting for root component to load".
