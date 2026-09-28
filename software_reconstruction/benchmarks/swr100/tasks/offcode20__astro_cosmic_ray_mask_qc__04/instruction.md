# Reconstruct astro_cosmic_ray_mask_qc

You are given public observations from a real software-in-the-loop reference
artifact in the `astronomy_fits_photometry` family.

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
astropy, photutils.

Parameter axes: `aperture_radius`, `background_model`, `sigma_clip`, `source_threshold`, `wcs_frame`

Public scenarios:
- `public_1` parameters: `{"aperture_radius": 10, "background_model": "edge", "sigma_clip": 1.9125, "source_threshold": 3.5625, "wcs_frame": "domain_specific"}`
- `public_2` parameters: `{"aperture_radius": 12, "background_model": "compat", "sigma_clip": 1.8125, "source_threshold": 6.7625, "wcs_frame": "baseline"}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on the
public scenarios and report which fields/signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode20`.
