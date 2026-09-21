# Technical Manual — Textural_Cardinality

This manual documents the mathematics, algorithms, interpretation boundaries, and export semantics currently implemented in the codebase.

## 0. Theoretical motivation and analytical status

### 0.1 Status of the term

`Textural_Cardinality` is an author-defined term. It is not used here as a pre-existing standard category in music theory. It is introduced as an operational, score-based construct: the cardinality of selected sets or multisets of symbolic musical objects active at a given score-global time point.

### 0.2 Relation to texture theory

The construct isolates one quantitative aspect of vertical texture: multiplicity. It must not be equated with musical texture as a whole. Musical texture may involve number of components, registral distribution, spacing, interdependence, timbre, articulation, dynamics, orchestration, stream behaviour, and perceptual fusion. This toolkit currently measures only selected cardinalities derived from symbolic note events.

Berry’s work on texture provides the closest theoretical motivation because it treats texture partly through sounding components, their number, and their interrelations. This toolkit adopts only the restricted cardinality aspect of that broader analytical field.

Lerdahl and Jackendoff, and Lerdahl’s later pitch-space work, are relevant as precedents for explicit formalization of musical structures and pitch relations. This toolkit does not implement GTTM, prolongational analysis, tonal tension, or Tonal Pitch Space.

Tenney’s historical work on consonance and dissonance is relevant as a terminological caution. Cardinality is not consonance, dissonance, roughness, sonority, or perceptual fusion.

Roeder’s work on pitch-class/set terminology, beat-class modelling, and pulse-stream analysis is relevant as a precedent for class-based and time-sensitive analytical abstraction. This toolkit does not compute set classes, interval-class vectors, transformational relations, beat-class sets, pulse streams, or grouping structures.

### 0.3 What the metrics do not measure

The toolkit does not measure timbre, orchestration, dynamics, roughness, spectral density, loudness, or formal function. It does not perform audio-frequency analysis.

The equal-tempered pitch-class layer is symbolic. It is not a native just-intonation model, spectral tuning model, adaptive tuning model, or continuous frequency-space model.

### 0.4 Interpretation of results

A peak in `vertical_note_count` means that more symbolic note events are active at that sampled time point. It does not necessarily mean that the passage is perceptually denser, louder, orchestrationally heavier, acoustically rougher, or formally more important.

A peak in `vertical_unique_pitch_count` means that more distinct symbolic pitch units are active. It does not describe registral compression, spacing, intervallic structure, spectral content, or voice-leading behaviour.

A peak in `vertical_pitch_class_cardinality` means that more equal-tempered pitch classes are represented in the active pitch-class universe. It does not identify the set class, interval-class vector, harmonic function, tonal distance, or microtonal/intonational system beyond the selected EDO grid.

### 0.5 Metric semantics note (temporal-semantics revision, package 1.1.0)

Package version **1.1.0** (`pyproject.toml`, `CITATION.cff`) adopts two intentional, value-affecting temporal-semantics decisions, replacing the earlier release-inclusive behaviour:

1. **Tie merging.** Tied note chains are merged into single sustained events before extraction (§3); a tie start + continuation no longer inflates `vertical_note_count` as repeated attacks. Rearticulated (untied) notes remain distinct.
2. **Half-open activity.** Vertical activity uses the half-open interval `[onset, offset)`: a note is **inactive** at its exact release instant, so coincident `A.end == B.onset` events are not counted simultaneously, and the final `t == duration` sample retains no ended events (§4–§5).

These change exported series values at shared boundaries and for tied/sustained passages. The active configuration is recorded per analysis under `params.temporal_semantics`. No changelog file exists in this repository; this note is the authoritative record of the change.

## 1) Data model and notation

The core note primitive is:

- `NoteTuple = (step, alter, octave)`
- Example: `("C", 1.0, 4)` = C-sharp 4.

For a score-global time instant `t`, let `A(t)` be the multiset of active note events. Activity is **half-open**: an event is active iff `onset <= t < offset`, and is **not** active at `t == offset`. Tied note chains are merged into one sustained event before extraction (§3), so a tie start + continuation is a single event rather than repeated attacks.

### 1.1 Core metrics

