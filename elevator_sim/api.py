"""Small public API for embedding the simulator in tests or notebooks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .models import PassengerRequest, SimulationConfig
from .schedulers import make_scheduler
from .simulation import Simulation, SimulationResult


RequestInput = PassengerRequest | Mapping[str, object]



def simulate(
    requests: Sequence[RequestInput],
    *,    # Makes every parameter afterwards keyword only, to force explicit inputs
    num_elevators: int,
    num_floors: int,
    capacity: int,
    start_floor: int = 1,
    scheduler: str = "eta",
    max_ticks: int = 1_000_000,
    num_express_elevators: int = 0,
    express_floors: Sequence[int] | None = None,
    acceptable_wait: int | None = None,
    late_wait_multiplier: float | None = None,
) -> SimulationResult:
    """Simulate a list of PassengerRequest objects or request dictionaries.

    Dictionary requests use the case-study column names: time, id, source, dest.
    """

    # try to create a normalized list of PassengerRequest objects from `requests` input
    normalized: list[PassengerRequest] = []
    for index, request in enumerate(requests):

        # if it's already a PassengerRequest, append
        if isinstance(request, PassengerRequest):
            normalized.append(request)
            continue

        # Otherwise, try to create a PassengerRequest object for current request
        # Assumes it is a dictionary-like object, if not will encounter error
        try:
            normalized.append(
                PassengerRequest(
                    request_time=int(request["time"]),
                    passenger_id=str(request["id"]),
                    source=int(request["source"]),
                    destination=int(request["dest"]),
                )
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"invalid request at index {index}: {error}") from error

    config = SimulationConfig(
        num_elevators=num_elevators,
        num_floors=num_floors,
        capacity=capacity,
        start_floor=start_floor,
        max_ticks=max_ticks,
        num_express_elevators=num_express_elevators,
        express_floors=(
            tuple(express_floors) if express_floors is not None else ()
        ),
    )

    simulation = Simulation(
        config=config,
        scheduler=make_scheduler(
            scheduler,
            acceptable_wait=acceptable_wait,
            late_wait_multiplier=late_wait_multiplier,
        ),
    )

    result = simulation.run(normalized)

    return result
