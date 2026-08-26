from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.generate_poisson_requests import (
    generate_files,
    generate_requests,
)


class RequestGeneratorTests(unittest.TestCase):
    def test_requests_are_sorted_valid_and_lobby_heavy(self) -> None:
        requests = generate_requests(
            seed=12345,
            request_count=10_000,
            num_floors=50,
            arrival_rate=5.0,
            lobby_probability=0.70,
            lobby_source_probability=0.20,
        )

        self.assertEqual(len(requests), 10_000)
        self.assertEqual(list(requests.columns), ["time", "id", "source", "dest"])
        self.assertTrue(requests["time"].is_monotonic_increasing)
        self.assertGreater(requests["time"].iloc[-1], 1_800)
        self.assertLess(requests["time"].iloc[-1], 2_200)
        self.assertTrue(requests["id"].is_unique)
        self.assertTrue(requests["source"].between(1, 50).all())
        self.assertTrue(requests["dest"].between(1, 50).all())
        self.assertTrue((requests["source"] != requests["dest"]).all())

        lobby_sources = (requests["source"] == 1).sum()
        self.assertAlmostEqual(
            lobby_sources / len(requests),
            0.20,
            delta=0.02,
        )

        non_lobby = requests.loc[requests["source"] != 1]
        lobby_destinations = (non_lobby["dest"] == 1).sum()
        self.assertAlmostEqual(
            lobby_destinations / len(non_lobby),
            0.70,
            delta=0.02,
        )

    def test_same_base_seed_produces_identical_files(self) -> None:
        with (
            tempfile.TemporaryDirectory() as first,
            tempfile.TemporaryDirectory() as second,
        ):
            common = {
                "file_count": 2,
                "requests_per_file": 100,
                "num_floors": 10,
                "arrival_rate": 4.0,
                "lobby_probability": 0.70,
                "lobby_source_probability": 0.20,
                "base_seed": 999,
            }
            first_paths = generate_files(output_dir=Path(first), **common)
            second_paths = generate_files(output_dir=Path(second), **common)

            self.assertEqual(
                [path.name for path in first_paths],
                [path.name for path in second_paths],
            )
            self.assertEqual(
                [path.read_bytes() for path in first_paths],
                [path.read_bytes() for path in second_paths],
            )


if __name__ == "__main__":
    unittest.main()
