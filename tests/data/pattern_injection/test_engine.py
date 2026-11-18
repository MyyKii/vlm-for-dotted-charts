"""Independent variants, exact temporal gaps, and safe three-file persistence."""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest
from pandas.testing import assert_frame_equal

from data.pattern_injection.catalog import load_catalog
from data.pattern_injection.engine import (
    CHANGE_SCHEMA,
    create_variant,
    load_variant,
    resolve_cutoff,
    save_variant,
    validate_variant,
)


def gap_recipe(cutoff="2026-01-01T12:00:00Z", duration=120):
    return [
        {
            "preset": "gap_medium",
            "parameters": {"duration_minutes": duration},
            "target": {"cutoff_utc": cutoff},
            "seed": 7,
        }
    ]


def test_gap_exact_changes_and_source_immutability(injection_source, injection_log):
    original_files = {path: path.read_bytes() for path in injection_source.parent.iterdir()}
    events, manifest, changes = create_variant(injection_source, gap_recipe())
    expected = injection_log.copy()
    mask = expected["time:timestamp"].ge(pd.Timestamp("2026-01-01T12:00:00Z"))
    expected.loc[mask, "time:timestamp"] += pd.Timedelta(minutes=120)
    assert_frame_equal(expected, events)
    assert changes["event_id"].tolist() == expected.loc[mask, "identity:id"].tolist()
    assert (
        changes["timestamp_before_utc"].tolist()
        == injection_log.loc[mask, "time:timestamp"].tolist()
    )
    assert changes["timestamp_after_utc"].tolist() == expected.loc[mask, "time:timestamp"].tolist()
    assert set(changes["change_type"]) == {"updated"}
    injection = manifest["injections"][0]
    assert injection["affected"] == {
        "event_count": 6,
        "case_count": 4,
        "change_filter": {"injection_id": "inj_001"},
    }
    assert injection["target_regions"] == [
        {
            "region_id": "region_001",
            "coordinate_space": "final_event_log",
            "time_type": "interval",
            "start_utc": "2026-01-01T12:00:00+00:00",
            "end_utc": "2026-01-01T14:00:00+00:00",
            "case_scope": {"type": "all"},
        }
    ]
    assert events["identity:id"].tolist() == injection_log["identity:id"].tolist()
    assert {path: path.read_bytes() for path in original_files} == original_files
    assert manifest["source"]["source_sha256"]
    assert manifest["split_group_id"] == "fixture-family"


@pytest.mark.parametrize("control", [False, True])
def test_three_file_round_trip_and_typed_control(
    injection_source, injection_log, tmp_path, control
):
    events, manifest, changes = create_variant(injection_source, [] if control else gap_recipe())
    before_manifest = copy.deepcopy(manifest)
    output = save_variant(events, manifest, changes, tmp_path / "injected")
    assert set(path.name for path in output.iterdir()) == {
        "events.parquet",
        "manifest.json",
        "changes.parquet",
    }
    assert not (output / "events.json").exists()
    reloaded_events, stored, reloaded_changes = load_variant(output)
    assert_frame_equal(events, reloaded_events, check_exact=True)
    assert_frame_equal(changes, reloaded_changes, check_exact=True)
    assert manifest == before_manifest
    assert stored["variant_id"] == manifest["variant_id"]
    assert stored["files"]["events.parquet"]["sha256"]
    assert pq.read_schema(output / "changes.parquet").equals(CHANGE_SCHEMA, check_metadata=False)
    if control:
        assert_frame_equal(events, injection_log)
        assert changes.empty
        assert manifest["injections"] == []


def test_reproducible_siblings_and_unused_catalog_entries(injection_source, tmp_path):
    first = create_variant(injection_source, gap_recipe(), sample_cases=2, seed=42)
    repeated = create_variant(injection_source, gap_recipe(), sample_cases=2, seed=42)
    assert_frame_equal(first[0], repeated[0])
    assert first[1] == repeated[1]
    assert_frame_equal(first[2], repeated[2])
    root = tmp_path / "variants"
    first_path = save_variant(*first, root)
    copy_path = save_variant(*repeated, tmp_path / "repeat")
    assert {
        name: (first_path / name).read_bytes()
        for name in ("events.parquet", "changes.parquet", "manifest.json")
    } == {
        name: (copy_path / name).read_bytes()
        for name in ("events.parquet", "changes.parquet", "manifest.json")
    }
    second = create_variant(injection_source, gap_recipe(duration=60), sample_cases=2, seed=42)
    second_path = save_variant(*second, root)
    assert first_path.parent == second_path.parent
    assert first_path != second_path
    catalog = load_catalog()
    catalog["presets"]["unused"] = catalog["presets"]["gap_medium"] | {
        "parameters": {"duration_minutes": 99}
    }
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog))
    assert (
        create_variant(injection_source, gap_recipe(), sample_cases=2, seed=42, catalog_path=path)[
            1
        ]
        == first[1]
    )


