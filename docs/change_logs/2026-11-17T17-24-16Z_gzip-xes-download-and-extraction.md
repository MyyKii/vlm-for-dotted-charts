# Gzip-compressed XES downloads

- Extended `downloader.py` to accept `.xes.gz` URL names and filename overrides,
  including uppercase suffixes. Stream the archive unchanged, decompress it with
  built-in gzip into temporary storage, and return the extracted `.xes` path.
  Both complete files are preserved under raw storage after successful extraction.
- Check both destinations before downloading. Stage and verify decompression
  before publishing; reject corrupt headers/deflate streams, truncation, invalid
  CRCs, and empty extracted files. No new dependencies were added.
- Added a small publication helper using hard-link backups and rollback callbacks
  so I/O publication failures remove newly created files or restore prior files.
  Existing downloads survive failed transfers and decompression with overwrite.
- Added generated gzip fixture bytes and 25 focused cases in downloader tests;
  retained CSV/plain XES coverage and rejection of unsupported `.csv.gz` files.
  The three new success cases first failed against the old implementation, then
  passed after implementation.
- Checks: downloader tests **74 passed**, complete suite **225 passed**;
  `ruff check .` and `ruff format --check .` **passed**. All HTTP is mocked.
- Follow-ups: verify gzip preparation through the unchanged CLI and document use.
  Publication is atomic per file; rollback handles raised I/O errors, not process
  termination between publishing two files. General archives remain unsupported.
