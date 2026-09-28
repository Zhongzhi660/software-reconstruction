# openssl_store_loader_policy_chain__02

Create an editable project in `/app/workspace` that reproduces the observed
behavior of the reference demo for `openssl_pki`.

The public observations in `/app/observations` were produced by running the
real software on the acquired parent demo. Use them as behavioral evidence, not
as files to copy into your answer.

This variant changes at least 5 parameter axes: provider, cert_store, purpose, chain, verification_purpose.

The private judge uses hidden scenarios centered on `verification_purpose`.
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

Parameter axes: `provider, cert_store, purpose, chain, verification_purpose`

Public scenarios:
- `public_1` parameters: `{"cert_store": 2.145, "chain": 4.225, "provider": 1.17, "purpose": "baseline", "verification_purpose": "stress"}`
- `public_2` parameters: `{"cert_store": 2.6, "chain": 1.885, "provider": 4.03, "purpose": "edge", "verification_purpose": "edge"}`

Use `/app/tools/feedback` while solving. It runs your `reconstruct.py` on the
public scenarios and reports which public oracle signatures match. Passing
public feedback is not sufficient by itself; hidden scenarios from the same
parameter space are used for final grading.
