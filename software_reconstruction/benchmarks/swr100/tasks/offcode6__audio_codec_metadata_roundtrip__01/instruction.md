# Reconstruct audio_codec_metadata_roundtrip

You are given public observations from a real software-in-the-loop reference
artifact in the `audio_signal_processing` family.

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
ffmpeg, sox, python scipy.signal, librosa.

Parameter axes: `channel_layout`, `filter_type`, `noise_profile`, `sample_rate`, `window_size`

Public scenarios:
- `public_1` parameters: `{"channel_layout": "edge", "filter_type": "stress", "noise_profile": "compat", "sample_rate": 2, "window_size": 9}`
- `public_2` parameters: `{"channel_layout": "stress", "filter_type": "stress", "noise_profile": "baseline", "sample_rate": 3, "window_size": 9}`
- `public_3` parameters: `{"channel_layout": "strict", "filter_type": "compat", "noise_profile": "edge", "sample_rate": 5, "window_size": 4}`
- `public_4` parameters: `{"channel_layout": "compat", "filter_type": "baseline", "noise_profile": "compat", "sample_rate": 3, "window_size": 6}`
- `public_5` parameters: `{"channel_layout": "stress", "filter_type": "strict", "noise_profile": "baseline", "sample_rate": 22, "window_size": 6}`
- `public_6` parameters: `{"channel_layout": "baseline", "filter_type": "compat", "noise_profile": "baseline", "sample_rate": 11, "window_size": 25}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode6`.
