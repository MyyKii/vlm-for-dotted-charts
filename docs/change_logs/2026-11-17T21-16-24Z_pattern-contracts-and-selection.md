# Phase 2 stage 1 — catalog, contracts, and selection

- Added the candidate catalog, validation of the two MVP strategy parameter
  contracts, and editable presets under `src/data/pattern_injection/`. Added
  package-data configuration so installed distributions include the JSON catalog.
- Added complete-case selection, stable-ID target filters, explicit/seeded gap
  target resolution, final-coordinate interval/instant regions, mandatory manifest
  validation, and a fixed nullable change schema supporting future additions and
  removals. Controls retain the same typed zero-row change table.
- Reused Phase-1 validation and identities; no Phase-1 code or data was changed.
  Added `docs/pattern_injection.md` and focused synthetic fixtures/contract tests.
- Checks: existing baseline suite **229 passed**; focused stage-1 tests
  **35 passed**; Ruff lint and formatting checks on the new modules/tests **passed**.
  The full suite after implementation is reserved for stage 4.
- Follow-ups: execution/strategy dispatch and three-file persistence are stage 2;
  batching/multiple injections are stage 3. Batching selection/jitter details have
  been requested from the user before implementing that policy. No rendering,
  reviews, annotation, or training artifacts are included.
