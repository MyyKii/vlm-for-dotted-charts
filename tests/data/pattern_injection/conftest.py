"""Small typed complete-case logs for offline Phase-2 checks."""

import pandas as pd
import pytest

from data.event_logs import EventLogConfig
from data.event_logs.preprocessing import preprocess_event_log
from data.event_logs.storage import save_processed_event_log


@pytest.fixture
def injection_log():
    rows = [
        {
            "case:concept:name": f"case-{case}",
            "concept:name": activity,
            "time:timestamp": f"2026-01-01T{hour:02}:00:00Z",
            "identity:id": f"event-{case}-{activity}",
            "org:resource": f"resource-{case}",
        }
        for case in range(4)
        for hour, activity in ((8, "Start"), (10 + case, "Work"), (18, "End"))
    ]
    frame = preprocess_event_log(pd.DataFrame(rows), EventLogConfig("fixture.csv"))
    frame["nullable_int"] = pd.Series([None, 2, 3] * 4, dtype="Int64")
    return frame


@pytest.fixture
def control_manifest():
    return {
        "schema_version": 1,
        "variant_id": "control_abc",
        "dataset_id": "fixture",
        "split_group_id": "fixture-family",
        "source": {
            "processed_path": "fixture.parquet",
            "processed_sha256": "0" * 64,
            "selected_baseline_sha256": "0" * 64,
            "selection": {
                "method": "all_complete_cases",
                "resolved_case_ids": [f"case-{case}" for case in range(4)],
            },
        },
        "event_changes_file": "changes.parquet",
        "event_count_before": 12,
        "event_count_after": 12,
        "injections": [],
    }


@pytest.fixture
def injection_source(injection_log, tmp_path):
    raw = tmp_path / "fixture.csv"
    injection_log.to_csv(raw, index=False)
    path = tmp_path / "fixture.parquet"
    save_processed_event_log(
        injection_log,
        EventLogConfig(raw),
        path,
        dataset_id="fixture",
        split_group_id="fixture-family",
    )
    return path
