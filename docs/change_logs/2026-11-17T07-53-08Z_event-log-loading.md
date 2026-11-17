# CSV and XES loading

- Added `loader.py`, tracked CSV/XES fixtures, shared fixture paths, and loader
  tests. Local sources return standard columns while retaining optional event
  attributes, source order, textual case/event IDs, and all rows for validation.
- CSV parsing supports mappings and separators and rejects malformed records.
  Missing files, directories, incompatible extensions, missing columns, and
  conflicting mappings produce descriptive errors. Source files stay unchanged.
- Inspected installed PM4Py APIs: `format_dataframe()` removes missing required
  rows, and XES date parsing assumes UTC for naive dates. Consequently, loading
  applies structural mappings directly and retains XES timestamp text through a
  streaming XML pass, leaving timezone decisions to preprocessing. PM4Py's
  `read_xes()` supplies the event attributes using its strict iterparse backend.
- Checks: loader tests **15 passed**; complete suite **54 passed**;
  `ruff check .` and `ruff format --check .` **passed**. No external datasets or
  services are needed by the tests.
- Limitations: local uncompressed `.csv`/`.xes` only. Preprocessing, validation,
  export, and CLI follow in subsequent stages. The XML timestamp pass adds one
  sequential source read to preserve explicit timezone semantics.
