#!/usr/bin/env python3
"""Validate and finalize holdout-100 tasks synced from the full benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

import audit_benchmark as auditor
import finalize_benchmark as finalizer


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def remove_python_caches(task: Path) -> None:
    for directory in sorted(
        task.rglob("__pycache__"),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        if directory.is_dir():
            shutil.rmtree(directory)
    for path in task.rglob("*.pyc"):
        if path.is_file():
            path.unlink()


def update_static_audit(
    root: Path,
    task_ids: list[str],
    updated_ids: list[str],
    repeat: int,
) -> dict[str, Any]:
    path = root / "validation/static_audit.jsonl"
    previous = {
        str(row["task_id"]): row for row in read_jsonl(path)
    }
    for index, task_id in enumerate(updated_ids, 1):
        row = auditor.audit_task(root / "tasks" / task_id, repeat)
        previous[task_id] = row
        print(
            json.dumps(
                {
                    "phase": "static_audit",
                    "progress": f"{index}/{len(updated_ids)}",
                    "task_id": task_id,
                    "passed": row["passed"],
                    "failed_checks": [
                        key
                        for key, value in row["checks"].items()
                        if not value
                    ],
                },
                sort_keys=True,
            ),
            flush=True,
        )
    records = [previous[task_id] for task_id in task_ids]
    if len(records) != 100:
        raise RuntimeError("static audit merge did not produce 100 rows")
    write_jsonl(path, records)
    self_test = auditor.global_comparator_self_test()
    state_counts = Counter(
        "passed" if row["passed"] else "failed" for row in records
    )
    failed = [
        {
            "task_id": row["task_id"],
            "family_id": row["family_id"],
            "failed_checks": [
                key
                for key, value in row["checks"].items()
                if not value
            ],
            "details": row["details"],
        }
        for row in records
        if not row["passed"]
    ]
    summary = {
        "schema": "swr-benchmark-static-oracle-audit-v2",
        "created_at": auditor.utc_now(),
        "benchmark_root": str(root),
        "task_count": len(records),
        "oracle_repeat_count": repeat,
        "state_counts": dict(state_counts),
        "passed": not failed and all(self_test.values()),
        "comparator_self_test": self_test,
        "failed": failed,
        "v3_sync_revalidated_task_ids": updated_ids,
    }
    auditor.write_json(
        root / "validation/static_audit_summary.json", summary
    )
    if not summary["passed"]:
        raise RuntimeError(
            f"static validation failed for {len(failed)} tasks"
        )
    return summary


def install_exact_tree_profile_evidence(
    root: Path,
    full_root: Path,
    updated_ids: list[str],
    full_profile: Path,
) -> Path:
    source = {
        Path(str(row.get("task_dir") or "")).name: row
        for row in read_jsonl(full_profile)
    }
    rows = []
    for task_id in updated_ids:
        row = dict(source[task_id])
        source_hash, _, _ = finalizer.tree_hash(
            full_root / "tasks" / task_id
        )
        destination_hash, _, _ = finalizer.tree_hash(
            root / "tasks" / task_id
        )
        if source_hash != destination_hash:
            raise RuntimeError(
                f"runtime evidence tree mismatch for {task_id}"
            )
        if row.get("issues") or not row.get("oracle_output_ok_count"):
            raise RuntimeError(
                f"full-profile evidence is not clean for {task_id}"
            )
        row["profiled_task_dir"] = row["task_dir"]
        row["task_dir"] = str(root / "tasks" / task_id)
        row["evidence_reused_by_canonical_tree_match"] = True
        row["canonical_task_tree_sha256"] = source_hash
        rows.append(row)
    output_dir = root / "validation/daytona_oracle_profile_v3_sync"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "task_profile.jsonl"
    write_jsonl(output, rows)
    finalizer.write_json(
        output_dir / "evidence_report.json",
        {
            "schema": "swr-exact-tree-profile-evidence-v1",
            "created_at": finalizer.utc_now(),
            "source_profile": str(full_profile),
            "source_profile_sha256": sha256_file(full_profile),
            "task_count": len(rows),
            "task_ids": updated_ids,
            "all_canonical_task_trees_match": True,
            "canonicalization": (
                "Transient Python bytecode caches were removed before "
                "hashing."
            ),
            "output": str(output),
        },
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--full-root", type=Path, required=True)
    parser.add_argument("--full-profile", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=2)
    args = parser.parse_args()

    root = args.root.resolve()
    full_root = args.full_root.resolve()
    sync_report_path = root / "v3_sync_report.json"
    sync_report = finalizer.load_json(sync_report_path)
    updated_ids = list(sync_report["updated_task_ids"])
    task_ids = [
        line.strip()
        for line in (root / "test_task_ids.txt").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    if len(updated_ids) != 17:
        raise RuntimeError(f"expected 17 updated tasks: {updated_ids}")
    if len(task_ids) != 100 or not set(updated_ids).issubset(task_ids):
        raise RuntimeError("invalid holdout ID inventory")

    static_summary_path = root / "validation/static_audit_summary.json"
    existing_static = (
        finalizer.load_json(static_summary_path)
        if static_summary_path.is_file()
        else {}
    )
    if (
        existing_static.get("passed") is True
        and set(
            existing_static.get("v3_sync_revalidated_task_ids") or []
        )
        == set(updated_ids)
    ):
        static = existing_static
        print(
            json.dumps(
                {
                    "phase": "static_audit",
                    "state": "reused_completed_v3_sync_audit",
                    "tasks": len(updated_ids),
                },
                sort_keys=True,
            ),
            flush=True,
        )
    else:
        static = update_static_audit(
            root, task_ids, updated_ids, max(2, args.repeat)
        )
    for task_id in updated_ids:
        remove_python_caches(root / "tasks" / task_id)
        remove_python_caches(full_root / "tasks" / task_id)
    evidence_path = install_exact_tree_profile_evidence(
        root,
        full_root,
        updated_ids,
        args.full_profile.resolve(),
    )
    finalizer.finalize(root)
    quality_path = root / "quality_report.json"
    quality = finalizer.load_json(quality_path)
    if not quality.get("approved"):
        raise RuntimeError("final holdout quality report is not approved")

    sync_report["state"] = "validated"
    sync_report["validated_at"] = finalizer.utc_now()
    sync_report["static_audit_summary"] = str(
        root / "validation/static_audit_summary.json"
    )
    sync_report["static_audit_summary_sha256"] = sha256_file(
        root / "validation/static_audit_summary.json"
    )
    sync_report["runtime_profile_evidence"] = str(evidence_path)
    sync_report["runtime_profile_evidence_sha256"] = sha256_file(
        evidence_path
    )
    sync_report["quality_report"] = str(quality_path)
    sync_report["static_revalidated_task_count"] = len(
        static["v3_sync_revalidated_task_ids"]
    )
    for record in sync_report["records"]:
        task_id = record["task_id"]
        source_hash, _, _ = finalizer.tree_hash(
            full_root / "tasks" / task_id
        )
        destination_hash, destination_files, destination_bytes = (
            finalizer.tree_hash(root / "tasks" / task_id)
        )
        if source_hash != destination_hash:
            raise RuntimeError(
                f"post-validation tree mismatch for {task_id}"
            )
        record["canonical_source_tree_sha256"] = source_hash
        record["canonical_destination_tree_sha256"] = destination_hash
        record["canonical_file_count"] = destination_files
        record["canonical_total_bytes"] = destination_bytes
    backup_root = Path(sync_report["backup_root"])
    if backup_root.is_dir():
        shutil.rmtree(backup_root)
    sync_report["backup_removed"] = not backup_root.exists()

    repair_path = root / "repair_report.json"
    repair = finalizer.load_json(repair_path)
    repair["v3_sync_report"] = str(sync_report_path)
    repair["v3_synced_task_count"] = len(updated_ids)
    repair["v3_synced_task_ids"] = updated_ids
    finalizer.write_json(repair_path, repair)
    quality["v3_sync_report"] = str(sync_report_path)
    quality["v3_synced_task_count"] = len(updated_ids)
    quality["v3_synced_task_ids"] = updated_ids
    finalizer.write_json(quality_path, quality)
    sync_report["benchmark_manifest_sha256"] = sha256_file(
        root / "benchmark_manifest.jsonl"
    )
    sync_report["quality_report_sha256"] = sha256_file(quality_path)
    finalizer.write_json(sync_report_path, sync_report)

    status_path = root / "STATUS.json"
    status = finalizer.load_json(status_path)
    status["v3_synced_task_count"] = len(updated_ids)
    status["v3_sync_report"] = str(sync_report_path)
    finalizer.write_json(status_path, status)
    print(
        json.dumps(
            {
                "state": "validated",
                "tasks": len(task_ids),
                "updated_tasks": len(updated_ids),
                "static_passed": static["state_counts"],
                "runtime_passed": quality["runtime_validation"][
                    "passed_task_count"
                ],
                "approved": quality["approved"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
