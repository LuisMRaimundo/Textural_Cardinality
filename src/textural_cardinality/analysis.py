"""Score-driven vertical cardinality analysis.

Cardinality is evaluated instantaneously at score time *t* as the size of the
active note multiset. Because that function changes only at event onsets and
offsets, :func:`_time_axis` always includes those boundary times so brief
sonorities are not missed. An optional uniform ``time_step`` grid is merged in
for plotting convenience only.
"""

from __future__ import annotations

from collections import Counter
import csv
import json
import math
from pathlib import Path
import statistics
import tempfile
from typing import Any

from music21 import converter
from music21.chord import Chord
from music21.note import Note
from music21.pitch import Pitch
from music21.stream import Score

from textural_cardinality.microtone_repair import (
    DEFAULT_MICROTONEREPAIR,
    WARN_MIDI_BIN_CENTS,
    apply_microtone_repair,
    detect_accidental_alter_mismatch,
    is_midi_score_path,
    normalize_microtone_repair,
)
from textural_cardinality.pitch_grid import (
    NoteTuple,
    TUNING_PRESETS,
    _STEP_TO_SEMITONE,
    _midi_from_note_tuple,
    _nearest_int,
    _pc_class,
    _pitch_unit,
    validate_edo,
)
from textural_cardinality.pitch_inventory import (
    excluded_indices,
    inventory_digest_line,
    out_of_register_notes,
    pitch_inventory_digest,
    prepare_score_for_analysis,
    public_inventory_rows,
    refresh_quantised_ps,
)
from textural_cardinality.pitch_overrides import normalize_pitch_overrides
from textural_cardinality.pitch_reference import (
    DEFAULT_PITCH_REFERENCE,
    PITCH_PIPELINE_ORDER,
    normalize_pitch_reference,
)
from textural_cardinality.pitch_utils import format_pitch_name, format_ps_display

_EPS = 1e-9
_TOL = 1e-6
DEFAULT_BIN_CENTS = 100.0
DEFAULT_EDO = 12
REFERENCE_REGISTER_LOW = "A0"
REFERENCE_REGISTER_HIGH = "C8"
REFERENCE_PS_LOW = 21.0  # A0 in pitch-space (midi 21)
REFERENCE_PS_HIGH = 108.0  # C8 in pitch-space (midi 108)
REFERENCE_UNIVERSE_12TET = 88
REFERENCE_UNIVERSE_QUARTER_TONE = 175
MICRO_POLE_CARDINALITY = 1
JSON_EXPORT_SCHEMA_VERSION = "1.2"
LABEL_MODE_COUNT = "count"
LABEL_MODE_INDEX = "index"
DEFAULT_LABEL_MODE = LABEL_MODE_COUNT
DEFAULT_LABEL_COUNT_THRESHOLDS: tuple[int, int] = (12, 60)
# Frozen protocol index threshold (macro boundary). micro_max stays 0.10 so meso remains.
FROZEN_INDEX_THRESHOLD = 0.35
DEFAULT_LABEL_THRESHOLDS: tuple[float, float] = (0.10, FROZEN_INDEX_THRESHOLD)
RESULT_SCALE_WIDTH = 50
RESULT_FRAME_WIDTH = 66
UNRELIABLE_LABEL_SUFFIX = " (UNRELIABLE: distinct notated pitches were merged by the grid)"
LABEL_BADGE_COLORS = {
    "micro": "#1F7A8C",
    "meso": "#C9A227",
    "macro": "#9B2226",
}

SUMMARY_METRICS = (
    "vertical_note_count",
    "vertical_unique_pitch_count",
    "vertical_pitch_class_cardinality",
    "micro_macro_pitch_cardinality",
    "micro_macro_normalized",
    "micro_meso_macro_normalized",
)


def validate_bin_cents(bin_cents: float) -> float:
    bin_cents = float(bin_cents)
    if bin_cents <= 0:
        raise ValueError("bin_cents must be > 0")
    return bin_cents


def linked_bin_cents_for_edo(edo: int) -> float:
    """``bin_cents = 1200 / edo`` for a linked GUI/API pair."""
    return 1200.0 / float(validate_edo(edo))


def linked_edo_for_bin_cents(bin_cents: float) -> int | None:
    """Return ``edo = 1200 / bin_cents`` when that quotient is an integer."""
    bc = validate_bin_cents(bin_cents)
    ratio = 1200.0 / bc
    nearest = int(round(ratio))
    if nearest >= 1 and abs(ratio - float(nearest)) <= 1e-6:
        return nearest
    return None


def universe_size_label(bin_cents: float) -> str:
    return f"universe size: {reference_pitch_universe_size(bin_cents)}"


def _struct_warning(
    code: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    severity: str = "warning",
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "details": details or {},
    }


def _pitch_to_note_tuple(p: Pitch) -> NoteTuple | None:
    if p.octave is None:
        return None
    step = str(p.step).upper()
    octave = int(p.octave)
    base_ps = 12.0 * (octave + 1) + _STEP_TO_SEMITONE[step]
    alter = float(p.ps) - base_ps
    return (step, alter, octave)


def _ps_in_reference_register(ps: float, tol: float = _TOL) -> bool:
    return (REFERENCE_PS_LOW - tol) <= float(ps) <= (REFERENCE_PS_HIGH + tol)


def _note_in_reference_register(note: NoteTuple, tol: float = _TOL) -> bool:
    return _ps_in_reference_register(_midi_from_note_tuple(note), tol=tol)


def reference_pitch_universe_size(bin_cents: float) -> int:
    """Return the closed A0–C8 pitch-position count for the active grid."""
    bin_cents = validate_bin_cents(bin_cents)
    if abs(bin_cents - DEFAULT_BIN_CENTS) <= _TOL:
        return REFERENCE_UNIVERSE_12TET
    if abs(bin_cents - 50.0) <= _TOL:
        return REFERENCE_UNIVERSE_QUARTER_TONE
    span_cents = (REFERENCE_PS_HIGH - REFERENCE_PS_LOW) * 100.0
    return int(round(span_cents / bin_cents)) + 1


def micro_macro_normalized(cardinality: int, universe_size: int) -> float:
    if universe_size <= 0:
        return 0.0
    return round(min(1.0, max(0.0, float(cardinality) / float(universe_size))), 6)


def meso_pole_cardinality(universe_size: int) -> float:
    """Arithmetic centre between micro (1) and macro (universe_size) poles."""
    universe_size = int(universe_size)
    if universe_size <= 0:
        return 0.0
    return (1.0 + float(universe_size)) / 2.0


def micro_meso_macro_normalized(cardinality: int, universe_size: int) -> float:
    """Map micro→0, meso centre→0.5, macro→1 on the closed A0–C8 cardinality span."""
    universe_size = int(universe_size)
    if universe_size <= 1:
        return 0.0 if int(cardinality) <= 1 else 1.0
    span = float(universe_size - 1)
    return round(min(1.0, max(0.0, (float(cardinality) - 1.0) / span)), 6)


def _ref_pitch_units(notes: list[NoteTuple], *, bin_cents: float) -> list[int]:
    units: list[int] = []
    for note in notes:
        if _note_in_reference_register(note):
            units.append(_pitch_unit(note, bin_cents=bin_cents))
    return units


def micro_macro_texture_params(bin_cents: float) -> dict[str, Any]:
    universe_size = reference_pitch_universe_size(bin_cents)
    meso_card = meso_pole_cardinality(universe_size)
    return {
        "reference_register": f"{REFERENCE_REGISTER_LOW}-{REFERENCE_REGISTER_HIGH}",
        "reference_ps_low": REFERENCE_PS_LOW,
        "reference_ps_high": REFERENCE_PS_HIGH,
        "reference_pitch_universe_size": universe_size,
        "micro_pole_cardinality": MICRO_POLE_CARDINALITY,
        "meso_pole_cardinality": meso_card,
        "macro_pole_cardinality": universe_size,
        "texture_scale": "micro_meso_macro",
        "micro_pole_normalized": 0.0,
        "meso_pole_normalized": 0.5,
        "macro_pole_normalized": 1.0,
    }


