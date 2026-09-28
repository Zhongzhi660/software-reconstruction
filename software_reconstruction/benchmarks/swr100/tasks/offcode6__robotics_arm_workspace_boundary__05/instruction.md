# Reconstruct robotics_arm_workspace_boundary

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
- `public_1` parameters: `{"actuator_gain": 15, "collision_margin": false, "initial_pose": 1.7231, "joint_limit": 4.8462, "trajectory_target": "trajectory-target-7"}`
- `public_2` parameters: `{"actuator_gain": 18, "collision_margin": true, "initial_pose": 6.2462, "joint_limit": 9.1538, "trajectory_target": "trajectory-target-2"}`
- `public_3` parameters: `{"actuator_gain": 6, "collision_margin": false, "initial_pose": 2.3846, "joint_limit": 4.7692, "trajectory_target": "trajectory-target-2"}`
- `public_4` parameters: `{"actuator_gain": 4, "collision_margin": true, "initial_pose": 2.6154, "joint_limit": 5.3077, "trajectory_target": "trajectory-target-8"}`
- `public_5` parameters: `{"actuator_gain": 9, "collision_margin": false, "initial_pose": 2.2423, "joint_limit": 0.55, "trajectory_target": "trajectory-target-13"}`
- `public_6` parameters: `{"actuator_gain": 7, "collision_margin": true, "initial_pose": 0.9308, "joint_limit": 0.5923, "trajectory_target": "trajectory-target-7"}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode6`.
