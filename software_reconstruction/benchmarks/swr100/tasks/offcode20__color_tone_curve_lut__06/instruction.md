# Reconstruct color_tone_curve_lut

You are given public observations from a real software-in-the-loop reference
artifact in the `color_imaging_pipeline` family.

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
colour-science, ImageMagick, scikit-image.

Parameter axes: `color_space`, `compression_quality`, `demosaic_method`, `tone_curve`, `white_point`

Public scenarios:
- `public_1` parameters: `{"color_space": "edge", "compression_quality": 29, "demosaic_method": "baseline", "tone_curve": 5.4, "white_point": 11.3}`
- `public_2` parameters: `{"color_space": "strict", "compression_quality": 31, "demosaic_method": "baseline", "tone_curve": 9.6, "white_point": 6.2}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on the
public scenarios and report which fields/signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode20`.
