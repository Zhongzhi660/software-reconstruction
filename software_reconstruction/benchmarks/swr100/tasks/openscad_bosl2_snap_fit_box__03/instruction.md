# openscad_bosl2_snap_fit_box__03

Create an editable project in `/app/workspace` that reproduces the observed
behavior of the reference demo for `openscad_parametric_cad`.

The public observations in `/app/observations` were produced by running the
real software on the acquired parent demo. Use them as behavioral evidence, not
as files to copy into your answer.

This variant changes at least 3 parameter axes: lip_depth, wall, corner_radius.

The private judge uses hidden scenarios centered on `corner_radius`.
Build the underlying mechanism so that unseen parameter settings continue to
work, instead of branching only on the public case.


## Required Reconstruction Interface

In addition to building an editable project, provide `/app/workspace/reconstruct.py`.
The verifier will execute it as:

```bash
python3 /app/workspace/reconstruct.py < scenario.json
```

It must read one scenario JSON object from stdin, use `scenario["parameters"]`,
and print JSON to stdout. Follow the same output shape as the public
`oracle_output.json` files inside `/app/observations/reference_outputs.tar.gz`;
usually this means printing `{"summary": ...}`.

Parameter axes: `lip_depth, wall, corner_radius`

Public scenarios:
- `public_1` parameters: `{"corner_radius": 34.68, "lip_depth": 10, "wall": 1.015}`
- `public_2` parameters: `{"corner_radius": 26.15, "lip_depth": 6, "wall": 2.9}`

Use `/app/tools/feedback` while solving. It runs your `reconstruct.py` on the
public scenarios and compares the generated STL geometry with the public reference geometry. Passing
public feedback is not sufficient by itself; hidden scenarios from the same
parameter space are used for final grading.


## OpenSCAD Geometry Artifact Contract

Each invocation of `reconstruct.py` must generate a valid STL mesh at
`/app/workspace/product.stl` (or return an `artifact_path` inside the workspace)
and print a JSON object to stdout. The STL must be regenerated from the current
scenario parameters. The verifier evaluates bounding-box dimensions, volume,
surface area, connected components, and sampled surface distance against the
hidden reference mesh. File hashes, byte counts, and fixed public meshes do not
satisfy this contract.
