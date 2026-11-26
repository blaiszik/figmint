# `mintfig-check` GitHub Action

Reusable composite GitHub Action that runs [`mintfig check`](../../../README.md) on Matplotlib/Seaborn scripts (`.py`), Jupyter notebooks (`.ipynb`), and exported journal PDFs (`.pdf`), writing a compact Markdown scorecard to the GitHub Actions Step Summary and exposing it for optional PR comments.

## Quickstart: Check Changed Figures in Pull Requests

Drop this workflow into `.github/workflows/figure-check.yml`:

```yaml
name: Figure Check

on:
  pull_request:

permissions:
  contents: read

jobs:
  mintfig:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Check changed plotting scripts & PDFs
        uses: blaiszik/mintfig/.github/actions/mintfig-check@main
        with:
          paths: "changed"
          width: "chat"
```

When `paths: "changed"` is set, the action inspects files changed relative to the PR base branch (`origin/$GITHUB_BASE_REF...HEAD`), selects `.py` and `.ipynb` files that reference Matplotlib, Seaborn, or `mintfig` (plus changed `.pdf` files), and audits every figure they produce.

## Check Explicit Paths or Globs

```yaml
- name: Audit paper figures
  uses: blaiszik/mintfig/.github/actions/mintfig-check@main
  with:
    paths: "figures/*.py notebooks/analysis.ipynb manuscript/fig*.pdf"
    width: "slide"
    journal: "nature"
    strict: "true"
```

## Optional: Post the Report as a PR Comment

Give the job `pull-requests: write` permission and pass `steps.check.outputs.report-markdown` to `actions/github-script@v7`:

```yaml
permissions:
  contents: read
  pull-requests: write

jobs:
  mintfig:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - id: check
        uses: blaiszik/mintfig/.github/actions/mintfig-check@main
        with:
          paths: "changed"
          fail-on-fix: "false"

      - name: Comment PR with figure audit
        if: github.event_name == 'pull_request' && steps.check.outputs.checked-count != '0'
        uses: actions/github-script@v7
        env:
          MINTFIG_REPORT: ${{ steps.check.outputs.report-markdown }}
        with:
          script: |
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: process.env.MINTFIG_REPORT,
            });
```

## Inputs

| Input | Default | Description |
| :--- | :--- | :--- |
| `paths` | `"changed"` | Space-separated `.py` / `.ipynb` / `.pdf` paths or globs, or `"changed"` to auto-detect changed plotting files in a PR. |
| `width` | `"chat"` | Reading width for script/notebook checks: `narrow` (450 px), `chat` (700 px), `slide` (1280 px), or a pixel number. |
| `journal` | `"nature"` | Target journal preset for `.pdf` preflight (`nature`, `science`, `cell`, `pnas`, `neurips`, `ieee`, `acs`, `aps`, `rsc`). |
| `strict` | `"false"` | Fail on warnings and advisories in addition to blocking errors/defects. |
| `fail-on-fix` | `"true"` | Exit non-zero when any figure returns `FIX FIRST` or fails execution. |
| `python-version` | `"3.12"` | Python version installed by `actions/setup-python@v5`. |
| `mintfig-version` | `""` | Version pin (e.g. `"0.3.0"` or `">=0.3,<1.0"`). Leave empty for latest PyPI release (or local repo when run inside `mintfig`). |
| `write-summary` | `"true"` | Append the formatted Markdown report to `$GITHUB_STEP_SUMMARY`. |

## Outputs

| Output | Description |
| :--- | :--- |
| `passed` | `"true"` when every checked figure shipped cleanly, otherwise `"false"`. |
| `checked-count` | Number of figures audited across all matched targets. |
| `failed-count` | Number of figures with `FIX FIRST` or script errors. |
| `report-markdown` | Complete GitHub Markdown scorecard (table, claim mismatches + closest data values, and `fix_hint`s). |

## Pairing with Dual-Theme PR Figure Cards

To embed light/dark figures directly in PR descriptions, generate a card with `mintfig.pr_card.save_pr_card`:

```python
from mintfig.pr_card import save_pr_card

card = save_pr_card(fig, "docs/pr_figures", name="ablation", repo_prefix="docs/pr_figures")
print(card["markdown"])
```

The emitted `<picture>` block switches cleanly between `<name>.light.png` and `<name>.dark.png` for GitHub light and dark mode and includes collapsible computed facts plus `mintfig explain` reproduce commands.
