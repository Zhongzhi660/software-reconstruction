# Reconstruct micro_mask_overlap_score

You are given public observations from a real software-in-the-loop reference
artifact in the `microscopy_cell_analysis` family.

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
CellProfiler, scikit-image, Bio-Formats.

Parameter axes: `channel_selection`, `illumination_correction`, `measurement_feature`, `object_size_range`, `threshold_method`

Public scenarios:
- `public_1` parameters: `{"channel_selection": "compat", "illumination_correction": false, "measurement_feature": 13.3, "object_size_range": 15, "threshold_method": "baseline"}`
- `public_2` parameters: `{"channel_selection": "strict", "illumination_correction": true, "measurement_feature": 7.5, "object_size_range": 22, "threshold_method": "stress"}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on the
public scenarios and report which fields/signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode20`.
