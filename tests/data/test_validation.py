"""Schema, required values, counts, and non-destructive diagnostics."""

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from data.event_logs.config import REQUIRED_COLUMNS
from data.event_logs.validation import validate_event_log


@pytest.fixture
def valid_log():
    return pd.DataFrame(
        {
            "case:concept:name": ["a", "a", "b"],
            "concept:name": ["Start", "End", "Start"],
            "time:timestamp": pd.to_datetime(
                ["2026-01-01T12:00:00Z", "2026-01-01T13:00:00Z", "2026-01-02T12:00:00Z"]
            ),
        }
    )


def test_valid_log(valid_log):
    assert validate_event_log(valid_log, expected_num_events=3) == []


@pytest.mark.parametrize("column", REQUIRED_COLUMNS)
def test_missing_columns(valid_log, column):
    with pytest.raises(ValueError, match=f"Missing required columns.*{column}"):
        validate_event_log(valid_log.drop(columns=column))


@pytest.mark.parametrize("column", ["case:concept:name", "concept:name"])
@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_identifiers(valid_log, column, value):
    valid_log.loc[1, column] = value
    with pytest.raises(ValueError, match=f"{column!r}.*rows.*1"):
        validate_event_log(valid_log)


@pytest.mark.parametrize(
    "values",
    [
        ["invalid"] * 3,
        pd.to_datetime(["2026-01-01"] * 3),
        pd.date_range("2026-01-01", periods=3, tz="Europe/Berlin"),
    ],
)
def test_invalid_timestamp_dtype(valid_log, values):
    valid_log["time:timestamp"] = values
    with pytest.raises(ValueError, match="time:timestamp.*UTC timestamps"):
        validate_event_log(valid_log)


def test_missing_timestamp(valid_log):
    valid_log.loc[1, "time:timestamp"] = pd.NaT
    with pytest.raises(ValueError, match="time:timestamp.*rows.*1"):
        validate_event_log(valid_log)


def test_empty_log(valid_log):
    with pytest.raises(ValueError, match="empty.*at least one valid case"):
        validate_event_log(valid_log.iloc[:0])


def test_event_count_change(valid_log):
    with pytest.raises(ValueError, match="Event count changed: expected 4, got 3"):
        validate_event_log(valid_log, expected_num_events=4)


def test_duplicates_are_diagnostic(valid_log):
    duplicated = pd.concat([valid_log, valid_log.iloc[[0]]], ignore_index=True)
    before = duplicated.copy(deep=True)

    findings = validate_event_log(duplicated, expected_num_events=4)

    assert findings == ["Duplicate case/activity/timestamp combinations: 1"]
    assert_frame_equal(duplicated, before)


def test_identical_timestamps_are_diagnostic(valid_log):
    valid_log["time:timestamp"] = valid_log["time:timestamp"].iloc[0]
    assert "All events share the same timestamp" in validate_event_log(valid_log)


@pytest.mark.parametrize("ids", [["e", "e", "f"], ["e", None, "f"], ["e", " ", "f"]])
def test_invalid_event_ids(valid_log, ids):
    valid_log["identity:id"] = ids
    with pytest.raises(ValueError, match="identity:id.*rows"):
        validate_event_log(valid_log)


@pytest.mark.parametrize("positions", [[0, 0, 1], [-1, 0, 1], [0.0, 1.0, 2.0], [0, None, 2]])
def test_invalid_source_positions(valid_log, positions):
    valid_log["@@source_row"] = positions
    with pytest.raises(ValueError, match="@@source_row"):
        validate_event_log(valid_log)
