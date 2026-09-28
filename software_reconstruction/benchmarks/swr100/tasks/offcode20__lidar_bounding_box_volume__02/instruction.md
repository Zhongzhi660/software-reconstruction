# Reconstruct lidar_bounding_box_volume

You are given public observations from a real software-in-the-loop reference
artifact in the `point_cloud_lidar` family.

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
Open3D, PDAL, laspy.

Parameter axes: `classification_filter`, `crop_bounds`, `normal_radius`, `registration_threshold`, `voxel_size`

Public scenarios:
- `public_1` parameters: `{"classification_filter": 0.8735, "crop_bounds": [2.2, 2.75, 3.3], "normal_radius": 7, "registration_threshold": 2.6895, "voxel_size": 6}`
- `public_2` parameters: `{"classification_filter": 2.3294, "crop_bounds": [7.15, 7.7, 8.25], "normal_radius": 8, "registration_threshold": 2.0955, "voxel_size": 6}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on the
public scenarios and report which fields/signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode20`.
