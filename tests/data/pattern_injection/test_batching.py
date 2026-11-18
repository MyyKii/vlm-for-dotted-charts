"""Deterministic order-preserving batches and explicitly limited composition."""

import json

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from data.pattern_injection.engine import (
    create_variant,
    load_variant,
    resolve_batch_target,
    save_variant,
)


def batch_recipe(*, ids=None, center="2026-01-01T09:00:00Z", jitter=0, count=2, seed=42):
    target = {}
    if ids is not None:
        target["event_ids"] = ids
    if center is not None:
        target["center_utc"] = center
    return {
        "preset": "batch_small",
        "parameters": {"num_events": count, "jitter_seconds": jitter},
        "target": target,
        "seed": seed,
    }


def gap():
    return {"preset": "gap_medium", "target": {"cutoff_utc": "2026-01-01T12:00:00Z"}}


def test_instant_batch_exact_updates(injection_source, injection_log):
    ids = ["event-0-Work", "event-1-Work"]
    events, manifest, changes = create_variant(injection_source, [batch_recipe(ids=ids)])
    expected = injection_log.copy()
    expected.loc[expected["identity:id"].isin(ids), "time:timestamp"] = pd.Timestamp(
        "2026-01-01T09:00:00Z"
    )
    assert_frame_equal(events, expected)
    injection = manifest["injections"][0]
    assert injection["selection"]["requested"]["event_ids"] == ids
    assert injection["selection"]["resolved"]["case_ids"] == ["case-0", "case-1"]
    assert injection["selection"]["resolved"]["activities"] == ["Work"]
    assert injection["target_regions"] == [
        {
            "region_id": "region_001",
            "coordinate_space": "final_event_log",
            "time_type": "instant",
            "timestamp_utc": "2026-01-01T09:00:00+00:00",
            "case_scope": {"type": "selected", "case_ids": ["case-0", "case-1"]},
            "activity_scope": ["Work"],
        }
    ]
    assert (
        changes["timestamp_before_utc"].tolist()
        == pd.to_datetime(["2026-01-01T10:00:00Z", "2026-01-01T11:00:00Z"]).tolist()
    )


def test_jitter_interval_includes_latest_event_and_reproduces(injection_source, tmp_path):
    recipe = [batch_recipe(ids=["event-0-Work", "event-1-Work"], jitter=30)]
    first = create_variant(injection_source, recipe)
    repeated = create_variant(injection_source, recipe)
    assert first[1] == repeated[1]
    assert_frame_equal(first[0], repeated[0])
    assert_frame_equal(first[2], repeated[2])
    injection = first[1]["injections"][0]
    region = injection["target_regions"][0]
    assert region["time_type"] == "interval"
    latest = first[2]["timestamp_after_utc"].max()
    assert pd.Timestamp(region["end_utc"]) == latest + pd.Timedelta(1, unit="ns")
    assert pd.Timestamp(region["start_utc"]) < pd.Timestamp(region["end_utc"])
    assert (first[2]["timestamp_after_utc"] >= pd.Timestamp("2026-01-01T08:59:30Z")).all()
    assert (first[2]["timestamp_after_utc"] <= pd.Timestamp("2026-01-01T09:00:30Z")).all()
    output = save_variant(*first, tmp_path / "results")
    assert_frame_equal(load_variant(output)[0], first[0])


def test_seeded_feasible_selection_and_distinct_cases(injection_source):
    entry = batch_recipe(center=None, count=4, jitter=20)
    entry["target"] = {"activities": ["Work"]}
    first = create_variant(injection_source, [entry], sample_cases=4, seed=7)
    second = create_variant(injection_source, [entry], sample_cases=4, seed=7)
    assert first[1] == second[1]
    resolved = first[1]["injections"][0]["selection"]["resolved"]
    assert len(resolved["event_ids"]) == len(resolved["case_ids"]) == 4
    assert (
        first[0]
        .groupby("case:concept:name")["time:timestamp"]
        .apply(lambda times: times.is_monotonic_increasing)
        .all()
    )


