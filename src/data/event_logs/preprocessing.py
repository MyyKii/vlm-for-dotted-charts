"""Explicit timestamp normalization and deterministic, non-mutating preparation."""

from numbers import Number
from zoneinfo import ZoneInfo

import pandas as pd

from data.event_logs.config import (
    ACTIVITY_COLUMN,
    CASE_ID_COLUMN,
    REQUIRED_COLUMNS,
    TIMESTAMP_COLUMN,
    EventLogConfig,
)

EVENT_ID_COLUMN = "identity:id"
SOURCE_ROW_COLUMN = "@@source_row"


def standardize_columns(frame: pd.DataFrame, config: EventLogConfig) -> pd.DataFrame:
    """Map required attributes without overwriting columns; accept mapped input."""
    if not frame.columns.is_unique:
        raise ValueError("Event-log column names must be unique")
    mapping = {}
    missing = []
    sources = (config.case_id_column, config.activity_column, config.timestamp_column)
    for source, target in zip(sources, REQUIRED_COLUMNS, strict=True):
        if source not in frame.columns:
            if target not in frame.columns:
                missing.append(source)
        elif source != target:
            if target in frame.columns:
                raise ValueError(
                    f"Column mapping {source!r} would overwrite existing column {target!r}"
                )
            mapping[source] = target
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    return frame.rename(columns=mapping)


def _timestamp_to_utc(value: object, row: object, config: EventLogConfig) -> pd.Timestamp:
    """Scalar fallback for mixed offsets and precise invalid-record errors."""
    try:
        if isinstance(value, Number):
            raise ValueError("numeric timestamps require an explicit textual date representation")
        timestamp = pd.to_datetime(value, format=config.timestamp_format or "ISO8601")
        if pd.isna(timestamp):
            raise ValueError("timestamp is missing or invalid")
        if timestamp.tzinfo is None:
            if config.source_timezone is None:
                raise ValueError("timezone-naive timestamp requires source_timezone")
            timestamp = timestamp.tz_localize(
                ZoneInfo(config.source_timezone), ambiguous="raise", nonexistent="raise"
            )
        return timestamp.tz_convert("UTC")
    except (ValueError, TypeError, OverflowError) as error:
        raise ValueError(f"Invalid {TIMESTAMP_COLUMN!r} at row {row!r}: {error}") from error


def _timestamps_to_utc(values: pd.Series, config: EventLogConfig) -> pd.Series:
    # Parse uniform timezones in bulk. Mixed offsets/awareness and invalid
    # records use the scalar path, which identifies the affected row.
    if not pd.api.types.is_numeric_dtype(values.dtype):
        try:
            parsed = pd.to_datetime(values, format=config.timestamp_format or "ISO8601")
            if not parsed.isna().any():
                if isinstance(parsed.dtype, pd.DatetimeTZDtype):
                    return parsed.dt.tz_convert("UTC")
                if pd.api.types.is_datetime64_dtype(parsed.dtype) and config.source_timezone:
                    return parsed.dt.tz_localize(
                        ZoneInfo(config.source_timezone), ambiguous="raise", nonexistent="raise"
                    ).dt.tz_convert("UTC")
        except (ValueError, TypeError, OverflowError):
            pass  # The scalar path below raises with the original row label.
    timestamps = [_timestamp_to_utc(value, row, config) for row, value in values.items()]
    return pd.Series(timestamps, index=values.index, dtype="datetime64[ns, UTC]", name=values.name)


def preprocess_event_log(frame: pd.DataFrame, config: EventLogConfig) -> pd.DataFrame:
    """Return standard attributes, UTC times, source order, and stable event IDs.

    Naive timestamps require an IANA ``source_timezone``. Ambiguous/nonexistent
    local times and invalid values raise; default text parsing is ISO 8601.
    Preserve supplied ``identity:id`` values. Otherwise derive ``source-row:N``
    IDs from zero-based input positions. These IDs are local to a source: use
    provenance ``source_sha256`` together with the event ID across logs.
    Retain positions in ``@@source_row`` across sorting and repeated processing.
    """
    processed = standardize_columns(frame, config)
    for column in (CASE_ID_COLUMN, ACTIVITY_COLUMN):
        processed[column] = processed[column].astype("string")
    processed[TIMESTAMP_COLUMN] = _timestamps_to_utc(processed[TIMESTAMP_COLUMN], config)

    if SOURCE_ROW_COLUMN not in processed.columns:
        processed[SOURCE_ROW_COLUMN] = range(len(processed))
    source_rows = processed[SOURCE_ROW_COLUMN]
    if (
        not pd.api.types.is_integer_dtype(source_rows.dtype)
        or source_rows.isna().any()
        or (source_rows < 0).any()
        or source_rows.duplicated().any()
    ):
        raise ValueError(f"{SOURCE_ROW_COLUMN!r} must contain unique nonnegative integer positions")
    if EVENT_ID_COLUMN not in processed.columns:
        processed[EVENT_ID_COLUMN] = "source-row:" + source_rows.astype("string")

    return processed.sort_values(
        [CASE_ID_COLUMN, TIMESTAMP_COLUMN, SOURCE_ROW_COLUMN], kind="stable"
    ).reset_index(drop=True)
