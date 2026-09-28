#!/usr/bin/env python3
"""Static, oracle, and adversarial audit for the repaired SWR benchmark."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
import tarfile
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import semantic_comparator


DATA_ROOT = Path(
    "/path/to/software_reconstruction_data"
)
DEFAULT_ROOT = (
    DATA_ROOT
    / "software_reconstruction/swr3000_variant_holdout100_benchmark_v2_20260911"
)
REQUIRED_PATHS = [
    "environment/Dockerfile",
    "environment/app/observations/manifest.json",
    "environment/app/observations/reference_outputs.tar.gz",
    "tests/private/judge.py",
    "tests/private/manifest.json",
    "tests/private/variant.json",
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


def candidate_summary(payload: Any) -> Any:
    if isinstance(payload, dict) and isinstance(payload.get("summary"), dict):
        return payload["summary"]
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        return payload["result"]
    return payload


def signature(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            candidate_summary(payload),
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def import_module(path: Path, prefix: str):
    name = f"{prefix}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    added = str(path.parent) not in sys.path
    if added:
        sys.path.insert(0, str(path.parent))
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
        if added:
            sys.path.remove(str(path.parent))
    return module


def public_payload(task: Path) -> tuple[dict[str, Any], bytes, list[str]]:
    archive_path = task / "environment/app/observations/reference_outputs.tar.gz"
    decompressed_bytes = bytearray()
    with tarfile.open(archive_path, "r:gz") as archive:
        names = [member.name for member in archive.getmembers() if member.isfile()]
        for member in archive.getmembers():
            if not member.isfile():
                continue
            member_handle = archive.extractfile(member)
            if member_handle is not None:
                decompressed_bytes.extend(member_handle.read())
        handle = archive.extractfile("public_manifest.json")
        if handle is None:
            raise RuntimeError("public_manifest.json missing")
        payload = json.loads(handle.read())
    return payload, bytes(decompressed_bytes), names


def passed(actual: Any, expected: Any, family: str) -> bool:
    checks = semantic_comparator.validate(
        candidate_summary(actual), candidate_summary(expected), family
    )
    return bool(checks) and all(check.get("passed") for check in checks)


def schema(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            "type": "object",
            "fields": {key: schema(item) for key, item in sorted(value.items())},
        }
    if isinstance(value, (list, tuple)):
        item_schemas = {
            json.dumps(schema(item), sort_keys=True) for item in value
        }
        return {
            "type": "array",
            "item_types": sorted(item_schemas),
        }
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if value is None:
        return "null"
    return type(value).__name__


def remove_one_field(value: Any) -> tuple[Any, bool]:
    if isinstance(value, dict) and value:
        result = copy.deepcopy(value)
        del result[sorted(result)[0]]
        return result, True
    return value, False


def truncate_one_list(value: Any) -> tuple[Any, bool]:
    if isinstance(value, list) and value:
        return copy.deepcopy(value[:-1]), True
    if isinstance(value, dict):
        for key in sorted(value):
            changed, ok = truncate_one_list(value[key])
            if ok:
                result = copy.deepcopy(value)
                result[key] = changed
                return result, True
    if isinstance(value, list):
        for index, item in enumerate(value):
            changed, ok = truncate_one_list(item)
            if ok:
                result = copy.deepcopy(value)
                result[index] = changed
                return result, True
    return value, False


def mutate_one_number(value: Any) -> tuple[Any, bool]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        delta = max(2.0, abs(float(value)) * 0.5)
        return float(value) + delta, True
    if isinstance(value, dict):
        for key in sorted(value):
            changed, ok = mutate_one_number(value[key])
            if ok:
                result = copy.deepcopy(value)
                result[key] = changed
                return result, True
    if isinstance(value, list):
        for index, item in enumerate(value):
            changed, ok = mutate_one_number(item)
            if ok:
                result = copy.deepcopy(value)
                result[index] = changed
                return result, True
    return value, False


def mutate_one_digest(value: Any) -> tuple[Any, bool]:
    if isinstance(value, dict):
        for key in sorted(value):
            lowered = key.lower()
            item = value[key]
            if isinstance(item, str) and (
                "digest" in lowered
                or "hash" in lowered
                or "signature" in lowered
                or "merkle" in lowered
                or "attestation" in lowered
            ):
                result = copy.deepcopy(value)
                result[key] = ("0" if not item.startswith("0") else "1") + item[1:]
                return result, True
            changed, ok = mutate_one_digest(item)
            if ok:
                result = copy.deepcopy(value)
                result[key] = changed
                return result, True
    if isinstance(value, list):
        for index, item in enumerate(value):
            changed, ok = mutate_one_digest(item)
            if ok:
                result = copy.deepcopy(value)
                result[index] = changed
                return result, True
    return value, False


def global_comparator_self_test() -> dict[str, bool]:
    expected_object = {f"field_{index:02d}": index for index in range(25)}
    wrong_object = dict(expected_object)
    wrong_object["field_24"] = -1
    expected_list = list(range(12))
    wrong_list = list(expected_list)
    wrong_list[10] = -1
    return {
        "checks_field_after_20": not passed(
            wrong_object, expected_object, "self_test"
        ),
        "checks_list_item_after_8": not passed(
            wrong_list, expected_list, "self_test"
        ),
        "checks_digest_strings": not passed(
            {"digest": "b" * 64},
            {"digest": "a" * 64},
            "self_test",
        ),
        "rejects_25_percent_numeric_error": not passed(
            {"value": 124.0}, {"value": 100.0}, "self_test"
        ),
    }


def audit_task(task: Path, repeat: int) -> dict[str, Any]:
    started = time.monotonic()
    manifest = load_json(task / "tests/private/manifest.json")
    variant = load_json(task / "tests/private/variant.json")
    family = manifest["family_id"]
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {}

    missing_paths = [
        relative for relative in REQUIRED_PATHS if not (task / relative).is_file()
    ]
    checks["package_complete"] = not missing_paths
    details["missing_paths"] = missing_paths

    judge_path = task / "tests/private/judge.py"
    try:
        compile(judge_path.read_text(encoding="utf-8"), str(judge_path), "exec")
        checks["judge_compiles"] = True
    except Exception as error:
        checks["judge_compiles"] = False
        details["judge_compile_error"] = f"{type(error).__name__}: {error}"
    judge_source = judge_path.read_text(encoding="utf-8")
    if family.startswith("openscad"):
        checks["benchmark_comparator_installed"] = (
            "geometry_signature" in judge_source
        )
    else:
        checks["benchmark_comparator_installed"] = (
            "import semantic_comparator" in judge_source
            and "return semantic_comparator.validate" in judge_source
        )

    payload, archive_content, archive_names = public_payload(task)
    public = payload.get("public_scenarios", [])
    hidden = manifest.get("hidden_scenarios", [])
    checks["public_scenarios_present"] = len(public) >= 2
    checks["hidden_scenarios_present"] = len(hidden) >= 2
    checks["public_parameters_match_manifest"] = [
        scenario.get("parameters") for scenario in public
    ] == [
        scenario.get("parameters")
        for scenario in manifest.get("public_scenarios", [])
    ]
    checks["parameter_effect_digest_absent"] = (
        b'"parameter_effect"' not in archive_content
        and b"parameter_effect." not in archive_content
    )
    concrete_names = [
        name
        for name in archive_names
        if Path(name).name
        not in {
            "public_manifest.json",
            "scenario.json",
            "oracle_output.json",
            "signature.json",
            "artifact_manifest.json",
        }
    ]
    checks["concrete_public_artifacts_present"] = bool(concrete_names)
    details["concrete_public_file_count"] = len(concrete_names)

    oracle_paths = sorted(task.joinpath("tests/private").glob("*_oracle.py"))
    checks["exactly_one_private_oracle"] = len(oracle_paths) == 1
    if len(oracle_paths) != 1:
        return {
            "task_id": task.name,
            "family_id": family,
            "passed": False,
            "checks": checks,
            "details": details,
        }
    try:
        oracle_module = import_module(oracle_paths[0], "benchmark_audit_oracle")
        oracle = oracle_module.ORACLES[family]
        checks["oracle_registered"] = True
    except Exception as error:
        checks["oracle_registered"] = False
        details["oracle_import_error"] = f"{type(error).__name__}: {error}"
        return {
            "task_id": task.name,
            "family_id": family,
            "passed": False,
            "checks": checks,
            "details": details,
        }

    try:
        public_expected = [
            candidate_summary(oracle(scenario["parameters"]))
            for scenario in public
        ]
        hidden_expected = [
            candidate_summary(oracle(scenario["parameters"]))
            for scenario in hidden
        ]
        checks["oracle_executes_all_scenarios"] = True
    except Exception as error:
        checks["oracle_executes_all_scenarios"] = False
        details["oracle_execution_error"] = f"{type(error).__name__}: {error}"
        details["runtime_validation_required"] = True
        return {
            "task_id": task.name,
            "family_id": family,
            "passed": False,
            "checks": checks,
            "details": details,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }

    visible_public = [
        candidate_summary(scenario.get("oracle_output")) for scenario in public
    ]
    public_match = [
        passed(actual, expected, family)
        for actual, expected in zip(visible_public, public_expected)
    ]
    checks["public_outputs_match_oracle"] = all(public_match)
    details["public_oracle_match_count"] = sum(public_match)

    stable = True
    repeat_signatures = []
    try:
        for scenario in hidden:
            signatures = [
                signature(oracle(scenario["parameters"])) for _ in range(repeat)
            ]
            repeat_signatures.append(signatures)
            stable = stable and len(set(signatures)) == 1
    except Exception as error:
        stable = False
        details["oracle_repeat_error"] = f"{type(error).__name__}: {error}"
    checks["oracle_deterministic"] = stable
    details["oracle_repeat_count"] = repeat

    public_signatures = {signature(output) for output in public_expected}
    hidden_signatures = [signature(output) for output in hidden_expected]
    replay_ids = [
        hidden[index].get("scenario_id")
        for index, item_signature in enumerate(hidden_signatures)
        if item_signature in public_signatures
    ]
    checks["no_public_hidden_output_collision"] = not replay_ids
    checks["hidden_outputs_distinct"] = len(set(hidden_signatures)) == len(
        hidden_signatures
    )
    details["public_hidden_replay_scenarios"] = replay_ids
    details["public_unique_output_count"] = len(public_signatures)
    details["hidden_unique_output_count"] = len(set(hidden_signatures))

    all_schemas = [schema(output) for output in public_expected + hidden_expected]
    checks["top_level_output_schema_stable"] = all(
        isinstance(output, dict) for output in public_expected + hidden_expected
    ) and len(
        {
            json.dumps(
                {
                    key: value["type"] if isinstance(value, dict) and "type" in value else value
                    for key, value in item.get("fields", {}).items()
                },
                sort_keys=True,
            )
            for item in all_schemas
        }
    ) == 1

    blank_rejections = [
        not passed({}, expected, family) for expected in hidden_expected
    ]
    checks["blank_solution_rejected"] = all(blank_rejections)
    lookup_rejections = [
        all(not passed(public_output, hidden_output, family) for public_output in visible_public)
        for hidden_output in hidden_expected
    ]
    checks["all_public_output_replays_rejected"] = all(lookup_rejections)

    missing_field_rejections = []
    list_truncation_rejections = []
    numeric_mutation_rejections = []
    digest_mutation_rejections = []
    for expected in hidden_expected:
        mutation, applicable = remove_one_field(expected)
        if applicable:
            missing_field_rejections.append(not passed(mutation, expected, family))
        mutation, applicable = truncate_one_list(expected)
        if applicable:
            list_truncation_rejections.append(not passed(mutation, expected, family))
        mutation, applicable = mutate_one_number(expected)
        if applicable:
            numeric_mutation_rejections.append(not passed(mutation, expected, family))
        mutation, applicable = mutate_one_digest(expected)
        if applicable:
            digest_mutation_rejections.append(not passed(mutation, expected, family))
    checks["missing_field_rejected"] = bool(missing_field_rejections) and all(
        missing_field_rejections
    )
    checks["list_truncation_rejected_when_applicable"] = all(
        list_truncation_rejections
    )
    checks["numeric_mutation_rejected_when_applicable"] = all(
        numeric_mutation_rejections
    )
    checks["digest_mutation_rejected_when_applicable"] = all(
        digest_mutation_rejections
    )
    details["list_mutation_scenario_count"] = len(list_truncation_rejections)
    details["numeric_mutation_scenario_count"] = len(numeric_mutation_rejections)
    details["digest_mutation_scenario_count"] = len(digest_mutation_rejections)

    axes = variant.get("axes_to_vary", [])
    checks["parameter_axes_present"] = len(axes) >= 3
    scenario_keys = [
        set(scenario.get("parameters", {}))
        for scenario in manifest.get("public_scenarios", []) + hidden
    ]
    checks["scenario_parameters_cover_axes"] = all(
        set(axes).issubset(keys) for keys in scenario_keys
    )
    checks["logical_task_id_preserved"] = bool(variant.get("task_id"))

    return {
        "task_id": task.name,
        "family_id": family,
        "passed": all(checks.values()),
        "checks": checks,
        "details": details,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def audit(root: Path, repeat: int) -> None:
    task_paths = [
        Path(line)
        for line in (root / "test_task_paths.txt").read_text().splitlines()
        if line.strip()
    ]
    if len(task_paths) != 100:
        raise RuntimeError(f"expected 100 task paths, found {len(task_paths)}")
    validation = root / "validation"
    validation.mkdir(parents=True, exist_ok=True)
    records = []
    with (validation / "static_audit.jsonl").open("w") as handle:
        for index, task in enumerate(task_paths, 1):
            record = audit_task(task, repeat)
            records.append(record)
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
            handle.flush()
            print(
                json.dumps(
                    {
                        "progress": f"{index}/100",
                        "task_id": task.name,
                        "passed": record["passed"],
                        "failed_checks": [
                            key
                            for key, value in record["checks"].items()
                            if not value
                        ],
                    },
                    sort_keys=True,
                ),
                flush=True,
            )

    comparator_self_test = global_comparator_self_test()
    state_counts = Counter(
        "passed" if record["passed"] else "failed" for record in records
    )
    failed = [
        {
            "task_id": record["task_id"],
            "family_id": record["family_id"],
            "failed_checks": [
                key for key, value in record["checks"].items() if not value
            ],
            "details": record["details"],
        }
        for record in records
        if not record["passed"]
    ]
    report = {
        "schema": "swr-benchmark-static-oracle-audit-v2",
        "created_at": utc_now(),
        "benchmark_root": str(root),
        "task_count": len(records),
        "oracle_repeat_count": repeat,
        "state_counts": dict(state_counts),
        "passed": not failed and all(comparator_self_test.values()),
        "comparator_self_test": comparator_self_test,
        "failed": failed,
    }
    write_json(validation / "static_audit_summary.json", report)
    write_json(
        root / "STATUS.json",
        {
            "state": (
                "static_validation_passed_pending_runtime"
                if report["passed"]
                else "static_validation_failed"
            ),
            "updated_at": utc_now(),
            "task_count": 100,
            "static_passed_count": state_counts["passed"],
            "static_failed_count": state_counts["failed"],
        },
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--repeat", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    audit(args.root.resolve(), max(2, args.repeat))


if __name__ == "__main__":
    main()
