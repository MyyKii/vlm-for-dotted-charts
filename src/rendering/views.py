"""Recover the selected Phase-1 baseline and prepare shared chart views."""

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from functools import cached_property
from pathlib import Path
from typing import Literal

import pandas as pd

from data.event_logs.config import ACTIVITY_COLUMN, CASE_ID_COLUMN, TIMESTAMP_COLUMN
from data.event_logs.preprocessing import EVENT_ID_COLUMN
from data.event_logs.storage import load_processed_event_log
from data.pattern_injection.engine import baseline_sha256, load_variant, utc_timestamp

ChartRole = Literal["baseline", "modified"]
RenderRole = Literal["baseline", "modified", "both"]
ReferenceSource = Literal["baseline", "modified_fallback"]
ViewMode = Literal["full", "time_window", "focused"]


@dataclass(frozen=True)
class ChartInputs:
    """Validated saved frames and their immutable-on-disk provenance."""

    variant_dir: Path
    baseline_path: Path
    manifest: dict
    modified: pd.DataFrame
    baseline: pd.DataFrame | None


def load_chart_inputs(
    variant_dir: Path | str, *, source_root: Path | str = Path(".")
) -> ChartInputs:
    """Load one Phase-2 variant and its exact selected baseline, if available.

    Relative source paths are based on ``source_root`` (normally the repository
    root). Both Phase-1 files are required for a match. A missing file permits
    modified-only views. A present source that fails validation raises an error.
    """
    directory = Path(variant_dir).resolve()
    try:
        modified, manifest, _ = load_variant(directory)
    except (OSError, ValueError) as error:
        raise ValueError(f"Invalid Phase-2 variant {directory}: {error}") from error
    # The recorded Parquet name also determines the Phase-1 sidecar name.
    path = Path(source_root).absolute() / manifest["source"]["processed_path"]
    try:
        baseline = _recover_baseline(path, manifest["source"])
    except (OSError, ValueError) as error:
        raise ValueError(f"Cannot verify Phase-1 baseline {path}: {error}") from error
    return ChartInputs(directory, path, manifest, modified, baseline)


def _recover_baseline(path: Path, source: dict) -> pd.DataFrame | None:
    try:
        path.stat()
        metadata_bytes = path.with_suffix(".json").read_bytes()
        original = load_processed_event_log(path)
    except FileNotFoundError:
        return None

    metadata = json.loads(metadata_bytes)
    if metadata["processed_sha256"] != source["processed_sha256"]:
        raise ValueError("Processed Parquet checksum differs from the Phase-2 manifest")
    metadata_digest = source.get("processed_metadata_sha256")
    if (
        metadata_digest is not None
        and hashlib.sha256(metadata_bytes).hexdigest() != metadata_digest
    ):
        raise ValueError("Phase-1 JSON checksum differs from the Phase-2 manifest")

    selection = source["selection"]
    method = selection["method"]
    ids = selection.get("resolved_case_ids")
    if method == "all_complete_cases" and ids is None:
        # The current Phase-2 loader requires IDs even for this method.
        baseline = original
    elif method in {"all_complete_cases", "sample_complete_cases", "explicit_complete_cases"}:
        if ids is None:
            raise ValueError(f"{method} requires resolved_case_ids")
        baseline = original.loc[original[CASE_ID_COLUMN].isin(ids)].reset_index(drop=True)
    else:
        raise ValueError(f"Unsupported Phase-2 baseline selection method {method!r}")
    digest = source.get("selected_baseline_sha256")
    if digest is not None and baseline_sha256(baseline) != digest:
        raise ValueError("Selected baseline fingerprint differs from the Phase-2 manifest")
    return baseline


def chart_roles(inputs: ChartInputs, role: RenderRole) -> tuple[ChartRole, ...]:
    """Resolve the requested roles, rejecting a comparison without its source."""
    if role not in ("baseline", "modified", "both"):
        raise ValueError(f"Unknown chart role {role!r}; use baseline, modified, or both")
    if role != "modified" and inputs.baseline is None:
        raise ValueError(
            f"Role {role!r} requires the Phase-1 baseline at {inputs.baseline_path} "
            "and its JSON sidecar. Use role='modified' for standalone rendering."
        )
    return ("baseline", "modified") if role == "both" else (role,)


