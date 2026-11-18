# Blueprint boundaries and final review verification

- Aligned `docs/blueprint.md` with the agreed pipeline: Phase 2 transforms logs
  and records provenance; Phase 3 produces charts, coordinate mappings, and one
  inspection notebook reusing production rendering; Phase 4 validates visual
  labels, visibility, boxes, and negatives. Removed rendering gates before Phase 2
  and the requirement to inject logs during Phase-3 inspection. Updated the status,
  pipeline diagram, and handoffs. Model-specific annotation conversion remains
  in Phase 5, preserving model-independent Phase-4 ground truth.
- Completed the existing Phase-2 guide with baseline-content verification,
  bounded names, internal gaps, and efficient modifying batching assignments.
  No rendering, notebook, annotation, or training implementation was added.
- Final checks: `ruff format --check .` **passed**; `ruff check .` **passed**;
  `python -m pytest` **398 passed** (35 new regression cases); and
  `git diff --check` **passed**. Earlier focused results are recorded in the
  individual integrity, naming, gap, and batching change logs. The blueprint
  changes were reviewed as documentation; no runtime documentation tests were
  invented. No GPU, network, or visual-quality checks were run for these fixes.
- Phase-1 modules, CLI flags, dependencies, and the three-file layout are unchanged.
  Source data and existing results were not rewritten. No Git commits, pushes, or
  branch changes were made.
- Remaining limitations: older outputs without a selected-baseline digest must
  be regenerated into a fresh output location. Canonical Parquet fingerprints
  require compatible recorded library versions. Abrupt interruption can still
  leave a partial directory, which save/load refuse; publication remains atomic
  per file. Additional strategies and all visual ground-truth work remain later
  tasks, as agreed.
