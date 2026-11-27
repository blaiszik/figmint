# mintfig Plugin for Claude Code

Automatically teaches Claude Code how to build message-first scientific figures (`mint.explain`, `mint.table`, and publication-ready journal plates) and installs a zero-noise `PostToolUse` guardrail that audits any plain Matplotlib or Seaborn script before its figure is shared.

## Prerequisites

Install the `mintfig` CLI in your environment (once):

```bash
pip install mintfig
# or: uv tool install mintfig
```

## 1-Command Installation

Install directly from GitHub:

```bash
claude plugin install https://github.com/blaiszik/mintfig --path plugins/claude-code
```

Or load directly from a local checkout:

```bash
claude --plugin-dir ./plugins/claude-code
```

Alternatively, install the global skill and `PostToolUse` hook via the `mintfig` CLI:

```bash
mintfig skill --install --global
mintfig hook --install --global
```

## What Is Included

| Component | Path | Purpose |
| :--- | :--- | :--- |
| Agent skill + references | `skills/mintfig/` | Teaches `mint.explain`, `mint.table`, `mint.check`, and journal plate specs (`references/{science,recipes,publication}.md`). |
| Automatic `PostToolUse` hook | `hooks/hooks.json` | Runs `mintfig hook run` after `Bash`, `Write`, or `Edit`. Silent on non-plot files and clean figures; injects `fix_hint` feedback when a Matplotlib/Seaborn figure has blocking defects. |
| Slash command | `commands/check.md` | Adds `/mintfig:check <plot.py \| analysis.ipynb \| figure.pdf>` for on-demand figure and PDF auditing. |

Set `MINTFIG_DISABLE_HOOK=1` in your environment at any time to temporarily pause the automatic `PostToolUse` audit hook.
