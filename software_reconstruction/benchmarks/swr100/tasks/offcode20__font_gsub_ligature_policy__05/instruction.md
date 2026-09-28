# Reconstruct font_gsub_ligature_policy

You are given public observations from a real software-in-the-loop reference
artifact in the `typography_font_shaping` family.

The public observation files are available inside the environment at:

- `/app/observations/manifest.json`
- `/app/observations/reference_outputs.tar.gz`

Start by reading `manifest.json`, then inspect/extract `reference_outputs.tar.gz`.
The archive contains `public_1/` and `public_2/` outputs, parameters, signatures,
and family-shaped artifacts. Use those files as behavioral evidence. Do not copy
the observation files into the answer workspace.

Create an editable reconstruction project in `/app/workspace`. The private
verifier will run `/app/workspace/reconstruct.py` with hidden scenario JSON on
stdin, so provide an executable `reconstruct.py` that reads a scenario object,
uses `scenario["parameters"]`, and prints JSON.

The reconstruction should use the domain software/tooling implied by the task:
fontTools, HarfBuzz, fontbakery.

Parameter axes: `glyph_subset`, `hinting_mode`, `kerning_policy`, `script_language`, `variation_axis`

Public scenarios:
- `public_1` parameters: `{"glyph_subset": "glyph-subset-11", "hinting_mode": 3.1294, "kerning_policy": "compat", "script_language": "compat", "variation_axis": 3.6235}`
- `public_2` parameters: `{"glyph_subset": "glyph-subset-8", "hinting_mode": 10.0471, "kerning_policy": "stress", "script_language": "strict", "variation_axis": 7.4941}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on the
public scenarios and report which fields/signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode20`.
