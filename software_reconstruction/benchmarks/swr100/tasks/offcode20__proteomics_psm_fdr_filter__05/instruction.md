# Reconstruct proteomics_psm_fdr_filter

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
- `public_1` parameters: `{"charge_state": 1.6471, "enzyme_rule": 3.4588, "fdr_threshold": 5.502, "mass_tolerance": 2.534, "retention_window": 3}`
- `public_2` parameters: `{"charge_state": 2.1412, "enzyme_rule": 7.9059, "fdr_threshold": 0.07, "mass_tolerance": 0.126, "retention_window": 21}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on the
public scenarios and report which fields/signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode20`.
