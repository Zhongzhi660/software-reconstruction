# Reconstruct container_syft_python_sbom

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
- `public_1` parameters: `{"base_image": 6.421, "entrypoint": "entrypoint_2_p", "labels": 8.193, "package_set": 10.186, "sbom_scope": 11.736}`
- `public_2` parameters: `{"base_image": 11.293, "entrypoint": "entrypoint_7_p", "labels": 4.871, "package_set": 8.414, "sbom_scope": 2.214}`
- `public_3` parameters: `{"base_image": 7.286, "entrypoint": "entrypoint_8_p", "labels": 5.143, "package_set": 8.0, "sbom_scope": 2.571}`
- `public_4` parameters: `{"base_image": 4.429, "entrypoint": "entrypoint_1_p", "labels": 8.0, "package_set": 6.857, "sbom_scope": 3.571}`
- `public_5` parameters: `{"base_image": 2.829, "entrypoint": "entrypoint_10_p", "labels": 2.436, "package_set": 0.629, "sbom_scope": 4.086}`
- `public_6` parameters: `{"base_image": 3.064, "entrypoint": "entrypoint_15_p", "labels": 2.436, "package_set": 4.4, "sbom_scope": 1.1}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `new10`.