def test_large_infeasible_seeded_batch_avoids_repeated_table_scans(monkeypatch):
    case_count = 10_000
    frame = pd.DataFrame(
        {
            "case:concept:name": [f"case-{case}" for case in range(case_count) for _ in range(3)],
            "concept:name": ["Start", "Work", "End"] * case_count,
            "time:timestamp": pd.date_range(
                "2026-01-01", periods=3 * case_count, freq="s", tz="UTC"
            ),
            "identity:id": [f"event-{event}" for event in range(3 * case_count)],
            "@@source_row": range(3 * case_count),
        }
    )
    # Each eligible event has a disjoint predecessor/successor window. A batch
    # cannot span two cases, despite having many cases and candidate centers.
    original_clip = pd.Series.clip
    scans = 0

    def bounded_scans(series, *args, **kwargs):
        nonlocal scans
        scans += 1
        assert scans <= 2, "Batch selection repeated full-table scans for candidate centers"
        return original_clip(series, *args, **kwargs)

    monkeypatch.setattr(pd.Series, "clip", bounded_scans)
    with pytest.raises(ValueError, match="Infeasible batch"):
        resolve_batch_target(
            frame, {"activities": ["Work"]}, {"num_events": 25, "jitter_seconds": 0}, 42
        )


def test_automatic_center_selection_skips_noop_centers(injection_log):
    for seed in range(10):
        target = resolve_batch_target(
            injection_log, {"activities": ["Start"]}, {"num_events": 2, "jitter_seconds": 0}, seed
        )
        assert target == resolve_batch_target(
            injection_log, {"activities": ["Start"]}, {"num_events": 2, "jitter_seconds": 0}, seed
        )
        assert all(
            pd.Timestamp(timestamp) != pd.Timestamp("2026-01-01T08:00:00Z")
            for timestamp in target["resolved"]["assigned_timestamps_utc"].values()
        )


def test_automatic_event_selection_prefers_cases_that_can_change(injection_log):
    for seed in range(10):
        selected = resolve_batch_target(
            injection_log,
            {"activities": ["Work"], "center_utc": "2026-01-01T10:00:00Z"},
            {"num_events": 2, "jitter_seconds": 0},
            seed,
        )["resolved"]
        assert "event-0-Work" not in selected["event_ids"]


def test_automatic_event_selection_prefers_modifying_alternatives_within_case(injection_log):
    selected = resolve_batch_target(
        injection_log,
        {
            "case_ids": ["case-0", "case-1"],
            "activities": ["Start", "Work"],
            "center_utc": "2026-01-01T10:00:00Z",
        },
        {"num_events": 2, "jitter_seconds": 0},
        42,
    )["resolved"]
    assert "event-0-Start" in selected["event_ids"]
    assert "event-0-Work" not in selected["event_ids"]


def test_automatic_selection_retains_required_cases_with_forced_unchanged_events(injection_log):
    selected = resolve_batch_target(
        injection_log,
        {"activities": ["Work"], "center_utc": "2026-01-01T10:00:00Z"},
        {"num_events": 4, "jitter_seconds": 0},
        42,
    )["resolved"]
    assert len(selected["event_ids"]) == len(selected["case_ids"]) == 4
    assert selected["assigned_timestamps_utc"]["event-0-Work"] == "2026-01-01T10:00:00+00:00"


@pytest.mark.parametrize("seed", [0, 1, 2, 42])
def test_jitter_assignments_change_events_when_a_modifying_timestamp_is_feasible(
    injection_source, seed
):
    entry = batch_recipe(
        ids=["event-0-Start", "event-1-Start"],
        center="2026-01-01T08:00:00Z",
        jitter=1e-9,
        seed=seed,
    )
    _, _, changes = create_variant(injection_source, [entry])
    assert len(changes) == 2
    assert changes["timestamp_before_utc"].ne(changes["timestamp_after_utc"]).all()


def test_unchanged_selected_batch_events_have_no_change_rows(injection_source):
    entry = batch_recipe(ids=["event-0-Work", "event-1-Work"], center="2026-01-01T10:00:00Z")
    _, manifest, changes = create_variant(injection_source, [entry])
    assert manifest["injections"][0]["selection"]["resolved"]["event_ids"] == [
        "event-0-Work",
        "event-1-Work",
    ]
    assert changes["event_id"].tolist() == ["event-1-Work"]
    assert manifest["injections"][0]["affected"]["event_count"] == 1


@pytest.mark.parametrize(
    "entry",
    [
        batch_recipe(ids=["event-0-Start", "event-0-Work"]),
        batch_recipe(ids=["event-0-Work"]),
        batch_recipe(ids=["event-0-Work", "event-1-Work"], center="2026-01-01T07:00:00Z"),
        batch_recipe(ids=["event-0-Work", "event-1-Work"], center="2026-01-01T19:00:00Z"),
        batch_recipe(count=5),
        batch_recipe(jitter=-1),
    ],
)
def test_infeasible_batch_targets_fail(injection_source, entry):
    with pytest.raises(ValueError):
        create_variant(injection_source, [entry])


