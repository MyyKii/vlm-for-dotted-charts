# Event Log Downloading — Developer Reference

Downloading is optional source acquisition for
[Phase 1 — Event Log Collection & Processing](event_log_preparation.md).
It produces local raw files before loading, preprocessing, validation, and storage
begin. This reference describes the implemented download contract.

## Interface & Raw Storage

`data.event_logs.downloader.download_event_log(url, filename=None,
raw_dir=Path("data/raw"), overwrite=False)` returns the local source `Path`.
The CLI requires exactly one of `--input` or `--url`; `--filename` requires URL
input. Existing processing options apply after download.

HTTP(S) URLs must include a valid host and contain no unescaped whitespace or
control characters. Use the decoded URL basename unless `filename` overrides it.
Supported names start with a letter, number, or underscore, contain only word
characters, spaces, dots, and hyphens, and end in `.xes`, `.csv`, or `.xes.gz`
(case-insensitive). Paths, hidden names, and unsupported extensions are rejected.
Gzip header filenames never determine the extracted path.

The default raw directory is `data/raw/` relative to the working directory.
The downloader creates it as needed and checks destinations before HTTP access.
Existing files, including either gzip destination, require explicit overwrite.

## HTTP Transfer Contract

Requests streams the response in 64 KiB chunks with a 10-second connect timeout
and 60-second read-inactivity timeout. The latter is not a total transfer limit.
The request asks for `Accept-Encoding: identity`; any HTTP content encoding is
decoded by Requests.

Only a nonempty HTTP 200 response without `Content-Range` is published. For an
unencoded response, `Content-Length`, when present, must be a nonnegative integer
matching the downloaded byte count. HTTP-encoded responses rely on Requests'
protocol/decoding errors rather than comparing encoded and decoded sizes.

HTTP errors, timeouts, interrupted streams, empty bodies, and detectable size
mismatches fail without publishing partial files. Without a reliable length or
protocol error, a clean end of the response alone cannot independently prove
source completeness. Event-log validity is checked by the preparation pipeline.

## Gzip XES Extraction

For `.xes.gz`, stream decompression with Python's built-in `gzip` module into the
same temporary directory as the downloaded archive. Fully read the gzip stream,
including its integrity checks, and require nonempty extracted data before
publishing either file. Corrupt headers/deflate streams, invalid CRCs, and truncated
archives produce descriptive errors and clean up temporary files.

Both the original archive and extracted `.xes` remain under raw storage; the
returned path points to the extracted XES consumed by the unchanged pipeline.
Direct local inputs remain `.xes` and `.csv`. Compressed CSV and other archive
formats are unsupported.

## Publication & Failure Handling

Downloads and extraction are staged in a temporary directory under raw storage.
Without overwrite, hard-link publication refuses existing destination paths,
including files created after the initial existence check. With overwrite,
hard-link backups allow restoration if a later publication operation raises.
Failures remove newly published files or restore replaced files, then clean up
temporary data. Complete sources remain available if subsequent log preparation
fails.

Publication is atomic **per file**, not a transaction across a gzip/XES pair.
Rollback handles raised I/O errors; process termination can interrupt publication
between files. The downloader does not implement retries, resume, dataset
discovery, or general archive extraction.

Invalid URLs/names, transfer/protocol failures, and invalid gzip contents raise
descriptive `ValueError`s; an existing destination raises `FileExistsError`.
Other filesystem failures propagate as `OSError`. The CLI reports processing
failures with status 1, without a traceback or success summary; argument errors
use argparse's status 2.

## Provenance & Tests

Storage accepts optional `source_url` and records the supplied URL alongside the
existing local `source_file`, `source_sha256`, and checksum-based `source_id`.
Local-file preparation omits the URL field. This optional field retains version-1
sidecar compatibility; it does not replace local checksums.

For gzip downloads, the source filename and checksum describe the extracted XES
actually consumed by preparation. The original `.xes.gz` remains alongside it,
unchanged, and the URL still identifies the archive's remote source.

`tests/data/test_downloader.py` covers streaming, filenames, HTTP errors,
overwrite conflicts, failure cleanup, gzip integrity, and publication rollback.
`tests/test_prepare_event_log_download.py` exercises URL/XES/CSV/gzip preparation
and provenance through the CLI. HTTP responses are mocked, with small generated
gzip fixtures and temporary files; tests need no network access or GPU.
