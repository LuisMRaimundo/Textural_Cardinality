"""CLI tests for headless score analysis (analyze-score subcommand)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile

import pytest
from music21.chord import Chord
from music21.note import Note
from music21.pitch import Pitch
from music21.stream import Part, Score

from textural_cardinality.__main__ import run_analyze_score, run_direct_input
from textural_cardinality.analysis import analyze_vertical_cardinality


def _write_score_with_chord(pitch_names: list[str]) -> str:
    score = Score()
    part = Part()
    for name in pitch_names:
        part.insert(0.0, Note(name, quarterLength=1.0))
    score.insert(0.0, part)
    with tempfile.NamedTemporaryFile(suffix=".musicxml", delete=False) as tf:
        path = tf.name
    score.write("musicxml", fp=path)
    return path


def _write_quarter_tone_score() -> str:
    score = Score()
    part = Part()
    part.insert(0.0, Note(quarterLength=1.0))
    part[0].pitch = Pitch(ps=60.0)
    part.insert(0.0, Note(quarterLength=1.0))
    part[1].pitch = Pitch(ps=60.5)
    score.insert(0.0, part)
    with tempfile.NamedTemporaryFile(suffix=".musicxml", delete=False) as tf:
        path = tf.name
    score.write("musicxml", fp=path)
    return path


def test_analyze_score_writes_csv_and_json_matching_direct_analysis(tmp_path: Path) -> None:
    score_path = _write_score_with_chord(["C4", "E4", "G4"])
    csv_path = tmp_path / "out.csv"
    json_path = tmp_path / "out.json"
    try:
        exit_code = run_analyze_score(
            [
                score_path,
                "--output-csv",
                str(csv_path),
                "--output-json",
                str(json_path),
                "--event-boundaries-only",
            ]
        )
        assert exit_code == 0
        assert csv_path.is_file()
        assert json_path.is_file()

        direct = analyze_vertical_cardinality(score_path, time_step=None)
        exported = json.loads(json_path.read_text(encoding="utf-8"))
        assert exported["series"] == direct["series"]
        assert exported["event_count"] == direct["event_count"]
        assert exported["sample_count"] == direct["sample_count"]

        csv_rows = list(csv.DictReader(csv_path.read_text(encoding="utf-8").splitlines()[1:]))
        assert len(csv_rows) == len(direct["series"])
        assert int(csv_rows[0]["vertical_note_count"]) == direct["series"][0]["vertical_note_count"]
    finally:
        Path(score_path).unlink(missing_ok=True)


def test_analyze_score_passes_tuning_preset(tmp_path: Path) -> None:
    score_path = _write_quarter_tone_score()
    csv_path = tmp_path / "preset.csv"
    json_path = tmp_path / "preset.json"
    try:
        exit_code = run_analyze_score(
            [
                score_path,
                "--output-csv",
                str(csv_path),
                "--output-json",
                str(json_path),
                "--tuning-preset",
                "24_edo",
                "--event-boundaries-only",
            ]
        )
        assert exit_code == 0
        exported = json.loads(json_path.read_text(encoding="utf-8"))
        assert exported["edo"] == 24
        assert exported["params"]["tuning"]["tuning_preset"] == "24_edo"
        assert exported["series"][0]["vertical_unique_pitch_count"] == 2
    finally:
        Path(score_path).unlink(missing_ok=True)


def test_analyze_score_invalid_file_path_returns_error(tmp_path: Path) -> None:
    exit_code = run_analyze_score(
        [
            str(tmp_path / "missing-score.musicxml"),
            "--output-csv",
            str(tmp_path / "out.csv"),
            "--output-json",
            str(tmp_path / "out.json"),
        ]
    )
    assert exit_code == 1
    assert not (tmp_path / "out.csv").exists()
    assert not (tmp_path / "out.json").exists()


def test_analyze_score_does_not_launch_gui(monkeypatch: pytest.MonkeyPatch) -> None:
    launched: list[str] = []

    def _forbidden_gui() -> None:
        launched.append("gui")
        raise AssertionError("GUI must not launch for analyze-score")

    monkeypatch.setattr("textural_cardinality.ui.gradio_app.main", _forbidden_gui)

    score_path = _write_score_with_chord(["C4"])
    try:
        with tempfile.TemporaryDirectory() as tmp:
            exit_code = run_analyze_score(
                [
                    score_path,
                    "--output-csv",
                    str(Path(tmp) / "out.csv"),
                    "--output-json",
                    str(Path(tmp) / "out.json"),
                    "--event-boundaries-only",
                ]
            )
        assert exit_code == 0
        assert launched == []
    finally:
        Path(score_path).unlink(missing_ok=True)


def test_inventory_subcommand_writes_csv(tmp_path: Path) -> None:
    from textural_cardinality.__main__ import run_inventory

    score_path = _write_score_with_chord(["C4", "E4"])
    csv_path = tmp_path / "inv.csv"
    try:
        exit_code = run_inventory([score_path, "--output-csv", str(csv_path)])
        assert exit_code == 0
        assert csv_path.is_file()
        text = csv_path.read_text(encoding="utf-8")
        assert "note_id" in text
        assert "sounding_ps" in text
    finally:
        Path(score_path).unlink(missing_ok=True)


def test_direct_input_mode_still_works_without_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    run_direct_input(["--notes", "4", "--unique-pitches", "3", "--pc-cardinality", "2", "--edo", "24"])
    out = capsys.readouterr().out
    assert '"vertical_note_count": 4' in out
    assert '"vertical_pitch_class_cardinality": 2' in out
