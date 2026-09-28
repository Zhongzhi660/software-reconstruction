# Reconstruct z3_array_memory_aliasing

You are given public observations from a real software-in-the-loop reference
artifact in the `z3_constraint_system` family.

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
z3.

Parameter axes: `bitwidth`, `bounds`, `capacity`, `precedence`, `satisfiability_mode`

Public scenarios:
- `public_1` parameters: `{"bitwidth": 6, "bounds": 3.125, "capacity": 13.5, "precedence": 2.143, "satisfiability_mode": "compat"}`
- `public_2` parameters: `{"bitwidth": 7, "bounds": 5.435, "capacity": 10.222, "precedence": 9.138, "satisfiability_mode": "compat"}`
- `public_3` parameters: `{"bitwidth": 5, "bounds": 6.4, "capacity": 6.5, "precedence": 6.143, "satisfiability_mode": "edge"}`
- `public_4` parameters: `{"bitwidth": 9, "bounds": 1.4, "capacity": 10.7, "precedence": 1.714, "satisfiability_mode": "stress"}`
- `public_5` parameters: `{"bitwidth": 3, "bounds": 1.485, "capacity": 4.62, "precedence": 3.771, "satisfiability_mode": "strict"}`
- `public_6` parameters: `{"bitwidth": 7, "bounds": 5.06, "capacity": 4.767, "precedence": 5.881, "satisfiability_mode": "edge"}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `new10`.