@pytest.mark.parametrize(
    "recipe",
    [
        gap_recipe(cutoff="2027-01-01T00:00:00Z"),
        gap_recipe(duration=0),
        gap_recipe(duration=1e-20),
        gap_recipe(duration=1e20),
        gap_recipe(cutoff="2026-01-01T12:00:00"),
        [{"preset": "missing"}],
        [{"preset": "gap_medium", "typo": 1}],
        {"preset": "gap_medium"},
    ],
)
def test_invalid_recipe_fails_without_outputs(injection_source, recipe):
    with pytest.raises(ValueError):
        create_variant(injection_source, recipe)
    assert not (injection_source.parent / "injected").exists()


def test_gap_seeded_target_reproduces(injection_source):
    first = create_variant(injection_source, [{"preset": "gap_medium"}], seed=3)
    second = create_variant(injection_source, [{"preset": "gap_medium"}], seed=3)
    assert first[1] == second[1]
    assert first[1]["injections"][0]["selection"]["mode"] == "seeded"


@pytest.mark.parametrize("cutoff", ["2026-01-01T07:00:00Z", "2026-01-01T08:00:00Z"])
def test_gap_rejects_cutoffs_that_only_translate_the_log(injection_source, cutoff):
    with pytest.raises(ValueError, match="internal gap"):
        create_variant(injection_source, gap_recipe(cutoff=cutoff))


def test_seeded_gap_always_has_events_on_both_sides(injection_log):
    for seed in range(20):
        selection = resolve_cutoff(injection_log, {}, seed)
        cutoff = pd.Timestamp(selection["resolved"]["cutoff_utc"])
        assert injection_log["time:timestamp"].lt(cutoff).any()
        assert injection_log["time:timestamp"].ge(cutoff).any()


def test_seeded_gap_rejects_a_single_timestamp(injection_log):
    injection_log["time:timestamp"] = injection_log["time:timestamp"].min()
    with pytest.raises(ValueError, match="internal gap"):
        resolve_cutoff(injection_log, {}, 42)


def test_existing_and_partial_outputs_are_never_replaced(injection_source, tmp_path):
    variant = create_variant(injection_source, gap_recipe())
    root = tmp_path / "results"
    output = save_variant(*variant, root)
    existing = {path: path.read_bytes() for path in output.iterdir()}
    with pytest.raises(FileExistsError, match="already exists"):
        save_variant(*variant, root)
    assert {path: path.read_bytes() for path in output.iterdir()} == existing
    partial_root = tmp_path / "partial"
    partial = partial_root / variant[1]["dataset_id"] / variant[1]["variant_id"]
    partial.mkdir(parents=True)
    with pytest.raises(FileExistsError):
        save_variant(*variant, partial_root)
    with pytest.raises(ValueError, match="exactly"):
        load_variant(partial)


def test_publication_failure_rolls_back(injection_source, tmp_path, monkeypatch):
    variant = create_variant(injection_source, gap_recipe())
    original_link = os.link

    def failing_link(source, destination):
        if destination.name == "changes.parquet":
            raise OSError("publication failed")
        original_link(source, destination)

    monkeypatch.setattr("data.pattern_injection.engine.os.link", failing_link)
    root = tmp_path / "failed"
    with pytest.raises(OSError, match="publication failed"):
        save_variant(*variant, root)
    assert list((root / "fixture").iterdir()) == []


def test_reload_detects_corrupted_events(injection_source, tmp_path):
    output = save_variant(*create_variant(injection_source, gap_recipe()), tmp_path / "results")
    (output / "events.parquet").write_bytes(b"corrupt")
    with pytest.raises((ValueError, OSError)):
        load_variant(output)


def test_reload_without_original_source(injection_source, tmp_path):
    output = save_variant(*create_variant(injection_source, gap_recipe()), tmp_path / "results")
    injection_source.unlink()
    injection_source.with_suffix(".json").unlink()
    assert len(load_variant(output)[0]) == 12


@pytest.mark.parametrize("field", ["event_id", "timestamp_after_utc", "timestamp_before_utc"])
def test_changed_event_consistency_is_validated(injection_source, field):
    events, manifest, changes = create_variant(injection_source, gap_recipe())
    if field == "event_id":
        changes.loc[0, field] = "unknown"
    else:
        changes.loc[0, field] += pd.Timedelta(minutes=10)
    with pytest.raises(ValueError):
        validate_variant(events, manifest, changes, baseline=pd.read_parquet(injection_source))


def test_cli_gap_and_control(injection_source, tmp_path):
    script = Path(__file__).resolve().parents[3] / "scripts" / "inject_patterns.py"
    recipe = tmp_path / "control.json"
    recipe.write_text("[]\n")
    for options in (
        ["--preset", "gap_medium", "--sample-cases", "2", "--seed", "42"],
        ["--recipe", str(recipe)],
    ):
        root = tmp_path / "cli"
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--input",
                str(injection_source),
                "--output-root",
                str(root),
                *options,
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert "Variant:" in result.stdout
    assert len(list((root / "fixture").iterdir())) == 2
