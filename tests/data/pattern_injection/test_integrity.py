"""Persisted schema/reference integrity and effective-configuration reproducibility."""

import copy
import hashlib
import json
import random

import pandas as pd
import pyarrow.parquet as pq
import pytest
from pandas.testing import assert_frame_equal

from data.pattern_injection.catalog import load_catalog, resolve_preset
from data.pattern_injection.engine import (
    create_variant,
    load_variant,
    save_variant,
    validate_variant,
)


@pytest.fixture
def gap_variant(injection_source):
    return create_variant(
        injection_source,
        [{"preset": "gap_medium", "target": {"cutoff_utc": "2026-01-01T12:00:00Z"}}],
    )


@pytest.mark.parametrize(
    "path,value",
    [
        (["schema_version"], True),
        (["schema_version"], 2),
        (["event_count_before"], 13),
        (["event_count_after"], 13),
        (["event_changes_file"], "../changes.parquet"),
        (["source", "processed_sha256"], "invented"),
        (["source", "selection", "resolved_case_ids"], ["missing"]),
        (["injections", 0, "order"], 2),
        (["injections", 0, "pattern_type"], "outlier"),
        (["injections", 0, "strategy"], "delay_case"),
        (["injections", 0, "affected", "event_count"], 7),
        (["injections", 0, "affected", "case_count"], 3),
        (["injections", 0, "affected", "change_filter"], {"injection_id": "other"}),
        (["injections", 0, "selection", "requested"], None),
        (["injections", 0, "selection", "resolved", "event_ids"], ["event-0-Start"]),
        (["injections", 0, "selection", "resolved", "case_ids"], ["case-0"]),
        (["injections", 0, "target_regions", 0, "end_utc"], "2026-01-01T15:00:00Z"),
        (
            ["injections", 0, "target_regions", 0, "case_scope"],
            {"type": "selected", "case_ids": ["case-0"]},
        ),
    ],
)
def test_inconsistent_manifest_is_rejected(gap_variant, path, value):
    events, manifest, changes = gap_variant
    manifest = copy.deepcopy(manifest)
    current = manifest
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value
    with pytest.raises(ValueError):
        validate_variant(events, manifest, changes)


@pytest.mark.parametrize(
    "column,value",
    [
        ("injection_id", "missing"),
        ("event_id", "missing"),
        ("case_id_before", "wrong-case"),
        ("case_id_after", "wrong-case"),
        ("timestamp_before_utc", pd.NaT),
        ("timestamp_after_utc", pd.NaT),
        ("before_values_json", '{"concept:name":"unexpected"}'),
    ],
)
def test_inconsistent_change_records_are_rejected(gap_variant, column, value):
    events, manifest, changes = gap_variant
    changes = changes.copy()
    changes.loc[0, column] = value
    with pytest.raises(ValueError):
        validate_variant(events, manifest, changes)


def test_control_rejects_unlinked_change_rows(injection_source, gap_variant):
    events, manifest, _ = create_variant(injection_source, [])
    with pytest.raises(ValueError, match="unknown injection_id"):
        validate_variant(events, manifest, gap_variant[2])


def test_reload_detects_manifest_count_corruption(gap_variant, tmp_path):
    output = save_variant(*gap_variant, tmp_path / "results")
    path = output / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["injections"][0]["affected"]["event_count"] += 1
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Affected counts"):
        load_variant(output)


def test_reload_rejects_extra_phase_one_sidecar(gap_variant, tmp_path):
    output = save_variant(*gap_variant, tmp_path / "results")
    (output / "events.json").write_text("{}")
    with pytest.raises(ValueError, match="exactly"):
        load_variant(output)


def test_multiple_candidate_regions_round_trip(injection_source, tmp_path):
    events, manifest, changes = create_variant(
        injection_source,
        [
            {
                "preset": "batch_small",
                "parameters": {"num_events": 2, "jitter_seconds": 30},
                "target": {
                    "event_ids": ["event-0-Work", "event-1-Work"],
                    "center_utc": "2026-01-01T09:00:00Z",
                },
            }
        ],
    )
    injection = manifest["injections"][0]
    selected = events.set_index("identity:id").loc[injection["selection"]["resolved"]["event_ids"]]
    injection["target_regions"] = [
        {
            "region_id": f"region_{number:03d}",
            "coordinate_space": "final_event_log",
            "time_type": "instant",
            "timestamp_utc": row["time:timestamp"].isoformat(),
            "case_scope": {"type": "selected", "case_ids": [row["case:concept:name"]]},
            "activity_scope": [row["concept:name"]],
        }
        for number, (_, row) in enumerate(selected.iterrows(), 1)
    ]
    output = save_variant(events, manifest, changes, tmp_path / "regions")
    assert load_variant(output)[1]["injections"][0]["target_regions"] == injection["target_regions"]