- `vertical_note_count(t) = |A(t)|`
- `vertical_unique_pitch_count(t) = |U(t)|`, where `U(t)` is the set of active symbolic pitch units after pitch-space quantisation.
- `vertical_pitch_class_cardinality(t) = |PC_edo(t)|`, where `PC_edo(t)` is the set of active equal-tempered pitch classes under the selected EDO mapping.

### 1.2 Cardinality hierarchy and ratios

Under an aligned pitch-unit grid:

`0 <= vertical_pitch_class_cardinality(t) <= vertical_unique_pitch_count(t) <= vertical_note_count(t)`

This hierarchy is not guaranteed if `bin_cents` and `edo` are deliberately mismatched.

Useful **interpretive** ratios (nonzero denominators only). These are **not** written to CSV or JSON exports; they may be computed offline from exported count fields:

- `unique_pitch_ratio(t) = vertical_unique_pitch_count(t) / vertical_note_count(t)`
- `pc_coverage_ratio(t) = vertical_pitch_class_cardinality(t) / edo`
- `pc_to_pitch_ratio(t) = vertical_pitch_class_cardinality(t) / vertical_unique_pitch_count(t)`

## 2) Pitch conversion formulas

Implemented in `src/textural_cardinality/pitch_grid.py` (canonical definitions). `iav/vertical_cardinality.py` and `src/textural_cardinality/analysis.py` import and re-export these primitives for backward-compatible import paths.

### 2.1 Pitch-space value

For each `NoteTuple n = (step, alter, octave)`:

- `ps(n) = 12 * (octave + 1) + step_to_semitone(step) + alter`

where `step_to_semitone = {C:0, D:2, E:4, F:5, G:7, A:9, B:11}`.

### 2.2 Pitch unit quantization

- `cents(n) = 100 * ps(n)`
- `unit(n) = round(cents(n) / bin_cents)`

