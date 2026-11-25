"""Core constants, formatting, glyph handling, argument guards, and Panel primitives."""

from __future__ import annotations

import contextlib
import contextvars
import difflib
import functools
import inspect
import itertools
import math
import numbers
import re
import unicodedata
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

import numpy as np
from matplotlib import dates as mdates
from matplotlib import patheffects
from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import to_rgb
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import (
    FixedLocator,
    FuncFormatter,
    LogLocator,
    MaxNLocator,
    NullFormatter,
    NullLocator,
)
from matplotlib.transforms import Bbox

from ..specs import JournalSpec
from ..themes import (
    FIGMINT_THEME,
    Theme,
    contrast_ratio,
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
MAX_FACETS = 12
MAX_CHANGE_ITEMS = 14
MAX_MATRIX_ROWS = 16
MAX_MATRIX_COLS = 12

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
    "table",
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


#: An ASCII hyphen used as a sign: at the start, or after a space or one of
#: ( [ = : ^ , /, and before a digit ("-3 °C", "Δ = -0.4", "10^-3"). Dates
#: ("2026-01-31"), ranges ("43-53 nm") and words ("1C-rate") keep their hyphen.
_SIGN_HYPHEN = re.compile(r"(?<![^\s(\[=:^,/])-(?=\d)")


def _minus_signs(text: str) -> str:
    """Caller text with sign hyphens drawn as a true minus ("−3 °C")."""
    return _SIGN_HYPHEN.sub("\N{MINUS SIGN}", text)


def _plain(text: object, theme: Theme | None = None) -> str:
    """Escape ``$`` so user text is never parsed as mathtext ("from $5M to $8M").

    An ASCII hyphen used as a sign becomes a minus (:func:`_minus_signs`).
    When ``theme`` defines ASCII glyph substitutes (e.g. ``sketch``), replaces
    Unicode minus, en-dash, and ellipsis on the rendered text artist.
    """
    out = _minus_signs(str(text)).replace(r"\$", "$").replace("$", r"\$")
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


#: Issues that indicate a real visual or legibility defect (as opposed to advisory polish).
_VISUAL_DEFECT_RULES: frozenset[str] = frozenset(
    {
        "text_overlaps",
        "text_struck_by_line",
        "text_malformed",
        "canvas_clipping",
        "line_past_axis",
        "glyph_missing",
        "latex_markup",
        "event_label_collides",
        "reference_label_collides",
        "value_label_on_reference",
        "text_on_data",
        "small_at_chat_size",
    }
)

_STRICT: contextvars.ContextVar[bool] = contextvars.ContextVar("figmint_strict", default=True)
_ADJUSTMENTS: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "figmint_adjustments", default=None
)


def _is_strict() -> bool:
    return _STRICT.get()


def _record_adjustment(message: str) -> None:
    log = _ADJUSTMENTS.get()
    if log is not None and message not in log:
        log.append(message)


@contextlib.contextmanager
def lenient() -> Iterator[None]:
    """Non-strict context for fast chat figures: auto-adjusts soft limits instead of raising.

    Inside ``with fm.lenient():`` (or when passing ``strict=False`` to :func:`explain`),
    figmint auto-facets >4 trend series, trims oversized lists/highlights, drops missing
    entries, stacks cramped side-by-side panels into full-width rows, and separates minor
    advisory warnings from real visual defects so an agent can ship a good-enough figure
    on the first try. Every adjustment is recorded in ``summary["adjustments"]``.
    """
    tok_s = _STRICT.set(False)
    existing = _ADJUSTMENTS.get()
    tok_a = _ADJUSTMENTS.set([] if existing is None else existing)
    try:
        yield
    finally:
        _STRICT.reset(tok_s)
        _ADJUSTMENTS.reset(tok_a)


