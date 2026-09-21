"""Gradio interface for vertical cardinality analysis."""

from __future__ import annotations

from typing import Any

import gradio as gr
import plotly.graph_objects as go

from textural_cardinality.analysis import (
    DEFAULT_BIN_CENTS,
    DEFAULT_EDO,
    DEFAULT_LABEL_COUNT_THRESHOLDS,
    DEFAULT_LABEL_MODE,
    DEFAULT_LABEL_THRESHOLDS,
    FROZEN_INDEX_THRESHOLD,
    TUNING_PRESETS,
    analyze_vertical_cardinality,
    format_analysis_summary,
    format_result_card_markdown,
    inspect_score_pitches,
    linked_bin_cents_for_edo,
    linked_edo_for_bin_cents,
    universe_size_label,
    validate_label_count_thresholds,
    validate_label_mode,
    validate_label_thresholds,
    write_cardinality_csv,
    write_cardinality_json,
)
from textural_cardinality.microtone_repair import DEFAULT_MICROTONEREPAIR
from textural_cardinality.pitch_overrides import (
    overrides_from_inventory_edits,
    save_pitch_overrides,
    sidecar_path_for_score,
)
from textural_cardinality.pitch_reference import DEFAULT_PITCH_REFERENCE


def _extract_path(file_obj: Any) -> str:
    if file_obj is None:
        raise gr.Error("Please upload a score file (MusicXML / MXL / MIDI).")
    if isinstance(file_obj, str):
        return file_obj
    if hasattr(file_obj, "name") and file_obj.name:
        return str(file_obj.name)
    raise gr.Error("Invalid file input.")


def _normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    vmax = max(values)
    if vmax <= 0:
        return [0.0 for _ in values]
    return [v / vmax for v in values]


