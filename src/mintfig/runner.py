"""Strict-contract script runner for automated preflight and bundle generation."""

from __future__ import annotations

import contextlib
import inspect
import json
import runpy
import sys
import traceback
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib import rcsetup
from matplotlib.figure import Figure

from . import style
from .bundle import BundleResult, bundle_figure
from .explainer import Explanation
from .plate import Plate
from .preflight import PreflightReport, preflight_figure, preflight_pdf
from .specs import JournalSpec, get_spec

RunStage = Literal["preflight", "contract", "runtime"]


@dataclass
class RunResult:
    """Outcome of running a plotting script through mintfig preflight & bundling."""

    ok: bool
    exit_code: int
    stage: RunStage
    script_path: Path
    report: PreflightReport | None
    bundle: BundleResult | None
    error: str | None
    fix_hint: str | None
    pdf_report: PreflightReport | None
    journal: str = "nature"
    spec_version: str = ""
    spec_source_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return the structured v0.2 JSON payload for agents and CI."""
        if self.stage == "preflight" and self.report is not None:
            artifacts = self.bundle.to_dict() if self.bundle is not None else {}
            payload = self.report.to_agent_dict(artifacts=artifacts)
            payload["ok"] = self.ok
            payload["exit_code"] = self.exit_code
            payload["stage"] = self.stage
            payload["script_path"] = str(self.script_path)
            return payload

        return {
            "schema_version": "0.2",
            "ok": False,
            "exit_code": self.exit_code,
            "stage": self.stage,
            "script_path": str(self.script_path),
            "journal": self.journal,
            "spec_version": self.spec_version,
            "spec_source_url": self.spec_source_url,
            "dimensions_mm": None,
            "summary": {"errors": 1, "warnings": 0, "passed": 0},
            "recommended_max_loops": 2,
            "error": self.error,
            "fix_hint": self.fix_hint,
            "issues": [
                {
                    "rule": f"script_{self.stage}",
                    "severity": "error",
                    "panel": None,
                    "elements": [self.script_path.name],
                    "message": self.error or f"Script {self.stage} failure",
                    "fix_hint": self.fix_hint,
                }
            ],
            "artifacts": {},
        }


def _script_line_info(exc: BaseException, script_path: Path) -> str:
    """Return `` at script.py:LINE`` for the innermost traceback frame in the script, or ``""``."""
    if isinstance(exc, SyntaxError) and exc.lineno is not None:
        return f" at {script_path.name}:{exc.lineno}"
    target_str = str(script_path.resolve())
    for frame in reversed(traceback.extract_tb(exc.__traceback__)):
        if str(Path(frame.filename).resolve()) == target_str:
            return f" at {script_path.name}:{frame.lineno}"
    return ""


def _format_runtime_error(exc: BaseException, script_path: Path) -> str:
    """Format a concise runtime error message including script line number when available."""
    return f"{type(exc).__name__}{_script_line_info(exc, script_path)}: {exc}"


def _merge_pdf_errors(report: PreflightReport, pdf_report: PreflightReport) -> bool:
    """Merge PDF-only failures (e.g. Type 3 fonts or MediaBox drift) into ``report``.

    A live-figure check that marks itself ``details["authoritative"] = False``
    (a prediction from current rcParams, such as ``vector_fonts``) is replaced
    by the exported PDF's result for the same rule whatever that result is,
    because the file on disk is what gets submitted.

    Returns True if ``report`` was modified.
    """
    modified = False
    existing_by_rule = {c.rule: idx for idx, c in enumerate(report.checks)}
    pdf_by_rule = {c.rule: c for c in pdf_report.checks}
    for rule, idx in existing_by_rule.items():
        live = report.checks[idx]
        pdf_check = pdf_by_rule.get(rule)
        if (
            pdf_check is not None
            and live.details.get("authoritative") is False
            and live.status != pdf_check.status
        ):
            report.checks[idx] = pdf_check
            modified = True
    for pdf_check in pdf_report.failures:
        idx = existing_by_rule.get(pdf_check.rule)
        if idx is None:
            report.checks.append(pdf_check)
            modified = True
        elif report.checks[idx].status != "fail":
            report.checks[idx] = pdf_check
            modified = True
    return modified


def _explanation_figure(explanation: Explanation) -> Figure:
    """Unwrap ``mint.explain(...)`` for the runner, keeping its style active for export.

    An Explanation renders under a scoped style; fonts are resolved at draw
    time, so the same rcParams must be live while the runner saves the bundle.
    ``run_script`` restores the caller's rcParams afterwards.
    """
    style.apply(explanation.spec)
    return explanation.fig


def _discover_target(
    namespace: dict[str, Any],
    *,
    spec: JournalSpec,
    width: str | float | None,
    script_path: Path | None = None,
) -> tuple[Plate | Figure | None, RunStage | None, str | None, str | None]:
    """Resolve ``build()``, ``plate``, or ``fig`` according to the strict script contract."""
    build_fn = namespace.get("build")
    if callable(build_fn):
        try:
            sig = inspect.signature(build_fn)
        except (TypeError, ValueError):
            sig = None

        kwargs: dict[str, Any] = {}
        if sig is not None:
            if "journal" in sig.parameters:
                kwargs["journal"] = spec.name
            if "width" in sig.parameters and width is not None:
                kwargs["width"] = width

        try:
            target = build_fn(**kwargs)
        except Exception as exc:  # noqa: BLE001
            line_info = _script_line_info(exc, script_path) if script_path is not None else ""
            return (
                None,
                "runtime",
                f"{type(exc).__name__} in build(){line_info}: {exc}",
                "Fix the runtime exception inside build() and re-run `mintfig run`.",
            )

        if isinstance(target, Explanation):
            target = _explanation_figure(target)
        if isinstance(target, (Plate, Figure)):
            return target, None, None, None
        return (
            None,
            "contract",
            f"build() returned {type(target).__name__}, expected mintfig.Plate or matplotlib.figure.Figure.",
            "Return a `mint.Plate` or `matplotlib.figure.Figure` from `def build() -> mint.Plate:`.",
        )

    for name in ("explanation", "fig"):
        if isinstance(namespace.get(name), Explanation):
            return _explanation_figure(namespace[name]), None, None, None

    plate_obj = namespace.get("plate")
    if isinstance(plate_obj, Plate):
        return plate_obj, None, None, None

    fig_obj = namespace.get("fig")
    if isinstance(fig_obj, Figure):
        return fig_obj, None, None, None

    return (
        None,
        "contract",
        "Script did not expose a `build()` callable, top-level `plate` (Plate), or top-level `fig` (Figure).",
        "Expose `plate = mint.Plate(...)` at module scope or define `def build() -> mint.Plate:`.",
    )


@contextlib.contextmanager
def _headless_backend() -> Iterator[None]:
    """Run the enclosed block under the non-interactive Agg backend.

    Interactive backends (e.g. ``macosx``) resize new figures to whole screen
    pixels, which breaks the millimetre lock. While active, ``matplotlib.use``
    and ``pyplot.switch_backend`` calls from user scripts are ignored. The
    caller's backend (or its unresolved auto-selection state) is restored on exit.
    """
    prev_backend = mpl.rcParams._get("backend")  # raw value; may be the auto sentinel
    prev_default = mpl.rcParamsDefault._get("backend")
    prev_backend_mod = plt._backend_mod
    orig_switch = plt.switch_backend
    orig_use = mpl.use

    orig_switch("agg")

    def _ignore_switch(*_args: Any, **_kwargs: Any) -> None:
        return None

    plt.switch_backend = _ignore_switch  # type: ignore[assignment]
    mpl.use = _ignore_switch  # type: ignore[assignment]
    try:
        yield
    finally:
        plt.switch_backend = orig_switch  # type: ignore[assignment]
        mpl.use = orig_use  # type: ignore[assignment]
        if prev_backend is rcsetup._auto_backend_sentinel or prev_backend_mod is None:
            # Backend had not been resolved yet: restore lazy auto-selection.
            mpl.rcParams._set("backend", prev_backend)
            mpl.rcParamsDefault._set("backend", prev_default)
            plt._backend_mod = None
        else:
            if str(prev_backend).lower() != "agg":
                orig_switch(prev_backend)
            mpl.rcParamsDefault._set("backend", prev_default)


def run_script(
    script_path: str | Path,
    *,
    journal: str | JournalSpec = "nature",
    width: str | float | None = None,
    bundle_dir: str | Path | None = None,
    include_proof: bool = True,
    strict: bool = False,
) -> RunResult:
    """Execute a plotting script, preflight its figure, and optionally export a bundle."""
    path = Path(script_path).resolve()
    spec = get_spec(journal)
    spec_version = getattr(spec, "spec_version", "")
    spec_source_url = getattr(spec, "source_url", "")

    if not path.exists():
        return RunResult(
            ok=False,
            exit_code=2,
            stage="runtime",
            script_path=path,
            report=None,
            bundle=None,
            error=f"Script not found: {path}",
            fix_hint=f"Verify that the script path {path} exists and is readable.",
            pdf_report=None,
            journal=spec.name,
            spec_version=spec_version,
            spec_source_url=spec_source_url,
        )

    orig_sys_path = list(sys.path)
    orig_show = plt.show
    existing_fignums = set(plt.get_fignums())
    created_fig: Figure | None = None

    try:
        with _headless_backend(), mpl.rc_context():
            script_dir = str(path.parent)
            if not sys.path or sys.path[0] != script_dir:
                sys.path.insert(0, script_dir)
            # Prevent user scripts calling plt.show() from blocking headless runs
            plt.show = lambda *_args, **_kwargs: None  # type: ignore[assignment]

            try:
                namespace = runpy.run_path(str(path), run_name="__mintfig_run__")
            except Exception as exc:  # noqa: BLE001
                return RunResult(
                    ok=False,
                    exit_code=2,
                    stage="runtime",
                    script_path=path,
                    report=None,
                    bundle=None,
                    error=_format_runtime_error(exc, path),
                    fix_hint="Fix the Python exception in the plotting script and re-run `mintfig run`.",
                    pdf_report=None,
                    journal=spec.name,
                    spec_version=spec_version,
                    spec_source_url=spec_source_url,
                )

            target, err_stage, err_msg, err_hint = _discover_target(
                namespace, spec=spec, width=width, script_path=path
            )
            if target is None:
                return RunResult(
                    ok=False,
                    exit_code=2,
                    stage=err_stage or "contract",
                    script_path=path,
                    report=None,
                    bundle=None,
                    error=err_msg,
                    fix_hint=err_hint,
                    pdf_report=None,
                    journal=spec.name,
                    spec_version=spec_version,
                    spec_source_url=spec_source_url,
                )

            created_fig = target.fig if isinstance(target, Plate) else target
            report = preflight_figure(created_fig, spec, strict=False)

            bundle_res: BundleResult | None = None
            pdf_report: PreflightReport | None = None
            if bundle_dir is not None:
                raw_caption = namespace.get("CAPTION")
                script_caption = (
                    raw_caption.strip()
                    if isinstance(raw_caption, str) and raw_caption.strip()
                    else None
                )
                raw_label = namespace.get("LABEL")
                script_label = (
                    raw_label.strip()
                    if isinstance(raw_label, str) and raw_label.strip()
                    else "fig:fig1"
                )
                raw_takeaway = namespace.get("TAKEAWAY")
                script_takeaway = (
                    raw_takeaway.strip()
                    if isinstance(raw_takeaway, str) and raw_takeaway.strip()
                    else None
                )
                raw_notes = namespace.get("PANEL_NOTES")
                script_notes = (
                    {str(k): str(v) for k, v in raw_notes.items()}
                    if isinstance(raw_notes, dict)
                    else None
                )
                bundle_res = bundle_figure(
                    target,
                    bundle_dir,
                    journal=spec,
                    report=report,
                    source_path=path,
                    caption=script_caption,
                    label=script_label,
                    takeaway=script_takeaway,
                    panel_notes=script_notes,
                    include_proof=include_proof,
                )
                pdf_report = preflight_pdf(bundle_res.figure_pdf, spec)
                if _merge_pdf_errors(report, pdf_report):
                    payload = report.to_agent_dict(artifacts=bundle_res.to_dict())
                    bundle_res.report_json.write_text(
                        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
                    )

            ok = report.passed and (not strict or not report.warnings)
            exit_code = 0 if ok else 1

            return RunResult(
                ok=ok,
                exit_code=exit_code,
                stage="preflight",
                script_path=path,
                report=report,
                bundle=bundle_res,
                error=None,
                fix_hint=None,
                pdf_report=pdf_report,
                journal=spec.name,
                spec_version=spec_version,
                spec_source_url=spec_source_url,
            )
    finally:
        plt.show = orig_show
        sys.path[:] = orig_sys_path
        if created_fig is not None:
            plt.close(created_fig)
        for num in set(plt.get_fignums()) - existing_fignums:
            plt.close(num)
