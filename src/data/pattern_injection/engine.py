"""Selection and version-1 contracts for complete Phase-2 event-log variants."""

import copy
import hashlib
import json
import os
import random
import re
from collections.abc import Iterable
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pandas.testing import assert_frame_equal

from data.event_logs.config import ACTIVITY_COLUMN, CASE_ID_COLUMN, TIMESTAMP_COLUMN
from data.event_logs.preprocessing import EVENT_ID_COLUMN, SOURCE_ROW_COLUMN
from data.event_logs.storage import load_processed_event_log
from data.event_logs.validation import validate_event_log
from data.pattern_injection.catalog import (
    CATALOG_PATH,
    STRATEGY_TYPES,
    load_catalog,
    resolve_preset,
    validate_parameters,
)
from data.pattern_injection.patterns import STRATEGIES

SCHEMA_VERSION = 1
CHANGE_SCHEMA = pa.schema(
    [
        ("injection_id", pa.string()),
        ("event_id", pa.string()),
        ("change_type", pa.string()),
        ("case_id_before", pa.string()),
        ("case_id_after", pa.string()),
        ("timestamp_before_utc", pa.timestamp("ns", tz="UTC")),
        ("timestamp_after_utc", pa.timestamp("ns", tz="UTC")),
        ("derived_from_event_id", pa.string()),
        ("before_values_json", pa.string()),
        ("after_values_json", pa.string()),
    ]
)
CHANGE_DTYPES = {
    field.name: "datetime64[ns, UTC]" if pa.types.is_timestamp(field.type) else "string"
    for field in CHANGE_SCHEMA
}
VARIANT_FILES = {"events.parquet", "changes.parquet", "manifest.json"}


def changes_frame(rows: Iterable[dict] = ()) -> pd.DataFrame:
    """Build the fixed typed change table, including a zero-row control table."""
    return pa.Table.from_pylist(list(rows), schema=CHANGE_SCHEMA).to_pandas().astype(CHANGE_DTYPES)


def utc_timestamp(value: object, name: str) -> pd.Timestamp:
    """Require an explicit UTC ISO timestamp; never guess a timezone or epoch unit."""
    if not isinstance(value, (str, pd.Timestamp)):
        raise ValueError(f"{name} must be an explicit UTC timestamp")
    try:
        timestamp = pd.Timestamp(value)
        if pd.isna(timestamp) or timestamp.tzinfo is None or timestamp.utcoffset().total_seconds():
            raise ValueError("expected a timezone-aware UTC value")
        return timestamp.tz_convert("UTC").as_unit("ns")
    except (ValueError, TypeError, OverflowError) as error:
        raise ValueError(f"Invalid {name}: {value!r}; use an explicit UTC timestamp") from error


def validate_seed(seed: int) -> None:
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")


def validate_events(frame: pd.DataFrame, expected_count: int | None = None) -> None:
    """Reuse Phase-1 integrity checks and require its stable event identities."""
    validate_event_log(frame, expected_num_events=expected_count)
    for column in (EVENT_ID_COLUMN, SOURCE_ROW_COLUMN):
        if column not in frame:
            raise ValueError(f"Phase 2 requires the Phase-1 field {column!r}")
    if not pd.api.types.is_string_dtype(frame[EVENT_ID_COLUMN]):
        raise ValueError(f"{EVENT_ID_COLUMN!r} must contain string IDs")


def _id_list(values: object, name: str) -> list[str]:
    if (
        not isinstance(values, list)
        or not values
        or any(not isinstance(value, str) or not value.strip() for value in values)
        or len(set(values)) != len(values)
    ):
        raise ValueError(f"{name} must be a nonempty list of unique string IDs")
    return sorted(values)


def select_complete_cases(
    frame: pd.DataFrame,
    *,
    sample_cases: int | None = None,
    case_ids: list[str] | None = None,
    seed: int = 42,
) -> tuple[pd.DataFrame, dict]:
    """Keep all events of resolved cases, without mutating or cropping the input."""
    validate_events(frame)
    validate_seed(seed)
    available = sorted(frame[CASE_ID_COLUMN].unique())
    if sample_cases is not None and case_ids is not None:
        raise ValueError("Choose sample_cases or explicit case_ids, not both")
    selection = {"method": "all_complete_cases"}
    if sample_cases is not None:
        if type(sample_cases) is not int or not 1 <= sample_cases <= len(available):
            raise ValueError(f"sample_cases must be between 1 and {len(available)}")
        resolved = sorted(random.Random(seed).sample(available, sample_cases))
        selection = {"method": "sample_complete_cases", "count": sample_cases, "seed": seed}
    elif case_ids is not None:
        resolved = _id_list(case_ids, "case_ids")
        if set(resolved) - set(available):
            raise ValueError("Unknown case_ids in baseline selection")
        selection = {"method": "explicit_complete_cases", "requested_case_ids": resolved}
    else:
        resolved = available
    selection["resolved_case_ids"] = resolved
    return frame.loc[frame[CASE_ID_COLUMN].isin(resolved)].copy().reset_index(drop=True), selection


