# Reconstruct ajv_recursive_api_payload

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
- `public_1` parameters: `{"additional_properties": 8.036, "format": "stress", "recursive_ref": 8.036, "required_fields": 8.929, "union_branch": 6.429}`
- `public_2` parameters: `{"additional_properties": 6.606, "format": "json", "recursive_ref": 3.922, "required_fields": 3.319, "union_branch": 11.257}`
- `public_3` parameters: `{"additional_properties": 6.429, "format": "edge", "recursive_ref": 1.0, "required_fields": 6.571, "union_branch": 7.857}`
- `public_4` parameters: `{"additional_properties": 4.57, "format": "yaml", "recursive_ref": 6.887, "required_fields": 6.712, "union_branch": 4.4}`
- `public_5` parameters: `{"additional_properties": 1.807, "format": "compat", "recursive_ref": 0.55, "required_fields": 2.279, "union_branch": 0.629}`
- `public_6` parameters: `{"additional_properties": 3.384, "format": "report", "recursive_ref": 5.058, "required_fields": 3.676, "union_branch": 2.757}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `new10`.
