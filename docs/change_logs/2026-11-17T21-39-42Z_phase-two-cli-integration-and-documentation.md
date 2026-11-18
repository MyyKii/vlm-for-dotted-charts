# Phase 2 stage 4 — CLI, integration, and documentation

- Completed direct batching CLI targets (center, half-open eligibility interval,
  cases, activities, event IDs) and parameter overrides. Preset and recipe modes
  reject incompatible flags and invalid settings with explicit failures.
- Strengthened manifest/reference checks and immediate-state replay validation,
  keeping strategy-specific checks in small functions. Effective numeric/time
  settings share variant identities; unused catalog entries remain irrelevant.
  Verified multiple candidate regions through three-file persistence.
- Added offline CLI and integrity tests in
  `tests/data/pattern_injection/test_cli.py` and `test_integrity.py`. Updated the
  README and completed `docs/pattern_injection.md` with usage, flags, catalog,
  recipes, schemas, controls, downstream handoff, grouping, and limitations.
  Package-data configuration includes the catalog without new dependencies.
- Checks: `ruff format --check .` **passed** (54 files);
  `ruff check .` **passed**; `python -m pytest` **363 passed**, including
  **134 Phase-2 tests**; `git diff --check` **passed**. Focused final CLI tests
  **22 passed** and integrity tests **38 passed**. An initial format check found
  a Python snippet in the feature guide; it was corrected and the check rerun.
- Verified actual seeded gap, explicit gap, seeded batching, and control CLI
  examples against **500 complete BPI Challenge 2012 cases / 10,388 events**.
  The respective change counts were 8,459 / 45 / 25 / 0. Outputs used temporary
  directories; original processed Parquet/JSON SHA-256 values stayed unchanged.
  The automated suite remains offline and does not require the BPI dataset.
- All four stages are complete. Phase-1 modules/writer and research data were
  preserved; the pre-existing `docs/blueprint.md` edit was not changed. No Git
  commits, branch changes, new dependencies, rendering, notebooks, visual review,
  annotation, or training artifacts were introduced.
- Limitations: only the two MVP timestamp strategies execute; other candidate
  labels remain future work. Prepared subsets retain Phase-1 Parquet/JSON
  provenance. At most one event per case is selected per batch, as confirmed by
  the user. Publication is atomic per file, and interrupted partial directories
  are refused. Cross-version byte equivalence is not guaranteed. GPU, rendering,
  and visual-quality checks were not run because they are outside Phase 2.