def _named_values(values: object, what: str, *, allow_nan: bool = False) -> dict[str, float]:
    """Normalise a mapping or a sequence of ``(name, value)`` pairs to ``{name: float}``.

    Anything with ``.items()`` (a dict, a pandas Series) counts as a mapping.
    """
    if _has_items(values):
        items = _pairs(values)
    elif isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
        from .._tabular import is_row_records

        if is_row_records(values):
            cols = list(dict.fromkeys(str(k) for row in values for k in row))
            shown = ", ".join(repr(c) for c in cols[:8])
            raise ExplainError(
                f"{what} received row-shaped dicts (columns: {shown}) instead of a name -> number mapping.",
                fix_hint=(
                    f'Pass name="...", value="..." (e.g. name="{cols[0]}", value="{cols[-1]}") '
                    "or convert to a dict {row[name]: row[value]}."
                ),
            )
        try:
            items = [(pair[0], pair[1]) for pair in values]
        except (TypeError, IndexError, KeyError) as exc:
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
    dropped_nan: list[str] = []
    for name, value in items:
        key = str(name)
        if getattr(value, "ndim", 0) >= 1:  # a DataFrame column, a list
            raise ExplainError(
                f"{what}[{key!r}] is a column of values, not one number.",
                fix_hint="Pass one number per name: a dict or a pandas Series (index = names), "
                'e.g. df["p99"] or df.median(); for raw observations per group use distribution().',
            )
        if key in out:
            raise ExplainError(
                f"{what} repeats the name {key!r}.",
                fix_hint="Give every item a unique name (aggregate duplicates first).",
            )
        number = _to_float(value, f"{what}[{key!r}]")
        if not math.isfinite(number) and not allow_nan:
            if not _is_strict():
                dropped_nan.append(key)
                continue
            raise ExplainError(
                f"{what}[{key!r}] is not finite ({value!r}).",
                fix_hint="Drop or impute missing values before plotting, and say so in `note`.",
            )
        out[key] = number
    if dropped_nan and out:
        _record_adjustment(f"{what}: dropped non-finite item(s) {dropped_nan[:4]!r}")
    if not out:
        raise ExplainError(f"{what} is empty.", fix_hint="Pass at least one named value.")
    return out


def _names(highlight: object, valid: Sequence[str], what: str = "highlight") -> list[str]:
    if highlight is None:
        return []
    names = [highlight] if isinstance(highlight, str) else [str(h) for h in highlight]  # type: ignore[union-attr]
    unknown = [n for n in names if n not in valid]
    if unknown:
        if not _is_strict():
            names = [n for n in names if n in valid]
            _record_adjustment(f"{what}: ignored unknown name(s) {unknown[:4]!r}")
        else:
            raise ExplainError(
                f"{what} names {unknown!r} that are not in the data.",
                fix_hint=f"Use names from: {', '.join(map(repr, list(valid)[:12]))}.",
            )
    if len(names) > MAX_HIGHLIGHTS:
        if not _is_strict():
            _record_adjustment(
                f"{what}: trimmed {len(names)} highlights to first {MAX_HIGHLIGHTS}"
            )
            names = names[:MAX_HIGHLIGHTS]
        else:
            raise ExplainError(
                f"{what} lists {len(names)} items; more than {MAX_HIGHLIGHTS} highlights nothing.",
                fix_hint=f"At most {MAX_HIGHLIGHTS} highlights: name only the items the takeaway "
                "sentence names (the rest stay as grey context), or split the claim across two "
                "panels with up to 3 highlights each.",
                rule="too_many_highlights",
            )
    return names


# --------------------------------------------------------------------------- #
# Argument checking shared by every form (unknown keywords -> ExplainError)
# --------------------------------------------------------------------------- #

#: Valid keyword arguments of each guarded callable, filled in by ``_guarded``.
_FORM_ARGS: dict[str, tuple[str, ...]] = {}
_EXPLAIN_ARGS = (
    "subtitle",
    "source",
    "note",
    "layout",
    "target",
    "width",
    "style",
    "palette",
    "colors",
    "strict",
    "out",
)
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


def _has_unit(text: str, unit: str) -> bool:
    """True when ``text`` already carries ``unit`` (a ``fmt`` such as "{:+.0f}%").

    A trailing unit counts only at a word boundary: "12 ms" does not end with "s".
    A currency counts anywhere ("$12", "−$0.10").
    """
    u = unit.strip()
    if not u:
        return False
    t = text.strip()
    if u in _CURRENCY_UNITS:
        return u in t
    if not t.endswith(u) or len(t) == len(u):
        return False
    return not (u[0].isalpha() and t[: -len(u)][-1:].isalpha())


def _with_unit(text: str, unit: str | None) -> str:
    if not unit:
        return text
    if _has_unit(text, unit):  # fmt already wrote it: never "−28%%"
        return text
    if unit in {"$", "\N{EURO SIGN}", "\N{POUND SIGN}"}:
        if text.startswith(("\N{MINUS SIGN}", "+")):  # the sign leads: "−$0.10", "+$0.50"
            return f"{text[0]}{unit}{text[1:]}"
        return f"{unit}{text}"
    if unit in {"%", "\N{MULTIPLICATION SIGN}", "x", "\N{DEGREE SIGN}"} or unit.startswith("%"):
        return f"{text}{unit}"
    return f"{text} {unit}"


