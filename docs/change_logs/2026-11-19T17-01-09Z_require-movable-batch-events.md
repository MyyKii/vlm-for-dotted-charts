# Require movable events in every batch case

- Updated the Phase-2 resolver to select cases and events with a valid new
  timestamp. The single center sweep counts distinct cases and excludes the
  original timestamp before expanding destination intervals by jitter. Source-row
  tie ordering and explicit overlap errors remain part of selection.
- Replaced fixed-size tests that allowed unchanged slots. Added coverage for
  pinned events with nonzero jitter, overlapping choices in one case, and a
  feasible center between two original timestamps. Updated the Phase-2 guide.
- All 173 pattern-injection tests passed, including the large infeasible scan
  guard. Targeted Ruff lint and `git diff --check` passed. The existing BPIC2012
  mixed variant reloaded successfully. The repository-wide suite follows after
  the size and center changes.
