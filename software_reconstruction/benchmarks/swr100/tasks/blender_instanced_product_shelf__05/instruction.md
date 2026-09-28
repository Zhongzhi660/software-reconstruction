# blender_instanced_product_shelf__05

Create an editable project in `/app/workspace` that reproduces the observed
behavior of the reference demo for `blender_scene_graph`.

The public observations in `/app/observations` were produced by running the
real software on the acquired parent demo. Use them as behavioral evidence, not
as files to copy into your answer.

This variant changes at least 5 parameter axes: lighting, product_count, shelf_rows, label_theme, camera.

The private judge uses hidden scenarios centered on `camera`.
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

Parameter axes: `lighting, product_count, shelf_rows, label_theme, camera`

Public scenarios:
- `public_1` parameters: `{"camera": 3.8, "label_theme": 1.9, "lighting": 2.1, "product_count": 10, "shelf_rows": 3.2}`
- `public_2` parameters: `{"camera": 7.7, "label_theme": 3.4, "lighting": 3.7, "product_count": 8, "shelf_rows": 1.1}`

Use `/app/tools/feedback` while solving. It runs your `reconstruct.py` on the
public scenarios and reports which public oracle signatures match. Passing
public feedback is not sufficient by itself; hidden scenarios from the same
parameter space are used for final grading.
