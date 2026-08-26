"""Discrete-time simulation engine."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from .elevator import Elevator
from .express_elevator import ExpressElevator
from .models import (
    PassengerRequest,
    PassengerState,
    SimulationConfig,
    SimulationEvent,
)
from .schedulers import Scheduler


@dataclass(slots=True)
class SimulationResult:
    config: SimulationConfig
    scheduler_name: str
    scheduler_parameters: dict[str, int | float]
    passengers: list[PassengerRequest]
    position_log: list[dict[str, int]]
    events: list[SimulationEvent]
    finished_at: int
    max_occupancy: dict[int, int]


class Simulation:
    """Run requests in timestamp order while exposing only arrived work."""

    def __init__(self, config: SimulationConfig, scheduler: Scheduler) -> None:
        self.config = config
        self.scheduler = scheduler

    def run(self, requests: list[PassengerRequest]) -> SimulationResult:
        # Create a copy to not affect original requests
        passengers = deepcopy(requests)

        # Check if all requests are valid
        self._validate_requests(passengers)

        # Sort passengers by the time of their request (should already be in order from CSV, but enforcing here)
        passengers.sort(key=lambda passenger: passenger.request_time)

        elevators = self._build_elevators()

        # Create empty position log 
        ##### **** IS THIS THE BEST OBJECT TO HOLD? COULD DECLARE EMPTY ARRAY OF RIGHT SIZE? HMM, actually won't know full size ahead of time, will be more than final time of request to complete all rides 
        position_log: list[dict[str, int]] = []

        # Create log to store events that occur in Simulation, for error traceback if needed
        events: list[SimulationEvent] = []
        max_occupancy = {elevator.elevator_id: 0 for elevator in elevators}


        # Index variable to keep track of which request is next
        next_request = 0

        # Current time of simulation
        # ALWAYS INCREMENTED even if no request comes in
        time = 0

        while True:
            # This is the only place new requests become visible to a scheduler.
            while (
                # while there are still passengers to be processed AND passengers match the current time
                next_request < len(passengers)
                and passengers[next_request].request_time == time
            ):
                passenger = passengers[next_request]

                 
                # Reference to the elevator assigned to passenger by the scheduler
                # Does NOT create a new elevator object
                assigned_elevator = self.scheduler.select_elevator(elevators, passenger, time)
                assigned_elevator.assign(passenger)
                events.append(
                    SimulationEvent(
                        time=time,
                        event="assigned",
                        elevator_id=assigned_elevator.elevator_id,
                        passenger_id=passenger.passenger_id,
                        floor=passenger.source,
                    )
                )

                # Increment to go to next request
                next_request += 1

            # Once all passengers for current time assigned, service all elevators on their respective floors
            for elevator in elevators:
                events.extend(elevator.service_floor(time))
                max_occupancy[elevator.elevator_id] = max(
                    max_occupancy[elevator.elevator_id], len(elevator.onboard)
                )

            # Create row dict to log current elevator positions
            row = {"time": time}
            row.update(
                {
                    f"elevator_{elevator.elevator_id}": elevator.floor
                    for elevator in elevators
                }
            )
            position_log.append(row)


            # Check if all passengers have been assigned AND all requests are completed
            all_released = (next_request == len(passengers))
            all_completed = all(
                passenger.state is PassengerState.COMPLETED
                for passenger in passengers
            )

            # End main `while` loop if both conditions met
            # Simulation body terminates
            if all_released and all_completed:
                break

            # If more work still needs to be done, move elevators to their next floors
            for elevator in elevators:
                elevator.move_one_floor()
            time += 1
            if time > self.config.max_ticks:
                raise RuntimeError(
                    "simulation exceeded max_ticks; inspect the request set or increase the limit"
                )

        return SimulationResult(
            config=self.config,
            scheduler_name=self.scheduler.name,
            scheduler_parameters=self.scheduler.parameters,
            passengers=passengers,
            position_log=position_log,
            events=events,
            finished_at=time,
            max_occupancy=max_occupancy,
        )

    def _build_elevators(self) -> list[Elevator]:
        """Build regular cars first, followed by the configured express cars."""

        regular_count = (
            self.config.num_elevators - self.config.num_express_elevators
        )
        elevators: list[Elevator] = []
        for index in range(self.config.num_elevators):
            common = {
                "elevator_id": index + 1,
                "floor": self.config.start_floor,
                "capacity": self.config.capacity,
                "min_floor": 1,
                "max_floor": self.config.num_floors,
            }
            if index < regular_count:
                elevators.append(Elevator(**common))
            else:
                elevators.append(
                    ExpressElevator(
                        **common,
                        allowed_floors=self.config.express_floors,
                    )
                )
        return elevators

    # Validates all requests before running simulation
    def _validate_requests(self, requests: list[PassengerRequest]) -> None:
        seen_ids: set[str] = set()
        for passenger in requests:
            if type(passenger.request_time) is not int or passenger.request_time < 0:
                raise ValueError(
                    f"request {passenger.passenger_id!r} has an invalid time"
                )
            if not passenger.passenger_id.strip():
                raise ValueError("passenger IDs cannot be empty")
            if passenger.passenger_id in seen_ids:
                raise ValueError(f"duplicate passenger ID: {passenger.passenger_id!r}")
            seen_ids.add(passenger.passenger_id)
            if not (1 <= passenger.source <= self.config.num_floors):
                raise ValueError(
                    f"request {passenger.passenger_id!r} has an invalid source floor"
                )
            if not (1 <= passenger.destination <= self.config.num_floors):
                raise ValueError(
                    f"request {passenger.passenger_id!r} has an invalid destination floor"
                )
            if passenger.source == passenger.destination:
                raise ValueError(
                    f"request {passenger.passenger_id!r} must travel to a different floor"
                )
            if passenger.state is not PassengerState.NEW:
                raise ValueError(
                    f"request {passenger.passenger_id!r} has already been simulated"
                )
