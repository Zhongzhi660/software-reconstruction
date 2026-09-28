#!/usr/bin/env python3
"""Create concrete parameter scenarios after base materialization passes."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_ROOT = Path("/path/to/software_reconstruction_data")
EXP_ROOT = DATA_ROOT / "software_reconstruction/true_10family_parametric_expansion"
DEFAULT_MANIFEST = EXP_ROOT / "resolved_source_manifest_100demos_strict_repaired_20260827_2030_verilog2_replaced.json"
DEFAULT_PARAM_DESIGN = EXP_ROOT / "per_demo_param_group_design_100demos_20260827_2215.json"
DEFAULT_OUTPUT = EXP_ROOT / "concrete_param_groups_100x6_20260827_2245.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_int(*parts: str, modulo: int = 1000) -> int:
    data = "|".join(parts).encode()
    return int(hashlib.blake2b(data, digest_size=8).hexdigest(), 16) % modulo


def number_for(axis: str, strategy: str, scenario_idx: int, hidden: bool) -> int | float | bool | str:
    token = axis.lower()
    seed = stable_int(axis, strategy, str(scenario_idx), "hidden" if hidden else "public", modulo=997)
    intensity = {
        "balanced_shift": 1.0,
        "boundary_low": 0.65,
        "boundary_high": 1.45,
        "cross_interaction": 1.2,
        "hidden_axis_holdout": 1.35,
        "stress_resource": 1.6,
    }.get(strategy, 1.0)

    if any(word in token for word in ("enable", "toggle", "critical", "ssl", "tls", "auth", "cache")):
        return bool((seed + scenario_idx + int(hidden)) % 2)
    if any(word in token for word in ("mode", "policy", "purpose", "solver", "algorithm", "format", "variant")):
        options = ["baseline", "strict", "compat", "stress", "edge"]
        return options[seed % len(options)]
    if any(word in token for word in ("count", "num", "teeth", "cells", "instances", "objects", "layers", "depth")):
        base = 3 + seed % 8
        return max(1, int(round(base * intensity)) + scenario_idx)
    if any(word in token for word in ("size", "scale", "length", "width", "height", "radius", "diameter", "spacing", "pitch")):
        return round((8.0 + (seed % 90) / 5.0) * intensity + scenario_idx * 0.75, 3)
    if any(word in token for word in ("time", "day", "validity", "timeout", "frame", "step", "rate")):
        return int(round((5 + seed % 40) * intensity + scenario_idx * 2))
    if any(word in token for word in ("clearance", "wall", "thickness", "tolerance", "threshold", "epsilon")):
        return round((0.4 + (seed % 35) / 20.0) * intensity, 3)
    if any(word in token for word in ("angle", "phase", "rotation", "orientation")):
        return int((seed * 7 + scenario_idx * 23) % 360)
    return round((1.0 + (seed % 70) / 10.0) * intensity, 3)


def scenario_values(axes: list[str], strategy: str, scenario_idx: int, hidden: bool) -> dict[str, Any]:
    return {
        axis: number_for(axis, strategy, scenario_idx, hidden)
        for axis in axes
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--param-design", type=Path, default=DEFAULT_PARAM_DESIGN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--groups-per-demo", type=int, default=6)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    design = json.loads(args.param_design.read_text(encoding="utf-8"))
    groups_by_demo = {item["demo_id"]: item["groups"] for item in design["demos"]}

    records = []
    for record in manifest["records"]:
        demo_id = record["demo_id"]
        for group in groups_by_demo.get(demo_id, [])[: args.groups_per_demo]:
            axes = list(group["axes_to_vary"])
            public = [
                {
                    "scenario_id": f"public_{idx}",
                    "parameters": scenario_values(axes, group["strategy"], idx, hidden=False),
                }
                for idx in range(1, 3)
            ]
            hidden = [
                {
                    "scenario_id": f"hidden_{idx}",
                    "parameters": scenario_values(axes, group["strategy"], idx, hidden=True),
                }
                for idx in range(1, 3)
            ]
            records.append(
                {
                    "demo_id": demo_id,
                    "family_id": record["family_id"],
                    "group_id": group["group_id"],
                    "strategy": group["strategy"],
                    "axes_to_vary": axes,
                    "hidden_intervention": group["hidden_intervention"],
                    "public_scenarios": public,
                    "hidden_scenarios": hidden,
                    "oracle_distinctness_gate": group["oracle_distinctness_gate"],
                    "status": "concrete_parameters_designed_requires_oracle_execution",
                }
            )

    payload = {
        "schema": "true10-concrete-param-groups-v1",
        "created_at": utc_now(),
        "manifest": str(args.manifest),
        "param_design": str(args.param_design),
        "groups_per_demo": args.groups_per_demo,
        "record_count": len(records),
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "record_count": len(records)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