`round` is Python 3 **half-to-even** (banker's) rounding: `round(60.5) == 60`, `round(61.5) == 62`. A dead helper `_nearest_int` (half-up) exists in `pitch_grid.py` but is not used. For `bin_cents = 100`, this is semitone-quantized pitch-space binning. When fractional pitch-space values are present on a 100-cent grid, the `microtones_merged` warning reports distinct pitches before and after quantisation and restates the half-to-even rule.

### 2.3 Pitch-class cardinality and EDO grids

Pitch-class cardinality is defined over `Z_edo = {0, 1, ..., edo - 1}`.

- `pc_edo(n) = round(ps(n) * edo / 12) mod edo`

Off-grid symbolic pitches are quantised to the nearest active grid and may appear in export `warnings`.

### 2.4 Arbitrary EDO grids and auto-detection

Named presets include 12-, 24-, 48-, 19-, 31-, and 53-EDO (`TUNING_PRESETS` in `pitch_grid.py`). Users may also supply explicit `bin_cents` and `edo` pairs.

**Tuning selection precedence** in `analyze_vertical_cardinality` (and the Gradio callback, which calls it):

1. **Explicit** `bin_cents` / `edo` when either differs from the 12-EDO defaults (`100.0`, `12`) — highest priority.
2. Else **`tuning_preset`** when supplied (GUI: any choice other than `(none)`).
3. Else **`auto_detect_tuning=True`**.
4. Else **default 12-EDO** (`tuning_provenance = default_12_edo`).

**Auto-detection** (`auto_detect_tuning=True`) inspects fractional pitch-space residues in extracted events:

1. Fast paths for semitone (12-EDO), quarter-tone (24-EDO), and eighth-tone (48-EDO) grids.
2. Intermediate candidates: third-tone (`36`-EDO, step `1/3` semitone, `bin_cents = 100/3`) and sixth-tone (`72`-EDO, step `1/6` semitone, `bin_cents = 100/6`).
3. Otherwise, a scan over `edo ∈ [2, 240]` retains the **last** (highest) EDO whose step `12/edo` divides every observed fractional residue; `bin_cents` is then set to `1200/edo`. (Multiple compatible EDO values often exist; the scan does not stop at the first match.)
4. If no grid fits within tolerance, the analysis falls back to 12-EDO and records `non_grid_pitches` in `warnings`.

Because music21 pitch-space values are floating-point, auto-detection may land on a high compatible EDO divisor (e.g. 228 rather than 19) even when the score is musically 19-EDO. For 19-, 31-, or 53-EDO analyses, prefer `tuning_preset` or explicit `bin_cents`/`edo` over auto-detect when reproducibility matters.

When `bin_cents` and `edo` are coherent (including preset pairs), `vertical_pitch_class_cardinality` is bounded by `edo` and the cardinality hierarchy in §1.2 holds. Deliberately mismatched `bin_cents`/`edo` pairs are accepted (warn-only `inconsistent_tuning_pair`) but may break that hierarchy. Universe size and pitch-unit quantisation follow `bin_cents`; pitch-class cardinality follows `edo`. The GUI links the pair: choosing an EDO or preset sets `bin_cents = 1200/edo`; editing `bin_cents` to a divisor of 1200 sets `edo`.

### 2.5 Unpitched and percussion events

Textural_Cardinality analyses **pitched** symbolic events only. Event extraction traverses `score.recurse().notes` and retains elements only when a definite pitch with octave can be formed (`_pitch_to_note_tuple`).

- `Note` and `Chord` members with valid pitch/octave are included.
- `Unpitched` percussion is listed in `pitch_inventory` with `used_in_metrics=False` and is excluded from `event_count` and from all pitch-cardinality measures.
- Scores containing only unpitched events do not crash; they yield `event_count = 0` and zero-valued cardinality series.

Percussion-specific cardinality (unpitched instrument multiplicity, timbral layer count, etc.) is **not** implemented in this release.

### 2.6 `pitch_grid.py`, `analysis.py`, and `iav/vertical_cardinality.py` relationship

Pitch-unit and pitch-class primitives (`NoteTuple`, `TUNING_PRESETS`, `_STEP_TO_SEMITONE`, `validate_edo`, `_nearest_int`, `_midi_from_note_tuple`, `_pitch_unit`, `_pc_class`) are **defined once** in `src/textural_cardinality/pitch_grid.py`. `iav/vertical_cardinality.py` and `src/textural_cardinality/analysis.py` import and re-export these names so existing import paths remain valid. The score-wide pipeline (`_collect_events`, `_build_cardinality_series`, tuning auto-detect, micro/macro, exports) exists only in `analysis.py`.

The public slice API `vertical_cardinality_for_notes` and summary-row pass-through `vertical_cardinality_from_summary_row` live in `iav/vertical_cardinality.py` and are re-exported through `textural_cardinality.cardinality` (dynamic import of the local `iav` module). `analyze_vertical_cardinality` does **not** call `iav` at runtime; slice-level cardinality on a flat active-note list is mathematically equivalent to the sweep-line counters when half-open activity semantics apply (verified in tests).

**Parity tests** (`tests/test_iav_analysis_pitch_parity.py`, 117 tests; `tests/test_pitch_grid_shared_primitives.py`, 4 tests) guard constant drift, re-export identity, primitive identity, slice cardinality equivalence, extended sweep-line vs naive-iav scans (24/48/31-EDO), event precompute (`units`/`pcs`), and a lightweight max-cardinality check on the micro-corpus fixtures. These tests do not add analytical features; they document and lock behavioural equivalence across `pitch_grid.py`, `analysis.py`, and `iav/vertical_cardinality.py`.

## 3) Event extraction from scores

Implemented in `src/textural_cardinality/analysis.py`.

**Order of operations:** parse → microtone repair → sounding conversion → part-level overrides → note-level overrides → tie merge → register filter → grid quantisation → sweep.

Inventory rows and `note_id` values (`part_index:measure:offset:voice:chord_index`) are built **before** tie merging. A note-level override or exclusion is copied onto every member of the same tie chain (`propagated_to`) so `stripTies(matchByPitch=True)` still merges the chain.

Defaults (`microtone_repair="off"`, `pitch_reference="written"`, no overrides) keep the 1.1.0 extraction numbers.

0. **Parse**, then optional microtone repair (`off` / `warn` / `from_accidentals`). `from_accidentals` recovers only accidentals music21 names as quarter-tones; arrow accidentals (sixth-/twelfth-tones) must be entered as pitch overrides.
1. Optional `toSoundingPitch()` on a copy when `pitch_reference="sounding"`. Default is **written** pitch (Horn in F and double-bass octave-change stay as notated). Transposing parts are always listed.
2. Part- then note-level overrides from the inventory / sidecar.
3. **Merge tied notes.** music21 `stripTies(inPlace=False, matchByPitch=True)`; on failure a `tie_merge_failed` warning is emitted. (Pass `merge_ties=False` to disable; default is `True`.)
4. Traverse `score.recurse().notes` (this iterator can include `Unpitched` elements; see §2.5).
5. Retain only `Note` and `Chord` elements for which `_pitch_to_note_tuple` succeeds (definite `pitch.octave`) and that are not excluded (`used_in_metrics=False`). Chord members without octave are skipped; unpitched percussion never forms an event.
6. Convert local element time to score-global time with `getOffsetInHierarchy(score)`.
7. Read duration in quarter lengths; `end = offset + max(0, duration)`.
8. Build active half-open intervals `[offset, end)`.
9. Expand chords to multiple note tuples.
10. Precompute per-event `units`, `pcs`, and `ref_units` under the active grid (recomputed after tuning selection via `_requantize_events`). Notes outside A0–C8 stay in unique-pitch count and emit `out_of_register_notes`; they are omitted from `micro_macro_*`.

## 4) Time axis construction

Implemented in `src/textural_cardinality/analysis.py::_time_axis`.

### 4.1 Instantaneous definition

Vertical cardinality is a **point measure** at score time *t*. The active multiset `A(t)` is a **piecewise-constant step function** that changes only at event onsets and offsets.

### 4.2 Event-boundary sampling (default)

The time axis is the sorted union of:

1. `0.0` and score duration `T`
2. every event **onset** `offset`
3. every event **offset** (release boundary) `end`
4. optionally, a supplementary uniform grid `{0, Δ, 2Δ, …}` while `t <= T + 1e-9`, where `Δ = max(1e-6, time_step)`

Each time point is rounded to 6 decimals for stable serialization.

### 4.3 Sampling modes

| `time_step` argument | `sampling` field | Behaviour |
|---------------------|------------------|-----------|
| positive float (default `0.25`) | `event_boundaries_with_uniform_grid` | exact boundaries + plotting grid |
| `None` | `event_boundaries_only` | minimal exact curve |

**Important:** `time_step` controls plot density, not detection completeness. Brief events shorter than `time_step` are captured because their onsets and offsets are always included.

### 4.4 What this does not do

This is not duration-weighted or window-aggregated density. A 0.01-beat event and a whole-bar chord both appear as instantaneous vertical states at their respective sample points.

## 5) Sweep-line cardinality algorithm

Implemented in `src/textural_cardinality/analysis.py::_build_cardinality_series`.

At each sampled time (half-open `[onset, offset)` activity):

1. Remove events once `end <= t` — a note is **inactive** at `t == end`, so an event ending exactly when another begins is **not** double-counted (no artificial boundary spike), and the final `t == duration` sample retains no ended events.
2. Add events with `offset <= t` (multiset counters track per-unit and per-pitch-class multiplicity; reported `vertical_unique_pitch_count` and `vertical_pitch_class_cardinality` are **distinct** unit/class counts: `len(active_units)`, `len(active_pcs)`).
3. **Zero-duration events** (`end == onset`) span an empty half-open interval and therefore contribute **no** cardinality (a `zero_duration_events` info warning is emitted when present).
4. Emit note count, unique pitch-unit count, pitch-class cardinality, and micro/macro fields (see §4.3.6)

(Implementation uses an `eps = 1e-9` float tolerance on the `<= t` comparisons; the intended predicate is `onset <= t < offset`.)

Complexity: `O(E log E + W + K)` where `E` is events, `W` is sample times, and `K` is note payload processed during add/remove.

With event-boundary sampling, `W = O(E)` in the minimal mode.

### 4.3.5 Interval summary vs point-sample statistics

`series` is unchanged: it still includes the terminal sample at `t == duration` with cardinality 0 (half-open semantics).

`summary` is computed over the half-open **intervals** between consecutive series times, duration-weighted, using the value at the start of each interval and **excluding** the terminal sample as a duration-bearing point. For each metric the export stores `duration_weighted_mean`, `min_over_sounding_time`, `max`, and `constant_value` when min equals max over sounding time. `silent_duration` is the total interval time with `vertical_note_count == 0` and is reported separately so silence does not pull the sounding-time minimum to 0.

GUI/CLI text starts with a framed ASCII `RESULT` block (cardinality, index to four decimals, `MICRO-`/`MESO-`/`MACRO-TEXTURE`, universe, thresholds), then one settings line and one pitches line, then metadata, then the duration-weighted block (`vertical_note_count` is marked as including duplications and as outside the micro/macro index), then the legacy point-sample min/max/mean line labelled `point-sample statistics (includes terminal boundary)`.

### 4.3.6 Micro/macro textural cardinality (thesis alignment)

Implemented in `src/textural_cardinality/analysis.py` (`reference_pitch_universe_size`, `micro_macro_normalized`, `_ref_pitch_units`).

**Reference register:** closed pitch-space interval **A0–C8** (`ps` 21.0–108.0). Only active notes whose pitch-space lies in this interval contribute to the micro/macro count.

**Reference universe size:**

| `bin_cents` | Positions in A0–C8 |
|-------------|-------------------|
| 100 (12-TET semitones) | 88 |
| 50 (quarter-tones) | 175 |
| other | `round((ps_high − ps_low) × 100 / bin_cents) + 1` with `ps_low = 21`, `ps_high = 108` |

**Metrics per series row:**

- `micro_macro_pitch_cardinality` — count of distinct pitches (duplications excluded) within A0–C8 among active notes.
- `micro_macro_normalized` — `micro_macro_pitch_cardinality / reference_pitch_universe_size` (macro-referenced ratio).
- `micro_meso_macro_normalized` — index `x = (c − 1) / (N − 1)` on `[0, 1]` for those distinct pitches (duplications excluded) within A0–C8.

**Poles (cardinality and normalized):**

| Pole | Cardinality (12-TET example) | `micro_meso_macro_normalized` |
|------|------------------------------|----------------------------------|
| **Micro** | 1 | 0.0 |
| **Meso** | `(1 + universe_size) / 2` (44.5 for 88) | 0.5 |
| **Macro** | full universe (88 or 175) | 1.0 |

Metadata is exposed under `params.micro_macro_texture`: `reference_register`, `reference_ps_low`, `reference_ps_high`, `reference_pitch_universe_size`, index-scale anchors (`micro_pole_cardinality` / `meso_pole_cardinality` / `macro_pole_cardinality` and the 0.0 / 0.5 / 1.0 normalised anchors — **not labels**), `texture_scale` (`micro_meso_macro`), `label_mode`, `label_count_thresholds`, and `label_thresholds` only when `label_mode="index"`.

The categorical label `texture_scale_label` is an **absolute pitch-count** reading by default (`label_mode="count"`, `label_count_thresholds=(12, 60)`): micro if `c <= 12`; macro if `c >= 60`; meso otherwise. It does not follow the index and is independent of `bin_cents`. Optional `label_mode="index"` uses the frozen protocol pair `label_thresholds=(0.10, 0.35)`.

The former “texture poles” lines are **index scale anchors (min / midpoint / max) — not labels**.

Auxiliary fields `vertical_note_count` and `vertical_unique_pitch_count` remain available but are not the thesis micro/macro construct. `vertical_note_count` includes duplications and is not part of the micro/macro index.

### Reading the result

The headline number is textural cardinality: distinct pitches (duplications excluded) within A0–C8 (`c`). The micro/meso/macro label is **absolute** (pitch counts) and does not change when the grid changes from 88 to 175 positions. The index `x = (c − 1) / (N − 1)` is **grid-relative and secondary**; it is printed once under that heading. When `c` varies, the label is the duration-weighted mean count rounded to the nearest integer, with min/max sounding labels reported. A `microtones_merged` warning marks the label unreliable (`texture_scale_label_reliable: false`).

## 6) Summary-row fallback calculations

Implemented in `iav/vertical_cardinality.py::vertical_cardinality_from_summary_row` and exposed via the CLI direct-input path (`python -m textural_cardinality --notes …`).

**Direct-input mode does not parse a score.** It echoes or passes through explicitly supplied summary-row integers. `bin_cents` and `edo` are accepted for `_metadata.tuning` only; they do **not** recompute pitch-unit or pitch-class cardinality from note tuples in this path.

Field mapping:

- `Notes` → `vertical_note_count`
- `Unique pitches` → `vertical_unique_pitch_count` (falls back to `Notes` when missing)
- `PC cardinality` → `vertical_pitch_class_cardinality` only when explicitly present (otherwise `null`)

No inference of pitch-class cardinality from unique-pitch counts is performed.

For slice-level recomputation from explicit `NoteTuple` sequences, use `vertical_cardinality_for_notes` (`textural_cardinality.cardinality`).

## 7) Output schema

Analysis output includes:

- `source_file_name`
- `time_step` — supplementary grid step, or `null`
- `sampling` — `event_boundaries_with_uniform_grid` or `event_boundaries_only`
- `duration_quarters`
- `event_count`
- `sample_count`
- `edo`
- `pitch_class_universe`
- `bin_cents`
- `params.temporal_semantics` — `activity_interval` (`half_open_onset_offset`), `active_predicate` (`onset <= t < offset`), `tie_handling` (`merge_tied_notes` or `as_imported`), `tie_merge_applied`, `zero_duration_policy` (`ignored_no_contribution`)
- `params.tuning` — `bin_cents`, `edo`, `tuning_preset`, `tuning_provenance` (`default_12_edo`, `explicit_bin_cents_edo`, `tuning_preset`, `auto_detected`), `auto_detected_from_n_events`, `non_grid_pitches_count`, `non_grid_pitches_sample`
- `params.micro_macro_texture`
- `texture_scale_label` — `micro` / `meso` / `macro` (count mode by default)
- `label_mode` — `count` or `index`
- `label_count_thresholds` — `[micro_max_count, macro_min_count]`
- `label_thresholds` — `[micro_max, macro_min]` only when `label_mode="index"` (frozen default `macro_min=0.35`)
- `label_basis` — `constant_value` or `duration_weighted_mean`
- `texture_scale_label_reliable`
- `reference_universe_size`
- `warnings` — list of objects with `code`, `severity`, `message`, `details`. Known codes:
  - `non_grid_pitches` (warning) — pitches quantised to nearest grid
  - `tie_merge_failed` (warning) — `stripTies` could not merge ties
  - `zero_duration_events` (info) — zero-duration events contribute no cardinality
- `series[]` rows containing:
  - `time_quarters`
  - `vertical_note_count`
  - `vertical_unique_pitch_count`
  - `vertical_pitch_class_cardinality`
  - `micro_macro_pitch_cardinality`
  - `micro_macro_normalized`
  - `micro_meso_macro_normalized`

CSV keeps metric column names unchanged. A leading metadata comment line records sampling, tuning, and micro/macro register metadata:

- `# sampling: …; tuning: …; micro_macro: register=A0-C8, universe_size=88; …`

**Exported series fields** (CSV columns and JSON `series[]` rows): `time_quarters`, `vertical_note_count`, `vertical_unique_pitch_count`, `vertical_pitch_class_cardinality`, `micro_macro_pitch_cardinality`, `micro_macro_normalized`, `micro_meso_macro_normalized`.

**Not exported:** interpretive ratios from §1.2 (`unique_pitch_ratio`, `pc_coverage_ratio`, `pc_to_pitch_ratio`). JSON additionally carries top-level metadata (`edo`, `bin_cents`, `params.temporal_semantics`, `params.tuning`, `params.micro_macro_texture`, `warnings`, etc.) but does not add ratio columns to `series[]`.

## 8) Brief tutorial

### 8.1 GUI tutorial

Implemented in `src/textural_cardinality/ui/gradio_app.py` (`build_demo`, `run_cardinality_app`).

1. Run `python -m textural_cardinality` with no CLI arguments (or `run.bat`) — launches the Gradio interface.
2. Upload a `MusicXML`, `MXL`, or `MIDI` file.
3. Configure:
   - **Supplementary time step** (default `0.25` quarterLength)
   - **Equal-tempered grid preset** — `(none)` or a named preset from `TUNING_PRESETS`
   - **Bin size (cents)** and **EDO** radio (`12`, `19`, `24`, `31`, `48`, `53`, `72`; arbitrary EDO is available programmatically)
   - **Auto-detect compatible symbolic grid**
   - **Display mode** — `Raw Counts` or `Normalized (0-1)` (plot scaling only; exported CSV/JSON use raw analysis values)
   - **Secondary axis for PC cardinality** (mainly for raw-count view)
   - **Label mode** (`count` default, or `index`) and **count thresholds** (default 12 / 60). Index thresholds are frozen at the protocol default `macro_min = 0.35`.
4. **Load & inspect** the pitch inventory; optionally edit sounding pitch / exclusion / per-part transposition.
5. **Run analysis**. Read the result card first (count → MICRO / MESO / MACRO), then the framed ASCII `RESULT` block, then download `CSV` / `JSON`.

EDO radio, named preset, and `bin_cents` are linked (`bin_cents = 1200/edo` when the pair is a divisor). The universe size is shown next to the controls.

The GUI always calls `analyze_vertical_cardinality` with default `merge_ties=True`. Plot normalisation (`_build_plot`) does not alter stored analysis series values.

### 8.2 Headless score analysis (`analyze-score`)

Implemented in `src/textural_cardinality/__main__.py::run_analyze_score`.

```bash
python -m textural_cardinality analyze-score path/to/score.mxl \
  --output-csv out.csv \
  --output-json out.json
```

Required: `--output-csv`, `--output-json`. Optional: `--time-step` (default `0.25`), `--event-boundaries-only` (sets `time_step=None`), `--bin-cents`, `--edo`, `--tuning-preset`, `--auto-detect-tuning`, `--microtone-repair`, `--pitch-reference`, `--pitch-overrides`, `--label-mode` (`count` default), `--label-count-thresholds` (default `12 60`), `--label-thresholds` (index mode only; frozen default `0.10 0.35`). New subcommand: `inventory` (CSV dump, no sweep).

Calls `analyze_vertical_cardinality` with default `merge_ties=True`, then `write_cardinality_csv` and `write_cardinality_json`. Does **not** launch Gradio. Exit code `0` on success, `1` on missing file, invalid `--time-step`, or analysis exception.

Stdout starts with the framed ASCII `RESULT` block (count, label, secondary index), then settings/pitches lines, metadata, duration-weighted statistics, and the legacy point-sample line. Additional lines: `event_count`, `sample_count`, `max vertical_note_count`, `max vertical_unique_pitch_count`, `max vertical_pitch_class_cardinality`, `output_csv`, `output_json`.

CLI entry routing (`main`): no arguments → Gradio; first argument `analyze-score` → this path; otherwise → direct-input mode (§8.3).

### 8.3 CLI direct-input tutorial

```bash
python -m textural_cardinality --notes 4 --unique-pitches 3 --pc-cardinality 2 --edo 24
```

### 8.4 Programmatic score analysis

```python
from textural_cardinality.analysis import analyze_vertical_cardinality

analysis = analyze_vertical_cardinality("path/to/score.mxl")
exact = analyze_vertical_cardinality("path/to/score.mxl", time_step=None)
```

Optional keyword arguments: `time_step` (default `0.25`, or `None` for event-boundaries only), `edo`, `bin_cents`, `auto_detect_tuning`, `tuning_preset`, `merge_ties` (default `True`), `debug_export_internal_path`, `microtone_repair`, `pitch_reference`, `pitch_overrides`, `label_mode` (default `"count"`), `label_count_thresholds` (default `(12, 60)`), `label_thresholds` (index mode only; frozen default `(0.10, 0.35)`).

## 10) Verification, CI, and regression fixtures

### 10.1 Test suite

**294 tests** in `tests/` (**16** modules). Representative groups:

| Module | Tests | Scope |
|--------|------:|-------|
| `test_analysis` | 7 | Event extraction, sweep-line series, time axis |
| `test_temporal_semantics_contract` | 10 | Tie merging, half-open `[onset, offset)`, zero-duration policy |
| `test_edo_export_contracts` | 19 | EDO presets, auto-detect, CSV/JSON export schema |
| `test_vertical_cardinality` / `test_microtonal_tuning` | 14 | Pitch-unit/PC cardinality, tuning metadata |
| `test_micro_macro_texture` | 7 | A0–C8 reference register and normalisation |
| `test_unpitched_policy` | 2 | Unpitched percussion exclusion |
| `test_gradio_gui_smoke` | 14 | Import, `build_demo`, delegation — **no Gradio server launch in CI** |
| `test_analytical_musicological_cardinality_plausibility` | 12 | Symbolic plausibility ordering (not perceptual validation) |
| `test_cli_analyze_score` | 6 | Headless `analyze-score` CLI and legacy direct-input routing |
| `test_regression_micro_corpus` | 31 | Micro-corpus fixture regression (see §10.3) |
| `test_iav_analysis_pitch_parity` | 117 | `pitch_grid.py` / `analysis.py` / `iav` pitch-primitive parity (see §10.4) |
| `test_pitch_grid_shared_primitives` | 4 | Shared `pitch_grid.py` re-export identity (see §10.4) |
| `test_repository_hygiene` | 5 | Repository metadata and CLI smoke checks |
| `test_pitch_pipeline` | 19 | Repair, inventory, overrides, transposition, interval summary |
| `test_texture_scale_label` | 27 | Absolute count labels, frozen index threshold 0.35, RESULT block |

### 10.2 Continuous integration

GitHub Actions workflow **Tests** (`.github/workflows/tests.yml`):

- Matrix: Python **3.10**, **3.11** (`fail-fast: false`)
- Install: `pip install -e ".[dev]"` and `pytest-cov`
- Full suite: `python -m pytest tests -q`
- Coverage gate: `--cov=textural_cardinality --cov=iav --cov-fail-under=85`

Local coverage on a representative run is approximately **87%** total (`textural_cardinality` + `iav`); the gate is set at **85%** to avoid brittle cross-environment failures.

### 10.3 Micro-corpus regression fixtures

`tests/fixtures/regression_corpus/` holds **7** synthetic symbolic MusicXML fixtures and matching expected JSON snapshots under `expected/`. Exercised by `tests/test_regression_micro_corpus.py`.

Fixtures: `monophony`, `dyad`, `triad`, `chromatic_cluster`, `tied_sustain`, `shared_boundary`, `microtonal_or_edo_case` (analysed with explicit `24_edo` preset).

Protected properties: fixture loading, scalar regression (`event_count`, `sample_count`, peak cardinalities), compact series rows, CLI/export parity with `analyze-score`, `params.temporal_semantics` in exports, ordering invariants, tie semantics, half-open boundary semantics, determinism, explicit 24-EDO path.

These fixtures are **output-stability regression** only. They are not a representative musical corpus, not perceptual validation, and not acoustic analysis.

### 10.4 `pitch_grid.py` / `analysis.py` / `iav` pitch-primitive parity

Shared pitch-grid primitives live in `src/textural_cardinality/pitch_grid.py`. `tests/test_pitch_grid_shared_primitives.py` (**4** tests) verifies that `analysis.py` and `iav/vertical_cardinality.py` re-export the same callables as the canonical module for `_pitch_unit`, `_pc_class`, `validate_edo`, and `TUNING_PRESETS`.

`tests/test_iav_analysis_pitch_parity.py` (**117** tests) verifies that the shared primitives and slice APIs agree for comparable inputs across the score-wide pipeline and the iav slice path. Covered areas:

- `_STEP_TO_SEMITONE` and `TUNING_PRESETS` constant parity (drift guard)
- `validate_edo` accept/reject behaviour
- `_midi_from_note_tuple`, `_pitch_unit`, `_pc_class` across representative `NoteTuple`s, `bin_cents`, and EDO grids
- slice cardinality equivalence vs `vertical_cardinality_for_notes`
- sweep-line series vs naive half-open scan using `vertical_cardinality_for_notes` at 24-, 48-, and 31-EDO (extends the existing 12-EDO check in `test_analysis.py`)
- `_collect_events` precomputed `units`/`pcs` vs both primitive implementations
- lightweight max-cardinality guard on all seven micro-corpus fixtures

This layer is **software validation only**. It does not extend metrics, temporal semantics, or analytical scope.

## 11) Limitations for thesis reporting

When citing results from this toolkit, state explicitly:

1. **Metric scope:** cardinality-only symbolic descriptor; not a complete texture theory.
2. **Temporal model:** instantaneous point measure at event boundaries (and optional supplementary grid points); not duration-weighted density.
3. **Pitch model:** equal-tempered pitch units and EDO pitch classes; off-grid pitches are quantised and logged in metadata.
4. **Pitched events only:** unpitched/percussion notation without definite pitch height is excluded; percussion cardinality is not implemented.
5. **Perceptual boundary:** peaks in cardinality do not imply perceptual density, loudness, or orchestrational weight.

## 12) References

See `REFERENCES.md`.
