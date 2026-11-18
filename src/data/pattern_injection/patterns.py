"""Timestamp transformations; selection, validation, and persistence live in the engine."""

import pandas as pd

from data.event_logs.config import TIMESTAMP_COLUMN
from data.event_logs.preprocessing import EVENT_ID_COLUMN


def _assign_timestamps(result: pd.DataFrame, mask: pd.Series, values: pd.Series) -> None:
    """Preserve input resolution when possible; promote explicitly for finer jitter."""
    try:
        compatible = values.array.as_unit(result[TIMESTAMP_COLUMN].dtype.unit, round_ok=False)
    except ValueError:
        result[TIMESTAMP_COLUMN] = result[TIMESTAMP_COLUMN].dt.as_unit("ns")
        compatible = values.array.as_unit("ns")
    result.loc[mask, TIMESTAMP_COLUMN] = compatible


def shift_suffix(
    frame: pd.DataFrame, parameters: dict, selection: dict, seed: int
) -> tuple[pd.DataFrame, list[dict]]:
    """Shift every event at/after the resolved cut-off; preserve all other values."""
    cutoff = pd.Timestamp(selection["resolved"]["cutoff_utc"])
    try:
        duration = pd.Timedelta(parameters["duration_minutes"], unit="min")
        if duration <= pd.Timedelta(0):
            raise ValueError("duration_minutes must resolve to a positive duration")
        result = frame.copy()
        mask = result[TIMESTAMP_COLUMN].ge(cutoff)
        _assign_timestamps(result, mask, result.loc[mask, TIMESTAMP_COLUMN] + duration)
        end = cutoff + duration
    except (ValueError, OverflowError) as error:
        raise ValueError(f"Infeasible gap duration: {error}") from error
    return result, [
        {
            "region_id": "region_001",
            "coordinate_space": "final_event_log",
            "time_type": "interval",
            "start_utc": cutoff.isoformat(),
            "end_utc": end.isoformat(),
            "case_scope": {"type": "all"},
        }
    ]


def synchronize_events(
    frame: pd.DataFrame, parameters: dict, selection: dict, seed: int
) -> tuple[pd.DataFrame, list[dict]]:
    """Apply resolved order-preserving assignments, one eligible event per case."""
    resolved = selection["resolved"]
    assignments = {
        event_id: pd.Timestamp(timestamp)
        for event_id, timestamp in resolved["assigned_timestamps_utc"].items()
    }
    result = frame.copy()
    mask = result[EVENT_ID_COLUMN].isin(assignments)
    _assign_timestamps(result, mask, result.loc[mask, EVENT_ID_COLUMN].map(assignments))
    timestamps = list(assignments.values())
    start, latest = min(timestamps), max(timestamps)
    region = {
        "region_id": "region_001",
        "coordinate_space": "final_event_log",
        "case_scope": {"type": "selected", "case_ids": resolved["case_ids"]},
        "activity_scope": resolved["activities"],
    }
    if start == latest:
        region.update(time_type="instant", timestamp_utc=start.isoformat())
    else:
        try:
            end = latest + pd.Timedelta(1, unit="ns")
        except (ValueError, OverflowError) as error:
            raise ValueError("Batch region cannot include its latest timestamp") from error
        region.update(time_type="interval", start_utc=start.isoformat(), end_utc=end.isoformat())
    return result, [region]


STRATEGIES = {"shift_suffix": shift_suffix, "synchronize_events": synchronize_events}