def test_unsupported_attributes_fail_before_publication(injection_source, tmp_path):
    events, manifest, changes = create_variant(injection_source, [])
    events["unsupported"] = [object()] * len(events)
    root = tmp_path / "failed"
    with pytest.raises(ValueError, match="Parquet cannot preserve"):
        save_variant(events, manifest, changes, root)
    assert not root.exists()


@pytest.mark.parametrize("control", [False, True])
@pytest.mark.parametrize(
    "column,value",
    [
        ("time:timestamp", pd.Timestamp("2026-01-01T08:01:00Z")),
        ("concept:name", "Unrecorded activity"),
        ("org:resource", "Unrecorded resource"),
        ("nullable_int", 999),
    ],
)
def test_save_rejects_unrecorded_changes(injection_source, tmp_path, control, column, value):
    recipe = (
        []
        if control
        else [{"preset": "gap_medium", "target": {"cutoff_utc": "2026-01-01T12:00:00Z"}}]
    )
    events, manifest, changes = create_variant(injection_source, recipe, sample_cases=2)
    events.loc[0, column] = value  # This event is outside the gap's recorded changes.
    root = tmp_path / "mutated"
    with pytest.raises(ValueError, match="selected baseline"):
        save_variant(events, manifest, changes, root)
    assert not root.exists()


@pytest.mark.parametrize("control", [False, True])
@pytest.mark.parametrize(
    "column,value",
    [
        ("time:timestamp", pd.Timestamp("2026-01-01T08:01:00Z")),
        ("org:resource", "Unrecorded resource"),
        ("concept:name", "Unrecorded activity"),
        ("nullable_int", 999),
    ],
)
def test_reload_rejects_unrecorded_changes_even_with_updated_file_hash(
    injection_source, tmp_path, control, column, value
):
    recipe = (
        []
        if control
        else [{"preset": "gap_medium", "target": {"cutoff_utc": "2026-01-01T12:00:00Z"}}]
    )
    output = save_variant(
        *create_variant(injection_source, recipe, sample_cases=2), tmp_path / "results"
    )
    path = output / "events.parquet"
    events = pd.read_parquet(path)
    events.loc[0, column] = value
    events.to_parquet(path, index=False)
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"][path.name] = {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "schema": [
            {"name": field.name, "type": str(field.type), "nullable": field.nullable}
            for field in pq.read_schema(path)
        ],
    }
    manifest_path.write_text(json.dumps(manifest))
    injection_source.unlink()
    injection_source.with_suffix(".json").unlink()
    with pytest.raises(ValueError, match="selected baseline"):
        load_variant(output)


def test_save_and_load_require_baseline_content_digest(injection_source, tmp_path):
    events, manifest, changes = create_variant(injection_source, [])
    del manifest["source"]["selected_baseline_sha256"]
    with pytest.raises(ValueError, match="regenerate"):
        save_variant(events, manifest, changes, tmp_path / "rejected")
    output = save_variant(*create_variant(injection_source, []), tmp_path / "results")
    manifest_path = output / "manifest.json"
    stored = json.loads(manifest_path.read_text())
    del stored["source"]["selected_baseline_sha256"]
    manifest_path.write_text(json.dumps(stored))
    with pytest.raises(ValueError, match="regenerate"):
        load_variant(output)


def test_complete_baseline_round_trip_with_typed_attributes_and_precision(
    injection_source, tmp_path
):
    events, manifest, changes = create_variant(
        injection_source,
        [{"preset": "batch_small", "parameters": {"num_events": 2, "jitter_seconds": 30}}],
        sample_cases=3,
    )
    assert events["time:timestamp"].dtype.unit == "ns"
    events = events.sample(frac=1, random_state=7).reset_index(drop=True)
    output = save_variant(events, manifest, changes, tmp_path / "results")
    assert_frame_equal(load_variant(output)[0], events)


