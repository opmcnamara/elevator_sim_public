"""Passenger metrics and human-readable observations."""

from __future__ import annotations

from collections import Counter
from statistics import fmean, median
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .simulation import SimulationResult


WAIT_TARGET_TICKS = 30
LONG_WAIT_TICKS = 45


def _percentile(values: list[int], percentile: float) -> float:
    """Compute a linearly interpolated percentile without third-party packages."""

    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * percentile
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _distribution(values: list[int]) -> dict[str, float | int]:
    return {
        "min": min(values),
        "max": max(values),
        "average": round(fmean(values), 3),
        "median": round(float(median(values)), 3),
        "p95": round(_percentile(values, 0.95), 3),
    }


def _express_elevator_summary(result: "SimulationResult") -> dict[str, object]:
    """Describe the express-car configuration used for a simulation run."""

    express_count = result.config.num_express_elevators
    first_express_id = result.config.num_elevators - express_count + 1
    return {
        "enabled": express_count > 0,
        "count": express_count,
        "elevator_ids": list(
            range(first_express_id, result.config.num_elevators + 1)
        ),
        "served_floors": list(result.config.express_floors),
    }


def build_summary(result: "SimulationResult") -> dict[str, object]:
    passengers = result.passengers
    wait_times = [p.wait_time for p in passengers if p.wait_time is not None]
    travel_times = [p.travel_time for p in passengers if p.travel_time is not None]
    total_times = [p.total_time for p in passengers if p.total_time is not None]
    assignments = Counter(p.assigned_elevator for p in passengers)

    if not passengers:
        return {
            "passenger_count": 0,
            "scheduler": result.scheduler_name,
            "scheduler_parameters": result.scheduler_parameters,
            "express_elevators": _express_elevator_summary(result),
            "finished_at": result.finished_at,
            "wait_time": None,
            "travel_time": None,
            "total_time": None,
            "assignments_per_elevator": {
                str(index): 0 for index in range(1, result.config.num_elevators + 1)
            },
            "max_occupancy": {
                str(key): value for key, value in result.max_occupancy.items()
            },
            "observations": ["No passenger requests were supplied."],
        }

    assert len(wait_times) == len(passengers)
    assert len(travel_times) == len(passengers)
    assert len(total_times) == len(passengers)
    within_wait_target = sum(wait <= WAIT_TARGET_TICKS for wait in wait_times)
    within_wait_target_percentage = 100 * within_wait_target / len(passengers)
    long_waits = sum(wait > LONG_WAIT_TICKS for wait in wait_times)
    long_wait_percentage = 100 * long_waits / len(passengers)
    zero_wait = sum(wait == 0 for wait in wait_times)
    observations = [
        f"{zero_wait}/{len(passengers)} passengers were picked up immediately.",
        (
            f"{within_wait_target_percentage:.1f}% of passengers were picked up "
            f"within {WAIT_TARGET_TICKS} ticks."
        ),
        (
            f"{long_wait_percentage:.1f}% of passengers waited longer than "
            f"{LONG_WAIT_TICKS} ticks."
        ),
        f"The slowest passenger completed in {max(total_times)} ticks.",
    ]

    return {
        "passenger_count": len(passengers),
        "scheduler": result.scheduler_name,
        "scheduler_parameters": result.scheduler_parameters,
        "express_elevators": _express_elevator_summary(result),
        "finished_at": result.finished_at,
        "wait_time": _distribution(wait_times),
        "travel_time": _distribution(travel_times),
        "total_time": _distribution(total_times),
        "assignments_per_elevator": {
            str(index): assignments[index]
            for index in range(1, result.config.num_elevators + 1)
        },
        "max_occupancy": {
            str(key): value for key, value in result.max_occupancy.items()
        },
        "observations": observations,
    }
