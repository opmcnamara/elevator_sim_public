"""Elevator state machine and its direction/capacity rules."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

from .models import Direction, PassengerRequest, PassengerState, SimulationEvent


@dataclass(slots=True)
class Elevator:
    """A single LOOK/SCAN-style elevator.

    The car keeps its current direction while demand exists ahead. It reverses
    only when there is no demand farther in that direction. A passenger boards
    only when the car is travelling in the passenger's requested direction.
    """

    elevator_id: int
    floor: int
    capacity: int
    min_floor: int
    max_floor: int
    direction: Direction = Direction.IDLE
    waiting: list[PassengerRequest] = field(default_factory=list)
    onboard: list[PassengerRequest] = field(default_factory=list)

    @property
    def pending_count(self) -> int:
        return len(self.waiting) + len(self.onboard)

    @property
    def is_idle(self) -> bool:
        return self.pending_count == 0

    def can_serve(self, passenger: PassengerRequest) -> bool:
        """Return whether this car is permitted to serve the complete trip."""

        del passenger
        return True

    def assign(self, passenger: PassengerRequest) -> None:
        if passenger.state is not PassengerState.NEW:
            raise ValueError(f"passenger {passenger.passenger_id!r} is already assigned")
        passenger.assigned_elevator = self.elevator_id
        passenger.state = PassengerState.WAITING
        self.waiting.append(passenger)

    def service_floor(self, time: int) -> list[SimulationEvent]:
        """Drop off, choose direction, and pick up at the current floor."""

        events: list[SimulationEvent] = []

        remaining_onboard: list[PassengerRequest] = []
        for passenger in self.onboard:
            if passenger.destination == self.floor:
                passenger.state = PassengerState.COMPLETED
                passenger.dropoff_time = time
                events.append(
                    SimulationEvent(
                        time=time,
                        event="dropoff",
                        elevator_id=self.elevator_id,
                        passenger_id=passenger.passenger_id,
                        floor=self.floor,
                    )
                )
            else:
                remaining_onboard.append(passenger)
        self.onboard = remaining_onboard

        self._choose_direction()
        available = self.capacity - len(self.onboard)

        # create list of eligible passengers (among passengers who are waiting for this elevator)
        # Eligibile: one the same floor + going in same direction
        eligible = sorted(
            (
                passenger
                for passenger in self.waiting
                if passenger.source == self.floor
                and passenger.direction == self.direction
            ),
            key=lambda passenger: (passenger.request_time, passenger.passenger_id),
        )


        boarding = eligible[:available]
        boarding_ids = {id(passenger) for passenger in boarding}

        for passenger in boarding:
            passenger.state = PassengerState.ONBOARD
            passenger.pickup_time = time
            self.onboard.append(passenger)
            events.append(
                SimulationEvent(
                    time=time,
                    event="pickup",
                    elevator_id=self.elevator_id,
                    passenger_id=passenger.passenger_id,
                    floor=self.floor,
                )
            )
        self.waiting = [
            passenger for passenger in self.waiting if id(passenger) not in boarding_ids
        ]

        self._choose_direction()
        return events

    def move_one_floor(self) -> None:
        """Move at most one floor, preserving the one-tick movement contract."""

        self._choose_direction()
        if self.direction is Direction.IDLE:
            return
        next_floor = self.floor + int(self.direction)
        if not self.min_floor <= next_floor <= self.max_floor:
            raise RuntimeError(
                f"elevator {self.elevator_id} attempted to leave the building"
            )
        self.floor = next_floor

    def predict_assignment(
        self, passenger: PassengerRequest, current_time: int
    ) -> tuple[int, int, int]:
        """Return (incremental system cost, candidate total, candidate wait).

        Two isolated shadow simulations measure the car's known workload with
        and without the candidate. The difference in summed passenger total
        times captures both the candidate's completion time and delay imposed
        on already-assigned riders. Future requests are not available here.
        """

        baseline = self._predict_pending_metrics(current_time)
        proposed = self._predict_pending_metrics(current_time, passenger)
        incremental_cost = sum(total for total, _ in proposed.values()) - sum(
            total for total, _ in baseline.values()
        )
        candidate_total, candidate_wait = proposed[passenger.passenger_id]
        return incremental_cost, candidate_total, candidate_wait

    def predict_threshold_assignment(
        self,
        passenger: PassengerRequest,
        current_time: int,
        acceptable_wait: int,
        late_wait_multiplier: float,
    ) -> tuple[float, int, int]:
        """Score an assignment with a heavier cost after a wait threshold.

        Subtracting the baseline penalized waits from the proposed penalized
        waits measures the candidate's cost plus any fairness cost imposed on
        passengers already assigned to this car. Waits up to the acceptable
        threshold cost one unit per tick; excess wait receives a quadratic
        penalty using the configured multiplier.
        """

        baseline = self._predict_pending_metrics(current_time)
        proposed = self._predict_pending_metrics(current_time, passenger)

        def wait_cost(wait_time: int) -> float:
            excess_wait = max(0, wait_time - acceptable_wait)
            return wait_time + late_wait_multiplier * excess_wait**2

        baseline_cost = sum(
            wait_cost(wait_time)
            for _, wait_time in baseline.values()
        )
        proposed_cost = sum(
            wait_cost(wait_time)
            for _, wait_time in proposed.values()
        )
        candidate_total, candidate_wait = proposed[passenger.passenger_id]
        return proposed_cost - baseline_cost, candidate_total, candidate_wait

    def _predict_pending_metrics(
        self,
        current_time: int,
        passenger: PassengerRequest | None = None,
    ) -> dict[str, tuple[int, int]]:
        """Shadow-simulate this car and return total/wait time by passenger."""

        # Keep predictions isolated from the live elevator and passengers.
        shadow = deepcopy(self)
        tracked = [*shadow.waiting, *shadow.onboard]

        # Include the candidate only in the proposed-assignment prediction.
        if passenger is not None:
            candidate = deepcopy(passenger)
            shadow.assign(candidate)
            tracked.append(candidate)
        if not tracked:
            return {}

        elapsed = 0

        # Allow several full-building sweeps per pending passenger.
        guard = max(
            100,
            4 * (self.max_floor - self.min_floor + 1) * (shadow.pending_count + 1),
        )
        while elapsed <= guard:
            shadow.service_floor(current_time + elapsed)

            # Every tracked passenger has completed once the shadow car is idle.
            if shadow.is_idle:
                metrics: dict[str, tuple[int, int]] = {}
                for tracked_passenger in tracked:
                    assert tracked_passenger.total_time is not None
                    assert tracked_passenger.wait_time is not None
                    metrics[tracked_passenger.passenger_id] = (
                        tracked_passenger.total_time,
                        tracked_passenger.wait_time,
                    )
                return metrics
            shadow.move_one_floor()
            elapsed += 1

        raise RuntimeError("scheduler prediction failed to converge")

    def _choose_direction(self) -> None:
        pending_floors = [p.source for p in self.waiting]
        pending_floors.extend(p.destination for p in self.onboard)
        if not pending_floors:
            self.direction = Direction.IDLE
            return

        # waiting passengers on current floor assigned to this elevator
        local_waiting = sorted(
            (p for p in self.waiting if p.source == self.floor),
            key=lambda passenger: (passenger.request_time, passenger.passenger_id),
        )

        if self.direction is Direction.UP:
            if any(floor > self.floor for floor in pending_floors):
                return
            if any(p.direction is Direction.UP for p in local_waiting):
                return
            if any(floor < self.floor for floor in pending_floors):
                self.direction = Direction.DOWN
                return

        elif self.direction is Direction.DOWN:
            if any(floor < self.floor for floor in pending_floors):
                return
            if any(p.direction is Direction.DOWN for p in local_waiting):
                return
            if any(floor > self.floor for floor in pending_floors):
                self.direction = Direction.UP
                return

        if local_waiting:
            self.direction = local_waiting[0].direction
            return

        nearest = min(
            pending_floors,
            key=lambda floor: (abs(floor - self.floor), floor),
        )
        self.direction = Direction.UP if nearest > self.floor else Direction.DOWN
