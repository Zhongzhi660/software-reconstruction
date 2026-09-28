# Reconstruct ajv_defaults_coercion_compat

You are given public observations from a real software-in-the-loop reference
artifact in the `ajv_schema` family.

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
ajv, jsonschema.

Parameter axes: `additional_properties`, `format`, `recursive_ref`, `required_fields`, `union_branch`

Public scenarios:
- `public_1` parameters: `{"additional_properties": 3.0, "format": "edge", "recursive_ref": 4.0, "required_fields": 5.286, "union_branch": 4.571}`
- `public_2` parameters: `{"additional_properties": 1.713, "format": "csv", "recursive_ref": 6.744, "required_fields": 3.998, "union_branch": 5.971}`
- `public_3` parameters: `{"additional_properties": 1.021, "format": "baseline", "recursive_ref": 3.771, "required_fields": 2.829, "union_branch": 3.3}`
- `public_4` parameters: `{"additional_properties": 1.42, "format": "table", "recursive_ref": 5.844, "required_fields": 4.698, "union_branch": 2.521}`
- `public_5` parameters: `{"additional_properties": 9.743, "format": "compat", "recursive_ref": 10.85, "required_fields": 4.65, "union_branch": 9.521}`
- `public_6` parameters: `{"additional_properties": 8.906, "format": "report", "recursive_ref": 8.244, "required_fields": 9.683, "union_branch": 10.828}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `new10`.
