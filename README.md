# KKR_take_home

A deterministic, discrete-time simulation of a modern destination-dispatch
elevator bank. Passengers submit an origin and destination, are assigned to one
car immediately, and remain assigned until completion.

## Time spent

A total amount of time of ~13 hours was spent on this project

## How the simulation works

At each timestamp, the engine performs these operations in a fixed order:

1. Release only requests whose `time` equals the current timestamp.
2. Immediately assign each released passenger to an elevator.
3. Drop off and pick up passengers at the current floors (door time is zero).
4. Record every elevator position for that timestamp.
5. If work remains, move each active elevator by exactly one floor and advance
   time by one.

The engine never jumps over quiet timestamps. Future requests live behind a
single release cursor and are never passed to a scheduler, so an assignment
cannot peek ahead.

Each car follows a LOOK/SCAN-style direction policy. It continues in its current
direction while any known stop is ahead, reverses when no demand remains ahead,
and becomes idle when its assigned workload is empty. A passenger boards only
when the car is moving in the passenger's requested direction. At a shared floor,
waiting passengers board oldest-first up to the configured capacity. This makes
direction and capacity behavior explicit and guarantees that every passenger in
a finite request list is eventually served.

A scheduler algorithm controls which elevator new passengers are assigned to, see the 
Scheduler section below for more details.

# 1. Running the Code

## Installation

Python 3.11 or newer is required. Users can do one of the following to run the simulation
1. Create and activate a virtual environment, installing necessary dependencies
2. Use Docker (see Docker section for details)

## Virtual Environment

```bash
python3 -m venv elev-sim-venv
source elev-sim-venv/bin/activate
```

Then install the project and all required packages. `pip` reads the dependency
list from `pyproject.toml` automatically:

```bash
python3 -m pip install --upgrade pip
python3 -m pip install -e .
```

The `-e` option creates an editable installation, so changes to the source code
are available immediately without reinstalling the project. Activate the
virtual environment again with `source elev-sim-venv/bin/activate` whenever you
open a new terminal session.

## Quick start

The simulation expects a CSV-type file, with the following fields: `time, id, source, dest`

The simulation allows for a configurable number of
  - elevators
  - floors in the building
  - maximum passengers per elevator

If no values for a given field are provided, default values of 8, 50, and 8 are used, respectively.

The general format of the command to run the simulation from the command line interface (CLI) is:

```bash
python3 -m elevator_sim /path/to/input.csv \
  --elevators 8 \
  --floors 50 \
  --capacity 8 \
  --output /path/to/desired/output/folder
```

For example, if you wanted to run a simulation for 10 elevators in a building with 50 floors, with a max
elevator capacity of 8, you would write:

```bash
python3 -m elevator_sim example_files/requests_1.csv \
  --elevators 10 \
  --floors 50 \
  --capacity 8 \
  --output example_output/requests_1_output
```

The CLI prints the summary and writes the following files at the output destination:

- `positions.csv`: every elevator's floor at every integer timestamp, starting
  at time 0.
- `passengers.csv`: assignment, pickup, drop-off, wait, travel, and total times.
- `events.csv`: an auditable assignment/pickup/drop-off trace.
- `summary.json`: min, max, average, median, and p95 wait/travel/total times plus
  notable observations.

## Docker

If Docker is installed you can build a reusable image from the project root:

```bash
docker build -t kkr-elevator-sim .
```

Run the bundled example by mounting its input file read-only and mounting a
local directory for the generated results:

```bash
mkdir -p test_results/docker_example

docker run --rm \
  --mount type=bind,source="$PWD/example_files/requests_1.csv",target=/data/requests.csv,readonly \
  --mount type=bind,source="$PWD/test_results/docker_example",target=/results \
  kkr-elevator-sim \
  /data/requests.csv \
  --elevators 10 \
  --floors 50 \
  --capacity 8 \
  --output /results
```

To process another CSV without rebuilding the image, replace the first mount's
`source` with that file's absolute path. The input must contain the columns
`time,id,source,dest`. Results written inside the container to `/results` appear
in the mounted local output directory.