def test_legacy_batch_can_reload_with_an_unchanged_resolved_event(injection_source, tmp_path):
    center = "2026-01-01T10:00:00+00:00"
    events, manifest, changes = create_variant(
        injection_source,
        [
            {
                "preset": "batch_small",
                "parameters": {"num_events": 2, "jitter_seconds": 0},
                "target": {"event_ids": ["event-1-Work", "event-2-Work"], "center_utc": center},
            }
        ],
    )
    batch = manifest["injections"][0]
    batch["parameters"] = {"num_events": 3, "jitter_seconds": 0}
    selection = batch["selection"]
    selection["requested"]["event_ids"].insert(0, "event-0-Work")
    selection["resolved"]["event_ids"].insert(0, "event-0-Work")
    selection["resolved"]["case_ids"].insert(0, "case-0")
    selection["resolved"]["assigned_timestamps_utc"]["event-0-Work"] = center
    batch["target_regions"][0]["case_scope"]["case_ids"] = selection["resolved"]["case_ids"]

    output = save_variant(events, manifest, changes, tmp_path / "legacy")
    reloaded, stored, reloaded_changes = load_variant(output)
    assert_frame_equal(reloaded, events)
    assert_frame_equal(reloaded_changes, changes)
    assert "min_events" not in stored["injections"][0]["parameters"]

    stored["injections"][0]["parameters"]["min_events"] = 2
    (output / "manifest.json").write_text(json.dumps(stored))
    with pytest.raises(
        ValueError, match="Resolved target event IDs do not agree with change records"
    ):
        load_variant(output)


def test_saved_interval_bounds_automatic_center_for_new_batches(injection_source, tmp_path):
    end = "2026-01-01T11:30:00Z"
    output = save_variant(
        *create_variant(
            injection_source,
            [
                {
                    "preset": "batch_small",
                    "parameters": {"num_events": 2, "jitter_seconds": 0},
                    "target": {
                        "activities": ["Work"],
                        "start_utc": "2026-01-01T10:00:00Z",
                        "end_utc": end,
                        "center_utc": end,
                    },
                }
            ],
        ),
        tmp_path / "center",
    )
    _, stored, _ = load_variant(output)
    batch = stored["injections"][0]
    assert pd.Timestamp(batch["selection"]["resolved"]["center_utc"]) == pd.Timestamp(end)
    path = output / "manifest.json"
    del batch["selection"]["requested"]["center_utc"]
    path.write_text(json.dumps(stored))
    with pytest.raises(ValueError, match="Automatic batch center must satisfy"):
        load_variant(output)

    del batch["parameters"]["min_events"]
    path.write_text(json.dumps(stored))
    assert load_variant(output)[1] == stored


def test_optional_original_provenance_is_not_invented(injection_source):
    path = injection_source.with_suffix(".json")
    metadata = json.loads(path.read_text())
    for key in ("source_sha256", "source_id", "source_file", "source_url", "processing_config"):
        metadata.pop(key, None)
    path.write_text(json.dumps(metadata))
    _, manifest, _ = create_variant(injection_source, [])
    assert "source_sha256" not in manifest["source"]
    assert "source_id" not in manifest["source"]
    assert "source_url" not in manifest["source"]
    assert manifest["source"]["processed_sha256"] == metadata["processed_sha256"]


def test_equivalent_effective_settings_have_identical_ids(injection_source):
    first = create_variant(
        injection_source,
        [{"preset": "gap_medium", "target": {"cutoff_utc": "2026-01-01T12:00:00Z"}}],
    )
    second = create_variant(
        injection_source,
        [
            {
                "preset": "gap_medium",
                "parameters": {"duration_minutes": 120.0},
                "target": {"cutoff_utc": "2026-01-01T12:00:00+00:00"},
            }
        ],
    )
    assert first[1]["variant_id"] == second[1]["variant_id"]
    assert_frame_equal(first[0], second[0])
    assert_frame_equal(first[2], second[2])


def test_random_state_is_not_mutated(injection_source):
    state = random.getstate()
    create_variant(
        injection_source,
        [{"preset": "batch_small", "parameters": {"num_events": 3}}],
        sample_cases=3,
        seed=7,
    )
    assert random.getstate() == state


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 10**1000, True])
def test_nonfinite_or_invalid_parameters_fail_clearly(value):
    with pytest.raises(ValueError, match="finite"):
        resolve_preset(load_catalog(), "gap_medium", {"duration_minutes": value})


def test_fractional_gap_preserves_nanoseconds(injection_source):
    _, _, changes = create_variant(
        injection_source, [{"preset": "gap_medium", "parameters": {"duration_minutes": 1e-8}}]
    )
    assert (
        (changes["timestamp_after_utc"] - changes["timestamp_before_utc"])
        .eq(pd.Timedelta(600, unit="ns"))
        .all()
    )
