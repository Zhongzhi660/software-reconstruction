# Reconstruct duckdb_outlier_quality_dashboard

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
- `public_1` parameters: `{"nested_types": 7.771, "ordering_ties": 2.186, "partitioning": 3, "schema_evolution": "compat", "window_frame": 4.59}`
- `public_2` parameters: `{"nested_types": 2.671, "ordering_ties": 2.429, "partitioning": 5, "schema_evolution": "stress", "window_frame": 10.03}`
- `public_3` parameters: `{"nested_types": 5.714, "ordering_ties": 7.714, "partitioning": 8, "schema_evolution": "edge", "window_frame": 9.0}`
- `public_4` parameters: `{"nested_types": 3.714, "ordering_ties": 5.143, "partitioning": 2, "schema_evolution": "baseline", "window_frame": 9.5}`
- `public_5` parameters: `{"nested_types": 2.2, "ordering_ties": 1.1, "partitioning": 3, "schema_evolution": "stress", "window_frame": 1.595}`
- `public_6` parameters: `{"nested_types": 2.285, "ordering_ties": 5.497, "partitioning": 26, "schema_evolution": "schema-evolution-10", "window_frame": 6.812}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `new10`.
