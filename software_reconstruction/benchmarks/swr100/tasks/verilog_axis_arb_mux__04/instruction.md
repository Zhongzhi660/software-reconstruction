# verilog_axis_arb_mux__04

Create an editable project in `/app/workspace` that reproduces the observed
behavior of the reference demo for `verilog_rtl`.

The public observations in `/app/observations` were produced by running the
real software on the acquired parent demo. Use them as behavioral evidence, not
as files to copy into your answer.

This variant changes at least 4 parameter axes: reset, frame, ports, width.

The private judge uses hidden scenarios centered on `width`.
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

Parameter axes: `reset, frame, ports, width`

Public scenarios:
- `public_1` parameters: `{"frame": 36, "ports": 7.44, "reset": 2.88, "width": 29.31}`
- `public_2` parameters: `{"frame": 35, "ports": 2.76, "reset": 4.08, "width": 12.54}`

Use `/app/tools/feedback` while solving. It runs your `reconstruct.py` on the
public scenarios and reports which public oracle signatures match. Passing
public feedback is not sufficient by itself; hidden scenarios from the same
parameter space are used for final grading.
