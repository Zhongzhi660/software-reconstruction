# Reconstruct circuit_bjt_amplifier_temperature

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
- `public_1` parameters: `{"analysis_type": "edge", "component_value": 5.4375, "source_waveform": "source_waveform_11_public", "temperature": 5.0962, "tolerance": 1.375}`
- `public_2` parameters: `{"analysis_type": "baseline", "component_value": 3.6875, "source_waveform": "source_waveform_17_public", "temperature": 4.4231, "tolerance": 1.25}`
- `public_3` parameters: `{"analysis_type": "compat", "component_value": 2.15, "source_waveform": "source_waveform_15_public", "temperature": 4.9231, "tolerance": 1.7}`
- `public_4` parameters: `{"analysis_type": "baseline", "component_value": 5.4, "source_waveform": "source_waveform_4_public", "temperature": 4.2308, "tolerance": 1.3}`
- `public_5` parameters: `{"analysis_type": "edge", "component_value": 1.0175, "source_waveform": "source_waveform_9_public", "temperature": 1.7346, "tolerance": 1.815}`
- `public_6` parameters: `{"analysis_type": "strict", "component_value": 0.935, "source_waveform": "source_waveform_2_public", "temperature": 1.1846, "tolerance": 2.31}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode6`.
