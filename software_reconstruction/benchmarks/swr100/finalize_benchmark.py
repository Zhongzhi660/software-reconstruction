#!/usr/bin/env python3
"""Consolidate validation evidence and publish the repaired holdout-100 set."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_ROOT = Path(
    "/path/to/software_reconstruction_data"
)
DEFAULT_ROOT = (
    DATA_ROOT
    / "software_reconstruction/swr3000_variant_holdout100_benchmark_v2_20260911"
)
PROFILE_DIRS = [
    "daytona_oracle_profile",
    "daytona_oracle_profile_retry1",
    "daytona_oracle_profile_retry2",
    "daytona_oracle_profile_retry3",
    "daytona_oracle_profile_v3_sync",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def tree_hash(task: Path) -> tuple[str, int, int]:
    hasher = hashlib.sha256()
    file_count = 0
    total_bytes = 0
    for path in sorted(item for item in task.rglob("*") if item.is_file()):
        relative = str(path.relative_to(task))
        size = path.stat().st_size
        hasher.update(relative.encode())
        hasher.update(b"\0")
        hasher.update(sha256_file(path).encode())
        hasher.update(b"\n")
        file_count += 1
        total_bytes += size
    return hasher.hexdigest(), file_count, total_bytes


def consolidate_runtime(root: Path, task_paths: list[Path]) -> dict[str, Any]:
    expected = {str(path): path.name for path in task_paths}
    latest: dict[str, dict[str, Any]] = {}
    provenance: dict[str, str] = {}
    for directory_name in PROFILE_DIRS:
        path = root / "validation" / directory_name / "task_profile.jsonl"
        if not path.is_file():
            continue
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                task_dir = str(record.get("task_dir") or "")
                if task_dir in expected:
                    latest[task_dir] = record
                    provenance[task_dir] = directory_name

    missing = sorted(set(expected) - set(latest))
    records = []
    for task_dir in sorted(latest):
        record = latest[task_dir]
        issues = record.get("issues") or []
        output_failures = int(record.get("oracle_output_failed_count") or 0)
        expected_scenarios = int(record.get("n_public") or 0) + int(
            record.get("n_hidden") or 0
        )
        output_successes = int(record.get("oracle_output_ok_count") or 0)
        checks = {
            "profile_has_no_issues": not issues,
            "oracle_all_scenarios_execute": (
                output_failures == 0 and output_successes == expected_scenarios
            ),
            "oracle_deterministic": record.get("oracle_deterministic") is True,
            "schema_consistent": record.get("schema_consistent") is True,
            "public_hidden_outputs_distinct": not bool(
                record.get("public_hidden_output_duplicate")
            ),
            "behavior_sensitive": float(
                record.get("behavioral_sensitivity") or 0.0
            )
            > 0.0,
        }
        records.append(
            {
                "task_id": expected[task_dir],
                "task_path": task_dir,
                "family_id": record.get("family"),
                "profile_source": provenance[task_dir],
                "passed": all(checks.values()),
                "checks": checks,
                "issues": issues,
                "oracle_output_ok_count": output_successes,
                "oracle_output_failed_count": output_failures,
                "behavioral_sensitivity": record.get("behavioral_sensitivity"),
                "field_sensitivity": record.get("field_sensitivity"),
                "parameter_effect_coverage": (
                    record.get("effective_parameter_axis_count")
                    / record.get("param_dim")
                    if record.get("param_dim")
                    and record.get("effective_parameter_axis_count") is not None
                    else None
                ),
            }
        )
    failed = [record for record in records if not record["passed"]]
    validation_dir = root / "validation"
    with (validation_dir / "daytona_runtime_consolidated.jsonl").open(
        "w", encoding="utf-8"
    ) as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    summary = {
        "schema": "swr-benchmark-daytona-runtime-consolidated-v2",
        "created_at": utc_now(),
        "expected_task_count": len(task_paths),
        "profiled_task_count": len(records),
        "passed_task_count": sum(record["passed"] for record in records),
        "failed_task_count": len(failed),
        "missing_task_paths": missing,
        "profile_source_counts": dict(Counter(provenance.values())),
        "passed": not missing and not failed and len(records) == len(task_paths),
        "failed": failed,
    }
    write_json(validation_dir / "daytona_runtime_summary.json", summary)
    return summary


def refresh_manifest(root: Path, task_paths: list[Path]) -> list[dict[str, Any]]:
    old_records = {}
    manifest_path = root / "benchmark_manifest.jsonl"
    if manifest_path.is_file():
        with manifest_path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    record = json.loads(line)
                    old_records[record["task_id"]] = record
    records = []
    for index, task in enumerate(task_paths, 1):
        private_manifest = load_json(task / "tests/private/manifest.json")
        variant = load_json(task / "tests/private/variant.json")
        tree_sha256, file_count, total_bytes = tree_hash(task)
        public_archive = (
            task
            / "environment/app/observations/reference_outputs.tar.gz"
        )
        old = old_records.get(task.name, {})
        record = {
            **old,
            "index": index,
            "task_id": task.name,
            "task_path": str(task),
            "repaired_task_path": str(task),
            "family_id": private_manifest["family_id"],
            "demo_id": private_manifest.get("demo_id"),
            "group_id": private_manifest.get("group_id"),
            "logical_task_id": variant.get("task_id"),
            "oracle_repaired": bool(
                private_manifest.get("family_oracle_repaired")
            ),
            "hidden_resampled": bool(
                variant.get("benchmark_hidden_resampled_at")
            ),
            "hidden_resampled_axes": variant.get(
                "benchmark_hidden_resampled_axes", []
            ),
            "collision_repair": {
                "hidden_resampled": bool(
                    variant.get("benchmark_hidden_resampled_at")
                ),
                "resampled_axes": variant.get(
                    "benchmark_hidden_resampled_axes", []
                ),
            },
            "archive": {
                "mode": "finalized",
                "archive_sha256": sha256_file(public_archive),
            },
            "semantic_comparator": (
                "geometry_specific"
                if private_manifest["family_id"].startswith("openscad")
                else "strict_complete_recursive"
            ),
            "repaired_tree_sha256": tree_sha256,
            "file_count": file_count,
            "total_bytes": total_bytes,
            "state": "validated",
        }
        records.append(record)
    with manifest_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    return records


def finalize(root: Path) -> None:
    ids = [
        line
        for line in (root / "test_task_ids.txt").read_text().splitlines()
        if line
    ]
    task_paths = [
        Path(line)
        for line in (root / "test_task_paths.txt").read_text().splitlines()
        if line
    ]
    if len(ids) != 100 or len(task_paths) != 100:
        raise RuntimeError("final benchmark must contain exactly 100 tasks")
    if [path.name for path in task_paths] != ids:
        raise RuntimeError("test task IDs and paths are not aligned")

    static = load_json(root / "validation/static_audit_summary.json")
    runtime = consolidate_runtime(root, task_paths)
    manifest = refresh_manifest(root, task_paths)
    family_counts = Counter(record["family_id"] for record in manifest)
    oracle_repaired = [
        record["task_id"] for record in manifest if record["oracle_repaired"]
    ]
    hidden_resampled = [
        record["task_id"] for record in manifest if record["hidden_resampled"]
    ]
    gates = {
        "exactly_100_tasks": len(task_paths) == 100,
        "logical_split_preserved": len(set(ids)) == 100,
        "source_baseline_frozen": (
            root / "baseline_freeze_manifest.jsonl"
        ).is_file(),
        "static_oracle_negative_audit_100_of_100": (
            static.get("passed") is True
            and static.get("state_counts") == {"passed": 100}
        ),
        "daytona_runtime_audit_100_of_100": runtime.get("passed") is True,
        "strict_complete_comparator_99_tasks": sum(
            record["semantic_comparator"] == "strict_complete_recursive"
            for record in manifest
        )
        == 99,
        "openscad_geometry_comparator_preserved": sum(
            record["semantic_comparator"] == "geometry_specific"
            for record in manifest
        )
        == 1,
        "all_tasks_have_final_hashes": all(
            len(record["repaired_tree_sha256"]) == 64 for record in manifest
        ),
    }
    report = {
        "schema": "swr-holdout100-final-quality-report-v2",
        "created_at": utc_now(),
        "benchmark_root": str(root),
        "source_split": str(
            DATA_ROOT
            / "software_reconstruction/swr3000_variant_holdout100_20260909_v1"
        ),
        "task_count": 100,
        "family_count": len(family_counts),
        "family_counts": dict(sorted(family_counts.items())),
        "oracle_repaired_task_count": len(oracle_repaired),
        "oracle_repaired_task_ids": oracle_repaired,
        "hidden_resampled_task_count": len(hidden_resampled),
        "hidden_resampled_task_ids": hidden_resampled,
        "static_validation": static,
        "runtime_validation": runtime,
        "acceptance_gates": gates,
        "approved": all(gates.values()),
        "score_compatibility": (
            "Scores from the v1 verifier are not directly comparable. "
            "Re-evaluate all baselines on this v2 task set."
        ),
    }
    write_json(root / "quality_report.json", report)
    write_json(
        root / "repair_report.json",
        {
            "schema": "swr-holdout100-benchmark-repair-v2-final",
            "created_at": report["created_at"],
            "source_split": report["source_split"],
            "output": str(root),
            "task_count": 100,
            "oracle_repaired_task_count": len(oracle_repaired),
            "hidden_resampled_task_count": len(hidden_resampled),
            "state": "validated",
            "records": manifest,
            "canonical_quality_report": str(root / "quality_report.json"),
        },
    )

    readme = f"""# SWR holdout-100 benchmark v2

