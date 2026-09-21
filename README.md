# Textural_Cardinality

**Repository:** [github.com/LuisMRaimundo/Textural_Cardinality](https://github.com/LuisMRaimundo/Textural_Cardinality)  
**Package version:** 1.2.2 (`pyproject.toml`, `CITATION.cff`)  
**CI:** GitHub Actions — full `tests/` suite on Python **3.10** and **3.11** (`python -m pytest tests -q`), with an **85%** coverage gate on `textural_cardinality` and `iav`. See [`.github/workflows/tests.yml`](.github/workflows/tests.yml).

Cardinality-only symbolic toolkit with a graphical interface for score upload, analysis, and professional plotting.

## Theoretical scope

Textural_Cardinality is an author-defined operational construct. It denotes a family of score-derived, time-indexed cardinality descriptors for vertical symbolic texture. In this release, it measures active note-event count, distinct symbolic pitch-unit count, equal-tempered pitch-class cardinality, and a **micro / meso / macro** label aligned with thesis §4.3.6. The headline result is the count of distinct pitches (duplications excluded) within **A0–C8**. That label is **absolute** (default thresholds 12 / 60) and does not change with the grid. A secondary index `x = (c − 1) / (N − 1)` is grid-relative (88 positions at 100-cent bins, 175 at 50-cent bins).

The construct is motivated by quantitative approaches to musical texture, especially approaches in which texture is partly described through the number of sounding components and their interrelations. It is narrower than a theory of texture. It does not model timbre, orchestration, register, spacing, density-compression, dynamics, articulation, stream segregation, perceptual salience, roughness, fusion, or formal function.

Textural_Cardinality should therefore be read as a reproducible symbolic descriptor, not as a complete analytical interpretation.

## Features

- Upload and analyze `MusicXML`, `MXL`, and `MIDI` files.
- Compute vertical cardinality over time with **exact event-boundary sampling** (brief sonorities are not missed):
  - `vertical_note_count`
  - `vertical_unique_pitch_count`
  - `vertical_pitch_class_cardinality`, parameterised by the selected EDO grid.
  - `micro_macro_pitch_cardinality` — distinct pitches (duplications excluded) within **A0–C8** (notes outside the register are excluded).
  - `micro_macro_normalized` — cardinality divided by the reference universe size (macro-referenced ratio).
  - `micro_meso_macro_normalized` — secondary, grid-relative index `x = (c − 1) / (N − 1)` on `[0, 1]`. The categorical **micro / meso / macro** label is read from the **count** of distinct pitches (default), not from this index.
- View results in an interactive Gradio interface with Plotly charts.
- Switch between `Raw Counts` and `Normalized (0-1)` views.
- Toggle a secondary axis for pitch-class cardinality visibility.
- Configure equal-tempered tuning via presets, `bin_cents`, `edo`, and auto-detection. The GUI links EDO and `bin_cents` (`bin_cents = 1200/edo`); a mismatched pair is accepted but warned.
- **Load & inspect** the pitches actually read (editable inventory, logged overrides, sidecar interchangeable with Registral_Dispersion).
- Download analysis as `CSV` and `JSON` with sampling, tuning, inventory, `schema_version` `1.2`, and the headline label fields (`texture_scale_label`, `label_mode`, `label_count_thresholds`, `label_basis`, `reference_universe_size`).

## Reading the result

The headline number is **textural cardinality**: the count of distinct pitches (duplications excluded) within A0–C8. That is `micro_macro_pitch_cardinality` (`c`), not the raw note count (which includes unisons).

The categorical **micro / meso / macro** label is **absolute** (pitch counts, independent of tuning):

- **micro** if `c <= 12`
- **macro** if `c >= 60`
- **meso** otherwise

Default `label_count_thresholds` are `(12, 60)`. The same count receives the same label at 100-cent bins (`N = 88`) and at 50-cent bins (`N = 175`). When `c` varies, the label is the duration-weighted mean count rounded to the nearest integer, with the min/max sounding labels reported alongside.

The normalised index `x = (c − 1) / (N − 1)` is **secondary and grid-relative**. It is shown once in the RESULT block as “secondary”. It is **not** the source of the default label. Optional `label_mode="index"` still exists; its threshold pair is **frozen** at the protocol default `macro_min = 0.35` (`0.10` / `0.35`).

Index scale anchors (1 / midpoint / `N`, and 0.0 / 0.5 / 1.0) describe that secondary scale only — they are not labels.

If the `microtones_merged` warning is present, the displayed label is marked unreliable.

## Scope and limitations

This toolkit is cardinality-only. It measures symbolic vertical multiplicity and symbolic pitch/pitch-class diversity. It does not perform audio analysis and does not estimate acoustic density, spectral density, loudness, orchestral balance, psychoacoustic roughness, or perceived textural weight.

**Temporal sampling.** Cardinality is defined instantaneously at score time *t* as the cardinality of the active symbolic note multiset *A(t)*. Membership is **half-open** — an event is active iff `onset <= t < offset` — so an event ending exactly when another begins is **not** counted twice and no artificial cardinality spike appears at shared boundaries. **Tied notes are merged** into single sustained events before sampling (a tie start + continuation is one event, not repeated attacks). Because *A(t)* changes only at event onsets and offsets, the analysis **always samples at all such boundary times**, ensuring that even extremely brief vertical states are represented exactly. The configurable `time_step` adds a **supplementary uniform grid** for plotting convenience only; it does not control detection completeness.

`vertical_pitch_class_cardinality` is parameterised by the active equal-tempered pitch-class universe. The default is 12-EDO. 24-EDO and 48-EDO are useful for quarter-tone and eighth-tone symbolic encodings when the score preserves those distinctions and when an equal-tempered reduction is analytically appropriate.

Non-EDO tunings, just-intonation ratios, spectral tuning fields, and continuous frequency-space models are not represented natively. Off-grid symbolic pitches are quantised to the nearest active grid in the current implementation and reported through `warnings` in JSON metadata. Named presets include 19-, 31-, and 53-EDO in addition to 12/24/48; arbitrary `bin_cents`/`edo` pairs are accepted. Tuning precedence is: explicit `bin_cents`/`edo` → `tuning_preset` → `auto_detect_tuning` → default 12-EDO. Auto-detection scans `edo ∈ [2, 240]` and keeps the **highest** compatible match (not the first), which can yield a finer grid than musically intended — use explicit presets for reproducible 19/31/53-EDO work.

**Pitched events only (metrics).** Unpitched percussion is listed in the pitch inventory with `used_in_metrics=False` and is excluded from cardinality measures. Scores with only unpitched material yield zero cardinality without error. Percussion-specific cardinality is not implemented.

**Tuning pair rule.** Universe size and pitch-unit quantisation follow `bin_cents`; pitch-class cardinality follows `edo`. A coherent pair satisfies `bin_cents × edo = 1200`. Mismatched pairs are still analysed (warn-only `inconsistent_tuning_pair`). The GUI sets both values when you pick an EDO or a named preset.

**Checking what the tool actually read.** Use **Load & inspect** in the GUI, or:

```bash
python -m textural_cardinality inventory score.musicxml --output-csv inventory.csv
```

The table is one row per notated pitch *before* tie merging. Edit `sounding_ps` / `used_in_metrics`, or add a per-part transposition; every edit is logged in `pitch_overrides` and can be saved as `<score>.pitch_overrides.json` (`"pitch_overrides_schema": "1"`), the same sidecar Registral_Dispersion loads.

**Written vs sounding.** Default `pitch_reference="written"` (backward compatible). Horn in F and octave-transposing parts (double bass) stay at written pitch unless you choose `sounding`. Transposing parts are always listed; `written` emits a warning naming them.

**Microtone repair.** Default `off`. Sibelius often writes `<accidental>quarter-sharp</accidental>` with `<alter>0</alter>`; music21 then keeps an integer `ps`. `warn` reports N mismatches; `from_accidentals` rewrites `alter` from the glyph name before ties are merged. This only recovers accidentals music21 names as quarter-tones. Arrow accidentals (sixth-/twelfth-tones, e.g. Haas) are not detected — enter them through pitch overrides.

**Halfway ties** on the grid still use Python 3 half-to-even rounding (`round(60.5) == 60`). The `microtones_merged` warning states this when fractional `ps` are collapsed on a 100-cent grid.

## Installation

```bash
pip install -e ".[dev]"
```

## Launch GUI

```bash
python -m textural_cardinality
```

With **no CLI arguments**, this launches the Gradio interface (or double-click `run.bat` on Windows).

## CLI entry routing

`python -m textural_cardinality` has four modes:

| Invocation | Behaviour |
|------------|-----------|
| No arguments | Launch Gradio GUI |
| `analyze-score …` | Headless score analysis → CSV/JSON export |
| `inventory …` | Dump the pitch-inventory table to CSV (no sweep) |
| Any other flags (e.g. `--notes`) | Legacy direct-input mode (no score parsing) |

## Headless score analysis (`analyze-score`)

Parses a `MusicXML`, `MXL`, or `MIDI` file through `analyze_vertical_cardinality` and writes the same CSV/JSON exports as the GUI. Does not launch Gradio.

```bash
python -m textural_cardinality analyze-score score.mxl \
  --output-csv out.csv \
  --output-json out.json
```

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `--output-csv` | *(required)* | Destination CSV path |
| `--output-json` | *(required)* | Destination JSON path |
| `--time-step` | `0.25` | Supplementary uniform grid step in quarter lengths |
| `--event-boundaries-only` | off | Event onsets/offsets only (`time_step=None`) |
| `--bin-cents` | `100.0` | Pitch quantisation grid in cents |
| `--edo` | `12` | Pitch-class universe size |
| `--tuning-preset` | — | Named preset: `12_edo`, `19_edo`, `24_edo`, `31_edo`, `48_edo`, `53_edo` |
| `--auto-detect-tuning` | off | Auto-detect compatible symbolic grid from score pitches |
| `--microtone-repair` | `off` | `off` / `warn` / `from_accidentals` |
| `--pitch-reference` | `written` | `written` or `sounding` |
| `--pitch-overrides` | — | Path to a `pitch_overrides` JSON sidecar |
| `--label-mode` | `count` | `count` (absolute pitch counts) or `index` (grid-relative) |
| `--label-count-thresholds` | `12 60` | Absolute pair: micro if `c <= 12`, macro if `c >= 60` |
| `--label-thresholds` | `0.10 0.35` | Index-mode pair only; `macro_min` is frozen at the protocol default `0.35` |

Tuning precedence matches the programmatic API (see **Analysis behavior** below): explicit `bin_cents`/`edo` when either differs from 12-EDO defaults → `tuning_preset` → `auto_detect_tuning` → default 12-EDO.

On success, stdout prints `event_count`, `sample_count`, `max vertical_note_count`, `max vertical_unique_pitch_count`, `max vertical_pitch_class_cardinality`, `output_csv`, and `output_json`. Exit code `0` on success; `1` on missing file, non-positive `--time-step` (without `--event-boundaries-only`), or analysis exception.

## CLI direct-input mode

This mode does not parse a score file. It echoes cardinality fields from explicitly supplied summary-row values (`Notes`, `Unique pitches`, optional `PC cardinality`). The `--bin-cents`, `--edo`, `--tuning-preset`, and `--auto-detect-tuning` flags populate `_metadata.tuning` only; they do not recompute counts from a score.

```bash
python -m textural_cardinality --notes 4 --unique-pitches 3 --pc-cardinality 2 --edo 24
```

Example output:

```json
{
  "vertical_note_count": 4,
  "vertical_unique_pitch_count": 3,
  "vertical_pitch_class_cardinality": 2,
  "_metadata": {
    "tuning": {
      "bin_cents": 100.0,
      "edo": 24,
      "tuning_preset": null,
      "tuning_provenance": "explicit_bin_cents_edo"
    }
  }
}
```

## Programmatic API

```python
from textural_cardinality.analysis import analyze_vertical_cardinality

# Default: event boundaries + supplementary grid (time_step=0.25)
result = analyze_vertical_cardinality("score.mxl")

# Minimal exact curve: event boundaries only
result = analyze_vertical_cardinality("score.mxl", time_step=None)
```

Key fields in the analysis result:

| Field | Description |
|-------|-------------|
| `sampling` | `event_boundaries_with_uniform_grid` or `event_boundaries_only` |
| `time_step` | Supplementary grid step, or `null` when omitted |
| `sample_count` | Number of time points in `series` |
| `event_count` | Number of extracted note/chord events |
| `params.tuning` | Active `bin_cents`, `edo`, preset, provenance, and non-grid pitch audit fields |
| `params.temporal_semantics` | Half-open activity, tie handling, zero-duration policy |
| `params.micro_macro_texture` | Reference register A0–C8, universe size (88/175), index-scale anchors, `label_mode`, `label_count_thresholds` |
| `texture_scale_label` | `micro` / `meso` / `macro` from distinct-pitch **count** by default |
| `label_mode` | `count` (default) or `index` |
| `label_count_thresholds` | `[micro_max_count, macro_min_count]` (default `[12, 60]`) |
| `label_thresholds` | Index-mode only: `[micro_max, macro_min]`, frozen default `macro_min=0.35` |
| `label_basis` | `constant_value` or `duration_weighted_mean` |
| `texture_scale_label_reliable` | `false` when `microtones_merged` is present |
| `reference_universe_size` | Grid-relative A0–C8 universe (`N`); used by the secondary index only |
| `warnings` | `non_grid_pitches`, `tie_merge_failed`, `zero_duration_events` when applicable |
| `series` | Time-indexed cardinality rows |

## Analysis behavior

- Uses score-global offsets (`getOffsetInHierarchy`) for temporal correctness.
- Uses an incremental sweep-line engine for efficient dense-score processing.
- **Merges tied notes** into single sustained events (`stripTies`, `matchByPitch=True`) before extraction: a tie start + continuation counts as one event, not repeated attacks; rearticulated untied notes stay distinct (`merge_ties=True` by default).
- Uses **half-open activity intervals `[onset, offset)`**: a note is not active at its exact release instant, so an event ending exactly when another begins is not double-counted, and the final score-duration sample retains no ended events.
- **Zero-duration events** contribute no cardinality (logged via a `zero_duration_events` info warning).
- **Always includes every event onset and offset** in the analysis time axis.
- Defaults to `time_step=0.25` quarter-length as a supplementary plotting grid (configurable in the UI; set to `None` in code for event-only sampling).
- Uses symbolic equal-tempered quantisation grids (`bin_cents`, `edo`) and does not model acoustic tuning systems.
- JSON includes active grid metadata (`edo`, `pitch_class_universe`, `bin_cents`, `params.tuning`, `params.temporal_semantics`, `sampling`, `sample_count`) plus `warnings` when non-grid pitches are quantised.
- CSV keeps metric column names unchanged and prepends a metadata comment line for sampling and tuning.
- Exported `series` rows contain count and micro/macro fields only; interpretive ratios (`unique_pitch_ratio`, `pc_coverage_ratio`, `pc_to_pitch_ratio`) are documented in the technical manual but are **not** written to CSV/JSON exports.

## Testing and quality control

Local verification (matches CI):

```bash
python -m pytest tests -q
python -m pytest tests -q --cov=textural_cardinality --cov=iav --cov-report=term-missing --cov-fail-under=85
```

**294 tests** across **16** modules, including temporal-semantics contracts, EDO/export contracts, unpitched policy, Gradio smoke tests (import/build/delegation only — no server launch in CI), analytical-musicological plausibility checks (not perceptual validation), headless `analyze-score` CLI tests, pitch-inventory/repair/override contracts (`tests/test_pitch_pipeline.py`), texture-scale label/RESULT contracts (`tests/test_texture_scale_label.py`), a **micro-corpus regression fixture set** (`tests/fixtures/regression_corpus/`, 7 symbolic MusicXML scores with expected JSON snapshots), **shared pitch-grid primitive tests** (`tests/test_pitch_grid_shared_primitives.py`, 4 tests), and **iav/analysis pitch-primitive parity tests** (`tests/test_iav_analysis_pitch_parity.py`, 117 tests). Regression fixtures and parity tests are software-validation guards only; they are not a musical corpus claim and do not validate perception or acoustics.

## Documentation

- Technical manual (formulas, algorithms, and interpretation): [`TECHNICAL_MANUAL.md`](TECHNICAL_MANUAL.md)
- Changelog: [`CHANGELOG.md`](CHANGELOG.md)
- Bibliographic references: [`REFERENCES.md`](REFERENCES.md)
- One-click installers (optional): [`installers/`](installers/)

## License

Copyright © 2026 Luís Raimundo and contributors. All rights reserved.

## Terms of use

This software and its documentation are proprietary. No open-source licence is granted by this repository or by [`NOTICE.md`](NOTICE.md). You may not copy, modify, merge, publish, distribute, sublicense, or sell copies of this software, or use it for commercial purposes, except as expressly permitted in writing by the copyright holder.

Academic and research use may be permitted under separate agreement or institutional policy; when in doubt, contact the author before redistribution or derivative distribution.

Third-party components: runtime dependencies (e.g. Python packages listed in `pyproject.toml`) are subject to their respective licences. This notice governs the Textural_Cardinality application source, documentation, and branding only.

## Contact

For licensing enquiries, cite the repository maintainer listed in [`CITATION.cff`](CITATION.cff).

email: lmr.2020@outlook.pt

## Acknowledgements

This project was developed by Luís Raimundo with the support and funding of the Fundação para a Ciência e a Tecnologia (FCT) and Universidade NOVA de Lisboa.

Funding DOI: https://doi.org/10.54499/2020.08817.BD

The author also gratefully acknowledges Isabel Pires for her support throughout the development of this work.
