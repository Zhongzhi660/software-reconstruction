#!/usr/bin/env python3
"""Create concrete parametric groups for admitted offcode20 demos."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_ROOT = Path("/path/to/software_reconstruction_data")
EXP_ROOT = DATA_ROOT / "software_reconstruction/offcode20_expansion"
DEFAULT_AUDIT = EXP_ROOT / "online_240demo_static_quality_audit.json"
DEFAULT_OUTPUT = EXP_ROOT / "online_concrete_param_groups_240x6.json"


STRATEGIES = (
    "balanced_shift",
    "boundary_low",
    "boundary_high",
    "cross_interaction",
    "hidden_axis_holdout",
    "stress_resource",
)


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
    if any(word in token for word in ("type", "policy", "method", "model", "frame", "space", "layout", "selection", "language")):
        options = ["baseline", "strict", "compat", "stress", "edge", "domain_specific"]
        return options[seed % len(options)]
    if any(word in token for word in ("outage", "substitution", "removal", "correction", "change")):
        return bool((seed + group_idx + scenario_idx + int(hidden)) % 2)
    if any(word in token for word in ("rate", "size", "range", "radius", "duration", "window", "replicates", "level", "scale", "quality")):
        return max(1, int(round((2 + seed % 18) * intensity)))
    if any(word in token for word in ("threshold", "tolerance", "cutoff", "offset", "limit", "clip")):
        return round((0.05 + (seed % 140) / 25.0) * intensity, 4)
    if any(word in token for word in ("taxon", "chain", "route", "station", "source", "region", "variable", "part", "glyph", "channel")):
        return f"{token}_{seed % 29}_{'hidden' if hidden else 'public'}"
    if any(word in token for word in ("tensor", "bounds", "position", "projection", "orientation")):
        return [round((seed % 13 + idx + 1) * intensity, 3) for idx in range(3)]
    return round((1.0 + (seed % 120) / 17.0) * intensity, 4)


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
                "hidden_intervention": record["oracle_focus"],
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
        "schema": "offcode20-concrete-param-groups-v1",
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
