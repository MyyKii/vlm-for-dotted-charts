"""Integrity validation and non-destructive diagnostics for standardized logs."""

import pandas as pd

from data.event_logs.config import (
    ACTIVITY_COLUMN,
    CASE_ID_COLUMN,
    REQUIRED_COLUMNS,
    TIMESTAMP_COLUMN,
)
from data.event_logs.preprocessing import EVENT_ID_COLUMN, SOURCE_ROW_COLUMN


def validate_event_log(frame: pd.DataFrame, *, expected_num_events: int | None = None) -> list[str]:
    """Raise for invalid data and return diagnostic findings without modifying it.

    Require nonempty string case/activity labels and timezone-aware UTC times.
    Check source order and event identity when present. Duplicate combinations
    of case, activity, and timestamp are reported, never removed. Chronological
    ordering alone makes no claim about the semantic validity of a process.
    """
    if not frame.columns.is_unique:
        raise ValueError("Event-log column names must be unique")
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    if frame.empty:
        raise ValueError("Event log is empty; at least one valid case is required")
    if expected_num_events is not None and len(frame) != expected_num_events:
        raise ValueError(f"Event count changed: expected {expected_num_events}, got {len(frame)}")

    for column in REQUIRED_COLUMNS:
        invalid = frame[column].isna()
        if column != TIMESTAMP_COLUMN:
            invalid |= frame[column].astype("string").str.strip().eq("").fillna(True)
        if invalid.any():
            raise ValueError(
                f"Missing or empty values in {column!r} at rows {frame.index[invalid].tolist()[:5]}"
            )
    for column in (CASE_ID_COLUMN, ACTIVITY_COLUMN):
        if not pd.api.types.is_string_dtype(frame[column]):
            raise ValueError(f"{column!r} must contain string values")
    timestamps = frame[TIMESTAMP_COLUMN]
    if not isinstance(timestamps.dtype, pd.DatetimeTZDtype) or str(timestamps.dt.tz) != "UTC":
        raise ValueError(f"{TIMESTAMP_COLUMN!r} must contain valid timezone-aware UTC timestamps")

    if EVENT_ID_COLUMN in frame.columns:
        event_ids = frame[EVENT_ID_COLUMN]
        invalid = event_ids.isna() | event_ids.astype("string").str.strip().eq("").fillna(True)
        invalid |= event_ids.duplicated(keep=False)
        if invalid.any():
            raise ValueError(
                f"Missing or duplicate {EVENT_ID_COLUMN!r} "
                f"at rows {frame.index[invalid].tolist()[:5]}"
            )
    if SOURCE_ROW_COLUMN in frame.columns:
        positions = frame[SOURCE_ROW_COLUMN]
        if (
            not pd.api.types.is_integer_dtype(positions.dtype)
            or positions.isna().any()
            or (positions < 0).any()
            or positions.duplicated().any()
        ):
            raise ValueError(
                f"{SOURCE_ROW_COLUMN!r} must contain unique nonnegative integer positions"
            )

    findings = []
    duplicate_count = int(frame.duplicated(subset=list(REQUIRED_COLUMNS)).sum())
    if duplicate_count:
        findings.append(f"Duplicate case/activity/timestamp combinations: {duplicate_count}")
    if timestamps.nunique() == 1:
        findings.append("All events share the same timestamp")
    return findings
