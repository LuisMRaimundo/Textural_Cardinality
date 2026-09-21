# Changelog

## 1.2.2 — 2026-09-21

Absolute (count) micro/meso/macro labels; index is secondary and grid-relative.

- Default **`label_mode="count"`** with **`label_count_thresholds=(12, 60)`**: micro if `c <= 12`, macro if `c >= 60`, otherwise meso. The same count yields the same label on 100-cent and 50-cent grids.
- Varying series: label the duration-weighted mean count rounded to the nearest integer, and report min/max sounding labels.
- If `microtones_merged` is present, the displayed label appends ` (UNRELIABLE: distinct notated pitches were merged by the grid)` and JSON sets `texture_scale_label_reliable: false`.
- Index mode remains available (`--label-mode index`). The index threshold pair is **frozen** at the protocol default **`macro_min=0.35`** (`label_thresholds=(0.10, 0.35)`); GUI index fields are read-only.
- RESULT card/block in count mode: pitch-count rule and count scale (caret on its own line); the index appears once as **secondary**.
- Metadata lines formerly titled “Texture poles …” are now “Index scale anchors (min / midpoint / max) — not labels”.
- JSON/CSV: always `label_mode`, `label_count_thresholds`; `label_thresholds` only when `label_mode="index"`.
- Docs: “Reading the result” states that the label is absolute and the index is grid-relative. Package version `1.2.2`.

## 1.2.1 — 2026-09-21

Explicit micro / meso / macro label on the headline result.

- **`label_thresholds=(micro_max, macro_min)`** (default `0.10`, `0.25`; require `0 < micro_max < macro_min < 1`) in the API, CLI (`--label-thresholds 0.10 0.25`), and GUI. These are annotation-protocol conventions, not a nearest-pole rule.
- **`texture_scale_label`** is read from the index `x = (c−1)/(N−1)` (`micro_meso_macro_normalized`): `micro` if `x < micro_max`; `macro` if `x >= macro_min`; otherwise `meso`. A constant sounding value is labelled as-is; a varying series is labelled from the duration-weighted mean and reports the min/max sounding labels.
- JSON and the CSV header comment export `texture_scale_label`, `label_thresholds`, `label_basis` (`constant_value` | `duration_weighted_mean`), and `reference_universe_size`.
- GUI result card above the text summary; every text summary (GUI, CLI) starts with a framed ASCII `RESULT` block, then settings and pitch-inventory lines. `vertical_note_count` is marked as including duplications and as outside the micro/macro index.
- Docs: “Reading the result” in README and TECHNICAL_MANUAL. Package version `1.2.1`; JSON `schema_version` remains `1.2`.

## 1.2.0 — 2026-09-21

Pitch-read audit, interchangeable overrides with Registral_Dispersion, and duration-weighted summaries.

- **Defaults unchanged:** `microtone_repair="off"`, `pitch_reference="written"`, no overrides. Regression snapshots and iav/analysis pitch-primitive parity tests are unchanged. Grid quantisation still uses Python 3 half-to-even `round`.
- **Microtone repair** (`off` / `warn` / `from_accidentals`) for Sibelius glyph-only accidentals. `from_accidentals` recovers only names music21 treats as quarter-tones; arrow accidentals (sixth-/twelfth-tones) must be entered as pitch overrides.
- **Pitch reference** `written` (default) or `sounding` (`toSoundingPitch()` on a copy). Transposing parts are always listed; `written` emits a warning when any exist.
- **Tuning pair:** warn-only `inconsistent_tuning_pair` when `bin_cents × edo ≠ 1200`. GUI links EDO/preset/`bin_cents` and shows the A0–C8 universe size. `microtones_merged` reports distinct pitches before/after 100-cent quantisation and states that halfway ties follow half-to-even rounding.
- **Pitch inventory + overrides** before tie merging (`note_id` = `part_index:measure:offset:voice:chord_index`). Sidecar `{"pitch_overrides_schema": "1", "pitch_overrides": [...]}` is interchangeable with Registral_Dispersion. Note-level edits propagate across a tie chain (`propagated_to`).
- **Unpitched** notes appear in the inventory with `used_in_metrics=False`. Out-of-register pitched notes warn that unique-pitch count includes them while `micro_macro_*` does not.
- **Summary:** duration-weighted interval statistics exclude the terminal half-open boundary; point-sample min/max/mean remain under a labelled legacy line. JSON `schema_version` is `1.2`.
- CLI: `analyze-score --microtone-repair --pitch-reference --pitch-overrides`; new `inventory` subcommand. GUI is two-step (Load & inspect → Run analysis).
