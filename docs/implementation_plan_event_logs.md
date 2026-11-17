# Event log collection and processing

Phase 1 implements local XES/CSV loading, standardization, validation, provenance,
storage, and a thin CLI. Follow the five stages in order; each stage requires
focused tests, the complete suite, Ruff linting/formatting, and its own change log.

The event-log APIs require Python >=3.11, PM4Py >=2.7, Pandas >=3.0, and PyArrow.
Pandas 3 provides the standard-library timezone and `ValueError` behavior used
for clear daylight-saving errors without an additional timezone dependency
([Pandas 3 timezone changes](https://pandas.pydata.org/docs/whatsnew/v3.0.0.html#pytz-now-an-optional-dependency)).

The supplied plan allows a single output format such as CSV. The repository's
`AGENTS.md` and blueprint prefer **Parquet**, so standardized logs use `.parquet`
with a JSON sidecar and the already declared PyArrow engine. No automated dataset
downloads, splitting, pattern injection, rendering, or model work is included.

1. **Configuration and setup:** immutable `EventLogConfig`, standard PM4Py column
   defaults, explicit CSV mappings, timestamp format, and source timezone.
2. **Loading:** local CSV via Pandas and XES via PM4Py; preserve event attributes
   and original order without exporting or silently dropping records.
3. **Preprocessing and validation:** UTC timestamps, deterministic ordering,
   stable identities, input immutability, and useful integrity errors.
4. **Storage:** validated Parquet round trips, deterministic provenance JSON,
   source checksums, source/group identifiers, and overwrite protection.
5. **CLI and integration:** coordinate the reusable APIs, report a short summary,
   test both formats end to end, and document usage.

Completed stages and exact checks are recorded in `docs/change_logs/`.

## Standardized event-log contract

Required attributes are `case:concept:name` (string), `concept:name` (string), and
`time:timestamp` (timezone-aware UTC datetime). Text dates default to ISO 8601;
other formats require `timestamp_format`. Naive dates require `source_timezone`;
ambiguous/nonexistent local times raise instead of being inferred or shifted.

Sorting uses case ID, UTC timestamp, then `@@source_row` (original zero-based
position). Preserve source `identity:id` values, or derive `source-row:N` IDs.
Event IDs are source-local; pair them with the source SHA-256 across datasets.
Both columns survive repeated preprocessing. Additional attributes and duplicate
event combinations remain intact. Validation returns diagnostics for duplicate
case/activity/time combinations and logs whose timestamps are all identical;
these findings do not prove process behavior or operational causes.

## Processed storage contract

`save_processed_event_log(frame, config, output_path, ...)` writes a `.parquet`
file and a same-stem `.json` sidecar. `load_processed_event_log(path)` validates
both and returns the typed DataFrame without requiring the raw file. Required
columns, event IDs, source positions, counts, schema, UTC timestamps, and the
processed checksum are checked. Writing verifies exact values and dtypes through
a Parquet round trip before publishing; unsupported attribute conversions fail
without producing output files. Scalar optional attributes are the baseline;
nested XES semantics beyond a lossless DataFrame round trip are not guaranteed.

The version-1 JSON includes source and processed SHA-256 checksums, source/file
relationships, dataset/group IDs, counts, time range, effective configuration,
transformations, diagnostics, schema, and PM4Py/Pandas/PyArrow versions. Metadata
has no wall-clock creation field. Dataset IDs default to the source stem; group
IDs default to dataset IDs. Supply a common `split_group_id` for related source
extracts; storage does not infer independence or assign dataset splits.

Existing output or metadata files are refused unless overwrite is explicit.
Publication is atomic per file. Reload checks reject incomplete/mismatched pairs
(including interruption between the two replacements during explicit overwrite).

## CLI and reusable interfaces

`scripts/prepare_event_log.py` builds configuration, calls the loader,
preprocessor, validator (checking the loaded event count), and storage API, then
prints the processing summary. Expected failures return status 1 without a
success summary; argument errors use argparse's status 2. CSV column mappings,
separators, explicit timestamp formats, source timezone, dataset/group IDs, and
overwrite are configurable. See the [README](../README.md#preparing-event-logs).

| Module | Public interface |
| --- | --- |
| `config` | `EventLogConfig(input_path, ...)` |
| `loader` | `load_event_log(config) -> DataFrame` |
| `preprocessing` | `standardize_columns(frame, config) -> DataFrame` |
| `preprocessing` | `preprocess_event_log(frame, config) -> DataFrame` |
| `validation` | `validate_event_log(frame, expected_num_events=...) -> list[str]` |
| `storage` | `save_processed_event_log(frame, config, output_path, ...) -> dict` |
| `storage` | `load_processed_event_log(input_path) -> DataFrame` |

Import modules under `data.event_logs`. Tests use small tracked fixtures and
temporary directories, run without downloads or GPUs, and cover the complete
CSV/XES CLI workflows and compatibility with PM4Py after Parquet reloading.
