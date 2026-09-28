# Reconstruct opa_configmap_secret_guard

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
- `public_1` parameters: `{"exception": false, "identity": "identity_4_p", "namespace": "namespace_0_p", "overlay": 1.857, "resource_shape": 6.714}`
- `public_2` parameters: `{"exception": true, "identity": "service-account", "namespace": "payments", "overlay": 4.564, "resource_shape": 4.643}`
- `public_3` parameters: `{"exception": false, "identity": "identity_3_p", "namespace": "namespace_5_p", "overlay": 3.143, "resource_shape": 1.964}`
- `public_4` parameters: `{"exception": false, "identity": "editor", "namespace": "analytics", "overlay": 3.921, "resource_shape": 3.75}`
- `public_5` parameters: `{"exception": false, "identity": "identity_15_p", "namespace": "namespace_10_p", "overlay": 2.436, "resource_shape": 9.964}`
- `public_6` parameters: `{"exception": false, "identity": "auditor", "namespace": "default", "overlay": 4.885, "resource_shape": 9.093}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `new10`.
