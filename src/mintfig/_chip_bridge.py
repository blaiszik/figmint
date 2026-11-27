"""Optional interoperability bridge between ``mintfig`` and standalone ``mintchip``.

``mintfig`` has zero hard dependency on ``mintchip``: every helper in this module
imports ``mintchip`` lazily and falls back cleanly when it is not installed.
"""

from __future__ import annotations

import html
import importlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

#: CSS token overrides syncing ``mintchip`` custom properties with ``data-mc-scheme``,
#: ``data-mf-scheme`` (``mint.brief``), and ``data-theme`` (``.mintfig/index.html``).
_LIGHT_TOKENS = (
    "--mc-paper:#FFFFFF;--mc-ink:#1A1D21;"
    "--mc-accent:#3B7DDD;--mc-good:#2A9152;--mc-bad:#DC4535;--mc-warn:#B87A00"
)
_DARK_TOKENS = (
    "--mc-paper:#14181F;--mc-ink:#E6E9EE;"
    "--mc-accent:#5590E8;--mc-good:#31A05C;--mc-bad:#E85A48;--mc-warn:#C08000"
)

SCHEME_SYNC_CSS = (
    f":root{{{_LIGHT_TOKENS}}}\n"
    f"@media (prefers-color-scheme: dark){{:root{{{_DARK_TOKENS}}}}}\n"
    f':root[data-mc-scheme="light"],:root[data-mf-scheme="light"],:root[data-theme="light"]'
    f"{{{_LIGHT_TOKENS}}}\n"
    f':root[data-mc-scheme="dark"],:root[data-mf-scheme="dark"],:root[data-theme="dark"]'
    f"{{{_DARK_TOKENS}}}\n"
)

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")

#: Legacy ``mint.inline`` -> standalone ``mintchip`` migration mapping.
MIGRATION_MAP: dict[str, str] = {
    "mint.inline.spark": "mintchip.spark",
    "mint.inline.ci": "mintchip.ci",
    "mint.inline.dist": "mintchip.dist",
    "mint.inline.bar": "mintchip.bar",
    "mint.inline.strip": "mintchip.strip",
    "mint.inline.delta": "mintchip.delta",
    "mint.inline.waterfall": "mintchip.waterfall",
    "mint.inline.share": "mintchip.share",
    "mint.inline.funnel": "mintchip.funnel",
    "mint.inline.ratio": "mintchip.ratio",
    "mint.inline.gauge": "mintchip.gauge",
    "mint.inline.timeline": "mintchip.timeline",
    "mint.inline.rank": "mintchip.rank",
    "mint.inline.shared_domain": "mintchip.shared_domain",
    "mint.inline.format_prose": "mintchip.format_prose",
    "mint.inline.document": "mintchip.document",
}


def import_mintchip() -> Any | None:
    """Return the ``mintchip`` module if installed, else ``None``."""
    try:
        return importlib.import_module("mintchip")
    except ImportError:
        return None


def has_mintchip() -> bool:
    """Return ``True`` when standalone ``mintchip`` is importable."""
    return import_mintchip() is not None


def _is_mintchip_module(obj: Any) -> bool:
    mod = getattr(type(obj), "__module__", "")
    return mod == "mintchip" or mod.startswith("mintchip.")


def is_table(obj: Any) -> bool:
    """Duck-typed check for a ``mintchip.Table`` without importing ``mintchip``."""
    if not _is_mintchip_module(obj):
        return False
    return (
        hasattr(obj, "columns")
        and hasattr(obj, "rows")
        and callable(getattr(obj, "html", None))
        and callable(getattr(obj, "markdown", None))
    )


def is_chip(obj: Any) -> bool:
    """Duck-typed check for a ``mintchip.Chip`` without importing ``mintchip``."""
    if not _is_mintchip_module(obj) or is_table(obj):
        return False
    return (
        hasattr(obj, "kind")
        and callable(getattr(obj, "html", None))
        and callable(getattr(obj, "markdown", None))
    )


def is_chip_item(obj: Any) -> bool:
    """Return ``True`` for either a ``mintchip.Chip`` or ``mintchip.Table``."""
    return is_chip(obj) or is_table(obj)


def chip_css() -> str:
    """Return ``mintchip.css()`` if ``mintchip`` is installed, else ``""``."""
    mc = import_mintchip()
    if mc is None:
        return ""
    css_fn = getattr(mc, "css", None)
    if not callable(css_fn):
        return ""
    return str(css_fn())


def _import_directives() -> Any | None:
    if import_mintchip() is None:
        return None
    try:
        return importlib.import_module("mintchip.directives")
    except ImportError:
        return None


