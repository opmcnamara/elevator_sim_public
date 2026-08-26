#!/usr/bin/env bash

set -euo pipefail

# Run from the project root even when this script is called from elsewhere.
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

input_dir="${1:-test_files/standard_test_files/files_rate_1/}"
results_root="${2:-test_results/standard_test_results_10_elevators}"

case "$input_dir" in
    /*) ;;
    *) input_dir="$project_root/$input_dir" ;;
esac

case "$results_root" in
    /*) ;;
    *) results_root="$project_root/$results_root" ;;
esac

python_command="${PYTHON:-python3}"
num_elevators="${ELEVATORS:-10}"
num_floors="${FLOORS:-50}"
capacity="${CAPACITY:-10}"
start_floor="${START_FLOOR:-1}"
num_express_elevators="${EXPRESS_ELEVATORS:-0}"
express_floors="${EXPRESS_FLOORS:-}"
acceptable_wait="${ACCEPTABLE_WAIT:-30}"
late_wait_multiplier="${LATE_WAIT_MULTIPLIER:-10}"

# Override this space-separated list to run fewer schedulers, for example:
# SCHEDULERS="eta" bash scripts/batch_runner.sh
read -r -a schedulers <<< "${SCHEDULERS:-eta nearest round-robin}"

if [[ ! -d "$input_dir" ]]; then
    echo "error: input directory does not exist: $input_dir" >&2
    exit 1
fi

shopt -s nullglob
input_files=("$input_dir"/*.csv)
shopt -u nullglob

if [[ ${#input_files[@]} -eq 0 ]]; then
    echo "error: no CSV files found in: $input_dir" >&2
    exit 1
fi

if ! [[ "$num_express_elevators" =~ ^[0-9]+$ ]]; then
    echo "error: EXPRESS_ELEVATORS must be a nonnegative integer" >&2
    exit 1
fi
if ! [[ "$num_elevators" =~ ^[1-9][0-9]*$ ]]; then
    echo "error: ELEVATORS must be a positive integer" >&2
    exit 1
fi
if ((num_express_elevators >= num_elevators)); then
    echo "error: EXPRESS_ELEVATORS must be less than ELEVATORS" >&2
    exit 1
fi
if ((num_express_elevators > 0)) && [[ -z "$express_floors" ]]; then
    echo "error: EXPRESS_FLOORS is required when EXPRESS_ELEVATORS is positive" >&2
    exit 1
fi
if ((num_express_elevators == 0)) && [[ -n "$express_floors" ]]; then
    echo "error: EXPRESS_FLOORS requires at least one express elevator" >&2
    exit 1
fi

for scheduler in "${schedulers[@]}"; do
    case "$scheduler" in
        eta|fair-eta|nearest|round-robin) ;;
        *)
            echo "error: unknown scheduler: $scheduler" >&2
            exit 1
            ;;
    esac
done

mkdir -p "$results_root"

completed_runs=0
total_runs=$((${#input_files[@]} * ${#schedulers[@]}))

for input_file in "${input_files[@]}"; do
    input_name="$(basename "$input_file" .csv)"

    for scheduler in "${schedulers[@]}"; do
        folder_base="$results_root/${input_name}_${scheduler}"
        output_dir="$folder_base"
        run_number=2

        # Preserve earlier output if the same dataset/scheduler is run again.
        while [[ -e "$output_dir" ]]; do
            printf -v run_suffix '%02d' "$run_number"
            output_dir="${folder_base}_run_${run_suffix}"
            ((run_number += 1))
        done

        mkdir -p "$output_dir"
        echo "[$((completed_runs + 1))/$total_runs] $input_name with $scheduler"

        simulation_command=(
            "$python_command" -m elevator_sim "$input_file"
            --elevators "$num_elevators"
            --floors "$num_floors"
            --capacity "$capacity"
            --start-floor "$start_floor"
            --express-elevators "$num_express_elevators"
            --scheduler "$scheduler"
        )
        if ((num_express_elevators > 0)); then
            simulation_command+=(--express-floors "$express_floors")
        fi
        if [[ "$scheduler" == "fair-eta" ]]; then
            simulation_command+=(
                --acceptable-wait "$acceptable_wait"
                --late-wait-multiplier "$late_wait_multiplier"
            )
        fi
        simulation_command+=(--output "$output_dir")

        if "${simulation_command[@]}" \
            >"$output_dir/run.log" 2>&1; then
            echo "  wrote: $output_dir"
        else
            echo "error: simulation failed; see $output_dir/run.log" >&2
            exit 1
        fi

        ((completed_runs += 1))
    done
done

echo "Completed $completed_runs runs."
echo "Results: $results_root"