## Scheduling algorithms

The default `eta` scheduler evaluates every elevator with two isolated shadow
simulations: its known workload as-is, and the same workload with the new
passenger. The score is the increase in summed passenger total time, so it
includes the candidate's completion time and any delay imposed on existing
riders. Candidate total time, wait, workload, and car ID are deterministic
tie-breakers. Because the predictor reuses the real movement rules, capacity,
direction, existing pickups, and existing drop-offs all affect the decision.

For an explicit fairness/efficiency comparison, `fair-eta` uses the same shadow
predictions but applies a simple service-level penalty to each predicted wait:

```text
excess_wait = max(0, predicted_wait - acceptable_wait)
wait_cost = predicted_wait + late_wait_multiplier * excess_wait ** 2
```

By default, waits up to 30 ticks cost one unit per tick and excess waits receive
a quadratic penalty with coefficient 10. The threshold represents the
building's acceptable service level, while the multiplier controls how much
average efficiency the scheduler may trade to avoid late service. With these
defaults, waits of 25, 30, 35, and 45 ticks have costs of 25, 30, 285, and
2,295 respectively. Run it with:

```bash
python3 -m elevator_sim example_files/requests_1.csv \
  --elevators 8 \
  --floors 60 \
  --capacity 8 \
  --scheduler fair-eta \
  --acceptable-wait 30 \
  --late-wait-multiplier 10 \
  --output example_output/requests_1_output_fair_eta
```

The selected threshold and multiplier are recorded in `summary.json` under
`scheduler_parameters`. This objective improves fairness incentives but does
not guarantee a strict maximum wait because assignments remain greedy and are
never revised.

Two comparison policies are included:

- `nearest`: distance plus a penalty when a moving car has already passed the
  passenger, then workload and ID tie-breakers.
- `round-robin`: even assignment without position awareness, serving as a useful
  baseline for fairness/efficiency comparisons.

### Express elevators

Additional functionality is built in to optionally reserve some of the cars as express elevators 
that only serve certain floors. 

These can be passed to the simulation using the `express-elevators, express-floors` arguments. 

```bash
python3 -m elevator_sim example_files/requests_1.csv\
  --elevators 10 \
  --floors 50 \
  --capacity 8 \
  --scheduler eta \
  --express-elevators 2 \
  --express-floors 1,10,20,30,40,50 \
  --output example_output/express_elevator_test
```

In this example, elevators 9 and 10 are express cars. A request is eligible to use an 
express elevator only when both the request's source and destination are in the configured floor
list. It still moves through intermediate floors at one floor per tick but does
not accept pickups or drop-offs there. At least one regular elevator is always
required in order to serve the entire building. 

# 2. Assumptions, Simplifications, Tradeoffs

## Assumptions & Simplifications

The following assumptions were given by the assignment description

- A passenger submits both their origin and destination floor at the time of request
- The system immediately assigns them to a specific elevator
- Once assigned, the passenger cannot modify their destination
- Time is modeled in discrete units
- One unit of time = one floor of travel (up or down)


I made the additional assumptions to keep the logic of the simulation simple

- Every passenger must make a request (i.e., no "freeloading" behind someone who made the same request)
- Onboarding and offloading passengers takes 0 time
  - Note: This is necessary to model the elevator always moving one floor per unit of time
- Passenger ID's are assigned sequentially in order of requests (used for tiebreakers)
- All requests are well-formed (the simulation will throw an error otherwise)
- A passenger's assigned elevator will never be changed once assigned 


## Tradeoffs

As with any real-life system, there are tradeoffs to be made when considering the efficiency of the system
vs. the practical experience of consumers using said system. In this particular situation, we want to 
minimize total time per passenger but we should also keep in mind the satisfaction of the passengers. 

Solely minimizing total time may lead to a frustrating experience using the elevator, therefore
I decided to sacrifice some global optimality to guarantee several nice properties for passengers

