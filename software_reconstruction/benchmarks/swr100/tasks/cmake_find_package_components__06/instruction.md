# cmake_find_package_components__06

Create an editable project in `/app/workspace` that reproduces the observed
behavior of the reference demo for `cmake_build_config`.

The public observations in `/app/observations` were produced by running the
real software on the acquired parent demo. Use them as behavioral evidence, not
as files to copy into your answer.

This variant changes at least 3 parameter axes: components, version, optional_dep.

The private judge uses hidden scenarios centered on `optional_dep`.
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

Parameter axes: `components, version, optional_dep`

Public scenarios:
- `public_1` parameters: `{"components": 2.2, "optional_dep": 4.7, "version": 4.0}`
- `public_2` parameters: `{"components": 2.5, "optional_dep": 3.8, "version": 7.5}`

Use `/app/tools/feedback` while solving. It runs your `reconstruct.py` on the
public scenarios and reports which public oracle signatures match. Passing
public feedback is not sufficient by itself; hidden scenarios from the same
parameter space are used for final grading.
