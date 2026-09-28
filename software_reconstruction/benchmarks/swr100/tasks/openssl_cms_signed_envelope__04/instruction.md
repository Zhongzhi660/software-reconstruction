# openssl_cms_signed_envelope__04

Create an editable project in `/app/workspace` that reproduces the observed
behavior of the reference demo for `openssl_pki`.

The public observations in `/app/observations` were produced by running the
real software on the acquired parent demo. Use them as behavioral evidence, not
as files to copy into your answer.

This variant changes at least 4 parameter axes: detach, verify, signer, recipient.

The private judge uses hidden scenarios centered on `recipient`.
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

Parameter axes: `detach, verify, signer, recipient`

Public scenarios:
- `public_1` parameters: `{"detach": 5.88, "recipient": 5.28, "signer": 7.32, "verify": 5.16}`
- `public_2` parameters: `{"detach": 5.16, "recipient": 4.2, "signer": 8.64, "verify": 9.24}`

Use `/app/tools/feedback` while solving. It runs your `reconstruct.py` on the
public scenarios and reports which public oracle signatures match. Passing
public feedback is not sufficient by itself; hidden scenarios from the same
parameter space are used for final grading.
