# cmake_object_plugin_export_graph__05

Create an editable project in `/app/workspace` that reproduces the observed
behavior of the reference demo for `cmake_build_config`.

The public observations in `/app/observations` were produced by running the
real software on the acquired parent demo. Use them as behavioral evidence, not
as files to copy into your answer.

This variant changes at least 5 parameter axes: install, transitive_target_exports, generated_header_values, install_tree_consumer, toolchain_override.

The private judge uses hidden scenarios centered on `toolchain_override`.
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

Parameter axes: `install, transitive_target_exports, generated_header_values, install_tree_consumer, toolchain_override`

Public scenarios:
- `public_1` parameters: `{"generated_header_values": 39, "install": 3.7, "install_tree_consumer": 6.7, "toolchain_override": 5.0, "transitive_target_exports": 5.2}`
- `public_2` parameters: `{"generated_header_values": 10, "install": 6.4, "install_tree_consumer": 1.2, "toolchain_override": 5.5, "transitive_target_exports": 2.7}`

Use `/app/tools/feedback` while solving. It runs your `reconstruct.py` on the
public scenarios and reports which public oracle signatures match. Passing
public feedback is not sufficient by itself; hidden scenarios from the same
parameter space are used for final grading.
