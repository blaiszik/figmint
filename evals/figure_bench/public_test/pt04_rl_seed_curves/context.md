# Thread

**User:** Training curves for our three continuous-control RL algorithms across
six random seeds up to 100k environment steps are in `data/rl_returns.csv`.

**Assistant:** Columns: `algorithm` (`SAC-tuned`, `TD3-clip`, `PPO-base`),
`seed` (0–5), `step_k` (0 to 100 in 10k increments), and `return_score`. 198
rows total.

**User:** Reviewers always ask for both the learning-curve mean ± SD band and
the raw individual seed scores at 100k steps so they can verify no single lucky
seed is carrying the average. How far ahead is `SAC-tuned` at 100k steps, and
does it beat both baselines outside seed spread?

**Assistant:** I'll show the mean learning curves with ±1 SD bands and include
the six final-step seed scores per algorithm.

**User:** Awesome — one figure for the robotics lab chat.
