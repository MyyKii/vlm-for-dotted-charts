"""Offline CLI fixtures exercise the final control/single/multiple-injection workflow."""

import json
import subprocess
import sys
from pathlib import Path

import pyarrow.parquet as pq
import pytest
from pandas.testing import assert_frame_equal

from data.pattern_injection.engine import CHANGE_SCHEMA, load_variant

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "inject_patterns.py"


def run_cli(source, root, *options):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(source), "--output-root", str(root), *options],
        cwd=root.parent,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def write_recipe(tmp_path, *, overlap=False):
    recipe = tmp_path / "recipe.json"
    recipe.write_text(
        json.dumps(
            [
                {"preset": "gap_medium", "target": {"cutoff_utc": "2026-01-01T12:00:00Z"}},
                {
                    "preset": "batch_small",
                    "parameters": {"num_events": 2, "jitter_seconds": 0},
                    "target": {
                        "event_ids": ["event-2-Work", "event-3-Work"]
                        if overlap
                        else ["event-0-Work", "event-1-Work"],
                        "center_utc": "2026-01-01T16:00:00Z" if overlap else "2026-01-01T09:00:00Z",
                    },
                    "seed": 7,
                },
            ]
        )
    )
    return recipe


@pytest.mark.parametrize(
    "kind,expected_instances", [("control", 0), ("gap", 1), ("batch", 1), ("mixed", 2)]
)
def test_complete_cli_workflows(
    injection_source, injection_log, tmp_path, kind, expected_instances
):
    sources = {path: path.read_bytes() for path in injection_source.parent.iterdir()}
    if kind == "control":
        path = tmp_path / "control.json"
        path.write_text("[]\n")
        options = ["--recipe", str(path), "--case-id", "case-0", "--case-id", "case-1"]
    elif kind == "gap":
        options = [
            "--preset",
            "gap_medium",
            "--cutoff-utc",
            "2026-01-01T12:00:00Z",
            "--duration-minutes",
            "60",
            "--sample-cases",
            "2",
            "--seed",
            "42",
        ]
    elif kind == "batch":
        options = [
            "--preset",
            "batch_small",
            "--num-events",
            "2",
            "--jitter-seconds",
            "0",
            "--center-utc",
            "2026-01-01T09:00:00Z",
            "--event-id",
            "event-0-Work",
            "--event-id",
            "event-1-Work",
            "--target-case-id",
            "case-0",
            "--target-case-id",
            "case-1",
            "--activity",
            "Work",
            "--start-utc",
            "2026-01-01T10:00:00Z",
            "--end-utc",
            "2026-01-01T12:00:00Z",
        ]
    else:
        options = ["--recipe", str(write_recipe(tmp_path)), "--seed", "42"]
    root = tmp_path / "injected"
    result = run_cli(injection_source, root, *options)
    assert result.returncode == 0, result.stderr
    assert f"Injections: {expected_instances}" in result.stdout
    (output,) = (root / "fixture").iterdir()
    events, manifest, changes = load_variant(output)
    assert len(manifest["injections"]) == expected_instances
    assert manifest["source"]["processed_path"] == str(injection_source)
    assert manifest["split_group_id"] == "fixture-family"
    assert str(events["time:timestamp"].dt.tz) == "UTC"
    assert pq.read_schema(output / "changes.parquet").equals(CHANGE_SCHEMA, check_metadata=False)
    assert set(events["identity:id"]).issubset(injection_log["identity:id"])
    assert {path: path.read_bytes() for path in sources} == sources
    if kind == "control":
        assert_frame_equal(events, injection_log.iloc[:6].reset_index(drop=True))
        assert changes.empty
    elif kind == "mixed":
        assert manifest["injections"][1]["seed"] == 7


