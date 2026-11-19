# Final PNG geometry and explicit export

- Added `rendering.geometry` for top-left pixel coordinates from the drawn Agg
  axes and event-ID membership in `rendering.views`. The versioned JSON stores
  the full case ordering and the effective transform for Phase 4.
- Added `rendering.export`, `scripts/render_charts.py`, and a deliberate notebook
  export cell. Each role gets a stable chart ID, with shared view IDs for matched
  pairs. Publication stages both output files, exclusively reserves directories,
  and rolls back its own files on errors. The exported PNG uses the clean canvas.
- All 44 rendering tests passed, including decoding PNGs at requested sizes,
  mapping rasterized markers within 3 px, checking co-located event inclusion,
  testing rollback and duplicate exports, and comparing clean preview bytes
  with export. Focused Ruff checks and `git diff --check` passed.
- Ran the focused CLI example on the full BPIC2012 saved gap variant and
  inspected its clean baseline/modified PNGs. Added usage, schema, and geometry
  documentation in `docs/dotted_chart_rendering.md`. Abrupt process interruption
  during publication can leave an incomplete directory that a retry refuses.
