"""Catalog, stable-ID selection, UTC regions, and typed change contracts."""

import copy
import json

import pandas as pd
import pyarrow.parquet as pq
import pytest
from pandas.testing import assert_frame_equal

from data.pattern_injection.catalog import CATALOG_PATH, load_catalog, resolve_preset
from data.pattern_injection.engine import (
    CHANGE_SCHEMA,
    changes_frame,
    resolve_cutoff,
    select_complete_cases,
    select_target_events,
    utc_timestamp,
    validate_changes,
    validate_manifest,
    validate_regions,
)


def test_catalog_and_editable_presets(tmp_path):
    catalog = load_catalog()
    assert len(catalog["classes"]) == 6
    assert set(catalog["presets"]) == {"gap_medium", "batch_small"}
    modified = copy.deepcopy(catalog)
    modified["presets"]["gap_short"] = {
        "type": "temporal_gap",
        "strategy": "shift_suffix",
        "parameters": {"duration_minutes": 5},
    }
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(modified))
    assert resolve_preset(load_catalog(path), "gap_short")["parameters"] == {"duration_minutes": 5}
    assert resolve_preset(catalog, "gap_medium", {"duration_minutes": 1})["parameters"] == {
        "duration_minutes": 1
    }
    assert load_catalog() == catalog


@pytest.mark.parametrize(
    "preset",
    [
        {"type": "outlier", "strategy": "delay_case", "parameters": {}},
        {"type": "batching", "strategy": "shift_suffix", "parameters": {"duration_minutes": 5}},
        {"type": "temporal_gap", "strategy": "shift_suffix", "parameters": {"duration_minutes": 0}},
        {
            "type": "temporal_gap",
            "strategy": "shift_suffix",
            "parameters": {"duration_minutes": True},
        },
        {"type": "batching", "strategy": "synchronize_events", "parameters": {"num_events": 1}},
        {
            "type": "batching",
            "strategy": "synchronize_events",
            "parameters": {"num_events": 2.5, "jitter_seconds": 0},
        },
    ],
)
def test_invalid_catalog_presets(tmp_path, preset):
    catalog = json.loads(CATALOG_PATH.read_text())
    catalog["presets"]["bad"] = preset
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(catalog))
    with pytest.raises(ValueError):
        load_catalog(path)


def test_unknown_preset_and_parameters():
    with pytest.raises(ValueError, match="Unknown preset"):
        resolve_preset(load_catalog(), "outlier")
    with pytest.raises(ValueError, match="parameters"):
        resolve_preset(load_catalog(), "gap_medium", {"typo": 1})


@pytest.mark.parametrize("minimum", [1, 26, 2.0, True, None, "10"])
def test_batch_minimum_requires_an_integer_in_bounds(minimum):
    with pytest.raises(ValueError, match="min_events"):
        resolve_preset(load_catalog(), "batch_small", {"min_events": minimum})


def test_batch_minimum_defaults_to_overridden_target():
    catalog = load_catalog()
    assert resolve_preset(catalog, "batch_small")["parameters"]["min_events"] == 25
    resolved = resolve_preset(catalog, "batch_small", {"num_events": 3})["parameters"]
    assert resolved["min_events"] == resolved["num_events"] == 3
    assert "min_events" not in catalog["presets"]["batch_small"]["parameters"]


def test_explicit_preset_minimum_survives_target_override():
    catalog = load_catalog()
    catalog["presets"]["batch_small"]["parameters"]["min_events"] = 10
    resolved = resolve_preset(catalog, "batch_small", {"num_events": 18})["parameters"]
    assert resolved["num_events"] == 18
    assert resolved["min_events"] == 10


def test_reproducible_complete_case_selection(injection_log):
    before = injection_log.copy(deep=True)
    first, selection = select_complete_cases(injection_log, sample_cases=2, seed=7)
    second, repeated = select_complete_cases(injection_log, sample_cases=2, seed=7)
    assert_frame_equal(first, second)
    assert selection == repeated
    assert len(first) == 6
    assert first.groupby("case:concept:name").size().tolist() == [3, 3]
    assert sorted(first["case:concept:name"].unique()) == selection["resolved_case_ids"]
    explicit, _ = select_complete_cases(injection_log, case_ids=selection["resolved_case_ids"])
    assert_frame_equal(first, explicit)
    shuffled = injection_log.sample(frac=1, random_state=1)
    assert select_complete_cases(shuffled, sample_cases=2, seed=7)[1] == selection
    assert_frame_equal(before, injection_log)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sample_cases": 0},
        {"sample_cases": 5},
        {"sample_cases": True},
        {"sample_cases": 1, "case_ids": ["case-0"]},
        {"case_ids": ["missing"]},
        {"case_ids": []},
        {"seed": -1},
    ],
)
def test_invalid_baseline_selection(injection_log, kwargs):
    with pytest.raises(ValueError):
        select_complete_cases(injection_log, **kwargs)


