"""Absolute count labels, optional index mode, and the framed RESULT summary."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

import pytest
from music21.note import Note
from music21.pitch import Pitch
from music21.stream import Part, Score

from textural_cardinality.__main__ import run_analyze_score
from textural_cardinality.analysis import (
    DEFAULT_LABEL_COUNT_THRESHOLDS,
    DEFAULT_LABEL_THRESHOLDS,
    FROZEN_INDEX_THRESHOLD,
    RESULT_SCALE_WIDTH,
    UNRELIABLE_LABEL_SUFFIX,
    analyze_vertical_cardinality,
    compute_interval_summary,
    count_scale_caret_column,
    format_analysis_summary,
    format_result_block,
    texture_label_fields_from_summary,
    texture_scale_label,
    texture_scale_label_from_count,
    validate_label_count_thresholds,
    validate_label_thresholds,
    write_cardinality_csv,
    write_cardinality_json,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CLUSTER = FIXTURES / "sibelius_glyph_only_cluster.musicxml"


def _write_score(build) -> str:
    score = Score()
    part = Part()
    build(part)
    score.insert(0.0, part)
    with tempfile.NamedTemporaryFile(suffix=".musicxml", delete=False) as tf:
        path = tf.name
    score.write("musicxml", fp=path)
    return path


def _count_example_analysis() -> dict:
    x = (52.0 - 1.0) / (175.0 - 1.0)
    return {
        "source_file_name": "example.mxl",
        "duration_quarters": 4.0,
        "time_step": 0.25,
        "sampling": "event_boundaries_only",
        "edo": 24,
        "bin_cents": 50.0,
        "pitch_class_universe": "Z24",
        "event_count": 52,
        "sample_count": 2,
        "warnings": [],
        "repairs": [],
        "pitch_overrides": [],
        "label_mode": "count",
        "label_count_thresholds": [12, 60],
        "label_basis": "constant_value",
        "reference_universe_size": 175,
        "params": {
            "microtone_repair": "off",
            "pitch_reference": "written",
            "tuning": {"tuning_provenance": "tuning_preset", "bin_cents": 50.0, "edo": 24},
            "micro_macro_texture": {
                "reference_register": "A0-C8",
                "reference_pitch_universe_size": 175,
                "micro_pole_cardinality": 1,
                "meso_pole_cardinality": 88.0,
                "macro_pole_cardinality": 175,
                "label_mode": "count",
                "label_count_thresholds": [12, 60],
            },
        },
        "summary": {
            "silent_duration": 0.0,
            "vertical_note_count": {
                "duration_weighted_mean": 52.0,
                "min_over_sounding_time": 52.0,
                "max": 52.0,
                "constant_value": 52.0,
            },
            "micro_macro_pitch_cardinality": {
                "duration_weighted_mean": 52.0,
                "min_over_sounding_time": 52.0,
                "max": 52.0,
                "constant_value": 52.0,
            },
            "micro_meso_macro_normalized": {
                "duration_weighted_mean": x,
                "min_over_sounding_time": x,
                "max": x,
                "constant_value": x,
            },
        },
        "series": [
            {
                "time_quarters": 0.0,
                "vertical_note_count": 52,
                "vertical_unique_pitch_count": 52,
                "vertical_pitch_class_cardinality": 24,
                "micro_macro_pitch_cardinality": 52,
                "micro_macro_normalized": 52.0 / 175.0,
                "micro_meso_macro_normalized": x,
            },
            {
                "time_quarters": 4.0,
                "vertical_note_count": 0,
                "vertical_unique_pitch_count": 0,
                "vertical_pitch_class_cardinality": 0,
                "micro_macro_pitch_cardinality": 0,
                "micro_macro_normalized": 0.0,
                "micro_meso_macro_normalized": 0.0,
            },
        ],
        "texture_scale_label": "meso",
    }


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (8, "micro"),
        (12, "micro"),
        (13, "meso"),
        (52, "meso"),
        (59, "meso"),
        (60, "macro"),
        (61, "macro"),
    ],
)
def test_count_threshold_boundaries(count: int, expected: str) -> None:
    assert texture_scale_label_from_count(count) == expected
    assert texture_scale_label_from_count(count, DEFAULT_LABEL_COUNT_THRESHOLDS) == expected


def test_same_count_same_label_on_both_grids() -> None:
    def build(part: Part) -> None:
        for i in range(8):
            note = Note(quarterLength=1.0)
            note.pitch = Pitch(ps=60.0 + i)
            part.insert(0.0, note)

    path = _write_score(build)
    try:
        semitone = analyze_vertical_cardinality(path, time_step=None, bin_cents=100.0, edo=12)
        quarter = analyze_vertical_cardinality(path, time_step=None, bin_cents=50.0, edo=24)
        assert semitone["series"][0]["micro_macro_pitch_cardinality"] == 8
        assert quarter["series"][0]["micro_macro_pitch_cardinality"] == 8
        assert semitone["texture_scale_label"] == quarter["texture_scale_label"] == "micro"
        assert semitone["reference_universe_size"] == 88
        assert quarter["reference_universe_size"] == 175
    finally:
        Path(path).unlink(missing_ok=True)


@pytest.mark.parametrize(
    "thresholds",
    [
        (12, 12),
        (60, 12),
        (0, 60),
        (-1, 12),
        (1, 1),
    ],
)
def test_invalid_count_thresholds_rejected(thresholds: tuple[int, int]) -> None:
    with pytest.raises(ValueError, match="1 <= micro_max_count < macro_min_count"):
        validate_label_count_thresholds(thresholds)


def test_analyze_rejects_invalid_count_thresholds_before_parse() -> None:
    with pytest.raises(ValueError, match="1 <= micro_max_count < macro_min_count"):
        analyze_vertical_cardinality("missing.musicxml", label_count_thresholds=(60, 12))


def test_frozen_index_threshold_default_is_0_35() -> None:
    assert FROZEN_INDEX_THRESHOLD == pytest.approx(0.35)
    assert DEFAULT_LABEL_THRESHOLDS == (0.10, 0.35)
    assert texture_scale_label(0.3499) == "meso"
    assert texture_scale_label(0.35) == "macro"


def test_index_mode_still_uses_index_thresholds() -> None:
    assert texture_scale_label(0.0402, (0.10, 0.35)) == "micro"
    assert texture_scale_label(0.10, (0.10, 0.35)) == "meso"
    assert texture_scale_label(0.2931, (0.10, 0.35)) == "meso"
    assert texture_scale_label(0.35, (0.10, 0.35)) == "macro"


@pytest.mark.parametrize(
    "thresholds",
    [(0.25, 0.10), (0.10, 0.10), (0.0, 0.35), (0.10, 1.0)],
)
def test_invalid_index_thresholds_raise(thresholds: tuple[float, float]) -> None:
    with pytest.raises(ValueError, match="0 < micro_max < macro_min < 1"):
        validate_label_thresholds(thresholds)


def test_varying_series_labels_rounded_mean_count_and_range() -> None:
    series = [
        {
            "time_quarters": 0.0,
            "vertical_note_count": 2,
            "vertical_unique_pitch_count": 2,
            "vertical_pitch_class_cardinality": 2,
            "micro_macro_pitch_cardinality": 2,
            "micro_macro_normalized": 2.0 / 88.0,
            "micro_meso_macro_normalized": (2.0 - 1.0) / 87.0,
        },
        {
            "time_quarters": 2.0,
            "vertical_note_count": 30,
            "vertical_unique_pitch_count": 30,
            "vertical_pitch_class_cardinality": 12,
            "micro_macro_pitch_cardinality": 30,
            "micro_macro_normalized": 30.0 / 88.0,
            "micro_meso_macro_normalized": (30.0 - 1.0) / 87.0,
        },
        {
            "time_quarters": 4.0,
            "vertical_note_count": 0,
            "vertical_unique_pitch_count": 0,
            "vertical_pitch_class_cardinality": 0,
            "micro_macro_pitch_cardinality": 0,
            "micro_macro_normalized": 0.0,
            "micro_meso_macro_normalized": 0.0,
        },
    ]
    summary = compute_interval_summary(series)
    fields = texture_label_fields_from_summary(summary, universe_size=88)
    assert fields["label_basis"] == "duration_weighted_mean"
    assert fields["cardinality"] == 16
    assert fields["texture_scale_label"] == "meso"
    assert fields["range_min_label"] == "micro"
    assert fields["range_max_label"] == "meso"
    assert fields["texture_scale_label_display"] == "meso (range: micro -> meso)"


def test_varying_score_exports_range_in_summary() -> None:
    def build(part: Part) -> None:
        part.insert(0.0, Note("C4", quarterLength=2.0))
        part.insert(0.0, Note("E4", quarterLength=2.0))
        for i in range(30):
            note = Note(quarterLength=2.0)
            note.pitch = Pitch(ps=48.0 + i)
            part.insert(2.0, note)

    path = _write_score(build)
    try:
        result = analyze_vertical_cardinality(path, time_step=None, bin_cents=100.0, edo=12)
        assert result["label_mode"] == "count"
        assert result["label_basis"] == "duration_weighted_mean"
        assert result["texture_scale_label"] == "meso"
        text = format_analysis_summary(result)
        assert "range: micro -> meso" in text
        assert "MESO-TEXTURE" in text
    finally:
        Path(path).unlink(missing_ok=True)


def test_merged_microtones_mark_label_unreliable() -> None:
    out = analyze_vertical_cardinality(
        str(CLUSTER),
        time_step=None,
        microtone_repair="from_accidentals",
        edo=24,
        bin_cents=100.0,
    )
    assert any(w.get("code") == "microtones_merged" for w in out["warnings"])
    assert out["texture_scale_label_reliable"] is False
    text = format_analysis_summary(out)
    assert UNRELIABLE_LABEL_SUFFIX.strip() in text
    assert "UNRELIABLE" in text


def test_result_block_count_mode_format_and_caret() -> None:
    analysis = _count_example_analysis()
    text = format_analysis_summary(analysis)
    first = text.splitlines()[0]
    assert set(first) == {"="}
    assert "RESULT" in text.splitlines()[1]
    assert "52 distinct pitches" in text
    assert "MESO-TEXTURE" in text
    assert "label rule (pitch counts): micro <= 12 < meso < 60 <= macro" in text
    assert "secondary: normalised occupation (c-1)/(N-1) = 0.2931" in text
    assert "N = 175" in text
    assert "Index scale anchors (min / midpoint / max) — not labels:" in text
    assert "Texture poles" not in text

    scale_line = next(ln for ln in text.splitlines() if "count scale" in ln)
    caret_line = text.splitlines()[text.splitlines().index(scale_line) + 2]
    assert caret_line.strip().startswith("^") or "^" in caret_line
    assert num_line_is_own_caret(scale_line, caret_line, 52, 175)
    block = format_result_block(analysis)
    assert block.splitlines()[0] == text.splitlines()[0]


def num_line_is_own_caret(scale_line: str, caret_line: str, count: int, n: int) -> bool:
    assert "^" in caret_line
    assert str(count) in caret_line
    return caret_line.index("^") - scale_line.index("|") == count_scale_caret_column(
        count, n, width=RESULT_SCALE_WIDTH
    )


def test_json_and_csv_header_count_mode_keys() -> None:
    def build(part: Part) -> None:
        part.insert(0.0, Note("C4", quarterLength=1.0))
        part.insert(0.0, Note("E4", quarterLength=1.0))
        part.insert(0.0, Note("G4", quarterLength=1.0))

    path = _write_score(build)
    try:
        result = analyze_vertical_cardinality(path, time_step=None)
        assert result["label_mode"] == "count"
        assert result["label_count_thresholds"] == [12, 60]
        assert "label_thresholds" not in result
        assert result["texture_scale_label"] == "micro"
        assert result["texture_scale_label_reliable"] is True
        json_path = write_cardinality_json(result)
        csv_path = write_cardinality_csv(result)
        exported = json.loads(Path(json_path).read_text(encoding="utf-8"))
        assert "label_mode" in exported
        assert "label_count_thresholds" in exported
        assert "label_thresholds" not in exported
        assert "texture_scale_label_reliable" in exported
        header = Path(csv_path).read_text(encoding="utf-8").splitlines()[0]
        assert "label_mode=count" in header
        assert "label_count_thresholds=" in header
        assert "label_thresholds=" not in header
        assert "index_scale_anchors=" in header
        Path(json_path).unlink(missing_ok=True)
        Path(csv_path).unlink(missing_ok=True)
    finally:
        Path(path).unlink(missing_ok=True)


def test_cli_count_and_index_flags(tmp_path: Path) -> None:
    def build(part: Part) -> None:
        part.insert(0.0, Note("C4", quarterLength=1.0))

    path = _write_score(build)
    csv_path = tmp_path / "out.csv"
    json_path = tmp_path / "out.json"
    try:
        code = run_analyze_score(
            [
                path,
                "--output-csv",
                str(csv_path),
                "--output-json",
                str(json_path),
                "--event-boundaries-only",
                "--label-mode",
                "count",
                "--label-count-thresholds",
                "12",
                "60",
            ]
        )
        assert code == 0
        exported = json.loads(json_path.read_text(encoding="utf-8"))
        assert exported["label_mode"] == "count"
        assert exported["label_count_thresholds"] == [12, 60]
        assert "label_thresholds" not in exported

        code = run_analyze_score(
            [
                path,
                "--output-csv",
                str(csv_path),
                "--output-json",
                str(json_path),
                "--event-boundaries-only",
                "--label-mode",
                "index",
                "--label-thresholds",
                "0.10",
                "0.35",
            ]
        )
        assert code == 0
        exported = json.loads(json_path.read_text(encoding="utf-8"))
        assert exported["label_mode"] == "index"
        assert exported["label_thresholds"] == [0.10, 0.35]
    finally:
        Path(path).unlink(missing_ok=True)


def test_duration_weighted_note_count_is_annotated() -> None:
    text = format_analysis_summary(_count_example_analysis())
    assert "vertical_note_count:" in text
    assert "(includes duplications; not part of the micro/macro index)" in text
    assert "point-sample statistics (includes terminal boundary)" in text