def _build_plot(analysis: dict[str, Any], *, view_mode: str, pc_secondary_axis: bool):
    edo = int(analysis.get("edo", 12))
    times = [float(r["time_quarters"]) for r in analysis["series"]]
    vnc = [float(r["vertical_note_count"] or 0) for r in analysis["series"]]
    vup = [float(r["vertical_unique_pitch_count"] or 0) for r in analysis["series"]]
    vpc_raw = [
        float(r["vertical_pitch_class_cardinality"])
        if r["vertical_pitch_class_cardinality"] is not None
        else 0.0
        for r in analysis["series"]
    ]
    mm_raw = [float(r.get("micro_meso_macro_normalized") or 0.0) for r in analysis["series"]]
    mm_macro_ratio = [float(r.get("micro_macro_normalized") or 0.0) for r in analysis["series"]]
    mm_card = [float(r.get("micro_macro_pitch_cardinality") or 0) for r in analysis["series"]]
    is_normalized = view_mode == "Normalized (0-1)"
    if is_normalized:
        # Normalized traces share comparable scale; prefer single-axis view.
        pc_secondary_axis = False
    y1_title = "Normalized Cardinality (0-1)" if is_normalized else "Cardinality"
    y2_title = f"PC Cardinality ({edo}-EDO)" if not is_normalized else f"Normalized PC ({edo}-EDO, 0-1)"
    pc_label = f"Pitch-Class Cardinality ({edo}-EDO)"

    if is_normalized:
        vnc_plot = _normalize(vnc)
        vup_plot = _normalize(vup)
        vpc_plot = [v / float(edo) if edo > 0 else 0.0 for v in vpc_raw]
        mm_plot = mm_raw
    else:
        vnc_plot = vnc
        vup_plot = vup
        vpc_plot = vpc_raw
        mm_plot = mm_card

    mm_params = analysis.get("params", {}).get("micro_macro_texture", {})
    meso_card = float(mm_params.get("meso_pole_cardinality") or 0.0)
    meso_y = 0.5 if is_normalized else meso_card

    peak_idx = max(range(len(mm_plot)), key=lambda i: mm_plot[i]) if mm_plot else 0

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=times,
            y=vnc_plot,
            mode="lines+markers",
            name="Note Count",
            line={"color": "#2E86DE", "width": 2.5},
            marker={"size": 5},
            hovertemplate="Time: %{x:.3f}<br>Note Count: %{y}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=times,
            y=vup_plot,
            mode="lines+markers",
            name="Unique Pitch Count",
            line={"color": "#10AC84", "width": 2.5},
            marker={"size": 5},
            hovertemplate="Time: %{x:.3f}<br>Unique Pitches: %{y}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=times,
            y=mm_plot,
            mode="lines+markers",
            name="Micro–Meso–Macro (A0-C8)" if not is_normalized else "Micro–Meso–Macro (0–1)",
            line={"color": "#8E44AD", "width": 3.0},
            marker={"size": 6},
            hovertemplate=(
                "Time: %{x:.3f}<br>Micro–Meso–Macro: %{y}<extra></extra>"
                if is_normalized
                else "Time: %{x:.3f}<br>Distinct pitches (A0-C8): %{y}<extra></extra>"
            ),
        )
    )
    if times and meso_card > 0:
        fig.add_hline(
            y=meso_y,
            line_dash="dash",
            line_color="rgba(142, 68, 173, 0.45)",
            annotation_text="Meso",
            annotation_position="right",
        )
    fig.add_trace(
        go.Scatter(
            x=times,
            y=vpc_plot,
            mode="lines+markers",
            name=pc_label,
            line={"color": "#EE5253", "width": 2.5, "dash": "dot"},
            marker={"size": 5},
            hovertemplate=f"Time: %{{x:.3f}}<br>PC Cardinality ({edo}-EDO): %{{y}}<extra></extra>",
            yaxis="y2" if pc_secondary_axis else "y",
        )
    )
    if times:
        fig.add_trace(
            go.Scatter(
                x=[times[peak_idx]],
                y=[mm_plot[peak_idx]],
                mode="markers+text",
                name="Peak Micro/Macro",
                text=["Peak"],
                textposition="top center",
                marker={"color": "#1B4F72", "size": 10, "symbol": "diamond"},
                hovertemplate="Peak at t=%{x:.3f}<br>Value=%{y}<extra></extra>",
            )
        )
    fig.update_layout(
        template="plotly_white",
        title={
            "text": "Textural_Cardinality - Vertical Cardinality Profile",
            "x": 0.01,
            "xanchor": "left",
        },
        xaxis_title="Time (quarterLength)",
        yaxis_title=y1_title,
        yaxis2={
            "title": y2_title,
            "overlaying": "y",
            "side": "right",
            "showgrid": False,
            "visible": pc_secondary_axis,
        },
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
        },
        margin={"l": 60, "r": 30, "t": 90, "b": 55},
        hovermode="x unified",
        font={"family": "Inter, Segoe UI, Arial", "size": 13},
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.07)", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.07)", zeroline=False, rangemode="tozero")
    return fig


def _records_from_df(df: Any) -> list[dict[str, Any]]:
    if df is None:
        return []
    if hasattr(df, "to_dict"):
        return list(df.to_dict(orient="records"))
    if isinstance(df, list):
        return [dict(r) for r in df if isinstance(r, dict)]
    return []


