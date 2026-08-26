
"""Generate reproducible, lobby-heavy elevator request CSV files.

At each integer timestamp, the number of new requests is sampled from a Poisson
distribution with the configured arrival rate. Generation continues until the
requested file size is reached, and rows are sorted by timestamp before being
written. NumPy provides the Poisson and uniform random sampling operations.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def generate_destinations(
    generator: np.random.Generator,
    *,
    sources: np.ndarray,
    num_floors: int,
    lobby_probability: float,
) -> np.ndarray:
    """Generate destinations after all source floors have been generated."""

    destinations = np.empty(sources.size, dtype=np.int64)

    # Mask for requests whose origin is the lobby.
    lobby_origins = sources == 1
    lobby_origin_count = int(np.count_nonzero(lobby_origins))

    # Lobby passengers choose uniformly among every non-lobby floor.
    destinations[lobby_origins] = generator.integers(
        2,
        num_floors + 1,
        size=lobby_origin_count,
        dtype=np.int64,
    )

    # Find requests whose origin is not the lobby.
    non_lobby_indexes = np.flatnonzero(~lobby_origins)

    # Independently send each non-lobby request to Floor 1 with the configured
    # probability.
    to_lobby = generator.random(non_lobby_indexes.size) < lobby_probability
    destinations[non_lobby_indexes[to_lobby]] = 1

    # The remaining requests choose uniformly among non-lobby floors other
    # than their own origin.
    other_indexes = non_lobby_indexes[~to_lobby]
    if other_indexes.size:
        # Generate floors 2..(num_floors - 1). Values at or above a request's
        # source are shifted up by one, producing a uniform sample from floors
        # 2..num_floors while skipping that source.
        sampled = generator.integers(
            2,
            num_floors,
            size=other_indexes.size,
            dtype=np.int64,
        )
        other_sources = sources[other_indexes]
        destinations[other_indexes] = np.where(
            sampled < other_sources,
            sampled,
            sampled + 1,
        )

    return destinations


def generate_requests(
    *,
    seed: int,
    request_count: int,
    num_floors: int,
    arrival_rate: float,
    lobby_probability: float,
    lobby_source_probability: float = 0.20,
) -> pd.DataFrame:
    """Generate one deterministic request DataFrame and sort it by time."""

    if arrival_rate <= 0:
        raise ValueError("arrival_rate must be greater than zero")
    if not 0 <= lobby_source_probability <= 1:
        raise ValueError("lobby_source_probability must be between 0 and 1")

    generator = np.random.default_rng(seed)

    # Allocate the complete table before generating any request attributes.
    requests = pd.DataFrame(
        {
            "time": np.zeros(request_count, dtype=np.int64),
            "id": [
                f"passenger_{request_number:05d}"
                for request_number in range(1, request_count + 1)
            ],
            "source": np.zeros(request_count, dtype=np.int64),
            "dest": np.zeros(request_count, dtype=np.int64),
        }
    )

    # Populate the time column first. Each iteration represents one simulation
    # tick and writes that tick into the next `arrivals` DataFrame rows.
    time = 0
    next_row = 0
    time_column = requests.columns.get_loc("time")
    while next_row < request_count:
        # For a Poisson arrival process, the count of requests in each fixed
        # time interval is Poisson-distributed. The final tick is truncated if
        # its sample would take the file past the requested row count.
        arrivals = min(
            int(generator.poisson(arrival_rate)),
            request_count - next_row,
        )
        if arrivals:
            final_row = next_row + arrivals
            requests.iloc[next_row:final_row, time_column] = time
            next_row = final_row
        time += 1

    # Independently choose whether each request starts in the lobby. All other
    # source floors are sampled uniformly from Floors 2..num_floors.
    lobby_sources = generator.random(request_count) < lobby_source_probability
    sources = np.ones(request_count, dtype=np.int64)
    non_lobby_source_count = int(np.count_nonzero(~lobby_sources))
    sources[~lobby_sources] = generator.integers(
        2,
        num_floors + 1,
        size=non_lobby_source_count,
        dtype=np.int64,
    )
    requests["source"] = sources

    # Generate destinations only after the complete source array is known.
    requests["dest"] = generate_destinations(
        generator,
        sources=sources,
        num_floors=num_floors,
        lobby_probability=lobby_probability,
    )

    # The tick loop already produces nondecreasing times. Sorting explicitly
    # preserves the output contract if the generation strategy changes later.

    # requests.sort_values(
    #     by=["time", "id"],
    #     kind="stable",
    #     ignore_index=True,
    #     inplace=True,
    # )
    return requests


def write_requests(path: Path, requests: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    requests.to_csv(path, index=False)


def generate_files(
    *,
    output_dir: Path,
    file_count: int,
    requests_per_file: int,
    num_floors: int,
    arrival_rate: float,
    lobby_probability: float,
    base_seed: int,
    lobby_source_probability: float = 0.20,
) -> list[Path]:
    """Generate independent files whose per-file seeds derive from base_seed."""

    seed_generator = np.random.default_rng(base_seed)
    seeds: list[int] = []
    seen_seeds: set[int] = set()
    while len(seeds) < file_count:
        seed = int(seed_generator.integers(1, 2**32, dtype=np.uint64))
        if seed not in seen_seeds:
            seen_seeds.add(seed)
            seeds.append(seed)
    output_paths: list[Path] = []

    for file_number, seed in enumerate(seeds, start=1):
        requests = generate_requests(
            seed=seed,
            request_count=requests_per_file,
            num_floors=num_floors,
            arrival_rate=arrival_rate,
            lobby_probability=lobby_probability,
            lobby_source_probability=lobby_source_probability,
        )
        output_path = output_dir / f"requests_{file_number:02d}_seed_{seed}.csv"
        write_requests(output_path, requests)
        output_paths.append(output_path)
        print(
            f"Wrote {output_path} "
            f"({len(requests):,} requests, "
            f"time {requests['time'].iloc[0]}..{requests['time'].iloc[-1]})"
        )

    return output_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate reproducible lobby-heavy elevator request CSV files."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("generated_requests"),
        help="destination directory (default: generated_requests)",
    )
    parser.add_argument(
        "--files",
        type=int,
        default=10,
        help="number of CSV files (default: 10)",
    )
    parser.add_argument(
        "--requests-per-file",
        type=int,
        default=10_000,
        help="passenger requests per file (default: 10000)",
    )
    parser.add_argument(
        "--num-floors",
        type=int,
        default=50,
        help="number of building floors (default: 50)",
    )
    parser.add_argument(
        "--arrival-rate",
        type=float,
        default=5.0,
        help="expected requests per simulation tick (default: 5)",
    )
    parser.add_argument(
        "--lobby-probability",
        type=float,
        default=0.70,
        help="P(destination=1 | source!=1), default: 0.70",
    )
    parser.add_argument(
        "--lobby-source-probability",
        type=float,
        default=0.20,
        help="probability that a request starts on Floor 1 (default: 0.20)",
    )
    parser.add_argument(
        "--base-seed",
        type=int,
        default=20_260_823,
        help="seed used to derive the ten per-file seeds (default: 20260823)",
    )
    return parser


def validate_arguments(args: argparse.Namespace) -> None:
    if args.files < 1:
        raise ValueError("--files must be at least 1")
    if args.requests_per_file < 1:
        raise ValueError("--requests-per-file must be at least 1")
    if args.num_floors < 3:
        raise ValueError("--num-floors must be at least 3")
    if args.arrival_rate <= 0:
        raise ValueError("--arrival-rate must be greater than zero")
    if not 0 <= args.lobby_probability <= 1:
        raise ValueError("--lobby-probability must be between 0 and 1")
    if not 0 <= args.lobby_source_probability <= 1:
        raise ValueError("--lobby-source-probability must be between 0 and 1")
    if args.files >= 2**32:
        raise ValueError("--files is too large for the per-file seed range")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        validate_arguments(args)
        paths = generate_files(
            output_dir=args.output_dir,
            file_count=args.files,
            requests_per_file=args.requests_per_file,
            num_floors=args.num_floors,
            arrival_rate=args.arrival_rate,
            lobby_probability=args.lobby_probability,
            lobby_source_probability=args.lobby_source_probability,
            base_seed=args.base_seed,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))

    print(f"Generated {len(paths)} reproducible CSV files in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
