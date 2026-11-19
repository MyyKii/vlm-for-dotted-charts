# Validated baselines and deterministic Dotted Charts

- Added `rendering.views` to validate saved Phase-2 variants, recover the exact
  full, sampled, or explicit-case Phase-1 baseline, and handle missing sources
  for standalone modified charts.
- Added one Agg scatter renderer in `rendering.renderer` with shared full-view
  limits, baseline case rows and activity colors, fixed margins, and descriptive
  crowding diagnostics. Tick reduction preserves all event and case positions.
- Added `tests/rendering` fixtures and checks. All 10 focused tests, Ruff lint,
  and `git diff --check` passed. Inspected a PM4Py reference on the tracked small
  XES fixture using explicit timestamp, case, and activity columns.
- Added `docs/dotted_chart_rendering.md` and documented relative source paths.
  The later Phase-3 stages cover notebook views, export metadata, and PNG checks.
