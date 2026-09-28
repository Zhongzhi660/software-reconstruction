# Reconstruct hydro_sink_fill_qc

You are given public observations from a real software-in-the-loop reference
artifact in the `hydrology_raster_modeling` family.

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
HydroMT, pysheds, rasterio.

Parameter axes: `basin_threshold`, `dem_resolution`, `flow_direction_method`, `nodata_policy`, `rainfall_window`

Public scenarios:
- `public_1` parameters: `{"basin_threshold": 5.321, "dem_resolution": 12.5, "flow_direction_method": "compat", "nodata_policy": "baseline", "rainfall_window": 24}`
- `public_2` parameters: `{"basin_threshold": 5.933, "dem_resolution": 2.0, "flow_direction_method": "domain_specific", "nodata_policy": "edge", "rainfall_window": 12}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on the
public scenarios and report which fields/signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode20`.
