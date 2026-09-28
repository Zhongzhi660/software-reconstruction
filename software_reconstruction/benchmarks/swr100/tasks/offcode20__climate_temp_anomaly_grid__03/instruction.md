# Reconstruct climate_temp_anomaly_grid

You are given public observations from a real software-in-the-loop reference
artifact in the `climate_netcdf_analysis` family.

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
xarray, netCDF4, NCO/CDO-style CLI.

Parameter axes: `calendar_type`, `missing_value_policy`, `regrid_method`, `time_window`, `variable_name`

Public scenarios:
- `public_1` parameters: `{"calendar_type": "baseline", "missing_value_policy": "domain_specific", "regrid_method": "strict", "time_window": 29, "variable_name": "variable-name-2"}`
- `public_2` parameters: `{"calendar_type": "baseline", "missing_value_policy": "edge", "regrid_method": "baseline", "time_window": 17, "variable_name": "variable-name-1"}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on the
public scenarios and report which fields/signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode20`.
