"""Explicit, traceable publication of clean chart PNGs and rendering metadata."""

import hashlib
import json
import os
import re
from contextlib import ExitStack
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

from rendering.geometry import RENDERING_SCHEMA_VERSION
from rendering.renderer import (
    AXES_RECT,
    MAX_TIME_TICK_LABELS,
    RenderedChart,
    RenderStyle,
    render_charts,
)
from rendering.views import ChartInputs, ChartRole, RenderRole, ViewSpec

DEFAULT_OUTPUT_ROOT = Path("data/generated/charts")
RENDERER_VERSION = 1
EXPORT_FILES = ("chart.png", "rendering.json")


def _stable_id(prefix: str, identity: dict) -> str:
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return f"{prefix}_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def _variant_reference(inputs: ChartInputs) -> tuple[dict, dict]:
    manifest = inputs.manifest
    source = manifest["source"]
    identity = {
        "dataset_id": manifest["dataset_id"],
        "variant_id": manifest["variant_id"],
        "split_group_id": manifest["split_group_id"],
        "variant_schema_version": manifest["schema_version"],
        "processed_sha256": source["processed_sha256"],
        "selected_baseline_sha256": source.get("selected_baseline_sha256"),
        "events_sha256": manifest["files"]["events.parquet"]["sha256"],
        "changes_sha256": manifest["files"]["changes.parquet"]["sha256"],
        "baseline_selection_method": source["selection"]["method"],
    }
    reference = {
        **identity,
        "directory": str(inputs.variant_dir),
        "manifest_file": "manifest.json",
        "processed_path": source["processed_path"],
        "resolved_processed_path": str(inputs.baseline_path),
    }
    for field in ("source_id", "source_sha256", "processed_metadata_sha256"):
        if field in source:
            reference[field] = source[field]
    return identity, reference


def _view_metadata(chart: RenderedChart) -> dict:
    view = chart.view
    spec = view.spec
    start, end = view.time_bounds
    return {
        "mode": spec.mode,
        "requested_time_window_utc": [spec.start_utc.isoformat(), spec.end_utc.isoformat()]
        if spec.mode == "time_window"
        else None,
        "time_start_utc": start.isoformat(),
        "time_end_utc": end.isoformat(),
        "case_filter": list(spec.case_ids) if spec.case_ids is not None else None,
        "activity_filter": list(spec.activities) if spec.activities is not None else None,
        "injection_id": view.focus[0] if view.focus is not None else None,
        "region_id": view.focus[1] if view.focus is not None else None,
        "context_ns": spec.context.value if spec.context is not None else None,
        "ordered_case_ids": list(view.ordered_case_ids),
        "case_order_source": view.case_order_source,
    }


def _style_metadata(chart: RenderedChart, style: RenderStyle, software_versions: dict) -> dict:
    figure = chart.canvas.figure
    axes = figure.axes[0]
    return {
        **asdict(style),
        "renderer_version": RENDERER_VERSION,
        "backend": "Agg",
        "software_versions": software_versions,
        "marker": "o",
        "marker_edge_width_pt": 0,
        "activity_colors": chart.activity_colors,
        "activity_color_source": chart.view.case_order_source,
        "legend_displayed": chart.legend_displayed,
        "legend_activities": [label.get_text() for label in figure.legends[0].get_texts()]
        if chart.legend_displayed
        else [],
        "title_displayed": False,
        "axes_rect_fraction": list(AXES_RECT),
        "max_time_tick_labels": MAX_TIME_TICK_LABELS,
        "time_ticks": [
            {"date_num": float(position), "label": label.get_text()}
            for position, label in zip(axes.get_xticks(), axes.get_xticklabels(), strict=True)
        ],
        "time_tick_offset_label": axes.xaxis.offsetText.get_text(),
        "case_ticks": [
            {"row": row, "case_id": chart.view.ordered_case_ids[row]} for row in chart.case_ticks
        ],
    }


