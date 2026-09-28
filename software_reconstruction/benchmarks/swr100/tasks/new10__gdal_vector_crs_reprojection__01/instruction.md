# Reconstruct gdal_vector_crs_reprojection

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
- `public_1` parameters: `{"bbox": 5.2, "crs": "compat", "layer_filter": "layer_filter_16_p", "nodata": 2.0, "resolution": 2.0}`
- `public_2` parameters: `{"bbox": 10.561, "crs": "crs-6", "layer_filter": "layer-filter-7", "nodata": 2.453, "resolution": 8.186}`
- `public_3` parameters: `{"bbox": 3.41, "crs": "baseline", "layer_filter": "layer_filter_12_p", "nodata": 3.536, "resolution": 1.43}`
- `public_4` parameters: `{"bbox": 5.646, "crs": "crs-14", "layer_filter": "layer-filter-8", "nodata": 4.282, "resolution": 4.921}`
- `public_5` parameters: `{"bbox": 6.355, "crs": "stress", "layer_filter": "layer_filter_10_p", "nodata": 7.086, "resolution": 14.105}`
- `public_6` parameters: `{"bbox": 12.796, "crs": "crs-5", "layer_filter": "layer-filter-9", "nodata": 6.989, "resolution": 5.661}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `new10`.
