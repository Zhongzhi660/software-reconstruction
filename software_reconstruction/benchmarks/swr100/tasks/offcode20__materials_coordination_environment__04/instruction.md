# Reconstruct materials_coordination_environment

You are given public observations from a real software-in-the-loop reference
artifact in the `materials_crystallography` family.

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
pymatgen, spglib, ASE.

Parameter axes: `diffraction_wavelength`, `site_substitution`, `space_group`, `strain_tensor`, `supercell_size`

Public scenarios:
- `public_1` parameters: `{"diffraction_wavelength": 2.0588, "site_substitution": true, "space_group": "stress", "strain_tensor": [2.5, 3.75, 5.0], "supercell_size": 16}`
- `public_2` parameters: `{"diffraction_wavelength": 4.6324, "site_substitution": false, "space_group": "stress", "strain_tensor": [5.0, 6.25, 7.5], "supercell_size": 24}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on the
public scenarios and report which fields/signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode20`.