def _range_with_unit(lo: str, hi: str, unit: str | None) -> str:
    """A range with its unit once at the end ("32\N{EN DASH}52%", "12\N{EN DASH}15 ms"), or on
    both ends for a currency, which leads its number ("$1.20\N{EN DASH}$1.50"). When either bound
    is negative, use " to " ("−1.7 to −1.1%") rather than colliding a dash and a minus sign."""
    sep = (
        " to "
        if (lo.startswith(("\N{MINUS SIGN}", "-")) or hi.startswith(("\N{MINUS SIGN}", "-")))
        else "\N{EN DASH}"
    )
    if unit in _CURRENCY_UNITS:
        return f"{_with_unit(lo, unit)}{sep}{_with_unit(hi, unit)}"
    return f"{lo}{sep}{_with_unit(hi, unit)}"


def _inline_unit(unit: str | None) -> bool:
    """Short units that belong on every value label, not just the first."""
    return unit in {"%", "$", "\N{EURO SIGN}", "\N{POUND SIGN}", "\N{MULTIPLICATION SIGN}", "x"}


_FOLD_UNITS = {"\N{MULTIPLICATION SIGN}", "x", "fold", "-fold", "fold change", "fold-change"}


def _fold_unit(unit: str | None, label: str | None, positive_log: bool) -> bool:
    """True when the values are raw ratios: unit "×"/"x"/"fold", or (on a log axis of
    positive values, with no unit) a label naming a fold change that is not log-transformed."""
    if isinstance(unit, str) and unit.strip().lower() in _FOLD_UNITS:
        return True
    return (
        unit is None
        and positive_log
        and bool(label)
        and re.search(r"\bfold\b", str(label), re.IGNORECASE) is not None
        and re.search(r"\blog", str(label), re.IGNORECASE) is None
    )


def _long_unit_issue(unit: object) -> dict[str, Any] | None:
    """Warn when ``unit=`` is words, not a symbol: it is printed after every value."""
    if not isinstance(unit, str):
        return None
    u = unit.strip()
    if len(u.split()) <= 2 and len(u) <= 16:
        return None
    return _issue(
        "unit_is_long",
        "warning",
        f"unit={unit!r} is words, and the unit is printed after every value in the facts "
        "and labels.",
        "Put the words in label= and keep unit= a symbol (ms, %, mg/L).",
    )


def _measure_text(label: str | None, unit: str | None) -> str | None:
    if label and unit:
        if re.search(rf"[(\[]\s*{re.escape(unit.strip())}\s*[)\]]\s*$", label):
            return label  # the label already ends with its unit: "Yield (MPa)"
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


def _percent_change(first: float, last: float, *, precise: bool = False) -> str | None:
    """"+46%"; with ``precise``, changes under 10% keep one decimal ("+2.9%", "\N{MINUS SIGN}0.4%")."""
    if first == 0 or not math.isfinite(first) or not math.isfinite(last):
        return None
    pct = (last - first) / abs(first) * 100.0
    sign = "+" if pct >= 0 else "\N{MINUS SIGN}"
    if precise and abs(pct) < 9.95:
        return f"{sign}{abs(pct):.1f}%"
    return f"{sign}{abs(pct):.0f}%"


def _signed(text: str) -> str:
    """Prefix "+" to a formatted non-negative, non-zero difference."""
    if text.startswith(("\N{MINUS SIGN}", "+")) or _shows_zero(text):
        return text
    return "+" + text


def _unsigned(text: str) -> str:
    """A width or gap from a possibly signed ``fmt`` ("+26%"): no leading "+"."""
    return text.strip().removeprefix("+")


def _diff_with_unit(text: str, unit: str | None) -> str:
    """A difference: in points when the unit is "%" (a percent of a percent misleads)."""
    if unit is not None and unit.strip().startswith("%"):
        if _has_unit(text, unit):  # fmt="{:+.0f}%": the difference is still in points
            text = text.strip()[: -len(unit.strip())].rstrip()
        bare = text.lstrip("+\N{MINUS SIGN}")
        return f"{text} {'point' if bare == '1' else 'points'}"
    return _with_unit(text, unit)


