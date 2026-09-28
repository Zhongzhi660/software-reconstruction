# Reconstruct sqlite_northwind_supplier_fillrate

You are given public observations from a real software-in-the-loop reference
artifact in the `sqlite_analytics` family.

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
sqlite3.

Parameter axes: `date_window`, `join_depth`, `null_policy`, `recovery_mode`, `schema_version`

Public scenarios:
- `public_1` parameters: `{"date_window": 9.9, "join_depth": 7, "null_policy": "baseline", "recovery_mode": "stress", "schema_version": "compat"}`
- `public_2` parameters: `{"date_window": 9.5, "join_depth": 3, "null_policy": "edge", "recovery_mode": "strict", "schema_version": "baseline"}`
- `public_3` parameters: `{"date_window": 2.365, "join_depth": 3, "null_policy": "compat", "recovery_mode": "edge", "schema_version": "baseline"}`
- `public_4` parameters: `{"date_window": 5.5, "join_depth": 4, "null_policy": "edge", "recovery_mode": "stress", "schema_version": "strict"}`
- `public_5` parameters: `{"date_window": 14.105, "join_depth": 9, "null_policy": "edge", "recovery_mode": "compat", "schema_version": "compat"}`
- `public_6` parameters: `{"date_window": 11.78, "join_depth": 11, "null_policy": "strict", "recovery_mode": "stress", "schema_version": "compat"}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `new10`.
