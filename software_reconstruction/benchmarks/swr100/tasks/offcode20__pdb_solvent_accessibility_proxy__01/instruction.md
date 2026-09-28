# Reconstruct pdb_solvent_accessibility_proxy

You are given public observations from a real software-in-the-loop reference
artifact in the `structural_biology_pdb` family.

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
Biopython, gemmi, MDAnalysis.

Parameter axes: `altloc_policy`, `chain_selection`, `distance_cutoff`, `residue_window`, `secondary_structure`

Public scenarios:
- `public_1` parameters: `{"altloc_policy": "compat", "chain_selection": "baseline", "distance_cutoff": 1.01, "residue_window": 17, "secondary_structure": 6.6471}`
- `public_2` parameters: `{"altloc_policy": "strict", "chain_selection": "domain_specific", "distance_cutoff": 4.33, "residue_window": 2, "secondary_structure": 3.7059}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on the
public scenarios and report which fields/signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode20`.
