"""CLI entrypoint for cardinality-only analysis."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from textural_cardinality.analysis import (
    DEFAULT_BIN_CENTS,
    DEFAULT_EDO,
    DEFAULT_LABEL_COUNT_THRESHOLDS,
    DEFAULT_LABEL_MODE,
    DEFAULT_LABEL_THRESHOLDS,
    TUNING_PRESETS,
    analyze_vertical_cardinality,
    format_analysis_summary,
    inspect_score_pitches,
    write_cardinality_csv,
    write_cardinality_json,
)
from textural_cardinality.cardinality import vertical_cardinality_from_summary_row
from textural_cardinality.microtone_repair import DEFAULT_MICROTONEREPAIR
from textural_cardinality.pitch_inventory import write_pitch_inventory_csv
from textural_cardinality.pitch_overrides import load_pitch_overrides
from textural_cardinality.pitch_reference import DEFAULT_PITCH_REFERENCE


def _series_peak(analysis: dict, field: str) -> int:
    if not analysis.get("series"):
        return 0
    return max(int(row[field]) for row in analysis["series"])


def _print_analyze_score_summary(
    analysis: dict,
    *,
    csv_path: Path,
    json_path: Path,
) -> None:
    print(format_analysis_summary(analysis))
    print(f"event_count: {analysis.get('event_count', 0)}")
    print(f"sample_count: {analysis.get('sample_count', 0)}")
    print(f"max vertical_note_count: {_series_peak(analysis, 'vertical_note_count')}")
    print(f"max vertical_unique_pitch_count: {_series_peak(analysis, 'vertical_unique_pitch_count')}")
    print(
        "max vertical_pitch_class_cardinality: "
        f"{_series_peak(analysis, 'vertical_pitch_class_cardinality')}"
    )
    print(f"output_csv: {csv_path}")
    print(f"output_json: {json_path}")


def run_analyze_score(argv: list[str] | None = None) -> int:
    """Headless score analysis: parse a score file and write CSV/JSON exports."""
    parser = argparse.ArgumentParser(
        description="Analyse a MusicXML/MXL/MIDI score and export vertical cardinality series."
    )
    parser.add_argument("score_path", help="Path to MusicXML, MXL, or MIDI score file.")
    parser.add_argument("--output-csv", required=True, help="Destination path for CSV export.")
    parser.add_argument("--output-json", required=True, help="Destination path for JSON export.")
    parser.add_argument(
        "--time-step",
        type=float,
        default=0.25,
        help="Supplementary uniform grid step in quarterLength (default: 0.25).",
    )
    parser.add_argument(
        "--event-boundaries-only",
        action="store_true",
        help="Sample only event onsets/offsets (equivalent to time_step=None).",
    )
    parser.add_argument("--bin-cents", type=float, default=DEFAULT_BIN_CENTS, help="Pitch grid in cents.")
    parser.add_argument("--edo", type=int, default=DEFAULT_EDO, help="Pitch-class universe (EDO).")
    parser.add_argument(
        "--auto-detect-tuning",
        action="store_true",
        help="Auto-detect compatible symbolic grid from score pitches.",
    )
    parser.add_argument(
        "--tuning-preset",
        choices=sorted(TUNING_PRESETS.keys()),
        default=None,
        help="Named equal-tempered tuning preset.",
    )
    parser.add_argument(
        "--microtone-repair",
        default=DEFAULT_MICROTONEREPAIR,
        choices=["off", "warn", "from_accidentals"],
        help="Accidental-glyph repair (default: off).",
    )
    parser.add_argument(
        "--pitch-reference",
        default=DEFAULT_PITCH_REFERENCE,
        choices=["written", "sounding"],
        help="Written (default) or sounding concert pitch.",
    )
    parser.add_argument(
        "--pitch-overrides",
        default=None,
        help="Path to a pitch_overrides JSON sidecar.",
    )
    parser.add_argument(
        "--label-mode",
        choices=["count", "index"],
        default=DEFAULT_LABEL_MODE,
        help="Label from distinct-pitch counts (default) or from the normalised index.",
    )
    parser.add_argument(
        "--label-count-thresholds",
        nargs=2,
        type=int,
        default=list(DEFAULT_LABEL_COUNT_THRESHOLDS),
        metavar=("MICRO_MAX_COUNT", "MACRO_MIN_COUNT"),
        help=(
            "Absolute pitch-count thresholds: micro if c <= MICRO_MAX_COUNT, "
            "macro if c >= MACRO_MIN_COUNT "
            f"(default: {DEFAULT_LABEL_COUNT_THRESHOLDS[0]} {DEFAULT_LABEL_COUNT_THRESHOLDS[1]})."
        ),
    )
    parser.add_argument(
        "--label-thresholds",
        nargs=2,
        type=float,
        default=list(DEFAULT_LABEL_THRESHOLDS),
        metavar=("MICRO_MAX", "MACRO_MIN"),
        help=(
            "Index-mode thresholds only (frozen default macro_min=0.35): "
            "micro if x < MICRO_MAX, macro if x >= MACRO_MIN "
            f"(default: {DEFAULT_LABEL_THRESHOLDS[0]:.2f} {DEFAULT_LABEL_THRESHOLDS[1]:.2f})."
        ),
    )
    args = parser.parse_args(argv)

    score_path = Path(args.score_path)
    if not score_path.is_file():
        print(f"Error: score file not found: {score_path}", file=sys.stderr)
        return 1

    csv_path = Path(args.output_csv)
    json_path = Path(args.output_json)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    time_step = None if args.event_boundaries_only else float(args.time_step)
    if time_step is not None and time_step <= 0:
        print("Error: --time-step must be > 0 unless --event-boundaries-only is set.", file=sys.stderr)
        return 1

    try:
        overrides = load_pitch_overrides(args.pitch_overrides) if args.pitch_overrides else None
        analysis = analyze_vertical_cardinality(
            str(score_path),
            time_step=time_step,
            bin_cents=float(args.bin_cents),
            edo=int(args.edo),
            auto_detect_tuning=bool(args.auto_detect_tuning),
            tuning_preset=args.tuning_preset,
            microtone_repair=args.microtone_repair,
            pitch_reference=args.pitch_reference,
            pitch_overrides=overrides,
            label_mode=args.label_mode,
            label_count_thresholds=(
                int(args.label_count_thresholds[0]),
                int(args.label_count_thresholds[1]),
            ),
            label_thresholds=(
                (float(args.label_thresholds[0]), float(args.label_thresholds[1]))
                if args.label_mode == "index"
                else None
            ),
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    temp_csv = write_cardinality_csv(analysis)
    temp_json = write_cardinality_json(analysis)
    try:
        shutil.copy2(temp_csv, csv_path)
        shutil.copy2(temp_json, json_path)
    finally:
        Path(temp_csv).unlink(missing_ok=True)
        Path(temp_json).unlink(missing_ok=True)

    _print_analyze_score_summary(analysis, csv_path=csv_path, json_path=json_path)
    return 0


def run_direct_input(argv: list[str] | None = None) -> None:
    """Legacy direct-input mode: echo summary-row cardinality values as JSON."""
    parser = argparse.ArgumentParser(
        description=(
            "Vertical cardinality direct-input mode. "
            "This CLI path does not parse a score file; it uses supplied summary-row values."
        )
    )
    parser.add_argument("--notes", type=int, default=0, help="Direct input value for 'Notes'.")
    parser.add_argument("--unique-pitches", type=int, default=0, help="Direct input value for 'Unique pitches'.")
    parser.add_argument("--pc-cardinality", type=int, default=None, help="Optional explicit direct input for 'PC cardinality'.")
    parser.add_argument("--bin-cents", type=float, default=DEFAULT_BIN_CENTS, help="Pitch quantization grid in cents.")
    parser.add_argument(
        "--edo",
        type=int,
        default=DEFAULT_EDO,
        help="Pitch-class universe (EDO) for cardinality calculations.",
    )
    parser.add_argument(
        "--auto-detect-tuning",
        action="store_true",
        help="Record auto-detect provenance in metadata (no score is parsed in this mode).",
    )
    parser.add_argument(
        "--tuning-preset",
        choices=sorted(TUNING_PRESETS.keys()),
        default=None,
        help="Convenience preset for (bin_cents, edo).",
    )
    args = parser.parse_args(argv)

    active_bin_cents = float(args.bin_cents)
    active_edo = int(args.edo)
    active_preset: str | None = None
    provenance = "default_12_edo"
    explicit_params = (abs(active_bin_cents - DEFAULT_BIN_CENTS) > 1e-9) or (active_edo != DEFAULT_EDO)
    if explicit_params:
        provenance = "explicit_bin_cents_edo"
    elif args.tuning_preset is not None:
        preset = TUNING_PRESETS[args.tuning_preset]
        active_bin_cents = float(preset["bin_cents"])
        active_edo = int(preset["edo"])
        active_preset = args.tuning_preset
        provenance = "tuning_preset"
    elif args.auto_detect_tuning:
        provenance = "auto_detected"
    else:
        active_preset = "12_edo"

    row = {"Notes": args.notes, "Unique pitches": args.unique_pitches}
    if args.pc_cardinality is not None:
        row["PC cardinality"] = args.pc_cardinality
    output = vertical_cardinality_from_summary_row(row, bin_cents=active_bin_cents, edo=active_edo)
    output["_metadata"] = {
        "tuning": {
            "bin_cents": active_bin_cents,
            "edo": active_edo,
            "tuning_preset": active_preset,
            "tuning_provenance": provenance,
        }
    }
    print(json.dumps(output, ensure_ascii=False))


def run_inventory(argv: list[str] | None = None) -> int:
    """Dump the pre-analysis pitch inventory to CSV without running the sweep."""
    parser = argparse.ArgumentParser(description="Dump the pitch inventory table to CSV.")
    parser.add_argument("score_path", help="Path to MusicXML, MXL, or MIDI score file.")
    parser.add_argument("--output-csv", required=True, help="Destination path for inventory CSV.")
    parser.add_argument("--bin-cents", type=float, default=DEFAULT_BIN_CENTS)
    parser.add_argument("--edo", type=int, default=DEFAULT_EDO)
    parser.add_argument(
        "--microtone-repair",
        default=DEFAULT_MICROTONEREPAIR,
        choices=["off", "warn", "from_accidentals"],
    )
    parser.add_argument(
        "--pitch-reference",
        default=DEFAULT_PITCH_REFERENCE,
        choices=["written", "sounding"],
    )
    parser.add_argument("--pitch-overrides", default=None)
    args = parser.parse_args(argv)

    score_path = Path(args.score_path)
    if not score_path.is_file():
        print(f"Error: score file not found: {score_path}", file=sys.stderr)
        return 1
    out_path = Path(args.output_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        overrides = load_pitch_overrides(args.pitch_overrides) if args.pitch_overrides else None
        inspected = inspect_score_pitches(
            str(score_path),
            microtone_repair=args.microtone_repair,
            pitch_reference=args.pitch_reference,
            bin_cents=float(args.bin_cents),
            edo=int(args.edo),
            pitch_overrides=overrides,
        )
        write_pitch_inventory_csv(out_path, inspected.get("pitch_inventory_raw") or [])
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(inspected.get("digest_line", ""))
    print(f"output_csv: {out_path}")
    return 0


def main() -> None:
    if len(sys.argv) == 1:
        from textural_cardinality.ui.gradio_app import main as run_gradio_app

        run_gradio_app()
        return

    if sys.argv[1] == "analyze-score":
        raise SystemExit(run_analyze_score(sys.argv[2:]))
    if sys.argv[1] == "inventory":
        raise SystemExit(run_inventory(sys.argv[2:]))

    run_direct_input()


if __name__ == "__main__":
    main()
