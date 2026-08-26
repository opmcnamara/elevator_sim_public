from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.compare_wait_results import (
    build_summary,
    histogram_bins,
    main,
    read_wait_data,
)


class CompareWaitResultsTests(unittest.TestCase):
    def write_passengers(
        self,
        path: Path,
        waits: list[int],
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["id", "wait_time"])
            writer.writeheader()
            for index, wait in enumerate(waits, start=1):
                writer.writerow({"id": f"p{index}", "wait_time": wait})

    def test_recursive_pooling_and_summary_differences(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_a = root / "eta"
            input_b = root / "fair_eta"
            self.write_passengers(input_a / "run_1/passengers.csv", [0, 10, 40])
            self.write_passengers(input_a / "run_2/passengers.csv", [20, 50])
            self.write_passengers(input_b / "run_1/passengers.csv", [0, 8, 35])
            self.write_passengers(input_b / "run_2/passengers.csv", [18, 45])

            frame_a, files_a = read_wait_data(input_a, "ETA")
            frame_b, files_b = read_wait_data(input_b, "Fair ETA")
            summary = build_summary(
                [
                    ("ETA", input_a, frame_a, files_a),
                    ("Fair ETA", input_b, frame_b, files_b),
                ],
                thresholds=(30, 45),
                overflow_at=45,
                bin_width=2,
            )

            self.assertEqual(len(frame_a), 5)
            self.assertEqual(len(frame_b), 5)
            self.assertEqual(summary["groups"]["ETA"]["run_count"], 2)
            self.assertEqual(
                summary["groups"]["ETA"]["thresholds"]["over_45"]["count"],
                1,
            )
            self.assertEqual(
                summary["groups"]["Fair ETA"]["thresholds"]["over_45"]["count"],
                0,
            )
            self.assertEqual(
                summary["comparison"]["wait_time_difference"]["average"],
                -2.8,
            )
            self.assertEqual(
                summary["comparison"]["threshold_difference"]["over_45"],
                {"count": -1, "percentage_points": -20.0},
            )

    def test_cli_writes_json_and_pooled_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_a = root / "a"
            input_b = root / "b"
            output = root / "output"
            self.write_passengers(input_a / "run/passengers.csv", [1, 2, 3])
            self.write_passengers(input_b / "run/passengers.csv", [2, 3, 4])

            with patch(
                "scripts.compare_wait_results.plot_histogram"
            ) as plot_histogram:
                exit_code = main(
                    [
                        str(input_a),
                        str(input_b),
                        "--label-a",
                        "A",
                        "--label-b",
                        "B",
                        "--output-dir",
                        str(output),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue((output / "pooled_wait_times.csv").is_file())
            summary = json.loads(
                (output / "wait_time_comparison.json").read_text(encoding="utf-8")
            )
            self.assertEqual(summary["groups"]["A"]["passenger_count"], 3)
            self.assertEqual(summary["groups"]["B"]["passenger_count"], 3)
            self.assertEqual(summary["histogram"]["overflow_at"], 30)
            self.assertEqual(summary["histogram"]["overflow_label"], ">30")
            plot_histogram.assert_called_once()

    def test_histogram_has_an_isolated_overflow_bin(self) -> None:
        self.assertEqual(
            histogram_bins(5, 2).tolist(),
            [0.0, 2.0, 4.0, 5.5, 6.5],
        )


if __name__ == "__main__":
    unittest.main()
