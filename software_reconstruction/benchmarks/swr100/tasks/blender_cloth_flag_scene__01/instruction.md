# blender_cloth_flag_scene__01

Create an editable project in `/app/workspace` that reproduces the observed
behavior of the reference demo for `blender_scene_graph`.

The public observations in `/app/observations` were produced by running the
real software on the acquired parent demo. Use them as behavioral evidence, not
as files to copy into your answer.

This variant changes at least 4 parameter axes: wind_strength, pin_group, frame, cloth_subdiv.

The private judge uses hidden scenarios centered on `cloth_subdiv`.
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

Parameter axes: `wind_strength, pin_group, frame, cloth_subdiv`

Public scenarios:
- `public_1` parameters: `{"cloth_subdiv": 3.1, "frame": 21, "pin_group": 6.7, "wind_strength": 3.1}`
- `public_2` parameters: `{"cloth_subdiv": 5.9, "frame": 16, "pin_group": 3.1, "wind_strength": 1.4}`

Use `/app/tools/feedback` while solving. It runs your `reconstruct.py` on the
public scenarios and reports which public oracle signatures match. Passing
public feedback is not sufficient by itself; hidden scenarios from the same
parameter space are used for final grading.
