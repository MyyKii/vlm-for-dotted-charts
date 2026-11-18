# Phase 2 — Controlled Pattern Injection

Phase 2 turns a **standardized Phase-1 event log** into reproducible, modified **event-log variants**. It records both **what changed** (individual events) and **where the intended pattern is located** (in event-log coordinates). One source can produce many independent variants, and a variant can contain several ordered injections.

**Scope:** Phase 2 modifies and validates event logs only. Phase 3 renders Dotted Charts; Phase 4 verifies visible patterns and bounding boxes; Phase 5 exports training examples. An injected pattern is a **candidate label**, not yet verified visual ground truth.

## 1. How the files work together

```text
Phase 1 input
  data/processed/BPI_Challenge_2012.parquet + BPI_Challenge_2012.json
                  |
                  v
scripts/inject_patterns.py       CLI options -> one preset or ordered recipe
                  |
                  v
engine.create_variant()
  1. catalog.py + pattern_catalog.json -> resolve and validate presets
  2. Load Phase-1 input; select complete cases -> baseline
  3. Resolve target(s) and exact assignments (explicit or seeded)
  4. Call patterns.py to modify timestamps
  5. Record changed events and intended target region(s)
  6. Validate results and build manifest / variant ID
                  |
                  v
      events, manifest, changes   (in memory)
                  |
                  v
engine.save_variant()            Validate -> write -> read back -> publish
                  |
                  v
data/processed/injected/<dataset_id>/<variant_id>/
  events.parquet                  Complete modified event log
  changes.parquet                 Exact per-event changes, linked by injection_id
  manifest.json                   Source, settings, injection IDs and locations
```

| Component | Responsibility |
| --- | --- |
| `scripts/inject_patterns.py` | Parse CLI arguments, construct a recipe, call create/save, report output. |
| `src/data/pattern_injection/configs/pattern_catalog.json` | Define candidate classes and reusable parameter presets. |
| `catalog.py` | Validate the catalog and resolve preset defaults plus overrides. |
| `engine.py` | Select cases/targets, orchestrate injections, build provenance, validate, save and load variants. |
| `patterns.py` | Apply the actual timestamp transformations (`shift_suffix`, `synchronize_events`). |

## 2. End-to-end example: inject a Temporal Gap

Run from the repository root after following the README installation instructions:

```bash
python scripts/inject_patterns.py \
  --input data/processed/BPI_Challenge_2012.parquet \
  --preset gap_medium \
  --sample-cases 500 \
  --seed 42
```

**What happens, in order:**

1. **CLI -> recipe.** The CLI translates `--preset gap_medium` into an ordered, single-entry recipe. Here, no explicit target or parameter override was supplied:
   ```json
   [{"preset": "gap_medium", "seed": 42, "target": {}, "parameters": {}}]
   ```
2. **Catalog -> effective configuration.** `resolve_preset()` loads `gap_medium`, which specifies `type=temporal_gap`, `strategy=shift_suffix`, and `duration_minutes=120`. CLI/recipe overrides can replace parameter defaults after validation.
3. **Load -> baseline.** `create_variant()` uses the existing Phase-1 loader to read the `.parquet` and matching `.json` provenance. `select_complete_cases()` uses seed 42 to choose **500 whole cases** (all their events), not a cropped time interval. The selected event log is the **baseline** for this variant; the exact case IDs are retained in the manifest. With no subset flags, all cases are used.
4. **Resolve target.** `resolve_cutoff()` picks an internal timestamp using the seed, or uses `--cutoff-utc` when provided. It records the actual cut-off and affected event/case IDs. A cut-off that shifts the entire log or selects no events is rejected.
5. **Transform.** `patterns.shift_suffix()` copies the baseline and shifts **every event at/after the cut-off** forward by 120 minutes. Existing event IDs, event counts, unrelated attributes and within-case event order remain unchanged.
6. **Record Ground Truth.** The engine compares the immediately preceding and resulting DataFrames via `_timestamp_changes()`. It creates change rows for moved events and a manifest entry describing the **empty time interval** produced by the gap.
7. **Validate and save.** `create_variant()` returns `(events, manifest, changes)` **without writing files**. The CLI passes them to `save_variant()`, which verifies consistency and publishes one new, non-overwriting variant directory.

A small example of step 5:

| Event | Before | After |
| --- | --- | --- |
| E1 | 10:00 | 10:00 |
| E2 | 11:00 | 11:00 |
| E3 | 12:00 | **14:00** |
| E4 | 13:00 | **15:00** |

For cut-off `12:00`, the candidate gap is **`[12:00, 14:00)`**, even though the *moved events* now appear at 14:00 and 15:00. This is why the pipeline stores **both** event changes and a separate target region.

## 3. The two implemented strategies

