from __future__ import annotations

import unittest
from random import Random

from elevator_sim import PassengerRequest, simulate
from elevator_sim.statistics import build_summary


class SimulationTests(unittest.TestCase):
    def test_late_request_does_not_skip_time(self) -> None:
        result = simulate(
            [{"time": 3, "id": "late", "source": 1, "dest": 2}],
            num_elevators=1,
            num_floors=5,
            capacity=1,
        )

        self.assertEqual([row["time"] for row in result.position_log], list(range(5)))
        self.assertEqual(
            [row["elevator_1"] for row in result.position_log], [1, 1, 1, 1, 2]
        )
        self.assertEqual(result.passengers[0].wait_time, 0)
        self.assertEqual(result.passengers[0].total_time, 1)

    def test_capacity_is_enforced_and_all_passengers_finish(self) -> None:
        result = simulate(
            [
                {"time": 0, "id": "first", "source": 1, "dest": 3},
                {"time": 0, "id": "second", "source": 1, "dest": 2},
            ],
            num_elevators=1,
            num_floors=5,
            capacity=1,
        )

        passengers = {p.passenger_id: p for p in result.passengers}
        self.assertEqual(result.max_occupancy[1], 1)
        self.assertEqual(passengers["first"].pickup_time, 0)
        self.assertEqual(passengers["second"].pickup_time, 4)
        self.assertTrue(all(p.dropoff_time is not None for p in result.passengers))

    def test_car_does_not_pick_up_opposite_direction_while_sweeping(self) -> None:
        result = simulate(
            [
                {"time": 0, "id": "up", "source": 1, "dest": 4},
                {"time": 1, "id": "down", "source": 3, "dest": 1},
            ],
            num_elevators=1,
            num_floors=5,
            capacity=2,
        )

        passengers = {p.passenger_id: p for p in result.passengers}
        self.assertEqual(passengers["up"].dropoff_time, 3)
        self.assertEqual(passengers["down"].pickup_time, 4)
        self.assertEqual(passengers["down"].dropoff_time, 6)

    def test_eta_scheduler_uses_idle_second_car(self) -> None:
        result = simulate(
            [
                {"time": 0, "id": "long-up", "source": 1, "dest": 10},
                {"time": 1, "id": "short-down", "source": 2, "dest": 1},
            ],
            num_elevators=2,
            num_floors=10,
            capacity=2,
            scheduler="eta",
        )

        passengers = {p.passenger_id: p for p in result.passengers}
        self.assertEqual(passengers["long-up"].assigned_elevator, 1)
        self.assertEqual(passengers["short-down"].assigned_elevator, 2)

    def test_eta_scheduler_accounts_for_delay_to_existing_passengers(self) -> None:
        result = simulate(
            [
                {"time": 0, "id": "waiting-down", "source": 5, "dest": 1},
                {"time": 1, "id": "new-up", "source": 2, "dest": 10},
            ],
            num_elevators=2,
            num_floors=10,
            capacity=2,
            scheduler="eta",
        )

        passengers = {p.passenger_id: p for p in result.passengers}
        self.assertEqual(passengers["waiting-down"].assigned_elevator, 1)
        # Car 1 is physically closer, but using it would carry the new rider
        # past floor 5 and substantially delay the already-assigned down trip.
        self.assertEqual(passengers["new-up"].assigned_elevator, 2)

    def test_each_position_changes_by_at_most_one_floor(self) -> None:
        result = simulate(
            [
                PassengerRequest(0, "a", 1, 8),
                PassengerRequest(2, "b", 7, 2),
                PassengerRequest(5, "c", 3, 6),
            ],
            num_elevators=2,
            num_floors=8,
            capacity=2,
        )
        for elevator_id in (1, 2):
            positions = [row[f"elevator_{elevator_id}"] for row in result.position_log]
            self.assertTrue(
                all(abs(current - previous) <= 1 for previous, current in zip(positions, positions[1:]))
            )

    def test_statistics_include_required_distributions(self) -> None:
        result = simulate(
            [{"time": 0, "id": "p", "source": 1, "dest": 4}],
            num_elevators=1,
            num_floors=4,
            capacity=1,
        )
        summary = build_summary(result)

        self.assertEqual(summary["wait_time"]["min"], 0)
        self.assertEqual(summary["wait_time"]["max"], 0)
        self.assertEqual(summary["wait_time"]["average"], 0.0)
        self.assertEqual(summary["total_time"]["min"], 3)
        self.assertEqual(summary["total_time"]["max"], 3)
        self.assertEqual(
            summary["express_elevators"],
            {
                "enabled": False,
                "count": 0,
                "elevator_ids": [],
                "served_floors": [],
            },
        )

    def test_statistics_report_wait_target_compliance(self) -> None:
        result = simulate(
            [
                {"time": 0, "id": "a", "source": 1, "dest": 40},
                {"time": 0, "id": "b", "source": 1, "dest": 2},
            ],
            num_elevators=1,
            num_floors=40,
            capacity=1,
        )
        summary = build_summary(result)

        self.assertEqual(
            summary["observations"][1],
            "50.0% of passengers were picked up within 30 ticks.",
        )
        self.assertEqual(
            summary["observations"][2],
            "50.0% of passengers waited longer than 45 ticks.",
        )
        self.assertTrue(
            all("detour" not in observation for observation in summary["observations"])
        )

    def test_invalid_requests_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate passenger ID"):
            simulate(
                [
                    {"time": 0, "id": "same", "source": 1, "dest": 2},
                    {"time": 1, "id": "same", "source": 2, "dest": 3},
                ],
                num_elevators=1,
                num_floors=3,
                capacity=1,
            )

    def test_seeded_random_workloads_preserve_core_invariants(self) -> None:
        random = Random(20260820)
        for scheduler in ("eta", "fair-eta", "nearest", "round-robin"):
            for case in range(8):
                requests = []
                for passenger_number in range(12):
                    source = random.randint(1, 12)
                    destination = random.randint(1, 11)
                    if destination >= source:
                        destination += 1
                    requests.append(
                        {
                            "time": random.randint(0, 18),
                            "id": f"{scheduler}-{case}-{passenger_number}",
                            "source": source,
                            "dest": destination,
                        }
                    )

                result = simulate(
                    requests,
                    num_elevators=3,
                    num_floors=12,
                    capacity=2,
                    scheduler=scheduler,
                )

                self.assertEqual(len(result.position_log), result.finished_at + 1)
                self.assertEqual(
                    [row["time"] for row in result.position_log],
                    list(range(result.finished_at + 1)),
                )
                self.assertLessEqual(max(result.max_occupancy.values()), 2)
                for passenger in result.passengers:
                    self.assertIsNotNone(passenger.dropoff_time)
                    self.assertGreaterEqual(passenger.wait_time, 0)
                    self.assertEqual(
                        passenger.travel_time,
                        abs(passenger.destination - passenger.source),
                    )
                for elevator_id in (1, 2, 3):
                    positions = [
                        row[f"elevator_{elevator_id}"]
                        for row in result.position_log
                    ]
                    self.assertTrue(all(1 <= floor <= 12 for floor in positions))
                    self.assertTrue(
                        all(
                            abs(current - previous) <= 1
                            for previous, current in zip(positions, positions[1:])
                        )
                    )


if __name__ == "__main__":
    unittest.main()