def _chart_metadata(
    inputs: ChartInputs, chart: RenderedChart, style: RenderStyle, software_versions: dict
) -> dict:
    variant_identity, source_variant = _variant_reference(inputs)
    injections = [
        {
            "injection_id": item["injection_id"],
            "pattern_type": item["pattern_type"],
            "target_regions": item["target_regions"],
            "changed_events": item["affected"]["event_count"],
        }
        for item in inputs.manifest["injections"]
    ]
    view = _view_metadata(chart)
    settings = _style_metadata(chart, style, software_versions)
    geometry = chart.geometry.record
    view_id = _stable_id(
        "view",
        {
            "variant": variant_identity,
            "injections": injections,
            "view": view,
            "style": settings,
            "geometry": geometry,
        },
    )
    digest_field = "selected_baseline_sha256" if chart.role == "baseline" else "events_sha256"
    input_digest = variant_identity[digest_field] or variant_identity["processed_sha256"]
    chart_id = _stable_id(chart.role, {"view_id": view_id, "input": input_digest})
    return {
        "schema_version": RENDERING_SCHEMA_VERSION,
        "chart_id": chart_id,
        "view_id": view_id,
        "dataset_id": inputs.manifest["dataset_id"],
        "variant_id": inputs.manifest["variant_id"],
        "split_group_id": inputs.manifest["split_group_id"],
        "role": chart.role,
        "source_variant": source_variant,
        "injections": injections,
        "view": view,
        "style": settings,
        "geometry": geometry,
        "counts": {
            **asdict(chart.counts),
            "filtering": {
                "time": view["mode"] != "full",
                "cases": view["case_filter"] is not None,
                "activities": view["activity_filter"] is not None,
            },
        },
        "diagnostics": list(chart.diagnostics),
    }


def export_charts(
    inputs: ChartInputs,
    *,
    view: ViewSpec = ViewSpec(),
    role: RenderRole = "both",
    style: RenderStyle = RenderStyle(),
    output_root: Path | str = DEFAULT_OUTPUT_ROOT,
) -> dict[ChartRole, Path]:
    """Explicitly save clean charts as PNG + JSON, reserving each output exclusively."""
    # Use the same dataset directory naming convention as the Phase-2 saver.
    dataset = re.sub(r"[^a-zA-Z0-9_-]+", "_", inputs.manifest["dataset_id"]).strip("_") or "dataset"
    parent = Path(output_root) / dataset / inputs.manifest["variant_id"]
    if parent.resolve().is_relative_to(inputs.variant_dir):
        raise ValueError(f"Chart output would modify the Phase-2 variant directory: {parent}")

    charts = render_charts(inputs, view=view, role=role, style=style)
    versions = {
        name: version(name) for name in ("matplotlib", "pillow", "pandas", "numpy", "pyarrow")
    }
    records = {
        item: _chart_metadata(inputs, chart, style, versions) for item, chart in charts.items()
    }
    outputs = {item: parent / record["chart_id"] for item, record in records.items()}
    for path in outputs.values():
        if path.exists() or path.is_symlink():
            raise FileExistsError(f"Chart output already exists: {path}")

    parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".chart-", dir=parent) as directory:
        staged = Path(directory)
        for item, chart in charts.items():
            files = staged / item
            files.mkdir()
            png = chart.png_bytes()
            (files / "chart.png").write_bytes(png)
            records[item]["image_sha256"] = hashlib.sha256(png).hexdigest()
            (files / "rendering.json").write_text(
                json.dumps(
                    records[item], indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
                )
                + "\n",
                encoding="utf-8",
            )
        with ExitStack() as rollback:
            for path in outputs.values():
                path.mkdir()
                rollback.callback(path.rmdir)
            for item, path in outputs.items():
                for filename in EXPORT_FILES:
                    target = path / filename
                    os.link(staged / item / filename, target)
                    rollback.callback(target.unlink)
            rollback.pop_all()
    return outputs