@dataclass(frozen=True)
class ViewSpec:
    """One view request with independent case/activity filters and explicit UTC."""

    mode: ViewMode = "full"
    start_utc: str | pd.Timestamp | None = None
    end_utc: str | pd.Timestamp | None = None
    injection_id: str | None = None
    region_id: str | None = None
    context: str | timedelta | pd.Timedelta | None = None
    case_ids: tuple[str, ...] | list[str] | None = None
    activities: tuple[str, ...] | list[str] | None = None

    def __post_init__(self) -> None:
        if self.mode not in ("full", "time_window", "focused"):
            raise ValueError(f"Unknown view mode {self.mode!r}; use full, time_window, or focused")
        if self.mode != "time_window" and (self.start_utc is not None or self.end_utc is not None):
            raise ValueError("start_utc and end_utc require time_window mode")
        focus = (self.injection_id, self.region_id, self.context)
        if self.mode != "focused" and any(value is not None for value in focus):
            raise ValueError("injection_id, region_id, and context require focused mode")
        if self.mode == "time_window":
            start = utc_timestamp(self.start_utc, "start_utc")
            end = utc_timestamp(self.end_utc, "end_utc")
            if start >= end:
                raise ValueError("time_window requires end_utc > start_utc")
            object.__setattr__(self, "start_utc", start)
            object.__setattr__(self, "end_utc", end)
        if self.mode == "focused":
            refs = [value for value in focus[:2] if value is not None]
            if not refs or any(not isinstance(value, str) or not value.strip() for value in refs):
                raise ValueError("focused mode requires a nonempty injection_id or region_id")
            object.__setattr__(self, "context", _positive_context(self.context))
        for field in ("case_ids", "activities"):
            values = getattr(self, field)
            if values is not None:
                if (
                    not isinstance(values, (list, tuple))
                    or not values
                    or any(not isinstance(value, str) or not value.strip() for value in values)
                ):
                    raise ValueError(f"{field} must be a nonempty list or tuple of strings")
                object.__setattr__(self, field, tuple(sorted(set(values))))


def _positive_context(value: object) -> pd.Timedelta:
    if not isinstance(value, (str, timedelta, pd.Timedelta)):
        raise ValueError("focused mode requires a positive context duration, for example '12h'")
    try:
        context = pd.Timedelta(value).as_unit("ns")
        if context > pd.Timedelta(0):
            return context
    except (ValueError, OverflowError) as error:
        raise ValueError(f"Invalid focus context duration {value!r}") from error
    raise ValueError("Focus context must be positive")


@dataclass(frozen=True)
class EffectiveView:
    """Case rows, reference activities, and bounds shared by both frames."""

    spec: ViewSpec
    baseline: pd.DataFrame | None
    modified: pd.DataFrame
    time_bounds: tuple[pd.Timestamp, pd.Timestamp]
    ordered_case_ids: tuple[str, ...]
    reference_activities: tuple[str, ...]
    case_order_source: ReferenceSource
    focus: tuple[str, str] | None

    @cached_property
    def _event_ids(self) -> dict[ChartRole, pd.Index]:
        ids: dict[ChartRole, pd.Index] = {"modified": pd.Index(self.modified[EVENT_ID_COLUMN])}
        if self.baseline is not None:
            ids["baseline"] = pd.Index(self.baseline[EVENT_ID_COLUMN])
        return ids

    def events(self, role: ChartRole) -> pd.DataFrame:
        """Return the event rows used for the given chart role."""
        if role == "modified":
            return self.modified
        if role == "baseline" and self.baseline is not None:
            return self.baseline
        raise ValueError(f"View has no event frame for role {role!r}")


def is_event_rendered(event_id: str, view: EffectiveView, *, role: ChartRole) -> bool:
    """Check role-specific inclusion by stable ID using the actual selected rows."""
    if role not in view._event_ids:
        raise ValueError(f"View has no event frame for role {role!r}")
    return event_id in view._event_ids[role]


def candidate_regions(inputs: ChartInputs) -> list[tuple[str, dict]]:
    """Return Phase-2 target regions with their parent injection IDs."""
    return [
        (injection["injection_id"], region)
        for injection in inputs.manifest["injections"]
        for region in injection["target_regions"]
    ]