| Strategy | Target selection (engine.py) | Transformation (patterns.py) | Candidate region |
| --- | --- | --- | --- |
| `shift_suffix` (`temporal_gap`) | Explicit `cutoff_utc`, or seeded internal cut-off. | Shift all timestamps from cut-off by positive `duration_minutes`. | Empty, half-open UTC interval `[cutoff, cutoff + duration)`; all cases. |
| `synchronize_events` (`batching`) | Explicit event/case/activity/time filters and/or seeded selection of feasible events and center. | Assign selected events timestamps near the center, preserving case order. | `instant` if all assigned timestamps match; otherwise a nonempty interval containing them. |

**Batching in practice:** With `num_events=25` and `jitter_seconds=30`, the engine selects **at most one event from each of 25 distinct cases** and assigns times inside `center ± 30 seconds`, constrained by each event's predecessor/successor. Targets and center can be specified explicitly; otherwise seeded selection finds feasible ones. It records the resolved event IDs, center and actual timestamp assignments. Infeasible explicit selections fail rather than being silently replaced. Only events whose timestamps actually changed produce change rows.

The catalog currently lists six *candidate labels*, but only `temporal_gap` and `batching` have executable strategies. New presets using existing strategies require JSON edits only; new transformation algorithms require Python code and tests.

## 4. What exactly is saved?

```text
data/processed/injected/
  bpic2012/
    gap_<16-character-digest>/
      events.parquet
      changes.parquet
      manifest.json
    batch_<16-character-digest>/
      ...
    mixed_<16-character-digest>/
      ...
    control_<16-character-digest>/
      ...
```

**`events.parquet` — the result:** The **entire selected event log after all injections**, including unchanged events. It retains Phase-1 event identities (`identity:id`), case/activity fields, UTC timestamps, `@@source_row` and other attributes. Phase 3 will render this file.

**`changes.parquet` — what actually changed:** One row per **changed event per injection**. Relevant columns:

| Column | Meaning |
| --- | --- |
| `injection_id`, `event_id`, `change_type` | Link to the manifest injection and stable event identity; the MVP writes `updated`. |
| `case_id_before`, `case_id_after` | Case identities before/after this injection. |
| `timestamp_before_utc`, `timestamp_after_utc` | Timestamp **immediately before and after this injection**, not necessarily the original and final timestamp of the entire recipe. |
| `derived_from_event_id`, `before_values_json`, `after_values_json` | Nullable fields reserved for future created/removed events or other attribute changes. |

**`manifest.json` — how, where, and from what:** One record for the variant plus an ordered `injections` array. Important fields:

| Field | Purpose |
| --- | --- |
| `variant_id`, `dataset_id`, `split_group_id`, `schema_version` | Variant identity, dataset identity, leakage-aware grouping and contract version. |
| `source` | Phase-1 paths/hashes, exact selected baseline case IDs, `selected_baseline_sha256` fingerprint. |
| `injections[]` | For each injection: `injection_id`, order, preset/strategy/type, parameters/seed, requested and resolved targets, affected counts. |
| `injections[].target_regions` | **Where the expected pattern lies in the completed event log**, including empty regions. Supports UTC `interval` or `instant`, case scope and optional activity scope. |
| `injections[].affected.change_filter` | Links to its `changes.parquet` rows through `injection_id`. |
| `files`, `software_versions` | Stored Parquet checksums/schemas and relevant dependency versions. |

A reduced illustration (not a complete manifest):

```json
{
  "variant_id": "gap_<digest>",
  "source": {"selected_baseline_sha256": "<sha256>"},
  "event_changes_file": "changes.parquet",
  "injections": [{
    "injection_id": "inj_001",
    "pattern_type": "temporal_gap",
    "strategy": "shift_suffix",
    "parameters": {"duration_minutes": 120.0},
    "affected": {"change_filter": {"injection_id": "inj_001"}},
    "target_regions": [{
      "coordinate_space": "final_event_log",
      "time_type": "interval",
      "start_utc": "2012-03-12T12:00:00+00:00",
      "end_utc": "2012-03-12T14:00:00+00:00",
      "case_scope": {"type": "all"}
    }]
  }]
}
```

The coordinates in `target_regions` are **event-log time/case coordinates, not pixel bounding boxes**. Their visual visibility and geometry are evaluated only after rendering.

## 5. Multiple injections, controls and reproducibility

