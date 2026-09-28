#!/usr/bin/env python3
"""Create concrete 100x6 parametric groups for admitted new10 online demos."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_ROOT = Path("/path/to/software_reconstruction_data")
EXP_ROOT = DATA_ROOT / "software_reconstruction/new10family_expansion"
DEFAULT_AUDIT = EXP_ROOT / "online_100demo_static_difficulty_audit.json"
DEFAULT_OUTPUT = EXP_ROOT / "online_concrete_param_groups_100x6.json"

STRATEGIES = (
    "balanced_shift",
    "boundary_low",
    "boundary_high",
    "cross_interaction",
    "hidden_axis_holdout",
    "stress_resource",
)

HIDDEN_FOCUS = {
    "sqlite_analytics": "date/null/join boundary rows not present in public observations",
    "duckdb_reporting": "schema evolution and ordering ties",
    "ajv_schema": "invalid near-miss payloads and recursive references",
    "opa_rego_policy": "namespace/resource exceptions and negative policy cases",
    "container_supply_chain": "SBOM/license/label edge cases not visible in public layer",
    "gdal_geospatial": "CRS/nodata/invalid geometry boundary cases",
    "samtools_bio_qc": "low-quality reads, region edges, missing genotypes",
    "z3_constraint_system": "sat/unsat boundary flips under changed bounds",
    "network_security_pcap": "protocol decoys and packet-loss/fragmentation cases",
    "document_ocr_publishing": "page overflow, OCR language/font and metadata changes",
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
    if any(word in token for word in ("mode", "policy", "format", "schema", "crs", "protocol", "language", "font")):
        options = ["baseline", "strict", "compat", "stress", "edge"]
        return options[seed % len(options)]
    if any(word in token for word in ("null", "exception", "conflict", "loss", "invalid")):
        return bool((seed + group_idx + scenario_idx + int(hidden)) % 2)
    if any(word in token for word in ("depth", "count", "partition", "port", "bitwidth", "ploidy")):
        return max(1, int(round((2 + seed % 8) * intensity)))
    if any(word in token for word in ("window", "range", "bbox", "resolution", "dpi", "capacity", "bounds", "quality", "threshold")):
        return round((1.0 + (seed % 100) / 10.0) * intensity, 3)
    if any(word in token for word in ("key", "identity", "namespace", "reference", "region", "layer", "entrypoint")):
        return f"{token}_{seed % 17}_{'h' if hidden else 'p'}"
    return round((1.0 + (seed % 50) / 7.0) * intensity, 3)


def scenario(record: dict[str, Any], strategy: str, group_idx: int, scenario_idx: int, hidden: bool) -> dict[str, Any]:
    axes = record["parameter_axes"]
    return {
        "scenario_id": f"{'hidden' if hidden else 'public'}_{scenario_idx}",
        "parameters": {
            axis: value_for(axis, strategy, record["demo_id"], group_idx, scenario_idx, hidden)
            for axis in axes
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
            records.append(
                {
                    "task_id": f"{record['demo_id']}__{group_idx:02d}",
                    "demo_id": record["demo_id"],
                    "family_id": record["family_id"],
                    "image_family": record["image_family"],
                    "source_repos": record["source_repos"],
                    "software": record["software"],
                    "group_id": f"{record['demo_id']}_param_group_{group_idx:02d}",
                    "strategy": strategy,
                    "axes_to_vary": record["parameter_axes"],
                    "hidden_intervention": HIDDEN_FOCUS[record["family_id"]],
                    "public_scenarios": [
                        scenario(record, strategy, group_idx, idx, hidden=False) for idx in range(1, 3)
                    ],
                    "hidden_scenarios": [
                        scenario(record, strategy, group_idx, idx, hidden=True) for idx in range(1, 4)
                    ],
                    "difficulty_audit": record["difficulty_audit"],
                    "oracle_distinctness_gate": "public and hidden native-tool outputs must differ across parameter groups and reject public-only lookup tables",
                    "status": "concrete_parameters_designed_requires_native_oracle_materialization",
                }
            )
    family_counts = {}
    for family_id in sorted({record["family_id"] for record in records}):
        family_counts[family_id] = sum(1 for record in records if record["family_id"] == family_id)
    payload = {
        "schema": "new10-online-concrete-param-groups-v1",
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