def select_target_events(frame: pd.DataFrame, target: dict) -> pd.DataFrame:
    """Filter eligible events by stable IDs, cases, activities, and a half-open UTC interval."""
    allowed = {"event_ids", "case_ids", "activities", "start_utc", "end_utc", "center_utc"}
    if not isinstance(target, dict) or set(target) - allowed:
        raise ValueError(f"Batch target accepts only {sorted(allowed)}")
    mask = pd.Series(True, index=frame.index)
    for key, column in (
        ("event_ids", EVENT_ID_COLUMN),
        ("case_ids", CASE_ID_COLUMN),
        ("activities", ACTIVITY_COLUMN),
    ):
        if key in target:
            requested = _id_list(target[key], key)
            if set(requested) - set(frame[column]):
                raise ValueError(f"Unresolvable target {key}")
            mask &= frame[column].isin(requested)
    if ("start_utc" in target) != ("end_utc" in target):
        raise ValueError("Target interval requires both start_utc and end_utc")
    if "start_utc" in target:
        start = utc_timestamp(target["start_utc"], "start_utc")
        end = utc_timestamp(target["end_utc"], "end_utc")
        if end <= start:
            raise ValueError("Target interval must have end_utc > start_utc")
        mask &= frame[TIMESTAMP_COLUMN].ge(start) & frame[TIMESTAMP_COLUMN].lt(end)
    if "center_utc" in target:
        utc_timestamp(target["center_utc"], "center_utc")
    selected = frame.loc[mask].copy()
    if selected.empty:
        raise ValueError("Target selects no eligible events")
    if "event_ids" in target and set(selected[EVENT_ID_COLUMN]) != set(target["event_ids"]):
        raise ValueError("Explicit event_ids conflict with the other target filters")
    return selected


def resolve_cutoff(frame: pd.DataFrame, target: dict, seed: int) -> dict:
    """Resolve an explicit or seeded gap cut-off and save affected stable IDs."""
    validate_seed(seed)
    if not isinstance(target, dict) or set(target) - {"cutoff_utc"}:
        raise ValueError("Gap target accepts only cutoff_utc")
    if target:
        cutoff = utc_timestamp(target["cutoff_utc"], "cutoff_utc")
    else:
        candidates = sorted(frame[TIMESTAMP_COLUMN].unique())[1:]
        if not candidates:
            raise ValueError("An internal gap requires at least two distinct event timestamps")
        cutoff = random.Random(seed).choice(candidates)
    mask = frame[TIMESTAMP_COLUMN].ge(cutoff)
    if mask.all():
        raise ValueError("Gap cut-off must leave events before it to create an internal gap")
    affected = frame.loc[mask]
    if affected.empty:
        raise ValueError("Gap cut-off selects no events")
    return {
        "mode": "explicit" if target else "seeded",
        "requested": target.copy(),
        "resolved": {
            "cutoff_utc": cutoff.isoformat(),
            "event_ids": sorted(affected[EVENT_ID_COLUMN]),
            "case_ids": sorted(affected[CASE_ID_COLUMN].unique()),
        },
    }


def _feasible_batch_centers(
    centers: list[int], eligible: pd.DataFrame, bounds: pd.DataFrame, jitter: int, count: int
) -> set[int]:
    """Sweep window boundaries once, counting distinct cases and possible edits."""
    edges = []
    for case, timestamp, (lower, upper) in zip(
        eligible[CASE_ID_COLUMN],
        eligible[TIMESTAMP_COLUMN],
        bounds.itertuples(index=False, name=None),
        strict=True,
    ):
        low, high, original = lower.value, upper.value, timestamp.value
        # A None owner counts possible modifications; case owners count distinct
        # feasible cases even when several of their events have overlapping windows.
        for start, end, owner in (
            (low, high, case),
            (low, min(high, original - 1), None),
            (max(low, original + 1), high, None),
        ):
            if start <= end:
                edges.extend([(start - jitter, 1, owner), (end + jitter + 1, -1, owner)])
    edges.sort(key=lambda edge: edge[0])
    active = {}
    case_count = movable_count = position = 0
    feasible = set()
    for center in centers:
        while position < len(edges) and edges[position][0] <= center:
            _, delta, owner = edges[position]
            if owner is None:
                movable_count += delta
            else:
                previous = active.get(owner, 0)
                active[owner] = previous + delta
                case_count += int(active[owner] > 0) - int(previous > 0)
            position += 1
        if (
            case_count >= count
            and movable_count > 0
            and pd.Timestamp.min.value + jitter <= center <= pd.Timestamp.max.value - jitter
        ):
            feasible.add(center)
    return feasible