def render_prose_html(block: str, *, theme: str = "auto") -> tuple[list[str], bool]:
    """Split a prose block into escaped paragraph HTML strings, rendering any ``{{...}}``
    mintchip directives inline when ``mintchip`` is importable.

    Returns ``(paragraphs, used_mintchip)``. When ``mintchip`` is absent or ``block`` has no
    valid directives, literal text is escaped and returned untouched.
    """
    if "{{" not in block:
        return [html.escape(p.strip()) for p in _PARAGRAPH_SPLIT.split(block) if p.strip()], False

    directives = _import_directives()
    if directives is None:
        return [html.escape(p.strip()) for p in _PARAGRAPH_SPLIT.split(block) if p.strip()], False

    try:
        pieces, found = directives.find(block)
    except Exception:  # noqa: BLE001 - non-mintchip {{...}} templates stay literal
        return [html.escape(p.strip()) for p in _PARAGRAPH_SPLIT.split(block) if p.strip()], False

    if not found:
        joined = "".join(pieces)
        return [html.escape(p.strip()) for p in _PARAGRAPH_SPLIT.split(joined) if p.strip()], False

    chips = [d.chip for d in found]
    domains = directives.shared_domains(chips)

    paragraphs: list[list[str]] = [[]]

    def _append_literal(raw: str) -> None:
        segs = _PARAGRAPH_SPLIT.split(raw)
        paragraphs[-1].append(html.escape(segs[0]))
        for seg in segs[1:]:
            paragraphs.append([html.escape(seg)])

    _append_literal(pieces[0])
    for d, dom, piece in zip(found, domains, pieces[1:], strict=True):
        if d.chip is not None:
            paragraphs[-1].append(d.chip.html(theme=theme, domain=dom))
        _append_literal(piece)

    rendered = ["".join(parts).strip() for parts in paragraphs if "".join(parts).strip()]
    return rendered, True


def render_prose_markdown(block: str) -> tuple[str, bool]:
    """Render any ``{{...}}`` mintchip directives in ``block`` as Markdown code spans when
    ``mintchip`` is importable; pass prose through untouched otherwise."""
    if "{{" not in block:
        return block, False

    directives = _import_directives()
    if directives is None:
        return block, False

    try:
        rendered, found = directives.render(block, format="md")
    except Exception:  # noqa: BLE001 - non-mintchip {{...}} templates stay literal
        return block, False

    return (str(rendered), bool(found))


def render_notebook_strip(
    entries: Sequence[Mapping[str, Any]],
    *,
    limit: int = 20,
) -> tuple[str, str]:
    """Build the `.mintfig/index.html` header ship-history strip.

    When ``len(entries) >= 2`` and ``mintchip`` is importable, returns
    ``(strip_html, mintchip_css_block)`` using ``mintchip.strip`` on the most recent
    ``limit`` entries (chronological order, oldest to newest). When ``mintchip`` is
    absent, returns a plain `.badge` summary with empty extra CSS. For fewer than 2
    entries, returns ``("", "")``.
    """
    if len(entries) < 2:
        return "", ""

    recent = list(entries[-limit:])
    values = [bool(e.get("ship", False)) for e in recent]
    passed = sum(1 for v in values if v)
    total = len(values)

    mc = import_mintchip()
    if mc is not None and callable(getattr(mc, "strip", None)):
        names = [
            str(e.get("takeaway") or e.get("id") or f"figure {i + 1}")[:48]
            for i, e in enumerate(recent)
        ]
        chip = mc.strip(values, names=names, label="Recent ship history")
        strip_html = f'<div class="nb-strip" id="nb-strip">{chip.html(theme="auto", label=True)}</div>'
        extra_css = f"{chip_css()}\n{SCHEME_SYNC_CSS}.nb-strip{{margin-top:6px;font-size:0.85rem}}\n"
        return strip_html, extra_css

    cls = "ship" if passed == total else "fix"
    badge = f'<span class="badge {cls}">{passed}/{total} ship</span>'
    return f'<div class="nb-strip" id="nb-strip">{badge}</div>', ".nb-strip{margin-top:6px}\n"


def migration_note() -> str:
    """Short migration guide from legacy ``mint.inline`` to standalone ``mintchip``."""
    return (
        "Legacy `mint.inline` remains supported for backward compatibility, while new inline "
        "word-sized graphics, shared-scale tables, and `{{...}}` prose directives live in the "
        "zero-dependency `mintchip` package (`pip install 'mintfig[chip]'` or `pip install mintchip`). "
        "Pass `mintchip.Chip` and `mintchip.Table` objects directly into `mint.brief(...)`."
    )