- **Multiple variants:** Rerun the CLI with different effective settings, seeds or case selections. Each run starts from the **Phase-1 source**, creating an independent sibling variant; it never implicitly builds on an injected variant.
- **Multiple injections in one variant:** Use `--recipe recipe.json` with an **ordered list** of preset entries. Each receives its own `injection_id` (`inj_001`, `inj_002`, ...). The next injection sees the preceding result; its change rows describe its own immediate before/after state. **MVP constraint:** An event can be targeted by at most one injection, and later injections may not invalidate earlier target regions. Conflicts fail; no automatic conflict resolution.
- **Unmodified control:** Use an empty recipe `[]`. Its `events.parquet` equals the selected baseline, `manifest.json` has `injections: []`, and `changes.parquet` is empty **but has the same typed schema**. A control is not automatically a negative training example.
- **Variant identity:** A short `gap_`, `batch_`, `mixed_` or `control_` prefix plus a deterministic 16-character digest reflects the effective source, selected cases and ordered injection configuration/targets. Unused presets do not change the ID. Existing variants are **never overwritten**.

Example control:

```bash
printf '[]\n' > control.json
python scripts/inject_patterns.py \
  --input data/processed/BPI_Challenge_2012.parquet \
  --recipe control.json --sample-cases 500 --seed 42
```

For a multi-injection recipe, write a JSON list of entries such as:

```json
[
  {"preset": "gap_medium", "target": {"cutoff_utc": "2026-01-01T12:00:00Z"}},
  {"preset": "batch_small", "parameters": {"num_events": 2, "jitter_seconds": 0},
   "target": {"event_ids": ["event-0-Work", "event-1-Work"],
              "center_utc": "2026-01-01T09:00:00Z"}}
]
```

*Illustrative fixture-specific IDs and timestamps: real targets must exist and pass feasibility checks.*

## 6. Save/load integrity and useful commands

`validate_variant()` checks schemas, IDs, per-injection change counts, target regions and transformation constraints. Crucially, it **reverses the recorded timestamp changes**, reconstructs the selected baseline and compares its fingerprint (`selected_baseline_sha256`). This detects undocumented edits, including a mutated control. File checksums separately detect changed saved Parquet bytes.

`save_variant()` writes to a temporary directory, verifies Parquet round-trips and `load_variant()` checks, then publishes exactly three files without overwriting. Incomplete directories are rejected; interrupted publication may require manual removal of the partial directory. Older variants lacking the baseline fingerprint must be regenerated. Fingerprint reproducibility depends on compatible Pandas/PyArrow versions, recorded in the manifest.

```python
from data.pattern_injection.engine import create_variant, save_variant, load_variant

events, manifest, changes = create_variant(
    "data/processed/BPI_Challenge_2012.parquet",
    [{"preset": "gap_medium"}],
    sample_cases=500,
    seed=42,
)
path = save_variant(events, manifest, changes, "data/processed/injected")
events, manifest, changes = load_variant(path)
```

| CLI option | Function |
| --- | --- |
| `--input` | Required Phase-1 `.parquet` with matching `.json` provenance. |
| `--preset` / `--recipe` | Exactly one: one catalog preset or an ordered JSON recipe (`[]` for a control). |
| `--sample-cases N` / repeated `--case-id ID` | Select complete baseline cases (mutually exclusive); default is all cases. |
| `--seed` | Reproducible selection, default `42`; default per-recipe injection seed. |
| `--cutoff-utc`, `--duration-minutes` | Gap target / duration override. |
| `--center-utc`, `--num-events`, `--jitter-seconds` | Batch center / size / jitter override. |
| `--start-utc`, `--end-utc`, repeated `--target-case-id`, `--event-id`, `--activity` | Batch eligibility filters / explicit event IDs. |
| `--catalog`, `--output-root` | Alternative catalog; output root (default `data/processed/injected`). |

Target/parameter flags apply only with `--preset` (put per-instance settings into a recipe). Explicit timestamps must be UTC (`Z` or `+00:00`). Use `python scripts/inject_patterns.py --help` for details. The CLI prints variant ID, event/injection/change counts and output path; processing errors exit with code 1, argument errors with code 2.

## 7. Handoff and current limits

Phase 3 loads a variant with `load_variant(path)` and uses `events.parquet` for Dotted Charts and `manifest.json`/`changes.parquet` for candidate pattern locations and event provenance. It can reconstruct the baseline from Phase-1 source/selection or reverse the recorded changes. Phase 4 then verifies visible labels, boxes, class-specific negatives and hard negatives; Phase 5 exports model-compatible training examples. Keep `dataset_id`, `variant_id`, `injection_id`, stable event IDs and `split_group_id` across these stages to avoid train/test leakage.

**Not part of Phase 2:** chart rendering or notebooks, review decisions, pixel boxes, automatic negative labels, training data, added/removed events, additional pattern algorithms and general overlapping-injection composition. The schema anticipates some of these without implementing them.

**Checks:** `ruff format --check .`, `ruff check .`, `python -m pytest`. Offline Phase-2 tests cover selection, transformations, controls, recipes, replay and persistence. See `docs/change_logs/` for implementation history.
