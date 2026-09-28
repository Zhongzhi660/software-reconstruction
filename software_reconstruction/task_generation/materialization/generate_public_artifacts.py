#!/usr/bin/env python3
"""Build agent-visible public reference artifacts for the 2400 planned tasks.

The hidden judges already contain deterministic family oracles. This script
uses those same oracles on public scenarios only, then writes
environment/app/observations/reference_outputs.tar.gz for each task.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import tarfile
import traceback
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_ROOT = Path("/path/to/software_reconstruction_data")
TASK_ROOT = DATA_ROOT / "software_reconstruction/materialized_planned2400_20260828"
DEFAULT_REPORT = TASK_ROOT / "public_artifact_build_report.json"
GROUPS = ("new10", "offcode6", "offcode20")
SUMMARY_FALLBACKS = {
    ("new10", "samtools_bio_qc"): (
        DATA_ROOT
        / "software_reconstruction/new10family_expansion/daytona_oracle_smoke_samtools_60_20260828/summary.json"
    ),
    ("offcode6", "circuit_simulation"): (
        DATA_ROOT
        / "software_reconstruction/offcode6_expansion/daytona_oracle_smoke_300_20260828/circuit_simulation/summary.json"
    ),
    ("offcode6", "finite_element_mechanics"): (
        DATA_ROOT
        / "software_reconstruction/offcode6_expansion/daytona_oracle_smoke_300_20260828/finite_element_mechanics/summary.json"
    ),
}
_FALLBACK_CACHE: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def add_json(tar: tarfile.TarFile, name: str, payload: Any) -> None:
    data = (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mtime = 0
    info.mode = 0o644
    tar.addfile(info, io.BytesIO(data))


def load_oracle(task: Path, group: str):
    oracle_path = task / "tests/private" / f"{group}_oracle.py"
    module_name = f"public_artifact_{group}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, oracle_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import oracle from {oracle_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_public_payload(task: Path, group: str) -> dict[str, Any]:
    private = task / "tests/private"
    manifest = load_json(private / "manifest.json")
    variant = load_json(private / "variant.json")
    family = manifest["family_id"]
    public = manifest.get("public_scenarios", [])
    if len(public) < 2:
        raise RuntimeError(f"expected at least two public scenarios, got {len(public)}")

    oracle = load_oracle(task, group)
    if family not in oracle.ORACLES:
        raise RuntimeError(f"family {family!r} not registered in {group}_oracle.ORACLES")

    scenarios: list[dict[str, Any]] = []
    signatures: list[str] = []
    for scenario in public:
        output = oracle.ORACLES[family](scenario["parameters"])
        signature = oracle.digest(output)
        signatures.append(signature)
        scenarios.append(
            {
                "scenario_id": scenario["scenario_id"],
                "parameters": scenario["parameters"],
                "oracle_output": output,
                "signature": signature,
            }
        )

    return {
        "schema": "public-reference-outputs-v1",
        "created_at": utc_now(),
        "source_group": group,
        "task_id": variant.get("task_id") or manifest.get("task_id") or task.name,
        "family_id": family,
        "demo_id": manifest.get("demo_id"),
        "distinct_public_signatures": len(set(signatures)) == len(signatures),
        "public_scenarios": scenarios,
    }


def fallback_records(group: str, family: str) -> dict[str, dict[str, Any]]:
    key = (group, family)
    if key not in SUMMARY_FALLBACKS:
        return {}
    if key not in _FALLBACK_CACHE:
        summary = load_json(SUMMARY_FALLBACKS[key])
        _FALLBACK_CACHE[key] = {
            str(record["task_id"]): record
            for record in summary.get("records", [])
            if record.get("state") == "passed"
        }
    return _FALLBACK_CACHE[key]


def build_public_payload_from_summary(task: Path, group: str) -> dict[str, Any]:
    private = task / "tests/private"
    manifest = load_json(private / "manifest.json")
    variant = load_json(private / "variant.json")
    family = manifest["family_id"]
    task_id = str(variant.get("task_id") or manifest.get("task_id") or task.name)
    record = fallback_records(group, family).get(task_id)
    if record is None:
        raise RuntimeError(f"no summary fallback record for {group}/{family}/{task_id}")

    public_by_id = {scenario["scenario_id"]: scenario for scenario in manifest.get("public_scenarios", [])}
    scenarios: list[dict[str, Any]] = []
    signatures: list[str] = []
    for scenario_result in record.get("scenario_results", []):
        sid = scenario_result.get("scenario_id")
        if not str(sid).startswith("public_"):
            continue
        if sid not in public_by_id:
            raise RuntimeError(f"summary public scenario {sid!r} not present in task manifest")
        signature = scenario_result["signature"]
        signatures.append(signature)
        scenarios.append(
            {
                "scenario_id": sid,
                "parameters": public_by_id[sid]["parameters"],
                "oracle_output": scenario_result.get("summary"),
                "signature": signature,
                "source": "daytona_smoke_summary_fallback",
            }
        )
    if len(scenarios) < 2:
        raise RuntimeError(f"summary fallback has only {len(scenarios)} public scenarios")
    return {
        "schema": "public-reference-outputs-v1",
        "created_at": utc_now(),
        "source_group": group,
        "task_id": task_id,
        "family_id": family,
        "demo_id": manifest.get("demo_id"),
        "distinct_public_signatures": len(set(signatures)) == len(signatures),
        "public_scenarios": scenarios,
        "source_summary": str(SUMMARY_FALLBACKS[(group, family)]),
    }


def write_reference_tar(task: Path, payload: dict[str, Any]) -> Path:
    obs_dir = task / "environment/app/observations"
    obs_dir.mkdir(parents=True, exist_ok=True)
    tar_path = obs_dir / "reference_outputs.tar.gz"
    tmp_path = obs_dir / f".reference_outputs.{os.getpid()}.tmp"
    with tarfile.open(tmp_path, "w:gz") as tar:
        add_json(tar, "public_manifest.json", payload)
        for scenario in payload["public_scenarios"]:
            sid = scenario["scenario_id"]
            add_json(tar, f"{sid}/scenario.json", {"scenario_id": sid, "parameters": scenario["parameters"]})
            add_json(tar, f"{sid}/oracle_output.json", scenario["oracle_output"])
            add_json(tar, f"{sid}/signature.json", {"scenario_id": sid, "signature": scenario["signature"]})
    tmp_path.replace(tar_path)
    return tar_path


def update_metadata(task: Path, payload: dict[str, Any], tar_path: Path) -> None:
    obs_manifest_path = task / "environment/app/observations/manifest.json"
    obs_manifest = load_json(obs_manifest_path)
    obs_manifest["reference_outputs"] = tar_path.name
    obs_manifest["public_artifact_schema"] = payload["schema"]
    obs_manifest["public_artifact_count"] = len(payload["public_scenarios"])
    obs_manifest["public_artifact_distinct_signatures"] = payload["distinct_public_signatures"]
    write_json(obs_manifest_path, obs_manifest)

    reconstruction_path = task / "reconstruction.json"
    reconstruction = load_json(reconstruction_path)
    reconstruction.setdefault("target_derivation", {})["public_observation_files"] = [
        "environment/app/observations/manifest.json",
        "environment/app/observations/reference_outputs.tar.gz",
    ]
    reconstruction.setdefault("target_derivation", {})["public_artifact_schema"] = payload["schema"]
    reconstruction.setdefault("target_derivation", {})["public_artifact_distinct_signatures"] = payload[
        "distinct_public_signatures"
    ]
    write_json(reconstruction_path, reconstruction)

    derivation_path = task / "tests/private/derivation_report.json"
    if derivation_path.exists():
        derivation = load_json(derivation_path)
        derivation["public_reference_outputs"] = {
            "path": "environment/app/observations/reference_outputs.tar.gz",
            "schema": payload["schema"],
            "public_artifact_count": len(payload["public_scenarios"]),
            "distinct_public_signatures": payload["distinct_public_signatures"],
        }
        write_json(derivation_path, derivation)


def process_task(task: Path, group: str, force: bool) -> dict[str, Any]:
    tar_path = task / "environment/app/observations/reference_outputs.tar.gz"
    if tar_path.exists() and not force:
        return {"task": task.name, "group": group, "state": "skipped_existing", "tar": str(tar_path)}
    try:
        payload = build_public_payload(task, group)
    except (FileNotFoundError, ModuleNotFoundError):
        payload = build_public_payload_from_summary(task, group)
    tar_path = write_reference_tar(task, payload)
    update_metadata(task, payload, tar_path)
    return {
        "task": task.name,
        "group": group,
        "family_id": payload["family_id"],
        "state": "generated",
        "tar": str(tar_path),
        "public_artifact_count": len(payload["public_scenarios"]),
        "distinct_public_signatures": payload["distinct_public_signatures"],
    }


def iter_tasks(groups: list[str], limit: int | None) -> list[tuple[str, Path]]:
    pairs: list[tuple[str, Path]] = []
    for group in groups:
        root = TASK_ROOT / group
        for task in sorted(p for p in root.iterdir() if p.is_dir()):
            pairs.append((group, task))
            if limit is not None and len(pairs) >= limit:
                return pairs
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groups", nargs="+", choices=GROUPS, default=list(GROUPS))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    results: list[dict[str, Any]] = []
    for idx, (group, task) in enumerate(iter_tasks(args.groups, args.limit), 1):
        try:
            result = process_task(task, group, args.force)
        except Exception as exc:  # keep the run resumable across missing deps.
            result = {
                "task": task.name,
                "group": group,
                "state": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback_tail": traceback.format_exc()[-4000:],
            }
        results.append(result)
        if idx % 25 == 0 or result["state"] == "failed":
            counts = Counter(item["state"] for item in results)
            print(f"[{idx}] {dict(counts)} latest={result['state']} {task.name}", flush=True)

    counts = Counter(item["state"] for item in results)
    families = Counter(item.get("family_id", "unknown") for item in results if item.get("family_id"))
    failures = Counter(
        f"{item.get('group')}::{item.get('error_type')}::{item.get('error')}"
        for item in results
        if item["state"] == "failed"
    )
    report = {
        "schema": "public-artifact-build-report-v1",
        "created_at": utc_now(),
        "task_root": str(TASK_ROOT),
        "groups": args.groups,
        "limit": args.limit,
        "force": args.force,
        "state_counts": dict(counts),
        "family_counts": dict(sorted(families.items())),
        "failure_counts": dict(failures.most_common()),
        "results": results,
    }
    write_json(args.report, report)
    print(json.dumps({k: report[k] for k in ["schema", "created_at", "state_counts", "failure_counts"]}, indent=2))
    return 0 if not counts.get("failed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
