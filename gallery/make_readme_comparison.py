"""Render the side-by-side README comparison figures on the same ablation data.

Writes two PNGs into ``gallery/output/readme_comparison/`` without touching any
other gallery outputs:

- ``matplotlib_default.png``: a realistic default agent Matplotlib render
  (wide 12×4.8 in canvas that shrinks text below 11 px at 700 px chat width,
  truncated bar baseline, unlabelled error bars/bands, legend box, topic-only
  title) that fails ``mint.check``.
- ``mintfig_reply.png``: the clean ``mint.explain`` render of the exact same
  data, passing ``summary["ship"] is True`` with zero issues.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

import mintfig as mint

OUT_DIR = Path(__file__).resolve().parent / "output" / "readme_comparison"
SOURCE = "runs/ablation_2026-11 (5 seeds per variant)"


def build_ablation_data() -> dict[str, object]:
    """Deterministic 5-variant, 5-seed ablation dataset shared by both renders."""
    rng = np.random.default_rng(7)
    steps = np.arange(0, 2001, 250)
    finals_main = {"full model": 0.82, "no retrieval": 0.74, "no fine-tuning": 0.69}
    scores = {
        "full model": 0.82,
        "no augmentation": 0.80,
        "smaller encoder": 0.78,
        "no retrieval": 0.74,
        "no fine-tuning": 0.69,
    }
    errors = {
        "full model": (0.80, 0.84),
        "no augmentation": (0.78, 0.82),
        "smaller encoder": (0.75, 0.81),
        "no retrieval": (0.71, 0.77),
        "no fine-tuning": (0.66, 0.72),
    }
    curves: dict[str, list[float]] = {}
    bands: dict[str, float] = {}
    for name, final in finals_main.items():
        tau = 420.0 if name == "no fine-tuning" else 300.0
        mean = final * (1.0 - np.exp(-steps / tau))
        curves[name] = (mean + rng.normal(0.0, 0.003, steps.size)).round(3).tolist()
        bands[name] = 0.02
    return {
        "steps": steps.tolist(),
        "scores": scores,
        "errors": errors,
        "curves": curves,
        "bands": bands,
    }


def render_matplotlib_default(data: dict[str, object], out_path: Path) -> dict[str, object]:
    """Render a realistic default agent Matplotlib plot and audit it with mint.check."""
    scores: dict[str, float] = data["scores"]  # type: ignore[assignment]
    errors: dict[str, tuple[float, float]] = data["errors"]  # type: ignore[assignment]
    steps: list[int] = data["steps"]  # type: ignore[assignment]
    curves: dict[str, list[float]] = data["curves"]  # type: ignore[assignment]
    bands: dict[str, float] = data["bands"]  # type: ignore[assignment]

    names = list(scores.keys())
    vals = [scores[k] for k in names]
    yerr = [scores[k] - errors[k][0] for k in names]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.8))
    ax1.bar(names, vals, yerr=yerr, capsize=4, color="#1f77b4", alpha=0.85)
    ax1.set_ylim(0.55, 0.88)
    ax1.set_title("Test Accuracy")
    ax1.set_ylabel("Accuracy")
    ax1.tick_params(axis="x", rotation=22)

    for label, ys in curves.items():
        arr = np.asarray(ys, dtype=float)
        sd = bands[label]
        (line,) = ax2.plot(steps, arr, label=label, linewidth=1.8)
        ax2.fill_between(steps, arr - sd, arr + sd, alpha=0.2, color=line.get_color())
    ax2.set_title("Validation Accuracy")
    ax2.set_xlabel("Training Step")
    ax2.set_ylabel("Accuracy")
    ax2.legend(loc="lower right")

    fig.suptitle("Ablation Results")
    fig.tight_layout()

    report = mint.check(fig, dpi=150)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return report


def render_mintfig_reply(data: dict[str, object], out_path: Path) -> dict[str, object]:
    """Render the clean mint.explain figure on the exact same dataset."""
    scores: dict[str, float] = data["scores"]  # type: ignore[assignment]
    errors: dict[str, tuple[float, float]] = data["errors"]  # type: ignore[assignment]
    steps: list[int] = data["steps"]  # type: ignore[assignment]
    curves: dict[str, list[float]] = data["curves"]  # type: ignore[assignment]
    bands: dict[str, float] = data["bands"]  # type: ignore[assignment]

    fig = mint.explain(
        "Removing retrieval costs 8 points of accuracy; removing fine-tuning costs 13",
        mint.compare(
            scores,
            error=errors,
            error_label="95% CI, 5 seeds",
            title="Both losses are outside seed noise",
            label="Test accuracy",
            highlight=["no retrieval", "no fine-tuning"],
        ),
        mint.trend(
            steps,
            curves,
            band=bands,
            band_label="± 1 s.d.",
            title="The gap opens in the first 500 steps",
            label="Validation accuracy",
            x_label="Training step",
        ),
        source=SOURCE,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary = fig.save(out_path)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate README comparison PNGs.")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR, help="Output directory")
    parser.add_argument(
        "--copy-to",
        type=Path,
        default=None,
        help="Optional extra directory to copy both PNGs into",
    )
    args = parser.parse_args(argv)

    data = build_ablation_data()
    mpl_path = args.out_dir / "matplotlib_default.png"
    mint_path = args.out_dir / "mintfig_reply.png"

    mpl_report = render_matplotlib_default(data, mpl_path)
    mint_summary = render_mintfig_reply(data, mint_path)

    print(
        f"matplotlib_default.png: ship={mpl_report['ship']} "
        f"issues={[i['rule'] for i in mpl_report['issues']]} "
        f"min_text_px={mpl_report['display']['min_text_px']}"
    )
    print(
        f"mintfig_reply.png: ship={mint_summary['ship']} "
        f"issues={mint_summary['issues']} "
        f"size_px={mint_summary['size_px']}"
    )

    if mpl_report["ship"] is not False:
        raise RuntimeError("Expected matplotlib_default.png to fail mint.check!")
    if mint_summary["ship"] is not True or mint_summary["issues"]:
        raise RuntimeError(f"Expected mintfig_reply.png to ship cleanly, got {mint_summary['issues']}")

    if args.copy_to is not None:
        args.copy_to.mkdir(parents=True, exist_ok=True)
        shutil.copy2(mpl_path, args.copy_to / mpl_path.name)
        shutil.copy2(mint_path, args.copy_to / mint_path.name)
        print(f"Copied both PNGs to {args.copy_to}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
