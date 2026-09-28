# Reconstruct pandoc_markdown_latex_math

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
- `public_1` parameters: `{"dpi": 3.565, "font": "strict", "language": "strict", "metadata": 2.657, "page_range": 8.68}`
- `public_2` parameters: `{"dpi": 17.941, "font": "font-9", "language": "language-15", "metadata": 10.31, "page_range": 16.326}`
- `public_3` parameters: `{"dpi": 6.7, "font": "strict", "language": "baseline", "metadata": 7.857, "page_range": 5.6}`
- `public_4` parameters: `{"dpi": 10.046, "font": "font-11", "language": "language-6", "metadata": 6.024, "page_range": 3.201}`
- `public_5` parameters: `{"dpi": 0.77, "font": "edge", "language": "strict", "metadata": 2.986, "page_range": 3.74}`
- `public_6` parameters: `{"dpi": 5.226, "font": "font-10", "language": "language-9", "metadata": 3.26, "page_range": 4.296}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `new10`.