def _relative_text(value: float, base: float, unit: str | None) -> str | None:
    """``value`` relative to ``base``: a ratio for "%" units ("0.58×"), else a percent change.

    None when the relation is meaningless: a zero or non-finite base, or a sign change.
    """
    if not (math.isfinite(value) and math.isfinite(base)) or base == 0:
        return None
    if unit is not None and unit.strip().startswith("%"):
        return _ratio_text(value / base) if value > 0 and base > 0 else None
    if (value < 0 < base) or (base < 0 < value):
        return None
    return _percent_change(base, value, precise=True)


def _vs_text(
    value: float,
    base: float,
    *,
    unit: str | None,
    diff_fmt: Callable[[float], str],
    log: bool = False,
    relative: bool = True,
) -> str:
    """``value`` against a baseline: "+12 ms (+46%)", "−33 points (0.58×)", or "4.7×" on a log axis.

    ``relative=False`` (zero is not meaningful, e.g. wavelengths) keeps only the difference.
    """
    if log:
        return _ratio_text(value / base)
    text = _diff_with_unit(_signed(diff_fmt(value - base)), unit)
    rel = _relative_text(value, base, unit) if relative else None
    return f"{text} ({rel})" if rel else text


def _baseline_name(
    baseline: object, names: Sequence[str], highlight: Sequence[str], kind: str
) -> str | None:
    """Check ``baseline=``: one item name, not also highlighted."""
    if baseline is None:
        return None
    if not isinstance(baseline, (str, numbers.Number)) or isinstance(baseline, bool):
        raise ExplainError(
            f"{kind}(baseline=...) must be one item name, got {type(baseline).__name__}.",
            fix_hint='Pass the reference item\'s name, e.g. baseline="control" or '
            'baseline="before".',
        )
    name = str(baseline)
    if name not in names:
        if not _is_strict():
            _record_adjustment(f"{kind}(baseline={name!r}): ignored (not in items)")
            return None
        raise ExplainError(
            f"{kind}(baseline={name!r}) is not one of the items.",
            fix_hint=f"Use one of: {', '.join(map(repr, list(names)[:12]))}.",
        )
    if name in highlight:
        if not _is_strict() and isinstance(highlight, list):
            highlight.remove(name)
            _record_adjustment(f"{kind}: kept baseline {name!r} in ink instead of highlight")
        else:
            raise ExplainError(
                f"{kind}(baseline={name!r}) is also in highlight.",
                fix_hint="The baseline is the reference, drawn in ink; highlight only the items "
                f"compared against it, e.g. highlight=[...] without {name!r}.",
            )
    if len(names) < 2:
        if not _is_strict():
            return None
        raise ExplainError(
            f"{kind}(baseline=...) needs at least one other item to compare with it.",
            fix_hint="Drop baseline=, or add the items to compare.",
        )
    return name


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

    * Log axis: fold change ("rises 2.3-fold", "falls 7,900-fold, 3.9 decades").
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
        fold = 10 ** abs(decades)
        if fold < 1.005:
            return "unchanged"
        # One wording for every series in a panel: the fold, plus decades once >= 1.
        text = f"{word} {_ratio_text(fold).rstrip(chr(0xD7))}-fold"
        return text + (f", {abs(decades):.1f} decades" if abs(decades) >= 1 else "")
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
    #: The reference item (``baseline=``): drawn in ink, never given a palette colour.
    color_baseline: str | None = None
    #: The smallest plot height (mm at scale 1, same arguments as ``_height_mm``) at
    #: which the form still reads: a figure too tall for one screen is first
    #: compressed toward it. None: the natural height is the minimum.
    _min_height_mm: Callable[[float, _Measure, _Sizes, Theme], float] | None = None
    #: The facts the alt text reads out: every group or series the panel is about (or
    #: the highlighted ones plus the baseline), not just the first fact. None: facts[0].
    alt_facts: list[str] | None = None

    def __post_init__(self) -> None:
        issue = _long_unit_issue(self.unit)
        if issue is not None and not any(i["rule"] == "unit_is_long" for i in self.issues):
            self.issues.append(issue)

    def to_spec(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind}
        out.update({k: _jsonable(v) for k, v in self.spec.items() if v is not None})
        return out

    def to_markdown(self) -> str:
        """Return a formatted Markdown table for ``table`` panels (raises for other forms)."""
        md = getattr(self, "_markdown", None)
        if md is None:
            raise ExplainError(
                f"{self.kind}() panels do not have a Markdown table representation.",
                fix_hint="Use fm.table(...) to render or export a Markdown table.",
            )
        return str(md)


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


