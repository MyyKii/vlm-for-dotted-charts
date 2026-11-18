# Bounded variant and staging directory names

- Replaced preset-name concatenation in `pattern_injection/engine.py` with a
  fixed descriptive prefix (`gap`, `batch`, `mixed`, or `control`) plus the
  deterministic digest of the effective ordered recipe. Generated IDs are at
  most 24 characters, independent of preset spelling and recipe length.
  Manifest validation rejects unsafe or over-64-character externally supplied
  IDs; temporary directories use a fixed short prefix.
- Added `test_variant_ids.py` regressions for long presets, 24-instance repeated
  recipes, long repeated presets, deterministic identities, changed seeds, safe
  persistence, and bounded staging names. Updated `docs/pattern_injection.md`.
- Checks: naming and existing engine tests **25 passed**; focused Ruff lint
  **passed**. Formatting was applied to the two affected Python files;
  full-project checks follow after the remaining fixes.
- No CLI or three-file layout changes. Generated directory names now use the
  short prefixes; preset names remain recorded inside each injection.
