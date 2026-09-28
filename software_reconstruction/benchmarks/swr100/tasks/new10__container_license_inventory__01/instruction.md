# Reconstruct container_license_inventory

You are given public observations from a real software-in-the-loop reference
artifact in the `container_supply_chain` family.

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
hadolint, syft, skopeo.

Parameter axes: `base_image`, `entrypoint`, `labels`, `package_set`, `sbom_scope`

Public scenarios:
- `public_1` parameters: `{"base_image": 6.857, "entrypoint": "entrypoint_14_p", "labels": 4.857, "package_set": 2.286, "sbom_scope": 6.143}`
- `public_2` parameters: `{"base_image": 1.143, "entrypoint": "entrypoint_4_p", "labels": 6.714, "package_set": 5.286, "sbom_scope": 3.714}`
- `public_3` parameters: `{"base_image": 3.379, "entrypoint": "entrypoint_8_p", "labels": 0.55, "package_set": 2.043, "sbom_scope": 1.257}`
- `public_4` parameters: `{"base_image": 0.943, "entrypoint": "entrypoint_12_p", "labels": 1.964, "package_set": 0.943, "sbom_scope": 3.143}`
- `public_5` parameters: `{"base_image": 3.764, "entrypoint": "entrypoint_0_p", "labels": 6.643, "package_set": 5.757, "sbom_scope": 7.529}`
- `public_6` parameters: `{"base_image": 10.186, "entrypoint": "entrypoint_15_p", "labels": 9.079, "package_set": 8.414, "sbom_scope": 4.429}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `new10`.