- A passenger onboard an elevator will never be travelling in the wrong direction
- An elevator will never reverse direction with passengers onboard
- Once boarded, passengers will never face additional delays
  - Note: This only holds under the assumption that offloading and onboarding takes 0 time


One can easily imagine a scenario where an elevator reverses direction to pick up a passenger on the floor below
while someone is currently traveling upward in the elevator. It might technically be more "efficient" overall, 
but would likely be extremely frustrating to the passenger already on the elevator 

Built into these tradeoffs is the implicit assumption that extra time traveling in the elevator is worse
than extra time waiting on the floor. This is a reasonable assumption as elevators are cramped and are 
generally less pleasant to be in than a regular floor.


# 3. Future Improvements

There are a variety of improvments that could be made to the simulation


- Additional testing
  - The general testing focusing on a realistic single building.
  More testing could be done to test the simulation under a variety of configurations. In 
  particular, it could be tested under different type of pathological conditions to see where
  the simulation might break down.

- Code efficiency
  - The code could be optimized to run faster. In particular, for the ETA scheduler it does two shadow
  simulations per elevator for each new passenger. However, if the new passenger isn't added to the elevator
  then the baseline simulation won't change for the next passenger. Implementing a cache to store these 
  intermediate baseline result would help cut down significantly on computation


- Interactive API
  - The simulation is currently run through the CLI, so creating an API through a web browser that has
  toggleable fields where a user can type inputs directly in would be a nice next step
  
- Dashboard 
  - creating an interactive dashboard where a user can see elevator positions at any given time, and a 
  list of onboard/waiting passengers and their estimated times to completion



  There are also a number of ideas to consider to make the simulation more realistic

  - Modeling continuous time instead of discrete 

  - Accounting for additional time needed for onboarding/offloading passengers

  - Accounting for non-constant elevator travel time (can pick up speed)


# 4 Bonus Materials  

Below is additional functionality for creating and running various test files.

## Unit Tests

A suite of unit tests are provided to make sure the simulation code is running properly. 
The tests can be run with the following command:

```bash
python3 -m unittest discover -s unit_tests -v
```

If using Docker, the suite of unit tests are run automatically when creating a Docker image.

## Generate reproducible request files

`scripts/generate_poisson_requests.py` creates
lobby-heavy request datasets for repeated scheduler comparisons. By default it
writes 10 CSV files with 10,000 requests each for a 50-floor building:


```bash
python3 scripts/generate_poisson_requests.py \
  --output-dir /path/to/files_destination 
```

Each file uses a different seed derived reproducibly from `--base-seed`. At each
integer timestamp, the number of new requests is sampled from a Poisson distribution
with a specified `arrival_rate`; generation continues until the file contains exactly
10,000 requests, and rows are sorted before export. Origins are uniform across
Floors 2 through 50 after independently assigning 20% of request origins to the
lobby. For a Floor 1 origin, the destination is uniform across floors 2 through
50. For other origins, the destination is Floor 1 with probability 70%;
otherwise it is uniform across the non-lobby floors other than the origin.
Poisson counts and floor choices use NumPy's reproducible `Generator` API. Each
file is assembled in a preallocated pandas DataFrame: timestamps are populated
first, followed by vectorized source and destination generation.

The default values can be overridden when running the script. 

```bash
python3 scripts/generate_poisson_requests.py \
  --output-dir test_files/poisson_rate_1 \
  --files 10 \
  --requests-per-file 10000 \
  --num-floors 50 \
  --arrival-rate 1.0 \
  --lobby-source-probability 0.2 \
  --lobby-probability 0.7 \
  --base-seed 20260823
```

## Generate files with Docker

It is also possible to generate the request files using an existing Docker image, simply modify the command.
Note that the directory you want to write the files to must already exist, so make it first before running the 
docker command

```bash
mkdir -p test_files/desired/write/location
```

```bash
docker run --rm \
  --entrypoint python3 \
  --mount type=bind,source="$PWD/test_files/desired/write/location",target=/output \
  kkr-elevator-sim \
  scripts/generate_poisson_requests.py \
  --output-dir /output \
  --files 10 \
  --requests-per-file 10000 \
  --num-floors 50 \
  --arrival-rate 1.0 \
  --lobby-source-probability 0.2 \
  --lobby-probability 0.7 \
  --base-seed 20260823
```


