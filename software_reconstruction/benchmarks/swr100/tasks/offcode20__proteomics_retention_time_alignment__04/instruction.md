# Reconstruct proteomics_retention_time_alignment

You are given public observations from a real software-in-the-loop reference
artifact in the `proteomics_mass_spectrometry` family.

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
OpenMS, pyteomics.

Parameter axes: `charge_state`, `enzyme_rule`, `fdr_threshold`, `mass_tolerance`, `retention_window`

Public scenarios:
- `public_1` parameters: `{"charge_state": 6.9118, "enzyme_rule": 6.9853, "fdr_threshold": 3.8625, "mass_tolerance": 7.0125, "retention_window": 10}`
- `public_2` parameters: `{"charge_state": 7.1324, "enzyme_rule": 4.7794, "fdr_threshold": 4.8625, "mass_tolerance": 1.4625, "retention_window": 12}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on the
public scenarios and report which fields/signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode20`.
