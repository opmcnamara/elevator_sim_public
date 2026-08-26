"""Elevator restricted to pickups and drop-offs at configured floors."""

from __future__ import annotations

from collections.abc import Collection

from .elevator import Elevator
from .models import PassengerRequest


class ExpressElevator(Elevator):
    """An elevator that accepts trips only between its allowed floors.

    Express cars still move one floor per tick and therefore pass intermediate
    floors. The restriction controls where they may pick up or drop off.
    """

    __slots__ = ("allowed_floors",)

    def __init__(
        self,
        *,
        elevator_id: int,
        floor: int,
        capacity: int,
        min_floor: int,
        max_floor: int,
        allowed_floors: Collection[int],
    ) -> None:
        super().__init__(
            elevator_id=elevator_id,
            floor=floor,
            capacity=capacity,
            min_floor=min_floor,
            max_floor=max_floor,
        )
        self.allowed_floors = frozenset(allowed_floors)
        if len(self.allowed_floors) < 2:
            raise ValueError("an express elevator requires at least two allowed floors")
        if any(
            not self.min_floor <= floor <= self.max_floor
            for floor in self.allowed_floors
        ):
            raise ValueError("express elevator floors must be within its floor range")

    def can_serve(self, passenger: PassengerRequest) -> bool:
        """Return whether both endpoints are express-service floors."""

        return (
            passenger.source in self.allowed_floors
            and passenger.destination in self.allowed_floors
        )

    def assign(self, passenger: PassengerRequest) -> None:
        """Reject invalid trips even if a scheduler eligibility check is bypassed."""

        if not self.can_serve(passenger):
            raise ValueError(
                f"express elevator {self.elevator_id} cannot serve passenger "
                f"{passenger.passenger_id!r} from floor {passenger.source} "
                f"to floor {passenger.destination}"
            )
        Elevator.assign(self, passenger)