## Running batches of test files

The Bash script `scripts/batch_runner.sh` allows a user to run a simulation for each input file
located in the specified input directory. The script can be run with a single scheduler, or a list of schedulers
by providing the desired schedulers separated by spaces.

```bash
ELEVATORS=10 \
FLOORS=50 \
CAPACITY=8 \
START_FLOOR=1 \
EXPRESS_ELEVATORS=2 \
EXPRESS_FLOORS="1,10,20,30,40,50" \
SCHEDULERS="eta fair-eta nearest round-robin" \
ACCEPTABLE_WAIT=30 \
LATE_WAIT_MULTIPLIER=10 \
bash scripts/batch_runner.sh \
  "/path/to/input/csv/folder" \
  "/path/to/test_results/folder"
```

The default values in `scripts/batch_runner.sh` are

```text
num_elevators="${ELEVATORS:-10}"
num_floors="${FLOORS:-50}"
capacity="${CAPACITY:-10}"
start_floor="${START_FLOOR:-1}"
num_express_elevators="${EXPRESS_ELEVATORS:-0}"
express_floors="${EXPRESS_FLOORS:-}"
acceptable_wait="${ACCEPTABLE_WAIT:-30}"
late_wait_multiplier="${LATE_WAIT_MULTIPLIER:-10}"
```

## Batch runs with Docker Compose

Batch runs can also be done within a Docker image.
`compose.yaml` provides a shorter interface for running every CSV in an input
directory. By default, it mounts local `test_files` at `/input` read-only and
local `test_results` at `/results`:

```bash
docker compose run --rm batch \
  /input/poisson_rate_1 \
  /results/eight_elevators
```

Use `INPUT_DIR` and `RESULTS_DIR` to mount directories located elsewhere. The
input path should be the directory containing the CSV files:

```bash
INPUT_DIR="/absolute/path/to/request_files" \
RESULTS_DIR="$PWD/test_results" \
ELEVATORS=8 \
SCHEDULERS="eta fair-eta" \
docker compose run --rm batch \
  /input \
  /results/eight_elevators
```

The remaining batch settings can also be overridden with `FLOORS`, `CAPACITY`,
`START_FLOOR`, `EXPRESS_ELEVATORS`, `EXPRESS_FLOORS`, `ACCEPTABLE_WAIT`, and
`LATE_WAIT_MULTIPLIER`.

## Python API

The required list-taking function is `elevator_sim.simulate`. It accepts either
`PassengerRequest` objects or dictionaries using the case-study field names:

```python
from elevator_sim import simulate

result = simulate(
    [
        {"time": 0, "id": "passenger1", "source": 1, "dest": 51},
        {"time": 0, "id": "passenger2", "source": 1, "dest": 37},
        {"time": 10, "id": "passenger3", "source": 20, "dest": 1},
    ],
    num_elevators=8,
    num_floors=60,
    capacity=8,
    scheduler="eta",
    num_express_elevators=1,
    express_floors=[1, 20, 40, 60],
)
```

`result.passengers`, `result.position_log`, and `result.events` make the run easy
to inspect in a notebook or test. `elevator_sim.io.write_results` writes the
standard output artifacts.

## Project layout


```text
elevator_sim/
  api.py          public list-based simulation function
  express_elevator.py  floor-restricted Elevator subclass
  models.py       requests, states, configuration, and events
  elevator.py     car state machine and shadow prediction
  schedulers.py   ETA, fair-ETA, nearest-car, and round-robin policies
  simulation.py   tick loop and no-peeking request release
  statistics.py   aggregate metrics and observations
  io.py           CSV input and CSV/JSON output
  cli.py          command-line interface
example_files/    runnable request CSV with 2000 requests
scripts/          reproducible workload-generation utilities
unit_tests/       behavior, constraints, validation, and I/O tests
```
