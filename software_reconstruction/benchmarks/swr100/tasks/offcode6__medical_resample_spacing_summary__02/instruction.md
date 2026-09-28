# Reconstruct medical_resample_spacing_summary

You are given public observations from a real software-in-the-loop reference
artifact in the `medical_imaging` family.

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
pydicom, nibabel, SimpleITK.

Parameter axes: `mask_threshold`, `modality`, `orientation`, `slice_range`, `window_level`

Public scenarios:
- `public_1` parameters: `{"mask_threshold": 0.825, "modality": "baseline", "orientation": "stress", "slice_range": 2, "window_level": 7}`
- `public_2` parameters: `{"mask_threshold": 2.5025, "modality": "compat", "orientation": "compat", "slice_range": 9, "window_level": 2}`
- `public_3` parameters: `{"mask_threshold": 2.55, "modality": "edge", "orientation": "compat", "slice_range": 16, "window_level": 14}`
- `public_4` parameters: `{"mask_threshold": 3.6, "modality": "stress", "orientation": "compat", "slice_range": 12, "window_level": 9}`
- `public_5` parameters: `{"mask_threshold": 7.44, "modality": "compat", "orientation": "strict", "slice_range": 8, "window_level": 16}`
- `public_6` parameters: `{"mask_threshold": 2.635, "modality": "baseline", "orientation": "edge", "slice_range": 22, "window_level": 11}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode6`.
