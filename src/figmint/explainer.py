"""Message-first figures for conversations.

``explain(takeaway, panel, ...)`` turns one claim plus its evidence into a
chat-sized figure. The caller states *what the reader should conclude* and picks
each panel by the question it answers; the information-design rules are applied
by construction rather than remembered:

==============  ===============================================  =================
Form            Question it answers                              Encoding
==============  ===============================================  =================
``compare``     How do items differ in size?                     sorted bars / dots
``trend``       How does it change over time or order?           lines, end labels
``change``      What moved between two states?                   slopegraph
``distribution``How are values spread within groups?             dots + median/IQR
``relate``      Do two measures move together?                   scatter (+ fit)
``share``       What makes up the total?                         sorted % bars
``matrix``      How do two categorical dimensions interact?      annotated heat table
==============  ===============================================  =================

Rules enforced here (sources in README, "Design rules"):

* The title is the takeaway sentence; each panel carries its own headline.
* Position/length on a common scale; bars start at zero; no pies, no dual axes.
* Colour marks only what the takeaway names (<= 3 highlights); the rest is grey.
  Without a highlight at most 4 series get a hue; more must be faceted.
* Labels sit on the data (no legends), all text is horizontal, units appear once.
* Text stays readable when the image is shown ~700 px wide in a chat column.
"""

from __future__ import annotations

import difflib
import functools
import inspect
import itertools
import json
import math
import numbers
import re
import unicodedata
import zlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from matplotlib import dates as mdates
from matplotlib import patheffects
from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import to_rgb
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from matplotlib.ticker import (
    FixedLocator,
    FuncFormatter,
    LogLocator,
    MaxNLocator,
    NullFormatter,
    NullLocator,
)
from matplotlib.transforms import Bbox

from .annotations import _relax_positions_pt
from .specs import JournalSpec, get_spec, mm_to_in
from .themes import (
    FIGMINT_THEME,
    THEME_ALIASES,
    THEMES,
    Theme,
    contrast_ratio,
    get_theme,
    relative_luminance,
)

# --------------------------------------------------------------------------- #
# House constants (sourced from the default theme for backwards compatibility)
# --------------------------------------------------------------------------- #

INK = FIGMINT_THEME.ink
MUTED = FIGMINT_THEME.muted
AXIS = FIGMINT_THEME.axis
GRID = FIGMINT_THEME.grid
CONTEXT_LINE = FIGMINT_THEME.context_line
CONTEXT_FILL = FIGMINT_THEME.context_fill
# Fixed categorical order (blue, vermilion, teal, amber), never cycled past four.
# Every pair is separated in hue under deuteranopia/protanopia *and* in
# lightness, so the lines stay distinct in a grayscale print.
SERIES_COLORS: tuple[str, ...] = FIGMINT_THEME.series_colors
# Highlights lead with the warm accent so the focus pops against grey context.
ACCENT_COLORS: tuple[str, ...] = FIGMINT_THEME.accent_colors
DEFAULT_COLOR = FIGMINT_THEME.default_color

MAX_HIGHLIGHTS = 3
MAX_COLORED_SERIES = 4
MAX_PANELS = 6
COMFORTABLE_PANELS = 4
MAX_COMPARE_ITEMS = 20
COMFORTABLE_COMPARE_ITEMS = 12
MAX_GROUPS = 8
MAX_TITLE_LINES = 3

#: Width, in CSS pixels, at which chat clients typically show an inline image.
DISPLAY_WIDTH_PX = 700
#: Smallest text height (px at display width) still comfortable to read.
MIN_TEXT_PX = 11.0

PT_TO_MM = 25.4 / 72.0
_MARGIN_MM = 4.0
_COL_GAP_MM = 8.0
_ROW_GAP_MM = 6.5
_LINE = 1.26  # line height as a multiple of font size

_ISO_DATE = re.compile(r"^\d{4}-\d{2}(-\d{2})?([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?)?$")
_TOPIC_TITLE = re.compile(
    r"^(overview|comparison|analysis|summary|results|plot|chart|figure|graph|breakdown)\b"
    r"|\b(vs\.?|versus)\b",
    re.IGNORECASE,
)
_HAS_DIGIT = re.compile(r"\d")

KINDS: tuple[str, ...] = (
    "compare",
    "trend",
    "change",
    "distribution",
    "relate",
    "share",
    "matrix",
)


class ExplainError(ValueError):
    """A rule the figure must satisfy was violated; ``fix_hint`` says how to repair it."""

    def __init__(self, message: str, *, fix_hint: str, rule: str = "explain_spec") -> None:
        super().__init__(f"{message} Fix: {fix_hint}")
        self.message = message
        self.fix_hint = fix_hint
        self.rule = rule


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #


_ILLUSTRATIVE_CUE = re.compile(
    r"\b(synthetic|illustrative|sketch|concept|conceptual|example|hypothetical|"
    r"estimate|estimated|schematic|stylized|toy|mock|demo|approximate|approx)\b",
    re.IGNORECASE,
)


def _plain(text: object, theme: Theme | None = None) -> str:
    """Escape ``$`` so user text is never parsed as mathtext ("from $5M to $8M").

    When ``theme`` defines ASCII glyph substitutes (e.g. ``sketch``), replaces
    Unicode minus, en-dash, and ellipsis on the rendered text artist.
    """
    out = str(text).replace(r"\$", "$").replace("$", r"\$")
    if theme is not None:
        if theme.minus_sign != "\N{MINUS SIGN}":
            out = _ascii_sci(out).replace("\N{MINUS SIGN}", theme.minus_sign)
        if theme.en_dash != "\N{EN DASH}":
            out = out.replace("\N{EN DASH}", theme.en_dash)
        if theme.ellipsis != "\N{HORIZONTAL ELLIPSIS}":
            out = out.replace("\N{HORIZONTAL ELLIPSIS}", theme.ellipsis)
    return _glyphs(out, ascii_only=theme is not None and theme.minus_sign == "-")


# --------------------------------------------------------------------------- #
# Scientific symbols: draw-time normalisation and missing-glyph detection
# --------------------------------------------------------------------------- #

_SUPER_CHARS = "⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺⁼⁽⁾ⁿⁱ"
_SUB_CHARS = "₀₁₂₃₄₅₆₇₈₉₋₊₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜ"
_SUPER_PLAIN = str.maketrans(_SUPER_CHARS, "0123456789-+=()ni")
_SUB_PLAIN = str.maketrans(_SUB_CHARS, "0123456789-+=()aeoxhklmnpst")
_SCRIPT_RUN = re.compile(f"([{_SUPER_CHARS}]+)|([{_SUB_CHARS}]+)")
#: Look-alikes that system fonts draw wrongly: Helvetica's MICRO SIGN is a slanted
#: italic mu, while its GREEK SMALL LETTER MU is upright like the surrounding text.
_GLYPH_SWAPS = str.maketrans({"\N{MICRO SIGN}": "\N{GREEK SMALL LETTER MU}"})
_MATH_WRAPPER = re.compile(r"\\math(?:regular|rm)\{|[{}^_$]|\\")


def _script(run: str, table: dict[int, int]) -> str:
    """A super/subscript run as upright body-font text ("{-}" keeps a sign unspaced)."""
    plain = run.translate(table)
    return r"\mathregular{" + "".join("{" + c + "}" if c in "-+=" else c for c in plain) + "}"


@functools.lru_cache(maxsize=64)
def _charmap(path: str) -> frozenset[int]:
    from matplotlib.font_manager import get_font

    try:
        return frozenset(get_font(path).get_charmap())
    except (OSError, RuntimeError, ValueError):
        return frozenset()


@functools.lru_cache(maxsize=64)
def _coverage_for(
    families: tuple[str, ...], weight: Any, style: str, rc_key: tuple[Any, ...]
) -> frozenset[int]:
    from matplotlib import font_manager

    prop = FontProperties(family=list(families), weight=weight, style=style)
    covered: set[int] = set()
    for path in font_manager.fontManager._find_fonts_by_props(prop):
        covered |= _charmap(str(path))
    return frozenset(covered)


def _coverage(prop: FontProperties) -> frozenset[int]:
    """Code points the font fallback chain of ``prop`` can draw (under the active rcParams)."""
    import matplotlib as mpl

    rc_key = tuple(tuple(mpl.rcParams[k]) for k in ("font.sans-serif", "font.serif", "font.family"))
    return _coverage_for(tuple(prop.get_family()), prop.get_weight(), prop.get_style(), rc_key)


def _body_coverage() -> frozenset[int]:
    """What the body font itself (no fallback) can draw."""
    return _coverage(FontProperties(family=["sans-serif"]))


def _glyphs(text: str, *, ascii_only: bool = False) -> str:
    """Draw-time symbol normalisation for already-escaped text.

    * MICRO SIGN -> Greek mu (upright in every body font).
    * A run of Unicode superscripts or subscripts ("×10¹⁷", "cm⁻³", "H₂O") is drawn
      as one mathtext script in the body font, so the run has one size, weight and
      baseline (fonts mix Latin-1 ¹²³ with the superscript block, often from
      different faces). ASCII-glyph styles write superscripts as "^-3" instead.
    * Inside such a string, characters the body font lacks are wrapped in
      ``\\mathrm{}`` so mathtext's fallback font draws them (non-math text in a
      mathtext string has no fallback of its own).
    """
    out = text.translate(_GLYPH_SWAPS)
    if not _SCRIPT_RUN.search(out):
        return out

    def _sub(m: re.Match[str]) -> str:
        if m.group(1):
            if ascii_only:
                return "^" + m.group(1).translate(_SUPER_PLAIN)
            return "$^{" + _script(m.group(1), _SUPER_PLAIN) + "}$"
        return "$_{" + _script(m.group(2), _SUB_PLAIN) + "}$"

    pieces = _SCRIPT_RUN.split(out)
    has_math = any(
        (i % 3 == 2 and p) or (i % 3 == 1 and p and not ascii_only) for i, p in enumerate(pieces)
    )
    if not has_math:
        return _SCRIPT_RUN.sub(_sub, out)
    body = _body_coverage()
    rebuilt: list[str] = []
    for i, piece in enumerate(pieces):
        if piece is None or piece == "":
            continue
        kind = i % 3
        if kind == 0:
            rebuilt.append(
                "".join(
                    c if (ord(c) in body or c.isspace() or not body) else "$\\mathrm{" + c + "}$"
                    for c in piece
                )
            )
        else:
            rebuilt.append(_SCRIPT_RUN.sub(_sub, piece))
    return "".join(rebuilt)


_TO_SUPER = {plain: sup for sup, plain in zip(_SUPER_CHARS, "0123456789-+=()ni", strict=True)}
_TO_SUB = {plain: sub for sub, plain in zip(_SUB_CHARS, "0123456789-+=()aeoxhklmnpst", strict=True)}
_DRAWN_SCRIPT = re.compile(r"\$([\^_])\{\\mathregular\{(.*?)\}\}\$")
_DRAWN_FALLBACK = re.compile(r"\$\\mathrm\{(.)\}\$")


def _reader_text(text: str) -> str:
    """Inverse of :func:`_plain` for drawn text: what the reader sees, as Unicode."""

    def _back(m: re.Match[str]) -> str:
        table = _TO_SUPER if m.group(1) == "^" else _TO_SUB
        return "".join(table.get(c, c) for c in m.group(2).replace("{", "").replace("}", ""))

    out = _DRAWN_FALLBACK.sub(lambda m: m.group(1), _DRAWN_SCRIPT.sub(_back, text))
    return out.replace(r"\$", "$")


def _logical_text(text: str) -> str:
    """The characters a reader sees, with figmint's mathtext wrappers removed."""
    from matplotlib import cbook

    if not cbook.is_math_text(text):
        return text
    return _MATH_WRAPPER.sub("", text.replace(r"\$", "\x00")).replace("\x00", "$")


def _missing_glyphs(fig: Figure) -> dict[str, str]:
    """Characters of visible text that no font in the artist's fallback chain can draw."""
    from matplotlib import cbook
    from matplotlib.text import Text

    missing: dict[str, str] = {}
    stix: frozenset[int] | None = None
    for artist in fig.findobj(Text):
        raw = artist.get_text()
        if not artist.get_visible() or not raw.strip():
            continue
        covered = _coverage(artist.get_fontproperties())
        if cbook.is_math_text(raw):
            if stix is None:
                stix = _coverage(FontProperties(family=["STIXGeneral", "DejaVu Sans"]))
            covered = covered | stix
        for ch in _logical_text(raw):
            if ch.isspace() or unicodedata.category(ch).startswith("C"):
                continue
            if ord(ch) not in covered and ch not in missing:
                missing[ch] = raw
    return missing


class _GlyphCapture:
    """Collect Matplotlib's missing-glyph warnings (and mathtext's log lines) instead of
    letting them reach stderr, where the agent never sees them."""

    _WARNING = re.compile(r"Glyph (\d+)")
    _LOG = re.compile(r"\[U\+([0-9a-fA-F]+)\]")

    def __init__(self) -> None:
        self.chars: set[str] = set()
        self._warnings: Any = None
        self._records: list[Any] = []
        self._others: list[Any] = []

    def _filter(self, record: Any) -> bool:
        match = self._LOG.search(record.getMessage())
        if match and "glyph" in record.getMessage():
            self.chars.add(chr(int(match.group(1), 16)))
            return False
        return True

    def __enter__(self) -> Any:
        import logging
        import warnings

        self._warnings = warnings.catch_warnings(record=True)
        self._records = self._warnings.__enter__()
        warnings.simplefilter("always")
        logging.getLogger("matplotlib.mathtext").addFilter(self._filter)
        logging.getLogger("matplotlib._mathtext").addFilter(self._filter)
        return self

    def __exit__(self, *exc: object) -> None:
        import logging
        import warnings

        logging.getLogger("matplotlib.mathtext").removeFilter(self._filter)
        logging.getLogger("matplotlib._mathtext").removeFilter(self._filter)
        self.missing()
        others = list(self._others)
        self._warnings.__exit__(*exc)
        for w in others:  # not ours to swallow
            warnings.warn_explicit(w.message, w.category, w.filename, w.lineno)

    def missing(self) -> set[str]:
        """Characters reported missing so far (warnings are consumed as they are read)."""
        while self._records:
            w = self._records.pop(0)
            match = self._WARNING.search(str(w.message))
            if match and "missing from" in str(w.message):
                self.chars.add(chr(int(match.group(1))))
            else:
                self._others.append(w)
        return set(self.chars)


def _glyph_issue(chars: Mapping[str, str] | set[str]) -> dict[str, Any]:
    listed = sorted(chars)
    named = ", ".join(
        f"{ch!r} (U+{ord(ch):04X} {unicodedata.name(ch, 'unnamed').lower()})" for ch in listed[:6]
    )
    return _issue(
        "glyph_missing",
        "warning",
        f"{len(listed)} character(s) cannot be drawn in this style's fonts and show as empty "
        f"boxes: {named}.",
        "Replace each with a plain-text equivalent (e.g. 'hbar' for ℏ, 'deg' for a missing "
        "degree sign, a Latin name for a symbol), or use a character from the same Unicode "
        "block that the figure already draws.",
    )


_FROM_SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")
_SCI_SUPERSCRIPT = re.compile("\N{MULTIPLICATION SIGN}10([⁻⁺]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+)")


def _ascii_sci(text: str) -> str:
    """For ASCII-glyph styles: "1.3×10⁻⁷" -> "1.3x10^-7" and "4.0×" -> "4.0x"."""
    out = _SCI_SUPERSCRIPT.sub(lambda m: "x10^" + m.group(1).translate(_FROM_SUPERSCRIPT), text)
    return out.replace("\N{MULTIPLICATION SIGN}", "x")


def _issue(
    rule: str,
    severity: str,
    message: str,
    fix_hint: str,
    *,
    panel: str | None = None,
) -> dict[str, Any]:
    return {
        "rule": rule,
        "severity": severity,
        "panel": panel,
        "message": message,
        "fix_hint": fix_hint,
    }


def _is_number(value: object) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return False
    if isinstance(value, (numbers.Real, np.integer, np.floating)):
        return True
    # 0-d numpy arrays (e.g. ``arr.sum(keepdims=False)`` from some libraries)
    return isinstance(value, np.ndarray) and value.ndim == 0 and value.dtype.kind in "iuf"


def _to_float(value: object, what: str) -> float:
    if value is None:
        return float("nan")
    if not _is_number(value):
        raise ExplainError(
            f"{what} must be a number, got {value!r}.",
            fix_hint="Pass plain numbers (not strings); convert or drop missing values first.",
        )
    return float(value)  # type: ignore[arg-type]


def _has_items(obj: object) -> bool:
    """Mapping-like: a dict, a dict view owner, a pandas Series or DataFrame (duck typed)."""
    return (
        not isinstance(obj, (str, bytes))
        and callable(getattr(obj, "items", None))
        and not isinstance(obj, np.ndarray)
    )


def _is_one_dimensional(obj: object) -> bool:
    """A pandas Series (or similar) is a sequence of values even though it has ``.items()``."""
    return getattr(obj, "ndim", None) == 1 and not isinstance(obj, Mapping)


def _pairs(obj: object) -> list[tuple[Any, Any]]:
    return list(obj.items())  # type: ignore[attr-defined]


def _named_values(values: object, what: str, *, allow_nan: bool = False) -> dict[str, float]:
    """Normalise a mapping or a sequence of ``(name, value)`` pairs to ``{name: float}``.

    Anything with ``.items()`` (a dict, a pandas Series) counts as a mapping.
    """
    if _has_items(values):
        items = _pairs(values)
    elif isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
        try:
            items = [(pair[0], pair[1]) for pair in values]
        except (TypeError, IndexError) as exc:
            raise ExplainError(
                f"{what} must be a mapping of name -> number.",
                fix_hint='Pass a dict such as {"checkout": 1840, "search": 460}.',
            ) from exc
    else:
        raise ExplainError(
            f"{what} must be a mapping of name -> number, got {type(values).__name__}.",
            fix_hint='Pass a dict such as {"checkout": 1840, "search": 460}.',
        )
    out: dict[str, float] = {}
    for name, value in items:
        key = str(name)
        if key in out:
            raise ExplainError(
                f"{what} repeats the name {key!r}.",
                fix_hint="Give every item a unique name (aggregate duplicates first).",
            )
        number = _to_float(value, f"{what}[{key!r}]")
        if not math.isfinite(number) and not allow_nan:
            raise ExplainError(
                f"{what}[{key!r}] is not finite ({value!r}).",
                fix_hint="Drop or impute missing values before plotting, and say so in `note`.",
            )
        out[key] = number
    if not out:
        raise ExplainError(f"{what} is empty.", fix_hint="Pass at least one named value.")
    return out


def _names(highlight: object, valid: Sequence[str], what: str = "highlight") -> list[str]:
    if highlight is None:
        return []
    names = [highlight] if isinstance(highlight, str) else [str(h) for h in highlight]  # type: ignore[union-attr]
    unknown = [n for n in names if n not in valid]
    if unknown:
        raise ExplainError(
            f"{what} names {unknown!r} that are not in the data.",
            fix_hint=f"Use names from: {', '.join(map(repr, list(valid)[:12]))}.",
        )
    if len(names) > MAX_HIGHLIGHTS:
        raise ExplainError(
            f"{what} lists {len(names)} items; more than {MAX_HIGHLIGHTS} highlights nothing.",
            fix_hint=f"Highlight only the <= {MAX_HIGHLIGHTS} items the takeaway sentence names.",
            rule="too_many_highlights",
        )
    return names


# --------------------------------------------------------------------------- #
# Argument checking shared by every form (unknown keywords -> ExplainError)
# --------------------------------------------------------------------------- #

#: Valid keyword arguments of each guarded callable, filled in by ``_guarded``.
_FORM_ARGS: dict[str, tuple[str, ...]] = {}
_EXPLAIN_ARGS = ("subtitle", "source", "note", "layout", "target", "width", "style", "out")
_LOG_X_WORDS = {"x_scale", "xscale", "x_log", "logx", "log_x", "xlog", "log_scale_x"}
_LOG_Y_WORDS = {
    "y_scale",
    "yscale",
    "y_log",
    "logy",
    "log_y",
    "ylog",
    "log_scale",
    "logscale",
    "log_axis",
    "log",
}
_INTERVAL_WORDS = {
    "errors",
    "err",
    "yerr",
    "xerr",
    "error_bars",
    "errorbars",
    "ci",
    "ci95",
    "std",
    "sd",
    "sem",
    "stderr",
    "uncertainty",
    "interval",
    "intervals",
    "error",
    "band",
    "bands",
    "spread",
}
_COLOUR_WORDS = {"color", "colour", "colors", "colours", "palette", "cmap", "colormap", "hue"}
_END_VALUE_WORDS = {
    "end_values",
    "end_value",
    "end_labels",
    "end_label",
    "show_values",
    "show_value",
    "label_values",
    "values_at_end",
    "show_end_values",
    "value_labels",
}
_ORDER_WORDS = {"sort", "order", "sorted", "sort_by", "ascending", "descending"}


def _specific_hint(kind: str, name: str, valid: Sequence[str]) -> str | None:
    """A hint for a keyword a scientist plausibly tries that this form does not take."""
    if kind != "explain" and name in _EXPLAIN_ARGS:
        return (
            f"`{name}=` belongs on fm.explain(...), not on a panel: "
            f"fm.explain(takeaway, fm.{kind}(...), {name}=...)."
        )
    if kind == "explain" and name in {"title", "label", "unit", "highlight", "fmt"}:
        return f"`{name}=` belongs on a panel, e.g. fm.compare({{...}}, {name}=...)."
    if name in _COLOUR_WORDS:
        return (
            "Colours are assigned by rule, not chosen: name the 1-3 things the takeaway is "
            "about in highlight= and everything else turns grey. A name keeps one colour "
            "across panels; to keep it across figures pin it on the figure: "
            'fm.explain(..., colors={"name": "red"}) (slots: blue, red, green, amber).'
        )
    if name in {"legend", "show_legend", "legend_loc"}:
        return "There are no legends: names are written on the data."
    if name in _LOG_X_WORDS:
        if "log_x" in valid:
            return "Use log_x=True for a logarithmic x axis."
        if "log" in valid:
            return f"{kind}() has one value axis; use log=True to make it logarithmic."
    if name in _LOG_Y_WORDS:
        if kind == "relate":
            return "Use log_y=True (and/or log_x=True) for logarithmic axes."
        if "log" in valid:
            return "Use log=True for a logarithmic value axis."
    if name in _INTERVAL_WORDS:
        if "error" in valid:
            return (
                "Use error= with (low, high) bounds or one half-width per item (or one "
                'number for all), plus error_label="95% CI".'
            )
        if "band" in valid:
            return (
                "Use band= with (low_values, high_values) or half-widths per series, plus "
                'band_label="95% CI"; raw replicates go in points=.'
            )
        return "Intervals are drawn by compare(error=...) and trend(band=...)."
    if name in _END_VALUE_WORDS and "end_values" in valid:
        return "Use end_values=False to keep the name at the line end but drop the value."
    if name in _ORDER_WORDS and "sort" not in valid:
        if kind == "share":
            return "share() always sorts parts largest first (part-of-whole reads by rank)."
        return f"{kind}() keeps the order you give: reorder the input (dicts keep insertion order)."
    if name in {"xlabel", "x_axis_label", "xaxis_label"} and "x_label" in valid:
        return "Use x_label=."
    if name in {"ylabel", "y_axis_label", "yaxis_label"}:
        if "y_label" in valid:
            return "Use y_label=."
        if "label" in valid:
            return 'Name the measure with label= and its unit with unit=, e.g. label="Yield", unit="%".'
    if name in {"units"} and "unit" in valid:
        return "Use unit= (singular)."
    if name in {"labels", "name", "names"} and kind in {"compare", "share"}:
        return "Did you mean label=? Item names are the keys of the values mapping; label= names the measure."
    return None


def _unknown_argument(kind: str, name: str, valid: Sequence[str]) -> ExplainError:
    hint = _specific_hint(kind, name, valid)
    if hint is None:
        elsewhere = [form for form, args in _FORM_ARGS.items() if form != kind and name in args]
        close = difflib.get_close_matches(name, valid, n=1, cutoff=0.6)
        if close:
            hint = f"Did you mean {close[0]}=?"
        elif elsewhere:
            hint = f"`{name}=` is an argument of {', '.join(f + '()' for f in elsewhere)}, not {kind}()."
        else:
            hint = f"{kind}() has no `{name}` argument."
    listed = ", ".join(valid)
    return ExplainError(
        f"{kind}() got an unexpected keyword argument {name!r}.",
        fix_hint=f"{hint} Valid arguments of {kind}(): {listed}.",
        rule="unknown_argument",
    )