def validate_label_mode(label_mode: str | None = None) -> str:
    mode = DEFAULT_LABEL_MODE if label_mode is None else str(label_mode).strip().lower()
    if mode not in {LABEL_MODE_COUNT, LABEL_MODE_INDEX}:
        raise ValueError(f"label_mode must be '{LABEL_MODE_COUNT}' or '{LABEL_MODE_INDEX}' (got {label_mode!r})")
    return mode


def validate_label_count_thresholds(
    label_count_thresholds: tuple[int, int] | list[int] | None = None,
) -> tuple[int, int]:
    """Require ``1 <= micro_max_count < macro_min_count``."""
    raw = DEFAULT_LABEL_COUNT_THRESHOLDS if label_count_thresholds is None else label_count_thresholds
    try:
        pair = tuple(raw)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ValueError(
            "label_count_thresholds must be a pair (micro_max_count, macro_min_count) "
            "satisfying 1 <= micro_max_count < macro_min_count"
        ) from exc
    if len(pair) != 2:
        raise ValueError(
            "label_count_thresholds must be a pair (micro_max_count, macro_min_count) "
            "satisfying 1 <= micro_max_count < macro_min_count"
        )
    try:
        micro_max = int(pair[0])
        macro_min = int(pair[1])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "label_count_thresholds must be a pair of integers (micro_max_count, macro_min_count) "
            "satisfying 1 <= micro_max_count < macro_min_count"
        ) from exc
    if not (1 <= micro_max < macro_min):
        raise ValueError(
            "label_count_thresholds must satisfy 1 <= micro_max_count < macro_min_count "
            f"(got micro_max_count={micro_max}, macro_min_count={macro_min})"
        )
    return (micro_max, macro_min)


def validate_label_thresholds(
    label_thresholds: tuple[float, float] | list[float] | None = None,
) -> tuple[float, float]:
    """Require ``0 < micro_max < macro_min < 1``. Default pair is frozen at macro_min=0.35."""
    raw = DEFAULT_LABEL_THRESHOLDS if label_thresholds is None else label_thresholds
    try:
        pair = tuple(raw)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ValueError(
            "label_thresholds must be a pair (micro_max, macro_min) "
            "satisfying 0 < micro_max < macro_min < 1"
        ) from exc
    if len(pair) != 2:
        raise ValueError(
            "label_thresholds must be a pair (micro_max, macro_min) "
            "satisfying 0 < micro_max < macro_min < 1"
        )
    try:
        micro_max = float(pair[0])
        macro_min = float(pair[1])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "label_thresholds must be a pair (micro_max, macro_min) "
            "satisfying 0 < micro_max < macro_min < 1"
        ) from exc
    if not (0.0 < micro_max < macro_min < 1.0):
        raise ValueError(
            "label_thresholds must satisfy 0 < micro_max < macro_min < 1 "
            f"(got micro_max={micro_max}, macro_min={macro_min})"
        )
    return (micro_max, macro_min)


def texture_scale_label_from_count(
    cardinality: float,
    label_count_thresholds: tuple[int, int] | list[int] | None = None,
) -> str:
    """Absolute label from distinct-pitch count ``c``.

    ``micro`` if ``c <= micro_max_count``; ``macro`` if ``c >= macro_min_count``; else ``meso``.
    """
    micro_max, macro_min = validate_label_count_thresholds(label_count_thresholds)
    count = int(round(float(cardinality)))
    if count <= micro_max:
        return "micro"
    if count >= macro_min:
        return "macro"
    return "meso"


def texture_scale_label(
    x: float,
    label_thresholds: tuple[float, float] | list[float] | None = None,
) -> str:
    """Categorical label from ``x = (c-1)/(N-1)`` (index mode only).

    Frozen default ``macro_min`` is ``0.35``. ``micro`` if ``x < micro_max``;
    ``macro`` if ``x >= macro_min``; else ``meso``.
    """
    micro_max, macro_min = validate_label_thresholds(label_thresholds)
    value = float(x)
    if value < micro_max:
        return "micro"
    if value >= macro_min:
        return "macro"
    return "meso"


def result_scale_caret_column(x: float, *, width: int = RESULT_SCALE_WIDTH) -> int:
    """Column of ``^`` on a 0–1 ASCII scale: ``round(x * scale_width)``."""
    return int(round(float(x) * int(width)))


def count_scale_caret_column(
    count: float,
    universe_size: int,
    *,
    width: int = RESULT_SCALE_WIDTH,
) -> int:
    """Column of ``^`` on the 1..N count scale."""
    n = max(int(universe_size), 1)
    if n <= 1:
        return 0
    span = float(n - 1)
    return int(round((float(count) - 1.0) / span * float(width)))


def _has_microtones_merged(warnings: list[dict[str, Any]] | None) -> bool:
    return any(str(w.get("code") or "") == "microtones_merged" for w in (warnings or []))


