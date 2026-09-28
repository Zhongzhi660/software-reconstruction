# Reconstruct qpdf_bookmark_metadata_repair

You are given public observations from a real software-in-the-loop reference
artifact in the `document_ocr_publishing` family.

The public observation files are available inside the environment at:

- `/app/observations/manifest.json`
- `/app/observations/reference_outputs.tar.gz`

Start by reading `manifest.json`, then inspect/extract `reference_outputs.tar.gz`.
The archive contains public scenario outputs, parameters, signatures, and
family-shaped native artifacts. Use those files as behavioral evidence. Do not
copy the observation files into the answer workspace.

Create an editable reconstruction project in `/app/workspace`. The private
verifier will run `/app/workspace/reconstruct.py` with hidden scenario JSON on
stdin, so provide an executable `reconstruct.py` that reads a scenario object,
uses `scenario["parameters"]`, and prints JSON.

The reconstruction should use the domain software/tooling implied by the task:
pandoc, poppler-utils, tesseract, qpdf.

Parameter axes: `dpi`, `font`, `language`, `metadata`, `page_range`

Public scenarios:
- `public_1` parameters: `{"dpi": 4.34, "font": "baseline", "language": "compat", "metadata": 2.214, "page_range": 3.41}`
- `public_2` parameters: `{"dpi": 10.036, "font": "font-15", "language": "language-3", "metadata": 3.889, "page_range": 8.886}`
- `public_3` parameters: `{"dpi": 9.0, "font": "strict", "language": "compat", "metadata": 3.714, "page_range": 2.0}`
- `public_4` parameters: `{"dpi": 2.046, "font": "font-11", "language": "language-8", "metadata": 7.596, "page_range": 2.901}`
- `public_5` parameters: `{"dpi": 1.43, "font": "compat", "language": "stress", "metadata": 3.771, "page_range": 3.245}`
- `public_6` parameters: `{"dpi": 6.271, "font": "font-13", "language": "language-14", "metadata": 4.517, "page_range": 3.636}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `new10`.