def test_requested_injection_with_no_changes_is_an_error(injection_source):
    entry = batch_recipe(ids=["event-0-Start", "event-1-Start"], center="2026-01-01T08:00:00Z")
    with pytest.raises(ValueError, match="changes no events"):
        create_variant(injection_source, [entry])


def test_batch_preserves_original_source_row_tie_order(injection_log):
    injection_log.loc[0:1, "@@source_row"] = [1, 0]
    injection_log.loc[3:4, "@@source_row"] = [4, 3]
    target = {
        "event_ids": ["event-0-Work", "event-1-Work"],
        "center_utc": "2026-01-01T08:00:00Z",
    }
    with pytest.raises(ValueError, match="Infeasible"):
        resolve_batch_target(injection_log, target, {"num_events": 2, "jitter_seconds": 0}, 42)
    resolved = resolve_batch_target(
        injection_log, target, {"num_events": 2, "jitter_seconds": 2}, 42
    )["resolved"]
    assert all(
        pd.Timestamp(timestamp) > pd.Timestamp("2026-01-01T08:00:00Z")
        for timestamp in resolved["assigned_timestamps_utc"].values()
    )


def test_disjoint_gap_then_batch_and_ordered_reconstruction(
    injection_source, injection_log, tmp_path
):
    entry = batch_recipe(ids=["event-0-Work", "event-1-Work"])
    events, manifest, changes = create_variant(injection_source, [gap(), entry])
    assert [injection["injection_id"] for injection in manifest["injections"]] == [
        "inj_001",
        "inj_002",
    ]
    assert [injection["order"] for injection in manifest["injections"]] == [1, 2]
    reconstructed = injection_log.set_index("identity:id").copy()
    for injection in manifest["injections"]:
        rows = changes.loc[changes["injection_id"].eq(injection["injection_id"])].set_index(
            "event_id"
        )
        assert (
            reconstructed.loc[rows.index, "time:timestamp"].tolist()
            == rows["timestamp_before_utc"].tolist()
        )
        reconstructed.loc[rows.index, "time:timestamp"] = rows["timestamp_after_utc"].array
        assert len(rows) == injection["affected"]["event_count"]
        assert rows["case_id_after"].nunique() == injection["affected"]["case_count"]
    assert_frame_equal(reconstructed, events.set_index("identity:id"))
    assert not changes["event_id"].duplicated().any()
    assert manifest["injections"][0]["target_regions"][0]["case_scope"] == {"type": "all"}
    output = save_variant(events, manifest, changes, tmp_path / "combined")
    assert len(load_variant(output)[1]["injections"]) == 2


def test_multiple_batch_instances_remain_separately_identifiable(injection_source):
    entries = [
        batch_recipe(ids=["event-0-Work", "event-1-Work"]),
        batch_recipe(ids=["event-2-Work", "event-3-Work"], center="2026-01-01T15:00:00Z"),
    ]
    _, manifest, changes = create_variant(injection_source, entries)
    assert len(manifest["injections"]) == 2
    assert set(changes["injection_id"]) == {"inj_001", "inj_002"}


@pytest.mark.parametrize(
    "entries",
    [
        [gap(), batch_recipe(ids=["event-2-Work", "event-3-Work"], center="2026-01-01T16:00:00Z")],
        [batch_recipe(ids=["event-0-Work", "event-1-Work"])] * 2,
    ],
)
def test_repeated_event_targets_fail_without_automatic_resolution(injection_source, entries):
    with pytest.raises(ValueError, match="Overlapping injections.*already changed"):
        create_variant(injection_source, entries)


def test_disjoint_edits_that_fill_earlier_gap_are_rejected(injection_source):
    entry = batch_recipe(ids=["event-0-Work", "event-1-Work"], center="2026-01-01T13:00:00Z")
    with pytest.raises(ValueError, match="invalidates an earlier gap region"):
        create_variant(injection_source, [gap(), entry])


def test_recipe_is_not_mutated(injection_source):
    recipe = [gap(), batch_recipe(ids=["event-0-Work", "event-1-Work"])]
    before = json.dumps(recipe, sort_keys=True)
    create_variant(injection_source, recipe)
    assert json.dumps(recipe, sort_keys=True) == before
