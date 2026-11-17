# Parquet storage and deterministic provenance

- Added `storage.py` and `tests/data/test_storage.py`; documented the version-1
  storage contract in `docs/implementation_plan_event_logs.md`.
- Store standardized logs with PyArrow and a JSON sidecar. Verify exact values,
  dtypes, event IDs, source positions, UTC timestamps, and counts through a full
  round trip before publishing. Create output directories; refuse either existing
  file unless explicitly allowed. Keep source files unchanged, including aliases.
- Metadata records source/processed checksums, source identity, dataset/group
  IDs, schema/storage version, counts, time range, effective configuration,
  transformations, diagnostics, and PM4Py/Pandas/PyArrow versions. No runtime
  timestamp is included, keeping metadata deterministic for identical inputs.
- Reload checks sidecar identity/version, checksum, schema, counts, and data
  integrity. The original source file is not required for reloading.
- Checks: storage tests **20 passed**; complete suite **120 passed**;
  `ruff check .` and `ruff format --check .` **passed**. Tests include nullable
  integers/booleans/strings, categories, nanosecond timestamps, deterministic
  bytes/metadata, explicit overwrites, corruption, and unsupported attributes.
- Limitations/follow-ups: flat scalar attributes are the baseline. Unsupported
  conversions fail explicitly. Publication is atomic per file, not across the
  pair; reload detects incomplete/mismatched artifacts. Grouping related sources
  requires an explicit group ID. CLI integration is stage 5.
