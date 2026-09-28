#!/usr/bin/env python3
"""Create concrete parametric groups for admitted off-code demos."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_ROOT = Path("/path/to/software_reconstruction_data")
EXP_ROOT = DATA_ROOT / "software_reconstruction/offcode6_expansion"
DEFAULT_AUDIT = EXP_ROOT / "online_60demo_static_quality_audit.json"
DEFAULT_OUTPUT = EXP_ROOT / "online_concrete_param_groups_60x6.json"


STRATEGIES = (
    "balanced_shift",
    "boundary_low",
    "boundary_high",
    "cross_interaction",
    "hidden_axis_holdout",
    "stress_resource",
)


HIDDEN_FOCUS = {
    "audio_signal_processing": "unseen resampling/filter/noise interactions not present in public clips",
    "robotics_control": "joint/controller/collision boundary cases under hidden poses",
    "molecular_chemistry": "stereo/protonation/substructure boundaries and descriptor changes",
    "medical_imaging": "slice/window/orientation/mask interventions on unseen image metadata",
    "circuit_simulation": "component/source/temperature interventions changing simulation summaries",
    "finite_element_mechanics": "mesh/material/load/boundary interventions changing mechanics summaries",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_int(*parts: str, modulo: int = 1000) -> int:
    data = "|".join(parts).encode()
    return int(hashlib.blake2b(data, digest_size=8).hexdigest(), 16) % modulo


def value_for(axis: str, strategy: str, demo_id: str, group_idx: int, scenario_idx: int, hidden: bool) -> Any:
    token = axis.lower()
    seed = stable_int(axis, strategy, demo_id, str(group_idx), str(scenario_idx), "hidden" if hidden else "public", modulo=997)
    intensity = {
        "balanced_shift": 1.0,
        "boundary_low": 0.55,
        "boundary_high": 1.55,
        "cross_interaction": 1.25,
        "hidden_axis_holdout": 1.4,
        "stress_resource": 1.7,
    }[strategy]
    if any(word in token for word in ("type", "layout", "profile", "modality", "orientation", "analysis")):
        options = ["baseline", "strict", "compat", "stress", "edge"]
        return options[seed % len(options)]
    if any(word in token for word in ("state", "stereo", "collision", "contact")):
        return bool((seed + group_idx + scenario_idx + int(hidden)) % 2)
    if any(word in token for word in ("rate", "size", "range", "level", "gain", "seed", "radius", "density")):
        return max(1, int(round((2 + seed % 16) * intensity)))
    if any(word in token for word in ("threshold", "margin", "tolerance", "property", "value")):
        return round((0.1 + (seed % 120) / 20.0) * intensity, 4)
    if any(word in token for word in ("target", "query", "waveform", "condition", "case", "region")):
        return f"{token}_{seed % 23}_{'hidden' if hidden else 'public'}"
    return round((1.0 + (seed % 100) / 13.0) * intensity, 4)


def scenario(record: dict[str, Any], strategy: str, group_idx: int, scenario_idx: int, hidden: bool) -> dict[str, Any]:
    return {
        "scenario_id": f"{'hidden' if hidden else 'public'}_{scenario_idx}",
        "parameters": {
            axis: value_for(axis, strategy, record["demo_id"], group_idx, scenario_idx, hidden)
            for axis in record["parameter_axes"]
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--groups-per-demo", type=int, default=6)
    args = parser.parse_args()

    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    admitted = [record for record in audit["records"] if record["difficulty_audit"]["admitted"]]
    records = []
    for record in admitted:
        for group_idx in range(1, args.groups_per_demo + 1):
            strategy = STRATEGIES[(group_idx - 1) % len(STRATEGIES)]
            records.append({
                "task_id": f"{record['demo_id']}__{group_idx:02d}",
                "demo_id": record["demo_id"],
                "family_id": record["family_id"],
                "broad_domain": record["broad_domain"],
                "source_repos": record["source_repos"],
                "software": record["software"],
                "group_id": f"{record['demo_id']}_param_group_{group_idx:02d}",
                "strategy": strategy,
                "axes_to_vary": record["parameter_axes"],
                "hidden_intervention": HIDDEN_FOCUS[record["family_id"]],
                "public_scenarios": [scenario(record, strategy, group_idx, idx, hidden=False) for idx in range(1, 3)],
                "hidden_scenarios": [scenario(record, strategy, group_idx, idx, hidden=True) for idx in range(1, 4)],
                "difficulty_audit": record["difficulty_audit"],
                "oracle_distinctness_gate": "public and hidden native-tool outputs must differ across parameter groups; public-only lookup tables must fail",
                "status": "concrete_parameters_designed_requires_native_oracle_materialization",
            })

    family_counts = {
        family_id: sum(1 for record in records if record["family_id"] == family_id)
        for family_id in sorted({record["family_id"] for record in records})
    }
    payload = {
        "schema": "offcode6-concrete-param-groups-v1",
        "created_at": utc_now(),
        "audit": str(args.audit),
        "groups_per_demo": args.groups_per_demo,
        "admitted_demo_count": len(admitted),
        "record_count": len(records),
        "family_counts": family_counts,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "record_count": len(records), "family_counts": family_counts}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