This directory is the repaired benchmark copy of:

`{report["source_split"]}`

The original 100 logical task IDs and the 2900/100 split are preserved.  The
source task directories were not modified.

## Inputs

- Test IDs: `test_task_ids.txt`
- Test task paths: `test_task_paths.txt`
- Per-task manifest and final hashes: `benchmark_manifest.jsonl`
- Frozen v1 source hashes: `baseline_freeze_manifest.jsonl`

## Validation

- Static/oracle/adversarial audit: `validation/static_audit_summary.json`
- Consolidated Daytona runtime audit: `validation/daytona_runtime_summary.json`
- Final report: `quality_report.json`

Acceptance status: **{"APPROVED" if report["approved"] else "NOT APPROVED"}**

The generic verifier now compares every dictionary field and every list item,
does not ignore digest-like values, and uses exact integer plus 1e-4 relative
float comparison.  The OpenSCAD task keeps its dedicated STL geometry verifier.
Public parameter-digest scaffolding was removed.  Hidden output replay,
determinism, schema, missing-field, list-truncation, numeric-tampering and
digest-tampering checks are covered by the static audit.

Do not compare v1 and v2 scores directly.  Baselines must be re-evaluated on
the v2 paths above because verifier strictness and selected private scenarios
changed.
"""
    (root / "README.md").write_text(readme, encoding="utf-8")
    write_json(
        root / "STATUS.json",
        {
            "state": "approved" if report["approved"] else "not_approved",
            "updated_at": utc_now(),
            "task_count": 100,
            "static_passed_count": 100
            if static.get("passed")
            else static.get("state_counts", {}).get("passed", 0),
            "runtime_passed_count": runtime.get("passed_task_count", 0),
            "acceptance_gates": gates,
        },
    )
    if not report["approved"]:
        raise SystemExit("benchmark did not pass all final acceptance gates")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    finalize(args.root.resolve())


if __name__ == "__main__":
    main()
