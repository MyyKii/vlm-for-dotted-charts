# Phase 3 diversification and verification

- Documented explicit full, time-window, focused, activity-filtered, and
  case-filtered configurations in `docs/dotted_chart_rendering.md`. Updated
  `README.md`, the blueprint, and the Phase-2 handoff to reflect the single
  renderer and its Phase-4 geometry contract.
- Exposed the existing Phase-2 baseline fingerprint so rendering can verify
  selected source content after the saved variant has already been validated.
  Covered missing-source CLI behavior, relative and linked Parquet paths, a
  full selection represented by its method, literal labels, deterministic
  Matplotlib settings, and filtered-marker rasterization.
- Ran the full test suite with **457 passed**, including 59 rendering tests.
  `ruff format --check .`, `ruff check .`, and `git diff --check` passed.
  The saved notebook schema validated and all outputs are cleared.
- Inspected the full BPIC2012 pair, a time window, Temporal Gap and Batching
  focus, `A_CANCELLED`, a two-case view, and a missing-source fallback in
  IPython. Default inspection created no chart files. A deliberate notebook
  export produced a clean Batching pair, and repeating the CLI focused
  BPIC2012 export reproduced both PNGs and JSON records byte for byte.
- Full-log views compress individual rows at the default size. The guide
  records observations from the pilot. Separate Jupyter kernel startup was
  blocked by the sandbox's local socket restriction, so notebook verification
  used IPython in process.
