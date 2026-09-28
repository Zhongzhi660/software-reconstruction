# Reconstruct gdal_vrt_mosaic_transform

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
- `public_1` parameters: `{"bbox": 8.5, "crs": "edge", "layer_filter": "layer_filter_7_p", "nodata": 3.4, "resolution": 16.66}`
- `public_2` parameters: `{"bbox": 8.681, "crs": "crs-8", "layer_filter": "layer-filter-11", "nodata": 12.139, "resolution": 20.316}`
- `public_3` parameters: `{"bbox": 8.4, "crs": "edge", "layer_filter": "layer_filter_7_p", "nodata": 7.857, "resolution": 8.0}`
- `public_4` parameters: `{"bbox": 10.361, "crs": "crs-17", "layer_filter": "layer-filter-4", "nodata": 9.024, "resolution": 5.586}`
- `public_5` parameters: `{"bbox": 3.08, "crs": "stress", "layer_filter": "layer_filter_15_p", "nodata": 1.729, "resolution": 0.825}`
- `public_6` parameters: `{"bbox": 6.196, "crs": "crs-5", "layer_filter": "layer-filter-2", "nodata": 3.574, "resolution": 2.666}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `new10`.
