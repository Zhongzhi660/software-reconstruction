# Reconstruct map_boundary_clip_antimeridian

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
- `public_1` parameters: `{"label_priority": 3.0882, "layer_filter": 2.6471, "projection": [3.75, 5.0, 6.25], "simplification_tolerance": 3.2125, "zoom_range": 6}`
- `public_2` parameters: `{"label_priority": 3.0882, "layer_filter": 6.1765, "projection": [10.0, 11.25, 12.5], "simplification_tolerance": 0.9625, "zoom_range": 20}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on the
public scenarios and report which fields/signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode20`.
