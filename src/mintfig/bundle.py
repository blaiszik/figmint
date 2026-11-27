"""Submission-ready figure bundle exporter (PDF, SVG, PNG, proof, LaTeX, JSON)."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from matplotlib.cm import ScalarMappable
from matplotlib.collections import PolyCollection
from matplotlib.container import ErrorbarContainer
from matplotlib.text import Text

from . import export
from .specs import JournalSpec, get_spec, in_to_mm, mm_to_in

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

    from .plate import Plate
    from .preflight import PreflightReport


@dataclass
class BundleResult:
    """Paths and preflight report produced by :func:`bundle_figure`."""

    out_dir: Path
    figure_pdf: Path
    figure_svg: Path
    preview_png: Path
    proof_png: Path | None
    figure_tex: Path
    reproduce_py: Path | None
    report_json: Path
    report: PreflightReport
    figure_json: Path | None = None
    caption_txt: Path | None = None

    def to_dict(self) -> dict[str, str | None]:
        """Return string paths for all exported bundle artifacts."""
        return {
            "out_dir": str(self.out_dir),
            "figure_pdf": str(self.figure_pdf),
            "figure_svg": str(self.figure_svg),
            "preview_png": str(self.preview_png),
            "proof_png": str(self.proof_png) if self.proof_png is not None else None,
            "figure_tex": str(self.figure_tex),
            "caption_txt": str(self.caption_txt) if self.caption_txt is not None else None,
            "reproduce_py": str(self.reproduce_py) if self.reproduce_py is not None else None,
            "report_json": str(self.report_json),
            "figure_json": str(self.figure_json) if self.figure_json is not None else None,
        }


_SAMPLE_N_RE = re.compile(r"\b[nN]\s*=\s*(\d[\d,]*)")


def _ensure_sentence(text: str) -> str:
    cleaned = " ".join(str(text).split()).strip()
    if not cleaned:
        return ""
    if cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def _format_panel_key_for_journal(key: str, spec: JournalSpec) -> str:
    k = str(key).strip()
    return k.upper() if spec.panel_label_case == "upper" else k.lower()


def _detect_error_and_sample_info(
    panel_items: list[tuple[str, Axes]],
    *,
    extra_texts: list[str],
    explanation: Any | None = None,
) -> tuple[list[str], list[str]]:
    """Detect error bars, shaded uncertainty bands, and sample counts ``n``."""
    error_notes: list[str] = []
    sample_counts: list[str] = []
    has_errorbars = False
    has_bands = False

    for _key, ax in panel_items:
        for container in ax.containers:
            if isinstance(container, ErrorbarContainer):
                has_errorbars = True
        for col in ax.collections:
            if isinstance(col, PolyCollection):
                alpha = col.get_alpha()
                if alpha is None or float(alpha) < 0.75:
                    has_bands = True
        for txt in ax.texts:
            raw = txt.get_text().strip()
            if raw:
                for m in _SAMPLE_N_RE.finditer(raw):
                    val = m.group(1)
                    if val not in sample_counts:
                        sample_counts.append(val)

    for text in extra_texts:
        if not text:
            continue
        for m in _SAMPLE_N_RE.finditer(text):
            val = m.group(1)
            if val not in sample_counts:
                sample_counts.append(val)

    if explanation is not None and hasattr(explanation, "panels"):
        for panel in explanation.panels.values():
            pspec = getattr(panel, "spec", {}) or {}
            err_lbl = pspec.get("error_label")
            band_lbl = pspec.get("band_label")
            if err_lbl:
                note = f"Error bars indicate {err_lbl}"
                if note not in error_notes:
                    error_notes.append(note)
            elif pspec.get("error") is not None:
                has_errorbars = True
            if band_lbl:
                note = f"Shaded bands indicate {band_lbl}"
                if note not in error_notes:
                    error_notes.append(note)
            elif pspec.get("band") is not None:
                has_bands = True
            n_val = pspec.get("n")
            if isinstance(n_val, int):
                s = f"{n_val:,}"
                if s not in sample_counts:
                    sample_counts.append(s)
            elif isinstance(n_val, Mapping):
                vals = [int(v) for v in n_val.values() if isinstance(v, (int, float))]
                if vals:
                    lo, hi = min(vals), max(vals)
                    s = f"{lo:,}" if lo == hi else f"{lo:,}–{hi:,}"
                    if s not in sample_counts:
                        sample_counts.append(s)
            for fact in getattr(panel, "facts", ()) or ():
                for m in _SAMPLE_N_RE.finditer(str(fact)):
                    val = m.group(1)
                    if val not in sample_counts:
                        sample_counts.append(val)

    if not error_notes:
        if has_errorbars and has_bands:
            error_notes.append("Error bars and shaded regions denote uncertainty intervals")
        elif has_errorbars:
            error_notes.append("Error bars denote uncertainty intervals")
        elif has_bands:
            error_notes.append("Shaded regions denote uncertainty bands")

    return error_notes, sample_counts


def _draft_caption(
    *,
    fig: Figure,
    spec: JournalSpec,
    takeaway: str | None = None,
    takeaway_subtitle: str | None = None,
    panel_notes: dict[str, str] | None = None,
    plate: Plate | None = None,
    explanation: Any | None = None,
    source: str | None = None,
    note: str | None = None,
) -> str:
    """Auto-draft a crisp Nature/Science-style manuscript figure legend."""
    from .preflight import _maps_data_to_color

    notes_lookup = {k.lower(): v.strip() for k, v in (panel_notes or {}).items() if v and v.strip()}

    if plate is not None:
        panel_items: list[tuple[str, Axes]] = [(key, plate.axes[key]) for key in plate.panel_keys]
    elif explanation is not None and getattr(explanation, "axes", None):
        panel_items = list(explanation.axes.items())
    else:
        panel_items = [
            (getattr(ax, "_mintfig_panel_key", None) or chr(ord("a") + idx), ax)
            for idx, ax in enumerate(fig.axes)
            if ax.get_visible()
            and getattr(ax, "_colorbar", None) is None
            and ax.get_label() != "<colorbar>"
            and getattr(ax, "_parent_axes", None) is None
        ]

    exp_panels: Mapping[str, Any] = (
        getattr(explanation, "panels", {}) if explanation is not None else {}
    )

    parts: list[str] = []

    # 1. Lead title sentence (Nature/Science bold legend opener)
    lead = (takeaway or "").strip()
    if not lead and panel_items:
        _first_key, first_ax = panel_items[0]
        first_title = (first_ax.get_title() or first_ax.get_title(loc="left") or "").strip()
        if first_title:
            lead = first_title
        else:
            xl = first_ax.get_xlabel().strip()
            yl = first_ax.get_ylabel().strip()
            if yl and xl:
                lead = f"{yl} as a function of {xl}"
            elif yl:
                lead = yl
            elif xl:
                lead = xl
            else:
                lead = f"Summary of {spec.display_name} figure"
    if lead:
        parts.append(_ensure_sentence(lead))

    if takeaway_subtitle and takeaway_subtitle.strip():
        sub = takeaway_subtitle.strip()
        if sub.lower() not in lead.lower():
            parts.append(_ensure_sentence(sub))

    # 2. Panel-by-panel clauses
    multi = len(panel_items) > 1
    panel_clauses: list[str] = []
    for key, ax in panel_items:
        disp_key = _format_panel_key_for_journal(key, spec)
        explicit_note = notes_lookup.get(str(key).lower())
        desc_bits: list[str] = []

        if explicit_note:
            desc_bits.append(explicit_note.rstrip("."))
        else:
            exp_panel = exp_panels.get(key) or exp_panels.get(str(key).lower())
            title = (ax.get_title() or ax.get_title(loc="left") or "").strip()
            if not title and exp_panel is not None and getattr(exp_panel, "title", None):
                title = str(exp_panel.title).strip()
            xl = ax.get_xlabel().strip()
            yl = ax.get_ylabel().strip()
            series = [
                str(line.get_label()).strip()
                for line in ax.get_lines()
                if line.get_visible()
                and line.get_label()
                and not str(line.get_label()).startswith("_")
            ]
            # Deduplicate series preserving order
            uniq_series = list(dict.fromkeys(series))

            cbar_label = ""
            for obj in list(ax.images) + list(ax.collections):
                if isinstance(obj, ScalarMappable) and _maps_data_to_color(obj):
                    cbar = getattr(obj, "colorbar", None)
                    if cbar is not None:
                        cbar_label = (
                            cbar.ax.get_ylabel().strip() or cbar.ax.get_xlabel().strip()
                        )
                        if cbar_label:
                            break

            if title:
                desc_bits.append(title.rstrip("."))
            if yl and xl:
                axis_phrase = f"{yl} versus {xl}"
                if not title or axis_phrase.lower() not in title.lower():
                    desc_bits.append(axis_phrase)
            elif yl and (not title or yl.lower() not in title.lower()):
                desc_bits.append(yl)
            elif xl and (not title or xl.lower() not in title.lower()):
                desc_bits.append(f"distribution across {xl}")
            elif exp_panel is not None and getattr(exp_panel, "describe", None):
                desc_bits.append(str(exp_panel.describe).rstrip("."))

            if cbar_label:
                desc_bits.append(f"colour scale shows {cbar_label}")
            if 2 <= len(uniq_series) <= 5:
                series_str = ", ".join(uniq_series[:-1]) + f" and {uniq_series[-1]}"
                desc_bits.append(f"comparing {series_str}")

        if desc_bits:
            body = "; ".join(desc_bits)
            if multi:
                panel_clauses.append(_ensure_sentence(f"{disp_key}, {body}"))
            elif body.lower() not in lead.lower():
                panel_clauses.append(_ensure_sentence(body))

    parts.extend(panel_clauses)

    # 3. Statistical / error-bar and sample-size disclosure
    extra_texts = [
        takeaway or "",
        takeaway_subtitle or "",
        note or "",
        source or "",
        *notes_lookup.values(),
    ]
    error_notes, sample_counts = _detect_error_and_sample_info(
        panel_items, extra_texts=extra_texts, explanation=explanation
    )
    existing_joined = " ".join(parts).lower()
    stat_bits: list[str] = []
    for en in error_notes:
        if en.lower() not in existing_joined:
            stat_bits.append(en)
    if sample_counts and not _SAMPLE_N_RE.search(" ".join(parts)):
        n_str = ", ".join(sample_counts[:3])
        if stat_bits:
            stat_bits[-1] = f"{stat_bits[-1]} (n = {n_str})"
        else:
            stat_bits.append(f"Sample size n = {n_str}")
    if stat_bits:
        parts.append(_ensure_sentence("; ".join(stat_bits)))

    # 4. Notes & source provenance
    if note and note.strip() and note.strip().lower() not in " ".join(parts).lower():
        parts.append(_ensure_sentence(note.strip()))
    if source and source.strip():
        src = source.strip()
        if src.lower() not in " ".join(parts).lower():
            parts.append(_ensure_sentence(f"Source: {src}"))

    if not parts:
        w_mm = in_to_mm(float(fig.get_figwidth()))
        return f"Publication figure formatted for {spec.display_name} ({w_mm:.1f} mm)."
    return " ".join(parts)


def _build_latex_snippet(
    *,
    spec: JournalSpec,
    width_mm: float,
    height_mm: float,
    caption: str,
    label: str,
) -> str:
    """Build a clean LaTeX figure environment referencing ``figure.pdf``."""
    spec_version = getattr(spec, "spec_version", "")
    source_url = getattr(spec, "source_url", "")

    header_parts = [f"Journal: {spec.display_name} ({spec.name})"]
    if spec_version:
        header_parts.append(f"Spec version: {spec_version}")
    lines = [f"% Generated by mintfig | {' | '.join(header_parts)}"]
    if source_url:
        lines.append(f"% Guidelines: {source_url}")
    lines.append(f"% Physical dimensions: {width_mm:.1f} x {height_mm:.1f} mm")
    lines.extend(
        [
            r"\begin{figure}[t]",
            r"  \centering",
            rf"  \includegraphics[width={width_mm:.1f}mm]{{figure.pdf}}",
            rf"  \caption{{{caption}}}",
            rf"  \label{{{label}}}",
            r"\end{figure}",
            "",
        ]
    )
    return "\n".join(lines)


def _build_figure_sidecar(
    *,
    fig: Figure,
    spec: JournalSpec,
    width_mm: float,
    height_mm: float,
    caption: str,
    label: str,
    takeaway: str | None,
    takeaway_subtitle: str | None,
    panel_notes: dict[str, str] | None,
    reproduce_py: Path | None,
    plate: Plate | None,
) -> dict[str, Any]:
    """Build the message-first ``figure.json`` sidecar for humans and downstream agents."""
    from .preflight import _maps_data_to_color

    notes_lookup = {k.lower(): v for k, v in (panel_notes or {}).items()}
    repro_sha256: str | None = None
    if reproduce_py is not None and reproduce_py.exists():
        repro_sha256 = hashlib.sha256(reproduce_py.read_bytes()).hexdigest()

    if plate is not None:
        panel_items = [(key, plate.axes[key]) for key in plate.panel_keys]
    else:
        panel_items = [
            (getattr(ax, "_mintfig_panel_key", None) or f"ax{idx}", ax)
            for idx, ax in enumerate(fig.axes)
            if ax.get_visible() and getattr(ax, "_colorbar", None) is None
        ]

    panels_meta: list[dict[str, Any]] = []
    for key, ax in panel_items:
        series = [
            str(line.get_label())
            for line in ax.get_lines()
            if line.get_visible()
            and line.get_label()
            and not str(line.get_label()).startswith("_")
        ]
        cmaps: list[str] = []
        has_cbar = False
        for obj in list(ax.images) + list(ax.collections):
            if isinstance(obj, ScalarMappable) and _maps_data_to_color(obj):
                cname = str(obj.get_cmap().name)
                if cname not in cmaps:
                    cmaps.append(cname)
                if getattr(obj, "colorbar", None) is not None:
                    has_cbar = True
        title = (ax.get_title() or ax.get_title(loc="left") or "").strip()
        panels_meta.append(
            {
                "key": str(key),
                "title": title or None,
                "xlabel": ax.get_xlabel().strip() or None,
                "ylabel": ax.get_ylabel().strip() or None,
                "note": notes_lookup.get(str(key).lower()),
                "series": series,
                "colormaps": cmaps,
                "has_colorbar": has_cbar,
                "xscale": ax.get_xscale(),
                "yscale": ax.get_yscale(),
            }
        )

    return {
        "schema_version": "0.2",
        "journal": spec.name,
        "display_name": spec.display_name,
        "spec_version": getattr(spec, "spec_version", ""),
        "spec_source_url": getattr(spec, "source_url", ""),
        "dimensions_mm": {
            "width": round(float(width_mm), 2),
            "height": round(float(height_mm), 2),
        },
        "takeaway": takeaway,
        "takeaway_subtitle": takeaway_subtitle,
        "caption": caption,
        "label": label,
        "reproduce_sha256": repro_sha256,
        "panels": panels_meta,
    }


def bundle_figure(
    target: Plate | Figure,
    out_dir: str | Path,
    *,
    journal: str | JournalSpec | None = None,
    report: PreflightReport | None = None,
    source_path: str | Path | None = None,
    source_code: str | None = None,
    caption: str | None = None,
    label: str = "fig:fig1",
    takeaway: str | None = None,
    takeaway_subtitle: str | None = None,
    panel_notes: dict[str, str] | None = None,
    include_proof: bool = True,
    preview_dpi: int = 300,
    rasterize_above: int | None = 10_000,
) -> BundleResult:
    """Export a complete submission-ready artifact bundle to ``out_dir``.

    Writes ``figure.pdf`` (locked-mm Type 42 vector), ``figure.svg`` (editable
    vector text), ``preview.png``, optional ``proof.png`` (CVD + scorecard),
    ``figure.tex`` (LaTeX inclusion snippet), ``figure.json`` (message-first
    structured sidecar), optional ``reproduce.py``, and ``report.json``.
    """
    from . import preflight as _preflight
    from . import proof as _proof
    from .plate import Plate

    plate_obj: Plate | None = target if isinstance(target, Plate) else None
    if plate_obj is not None:
        fig = plate_obj.fig
        spec = get_spec(journal) if journal is not None else plate_obj.spec
    else:
        fig = target
        if journal is not None:
            spec = get_spec(journal)
        elif getattr(fig, "_mintfig_journal", None):
            spec = get_spec(fig._mintfig_journal)  # type: ignore[attr-defined]
        elif report is not None:
            spec = get_spec(report.journal)
        else:
            spec = get_spec("nature")

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    w_in, h_in = fig.get_size_inches()
    width_mm = in_to_mm(float(w_in))
    height_mm = in_to_mm(float(h_in))

    active_report = (
        report if report is not None else _preflight.preflight_figure(fig, spec, strict=False)
    )

    figure_pdf = export.save_figure(
        fig,
        out / "figure.pdf",
        spec=spec,
        rasterize_above=rasterize_above,
        lock_dimensions=True,
    )
    figure_svg = export.save_figure(
        fig,
        out / "figure.svg",
        spec=spec,
        rasterize_above=rasterize_above,
        lock_dimensions=True,
    )
    preview_png = export.save_figure(
        fig,
        out / "preview.png",
        spec=spec,
        dpi=preview_dpi,
        rasterize_above=rasterize_above,
        lock_dimensions=True,
    )

    proof_png: Path | None = None
    if include_proof:
        proof_png = _proof.render_proof_sheet(fig, active_report, out / "proof.png", dpi=220)

    resolved_takeaway = takeaway if takeaway is not None else (plate_obj.takeaway if plate_obj else None)
    resolved_subtitle = (
        takeaway_subtitle
        if takeaway_subtitle is not None
        else (plate_obj.takeaway_subtitle if plate_obj else None)
    )
    merged_notes: dict[str, str] = {}
    if plate_obj is not None and plate_obj.panel_notes:
        merged_notes.update(plate_obj.panel_notes)
    if panel_notes:
        merged_notes.update(panel_notes)

    resolved_caption = caption
    if (resolved_caption is None or not str(resolved_caption).strip()) and plate_obj is not None:
        resolved_caption = plate_obj.caption
    if resolved_caption is None or not str(resolved_caption).strip():
        fig_cap = getattr(fig, "_mintfig_caption", None)
        if isinstance(fig_cap, str) and fig_cap.strip():
            resolved_caption = fig_cap.strip()
    if resolved_caption is not None and str(resolved_caption).strip():
        effective_caption = str(resolved_caption).strip()
    else:
        effective_caption = _draft_caption(
            fig=fig,
            spec=spec,
            takeaway=resolved_takeaway,
            takeaway_subtitle=resolved_subtitle,
            panel_notes=merged_notes or None,
            plate=plate_obj,
        )

    caption_txt = out / "caption.txt"
    caption_txt.write_text(effective_caption.rstrip() + "\n", encoding="utf-8")

    figure_tex = out / "figure.tex"
    figure_tex.write_text(
        _build_latex_snippet(
            spec=spec,
            width_mm=width_mm,
            height_mm=height_mm,
            caption=effective_caption,
            label=label,
        ),
        encoding="utf-8",
    )

    reproduce_py: Path | None = None
    if source_path is not None:
        src = Path(source_path)
        dest = out / "reproduce.py"
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
        reproduce_py = dest
    elif source_code is not None:
        dest = out / "reproduce.py"
        dest.write_text(source_code, encoding="utf-8")
        reproduce_py = dest

    figure_json = out / "figure.json"
    sidecar = _build_figure_sidecar(
        fig=fig,
        spec=spec,
        width_mm=width_mm,
        height_mm=height_mm,
        caption=effective_caption,
        label=label,
        takeaway=resolved_takeaway,
        takeaway_subtitle=resolved_subtitle,
        panel_notes=merged_notes or None,
        reproduce_py=reproduce_py,
        plate=plate_obj,
    )
    figure_json.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")

    report_json = out / "report.json"
    result = BundleResult(
        out_dir=out,
        figure_pdf=figure_pdf,
        figure_svg=figure_svg,
        preview_png=preview_png,
        proof_png=proof_png,
        figure_tex=figure_tex,
        reproduce_py=reproduce_py,
        report_json=report_json,
        report=active_report,
        figure_json=figure_json,
        caption_txt=caption_txt,
    )

    artifacts_dict = result.to_dict()
    if hasattr(active_report, "to_agent_dict"):
        payload = active_report.to_agent_dict(artifacts=artifacts_dict)
    else:
        payload = active_report.to_dict()
    report_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    return result


def _strip_chat_chrome_and_refit(
    fig: Figure,
    spec: JournalSpec,
    *,
    width_mm: float,
    explanation: Any,
) -> None:
    """Remove chat headline banner, top rules, and footer lines, then refit vertical canvas."""
    if not fig.axes:
        return

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    fig_h_px = float(fig.bbox.height) or 1.0
    old_h_mm = in_to_mm(float(fig.get_figheight()))
    if old_h_mm <= 0.0:
        return

    ax_top_y = max(float(ax.get_position().y1) for ax in fig.axes)
    ax_bot_y = min(float(ax.get_position().y0) for ax in fig.axes)

    # Collect every figure-level Text/Annotation (including colored-word Annotation runs).
    fig_text_artists: list[Text] = []
    seen_ids: set[int] = set()
    for art in [*fig.texts, *fig.artists]:
        if isinstance(art, Text) and id(art) not in seen_ids:
            seen_ids.add(id(art))
            fig_text_artists.append(art)

    def _rendered_y_bounds(t: Text) -> tuple[float, float]:
        try:
            bb = t.get_window_extent(renderer)
            if bb is not None and bb.height > 0:
                return float(bb.y0) / fig_h_px, float(bb.y1) / fig_h_px
        except (RuntimeError, ValueError, AttributeError):
            pass
        ty = float(t.get_position()[1])
        return ty, ty

    y_bounds: dict[int, tuple[float, float]] = {id(t): _rendered_y_bounds(t) for t in fig_text_artists}

    # Identify panel-label tags and panel titles/measure lines to keep.
    panel_tags = [t for t in fig_text_artists if getattr(t, "_mintfig_panel_label", False)]
    panel_title_tokens: set[str] = set()
    for p in getattr(explanation, "panels", {}).values():
        for fld in (getattr(p, "title", None), getattr(p, "label", None), getattr(p, "measure_note", None)):
            if fld:
                panel_title_tokens.add(" ".join(str(fld).split()).lower())

    subtitle_norm = " ".join(str(getattr(explanation, "subtitle", None) or "").split()).lower()
    note_norm = " ".join(str(getattr(explanation, "note", None) or "").split()).lower()
    source_norm = " ".join(str(getattr(explanation, "source", None) or "").split()).lower()

    if panel_tags:
        body_ceiling_y = max(y_bounds[id(t)][1] for t in panel_tags) + 0.004
    else:
        # Single-panel figure: walk upward from axes top keeping panel title/measure lines,
        # stopping at the larger chat takeaway headline or subtitle.
        above = sorted(
            [t for t in fig_text_artists if y_bounds[id(t)][0] >= ax_top_y - 0.005],
            key=lambda t: y_bounds[id(t)][0],
        )
        max_fs = max((float(t.get_fontsize()) for t in above), default=0.0)
        kept_top = ax_top_y
        for t in above:
            raw = " ".join(t.get_text().split()).lower()
            fs = float(t.get_fontsize())
            ty0, ty1 = y_bounds[id(t)]
            is_headline = fs >= max_fs - 0.1 and max_fs > spec.font_max_pt + 0.4
            is_sub = bool(subtitle_norm) and raw and raw in subtitle_norm
            matches_panel = any(raw and (raw in tok or tok in raw) for tok in panel_title_tokens)
            gap_mm = (ty0 - kept_top) * old_h_mm
            if is_headline or is_sub or (not matches_panel and gap_mm > 5.0):
                break
            kept_top = max(kept_top, ty1)
        body_ceiling_y = kept_top + 0.004

    # Remove chat header texts (kicker, headline, subtitle) and bottom footer texts.
    remove_ids: set[int] = set()
    for t in fig_text_artists:
        if getattr(t, "_mintfig_panel_label", False):
            continue
        ty0, ty1 = y_bounds[id(t)]
        raw = " ".join(t.get_text().split()).lower()
        if ty0 > body_ceiling_y or (ty1 > body_ceiling_y + 0.015):
            remove_ids.add(id(t))
        elif ty1 < ax_bot_y - 0.015:
            is_footer = (
                raw.startswith("source:")
                or (bool(source_norm) and raw in source_norm)
                or (bool(note_norm) and raw in note_norm)
            )
            if is_footer:
                remove_ids.add(id(t))

    # Cascade removal to any Annotation chained onto a removed text via xycoords/anncoords.
    changed_rem = True
    while changed_rem:
        changed_rem = False
        for t in fig_text_artists:
            if id(t) in remove_ids:
                continue
            parent_ref = getattr(t, "anncoords", None) or getattr(t, "xycoords", None)
            if parent_ref is not None and id(parent_ref) in remove_ids:
                remove_ids.add(id(t))
                changed_rem = True

    for t in fig_text_artists:
        if id(t) in remove_ids:
            try:
                t.remove()
            except ValueError:
                pass

    # Remove top/bottom decorative rules/flags that sit outside the panel region.
    for line in [*list(fig.lines), *[a for a in fig.artists if hasattr(a, "get_ydata")]]:
        try:
            ys = [float(v) for v in line.get_ydata()]
        except (TypeError, ValueError, AttributeError):
            continue
        if not ys:
            continue
        if min(ys) > body_ceiling_y or max(ys) < ax_bot_y - 0.012:
            try:
                line.remove()
            except ValueError:
                pass

    # Align panel label typography with the target journal spec (case + bold pt).
    for idx, t in enumerate(panel_tags):
        raw = t.get_text().strip()
        if raw:
            t.set_text(raw.upper() if spec.panel_label_case == "upper" else raw.lower())
        t.set_fontsize(spec.panel_label_pt)
        t.set_fontweight(spec.panel_label_weight)
        t.set_color("#000000")
        t._mintfig_panel_key = raw.lower() if raw else chr(ord("a") + idx)  # type: ignore[attr-defined]
        t.set_gid(f"panel-{str(t._mintfig_panel_key).lower()}/labels")  # type: ignore[attr-defined]

    # Measure tight vertical bounds of remaining visible figure content.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    fig_h_px = float(fig.bbox.height) or 1.0
    y_min_frac = 1.0
    y_max_frac = 0.0

    for ax in fig.axes:
        if not ax.get_visible():
            continue
        tb = ax.get_tightbbox(renderer)
        if tb is not None and tb.height > 0:
            y_min_frac = min(y_min_frac, float(tb.y0) / fig_h_px)
            y_max_frac = max(y_max_frac, float(tb.y1) / fig_h_px)
        else:
            pos = ax.get_position()
            y_min_frac = min(y_min_frac, float(pos.y0))
            y_max_frac = max(y_max_frac, float(pos.y1))

    remaining_fig_texts = [
        t for t in fig_text_artists if id(t) not in remove_ids and t.get_visible() and t.get_text().strip()
    ]
    for t in remaining_fig_texts:
        try:
            bb = t.get_window_extent(renderer)
        except (RuntimeError, ValueError, AttributeError):
            continue
        if bb is not None and bb.height > 0:
            y_min_frac = min(y_min_frac, float(bb.y0) / fig_h_px)
            y_max_frac = max(y_max_frac, float(bb.y1) / fig_h_px)

    if y_max_frac <= y_min_frac:
        return

    y_bot_mm = max(0.0, y_min_frac * old_h_mm)
    y_top_mm = min(old_h_mm, y_max_frac * old_h_mm)
    content_h_mm = max(y_top_mm - y_bot_mm, 18.0)
    pad_mm = 3.0
    new_h_mm = round(min(content_h_mm + 2.0 * pad_mm, spec.max_height_mm), 1)
    avail_h_mm = max(new_h_mm - 2.0 * pad_mm, 10.0)
    scale_y = min(1.0, avail_h_mm / content_h_mm)

    def _map_y(y_old: float) -> float:
        mm_val = y_old * old_h_mm
        new_mm = (mm_val - y_bot_mm) * scale_y + pad_mm
        return new_mm / new_h_mm

    for ax in fig.axes:
        pos = ax.get_position()
        ny0 = _map_y(float(pos.y0))
        ny1 = _map_y(float(pos.y1))
        ax.set_position([float(pos.x0), ny0, float(pos.width), max(ny1 - ny0, 0.01)])

    for t in remaining_fig_texts:
        # Chained word-color Annotations anchor to their preceding Text artist;
        # moving the root Text automatically moves every chained run with it.
        if isinstance(getattr(t, "anncoords", None), Text) or isinstance(
            getattr(t, "xycoords", None), Text
        ):
            continue
        tx, ty = t.get_position()
        t.set_position((float(tx), _map_y(float(ty))))

    for line in [*list(fig.lines), *[a for a in fig.artists if hasattr(a, "get_ydata")]]:
        if line.get_transform() == fig.transFigure:
            line.set_ydata([_map_y(float(v)) for v in line.get_ydata()])

    fig.set_size_inches(mm_to_in(width_mm), mm_to_in(new_h_mm), forward=False)


def _clamp_publication_fonts(fig: Figure, spec: JournalSpec) -> None:
    """Keep every visible text artist inside the target journal's legal font-size bounds."""
    for txt in fig.findobj(Text):
        if not txt.get_visible() or not txt.get_text().strip():
            continue
        is_panel = bool(getattr(txt, "_mintfig_panel_label", False))
        fs = float(txt.get_fontsize())
        if is_panel:
            txt.set_fontsize(spec.panel_label_pt)
            continue
        if fs < spec.font_min_pt:
            txt.set_fontsize(spec.font_min_pt)
        elif fs > spec.font_max_pt:
            txt.set_fontsize(spec.font_max_pt)


