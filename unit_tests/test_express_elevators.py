from __future__ import annotations

import unittest
from random import Random

from elevator_sim import (
    ExpressElevator,
    PassengerRequest,
    SimulationConfig,
    simulate,
)
from elevator_sim.cli import build_parser
from elevator_sim.models import PassengerState
from elevator_sim.statistics import build_summary


class ExpressElevatorTests(unittest.TestCase):
    def test_cli_defaults_to_eight_elevators(self) -> None:
        args = build_parser().parse_args(["requests.csv"])

        self.assertEqual(args.elevators, 8)

    def test_express_car_accepts_only_trips_between_allowed_floors(self) -> None:
        elevator = ExpressElevator(
            elevator_id=2,
            floor=1,
            capacity=4,
            min_floor=1,
            max_floor=20,
            allowed_floors={1, 10, 20},
        )
        permitted = PassengerRequest(0, "permitted", 1, 20)
        invalid_source = PassengerRequest(0, "invalid-source", 2, 20)
        invalid_destination = PassengerRequest(0, "invalid-destination", 1, 19)

        self.assertTrue(elevator.can_serve(permitted))
        self.assertFalse(elevator.can_serve(invalid_source))
        self.assertFalse(elevator.can_serve(invalid_destination))

        with self.assertRaisesRegex(ValueError, "cannot serve passenger"):
            elevator.assign(invalid_source)
        self.assertIs(invalid_source.state, PassengerState.NEW)

        elevator.assign(permitted)
        self.assertEqual(permitted.assigned_elevator, 2)

    def test_configuration_rejects_invalid_express_settings(self) -> None:
        invalid_settings = (
            {
                "num_elevators": 2,
                "num_express_elevators": 2,
                "express_floors": (1, 10),
            },
            {
                "num_elevators": 2,
                "num_express_elevators": 1,
                "express_floors": (),
            },
            {
                "num_elevators": 2,
                "num_express_elevators": 0,
                "express_floors": (1, 10),
            },
            {
                "num_elevators": 2,
                "num_express_elevators": 1,
                "express_floors": (1, 11),
            },
            {
                "num_elevators": 2,
                "num_express_elevators": 1,
                "express_floors": (1, 1),
            },
        )

        for settings in invalid_settings:
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                SimulationConfig(
                    num_floors=10,
                    capacity=4,
                    **settings,
                )

    def test_all_schedulers_filter_incompatible_express_cars(self) -> None:
        requests = [
            {"time": 0, "id": "local-a", "source": 2, "dest": 3},
            {"time": 0, "id": "local-b", "source": 4, "dest": 5},
            {"time": 0, "id": "express", "source": 1, "dest": 10},
        ]

        for scheduler in ("eta", "fair-eta", "nearest", "round-robin"):
            with self.subTest(scheduler=scheduler):
                result = simulate(
                    requests,
                    num_elevators=2,
                    num_floors=10,
                    capacity=2,
                    scheduler=scheduler,
                    num_express_elevators=1,
                    express_floors=[1, 10],
                )
                passengers = {
                    passenger.passenger_id: passenger
                    for passenger in result.passengers
                }

                self.assertEqual(passengers["local-a"].assigned_elevator, 1)
                self.assertEqual(passengers["local-b"].assigned_elevator, 1)
                self.assertEqual(passengers["express"].assigned_elevator, 2)
                self.assertTrue(
                    all(
                        passenger.state is PassengerState.COMPLETED
                        for passenger in result.passengers
                    )
                )
                self.assertEqual(result.config.express_floors, (1, 10))
                self.assertEqual(
                    build_summary(result)["express_elevators"],
                    {
                        "enabled": True,
                        "count": 1,
                        "elevator_ids": [2],
                        "served_floors": [1, 10],
                    },
                )

    def test_round_robin_skips_multiple_incompatible_express_cars(self) -> None:
        result = simulate(
            [
                {"time": 0, "id": "express-a", "source": 1, "dest": 10},
                {"time": 0, "id": "express-b", "source": 10, "dest": 1},
                {"time": 0, "id": "express-c", "source": 1, "dest": 10},
                {"time": 0, "id": "local-a", "source": 2, "dest": 3},
                {"time": 0, "id": "local-b", "source": 4, "dest": 5},
            ],
            num_elevators=3,
            num_floors=10,
            capacity=5,
            scheduler="round-robin",
            num_express_elevators=2,
            express_floors=(1, 10),
        )
        passengers = {
            passenger.passenger_id: passenger for passenger in result.passengers
        }

        self.assertEqual(passengers["express-a"].assigned_elevator, 1)
        self.assertEqual(passengers["express-b"].assigned_elevator, 2)
        self.assertEqual(passengers["express-c"].assigned_elevator, 3)
        self.assertEqual(passengers["local-a"].assigned_elevator, 1)
        self.assertEqual(passengers["local-b"].assigned_elevator, 1)

    def test_random_requests_never_use_an_incompatible_express_car(self) -> None:
        random = Random(20260824)
        express_floors = {1, 5, 10, 15}
        requests = []
        for passenger_number in range(30):
            source = random.randint(1, 15)
            destination = random.randint(1, 14)
            if destination >= source:
                destination += 1
            requests.append(
                {
                    "time": random.randint(0, 30),
                    "id": f"passenger-{passenger_number}",
                    "source": source,
                    "dest": destination,
                }
            )

        for scheduler in ("eta", "fair-eta", "nearest", "round-robin"):
            with self.subTest(scheduler=scheduler):
                result = simulate(
                    requests,
                    num_elevators=4,
                    num_floors=15,
                    capacity=3,
                    scheduler=scheduler,
                    num_express_elevators=2,
                    express_floors=express_floors,
                )
                for passenger in result.passengers:
                    if passenger.assigned_elevator in {3, 4}:
                        self.assertIn(passenger.source, express_floors)
                        self.assertIn(passenger.destination, express_floors)
                    self.assertIs(passenger.state, PassengerState.COMPLETED)

    def test_cli_parses_express_configuration(self) -> None:
        args = build_parser().parse_args(
            [
                "requests.csv",
                "--elevators",
                "4",
                "--express-elevators",
                "2",
                "--express-floors",
                "1, 10,20",
            ]
        )

        self.assertEqual(args.express_elevators, 2)
        self.assertEqual(args.express_floors, (1, 10, 20))


if __name__ == "__main__":
    unittest.main()
