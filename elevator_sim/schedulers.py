"""Pluggable destination-dispatch assignment policies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from math import isfinite

from .elevator import Elevator
from .models import Direction, PassengerRequest


class Scheduler(ABC):
    name: str

    @property
    def parameters(self) -> dict[str, int | float]:
        """Serializable scheduler settings used for reproducible output."""

        return {}

    @abstractmethod
    def select_elevator(
        self,
        elevators: list[Elevator],
        passenger: PassengerRequest,
        current_time: int,
    ) -> Elevator:
        """Choose an elevator without mutating simulation state."""


def eligible_elevators(
    elevators: list[Elevator], passenger: PassengerRequest
) -> list[Elevator]:
    """Return cars permitted to serve both endpoints of the request."""

    eligible = [
        elevator for elevator in elevators if elevator.can_serve(passenger)
    ]
    if not eligible:
        raise RuntimeError(
            f"no elevator can serve passenger {passenger.passenger_id!r} "
            f"from floor {passenger.source} to floor {passenger.destination}"
        )
    return eligible


class EstimatedCompletionScheduler(Scheduler):
    """Minimize incremental total time across new and assigned passengers."""

    name = "eta"

    def select_elevator(
        self,
        elevators: list[Elevator],
        passenger: PassengerRequest,
        current_time: int,
    ) -> Elevator:
        def score(elevator: Elevator) -> tuple[int, int, int, int, int]:
            incremental_cost, total_time, wait_time = elevator.predict_assignment(
                passenger, current_time
            )
            return (
                incremental_cost,
                total_time,
                wait_time,
                elevator.pending_count,
                elevator.elevator_id,
            )

        return min(eligible_elevators(elevators, passenger), key=score)


class FairEstimatedCompletionScheduler(Scheduler):
    """Minimize predicted wait cost with a late-service penalty."""

    name = "fair-eta"

    def __init__(
        self,
        acceptable_wait: int = 30,
        late_wait_multiplier: float = 10.0,
    ) -> None:
        if acceptable_wait < 0:
            raise ValueError("acceptable_wait must be at least 0")
        normalized_multiplier = float(late_wait_multiplier)
        if not isfinite(normalized_multiplier) or normalized_multiplier < 1:
            raise ValueError(
                "late_wait_multiplier must be finite and at least 1"
            )
        self.acceptable_wait = acceptable_wait
        self.late_wait_multiplier = normalized_multiplier

    @property
    def parameters(self) -> dict[str, int | float]:
        return {
            "acceptable_wait": self.acceptable_wait,
            "late_wait_multiplier": self.late_wait_multiplier,
        }

    def select_elevator(
        self,
        elevators: list[Elevator],
        passenger: PassengerRequest,
        current_time: int,
    ) -> Elevator:
        def score(elevator: Elevator) -> tuple[float, int, int, int, int]:
            incremental_cost, total_time, wait_time = (
                elevator.predict_threshold_assignment(
                    passenger,
                    current_time,
                    self.acceptable_wait,
                    self.late_wait_multiplier,
                )
            )
            return (
                incremental_cost,
                wait_time,
                total_time,
                elevator.pending_count,
                elevator.elevator_id,
            )

        return min(eligible_elevators(elevators, passenger), key=score)


class NearestCarScheduler(Scheduler):
    """A lightweight nearest-car heuristic for comparison."""

    name = "nearest"

    def select_elevator(
        self,
        elevators: list[Elevator],
        passenger: PassengerRequest,
        current_time: int,
    ) -> Elevator:
        del current_time

        def score(elevator: Elevator) -> tuple[int, int, int]:
            distance = abs(elevator.floor - passenger.source)
            moving_away = (
                elevator.direction is Direction.UP
                and passenger.source < elevator.floor
                ) or (
                elevator.direction is Direction.DOWN
                and passenger.source > elevator.floor
            )
            penalty = elevator.max_floor - elevator.min_floor + 1 if moving_away else 0
            return distance + penalty, elevator.pending_count, elevator.elevator_id

        return min(eligible_elevators(elevators, passenger), key=score)


class RoundRobinScheduler(Scheduler):
    """Assign evenly without considering position; useful as a baseline."""

    name = "round-robin"

    def __init__(self) -> None:
        self._next_index = 0

    def select_elevator(
        self,
        elevators: list[Elevator],
        passenger: PassengerRequest,
        current_time: int,
    ) -> Elevator:
        del current_time
        for _ in elevators:
            elevator = elevators[self._next_index % len(elevators)]
            self._next_index += 1
            if elevator.can_serve(passenger):
                return elevator
        raise RuntimeError(
            f"no elevator can serve passenger {passenger.passenger_id!r} "
            f"from floor {passenger.source} to floor {passenger.destination}"
        )


def make_scheduler(
    name: str,
    *,
    acceptable_wait: int | None = None,
    late_wait_multiplier: float | None = None,
) -> Scheduler:
    normalized = name.strip().lower()
    if normalized == "fair-eta":
        threshold = 30 if acceptable_wait is None else acceptable_wait
        multiplier = (
            10.0
            if late_wait_multiplier is None
            else late_wait_multiplier
        )
        return FairEstimatedCompletionScheduler(threshold, multiplier)
    if acceptable_wait is not None or late_wait_multiplier is not None:
        raise ValueError(
            "acceptable_wait and late_wait_multiplier are only valid with "
            "scheduler 'fair-eta'"
        )

    schedulers: dict[str, type[Scheduler]] = {
        "eta": EstimatedCompletionScheduler,
        "nearest": NearestCarScheduler,
        "round-robin": RoundRobinScheduler,
    }
    try:
        return schedulers[normalized]()
    except KeyError as error:
        choices = ", ".join(sorted((*schedulers, "fair-eta")))
        raise ValueError(f"unknown scheduler {name!r}; choose one of: {choices}") from error
