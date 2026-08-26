from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from elevator_sim import simulate
from elevator_sim.io import read_requests, write_results


class InputOutputTests(unittest.TestCase):
    def test_read_and_write_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "input.csv"
            input_path.write_text(
                "time,id,source,dest\n0,p1,1,3\n2,p2,3,1\n", encoding="utf-8"
            )
            requests = read_requests(input_path)
            result = simulate(
                requests,
                num_elevators=1,
                num_floors=3,
                capacity=1,
            )
            paths = write_results(result, root / "results")

            self.assertEqual(set(paths), {"positions", "passengers", "events", "summary"})
            with paths["positions"].open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["time"], "0")
            self.assertEqual(rows[0]["elevator_1"], "1")

            summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
            self.assertEqual(summary["passenger_count"], 2)

    def test_missing_columns_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "bad.csv"
            path.write_text("time,id,source\n0,p1,1\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing columns: dest"):
                read_requests(path)


if __name__ == "__main__":
    unittest.main()

