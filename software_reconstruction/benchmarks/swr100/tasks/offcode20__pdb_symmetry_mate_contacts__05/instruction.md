# Reconstruct pdb_symmetry_mate_contacts

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
- `public_1` parameters: `{"altloc_policy": "edge", "chain_selection": "compat", "distance_cutoff": 5.838, "residue_window": 27, "secondary_structure": 8.0706}`
- `public_2` parameters: `{"altloc_policy": "baseline", "chain_selection": "baseline", "distance_cutoff": 2.254, "residue_window": 14, "secondary_structure": 10.1294}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on the
public scenarios and report which fields/signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode20`.
