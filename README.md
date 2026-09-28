# Software-in-the-Loop Reconstruction

This repository contains the core implementation accompanying the paper.
Software-in-the-Loop Reconstruction asks terminal agents to
recover executable software behavior from public observations and evaluates
their implementations on hidden scenarios with semantic verifiers.

The complete collection contains 3,000 reconstruction tasks derived from 500
workflow demonstrations across 46 software families.

## Scope

The repository contains the essential source code for:

1. parameter and scenario generation;
2. task materialization and hidden-verifier installation;
3. oracle validation and behavioral profiling;
4. the frozen SWR100 benchmark release and its auditing tools; and
5. verified-trajectory conversion for supervised fine-tuning.

The 100 materialized SWR100 tasks are included under
`software_reconstruction/benchmarks/swr100/tasks/`. Each task contains its
agent-facing environment and the private evaluator required to reproduce the
reported benchmark; “private” denotes files withheld from the agent at
evaluation time. The remaining generated datasets, rollout traces, model
checkpoints, plotting code, paper artifacts, and machine-specific deployment
files are not included.

## Source Layout

```text
software_reconstruction/
├── task_generation/
│   ├── scenario_generation/
│   ├── materialization/
│   ├── oracle_validation/
│   ├── verifier_integration/
│   └── validate_task_contract.py
├── profiling/
│   ├── profile_task_behavior.py
│   └── profile_task_behavior_daytona.py
├── benchmarks/
│   └── swr100/
│       ├── tasks/
│       ├── semantic_comparator.py
│       ├── reference_oracles.py
│       ├── audit_benchmark.py
│       ├── repair_benchmark.py
│       ├── finalize_benchmark.py
│       ├── sync_from_swr3000.py
│       └── validate_sync.py
├── release/
│   ├── build_swr3000_inventory.py
│   └── materialize_rollout_dataset.py
└── training/
    └── build_verified_trajectory_sft.py
```

## Basic Usage

The controller-side tools require Python 3.10 or later. Optional dependencies
vary by software family and execution backend. Compressed task assets are
stored with Git LFS; run `git lfs pull` after cloning if they were not fetched
automatically.

Validate a materialized task collection:

```bash
python3 software_reconstruction/task_generation/validate_task_contract.py \
  /path/to/materialized_tasks \
  --report /path/to/validation_report.json
```

Profile task behavior locally:

```bash
python3 software_reconstruction/profiling/profile_task_behavior.py \
  --source swr=/path/to/tasks \
  --out-dir /path/to/profile_output
```

Profile reference behavior in Daytona:

```bash
export DAYTONA_API_KEY="<configured outside this repository>"
python3 software_reconstruction/profiling/profile_task_behavior_daytona.py \
  --source swr=/path/to/tasks \
  --out-dir /path/to/profile_output
```

Audit an SWR100 release:

```bash
python3 software_reconstruction/benchmarks/swr100/audit_benchmark.py \
  --root /path/to/materialized/swr100
```

Build supervised examples from verified trajectories:

```bash
export SWR_DATA_ROOT="/path/to/software_reconstruction_data"
export SWR_QMAX_POOL="/path/to/verified_pass_pool.jsonl"
export SWR_Q27_ROLLOUT_ROOT="/path/to/rollout_root"
python3 software_reconstruction/training/build_verified_trajectory_sft.py \
  --output-dir /path/to/sft_output
```

Run each entry point with `--help` for its complete interface. Input and output
locations are supplied through command-line options or documented environment
variables; no credentials are stored in this repository.