def test_stable_target_selection_ignores_dataframe_indices(injection_log):
    injection_log.index = [100] * len(injection_log)
    target = {"case_ids": ["case-0", "case-1"], "activities": ["Work"]}
    selected = select_target_events(injection_log, target)
    assert selected["identity:id"].tolist() == ["event-0-Work", "event-1-Work"]
    assert resolve_cutoff(injection_log, {}, 42) == resolve_cutoff(injection_log, {}, 42)
    cutoff = resolve_cutoff(injection_log, {"cutoff_utc": "2026-01-01T12:00:00Z"}, 42)
    assert cutoff["requested"] == {"cutoff_utc": "2026-01-01T12:00:00Z"}
    assert "event-2-Work" in cutoff["resolved"]["event_ids"]


@pytest.mark.parametrize(
    "target",
    [
        {"event_ids": ["missing"]},
        {"case_ids": ["missing"]},
        {"start_utc": "2026-01-01T00:00:00Z"},
        {"start_utc": "2027-01-01T00:00:00Z", "end_utc": "2028-01-01T00:00:00Z"},
        {"event_ids": ["event-0-Start"], "activities": ["End"]},
    ],
)
def test_unresolvable_targets(injection_log, target):
    with pytest.raises(ValueError):
        select_target_events(injection_log, target)


@pytest.mark.parametrize("value", ["2026-01-01", "NaT", 123, "2026-01-01T12:00:00+02:00"])
def test_target_times_require_explicit_utc(value):
    with pytest.raises(ValueError, match="UTC"):
        utc_timestamp(value, "target")


def regions():
    return [
        {
            "region_id": "region_001",
            "coordinate_space": "final_event_log",
            "time_type": "interval",
            "start_utc": "2026-01-01T12:00:00Z",
            "end_utc": "2026-01-01T14:00:00Z",
            "case_scope": {"type": "all"},
        },
        {
            "region_id": "region_002",
            "coordinate_space": "final_event_log",
            "time_type": "instant",
            "timestamp_utc": "2026-01-01T16:00:00Z",
            "case_scope": {"type": "selected", "case_ids": ["case-0"]},
            "activity_scope": ["Work"],
        },
    ]


def test_multiple_regions_and_control_contract(control_manifest):
    validate_regions(regions())
    validate_manifest(control_manifest)
    validate_changes(changes_frame(), control_manifest)


@pytest.mark.parametrize(
    "update",
    [
        {"end_utc": "2026-01-01T12:00:00Z"},
        {"timestamp_utc": "2026-01-01T12:00:00Z"},
        {"coordinate_space": "image"},
        {"case_scope": {}},
        {"case_scope": {"type": "selected", "case_ids": []}},
    ],
)
def test_invalid_region(update):
    region = regions()[0] | update
    with pytest.raises(ValueError):
        validate_regions([region])


@pytest.mark.parametrize("empty", [True, False])
def test_fixed_change_schema_round_trip(tmp_path, empty):
    rows = (
        []
        if empty
        else [
            {
                "injection_id": "inj_001",
                "event_id": "event-0-Work",
                "change_type": "updated",
                "case_id_before": "case-0",
                "case_id_after": "case-0",
                "timestamp_before_utc": pd.Timestamp("2026-01-01T10:00:00.123456789Z"),
                "timestamp_after_utc": pd.Timestamp("2026-01-01T12:00:00.123456789Z"),
            }
        ]
    )
    changes = changes_frame(rows)
    path = tmp_path / "changes.parquet"
    import pyarrow as pa

    pq.write_table(pa.Table.from_pandas(changes, schema=CHANGE_SCHEMA, preserve_index=False), path)
    assert pq.read_schema(path).equals(CHANGE_SCHEMA, check_metadata=False)
    assert_frame_equal(changes, pd.read_parquet(path))


def test_future_additions_and_removals_fit_the_schema():
    table = changes_frame(
        [
            {
                "injection_id": "inj_001",
                "event_id": "new-event",
                "change_type": "added",
                "case_id_after": "new-case",
                "timestamp_after_utc": pd.Timestamp("2026-01-01T10:00:00Z"),
                "derived_from_event_id": "old-event",
                "after_values_json": '{"concept:name":"Work","@@source_row":100}',
            },
            {
                "injection_id": "inj_001",
                "event_id": "old-event",
                "change_type": "removed",
                "case_id_before": "old-case",
                "timestamp_before_utc": pd.Timestamp("2026-01-01T10:00:00Z"),
                "before_values_json": '{"concept:name":"Work","@@source_row":0}',
            },
        ]
    )
    manifest = {
        "injections": [{"injection_id": "inj_001", "affected": {"event_count": 2, "case_count": 2}}]
    }
    validate_changes(table, manifest)
