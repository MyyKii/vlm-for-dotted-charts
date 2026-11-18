"""Create a reproducible Phase-2 variant from a standardized Phase-1 event log."""

import argparse
import json
import sys
from pathlib import Path

from data.pattern_injection.catalog import CATALOG_PATH
from data.pattern_injection.engine import create_variant, save_variant


def main(argv: list[str] | None = None) -> int:
    """Parse a preset/recipe and delegate transformations and persistence to the engine."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Phase-1 .parquet + .json pair")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--preset", help="Preset name in the catalog")
    source.add_argument("--recipe", type=Path, help="Ordered JSON list; [] creates a control")
    parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    subset = parser.add_mutually_exclusive_group()
    subset.add_argument("--sample-cases", type=int, help="Number of complete cases to sample")
    subset.add_argument("--case-id", action="append", help="Baseline case ID; repeat for multiple")
    parser.add_argument(
        "--seed", type=int, default=42, help="Sampling/injection seed (default: 42)"
    )
    parser.add_argument("--cutoff-utc", help="Explicit gap cut-off; otherwise seeded")
    parser.add_argument("--duration-minutes", type=float, help="Override gap preset duration")
    parser.add_argument("--center-utc", help="Explicit batch center; otherwise seeded")
    parser.add_argument("--start-utc", help="Batch eligibility interval start (inclusive)")
    parser.add_argument("--end-utc", help="Batch eligibility interval end (exclusive)")
    parser.add_argument("--target-case-id", action="append", help="Eligible batch case; repeat")
    parser.add_argument("--event-id", action="append", help="Explicit batch event ID; repeat")
    parser.add_argument("--activity", action="append", help="Eligible batch activity; repeat")
    parser.add_argument("--num-events", type=int, help="Override batch size (distinct cases)")
    parser.add_argument("--jitter-seconds", type=float, help="Override batch jitter radius")
    parser.add_argument("--output-root", type=Path, default=Path("data/processed/injected"))
    args = parser.parse_args(argv)
    target = {
        key: value
        for key, value in {
            "cutoff_utc": args.cutoff_utc,
            "center_utc": args.center_utc,
            "start_utc": args.start_utc,
            "end_utc": args.end_utc,
            "case_ids": args.target_case_id,
            "event_ids": args.event_id,
            "activities": args.activity,
        }.items()
        if value is not None
    }
    parameters = {
        key: value
        for key, value in {
            "duration_minutes": args.duration_minutes,
            "num_events": args.num_events,
            "jitter_seconds": args.jitter_seconds,
        }.items()
        if value is not None
    }
    if args.recipe is not None and (target or parameters):
        parser.error(
            "Target and parameter flags require --preset; put per-instance settings in the recipe"
        )
    try:
        if args.recipe is not None:
            recipe = json.loads(args.recipe.read_text(encoding="utf-8"))
        else:
            recipe = [
                {
                    "preset": args.preset,
                    "seed": args.seed,
                    "target": target,
                    "parameters": parameters,
                }
            ]
        events, manifest, changes = create_variant(
            args.input,
            recipe,
            sample_cases=args.sample_cases,
            case_ids=args.case_id,
            seed=args.seed,
            catalog_path=args.catalog,
        )
        output = save_variant(events, manifest, changes, args.output_root)
    except (OSError, ValueError, TypeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(f"Variant: {manifest['variant_id']}")
    print(f"Events: {len(events)}")
    print(f"Injections: {len(manifest['injections'])}")
    print(f"Changed events: {len(changes)}")
    print(f"Output: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
