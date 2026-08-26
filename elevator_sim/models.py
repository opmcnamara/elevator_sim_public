"""Core domain types for the elevator simulation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum


class Direction(IntEnum):
    """Elevator and passenger travel direction."""

    DOWN = -1
    IDLE = 0
    UP = 1


class PassengerState(str, Enum):
    NEW = "new"
    WAITING = "waiting"
    ONBOARD = "onboard"
    COMPLETED = "completed"


@dataclass(slots=True)
class PassengerRequest:
    """A request plus the timestamps populated while it is served."""

    request_time: int
    passenger_id: str
    source: int
    destination: int
    state: PassengerState = PassengerState.NEW
    assigned_elevator: int | None = None
    pickup_time: int | None = None
    dropoff_time: int | None = None

    @property
    def direction(self) -> Direction:
        return Direction.UP if self.destination > self.source else Direction.DOWN

    @property
    def wait_time(self) -> int | None:
        if self.pickup_time is None:
            return None
        return self.pickup_time - self.request_time

    @property
    def travel_time(self) -> int | None:
        if self.pickup_time is None or self.dropoff_time is None:
            return None
        return self.dropoff_time - self.pickup_time

    @property
    def total_time(self) -> int | None:
        if self.dropoff_time is None:
            return None
        return self.dropoff_time - self.request_time


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    num_elevators: int
    num_floors: int
    capacity: int
    start_floor: int = 1
    max_ticks: int = 1_000_000
    num_express_elevators: int = 0
    express_floors: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        try:
            normalized_express_floors = tuple(self.express_floors)
        except TypeError as error:
            raise ValueError("express_floors must be a collection of floors") from error
        object.__setattr__(self, "express_floors", normalized_express_floors)

        if self.num_elevators < 1:
            raise ValueError("num_elevators must be at least 1")
        if self.num_floors < 2:
            raise ValueError("num_floors must be at least 2")
        if self.capacity < 1:
            raise ValueError("capacity must be at least 1")
        if not 1 <= self.start_floor <= self.num_floors:
            raise ValueError("start_floor must be within the building")
        if self.max_ticks < 1:
            raise ValueError("max_ticks must be at least 1")
        if not 0 <= self.num_express_elevators < self.num_elevators:
            raise ValueError(
                "num_express_elevators must be between 0 and num_elevators - 1"
            )
        if self.num_express_elevators == 0:
            if self.express_floors:
                raise ValueError(
                    "express_floors requires at least one express elevator"
                )
            return
        if len(self.express_floors) < 2:
            raise ValueError("express_floors must contain at least two floors")
        if any(type(floor) is not int for floor in self.express_floors):
            raise ValueError("express_floors must contain only integers")
        if len(set(self.express_floors)) != len(self.express_floors):
            raise ValueError("express_floors must not contain duplicates")
        if any(
            not 1 <= floor <= self.num_floors for floor in self.express_floors
        ):
            raise ValueError("express_floors must be within the building")


@dataclass(frozen=True, slots=True)
class SimulationEvent:
    time: int
    event: str
    elevator_id: int
    passenger_id: str
    floor: int
