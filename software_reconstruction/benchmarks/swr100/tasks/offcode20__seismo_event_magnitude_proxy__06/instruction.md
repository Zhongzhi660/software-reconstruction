# Reconstruct seismo_event_magnitude_proxy

You are given public observations from a real software-in-the-loop reference
artifact in the `seismology_waveform_processing` family.

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
ObsPy.

Parameter axes: `filter_band`, `phase_pick`, `response_removal`, `station_selection`, `window_duration`

Public scenarios:
- `public_1` parameters: `{"filter_band": 8.9, "phase_pick": 6.4, "response_removal": true, "station_selection": "edge", "window_duration": 32}`
- `public_2` parameters: `{"filter_band": 4.1, "phase_pick": 5.2, "response_removal": true, "station_selection": "domain_specific", "window_duration": 29}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on the
public scenarios and report which fields/signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode20`.