def texture_label_fields_from_summary(
    summary: dict[str, Any],
    *,
    universe_size: int,
    label_mode: str | None = None,
    label_count_thresholds: tuple[int, int] | list[int] | None = None,
    label_thresholds: tuple[float, float] | list[float] | None = None,
    warnings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Derive label export fields from a duration-weighted interval summary."""
    mode = validate_label_mode(label_mode)
    count_thresholds = validate_label_count_thresholds(label_count_thresholds)
    index_thresholds = (
        validate_label_thresholds(label_thresholds) if mode == LABEL_MODE_INDEX else None
    )
    card = summary.get("micro_macro_pitch_cardinality") or {}
    mm = summary.get("micro_meso_macro_normalized") or {}
    if card.get("constant_value") is not None:
        basis = "constant_value"
        c_raw = float(card["constant_value"])
        x = float(mm["constant_value"]) if mm.get("constant_value") is not None else 0.0
    else:
        basis = "duration_weighted_mean"
        c_raw = float(card.get("duration_weighted_mean") or 0.0)
        x = float(mm.get("duration_weighted_mean") or 0.0)
    c_int = int(round(c_raw)) if mode == LABEL_MODE_COUNT else c_raw
    if mode == LABEL_MODE_COUNT:
        primary = texture_scale_label_from_count(c_int, count_thresholds)
        min_c = card.get("min_over_sounding_time")
        max_c = card.get("max")
        min_lab = (
            texture_scale_label_from_count(float(min_c), count_thresholds)
            if min_c is not None
            else None
        )
        max_lab = (
            texture_scale_label_from_count(float(max_c), count_thresholds)
            if max_c is not None
            else None
        )
        labeled_c = float(c_int)
    else:
        assert index_thresholds is not None
        primary = texture_scale_label(x, index_thresholds)
        min_x = mm.get("min_over_sounding_time")
        max_x = mm.get("max")
        min_lab = texture_scale_label(float(min_x), index_thresholds) if min_x is not None else None
        max_lab = texture_scale_label(float(max_x), index_thresholds) if max_x is not None else None
        labeled_c = c_raw
    display = primary
    if basis == "duration_weighted_mean" and min_lab and max_lab and min_lab != max_lab:
        display = f"{primary} (range: {min_lab} -> {max_lab})"
    reliable = not _has_microtones_merged(warnings)
    if not reliable:
        display = f"{display}{UNRELIABLE_LABEL_SUFFIX}"
    universe = int(universe_size)
    c_over_n = (float(labeled_c) / float(universe)) if universe > 0 else 0.0
    if universe > 1:
        index_from_c = (float(labeled_c) - 1.0) / float(universe - 1)
    else:
        index_from_c = 0.0
    out: dict[str, Any] = {
        "texture_scale_label": primary,
        "texture_scale_label_display": display,
        "texture_scale_label_reliable": reliable,
        "label_mode": mode,
        "label_count_thresholds": [int(count_thresholds[0]), int(count_thresholds[1])],
        "label_basis": basis,
        "reference_universe_size": universe,
        "index_value": float(x if mode == LABEL_MODE_INDEX else index_from_c),
        "cardinality": float(labeled_c),
        "c_over_n": float(c_over_n),
        "range_min_label": min_lab,
        "range_max_label": max_lab,
    }
    if mode == LABEL_MODE_INDEX and index_thresholds is not None:
        out["label_thresholds"] = [float(index_thresholds[0]), float(index_thresholds[1])]
    return out


def compute_texture_label_fields(analysis: dict[str, Any]) -> dict[str, Any]:
    """Label fields from an analysis dict (computes summary if missing)."""
    summary = analysis.get("summary") or compute_interval_summary(analysis.get("series") or [])
    mm_params = analysis.get("params", {}).get("micro_macro_texture", {})
    universe = int(
        analysis.get("reference_universe_size")
        or mm_params.get("reference_pitch_universe_size")
        or 0
    )
    mode = analysis.get("label_mode") or mm_params.get("label_mode")
    count_thr = analysis.get("label_count_thresholds")
    if count_thr is None:
        count_thr = mm_params.get("label_count_thresholds")
    index_thr = analysis.get("label_thresholds")
    if index_thr is None:
        index_thr = mm_params.get("label_thresholds")
    return texture_label_fields_from_summary(
        summary,
        universe_size=universe,
        label_mode=mode,
        label_count_thresholds=count_thr,
        label_thresholds=index_thr,
        warnings=analysis.get("warnings"),
    )


def _basis_display(basis: str) -> str:
    if basis == "constant_value":
        return "constant value"
    if basis == "duration_weighted_mean":
        return "duration-weighted mean"
    return str(basis)


def _universe_phrase(analysis: dict[str, Any], fields: dict[str, Any], *, style: str) -> str:
    n = int(fields.get("reference_universe_size") or 0)
    edo = int(analysis.get("edo") or analysis.get("params", {}).get("tuning", {}).get("edo") or 0)
    bin_cents = analysis.get("bin_cents")
    if bin_cents is None:
        bin_cents = analysis.get("params", {}).get("tuning", {}).get("bin_cents")
    bc = float(bin_cents) if bin_cents is not None else 0.0
    if style == "card":
        return f"{n} ({edo}-EDO, {bc:.0f}-cent bins, A0–C8)"
    return f"{n} ({edo}-EDO, A0-C8)"


def _ascii_scale_lines(
    x: float,
    micro_max: float,
    macro_min: float,
    *,
    width: int = RESULT_SCALE_WIDTH,
) -> tuple[str, str]:
    bar = ["-"] * (width + 1)
    bar[0] = "|"
    bar[width] = "|"
    bar[result_scale_caret_column(micro_max, width=width)] = "+"
    bar[result_scale_caret_column(macro_min, width=width)] = "+"
    scale = f"scale  micro {''.join(bar)} macro"
    prefix = "scale  micro "
    buf = [" "] * (len(prefix) + width + 1 + 16)

    def _put(pos_in_bar: int, text: str) -> None:
        start = len(prefix) + int(pos_in_bar)
        for i, ch in enumerate(text):
            j = start + i
            if 0 <= j < len(buf):
                buf[j] = ch

    _put(0, "0")
    _put(result_scale_caret_column(micro_max, width=width), f"{micro_max:.2f}")
    _put(result_scale_caret_column(macro_min, width=width), f"{macro_min:.2f}")
    _put(result_scale_caret_column(x, width=width), f"^{float(x):.2f}")
    _put(width, "1")
    return scale, "".join(buf).rstrip()


def _count_scale_lines(
    count: float,
    micro_max_count: int,
    macro_min_count: int,
    universe_size: int,
    *,
    width: int = RESULT_SCALE_WIDTH,
) -> tuple[str, str, str]:
    n = max(int(universe_size), 1)
    bar = ["-"] * (width + 1)
    bar[0] = "|"
    bar[width] = "|"
    p_micro = max(0, min(width, count_scale_caret_column(micro_max_count, n, width=width)))
    p_macro = max(0, min(width, count_scale_caret_column(macro_min_count, n, width=width)))
    bar[p_micro] = "+"
    bar[p_macro] = "+"
    prefix = "count scale  1 "
    scale = f"{prefix}{''.join(bar)} N={n}"
    ticks = [" "] * (len(prefix) + width + 1 + 8)
    caret = [" "] * (len(prefix) + width + 1 + 8)

    def _put(buf: list[str], pos_in_bar: int, text: str) -> None:
        start = len(prefix) + int(pos_in_bar)
        for i, ch in enumerate(text):
            j = start + i
            if 0 <= j < len(buf):
                buf[j] = ch

    _put(ticks, p_micro, str(int(micro_max_count)))
    _put(ticks, p_macro, str(int(macro_min_count)))
    c_int = int(round(float(count)))
    _put(caret, count_scale_caret_column(c_int, n, width=width), f"^ {c_int}")
    return scale, "".join(ticks).rstrip(), "".join(caret).rstrip()


def _heading_from_fields(fields: dict[str, Any]) -> str:
    label = str(fields["texture_scale_label"]).upper()
    display = str(fields["texture_scale_label_display"])
    heading = f"{label}-TEXTURE"
    if display != fields["texture_scale_label"]:
        rest = display[len(fields["texture_scale_label"]) :]
        heading = f"{label}-TEXTURE{rest}"
    return heading


def format_result_block(analysis: dict[str, Any]) -> str:
    """Framed ASCII RESULT block (pure ASCII; first block of every text summary)."""
    fields = compute_texture_label_fields(analysis)
    heading = _heading_from_fields(fields)
    c_txt = _fmt_card_value(fields["cardinality"])
    indent = "         "
    frame = "=" * RESULT_FRAME_WIDTH
    n = int(fields["reference_universe_size"] or 0)
    x = float(fields["index_value"])
    if fields["label_mode"] == LABEL_MODE_COUNT:
        micro_c, macro_c = fields["label_count_thresholds"]
        scale_line, tick_line, caret_line = _count_scale_lines(
            fields["cardinality"], micro_c, macro_c, n
        )
        lines = [
            frame,
            (
                f" RESULT  textural cardinality = {c_txt} distinct pitches "
                f"(duplications excluded)  ->  {heading}"
            ),
            f"{indent}label rule (pitch counts): micro <= {micro_c} < meso < {macro_c} <= macro",
            f"{indent}{scale_line}",
            f"{indent}{tick_line}",
            f"{indent}{caret_line}",
            (
                f"{indent}secondary: normalised occupation (c-1)/(N-1) = {x:.4f} "
                f"(grid-relative, N = {n})"
            ),
            frame,
        ]
        return "\n".join(lines)
    micro_max, macro_min = fields["label_thresholds"]
    scale_line, num_line = _ascii_scale_lines(x, micro_max, macro_min)
    universe = _universe_phrase(analysis, fields, style="ascii")
    lines = [
        frame,
        f" RESULT  textural cardinality = {c_txt} distinct pitches (duplications excluded)",
        f"{indent}index (c-1)/(N-1) = {x:.4f}   ->   {heading}",
        f"{indent}{scale_line}",
        f"{indent}{num_line}",
        (
            f"{indent}universe N = {universe} | "
            f"thresholds {micro_max:.2f} / {macro_min:.2f} (frozen default {FROZEN_INDEX_THRESHOLD:.2f}) | "
            f"basis: {_basis_display(fields['label_basis'])}"
        ),
        frame,
    ]
    return "\n".join(lines)


def format_result_card_markdown(analysis: dict[str, Any]) -> str:
    """Highlighted GUI card: large headline plus a coloured word badge."""
    fields = compute_texture_label_fields(analysis)
    label = str(fields["texture_scale_label"])
    color = LABEL_BADGE_COLORS.get(label, "#444444")
    heading = f"{label.upper()}-TEXTURE"
    badge = (
        f'<span style="display:inline-block;background:{color};color:#ffffff;'
        f"padding:2px 10px;border-radius:4px;font-weight:700;"
        f'letter-spacing:0.04em">{label.upper()}</span>'
    )
    extra = ""
    display = str(fields["texture_scale_label_display"])
    if display != label:
        extra = display[len(label) :].replace("->", "→")
    c_txt = _fmt_card_value(fields["cardinality"])
    n = int(fields["reference_universe_size"] or 0)
    if fields["label_mode"] == LABEL_MODE_COUNT:
        micro_c, macro_c = fields["label_count_thresholds"]
        return (
            f"### Textural cardinality: **{c_txt} distinct pitches** → **{heading}** {badge}{extra}\n\n"
            f"label rule (pitch counts): micro ≤ {micro_c} < meso < {macro_c} ≤ macro\n\n"
            f"secondary: normalised occupation (c−1)/(N−1) = **{fields['index_value']:.4f}** "
            f"(grid-relative, N = {n})"
        )
    micro_max, macro_min = fields["label_thresholds"]
    universe = _universe_phrase(analysis, fields, style="card")
    return (
        f"### Textural cardinality: **{c_txt} distinct pitches** → **{heading}** {badge}{extra}\n\n"
        f"index (c−1)/(N−1) = **{fields['index_value']:.3f}** · "
        f"c/N = {fields['c_over_n']:.3f} · universe N = {universe}\n\n"
        f"thresholds: micro < {micro_max:.2f} ≤ meso < {macro_min:.2f} ≤ macro "
        f"(frozen default {FROZEN_INDEX_THRESHOLD:.2f}) · "
        f"basis: {_basis_display(fields['label_basis'])}"
    )


def format_settings_line(analysis: dict[str, Any]) -> str:
    params = analysis.get("params") or {}
    repair = params.get("microtone_repair", analysis.get("microtone_repair", DEFAULT_MICROTONEREPAIR))
    ref = params.get("pitch_reference", analysis.get("pitch_reference", DEFAULT_PITCH_REFERENCE))
    n_repairs = len(analysis.get("repairs") or [])
    n_overrides = len(analysis.get("pitch_overrides") or [])
    n_warnings = len(analysis.get("warnings") or [])
    return (
        f"settings: microtone_repair={repair} | pitch_reference={ref} | "
        f"repairs={n_repairs} | overrides={n_overrides} | warnings={n_warnings}"
    )


def format_pitches_line(analysis: dict[str, Any]) -> str:
    digest = analysis.get("pitch_inventory_digest") or {}
    n_notes = digest.get("n_notes")
    n_unique = digest.get("n_unique_sounding")
    mn = digest.get("min")
    mx = digest.get("max")
    if n_notes is None and n_unique is None and mn is None:
        return "pitches:  n_notes=n/a n_unique=n/a min=n/a max=n/a"
    min_s = "n/a" if mn is None else f"{format_pitch_name(float(mn))} ({format_ps_display(float(mn))})"
    max_s = "n/a" if mx is None else f"{format_pitch_name(float(mx))} ({format_ps_display(float(mx))})"
    return (
        f"pitches:  n_notes={n_notes if n_notes is not None else 'n/a'} "
        f"n_unique={n_unique if n_unique is not None else 'n/a'} "
        f"min={min_s} max={max_s}"
    )


def format_summary_metadata(analysis: dict[str, Any]) -> str:
    mm_params = analysis.get("params", {}).get("micro_macro_texture", {})
    fields = compute_texture_label_fields(analysis)
    lo = mm_params.get("micro_pole_cardinality", 1)
    mid = mm_params.get("meso_pole_cardinality", "n/a")
    hi = mm_params.get("macro_pole_cardinality", "n/a")
    mode = fields["label_mode"]
    if mode == LABEL_MODE_COUNT:
        micro_c, macro_c = fields["label_count_thresholds"]
        rule = f"Label rule (pitch counts): micro <= {micro_c} < meso < {macro_c} <= macro"
    else:
        micro_max, macro_min = fields["label_thresholds"]
        rule = (
            f"Label rule (index, frozen default {FROZEN_INDEX_THRESHOLD:.2f}): "
            f"x < {micro_max:.2f} / x >= {macro_min:.2f}"
        )
    return (
        f"File: {analysis.get('source_file_name', 'unknown')}\n"
        f"Duration (quarters): {float(analysis.get('duration_quarters') or 0.0):.3f}\n"
        f"Time step (supplementary grid): {analysis.get('time_step')}\n"
        f"Sampling: {analysis.get('sampling', 'n/a')}\n"
        f"Reference register: {mm_params.get('reference_register', 'A0-C8')}\n"
        f"Reference universe size: {mm_params.get('reference_pitch_universe_size', fields['reference_universe_size'])}\n"
        f"Index scale anchors (min / midpoint / max) — not labels: {lo} / {mid} / {hi}\n"
        f"Index scale anchors (min / midpoint / max) — not labels: 0.0 / 0.5 / 1.0\n"
        f"Label mode: {mode}\n"
        f"{rule}\n"
        f"EDO: {analysis.get('edo', 12)}\n"
        f"Pitch-class universe: {analysis.get('pitch_class_universe', 'Z12')}\n"
        f"Tuning provenance: {analysis.get('params', {}).get('tuning', {}).get('tuning_provenance', 'n/a')}\n"
        f"Events: {analysis.get('event_count', 'n/a')}\n"
        f"Sample points: {analysis.get('sample_count', len(analysis.get('series') or []))}"
    )


def _is_multiple_of_step(value: float, step: float, tol: float = _TOL) -> bool:
    nearest = round(value / step)
    return abs(value - nearest * step) <= tol


def _iter_raw_pitches(events: list[dict[str, Any]]) -> list[tuple[int | None, float | None, float]]:
    out: list[tuple[int | None, float | None, float]] = []
    for ev in events:
        for rp in ev.get("raw_pitches", []):
            out.append((rp.get("part_index"), rp.get("beat"), float(rp["ps"])))
    return out


def _non_grid_pitches(
    events: list[dict[str, Any]],
    *,
    bin_cents: float,
    tol: float = _TOL,
) -> list[tuple[int | None, float | None, float]]:
    bad: list[tuple[int | None, float | None, float]] = []
    for part_index, beat, ps in _iter_raw_pitches(events):
        nearest = round((ps * 100.0) / bin_cents)
        snapped = (nearest * bin_cents) / 100.0
        if abs(ps - snapped) > tol:
            bad.append((part_index, beat, ps))
    return bad


def _requantize_events(events: list[dict[str, Any]], *, bin_cents: float, edo: int) -> None:
    for ev in events:
        pitches = ev["notes"]
        ev["units"] = [_pitch_unit(n, bin_cents=bin_cents) for n in pitches]
        ev["pcs"] = [_pc_class(n, edo=edo) for n in pitches]
        ev["ref_units"] = _ref_pitch_units(pitches, bin_cents=bin_cents)


def detect_tuning_grid(events: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Inspect every event pitch-space value and infer a compatible EDO grid.
    """
    raw = _iter_raw_pitches(events)
    if not raw:
        return {
            "detected_bin_cents": DEFAULT_BIN_CENTS,
            "detected_edo": DEFAULT_EDO,
            "tuning_preset_match": "12_edo",
            "non_grid_pitches": [],
        }

    fracs: list[float] = []
    for _, _, ps in raw:
        frac = ps - math.floor(ps)
        if abs(frac - 1.0) <= _TOL or abs(frac) <= _TOL:
            frac = 0.0
        fracs.append(frac)

    if all(abs(frac) <= _TOL for frac in fracs):
        return {
            "detected_bin_cents": DEFAULT_BIN_CENTS,
            "detected_edo": DEFAULT_EDO,
            "tuning_preset_match": "12_edo",
            "non_grid_pitches": [],
        }

    candidates = [
        ("24_edo", 0.5, 50.0, 24),
        ("48_edo", 0.25, 25.0, 48),
        (None, 1.0 / 3.0, 100.0 / 3.0, 36),
        (None, 1.0 / 6.0, 100.0 / 6.0, 72),
    ]
    for preset_name, step, bin_cents, edo in candidates:
        if all(_is_multiple_of_step(frac, step) for frac in fracs):
            return {
                "detected_bin_cents": float(bin_cents),
                "detected_edo": int(edo),
                "tuning_preset_match": preset_name,
                "non_grid_pitches": [],
            }

    best_edo: int | None = None
    for edo in range(2, 241):
        step = 12.0 / float(edo)
        if all(_is_multiple_of_step(frac, step) for frac in fracs):
            best_edo = edo
    if best_edo is not None:
        best_bin = 1200.0 / float(best_edo)
        preset_name: str | None = None
        for name, preset in TUNING_PRESETS.items():
            if (
                int(preset["edo"]) == best_edo
                and abs(float(preset["bin_cents"]) - best_bin) <= _TOL
            ):
                preset_name = name
                break
        return {
            "detected_bin_cents": best_bin,
            "detected_edo": best_edo,
            "tuning_preset_match": preset_name,
            "non_grid_pitches": [],
        }

    return {
        "detected_bin_cents": DEFAULT_BIN_CENTS,
        "detected_edo": DEFAULT_EDO,
        "tuning_preset_match": None,
        "non_grid_pitches": _non_grid_pitches(events, bin_cents=DEFAULT_BIN_CENTS),
    }


def _collect_events(
    score: Score,
    *,
    edo: int = 12,
    bin_cents: float = 100.0,
) -> tuple[list[dict[str, Any]], float]:
    edo = validate_edo(edo)
    bin_cents = validate_bin_cents(bin_cents)
    part_index_map: dict[int, int] = {id(part): i for i, part in enumerate(score.parts)}
    events: list[dict[str, Any]] = []
    end_time = 0.0
    for el in score.recurse().notes:
        # Use score-global offset (not local measure/voice offset).
        offset = float(el.getOffsetInHierarchy(score))
        duration = float(el.duration.quarterLength) if el.duration is not None else 0.0
        end = offset + max(0.0, duration)
        pitches: list[NoteTuple] = []
        raw_pitches: list[dict[str, Any]] = []
        part = el.getContextByClass("Part")
        part_index = part_index_map.get(id(part)) if part is not None else None
        beat_value = float(el.beat) if getattr(el, "beat", None) is not None else offset
        excluded = excluded_indices(el)
        if isinstance(el, Note):
            if 0 not in excluded:
                nt = _pitch_to_note_tuple(el.pitch)
                if nt is not None:
                    pitches.append(nt)
                    raw_pitches.append(
                        {
                            "part_index": part_index,
                            "beat": beat_value,
                            "ps": float(el.pitch.ps),
                        }
                    )
        elif isinstance(el, Chord):
            for i, p in enumerate(el.pitches):
                if i in excluded:
                    continue
                nt = _pitch_to_note_tuple(p)
                if nt is not None:
                    pitches.append(nt)
                    raw_pitches.append(
                        {
                            "part_index": part_index,
                            "beat": beat_value,
                            "ps": float(p.ps),
                        }
                    )
        if not pitches:
            continue
        events.append(
            {
                "offset": offset,
                "end": end,
                "notes": pitches,
                "units": [_pitch_unit(n, bin_cents=bin_cents) for n in pitches],
                "pcs": [_pc_class(n, edo=edo) for n in pitches],
                "ref_units": _ref_pitch_units(pitches, bin_cents=bin_cents),
                "raw_pitches": raw_pitches,
            }
        )
        end_time = max(end_time, end)
    return events, end_time


def _time_axis(
    end_time: float,
    time_step: float | None,
    events: list[dict[str, Any]] | None = None,
) -> list[float]:
    """
    Build analysis times that include every vertical state change.

    Event onsets and offsets are always included so brief sonorities are not
    missed between coarse uniform grid points. When ``time_step`` is set, a
    regular grid is merged in for plotting convenience.
    """
    times: set[float] = {0.0}
    if end_time > 0.0:
        times.add(round(end_time, 6))

    if events:
        for ev in events:
            times.add(round(float(ev["offset"]), 6))
            times.add(round(float(ev["end"]), 6))

    if time_step is not None:
        step = max(1e-6, float(time_step))
        t = 0.0
        while t <= end_time + 1e-9:
            times.add(round(t, 6))
            t += step

    if not times:
        times.add(0.0)
    return sorted(times)


def _build_cardinality_series(
    times: list[float],
    events: list[dict[str, Any]],
    *,
    reference_universe_size: int,
) -> list[dict[str, Any]]:
    if not times:
        return []

    starts = sorted(events, key=lambda ev: (float(ev["offset"]), float(ev["end"])))
    ends = sorted(events, key=lambda ev: (float(ev["end"]), float(ev["offset"])))
    si = 0
    ei = 0

    active_note_count = 0
    active_units: Counter[int] = Counter()
    active_pcs: Counter[int] = Counter()
    active_ref_units: Counter[int] = Counter()

    series: list[dict[str, Any]] = []
    for t in times:
        # Half-open activity semantics [onset, offset): a note is inactive at t == end,
        # so it is removed once end <= t (no release-inclusive overlap spike at shared
        # boundaries). Zero-duration events span an empty half-open interval and therefore
        # contribute no vertical cardinality.
        while ei < len(ends) and float(ends[ei]["end"]) <= t + _EPS:
            ev = ends[ei]
            ei += 1
            if (float(ev["end"]) - float(ev["offset"])) <= _EPS:
                continue
            active_note_count -= len(ev["notes"])
            for unit in ev["units"]:
                active_units[unit] -= 1
                if active_units[unit] <= 0:
                    del active_units[unit]
            for pc in ev["pcs"]:
                active_pcs[pc] -= 1
                if active_pcs[pc] <= 0:
                    del active_pcs[pc]
            for unit in ev.get("ref_units", []):
                active_ref_units[unit] -= 1
                if active_ref_units[unit] <= 0:
                    del active_ref_units[unit]

        while si < len(starts) and float(starts[si]["offset"]) <= t + _EPS:
            ev = starts[si]
            si += 1
            if (float(ev["end"]) - float(ev["offset"])) <= _EPS:
                continue
            active_note_count += len(ev["notes"])
            active_units.update(ev["units"])
            active_pcs.update(ev["pcs"])
            active_ref_units.update(ev.get("ref_units", []))

        mm_card = len(active_ref_units)
        series.append(
            {
                "time_quarters": t,
                "vertical_note_count": int(active_note_count),
                "vertical_unique_pitch_count": int(len(active_units)),
                "vertical_pitch_class_cardinality": int(len(active_pcs)),
                "micro_macro_pitch_cardinality": int(mm_card),
                "micro_macro_normalized": micro_macro_normalized(mm_card, reference_universe_size),
                "micro_meso_macro_normalized": micro_meso_macro_normalized(
                    mm_card, reference_universe_size
                ),
            }
        )
    return series


def compute_interval_summary(series: list[dict[str, Any]]) -> dict[str, Any]:
    """Duration-weighted stats over half-open intervals, excluding the terminal sample."""
    empty_metric = {
        "duration_weighted_mean": 0.0,
        "min_over_sounding_time": None,
        "max": None,
        "constant_value": None,
    }
    if len(series) < 2:
        return {"silent_duration": 0.0, **{m: dict(empty_metric) for m in SUMMARY_METRICS}}

    silent = 0.0
    acc: dict[str, dict[str, Any]] = {
        m: {"weighted_sum": 0.0, "dur": 0.0, "sounding": []} for m in SUMMARY_METRICS
    }
    for i in range(len(series) - 1):
        t0 = float(series[i]["time_quarters"])
        t1 = float(series[i + 1]["time_quarters"])
        dur = t1 - t0
        if dur <= _EPS:
            continue
        row = series[i]
        sounding = float(row.get("vertical_note_count") or 0) > 0
        if not sounding:
            silent += dur
        for metric in SUMMARY_METRICS:
            val = float(row.get(metric) or 0.0)
            acc[metric]["weighted_sum"] += val * dur
            acc[metric]["dur"] += dur
            if sounding:
                acc[metric]["sounding"].append(val)

    out: dict[str, Any] = {"silent_duration": float(silent)}
    for metric in SUMMARY_METRICS:
        info = acc[metric]
        total = float(info["dur"])
        mean = (info["weighted_sum"] / total) if total > 0 else 0.0
        sounding_vals: list[float] = info["sounding"]
        if sounding_vals:
            mn = min(sounding_vals)
            mx = max(sounding_vals)
            const = mn if abs(mn - mx) <= _TOL else None
        else:
            mn = None
            mx = None
            const = None
        out[metric] = {
            "duration_weighted_mean": float(mean),
            "min_over_sounding_time": mn,
            "max": mx,
            "constant_value": const,
        }
    return out


def _fmt_card_value(value: float | None) -> str:
    if value is None:
        return "n/a"
    if abs(float(value) - round(float(value))) <= _TOL:
        return f"{int(round(float(value)))}"
    return f"{float(value):.4f}"


def format_analysis_summary(analysis: dict[str, Any]) -> str:
    """RESULT frame, settings, pitches, metadata, duration-weighted, then legacy line."""
    series = analysis.get("series") or []
    summary = analysis.get("summary") or compute_interval_summary(series)
    lines = [
        format_result_block(analysis),
        format_settings_line(analysis),
        format_pitches_line(analysis),
        format_summary_metadata(analysis),
        "duration-weighted interval statistics (excludes terminal boundary):",
    ]
    for metric in SUMMARY_METRICS:
        block = summary.get(metric) or {}
        extra = ""
        if metric == "vertical_note_count":
            extra = " (includes duplications; not part of the micro/macro index)"
        lines.append(
            f"  {metric}: mean={_fmt_card_value(block.get('duration_weighted_mean'))} "
            f"min_sounding={_fmt_card_value(block.get('min_over_sounding_time'))} "
            f"max={_fmt_card_value(block.get('max'))}"
            + (
                f" constant_value={_fmt_card_value(block.get('constant_value'))}"
                if block.get("constant_value") is not None
                else ""
            )
            + extra
        )
    lines.append(f"silent_duration: {float(summary.get('silent_duration') or 0.0):.3f}")

    note_values = [float(r.get("vertical_note_count") or 0) for r in series] or [0.0]
    unique_values = [float(r.get("vertical_unique_pitch_count") or 0) for r in series] or [0.0]
    pc_values = [float(r.get("vertical_pitch_class_cardinality") or 0) for r in series] or [0.0]
    mm_values = [float(r.get("micro_meso_macro_normalized") or 0) for r in series] or [0.0]
    mm_macro_ratio_values = [float(r.get("micro_macro_normalized") or 0) for r in series] or [0.0]
    mm_card_values = [float(r.get("micro_macro_pitch_cardinality") or 0) for r in series] or [0.0]

    lines.append("point-sample statistics (includes terminal boundary)")
    lines.append(
        f"Micro–Meso–Macro cardinality min/max/mean: "
        f"{min(mm_card_values):.0f}/{max(mm_card_values):.0f}/{statistics.fmean(mm_card_values):.2f}"
    )
    lines.append(
        f"Micro–Meso–Macro normalized min/max/mean: "
        f"{min(mm_values):.3f}/{max(mm_values):.3f}/{statistics.fmean(mm_values):.3f}"
    )
    lines.append(
        f"Macro-ratio normalized min/max/mean: "
        f"{min(mm_macro_ratio_values):.3f}/{max(mm_macro_ratio_values):.3f}/"
        f"{statistics.fmean(mm_macro_ratio_values):.3f}"
    )
    lines.append(
        f"Note Count min/max/mean: {min(note_values):.0f}/{max(note_values):.0f}/{statistics.fmean(note_values):.2f}"
    )
    lines.append(
        f"Unique Pitch min/max/mean: {min(unique_values):.0f}/{max(unique_values):.0f}/{statistics.fmean(unique_values):.2f}"
    )
    lines.append(
        f"PC Cardinality min/max/mean: {min(pc_values):.0f}/{max(pc_values):.0f}/{statistics.fmean(pc_values):.2f}"
    )
    return "\n".join(lines)


def _merge_tied_notes(score: Score) -> tuple[Score, bool]:
    """
    Merge tied note chains into single sustained events before event extraction.

    A tie start + continuation(s) becomes one event spanning the union duration via
    music21 ``stripTies`` (``matchByPitch=True`` so chord-internal and pitch-matched ties
    merge while untied members remain separate). Rearticulated (untied) notes are left
    as distinct events. On any music21 failure the original score is returned with
    ``ok=False`` so analysis can still proceed (and emit a ``tie_merge_failed`` warning).
    """
    try:
        merged = score.stripTies(inPlace=False, matchByPitch=True)
        if merged is None:
            return score, False
        return merged, True
    except Exception:
        return score, False


def inspect_score_pitches(
    score_path: str,
    *,
    microtone_repair: str = DEFAULT_MICROTONEREPAIR,
    pitch_reference: str = DEFAULT_PITCH_REFERENCE,
    bin_cents: float = DEFAULT_BIN_CENTS,
    edo: int = DEFAULT_EDO,
    pitch_overrides: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Parse, repair, convert, and build the pre-tie-merge pitch inventory."""
    del edo
    bin_cents = validate_bin_cents(bin_cents)
    repair_mode = normalize_microtone_repair(microtone_repair)
    ref = normalize_pitch_reference(pitch_reference)
    is_midi = is_midi_score_path(score_path)
    score = converter.parse(score_path)
    score, repair_msgs, repairs = apply_microtone_repair(score, repair_mode, is_midi=is_midi)
    prepared = prepare_score_for_analysis(
        score,
        pitch_reference=ref,
        pitch_overrides=pitch_overrides,
        register_low_ps=REFERENCE_PS_LOW,
        register_high_ps=REFERENCE_PS_HIGH,
        repairs=repairs,
        bin_cents=bin_cents,
    )
    warnings: list[dict[str, Any]] = []
    if is_midi and bin_cents < DEFAULT_BIN_CENTS - _TOL:
        warnings.append(_struct_warning("midi_microtones_not_recoverable", WARN_MIDI_BIN_CENTS))
    if repair_mode == "warn" and repair_msgs:
        n_mismatch = len(detect_accidental_alter_mismatch(converter.parse(score_path)))
        for msg in repair_msgs:
            warnings.append(
                _struct_warning("microtone_glyph_alter_mismatch", msg, details={"n": n_mismatch})
            )
    elif repair_mode == "from_accidentals":
        for msg in repair_msgs:
            warnings.append(_struct_warning("microtone_repaired", msg, details={"n": len(repairs)}))
    for msg in prepared.warnings:
        code = "manual_overrides" if "override" in msg.lower() else "transposing_parts_written"
        warnings.append(_struct_warning(code, msg))
    oor = out_of_register_notes(prepared.inventory)
    if oor:
        warnings.append(
            _struct_warning(
                "out_of_register_notes",
                (
                    f"{len(oor)} pitched note(s) lie outside A0–C8. "
                    "vertical_unique_pitch_count includes them; micro_macro_* does not."
                ),
                details={"n": len(oor), "min_ps": min(oor), "max_ps": max(oor)},
            )
        )
    digest = pitch_inventory_digest(prepared.inventory, bin_cents=bin_cents)
    return {
        "pitch_inventory": public_inventory_rows(prepared.inventory),
        "pitch_inventory_raw": prepared.inventory,
        "pitch_inventory_digest": digest,
        "digest_line": inventory_digest_line(digest),
        "transposing_parts": prepared.transposing_parts,
        "repairs": repairs,
        "pitch_overrides": prepared.pitch_overrides,
        "warnings": warnings,
        "microtone_repair": repair_mode,
        "pitch_reference": ref,
    }


def analyze_vertical_cardinality(
    score_path: str,
    *,
    time_step: float | None = 0.25,
    edo: int = DEFAULT_EDO,
    bin_cents: float = DEFAULT_BIN_CENTS,
    auto_detect_tuning: bool = False,
    tuning_preset: str | None = None,
    merge_ties: bool = True,
    debug_export_internal_path: bool = False,
    microtone_repair: str = DEFAULT_MICROTONEREPAIR,
    pitch_reference: str = DEFAULT_PITCH_REFERENCE,
    pitch_overrides: list[dict[str, Any]] | None = None,
    label_mode: str = DEFAULT_LABEL_MODE,
    label_count_thresholds: tuple[int, int] | list[int] | None = None,
    label_thresholds: tuple[float, float] | list[float] | None = None,
) -> dict[str, Any]:
    edo = validate_edo(edo)
    bin_cents = validate_bin_cents(bin_cents)
    mode = validate_label_mode(label_mode)
    count_thresholds = validate_label_count_thresholds(label_count_thresholds)
    index_thresholds = (
        validate_label_thresholds(label_thresholds) if mode == LABEL_MODE_INDEX else None
    )
    if tuning_preset is not None and tuning_preset not in TUNING_PRESETS:
        raise ValueError(f"Unknown tuning_preset: {tuning_preset}")
    repair_mode = normalize_microtone_repair(microtone_repair)
    ref = normalize_pitch_reference(pitch_reference)
    overrides = normalize_pitch_overrides(pitch_overrides)
    is_midi = is_midi_score_path(score_path)

    score = converter.parse(score_path)
    parsed_for_mismatch = score
    score, repair_msgs, repairs = apply_microtone_repair(score, repair_mode, is_midi=is_midi)
    prepared = prepare_score_for_analysis(
        score,
        pitch_reference=ref,
        pitch_overrides=overrides,
        register_low_ps=REFERENCE_PS_LOW,
        register_high_ps=REFERENCE_PS_HIGH,
        repairs=repairs,
        bin_cents=bin_cents,
    )
    score = prepared.score
    tie_merge_ok = True
    if merge_ties:
        score, tie_merge_ok = _merge_tied_notes(score)
    events, end_time = _collect_events(score, edo=DEFAULT_EDO, bin_cents=DEFAULT_BIN_CENTS)

    explicit_params = (abs(bin_cents - DEFAULT_BIN_CENTS) > _TOL) or (edo != DEFAULT_EDO)
    active_bin_cents = DEFAULT_BIN_CENTS
    active_edo = DEFAULT_EDO
    active_preset: str | None = "12_edo"
    tuning_provenance = "default_12_edo"
    auto_detected_from_n_events: int | None = None

    if explicit_params:
        active_bin_cents = bin_cents
        active_edo = edo
        tuning_provenance = "explicit_bin_cents_edo"
        for name, preset in TUNING_PRESETS.items():
            if (
                int(preset["edo"]) == active_edo
                and abs(float(preset["bin_cents"]) - active_bin_cents) <= _TOL
            ):
                active_preset = name
                break
        else:
            active_preset = None
    elif tuning_preset is not None:
        preset = TUNING_PRESETS[tuning_preset]
        active_bin_cents = float(preset["bin_cents"])
        active_edo = int(preset["edo"])
        active_preset = tuning_preset
        tuning_provenance = "tuning_preset"
    elif auto_detect_tuning:
        detected = detect_tuning_grid(events)
        active_bin_cents = float(detected["detected_bin_cents"])
        active_edo = int(detected["detected_edo"])
        active_preset = detected.get("tuning_preset_match")
        tuning_provenance = "auto_detected"
        auto_detected_from_n_events = len(events)

    _requantize_events(events, bin_cents=active_bin_cents, edo=active_edo)
    refresh_quantised_ps(prepared.inventory, bin_cents=active_bin_cents, pitch_reference=ref)
    digest = pitch_inventory_digest(prepared.inventory, bin_cents=active_bin_cents)
    non_grid = _non_grid_pitches(events, bin_cents=active_bin_cents)
    warnings: list[dict[str, Any]] = []
    if is_midi and active_bin_cents < DEFAULT_BIN_CENTS - _TOL:
        warnings.append(_struct_warning("midi_microtones_not_recoverable", WARN_MIDI_BIN_CENTS))
    if repair_mode == "warn":
        n_mismatch = len(detect_accidental_alter_mismatch(parsed_for_mismatch))
        for msg in repair_msgs:
            warnings.append(
                _struct_warning("microtone_glyph_alter_mismatch", msg, details={"n": n_mismatch})
            )
    elif repair_mode == "from_accidentals":
        for msg in repair_msgs:
            warnings.append(
                _struct_warning("microtone_repaired", msg, details={"n": len(repairs)})
            )
    for msg in prepared.warnings:
        code = "manual_overrides" if "override" in msg.lower() else "transposing_parts_written"
        warnings.append(_struct_warning(code, msg, details={"n": len(overrides)} if code == "manual_overrides" else {}))
    if abs(float(active_bin_cents) * float(active_edo) - 1200.0) > 1e-6:
        warnings.append(
            _struct_warning(
                "inconsistent_tuning_pair",
                (
                    "bin_cents and edo are inconsistent (bin_cents × edo ≠ 1200). "
                    "Universe size and pitch quantisation follow bin_cents; "
                    "pitch-class cardinality follows edo."
                ),
                details={
                    "bin_cents": float(active_bin_cents),
                    "edo": int(active_edo),
                    "product": float(active_bin_cents) * float(active_edo),
                },
            )
        )
    sounding_ps = [
        float(r["_sounding_ps"])
        for r in prepared.inventory
        if not r.get("_unpitched") and r.get("_sounding_ps") not in (None, "")
    ]
    has_fractional = any(abs(ps - round(ps)) > _TOL for ps in sounding_ps)
    if has_fractional and abs(active_bin_cents - DEFAULT_BIN_CENTS) <= _TOL:
        n_before = len({round(ps, 6) for ps in sounding_ps})
        n_after = len({int(r["quantised_ps"]) for r in prepared.inventory if r.get("quantised_ps") is not None})
        warnings.append(
            _struct_warning(
                "microtones_merged",
                (
                    f"{n_before} distinct sounding pitches were merged to {n_after} "
                    "quantised units on the 100-cent grid. Halfway ties follow "
                    "half-to-even (banker's) rounding."
                ),
                details={"n_before": n_before, "n_after": n_after},
            )
        )
    oor = out_of_register_notes(prepared.inventory)
    if oor:
        warnings.append(
            _struct_warning(
                "out_of_register_notes",
                (
                    f"{len(oor)} pitched note(s) lie outside A0–C8. "
                    "vertical_unique_pitch_count includes them; micro_macro_* does not."
                ),
                details={"n": len(oor), "min_ps": min(oor), "max_ps": max(oor)},
            )
        )
    if non_grid:
        warnings.append(
            {
                "code": "non_grid_pitches",
                "severity": "warning",
                "message": (
                    "The score contains pitches that cannot be quantised exactly "
                    "to the active tuning grid. These events have been quantised "
                    "to the nearest grid point. Consider increasing the grid "
                    "resolution (smaller bin_cents) or supplying a custom "
                    "tuning."
                ),
                "details": {
                    "n_non_grid_pitches": len(non_grid),
                    "active_bin_cents": float(active_bin_cents),
                    "active_edo": int(active_edo),
                    "sample": non_grid[:5],
                },
            }
        )
    if merge_ties and not tie_merge_ok:
        warnings.append(
            {
                "code": "tie_merge_failed",
                "severity": "warning",
                "message": (
                    "music21 stripTies could not merge tied notes for this score; "
                    "tied continuations may be counted as separate events."
                ),
                "details": {},
            }
        )
    n_zero_duration = sum(
        1 for ev in events if (float(ev["end"]) - float(ev["offset"])) <= _EPS
    )
    if n_zero_duration:
        warnings.append(
            {
                "code": "zero_duration_events",
                "severity": "info",
                "message": (
                    "Zero-duration events (e.g. notated grace notes with no duration) "
                    "contribute no vertical cardinality under half-open [onset, offset) "
                    "activity semantics."
                ),
                "details": {"n_zero_duration_events": int(n_zero_duration)},
            }
        )

    times = _time_axis(end_time, time_step, events)
    ref_universe_size = reference_pitch_universe_size(active_bin_cents)
    series = _build_cardinality_series(times, events, reference_universe_size=ref_universe_size)
    interval_summary = compute_interval_summary(series)
    mm_params = micro_macro_texture_params(active_bin_cents)
    mm_params["label_mode"] = mode
    mm_params["label_count_thresholds"] = [int(count_thresholds[0]), int(count_thresholds[1])]
    if index_thresholds is not None:
        mm_params["label_thresholds"] = [float(index_thresholds[0]), float(index_thresholds[1])]
    label_fields = texture_label_fields_from_summary(
        interval_summary,
        universe_size=ref_universe_size,
        label_mode=mode,
        label_count_thresholds=count_thresholds,
        label_thresholds=index_thresholds,
        warnings=warnings,
    )
    result: dict[str, Any] = {
        "schema_version": JSON_EXPORT_SCHEMA_VERSION,
        "source_file_name": Path(str(score_path)).name,
        "time_step": float(time_step) if time_step is not None else None,
        "sampling": (
            "event_boundaries_with_uniform_grid"
            if time_step is not None
            else "event_boundaries_only"
        ),
        "duration_quarters": float(end_time),
        "event_count": len(events),
        "sample_count": len(times),
        "edo": int(active_edo),
        "pitch_class_universe": f"Z{active_edo}",
        "bin_cents": float(active_bin_cents),
        "warnings": warnings,
        "params": {
            "temporal_semantics": {
                "activity_interval": "half_open_onset_offset",
                "active_predicate": "onset <= t < offset",
                "tie_handling": "merge_tied_notes" if merge_ties else "as_imported",
                "tie_merge_applied": bool(merge_ties and tie_merge_ok),
                "zero_duration_policy": "ignored_no_contribution",
            },
            "micro_macro_texture": mm_params,
            "tuning": {
                "bin_cents": float(active_bin_cents),
                "edo": int(active_edo),
                "tuning_preset": active_preset,
                "tuning_provenance": tuning_provenance,
                "auto_detected_from_n_events": auto_detected_from_n_events,
                "non_grid_pitches_count": len(non_grid),
                "non_grid_pitches_sample": non_grid[:5],
            },
            "pitch_pipeline": list(PITCH_PIPELINE_ORDER),
            "microtone_repair": repair_mode,
            "pitch_reference": ref,
        },
        "series": series,
        "summary": interval_summary,
        "texture_scale_label": label_fields["texture_scale_label"],
        "texture_scale_label_reliable": label_fields["texture_scale_label_reliable"],
        "label_mode": mode,
        "label_count_thresholds": [int(count_thresholds[0]), int(count_thresholds[1])],
        "label_basis": label_fields["label_basis"],
        "reference_universe_size": int(ref_universe_size),
        "pitch_inventory": public_inventory_rows(prepared.inventory),
        "pitch_inventory_digest": digest,
        "pitch_overrides": prepared.pitch_overrides,
        "transposing_parts": prepared.transposing_parts,
        "repairs": repairs,
    }
    if index_thresholds is not None:
        result["label_thresholds"] = [float(index_thresholds[0]), float(index_thresholds[1])]
    if debug_export_internal_path:
        result["source_file_internal_path"] = str(score_path)
    return result


def write_cardinality_csv(analysis: dict[str, Any]) -> str:
    with tempfile.NamedTemporaryFile(
        prefix="textural_cardinality_",
        suffix=".csv",
        delete=False,
    ) as tf:
        out_path = tf.name
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        tuning = analysis.get("params", {}).get("tuning", {})
        mm = analysis.get("params", {}).get("micro_macro_texture", {})
        f.write(
            "# sampling: "
            f"{analysis.get('sampling', 'n/a')}, "
            f"time_step={analysis.get('time_step')}, "
            f"sample_count={analysis.get('sample_count', len(analysis.get('series', [])))}, "
            f"event_count={analysis.get('event_count', 'n/a')}; "
            f"micro_macro: register={mm.get('reference_register', 'A0-C8')}, "
            f"universe_size={mm.get('reference_pitch_universe_size', 'n/a')}, "
            f"index_scale_anchors={mm.get('micro_pole_cardinality', 1)}/"
            f"{mm.get('meso_pole_cardinality', 'n/a')}/"
            f"{mm.get('macro_pole_cardinality', 'n/a')}; "
            f"tuning: bin_cents={tuning.get('bin_cents', analysis.get('bin_cents'))}, "
            f"edo={tuning.get('edo', analysis.get('edo'))}, "
            f"preset={tuning.get('tuning_preset')}, "
            f"provenance={tuning.get('tuning_provenance')}; "
            f"texture_scale_label={analysis.get('texture_scale_label', 'n/a')}, "
            f"label_mode={analysis.get('label_mode', DEFAULT_LABEL_MODE)}, "
            f"label_count_thresholds={analysis.get('label_count_thresholds', list(DEFAULT_LABEL_COUNT_THRESHOLDS))}, "
            + (
                f"label_thresholds={analysis.get('label_thresholds')}, "
                if analysis.get("label_mode") == LABEL_MODE_INDEX
                else ""
            )
            + f"label_basis={analysis.get('label_basis', 'n/a')}, "
            f"texture_scale_label_reliable={analysis.get('texture_scale_label_reliable', True)}, "
            f"reference_universe_size="
            f"{analysis.get('reference_universe_size', mm.get('reference_pitch_universe_size', 'n/a'))}\n"
        )
        w = csv.DictWriter(
            f,
            fieldnames=[
                "time_quarters",
                "vertical_note_count",
                "vertical_unique_pitch_count",
                "vertical_pitch_class_cardinality",
                "micro_macro_pitch_cardinality",
                "micro_macro_normalized",
                "micro_meso_macro_normalized",
            ],
        )
        w.writeheader()
        for row in analysis["series"]:
            w.writerow(row)
    return out_path


def write_cardinality_json(analysis: dict[str, Any]) -> str:
    with tempfile.NamedTemporaryFile(
        prefix="textural_cardinality_",
        suffix=".json",
        delete=False,
    ) as tf:
        out_path = tf.name
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)
    return out_path
