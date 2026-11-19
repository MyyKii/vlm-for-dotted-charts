# Support a target and minimum batch size

- Added optional `min_events` to batching parameters. The catalog defaults it
  to the target after recipe overrides. The resolver maximizes the achievable
  size up to `num_events` when choosing a center, with seeded tie-breaking.
  Explicit event-ID requests retain the target cardinality.
- Accepted reduced batches in creation, saving, and loading. New batch
  manifests require a change row for each resolved event ID. Historical batch
  manifests retain their original validation rules.
- Updated the Phase-2 guide and added tests for the 25, 18, and 7 movable-case
  outcomes, minimum validation, the default, seeded center choice, reduced
  batch round trips, and a legacy round trip with an unchanged event.
- All 191 pattern-injection tests passed. Targeted Ruff lint and
  `git diff --check` passed. The repository-wide suite follows after the
  automatic center bounds change.
