# Reconstruct acoustic_absorption_sweep

You are given public observations from a real software-in-the-loop reference
artifact in the `acoustics_room_simulation` family.

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
pyroomacoustics, scipy.signal.

Parameter axes: `absorption_level`, `microphone_array`, `rir_length`, `room_size`, `source_position`

Public scenarios:
- `public_1` parameters: `{"absorption_level": 19, "microphone_array": 6.9853, "rir_length": 9.3382, "room_size": 2, "source_position": "source-position-4"}`
- `public_2` parameters: `{"absorption_level": 4, "microphone_array": 3.3824, "rir_length": 8.0147, "room_size": 15, "source_position": "source-position-11"}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on the
public scenarios and report which fields/signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode20`.
