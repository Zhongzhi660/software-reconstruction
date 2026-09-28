# Reconstruct video_subtitle_burnin_policy

You are given public observations from a real software-in-the-loop reference
artifact in the `video_broadcast_qc` family.

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
ffmpeg, ffprobe, VMAF.

Parameter axes: `audio_layout`, `frame_rate`, `gop_size`, `pixel_format`, `subtitle_policy`

Public scenarios:
- `public_1` parameters: `{"audio_layout": "stress", "frame_rate": "stress", "gop_size": 8, "pixel_format": 1.3912, "subtitle_policy": "stress"}`
- `public_2` parameters: `{"audio_layout": "domain_specific", "frame_rate": "strict", "gop_size": 10, "pixel_format": 0.8735, "subtitle_policy": "stress"}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on the
public scenarios and report which fields/signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode20`.
