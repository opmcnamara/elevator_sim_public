from __future__ import annotations

import unittest
from statistics import fmean

from elevator_sim import simulate
from elevator_sim.elevator import Elevator
from elevator_sim.models import PassengerRequest
from elevator_sim.statistics import build_summary


FAIRNESS_TRADEOFF_REQUESTS = [
    {"time": 0, "id": "p0", "source": 9, "dest": 5},
    {"time": 6, "id": "p1", "source": 10, "dest": 12},
    {"time": 12, "id": "p2", "source": 5, "dest": 1},
    {"time": 4, "id": "p3", "source": 7, "dest": 12},
    {"time": 0, "id": "p4", "source": 2, "dest": 9},
    {"time": 0, "id": "p5", "source": 9, "dest": 4},
    {"time": 16, "id": "p6", "source": 2, "dest": 4},
    {"time": 11, "id": "p7", "source": 7, "dest": 12},
    {"time": 12, "id": "p8", "source": 9, "dest": 2},
    {"time": 18, "id": "p9", "source": 1, "dest": 5},
]


class FairSchedulerTests(unittest.TestCase):
    def test_late_wait_penalty_reduces_worst_wait_at_average_wait_cost(self) -> None:
        common = {
            "num_elevators": 2,
            "num_floors": 12,
            "capacity": 2,
        }
        efficient = simulate(
            FAIRNESS_TRADEOFF_REQUESTS,
            scheduler="eta",
            **common,
        )
        fair = simulate(
            FAIRNESS_TRADEOFF_REQUESTS,
            scheduler="fair-eta",
            acceptable_wait=5,
            late_wait_multiplier=10,
            **common,
        )

        efficient_waits = [passenger.wait_time for passenger in efficient.passengers]
        fair_waits = [passenger.wait_time for passenger in fair.passengers]
        self.assertNotIn(None, efficient_waits)
        self.assertNotIn(None, fair_waits)

        self.assertEqual(max(efficient_waits), 11)
        self.assertEqual(max(fair_waits), 8)
        self.assertAlmostEqual(fmean(efficient_waits), 4.2)
        self.assertAlmostEqual(fmean(fair_waits), 5.0)

    def test_inactive_threshold_matches_eta_assignments(self) -> None:
        common = {
            "num_elevators": 2,
            "num_floors": 12,
            "capacity": 2,
        }
        efficient = simulate(
            FAIRNESS_TRADEOFF_REQUESTS,
            scheduler="eta",
            **common,
        )
        linear_wait = simulate(
            FAIRNESS_TRADEOFF_REQUESTS,
            scheduler="fair-eta",
            acceptable_wait=1_000,
            late_wait_multiplier=10,
            **common,
        )

        self.assertEqual(
            [passenger.assigned_elevator for passenger in efficient.passengers],
            [
                passenger.assigned_elevator
                for passenger in linear_wait.passengers
            ],
        )

    def test_threshold_cost_uses_the_configured_multiplier(self) -> None:
        elevator = Elevator(
            elevator_id=1,
            floor=1,
            capacity=4,
            min_floor=1,
            max_floor=10,
        )
        passenger = PassengerRequest(
            request_time=0,
            passenger_id="p",
            source=3,
            destination=5,
        )

        incremental_cost, total_time, wait_time = (
            elevator.predict_threshold_assignment(
                passenger,
                current_time=0,
                acceptable_wait=1,
                late_wait_multiplier=10,
            )
        )

        self.assertEqual(wait_time, 2)
        self.assertEqual(total_time, 4)
        self.assertEqual(incremental_cost, 12)

    def test_fair_scheduler_settings_are_validated_and_reported(self) -> None:
        request = [{"time": 0, "id": "p", "source": 1, "dest": 5}]

        with self.assertRaisesRegex(ValueError, "at least 0"):
            simulate(
                request,
                num_elevators=2,
                num_floors=5,
                capacity=2,
                scheduler="fair-eta",
                acceptable_wait=-1,
            )
        with self.assertRaisesRegex(ValueError, "finite and at least 1"):
            simulate(
                request,
                num_elevators=2,
                num_floors=5,
                capacity=2,
                scheduler="fair-eta",
                late_wait_multiplier=0.5,
            )
        with self.assertRaisesRegex(ValueError, "only valid"):
            simulate(
                request,
                num_elevators=2,
                num_floors=5,
                capacity=2,
                scheduler="eta",
                acceptable_wait=30,
                late_wait_multiplier=10,
            )

        result = simulate(
            request,
            num_elevators=2,
            num_floors=5,
            capacity=2,
            scheduler="fair-eta",
        )
        summary = build_summary(result)

        self.assertEqual(result.scheduler_name, "fair-eta")
        self.assertEqual(
            result.scheduler_parameters,
            {"acceptable_wait": 30, "late_wait_multiplier": 10.0},
        )
        self.assertEqual(
            summary["scheduler_parameters"],
            {"acceptable_wait": 30, "late_wait_multiplier": 10.0},
        )


if __name__ == "__main__":
    unittest.main()