def resolve_batch_target(frame: pd.DataFrame, target: dict, parameters: dict, seed: int) -> dict:
    """Select at most one event per case and sample within feasible jitter bounds.

    Neighbor timestamps and original source-row tie order bound each assignment.
    Seeded centers come from eligible timestamps and feasible window boundaries
    within the current log's time range. Feasible centers are computed in one
    boundary sweep, with at least one possible modifying assignment. Automatic
    event selection prefers modifying events/cases; explicit IDs are never substituted.
    """
    validate_seed(seed)
    eligible = select_target_events(frame, target).set_index(EVENT_ID_COLUMN, drop=False)
    count = parameters["num_events"]
    if eligible[CASE_ID_COLUMN].nunique() < count:
        raise ValueError("Infeasible batch target: fewer eligible distinct cases than num_events")
    if "event_ids" in target and (
        len(eligible) != count or eligible[CASE_ID_COLUMN].nunique() != count
    ):
        raise ValueError("Explicit batch event_ids must match num_events and use distinct cases")
    try:
        jitter = pd.Timedelta(parameters["jitter_seconds"], unit="s")
    except (ValueError, OverflowError) as error:
        raise ValueError(f"Infeasible jitter_seconds: {error}") from error
    ordered = frame.sort_values(
        [CASE_ID_COLUMN, TIMESTAMP_COLUMN, SOURCE_ROW_COLUMN], kind="stable"
    ).copy()
    ordered[TIMESTAMP_COLUMN] = ordered[TIMESTAMP_COLUMN].dt.as_unit("ns")
    grouped = ordered.groupby(CASE_ID_COLUMN, sort=False)
    lower = grouped[TIMESTAMP_COLUMN].shift(1).fillna(pd.Timestamp.min.tz_localize("UTC"))
    upper = grouped[TIMESTAMP_COLUMN].shift(-1).fillna(pd.Timestamp.max.tz_localize("UTC"))
    # Equal timestamps must also retain the Phase-1 source-row tie order.
    lower += pd.to_timedelta(
        grouped[SOURCE_ROW_COLUMN].shift(1).gt(ordered[SOURCE_ROW_COLUMN]).astype(int), unit="ns"
    )
    upper -= pd.to_timedelta(
        grouped[SOURCE_ROW_COLUMN].shift(-1).lt(ordered[SOURCE_ROW_COLUMN]).astype(int), unit="ns"
    )
    bounds = (
        pd.DataFrame({"lower": lower, "upper": upper, EVENT_ID_COLUMN: ordered[EVENT_ID_COLUMN]})
        .set_index(EVENT_ID_COLUMN)
        .loc[eligible.index]
    )
    rng = random.Random(seed)
    if "center_utc" in target:
        centers = [utc_timestamp(target["center_utc"], "center_utc")]
    else:
        earliest, latest = frame[TIMESTAMP_COLUMN].min().value, frame[TIMESTAMP_COLUMN].max().value
        candidates = {timestamp.value for timestamp in eligible[TIMESTAMP_COLUMN]}
        for low, high in bounds.itertuples(index=False, name=None):
            candidates.add(max(earliest, min(latest, low.value - jitter.value)))
            candidates.add(max(earliest, min(latest, high.value + jitter.value)))
        candidates = sorted(candidates)
        feasible_centers = _feasible_batch_centers(
            candidates, eligible, bounds, jitter.value, count
        )
        centers = [pd.Timestamp(value, tz="UTC") for value in candidates]
        rng.shuffle(centers)
        centers = [center for center in centers if center.value in feasible_centers]
    if not centers:
        raise ValueError(
            "Infeasible batch target: no center permits enough cases and a timestamp change"
        )
    center = centers[0]
    try:
        low = bounds["lower"].clip(lower=center - jitter)
        high = bounds["upper"].clip(upper=center + jitter)
    except (ValueError, OverflowError) as error:
        raise ValueError(f"Infeasible center/jitter window: {error}") from error
    feasible = eligible.loc[low.le(high)]
    choices = feasible.groupby(CASE_ID_COLUMN)[EVENT_ID_COLUMN].agg(sorted).to_dict()
    if len(choices) < count:
        raise ValueError(
            "Infeasible batch target: not enough distinct cases within predecessor/successor bounds"
        )
    moving = feasible.loc[
        low.loc[feasible.index].ne(feasible[TIMESTAMP_COLUMN])
        | high.loc[feasible.index].ne(feasible[TIMESTAMP_COLUMN])
    ]
    moving_choices = moving.groupby(CASE_ID_COLUMN)[EVENT_ID_COLUMN].agg(sorted).to_dict()
    if "event_ids" in target or len(moving_choices) >= count:
        cases = rng.sample(sorted(choices if "event_ids" in target else moving_choices), count)
    else:
        cases = sorted(moving_choices) + rng.sample(
            sorted(set(choices) - set(moving_choices)), count - len(moving_choices)
        )
    chosen = [rng.choice(moving_choices.get(case, choices[case])) for case in cases]
    assignments = {}
    for event_id in sorted(chosen):
        start, end = low.loc[event_id].value, high.loc[event_id].value
        original = eligible.loc[event_id, TIMESTAMP_COLUMN].value
        if start <= original <= end and start < end:
            timestamp = rng.randint(start, end - 1)
            timestamp += int(timestamp >= original)
        else:
            timestamp = rng.randint(start, end)
        assignments[event_id] = pd.Timestamp(timestamp, tz="UTC").isoformat()
    selected = eligible.loc[sorted(chosen)]
    return {
        "mode": "explicit" if target else "seeded",
        "requested": copy.deepcopy(target),
        "resolved": {
            "center_utc": center.isoformat(),
            "event_ids": sorted(chosen),
            "case_ids": sorted(selected[CASE_ID_COLUMN].unique()),
            "activities": sorted(selected[ACTIVITY_COLUMN].unique()),
            "assigned_timestamps_utc": assignments,
        },
    }


