# Phase 2 stage 2 — Temporal Gap, engine, and storage

- Implemented `shift_suffix` with a minimal strategy registry and independent
  variant creation from the existing Phase-1 loader. Gap changes preserve IDs,
  attributes, counts, source positions, and per-case ordering. Manifests record
  effective settings, exact selection, original/processed provenance, grouping,
  and empty gap locations in final event-log coordinates.
- Added deterministic variant identity, immediate timestamp change records,
  baseline reconstruction, and a minimal Phase-2 reader/writer. Each variant has
  exactly three files, including controls with typed empty changes. Round trips,
  checksums, schemas, counts, and references are verified. Existing/partial
  results are refused; raised publication failures remove newly created files.
- Added `scripts/inject_patterns.py` for single gaps and empty-recipe controls;
  updated `docs/pattern_injection.md` with interfaces, CLI, and persistence rules.
  Added engine/storage/CLI tests under `tests/data/pattern_injection/`.
- Checks: focused Phase-2 suite **56 passed**; Ruff lint and format checks on
  affected Python files **passed**. Full-project checks remain for stage 4.
- Limitations/follow-ups: batching and multiple injections follow in stage 3.
  Prepared subsets retain the Phase-1 Parquet/JSON contract. Publication is atomic
  per file; abrupt process termination can leave a directory that readers reject.
  No Phase-1 writer changes, `events.json`, rendering, or later-phase work.
