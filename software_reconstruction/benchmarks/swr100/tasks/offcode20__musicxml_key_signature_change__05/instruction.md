# Reconstruct musicxml_key_signature_change

You are given public observations from a real software-in-the-loop reference
artifact in the `music_score_engraving` family.

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
music21, MusicXML, LilyPond-style rendering.

Parameter axes: `instrument_part`, `lyric_alignment`, `meter_change`, `quantization_grid`, `transpose_interval`

Public scenarios:
- `public_1` parameters: `{"instrument_part": "instrument-part-6", "lyric_alignment": 4.6118, "meter_change": true, "quantization_grid": 9.7176, "transpose_interval": 7.4118}`
- `public_2` parameters: `{"instrument_part": "instrument-part-5", "lyric_alignment": 8.1529, "meter_change": false, "quantization_grid": 3.2118, "transpose_interval": 7.4941}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on the
public scenarios and report which fields/signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode20`.