def validate_regions(regions: list[dict]) -> None:
    """Check candidate regions in final log coordinates, including point-like batches."""
    if not isinstance(regions, list) or not regions:
        raise ValueError("Each injection requires one or more target_regions")
    seen = set()
    for region in regions:
        if not isinstance(region, dict):
            raise ValueError("Each target region must be an object")
        region_id = region.get("region_id")
        if not isinstance(region_id, str) or not region_id.strip() or region_id in seen:
            raise ValueError("region_id must be nonempty and unique within an injection")
        seen.add(region_id)
        if region.get("coordinate_space") != "final_event_log":
            raise ValueError("Regions must use coordinate_space final_event_log")
        scope = region.get("case_scope")
        if scope == {"type": "all"}:
            pass
        elif isinstance(scope, dict) and set(scope) == {"type", "case_ids"}:
            if scope["type"] != "selected":
                raise ValueError("case_scope type must be all or selected")
            _id_list(scope["case_ids"], "case_scope.case_ids")
        else:
            raise ValueError("case_scope must explicitly identify all or selected cases")
        if "activity_scope" in region:
            _id_list(region["activity_scope"], "activity_scope")
        time_fields = set(region) & {"start_utc", "end_utc", "timestamp_utc"}
        if region.get("time_type") == "interval" and time_fields == {"start_utc", "end_utc"}:
            start = utc_timestamp(region["start_utc"], "start_utc")
            end = utc_timestamp(region["end_utc"], "end_utc")
            if end <= start:
                raise ValueError("Region interval must have end_utc > start_utc")
        elif region.get("time_type") == "instant" and time_fields == {"timestamp_utc"}:
            utc_timestamp(region["timestamp_utc"], "timestamp_utc")
        else:
            raise ValueError("Region needs exactly one interval or instant time representation")


