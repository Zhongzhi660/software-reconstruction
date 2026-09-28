# Reconstruct materials_surface_slab_orientation

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
- `public_1` parameters: `{"diffraction_wavelength": 5.3529, "site_substitution": false, "space_group": "compat", "strain_tensor": [1.0, 2.0, 3.0], "supercell_size": 14}`
- `public_2` parameters: `{"diffraction_wavelength": 3.4644, "site_substitution": false, "space_group": "space-group-13", "strain_tensor": 10.822, "supercell_size": 43}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on the
public scenarios and report which fields/signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode20`.
