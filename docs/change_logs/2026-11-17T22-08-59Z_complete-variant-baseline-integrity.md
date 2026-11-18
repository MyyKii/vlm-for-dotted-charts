# Complete baseline integrity on variant save and load

- Fixed the major review finding in `pattern_injection/engine.py`: creation
  fingerprints the complete selected baseline before injection, and the existing
  reverse replay verifies that content digest on every save and load. It covers
  unchanged events, attributes, identities, and schema, including control logs.
  Canonical Parquet bytes sort by stable event ID and normalize event timestamp
  precision to ns; no additional variant files or validation framework were added.
- Updated contract fixtures, integrity regressions, and `docs/pattern_injection.md`.
  Tests reject unrecorded timestamp/activity/resource/nullable-value changes even
  after updating the output checksum and removing the original source. Valid
  nullable attributes, precision promotion, and reordered events round-trip.
- Checks: focused Phase-2 suite **152 passed**; Ruff lint on Phase-2 modules/tests
  **passed**. Formatting was applied only to affected Python files. Full-project
  checks follow after the remaining review fixes.
- Limitation: outputs without `source.selected_baseline_sha256` must be recreated
  from Phase 1; the old source hash cannot validate their reconstructed content.
  The three-file contract, CLI, Phase-1 code, and source data are preserved.
