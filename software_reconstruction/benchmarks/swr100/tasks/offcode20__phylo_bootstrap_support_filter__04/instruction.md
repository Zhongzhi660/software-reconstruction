# Reconstruct phylo_bootstrap_support_filter

You are given public observations from a real software-in-the-loop reference
artifact in the `phylogenetics_tree_reconstruction` family.

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
Biopython, IQ-TREE/FastTree-style CLI.

Parameter axes: `alignment_trim`, `bootstrap_replicates`, `branch_support_threshold`, `outgroup_taxon`, `substitution_model`

Public scenarios:
- `public_1` parameters: `{"alignment_trim": 7.5735, "bootstrap_replicates": 6, "branch_support_threshold": 0.4625, "outgroup_taxon": "outgroup-taxon-6", "substitution_model": "compat"}`
- `public_2` parameters: `{"alignment_trim": 2.4265, "bootstrap_replicates": 24, "branch_support_threshold": 5.6125, "outgroup_taxon": "outgroup-taxon-15", "substitution_model": "strict"}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on the
public scenarios and report which fields/signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode20`.
