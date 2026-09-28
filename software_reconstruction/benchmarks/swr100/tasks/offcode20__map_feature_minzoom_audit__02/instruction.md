# Reconstruct map_feature_minzoom_audit

You are given public observations from a real software-in-the-loop reference
artifact in the `cartography_map_rendering` family.

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
tippecanoe, osmium, vector-tile tooling.

Parameter axes: `label_priority`, `layer_filter`, `projection`, `simplification_tolerance`, `zoom_range`

Public scenarios:
- `public_1` parameters: `{"label_priority": 3.8824, "layer_filter": 1.5529, "projection": [6.6, 7.15, 7.7], "simplification_tolerance": 1.4135, "zoom_range": 10}`
- `public_2` parameters: `{"label_priority": 2.2324, "layer_filter": 2.4912, "projection": [3.85, 4.4, 4.95], "simplification_tolerance": 2.4915, "zoom_range": 7}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on the
public scenarios and report which fields/signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode20`.
