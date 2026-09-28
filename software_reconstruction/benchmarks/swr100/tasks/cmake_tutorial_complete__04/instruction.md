# cmake_tutorial_complete__04

Create an editable project in `/app/workspace` that reproduces the observed
behavior of the reference demo for `cmake_build_config`.

The public observations in `/app/observations` were produced by running the
real software on the acquired parent demo. Use them as behavioral evidence, not
as files to copy into your answer.

This variant changes at least 4 parameter axes: dependency, consumer, feature_flags, testing.

The private judge uses hidden scenarios centered on `testing`.
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

Parameter axes: `dependency, consumer, feature_flags, testing`

Public scenarios:
- `public_1` parameters: `{"consumer": 8.16, "dependency": 3.48, "feature_flags": 7.44, "testing": 7.44}`
- `public_2` parameters: `{"consumer": 1.44, "dependency": 1.8, "feature_flags": 3.24, "testing": 3.12}`

Use `/app/tools/feedback` while solving. It runs your `reconstruct.py` on the
public scenarios and reports which public oracle signatures match. Passing
public feedback is not sufficient by itself; hidden scenarios from the same
parameter space are used for final grading.
