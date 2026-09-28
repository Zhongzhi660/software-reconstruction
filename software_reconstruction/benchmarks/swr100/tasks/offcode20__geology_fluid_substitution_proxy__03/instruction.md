# Reconstruct geology_fluid_substitution_proxy

You are given public observations from a real software-in-the-loop reference
artifact in the `geology_well_log_analysis` family.

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
welly, striplog, bruges.

Parameter axes: `curve_selection`, `depth_interval`, `lithology_alias`, `smoothing_window`, `unit_system`

Public scenarios:
- `public_1` parameters: `{"curve_selection": "domain_specific", "depth_interval": 1.55, "lithology_alias": 11.1235, "smoothing_window": 3, "unit_system": 9.5735}`
- `public_2` parameters: `{"curve_selection": "domain_specific", "depth_interval": 8.8441, "lithology_alias": 1.8235, "smoothing_window": 16, "unit_system": 3.3735}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on the
public scenarios and report which fields/signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode20`.
