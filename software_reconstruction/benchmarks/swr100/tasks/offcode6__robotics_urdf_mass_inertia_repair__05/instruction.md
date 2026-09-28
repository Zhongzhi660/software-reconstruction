# Reconstruct robotics_urdf_mass_inertia_repair

You are given public observations from a real software-in-the-loop reference
artifact in the `robotics_control` family.

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
mujoco, python, urdf/mjcf tooling.

Parameter axes: `actuator_gain`, `collision_margin`, `initial_pose`, `joint_limit`, `trajectory_target`

Public scenarios:
- `public_1` parameters: `{"actuator_gain": 6, "collision_margin": false, "initial_pose": 10.6615, "joint_limit": 3.7692, "trajectory_target": "trajectory-target-9"}`
- `public_2` parameters: `{"actuator_gain": 3, "collision_margin": true, "initial_pose": 5.4923, "joint_limit": 9.9077, "trajectory_target": "trajectory-target-4"}`
- `public_3` parameters: `{"actuator_gain": 10, "collision_margin": false, "initial_pose": 6.0769, "joint_limit": 6.1538, "trajectory_target": "trajectory-target-4"}`
- `public_4` parameters: `{"actuator_gain": 16, "collision_margin": true, "initial_pose": 6.4615, "joint_limit": 2.3846, "trajectory_target": "trajectory-target-3"}`
- `public_5` parameters: `{"actuator_gain": 6, "collision_margin": true, "initial_pose": 2.2846, "joint_limit": 1.9038, "trajectory_target": "trajectory-target-14"}`
- `public_6` parameters: `{"actuator_gain": 8, "collision_margin": false, "initial_pose": 3.6385, "joint_limit": 1.8192, "trajectory_target": "trajectory-target-16"}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode6`.
