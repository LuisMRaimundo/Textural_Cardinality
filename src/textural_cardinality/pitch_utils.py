"""Note-name helpers shared with Registral_Dispersion override files."""

from __future__ import annotations

import re

import music21 as m21

_CENTS_SUFFIX = re.compile(
    r"^(?P<name>.+?)\s*(?P<cents>[+-]\d+(?:\.\d+)?)\s*c(?:ents)?$",
    re.IGNORECASE,
)


def note_name_to_midi_ps(note_name: str) -> float:
    p = m21.pitch.Pitch(note_name.strip())
    return float(p.ps)


def parse_pitch_input(value: object) -> float:
    """
    Parse a pitch as MIDI ``ps`` from a number or a note name.

    Accepted forms: ``56.5``, ``"56.5"``, ``"A#3"``, ``"Bb2"``, ``"A~3"``,
    ``"A#~3"``, ``"G3+50c"``, ``"A#3 +50c"``.
    """
    if isinstance(value, bool):
        raise ValueError(
            f"Cannot parse pitch {value!r}. Use a MIDI number (e.g. 56.5) or a name "
            "(A#3, A~3, A#~3, Bb2, G3+50c)."
        )
    if isinstance(value, int | float):
        if value != value:  # NaN
            raise ValueError("Cannot parse pitch NaN.")
        return float(value)
    s = str(value).strip()
    if not s:
        raise ValueError(
            "Cannot parse an empty pitch. Use a MIDI number (e.g. 56.5) or a name "
            "(A#3, A~3, A#~3, Bb2, G3+50c)."
        )
    try:
        return float(s)
    except ValueError:
        pass
    cents_match = _CENTS_SUFFIX.fullmatch(s)
    if cents_match is not None:
        base = _name_to_ps_or_raise(cents_match.group("name"))
        return base + float(cents_match.group("cents")) / 100.0
    return _name_to_ps_or_raise(s)


def _name_to_ps_or_raise(name: str) -> float:
    token = name.strip()
    try:
        return note_name_to_midi_ps(token)
    except Exception as exc:
        raise ValueError(
            f"Cannot parse pitch {name!r}. Use a MIDI number (e.g. 56.5) or a name "
            "(A#3, A~3, A#~3, Bb2, G3+50c)."
        ) from exc


def format_pitch_name(ps: float | None) -> str:
    if ps is None:
        return ""
    p = m21.pitch.Pitch()
    p.ps = float(ps)
    return str(p.nameWithOctave)


def format_ps_display(ps: float | None) -> float | None:
    if ps is None:
        return None
    return round(float(ps), 2)