def validate_manifest(manifest: dict) -> None:
    """Validate the mandatory manifest fields independently of Parquet storage."""
    if (
        not isinstance(manifest, dict)
        or type(manifest.get("schema_version")) is not int
        or manifest["schema_version"] != SCHEMA_VERSION
    ):
        raise ValueError("Unsupported or missing variant schema_version")
    for field in ("variant_id", "dataset_id", "split_group_id"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            raise ValueError(f"Manifest requires a nonempty {field}")
    variant_id = manifest["variant_id"]
    if len(variant_id) > 64 or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", variant_id):
        raise ValueError("variant_id must be a safe directory name of at most 64 characters")
    source = manifest.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("selection"), dict):
        raise ValueError("Manifest requires source provenance and exact selection")
    for field in ("processed_path", "processed_sha256"):
        if not isinstance(source.get(field), str) or not source[field]:
            raise ValueError(f"Manifest source requires {field}")
    if not re.fullmatch(r"[0-9a-f]{64}", source["processed_sha256"]):
        raise ValueError("processed_sha256 must be an actual SHA-256 hexadecimal digest")
    baseline_digest = source.get("selected_baseline_sha256")
    if not isinstance(baseline_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", baseline_digest):
        raise ValueError(
            "Missing or invalid selected_baseline_sha256; regenerate from the Phase-1 input"
        )
    if not isinstance(source["selection"].get("method"), str) or not source["selection"]["method"]:
        raise ValueError("Source selection requires its reproducible method")
    _id_list(source["selection"].get("resolved_case_ids"), "resolved_case_ids")
    if manifest.get("event_changes_file") != "changes.parquet":
        raise ValueError("event_changes_file must be changes.parquet")
    for field in ("event_count_before", "event_count_after"):
        if type(manifest.get(field)) is not int or manifest[field] < 1:
            raise ValueError(f"{field} must be a positive integer")
    injections = manifest.get("injections")
    if not isinstance(injections, list):
        raise ValueError("injections must be an ordered list, empty for a control")
    seen = set()
    for order, injection in enumerate(injections, 1):
        if not isinstance(injection, dict):
            raise ValueError("Each injection must be an object")
        injection_id = injection.get("injection_id")
        if not isinstance(injection_id, str) or not injection_id or injection_id in seen:
            raise ValueError("injection_id must be nonempty and unique")
        seen.add(injection_id)
        if type(injection.get("order")) is not int or injection["order"] != order:
            raise ValueError("Injection order must be consecutive, starting at 1")
        strategy = injection.get("strategy")
        if not isinstance(strategy, str):
            raise ValueError("Injection requires a strategy")
        validate_parameters(strategy, injection.get("parameters"))
        if injection.get("pattern_type") != STRATEGY_TYPES[strategy]:
            raise ValueError("Injection pattern_type does not match its strategy")
        if not isinstance(injection.get("preset"), str) or not injection["preset"]:
            raise ValueError("Injection requires its preset")
        validate_seed(injection.get("seed"))
        selection = injection.get("selection")
        if not isinstance(selection, dict) or not all(
            isinstance(selection.get(key), dict) for key in ("requested", "resolved")
        ):
            raise ValueError("Injection selection requires requested and resolved targets")
        if selection.get("mode") not in {"explicit", "seeded"}:
            raise ValueError("Injection selection mode must be explicit or seeded")
        for field in ("event_ids", "case_ids"):
            _id_list(selection["resolved"].get(field), f"resolved {field}")
        validate_regions(injection.get("target_regions"))
        affected = injection.get("affected")
        if not isinstance(affected, dict) or affected.get("change_filter") != {
            "injection_id": injection_id
        }:
            raise ValueError("Affected rows must reference their injection_id in changes.parquet")
        for field in ("event_count", "case_count"):
            if type(affected.get(field)) is not int or affected[field] < 1:
                raise ValueError("An explicitly requested injection must change events and cases")
        if affected["case_count"] > affected["event_count"]:
            raise ValueError("Affected case count cannot exceed affected event count")


def validate_changes(changes: pd.DataFrame, manifest: dict) -> None:
    """Validate typed immediate pre/post records and per-injection references/counts."""
    if list(changes.columns) != CHANGE_SCHEMA.names or any(
        changes[name].dtype != pd.Series(dtype=dtype).dtype for name, dtype in CHANGE_DTYPES.items()
    ):
        raise ValueError("Changes must use the fixed typed CHANGE_SCHEMA")
    for column in ("injection_id", "event_id", "change_type"):
        if changes[column].isna().any() or changes[column].str.strip().eq("").any():
            raise ValueError(f"Missing {column} in changes")
    if not changes["change_type"].isin(["updated", "added", "removed"]).all():
        raise ValueError("change_type must be updated, added, or removed")
    if changes.duplicated(["injection_id", "event_id"]).any():
        raise ValueError("Only one change row per event per injection is allowed")
    for change_type, required, absent in (
        ("updated", ["before", "after"], []),
        ("added", ["after"], ["before"]),
        ("removed", ["before"], ["after"]),
    ):
        rows = changes.loc[changes["change_type"].eq(change_type)]
        for side in required:
            if rows[[f"case_id_{side}", f"timestamp_{side}_utc"]].isna().any().any():
                raise ValueError(f"{change_type} rows require {side} case and timestamp")
        for side in absent:
            if rows[[f"case_id_{side}", f"timestamp_{side}_utc"]].notna().any().any():
                raise ValueError(f"{change_type} rows must have null {side} case and timestamp")
    known = {injection["injection_id"] for injection in manifest["injections"]}
    if set(changes["injection_id"]) - known:
        raise ValueError("Change rows reference an unknown injection_id")
    for injection in manifest["injections"]:
        rows = changes.loc[changes["injection_id"].eq(injection["injection_id"])]
        cases = set(rows["case_id_before"].dropna()) | set(rows["case_id_after"].dropna())
        if (
            len(rows) != injection["affected"]["event_count"]
            or len(cases) != injection["affected"]["case_count"]
        ):
            raise ValueError("Affected counts do not agree with changes.parquet")


def _json(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    )


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def baseline_sha256(frame: pd.DataFrame) -> str:
    """Fingerprint every selected baseline value and dtype, keyed by stable event ID.

    Canonical Parquet bytes exclude transient indices and normalize the event time
    unit to ns, allowing lossless precision promotion during injection. Parquet
    also normalizes nullable payloads that can differ in memory after a reload.
    """
    canonical = frame.sort_values(EVENT_ID_COLUMN, kind="stable").reset_index(drop=True)
    canonical[TIMESTAMP_COLUMN] = canonical[TIMESTAMP_COLUMN].dt.as_unit("ns")
    try:
        return hashlib.sha256(canonical.to_parquet(engine="pyarrow", index=False)).hexdigest()
    except (pa.ArrowException, TypeError) as error:
        raise ValueError(
            f"Parquet cannot preserve the selected baseline schema: {error}"
        ) from error


def _ordered_ids(frame: pd.DataFrame) -> list[str]:
    return frame.sort_values([CASE_ID_COLUMN, TIMESTAMP_COLUMN, SOURCE_ROW_COLUMN], kind="stable")[
        EVENT_ID_COLUMN
    ].tolist()


def _timestamp_changes(
    before: pd.DataFrame, after: pd.DataFrame, injection_id: str
) -> pd.DataFrame:
    changed = before[TIMESTAMP_COLUMN].ne(after[TIMESTAMP_COLUMN])
    rows = pd.DataFrame(
        {
            "injection_id": injection_id,
            "event_id": before.loc[changed, EVENT_ID_COLUMN],
            "change_type": "updated",
            "case_id_before": before.loc[changed, CASE_ID_COLUMN],
            "case_id_after": after.loc[changed, CASE_ID_COLUMN],
            "timestamp_before_utc": before.loc[changed, TIMESTAMP_COLUMN],
            "timestamp_after_utc": after.loc[changed, TIMESTAMP_COLUMN],
            "derived_from_event_id": None,
            "before_values_json": None,
            "after_values_json": None,
        }
    )
    return rows.astype(CHANGE_DTYPES).reset_index(drop=True)


def _validate_final_regions(events: pd.DataFrame, injections: list[dict]) -> None:
    """Check gap emptiness and containment without repairing earlier regions."""
    for injection in injections:
        covered = set()
        for region in injection["target_regions"]:
            scope = region["case_scope"]
            scoped = events
            if scope["type"] == "selected":
                if set(scope["case_ids"]) - set(events[CASE_ID_COLUMN]):
                    raise ValueError("Region references unknown case IDs")
                scoped = scoped.loc[scoped[CASE_ID_COLUMN].isin(scope["case_ids"])]
            if "activity_scope" in region:
                if set(region["activity_scope"]) - set(events[ACTIVITY_COLUMN]):
                    raise ValueError("Region references unknown activities")
                scoped = scoped.loc[scoped[ACTIVITY_COLUMN].isin(region["activity_scope"])]
            if region["time_type"] == "interval":
                inside = scoped[TIMESTAMP_COLUMN].ge(pd.Timestamp(region["start_utc"])) & scoped[
                    TIMESTAMP_COLUMN
                ].lt(pd.Timestamp(region["end_utc"]))
            else:
                inside = scoped[TIMESTAMP_COLUMN].eq(pd.Timestamp(region["timestamp_utc"]))
            if injection["strategy"] == "shift_suffix" and inside.any():
                raise ValueError("A later injection invalidates an earlier gap region")
            covered.update(scoped.loc[inside, EVENT_ID_COLUMN])
        if (
            injection["strategy"] == "synchronize_events"
            and set(injection["selection"]["resolved"]["event_ids"]) - covered
        ):
            raise ValueError("A later injection invalidates an earlier batch region")


def _validate_gap_update(before: pd.DataFrame, injection: dict, rows: pd.DataFrame) -> None:
    selection = injection["selection"]
    expected = resolve_cutoff(
        before.reset_index(drop=True), selection["requested"], injection["seed"]
    )
    cutoff = utc_timestamp(selection["resolved"].get("cutoff_utc"), "cutoff_utc")
    duration = pd.Timedelta(injection["parameters"]["duration_minutes"], unit="min")
    if (
        selection != expected
        or set(rows["event_id"]) != set(expected["resolved"]["event_ids"])
        or not rows["timestamp_after_utc"].eq(rows["timestamp_before_utc"] + duration).all()
    ):
        raise ValueError("Gap change records do not match its target and duration")
    regions = injection["target_regions"]
    if (
        len(regions) != 1
        or regions[0].get("case_scope") != {"type": "all"}
        or regions[0].get("time_type") != "interval"
        or "activity_scope" in regions[0]
        or pd.Timestamp(regions[0]["start_utc"]) != cutoff
        or pd.Timestamp(regions[0]["end_utc"]) != cutoff + duration
    ):
        raise ValueError("Gap region does not match its cut-off and duration")


def _validate_batch_update(before: pd.DataFrame, after: pd.DataFrame, injection: dict) -> None:
    resolved = injection["selection"]["resolved"]
    ids = resolved["event_ids"]
    selected = before.loc[ids]
    center = utc_timestamp(resolved.get("center_utc"), "center_utc")
    jitter = pd.Timedelta(injection["parameters"]["jitter_seconds"], unit="s")
    assigned = resolved.get("assigned_timestamps_utc")
    requested = injection["selection"]["requested"]
    eligible = select_target_events(before.reset_index(drop=True), requested)
    if (
        len(ids) != injection["parameters"]["num_events"]
        or selected[CASE_ID_COLUMN].nunique() != len(ids)
        or set(ids) - set(eligible[EVENT_ID_COLUMN])
        or ("event_ids" in requested and set(ids) != set(requested["event_ids"]))
        or not isinstance(assigned, dict)
        or set(assigned) != set(ids)
        or sorted(selected[CASE_ID_COLUMN].unique()) != resolved.get("case_ids")
        or sorted(selected[ACTIVITY_COLUMN].unique()) != resolved.get("activities")
        or (
            "center_utc" in requested
            and utc_timestamp(requested["center_utc"], "center_utc") != center
        )
    ):
        raise ValueError(
            "Batch resolved targets do not match its settings or case/activity selection"
        )
    for event_id, timestamp in after[TIMESTAMP_COLUMN].items():
        if (
            utc_timestamp(assigned[event_id], "assigned timestamp") != timestamp
            or not center - jitter <= timestamp <= center + jitter
        ):
            raise ValueError("Batch timestamps do not match its resolved jitter assignment")


def validate_variant(
    events: pd.DataFrame,
    manifest: dict,
    changes: pd.DataFrame,
    *,
    baseline: pd.DataFrame | None = None,
) -> None:
    """Check the MVP contract and reverse immediate updates to verify the baseline.

    Verify the complete reconstructed baseline against its persisted content
    digest, including unchanged events and attributes. Reloading needs no original
    source file. Creation also compares directly with the selected source frame.
    """
    validate_manifest(manifest)
    validate_events(events, manifest["event_count_after"])
    validate_changes(changes, manifest)
    if not changes["change_type"].eq("updated").all():
        raise ValueError(
            "The MVP only executes timestamp updates; additions/removals are future work"
        )
    if changes["event_id"].duplicated().any():
        raise ValueError("An event may be modified by at most one injection in a variant")
    if set(events[CASE_ID_COLUMN]) != set(manifest["source"]["selection"]["resolved_case_ids"]):
        raise ValueError("Final cases do not match the selected baseline cases")
    restored = events.set_index(EVENT_ID_COLUMN, drop=False).copy()
    if set(changes["event_id"]) - set(restored.index):
        raise ValueError("Changes reference unknown stable event IDs")
    for injection in reversed(manifest["injections"]):
        rows = changes.loc[changes["injection_id"].eq(injection["injection_id"])]
        ids = rows["event_id"].tolist()
        actual = restored.loc[ids]
        if (
            actual[CASE_ID_COLUMN].tolist() != rows["case_id_after"].tolist()
            or actual[TIMESTAMP_COLUMN].tolist() != rows["timestamp_after_utc"].tolist()
            or rows["case_id_before"].tolist() != rows["case_id_after"].tolist()
            or rows["timestamp_before_utc"].eq(rows["timestamp_after_utc"]).any()
            or rows[["before_values_json", "after_values_json"]].notna().any().any()
        ):
            raise ValueError("Immediate change records do not agree with the resulting event log")
        resolved_ids = injection["selection"]["resolved"].get("event_ids")
        if (
            not isinstance(resolved_ids, list)
            or len(set(resolved_ids)) != len(resolved_ids)
            or not set(ids).issubset(resolved_ids)
            or set(resolved_ids) - set(restored.index)
        ):
            raise ValueError("Resolved target event IDs do not agree with change records")
        selected_after = restored.loc[resolved_ids].copy()
        order_after = _ordered_ids(restored)
        restored.loc[ids, TIMESTAMP_COLUMN] = rows["timestamp_before_utc"].array
        if _ordered_ids(restored) != order_after:
            raise ValueError("Injection violates predecessor/successor order within a case")
        if injection["strategy"] == "shift_suffix":
            _validate_gap_update(restored, injection, rows)
        else:
            _validate_batch_update(restored, selected_after, injection)
    restored = restored.reset_index(drop=True)
    validate_events(restored, manifest["event_count_before"])
    if baseline_sha256(restored) != manifest["source"]["selected_baseline_sha256"]:
        raise ValueError(
            "Change records cannot reconstruct the selected baseline: unrecorded changes"
        )
    if baseline is not None:
        try:
            restored[TIMESTAMP_COLUMN] = restored[TIMESTAMP_COLUMN].array.as_unit(
                baseline[TIMESTAMP_COLUMN].dtype.unit, round_ok=False
            )
            assert_frame_equal(baseline.reset_index(drop=True), restored, check_exact=True)
        except (AssertionError, ValueError) as error:
            raise ValueError("Change records cannot reconstruct the selected baseline") from error
    _validate_final_regions(events, manifest["injections"])


def _resolve_recipe(recipe: list[dict], catalog: dict, seed: int) -> list[dict]:
    if not isinstance(recipe, list):
        raise ValueError("Recipe must be an ordered JSON list (empty for a control)")
    resolved = []
    for entry in recipe:
        if not isinstance(entry, dict) or set(entry) - {"preset", "parameters", "target", "seed"}:
            raise ValueError("Recipe entries accept only preset, parameters, target, and seed")
        effective = resolve_preset(catalog, entry.get("preset"), entry.get("parameters"))
        effective["preset"] = entry["preset"]
        effective["target"] = copy.deepcopy(entry.get("target", {}))
        if not isinstance(effective["target"], dict):
            raise ValueError("Recipe target must be an object")
        effective["seed"] = entry.get("seed", seed)
        validate_seed(effective["seed"])
        if effective["strategy"] not in STRATEGIES:
            raise ValueError(f"Strategy {effective['strategy']!r} is not implemented yet")
        resolved.append(effective)
    return resolved


def create_variant(
    input_path: Path | str,
    recipe: list[dict],
    *,
    sample_cases: int | None = None,
    case_ids: list[str] | None = None,
    seed: int = 42,
    catalog_path: Path | str = CATALOG_PATH,
) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """Create one independent variant from a Phase-1 Parquet/JSON pair, without writing.

    The return value is ``(events, manifest, changes)``. An empty recipe produces
    a control. No input is modified and no other injected variant is loaded.
    """
    validate_seed(seed)
    settings = _resolve_recipe(recipe, load_catalog(catalog_path), seed)
    path = Path(input_path)
    if path.suffix != ".parquet":
        raise ValueError("Phase-2 input must be a Phase-1 .parquet log with JSON provenance")
    original = load_processed_event_log(path)
    metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    for field in ("dataset_id", "split_group_id"):
        if not isinstance(metadata.get(field), str) or not metadata[field].strip():
            raise ValueError(f"Phase-1 provenance requires {field}")
    baseline, selection = select_complete_cases(
        original, sample_cases=sample_cases, case_ids=case_ids, seed=seed
    )
    source = {
        "processed_path": str(path),
        "processed_sha256": metadata["processed_sha256"],
        "processed_metadata_path": str(path.with_suffix(".json")),
        "processed_metadata_sha256": _sha256(path.with_suffix(".json")),
        "selection": selection,
        "selected_baseline_sha256": baseline_sha256(baseline),
    }
    for key in ("source_file", "source_sha256", "source_id", "source_url", "processing_config"):
        if key in metadata:
            source[key] = metadata[key]
    events = baseline.copy()
    injections = []
    tables = []
    for order, setting in enumerate(settings, 1):
        injection_id = f"inj_{order:03d}"
        target = (
            resolve_cutoff(events, setting["target"], setting["seed"])
            if setting["strategy"] == "shift_suffix"
            else resolve_batch_target(
                events, setting["target"], setting["parameters"], setting["seed"]
            )
        )
        changed_ids = {event_id for table in tables for event_id in table["event_id"]}
        if changed_ids.intersection(target["resolved"]["event_ids"]):
            raise ValueError(
                "Overlapping injections: a later target includes an already changed event"
            )
        transformed, regions = STRATEGIES[setting["strategy"]](
            events, setting["parameters"], target, setting["seed"]
        )
        rows = _timestamp_changes(events, transformed, injection_id)
        if rows.empty:
            raise ValueError(
                "Explicitly requested injection changes no events; use [] for a control"
            )
        injections.append(
            {
                "injection_id": injection_id,
                "order": order,
                "pattern_type": setting["type"],
                "strategy": setting["strategy"],
                "preset": setting["preset"],
                "parameters": setting["parameters"],
                "seed": setting["seed"],
                "selection": target,
                "target_regions": regions,
                "affected": {
                    "event_count": len(rows),
                    "case_count": int(rows["case_id_after"].nunique()),
                    "change_filter": {"injection_id": injection_id},
                },
            }
        )
        tables.append(rows)
        events = transformed
        _validate_final_regions(events, injections)
    identity = {
        "schema_version": SCHEMA_VERSION,
        "processed_sha256": source["processed_sha256"],
        "selection": selection,
        "dataset_id": metadata["dataset_id"],
        "split_group_id": metadata["split_group_id"],
        "injections": [
            {
                **{
                    name: injection[name]
                    for name in ("pattern_type", "strategy", "preset", "parameters", "seed")
                },
                "target": injection["selection"]["resolved"],
            }
            for injection in injections
        ],
    }
    digest = hashlib.sha256(_json(identity).encode("utf-8")).hexdigest()[:16]
    types = {setting["type"] for setting in settings}
    prefix = (
        "control"
        if not types
        else "gap"
        if types == {"temporal_gap"}
        else "batch"
        if types == {"batching"}
        else "mixed"
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "variant_id": f"{prefix}_{digest}",
        "dataset_id": metadata["dataset_id"],
        "split_group_id": metadata["split_group_id"],
        "source": source,
        "event_changes_file": "changes.parquet",
        "event_count_before": len(baseline),
        "event_count_after": len(events),
        "injections": injections,
        "event_id_column": EVENT_ID_COLUMN,
        "source_row_column": SOURCE_ROW_COLUMN,
        "storage_format": "parquet",
        "software_versions": {
            "pandas": pd.__version__,
            "pyarrow": pa.__version__,
            "pm4py": version("pm4py"),
        },
    }
    changes = pd.concat(tables, ignore_index=True) if tables else changes_frame()
    validate_variant(events, manifest, changes, baseline=baseline)
    return events, manifest, changes


def _file_contract(path: Path) -> dict:
    return {
        "sha256": _sha256(path),
        "schema": [
            {"name": field.name, "type": str(field.type), "nullable": field.nullable}
            for field in pq.read_schema(path)
        ],
    }


def save_variant(
    events: pd.DataFrame, manifest: dict, changes: pd.DataFrame, output_root: Path | str
) -> Path:
    """Validate round trips and publish exactly three files; never replace a result.

    Files are staged before exclusively reserving the variant directory. Each
    publication is atomic; raised errors roll back only this invocation's files.
    Readers reject incomplete directories, including interrupted publications.
    """
    validate_variant(events, manifest, changes)
    variant_id = manifest["variant_id"]
    dataset_folder = re.sub(r"[^a-zA-Z0-9_-]+", "_", manifest["dataset_id"]).strip("_") or "dataset"
    parent = Path(output_root) / dataset_folder
    output = parent / variant_id
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Variant output already exists: {output}")
    parent.mkdir(parents=True, exist_ok=True)
    stored = copy.deepcopy(manifest)
    with TemporaryDirectory(prefix=".variant-", dir=parent) as directory:
        staged = Path(directory)
        try:
            events.to_parquet(staged / "events.parquet", engine="pyarrow", index=False)
            table = pa.Table.from_pandas(changes, schema=CHANGE_SCHEMA, preserve_index=False)
            pq.write_table(table, staged / "changes.parquet")
            assert_frame_equal(
                events.reset_index(drop=True),
                pd.read_parquet(staged / "events.parquet"),
                check_exact=True,
            )
            assert_frame_equal(
                changes.reset_index(drop=True),
                pd.read_parquet(staged / "changes.parquet"),
                check_exact=True,
            )
        except (pa.ArrowException, AssertionError, TypeError) as error:
            raise ValueError(f"Parquet cannot preserve the variant schema: {error}") from error
        stored["files"] = {
            name: _file_contract(staged / name) for name in ("events.parquet", "changes.parquet")
        }
        (staged / "manifest.json").write_text(
            json.dumps(stored, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
            + "\n",
            encoding="utf-8",
        )
        load_variant(staged)
        # Exclusive reservation refuses concurrent writers and existing empty directories.
        output.mkdir()
        published = []
        try:
            for name in ("events.parquet", "changes.parquet", "manifest.json"):
                destination = output / name
                os.link(staged / name, destination)
                published.append(destination)
        except OSError:
            for destination in reversed(published):
                destination.unlink()
            output.rmdir()
            raise
    return output


def load_variant(path: Path | str) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """Read the three-file contract and verify hashes, schemas, references, and updates."""
    directory = Path(path)
    if {entry.name for entry in directory.iterdir()} != VARIANT_FILES:
        raise ValueError(
            "Variant must contain exactly events.parquet, changes.parquet, manifest.json"
        )
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    validate_manifest(manifest)
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != {"events.parquet", "changes.parquet"}:
        raise ValueError("Manifest requires Parquet file hashes and schemas")
    for name, contract in files.items():
        if contract != _file_contract(directory / name):
            raise ValueError(f"Variant checksum or schema mismatch: {name}")
    if not pq.read_schema(directory / "changes.parquet").equals(
        CHANGE_SCHEMA, check_metadata=False
    ):
        raise ValueError("changes.parquet does not use the fixed typed CHANGE_SCHEMA")
    events = pd.read_parquet(directory / "events.parquet", engine="pyarrow")
    changes = pd.read_parquet(directory / "changes.parquet", engine="pyarrow")
    validate_variant(events, manifest, changes)
    return events, manifest, changes
