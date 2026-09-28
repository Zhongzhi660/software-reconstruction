# kicad_usb_uart_bridge__02

Create an editable project in `/app/workspace` that reproduces the observed
behavior of the reference demo for `kicad_pcb`.

The public observations in `/app/observations` were produced by running the
real software on the acquired parent demo. Use them as behavioral evidence, not
as files to copy into your answer.

This variant changes at least 5 parameter axes: esd, mcu, diff_pair, drc, usb_connector.

The private judge uses hidden scenarios centered on `usb_connector`.
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

Parameter axes: `esd, mcu, diff_pair, drc, usb_connector`

Public scenarios:
- `public_1` parameters: `{"diff_pair": 0.845, "drc": 4.225, "esd": 3.835, "mcu": 1.105, "usb_connector": 4.615}`
- `public_2` parameters: `{"diff_pair": 1.105, "drc": 3.38, "esd": 3.38, "mcu": 3.315, "usb_connector": 1.3}`

Use `/app/tools/feedback` while solving. It runs your `reconstruct.py` on the
public scenarios and reports which public oracle signatures match. Passing
public feedback is not sufficient by itself; hidden scenarios from the same
parameter space are used for final grading.
