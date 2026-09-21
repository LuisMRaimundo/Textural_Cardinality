"""Pitch inventory, repair, transposition, overrides, and interval summary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from music21.note import Note
from music21.stream import Part, Score
from music21.tie import Tie

from textural_cardinality.analysis import (
    JSON_EXPORT_SCHEMA_VERSION,
    analyze_vertical_cardinality,
    inspect_score_pitches,
    linked_bin_cents_for_edo,
    linked_edo_for_bin_cents,
    micro_macro_normalized,
    micro_meso_macro_normalized,
)
from textural_cardinality.pitch_overrides import (
    load_pitch_overrides,
    save_pitch_overrides,
)
from textural_cardinality.pitch_utils import parse_pitch_input

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CLUSTER = FIXTURES / "sibelius_glyph_only_cluster.musicxml"
HORN = FIXTURES / "horn_trombone_collision.musicxml"
BASS = FIXTURES / "bass_cello_octave.musicxml"
UNPITCHED = FIXTURES / "unpitched_and_pitched.musicxml"


def _codes(analysis: dict) -> set[str]:
    return {w.get("code") for w in analysis.get("warnings") or []}


def _warning(analysis: dict, code: str) -> dict:
    for w in analysis.get("warnings") or []:
        if w.get("code") == code:
            return w
    raise AssertionError(f"missing warning {code}: {_codes(analysis)}")


def test_cluster_repair_off_collapses_to_four() -> None:
    out = analyze_vertical_cardinality(str(CLUSTER), time_step=None)
    row = out["series"][0]
    assert row["vertical_unique_pitch_count"] == 4
    assert out["repairs"] == []
    assert "microtone_glyph_alter_mismatch" not in _codes(out)
    assert "microtone_repaired" not in _codes(out)


def test_cluster_repair_warn_unique_four_and_n() -> None:
    out = analyze_vertical_cardinality(
        str(CLUSTER), time_step=None, microtone_repair="warn"
    )
    assert out["series"][0]["vertical_unique_pitch_count"] == 4
    warn = _warning(out, "microtone_glyph_alter_mismatch")
    assert warn["details"]["n"] == 4


def test_cluster_repair_from_accidentals_24_edo() -> None:
    out = analyze_vertical_cardinality(
        str(CLUSTER),
        time_step=None,
        microtone_repair="from_accidentals",
        bin_cents=50.0,
        edo=24,
    )
    row = out["series"][0]
    assert row["vertical_note_count"] == 8
    assert row["vertical_unique_pitch_count"] == 8
    assert row["vertical_pitch_class_cardinality"] == 8
    assert row["micro_macro_pitch_cardinality"] == 8
    assert out["params"]["micro_macro_texture"]["reference_pitch_universe_size"] == 175
    assert row["micro_macro_normalized"] == pytest.approx(micro_macro_normalized(8, 175))
    assert row["micro_meso_macro_normalized"] == pytest.approx(
        micro_meso_macro_normalized(8, 175)
    )
    mm = out["summary"]["micro_macro_pitch_cardinality"]
    assert mm["constant_value"] == 8
    assert out["summary"]["silent_duration"] == 0
    assert out["pitch_inventory_digest"]["n_unique_sounding"] == 8


def test_cluster_inconsistent_pair_merges_eight_to_four() -> None:
    out = analyze_vertical_cardinality(
        str(CLUSTER),
        time_step=None,
        microtone_repair="from_accidentals",
        edo=24,
        bin_cents=100.0,
    )
    assert out["series"][0]["vertical_unique_pitch_count"] == 4
    pair = _warning(out, "inconsistent_tuning_pair")
    assert pair["details"]["edo"] == 24
    merged = _warning(out, "microtones_merged")
    assert merged["details"]["n_before"] == 8
    assert merged["details"]["n_after"] == 4
    assert "half-to-even" in merged["message"]


def test_horn_trombone_written_vs_sounding() -> None:
    written = analyze_vertical_cardinality(str(HORN), time_step=None, pitch_reference="written")
    sounding = analyze_vertical_cardinality(str(HORN), time_step=None, pitch_reference="sounding")
    assert written["series"][0]["vertical_unique_pitch_count"] == 2
    assert sounding["series"][0]["vertical_unique_pitch_count"] == 1
    assert written["transposing_parts"]
    assert "transposing_parts_written" in _codes(written)


def test_bass_cello_octave_change() -> None:
    written = analyze_vertical_cardinality(str(BASS), time_step=None, pitch_reference="written")
    sounding = analyze_vertical_cardinality(str(BASS), time_step=None, pitch_reference="sounding")
    assert written["series"][0]["vertical_unique_pitch_count"] == 1
    assert sounding["series"][0]["vertical_unique_pitch_count"] == 2
    digest = sounding["pitch_inventory_digest"]
    assert digest["min"] == pytest.approx(31.0)


def test_unpitched_listed_but_excluded_from_metrics() -> None:
    out = analyze_vertical_cardinality(str(UNPITCHED), time_step=None)
    assert len(out["pitch_inventory"]) == 2
    drum = next(r for r in out["pitch_inventory"] if "unpitched" in str(r.get("flags")))
    assert drum["used_in_metrics"] is False
    assert out["series"][0]["vertical_note_count"] == 1
    assert out["series"][0]["vertical_unique_pitch_count"] == 1


def test_override_change_exclude_and_part_transposition(tmp_path: Path) -> None:
    baseline = analyze_vertical_cardinality(str(CLUSTER), time_step=None)
    row = next(r for r in baseline["pitch_inventory"] if r["used_in_metrics"])
    pitch_ov = {
        "note_id": row["note_id"],
        "part": row["part"],
        "measure": row["measure"],
        "field": "sounding_ps",
        "original": row["sounding_ps"],
        "new": 72.0,
        "kind": "manual_pitch",
    }
    exclude_ov = {
        "note_id": row["note_id"],
        "part": row["part"],
        "measure": row["measure"],
        "field": "used_in_metrics",
        "original": True,
        "new": False,
        "kind": "manual_exclude",
    }
    part_ov = {
        "part": row["part"],
        "field": "part_transposition",
        "original": 0.0,
        "new": 0.5,
        "kind": "part_transposition",
    }
    changed = analyze_vertical_cardinality(
        str(CLUSTER), time_step=None, pitch_overrides=[pitch_ov]
    )
    logged = next(e for e in changed["pitch_overrides"] if e["kind"] == "manual_pitch")
    assert logged["original"] == pytest.approx(float(row["sounding_ps"]))
    assert logged["new"] == pytest.approx(72.0)
    assert "manual_overrides" in _codes(changed)

    excluded = analyze_vertical_cardinality(
        str(CLUSTER), time_step=None, pitch_overrides=[exclude_ov]
    )
    assert excluded["series"][0]["vertical_note_count"] == baseline["series"][0]["vertical_note_count"] - 1

    shifted = analyze_vertical_cardinality(
        str(CLUSTER), time_step=None, pitch_overrides=[part_ov]
    )
    part_logged = next(e for e in shifted["pitch_overrides"] if e["kind"] == "part_transposition")
    assert part_logged["new"] == pytest.approx(0.5)

    sidecar = tmp_path / "cluster.musicxml.pitch_overrides.json"
    save_pitch_overrides(sidecar, [pitch_ov])
    raw = json.loads(sidecar.read_text(encoding="utf-8"))
    assert raw["pitch_overrides_schema"] == "1"
    loaded = load_pitch_overrides(sidecar)
    again = analyze_vertical_cardinality(str(CLUSTER), time_step=None, pitch_overrides=loaded)
    assert again["series"] == changed["series"]


def test_invalid_pitch_name_rejected() -> None:
    with pytest.raises(ValueError, match="Cannot parse pitch"):
        parse_pitch_input("not-a-pitch")


def test_tied_override_propagates_and_merges(tmp_path: Path) -> None:
    score = Score()
    part = Part()
    notes = []
    for i, ql in enumerate((1.0, 1.0, 1.0)):
        n = Note("C4", quarterLength=ql)
        if i == 0:
            n.tie = Tie("start")
        elif i == 1:
            n.tie = Tie("continue")
        else:
            n.tie = Tie("stop")
        part.insert(float(i), n)
        notes.append(n)
    score.insert(0.0, part)
    path = tmp_path / "tied.musicxml"
    score.write("musicxml", fp=str(path))

    inspected = inspect_score_pitches(str(path))
    first = inspected["pitch_inventory"][0]
    ov = {
        "note_id": first["note_id"],
        "part": first["part"],
        "measure": first["measure"],
        "field": "sounding_ps",
        "original": first["sounding_ps"],
        "new": 64.0,
        "kind": "manual_pitch",
    }
    out = analyze_vertical_cardinality(str(path), time_step=None, pitch_overrides=[ov])
    assert out["event_count"] == 1
    assert out["series"][0]["vertical_unique_pitch_count"] == 1
    logged = next(e for e in out["pitch_overrides"] if e["kind"] == "manual_pitch")
    assert logged["new"] == pytest.approx(64.0)
    assert logged.get("propagated_to")
    assert first["note_id"] not in logged["propagated_to"]


def test_terminal_sample_summary_excludes_zero() -> None:
    from music21.chord import Chord

    score = Score()
    part = Part()
    part.insert(0.0, Chord(["C4", "E4", "G4"], quarterLength=4.0))
    score.insert(0.0, part)
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".musicxml", delete=False) as tf:
        path = tf.name
    score.write("musicxml", fp=path)
    try:
        out = analyze_vertical_cardinality(path, time_step=1.0)
        mm = out["summary"]["micro_macro_pitch_cardinality"]
        assert mm["min_over_sounding_time"] == 3
        assert mm["max"] == 3
        assert mm["constant_value"] == 3
        point_min = min(r["micro_macro_pitch_cardinality"] for r in out["series"])
        assert point_min == 0
        assert out["series"][-1]["vertical_note_count"] == 0
    finally:
        Path(path).unlink(missing_ok=True)


def test_linked_tuning_widgets() -> None:
    assert linked_bin_cents_for_edo(24) == pytest.approx(50.0)
    assert linked_edo_for_bin_cents(50.0) == 24
    assert linked_edo_for_bin_cents(100.0) == 12
    assert linked_edo_for_bin_cents(40.0) == 30
    assert linked_edo_for_bin_cents(37.0) is None


def test_schema_version_exported() -> None:
    out = analyze_vertical_cardinality(str(CLUSTER), time_step=None)
    assert out["schema_version"] == JSON_EXPORT_SCHEMA_VERSION == "1.2"


def test_midi_bin_cents_warning(tmp_path: Path) -> None:
    score = Score()
    part = Part()
    part.insert(0.0, Note("C4", quarterLength=1.0))
    score.insert(0.0, part)
    mid = tmp_path / "one.mid"
    score.write("midi", fp=str(mid))
    out = analyze_vertical_cardinality(str(mid), time_step=None, bin_cents=50.0, edo=24)
    assert "midi_microtones_not_recoverable" in _codes(out)


def test_overrides_from_inventory_edits_and_sidecar_path() -> None:
    from textural_cardinality.pitch_overrides import (
        coerce_used_in_metrics,
        overrides_from_inventory_edits,
        sidecar_path_for_score,
    )

    assert coerce_used_in_metrics(True) is True
    assert coerce_used_in_metrics("no") is False
    original = [
        {
            "note_id": "0:1:0:1:0",
            "part": "P1",
            "measure": 1,
            "sounding_ps": 60.0,
            "sounding_name": "C4",
            "used_in_metrics": True,
        }
    ]
    edited = [
        {
            "note_id": "0:1:0:1:0",
            "part": "P1",
            "measure": 1,
            "sounding_ps": 61.0,
            "sounding_name": "C#4",
            "used_in_metrics": False,
        }
    ]
    ovs = overrides_from_inventory_edits(
        original, edited, [{"part": "P1", "extra_semitones": 0.5}]
    )
    kinds = {o["kind"] for o in ovs}
    assert kinds == {"manual_pitch", "manual_exclude", "part_transposition"}
    assert sidecar_path_for_score("score.musicxml").name.endswith(".pitch_overrides.json")
    with pytest.raises(ValueError):
        coerce_used_in_metrics("maybe")
    assert parse_pitch_input("G3+50c") == pytest.approx(55.5)
    assert parse_pitch_input("C4") == pytest.approx(60.0)


def test_inspect_and_gradio_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    from textural_cardinality.ui import gradio_app

    inspected = inspect_score_pitches(str(CLUSTER))
    table, digest, parts, warnings, original = gradio_app.inspect_cardinality_app(
        str(CLUSTER), "off", "written", 100.0, 12
    )
    assert table
    assert "notes" in digest.lower() or digest
    assert original == table
    assert gradio_app._records_from_df(None) == []
    assert gradio_app._records_from_df(table) == table
    parts2 = gradio_app._parts_table_from_inventory(inspected["pitch_inventory_raw"])
    assert parts2
    with pytest.raises(Exception):
        gradio_app.inspect_cardinality_app(None, "off", "written", 100.0, 12)


def test_reference_and_override_normalisers() -> None:
    from textural_cardinality.pitch_overrides import normalize_pitch_overrides
    from textural_cardinality.pitch_reference import (
        convert_score_to_sounding,
        interval_semitones,
        normalize_pitch_reference,
    )
    from music21.interval import Interval

    assert normalize_pitch_reference(None) == "written"
    assert normalize_pitch_reference("concert") == "sounding"
    with pytest.raises(ValueError):
        normalize_pitch_reference("not-a-mode")
    assert interval_semitones(Interval(-7)) == pytest.approx(-7.0)
    assert interval_semitones(None) is None
    with pytest.raises(ValueError):
        normalize_pitch_overrides("bad")
    with pytest.raises(ValueError):
        normalize_pitch_overrides([{"kind": "nope"}])
    ovs = normalize_pitch_overrides(
        {
            "pitch_overrides_schema": "1",
            "pitch_overrides": [{"note_id": "0:1:0:1:0", "new": "E4", "kind": "manual_pitch"}],
        }
    )
    assert ovs[0]["new"] == pytest.approx(64.0)
    score = converter_parse_horn()
    sounding = convert_score_to_sounding(score)
    assert list(sounding.recurse().notes)


def converter_parse_horn():
    from music21 import converter

    return converter.parse(str(HORN))


def test_midi_repair_modes_do_not_crash(tmp_path: Path) -> None:
    from textural_cardinality.microtone_repair import apply_microtone_repair, is_midi_score_path

    score = Score()
    part = Part()
    part.insert(0.0, Note("C4", quarterLength=1.0))
    score.insert(0.0, part)
    mid = tmp_path / "one.mid"
    score.write("midi", fp=str(mid))
    assert is_midi_score_path(str(mid)) is True
    parsed = __import__("music21").converter.parse(str(mid))
    _, msgs, repairs = apply_microtone_repair(parsed, "from_accidentals", is_midi=True)
    assert msgs and repairs == []
    with pytest.raises(ValueError):
        from textural_cardinality.microtone_repair import normalize_microtone_repair

        normalize_microtone_repair("bogus")
    assert parse_pitch_input(60) == 60.0
    with pytest.raises(ValueError):
        parse_pitch_input("")
    with pytest.raises(ValueError):
        parse_pitch_input(True)


def test_out_of_register_warning(tmp_path: Path) -> None:
    score = Score()
    part = Part()
    n = Note("C4", quarterLength=1.0)
    n.pitch.ps = 120.0
    part.insert(0.0, n)
    score.insert(0.0, part)
    path = tmp_path / "high.musicxml"
    score.write("musicxml", fp=str(path))
    out = analyze_vertical_cardinality(str(path), time_step=None)
    warn = _warning(out, "out_of_register_notes")
    assert warn["details"]["n"] == 1
    assert "vertical_unique_pitch_count includes them" in warn["message"]
