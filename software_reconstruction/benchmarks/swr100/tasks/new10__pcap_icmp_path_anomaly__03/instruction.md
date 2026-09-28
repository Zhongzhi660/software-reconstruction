# Reconstruct pcap_icmp_path_anomaly

You are given public observations from a real software-in-the-loop reference
artifact in the `network_security_pcap` family.

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
tshark, tcpdump, nmap.

Parameter axes: `alert_rule`, `flow_pattern`, `packet_loss`, `port`, `protocol`

Public scenarios:
- `public_1` parameters: `{"alert_rule": 10.629, "flow_pattern": 5.979, "packet_loss": false, "port": 5, "protocol": "strict"}`
- `public_2` parameters: `{"alert_rule": 11.6, "flow_pattern": 6.73, "packet_loss": true, "port": 28, "protocol": "tcp"}`
- `public_3` parameters: `{"alert_rule": 3.0, "flow_pattern": 4.143, "packet_loss": true, "port": 3, "protocol": "baseline"}`
- `public_4` parameters: `{"alert_rule": 6.893, "flow_pattern": 5.337, "packet_loss": false, "port": 32, "protocol": "dns"}`
- `public_5` parameters: `{"alert_rule": 0.55, "flow_pattern": 4.086, "packet_loss": true, "port": 3, "protocol": "baseline"}`
- `public_6` parameters: `{"alert_rule": 1.693, "flow_pattern": 3.865, "packet_loss": false, "port": 27, "protocol": "http"}`

Use `/app/tools/feedback` while solving. It will run your `reconstruct.py` on
the public scenarios and report which signatures match the public oracle
outputs. Passing public feedback is not sufficient by itself; hidden scenarios
from the same parameter space are used for final grading.

Source group: `new10`.
