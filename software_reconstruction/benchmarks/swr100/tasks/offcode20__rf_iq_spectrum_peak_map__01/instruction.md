# Reconstruct rf_iq_spectrum_peak_map

You are given public observations from a real software-in-the-loop reference
artifact in the `rf_signal_processing` family.

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
GNU Radio, scipy.signal.

Parameter axes: `carrier_offset`, `filter_taps`, `modulation_type`, `sample_rate`, `snr_level`

Public scenarios:
- `public_1` parameters: `{"carrier_offset": 4.57, "filter_taps": 2.1176, "modulation_type": "baseline", "sample_rate": 7, "snr_level": 14}`
- `public_2` parameters: `{"carrier_offset": 0.81, "filter_taps": 8.0, "modulation_type": "stress", "sample_rate": 9, "snr_level": 10}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on the
public scenarios and report which fields/signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode20`.
