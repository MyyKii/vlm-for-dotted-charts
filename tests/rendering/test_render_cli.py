"""Dotted Chart export CLI using real saved artifacts."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "render_charts.py"


def run_cli(path, root, *options):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--variant", str(path), "--output-root", str(root), *options],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_cli_exports_a_clean_focused_pair(gap_path, tmp_path):
    root = tmp_path / "charts"
    options = (
        "--view",
        "focused",
        "--injection-id",
        "inj_001",
        "--region-id",
        "region_001",
        "--context-hours",
        "1",
        "--role",
        "both",
        "--width-px",
        "517",
        "--height-px",
        "273",
        "--dpi",
        "173",
        "--case-id",
        "case-a",
        "--activity",
        "Work",
    )
    result = run_cli(gap_path, root, *options)
    assert result.returncode == 0, result.stderr
    paths = list(root.glob("fixture/*/*/rendering.json"))
    assert len(paths) == 2
    records = [json.loads(path.read_text()) for path in paths]
    assert len({record["view_id"] for record in records}) == 1
    assert {record["role"] for record in records} == {"baseline", "modified"}
    assert all(record["view"]["case_filter"] == ["case-a"] for record in records)
    for path in paths:
        with Image.open(path.with_name("chart.png")) as image:
            assert image.size == (517, 273)
    duplicate = run_cli(gap_path, root, *options)
    assert duplicate.returncode == 1
    assert "Chart output already exists" in duplicate.stderr


@pytest.mark.parametrize(
    ("options", "message"),
    [
        (("--view", "time_window", "--start-utc", "2026-01-01"), "Invalid start_utc"),
        (("--view", "focused", "--region-id", "region_999", "--context-hours", "1"), "region_999"),
        (("--activity", "missing-activity"), "Unknown activities.*missing-activity"),
    ],
)
def test_cli_names_invalid_view_values(gap_path, tmp_path, options, message):
    root = tmp_path / "charts"
    result = run_cli(gap_path, root, *options)
    assert result.returncode == 1
    assert re.search(message, result.stderr)
    assert not root.exists()


def test_cli_reports_invalid_variant_path(tmp_path):
    variant = tmp_path / "missing-variant"
    root = tmp_path / "charts"
    result = run_cli(variant, root)
    assert result.returncode == 1
    assert str(variant) in result.stderr
    assert "Invalid Phase-2 variant" in result.stderr
    assert not root.exists()


def test_cli_missing_baseline_handles_only_modified(gap_path, source_path, tmp_path):
    source_path.unlink()
    root = tmp_path / "charts"
    for role in ("baseline", "both"):
        result = run_cli(gap_path, root, "--role", role)
        assert result.returncode == 1
        assert "requires the Phase-1 baseline" in result.stderr
        assert not root.exists()

    rendered = run_cli(
        gap_path, root, "--role", "modified", "--width-px", "500", "--height-px", "300"
    )
    assert rendered.returncode == 0, rendered.stderr
    (metadata_path,) = root.glob("fixture/*/*/rendering.json")
    record = json.loads(metadata_path.read_text())
    assert record["view"]["case_order_source"] == "modified_fallback"
    assert record["style"]["activity_color_source"] == "modified_fallback"
