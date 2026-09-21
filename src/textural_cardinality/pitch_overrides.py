"""Manual pitch / exclude / part-transposition overrides and sidecar JSON.

Sidecar schema is interchangeable with Registral_Dispersion:
``{"pitch_overrides_schema": "1", "pitch_overrides": [...]}``.
``note_id`` is ``part_index:measure:offset:voice:chord_index``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from textural_cardinality.pitch_utils import parse_pitch_input

OVERRIDE_KIND_MANUAL_PITCH = "manual_pitch"
OVERRIDE_KIND_MANUAL_EXCLUDE = "manual_exclude"
OVERRIDE_KIND_PART_TRANSPOSITION = "part_transposition"
OVERRIDE_KINDS = frozenset(
    {OVERRIDE_KIND_MANUAL_PITCH, OVERRIDE_KIND_MANUAL_EXCLUDE, OVERRIDE_KIND_PART_TRANSPOSITION}
)

PITCH_OVERRIDES_SCHEMA = "1"
SIDECAR_SUFFIX = ".pitch_overrides.json"

_TRUE = frozenset({"1", "true", "yes", "y", "on"})
_FALSE = frozenset({"0", "false", "no", "n", "off"})


def sidecar_path_for_score(score_path: str | Path) -> Path:
    p = Path(score_path)
    return p.with_name(p.name + SIDECAR_SUFFIX)


def coerce_used_in_metrics(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return True
    if isinstance(value, int | float) and not isinstance(value, bool):
        return bool(value)
    s = str(value).strip().lower()
    if s in _TRUE:
        return True
    if s in _FALSE:
        return False
    raise ValueError(f"Cannot parse used_in_metrics {value!r}; expected true/false.")


def normalize_pitch_overrides(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict) and "pitch_overrides" in value:
        value = value["pitch_overrides"]
    if not isinstance(value, list):
        raise ValueError("pitch_overrides must be a list of objects.")
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ValueError(f"pitch_overrides[{i}] must be an object, got {type(raw).__name__}.")
        kind = str(raw.get("kind") or "").strip() or OVERRIDE_KIND_MANUAL_PITCH
        if kind not in OVERRIDE_KINDS:
            raise ValueError(
                f"pitch_overrides[{i}].kind {kind!r} is not one of {sorted(OVERRIDE_KINDS)}."
            )
        entry = {
            "note_id": raw.get("note_id"),
            "part": raw.get("part"),
            "measure": raw.get("measure"),
            "field": raw.get("field"),
            "original": raw.get("original"),
            "new": raw.get("new"),
            "reason": raw.get("reason"),
            "kind": kind,
        }
        if raw.get("propagated_to") not in (None, ""):
            entry["propagated_to"] = list(raw["propagated_to"])
        if kind == OVERRIDE_KIND_MANUAL_PITCH:
            entry["new"] = parse_pitch_input(raw.get("new"))
            if raw.get("original") not in (None, ""):
                try:
                    entry["original"] = parse_pitch_input(raw.get("original"))
                except ValueError:
                    entry["original"] = raw.get("original")
            if not entry.get("field"):
                entry["field"] = "sounding_ps"
        elif kind == OVERRIDE_KIND_MANUAL_EXCLUDE:
            entry["new"] = coerce_used_in_metrics(raw.get("new"))
            if raw.get("original") not in (None, ""):
                try:
                    entry["original"] = coerce_used_in_metrics(raw.get("original"))
                except ValueError:
                    entry["original"] = raw.get("original")
            if not entry.get("field"):
                entry["field"] = "used_in_metrics"
        else:
            entry["new"] = float(parse_pitch_input(raw.get("new", 0)))
            if raw.get("original") not in (None, ""):
                try:
                    entry["original"] = float(parse_pitch_input(raw.get("original")))
                except ValueError:
                    entry["original"] = raw.get("original")
            else:
                entry["original"] = 0.0
            if not entry.get("field"):
                entry["field"] = "part_transposition"
        out.append(entry)
    return out


def load_pitch_overrides(path: str | Path) -> list[dict[str, Any]]:
    """Load a sidecar JSON list or ``{\"pitch_overrides\": [...]}`` wrapper."""
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    return normalize_pitch_overrides(raw)


def save_pitch_overrides(path: str | Path, overrides: list[dict[str, Any]]) -> str:
    p = Path(path)
    payload = {
        "pitch_overrides_schema": PITCH_OVERRIDES_SCHEMA,
        "pitch_overrides": list(overrides),
    }
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(p)


def warn_manual_overrides(n: int) -> str:
    return f"{n} manual pitch override(s) applied"


def overrides_from_inventory_edits(
    original_rows: list[dict[str, Any]],
    edited_rows: list[dict[str, Any]],
    part_transpositions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    by_id = {str(r.get("note_id")): r for r in original_rows if r.get("note_id") not in (None, "")}
    out: list[dict[str, Any]] = []
    for row in edited_rows:
        nid = str(row.get("note_id") or "")
        if not nid or nid not in by_id:
            continue
        orig = by_id[nid]
        new_used = coerce_used_in_metrics(row.get("used_in_metrics", orig.get("used_in_metrics")))
        old_used = coerce_used_in_metrics(orig.get("used_in_metrics", True))
        if new_used != old_used:
            out.append(
                {
                    "note_id": nid,
                    "part": row.get("part", orig.get("part")),
                    "measure": row.get("measure", orig.get("measure")),
                    "field": "used_in_metrics",
                    "original": old_used,
                    "new": new_used,
                    "reason": row.get("reason"),
                    "kind": OVERRIDE_KIND_MANUAL_EXCLUDE,
                }
            )
        edited_ps_raw = row.get("sounding_ps")
        edited_name = row.get("sounding_name")
        orig_ps = orig.get("sounding_ps", orig.get("_sounding_ps"))
        new_ps = None
        field = "sounding_ps"
        if edited_ps_raw not in (None, "") and str(edited_ps_raw).strip() != "":
            new_ps = parse_pitch_input(edited_ps_raw)
        elif edited_name not in (None, "") and str(edited_name).strip() != "":
            new_ps = parse_pitch_input(edited_name)
            field = "sounding_name"
        if new_ps is None or orig_ps in (None, ""):
            continue
        if abs(float(new_ps) - float(orig_ps)) > 1e-9:
            out.append(
                {
                    "note_id": nid,
                    "part": row.get("part", orig.get("part")),
                    "measure": row.get("measure", orig.get("measure")),
                    "field": field,
                    "original": float(orig_ps),
                    "new": float(new_ps),
                    "reason": row.get("reason"),
                    "kind": OVERRIDE_KIND_MANUAL_PITCH,
                }
            )
    for extra in part_transpositions or []:
        try:
            delta = float(extra.get("extra_semitones") if "extra_semitones" in extra else extra.get("new", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Cannot parse extra transposition {extra.get('extra_semitones', extra.get('new'))!r}."
            ) from exc
        if abs(delta) <= 1e-12:
            continue
        out.append(
            {
                "note_id": None,
                "part": extra.get("part", extra.get("part_index")),
                "measure": None,
                "field": "part_transposition",
                "original": 0.0,
                "new": delta,
                "reason": extra.get("reason"),
                "kind": OVERRIDE_KIND_PART_TRANSPOSITION,
            }
        )
    return out
