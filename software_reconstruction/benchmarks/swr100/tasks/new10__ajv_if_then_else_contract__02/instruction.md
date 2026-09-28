# Reconstruct ajv_if_then_else_contract

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
- `public_1` parameters: `{"additional_properties": 1.807, "format": "compat", "recursive_ref": 2.593, "required_fields": 1.336, "union_branch": 4.243}`
- `public_2` parameters: `{"additional_properties": 2.284, "format": "report", "recursive_ref": 3.801, "required_fields": 5.798, "union_branch": 4.721}`
- `public_3` parameters: `{"additional_properties": 6.857, "format": "edge", "recursive_ref": 2.286, "required_fields": 6.143, "union_branch": 5.143}`
- `public_4` parameters: `{"additional_properties": 2.142, "format": "yaml", "recursive_ref": 5.601, "required_fields": 6.569, "union_branch": 6.828}`
- `public_5` parameters: `{"additional_properties": 1.55, "format": "edge", "recursive_ref": 3.543, "required_fields": 9.743, "union_branch": 11.514}`
- `public_6` parameters: `{"additional_properties": 9.349, "format": "csv", "recursive_ref": 4.48, "required_fields": 7.248, "union_branch": 8.835}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `new10`.
