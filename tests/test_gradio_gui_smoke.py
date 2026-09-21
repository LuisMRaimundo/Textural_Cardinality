"""Smoke tests for the Gradio GUI delegation layer (no browser, no server launch)."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import gradio as gr
import plotly.graph_objects as go
import pytest

import textural_cardinality.ui.gradio_app as gradio_app


FORBIDDEN_SCOPE_TOKENS = (
    "fft",
    "stft",
    "spectral",
    "psychoacoustic",
    "combination_tone",
    "resultant_tone",
    "virtual_pitch",
    "audio_analysis",
    "librosa",
    "soundfile",
)


def _sample_analysis() -> dict[str, Any]:
    return {
        "source_file_name": "fixture.mxl",
        "time_step": 0.25,
        "sampling": "event_boundaries_with_uniform_grid",
        "duration_quarters": 2.0,
        "event_count": 2,
        "sample_count": 2,
        "edo": 24,
        "pitch_class_universe": "Z24",
        "bin_cents": 50.0,
        "warnings": [],
        "params": {
            "temporal_semantics": {
                "activity_interval": "half_open_onset_offset",
                "active_predicate": "onset <= t < offset",
            },
            "tuning": {
                "bin_cents": 50.0,
                "edo": 24,
                "tuning_preset": "24_edo",
                "tuning_provenance": "tuning_preset",
            },
            "micro_macro_texture": {
                "reference_register": "A0-C8",
                "reference_pitch_universe_size": 175,
                "micro_pole_cardinality": 1,
                "meso_pole_cardinality": 88.0,
                "macro_pole_cardinality": 175,
            },
        },
        "series": [
            {
                "time_quarters": 0.0,
                "vertical_note_count": 2,
                "vertical_unique_pitch_count": 2,
                "vertical_pitch_class_cardinality": 2,
                "micro_macro_pitch_cardinality": 2,
                "micro_macro_normalized": 0.011429,
                "micro_meso_macro_normalized": 0.005747,
            },
            {
                "time_quarters": 1.0,
                "vertical_note_count": 3,
                "vertical_unique_pitch_count": 3,
                "vertical_pitch_class_cardinality": 3,
                "micro_macro_pitch_cardinality": 3,
                "micro_macro_normalized": 0.017143,
                "micro_meso_macro_normalized": 0.011494,
            },
        ],
    }


def test_import_gradio_app_does_not_launch_server_or_run_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    analysis_calls: list[str] = []

    def _forbidden_analysis(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        analysis_calls.append("called")
        raise AssertionError("analyze_vertical_cardinality must not run on import")

    monkeypatch.setattr(
        "textural_cardinality.analysis.analyze_vertical_cardinality",
        _forbidden_analysis,
    )
    reloaded = importlib.reload(gradio_app)
    assert analysis_calls == []
    assert hasattr(reloaded, "build_demo")
    assert hasattr(reloaded, "run_cardinality_app")
    assert not hasattr(reloaded, "_server_started")


def test_build_demo_returns_gradio_blocks_without_launch() -> None:
    demo = gradio_app.build_demo()
    assert demo is not None
    assert isinstance(demo, gr.Blocks)


def test_tuning_widget_handlers_link_edo_and_bin_cents() -> None:
    bin_cents, label = gradio_app.on_edo_change(24)
    assert bin_cents == pytest.approx(50.0)
    assert "175" in label
    edo, bin_cents, label = gradio_app.on_preset_change("24_edo")
    assert edo == 24
    assert bin_cents == pytest.approx(50.0)
    assert "175" in label
    edo, label = gradio_app.on_bin_cents_change(50.0)
    assert edo == 24
    edo_update, label = gradio_app.on_bin_cents_change(37.0)
    assert edo_update == gr.update()
    none_edo, none_bin, none_label = gradio_app.on_preset_change("(none)")
    assert none_edo == gr.update()


def test_run_cardinality_app_delegates_to_analysis_once(monkeypatch: pytest.MonkeyPatch) -> None:
    analysis = _sample_analysis()
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_analyze(score_path: str, **kwargs: Any) -> dict[str, Any]:
        calls.append((score_path, kwargs))
        return analysis

    monkeypatch.setattr(gradio_app, "analyze_vertical_cardinality", fake_analyze)
    monkeypatch.setattr(gradio_app, "write_cardinality_csv", lambda _a: "/tmp/fake.csv")
    monkeypatch.setattr(gradio_app, "write_cardinality_json", lambda _a: "/tmp/fake.json")

    result = gradio_app.run_cardinality_app(
        "/tmp/fixture.mxl",
        time_step=0.5,
        tuning_preset="24_edo",
        bin_cents=50.0,
        edo=24,
        auto_detect_tuning=True,
        view_mode="Raw Counts",
        pc_secondary_axis=True,
    )

    assert len(calls) == 1
    score_path, kwargs = calls[0]
    assert score_path == "/tmp/fixture.mxl"
    assert kwargs["time_step"] == 0.5
    assert kwargs["bin_cents"] == 50.0
    assert kwargs["edo"] == 24
    assert kwargs["auto_detect_tuning"] is True
    assert kwargs["tuning_preset"] == "24_edo"
    assert kwargs["label_mode"] == "count"
    assert kwargs["label_count_thresholds"] == (12, 60)
    assert kwargs["label_thresholds"] is None
    assert result[3] == "/tmp/fake.csv"
    assert result[4] == "/tmp/fake.json"


def test_run_cardinality_app_maps_none_preset_to_null(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_analyze(_score_path: str, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return _sample_analysis()

    monkeypatch.setattr(gradio_app, "analyze_vertical_cardinality", fake_analyze)
    monkeypatch.setattr(gradio_app, "write_cardinality_csv", lambda _a: "/tmp/fake.csv")
    monkeypatch.setattr(gradio_app, "write_cardinality_json", lambda _a: "/tmp/fake.json")

    gradio_app.run_cardinality_app(
        "fixture.mxl",
        time_step=0.25,
        tuning_preset="(none)",
        bin_cents=100.0,
        edo=12,
        auto_detect_tuning=False,
        view_mode="Raw Counts",
        pc_secondary_axis=False,
    )

    assert calls[0]["tuning_preset"] is None


def test_run_cardinality_app_success_output_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gradio_app, "analyze_vertical_cardinality", lambda *_a, **_k: _sample_analysis())
    monkeypatch.setattr(gradio_app, "write_cardinality_csv", lambda _a: "/tmp/out.csv")
    monkeypatch.setattr(gradio_app, "write_cardinality_json", lambda _a: "/tmp/out.json")

    fig, card, summary, csv_path, json_path = gradio_app.run_cardinality_app(
        "fixture.mxl",
        time_step=0.25,
        tuning_preset="(none)",
        bin_cents=50.0,
        edo=24,
        auto_detect_tuning=False,
        view_mode="Normalized (0-1)",
        pc_secondary_axis=True,
    )

    assert isinstance(fig, go.Figure)
    assert isinstance(card, str)
    assert isinstance(summary, str)
    assert isinstance(csv_path, str)
    assert isinstance(json_path, str)
    assert "### Textural cardinality" in card
    assert "MICRO" in card or "MESO" in card or "MACRO" in card
    assert "fixture.mxl" in summary
    assert "EDO: 24" in summary
    assert "Note Count min/max/mean: 2/3/2.50" in summary
    assert summary.lstrip().startswith("=") or summary.startswith("=")


def test_run_cardinality_app_rejects_missing_file() -> None:
    with pytest.raises(gr.Error, match="upload a score file"):
        gradio_app.run_cardinality_app(
            None,
            time_step=0.25,
            tuning_preset="(none)",
            bin_cents=100.0,
            edo=12,
            auto_detect_tuning=False,
            view_mode="Raw Counts",
            pc_secondary_axis=False,
        )


def test_run_cardinality_app_rejects_invalid_count_thresholds() -> None:
    with pytest.raises(gr.Error, match="1 <= micro_max_count < macro_min_count"):
        gradio_app.run_cardinality_app(
            "fixture.mxl",
            time_step=0.25,
            tuning_preset="(none)",
            bin_cents=100.0,
            edo=12,
            auto_detect_tuning=False,
            view_mode="Raw Counts",
            pc_secondary_axis=False,
            label_mode="count",
            micro_max_count=60,
            macro_min_count=12,
        )


def test_run_cardinality_app_rejects_invalid_index_thresholds() -> None:
    with pytest.raises(gr.Error, match="0 < micro_max < macro_min < 1"):
        gradio_app.run_cardinality_app(
            "fixture.mxl",
            time_step=0.25,
            tuning_preset="(none)",
            bin_cents=100.0,
            edo=12,
            auto_detect_tuning=False,
            view_mode="Raw Counts",
            pc_secondary_axis=False,
            label_mode="index",
            micro_max=0.35,
            macro_min=0.10,
        )


def test_run_cardinality_app_rejects_non_positive_time_step() -> None:
    with pytest.raises(gr.Error, match="Time step must be > 0"):
        gradio_app.run_cardinality_app(
            "fixture.mxl",
            time_step=0.0,
            tuning_preset="(none)",
            bin_cents=100.0,
            edo=12,
            auto_detect_tuning=False,
            view_mode="Raw Counts",
            pc_secondary_axis=False,
        )


def test_extract_path_accepts_string_and_file_like_objects() -> None:
    assert gradio_app._extract_path("fixture.mxl") == "fixture.mxl"
    assert gradio_app._extract_path(SimpleNamespace(name="uploaded.musicxml")) == "uploaded.musicxml"


def test_summary_preserves_analysis_numerical_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    analysis = _sample_analysis()
    monkeypatch.setattr(gradio_app, "analyze_vertical_cardinality", lambda *_a, **_k: analysis)
    monkeypatch.setattr(gradio_app, "write_cardinality_csv", lambda _a: "/tmp/out.csv")
    monkeypatch.setattr(gradio_app, "write_cardinality_json", lambda _a: "/tmp/out.json")

    _fig, _card, summary, _csv, _json = gradio_app.run_cardinality_app(
        "fixture.mxl",
        time_step=0.25,
        tuning_preset="(none)",
        bin_cents=50.0,
        edo=24,
        auto_detect_tuning=False,
        view_mode="Raw Counts",
        pc_secondary_axis=False,
    )

    note_values = [row["vertical_note_count"] for row in analysis["series"]]
    unique_values = [row["vertical_unique_pitch_count"] for row in analysis["series"]]
    pc_values = [row["vertical_pitch_class_cardinality"] for row in analysis["series"]]
    assert f"Note Count min/max/mean: {min(note_values):.0f}/{max(note_values):.0f}/" in summary
    assert f"{min(unique_values):.0f}/{max(unique_values):.0f}/" in summary
    assert f"{min(pc_values):.0f}/{max(pc_values):.0f}/" in summary
    assert "Duration (quarters): 2.000" in summary
    assert "Sample points: 2" in summary


def test_gradio_app_has_no_out_of_scope_audio_or_spectral_imports() -> None:
    source_path = Path(gradio_app.__file__).resolve()
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_roots = {
        node.names[0].name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        for name in [alias.name]
    }
    imported_roots.update(
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert "librosa" not in imported_roots
    assert "soundfile" not in imported_roots

    lowered = source_path.read_text(encoding="utf-8").lower()
    for token in FORBIDDEN_SCOPE_TOKENS:
        assert token not in lowered


def test_build_plot_reads_analysis_without_mutating_series() -> None:
    analysis = _sample_analysis()
    original_series = [dict(row) for row in analysis["series"]]
    fig = gradio_app._build_plot(analysis, view_mode="Raw Counts", pc_secondary_axis=True)
    assert isinstance(fig, go.Figure)
    assert analysis["series"] == original_series
