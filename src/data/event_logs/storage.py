"""Validated Parquet storage with deterministic JSON provenance."""

import hashlib
import json
import os
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pandas.testing import assert_frame_equal

from data.event_logs.config import ACTIVITY_COLUMN, CASE_ID_COLUMN, TIMESTAMP_COLUMN, EventLogConfig
from data.event_logs.preprocessing import EVENT_ID_COLUMN, SOURCE_ROW_COLUMN
from data.event_logs.validation import validate_event_log

STORAGE_VERSION = 1


def _sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _schema(path: Path) -> list[dict[str, object]]:
    return [
        {"name": field.name, "type": str(field.type), "nullable": field.nullable}
        for field in pq.read_schema(path)
    ]


def _summary(frame: pd.DataFrame) -> dict[str, object]:
    return {
        "num_events": len(frame),
        "num_cases": int(frame[CASE_ID_COLUMN].nunique()),
        "num_activities": int(frame[ACTIVITY_COLUMN].nunique()),
        "time_range": {
            "start": frame[TIMESTAMP_COLUMN].min().isoformat(),
            "end": frame[TIMESTAMP_COLUMN].max().isoformat(),
        },
    }


def _validate_stored_log(frame: pd.DataFrame, expected_num_events: int) -> list[str]:
    findings = validate_event_log(frame, expected_num_events=expected_num_events)
    for column in (EVENT_ID_COLUMN, SOURCE_ROW_COLUMN):
        if column not in frame.columns:
            raise ValueError(
                f"Processed storage requires {column!r}; preprocess the event log first"
            )
    return findings


def save_processed_event_log(
    frame: pd.DataFrame,
    config: EventLogConfig,
    output_path: Path | str,
    *,
    dataset_id: str | None = None,
    split_group_id: str | None = None,
    source_url: str | None = None,
    overwrite: bool = False,
) -> dict[str, object]:
    """Write a Parquet log and same-stem JSON sidecar; return its metadata.

    Validate a complete round trip before publishing either file. Preserve flat
    optional attributes and reject conversions that change values or dtypes.
    Source-local event IDs are scoped by the source checksum. Group IDs default
    to the dataset ID; callers can group related extracts explicitly. No split
    assignment occurs here. Existing files require ``overwrite=True``. Optional
    ``source_url`` records download provenance alongside the local file checksum.
    """
    findings = _validate_stored_log(frame, len(frame))
    source = Path(config.input_path)
    output = Path(output_path)
    metadata_path = output.with_suffix(".json")
    if output.suffix != ".parquet":
        raise ValueError("Processed output must use the .parquet extension")
    if source.resolve() in {output.resolve(), metadata_path.resolve()}:
        raise ValueError("Output must not overwrite the source event log")
    for path in (output, metadata_path):
        if path.exists() and not overwrite:
            raise FileExistsError(f"Output already exists: {path}; explicitly allow overwrite")
    dataset_id = source.stem if dataset_id is None else dataset_id
    split_group_id = dataset_id if split_group_id is None else split_group_id
    for name, value in (("dataset_id", dataset_id), ("split_group_id", split_group_id)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a nonempty string")
    checksum = _sha256(source)
    processing_config = asdict(config)
    processing_config["input_path"] = str(source)
    processing_config["timestamp_format"] = config.timestamp_format or "ISO8601"

    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=f".{output.stem}-", dir=output.parent) as directory:
        staged_output = Path(directory) / output.name
        staged_metadata = Path(directory) / metadata_path.name
        try:
            frame.to_parquet(staged_output, engine="pyarrow", index=False)
            reloaded = pd.read_parquet(staged_output, engine="pyarrow")
            _validate_stored_log(reloaded, len(frame))
            assert_frame_equal(frame.reset_index(drop=True), reloaded, check_exact=True)
        except (pa.ArrowException, AssertionError, TypeError) as error:
            raise ValueError(
                "Parquet cannot preserve this event-log schema; use supported scalar attributes: "
                f"{error}"
            ) from error
        metadata = {
            "storage_version": STORAGE_VERSION,
            "storage_format": "parquet",
            "schema": _schema(staged_output),
            "source_file": source.name,
            "source_sha256": checksum,
            "source_id": f"sha256:{checksum}",
            "dataset_id": dataset_id,
            "split_group_id": split_group_id,
            "processed_file": output.name,
            "processed_sha256": _sha256(staged_output),
            **_summary(frame),
            "processing_config": processing_config,
            "transformations": [
                "standardize_required_columns",
                "normalize_timestamps_to_UTC",
                "preserve_or_derive_source_local_event_ids",
                "sort_by_case_timestamp_source_row",
            ],
            "event_id_column": EVENT_ID_COLUMN,
            "source_row_column": SOURCE_ROW_COLUMN,
            "diagnostics": findings,
            "pm4py_version": version("pm4py"),
            "pandas_version": pd.__version__,
            "pyarrow_version": pa.__version__,
        }
        if source_url is not None:
            metadata["source_url"] = source_url
        staged_metadata.write_text(
            json.dumps(metadata, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
            + "\n",
            encoding="utf-8",
        )
        if overwrite:
            staged_output.replace(output)
            staged_metadata.replace(metadata_path)
        else:
            # Linking within the same filesystem publishes complete files and
            # atomically refuses existing paths, including concurrent writers.
            os.link(staged_output, output)
            try:
                os.link(staged_metadata, metadata_path)
            except OSError:
                output.unlink()  # Roll back only the file created above.
                raise
    return metadata


def load_processed_event_log(input_path: Path | str) -> pd.DataFrame:
    """Reload a saved log and verify its sidecar, checksum, schema, and counts.

    The original source need not remain available. Both the Parquet file and its
    same-stem JSON metadata are required; unsupported storage versions fail.
    """
    path = Path(input_path)
    metadata_path = path.with_suffix(".json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict) or metadata.get("storage_version") != STORAGE_VERSION:
        raise ValueError("Unsupported or missing event-log storage_version")
    if metadata.get("storage_format") != "parquet" or metadata.get("processed_file") != path.name:
        raise ValueError("Metadata does not describe this Parquet file")
    if metadata.get("processed_sha256") != _sha256(path):
        raise ValueError("Processed event-log checksum does not match metadata")
    if metadata.get("schema") != _schema(path):
        raise ValueError("Processed event-log schema does not match metadata")
    frame = pd.read_parquet(path, engine="pyarrow")
    if not isinstance(metadata.get("num_events"), int):
        raise ValueError("Metadata must include an integer num_events")
    _validate_stored_log(frame, metadata["num_events"])
    for key, value in _summary(frame).items():
        if metadata.get(key) != value:
            raise ValueError(f"Processed event-log {key} does not match metadata")
    return frame
