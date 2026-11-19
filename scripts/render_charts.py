"""Export clean Dotted Charts from one validated Phase-2 variant."""

import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd

from rendering.export import DEFAULT_OUTPUT_ROOT, export_charts
from rendering.renderer import RenderStyle
from rendering.views import ViewSpec, load_chart_inputs


def main(argv: list[str] | None = None) -> int:
    """Translate explicit CLI options to the shared view and export API."""
    defaults = RenderStyle()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--variant", required=True, type=Path, help="Saved Phase-2 variant directory"
    )
    parser.add_argument(
        "--source-root", type=Path, default=Path("."), help="Base for relative Phase-1 paths"
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--role", choices=("baseline", "modified", "both"), default="both")
    parser.add_argument("--view", choices=("full", "time_window", "focused"), default="full")
    parser.add_argument("--start-utc", help="Inclusive UTC start for time_window")
    parser.add_argument("--end-utc", help="Exclusive UTC end for time_window")
    parser.add_argument("--injection-id", help="Injection reference for focused")
    parser.add_argument("--region-id", help="Target region reference for focused")
    parser.add_argument(
        "--context-hours", type=float, help="Positive padding on both sides of a region"
    )
    parser.add_argument(
        "--case-id", action="append", help="Displayed case ID; repeat to include more"
    )
    parser.add_argument(
        "--activity", action="append", help="Displayed activity; repeat to include more"
    )
    parser.add_argument("--width-px", type=int, default=defaults.width_px)
    parser.add_argument("--height-px", type=int, default=defaults.height_px)
    parser.add_argument("--dpi", type=int, default=defaults.dpi)
    parser.add_argument(
        "--marker-size",
        type=float,
        default=defaults.marker_size,
        help="Marker area in points squared",
    )
    parser.add_argument("--alpha", type=float, default=defaults.alpha)
    parser.add_argument("--palette", default=defaults.palette, help="Matplotlib colormap name")
    parser.add_argument(
        "--legend", action="store_true", help="Show the shared activity legend if it fits"
    )
    parser.add_argument("--background", default=defaults.background)
    parser.add_argument("--max-case-tick-labels", type=int, default=defaults.max_case_tick_labels)
    args = parser.parse_args(argv)
    try:
        if args.context_hours is not None and (
            not math.isfinite(args.context_hours) or args.context_hours <= 0
        ):
            raise ValueError("--context-hours must be positive and finite")
        view = ViewSpec(
            mode=args.view,
            start_utc=args.start_utc,
            end_utc=args.end_utc,
            injection_id=args.injection_id,
            region_id=args.region_id,
            context=pd.Timedelta(hours=args.context_hours)
            if args.context_hours is not None
            else None,
            case_ids=args.case_id,
            activities=args.activity,
        )
        style = RenderStyle(
            width_px=args.width_px,
            height_px=args.height_px,
            dpi=args.dpi,
            marker_size=args.marker_size,
            alpha=args.alpha,
            palette=args.palette,
            legend=args.legend,
            background=args.background,
            max_case_tick_labels=args.max_case_tick_labels,
        )
        inputs = load_chart_inputs(args.variant, source_root=args.source_root)
        outputs = export_charts(
            inputs, view=view, role=args.role, style=style, output_root=args.output_root
        )
        for role, path in outputs.items():
            rendering = json.loads((path / "rendering.json").read_text(encoding="utf-8"))
            print(f"{role} {rendering['chart_id']} ({rendering['view_id']}): {path}")
            for diagnostic in rendering["diagnostics"]:
                print(f"{role}: {diagnostic}", file=sys.stderr)
    except (OSError, ValueError, OverflowError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
