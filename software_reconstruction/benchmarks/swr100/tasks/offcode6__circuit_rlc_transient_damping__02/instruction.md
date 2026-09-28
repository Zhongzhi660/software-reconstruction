# Reconstruct circuit_rlc_transient_damping

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
- `public_1` parameters: `{"analysis_type": "compat", "component_value": 2.365, "source_waveform": "source_waveform_9_public", "temperature": 3.4269, "tolerance": 2.3375}`
- `public_2` parameters: `{"analysis_type": "strict", "component_value": 0.055, "source_waveform": "source_waveform_9_public", "temperature": 3.0038, "tolerance": 2.42}`
- `public_3` parameters: `{"analysis_type": "stress", "component_value": 2.65, "source_waveform": "source_waveform_5_public", "temperature": 6.0769, "tolerance": 0.55}`
- `public_4` parameters: `{"analysis_type": "stress", "component_value": 1.75, "source_waveform": "source_waveform_8_public", "temperature": 5.0769, "tolerance": 1.95}`
- `public_5` parameters: `{"analysis_type": "strict", "component_value": 1.395, "source_waveform": "source_waveform_11_public", "temperature": 6.0808, "tolerance": 7.905}`
- `public_6` parameters: `{"analysis_type": "edge", "component_value": 1.7825, "source_waveform": "source_waveform_16_public", "temperature": 4.0538, "tolerance": 5.89}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode6`.
