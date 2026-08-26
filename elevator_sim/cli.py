"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .io import read_requests, write_results
from .models import SimulationConfig
from .schedulers import make_scheduler
from .simulation import Simulation
from .statistics import build_summary


def parse_floor_list(value: str) -> tuple[int, ...]:
    """Parse a comma-separated CLI floor list."""

    try:
        floors = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "express floors must be comma-separated integers"
        ) from error
    if not floors:
        raise argparse.ArgumentTypeError("express floors cannot be empty")
    return floors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a discrete-time destination-dispatch elevator simulation."
    )
    parser.add_argument("input", type=Path, help="CSV with time,id,source,dest columns")
    parser.add_argument(
        "--elevators",
        type=int,
        default=8,
        help="number of elevators (default: 8)",
    )
    parser.add_argument("--floors", type=int, default=50, help="number of floors")
    parser.add_argument("--capacity", type=int, default=8, help="passengers per car")
    parser.add_argument("--start-floor", type=int, default=1, help="initial car floor")
    parser.add_argument(
        "--express-elevators",
        type=int,
        default=0,
        help="number of restricted express cars (default: 0)",
    )
    parser.add_argument(
        "--express-floors",
        type=parse_floor_list,
        default=(),
        metavar="FLOOR,...",
        help="comma-separated floors served by every express car",
    )
    parser.add_argument(
        "--scheduler",
        choices=("eta", "fair-eta", "nearest", "round-robin"),
        default="eta",
        help="assignment algorithm (default: eta)",
    )
    parser.add_argument(
        "--acceptable-wait",
        type=int,
        default=None,
        metavar="TICKS",
        help=(
            "wait threshold used only by fair-eta; later ticks receive a "
            "heavier cost (default: 30)"
        ),
    )
    parser.add_argument(
        "--late-wait-multiplier",
        type=float,
        default=None,
        metavar="MULTIPLIER",
        help=(
            "quadratic excess-wait penalty used only by fair-eta "
            "(default: 10)"
        ),
    )

    ## Maybe add required for file output, or the name automatically incorporates input CSV fiile name by default
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("test_results/simulation_output"),
        help=(
            "directory for CSV and JSON results "
            "(default: test_results/simulation_output)"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = SimulationConfig(
            num_elevators=args.elevators,
            num_floors=args.floors,
            capacity=args.capacity,
            start_floor=args.start_floor,
            num_express_elevators=args.express_elevators,
            express_floors=args.express_floors,
        )
        result = Simulation(
            config,
            make_scheduler(
                args.scheduler,
                acceptable_wait=args.acceptable_wait,
                late_wait_multiplier=args.late_wait_multiplier,
            ),
        ).run(read_requests(args.input))
        paths = write_results(result, args.output)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(json.dumps(build_summary(result), indent=2))
    print("\nWrote:")
    for name, path in paths.items():
        print(f"  {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
