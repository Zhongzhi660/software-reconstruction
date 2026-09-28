# Reconstruct chem_smiles_descriptor_matrix

You are given public observations from a real software-in-the-loop reference
artifact in the `molecular_chemistry` family.

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
rdkit, openbabel.

Parameter axes: `conformer_seed`, `fingerprint_radius`, `protonation_state`, `stereochemistry`, `substructure_query`

Public scenarios:
- `public_1` parameters: `{"conformer_seed": 5, "fingerprint_radius": 7, "protonation_state": false, "stereochemistry": true, "substructure_query": "c1ccccc1"}`
- `public_2` parameters: `{"conformer_seed": 14, "fingerprint_radius": 9, "protonation_state": true, "stereochemistry": true, "substructure_query": "N"}`
- `public_3` parameters: `{"conformer_seed": 13, "fingerprint_radius": 7, "protonation_state": false, "stereochemistry": true, "substructure_query": "N"}`
- `public_4` parameters: `{"conformer_seed": 16, "fingerprint_radius": 16, "protonation_state": true, "stereochemistry": true, "substructure_query": "CCO"}`
- `public_5` parameters: `{"conformer_seed": 16, "fingerprint_radius": 17, "protonation_state": true, "stereochemistry": false, "substructure_query": "CCO"}`
- `public_6` parameters: `{"conformer_seed": 17, "fingerprint_radius": 26, "protonation_state": false, "stereochemistry": false, "substructure_query": "CCO"}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode6`.
