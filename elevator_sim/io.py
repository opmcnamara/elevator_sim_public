"""CSV input and simulation artifact writers."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import PassengerRequest
from .simulation import SimulationResult
from .statistics import build_summary


REQUIRED_COLUMNS = ("time", "id", "source", "dest")


def read_requests(path: str | Path) -> list[PassengerRequest]:
    input_path = Path(path)
    with input_path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        missing = set(REQUIRED_COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"input CSV is missing columns: {', '.join(sorted(missing))}")

        requests: list[PassengerRequest] = []
        for line_number, row in enumerate(reader, start=2):
            try:
                requests.append(
                    PassengerRequest(
                        request_time=int(row["time"]),
                        passenger_id=row["id"].strip(),
                        source=int(row["source"]),
                        destination=int(row["dest"]),
                    )
                )
            except (TypeError, ValueError, AttributeError) as error:
                raise ValueError(
                    f"invalid request on CSV line {line_number}: {error}"
                ) from error
    return requests


def write_results(result: SimulationResult, output_dir: str | Path) -> dict[str, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "positions": directory / "positions.csv",
        "passengers": directory / "passengers.csv",
        "events": directory / "events.csv",
        "summary": directory / "summary.json",
    }

    position_fields = ["time"] + [
        f"elevator_{index}" for index in range(1, result.config.num_elevators + 1)
    ]
    with paths["positions"].open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=position_fields)
        writer.writeheader()
        writer.writerows(result.position_log)

    passenger_fields = [
        "id",
        "request_time",
        "source",
        "dest",
        "elevator",
        "pickup_time",
        "dropoff_time",
        "wait_time",
        "travel_time",
        "total_time",
    ]
    with paths["passengers"].open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=passenger_fields)
        writer.writeheader()
        for passenger in result.passengers:
            writer.writerow(
                {
                    "id": passenger.passenger_id,
                    "request_time": passenger.request_time,
                    "source": passenger.source,
                    "dest": passenger.destination,
                    "elevator": passenger.assigned_elevator,
                    "pickup_time": passenger.pickup_time,
                    "dropoff_time": passenger.dropoff_time,
                    "wait_time": passenger.wait_time,
                    "travel_time": passenger.travel_time,
                    "total_time": passenger.total_time,
                }
            )

    with paths["events"].open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=["time", "event", "elevator", "passenger", "floor"]
        )
        writer.writeheader()
        for event in result.events:
            writer.writerow(
                {
                    "time": event.time,
                    "event": event.event,
                    "elevator": event.elevator_id,
                    "passenger": event.passenger_id,
                    "floor": event.floor,
                }
            )

    with paths["summary"].open("w", encoding="utf-8") as stream:
        json.dump(build_summary(result), stream, indent=2)
        stream.write("\n")

    return paths

