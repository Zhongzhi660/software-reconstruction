# Reconstruct grid_island_detection_qc

You are given public observations from a real software-in-the-loop reference
artifact in the `power_grid_simulation` family.

The public observation files are available inside the environment at:

- `/app/observations/manifest.json`
- `/app/observations/reference_outputs.tar.gz`

Start by reading `manifest.json`, then inspect/extract `reference_outputs.tar.gz`.
The archive contains `public_1/` and `public_2/` outputs, parameters, signatures,
and family-shaped artifacts. Use those files as behavioral evidence. Do not copy
the observation files into the answer workspace.

Create an editable reconstruction project in `/app/workspace`. The private
verifier will run `/app/workspace/reconstruct.py` with hidden scenario JSON on
stdin, so provide an executable `reconstruct.py` that reads a scenario object,
uses `scenario["parameters"]`, and prints JSON.

The reconstruction should use the domain software/tooling implied by the task:
pandapower, PyPSA, OpenDSSDirect.

Parameter axes: `generator_dispatch`, `line_outage`, `load_scale`, `tap_position`, `voltage_limit`

Public scenarios:
- `public_1` parameters: `{"generator_dispatch": 5.5176, "line_outage": false, "load_scale": 11, "tap_position": [16.8, 18.2, 19.6], "voltage_limit": 5.278}`
- `public_2` parameters: `{"generator_dispatch": 8.8941, "line_outage": false, "load_scale": 17, "tap_position": [1.4, 2.8, 4.2], "voltage_limit": 7.742}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on the
public scenarios and report which fields/signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode20`.
