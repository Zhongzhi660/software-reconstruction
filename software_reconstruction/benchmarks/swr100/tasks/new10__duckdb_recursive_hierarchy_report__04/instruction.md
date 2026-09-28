# Reconstruct duckdb_recursive_hierarchy_report

You are given public observations from a real software-in-the-loop reference
artifact in the `duckdb_reporting` family.

The public observation files are available inside the environment at:

- `/app/observations/manifest.json`
- `/app/observations/reference_outputs.tar.gz`

Start by reading `manifest.json`, then inspect/extract `reference_outputs.tar.gz`.
The archive contains public scenario outputs, parameters, signatures, and
family-shaped native artifacts. Use those files as behavioral evidence. Do not
copy the observation files into the answer workspace.

Create an editable reconstruction project in `/app/workspace`. The private
verifier will run `/app/workspace/reconstruct.py` with hidden scenario JSON on
stdin, so provide an executable `reconstruct.py` that reads a scenario object,
uses `scenario["parameters"]`, and prints JSON.

The reconstruction should use the domain software/tooling implied by the task:
duckdb, jq.

Parameter axes: `nested_types`, `ordering_ties`, `partitioning`, `schema_evolution`, `window_frame`

Public scenarios:
- `public_1` parameters: `{"nested_types": 8.036, "ordering_ties": 10.0, "partitioning": 10, "schema_evolution": "compat", "window_frame": 6.375}`
- `public_2` parameters: `{"nested_types": 3.036, "ordering_ties": 2.857, "partitioning": 8, "schema_evolution": "baseline", "window_frame": 2.875}`
- `public_3` parameters: `{"nested_types": 1.714, "ordering_ties": 6.429, "partitioning": 9, "schema_evolution": "edge", "window_frame": 3.4}`
- `public_4` parameters: `{"nested_types": 7.0, "ordering_ties": 2.143, "partitioning": 5, "schema_evolution": "edge", "window_frame": 8.5}`
- `public_5` parameters: `{"nested_types": 3.3, "ordering_ties": 3.614, "partitioning": 3, "schema_evolution": "edge", "window_frame": 0.66}`
- `public_6` parameters: `{"nested_types": 4.164, "ordering_ties": 3.143, "partitioning": 1, "schema_evolution": "baseline", "window_frame": 5.005}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `new10`.
