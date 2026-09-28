# Reconstruct gtfs_realtime_trip_update_join

You are given public observations from a real software-in-the-loop reference
artifact in the `transport_gtfs_schedule` family.

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
GTFS validators, transit feed tooling.

Parameter axes: `headway_window`, `route_filter`, `service_date`, `time_zone`, `transfer_policy`

Public scenarios:
- `public_1` parameters: `{"headway_window": 8, "route_filter": "route-filter-2", "service_date": 3.3971, "time_zone": 1.6176, "transfer_policy": "stress"}`
- `public_2` parameters: `{"headway_window": 6, "route_filter": "route-filter-11", "service_date": 0.7765, "time_zone": 1.2941, "transfer_policy": "edge"}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on the
public scenarios and report which fields/signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `offcode20`.