def test_cli_reproduces_but_refuses_existing_results(injection_source, tmp_path):
    root = tmp_path / "first"
    options = (
        "--preset",
        "batch_small",
        "--num-events",
        "3",
        "--jitter-seconds",
        "30",
        "--activity",
        "Work",
        "--seed",
        "7",
    )
    first = run_cli(injection_source, root, *options)
    assert first.returncode == 0, first.stderr
    (output,) = (root / "fixture").iterdir()
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    refused = run_cli(injection_source, root, *options)
    assert refused.returncode == 1
    assert "already exists" in refused.stderr
    assert "Traceback" not in refused.stderr
    assert "Output:" not in refused.stdout
    assert {path.name: path.read_bytes() for path in output.iterdir()} == before
    second_root = tmp_path / "second"
    repeated = run_cli(injection_source, second_root, *options)
    assert repeated.returncode == 0, repeated.stderr
    (second,) = (second_root / "fixture").iterdir()
    assert second.name == output.name
    assert {path.name: path.read_bytes() for path in second.iterdir()} == before


@pytest.mark.parametrize(
    "options,message",
    [
        (["--preset", "missing"], "Unknown preset"),
        (["--preset", "gap_medium", "--cutoff-utc", "2027-01-01T00:00:00Z"], "selects no events"),
        (["--preset", "gap_medium", "--sample-cases", "0"], "sample_cases"),
        (["--preset", "gap_medium", "--seed", "-1"], "seed"),
        (["--preset", "gap_medium", "--duration-minutes", "nan"], "finite"),
        (
            ["--preset", "batch_small", "--num-events", "2", "--jitter-seconds", "-1"],
            "jitter_seconds",
        ),
        (["--preset", "batch_small", "--num-events", "2", "--center-utc", "2026-01-01"], "UTC"),
        (["--preset", "gap_medium", "--num-events", "2"], "parameters"),
        (["--preset", "batch_small", "--cutoff-utc", "2026-01-01T12:00:00Z"], "Batch target"),
        (["--preset", "batch_small", "--num-events", "2", "--event-id", "missing"], "Unresolvable"),
    ],
)
def test_cli_invalid_settings_fail_cleanly(injection_source, tmp_path, options, message):
    root = tmp_path / "failed"
    result = run_cli(injection_source, root, *options)
    assert result.returncode == 1
    assert message in result.stderr
    assert "Traceback" not in result.stderr
    assert "Output:" not in result.stdout
    assert not root.exists()


def test_cli_rejects_overlapping_recipe(injection_source, tmp_path):
    root = tmp_path / "failed"
    result = run_cli(injection_source, root, "--recipe", str(write_recipe(tmp_path, overlap=True)))
    assert result.returncode == 1
    assert "already changed event" in result.stderr
    assert not root.exists()


@pytest.mark.parametrize("text", ["{", "{}", '[{"preset":"gap_medium","extra":1}]'])
def test_cli_invalid_recipe_files(injection_source, tmp_path, text):
    path = tmp_path / "recipe.json"
    path.write_text(text)
    result = run_cli(injection_source, tmp_path / "failed", "--recipe", str(path))
    assert result.returncode == 1
    assert "Traceback" not in result.stderr


def test_cli_rejects_recipe_and_target_flags(injection_source, tmp_path):
    path = tmp_path / "control.json"
    path.write_text("[]")
    result = run_cli(
        injection_source,
        tmp_path / "failed",
        "--recipe",
        str(path),
        "--center-utc",
        "2026-01-01T09:00:00Z",
    )
    assert result.returncode == 2
    assert "require --preset" in result.stderr


def test_cli_requires_phase_one_provenance(tmp_path, injection_log):
    source = tmp_path / "bare.parquet"
    injection_log.to_parquet(source, index=False)
    result = run_cli(source, tmp_path / "failed", "--preset", "gap_medium")
    assert result.returncode == 1
    assert ".json" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_help_lists_target_and_subset_flags(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0
    assert "--recipe" in result.stdout
    assert "--sample-cases" in result.stdout
    assert "--center-utc" in result.stdout
    assert "--target-case-id" in result.stdout
