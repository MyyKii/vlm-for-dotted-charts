# Standardization, UTC timestamps, and validation

- Added `preprocessing.py` and `validation.py` with focused tests. Moved the
  existing column-mapping helper from the loader into preprocessing for reuse;
  loading retains its existing interface and now also accepts mapped input.
- Parse ISO 8601 or explicitly formatted timestamps; require a source timezone
  for naive values and reject invalid/ambiguous/nonexistent local dates. Normalize
  aware values to UTC. Sort by case, timestamp, and original source position.
- Preserve supplied event IDs; otherwise derive source-local `source-row:N` IDs
  paired with the provenance checksum across logs. Retain `@@source_row`, optional
  attributes, and duplicate event combinations without input mutation.
- Validation checks required columns/values, string identifiers, UTC timestamps,
  nonempty logs, event counts, and supplied identity/order columns. It returns
  diagnostics for duplicate combinations and identical timestamps without making
  semantic claims about process behavior.
- Documented the contract in the implementation plan. Declared PM4Py >=2.7 and
  Pandas >=2.0 minimums for the supported DataFrame/ISO-8601 APIs, without adding
  packages. Tested with PM4Py 2.7.23.12 and Pandas 3.1.1.
- Checks: preprocessing/validation tests **46 passed**; complete suite **100
  passed**; `ruff check .` and `ruff format --check .` **passed** after fixing one
  long error-message line. All checks are offline and CPU-only.
- Limitations/follow-ups: generated IDs are source-local, numeric epoch dates
  are unsupported, and heterogeneous timezones require scalar parsing. Storage
  and CLI integration follow in stages 4 and 5.
