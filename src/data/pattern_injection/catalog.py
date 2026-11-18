"""Small JSON catalog of candidate classes and executable strategy presets."""

import copy
import json
import math
import re
from pathlib import Path

CATALOG_PATH = Path(__file__).parent / "configs" / "pattern_catalog.json"
STRATEGY_TYPES = {"shift_suffix": "temporal_gap", "synchronize_events": "batching"}


def validate_parameters(strategy: str, parameters: dict) -> None:
    """Reject unknown strategies, misspelled options, and nonfinite parameters."""
    if not isinstance(strategy, str) or strategy not in STRATEGY_TYPES:
        raise ValueError(f"Unsupported strategy: {strategy!r}")
    required = (
        {"duration_minutes"} if strategy == "shift_suffix" else {"num_events", "jitter_seconds"}
    )
    if not isinstance(parameters, dict) or set(parameters) != required:
        raise ValueError(f"{strategy} parameters must be exactly {sorted(required)}")
    for name, value in parameters.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be a finite nonnegative number")
        try:
            valid = math.isfinite(value) and value >= 0
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError(f"{name} must be a finite nonnegative number")
    if strategy == "shift_suffix" and parameters["duration_minutes"] <= 0:
        raise ValueError("duration_minutes must be positive")
    if strategy == "synchronize_events" and (
        type(parameters["num_events"]) is not int or parameters["num_events"] < 2
    ):
        raise ValueError("num_events must be an integer of at least 2")


def load_catalog(path: Path | str = CATALOG_PATH) -> dict:
    """Load candidate labels and validate every preset; future labels have no algorithm."""
    catalog = json.loads(Path(path).read_text(encoding="utf-8"))
    if (
        not isinstance(catalog, dict)
        or type(catalog.get("version")) is not int
        or catalog["version"] != 1
    ):
        raise ValueError("Unsupported or missing pattern catalog version")
    classes = catalog.get("classes")
    if (
        not isinstance(classes, list)
        or not classes
        or any(not isinstance(label, str) or not label.strip() for label in classes)
        or len(set(classes)) != len(classes)
    ):
        raise ValueError("Catalog classes must be unique nonempty strings")
    presets = catalog.get("presets")
    if not isinstance(presets, dict):
        raise ValueError("Catalog presets must be an object")
    for name, preset in presets.items():
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", name):
            raise ValueError(f"Invalid preset name: {name!r}")
        if not isinstance(preset, dict) or set(preset) != {"type", "strategy", "parameters"}:
            raise ValueError(f"Invalid preset: {name!r}")
        strategy = preset["strategy"]
        if not isinstance(strategy, str):
            raise ValueError(f"Invalid strategy in preset {name!r}")
        validate_parameters(strategy, preset["parameters"])
        if preset["type"] != STRATEGY_TYPES[strategy] or preset["type"] not in classes:
            raise ValueError(f"Preset {name!r} has an incompatible candidate type")
    return catalog


def resolve_preset(catalog: dict, name: str, parameters: dict | None = None) -> dict:
    """Copy a preset and apply explicitly supplied parameter overrides."""
    if not isinstance(name, str) or name not in catalog["presets"]:
        raise ValueError(f"Unknown preset: {name!r}")
    preset = copy.deepcopy(catalog["presets"][name])
    if parameters is not None:
        if not isinstance(parameters, dict):
            raise ValueError("Parameter overrides must be an object")
        preset["parameters"].update(parameters)
    validate_parameters(preset["strategy"], preset["parameters"])
    # Numerically equivalent JSON/CLI settings share an effective identity.
    for key in ("duration_minutes", "jitter_seconds"):
        if key in preset["parameters"]:
            preset["parameters"][key] = float(preset["parameters"][key])
    return preset
