# Reconstruct opa_k8s_container_limits

You are given public observations from a real software-in-the-loop reference
artifact in the `opa_rego_policy` family.

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
opa, helm, kustomize, kubeconform.

Parameter axes: `exception`, `identity`, `namespace`, `overlay`, `resource_shape`

Public scenarios:
- `public_1` parameters: `{"exception": false, "identity": "identity_2_p", "namespace": "namespace_0_p", "overlay": 1.179, "resource_shape": 1.964}`
- `public_2` parameters: `{"exception": true, "identity": "editor", "namespace": "platform", "overlay": 4.785, "resource_shape": 4.536}`
- `public_3` parameters: `{"exception": false, "identity": "identity_0_p", "namespace": "namespace_0_p", "overlay": 4.143, "resource_shape": 7.429}`
- `public_4` parameters: `{"exception": true, "identity": "viewer", "namespace": "platform", "overlay": 5.135, "resource_shape": 4.786}`
- `public_5` parameters: `{"exception": true, "identity": "identity_7_p", "namespace": "namespace_15_p", "overlay": 3.543, "resource_shape": 10.629}`
- `public_6` parameters: `{"exception": false, "identity": "ci-bot", "namespace": "platform", "overlay": 3.335, "resource_shape": 12.636}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `new10`.
