"""Subprocess entry point for ``mintfig check`` under a project's own Python interpreter.

Invoked automatically by :func:`mintfig.figcheck.check_script` and
:func:`mintfig.figcheck.check_notebook` when the resolved interpreter (explicit
``--python`` or an auto-detected ``.venv`` / ``VIRTUAL_ENV`` / ``CONDA_PREFIX``)
differs from ``sys.executable``. Runs the target script or notebook with the
project's installed scientific stack (pandas, seaborn, scipy, etc.) while
injecting ``mintfig`` on ``sys.path`` only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run mintfig check inside a target Python environment.")
    parser.add_argument("--target", required=True, help="Path to .py script or .ipynb notebook.")
    parser.add_argument("--mode", choices=("script", "notebook"), required=True)
    parser.add_argument("--output", required=True, help="JSON output file path.")
    parser.add_argument("--width", default="chat", help="Display width preset or integer pixels.")
    parser.add_argument("--claim", default=None, help="Optional explicit claim text.")
    parser.add_argument("--mintfig-root", default=None, help="Directory containing the mintfig package.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.mintfig_root:
        root = str(Path(args.mintfig_root))
        if root not in sys.path:
            # Prefer target venv's compiled dependencies (numpy/matplotlib) if root is site-packages;
            # prepend when root is a source tree (e.g. src/) containing only mintfig.
            if Path(root).name in {"site-packages", "dist-packages"}:
                sys.path.append(root)
            else:
                sys.path.insert(0, root)

    out_path = Path(args.output)
    width: str | int = args.width
    try:
        from mintfig.figcheck import WIDTHS, _run_notebook_in_process, _run_script_in_process

        if width not in WIDTHS:
            width = int(str(width))
        if args.mode == "notebook":
            reports = _run_notebook_in_process(args.target, claim=args.claim, width=width)
        else:
            reports = _run_script_in_process(args.target, claim=args.claim, width=width)
        payload = {"ok": True, "reports": reports}
    except Exception as exc:  # noqa: BLE001 - propagate script/runner errors cleanly via JSON
        payload = {
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    out_path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
