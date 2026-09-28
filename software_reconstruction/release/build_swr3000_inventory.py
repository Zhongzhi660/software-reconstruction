#!/usr/bin/env python3
"""Build the 3000-variant reconstruction inventory manifest."""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_ROOT = Path(
    os.environ.get(
        "TERMINAL_AGENT_DATA_ROOT",
        "/path/to/software_reconstruction_data",
    )
)
SILR_ROOT = Path(
    os.environ.get("SWR_DATA_ROOT", str(DATA_ROOT / "software_reconstruction"))
)
DEFAULT_OUTPUT = SILR_ROOT / "final_reconstruction_inventory_3000_20260828"


SOURCES = {
    "true10": {
        "plan": SILR_ROOT / "true_10family_parametric_expansion/concrete_param_groups_100x6_20260827_2245.json",
        "materialized_root": None,
        "oracle_status": "parent/demo oracle smoke evidence exists; full 600 rollout started separately",
    },
    "new10": {
        "plan": SILR_ROOT / "new10family_expansion/online_concrete_param_groups_100x6.json",
        "materialized_root": SILR_ROOT / "materialized_planned2400_20260828/new10",
        "oracle_status": "600/600 native+Daytona oracle smoke passed; hidden oracle judges integrated and V2 validated",
    },
    "offcode6": {
        "plan": SILR_ROOT / "offcode6_expansion/online_concrete_param_groups_60x6.json",
        "materialized_root": SILR_ROOT / "materialized_planned2400_20260828/offcode6",
        "oracle_status": "360/360 native+Daytona oracle smoke passed; hidden oracle judges integrated and V2 validated",
    },
    "offcode20": {
        "plan": SILR_ROOT / "offcode20_expansion/online_concrete_param_groups_240x6.json",
        "materialized_root": SILR_ROOT / "materialized_planned2400_20260828/offcode20",
        "oracle_status": "1440/1440 Daytona oracle smoke passed; hidden oracle judges integrated and V2 validated",
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_records(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["records"]


def safe_id(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")


def record_task_id(record: dict[str, Any]) -> str:
    if record.get("task_id"):
        return str(record["task_id"])
    suffix = str(record["group_id"]).rsplit("_", 1)[-1]
    return safe_id(f"{record['demo_id']}__{suffix}")


def task_path(group: str, root: Path | None, record: dict[str, Any]) -> str | None:
    if root is None:
        return None
    task_id = f"{group}__{record_task_id(record)}"
    path = root / task_id
    return str(path) if path.is_dir() else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for group, spec in SOURCES.items():
        records = load_records(spec["plan"])
        for record in records:
            task_id = record_task_id(record)
            rows.append(
                {
                    "inventory_id": f"{group}::{task_id}",
                    "source_group": group,
                    "task_id": task_id,
                    "family_id": record["family_id"],
                    "demo_id": record["demo_id"],
                    "group_id": record["group_id"],
                    "axes_to_vary": record.get("axes_to_vary", []),
                    "public_scenario_count": len(record.get("public_scenarios", [])),
                    "hidden_scenario_count": len(record.get("hidden_scenarios", [])),
                    "status": record.get("status"),
                    "oracle_status": spec["oracle_status"],
                    "plan_path": str(spec["plan"]),
                    "task_path": task_path(group, spec["materialized_root"], record),
                }
            )

    by_group = Counter(row["source_group"] for row in rows)
    by_family = Counter(row["family_id"] for row in rows)
    materialized = sum(1 for row in rows if row["task_path"])
    summary = {
        "schema": "reconstruction-inventory-3000-v1",
        "created_at": utc_now(),
        "output": str(out),
        "variant_count": len(rows),
        "materialized_count": materialized,
        "planned_only_count": len(rows) - materialized,
        "source_counts": dict(sorted(by_group.items())),
        "family_counts": dict(sorted(by_family.items())),
        "manifest_jsonl": str(out / "final_3000_task_manifest.jsonl"),
        "notes": [
            "new10/offcode6/offcode20 are materialized under materialized_planned2400_20260828 and now have hidden oracle judges integrated.",
            "true10 remains represented from its concrete 600-variant plan here; its rollout/materialization history is separate.",
        ],
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (out / "final_3000_task_manifest.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
