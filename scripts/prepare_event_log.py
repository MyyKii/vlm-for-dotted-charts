"""Prepare a local or HTTP(S) XES/CSV event log and export validated Parquet + JSON."""

import argparse
import sys
from pathlib import Path

from data.event_logs import EventLogConfig
from data.event_logs.config import ACTIVITY_COLUMN, CASE_ID_COLUMN, TIMESTAMP_COLUMN
from data.event_logs.downloader import download_event_log
from data.event_logs.loader import load_event_log
from data.event_logs.preprocessing import preprocess_event_log
from data.event_logs.storage import save_processed_event_log
from data.event_logs.validation import validate_event_log


def main(argv: list[str] | None = None) -> int:
    """Coordinate preparation; return a nonzero exit status for invalid inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="Local .xes or .csv source")
    source.add_argument("--url", help="HTTP(S) URL of an .xes or .csv source")
    parser.add_argument("--filename", help="Local filename for a URL download under data/raw/")
    parser.add_argument("--output", required=True, type=Path, help="Processed .parquet path")
    parser.add_argument("--format", choices=("xes", "csv"), help="Default: infer from input suffix")
    parser.add_argument("--case-id-column", default=CASE_ID_COLUMN)
    parser.add_argument("--activity-column", default=ACTIVITY_COLUMN)
    parser.add_argument("--timestamp-column", default=TIMESTAMP_COLUMN)
    parser.add_argument("--csv-separator", default=",")
    parser.add_argument("--timestamp-format", help="Pandas datetime format; default: ISO 8601")
    parser.add_argument("--source-timezone", help="IANA timezone required for naive timestamps")
    parser.add_argument("--dataset-id", help="Default: source filename stem")
    parser.add_argument("--split-group-id", help="Shared provenance group; default: dataset ID")
    parser.add_argument(
        "--overwrite", action="store_true", help="Replace existing download, output, and metadata"
    )
    args = parser.parse_args(argv)
    if args.filename is not None and args.url is None:
        parser.error("--filename requires --url")

    try:
        input_path = args.input
        if args.url is not None:
            input_path = download_event_log(
                args.url, filename=args.filename, overwrite=args.overwrite
            )
        config = EventLogConfig(
            input_path=input_path,
            file_format=args.format,
            case_id_column=args.case_id_column,
            activity_column=args.activity_column,
            timestamp_column=args.timestamp_column,
            csv_separator=args.csv_separator,
            timestamp_format=args.timestamp_format,
            source_timezone=args.source_timezone,
        )
        loaded = load_event_log(config)
        processed = preprocess_event_log(loaded, config)
        findings = validate_event_log(processed, expected_num_events=len(loaded))
        metadata = save_processed_event_log(
            processed,
            config,
            args.output,
            dataset_id=args.dataset_id,
            split_group_id=args.split_group_id,
            source_url=args.url,
            overwrite=args.overwrite,
        )
    except (OSError, ValueError, TypeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(f"Input: {config.input_path}")
    print(f"Events: {metadata['num_events']}")
    print(f"Cases: {metadata['num_cases']}")
    print(f"Activities: {metadata['num_activities']}")
    time_range = metadata["time_range"]
    print(f"Time range (UTC): {time_range['start']} to {time_range['end']}")
    print(f"Output: {args.output}")
    print(f"Metadata: {args.output.with_suffix('.json')}")
    for finding in findings:
        print(f"Diagnostic: {finding}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
