"""Render all six ``fm.explain`` reference chat figures in ``bold``, ``editorial``, and ``sketch``.

All data are synthetic (reusing the six reference specs from ``gallery/output/explain/``).
Writes to ``gallery/output/explain_styles/<style>/<name>.png`` (plus reproducible ``.json``
specs) without modifying ``gallery/output/explain/``.
"""

from __future__ import annotations

import json
from pathlib import Path

import figmint as fm

STYLES: tuple[str, ...] = ("bold", "editorial", "sketch")
EXAMPLE_NAMES: tuple[str, ...] = (
    "latency_regression",
    "build_time",
    "benchmark_gains",
    "agent_matrix",
    "regional_orders",
    "checkout_story",
)


def render_all(
    *,
    styles: tuple[str, ...] = STYLES,
    out_root: Path | None = None,
) -> list[dict[str, object]]:
    """Render each reference spec across ``styles`` and return summary rows."""
    repo_gallery = Path(__file__).resolve().parent
    spec_dir = repo_gallery / "output" / "explain"
    target_root = out_root if out_root is not None else (repo_gallery / "output" / "explain_styles")

    rows: list[dict[str, object]] = []
    for style_name in styles:
        style_dir = target_root / style_name
        style_dir.mkdir(parents=True, exist_ok=True)
        for name in EXAMPLE_NAMES:
            spec = json.loads((spec_dir / f"{name}.json").read_text("utf-8"))
            spec["style"] = style_name
            explanation = fm.explain_from_spec(spec)
            summary = explanation.save(style_dir / f"{name}.png", write_spec=True)
            rows.append(
                {
                    "style": style_name,
                    "name": name,
                    "ok": summary["ok"],
                    "size_px": summary["size_px"],
                    "min_text_px": summary["display"]["min_text_px"],
                    "issues": summary["issues"],
                }
            )
    return rows


if __name__ == "__main__":
    results = render_all()
    for row in results:
        print(
            f"{row['style']:<8} {row['name']:<20} ok={row['ok']} "
            f"px={row['size_px']} min_px={row['min_text_px']} issues={row['issues']}"
        )
