# Require internal Temporal Gaps

- `resolve_cutoff()` now rejects explicit cut-offs at/before the earliest event:
  translating every event does not create an internal gap. Seeded targets select
  only later distinct timestamps, preserving events on both sides; a log with a
  single timestamp cannot receive a gap. Existing empty-suffix rejection remains.
- Added regressions for full-log translations, 20 reproducible seeded targets,
  and a single-timestamp input in `test_engine.py`. Updated the Phase-2 guide.
- Checks: focused engine/contract tests **60 passed**. Ruff import sorting and
  formatting were applied only to affected Python files. Full-project checks
  follow after the batching and blueprint fixes.
- The strategy, recipe format, CLI flags, and three-file contract are unchanged.
  Previously accepted translation-only targets now fail explicitly.
