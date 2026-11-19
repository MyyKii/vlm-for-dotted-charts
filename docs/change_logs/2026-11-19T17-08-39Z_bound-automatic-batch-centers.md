# Bound automatic batch centers to the requested interval

- Intersected the automatic center search with `[start_utc, end_utc)` and
  swept the clipped boundaries. Validation enforces the interval for new
  manifests with an automatic center. A requested `center_utc` identifies a
  manual center. Jitter and neighbor bounds govern assignments. Historical
  manifests retain their original center validation.
- Updated the bundled two-pattern recipe to target 25 events with a minimum of
  10. Updated the guide and added tests for both edges, a case where the
  exclusive endpoint is the only possible center, and legacy and manual centers.
- All 194 focused tests and all 482 repository tests passed. Ruff format and
  lint and `git diff --check` passed. A separate check compared 200 randomized
  sweeps against exhaustive nanosecond-range enumeration.
- Ran the updated recipe on the full saved BPIC2012 log in a temporary output
  directory. Its batch moved 25 events across 25 cases at
  `2012-01-10T08:16:07.447000001Z`. Both the new and historical mixed variants
  reloaded successfully.