def _interval_issue(form: str, arg: str, label_arg: str) -> dict[str, Any]:
    return _issue(
        "interval_unlabelled",
        "warning",
        f"{form}({arg}=...) draws intervals without saying what they are; a whisker with no "
        "stated meaning cannot be interpreted.",
        f'Pass {label_arg}="95% CI" (or "\N{PLUS-MINUS SIGN} 1 s.d., n = 5", "min\N{EN DASH}max of 3 runs").',
    )


def _or_list(items: Sequence[str]) -> str:
    """"a", "a or b", "a, b or c"."""
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " or " + items[-1]


_X_UNIT = re.compile(r"[(\[]\s*([^()\[\]]{1,16}?)\s*[)\]]\s*$")


def _x_unit(x_label: str | None) -> str | None:
    """The unit at the end of an axis label: "Time after dose (h)" -> "h".

    Only a bracket that reads as a unit: one token that does not start with a
    digit. "Cycle (1C/1C)" or "Dose (per 70 kg)" give no unit (pass ``x_unit=``).
    """
    if not x_label:
        return None
    found = _X_UNIT.search(x_label)
    if not found:
        return None
    text = found.group(1)
    if text[:1].isdigit() or any(ch.isspace() for ch in text):
        return None
    return text


def _resolve_x_unit(x_unit: object, x_label: str | None, kind: str) -> str | None:
    """``x_unit=`` when given ("" turns the unit off), else the one parsed from ``x_label``."""
    if x_unit is None:
        return _x_unit(x_label)
    if not isinstance(x_unit, str):
        raise ExplainError(
            f"{kind}(x_unit={x_unit!r}) must be a string.",
            fix_hint='Pass the x unit as text, e.g. x_unit="h" or x_unit="cycles"; '
            'x_unit="" states x values with no unit.',
        )
    return x_unit.strip() or None


class _DateTickFormatter(mdates.ConciseDateFormatter):
    """Concise date ticks where a day-of-month always carries its month.

    Matplotlib's concise labels read "15, Oct, 15, Nov": the first "15" (15 Sep) looks
    like 15 Oct. Here day ticks read "15 Sep", "1 Oct", "15 Oct"; month ticks stay
    "Oct" (January shows the year). Leading zeros are dropped portably.
    """

    def format_ticks(self, values: Any) -> list[str]:
        return [re.sub(r"^0(?=\d)", "", text) for text in super().format_ticks(values)]


def _date_formatter(locator: mdates.DateLocator) -> mdates.ConciseDateFormatter:
    return _DateTickFormatter(
        locator,
        formats=["%Y", "%b", "%d %b", "%H:%M", "%H:%M", "%S.%f"],
        zero_formats=["", "%Y", "%d %b", "%d %b", "%H:%M", "%H:%M"],
        show_offset=False,
    )


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


def _and_list(items: Sequence[str]) -> str:
    """"a", "a and b", "a, b and c"."""
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


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


#: Two-sided 95% Student t quantiles (0.975) for 1-30 degrees of freedom.
_T975 = (
    12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228,
    2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086,
    2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042,
)  # fmt: skip


def _t975(df: int) -> float:
    """The 0.975 quantile of Student's t: a table to 30 df, then the Cornish-Fisher
    series in 1/df (within 0.01% of the exact value beyond 30 df)."""
    if df < 1:
        return float("nan")
    if df <= len(_T975):
        return _T975[df - 1]
    z = 1.959964
    g1 = (z**3 + z) / 4.0
    g2 = (5 * z**5 + 16 * z**3 + 3 * z) / 96.0
    g3 = (3 * z**7 + 19 * z**5 + 17 * z**3 - 15 * z) / 384.0
    return z + g1 / df + g2 / df**2 + g3 / df**3


def _slope_ci(gx: np.ndarray, gy: np.ndarray, slope: float, intercept: float) -> tuple[float, float]:
    """95% confidence interval of a least-squares slope (t with n - 2 df)."""
    n = gx.size
    sxx = float(((gx - gx.mean()) ** 2).sum())
    if n < 3 or sxx <= 0:
        return float("nan"), float("nan")
    resid = gy - (slope * gx + intercept)
    se = math.sqrt(float((resid**2).sum()) / (n - 2) / sxx)
    half = _t975(n - 2) * se
    return slope - half, slope + half


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
