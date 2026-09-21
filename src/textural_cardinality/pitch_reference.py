"""Written vs sounding pitch reference and transposing-part detection.

Order of operations:

    parse → microtone repair → sounding conversion → part-level overrides
    → note-level overrides → tie merge → register filter → grid quantisation → sweep
"""

from __future__ import annotations

import copy
from typing import Any

from music21 import stream

PITCH_REFERENCE_WRITTEN = "written"
PITCH_REFERENCE_SOUNDING = "sounding"
PITCH_REFERENCE_MODES = frozenset({PITCH_REFERENCE_WRITTEN, PITCH_REFERENCE_SOUNDING})
DEFAULT_PITCH_REFERENCE = PITCH_REFERENCE_WRITTEN

PITCH_PIPELINE_ORDER = (
    "parse",
    "microtone_repair",
    "sounding_conversion",
    "part_level_overrides",
    "note_level_overrides",
    "tie_merge",
    "register_filter",
    "grid_quantisation",
    "sweep",
)


def normalize_pitch_reference(value: Any) -> str:
    if value is None or str(value).strip() == "":
        return DEFAULT_PITCH_REFERENCE
    s = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "concert": PITCH_REFERENCE_SOUNDING,
        "concert_pitch": PITCH_REFERENCE_SOUNDING,
        "as_written": PITCH_REFERENCE_WRITTEN,
        "notated": PITCH_REFERENCE_WRITTEN,
    }
    s = aliases.get(s, s)
    if s in PITCH_REFERENCE_MODES:
        return s
    raise ValueError(
        f"Unknown pitch_reference {value!r}; expected "
        f"{PITCH_REFERENCE_WRITTEN!r} or {PITCH_REFERENCE_SOUNDING!r}."
    )


def interval_semitones(interval: Any) -> float | None:
    if interval is None:
        return None
    if hasattr(interval, "semitones"):
        try:
            return float(interval.semitones)
        except (TypeError, ValueError):
            pass
    chromatic = getattr(interval, "chromatic", None)
    if chromatic is not None and hasattr(chromatic, "semitones"):
        try:
            return float(chromatic.semitones)
        except (TypeError, ValueError):
            pass
    return None


def _part_label(part) -> str:
    if part is None:
        return ""
    name = getattr(part, "partName", None)
    if name not in (None, ""):
        return str(name)
    pid = getattr(part, "id", None)
    if isinstance(pid, str) and pid and not str(pid).isdigit():
        return pid
    return ""


def _instrument_name(part) -> str:
    if part is None or not hasattr(part, "getInstrument"):
        return ""
    try:
        inst = part.getInstrument(returnDefault=True)
    except Exception:
        return ""
    if inst is None:
        return ""
    for attr in ("instrumentName", "bestName"):
        val = getattr(inst, attr, None)
        if callable(val):
            try:
                val = val()
            except Exception:
                val = None
        if val not in (None, ""):
            return str(val)
    return ""


def _xml_transpose_semitones(part) -> float | None:
    if part is None:
        return None
    for el in part.recurse():
        name = type(el).__name__
        has_chromatic = hasattr(el, "chromatic")
        has_octave = hasattr(el, "octaveChange") or hasattr(el, "octave-change")
        if name != "Transpose" and not (has_chromatic and has_octave):
            continue
        semi = 0.0
        found = False
        ch = getattr(el, "chromatic", None)
        if ch is not None:
            found = True
            try:
                semi += float(ch.semitones if hasattr(ch, "semitones") else ch)
            except (TypeError, ValueError):
                pass
        oct_change = getattr(el, "octaveChange", None)
        if oct_change not in (None, 0, 0.0):
            found = True
            try:
                semi += 12.0 * float(oct_change)
            except (TypeError, ValueError):
                pass
        if found:
            return semi
    return None


def detect_transposing_parts(score: stream.Stream) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    parts = list(getattr(score, "parts", []) or [])
    if not parts:
        return rows
    for part in parts:
        inst = None
        try:
            inst = part.getInstrument(returnDefault=True)
        except Exception:
            inst = None
        transposition = getattr(inst, "transposition", None) if inst is not None else None
        semi = interval_semitones(transposition)
        if transposition is None:
            semi = _xml_transpose_semitones(part)
            if semi is None:
                continue
        rows.append(
            {
                "part": _part_label(part),
                "instrument": _instrument_name(part),
                "interval_semitones": None if semi is None else float(semi),
            }
        )
    return rows


def convert_score_to_sounding(score: stream.Stream) -> stream.Stream:
    sounding = copy.deepcopy(score)
    try:
        sounding.toSoundingPitch(inPlace=True)
    except Exception:
        return sounding
    return sounding


def warn_written_with_transposing_parts(parts: list[dict[str, Any]]) -> str:
    labels = []
    for p in parts:
        part = p.get("part") or "?"
        inst = p.get("instrument") or "unknown"
        semi = p.get("interval_semitones")
        semi_s = "?" if semi is None else f"{semi:g}"
        labels.append(f"{part} ({inst}, {semi_s} st)")
    listed = ", ".join(labels) if labels else "(unnamed)"
    return (
        f"Transposing part(s) present: {listed}. "
        "Metrics are NOT in sounding pitch (pitch_reference='written'). "
        "Re-run with pitch_reference='sounding' for concert pitch."
    )