def _parts_table_from_inventory(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[tuple, dict[str, Any]] = {}
    for row in rows:
        nid = str(row.get("note_id") or "")
        try:
            part_index = int(str(row.get("_part_index", nid.split(":")[0] if nid else 0)))
        except (TypeError, ValueError):
            part_index = 0
        key = (part_index, row.get("part"), row.get("instrument"))
        if key in seen:
            continue
        seen[key] = {
            "part_index": part_index,
            "part": row.get("part") or "",
            "instrument": row.get("instrument") or "",
            "extra_semitones": 0.0,
        }
    return list(seen.values())


def on_edo_change(edo: int) -> tuple[float, str]:
    bc = linked_bin_cents_for_edo(int(edo))
    return bc, universe_size_label(bc)


def on_preset_change(preset: str) -> tuple[Any, Any, str]:
    if preset in (None, "", "(none)"):
        return gr.update(), gr.update(), gr.update()
    p = TUNING_PRESETS[str(preset)]
    bc = float(p["bin_cents"])
    return int(p["edo"]), bc, universe_size_label(bc)


def on_bin_cents_change(bin_cents: float) -> tuple[Any, str]:
    bc = float(bin_cents)
    edo = linked_edo_for_bin_cents(bc)
    label = universe_size_label(bc)
    if edo is None:
        return gr.update(), label
    return edo, label


def inspect_cardinality_app(
    file_obj: Any,
    microtone_repair: str,
    pitch_reference: str,
    bin_cents: float,
    edo: int,
):
    score_path = _extract_path(file_obj)
    inspected = inspect_score_pitches(
        score_path,
        microtone_repair=str(microtone_repair or DEFAULT_MICROTONEREPAIR),
        pitch_reference=str(pitch_reference or DEFAULT_PITCH_REFERENCE),
        bin_cents=float(bin_cents) if bin_cents is not None else DEFAULT_BIN_CENTS,
        edo=int(edo) if edo is not None else DEFAULT_EDO,
    )
    table = inspected.get("pitch_inventory") or []
    parts = _parts_table_from_inventory(inspected.get("pitch_inventory_raw") or table)
    warn_text = "\n".join(w.get("message", "") for w in inspected.get("warnings") or []) or "No warnings."
    return table, inspected.get("digest_line") or "", parts, warn_text, table


def _compose_summary(analysis: dict[str, Any]) -> str:
    summary = format_analysis_summary(analysis)
    pc_values = [float(r.get("vertical_pitch_class_cardinality") or 0) for r in analysis.get("series") or []]
    if pc_values and all(v == pc_values[0] for v in pc_values):
        if pc_values[0] == float(analysis.get("edo", 0)):
            summary += f"\nPC coverage: full Z{int(analysis.get('edo', 0))} saturation in all sampled windows."
        else:
            summary += "\nPC cardinality is constant across all sampled windows."
    return summary


def run_cardinality_app(
    file_obj: Any,
    time_step: float,
    tuning_preset: str,
    bin_cents: float,
    edo: int,
    auto_detect_tuning: bool,
    view_mode: str,
    pc_secondary_axis: bool,
    microtone_repair: str = DEFAULT_MICROTONEREPAIR,
    pitch_reference: str = DEFAULT_PITCH_REFERENCE,
    inventory_df: Any = None,
    part_transpose_df: Any = None,
    inventory_original: Any = None,
    label_mode: str = DEFAULT_LABEL_MODE,
    micro_max_count: float = DEFAULT_LABEL_COUNT_THRESHOLDS[0],
    macro_min_count: float = DEFAULT_LABEL_COUNT_THRESHOLDS[1],
    micro_max: float = DEFAULT_LABEL_THRESHOLDS[0],
    macro_min: float = DEFAULT_LABEL_THRESHOLDS[1],
):
    score_path = _extract_path(file_obj)
    ts = float(time_step) if time_step is not None else 0.25
    if ts <= 0:
        raise gr.Error("Time step must be > 0.")
    try:
        mode = validate_label_mode(label_mode)
        count_thresholds = validate_label_count_thresholds(
            (
                int(micro_max_count if micro_max_count is not None else DEFAULT_LABEL_COUNT_THRESHOLDS[0]),
                int(macro_min_count if macro_min_count is not None else DEFAULT_LABEL_COUNT_THRESHOLDS[1]),
            )
        )
        index_thresholds = None
        if mode == "index":
            index_thresholds = validate_label_thresholds(
                (
                    float(micro_max if micro_max is not None else DEFAULT_LABEL_THRESHOLDS[0]),
                    float(macro_min if macro_min is not None else DEFAULT_LABEL_THRESHOLDS[1]),
                )
            )
    except (TypeError, ValueError) as exc:
        raise gr.Error(str(exc)) from exc
    preset = None if tuning_preset == "(none)" else tuning_preset
    original_rows = _records_from_df(inventory_original)
    edited_rows = _records_from_df(inventory_df)
    part_rows = _records_from_df(part_transpose_df)
    overrides: list[dict[str, Any]] = []
    if original_rows and edited_rows:
        try:
            overrides = overrides_from_inventory_edits(original_rows, edited_rows, part_rows)
        except ValueError as exc:
            raise gr.Error(str(exc)) from exc
    analysis = analyze_vertical_cardinality(
        score_path,
        time_step=ts,
        bin_cents=float(bin_cents) if bin_cents is not None else DEFAULT_BIN_CENTS,
        edo=int(edo) if edo is not None else DEFAULT_EDO,
        auto_detect_tuning=bool(auto_detect_tuning),
        tuning_preset=preset,
        microtone_repair=str(microtone_repair or DEFAULT_MICROTONEREPAIR),
        pitch_reference=str(pitch_reference or DEFAULT_PITCH_REFERENCE),
        pitch_overrides=overrides or None,
        label_mode=mode,
        label_count_thresholds=count_thresholds,
        label_thresholds=index_thresholds,
    )
    fig = _build_plot(analysis, view_mode=view_mode, pc_secondary_axis=bool(pc_secondary_axis))
    csv_path = write_cardinality_csv(analysis)
    json_path = write_cardinality_json(analysis)
    if analysis.get("pitch_overrides"):
        try:
            save_pitch_overrides(sidecar_path_for_score(score_path), analysis["pitch_overrides"])
        except OSError:
            pass
    return fig, format_result_card_markdown(analysis), _compose_summary(analysis), csv_path, json_path


def build_demo() -> gr.Blocks:
    demo = gr.Blocks(title="Textural_Cardinality - Vertical Cardinality", theme=gr.themes.Soft())
    with demo:
        gr.Markdown("# Textural_Cardinality")
        gr.Markdown(
            "1. **Load & inspect** the pitches the tool actually read. "
            "Edit `sounding_ps` / `sounding_name` / `used_in_metrics` or add a per-part "
            "transposition. 2. **Run analysis** on the edited state. "
            "Event onsets and offsets are always sampled; the time step is a plotting grid only."
        )
        file_in = gr.File(label="Score file (MusicXML / MXL / MIDI)")
        with gr.Row():
            time_step_in = gr.Number(
                value=0.25,
                label="Supplementary time step (quarterLength)",
                info="Adds uniform grid points for plotting. Event onsets/offsets are always included.",
            )
            tuning_preset_in = gr.Dropdown(
                choices=["(none)"] + sorted(TUNING_PRESETS.keys()),
                value="(none)",
                label="Equal-tempered grid preset",
            )
            bin_cents_in = gr.Number(value=DEFAULT_BIN_CENTS, label="Bin size (cents)")
            edo_in = gr.Radio(
                choices=[12, 19, 24, 31, 48, 53, 72],
                value=DEFAULT_EDO,
                label="Pitch-class universe (EDO)",
            )
            universe_out = gr.Textbox(
                value=universe_size_label(DEFAULT_BIN_CENTS),
                label="Reference universe (A0–C8)",
                interactive=False,
            )
            auto_detect_in = gr.Checkbox(value=False, label="Auto-detect compatible symbolic grid from score")
            view_mode_in = gr.Radio(
                choices=["Raw Counts", "Normalized (0-1)"],
                value="Raw Counts",
                label="Display mode",
            )
            pc_axis_in = gr.Checkbox(value=True, label="Use secondary axis for PC cardinality (mainly useful for raw counts)")
        with gr.Row():
            label_mode_in = gr.Radio(
                choices=["count", "index"],
                value=DEFAULT_LABEL_MODE,
                label="Label mode",
                info="count = absolute distinct-pitch counts (default). index = grid-relative (c−1)/(N−1).",
            )
            micro_max_count_in = gr.Number(
                value=DEFAULT_LABEL_COUNT_THRESHOLDS[0],
                precision=0,
                label="micro_max_count",
                info="Absolute pitch-count rule: micro if c <= this value (default 12).",
            )
            macro_min_count_in = gr.Number(
                value=DEFAULT_LABEL_COUNT_THRESHOLDS[1],
                precision=0,
                label="macro_min_count",
                info="Absolute pitch-count rule: macro if c >= this value (default 60).",
            )
            frozen_index_out = gr.Number(
                value=FROZEN_INDEX_THRESHOLD,
                label="Frozen index threshold",
                info="Protocol index macro boundary, frozen at 0.35. Used only in index mode.",
                interactive=False,
            )
            micro_max_in = gr.Number(
                value=DEFAULT_LABEL_THRESHOLDS[0],
                label="index micro_max (frozen pair)",
                info="Index mode only. Frozen protocol pair with macro_min=0.35.",
                interactive=False,
            )
            macro_min_in = gr.Number(
                value=DEFAULT_LABEL_THRESHOLDS[1],
                label="index macro_min (frozen at 0.35)",
                info="Index mode only. Frozen at the protocol default 0.35.",
                interactive=False,
            )
        with gr.Row():
            microtone_repair_in = gr.Radio(
                choices=["off", "warn", "from_accidentals"],
                value=DEFAULT_MICROTONEREPAIR,
                label="Microtone repair",
            )
            pitch_reference_in = gr.Radio(
                choices=["written", "sounding"],
                value=DEFAULT_PITCH_REFERENCE,
                label="Pitch reference",
            )
        inspect_btn = gr.Button("Load & inspect")
        inventory_out = gr.Dataframe(
            label="Pitch inventory (edit sounding_ps / sounding_name / used_in_metrics)",
            interactive=True,
        )
        digest_out = gr.Textbox(label="Pitch inventory digest", lines=2)
        parts_out = gr.Dataframe(
            label="Per-part extra transposition (semitones, fractional allowed)",
            headers=["part_index", "part", "instrument", "extra_semitones"],
            interactive=True,
        )
        inspect_warnings_out = gr.Textbox(label="Inspect warnings", lines=4)
        inventory_original = gr.State([])
        run_btn = gr.Button("Run analysis", variant="primary")
        plot_out = gr.Plot(label="Vertical cardinality plot")
        result_card_out = gr.Markdown(label="Textural cardinality result")
        summary_out = gr.Textbox(label="Summary", lines=16)
        csv_out = gr.File(label="Download CSV")
        json_out = gr.File(label="Download JSON")
        edo_in.change(fn=on_edo_change, inputs=[edo_in], outputs=[bin_cents_in, universe_out])
        tuning_preset_in.change(
            fn=on_preset_change,
            inputs=[tuning_preset_in],
            outputs=[edo_in, bin_cents_in, universe_out],
        )
        bin_cents_in.change(fn=on_bin_cents_change, inputs=[bin_cents_in], outputs=[edo_in, universe_out])
        inspect_btn.click(
            fn=inspect_cardinality_app,
            inputs=[file_in, microtone_repair_in, pitch_reference_in, bin_cents_in, edo_in],
            outputs=[inventory_out, digest_out, parts_out, inspect_warnings_out, inventory_original],
        )
        run_btn.click(
            fn=run_cardinality_app,
            inputs=[
                file_in,
                time_step_in,
                tuning_preset_in,
                bin_cents_in,
                edo_in,
                auto_detect_in,
                view_mode_in,
                pc_axis_in,
                microtone_repair_in,
                pitch_reference_in,
                inventory_out,
                parts_out,
                inventory_original,
                label_mode_in,
                micro_max_count_in,
                macro_min_count_in,
                micro_max_in,
                macro_min_in,
            ],
            outputs=[plot_out, result_card_out, summary_out, csv_out, json_out],
        )
    return demo


def main() -> None:
    build_demo().launch(inbrowser=True)


if __name__ == "__main__":
    main()