def region_time_bounds(region: dict) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Read validated UTC region bounds, returning the same time twice for an instant."""
    if region["time_type"] == "instant":
        timestamp = utc_timestamp(region["timestamp_utc"], "timestamp_utc")
        return timestamp, timestamp
    return (
        utc_timestamp(region["start_utc"], "start_utc"),
        utc_timestamp(region["end_utc"], "end_utc"),
    )


def _resolve_focus(inputs: ChartInputs, spec: ViewSpec) -> tuple[str, dict]:
    matches = [
        (injection_id, region)
        for injection_id, region in candidate_regions(inputs)
        if (spec.injection_id is None or spec.injection_id == injection_id)
        and (spec.region_id is None or spec.region_id == region["region_id"])
    ]
    description = f"injection_id={spec.injection_id!r}, region_id={spec.region_id!r}"
    if not matches:
        raise ValueError(f"No target region matches {description}")
    if len(matches) > 1:
        raise ValueError(f"Ambiguous target region for {description}; specify both IDs")
    return matches[0]


def _full_time_bounds(
    inputs: ChartInputs, reference: pd.DataFrame
) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = min(reference[TIMESTAMP_COLUMN].min(), inputs.modified[TIMESTAMP_COLUMN].min())
    end = max(reference[TIMESTAMP_COLUMN].max(), inputs.modified[TIMESTAMP_COLUMN].max())
    if start == end:
        # Give a constant full log a usable linear time axis.
        start = pd.Timestamp(max(pd.Timestamp.min.value, start.value - 500_000_000), tz="UTC")
        end = pd.Timestamp(min(pd.Timestamp.max.value, end.value + 500_000_000), tz="UTC")
    return start, end


def _filter_events(
    frame: pd.DataFrame, spec: ViewSpec, bounds: tuple[pd.Timestamp, pd.Timestamp]
) -> pd.DataFrame:
    if spec.mode != "full":
        times = frame[TIMESTAMP_COLUMN]
        frame = frame.loc[times.ge(bounds[0]) & times.lt(bounds[1])]
    if spec.case_ids is not None:
        frame = frame.loc[frame[CASE_ID_COLUMN].isin(spec.case_ids)]
    if spec.activities is not None:
        frame = frame.loc[frame[ACTIVITY_COLUMN].isin(spec.activities)]
    return frame


def select_view(inputs: ChartInputs, spec: ViewSpec = ViewSpec()) -> EffectiveView:
    """Apply one view specification and align the case rows across both roles."""
    reference = inputs.modified if inputs.baseline is None else inputs.baseline
    first_times = reference.groupby(CASE_ID_COLUMN, sort=True)[TIMESTAMP_COLUMN].min()
    order = first_times.sort_values(kind="stable").index
    activities = tuple(sorted(reference[ACTIVITY_COLUMN].unique()))
    for requested, available, field in (
        (spec.case_ids, order, "case IDs"),
        (spec.activities, activities, "activities"),
    ):
        if requested is not None and (unknown := set(requested).difference(available)):
            raise ValueError(f"Unknown {field} in selected variant: {sorted(unknown)}")

    focus = None
    if spec.mode == "time_window":
        bounds = (spec.start_utc, spec.end_utc)
    elif spec.mode == "focused":
        injection_id, region = _resolve_focus(inputs, spec)
        focus = (injection_id, region["region_id"])
        start, end = region_time_bounds(region)
        try:
            bounds = (start - spec.context, end + spec.context)
        except (ValueError, OverflowError) as error:
            raise ValueError(
                "Focus context places the time bounds outside the UTC range"
            ) from error
    else:
        bounds = _full_time_bounds(inputs, reference)

    modified = _filter_events(inputs.modified, spec, bounds)
    baseline = None if inputs.baseline is None else _filter_events(inputs.baseline, spec, bounds)
    if spec.case_ids is not None:
        rows = set(spec.case_ids)
    else:
        rows = set(modified[CASE_ID_COLUMN].unique())
        if baseline is not None:
            rows.update(baseline[CASE_ID_COLUMN].unique())
    return EffectiveView(
        spec,
        baseline,
        modified,
        bounds,
        tuple(case_id for case_id in order if case_id in rows),
        activities,
        "modified_fallback" if inputs.baseline is None else "baseline",
        focus,
    )
