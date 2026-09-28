#!/usr/bin/env python3
"""Atomically sync changed task variants from the validated full benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import finalize_benchmark as finalizer


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, payload: Any) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hidden_scenarios(task: Path) -> list[dict[str, Any]]:
    manifest = load_json(task / "tests/private/manifest.json")
    return manifest.get("hidden_scenarios") or []


def task_ids(root: Path) -> list[str]:
    return [
        line.strip()
        for line in (root / "test_task_ids.txt").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]


def rollback(
    holdout_tasks: Path,
    backup_root: Path,
    replaced: list[str],
) -> None:
    for task_id in reversed(replaced):
        destination = holdout_tasks / task_id
        backup = backup_root / task_id
        if destination.exists():
            shutil.rmtree(destination)
        if backup.exists():
            os.replace(backup, destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--holdout-root", type=Path, required=True)
    parser.add_argument("--full-root", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, default=17)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    holdout_root = args.holdout_root.resolve()
    full_root = args.full_root.resolve()
    holdout_tasks = holdout_root / "tasks"
    full_tasks = full_root / "tasks"
    ids = task_ids(holdout_root)
    if len(ids) != 100 or len(set(ids)) != 100:
        raise RuntimeError("holdout must contain 100 unique task IDs")

    missing = [
        task_id
        for task_id in ids
        if not (holdout_tasks / task_id).is_dir()
        or not (full_tasks / task_id).is_dir()
    ]
    if missing:
        raise RuntimeError(f"missing task directories: {missing}")
    changed = [
        task_id
        for task_id in ids
        if hidden_scenarios(holdout_tasks / task_id)
        != hidden_scenarios(full_tasks / task_id)
    ]
    if len(changed) != args.expected_count:
        raise RuntimeError(
            f"expected {args.expected_count} changed variants, "
            f"found {len(changed)}"
        )

    run_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    staging_root = holdout_root / f".v3_sync_staging_{run_tag}"
    backup_root = holdout_root / f".v3_sync_backup_{run_tag}"
    staging_root.mkdir()
    backup_root.mkdir()
    for index, task_id in enumerate(changed, 1):
        shutil.copytree(
            full_tasks / task_id,
            staging_root / task_id,
            symlinks=True,
        )
        source_hash, source_files, source_bytes = finalizer.tree_hash(
            full_tasks / task_id
        )
        staged_hash, staged_files, staged_bytes = finalizer.tree_hash(
            staging_root / task_id
        )
        if (
            source_hash,
            source_files,
            source_bytes,
        ) != (
            staged_hash,
            staged_files,
            staged_bytes,
        ):
            raise RuntimeError(f"staged copy mismatch: {task_id}")
        print(
            json.dumps(
                {
                    "progress": f"{index}/{len(changed)}",
                    "task_id": task_id,
                    "tree_sha256": source_hash,
                },
                sort_keys=True,
            ),
            flush=True,
        )

    replaced: list[str] = []
    try:
        for task_id in changed:
            destination = holdout_tasks / task_id
            os.replace(destination, backup_root / task_id)
            os.replace(staging_root / task_id, destination)
            replaced.append(task_id)
    except BaseException:
        rollback(holdout_tasks, backup_root, replaced)
        raise
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root)

    task_paths = [holdout_tasks / task_id for task_id in ids]
    manifest = finalizer.refresh_manifest(holdout_root, task_paths)
    manifest_path = holdout_root / "benchmark_manifest.jsonl"
    records = []
    for task_id in changed:
        source_hash, source_files, source_bytes = finalizer.tree_hash(
            full_tasks / task_id
        )
        destination_hash, destination_files, destination_bytes = (
            finalizer.tree_hash(holdout_tasks / task_id)
        )
        if (
            source_hash,
            source_files,
            source_bytes,
        ) != (
            destination_hash,
            destination_files,
            destination_bytes,
        ):
            rollback(holdout_tasks, backup_root, replaced)
            raise RuntimeError(f"installed copy mismatch: {task_id}")
        records.append(
            {
                "task_id": task_id,
                "source_tree_sha256": source_hash,
                "destination_tree_sha256": destination_hash,
                "file_count": destination_files,
                "total_bytes": destination_bytes,
                "hidden_scenarios_match": (
                    hidden_scenarios(holdout_tasks / task_id)
                    == hidden_scenarios(full_tasks / task_id)
                ),
            }
        )

    report_path = args.report or holdout_root / "v3_sync_report.json"
    report = {
        "schema": "swr-holdout100-v3-variant-sync-v1",
        "state": "installed_pending_validation",
        "created_at": utc_now(),
        "holdout_root": str(holdout_root),
        "full_root": str(full_root),
        "full_benchmark_manifest_sha256": sha256_file(
            full_root / "benchmark_manifest.jsonl"
        ),
        "benchmark_manifest_sha256": sha256_file(manifest_path),
        "selected_task_count": len(ids),
        "updated_task_count": len(changed),
        "updated_task_ids": changed,
        "backup_root": str(backup_root),
        "records": records,
    }
    write_json_atomic(report_path, report)
    write_json_atomic(
        holdout_root / "STATUS.json",
        {
            "state": "v3_sync_installed_pending_validation",
            "updated_at": utc_now(),
            "task_count": len(manifest),
            "updated_task_count": len(changed),
            "sync_report": str(report_path),
        },
    )
    repair_report_path = holdout_root / "repair_report.json"
    repair_report = load_json(repair_report_path)
    repair_report["state"] = "v3_sync_installed_pending_validation"
    repair_report["v3_sync_report"] = str(report_path)
    write_json_atomic(repair_report_path, repair_report)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