def _guarded(kind: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Turn unknown or mis-passed arguments into an ExplainError naming the valid ones."""

    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        sig = inspect.signature(fn)
        valid = tuple(
            p.name
            for p in sig.parameters.values()
            if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        )
        positional = [
            p.name
            for p in sig.parameters.values()
            if p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD and p.default is p.empty
        ]
        _FORM_ARGS[kind] = valid

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for name in kwargs:
                if name not in valid:
                    raise _unknown_argument(kind, name, valid)
            try:
                sig.bind(*args, **kwargs)
            except TypeError as exc:
                shown = ", ".join(positional) or "..."
                raise ExplainError(
                    f"{kind}(): {exc}.",
                    fix_hint=f"Call it as fm.{kind}({shown}, keyword=...); every option after "
                    f"the data is a keyword. Valid arguments: {', '.join(valid)}.",
                    rule="unknown_argument",
                ) from exc
            return fn(*args, **kwargs)

        return wrapper

    return deco


_CURRENCY_UNITS = frozenset({"$", "\N{EURO SIGN}", "\N{POUND SIGN}", "\N{YEN SIGN}"})
_SUPERSCRIPT = str.maketrans("0123456789-+", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺")
#: Magnitudes at or above this are written in scientific notation (any unit).
_SCI_LARGE = 1e12
#: With a physical unit (not a currency) plain numbers stop here.
_SCI_LARGE_PHYSICAL = 1e6
#: A set whose magnitudes are all below this is written in scientific notation.
_SCI_SMALL = 1e-3
_FMT_HINT = (
    'Pass fmt as a format spec such as ".2f", ".1%" or ".3g", or as a template such as '
    '"{:.2f}" or "{:,.0f} ms".'
)


def _shows_zero(text: str) -> bool:
    """True when a formatted number has no non-zero digit (so it reads as zero)."""
    mantissa = text.split("\N{MULTIPLICATION SIGN}10", 1)[0]
    return not any(ch in "123456789" for ch in mantissa)


def _clean_sign(text: str) -> str:
    """Unicode minus, and never a signed zero ("−0.0" becomes "0.0")."""
    if _shows_zero(text):
        text = text.replace("-", "").replace("+", "").replace("\N{MINUS SIGN}", "")
    return text.replace("-", "\N{MINUS SIGN}")


def _sci_text(v: float, digits: int = 3, *, pad: bool = False) -> str:
    """``1.3×10⁻⁷``: real multiplication sign and Unicode superscripts, ``digits`` s.f.

    ``pad=True`` keeps trailing zeros ("1.20×10¹⁶") so every label of a set shows
    the same number of significant figures.
    """
    if v == 0 or not math.isfinite(v):
        return "0" if v == 0 else "\N{EN DASH}"
    mantissa, exponent = f"{v:.{max(0, digits - 1)}e}".split("e")
    if "." in mantissa and not pad:
        mantissa = mantissa.rstrip("0").rstrip(".")
    exp = int(exponent)
    if exp == 0:
        return _clean_sign(mantissa)
    return _clean_sign(f"{mantissa}\N{MULTIPLICATION SIGN}10{str(exp).translate(_SUPERSCRIPT)}")


def _sig_text(
    v: float, digits: int = 3, *, large: float = _SCI_LARGE, pad: bool = False
) -> str:
    """One value to its own ``digits`` significant figures (scientific when extreme;
    ``pad`` keeps a scientific mantissa's trailing zeros)."""
    if not math.isfinite(v):
        return "\N{EN DASH}"
    if v == 0:
        return "0"
    mag = abs(v)
    if mag < _SCI_SMALL or mag >= large:
        return _sci_text(v, digits, pad=pad)
    decimals = max(0, digits - 1 - math.floor(math.log10(mag)))
    text = f"{v:,.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return _clean_sign(text)


def _check_fmt(fmt: object) -> str | None:
    """Validate ``fmt=``: a format spec (".2f") or a template ("{:.2f}"); returns a template."""
    if fmt is None:
        return None
    if not isinstance(fmt, str) or not fmt.strip():
        raise ExplainError(
            f"fmt={fmt!r} cannot format a number (an empty fmt would blank every label and fact).",
            fix_hint=_FMT_HINT + " Omit fmt for automatic formatting.",
            rule="bad_fmt",
        )
    template = fmt if "{" in fmt else "{:" + fmt + "}"
    try:
        sample = template.format(1.2345)
        template.format(-12345.678)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
        raise ExplainError(
            f"fmt={fmt!r} is not a usable number format ({exc}).",
            fix_hint=_FMT_HINT,
            rule="bad_fmt",
        ) from exc
    if not any(ch.isdigit() for ch in sample):
        raise ExplainError(
            f"fmt={fmt!r} does not print the number.",
            fix_hint=_FMT_HINT,
            rule="bad_fmt",
        )
    return template


def _formatter(
    values: Sequence[float],
    fmt: str | None = None,
    *,
    unit: str | None = None,
    log: bool = False,
    suffix: bool | None = None,
) -> Callable[[float], str]:
    """Number formatter for one set of values. A non-zero value never reads as zero.

    * About three significant figures, with the same decimals across the set when
      it spans less than three orders of magnitude ("1,840", "0.74", "12.5").
    * Scientific notation ("1.3×10⁻⁷") when the largest magnitude is >= 1e12, when
      every magnitude is < 1e-3, or above 1e6 with a physical (non-currency) unit.
      "M"/"B" suffixes are kept only without a unit or with a currency.
    * Sets spanning >= 3 orders of magnitude, and log axes, give each value its
      own three significant figures. On a log axis (``log=True``), when any value
      needs scientific notation, every value uses it.
    * ``fmt`` (spec ".2f" or template "{:.2f}") overrides all of this, except that a
      non-zero value it would print as zero falls back to its own significant figures.
    """
    template = _check_fmt(fmt)
    allow_suffix = (unit is None or unit in _CURRENCY_UNITS) if suffix is None else suffix
    large = _SCI_LARGE if allow_suffix else _SCI_LARGE_PHYSICAL
    finite = [abs(float(v)) for v in values if math.isfinite(float(v))]
    mags = [v for v in finite if v > 0]
    top = max(mags, default=0.0)
    small = min(mags, default=0.0)

    if template is not None:

        def _custom(v: float) -> str:
            if not math.isfinite(v):
                return "\N{EN DASH}"
            text = template.format(v)
            if v != 0 and _shows_zero(text):
                return _sig_text(v, large=large)
            return _clean_sign(text)

        return _custom

    if not mags:
        return lambda v: "\N{EN DASH}" if not math.isfinite(v) else "0"

    # Scientific labels of one set show one number of significant figures (the most
    # any of them needs, at most 3): "1.20×10¹⁶" beside "3.89×10¹⁷", not "1.2×10¹⁶".
    def _sci_digits(shown: Sequence[float]) -> int:
        need = [
            len(re.sub(r"\D", "", _sci_text(v).split("\N{MULTIPLICATION SIGN}")[0]))
            for v in shown
            if v > 0
        ]
        return max(need, default=3)

    if log and (small < _SCI_SMALL or top >= large):
        # On a log axis one notation per set: "5.93×10⁻⁶" beside "0.00634" reads as
        # two kinds of number, so once any value needs scientific notation all use it.
        d_all = _sci_digits(mags)
        return lambda v: _sci_text(v, d_all, pad=True) if math.isfinite(v) else "\N{EN DASH}"
    if log or top / small >= 1e3:
        d_sci = _sci_digits([v for v in mags if v < _SCI_SMALL or v >= large])

        def _mixed(v: float) -> str:
            if math.isfinite(v) and v != 0 and (abs(v) < _SCI_SMALL or abs(v) >= large):
                return _sci_text(v, d_sci, pad=True)
            return _sig_text(v, large=large)

        return _mixed
    if top >= large or top < _SCI_SMALL:
        d_all = _sci_digits(mags)
        return lambda v: _sci_text(v, d_all, pad=True) if math.isfinite(v) else "\N{EN DASH}"

    if allow_suffix and top >= 1e9:
        scale, suffix_text = 1e9, "B"
    elif allow_suffix and top >= 1e6:
        scale, suffix_text = 1e6, "M"
    else:
        scale, suffix_text = 1.0, ""
    scaled = [v / scale for v in finite]
    top_s = top / scale
    if top_s >= 100 or all(abs(v - round(v)) < 1e-9 for v in scaled):
        decimals = 0
    elif top_s >= 10:
        decimals = 1
    elif top_s >= 1:
        decimals = 2
    else:
        decimals = max(2, 2 - math.floor(math.log10(top_s)))
    while decimals > 0 and all(
        abs(round(v, decimals - 1) - v) < 0.5 * 10 ** (-decimals - 2) for v in scaled
    ):
        decimals -= 1

    def _format(v: float) -> str:
        if not math.isfinite(v):
            return "\N{EN DASH}"
        text = f"{v / scale:,.{decimals}f}"
        if v != 0 and _shows_zero(text):
            return _sig_text(v, large=large)
        return _clean_sign(text) + suffix_text

    return _format


def _tick_text(v: float, minus: str = "\N{MINUS SIGN}", axis: Any = None) -> str:
    """Axis tick label: plain ``,.10g`` for ordinary numbers, scientific when extreme."""
    if axis is not None and v != 0 and axis.get_scale() == "linear":
        lo, hi = axis.get_view_interval()
        if abs(v) < 1e-9 * abs(hi - lo):
            v = 0.0  # floating-point noise of a tick at zero
    if v != 0 and math.isfinite(v) and (abs(v) < _SCI_SMALL or abs(v) >= _SCI_LARGE):
        return _sci_text(v).replace("\N{MINUS SIGN}", minus)
    return f"{v:,.10g}".replace("-", minus)


def _tick_label(v: float, minus: str = "\N{MINUS SIGN}", axis: Any = None) -> str:
    """What a tick shows: :func:`_tick_text` with the style's glyphs ("1.3x10^-7" in ASCII
    styles) and super/subscripts drawn in the body font."""
    ascii_only = minus != "\N{MINUS SIGN}"
    text = _tick_text(v, "\N{MINUS SIGN}", axis)
    if ascii_only:
        text = _ascii_sci(text).replace("\N{MINUS SIGN}", minus)
    return _glyphs(text, ascii_only=ascii_only)


def _narrow_log_ticks(
    axis: Any,
    lo: float,
    hi: float,
    minus: str = "\N{MINUS SIGN}",
    *,
    max_ticks: int = 6,
    extend: bool = True,
    data_hi: float | None = None,
) -> tuple[float, float]:
    """Ticks and labels for a log axis; returns the (possibly widened) limits to set.

    * Under ~1.5 decades: 1-2-5 ticks (a decade locator would show one label).
    * Otherwise decades, thinned to at most ``max_ticks`` counting down from the top,
      so the largest values always sit under or just above a labelled tick; when the
      data reach more than half a decade past the top labelled decade (and ``extend``),
      the axis grows to the next decade and labels it.
    * ``data_hi`` (the largest observation) marks a value axis: it then always gets
      at least two labelled ticks and one at or above ``data_hi``, widening the
      returned limits as needed.
    * Labels are text in the body font: plain numbers between 0.01 and 10,000,
      otherwise "10⁻⁸" (super/subscripts drawn as one run; "10^-8" in ASCII styles).
    """
    ascii_only = minus != "\N{MINUS SIGN}"
    lo = lo if lo > 0 else hi / 10.0
    if hi / lo < 10**1.5 and data_hi is not None:
        k0, k1 = math.floor(math.log10(lo)) - 1, math.ceil(math.log10(hi)) + 1
        cands = [m * 10.0**k for k in range(k0, k1 + 1) for m in (1.0, 2.0, 5.0)]
        top_tick = min(c for c in cands if c >= data_hi * (1 - 1e-9))
        hi = max(hi, top_tick)
        ticks = [c for c in cands if lo * (1 - 1e-9) <= c <= hi * (1 + 1e-9)]
        if len(ticks) < 2:
            below = max(c for c in cands if c < ticks[0])
            lo = min(lo, below)
            ticks = [below, *ticks]
        axis.set_major_locator(FixedLocator(ticks))
    elif hi / lo < 10**1.5:
        axis.set_major_locator(LogLocator(base=10.0, subs=(1.0, 2.0, 5.0)))
    else:
        bottom = math.ceil(math.log10(lo) - 1e-9)
        top = math.floor(math.log10(hi) + 1e-9)
        if data_hi is not None and 10.0**top < data_hi * (1 - 1e-9):
            top = math.ceil(math.log10(data_hi) - 1e-9)
            hi = max(hi, 10.0**top)
        elif extend and math.log10(hi) - top > 0.5:
            top += 1
            hi = 10.0**top
        count = top - bottom + 1
        stride = max(1, math.ceil(count / max(2, max_ticks)))
        decades = list(range(top, bottom - 1, -stride))[::-1]
        axis.set_major_locator(FixedLocator([10.0**d for d in decades]))
    plain = lo >= 0.0099 and hi <= 10_001

    def _label(v: float, _p: Any) -> str:
        if v <= 0 or not math.isfinite(v):
            return ""
        exp = math.log10(v)
        if not plain and abs(exp - round(exp)) < 1e-9:
            power = str(round(exp))
            text = f"10^{power}" if ascii_only else "10" + power.translate(_SUPERSCRIPT)
            return _glyphs(text, ascii_only=ascii_only)
        return _tick_label(v, minus)

    axis.set_major_formatter(FuncFormatter(_label))
    axis.set_minor_formatter(NullFormatter())
    # No minor ticks on chat-figure log axes. Matplotlib's default decides from the
    # axis length, so two side-by-side panels a few points apart in width would
    # differ (one with 2..9 ticks, one without); the labelled decades say "log".
    axis.set_minor_locator(NullLocator())
    return lo, hi


def _ratio_text(ratio: float) -> str:
    """A ratio to 3 significant figures: 4.0×, 62×, 1,200×, 63,900× (from unrounded values)."""
    if ratio >= 1000 and ratio < _SCI_LARGE:
        rounded = round(ratio, 2 - math.floor(math.log10(ratio)))
        return f"{rounded:,.0f}\N{MULTIPLICATION SIGN}"
    if ratio >= 100:
        return f"{_sig_text(ratio)}\N{MULTIPLICATION SIGN}"
    if ratio >= 10:
        return f"{ratio:.0f}\N{MULTIPLICATION SIGN}"
    if 0 < ratio < 1:  # "0.72×": a fraction keeps two significant figures
        decimals = 1 - math.floor(math.log10(ratio))
        return f"{ratio:.{decimals}f}\N{MULTIPLICATION SIGN}"
    return f"{ratio:.1f}\N{MULTIPLICATION SIGN}"


def _with_unit(text: str, unit: str | None) -> str:
    if not unit:
        return text
    if unit in {"$", "\N{EURO SIGN}", "\N{POUND SIGN}"}:
        if text.startswith("\N{MINUS SIGN}"):
            return f"\N{MINUS SIGN}{unit}{text[1:]}"
        return f"{unit}{text}"
    if unit in {"%", "\N{MULTIPLICATION SIGN}", "x", "\N{DEGREE SIGN}"} or unit.startswith("%"):
        return f"{text}{unit}"
    return f"{text} {unit}"


def _inline_unit(unit: str | None) -> bool:
    """Short units that belong on every value label, not just the first."""
    return unit in {"%", "$", "\N{EURO SIGN}", "\N{POUND SIGN}", "\N{MULTIPLICATION SIGN}", "x"}


def _measure_text(label: str | None, unit: str | None) -> str | None:
    if label and unit:
        return f"{label} ({unit})"
    return label or unit or None


def _relative_luminance(color: str) -> float:
    return relative_luminance(color)


def _contrast_on_white(color: str) -> float:
    return contrast_ratio(color, "#FFFFFF")


def _text_color(
    color: str,
    *,
    minimum: float = 4.5,
    background: str = "#FFFFFF",
    ink: str = INK,
) -> str:
    """Darken a series colour toward ink until it is legible as small text on ``background``."""
    rgb = np.array(to_rgb(color))
    ink_rgb = np.array(to_rgb(ink))
    for mix in (0.0, 0.15, 0.3, 0.45, 0.6, 0.8, 1.0):
        blended = rgb * (1 - mix) + ink_rgb * mix
        candidate = "#{:02X}{:02X}{:02X}".format(*(round(c * 255) for c in blended))
        if contrast_ratio(candidate, background) >= minimum:
            return candidate
    return ink


def _percent_change(first: float, last: float) -> str | None:
    if first == 0 or not math.isfinite(first) or not math.isfinite(last):
        return None
    pct = (last - first) / abs(first) * 100.0
    sign = "+" if pct >= 0 else "\N{MINUS SIGN}"
    return f"{sign}{abs(pct):.0f}%"


def _signed(text: str) -> str:
    """Prefix "+" to a formatted non-negative, non-zero difference."""
    if text.startswith("\N{MINUS SIGN}") or _shows_zero(text):
        return text
    return "+" + text


def _diff_with_unit(text: str, unit: str | None) -> str:
    """A difference: in points when the unit is "%" (a percent of a percent misleads)."""
    if unit is not None and unit.strip().startswith("%"):
        bare = text.lstrip("+\N{MINUS SIGN}")
        return f"{text} {'point' if bare == '1' else 'points'}"
    return _with_unit(text, unit)


def _change_text(
    first: float,
    last: float,
    *,
    series_range: float,
    unit: str | None,
    diff_fmt: Callable[[float], str],
    log: bool = False,
) -> str | None:
    """How a series moved, in the terms that are meaningful for it.

    * Log axis: fold change ("rises 2.3-fold", "falls 3.9 decades").
    * Unit "%": the difference in points ("+94 points"), never a percent of a percent.
    * Otherwise a percent change, omitted when the baseline is within ~5% of the
      series' range from zero or the sign changes (both make the percent meaningless).
    """
    if not (math.isfinite(first) and math.isfinite(last)):
        return None
    if log:
        if first <= 0 or last <= 0:
            return None
        decades = math.log10(last / first)
        word = "rises" if decades > 0 else "falls"
        if abs(decades) >= 1:
            return f"{word} {abs(decades):.1f} decades"
        fold = 10 ** abs(decades)
        if fold < 1.005:
            return "unchanged"
        return f"{word} {fold:.2g}-fold" if fold < 10 else f"{word} {fold:.0f}-fold"
    if unit is not None and unit.strip().startswith("%"):
        return _diff_with_unit(_signed(diff_fmt(last - first)), unit)
    if first == 0 or (first < 0 < last) or (last < 0 < first):
        return None
    if abs(first) <= 0.05 * series_range:
        return None
    return _percent_change(first, last)


# --------------------------------------------------------------------------- #
# Typography and drawing context
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _Sizes:
    """Type scale derived from the target spec (points)."""

    scale: float
    title: float
    body: float
    small: float
    foot: float

    @classmethod
    def from_spec(cls, spec: JournalSpec, theme: Theme = FIGMINT_THEME) -> _Sizes:
        return cls(
            scale=spec.body_pt / 8.5,
            title=min(spec.font_max_pt, round(spec.body_pt * theme.title_scale)),
            body=spec.body_pt,
            small=spec.tick_pt,
            foot=max(spec.font_min_pt, spec.tick_pt - 0.5),
        )


class _Measure:
    """Measure and wrap text with the active rcParams font.

    Measured at 720 dpi and scaled back to points: small pixel sizes hit
    embedded bitmap strikes in some system fonts (Helvetica.ttc), which FreeType
    cannot load.
    """

    _DPI = 720

    def __init__(self, theme: Theme | None = None) -> None:
        self._renderer = FigureCanvasAgg(Figure(figsize=(1, 1), dpi=self._DPI)).get_renderer()
        self.theme = theme

    def width_pt(
        self,
        text: str,
        size: float,
        weight: str = "normal",
        family: Sequence[str] | str | None = None,
    ) -> float:
        if not text:
            return 0.0
        if family is None:
            prop = FontProperties(size=size, weight=weight)
        else:
            fam = list(family) if not isinstance(family, str) else family
            prop = FontProperties(family=fam, size=size, weight=weight)
        # Measure exactly what is drawn: the same symbol normalisation and, for
        # super/subscript runs, the same mathtext layout.
        from matplotlib import cbook

        shown = _plain(text, self.theme)
        ismath = bool(cbook.is_math_text(shown))
        if not ismath:
            shown = shown.replace(r"\$", "$")
        width, _, _ = self._renderer.get_text_width_height_descent(shown, prop, ismath=ismath)
        return float(width) * 72.0 / self._DPI

    def wrap(
        self,
        text: str,
        max_pt: float,
        size: float,
        weight: str = "normal",
        family: Sequence[str] | str | None = None,
    ) -> list[str]:
        lines: list[str] = []
        for paragraph in str(text).splitlines() or [""]:
            current = ""
            for word in paragraph.split():
                trial = f"{current} {word}".strip()
                if current and self.width_pt(trial, size, weight, family) > max_pt:
                    lines.append(current)
                    current = word
                else:
                    current = trial
            lines.append(current)
        return lines


@dataclass
class _Ctx:
    """What a panel needs while drawing."""

    fig: Figure
    sizes: _Sizes
    key: str
    cell_width_mm: float
    measure: _Measure
    theme: Theme = FIGMINT_THEME
    measure_label: str | None = None
    extra_axes: list[Axes] = field(default_factory=list)
    finishers: list[Callable[[], None]] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)
    #: Figure-level colour of each name this panel colours (from ``_colour_registry``).
    colors: dict[str, str] = field(default_factory=dict)
    #: Colour of a panel that colours its items uniformly (None: the theme default).
    uniform_color: str | None = None

    @property
    def default_color(self) -> str:
        return self.uniform_color or self.theme.default_color

    @property
    def pt_per_px(self) -> float:
        return 72.0 / float(self.fig.dpi)

    def tag(self, ax: Axes) -> Axes:
        ax._figmint_panel_key = self.key  # type: ignore[attr-defined]
        ax._figmint_measure_label = self.measure_label  # type: ignore[attr-defined]
        return ax

    def text_color(self, color: str, *, minimum: float = 4.5) -> str:
        return _text_color(
            color,
            minimum=minimum,
            background=self.theme.background,
            ink=self.theme.ink,
        )

    def halo_bbox(self, pad: float = 0.1, alpha: float | None = None) -> dict[str, Any]:
        return {
            "boxstyle": f"square,pad={pad}",
            "facecolor": self.theme.background,
            "edgecolor": "none",
            "alpha": self.theme.halo_alpha if alpha is None else alpha,
        }

    def line_effects(self) -> list[Any] | None:
        if self.theme.stroke_outline_pt <= 0.0:
            return None
        return [
            patheffects.withStroke(
                linewidth=self.theme.stroke_outline_pt * self.sizes.scale,
                foreground=self.theme.background,
            )
        ]


@dataclass
class Panel:
    """One piece of evidence: a form chosen by the question it answers."""

    kind: str
    title: str | None
    label: str | None
    unit: str | None
    spec: dict[str, Any]
    facts: list[str]
    describe: str
    _height_mm: Callable[[float, _Measure, _Sizes, Theme], float]
    _draw: Callable[[_Ctx, Axes], Callable[[], None] | None]
    issues: list[dict[str, Any]] = field(default_factory=list)
    _frames: Callable[[_Ctx, Axes, Bbox], list[tuple[Axes, Bbox]]] | None = None
    #: Line and scatter panels grow to fill their row; bar-like panels keep their pitch.
    stretch: bool = False
    #: Appended to the measure line under the headline (what an interval means, log scale).
    measure_note: str | None = None
    #: Colour identity (see ``_colour_registry``): every name this panel could colour,
    #: the names it emphasises (highlighted, or coloured by default such as trend series),
    #: and how it colours: "highlight", "series", "uniform" (one default colour) or "none".
    color_items: tuple[str, ...] = ()
    color_focus: tuple[str, ...] = ()
    color_mode: str = "none"
    #: True when, with no figure entity among its items, the panel draws in the default colour.
    uses_default: bool = False

    def to_spec(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind}
        out.update({k: _jsonable(v) for k, v in self.spec.items() if v is not None})
        return out


def _jsonable(value: Any) -> Any:
    """Plain JSON types for a spec: numpy, pandas-like, dates, tuples, NaN -> None."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (numbers.Integral, np.integer)):
        return int(value)  # type: ignore[arg-type]
    if _is_number(value):
        number = float(value)  # type: ignore[arg-type]
        return number if math.isfinite(number) else None
    if isinstance(value, datetime):
        if value.tzinfo is not None:  # the spec's ISO dates are naive UTC (as drawn)
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        text = value.isoformat()
        return text[:10] if text[10:] in ("T00:00:00", "") else text
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, np.datetime64):
        return str(np.datetime64(value, "s")).replace("T00:00:00", "")
    if _has_items(value):
        return {str(k): _jsonable(v) for k, v in _pairs(value)}
    if isinstance(value, np.ndarray):
        return [_jsonable(v) for v in value.tolist()]
    if isinstance(value, (list, tuple)) or (
        isinstance(value, Sequence) and not isinstance(value, (str, bytes))
    ):
        return [_jsonable(v) for v in value]
    if hasattr(value, "tolist"):
        return _jsonable(value.tolist())
    return str(value)


def _base_spec(
    title: str | None, label: str | None, unit: str | None, **extra: Any
) -> dict[str, Any]:
    spec: dict[str, Any] = dict(extra)
    spec.update({"title": title, "label": label, "unit": unit})
    return spec


def _bare_axes(ax: Axes) -> None:
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_facecolor("none")


def _value_axis(
    ax: Axes,
    sizes: _Sizes,
    theme: Theme = FIGMINT_THEME,
    *,
    axis: str = "y",
    nbins: int = 4,
) -> None:
    """Quiet quantitative axis: themed gridlines, spines, and thousands-separated labels."""
    other = "x" if axis == "y" else "y"
    if theme.hide_spines:
        for spine in ax.spines.values():
            spine.set_visible(False)
    else:
        for name in ("top", "right", "left" if axis == "y" else "bottom"):
            ax.spines[name].set_visible(False)
        base = ax.spines["bottom" if axis == "y" else "left"]
        base.set_color(theme.axis)
        base.set_linewidth(theme.axis_lw)
    ax.tick_params(axis=axis, length=0, labelsize=sizes.small, labelcolor=theme.muted, pad=3)
    ax.tick_params(
        axis=other,
        length=theme.tick_length,
        width=theme.tick_width,
        color=theme.axis,
        labelsize=sizes.small,
        labelcolor=theme.muted,
    )
    if theme.grid_style != "none" and theme.grid_lw > 0:
        grid_axis = "both" if theme.grid_both_axes else axis
        ax.grid(
            axis=grid_axis,
            color=theme.grid,
            linestyle=theme.grid_style,
            linewidth=theme.grid_lw,
        )
    else:
        ax.grid(False)
    ax.set_axisbelow(True)
    target = ax.yaxis if axis == "y" else ax.xaxis
    minus = theme.minus_sign
    if target.get_scale() == "linear":
        target.set_major_locator(MaxNLocator(nbins=nbins, steps=[1, 2, 2.5, 5, 10]))
        target.set_major_formatter(
            FuncFormatter(lambda v, _pos, m=minus, a=target: _tick_label(v, m, a))
        )


def _apply_inline_y_ticks(
    ax: Axes,
    sizes: _Sizes,
    theme: Theme,
    *,
    unit: str | None = None,
) -> None:
    """Editorial-style inline y-tick labels sitting directly above each horizontal gridline.

    Hides the left-gutter y-tick labels, ensures headroom above the highest tick,
    and prints the unit on the topmost tick only.
    """
    y0, y1 = ax.get_ylim()
    span = (y1 - y0) or 1.0
    ticks = [float(t) for t in ax.yaxis.get_majorticklocs() if y0 + 0.01 * span <= t <= y1]
    if not ticks:
        return
    # Ensure room above the highest gridline so its inline label stays inside the axes.
    top_tick = ticks[-1]
    if y1 - top_tick < 0.14 * span:
        ax.set_ylim(y0, top_tick + 0.16 * span)
        y0, y1 = ax.get_ylim()
        span = (y1 - y0) or 1.0
        ticks = [float(t) for t in ax.yaxis.get_majorticklocs() if y0 + 0.01 * span <= t <= y1]
        if not ticks:
            return
    ax.tick_params(axis="y", labelleft=False)
    minus = theme.minus_sign
    inline: list[tuple[Any, bool]] = []
    ax._figmint_inline_ticks = inline  # type: ignore[attr-defined]
    for idx, tick in enumerate(ticks):
        raw = _tick_text(tick, minus, ax.yaxis)
        top = idx == len(ticks) - 1
        text = _with_unit(raw, unit) if (top and unit) else raw
        note = ax.annotate(
            _plain(text, theme),
            (0.0, tick),
            xycoords=("axes fraction", "data"),
            xytext=(0.0, 2.0),
            textcoords="offset points",
            ha="left",
            va="bottom",
            fontsize=sizes.small,
            color=theme.muted,
            zorder=3,
            bbox={
                "boxstyle": "square,pad=0.05",
                "facecolor": theme.background,
                "edgecolor": "none",
                "alpha": theme.halo_alpha,
            },
        )
        inline.append((note, top and bool(unit)))


def _clear_inline_ticks(ctx: _Ctx, ax: Axes) -> None:
    """Keep inline y-tick labels off the data lines (runs after layout).

    A label a data line passes through is dropped (its gridline still marks the
    value, and the labels above and below give the scale). The top label carries
    the unit, so it is kept and lifted above the lines on its halo instead.
    """
    inline = getattr(ax, "_figmint_inline_ticks", None)
    if not inline:
        return
    renderer = ctx.fig.canvas.get_renderer()
    # Horizontal rules (reference, zero line) sit on a tick by design: not data.
    paths = [
        path
        for path in _data_paths(ax, [])
        if len(path.vertices) and np.ptp(path.vertices[:, 1]) > 0.5
    ]
    for note, carries_unit in inline:
        if not note.get_visible():
            continue
        box = note.get_window_extent(renderer)
        if any(path.intersects_bbox(box, filled=False) for path in paths):
            if carries_unit:
                note.set_zorder(6)
            else:
                note.set_visible(False)


def _keep_inside_x(ctx: _Ctx, ax: Axes, note: Any) -> None:
    """Re-anchor a label centred on a data x so it stays within the axes' width.

    A centred label near the right edge would run into text drawn beside the axes
    (the "median" column header of distribution()).
    """
    renderer = ctx.fig.canvas.get_renderer()
    box = note.get_window_extent(renderer)
    frame = ax.get_window_extent(renderer)
    if box.x1 > frame.x1:
        note.set_horizontalalignment("right")
        note.set_position((-2.0, note.xyann[1]))
    elif box.x0 < frame.x0:
        note.set_horizontalalignment("left")
        note.set_position((2.0, note.xyann[1]))


def _reference_line(reference: object, what: str) -> tuple[float, str] | None:
    if reference is None:
        return None
    if _is_number(reference):
        return float(reference), ""  # type: ignore[arg-type]
    try:
        value, text = reference  # type: ignore[misc]
    except (TypeError, ValueError) as exc:
        raise ExplainError(
            f"{what} must be a number or a (value, label) pair.",
            fix_hint='Use reference=(300, "target") or reference=300.',
        ) from exc
    return _to_float(value, what), str(text)


# --------------------------------------------------------------------------- #
# compare / share
# --------------------------------------------------------------------------- #


def _bar_panel(
    *,
    kind: str,
    names: list[str],
    values: list[float],
    highlight: list[str],
    labels: list[str],
    title: str | None,
    label: str | None,
    unit: str | None,
    spec: dict[str, Any],
    facts: list[str],
    describe: str,
    dots: bool,
    errors: dict[str, tuple[float, float]] | None,
    reference: tuple[float, str] | None,
    muted_names: Sequence[str] = (),
    issues: list[dict[str, Any]] | None = None,
    log: bool = False,
    measure_note: str | None = None,
) -> Panel:
    n = len(names)
    hl_index = {name: i for i, name in enumerate(highlight)}

    def _wrapped(
        cell_width_mm: float,
        measure: _Measure,
        sizes: _Sizes,
        theme: Theme = FIGMINT_THEME,
    ) -> list[str]:
        """Item names wrapped to two lines so long names never squeeze the bars."""
        cell_pt = cell_width_mm * sizes.scale / PT_TO_MM
        ell = theme.ellipsis
        out: list[str] = []
        for name in names:
            weight = "bold" if name in hl_index else "normal"
            lines = measure.wrap(name, 0.42 * cell_pt, sizes.body, weight)
            if len(lines) > 2:
                lines = [lines[0], " ".join(lines[1:])]
            fitted: list[str] = []
            for line in lines:
                min_len = max(4, len(ell) + 2)
                while (
                    len(line) > min_len
                    and measure.width_pt(line, sizes.body, weight) > 0.5 * cell_pt
                ):
                    if len(ell) == 1:
                        line = line[:-2].rstrip() + ell
                    else:
                        base = line.removesuffix(ell)
                        line = base[:-1].rstrip() + ell
                fitted.append(line)
            out.append("\n".join(fitted))
        return out

    def _truncated(shown: list[str], theme: Theme = FIGMINT_THEME) -> list[str]:
        ell = theme.ellipsis
        return [
            name
            for name, text in zip(names, shown, strict=True)
            if text.endswith(ell) and not name.endswith(ell)
        ]

    def _pitch(wrapped: list[str]) -> float:
        return 8.2 if any("\n" in name for name in wrapped) else 5.3

    def _draw(ctx: _Ctx, ax: Axes) -> None:
        sz = ctx.sizes
        theme = ctx.theme
        # Figure-level colours: highlighted names, or (without highlight) names that are
        # coloured elsewhere in the figure; every other item is context grey.
        accent = {name: col for name, col in ctx.colors.items() if name in names}

        def _color(name: str) -> str:
            if highlight or accent:
                return accent.get(name, theme.context_fill)
            return theme.context_fill if name in muted_names else ctx.default_color

        y = np.arange(n, dtype=float)
        vals = np.asarray(values, dtype=float)
        colors = [_color(name) for name in names]
        lows = np.array([errors[nm][0] if errors else v for nm, v in zip(names, vals, strict=True)])
        highs = np.array(
            [errors[nm][1] if errors else v for nm, v in zip(names, vals, strict=True)]
        )
        _bare_axes(ax)
        ax.set_ylim(n - 0.5, -0.5)

        if dots:
            lo = float(min(lows.min(), reference[0] if reference else np.inf))
            hi = float(max(highs.max(), reference[0] if reference else -np.inf))
            if log:
                ax.set_xscale("log")
                pad = max((hi / lo) ** 0.05, 1.15)
                ax.set_xlim(
                    *_narrow_log_ticks(
                        ax.xaxis, lo / pad, hi * pad, theme.minus_sign, extend=False, data_hi=hi
                    )
                )
            else:
                if not errors and lo >= 0 and (hi - lo) > 0.6 * hi:
                    lo = 0.0  # the spread already covers most of the way to zero
                span = (hi - lo) or abs(hi) or 1.0
                ax.set_xlim(lo - 0.05 * span, hi + 0.03 * span)
            left = ax.get_xlim()[0]
            stem_color = theme.grid if theme.grid_style != "none" else theme.context_fill
            dot_colors = [c if c != theme.context_fill else theme.axis for c in colors]
            if errors:
                # Thin whiskers with small end caps: the caps stay visible beside the dot,
                # and the value axis below lets the reader measure each interval.
                ax.hlines(y, lows, highs, color=dot_colors, linewidth=0.9 * sz.scale, zorder=2)
                for ends in (lows, highs):
                    ax.vlines(
                        ends,
                        y - 0.16,
                        y + 0.16,
                        color=dot_colors,
                        linewidth=0.9 * sz.scale,
                        zorder=2,
                    )
            else:
                ax.hlines(y, left, vals, color=stem_color, linewidth=0.7, zorder=1)
            ax.scatter(
                vals,
                y,
                s=(5.2 * sz.scale) ** 2,
                color=dot_colors,
                edgecolor=theme.background,
                linewidth=0.6,
                zorder=3,
            )
        else:
            lo = float(min(0.0, vals.min(), reference[0] if reference else 0.0))
            hi = float(max(0.0, vals.max(), reference[0] if reference else 0.0))
            if hi == lo:
                hi = lo + 1.0
            ax.set_xlim(lo, hi)
            bar_kw: dict[str, Any] = {
                "height": theme.bar_height,
                "color": colors,
                "linewidth": theme.bar_edge_lw,
                "zorder": 2,
            }
            if theme.bar_edgecolor is not None and theme.bar_edge_lw > 0:
                bar_kw["edgecolor"] = theme.bar_edgecolor
            ax.barh(y, vals, **bar_kw)
            ax.axvline(0.0, color=theme.zero_line, linewidth=theme.zero_line_lw, zorder=3)

        if log:
            # A log scale must be visible: the reader cannot infer it from the dots.
            ax.tick_params(
                axis="x",
                length=theme.tick_length,
                width=theme.tick_width,
                color=theme.axis,
                labelsize=sz.small,
                labelcolor=theme.muted,
            )
            ax.spines["bottom"].set_visible(True)
            ax.spines["bottom"].set_color(theme.axis)
            ax.spines["bottom"].set_linewidth(theme.axis_lw)
        elif errors:
            # Intervals need a scale to be read: a light value axis like trend's.
            minus = theme.minus_sign
            ax.xaxis.set_major_locator(MaxNLocator(nbins=4, steps=[1, 2, 2.5, 5, 10]))
            ax.xaxis.set_major_formatter(
                FuncFormatter(lambda v, _p, m=minus, a=ax.xaxis: _tick_label(v, m, a))
            )
            ax.tick_params(axis="x", length=0, labelsize=sz.small, labelcolor=theme.muted, pad=3)
            if theme.grid_style != "none" and theme.grid_lw > 0:
                ax.grid(
                    axis="x", color=theme.grid, linestyle=theme.grid_style, linewidth=theme.grid_lw
                )
            ax.set_axisbelow(True)
            cover = (float(lows.min()), float(highs.max()))
            if reference is not None:
                cover = (min(cover[0], reference[0]), max(cover[1], reference[0]))
            ax._figmint_cover = cover  # type: ignore[attr-defined]
            _cover_with_ticks(ax.xaxis, *cover)
        else:
            ax.xaxis.set_visible(False)
        shown_names = _wrapped(ctx.cell_width_mm, ctx.measure, sz, theme)
        cut = _truncated(shown_names, theme)
        if cut:
            ctx.issues.append(
                _issue(
                    "names_truncated",
                    "warning",
                    f"{len(cut)} item name(s) were cut to fit: {', '.join(map(repr, cut[:3]))}.",
                    "Shorten the names, or give this panel a full-width row with "
                    'layout=[["a"], ["b"]].',
                    panel=ctx.key,
                )
            )
        ax.set_yticks(y, [_plain(nm, theme) for nm in shown_names])
        ax.tick_params(axis="y", length=0, labelsize=sz.body, labelcolor=theme.ink, pad=5)
        for tick, name in zip(ax.get_yticklabels(), names, strict=True):
            tick.set_linespacing(1.05)
            if name in accent:
                tick.set_fontweight("bold")
            elif name in muted_names:
                tick.set_color(theme.muted)

        for yi, name, value, hi_v, text in zip(y, names, vals, highs, labels, strict=True):
            anchor = hi_v if (dots or value >= 0) else 0.0
            ax.annotate(
                _plain(text, theme),
                (anchor, yi),
                xytext=(5.0 if (dots or value >= 0) else 4.0, 0.0),
                textcoords="offset points",
                ha="left",
                va="center",
                fontsize=sz.small,
                color=theme.muted if name in muted_names else theme.ink,
                fontweight="bold" if name in accent else "normal",
                annotation_clip=False,
            )

        if reference is not None:
            ref_value, ref_text = reference
            ax.axvline(
                ref_value,
                color=theme.ink,
                linewidth=0.7,
                linestyle=(0, (3, 2)),
                zorder=4,
            )
            if ref_text:
                ax.annotate(
                    _plain(ref_text, theme),
                    (ref_value, 1.0),
                    xycoords=("data", "axes fraction"),
                    xytext=(0.0, 2.5),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=sz.small,
                    color=theme.muted,
                    annotation_clip=False,
                )

    return Panel(
        kind=kind,
        title=title,
        label=label,
        unit=unit,
        spec=spec,
        facts=facts,
        describe=describe,
        issues=list(issues or []),
        _height_mm=lambda w, measure, sizes, theme: (
            max(14.0, _pitch(_wrapped(w, measure, sizes, theme)) * n + 1.0)
            + (4.0 if reference and reference[1] else 0.0)
            + (5.0 if (log or errors) else 0.0)
        ),
        _draw=_draw,
        measure_note=measure_note,
        color_items=tuple(nm for nm in names if nm not in muted_names),
        color_focus=tuple(highlight),
        color_mode="highlight" if highlight else "uniform",
        uses_default=not highlight,
    )


def _sort_order(sort: object) -> str:
    """``True``/"desc" -> "desc", "asc" -> "asc", ``False``/None -> "given"."""
    if sort is True or (isinstance(sort, str) and sort.lower() in {"desc", "descending"}):
        return "desc"
    if isinstance(sort, str) and sort.lower() in {"asc", "ascending"}:
        return "asc"
    if sort is False or sort is None or (isinstance(sort, str) and sort.lower() == "none"):
        return "given"
    raise ExplainError(
        f"compare(sort={sort!r}) is not a sort order.",
        fix_hint='Use sort=True or "desc" (largest first), "asc" (smallest first, for '
        "lower-is-better measures such as loss or IC50), or False (keep the order given).",
    )


_INTERVAL_MODES = {
    "bounds": "absolute bounds (low, high)",
    "halfwidth": "\N{PLUS-MINUS SIGN} half-widths",
}


def _interval_mode_text(modes: set[str], what: str) -> str:
    if len(modes) == 1:
        return f"{what} read as {_INTERVAL_MODES[next(iter(modes))]}"
    return f"{what} read as absolute bounds (low, high) for some items, \N{PLUS-MINUS SIGN} half-widths for others"


def _halfwidth(value: object, what: str) -> float:
    hw = _to_float(value, what)
    if not math.isfinite(hw) or hw < 0:
        raise ExplainError(
            f"{what} = {value!r} is not a usable half-width.",
            fix_hint="A half-width is one non-negative number (the \N{PLUS-MINUS SIGN} value).",
        )
    return hw


def _compare_intervals(
    error: object, data: dict[str, float]
) -> tuple[dict[str, tuple[float, float]], set[str]]:
    """Read ``compare(error=...)``: per item (low, high) or a half-width, or one number for all."""
    names = list(data)
    hint = (
        "Give each item either (low, high) absolute bounds or one number meaning \N{PLUS-MINUS SIGN} "
        'that much, e.g. error={"a": (2.8, 3.2), "b": 0.3}, or error=0.2 for every item.'
    )
    if _is_number(error):
        hw = _halfwidth(error, "compare(error)")
        return {nm: (data[nm] - hw, data[nm] + hw) for nm in names}, {"halfwidth"}
    if _has_items(error):
        entries = {str(k): v for k, v in _pairs(error)}
    elif isinstance(error, (Sequence, np.ndarray)) and not isinstance(error, (str, bytes)):
        listed = list(error)
        if len(listed) != len(names):
            raise ExplainError(
                f"compare(error) lists {len(listed)} intervals for {len(names)} items.",
                fix_hint=hint + " A list must follow the order of values.",
            )
        entries = dict(zip(names, listed, strict=True))
    else:
        raise ExplainError(
            f"compare(error) must be a mapping, a list or one number, got {type(error).__name__}.",
            fix_hint=hint,
        )
    extra = [k for k in entries if k not in data]
    if extra:
        raise ExplainError(
            f"compare(error) names {extra[:4]!r}, which are not in values.",
            fix_hint=f"Use names from: {', '.join(map(repr, names[:12]))}.",
        )
    errors: dict[str, tuple[float, float]] = {}
    modes: set[str] = set()
    for name in names:
        if name not in entries:
            raise ExplainError(
                f"compare(error) has no entry for {name!r}.",
                fix_hint=hint + " Every item needs one, or omit `error`.",
            )
        entry = entries[name]
        if _is_number(entry):
            hw = _halfwidth(entry, f"compare(error[{name!r}])")
            errors[name] = (data[name] - hw, data[name] + hw)
            modes.add("halfwidth")
            continue
        try:
            pair = [v for v in entry]  # type: ignore[union-attr]
        except TypeError as exc:
            raise ExplainError(
                f"compare(error[{name!r}]) = {entry!r} is neither (low, high) nor a number.",
                fix_hint=hint,
            ) from exc
        if len(pair) != 2:
            raise ExplainError(
                f"compare(error[{name!r}]) has {len(pair)} numbers; an interval has two.",
                fix_hint=hint,
            )
        low, high = (_to_float(v, f"compare(error[{name!r}])") for v in pair)
        if not (math.isfinite(low) and math.isfinite(high)):
            raise ExplainError(
                f"compare(error[{name!r}]) = ({low}, {high}) is not finite.",
                fix_hint=hint,
            )
        if not low <= data[name] <= high:
            raise ExplainError(
                f"compare(error[{name!r}]) = ({low}, {high}) does not bracket the value "
                f"{data[name]}.",
                fix_hint="Pass absolute (low, high) bounds, not +/- offsets; for a symmetric "
                "interval pass one number, the half-width.",
            )
        errors[name] = (low, high)
        modes.add("bounds")
    return errors, modes


def _interval_issue(form: str, arg: str, label_arg: str) -> dict[str, Any]:
    return _issue(
        "interval_unlabelled",
        "warning",
        f"{form}({arg}=...) draws intervals without saying what they are; a whisker with no "
        "stated meaning cannot be interpreted.",
        f'Pass {label_arg}="95% CI" (or "\N{PLUS-MINUS SIGN} 1 s.d., n = 5", "min\N{EN DASH}max of 3 runs").',
    )


@_guarded("compare")
def compare(
    values: Mapping[str, float] | Sequence[tuple[str, float]],
    *,
    title: str | None = None,
    label: str | None = None,
    unit: str | None = None,
    highlight: str | Sequence[str] | None = None,
    sort: bool | str = True,
    zero: bool = True,
    error: Mapping[str, Any] | Sequence[Any] | float | None = None,
    error_label: str | None = None,
    reference: float | tuple[float, str] | None = None,
    log: bool = False,
    fmt: str | None = None,
) -> Panel:
    """How do items differ in size? Sorted horizontal bars with the values written on them.

    ``values`` maps item name to number (a dict or anything with ``.items()``).
    Bars start at zero (length is only honest from zero); pass ``zero=False``
    when zero is not meaningful and the panel becomes a dot plot. ``log=True``
    puts the dots on a logarithmic axis for values spanning decades.
    ``error`` gives each item ``(low, high)`` bounds or one half-width (or one
    number for all) and switches to dot-and-interval marks; say what the
    interval is with ``error_label``. ``sort`` is ``True``/``"desc"``,
    ``"asc"`` (lower is better) or ``False`` (keep an inherent order).
    """
    data = _named_values(values, "compare(values)")
    names = list(data)
    if len(names) > MAX_COMPARE_ITEMS:
        raise ExplainError(
            f"compare() got {len(names)} items; a ranked list longer than "
            f"{MAX_COMPARE_ITEMS} is scanned, not read.",
            fix_hint="Show the top 10 (say so in the title) or use distribution() for the spread.",
            rule="too_many_items",
        )
    order = _sort_order(sort)
    hl = _names(highlight, names)
    ref = _reference_line(reference, "compare(reference)")
    errors: dict[str, tuple[float, float]] | None = None
    modes: set[str] = set()
    if error is not None:
        errors, modes = _compare_intervals(error, data)
    if log:
        lows = [errors[nm][0] for nm in names] if errors else []
        if min([*data.values(), *lows, *([ref[0]] if ref else [])]) <= 0:
            raise ExplainError(
                "compare(log=True) needs strictly positive values (and interval bounds and "
                "reference).",
                fix_hint="Drop log=True, or remove the non-positive items and say so in note=.",
            )

    issues: list[dict[str, Any]] = []
    if len(names) > COMFORTABLE_COMPARE_ITEMS:
        issues.append(
            _issue(
                "many_items",
                "warning",
                f"{len(names)} items is a long list for one glance.",
                "Show the top 10 (say so in the title) and pass the rest as a sentence in note=.",
            )
        )
    if zero and not log and errors is None and min(data.values()) > 0:
        lo, hi = min(data.values()), max(data.values())
        if hi > 0 and (hi - lo) / hi < 0.1 and len(names) > 1:
            issues.append(
                _issue(
                    "differences_invisible",
                    "warning",
                    f"All values lie within {100 * (hi - lo) / hi:.0f}% of each other, so "
                    "zero-based bars will look identical.",
                    "If the small differences are the point, pass zero=False (dot plot) and "
                    "say in the title that the differences are small.",
                )
            )
    if errors is not None and not error_label:
        issues.append(_interval_issue("compare", "error", "error_label"))

    if order == "desc":
        names = sorted(names, key=lambda nm: data[nm], reverse=True)
    elif order == "asc":
        names = sorted(names, key=lambda nm: data[nm])
    vals = [data[nm] for nm in names]
    fmt_fn = _formatter(vals, fmt, unit=unit, log=log)
    labels = [
        _with_unit(fmt_fn(v), unit) if (i == 0 or _inline_unit(unit)) else fmt_fn(v)
        for i, v in enumerate(vals)
    ]

    def _u(v: float, f: Callable[[float], str] = fmt_fn) -> str:
        return _with_unit(f(v), unit)

    descending = sorted(data, key=lambda nm: data[nm], reverse=True)
    ranking = names if order != "given" else descending
    rank_word = "lowest first" if order == "asc" else "highest first"
    top, bottom = descending[0], descending[-1]
    facts = [f"highest: {top} {_u(data[top])}"]
    if len(descending) > 1:
        facts.append(f"lowest: {bottom} {_u(data[bottom])}")
        if all(v > 0 for v in data.values()):
            facts.append(
                f"highest/lowest ratio: {_ratio_text(data[top] / data[bottom])} "
                "(from unrounded values)"
            )
        else:
            span_fmt = _formatter([data[top] - data[bottom]], fmt, unit=unit)
            facts.append(
                f"range: {_u(data[bottom])} to {_u(data[top])} "
                f"(spread {_u(data[top] - data[bottom], span_fmt)})"
            )
    if len(descending) > 2:
        second = descending[1]
        if data[second] > 0 and data[top] > 0 and data[top] / data[second] >= 1.1:
            facts.append(
                f"{top} is {_ratio_text(data[top] / data[second])} the next highest "
                f"({second} {_u(data[second])})"
            )
    diffs: list[tuple[str, float, str, float]] = []
    for name in hl:
        if ref is not None:
            diffs.append((name, data[name] - ref[0], ref[1] or "reference", ref[0]))
        else:
            others = [nm for nm in ranking if nm not in hl]
            if others:
                diffs.append((name, data[name] - data[others[0]], others[0], data[others[0]]))
    diff_fmt = _formatter([d[1] for d in diffs], fmt, unit=unit)
    if log and fmt is None and any("\N{MULTIPLICATION SIGN}10" in fmt_fn(v) for v in vals):
        # The values are in scientific notation on this log axis: so are their differences.
        diff_fmt = _sci_text
    for name in hl:
        text = f"{name}: {_u(data[name])} (rank {ranking.index(name) + 1} of {len(ranking)}, {rank_word})"
        for d_name, d_value, other, other_value in diffs:
            if d_name == name:
                text += (
                    f"; {_diff_with_unit(_signed(diff_fmt(d_value)), unit)} vs {other} "
                    f"({_u(other_value)})"
                )
        facts.append(text)
    if errors is not None:
        bound_fmt = _formatter(
            # On a log axis the bounds share the values' notation.
            [*(vals if log else []), *(v for pair in errors.values() for v in pair)],
            fmt,
            unit=unit,
            log=log,
        )

        def _span(nm: str) -> str:
            lo_v, hi_v = errors[nm]  # type: ignore[index]
            return f"{bound_fmt(lo_v)}\N{EN DASH}{_with_unit(bound_fmt(hi_v), unit)}"

        pairs: list[tuple[str, str]] = []
        if hl:
            others = [nm for nm in ranking if nm not in hl]
            pairs = [(nm, others[0]) for nm in hl] if others else []
        elif len(ranking) > 1:
            pairs = [(ranking[1], ranking[0])]
        for a, b in pairs:
            (a_lo, a_hi), (b_lo, b_hi) = errors[a], errors[b]
            verb = "overlaps" if (a_lo <= b_hi and b_lo <= a_hi) else "does not overlap"
            facts.append(f"{a} {_span(a)} {verb} {b} {_span(b)}")
        facts.append(_interval_mode_text(modes, "intervals"))

    what = label or "values"
    describe = (
        f"{'Dot plot' if (not zero or errors or log) else 'Bar chart'} of {what} for {len(names)} items"
        + (f", in {unit}" if unit else "")
        + (" on a log scale" if log else "")
        + (f", with intervals ({error_label})" if errors and error_label else "")
    )
    notes = [
        n
        for n in (
            "log scale" if log else None,
            f"intervals: {error_label}" if errors and error_label else None,
        )
        if n
    ]
    return _bar_panel(
        kind="compare",
        names=names,
        values=vals,
        highlight=hl,
        labels=labels,
        title=title,
        label=label,
        unit=unit,
        spec=_base_spec(
            title,
            label,
            unit,
            values={nm: data[nm] for nm in data},
            highlight=hl or None,
            sort=sort,
            zero=zero,
            error=_jsonable(error) if errors else None,
            error_label=error_label,
            reference=list(ref) if ref else None,
            log=log or None,
            fmt=fmt,
        ),
        facts=facts,
        describe=describe,
        dots=(not zero) or errors is not None or log,
        errors=errors,
        reference=ref,
        issues=issues,
        log=log,
        measure_note="; ".join(notes) or None,
    )


@_guarded("share")
def share(
    parts: Mapping[str, float] | Sequence[tuple[str, float]],
    *,
    title: str | None = None,
    label: str | None = None,
    unit: str | None = None,
    highlight: str | Sequence[str] | None = None,
    top: int = 7,
    fmt: str | None = None,
) -> Panel:
    """What makes up the total? Sorted bars of each part's percentage (never a pie).

    Parts beyond the ``top`` largest are folded into one muted "Other" bar.
    ``label`` and ``unit`` describe the total, which is stated above the bars.
    """
    data = _named_values(parts, "share(parts)")
    if min(data.values()) < 0:
        raise ExplainError(
            "share() needs non-negative parts; a negative part has no share of a total.",
            fix_hint="Use compare() for signed values.",
        )
    total = sum(data.values())
    if total <= 0:
        raise ExplainError("share() parts sum to zero.", fix_hint="Pass positive parts.")
    if top < 2:
        raise ExplainError("share(top) must be at least 2.", fix_hint="Use top=5 or similar.")
    ranked = sorted(data, key=lambda nm: data[nm], reverse=True)
    kept = ranked if len(ranked) <= top + 1 else ranked[:top]
    rest = [nm for nm in ranked if nm not in kept]
    hl = _names(highlight, kept, "share(highlight)")

    names = list(kept)
    pct = [100.0 * data[nm] / total for nm in kept]
    other_name = f"Other ({len(rest)})"
    if rest:
        names.append(other_name)
        pct.append(100.0 * sum(data[nm] for nm in rest) / total)
    if fmt is not None:
        pct_fmt = _formatter(pct, fmt, unit="%")
    else:
        decimals = 0 if max(pct) >= 10 else 1

        def pct_fmt(v: float) -> str:
            text = f"{v:.{decimals}f}"
            return _sig_text(v, 2) if (v != 0 and _shows_zero(text)) else text

    labels = [f"{pct_fmt(v)}%" for v in pct]

    total_fmt = _formatter([total], unit=unit)
    total_text = _with_unit(total_fmt(total), unit)
    measure = f"Share of {label or 'total'} ({total_text} in all)"
    cumulative = np.cumsum(pct[: len(kept)])
    facts = [f"total: {total_text}", f"largest: {kept[0]} {labels[0]}"]
    if len(kept) >= 3:
        facts.append(f"top 3 together: {cumulative[2]:.0f}%")
    if rest:
        facts.append(f"{len(rest)} smaller parts folded into Other: {labels[-1]}")

    return _bar_panel(
        kind="share",
        names=names,
        values=pct,
        highlight=hl,
        labels=labels,
        title=title,
        label=measure,
        unit=None,
        spec=_base_spec(
            title, label, unit, parts=dict(data), highlight=hl or None, top=top, fmt=fmt
        ),
        facts=facts,
        describe=f"Bar chart of each part's share of {label or 'the total'} ({len(data)} parts)",
        dots=False,
        errors=None,
        reference=None,
        muted_names=(other_name,) if rest else (),
    )


# --------------------------------------------------------------------------- #
# trend
# --------------------------------------------------------------------------- #


def _parse_x(x: Sequence[Any]) -> tuple[str, np.ndarray, list[str]]:
    """Return ``(kind, positions, display strings)`` for numeric, date or ordered-category x."""
    if x is None or isinstance(x, (str, bytes)) or _is_number(x):
        raise ExplainError(
            f"trend(x) must be a list of x positions, got {type(x).__name__}.",
            fix_hint="Pass numbers, dates (ISO strings or date objects) or ordered labels, one "
            "per value of each series.",
        )
    xs = list(x)
    if len(xs) < 2:
        raise ExplainError(
            "trend() needs at least two x positions.",
            fix_hint="Use compare() for a single point in time.",
        )
    if all(_is_number(v) for v in xs):
        arr = np.asarray([float(v) for v in xs], dtype=float)
        if not np.all(np.isfinite(arr)):
            raise ExplainError(
                "trend(x) contains a missing or infinite x value.",
                fix_hint="Drop the positions with no x (and their series values) first.",
            )
        return "number", arr, [_x_text(v) for v in arr]
    if all(isinstance(v, (datetime, date, np.datetime64)) for v in xs) or all(
        isinstance(v, str) and _ISO_DATE.match(v) for v in xs
    ):
        try:
            stamps = np.array([np.datetime64(v) for v in xs], dtype="datetime64[s]")
        except ValueError as exc:
            raise ExplainError(
                f"trend(x) dates could not be read ({exc}).",
                fix_hint="Pass ISO dates such as '2026-01-31' or date/datetime objects.",
            ) from exc
        days = stamps.astype("datetime64[D]")
        if np.all(stamps == days):
            shown = [str(v)[:10] for v in xs]
        else:  # sub-day data: a fact reading "from 2026-01-01 to 2026-01-01" says nothing
            shown = [str(v).replace("T", " ")[:16] for v in stamps]
        return "date", np.asarray(mdates.date2num(stamps), dtype=float), shown
    return "category", np.arange(len(xs), dtype=float), [str(v) for v in xs]


def _x_text(v: float) -> str:
    """An x value in facts: years plain, others to three significant figures ("3.03")."""
    if v == round(v) and 1000 <= v <= 2200:
        return f"{v:.0f}"
    return _sig_text(float(v), large=_SCI_LARGE_PHYSICAL)


def _values_array(values: object, what: str) -> np.ndarray:
    if values is None or isinstance(values, (str, bytes)) or _is_number(values):
        raise ExplainError(
            f"{what} must be a list of numbers, got {values!r}.",
            fix_hint="Pass one number per x position (None for gaps).",
        )
    try:
        return np.asarray(
            [np.nan if v is None else _to_float(v, what) for v in values],  # type: ignore[union-attr]
            dtype=float,
        )
    except TypeError as exc:
        raise ExplainError(
            f"{what} must be a list of numbers.",
            fix_hint="Pass numbers (use None for gaps).",
        ) from exc


def _series_map(series: object, n: int) -> tuple[dict[str, np.ndarray], bool]:
    """``({name: values}, single)``; a mapping, a pandas DataFrame, or one bare sequence."""
    if series is None:
        return {}, False
    if _has_items(series) and not _is_one_dimensional(series):
        raw = {str(k): v for k, v in _pairs(series)}
        single = False
    else:
        raw = {"": series}
        single = True
    out: dict[str, np.ndarray] = {}
    for name, values in raw.items():
        arr = _values_array(values, f"trend(series[{name!r}])")
        if arr.ndim != 1 or arr.size != n:
            raise ExplainError(
                f"trend(series[{name!r}]) has {arr.size} values but x has {n}.",
                fix_hint="Every series must have one value per x position (None for gaps).",
            )
        out[name] = arr
    if not out:
        raise ExplainError("trend(series) is empty.", fix_hint="Pass at least one series.")
    return out, single


def _replicates(points: object, n: int, names_hint: Sequence[str]) -> dict[str, list[np.ndarray]]:
    """Read ``trend(points=...)``: per series, the raw replicate values at each x."""
    hint = (
        'Pass points={"name": [[replicates at x0], [replicates at x1], ...]} or '
        "{name: 2-D array of shape (n_x, n_replicates)}; use NaN or an empty list where an x "
        "has no measurement."
    )
    if _has_items(points) and not _is_one_dimensional(points):
        raw = {str(k): v for k, v in _pairs(points)}
    elif len(names_hint) <= 1:
        raw = {names_hint[0] if names_hint else "": points}
    else:
        raise ExplainError("trend(points) must map series names to replicates.", fix_hint=hint)
    out: dict[str, list[np.ndarray]] = {}
    for name, rows in raw.items():
        if isinstance(rows, (str, bytes)) or _is_number(rows) or rows is None:
            raise ExplainError(
                f"trend(points[{name!r}]) is not a list of replicates.", fix_hint=hint
            )
        rows_list = list(rows)  # type: ignore[call-overload]
        if len(rows_list) != n:
            raise ExplainError(
                f"trend(points[{name!r}]) has {len(rows_list)} rows but x has {n}.",
                fix_hint=hint,
            )
        per_x: list[np.ndarray] = []
        for row in rows_list:
            if row is None or _is_number(row):
                arr = np.asarray([np.nan if row is None else float(row)], dtype=float)
            else:
                arr = _values_array(row, f"trend(points[{name!r}])")
            per_x.append(arr[np.isfinite(arr)])
        out[name] = per_x
    return out


def _trend_bands(
    band: object, data: dict[str, np.ndarray], n: int
) -> tuple[dict[str, tuple[np.ndarray, np.ndarray]], dict[str, Any], set[str]]:
    """Read ``trend(band=...)``: per series (low, high) sequences, half-width sequence or number.

    Returns the absolute bounds, the per-series normalised spec, and the modes read.
    """
    hint = (
        "Per series pass (low_values, high_values) as absolute bounds, one half-width per x, "
        'or one number for a constant \N{PLUS-MINUS SIGN} band, e.g. band={"a": 0.5}.'
    )
    names = list(data)
    if band is None:
        return {}, {}, set()
    if _has_items(band) and not _is_one_dimensional(band):
        raw = {str(k): v for k, v in _pairs(band)}
    elif len(names) == 1:
        raw = {names[0]: band}
    else:
        raise ExplainError(
            "trend(band) must map series names to bands when there are several series.",
            fix_hint=hint,
        )
    bounds: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    spec: dict[str, Any] = {}
    modes: set[str] = set()
    for name, entry in raw.items():
        if name not in data:
            raise ExplainError(
                f"trend(band) names {name!r}, which is not a series.",
                fix_hint=f"Use one of: {', '.join(map(repr, names))}.",
            )
        values = data[name]
        if _is_number(entry):
            hw = _halfwidth(entry, f"trend(band[{name!r}])")
            bounds[name] = (values - hw, values + hw)
            spec[name] = hw
            modes.add("halfwidth")
            continue
        try:
            arr = np.asarray(
                [[np.nan if v is None else float(v) for v in part] for part in entry]  # type: ignore[union-attr]
                if not isinstance(entry, np.ndarray)
                else entry,
                dtype=float,
            )
        except (TypeError, ValueError):
            try:
                arr = np.asarray(
                    [np.nan if v is None else float(v) for v in entry],  # type: ignore[union-attr]
                    dtype=float,
                )
            except (TypeError, ValueError) as exc:
                raise ExplainError(f"trend(band[{name!r}]) is not numeric.", fix_hint=hint) from exc
        if arr.ndim == 2 and arr.shape == (2, n):
            low, high = arr[0], arr[1]
            ok = np.isfinite(low) & np.isfinite(high) & np.isfinite(values)
            if np.any(low[ok] > high[ok]) or np.any(
                (values[ok] < low[ok] - 1e-12 * np.abs(values[ok]))
                | (values[ok] > high[ok] + 1e-12 * np.abs(values[ok]))
            ):
                raise ExplainError(
                    f"trend(band[{name!r}]) (low, high) does not bracket the series values.",
                    fix_hint="Pass absolute (low, high) bounds, not +/- offsets; for a symmetric "
                    "band pass the half-widths (one sequence) or one number.",
                )
            bounds[name] = (low, high)
            spec[name] = [low.tolist(), high.tolist()]
            modes.add("bounds")
        elif arr.ndim == 1 and arr.size == n:
            if np.any(arr[np.isfinite(arr)] < 0):
                raise ExplainError(
                    f"trend(band[{name!r}]) has a negative half-width.", fix_hint=hint
                )
            bounds[name] = (values - arr, values + arr)
            spec[name] = arr.tolist()
            modes.add("halfwidth")
        else:
            raise ExplainError(
                f"trend(band[{name!r}]) has shape {arr.shape}; with {n} x positions expected "
                f"(2, {n}) bounds, {n} half-widths or one number.",
                fix_hint=hint,
            )
    return bounds, spec, modes


def _r2_text(r2: float) -> str:
    """R² to three decimals, four when it would otherwise read as 1.000."""
    return f"{r2:.4f}" if 0.9995 <= r2 < 1.0 else f"{r2:.3f}"


def _log_trend_facts(
    data: Mapping[str, np.ndarray],
    names: Sequence[str],
    xpos: np.ndarray,
    x_kind: str,
    log_x: bool,
    label: str | None,
) -> list[str]:
    """Facts a log-scale trend is judged by: slopes of log₁₀(y) and peak ratios.

    The least-squares slope of log₁₀(y) against x (plotted x units, numeric linear x
    only) with its R² lets an agent check an Arrhenius or exponential claim; when
    the peak is not an endpoint, its ratio to the first and last values (unrounded).
    """
    out: list[str] = []
    for name in names:
        arr = data[name]
        ok = np.isfinite(arr) & (arr > 0)
        shown = name or (label or "value")
        if x_kind == "number" and not log_x and ok.sum() >= 3 and np.ptp(xpos[ok]) > 0:
            lx, ly = xpos[ok].astype(float), np.log10(arr[ok])
            slope, icept = np.polyfit(lx, ly, 1)
            resid = ly - (slope * lx + icept)
            total = float(((ly - ly.mean()) ** 2).sum())
            r2 = 1.0 - float((resid**2).sum()) / total if total > 0 else float("nan")
            out.append(
                f"{shown}: log\N{SUBSCRIPT ONE}\N{SUBSCRIPT ZERO} slope "
                f"{_sig_text(float(slope), 3)} per unit x"
                + (f", R\N{SUPERSCRIPT TWO} = {_r2_text(r2)}" if math.isfinite(r2) else "")
            )
        idx = np.flatnonzero(ok)
        if idx.size >= 3:
            peak = int(idx[int(np.argmax(arr[idx]))])
            if peak not in (int(idx[0]), int(idx[-1])):
                top = float(arr[peak])
                out.append(
                    f"{shown}: peak is {_ratio_text(top / float(arr[idx[0]]))} the first value "
                    f"and {_ratio_text(top / float(arr[idx[-1]]))} the last"
                )
    return out


def _reference_crossings(
    ref: tuple[float, str],
    names: Sequence[str],
    data: Mapping[str, np.ndarray],
    xpos: np.ndarray,
    x_kind: str,
    x_text: Sequence[str],
    log: bool,
    log_x: bool,
    label: str | None,
) -> list[str]:
    """Where each named series first crosses the reference value.

    Interpolated linearly between the two bracketing measured x positions (in log
    space on a log axis, matching the straight segments drawn there). Series that
    never cross are skipped.
    """
    value, ref_text = ref
    # The reference as the caller gave it ("50", not "50.0" from the series' digits).
    ref_fmt = _formatter([value], log=log)
    out: list[str] = []
    target = math.log10(value) if log and value > 0 else value
    for name in names:
        arr = data[name]
        idx = np.flatnonzero(np.isfinite(arr))
        if idx.size < 2:
            continue
        ys = np.log10(arr[idx]) if log else arr[idx]
        xs = np.log10(xpos[idx]) if log_x else xpos[idx].astype(float)
        diff = ys - target
        where: str | None = None
        for k in range(idx.size):
            if diff[k] == 0:
                if k == 0:
                    continue  # starting on the line is not a crossing
                at = xs[k]
                exact = True
            elif k + 1 < idx.size and diff[k] * diff[k + 1] < 0:
                t = diff[k] / (diff[k] - diff[k + 1])
                at = xs[k] + t * (xs[k + 1] - xs[k])
                exact = False
            else:
                continue
            if x_kind == "category":
                where = (
                    f"at {x_text[idx[k]]}"
                    if exact
                    else f"between {x_text[idx[k]]} and {x_text[idx[k + 1]]}"
                )
            elif x_kind == "date":
                when = mdates.num2date(float(at)).date().isoformat()
                where = f"at {'' if exact else 'about '}{when}"
            else:
                x_val = 10**at if log_x else at
                where = f"at {'' if exact else 'about '}{_sig_text(float(x_val), 2)}"
            break
        if where is None:
            continue
        shown = name or (label or "value")
        named = f" ({ref_text})" if ref_text else ""
        out.append(f"{shown} crosses {ref_fmt(value)}{named} {where}")
    return out


def _first_finite(arr: np.ndarray) -> tuple[int, float]:
    idx = int(np.flatnonzero(np.isfinite(arr))[0])
    return idx, float(arr[idx])


def _last_finite(arr: np.ndarray) -> tuple[int, float]:
    idx = int(np.flatnonzero(np.isfinite(arr))[-1])
    return idx, float(arr[idx])


def _isolated(arr: np.ndarray) -> np.ndarray:
    """Finite points with no finite neighbour on either side (a line cannot show them)."""
    finite = np.isfinite(arr)
    left = np.concatenate([[False], finite[:-1]])
    right = np.concatenate([finite[1:], [False]])
    return finite & ~left & ~right


@_guarded("trend")
def trend(
    x: Sequence[Any],
    series: Mapping[str, Sequence[float]] | Sequence[float] | None = None,
    *,
    title: str | None = None,
    label: str | None = None,
    unit: str | None = None,
    x_label: str | None = None,
    highlight: str | Sequence[str] | None = None,
    facet: bool = False,
    band: Any = None,
    band_label: str | None = None,
    points: Any = None,
    events: Mapping[Any, str] | None = None,
    reference: float | tuple[float, str] | None = None,
    zero: bool = False,
    log: bool = False,
    log_y: bool | None = None,
    log_x: bool = False,
    end_values: bool = True,
    fmt: str | None = None,
) -> Panel:
    """How does it change over time or order? Lines labelled at their ends (no legend).

    ``x`` is numbers, ISO dates or ordered labels (numeric and date x are sorted
    with their series; repeated x values are refused). ``series`` maps name to
    values (a dict, a pandas DataFrame, or one sequence). At most four series
    get a hue. With more, name the ones the takeaway is about in ``highlight``
    (the rest become grey context) or pass ``facet=True`` for small multiples
    on a shared scale. ``band`` gives a series an uncertainty ribbon: ``(low,
    high)`` sequences, half-widths per x, or one number; say what it is with
    ``band_label``. ``points`` gives raw replicates per x (the line becomes
    their mean). ``log``/``log_y`` and ``log_x`` make an axis logarithmic.
    ``end_values=False`` keeps the end label's name but drops its value.
    """
    log = bool(log or log_y)
    x_kind, xpos, x_text = _parse_x(x)
    n = len(xpos)
    data, single = _series_map(series, n)
    reps: dict[str, list[np.ndarray]] = {}
    if points is not None:
        reps = _replicates(points, n, list(data) if data else [""])
        for name, per_x in reps.items():
            means = np.array([float(r.mean()) if r.size else np.nan for r in per_x])
            if name in data:
                given = data[name]
                both = np.isfinite(given) & np.isfinite(means)
                if not np.allclose(given[both], means[both], rtol=1e-6, atol=1e-12) or np.any(
                    np.isfinite(means) != np.isfinite(given)
                ):
                    raise ExplainError(
                        f"trend(series[{name!r}]) differs from the mean of points[{name!r}].",
                        fix_hint="With points=, the line is the mean of the replicates: leave the "
                        "series out of series= (or pass series=None).",
                    )
            data[name] = means
        if not data:
            raise ExplainError("trend(points) is empty.", fix_hint="Pass at least one series.")
        single = single or (list(reps) == [""])
    if not data:
        raise ExplainError(
            "trend() needs series= (or points= with raw replicates).",
            fix_hint='e.g. fm.trend([1, 2, 3], {"a": [3, 4, 6]}).',
        )
    for name, arr in data.items():
        if np.isfinite(arr).sum() < 2:
            raise ExplainError(
                f"trend(series[{name!r}]) has fewer than two finite values.",
                fix_hint="Drop the series or use compare().",
            )

    # Numeric and date x are drawn in x order: sort with the series, refuse repeats.
    if x_kind in {"number", "date"}:
        order = np.argsort(xpos, kind="stable")
        if np.any(np.diff(xpos[order]) == 0):
            dup = x_text[int(order[int(np.flatnonzero(np.diff(xpos[order]) == 0)[0])])]
            raise ExplainError(
                f"trend(x) repeats the x value {dup}; a line needs one value per x.",
                fix_hint="Aggregate replicates first: the mean per x in series=, the spread in "
                "band= (with band_label=), or pass the raw replicates as points={name: "
                "[[values at x0], [values at x1], ...]}.",
            )
        if np.any(order != np.arange(n)):
            xpos = xpos[order]
            x_text = [x_text[i] for i in order]
            x_list = list(x)
            x = [x_list[i] for i in order]
            data = {k: v[order] for k, v in data.items()}
            reps = {k: [v[i] for i in order] for k, v in reps.items()}
            if band is not None:
                band = _reorder_band(band, order, n)
    if log_x:
        if x_kind != "number":
            raise ExplainError(
                "trend(log_x=True) needs numeric x (dose, frequency, 1/T).",
                fix_hint="Pass numbers as x, or drop log_x.",
            )
        if xpos.min() <= 0:
            raise ExplainError(
                "trend(log_x=True) needs strictly positive x values.",
                fix_hint="Drop log_x=True or remove the x positions <= 0.",
            )

    names = list(data)
    hl = _names(highlight, names)
    if len(names) > MAX_COLORED_SERIES and not hl and not facet:
        raise ExplainError(
            f"trend() got {len(names)} series and no highlight; more than "
            f"{MAX_COLORED_SERIES} coloured lines cannot be told apart or held in mind.",
            fix_hint="Pass highlight=[...] with the 1-3 series the takeaway names (others turn "
            "grey), or facet=True for small multiples.",
            rule="too_many_series",
        )
    if facet and len(names) > 12:
        raise ExplainError(
            f"trend(facet=True) got {len(names)} series; more than 12 small multiples is a wall.",
            fix_hint="Keep the 6-12 most relevant series, or highlight a few in one panel.",
            rule="too_many_series",
        )
    ref = _reference_line(reference, "trend(reference)")
    bands, band_spec, band_modes = _trend_bands(band, data, n)
    event_items: list[tuple[float, str]] = []
    for at, text in (events or {}).items():
        if x_kind == "number":
            try:
                pos = _to_float(float(at) if isinstance(at, str) else at, "trend(events) key")
            except ValueError as exc:
                raise ExplainError(
                    f"trend(events) key {at!r} is not a number on this numeric x axis.",
                    fix_hint="Use an x value, e.g. events={4: 'deploy'}.",
                ) from exc
        elif x_kind == "date":
            try:
                pos = float(mdates.date2num(np.datetime64(at)))
            except ValueError as exc:
                raise ExplainError(
                    f"trend(events) key {at!r} is not a date.",
                    fix_hint="Use an ISO date such as '2026-03-01' or a date object.",
                ) from exc
        else:
            if str(at) not in x_text:
                raise ExplainError(
                    f"trend(events) key {at!r} is not one of the x labels.",
                    fix_hint="Use an x value exactly as it appears in x.",
                )
            pos = float(x_text.index(str(at)))
        event_items.append((pos, str(text)))

    all_values = np.concatenate([v[np.isfinite(v)] for v in data.values()])
    rep_values = np.concatenate([r for per_x in reps.values() for r in per_x] or [np.empty(0)])
    if log and (all_values.min() <= 0 or (rep_values.size and rep_values.min() <= 0)):
        raise ExplainError(
            "trend(log=True) needs strictly positive values.",
            fix_hint="Drop log=True or remove non-positive values.",
        )
    if log and ref is not None and ref[0] <= 0:
        raise ExplainError(
            "trend(reference) must be positive on a log axis.",
            fix_hint="Drop the reference or log=True.",
        )
    fmt_fn = _formatter(list(all_values), fmt, unit=unit, log=log)

    _last = _last_finite
    _first = _first_finite

    colored = hl if hl else ([] if facet else names)
    issues: list[dict[str, Any]] = []
    if bands and not band_label:
        issues.append(_interval_issue("trend", "band", "band_label"))

    facts: list[str] = []
    for name in (hl or names)[:6]:
        arr = data[name]
        i0, v0 = _first(arr)
        i1, v1 = _last(arr)
        finite = arr[np.isfinite(arr)]
        moved = _change_text(
            v0,
            v1,
            series_range=float(finite.max() - finite.min()),
            unit=unit,
            diff_fmt=_formatter([v1 - v0], fmt, unit=unit),
            log=log,
        )
        peak = int(np.nanargmax(arr))
        shown = name or (label or "value")
        missing = int((~np.isfinite(arr)).sum())
        facts.append(
            f"{shown}: {fmt_fn(v0)} \N{RIGHTWARDS ARROW} {_with_unit(fmt_fn(v1), unit)} "
            f"from {x_text[i0]} to {x_text[i1]}"
            + (f" ({moved})" if moved else "")
            + f"; peak {fmt_fn(float(arr[peak]))} at {x_text[peak]}"
            + (f"; {missing} of {n} points missing" if missing else "")
        )
    if log:
        facts.extend(_log_trend_facts(data, (hl or names)[:6], xpos, x_kind, log_x, label))
    for name in names:
        if name not in (hl or names)[:6] and (~np.isfinite(data[name])).any():
            facts.append(
                f"{name or 'series'}: {int((~np.isfinite(data[name])).sum())} of {n} points missing"
            )
    if 2 <= len(colored) <= MAX_COLORED_SERIES:
        a, b = colored[0], colored[1]
        both = np.flatnonzero(np.isfinite(data[a]) & np.isfinite(data[b]))
        if both.size:
            idx = int(both[-1])
            va, vb = float(data[a][idx]), float(data[b][idx])
            if log:
                ratio = va / vb
                rel = (
                    f"{_ratio_text(ratio)} {b}"
                    if ratio >= 1
                    else f"{_ratio_text(1 / ratio)} below {b}"
                )
                facts.append(f"at {x_text[idx]}: {a} is {rel}")
            else:
                gap_fmt = _formatter([abs(va - vb)], fmt, unit=unit)
                if va == vb:
                    facts.append(f"at {x_text[idx]}: {a} equals {b}")
                else:
                    facts.append(
                        f"at {x_text[idx]}: {a} is {_diff_with_unit(gap_fmt(abs(va - vb)), unit)} "
                        f"{'above' if va > vb else 'below'} {b}"
                    )
        for other in colored[1:]:
            diff = data[a] - data[other]
            idxs = np.flatnonzero(np.isfinite(diff) & (diff != 0))
            if idxs.size < 2:
                continue
            start = np.sign(diff[idxs[0]])
            flips = idxs[np.sign(diff[idxs]) != start]
            if flips.size:
                k = int(flips[0])
                facts.append(
                    f"{a} first crosses {'above' if start < 0 else 'below'} {other} at {x_text[k]}"
                )
    if ref is not None:
        facts.extend(
            _reference_crossings(
                # Highlighted series first, then the grey context ones: a potency claim
                # ("10x below the others") needs every curve's crossing.
                ref,
                [*hl, *(nm for nm in names if nm not in hl)][:6],
                data,
                xpos,
                x_kind,
                x_text,
                log,
                log_x,
                label,
            )
        )
    if reps:
        for name, per_x in reps.items():
            counts = [r.size for r in per_x]
            measured = [c for c in counts if c]
            lo_n, hi_n = min(measured, default=0), max(measured, default=0)
            facts.append(
                f"{name or (label or 'values')}: line is the mean of n = "
                + (f"{lo_n}" if lo_n == hi_n else f"{lo_n}\N{EN DASH}{hi_n}")
                + " replicates per x"
            )
    if bands:
        facts.append(_interval_mode_text(band_modes, "bands"))

    describe = (
        f"{'Small-multiple line charts' if facet else 'Line chart'} of {label or 'values'}"
        + (f" ({unit})" if unit else "")
        + (" on a log scale" if log else "")
        + f" over {x_label or 'x'}"
        + (" (log scale)" if log_x else "")
        + f" from {x_text[0]} to {x_text[-1]}, {len(names)} series"
        + (f", shaded bands show {band_label}" if bands and band_label else "")
    )
    show_markers = n <= 12

    def _setup_x(
        ax: Axes, sizes: _Sizes, theme: Theme = FIGMINT_THEME, *, sparse: bool = False
    ) -> None:
        minus = theme.minus_sign
        if log_x:
            ax.set_xscale("log")
            ax.set_xlim(float(xpos.min()), float(xpos.max()))
            ax.xaxis.set_minor_formatter(NullFormatter())
            _narrow_log_ticks(ax.xaxis, float(xpos.min()), float(xpos.max()), minus, extend=False)
            return
        ax.set_xlim(float(xpos.min()), float(xpos.max()))
        if x_kind == "date":
            locator = mdates.AutoDateLocator(minticks=2, maxticks=3 if sparse else 6)
            ax.xaxis.set_major_locator(locator)
            ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator, show_offset=False))
        elif x_kind == "category":
            limit = 3 if sparse else 8
            step = max(1, math.ceil(len(xpos) / limit))
            shown = list(range(0, len(xpos), step))
            ax.set_xticks(xpos[shown], [_plain(x_text[i], theme) for i in shown])
        else:
            whole = bool(np.all(xpos == np.round(xpos)))
            years = whole and 1000 <= xpos.min() and xpos.max() <= 2200
            if len(xpos) <= 8:
                # Few measured positions (doping 0, 0.5, 1, 2, 4): tick exactly there;
                # labels that would touch are thinned after layout (_fit_ticks).
                ax.xaxis.set_major_locator(FixedLocator(xpos.tolist()))
            else:
                ax.xaxis.set_major_locator(MaxNLocator(nbins=3 if sparse else 6, integer=whole))
            ax.xaxis.set_major_formatter(
                FuncFormatter(
                    lambda v, _p, m=minus, a=ax.xaxis: f"{v:.0f}" if years else _tick_label(v, m, a)
                )
            )

    def _ylimits() -> tuple[float, float]:
        lows = [all_values.min()] + [np.nanmin(b[0]) for b in bands.values()]
        highs = [all_values.max()] + [np.nanmax(b[1]) for b in bands.values()]
        if rep_values.size:
            lows.append(rep_values.min())
            highs.append(rep_values.max())
        if ref is not None:
            lows.append(ref[0])
            highs.append(ref[0])
        lo, hi = float(min(lows)), float(max(highs))
        if log:
            lo = max(lo, float(all_values.min()) / 10.0) if lo <= 0 else lo
            return lo / 1.15, hi * 1.15
        span = (hi - lo) or abs(hi) or 1.0
        bottom = 0.0 if (zero and lo >= 0) else lo - 0.06 * span
        return bottom, hi + 0.08 * span

    def _decorate(
        ctx: _Ctx, ax: Axes, sizes: _Sizes
    ) -> tuple[list[Any], list[Any], tuple[Any, ...] | None]:
        """Reference and event rules.

        Returns (event labels with their rules, other labels, the reference label
        with its line for :func:`_place_reference_label`, or None).
        """
        theme = ctx.theme
        others: list[Any] = []
        events_drawn: list[Any] = []
        ref_drawn: tuple[Any, ...] | None = None
        if ref is not None:
            ref_line = ax.axhline(
                ref[0], color=theme.ink, linewidth=0.7, linestyle=(0, (3, 2)), zorder=2
            )
            if ref[1]:
                # Inline-tick styles print tick values at the left edge: label on the right.
                right = theme.inline_y_ticks
                ref_note = ax.annotate(
                    _plain(ref[1], theme),
                    (1.0 if right else 0.0, ref[0]),
                    xycoords=("axes fraction", "data"),
                    xytext=(-2.0 if right else 2.0, 2.5),
                    textcoords="offset points",
                    ha="right" if right else "left",
                    va="bottom",
                    fontsize=sizes.small,
                    color=theme.muted,
                    bbox=ctx.halo_bbox(0.1),
                )
                others.append(ref_note)
                ref_drawn = (ref_note, ref_line, ref[1], right)
        lo_x, hi_x = (
            (math.log10(xpos.min()), math.log10(xpos.max())) if log_x else (xpos.min(), xpos.max())
        )
        for pos, text in event_items:
            rule = ax.axvline(pos, color=theme.axis, linewidth=0.6, zorder=1)
            at = math.log10(pos) if (log_x and pos > 0) else pos
            near_right = at > lo_x + 0.7 * (hi_x - lo_x)
            note = ax.annotate(
                _plain(text, theme),
                (pos, 1.0),
                xycoords=("data", "axes fraction"),
                xytext=(-3.0 if near_right else 3.0, -2.0),
                textcoords="offset points",
                ha="right" if near_right else "left",
                va="top",
                fontsize=sizes.small,
                color=theme.muted,
                bbox=ctx.halo_bbox(0.1),
            )
            events_drawn.append((note, rule, pos, text, near_right))
        return events_drawn, others, ref_drawn

    def _measured_points(
        ax: Axes, name: str, col: str, sizes: _Sizes, theme: Theme, *, context: bool = False
    ) -> None:
        """Replicates as pale dots; a marker at each measurement when x is sparse; lone points."""
        if name in reps:
            rx = np.concatenate([np.full(r.size, xpos[i]) for i, r in enumerate(reps[name])])
            ry = np.concatenate(reps[name])
            ax.scatter(
                rx,
                ry,
                s=(2.4 * sizes.scale) ** 2,
                color=col,
                alpha=0.3 if not context else 0.2,
                linewidth=0,
                zorder=3,
                clip_on=False,
            )
        arr = data[name]
        mask = np.isfinite(arr) if show_markers else _isolated(arr)
        if mask.any():
            ax.plot(
                xpos[mask],
                arr[mask],
                linestyle="none",
                marker="o",
                markersize=(2.2 if context else 2.8) * sizes.scale,
                color=col,
                markeredgecolor=theme.background,
                markeredgewidth=0.4,
                zorder=3 if context else 4,
                label="_points",
                clip_on=False,
            )

    # ---- single panel with direct labels --------------------------------- #
    def _draw(ctx: _Ctx, ax: Axes) -> Callable[[], None]:
        sz = ctx.sizes
        theme = ctx.theme
        palette = theme.accent_colors if hl else theme.series_colors
        color_of = {
            name: ctx.colors.get(name, ctx.default_color if not name else palette[i])
            for i, name in enumerate(colored)
        }
        effects = ctx.line_effects()
        if log:
            ax.set_yscale("log")
        _value_axis(ax, sz, theme)
        _setup_x(ax, sz, theme)
        ax.set_ylim(*_ylimits())
        y0, y1 = ax.get_ylim()
        if log:
            y0, y1 = _narrow_log_ticks(ax.yaxis, y0, y1, theme.minus_sign, data_hi=y1 / 1.15)
            ax.set_ylim(y0, y1)
        if theme.hide_spines and not log and y0 <= 0.0 <= y1:
            ax.axhline(0.0, color=theme.zero_line, linewidth=theme.zero_line_lw, zorder=2)
        if theme.inline_y_ticks and not log:
            _apply_inline_y_ticks(ax, sz, theme, unit=unit)
        if x_label:
            ax.set_xlabel(_plain(x_label, theme), fontsize=sz.small, color=theme.muted, labelpad=2)

        context = [nm for nm in names if nm not in color_of]
        for name in context:
            line_kw: dict[str, Any] = {
                "color": theme.context_line,
                "linewidth": theme.context_line_lw * sz.scale,
                "zorder": 2,
                "label": "_context",
            }
            if effects is not None:
                line_kw["path_effects"] = effects
            ax.plot(xpos, data[name], **line_kw)
            _measured_points(ax, name, theme.context_line, sz, theme, context=True)
        for name in colored:
            col = color_of[name]
            if name in bands:
                ax.fill_between(
                    xpos,
                    bands[name][0],
                    bands[name][1],
                    color=col,
                    alpha=0.14,
                    linewidth=0,
                    zorder=2,
                )
            line_kw = {
                "color": col,
                "linewidth": theme.line_lw * sz.scale,
                "zorder": 4,
                "label": name or "_single",
                "solid_capstyle": theme.line_capstyle,
            }
            if effects is not None:
                line_kw["path_effects"] = effects
            ax.plot(xpos, data[name], **line_kw)
            _measured_points(ax, name, col, sz, theme)
            i1, v1 = _last(data[name])
            ax.plot(
                [xpos[i1]],
                [v1],
                marker="o",
                markersize=3.6 * sz.scale,
                color=col,
                markeredgecolor=theme.background,
                markeredgewidth=0.6,
                zorder=5,
                label="_end",
                clip_on=False,
            )
        events_drawn, other_notes, ref_drawn = _decorate(ctx, ax, sz)

        label_context = bool(context) and len(names) <= 8
        entries: list[tuple[str, float, float, str, str, str]] = []
        for name in colored:
            i1, v1 = _last(data[name])
            if not name:
                if not end_values:
                    continue
                text = _with_unit(fmt_fn(v1), unit)
            else:
                text = f"{name}  {fmt_fn(v1)}" if end_values else name
            entries.append(
                (text, float(xpos[i1]), v1, ctx.text_color(color_of[name]), "bold", color_of[name])
            )
        if label_context:
            for name in context:
                i1, v1 = _last(data[name])
                entries.append(
                    (name, float(xpos[i1]), v1, theme.muted, "normal", theme.context_line)
                )
        elif context:
            mid = sorted(context, key=lambda nm: _last(data[nm])[1])[len(context) // 2]
            i1, v1 = _last(data[mid])
            entries.append(
                (
                    f"{len(context)} others",
                    float(xpos[i1]),
                    v1,
                    theme.muted,
                    "normal",
                    theme.context_line,
                )
            )

        annotations = [
            ax.annotate(
                _plain(text, theme),
                (px, py),
                xytext=(6.0, 0.0),
                textcoords="offset points",
                ha="left",
                va="center",
                fontsize=sz.small,
                color=text_color,
                fontweight=weight,
                annotation_clip=False,
            )
            for text, px, py, text_color, weight, _ in entries
        ]

        def _finish() -> None:
            _relax_end_labels()
            _clear_inline_ticks(ctx, ax)
            _place_reference_label(ctx, ax, ref_drawn, annotations)
            _place_event_labels(ctx, ax, events_drawn, [*annotations, *other_notes])

        def _relax_end_labels() -> None:
            if not annotations:
                return
            renderer = ctx.fig.canvas.get_renderer()
            box = ax.get_window_extent(renderer)
            k = ctx.pt_per_px
            ys = np.array([ax.transData.transform((e[1], e[2]))[1] * k for e in entries])
            placed = _relax_positions_pt(
                ys, sz.small * 1.22, box.y0 * k + sz.small * 0.4, box.y1 * k - sz.small * 0.4
            )
            for ann, entry, y0, y1 in zip(annotations, entries, ys, placed, strict=True):
                shift = float(y1 - y0)
                ann.set_position((6.0, shift))
                if abs(shift) > sz.small * 0.75:
                    ax.annotate(
                        "",
                        (entry[1], entry[2]),
                        xytext=(5.0, shift),
                        textcoords="offset points",
                        arrowprops={
                            "arrowstyle": "-",
                            "color": entry[5],
                            "linewidth": 0.5,
                            "shrinkA": 0,
                            "shrinkB": 2.5,
                        },
                        annotation_clip=False,
                    )

        return _finish

    # ---- small multiples -------------------------------------------------- #
    def _facet_grid(cell_width_mm: float) -> tuple[int, int]:
        ncols = max(1, min(len(names), int(cell_width_mm // 30.0), 4))
        return math.ceil(len(names) / ncols), ncols

    def _facet_frames(ctx: _Ctx, ax: Axes, rect: Bbox) -> list[tuple[Axes, Bbox]]:
        sz = ctx.sizes
        theme = ctx.theme
        effects = ctx.line_effects()
        ax.remove()
        nrows, ncols = _facet_grid(ctx.cell_width_mm)
        px_per_mm = float(ctx.fig.dpi) / 25.4
        gap_x, gap_y = 4.0 * px_per_mm * sz.scale, 4.5 * px_per_mm * sz.scale
        cell_w = (rect.width - gap_x * (ncols - 1)) / ncols
        cell_h = (rect.height - gap_y * (nrows - 1)) / nrows
        ylim = _ylimits()
        frames: list[tuple[Axes, Bbox]] = []
        facet_events: list[tuple[Axes, list[Any], list[Any]]] = []
        first: Axes | None = None
        for idx, name in enumerate(names):
            r, c = divmod(idx, ncols)
            x0 = rect.x0 + c * (cell_w + gap_x)
            y1 = rect.y1 - r * (cell_h + gap_y)
            sub = Bbox.from_extents(x0, y1 - cell_h, x0 + cell_w, y1)
            child = ctx.fig.add_axes([0.1, 0.1, 0.5, 0.5], sharey=first)
            first = first or child
            ctx.tag(child)
            ctx.extra_axes.append(child)
            if log:
                child.set_yscale("log")
            _value_axis(child, sz, theme, nbins=3)
            _setup_x(child, sz, theme, sparse=True)
            child.set_ylim(*ylim)
            if log:
                child.set_ylim(
                    *_narrow_log_ticks(
                        child.yaxis,
                        ylim[0],
                        ylim[1],
                        theme.minus_sign,
                        max_ticks=4,
                        data_hi=ylim[1] / 1.15,
                    )
                )
            col = theme.accent_colors[hl.index(name)] if name in hl else theme.default_color
            ghost_col = theme.context_fill
            for other in names:
                if other != name:
                    child.plot(
                        xpos,
                        data[other],
                        color=ghost_col,
                        linewidth=0.7 * sz.scale,
                        zorder=1,
                        label="_ghost",
                    )
            if name in bands:
                child.fill_between(
                    xpos,
                    bands[name][0],
                    bands[name][1],
                    color=col,
                    alpha=0.14,
                    linewidth=0,
                    zorder=2,
                )
            line_kw: dict[str, Any] = {
                "color": col,
                "linewidth": theme.facet_line_lw * sz.scale,
                "zorder": 3,
                "label": "_series",
                "solid_capstyle": theme.line_capstyle,
            }
            if effects is not None:
                line_kw["path_effects"] = effects
            child.plot(xpos, data[name], **line_kw)
            _measured_points(child, name, col, sz, theme)
            i1, v1 = _last(data[name])
            child.plot(
                [xpos[i1]],
                [v1],
                marker="o",
                markersize=3.2 * sz.scale,
                color=col,
                markeredgecolor=theme.background,
                markeredgewidth=0.6,
                zorder=4,
                clip_on=False,
                label="_end",
            )
            child_events, child_notes, child_ref = _decorate(ctx, child, sz)
            facet_events.append((child, child_events, child_notes, child_ref))
            child.set_title(
                _plain(f"{name}  {fmt_fn(v1)}" if end_values else name, theme),
                loc="left",
                fontsize=sz.small,
                fontweight="bold",
                color=ctx.text_color(col) if name in hl else theme.ink,
                pad=3.0,
            )
            child.tick_params(axis="y", labelleft=(c == 0))
            last_in_column = idx + ncols >= len(names)
            child.tick_params(axis="x", labelbottom=last_in_column)
            frames.append((child, sub))

        def _equalize() -> None:
            """Give every small multiple the same plot width (only column one has y labels)."""
            fig_w = ctx.fig.bbox.width
            gutter = frames[0][0].get_position().x0 * fig_w - rect.x0
            plot_w = (rect.width - gutter - gap_x * (ncols - 1)) / ncols
            for idx, (child, _sub) in enumerate(frames):
                pos = child.get_position()
                left = rect.x0 + gutter + (idx % ncols) * (plot_w + gap_x)
                child.set_position([left / fig_w, pos.y0, plot_w / fig_w, pos.height])

        ctx.finishers.append(_equalize)
        for child, child_events, child_notes, child_ref in facet_events:
            if child_ref is not None:
                ctx.finishers.append(
                    functools.partial(
                        _place_reference_label,
                        ctx,
                        child,
                        child_ref,
                        [getattr(child, "_left_title", None)],
                    )
                )
            if child_events:
                ctx.finishers.append(
                    functools.partial(
                        _place_event_labels,
                        ctx,
                        child,
                        child_events,
                        [*child_notes, getattr(child, "_left_title", None)],
                    )
                )
        return frames

    series_spec: Any
    if single:
        series_spec = None if "" in reps else data[""]
    else:
        series_spec = {k: v for k, v in data.items() if k not in reps} or None
    spec = _base_spec(
        title,
        label,
        unit,
        x=[
            (int(v) if float(v) == int(v) else float(v))
            if _is_number(v)
            else (v if isinstance(v, str) else _jsonable(v))
            for v in x
        ],
        series=_jsonable(series_spec),
        x_label=x_label,
        highlight=hl or None,
        facet=facet or None,
        band=band_spec or None,
        band_label=band_label,
        points={k: [r.tolist() for r in v] for k, v in reps.items()} or None,
        events={str(_jsonable(k)): str(v) for k, v in (events or {}).items()} or None,
        reference=list(ref) if ref else None,
        zero=zero or None,
        log=log or None,
        log_x=log_x or None,
        end_values=None if end_values else False,
        fmt=fmt,
    )
    notes = [
        nt
        for nt in (
            f"band: {band_label}" if bands and band_label else None,
            "dots: replicates" if reps else None,
        )
        if nt
    ]

    if facet:

        def _facet_height(
            cell_width_mm: float, _m: _Measure, _s: _Sizes, _t: Theme = FIGMINT_THEME
        ) -> float:
            nrows, _ = _facet_grid(cell_width_mm)
            return nrows * 27.0 + (nrows - 1) * 4.5 + (4.0 if x_label else 0.0)

        return Panel(
            kind="trend",
            title=title,
            label=label,
            unit=unit,
            spec=spec,
            facts=facts,
            describe=describe,
            issues=issues,
            _height_mm=_facet_height,
            _draw=lambda _ctx, _ax: None,
            _frames=_facet_frames,
            measure_note="; ".join(notes) or None,
        )

    return Panel(
        kind="trend",
        title=title,
        label=label,
        unit=unit,
        spec=spec,
        facts=facts,
        describe=describe,
        issues=issues,
        _height_mm=lambda w, _m, _s, _t: min(54.0, max(36.0, 0.40 * w)) + (4.0 if x_label else 0.0),
        stretch=True,
        _draw=_draw,
        measure_note="; ".join(notes) or None,
        color_items=tuple(nm for nm in names if nm),
        color_focus=tuple(nm for nm in colored if nm),
        color_mode="highlight" if hl else "series",
        uses_default="" in colored,
    )


def _data_paths(ax: Axes, skip: Sequence[Any]) -> list[Any]:
    """Display-space paths of the lines and markers drawn on ``ax`` (not ``skip``)."""
    paths = []
    for line in ax.get_lines():
        if line in skip or not line.get_visible():
            continue
        xy = line.get_xydata()
        if xy is None or len(xy) == 0:
            continue
        path = line.get_transform().transform_path(line.get_path())
        paths.append(path)
    return paths


def _place_event_labels(ctx: _Ctx, ax: Axes, events: Sequence[Any], avoid: Sequence[Any]) -> None:
    """Move each event label to a spot where it covers no line, marker or other label.

    Tries the top of the rule on its preferred side, then the other side, then just
    under the top gridline, then the bottom of the plot. When every spot is taken the
    first is kept and an ``event_label_collides`` warning says to shorten the label.
    """
    if not events:
        return
    renderer = ctx.fig.canvas.get_renderer()
    frame = ax.get_window_extent(renderer)
    rules = [rule for _note, rule, _pos, _text, _right in events]
    paths = _data_paths(ax, rules)
    taken = [
        t.get_window_extent(renderer)
        for t in [*avoid, *ctx.fig.texts]
        if t is not None and t.get_visible() and t.get_text()
    ]
    taken += [box for axis in (ax.xaxis, ax.yaxis) for _, box in _tick_label_boxes(axis, renderer)]
    # A label may reach left over the empty top of the y-tick gutter, never past it.
    gutter = ax.yaxis.get_tightbbox(renderer)
    left_limit = min(frame.x0, gutter.x0) if gutter is not None else frame.x0
    y0, y1 = ax.get_ylim()
    ticks = [float(t) for t in ax.yaxis.get_majorticklocs() if min(y0, y1) < t < max(y0, y1)]
    upper = sorted(ticks, reverse=y1 > y0)
    frac_top = None
    if upper:
        top_tick = upper[0]
        display = ax.transData.transform((ax.get_xlim()[0], top_tick))
        frac_top = float(ax.transAxes.inverted().transform(display)[1])
    for note, _rule, pos, text, near_right in events:
        sides = [near_right, not near_right]
        spots = [(1.0, "top", side) for side in sides]
        if frac_top is not None and 0.2 < frac_top < 0.98:
            spots += [(frac_top, "top", side) for side in sides]
        spots += [(0.0, "bottom", side) for side in sides]
        # Last resort before warning: just above the plot frame, beside the rule's top.
        spots += [(1.0, "above", side) for side in sides]
        chosen = None
        for frac, va, right in spots:
            note.xy = (pos, frac)
            note.set_verticalalignment("bottom" if va == "above" else va)
            note.set_horizontalalignment("right" if right else "left")
            dy = -2.0 if va == "top" else (2.0 if va == "bottom" else 1.0)
            note.set_position((-3.0 if right else 3.0, dy))
            box = note.get_window_extent(renderer).expanded(1.0, 1.0)
            inside = box.x0 >= left_limit - 1 and box.x1 <= frame.x1 + 1
            if va == "above":
                inside = inside and box.y1 <= ctx.fig.bbox.y1
            clear = not any(box.overlaps(other) for other in taken)
            free = not any(path.intersects_bbox(box, filled=False) for path in paths)
            if inside and clear and free:
                chosen = box
                break
        if chosen is None:
            frac, va, right = spots[0]
            note.xy = (pos, frac)
            note.set_verticalalignment(va)
            note.set_horizontalalignment("right" if right else "left")
            note.set_position((-3.0 if right else 3.0, -2.0))
            chosen = note.get_window_extent(renderer)
            ctx.issues.append(
                _issue(
                    "event_label_collides",
                    "warning",
                    f"The event label {text!r} covers a line or another label wherever it is "
                    "placed in this panel.",
                    "Shorten the event label (one or two words, e.g. 'v2.3'), move the detail "
                    'to note=, or give the panel a full-width row with layout=[["a"], ["b"]].',
                    panel=ctx.key,
                )
            )
        taken.append(chosen)


def _place_reference_label(ctx: _Ctx, ax: Axes, ref: Any, avoid: Sequence[Any]) -> None:
    """Move a reference-line label to a spot where it covers no line, marker or label.

    ``ref`` is ``(note, line, text, prefer_right)``. Tries the preferred end above the
    line, the other end above it, then both ends below it. When every spot is taken
    the first is kept and a ``reference_label_collides`` warning says what to change.
    """
    if ref is None:
        return
    note, line, text, prefer_right = ref
    renderer = ctx.fig.canvas.get_renderer()
    frame = ax.get_window_extent(renderer)
    paths = _data_paths(ax, [line])
    taken = [
        t.get_window_extent(renderer)
        for t in [*avoid, *ax.texts, *ctx.fig.texts]
        if t is not None and t is not note and t.get_visible() and t.get_text()
    ]
    taken += [box for axis in (ax.xaxis, ax.yaxis) for _, box in _tick_label_boxes(axis, renderer)]
    sides = [prefer_right, not prefer_right]
    spots = [(right, above) for above in (True, False) for right in sides]
    y_value = note.xy[1]
    for right, above in spots:
        note.xy = (1.0 if right else 0.0, y_value)
        note.set_horizontalalignment("right" if right else "left")
        note.set_verticalalignment("bottom" if above else "top")
        note.set_position((-2.0 if right else 2.0, 2.5 if above else -2.5))
        box = note.get_window_extent(renderer)
        inside = (
            box.x0 >= frame.x0 - 1
            and box.x1 <= frame.x1 + 1
            and box.y0 >= frame.y0 - 1
            and box.y1 <= frame.y1 + 1
        )
        clear = not any(box.overlaps(other) for other in taken)
        free = not any(path.intersects_bbox(box, filled=False) for path in paths)
        if inside and clear and free:
            return
    right, above = spots[0]
    note.xy = (1.0 if right else 0.0, y_value)
    note.set_horizontalalignment("right" if right else "left")
    note.set_verticalalignment("bottom")
    note.set_position((-2.0 if right else 2.0, 2.5))
    ctx.issues.append(
        _issue(
            "reference_label_collides",
            "warning",
            f"The reference label {text!r} covers a line or another label wherever it is "
            "placed in this panel.",
            "Shorten the reference label (one or two words), move the detail to note=, or "
            'give the panel a full-width row with layout=[["a"], ["b"]].',
            panel=ctx.key,
        )
    )


def _reorder_band(band: Any, order: np.ndarray, n: int) -> Any:
    """Apply the x sort to a band given in any accepted form (numbers stay as they are)."""

    def _one(entry: Any) -> Any:
        if _is_number(entry):
            return entry
        try:
            arr = np.asarray(
                [[np.nan if v is None else float(v) for v in part] for part in entry]
                if not isinstance(entry, np.ndarray)
                else entry,
                dtype=float,
            )
        except (TypeError, ValueError):
            try:
                arr = np.asarray([np.nan if v is None else float(v) for v in entry], dtype=float)
            except (TypeError, ValueError):
                return entry  # reported by _trend_bands
        if arr.ndim == 2 and arr.shape == (2, n):
            return arr[:, order]
        if arr.ndim == 1 and arr.size == n:
            return arr[order]
        return entry

    if _has_items(band) and not _is_one_dimensional(band):
        return {k: _one(v) for k, v in _pairs(band)}
    return _one(band)


# --------------------------------------------------------------------------- #
# change (slopegraph)
# --------------------------------------------------------------------------- #


@_guarded("change")
def change(
    before: Mapping[str, float],
    after: Mapping[str, float],
    *,
    labels: Sequence[str] = ("Before", "After"),
    title: str | None = None,
    label: str | None = None,
    unit: str | None = None,
    highlight: str | Sequence[str] | None = None,
    fmt: str | None = None,
) -> Panel:
    """What moved between two states? A slopegraph: one line per item, steepness is the change.

    ``before`` and ``after`` map the same item names to values on one scale.
    """
    left = _named_values(before, "change(before)")
    right = _named_values(after, "change(after)")
    if set(left) != set(right):
        missing = sorted(set(left) ^ set(right))
        raise ExplainError(
            f"change() needs the same items before and after; unmatched: {missing[:6]!r}.",
            fix_hint="Drop items that lack one of the two values, and say so in `note`.",
        )
    if isinstance(labels, (str, bytes)) or len(labels) != 2:
        raise ExplainError(
            "change(labels) needs exactly two names.", fix_hint='e.g. ("2024", "2025").'
        )
    labels = (str(labels[0]), str(labels[1]))
    names = sorted(right, key=lambda nm: right[nm], reverse=True)
    if len(names) > 14:
        raise ExplainError(
            f"change() got {len(names)} items; a slopegraph tangles beyond about 14.",
            fix_hint="Keep the items the takeaway is about, or use compare() on the differences.",
            rule="too_many_items",
        )
    hl = _names(highlight, names)
    fmt_fn = _formatter([*left.values(), *right.values()], fmt, unit=unit)
    deltas = {nm: right[nm] - left[nm] for nm in names}
    delta_fmt = _formatter(list(deltas.values()), fmt, unit=unit)

    def _delta_text(name: str) -> str:
        return _signed(delta_fmt(deltas[name]))

    biggest = max(names, key=lambda nm: abs(deltas[nm]))
    ups = sum(1 for d in deltas.values() if d > 0)
    downs = sum(1 for d in deltas.values() if d < 0)
    facts = [
        (
            f"largest change: {biggest} {fmt_fn(left[biggest])} \N{RIGHTWARDS ARROW} "
            f"{_with_unit(fmt_fn(right[biggest]), unit)} ({_delta_text(biggest)})"
        ),
        f"{ups} up, {downs} down, {len(names) - ups - downs} unchanged",
    ]
    for name in hl:
        if name != biggest:
            facts.append(
                f"{name}: {fmt_fn(left[name])} \N{RIGHTWARDS ARROW} "
                f"{_with_unit(fmt_fn(right[name]), unit)} ({_delta_text(name)})"
            )

    def _draw(ctx: _Ctx, ax: Axes) -> Callable[[], None]:
        sz = ctx.sizes
        theme = ctx.theme
        accent = {name: col for name, col in ctx.colors.items() if name in names}
        focus_mode = bool(hl or accent)
        effects = ctx.line_effects()
        _bare_axes(ax)
        ax.xaxis.set_visible(False)
        ax.yaxis.set_visible(False)
        values = [*left.values(), *right.values()]
        lo, hi = min(values), max(values)
        span = (hi - lo) or abs(hi) or 1.0
        ax.set_xlim(0.0, 1.0)
        ax.set_ylim(lo - 0.05 * span, hi + 0.05 * span)
        rail_col = theme.grid if theme.grid_style != "none" else theme.context_line
        ax.vlines([0.0, 1.0], lo, hi, color=rail_col, linewidth=0.7, zorder=1)
        for x_at, text, color in ((0.0, labels[0], theme.muted), (1.0, labels[1], theme.ink)):
            ax.annotate(
                _plain(text, theme),
                (x_at, 1.0),
                xycoords=("data", "axes fraction"),
                xytext=(0.0, 5.0),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=sz.small,
                fontweight="bold",
                color=color,
                annotation_clip=False,
            )
        left_notes, right_notes = [], []
        for name in names:
            focus = name in accent
            col = accent.get(name, theme.axis if not focus_mode else theme.context_line)
            line_kw: dict[str, Any] = {
                "color": col,
                "linewidth": (
                    (theme.line_lw + 0.1 if focus else theme.context_line_lw + 0.1) * sz.scale
                ),
                "marker": "o",
                "markersize": (3.6 if focus else 3.0) * sz.scale,
                "markerfacecolor": col,
                "markeredgecolor": theme.background,
                "markeredgewidth": 0.6,
                "zorder": 4 if focus else 2,
                "clip_on": False,
                "label": "_slope",
                "solid_capstyle": theme.line_capstyle,
            }
            if effects is not None:
                line_kw["path_effects"] = effects
            ax.plot([0.0, 1.0], [left[name], right[name]], **line_kw)
            text_color = ctx.text_color(col) if focus else theme.ink
            weight = "bold" if focus else "normal"
            left_notes.append(
                ax.annotate(
                    _plain(fmt_fn(left[name]), theme),
                    (0.0, left[name]),
                    xytext=(-6.0, 0.0),
                    textcoords="offset points",
                    ha="right",
                    va="center",
                    fontsize=sz.small,
                    color=text_color if focus else theme.muted,
                    fontweight=weight,
                    annotation_clip=False,
                )
            )
            right_notes.append(
                ax.annotate(
                    _plain(f"{fmt_fn(right[name])}  {name} ({_delta_text(name)})", theme),
                    (1.0, right[name]),
                    xytext=(6.0, 0.0),
                    textcoords="offset points",
                    ha="left",
                    va="center",
                    fontsize=sz.small,
                    color=text_color,
                    fontweight=weight,
                    annotation_clip=False,
                )
            )

        def _finish() -> None:
            renderer = ctx.fig.canvas.get_renderer()
            box = ax.get_window_extent(renderer)
            k = ctx.pt_per_px
            for notes, x_at, source, dx in (
                (left_notes, 0.0, left, -6.0),
                (right_notes, 1.0, right, 6.0),
            ):
                ys = np.array([ax.transData.transform((x_at, source[nm]))[1] * k for nm in names])
                placed = _relax_positions_pt(ys, sz.small * 1.22, box.y0 * k, box.y1 * k)
                for note, y0, y1 in zip(notes, ys, placed, strict=True):
                    note.set_position((dx, float(y1 - y0)))

        return _finish

    def _narrow(ctx: _Ctx, ax: Axes, rect: Bbox) -> list[tuple[Axes, Bbox]]:
        """A slopegraph reads by steepness, so it never spans a full-width row."""
        limit = 92.0 * ctx.sizes.scale * float(ctx.fig.dpi) / 25.4
        return [(ax, Bbox.from_extents(rect.x0, rect.y0, min(rect.x1, rect.x0 + limit), rect.y1))]

    return Panel(
        kind="change",
        title=title,
        label=label,
        unit=unit,
        spec=_base_spec(
            title,
            label,
            unit,
            before=dict(left),
            after=dict(right),
            labels=list(labels),
            highlight=hl or None,
            fmt=fmt,
        ),
        facts=facts,
        describe=f"Slopegraph of {label or 'values'} for {len(names)} items, {labels[0]} to {labels[1]}",
        _height_mm=lambda _w, _m, _s, _t: max(38.0, 4.6 * len(names) + 12.0),
        _frames=_narrow,
        _draw=_draw,
        color_items=tuple(names),
        color_focus=tuple(hl),
        color_mode="highlight" if hl else "uniform",
        uses_default=False,  # without highlight every slope is the same neutral grey
    )


# --------------------------------------------------------------------------- #
# distribution
# --------------------------------------------------------------------------- #


@_guarded("distribution")
def distribution(
    groups: Mapping[str, Sequence[float]] | Sequence[float],
    *,
    title: str | None = None,
    label: str | None = None,
    unit: str | None = None,
    highlight: str | Sequence[str] | None = None,
    reference: float | tuple[float, str] | None = None,
    log: bool = False,
    stat: str = "median",
    fmt: str | None = None,
) -> Panel:
    """How are values spread within groups? Every observation as a dot, with a centre and spread.

    ``groups`` maps a group name to its raw observations (not pre-aggregated
    means): showing the points is what distinguishes this from compare().
    ``stat="median"`` (default) marks the median and the middle half (IQR);
    ``stat="mean"`` marks the mean and \N{PLUS-MINUS SIGN} 1 standard deviation.
    """
    if stat not in {"median", "mean"}:
        raise ExplainError(
            f"distribution(stat={stat!r}) is not a summary this form draws.",
            fix_hint='Use stat="median" (median and middle half) or stat="mean" (mean and '
            "\N{PLUS-MINUS SIGN} 1 s.d.).",
        )
    if _has_items(groups) and not _is_one_dimensional(groups):
        raw = {str(k): v for k, v in _pairs(groups)}
    elif isinstance(groups, (str, bytes)) or _is_number(groups) or groups is None:
        raise ExplainError(
            "distribution(groups) must map group names to lists of observations.",
            fix_hint='e.g. {"control": [4.1, 3.9, 4.4, ...], "treated": [...]}.',
        )
    else:
        raw = {"": groups}
    data: dict[str, np.ndarray] = {}
    dropped: dict[str, int] = {}
    given: dict[str, np.ndarray] = {}
    for name, values in raw.items():
        if _is_number(values) or values is None or isinstance(values, (str, bytes)):
            raise ExplainError(
                f"distribution(groups[{name!r}]) is {values!r}, not a list of observations.",
                fix_hint="distribution() shows raw observations; for one summary number per "
                "group use compare() (with error= for an interval).",
            )
        arr = _values_array(values, f"distribution(groups[{name!r}])")
        given[name] = arr
        dropped[name] = int((~np.isfinite(arr)).sum())
        arr = arr[np.isfinite(arr)]
        if arr.size < 3:
            raise ExplainError(
                f"distribution(groups[{name!r}]) has {arr.size} finite values; a spread needs >= 3.",
                fix_hint="Use compare() for one or two values per item.",
            )
        data[name] = arr
    if not data:
        raise ExplainError("distribution(groups) is empty.", fix_hint="Pass at least one group.")
    names = list(data)
    if len(names) > MAX_GROUPS:
        raise ExplainError(
            f"distribution() got {len(names)} groups; more than {MAX_GROUPS} rows of dots blur together.",
            fix_hint="Keep the groups the takeaway compares, or compare() their medians.",
            rule="too_many_items",
        )
    hl = _names(highlight, names)
    ref = _reference_line(reference, "distribution(reference)")
    everything = np.concatenate(list(data.values()))
    if log and (everything.min() <= 0 or (ref is not None and ref[0] <= 0)):
        raise ExplainError(
            "distribution(log=True) needs strictly positive values.",
            fix_hint="Drop log=True or remove non-positive values.",
        )
    if stat == "mean":
        stats = {}
        for nm, arr in data.items():
            m, sd = float(arr.mean()), float(arr.std(ddof=1))
            stats[nm] = (m - sd, m, m + sd)
    else:
        stats = {
            nm: tuple(float(q) for q in np.percentile(arr, [25, 50, 75]))
            for nm, arr in data.items()
        }
    fmt_fn = _formatter([q for trio in stats.values() for q in trio], fmt, unit=unit, log=log)
    facts = []
    for nm in names:
        lo_q, mid, hi_q = stats[nm]
        spread = (
            f"\N{PLUS-MINUS SIGN} 1 s.d. {fmt_fn(lo_q)}\N{EN DASH}{fmt_fn(hi_q)}"
            if stat == "mean"
            else f"middle half {fmt_fn(lo_q)}\N{EN DASH}{fmt_fn(hi_q)}"
        )
        text = (
            f"{nm or (label or 'values')}: {stat} {_with_unit(fmt_fn(mid), unit)}, {spread}, "
            f"n={data[nm].size}"
        )
        if dropped[nm]:
            text += f"; {dropped[nm]} missing value{'s' if dropped[nm] > 1 else ''} dropped"
        facts.append(text)
    caution = _small_n_caution(
        {nm or (label or "values"): data[nm].size for nm in names},
        "quartiles are not meaningful" if stat == "median" else "the s.d. is a rough estimate",
    )
    if caution:
        facts.append(caution)
    if hl and log:
        # On a log axis groups differ by factors: state ratios, not differences.
        for h in hl:
            for other in names:
                if other != h:
                    ratio = _ratio_text(stats[h][1] / stats[other][1])
                    facts.append(f"{h} is {ratio} {other} ({stat})")
    elif hl:
        diffs = [
            (h, other, stats[h][1] - stats[other][1]) for h in hl for other in names if other != h
        ]
        diff_fmt = _formatter([d for _, _, d in diffs], fmt, unit=unit)
        for h, other, d in diffs:
            shown = _diff_with_unit(_signed(diff_fmt(d)), unit)
            facts.append(f"{h} \N{MINUS SIGN} {other}: {stat} {shown}")
    any_spread = any(a.size >= 5 for a in data.values())

    def _draw(ctx: _Ctx, ax: Axes) -> Callable[[], None] | None:
        sz = ctx.sizes
        theme = ctx.theme
        accent = {name: col for name, col in ctx.colors.items() if name in names}
        n = len(names)
        if log:
            ax.set_xscale("log")
        _value_axis(ax, sz, theme, axis="x", nbins=5 if ctx.cell_width_mm >= 100 else 3)
        ax.spines["left"].set_visible(False)
        ax.spines["bottom"].set_visible(False)
        if theme.grid_style != "none" and theme.grid_lw > 0:
            ax.grid(
                axis="x",
                color=theme.grid,
                linestyle=theme.grid_style,
                linewidth=theme.grid_lw,
            )
            ax.grid(axis="y", visible=False)
        ax.set_ylim(n - 0.45, -0.6)
        lo, hi = float(everything.min()), float(everything.max())
        if ref is not None:
            lo, hi = min(lo, ref[0]), max(hi, ref[0])
        if log:
            ax.set_xlim(
                *_narrow_log_ticks(
                    ax.xaxis, lo / 1.12, hi * 1.12, theme.minus_sign, extend=False, data_hi=hi
                )
            )
        else:
            span = (hi - lo) or abs(hi) or 1.0
            ax.set_xlim(lo - 0.04 * span, hi + 0.04 * span)
            # The value axis covers every dot (re-checked after tick thinning).
            ax._figmint_cover = (lo, hi)  # type: ignore[attr-defined]
            # After layout: >= 3 round ticks bracketing every dot (_bracket_with_ticks).
            ax._figmint_bracket = (  # type: ignore[attr-defined]
                lo,
                hi,
                6 if ctx.cell_width_mm >= 100 else 4,
                theme.minus_sign,
            )
            _cover_with_ticks(ax.xaxis, lo, hi)
        ax.set_yticks(range(n), [""] * n)
        ax.tick_params(axis="y", length=0)
        ax.annotate(
            stat,
            (1.0, 1.0),
            xycoords="axes fraction",
            xytext=(6.0, 2.5),
            textcoords="offset points",
            ha="left",
            va="bottom",
            fontsize=sz.small,
            color=theme.muted,
            annotation_clip=False,
        )
        rng = np.random.default_rng(0)
        for row, name in enumerate(names):
            arr = data[name]
            col = accent.get(name, theme.context_line if (hl or accent) else ctx.default_color)
            shown = arr if arr.size <= 600 else rng.choice(arr, size=600, replace=False)
            alpha = 0.8 if shown.size <= 30 else (0.5 if shown.size <= 150 else 0.28)
            jitter = rng.uniform(-0.2, 0.2, size=shown.size)
            ax.scatter(
                shown,
                row + jitter,
                s=(3.4 * sz.scale) ** 2,
                color=col,
                alpha=alpha,
                linewidth=0,
                zorder=2,
            )
            q1, med, q3 = stats[name]
            if log:
                q1 = max(q1, ax.get_xlim()[0])
            # Summary through the dot row: a thin line for the middle half (or +/- 1 s.d.)
            # and a taller tick for the centre, haloed so it reads over the dots. With
            # fewer than five observations quartiles and s.d. mean little: the centre
            # tick only.
            halo = [
                patheffects.withStroke(
                    linewidth=2.6 * sz.scale, foreground=theme.background, alpha=0.9
                )
            ]
            if arr.size >= 5:
                ax.hlines(
                    row,
                    q1,
                    q3,
                    color=theme.ink,
                    linewidth=1.0 * sz.scale,
                    zorder=4,
                    path_effects=halo,
                )
            ax.vlines(
                med,
                row - 0.3,
                row + 0.3,
                color=theme.ink,
                linewidth=2.0 * sz.scale,
                zorder=5,
                path_effects=halo,
            )
            for text, dy, va, size, color, weight in (
                (name, 0.5, "bottom", sz.body, theme.ink, "bold" if name in accent else "normal"),
                (f"n={arr.size}", -1.5, "top", sz.foot, theme.muted, "normal"),
            ):
                ax.annotate(
                    _plain(text, theme),
                    (0.0, row),
                    xycoords=("axes fraction", "data"),
                    xytext=(-7.0, dy),
                    textcoords="offset points",
                    ha="right",
                    va=va,
                    fontsize=size,
                    color=color,
                    fontweight=weight,
                    annotation_clip=False,
                )
            value = (
                _with_unit(fmt_fn(med), unit) if (row == 0 or _inline_unit(unit)) else fmt_fn(med)
            )
            ax.annotate(
                _plain(value, theme),
                (1.0, row),
                xycoords=("axes fraction", "data"),
                xytext=(6.0, 0.0),
                textcoords="offset points",
                ha="left",
                va="center",
                fontsize=sz.small,
                color=theme.ink,
                fontweight="bold" if name in accent else "normal",
                annotation_clip=False,
            )
        if ref is not None:
            ax.axvline(ref[0], color=theme.ink, linewidth=0.7, linestyle=(0, (3, 2)), zorder=3)
            if ref[1]:
                note = ax.annotate(
                    _plain(ref[1], theme),
                    (ref[0], 1.0),
                    xycoords=("data", "axes fraction"),
                    xytext=(0.0, 2.5),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=sz.small,
                    color=theme.muted,
                    annotation_clip=False,
                )
                return lambda: _keep_inside_x(ctx, ax, note)
        return None

    return Panel(
        kind="distribution",
        title=title,
        label=label,
        unit=unit,
        spec=_base_spec(
            title,
            label,
            unit,
            groups=_jsonable(given.get("", given)),
            highlight=hl or None,
            reference=list(ref) if ref else None,
            log=log or None,
            stat=stat if stat != "median" else None,
            fmt=fmt,
        ),
        facts=facts,
        describe=(
            f"Dot strips of {label or 'values'}"
            + (f" ({unit})" if unit else "")
            + f" for {len(names)} group(s), each with "
            + (
                f"a {stat} tick"
                if not any_spread
                else "a mean tick and a \N{PLUS-MINUS SIGN} 1 s.d. line"
                if stat == "mean"
                else "a median tick and a line over the middle half (interquartile range)"
            )
        ),
        _height_mm=lambda _w, _m, _s, _t: 8.5 * len(names) + 11.0,
        _draw=_draw,
        # The spread line is drawn only for groups with n >= 5: caption it only then.
        measure_note=(
            f"tick: {stat}"
            if not any_spread
            else (
                "tick: mean; line: \N{PLUS-MINUS SIGN} 1 s.d."
                if stat == "mean"
                else "tick: median; line: middle half"
            )
            + (
                ""
                if all(a.size >= 5 for a in data.values())
                else " (n \N{GREATER-THAN OR EQUAL TO} 5)"
            )
        ),
        color_items=tuple(nm for nm in names if nm),
        color_focus=tuple(hl),
        color_mode="highlight" if hl else "uniform",
        uses_default=not hl,
    )


# --------------------------------------------------------------------------- #
# relate
# --------------------------------------------------------------------------- #


def _small_n_caution(sizes: Mapping[str, int], what: str) -> str | None:
    """One caution for every group with fewer than five observations (never one per group)."""
    small = {nm: n for nm, n in sizes.items() if n < 5}
    if not small:
        return None
    counts = set(small.values())
    if len(small) == len(sizes) and len(counts) == 1:
        if len(sizes) == 1:
            return f"n = {next(iter(counts))}: {what}"
        return f"every group has n = {next(iter(counts))}: {what}"
    listed = ", ".join(f"{nm} (n = {n})" for nm, n in small.items())
    return f"n < 5 in {listed}: {what}"


def _line_text(slope: float, intercept: float, x_name: str, y_name: str) -> str:
    """``y = 2.1·x + 3.4`` with Unicode minus and three significant figures."""
    sign = "\N{MINUS SIGN}" if intercept < 0 else "+"
    return f"{y_name} = {_sig_text(slope)}\N{MIDDLE DOT}{x_name} {sign} {_sig_text(abs(intercept))}"


def _strength(r: float) -> str:
    return (
        "no"
        if not math.isfinite(r) or abs(r) < 0.2
        else "weak"
        if abs(r) < 0.5
        else "moderate"
        if abs(r) < 0.8
        else "strong"
    )


def _r_text(r: float) -> str:
    return _clean_sign(f"{r:.2f}") if math.isfinite(r) else "n/a"


@_guarded("relate")
def relate(
    x: Sequence[float],
    y: Sequence[float],
    *,
    x_label: str,
    y_label: str,
    title: str | None = None,
    names: Sequence[str] | None = None,
    groups: Sequence[str] | None = None,
    highlight: str | Sequence[str] | None = None,
    fit: bool = False,
    log_x: bool = False,
    log_y: bool = False,
    reference: float | tuple[float, str] | None = None,
) -> Panel:
    """Do two measures move together? A scatter with both axes named.

    ``names`` labels the points so ``highlight`` can call out up to three of
    them. ``groups`` gives each point a group (at most four), coloured and
    labelled on the plot; ``highlight`` may then name a group. ``fit=True``
    adds a least-squares line (one per group) and reports r, n, slope and
    intercept computed from the data (in log space on log axes).
    ``reference=(value, "label")`` draws a horizontal line at that y.
    """
    if not x_label or not y_label:
        raise ExplainError(
            "relate() needs x_label and y_label.",
            fix_hint='Name both measures with their units, e.g. x_label="Batch size", '
            'y_label="Throughput (req/s)".',
        )
    xs = _values_array(x, "relate(x)")
    ys = _values_array(y, "relate(y)")
    if xs.shape != ys.shape or xs.ndim != 1:
        raise ExplainError(
            f"relate() got {xs.size} x values and {ys.size} y values.",
            fix_hint="Pass two equal-length lists of numbers.",
        )
    keep = np.isfinite(xs) & np.isfinite(ys)
    n_dropped = int((~keep).sum())
    point_names = [str(nm) for nm in names] if names is not None else None
    if point_names is not None and len(point_names) != xs.size:
        raise ExplainError(
            "relate(names) must have one name per point.",
            fix_hint="Pass names aligned with x and y, or omit names.",
        )
    point_groups = [str(g) for g in groups] if groups is not None else None
    if point_groups is not None and len(point_groups) != xs.size:
        raise ExplainError(
            "relate(groups) must have one group label per point.",
            fix_hint='Pass groups aligned with x and y, e.g. groups=["A", "A", "B", ...].',
        )
    group_names = list(dict.fromkeys(point_groups)) if point_groups is not None else []
    if len(group_names) > MAX_COLORED_SERIES:
        raise ExplainError(
            f"relate(groups) has {len(group_names)} groups; more than {MAX_COLORED_SERIES} "
            "colours cannot be told apart or held in mind.",
            fix_hint="Merge groups so at most 4 remain, or split the figure into panels with "
            "one relate() per group.",
            rule="too_many_series",
        )
    hl_groups: list[str] = []
    hl: list[str] = []
    if highlight is not None:
        wanted = [highlight] if isinstance(highlight, str) else [str(h) for h in highlight]
        if group_names and all(h in group_names for h in wanted):
            hl_groups = _names(wanted, group_names, "relate(highlight)")
        elif point_names is None:
            raise ExplainError(
                "relate(highlight) needs names= (or groups=) to know which points to call out.",
                fix_hint="Pass names=[...] aligned with x and y, or name a group from groups=.",
            )
        else:
            hl = _names(wanted, point_names, "relate(highlight)")
    ref = _reference_line(reference, "relate(reference)")
    spec_points = {
        "x": _jsonable(xs),
        "y": _jsonable(ys),
        "names": point_names,
        "groups": point_groups,
    }
    xs, ys = xs[keep], ys[keep]
    if point_names is not None:
        point_names = [nm for nm, ok in zip(point_names, keep, strict=True) if ok]
    if point_groups is not None:
        point_groups = [g for g, ok in zip(point_groups, keep, strict=True) if ok]
    if xs.size < 3:
        raise ExplainError(
            f"relate() has {xs.size} complete points; a relationship needs >= 3.",
            fix_hint="Use compare() for a couple of items.",
        )
    if (log_x and xs.min() <= 0) or (log_y and ys.min() <= 0):
        raise ExplainError(
            "relate() log axes need strictly positive values.",
            fix_hint="Drop log_x/log_y or remove non-positive points.",
        )
    if log_y and ref is not None and ref[0] <= 0:
        raise ExplainError(
            "relate(reference) must be positive on a log y axis.",
            fix_hint="Drop the reference or log_y=True.",
        )
    fx = np.log10(xs) if log_x else xs
    fy = np.log10(ys) if log_y else ys

    def _fit(mask: np.ndarray) -> tuple[float, float, float]:
        gx, gy = fx[mask], fy[mask]
        if gx.size < 2:
            return float("nan"), float("nan"), float("nan")
        r_val = (
            float(np.corrcoef(gx, gy)[0, 1]) if np.ptp(gx) > 0 and np.ptp(gy) > 0 else float("nan")
        )
        if np.ptp(gx) > 0:
            m, b = np.polyfit(gx, gy, 1)
            return r_val, float(m), float(b)
        return r_val, float("nan"), float("nan")

    everyone = np.ones(xs.size, bool)
    r, slope, intercept = _fit(everyone)
    strength = _strength(r)
    direction = "" if strength == "no" else (" positive" if r > 0 else " negative")
    space = " in log space" if (log_x or log_y) else ""
    facts = [
        f"Pearson r = {_r_text(r)} (n = {xs.size}): {strength}{direction} linear relationship"
        + space
    ]
    x_sym = "log\N{SUBSCRIPT ONE}\N{SUBSCRIPT ZERO}(x)" if log_x else "x"
    y_sym = "log\N{SUBSCRIPT ONE}\N{SUBSCRIPT ZERO}(y)" if log_y else "y"
    group_masks = {
        g: np.array([pg == g for pg in point_groups], dtype=bool)  # type: ignore[union-attr]
        for g in group_names
    }
    group_fits = {g: _fit(mask) for g, mask in group_masks.items()}
    if fit and not group_names and math.isfinite(slope):
        facts.append(
            f"fitted line{space}: {_line_text(slope, intercept, x_sym, y_sym)}"
            + (f" (x = {x_label}, y = {y_label})" if not space else "")
        )
    for g in group_names:
        g_r, g_m, g_b = group_fits[g]
        text = f"{g}: r = {_r_text(g_r)}, n = {int(group_masks[g].sum())}"
        if fit and math.isfinite(g_m):
            text += f"; fitted line{space}: {_line_text(g_m, g_b, x_sym, y_sym)}"
        facts.append(text)
    if group_names:
        caution = _small_n_caution(
            {g: int(group_masks[g].sum()) for g in group_names},
            "r is a rough estimate" + (" and so is the fitted line" if fit else ""),
        )
        if caution:
            facts.append(caution)
    if n_dropped:
        facts.append(
            f"{n_dropped} point{'s' if n_dropped > 1 else ''} with a missing value dropped"
        )
    issues: list[dict[str, Any]] = []
    if fit and group_names:
        # One line per group: judge each drawn fit, and warn only when none is strong
        # enough to carry a line (a flat fit next to a steep one is often the finding).
        drawn = {g: group_fits[g][0] for g in group_names if math.isfinite(group_fits[g][1])}
        if drawn and all(_strength(g_r) in {"no", "weak"} for g_r in drawn.values()):
            listed = ", ".join(f"{g} r = {_r_text(g_r)}" for g, g_r in drawn.items())
            issues.append(
                _issue(
                    "fit_on_weak_relationship",
                    "warning",
                    f"fit=True draws a line through a weak relationship in every group ({listed}).",
                    "Drop fit=True, or say in the title that the relationship is weak.",
                )
            )
    elif fit and strength in {"no", "weak"}:
        issues.append(
            _issue(
                "fit_on_weak_relationship",
                "warning",
                f"fit=True draws a line through a {strength} relationship (r = {_r_text(r)}).",
                "Drop fit=True, or say in the title that the relationship is weak.",
            )
        )

    def _draw(ctx: _Ctx, ax: Axes) -> Callable[[], None] | None:
        sz = ctx.sizes
        theme = ctx.theme
        effects = ctx.line_effects()
        if theme.hide_spines:
            for spine in ax.spines.values():
                spine.set_visible(False)
            if theme.grid_style != "none" and theme.grid_lw > 0:
                ax.grid(
                    axis="both",
                    color=theme.grid,
                    linestyle=theme.grid_style,
                    linewidth=theme.grid_lw,
                )
        else:
            for name in ("top", "right"):
                ax.spines[name].set_visible(False)
            if theme.inline_y_ticks:
                ax.spines["left"].set_visible(False)
                ax.spines["bottom"].set_color(theme.axis)
                ax.spines["bottom"].set_linewidth(theme.axis_lw)
                ax.grid(
                    axis="y",
                    color=theme.grid,
                    linestyle=theme.grid_style,
                    linewidth=theme.grid_lw,
                )
            else:
                for name in ("left", "bottom"):
                    ax.spines[name].set_color(theme.axis)
                    ax.spines[name].set_linewidth(theme.axis_lw)
                ax.grid(False)
        ax.set_axisbelow(True)
        if log_x:
            ax.set_xscale("log")
        if log_y:
            ax.set_yscale("log")
        ax.tick_params(
            length=theme.tick_length,
            width=theme.tick_width,
            color=theme.axis,
            labelsize=sz.small,
            labelcolor=theme.muted,
        )
        if theme.inline_y_ticks:
            ax.tick_params(axis="y", length=0)
        minus = theme.minus_sign
        for axis, is_log in ((ax.xaxis, log_x), (ax.yaxis, log_y)):
            if not is_log:
                axis.set_major_locator(MaxNLocator(nbins=5, steps=[1, 2, 2.5, 5, 10]))
                axis.set_major_formatter(
                    FuncFormatter(lambda v, _p, m=minus, a=axis: _tick_label(v, m, a))
                )
        ax.set_xlabel(_plain(x_label, theme), fontsize=sz.small, color=theme.muted, labelpad=3)
        alpha = 0.9 if xs.size <= 40 else (0.6 if xs.size <= 250 else 0.32)
        # Points called out: highlighted names, or (without highlight) names coloured
        # elsewhere in the figure, so a point keeps its entity's colour.
        called = list(hl)
        if not hl and not group_names and point_names:
            called = [nm for nm in dict.fromkeys(point_names) if nm in ctx.colors]
        is_focus = (
            np.array([(nm in called) for nm in point_names])
            if point_names
            else np.zeros(xs.size, bool)
        )
        group_color: dict[str, str] = {}
        if group_names:
            if hl_groups:
                for i, g in enumerate(hl_groups):
                    group_color[g] = ctx.colors.get(g, theme.accent_colors[i])
                for g in group_names:
                    group_color.setdefault(g, theme.axis)
            else:
                for i, g in enumerate(group_names):
                    group_color[g] = ctx.colors.get(g, theme.series_colors[i])
            order = [g for g in group_names if g not in hl_groups] + hl_groups
            for g in order:
                mask = group_masks[g] & ~is_focus
                focus_group = not hl_groups or g in hl_groups
                ax.scatter(
                    xs[mask],
                    ys[mask],
                    s=(4.0 * sz.scale) ** 2,
                    color=group_color[g],
                    alpha=alpha if focus_group else min(alpha, 0.6),
                    edgecolor=theme.background,
                    linewidth=0.4,
                    zorder=3 if focus_group else 2,
                )
        else:
            base_color = theme.axis if called else ctx.default_color
            ax.scatter(
                xs[~is_focus],
                ys[~is_focus],
                s=(4.0 * sz.scale) ** 2,
                color=base_color,
                alpha=alpha,
                edgecolor=theme.background,
                linewidth=0.4,
                zorder=2,
            )
        if ref is not None:
            ax.axhline(ref[0], color=theme.ink, linewidth=0.7, linestyle=(0, (3, 2)), zorder=2)
            if ref[1]:
                ax.annotate(
                    _plain(ref[1], theme),
                    (0.0, ref[0]),
                    xycoords=("axes fraction", "data"),
                    xytext=(2.0, 2.5),
                    textcoords="offset points",
                    ha="left",
                    va="bottom",
                    fontsize=sz.small,
                    color=theme.muted,
                    bbox=ctx.halo_bbox(0.1),
                )
        ax.autoscale_view()
        for axis, is_log in ((ax.xaxis, log_x), (ax.yaxis, log_y)):
            if is_log:
                lo_v, hi_v = sorted(axis.get_view_interval())
                data_hi = float((xs if axis is ax.xaxis else ys).max())
                if axis is ax.yaxis and ref is not None:
                    data_hi = max(data_hi, ref[0])
                lims = _narrow_log_ticks(axis, lo_v, hi_v, minus, extend=False, data_hi=data_hi)
                (ax.set_xlim if axis is ax.xaxis else ax.set_ylim)(*lims)

        def _fit_line(mask: np.ndarray, m: float, b: float, color: str, z: int) -> None:
            gx = np.linspace(fx[mask].min(), fx[mask].max(), 50)
            gy = m * gx + b
            fit_kw: dict[str, Any] = {
                "color": color,
                "linewidth": 0.9 * sz.scale,
                "zorder": z,
                "label": "_fit",
            }
            if effects is not None:
                fit_kw["path_effects"] = effects
            ax.plot(10**gx if log_x else gx, 10**gy if log_y else gy, **fit_kw)

        if fit and not group_names and math.isfinite(slope):
            _fit_line(everyone, slope, intercept, theme.ink, 3)
            ax.annotate(
                _plain(f"r = {_r_text(r)}, n = {xs.size}", theme),
                (0.0 if r < 0 else 1.0, 0.0),
                xycoords="axes fraction",
                xytext=(5.0 if r < 0 else -5.0, 5.0),
                textcoords="offset points",
                ha="left" if r < 0 else "right",
                va="bottom",
                fontsize=sz.small,
                color=theme.muted,
                bbox=ctx.halo_bbox(0.15, alpha=0.9),
            )
        for i, name in enumerate(called):
            idx = point_names.index(name)  # type: ignore[union-attr]
            col = ctx.colors.get(name, theme.accent_colors[i % len(theme.accent_colors)])
            ax.scatter(
                [xs[idx]],
                [ys[idx]],
                s=(5.4 * sz.scale) ** 2,
                color=col,
                edgecolor=theme.background,
                linewidth=0.7,
                zorder=5,
            )
            right_half = (fx[idx] - fx.min()) > 0.62 * (np.ptp(fx) or 1.0)
            ax.annotate(
                _plain(name, theme),
                (xs[idx], ys[idx]),
                xytext=(-6.0 if right_half else 6.0, 5.0),
                textcoords="offset points",
                ha="right" if right_half else "left",
                va="bottom",
                fontsize=sz.small,
                fontweight="bold",
                color=ctx.text_color(col),
                zorder=6,
                bbox=ctx.halo_bbox(0.12),
            )
        if not group_names:
            return None

        # Group names sit at each group's right end (its fit line end when fitted).
        anchors: list[tuple[str, float, float, str, bool]] = []
        for g in group_names:
            mask = group_masks[g]
            _g_r, g_m, g_b = group_fits[g]
            focus_group = not hl_groups or g in hl_groups
            if fit and math.isfinite(g_m):
                _fit_line(mask, g_m, g_b, group_color[g], 4 if focus_group else 3)
                end_x = float(fx[mask].max())
                ax_x = 10**end_x if log_x else end_x
                end_y = g_m * end_x + g_b
                ax_y = 10**end_y if log_y else end_y
            else:
                idx = int(np.flatnonzero(mask)[int(np.argmax(fx[mask]))])
                ax_x, ax_y = float(xs[idx]), float(ys[idx])
            # Context groups keep a direct label in the muted colour, as grey context
            # lines in trend() do, so no cloud on the plot is left unidentified.
            anchors.append((g, ax_x, ax_y, group_color[g], focus_group))
        notes = [
            ax.annotate(
                _plain(g, theme),
                (px, py),
                xytext=(5.0, 0.0),
                textcoords="offset points",
                ha="left",
                va="center",
                fontsize=sz.small,
                fontweight="bold" if focus else "normal",
                color=ctx.text_color(col) if focus else theme.muted,
                zorder=6,
                bbox=ctx.halo_bbox(0.12),
                annotation_clip=False,
            )
            for g, px, py, col, focus in anchors
        ]

        def _finish() -> None:
            renderer = ctx.fig.canvas.get_renderer()
            box = ax.get_window_extent(renderer)
            k = ctx.pt_per_px
            ys_pt = np.array([ax.transData.transform((a[1], a[2]))[1] * k for a in anchors])
            placed = _relax_positions_pt(
                ys_pt, sz.small * 1.22, box.y0 * k + sz.small * 0.4, box.y1 * k - sz.small * 0.4
            )
            for note, y0, y1 in zip(notes, ys_pt, placed, strict=True):
                note.set_position((5.0, float(y1 - y0)))

        return _finish

    return Panel(
        kind="relate",
        title=title,
        label=y_label,
        unit=None,
        spec={
            "title": title,
            "x": spec_points["x"],
            "y": spec_points["y"],
            "x_label": x_label,
            "y_label": y_label,
            "names": spec_points["names"],
            "groups": spec_points["groups"],
            "highlight": (hl_groups or hl) or None,
            "fit": fit or None,
            "log_x": log_x or None,
            "log_y": log_y or None,
            "reference": list(ref) if ref else None,
        },
        facts=facts,
        describe=f"Scatter plot of {y_label} against {x_label}, {xs.size} points"
        + (f" in {len(group_names)} groups" if group_names else ""),
        issues=issues,
        _height_mm=lambda w, _m, _s, _t: min(62.0, max(40.0, 0.6 * w)),
        stretch=True,
        _draw=_draw,
        color_items=tuple(dict.fromkeys([*group_names, *(point_names or [])])),
        color_focus=tuple(hl_groups or [*group_names, *hl]),
        color_mode="highlight" if (hl_groups or hl) else ("series" if group_names else "uniform"),
        uses_default=not group_names and not hl,
    )


# --------------------------------------------------------------------------- #
# matrix
# --------------------------------------------------------------------------- #

_SEQ_STOPS = FIGMINT_THEME.seq_stops
_DIV_LOW = FIGMINT_THEME.div_low
_DIV_HIGH = FIGMINT_THEME.div_high
_DIV_MID = FIGMINT_THEME.div_mid


def _ramp(stops: Sequence[str], t: np.ndarray) -> np.ndarray:
    colors = np.array([to_rgb(c) for c in stops])
    pos = np.clip(t, 0.0, 1.0) * (len(stops) - 1)
    lower = np.floor(pos).astype(int).clip(0, len(stops) - 2)
    frac = (pos - lower)[..., None]
    return colors[lower] * (1 - frac) + colors[lower + 1] * frac


def _matrix_highlight(
    highlight: object, row_names: list[str], col_names: list[str]
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Cells ``(row, col)``, whole rows and whole columns named by ``matrix(highlight=...)``."""
    hint = (
        'Use highlight=("row name", "col name") for one cell, a list of such pairs, or a row '
        'or column name alone, e.g. highlight="Rust" or highlight=[("Rust", "perf"), "Go"].'
    )
    cells: list[tuple[int, int]] = []
    hl_rows: list[int] = []
    hl_cols: list[int] = []
    if highlight is None:
        return cells, hl_rows, hl_cols

    def _name(entry: object) -> None:
        key = str(entry)
        if key not in row_names and key not in col_names:
            raise ExplainError(
                f"matrix(highlight) names {key!r}, which is neither a row nor a column.",
                fix_hint=hint,
            )
        if key in row_names:
            hl_rows.append(row_names.index(key))
        if key in col_names:
            hl_cols.append(col_names.index(key))

    def _cell(pair: Sequence[Any]) -> None:
        r_name, c_name = str(pair[0]), str(pair[1])
        if r_name not in row_names or c_name not in col_names:
            raise ExplainError(
                f"matrix(highlight) cell ({r_name!r}, {c_name!r}) is not in rows/cols.",
                fix_hint="Use (row name, column name) pairs exactly as given. " + hint,
            )
        cells.append((row_names.index(r_name), col_names.index(c_name)))

    def _is_pair(entry: object) -> bool:
        return (
            isinstance(entry, (tuple, list))
            and len(entry) == 2
            and not any(isinstance(e, (list, tuple)) for e in entry)
        )

    if isinstance(highlight, (str, numbers.Number)):
        _name(highlight)
    elif (
        _is_pair(highlight)
        and str(highlight[0]) in row_names  # type: ignore[index]
        and str(highlight[1]) in col_names  # type: ignore[index]
    ):
        _cell(highlight)  # type: ignore[arg-type]
    elif isinstance(highlight, (list, tuple)):
        for entry in highlight:
            if _is_pair(entry):
                _cell(entry)  # type: ignore[arg-type]
            elif isinstance(entry, (str, numbers.Number)):
                _name(entry)
            else:
                raise ExplainError(
                    f"matrix(highlight) entry {entry!r} is not a (row, col) pair or a name.",
                    fix_hint=hint,
                )
    else:
        raise ExplainError(
            f"matrix(highlight) must be a pair, a list of pairs or a name, got "
            f"{type(highlight).__name__}.",
            fix_hint=hint,
        )
    total = len(cells) + len(set(hl_rows)) + len(set(hl_cols))
    if total > MAX_HIGHLIGHTS:
        raise ExplainError(
            f"matrix(highlight) marks {total} cells/rows/columns; more than {MAX_HIGHLIGHTS} "
            "highlights nothing.",
            fix_hint=f"Outline only the <= {MAX_HIGHLIGHTS} cells the takeaway names.",
            rule="too_many_highlights",
        )
    return cells, sorted(set(hl_rows)), sorted(set(hl_cols))


@_guarded("matrix")
def matrix(
    values: Sequence[Sequence[float | None]],
    *,
    rows: Sequence[str] | None = None,
    cols: Sequence[str] | None = None,
    title: str | None = None,
    label: str | None = None,
    unit: str | None = None,
    diverging: bool = False,
    center: float = 0.0,
    highlight: Any = None,
    fmt: str | None = None,
) -> Panel:
    """How do two categorical dimensions interact? A heat table: colour for the pattern, a number in every cell.

    ``values[i][j]`` belongs to ``rows[i]`` and ``cols[j]``; a pandas DataFrame
    supplies ``rows`` and ``cols`` from its index and columns. One hue runs
    light to dark; ``diverging=True`` uses two hues around ``center`` for signed
    data. ``highlight`` outlines cells: one ``(row, col)`` pair, a list of
    pairs, or a row or column name for the whole strip.
    """
    is_frame = hasattr(values, "columns") and hasattr(values, "index")
    if is_frame:
        rows = [str(r) for r in values.index] if rows is None else rows  # type: ignore[attr-defined]
        cols = [str(c) for c in values.columns] if cols is None else cols  # type: ignore[attr-defined]
        values = values.to_numpy().tolist() if hasattr(values, "to_numpy") else values  # type: ignore[attr-defined]
    if rows is None or cols is None:
        raise ExplainError(
            "matrix() needs rows= and cols= to name its rows and columns.",
            fix_hint='Pass rows=["r1", ...] and cols=["c1", ...] aligned with values, or pass a '
            "pandas DataFrame (its index and columns are used).",
        )
    if isinstance(rows, (str, bytes)) or isinstance(cols, (str, bytes)):
        raise ExplainError(
            "matrix(rows) and matrix(cols) must be lists of names.",
            fix_hint='e.g. rows=["Python", "Go"], cols=["bugfix", "docs"].',
        )
    try:
        grid = np.array(
            [
                [np.nan if v is None else _to_float(v, "matrix(values)") for v in row]
                for row in values
            ],
            dtype=float,
        )
    except (TypeError, ValueError) as exc:
        raise ExplainError(
            "matrix(values) must be a rectangular list of rows of numbers.",
            fix_hint="Pass values[i][j] for rows[i] and cols[j]; use None for empty cells.",
        ) from exc
    row_names, col_names = [str(r) for r in rows], [str(c) for c in cols]
    if grid.ndim != 2 or grid.shape != (len(row_names), len(col_names)):
        raise ExplainError(
            f"matrix(values) has shape {grid.shape} but there are {len(row_names)} rows and "
            f"{len(col_names)} cols.",
            fix_hint="values must have one inner list per row, each with one number per column.",
        )
    if len(row_names) > 16 or len(col_names) > 12:
        raise ExplainError(
            f"matrix() got {len(row_names)}x{len(col_names)} cells; beyond 16x12 the numbers "
            "stop being readable at chat size.",
            fix_hint="Aggregate or keep the rows/columns the takeaway is about.",
            rule="too_many_items",
        )
    finite = grid[np.isfinite(grid)]
    if finite.size == 0:
        raise ExplainError("matrix(values) has no finite cells.", fix_hint="Pass numbers.")
    cells, hl_rows, hl_cols = _matrix_highlight(highlight, row_names, col_names)

    fmt_fn = _formatter(list(finite), fmt, unit=unit)
    lo, hi = float(finite.min()), float(finite.max())

    hi_at = np.unravel_index(int(np.nanargmax(grid)), grid.shape)
    lo_at = np.unravel_index(int(np.nanargmin(grid)), grid.shape)
    facts = [
        (
            f"highest: {row_names[hi_at[0]]} \N{MULTIPLICATION SIGN} {col_names[hi_at[1]]} = "
            f"{_with_unit(fmt_fn(hi), unit)}"
        ),
        (
            f"lowest: {row_names[lo_at[0]]} \N{MULTIPLICATION SIGN} {col_names[lo_at[1]]} = "
            f"{_with_unit(fmt_fn(lo), unit)}"
        ),
    ]
    with np.errstate(all="ignore"):
        row_means = np.array(
            [float(np.mean(r[np.isfinite(r)])) if np.isfinite(r).any() else np.nan for r in grid]
        )
    mean_fmt = _formatter(list(row_means[np.isfinite(row_means)]), fmt, unit=unit)
    facts.append(
        f"highest row mean: {row_names[int(np.nanargmax(row_means))]} "
        f"({_with_unit(mean_fmt(float(np.nanmax(row_means))), unit)})"
    )
    if row_names == col_names and len(row_names) > 1:
        off = grid.copy()
        np.fill_diagonal(off, np.nan)
        if np.isfinite(off).any():
            at = np.unravel_index(int(np.nanargmax(off)), off.shape)
            facts.append(
                f"largest off-diagonal: {row_names[at[0]]} \N{MULTIPLICATION SIGN} "
                f"{col_names[at[1]]} = {_with_unit(fmt_fn(float(off[at])), unit)}"
            )
            if diverging:
                # Signed data: the strongest relationship may be negative. A symmetric
                # matrix names each pair once (upper triangle).
                mag = np.abs(off)
                if np.allclose(grid, grid.T, equal_nan=True):
                    mag[np.tril_indices_from(mag)] = np.nan
                if np.isfinite(mag).any():
                    st = np.unravel_index(int(np.nanargmax(mag)), mag.shape)
                    facts.append(
                        f"strongest off-diagonal: {row_names[st[0]]} \N{MULTIPLICATION SIGN} "
                        f"{col_names[st[1]]} = {_with_unit(fmt_fn(float(off[st])), unit)}"
                    )
    empty = int((~np.isfinite(grid)).sum())
    if empty:
        facts.append(f"{empty} of {grid.size} cells empty (no value)")
    longest = max(len(fmt_fn(float(v))) for v in finite)

    def _draw(ctx: _Ctx, ax: Axes) -> None:
        sz = ctx.sizes
        theme = ctx.theme
        n_rows, n_cols = grid.shape
        if diverging:
            reach = max(hi - center, center - lo) or 1.0
            t = (grid - center) / reach  # -1 .. 1
            rgb = np.where(
                (t < 0)[..., None],
                _ramp((*theme.div_low, theme.div_mid), 1.0 + np.nan_to_num(t)),
                _ramp((theme.div_mid, *theme.div_high), np.nan_to_num(t)),
            )
        else:
            t = (grid - lo) / ((hi - lo) or 1.0)
            rgb = _ramp(theme.seq_stops, np.nan_to_num(t))
        bg_rgb = np.array(to_rgb(theme.background))
        rgb = np.where(np.isfinite(grid)[..., None], rgb, bg_rgb)

        _bare_axes(ax)
        ax.imshow(
            rgb,
            aspect="auto",
            interpolation="nearest",
            zorder=1,
            extent=(-0.5, n_cols - 0.5, n_rows - 0.5, -0.5),
        )
        divider_col = theme.ink if theme.sketch is not None else theme.background
        divider_lw = 0.8 if theme.sketch is not None else 1.6
        ax.hlines(
            np.arange(n_rows + 1) - 0.5,
            -0.5,
            n_cols - 0.5,
            color=divider_col,
            linewidth=divider_lw,
            zorder=2,
        )
        ax.vlines(
            np.arange(n_cols + 1) - 0.5,
            -0.5,
            n_rows - 0.5,
            color=divider_col,
            linewidth=divider_lw,
            zorder=2,
        )
        ax.set_xlim(-0.5, n_cols - 0.5)
        ax.set_ylim(n_rows - 0.5, -0.5)
        ax.xaxis.tick_top()
        ax.set_xticks(range(n_cols), [_plain(c, theme) for c in col_names])
        ax.set_yticks(range(n_rows), [_plain(r, theme) for r in row_names])
        ax.tick_params(length=0, labelsize=sz.small, labelcolor=theme.ink, pad=3)
        for (i, j), value in np.ndenumerate(grid):
            if not math.isfinite(value):
                continue
            dark = (
                _relative_luminance(
                    "#{:02X}{:02X}{:02X}".format(*(round(c * 255) for c in rgb[i, j]))
                )
                < 0.36
            )
            note = ax.text(
                j,
                i,
                _plain(fmt_fn(float(value)), theme),
                ha="center",
                va="center",
                fontsize=sz.small,
                color="white" if dark else theme.ink,
                zorder=3,
            )
            note._figmint_heatmap_text = True  # type: ignore[attr-defined]
        strips = [
            *((i, j, i, j) for i, j in cells),
            *((i, 0, i, n_cols - 1) for i in hl_rows),
            *((0, j, n_rows - 1, j) for j in hl_cols),
        ]
        for i in hl_rows:
            ax.get_yticklabels()[i].set_fontweight("bold")
        for j in hl_cols:
            ax.get_xticklabels()[j].set_fontweight("bold")
        for i0, j0, i1, j1 in strips:
            ax.plot(
                [j0 - 0.5, j1 + 0.5, j1 + 0.5, j0 - 0.5, j0 - 0.5],
                [i0 - 0.5, i0 - 0.5, i1 + 0.5, i1 + 0.5, i0 - 0.5],
                color=theme.ink,
                linewidth=1.6 * sz.scale,
                zorder=4,
                solid_joinstyle="miter",
                clip_on=False,
                label="_cell",
            )

    def _check_fit(ctx: _Ctx, ax: Axes) -> None:
        cell_pt = (
            ax.get_window_extent(ctx.fig.canvas.get_renderer()).width
            * ctx.pt_per_px
            / grid.shape[1]
        )
        need_pt = longest * ctx.sizes.small * 0.6 + 3.0
        if cell_pt < need_pt:
            raise ExplainError(
                f"matrix() cells are {cell_pt:.0f} pt wide but the numbers need about {need_pt:.0f} pt.",
                fix_hint="Give the matrix a full-width row, swap rows and cols so fewer run "
                "across, shorten the numbers with fmt, or cut columns.",
                rule="matrix_cells_too_small",
            )

    def _draw_and_check(ctx: _Ctx, ax: Axes) -> Callable[[], None]:
        _draw(ctx, ax)
        return lambda: _check_fit(ctx, ax)

    def _headers(ctx: _Ctx, ax: Axes, rect: Bbox) -> list[tuple[Axes, Bbox]]:
        """Column headers must not touch: wrap long ones to two lines, else refuse.

        Runs between drawing and the final fit, on the axes at its final width.
        """
        _fit_axes(ctx.fig, ax, rect)
        renderer = ctx.fig.canvas.get_renderer()
        gap = 0.35 * ctx.sizes.small / ctx.pt_per_px

        def _collide() -> bool:
            boxes = [t.get_window_extent(renderer) for t in ax.get_xticklabels() if t.get_text()]
            return _labels_collide([(0.0, b) for b in boxes], True, gap)

        if not _collide():
            return [(ax, rect)]
        cell_pt = ax.get_window_extent(renderer).width * ctx.pt_per_px / grid.shape[1]
        wrapped: list[str] = []
        for name in col_names:
            words = name.split()
            if len(words) < 2 or ctx.measure.width_pt(name, ctx.sizes.small) <= cell_pt:
                wrapped.append(name)
                continue
            splits = [(" ".join(words[:i]), " ".join(words[i:])) for i in range(1, len(words))]
            best = min(
                splits,
                key=lambda pair: max(ctx.measure.width_pt(p, ctx.sizes.small) for p in pair),
            )
            wrapped.append("\n".join(best))
        ax.set_xticks(range(len(col_names)), [_plain(c, ctx.theme) for c in wrapped])
        for j in hl_cols:
            ax.get_xticklabels()[j].set_fontweight("bold")
        for header in ax.get_xticklabels():
            header.set_linespacing(1.05)
        if _collide():
            raise ExplainError(
                f"matrix() column headers overlap: {grid.shape[1]} columns of about "
                f"{cell_pt:.0f} pt cannot hold names such as "
                f"{max(col_names, key=len)!r}.",
                fix_hint='Give the matrix a wider cell with layout= (e.g. layout=[["a"], '
                '["b", "c"]] for a full-width row), shorten the column names, or swap rows '
                "and cols so the long names run down the side.",
                rule="matrix_cells_too_small",
            )
        return [(ax, rect)]

    return Panel(
        kind="matrix",
        title=title,
        label=label,
        unit=unit,
        spec=_base_spec(
            title,
            label,
            unit,
            values=[[None if not math.isfinite(v) else float(v) for v in row] for row in grid],
            rows=row_names,
            cols=col_names,
            diverging=diverging or None,
            center=center if diverging else None,
            highlight=_jsonable(highlight) if highlight is not None else None,
            fmt=fmt,
        ),
        facts=facts,
        describe=(
            f"Heat table of {label or 'values'}"
            + (f" ({unit})" if unit else "")
            + f", {len(row_names)} rows by {len(col_names)} columns, a number in every cell"
        ),
        _height_mm=lambda _w, _m, _s, _t: 6.2 * len(row_names) + 6.0,
        _draw=_draw_and_check,
        _frames=_headers,
    )


# --------------------------------------------------------------------------- #
# custom
# --------------------------------------------------------------------------- #


@_guarded("custom")
def custom(
    draw: Callable[[Axes], None],
    *,
    title: str | None = None,
    label: str | None = None,
    unit: str | None = None,
    height_mm: float = 48.0,
    describe: str = "Custom panel",
) -> Panel:
    """Escape hatch: draw anything on a house-styled Axes when no form fits.

    The built-in rules do not apply inside ``draw``; preflight still does.
    """
    if not callable(draw):
        raise ExplainError(
            "custom(draw) must be a function taking an Axes.", fix_hint="Pass def draw(ax): ..."
        )

    def _draw(ctx: _Ctx, ax: Axes) -> None:
        _value_axis(ax, ctx.sizes, ctx.theme)
        draw(ax)

    return Panel(
        kind="custom",
        title=title,
        label=label,
        unit=unit,
        spec={"title": title, "label": label, "unit": unit},
        facts=[],
        describe=describe,
        _height_mm=lambda _w, _m, _s, _t: float(height_mm),
        stretch=True,
        _draw=_draw,
    )


# --------------------------------------------------------------------------- #
# Layout and the Explanation object
# --------------------------------------------------------------------------- #


def _auto_layout(keys: list[str]) -> list[list[str]]:
    n = len(keys)
    if n <= 2:
        return [keys]
    if n == 3:
        return [[keys[0], keys[0]], [keys[1], keys[2]]]
    if n % 2 == 0:
        return [keys[i : i + 2] for i in range(0, n, 2)]
    return [[keys[0], keys[0]], *[keys[i : i + 2] for i in range(1, n, 2)]]


def _validate_layout(layout: Sequence[Sequence[str]], keys: list[str]) -> list[list[str]]:
    rows = [[str(k) for k in row] for row in layout]
    seen: list[str] = []
    for row in rows:
        if not row:
            raise ExplainError(
                "layout has an empty row.", fix_hint='e.g. layout=[["a"], ["b", "c"]].'
            )
        collapsed = [k for i, k in enumerate(row) if i == 0 or row[i - 1] != k]
        if len(set(collapsed)) != len(collapsed):
            raise ExplainError(
                f"layout row {row!r} repeats a panel non-contiguously.",
                fix_hint="Repeat a key only side by side to make that panel wider.",
            )
        for key in collapsed:
            if key in seen:
                raise ExplainError(
                    f"layout places panel {key!r} in more than one row.",
                    fix_hint="Each panel occupies one row; rows are stacked top to bottom.",
                )
            seen.append(key)
    if sorted(seen) != sorted(keys):
        raise ExplainError(
            f"layout uses panels {sorted(seen)!r} but the figure has {sorted(keys)!r}.",
            fix_hint="Panels are keyed a, b, c ... in the order passed; list each exactly once.",
        )
    return rows


#: Named colour slots for ``explain(colors=...)``: an index into the theme's validated
#: series palette, so a pinned colour stays colour-blind and grayscale safe in every style.
COLOR_SLOTS: dict[str, int] = {"blue": 0, "red": 1, "green": 2, "amber": 3}


def _entity_key(name: object) -> str:
    return str(name).strip()


def _pinned_colors(colors: object, theme: Theme) -> dict[str, str]:
    """Read ``explain(colors={name: slot})`` into ``{name: hex}`` from the theme palette."""
    if colors is None:
        return {}
    slots = ", ".join(f'"{s}"' for s in COLOR_SLOTS)
    hint = (
        f"Pass colors={{name: slot}} with slot one of {slots}, e.g. "
        'colors={"no retrieval": "red", "full model": "blue"}. Slots resolve to the style\'s '
        "validated palette (colour-blind and grayscale separated), so arbitrary colours are not "
        "accepted."
    )
    if not _has_items(colors):
        raise ExplainError(
            f"explain(colors=...) must map names to colour slots, got {type(colors).__name__}.",
            fix_hint=hint,
            rule="bad_colors",
        )
    out: dict[str, str] = {}
    used: dict[str, str] = {}
    for name, slot in _pairs(colors):
        key = _entity_key(name)
        word = slot.strip().lower() if isinstance(slot, str) else None
        if word not in COLOR_SLOTS:
            raise ExplainError(
                f"explain(colors[{key!r}]) = {slot!r} is not a colour slot.",
                fix_hint=hint,
                rule="bad_colors",
            )
        if word in used:
            raise ExplainError(
                f"explain(colors=...) gives {used[word]!r} and {key!r} the same slot {word!r}; "
                "one colour must mean one thing.",
                fix_hint=f"Give each pinned name its own slot ({slots}; at most four names).",
                rule="bad_colors",
            )
        used[word] = key
        out[key] = theme.series_colors[COLOR_SLOTS[word] % len(theme.series_colors)]
    return out


def _colour_registry(
    panels: Sequence[Panel], theme: Theme, pinned: Mapping[str, str]
) -> tuple[list[dict[str, str]], str, list[dict[str, Any]]]:
    """One colour per named entity across the whole figure.

    Entities are the names a panel emphasises (highlighted items, then trend series and
    relate groups that are coloured by default) plus ``pinned`` names, each group in
    order of first appearance. Each gets one colour from one pool: the accent order when any panel has a
    highlight, else the series order, with the uniform default colour moved last when some
    panel still draws in it. Returns per-panel ``{name: colour}`` maps (keys are the
    panel's own names), the uniform colour, and issues.
    """
    # Highlighted names first (they are what the takeaway is about and get the warm
    # accent), then names coloured by default (trend series, relate groups); each in
    # order of first appearance across the panels.
    entities: list[str] = []
    for modes in (("highlight",), ("series",)):
        for panel in panels:
            if panel.color_mode not in modes:
                continue
            for name in panel.color_focus:
                key = _entity_key(name)
                if key and key not in entities:
                    entities.append(key)
    known = set(entities) | set(pinned)

    def _uniform(panel: Panel) -> bool:
        if not panel.uses_default:
            return False
        if panel.color_mode == "series":
            return True  # an unnamed single series
        return not any(_entity_key(nm) in known for nm in panel.color_items)

    any_highlight = any(p.color_mode == "highlight" for p in panels)
    base = list(theme.accent_colors) if any_highlight else list(theme.series_colors)
    base += [c for c in theme.series_colors if c not in base]
    default = theme.default_color
    pool = [c for c in base if c not in pinned.values()]
    if any(_uniform(p) for p in panels) and default in pool:
        pool = [c for c in pool if c != default] + [default]

    registry: dict[str, str] = dict(pinned)
    overflow: list[str] = []
    for key in entities:
        if key in registry:
            continue
        if pool:
            registry[key] = pool.pop(0)
        else:
            overflow.append(key)

    taken = set(registry.values())
    uniform = default
    if default in taken:  # a pinned or fifth entity took it: use a free colour if one is left
        uniform = next((c for c in base if c not in taken), default)

    per_panel: list[dict[str, str]] = []
    for panel in panels:
        colours: dict[str, str] = {}
        if panel.color_mode != "none":
            wanted = (
                list(panel.color_focus)
                if panel.color_mode in {"highlight", "series"}
                else [nm for nm in panel.color_items if _entity_key(nm) in known]
            )
            if panel.color_mode == "series":
                # coloured by default: entities pinned elsewhere keep their colour too
                wanted = list(dict.fromkeys(wanted))
            for name in wanted:
                key = _entity_key(name)
                if key in registry:
                    colours[name] = registry[key]
            for name in wanted:  # overflow: a colour not used elsewhere in this panel
                if name not in colours and _entity_key(name):
                    free = [c for c in base if c not in colours.values()]
                    colours[name] = free[0] if free else base[0]
        per_panel.append(colours)

    issues: list[dict[str, Any]] = []
    if overflow:
        named = [*list(registry)[: len(base)], *overflow]
        issues.append(
            _issue(
                "colour_reused_across_panels",
                "warning",
                f"{len(named)} names need colour across the panels "
                f"({', '.join(map(repr, named[:8]))}) but the palette has {len(base)} "
                f"colours; {', '.join(map(repr, overflow))} reuse a colour that means "
                "something else in another panel.",
                "Highlight fewer names (the ones the takeaway is about), or split the "
                "argument into two figures.",
            )
        )
    return per_panel, uniform, issues


def _fit_axes(fig: Figure, ax: Axes, rect: Bbox) -> None:
    """Resize ``ax`` so that it and everything attached to it exactly fills ``rect`` (pixels)."""
    renderer = fig.canvas.get_renderer()
    fig_w, fig_h = fig.bbox.width, fig.bbox.height
    ax.set_position([rect.x0 / fig_w, rect.y0 / fig_h, rect.width / fig_w, rect.height / fig_h])
    for _ in range(6):
        tight = ax.get_tightbbox(renderer)
        if tight is None:
            return
        box = ax.get_window_extent(renderer)
        x0 = box.x0 + (rect.x0 - tight.x0)
        x1 = box.x1 - (tight.x1 - rect.x1)
        y0 = box.y0 + (rect.y0 - tight.y0)
        y1 = box.y1 - (tight.y1 - rect.y1)
        if x1 - x0 < 24 or y1 - y0 < 16:
            raise ExplainError(
                "A panel's labels leave no room for its data at this width.",
                fix_hint="Shorten item or series names, use fewer columns (a full-width row via "
                'layout=[["a"], ["b", "c"]]), pass end_values=False on a trend to drop the '
                "numbers at the line ends, or split the figure in two.",
                rule="panel_too_small",
            )
        moved = max(abs(x0 - box.x0), abs(x1 - box.x1), abs(y0 - box.y0), abs(y1 - box.y1))
        ax.set_position([x0 / fig_w, y0 / fig_h, (x1 - x0) / fig_w, (y1 - y0) / fig_h])
        if moved < 0.5:
            return


#: Plot height cap (mm at scale 1) for a full-width trend/relate in a multi-row figure.
_FULL_ROW_STRETCH_MM = 44.0
#: How much a bar-like panel may grow to fill a row set by a taller neighbour.
_ROW_GROWTH = 1.3
#: Narrowest plot area (mm at scale 1) a panel may be left with after its labels fit.
_MIN_PLOT_MM = 20.0


def _check_plot_width(fig: Figure, panel: Panel, ax: Axes, rect: Bbox, scale: float) -> None:
    """Refuse a panel whose labels leave a sliver of plot (end labels in a narrow cell)."""
    if panel.kind in {"matrix", "custom"}:
        return
    px_per_mm = float(fig.dpi) / 25.4
    plot_mm = ax.get_window_extent(fig.canvas.get_renderer()).width / px_per_mm
    # Lines and scatters need room to show a shape; bars, dots and slopes less so.
    least = _MIN_PLOT_MM if panel.stretch or panel.kind == "trend" else 0.4 * _MIN_PLOT_MM
    floor = min(least * scale, 0.42 * rect.width / px_per_mm)
    if plot_mm + 0.05 < floor:
        hint = 'Use fewer columns (e.g. layout=[["a", "a"], ["b", "c"]] gives one panel the full width), shorten the item or series names'
        if panel.kind == "trend":
            hint += ", or pass end_values=False to drop the numbers at the line ends"
        raise ExplainError(
            f"The labels leave only {plot_mm:.0f} mm of plot area (at least {floor:.0f} mm is "
            "needed to read the data).",
            fix_hint=hint + ".",
            rule="panel_too_small",
        )


def _cover_with_ticks(axis: Any, lo: float, hi: float) -> None:
    """Widen a linear axis to the ticks just beyond [lo, hi] so no mark sits past the
    last labelled value (at most half the data span on each side)."""
    v0, v1 = sorted(axis.get_view_interval())
    span = (hi - lo) or abs(hi) or 1.0
    ticks = axis.get_major_locator().tick_values(v0, v1)
    above = [float(t) for t in ticks if t >= hi - 1e-12 * span]
    below = [float(t) for t in ticks if t <= lo + 1e-12 * span]
    if above and above[0] - hi < 0.5 * span:
        v1 = max(v1, above[0])
    if below and lo - below[-1] < 0.5 * span:
        v0 = min(v0, below[-1])
    if axis.axis_name == "x":
        axis.axes.set_xlim(v0, v1)
    else:
        axis.axes.set_ylim(v0, v1)


def _tick_label_boxes(axis: Any, renderer: Any) -> list[tuple[float, Bbox]]:
    """(location, window box) of every visible, non-empty major tick label in view."""
    out: list[tuple[float, Bbox]] = []
    for tick in axis._update_ticks():
        label = tick.label1
        if label.get_visible() and label.get_text().strip():
            out.append((float(tick.get_loc()), label.get_window_extent(renderer)))
    return out


def _labels_collide(boxes: list[tuple[float, Bbox]], horizontal: bool, gap: float) -> bool:
    spans = sorted(((b.x0, b.x1) if horizontal else (b.y0, b.y1)) for _, b in boxes)
    return any(nxt[0] - cur[1] < gap for cur, nxt in itertools.pairwise(spans))


def _fit_ticks(fig: Figure, ax: Axes, which: str = "xy") -> None:
    """Thin tick labels that would touch ("8001,200 1,600") on every axis of ``ax``.

    Runs after layout, so the decision uses the measured label widths and the final
    axes size. A "nice number" locator gets fewer bins; a date locator fewer ticks;
    fixed ticks (log decades, measured x positions, categories) keep a greedy subset
    counted back from the last label, so the end of the range stays labelled.
    """
    renderer = fig.canvas.get_renderer()
    for axis, horizontal in ((ax.xaxis, True), (ax.yaxis, False)):
        if not axis.get_visible() or axis.axis_name not in which:
            continue
        size = max((t.label1.get_fontsize() for t in axis.get_major_ticks()[:1]), default=8.0)
        gap = 0.55 * size * fig.dpi / 72.0
        for _ in range(8):
            boxes = _tick_label_boxes(axis, renderer)
            if len(boxes) < 2 or not _labels_collide(boxes, horizontal, gap):
                break
            locator = axis.get_major_locator()
            if isinstance(locator, MaxNLocator) and len(boxes) > 2:
                nbins = locator._nbins if isinstance(locator._nbins, int) else len(boxes)
                # Fewer bins on round steps keep both ends labelled ("0 1,000 2,000").
                locator.set_params(nbins=max(1, min(nbins, len(boxes)) - 1), steps=[1, 2, 5, 10])
                continue
            if isinstance(locator, mdates.AutoDateLocator) and len(boxes) > 2:
                fewer = mdates.AutoDateLocator(minticks=2, maxticks=max(2, len(boxes) - 1))
                axis.set_major_locator(fewer)
                axis.set_major_formatter(mdates.ConciseDateFormatter(fewer, show_offset=False))
                continue
            # Greedy subset from the end: keep a label when it clears the last one kept.
            ordered = sorted(boxes, key=lambda lb: lb[1].x0 if horizontal else lb[1].y0)
            kept: list[tuple[float, Bbox]] = [ordered[-1]]
            for loc, box in reversed(ordered[:-1]):
                prev = kept[-1][1]
                room = (prev.x0 - box.x1) if horizontal else (prev.y0 - box.y1)
                if room >= gap:
                    kept.append((loc, box))
            keep = [loc for loc, _ in kept]
            old = axis.get_major_formatter()
            span = abs(float(np.diff(axis.get_view_interval())[0])) or 1.0

            def _subset(
                v: float, pos: Any, old: Any = old, keep: list[float] = keep, span: float = span
            ) -> str:
                if any(abs(v - k) <= 1e-9 * max(abs(k), span) for k in keep):
                    return old(v, pos)
                return ""

            axis.set_major_formatter(FuncFormatter(_subset))
            break
        cover = getattr(ax, "_figmint_cover", None)
        bracket = getattr(ax, "_figmint_bracket", None)
        if (
            bracket is not None
            and horizontal
            and axis.get_scale() == "linear"
            and _bracket_with_ticks(fig, axis, *bracket)
        ):
            continue
        if cover is not None and horizontal and axis.get_scale() == "linear":
            _cover_with_ticks(axis, *cover)


def _bracket_with_ticks(
    fig: Figure, axis: Any, lo: float, hi: float, max_ticks: int, minus: str
) -> bool:
    """Round ticks that bracket [lo, hi]: at least three, the lowest at or below every
    observation and the highest at or above it, on the finest nice step whose labels
    fit (so the axis is widened as little as possible). Returns False when no step
    fits, leaving the caller's fallback in charge."""
    span = (hi - lo) or abs(hi) or 1.0
    renderer = fig.canvas.get_renderer()
    size = max((t.label1.get_fontsize() for t in axis.get_major_ticks()[:1]), default=8.0)
    gap = 0.55 * size * fig.dpi / 72.0
    base = 10.0 ** math.floor(math.log10(span / max_ticks))
    steps = [m * base * 10**k for k in (-1, 0, 1, 2) for m in (1, 2, 2.5, 5)]
    set_lim = axis.axes.set_xlim if axis.axis_name == "x" else axis.axes.set_ylim
    old_lim = axis.get_view_interval()
    old_locator, old_formatter = axis.get_major_locator(), axis.get_major_formatter()
    for step in sorted(steps):
        k0 = math.floor(lo / step + 1e-9)
        k1 = math.ceil(hi / step - 1e-9)
        if k1 - k0 + 1 > max_ticks:
            continue
        while k1 - k0 + 1 < 3:  # one more round tick on the side with the less widening
            if (lo - k0 * step) <= (k1 * step - hi) or (k0 - 1) * step < 0 <= lo:
                k1 += 1
            else:
                k0 -= 1
        count = k1 - k0 + 1
        ticks = [float(f"{k * step:.12g}") for k in range(k0, k1 + 1)]
        axis.set_major_locator(FixedLocator(ticks))
        axis.set_major_formatter(
            FuncFormatter(lambda v, _p, m=minus, a=axis: _tick_label(v, m, a))
        )
        # Dots on an end tick stay whole: the view reaches 3% of the span past the data.
        margin = 0.03 * span
        set_lim(min(ticks[0], lo - margin), max(ticks[-1], hi + margin))
        boxes = _tick_label_boxes(axis, renderer)
        if len(boxes) == count and not _labels_collide(boxes, True, gap):
            return True
    axis.set_major_locator(old_locator)
    axis.set_major_formatter(old_formatter)
    set_lim(*old_lim)
    return False


#: Which tick labels of each form are numbers or dates that may be thinned (never names).
_TICK_AXES = {"trend": "xy", "relate": "xy", "distribution": "x", "compare": "x"}


#: Mathtext draws a superscript or subscript at this fraction of its parent's size.
_SCRIPT_SHRINK = 0.7


def _script_depth(text: str) -> int:
    """Deepest superscript/subscript nesting inside the ``$...$`` parts of ``text``.

    ``"µm$^{2}$"`` is 1, ``"$e^{x^{2}}$"`` is 2, plain text (or escaped ``\\$``) is 0.
    """
    parts = re.split(r"(?<!\\)\$", text)
    deepest = 0
    for math_part in parts[1::2]:
        stack: list[int] = []  # depth of each open brace group
        depth = 0
        pending = False  # the next token or group is a script
        for ch in math_part:
            if ch in "^_":
                pending = True
                continue
            if ch == "{":
                stack.append(depth)
                if pending:
                    depth += 1
                    deepest = max(deepest, depth)
                pending = False
                continue
            if ch == "}":
                depth = stack.pop() if stack else 0
                continue
            if pending and not ch.isspace():
                deepest = max(deepest, depth + 1)
                pending = False
    return deepest


class Summary(dict):  # type: ignore[type-arg]
    """What :meth:`Explanation.save` returns: a plain dict that prints as indented JSON.

    Keys: ``schema_version``, ``ok``, ``style``, ``path``, ``size_px``, ``size_mm``,
    ``display``, ``takeaway``, ``panels`` (key, kind, title, facts), ``alt_text``,
    ``colors``, ``issues`` and ``rendered``. ``display`` holds ``width_px`` (the chat
    width the sizes refer to), ``min_text_px`` (smallest font size at that width,
    counting each text at its own size) and ``min_script_px``: the smallest
    mathtext superscript or subscript at that width (drawn at about 70% of its
    label's size, 49% when nested), or ``None`` when the figure has no scripts.
    The ``min_text_px`` floor does not apply to scripts.
    """

    def __str__(self) -> str:
        return json.dumps(self, indent=2, ensure_ascii=False)


class Explanation:
    """A rendered message-first figure plus what an agent needs to hand it over."""

    def __init__(
        self,
        *,
        fig: Figure,
        spec: JournalSpec,
        theme: Theme = FIGMINT_THEME,
        takeaway: str,
        subtitle: str | None,
        source: str | None,
        note: str | None,
        panels: dict[str, Panel],
        axes: dict[str, Axes],
        layout: list[list[str]],
        width: str | float,
        issues: list[dict[str, Any]],
        colors: dict[str, str] | None = None,
    ) -> None:
        self.fig = fig
        self.colors = colors
        #: Colour slot of every named entity in the figure ({"no retrieval": "red"}); pass
        #: it as ``colors=`` to the next figure to keep the same colours.
        self.entity_colors: dict[str, str] = {}
        self.spec = spec
        self.theme = theme
        self.takeaway = takeaway
        self.subtitle = subtitle
        self.source = source
        self.note = note
        self.panels = panels
        self.axes = axes
        self.layout = layout
        self.width = width
        self.issues = issues
        self.saved_path: Path | None = None
        self.saved_px: tuple[int, int] | None = None

    def __getitem__(self, key: str) -> Axes:
        return self.axes[key]

    @property
    def width_mm(self) -> float:
        return float(self.fig.get_figwidth()) * 25.4

    @property
    def height_mm(self) -> float:
        return float(self.fig.get_figheight()) * 25.4

    @property
    def ok(self) -> bool:
        return not any(issue["severity"] == "error" for issue in self.issues)

    @property
    def min_text_px(self) -> float:
        """Smallest text height in pixels when the figure is shown ``DISPLAY_WIDTH_PX`` wide."""
        from matplotlib.text import Text

        sizes = [
            float(t.get_fontsize())
            for t in self.fig.findobj(Text)
            if t.get_visible() and t.get_text().strip()
        ]
        px_per_pt = DISPLAY_WIDTH_PX / (float(self.fig.get_figwidth()) * 72.0)
        return round(min(sizes, default=0.0) * px_per_pt, 1)

    @property
    def min_script_px(self) -> float | None:
        """Smallest mathtext superscript/subscript height in pixels at display width."""
        from matplotlib.text import Text

        sizes = [
            float(t.get_fontsize()) * _SCRIPT_SHRINK**depth
            for t in self.fig.findobj(Text)
            if t.get_visible() and (depth := _script_depth(t.get_text()))
        ]
        if not sizes:
            return None
        px_per_pt = DISPLAY_WIDTH_PX / (float(self.fig.get_figwidth()) * 72.0)
        return round(min(sizes) * px_per_pt, 1)

    @property
    def alt_text(self) -> str:
        parts = [self.takeaway.rstrip(".") + "."]
        for key, panel in self.panels.items():
            lead = f"Panel {key}: " if len(self.panels) > 1 else ""
            body = panel.describe
            if panel.title:
                body = f"{panel.title.rstrip('.')}. {body}"
            if panel.facts:
                body += f". {panel.facts[0]}"
            parts.append(f"{lead}{body}.")
        if self.source:
            parts.append(f"Source: {self.source.rstrip('.')}.")
        return " ".join(parts)

    def to_spec(self) -> dict[str, Any]:
        """JSON-serialisable spec that ``figmint explain`` renders back to the same figure."""
        out: dict[str, Any] = {"takeaway": self.takeaway}
        for key in ("subtitle", "source", "note"):
            if getattr(self, key):
                out[key] = getattr(self, key)
        if self.theme.name != "figmint":
            out["style"] = self.theme.name
        if self.spec.name != "screen":
            out["target"] = self.spec.name
        if self.width != "chat":
            out["width"] = self.width
        if self.colors:
            out["colors"] = dict(self.colors)
        out["layout"] = self.layout
        out["panels"] = [panel.to_spec() for panel in self.panels.values()]
        return out

    def summary(self) -> Summary:
        """What to check before showing the figure: facts to verify the claim, and issues to fix."""
        return Summary(
            {
                "schema_version": "0.2",
                "ok": self.ok,
                "style": self.theme.name,
                "path": str(self.saved_path) if self.saved_path else None,
                "size_px": list(self.saved_px) if self.saved_px else None,
                "size_mm": [round(self.width_mm, 1), round(self.height_mm, 1)],
                "display": {
                    "width_px": DISPLAY_WIDTH_PX,
                    "min_text_px": self.min_text_px,
                    "min_script_px": self.min_script_px,
                },
                "takeaway": self.takeaway,
                "panels": [
                    {"key": key, "kind": p.kind, "title": p.title, "facts": p.facts}
                    for key, p in self.panels.items()
                ],
                "alt_text": self.alt_text,
                "colors": dict(self.entity_colors),
                "issues": self.issues,
                "rendered": self.saved_path is not None,
            }
        )

    def save(
        self,
        path: str | Path,
        *,
        scale: float = 2.0,
        write_spec: bool = False,
        embed: bool = True,
    ) -> Summary:
        """Write the figure (PNG, SVG or PDF by suffix) and return :meth:`summary`.

        PNGs for the screen target are ``DISPLAY_WIDTH_PX * scale`` pixels wide
        (1400 px by default: crisp on high-density displays at chat width).
        ``write_spec=True`` also writes ``<name>.json``, the reproducible spec.
        A PNG carries its own spec, takeaway and alt text as text chunks
        (``figmint:spec``, ``figmint:takeaway``, ``figmint:alt_text``) so
        :func:`load` can rebuild it later; ``embed=False`` leaves them out.
        The figure is written even when ``ok`` is false (``rendered`` says so).
        """
        from .export import save_figure

        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        if self.spec.name == "screen":
            dpi = round(DISPLAY_WIDTH_PX * float(scale) / float(self.fig.get_figwidth()))
        else:
            dpi = int(self.spec.dpi_combo)
        with self.theme.rc_context(self.spec), _GlyphCapture() as glyph_log:
            save_figure(self.fig, out, journal=self.spec, dpi=dpi)
        late = glyph_log.missing()
        if late and not any(i["rule"] == "glyph_missing" for i in self.issues):
            self.issues.append(_glyph_issue(late))
        self.saved_path = out.resolve()
        if out.suffix.lower() == ".png":
            self.saved_px = (
                round(self.fig.get_figwidth() * dpi),
                round(self.fig.get_figheight() * dpi),
            )
            if embed:
                _embed_png_text(
                    out,
                    {
                        "figmint:spec": json.dumps(self.to_spec(), ensure_ascii=False),
                        "figmint:takeaway": self.takeaway,
                        "figmint:alt_text": self.alt_text,
                    },
                )
        else:
            self.saved_px = None
        if write_spec:
            out.with_suffix(".json").write_text(
                json.dumps(self.to_spec(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        return self.summary()

    def preflight(self) -> Any:
        """Run figmint's full preflight on the figure under the target's style."""
        from .preflight import preflight_figure

        with self.theme.rc_context(self.spec), _GlyphCapture():
            return preflight_figure(self.fig, self.spec)

    def bundle(self, out_dir: str | Path, **kwargs: Any) -> Any:
        """Export the full manuscript bundle (PDF, SVG, proof sheet, sidecar) for this figure."""
        from .bundle import bundle_figure

        kwargs.setdefault("takeaway", self.takeaway)
        kwargs.setdefault("takeaway_subtitle", self.subtitle)
        kwargs.setdefault(
            "panel_notes", {k: p.title for k, p in self.panels.items() if p.title} or None
        )
        kwargs.setdefault("caption", self.alt_text)
        with self.theme.rc_context(self.spec):
            return bundle_figure(self.fig, out_dir, journal=self.spec, **kwargs)

    def _repr_png_(self) -> bytes:
        import io

        buffer = io.BytesIO()
        with self.theme.rc_context(self.spec), _GlyphCapture():
            self.fig.savefig(buffer, format="png", dpi=160)
        return buffer.getvalue()


#: Preflight checks phrase their hints for the publication path (Plate, rcParams).
#: On an explain figure the agent can only change explain arguments, so say those.
_EXPLAIN_PREFLIGHT_HINTS: dict[str, str] = {
    "font_sizes": "Text sizes are fixed by fm.explain; this comes from a custom() panel: set "
    "fontsize >= 7 in its draw function, or use a built-in form.",
    "font_family": "Fonts come from style=; use the default style='figmint', or set the "
    "fontfamily inside a custom() panel to a sans-serif font.",
    "text_overlaps": "Two labels in this panel touch. Shorten the item names, end labels or "
    "event text (end_values=False drops the numbers at line ends); show fewer items or "
    'series; give the panel a full-width row with layout=[["a"], ["b", "c"]]; or drop a panel '
    "and move it to a second figure.",
    "canvas_clipping": "Text runs off the image edge. Shorten the longest name or label (or "
    'end_values=False on a trend); give the panel a full-width row with layout=[["a"], ["b"]]; '
    "or drop a panel so the rest get more width.",
    "hairline_strokes": "This comes from a custom() panel: draw lines at linewidth >= 0.5.",
    "colormaps": "Use matrix() for a heat table, or a perceptual colormap such as 'viridis' "
    "inside custom().",
    "layout_collapse": "Give the panel more room: a full-width row via layout=, fewer panels, "
    "or shorter names.",
    "color_separation": "Name fewer series in highlight= (others turn grey), or pass facet=True.",
    "clarity_metadata": "Name what is measured with label= and unit= (and x_label= on trend), "
    'e.g. label="p99 latency", unit="ms".',
    "bar_baseline_nonzero": "Bars must start at zero: use compare() (zero=True), or zero=False "
    "for a dot plot.",
    "chartjunk_hints": "Built-in forms label the data directly; remove legends, frames and 3-D "
    "effects from custom() panels.",
    "text_on_data": "Shorten labels, name fewer items in highlight=, or give the panel a "
    'full-width row with layout=[["a"], ["b"]].',
    "vector_fonts": "Save as .png for chat; for print use target= with a journal name.",
    "file_size": "Save as .png for chat; reduce points in custom() panels.",
}


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    if not data.startswith(_PNG_SIGNATURE):
        raise ExplainError(
            "The file is not a PNG.",
            fix_hint="Pass a PNG written by Explanation.save(), or a .json spec.",
        )
    chunks: list[tuple[bytes, bytes]] = []
    pos = len(_PNG_SIGNATURE)
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos : pos + 4], "big")
        kind = data[pos + 4 : pos + 8]
        chunks.append((kind, data[pos + 8 : pos + 8 + length]))
        pos += 12 + length
        if kind == b"IEND":
            break
    return chunks


def _embed_png_text(path: Path, entries: Mapping[str, str]) -> None:
    """Insert uncompressed iTXt chunks before IEND; image data (IDAT) is left byte-identical."""
    data = path.read_bytes()
    end = data.rfind(b"IEND") - 4
    if end < len(_PNG_SIGNATURE):
        return
    extra = b""
    for key, text in entries.items():
        body = key.encode("latin-1") + b"\x00\x00\x00" + b"\x00" + b"\x00" + text.encode("utf-8")
        chunk_type = b"iTXt"
        crc = zlib.crc32(chunk_type + body) & 0xFFFFFFFF
        extra += len(body).to_bytes(4, "big") + chunk_type + body + crc.to_bytes(4, "big")
    path.write_bytes(data[:end] + extra + data[end:])


def read_png_text(path: str | Path) -> dict[str, str]:
    """The ``figmint:*`` text chunks of a PNG written by :meth:`Explanation.save`."""
    out: dict[str, str] = {}
    for kind, body in _png_chunks(Path(path).read_bytes()):
        if kind == b"iTXt":
            key, _, rest = body.partition(b"\x00")
            # compression flag, method, then language tag and translated keyword (NUL-ended)
            flag = rest[0:1]
            rest = rest[2:]
            _lang, _, rest = rest.partition(b"\x00")
            _tkey, _, text = rest.partition(b"\x00")
            if flag == b"\x01":
                text = zlib.decompress(text)
            out[key.decode("latin-1")] = text.decode("utf-8")
        elif kind == b"tEXt":
            key, _, text = body.partition(b"\x00")
            out[key.decode("latin-1")] = text.decode("latin-1")
    return {k: v for k, v in out.items() if k.startswith("figmint:")}


def load(path: str | Path) -> Explanation:
    """Rebuild an :class:`Explanation` from a PNG saved by figmint or from a ``.json`` spec."""
    source = Path(path)
    if not source.exists():
        raise ExplainError(
            f"{source} does not exist.",
            fix_hint="Pass the path of a PNG written by Explanation.save() or a .json spec.",
        )
    if source.suffix.lower() == ".json":
        try:
            spec = json.loads(source.read_text("utf-8"))
        except json.JSONDecodeError as exc:
            raise ExplainError(
                f"{source} is not valid JSON ({exc}).",
                fix_hint="Fix the JSON, or pass the PNG the figure was saved as.",
            ) from exc
        return explain_from_spec(spec)
    text = read_png_text(source)
    if "figmint:spec" not in text:
        raise ExplainError(
            f"{source.name} carries no figmint spec.",
            fix_hint="Only PNGs written by Explanation.save() (embed=True, the default) carry "
            "their spec; otherwise load the .json written with save(..., write_spec=True).",
        )
    return explain_from_spec(json.loads(text["figmint:spec"]))


def _takeaway_issues(takeaway: str) -> list[dict[str, Any]]:
    words = takeaway.split()
    if len(words) < 4 or (_TOPIC_TITLE.search(takeaway) and not _HAS_DIGIT.search(takeaway)):
        return [
            _issue(
                "takeaway_is_a_topic",
                "warning",
                f"The takeaway {takeaway!r} reads like a topic, not a conclusion.",
                'State what the reader should conclude, with the number: "Checkout p99 tripled '
                'after the v2.3 deploy", not "Latency by service".',
            )
        ]
    return []


@_guarded("explain")
def explain(
    takeaway: str,
    *panels: Panel | Mapping[str, Any],
    subtitle: str | None = None,
    source: str | None = None,
    note: str | None = None,
    layout: Sequence[Sequence[str]] | None = None,
    target: str | JournalSpec = "screen",
    width: str | float = "chat",
    style: str | Theme = "figmint",
    colors: Mapping[str, str] | None = None,
    out: str | Path | None = None,
) -> Explanation:
    """Build a message-first figure: one takeaway sentence and the panels that prove it.

    Parameters
    ----------
    takeaway:
        The conclusion, as a sentence, ideally with its number. It becomes the title.
    panels:
        One to six panels from :func:`compare`, :func:`trend`, :func:`change`,
        :func:`distribution`, :func:`relate`, :func:`share`, :func:`matrix` or
        :func:`custom` (or their dict specs). Use several only when the argument
        has steps; panels are keyed ``a``, ``b``, ``c`` in order.
    subtitle:
        Optional context line under the title (scope, period, population).
    source, note:
        Footer lines: where the numbers came from, and any caveat (synthetic,
        estimated, n, what an interval means).
    layout:
        Rows of panel keys, e.g. ``[["a"], ["b", "c"]]``; repeat a key within a
        row to widen it. Defaults: two panels side by side, three as one wide
        row above two, four as a 2x2.
    target, width:
        Spec and width preset. The default (``"screen"``, ``"chat"``) is sized
        for a ~700 px chat column; pass a journal name for print.
    style:
        Visual surface theme: ``"figmint"`` (default), ``"bold"``, ``"editorial"``, ``"sketch"``,
        or a custom :class:`Theme`. Changes surface aesthetics only, never rules.
    colors:
        Pin a name to a colour slot so it keeps its colour across figures in one
        conversation: ``{"no retrieval": "red"}``. Slots are ``"blue"``, ``"red"``,
        ``"green"`` and ``"amber"``, resolved from the style's validated palette.
        Within one figure a name always has one colour; pinned names are fixed
        entries of that registry.
    out:
        If given, the figure is saved there immediately.
    """
    if not isinstance(takeaway, str) or not takeaway.strip():
        raise ExplainError(
            "explain() needs a takeaway sentence as its first argument.",
            fix_hint="Write the one thing the reader should conclude, then choose panels that show it.",
            rule="takeaway_missing",
        )
    takeaway = " ".join(takeaway.split())
    try:
        theme = get_theme(style)
    except (TypeError, ValueError) as exc:
        aliases = ", ".join(sorted(THEME_ALIASES))
        raise ExplainError(
            str(exc),
            fix_hint=f"Use one of: {', '.join(THEMES)} (aliases: {aliases}).",
            rule="unknown_style",
        ) from exc

    built: list[Panel] = []
    for item in panels:
        if isinstance(item, Panel):
            built.append(item)
        elif isinstance(item, Mapping):
            built.append(panel_from_spec(item))
        else:
            raise ExplainError(
                f"explain() panels must come from fm.compare/trend/..., got {type(item).__name__}.",
                fix_hint="e.g. fm.explain('...', fm.compare({...}), fm.trend(x, {...})).",
            )
    if not built:
        raise ExplainError(
            "explain() needs at least one panel.",
            fix_hint="Add evidence, e.g. fm.compare({'a': 3, 'b': 1}).",
        )
    if len(built) > MAX_PANELS:
        raise ExplainError(
            f"explain() got {len(built)} panels; more than {MAX_PANELS} cannot be read in one figure.",
            fix_hint="Split the argument into two figures, each with its own takeaway.",
            rule="too_many_panels",
        )

    pinned = _pinned_colors(colors, theme)
    panel_colors, uniform_color, colour_issues = _colour_registry(built, theme, pinned)

    spec = get_spec(target)
    keys = [chr(ord("a") + i) for i in range(len(built))]
    panel_map = dict(zip(keys, built, strict=True))
    rows = _validate_layout(layout, keys) if layout is not None else _auto_layout(keys)

    issues: list[dict[str, Any]] = list(_takeaway_issues(takeaway))
    issues.extend(colour_issues)
    if len(built) > COMFORTABLE_PANELS:
        issues.append(
            _issue(
                "many_panels",
                "warning",
                f"{len(built)} panels is a lot for one glance in a conversation.",
                "Keep the panels the takeaway needs; move the rest to a follow-up figure.",
            )
        )
    if theme.warn_unless_illustrative:
        provenance = " ".join(t for t in (source, note) if t)
        if not _ILLUSTRATIVE_CUE.search(provenance):
            issues.append(
                _issue(
                    "sketch_on_measured_data",
                    "warning",
                    "style='sketch' signals a conceptual sketch, but source/note does not mark "
                    "these numbers as illustrative or synthetic.",
                    "Use style='figmint', 'editorial', or 'bold' for measured data, or note in "
                    "source=/note= that the values are illustrative or synthetic.",
                )
            )

    with theme.rc_context(spec), _GlyphCapture() as glyph_log:
        sizes = _Sizes.from_spec(spec, theme)
        s = sizes.scale
        measure = _Measure(theme)
        width_mm = float(spec.resolve_width_mm(width))
        margin = _MARGIN_MM * s
        content_mm = width_mm - 2 * margin
        content_pt = content_mm / PT_TO_MM

        def _line_mm(size: float) -> float:
            return size * _LINE * PT_TO_MM

        title_lines = measure.wrap(
            takeaway,
            content_pt,
            sizes.title,
            theme.title_weight,
            family=theme.title_family,
        )
        if len(title_lines) > MAX_TITLE_LINES:
            raise ExplainError(
                f"The takeaway is {len(takeaway)} characters and wraps to {len(title_lines)} lines.",
                fix_hint="Cut it to one sentence (about 100 characters); move scope and caveats "
                "to subtitle= and note=.",
                rule="takeaway_too_long",
            )
        subtitle_lines = measure.wrap(subtitle, content_pt, sizes.body) if subtitle else []
        footer_text = [t for t in (note, f"Source: {source}" if source else None) if t]
        footer_lines = [ln for t in footer_text for ln in measure.wrap(t, content_pt, sizes.foot)]

        top_rule_pad = 2.2 * s if theme.top_rule else 0.0
        header_mm = (
            top_rule_pad
            + len(title_lines) * _line_mm(sizes.title)
            + len(subtitle_lines) * _line_mm(sizes.body)
        )
        header_gap = 4.0 * s
        footer_rule_pad = 2.0 * s if (theme.footer_rule and footer_lines) else 0.0
        footer_mm = footer_rule_pad + len(footer_lines) * _line_mm(sizes.foot)
        footer_gap = 3.5 * s if footer_lines else 0.0

        multi = len(built) > 1
        letter_pt = measure.width_pt("a", sizes.body, "bold") + sizes.body * 0.75 if multi else 0.0

        # Per-row geometry (mm)
        row_plans: list[dict[str, Any]] = []
        for row in rows:
            order = [k for i, k in enumerate(row) if i == 0 or row[i - 1] != k]
            unit_mm = (content_mm - _COL_GAP_MM * s * (len(row) - 1)) / len(row)
            cells: list[dict[str, Any]] = []
            x_mm = margin
            for key in order:
                span = row.count(key)
                cell_w = unit_mm * span + _COL_GAP_MM * s * (span - 1)
                panel = panel_map[key]
                head_lines = (
                    measure.wrap(panel.title, cell_w / PT_TO_MM - letter_pt, sizes.body, "bold")
                    if panel.title
                    else ([""] if multi else [])
                )
                inline_unit_panel = (
                    theme.inline_y_ticks
                    and panel.kind == "trend"
                    and not panel.spec.get("facet")
                    and not panel.spec.get("log")
                    and bool(panel.unit)
                )
                measure_text = (
                    panel.label if inline_unit_panel else _measure_text(panel.label, panel.unit)
                )
                if panel.measure_note:
                    measure_text = (
                        f"{measure_text}; {panel.measure_note}"
                        if measure_text
                        else panel.measure_note
                    )
                measure_lines = (
                    measure.wrap(measure_text, cell_w / PT_TO_MM - letter_pt, sizes.small)
                    if measure_text
                    else []
                )
                head_mm = len(head_lines) * _line_mm(sizes.body) + len(measure_lines) * _line_mm(
                    sizes.small
                )
                if head_mm:
                    head_mm += 2.2 * s
                cells.append(
                    {
                        "key": key,
                        "x": x_mm,
                        "w": cell_w,
                        "head_lines": head_lines,
                        "measure_lines": measure_lines,
                        "head_mm": head_mm,
                        "plot_mm": panel._height_mm(cell_w / s, measure, sizes, theme) * s,
                    }
                )
                x_mm += cell_w + _COL_GAP_MM * s
            if len(rows) > 1 and len(cells) == 1 and panel_map[cells[0]["key"]].stretch:
                # A full-width line or scatter panel in a multi-row figure would set the
                # tallest row of the figure; cap it so three panels stay on one screen.
                cells[0]["plot_mm"] = min(cells[0]["plot_mm"], _FULL_ROW_STRETCH_MM * s)
            row_plans.append(
                {
                    "cells": cells,
                    "head_mm": max(c["head_mm"] for c in cells),
                    "plot_mm": max(c["plot_mm"] for c in cells),
                }
            )

        body_mm = sum(r["head_mm"] + r["plot_mm"] for r in row_plans) + _ROW_GAP_MM * s * (
            len(row_plans) - 1
        )
        height_mm = margin + header_mm + header_gap + body_mm + footer_gap + footer_mm + margin

        fig = Figure(
            figsize=(mm_to_in(width_mm), mm_to_in(height_mm)),
            dpi=150,
            facecolor=theme.background,
        )
        FigureCanvasAgg(fig)
        fig._figmint_journal = spec.name  # type: ignore[attr-defined]
        px_per_mm = float(fig.dpi) / 25.4

        def _fx(mm: float) -> float:
            return mm / width_mm

        def _fy(mm_from_top: float) -> float:
            return 1.0 - mm_from_top / height_mm

        cursor = margin
        if theme.top_rule:
            rule_y = _fy(cursor + 0.3 * s)
            fig.add_artist(
                Line2D(
                    [_fx(margin), _fx(width_mm - margin)],
                    [rule_y, rule_y],
                    transform=fig.transFigure,
                    color=theme.top_rule_color or theme.ink,
                    linewidth=theme.top_rule_lw * s,
                    solid_capstyle="butt",
                )
            )
            cursor += top_rule_pad

        for line in title_lines:
            title_kw: dict[str, Any] = {
                "ha": "left",
                "va": "top",
                "fontsize": sizes.title,
                "fontweight": theme.title_weight,
                "color": theme.ink,
            }
            if theme.title_family is not None:
                title_kw["fontfamily"] = list(theme.title_family)
            t_art = fig.text(_fx(margin), _fy(cursor), _plain(line, theme), **title_kw)
            if theme.allow_serif_title:
                t_art._figmint_allow_serif = True  # type: ignore[attr-defined]
            cursor += _line_mm(sizes.title)
        for line in subtitle_lines:
            fig.text(
                _fx(margin),
                _fy(cursor + 0.3 * s),
                _plain(line, theme),
                ha="left",
                va="top",
                fontsize=sizes.body,
                color=theme.muted,
            )
            cursor += _line_mm(sizes.body)
        cursor += header_gap

        axes: dict[str, Axes] = {}
        finishers: list[tuple[str, Panel, Callable[[], None]]] = []
        tick_axes: list[tuple[Axes, str]] = []
        contexts: list[tuple[str, _Ctx, int]] = []
        for plan in row_plans:
            row_top = cursor
            for cell in plan["cells"]:
                key = cell["key"]
                panel = panel_map[key]
                text_x = cell["x"] + letter_pt * PT_TO_MM
                y_mm = row_top
                if multi:
                    tag = fig.text(
                        _fx(cell["x"]),
                        _fy(y_mm),
                        key,
                        ha="left",
                        va="top",
                        fontsize=sizes.body,
                        fontweight="bold",
                        color=theme.resolved_panel_tag_color,
                    )
                    tag._figmint_panel_label = True  # type: ignore[attr-defined]
                for line in cell["head_lines"]:
                    if line:
                        fig.text(
                            _fx(text_x),
                            _fy(y_mm),
                            _plain(line, theme),
                            ha="left",
                            va="top",
                            fontsize=sizes.body,
                            fontweight="bold",
                            color=theme.ink,
                        )
                    y_mm += _line_mm(sizes.body)
                for line in cell["measure_lines"]:
                    fig.text(
                        _fx(text_x),
                        _fy(y_mm + 0.2 * s),
                        _plain(line, theme),
                        ha="left",
                        va="top",
                        fontsize=sizes.small,
                        color=theme.muted,
                    )
                    y_mm += _line_mm(sizes.small)

                plot_top = row_top + plan["head_mm"]
                # Bar-like panels keep their own pitch instead of fattening to
                # match a taller neighbour in the same row.
                plot_mm = (
                    plan["plot_mm"]
                    if panel.stretch
                    else min(plan["plot_mm"], cell["plot_mm"] * _ROW_GROWTH)
                )
                rect = Bbox.from_extents(
                    cell["x"] * px_per_mm,
                    (height_mm - plot_top - plot_mm) * px_per_mm,
                    (cell["x"] + cell["w"]) * px_per_mm,
                    (height_mm - plot_top) * px_per_mm,
                )
                ctx = _Ctx(
                    fig=fig,
                    sizes=sizes,
                    key=key,
                    cell_width_mm=cell["w"] / s,
                    measure=measure,
                    theme=theme,
                    measure_label=_measure_text(panel.label, panel.unit) or "(see measure_unnamed)",
                    colors=panel_colors[keys.index(key)],
                    uniform_color=uniform_color,
                )
                ax = ctx.tag(fig.add_axes([0.1, 0.1, 0.5, 0.5]))
                _fit_axes(fig, ax, rect)
                try:
                    finish = panel._draw(ctx, ax)
                    frames = panel._frames(ctx, ax, rect) if panel._frames else [(ax, rect)]
                    for frame_ax, frame_rect in frames:
                        _fit_axes(fig, frame_ax, frame_rect)
                        _check_plot_width(fig, panel, frame_ax, frame_rect, s)
                except ExplainError as exc:
                    raise ExplainError(
                        f"Panel {key} ({panel.kind}): {exc.message}",
                        fix_hint=exc.fix_hint,
                        rule=exc.rule,
                    ) from exc
                which = _TICK_AXES.get(panel.kind, "")
                if which:
                    tick_axes.extend((frame_ax, which) for frame_ax, _ in frames)
                if callable(finish):
                    finishers.append((key, panel, finish))
                finishers.extend((key, panel, extra) for extra in ctx.finishers)
                issues.extend({**issue, "panel": key} for issue in (*panel.issues, *ctx.issues))
                contexts.append((key, ctx, len(ctx.issues)))
                if panel.kind in KINDS and not (panel.label or panel.unit):
                    issues.append(
                        _issue(
                            "measure_unnamed",
                            "warning",
                            f"Panel {key} ({panel.kind}) does not say what is measured.",
                            'Pass label= and unit=, e.g. label="p99 latency", unit="ms".',
                            panel=key,
                        )
                    )
                axes[key] = frames[0][0]
            cursor = row_top + plan["head_mm"] + plan["plot_mm"] + _ROW_GAP_MM * s

        y_mm = height_mm - margin - footer_mm
        if theme.footer_rule and footer_lines:
            frule_y = _fy(y_mm + 0.3 * s)
            fig.add_artist(
                Line2D(
                    [_fx(margin), _fx(width_mm - margin)],
                    [frule_y, frule_y],
                    transform=fig.transFigure,
                    color=theme.footer_rule_color or theme.grid,
                    linewidth=theme.footer_rule_lw * s,
                    solid_capstyle="butt",
                )
            )
            y_mm += footer_rule_pad
        for line in footer_lines:
            fig.text(
                _fx(margin),
                _fy(y_mm),
                _plain(line, theme),
                ha="left",
                va="top",
                fontsize=sizes.foot,
                color=theme.muted,
            )
            y_mm += _line_mm(sizes.foot)

        for key, panel, finish in finishers:
            try:
                finish()
            except ExplainError as exc:
                raise ExplainError(
                    f"Panel {key} ({panel.kind}): {exc.message}",
                    fix_hint=exc.fix_hint,
                    rule=exc.rule,
                ) from exc
        for tick_ax, which in tick_axes:
            _fit_ticks(fig, tick_ax, which)
        for key, ctx, seen in contexts:  # warnings raised while finishing the layout
            issues.extend({**issue, "panel": key} for issue in ctx.issues[seen:])

        result = Explanation(
            fig=fig,
            spec=spec,
            theme=theme,
            takeaway=takeaway,
            subtitle=subtitle,
            source=source,
            note=note,
            panels=panel_map,
            axes=axes,
            layout=rows,
            width=width,
            issues=issues,
            colors={k: str(v) for k, v in _pairs(colors)} if colors else None,
        )
        slot_of = {theme.series_colors[i]: slot for slot, i in COLOR_SLOTS.items()}
        for panel_map_colors in panel_colors:
            for name, col in panel_map_colors.items():
                key = _entity_key(name)
                used = set(result.entity_colors.values())
                if col in slot_of and key not in result.entity_colors and slot_of[col] not in used:
                    result.entity_colors[key] = slot_of[col]  # overflow reuse is left out

        if height_mm > spec.max_height_mm + 0.5:
            issues.append(
                _issue(
                    "too_tall",
                    "warning",
                    f"The figure is {height_mm:.0f} mm tall (about "
                    f"{height_mm / width_mm * DISPLAY_WIDTH_PX:.0f} px at chat width), more than "
                    "fits on one screen.",
                    "Split it into two figures, each with its own takeaway, or drop a panel.",
                )
            )
        if spec.name == "screen" and result.min_text_px < MIN_TEXT_PX:
            issues.append(
                _issue(
                    "small_at_chat_size",
                    "warning",
                    f"The smallest text is {result.min_text_px:.1f} px when shown "
                    f"{DISPLAY_WIDTH_PX} px wide (floor {MIN_TEXT_PX:.0f} px).",
                    'Use width="chat": a wider canvas is scaled down to the same chat column.',
                )
            )

        missing = _missing_glyphs(fig)
        for ch in glyph_log.missing():
            missing.setdefault(ch, "")
        if missing:
            issues.append(_glyph_issue(missing))

        from .preflight import preflight_figure

        report = preflight_figure(fig, spec)
        for check in report.issues:
            if check.rule == "dimensions":
                continue  # height is reported above as too_tall, in chat terms
            issues.append(
                {
                    "rule": check.rule,
                    "severity": "error" if check.status == "fail" else "warning",
                    "panel": check.panel,
                    "message": check.message,
                    "fix_hint": _EXPLAIN_PREFLIGHT_HINTS.get(check.rule, check.fix_hint),
                }
            )

    if out is not None:
        result.save(out)
    return result


# --------------------------------------------------------------------------- #
# JSON spec entry points
# --------------------------------------------------------------------------- #

_BUILDERS: dict[str, Callable[..., Panel]] = {
    "compare": compare,
    "trend": trend,
    "change": change,
    "distribution": distribution,
    "relate": relate,
    "share": share,
    "matrix": matrix,
}
_POSITIONAL: dict[str, tuple[str, ...]] = {
    "compare": ("values",),
    "trend": ("x",),  # series may be replaced by points=
    "change": ("before", "after"),
    "distribution": ("groups",),
    "relate": ("x", "y"),
    "share": ("parts",),
    "matrix": ("values",),
}


def panel_from_spec(spec: Mapping[str, Any]) -> Panel:
    """Build one panel from its dict form, e.g. ``{"kind": "compare", "values": {...}}``."""
    options = dict(spec)
    kind = options.pop("kind", None)
    if kind not in _BUILDERS:
        raise ExplainError(
            f"Unknown panel kind {kind!r}.",
            fix_hint=f"Use one of: {', '.join(KINDS)}.",
        )
    missing = [name for name in _POSITIONAL[kind] if name not in options]
    if missing:
        raise ExplainError(
            f"A {kind} panel needs {', '.join(map(repr, missing))}.",
            fix_hint=f"Required keys for {kind}: {', '.join(_POSITIONAL[kind])}.",
        )
    try:
        return _BUILDERS[kind](**options)
    except TypeError as exc:
        raise ExplainError(
            f"Invalid options for a {kind} panel: {exc}.",
            fix_hint=f"See `figmint explain --example` or help(figmint.{kind}).",
        ) from exc


def explain_from_spec(spec: Mapping[str, Any], *, out: str | Path | None = None) -> Explanation:
    """Render a whole figure from its JSON spec (the inverse of :meth:`Explanation.to_spec`)."""
    options = dict(spec)
    takeaway = options.pop("takeaway", "")
    panels = options.pop("panels", None)
    if not isinstance(panels, Sequence) or isinstance(panels, (str, bytes)) or not panels:
        raise ExplainError(
            'The spec needs a "panels" list.',
            fix_hint='e.g. {"takeaway": "...", "panels": [{"kind": "compare", "values": {...}}]}.',
        )
    allowed = {"subtitle", "source", "note", "layout", "target", "width", "style", "colors"}
    unknown = sorted(set(options) - allowed)
    if unknown:
        raise ExplainError(
            f"Unknown top-level key(s) {unknown!r}.",
            fix_hint=f"Allowed: takeaway, panels, {', '.join(sorted(allowed))}.",
        )
    return explain(takeaway, *[panel_from_spec(p) for p in panels], out=out, **options)


EXAMPLE_SPEC: dict[str, Any] = {
    "takeaway": "Checkout is the slow service: its p99 is 4x the next worst",
    "subtitle": "API p99 latency by service, week of 16 Nov",
    "source": "synthetic example data",
    "panels": [
        {
            "kind": "compare",
            "title": "Checkout stands alone",
            "label": "p99 latency",
            "unit": "ms",
            "values": {
                "checkout": 1840,
                "search": 460,
                "auth": 310,
                "catalog": 280,
                "cart": 240,
                "profile": 120,
            },
            "highlight": "checkout",
        },
        {
            "kind": "trend",
            "title": "It regressed after the v2.3 deploy",
            "label": "p99 latency",
            "unit": "ms",
            "x_label": "Week",
            "x": [1, 2, 3, 4, 5, 6, 7, 8],
            "series": {
                "checkout": [540, 560, 550, 570, 980, 1400, 1700, 1840],
                "search": [450, 470, 455, 465, 460, 450, 470, 460],
                "auth": [300, 310, 305, 315, 300, 320, 305, 310],
            },
            "highlight": "checkout",
            "events": {"4": "v2.3 deploy"},
        },
    ],
}
