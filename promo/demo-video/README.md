# mintfig demo videos (Remotion)

Two 40-second social clips, each in 1920×1080 and 1080×1080, 30 fps, silent.

**`MintCheck` / `MintCheckSquare`** (`src/Video.tsx`) sell `mint.check`: the figure an agent
ships today, `mintfig check` catching its wrong number and unreadable text, the fixed figure,
`mint.explain`, and the figure-bench numbers. `make_assets.py` draws the figures and runs
`mint.check` on them (the terminal text is that output, lightly trimmed to fit). The bench
numbers are the final-submission rows of `evals/figure_bench/runs/compare_r6_b1_u1.md`
(u1 plain Matplotlib vs r6 mintfig).

**`AgentReply` / `AgentReplySquare`** (`src/AgentVideo.tsx`) sell the reply itself: an
agent's wall-of-numbers paragraph becomes prose with mintchip chips (and a chip's popover),
then a mintchip table, then a mintfig figure in the chat with a hover tooltip and
click-to-cite, then the same report as plain text in a terminal. `make_agent_assets.py`
writes `src/agent_assets.json`: mintchip's HTML chips, popover, table and stylesheet, and
mintfig's interactive HTML fragment, used as-is. The fragment's script is dropped, and the
video reproduces its hover with the page's own rules: the tooltip is the mark's aria-label,
centred above it, and the click note is `copied: <file> · <panel> · <name @ x = value>`. The
terminal lines are `mintchip render`, `mintchip table` and `mint.load(...).to_text()`. It
needs mintchip importable (`../../../mintchip/src` by default).

```bash
npm install
npm run assets                 # MintCheck: public/{before,after,mintfig}.png, src/assets.json
npm run assets:agent           # AgentReply: public/loss.png, src/agent_assets.json
npm run studio                 # preview
npm run render                 # out/mintfig-check-16x9.mp4
npm run render:square          # out/mintfig-check-1x1.mp4
npm run render:agent           # out/agent-reply-16x9.mp4
npm run render:agent:square    # out/agent-reply-1x1.mp4
```

`remotion.config.ts` points the renderer at the system Google Chrome: on the Mac this was
built on, Remotion's bundled chrome-headless-shell never fires `requestAnimationFrame`
and every render hangs at "Waiting for root component to load".