def _fit_horizontal_overflow(fig: Figure) -> None:
    """Nudge rightmost axes width inward if any direct label overflows the locked canvas right edge."""
    if not fig.axes:
        return
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    fig_w_px = float(fig.bbox.width) or 1.0
    max_over_px = 0.0
    offending_axes: set[int] = set()
    for txt in fig.findobj(Text):
        if not txt.get_visible() or not txt.get_text().strip():
            continue
        try:
            bb = txt.get_window_extent(renderer)
        except (RuntimeError, ValueError, AttributeError):
            continue
        over = float(bb.x1) - (fig_w_px - 3.0)
        if over > 0.5:
            max_over_px = max(max_over_px, over)
            if txt.axes is not None:
                offending_axes.add(id(txt.axes))

    if max_over_px <= 0.5:
        return

    shrink_frac = (max_over_px + 4.0) / fig_w_px
    targets = [ax for ax in fig.axes if id(ax) in offending_axes] or [
        max(fig.axes, key=lambda a: float(a.get_position().x1))
    ]
    for ax in targets:
        pos = ax.get_position()
        new_w = max(float(pos.width) - shrink_frac, 0.12)
        ax.set_position([float(pos.x0), float(pos.y0), new_w, float(pos.height)])


def to_publication(
    explanation: Any,
    *,
    journal: str | JournalSpec = "nature",
    width: str | float = "double",
    out_dir: str | Path | None = None,
    style: str | None = None,
    keep_takeaway: bool = False,
    label: str = "fig:fig1",
    caption: str | None = None,
    include_proof: bool = True,
    preview_dpi: int = 300,
    rasterize_above: int | None = 10_000,
) -> BundleResult | Figure:
    """Convert a chat :class:`~mintfig.Explanation` into an exact-mm journal figure or bundle.

    Rebuilds ``explanation`` at the target journal's exact physical millimeter
    column geometry (e.g., Nature 183 mm double-column, Science 120 mm), moves
    the chat takeaway banner into an auto-drafted *Nature*/*Science* manuscript
    legend (``caption.txt`` and ``figure.tex``), and optionally exports a
    complete submission bundle to ``out_dir``.

    Parameters
    ----------
    explanation:
        An :class:`~mintfig.Explanation` produced by ``mint.explain(...)``.
    journal:
        Target journal preset or :class:`~mintfig.specs.JournalSpec` (default ``"nature"``).
    width:
        Journal column width preset (``"single"``, ``"mid"``, ``"double"``, ``"full"``)
        or explicit width in millimeters.
    out_dir:
        If provided, exports ``figure.pdf``, ``figure.svg``, ``preview.png``,
        ``proof.png``, ``figure.tex``, ``caption.txt``, ``figure.json``, and
        ``report.json`` and returns :class:`BundleResult`. If ``None``, returns
        the rebuilt Matplotlib :class:`~matplotlib.figure.Figure`.
    style:
        Optional surface style override; defaults to ``"mintfig"`` (clean white
        press ground with sans-serif typography).
    keep_takeaway:
        When ``False`` (default), strips the chat headline banner from the
        printed figure canvas so the takeaway lives cleanly in the manuscript
        caption. Set ``True`` to retain the headline inside the figure.
    """
    if not hasattr(explanation, "to_spec"):
        raise TypeError(
            f"to_publication() expects a mint.Explanation with .to_spec(), got {type(explanation).__name__}"
        )

    from ._explain.layout import explain_from_spec

    target_spec = get_spec(journal)
    width_mm = float(target_spec.resolve_width_mm(width))

    spec_dict = dict(explanation.to_spec())
    spec_dict["target"] = target_spec.name
    spec_dict["width"] = width
    spec_dict["style"] = style if style is not None else "mintfig"
    spec_dict.pop("kicker", None)

    pub_exp = explain_from_spec(spec_dict, strict=False)
    fig = pub_exp.fig
    fig._mintfig_journal = target_spec.name  # type: ignore[attr-defined]

    if not keep_takeaway:
        _strip_chat_chrome_and_refit(
            fig,
            target_spec,
            width_mm=width_mm,
            explanation=pub_exp,
        )

    _clamp_publication_fonts(fig, target_spec)
    _fit_horizontal_overflow(fig)

    # Tag panel axes with semantic gids so Illustrator/Inkscape layers stay clean.
    for key, ax in getattr(pub_exp, "axes", {}).items():
        ax._mintfig_panel_key = key  # type: ignore[attr-defined]
        if ax.get_gid() is None:
            ax.set_gid(f"panel-{str(key).lower()}/axes")

    # Build rich per-panel reading notes from Explanation panels for the manuscript caption.
    panel_notes: dict[str, str] = {}
    for key, panel in getattr(explanation, "panels", {}).items():
        bits: list[str] = []
        if getattr(panel, "title", None):
            bits.append(str(panel.title).strip().rstrip("."))
        if getattr(panel, "describe", None):
            desc = str(panel.describe).strip().rstrip(".")
            if not bits or desc.lower() not in bits[0].lower():
                bits.append(desc)
        if bits:
            panel_notes[str(key)] = "; ".join(bits)

    if caption is not None and str(caption).strip():
        effective_caption = str(caption).strip()
    else:
        effective_caption = _draft_caption(
            fig=fig,
            spec=target_spec,
            takeaway=getattr(explanation, "takeaway", None),
            takeaway_subtitle=getattr(explanation, "subtitle", None),
            panel_notes=panel_notes or None,
            explanation=explanation,
            source=getattr(explanation, "source", None),
            note=getattr(explanation, "note", None),
        )

    fig._mintfig_caption = effective_caption  # type: ignore[attr-defined]

    if out_dir is not None:
        return bundle_figure(
            fig,
            out_dir,
            journal=target_spec,
            caption=effective_caption,
            label=label,
            takeaway=getattr(explanation, "takeaway", None),
            takeaway_subtitle=getattr(explanation, "subtitle", None),
            panel_notes=panel_notes or None,
            include_proof=include_proof,
            preview_dpi=preview_dpi,
            rasterize_above=rasterize_above,
        )

    return fig
