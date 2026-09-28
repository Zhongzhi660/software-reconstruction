# Reconstruct fea_truss_load_path

You are given public observations from a real software-in-the-loop reference
artifact in the `finite_element_mechanics` family.

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
CalculiX, Elmer, SfePy.

Parameter axes: `boundary_condition`, `contact_region`, `load_case`, `material_property`, `mesh_density`

Public scenarios:
- `public_1` parameters: `{"boundary_condition": "boundary_condition_19_public", "contact_region": false, "load_case": "load_case_11_public", "material_property": 0.1375, "mesh_density": 5}`
- `public_2` parameters: `{"boundary_condition": "boundary_condition_1_public", "contact_region": false, "load_case": "load_case_9_public", "material_property": 3.3, "mesh_density": 7}`
- `public_3` parameters: `{"boundary_condition": "boundary_condition_13_public", "contact_region": true, "load_case": "load_case_15_public", "material_property": 4.3, "mesh_density": 5}`
- `public_4` parameters: `{"boundary_condition": "boundary_condition_4_public", "contact_region": false, "load_case": "load_case_11_public", "material_property": 4.0, "mesh_density": 7}`
- `public_5` parameters: `{"boundary_condition": "boundary_condition_16_public", "contact_region": false, "load_case": "load_case_0_public", "material_property": 9.145, "mesh_density": 9}`
- `public_6` parameters: `{"boundary_condition": "boundary_condition_1_public", "contact_region": true, "load_case": "load_case_8_public", "material_property": 3.255, "mesh_density": 25}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode6`.
