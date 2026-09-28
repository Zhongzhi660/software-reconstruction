# Reconstruct gdal_invalid_geometry_repair

You are given public observations from a real software-in-the-loop reference
artifact in the `gdal_geospatial` family.

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
gdal, ogr2ogr, proj.

Parameter axes: `bbox`, `crs`, `layer_filter`, `nodata`, `resolution`

Public scenarios:
- `public_1` parameters: `{"bbox": 5.27, "crs": "baseline", "layer_filter": "layer_filter_5_p", "nodata": 12.179, "resolution": 5.58}`
- `public_2` parameters: `{"bbox": 2.566, "crs": "crs-9", "layer_filter": "layer-filter-1", "nodata": 4.996, "resolution": 3.491}`
- `public_3` parameters: `{"bbox": 10.1, "crs": "stress", "layer_filter": "layer_filter_3_p", "nodata": 1.714, "resolution": 9.2}`
- `public_4` parameters: `{"bbox": 11.461, "crs": "crs-10", "layer_filter": "layer-filter-16", "nodata": 6.453, "resolution": 7.786}`
- `public_5` parameters: `{"bbox": 2.255, "crs": "baseline", "layer_filter": "layer_filter_13_p", "nodata": 2.2, "resolution": 4.565}`
- `public_6` parameters: `{"bbox": 2.236, "crs": "crs-1", "layer_filter": "layer-filter-17", "nodata": 5.539, "resolution": 4.646}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `new10`.
