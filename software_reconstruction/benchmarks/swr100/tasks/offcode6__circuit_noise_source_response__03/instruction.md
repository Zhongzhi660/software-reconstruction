# Reconstruct circuit_noise_source_response

You are given public observations from a real software-in-the-loop reference
artifact in the `circuit_simulation` family.

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
ngspice, xyce, PySpice.

Parameter axes: `analysis_type`, `component_value`, `source_waveform`, `temperature`, `tolerance`

Public scenarios:
- `public_1` parameters: `{"analysis_type": "strict", "component_value": 6.4325, "source_waveform": "source_waveform_7_public", "temperature": 11.0885, "tolerance": 6.975}`
- `public_2` parameters: `{"analysis_type": "baseline", "component_value": 0.3875, "source_waveform": "source_waveform_9_public", "temperature": 11.0885, "tolerance": 1.7825}`
- `public_3` parameters: `{"analysis_type": "baseline", "component_value": 4.25, "source_waveform": "source_waveform_10_public", "temperature": 2.3077, "tolerance": 1.9}`
- `public_4` parameters: `{"analysis_type": "strict", "component_value": 4.25, "source_waveform": "source_waveform_4_public", "temperature": 5.4615, "tolerance": 4.9}`
- `public_5` parameters: `{"analysis_type": "baseline", "component_value": 1.21, "source_waveform": "source_waveform_1_public", "temperature": 3.2577, "tolerance": 0.88}`
- `public_6` parameters: `{"analysis_type": "compat", "component_value": 3.135, "source_waveform": "source_waveform_14_public", "temperature": 0.7615, "tolerance": 2.6125}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode6`.
