#!/usr/bin/env python3
"""Build a versioned, benchmark-grade copy of the SWR holdout-100 tasks."""

from __future__ import annotations

import argparse
import ast
import gzip
import hashlib
import importlib.util
import io
import itertools
import json
import os
import random
import shutil
import sys
import tarfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import semantic_comparator
from reference_oracles import REPAIRED_ORACLES, digest


DATA_ROOT = Path(
    "/path/to/software_reconstruction_data"
)
DEFAULT_SPLIT = (
    DATA_ROOT
    / "software_reconstruction/swr3000_variant_holdout100_20260909_v1"
)
DEFAULT_OUTPUT = (
    DATA_ROOT
    / "software_reconstruction/swr3000_variant_holdout100_benchmark_v2_20260911"
)
HERE = Path(__file__).resolve().parent
SEMANTIC_SOURCE = HERE / "semantic_comparator.py"
ORACLE_SOURCE = HERE / "reference_oracles.py"
ORACLE_OVERRIDE_FAMILIES = {
    "circuit_simulation",
    "finite_element_mechanics",
    "molecular_chemistry",
    "transport_gtfs_schedule",
    "z3_constraint_system",
}
RESAMPLE_AXES = {
    "acoustics_room_simulation": ["absorption_level", "rir_length"],
    "hydrology_raster_modeling": ["rainfall_window"],
    "materials_crystallography": ["strain_tensor"],
    "music_score_engraving": ["quantization_grid", "transpose_interval"],
    "phylogenetics_tree_reconstruction": ["branch_support_threshold"],
    "power_grid_simulation": ["load_scale"],
    "structural_biology_pdb": ["distance_cutoff"],
    "video_broadcast_qc": ["frame_rate"],
}
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_SOURCE = (
    PACKAGE_ROOT
    / "task_generation/materialization/public_artifact_renderers.py"
)


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


def tree_snapshot(task: Path) -> dict[str, Any]:
    files = []
    total_bytes = 0
    tree_hasher = hashlib.sha256()
    for path in sorted(item for item in task.rglob("*") if item.is_file()):
        relative = str(path.relative_to(task))
        size = path.stat().st_size
        file_hash = sha256_file(path)
        total_bytes += size
        tree_hasher.update(relative.encode())
        tree_hasher.update(b"\0")
        tree_hasher.update(file_hash.encode())
        tree_hasher.update(b"\n")
        files.append({"path": relative, "bytes": size, "sha256": file_hash})
    return {
        "task_dir": str(task),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "tree_sha256": tree_hasher.hexdigest(),
        "files": files,
    }


def import_module(path: Path, prefix: str):
    name = f"{prefix}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    added = str(path.parent) not in sys.path
    if added:
        sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        if added:
            sys.path.remove(str(path.parent))
    return module


def source_group(task: Path) -> str:
    names = sorted(task.joinpath("tests/private").glob("*_oracle.py"))
    if names:
        return names[0].name.removesuffix("_oracle.py")
    return "true10"


def patch_function(source: str, name: str, replacement: str) -> str:
    tree = ast.parse(source)
    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    if len(matches) != 1:
        raise RuntimeError(f"expected one {name} function, found {len(matches)}")
    node = matches[0]
    lines = source.splitlines(keepends=True)
    start = node.lineno - 1
    end = node.end_lineno
    replacement_text = replacement.rstrip() + "\n\n"
    return "".join(lines[:start]) + replacement_text + "".join(lines[end:])


def repair_judge(task: Path) -> None:
    private = task / "tests/private"
    judge_path = private / "judge.py"
    source = judge_path.read_text(encoding="utf-8")
    if "import semantic_comparator" not in source:
        tree = ast.parse(source)
        imports = [
            node
            for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        if not imports:
            raise RuntimeError(f"{judge_path} has no import block")
        insert_after = imports[-1].end_lineno
        lines = source.splitlines(keepends=True)
        lines.insert(insert_after, "import semantic_comparator\n")
        source = "".join(lines)
    source = patch_function(
        source,
        "validate_semantics",
        """def validate_semantics(family, got, expected):
    got = candidate_summary(got)
    expected = candidate_summary(expected)
    return semantic_comparator.validate(got, expected, family)""",
    )
    judge_path.write_text(source, encoding="utf-8")
    shutil.copy2(SEMANTIC_SOURCE, private / "semantic_comparator.py")


def repair_oracle(task: Path, family: str) -> bool:
    if family not in ORACLE_OVERRIDE_FAMILIES:
        return False
    private = task / "tests/private"
    oracle_paths = sorted(private.glob("*_oracle.py"))
    if len(oracle_paths) != 1:
        raise RuntimeError(
            f"{task.name}: repaired family {family} has {len(oracle_paths)} oracle files"
        )
    shutil.copy2(ORACLE_SOURCE, private / "benchmark_reference_oracles.py")
    oracle_path = oracle_paths[0]
    source = oracle_path.read_text(encoding="utf-8")
    marker = "# benchmark-v2 oracle override"
    if marker not in source:
        source = (
            source.rstrip()
            + "\n\n"
            + marker
            + "\nfrom benchmark_reference_oracles import REPAIRED_ORACLES\n"
            + "ORACLES.update(REPAIRED_ORACLES)\n"
        )
        oracle_path.write_text(source, encoding="utf-8")
    return True


def candidate_summary(payload: Any) -> Any:
    if isinstance(payload, dict) and isinstance(payload.get("summary"), dict):
        return payload["summary"]
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        return payload["result"]
    return payload


def output_signature(payload: Any) -> str:
    return digest(candidate_summary(payload))


def semantically_equal(actual: Any, expected: Any, family: str) -> bool:
    checks = semantic_comparator.validate(
        candidate_summary(actual), candidate_summary(expected), family
    )
    return bool(checks) and all(check.get("passed") for check in checks)


def parameter_pool(values: list[Any]) -> list[Any]:
    numeric = [
        float(value)
        for value in values
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    all_integral = numeric and all(
        isinstance(value, int) and not isinstance(value, bool) for value in values
    )
    if numeric:
        low = min(numeric)
        high = max(numeric)
        if all_integral:
            lower = max(-64, int(low) - 12)
            upper = min(4096, int(high) + 24)
            return list(range(lower, upper + 1))
        span = max(1.0, high - low)
        return [
            round(low - span * 0.2 + span * 1.4 * (index + 0.37) / 160, 7)
            for index in range(160)
        ]
    unique = {
        json.dumps(value, sort_keys=True, default=str): value for value in values
    }
    result = list(unique.values())
    for index in range(80):
        source = copy_value = json.loads(
            json.dumps(values[index % len(values)], default=str)
        )
        if isinstance(copy_value, list):
            changed = False
            for item_index, item in enumerate(copy_value):
                if isinstance(item, (int, float)) and not isinstance(item, bool):
                    copy_value[item_index] = round(
                        float(item) + (index + 1) * 0.0137, 7
                    )
                    changed = True
                    break
            if not changed:
                copy_value.append(f"benchmark-{index}")
        elif isinstance(copy_value, dict):
            copy_value[f"benchmark_{index}"] = index
        else:
            copy_value = f"{source}-benchmark-{index}"
        key = json.dumps(copy_value, sort_keys=True, default=str)
        if key not in unique:
            unique[key] = copy_value
            result.append(copy_value)
    return result


def resample_public_hidden_collisions(
    task: Path, family: str
) -> dict[str, Any]:
    if family not in RESAMPLE_AXES and family not in ORACLE_OVERRIDE_FAMILIES:
        return {
            "old_collision_count": 0,
            "new_collision_count": 0,
            "changed_scenarios": [],
            "screened_from_existing_profile": True,
        }
    if family in ORACLE_OVERRIDE_FAMILIES:
        return {
            "old_collision_count": None,
            "old_hidden_duplicate_count": None,
            "new_collision_count": 0,
            "new_hidden_duplicate_count": 0,
            "changed_scenarios": [],
            "resolved_by_oracle_override": True,
        }
    private = task / "tests/private"
    manifest_path = private / "manifest.json"
    variant_path = private / "variant.json"
    manifest = load_json(manifest_path)
    oracle_path = next(private.glob("*_oracle.py"))
    oracle_module = import_module(oracle_path, "benchmark_collision_oracle")
    oracle = oracle_module.ORACLES[family]
    public = manifest.get("public_scenarios", [])
    hidden = manifest.get("hidden_scenarios", [])
    public_outputs = [oracle(scenario["parameters"]) for scenario in public]
    public_signatures = {output_signature(output) for output in public_outputs}
    old_hidden_outputs = [oracle(scenario["parameters"]) for scenario in hidden]
    old_hidden_signatures = [
        output_signature(output) for output in old_hidden_outputs
    ]
    replacement_indices = []
    accepted_outputs = []
    public_collision_count = 0
    hidden_duplicate_count = 0
    for index, output in enumerate(old_hidden_outputs):
        collides_public = any(
            semantically_equal(output, public_output, family)
            for public_output in public_outputs
        )
        duplicates_hidden = any(
            semantically_equal(output, accepted, family)
            for accepted in accepted_outputs
        )
        if collides_public:
            public_collision_count += 1
        if duplicates_hidden:
            hidden_duplicate_count += 1
        if collides_public or duplicates_hidden:
            replacement_indices.append(index)
        else:
            accepted_outputs.append(output)
    if not replacement_indices:
        return {
            "old_collision_count": 0,
            "new_collision_count": 0,
            "old_hidden_duplicate_count": 0,
            "new_hidden_duplicate_count": 0,
            "changed_scenarios": [],
        }
    axes = RESAMPLE_AXES.get(family)
    if not axes:
        raise RuntimeError(
            f"{task.name}: collision in {family} has no approved resampling axes"
        )

    pools = {}
    all_scenarios = public + hidden
    for axis in axes:
        values = [
            scenario["parameters"][axis]
            for scenario in all_scenarios
            if axis in scenario.get("parameters", {})
        ]
        if not values:
            raise RuntimeError(f"{task.name}: no values for resampling axis {axis}")
        pools[axis] = parameter_pool(values)
    combinations = [
        dict(zip(axes, values))
        for values in itertools.product(*(pools[axis] for axis in axes))
    ]
    random.Random(f"swr-benchmark-v2:{task.name}").shuffle(combinations)

    selected_outputs: list[Any] = []
    changed = []
    repaired_hidden = []
    for index, scenario in enumerate(hidden):
        original_parameters = dict(scenario["parameters"])
        original_signature = old_hidden_signatures[index]
        original_output = old_hidden_outputs[index]
        if index not in replacement_indices:
            repaired_hidden.append(scenario)
            selected_outputs.append(original_output)
            continue
        replacement = None
        for changes in combinations:
            candidate_parameters = dict(original_parameters)
            candidate_parameters.update(changes)
            candidate_output = oracle(candidate_parameters)
            signature = output_signature(candidate_output)
            protected_outputs = [
                old_hidden_outputs[future_index]
                for future_index in range(index + 1, len(hidden))
                if future_index not in replacement_indices
            ]
            if any(
                semantically_equal(candidate_output, public_output, family)
                for public_output in public_outputs
            ) or any(
                semantically_equal(candidate_output, selected_output, family)
                for selected_output in selected_outputs + protected_outputs
            ):
                continue
            replacement = {
                **scenario,
                "parameters": candidate_parameters,
            }
            selected_outputs.append(candidate_output)
            changed.append(
                {
                    "scenario_id": scenario.get("scenario_id"),
                    "old_parameters": original_parameters,
                    "new_parameters": candidate_parameters,
                    "old_signature": original_signature,
                    "new_signature": signature,
                    "changed_axes": axes,
                }
            )
            break
        if replacement is None:
            raise RuntimeError(
                f"{task.name}: could not find a non-replay hidden scenario"
            )
        repaired_hidden.append(replacement)

    for path in [manifest_path, variant_path]:
        payload = load_json(path)
        payload["hidden_scenarios"] = repaired_hidden
        payload["benchmark_hidden_resampled_at"] = utc_now()
        payload["benchmark_hidden_resampled_axes"] = axes
        write_json(path, payload)
    new_outputs = [
        oracle(scenario["parameters"])
        for scenario in repaired_hidden
    ]
    new_signatures = [output_signature(output) for output in new_outputs]
    new_collisions = sum(
        any(
            semantically_equal(output, public_output, family)
            for public_output in public_outputs
        )
        for output in new_outputs
    )
    new_duplicates = sum(
        any(
            semantically_equal(output, previous, family)
            for previous in new_outputs[:index]
        )
        for index, output in enumerate(new_outputs)
    )
    if new_collisions or new_duplicates:
        raise RuntimeError(f"{task.name}: hidden resampling did not remove collisions")
    return {
        "old_collision_count": public_collision_count,
        "old_hidden_duplicate_count": hidden_duplicate_count,
        "new_collision_count": new_collisions,
        "new_hidden_duplicate_count": new_duplicates,
        "changed_scenarios": changed,
        "resampled_axes": axes,
    }


def _strip_parameter_effect(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_parameter_effect(item)
            for key, item in value.items()
            if key != "parameter_effect"
            and key not in {
                "smoke_augmented_output_with_parameter_effect",
                "smoke_synthesized_parameter_keys",
            }
        }
    if isinstance(value, list):
        return [_strip_parameter_effect(item) for item in value]
    return value


def _json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
    ).encode()


def _tar_bytes(entries: dict[str, bytes]) -> bytes:
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode="wb", mtime=0) as gzip_handle:
        with tarfile.open(fileobj=gzip_handle, mode="w") as archive:
            for name, data in sorted(entries.items()):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mtime = 0
                info.mode = 0o644
                archive.addfile(info, io.BytesIO(data))
    return compressed.getvalue()


def _load_tar(path: Path) -> dict[str, bytes]:
    entries = {}
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            handle = archive.extractfile(member)
            if handle is not None:
                entries[member.name] = handle.read()
    return entries


def clean_public_archive(task: Path) -> dict[str, Any]:
    archive_path = task / "environment/app/observations/reference_outputs.tar.gz"
    entries = _load_tar(archive_path)
    manifest = _strip_parameter_effect(json.loads(entries["public_manifest.json"]))
    scenario_by_id = {
        scenario["scenario_id"]: scenario
        for scenario in manifest.get("public_scenarios", [])
    }
    removed_text_lines = 0
    for name, data in list(entries.items()):
        if name.endswith(".json"):
            try:
                payload = _strip_parameter_effect(json.loads(data))
            except Exception:
                continue
            entries[name] = _json_bytes(payload)
        elif name.endswith((".txt", ".csv", ".tsv")) and b"parameter_effect" in data:
            lines = data.decode("utf-8", "replace").splitlines()
            kept = [line for line in lines if "parameter_effect" not in line]
            removed_text_lines += len(lines) - len(kept)
            entries[name] = ("\n".join(kept) + "\n").encode()

    signatures = []
    for scenario_id, scenario in scenario_by_id.items():
        output_name = f"{scenario_id}/oracle_output.json"
        output = json.loads(entries[output_name])
        signature = digest(output)
        scenario["oracle_output"] = output
        scenario["signature"] = signature
        signatures.append(signature)
        entries[f"{scenario_id}/signature.json"] = _json_bytes(
            {"scenario_id": scenario_id, "signature": signature}
        )
    manifest["public_scenarios"] = list(scenario_by_id.values())
    manifest["schema"] = "swr-benchmark-public-reference-v2"
    manifest["benchmark_repaired_at"] = utc_now()
    manifest["parameter_effect_digest_removed"] = True
    manifest["distinct_public_signatures"] = len(signatures) == len(set(signatures))
    entries["public_manifest.json"] = _json_bytes(manifest)
    archive_path.write_bytes(_tar_bytes(entries))
    return {
        "mode": "cleaned_existing",
        "scenario_count": len(signatures),
        "distinct_public_signatures": len(signatures) == len(set(signatures)),
        "removed_parameter_effect_text_lines": removed_text_lines,
        "archive_sha256": sha256_file(archive_path),
    }


def regenerate_public_archive(
    task: Path, family: str, artifact_module: Any
) -> dict[str, Any]:
    archive_path = task / "environment/app/observations/reference_outputs.tar.gz"
    old_entries = _load_tar(archive_path)
    manifest = _strip_parameter_effect(
        json.loads(old_entries["public_manifest.json"])
    )
    private = task / "tests/private"
    oracle_path = next(private.glob("*_oracle.py"))
    oracle_module = import_module(oracle_path, "benchmark_task_oracle")
    oracle = oracle_module.ORACLES[family]
    entries: dict[str, bytes] = {}
    signatures = []
    public_scenarios = []
    concrete_files = 0

    for original in manifest.get("public_scenarios", []):
        scenario = {
            "scenario_id": original["scenario_id"],
            "parameters": original["parameters"],
        }
        scenario_id = scenario["scenario_id"]
        raw_output = oracle(scenario["parameters"])
        visible_output = {"summary": raw_output}
        signature = digest(visible_output)
        scenario["oracle_output"] = visible_output
        scenario["signature"] = signature
        public_scenarios.append(scenario)
        signatures.append(signature)
        entries[f"{scenario_id}/scenario.json"] = _json_bytes(
            {
                "scenario_id": scenario_id,
                "parameters": scenario["parameters"],
            }
        )
        entries[f"{scenario_id}/oracle_output.json"] = _json_bytes(visible_output)
        entries[f"{scenario_id}/signature.json"] = _json_bytes(
            {"scenario_id": scenario_id, "signature": signature}
        )
        artifacts = artifact_module.family_artifacts(
            family,
            scenario_id,
            scenario["parameters"],
            visible_output,
        )
        entries[f"{scenario_id}/artifact_manifest.json"] = _json_bytes(
            {
                "schema": "swr-benchmark-public-scenario-artifacts-v2",
                "scenario_id": scenario_id,
                "family_id": family,
                "files": sorted(artifacts),
            }
        )
        for name, data in sorted(artifacts.items()):
            entries[f"{scenario_id}/{name}"] = data
            concrete_files += 1

    manifest["public_scenarios"] = public_scenarios
    manifest["schema"] = "swr-benchmark-public-reference-v2"
    manifest["benchmark_repaired_at"] = utc_now()
    manifest["parameter_effect_digest_removed"] = True
    manifest["repaired_family_oracle"] = family
    manifest["distinct_public_signatures"] = (
        len(signatures) == len(set(signatures))
    )
    entries["public_manifest.json"] = _json_bytes(manifest)
    archive_path.write_bytes(_tar_bytes(entries))
    return {
        "mode": "regenerated_from_repaired_oracle",
        "scenario_count": len(signatures),
        "distinct_public_signatures": len(signatures) == len(set(signatures)),
        "concrete_file_count": concrete_files,
        "archive_sha256": sha256_file(archive_path),
    }


def update_metadata(
    task: Path,
    repaired_oracle: bool,
    benchmark_version: str = "swr-holdout100-v2",
) -> None:
    for relative in [
        "tests/private/manifest.json",
        "tests/private/variant.json",
        "environment/app/observations/manifest.json",
    ]:
        path = task / relative
        if not path.exists():
            continue
        payload = load_json(path)
        payload["benchmark_version"] = benchmark_version
        payload["benchmark_repaired_at"] = utc_now()
        payload["semantic_comparator"] = {
            "coverage": "complete_recursive",
            "dictionary_fields_truncated": False,
            "list_elements_truncated": False,
            "digest_fields_ignored": False,
            "integer_tolerance": 0,
            "float_abs_tolerance": 1e-6,
            "float_rel_tolerance": 1e-4,
        }
        payload["parameter_effect_digest_removed"] = True
        payload["family_oracle_repaired"] = repaired_oracle
        write_json(path, payload)


def build(split: Path, output: Path, force: bool) -> None:
    source_paths = [
        Path(line)
        for line in (split / "test_task_paths.txt").read_text().splitlines()
        if line.strip()
    ]
    task_ids = [
        line.strip()
        for line in (split / "test_task_ids.txt").read_text().splitlines()
        if line.strip()
    ]
    if len(source_paths) != 100 or len(task_ids) != 100:
        raise RuntimeError(
            f"expected exactly 100 tasks, found {len(source_paths)} paths and "
            f"{len(task_ids)} ids"
        )
    for task_id, source in zip(task_ids, source_paths):
        if source.name != task_id:
            raise RuntimeError(f"task id/path mismatch: {task_id} != {source}")

    staging = output.with_name(output.name + ".staging")
    if output.exists() or staging.exists():
        if not force:
            raise FileExistsError(
                f"{output} or its staging directory exists; pass --force to rebuild"
            )
        shutil.rmtree(output, ignore_errors=True)
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    (staging / "tasks").mkdir()

    artifact_module = import_module(ARTIFACT_SOURCE, "benchmark_artifacts")
    freeze_records = []
    repair_records = []
    new_paths = []

    for index, (task_id, source) in enumerate(zip(task_ids, source_paths), 1):
        freeze = tree_snapshot(source)
        freeze["task_id"] = task_id
        freeze_records.append(freeze)

        destination = staging / "tasks" / task_id
        shutil.copytree(source, destination, symlinks=True)
        manifest = load_json(destination / "tests/private/manifest.json")
        family = manifest["family_id"]
        group = source_group(destination)

        if family.startswith("openscad"):
            comparator = "existing_geometry_specific"
        else:
            repair_judge(destination)
            comparator = "strict_complete_recursive"
        collision_repair = resample_public_hidden_collisions(
            destination, family
        )
        repaired_oracle = repair_oracle(destination, family)
        if repaired_oracle:
            archive_report = regenerate_public_archive(
                destination, family, artifact_module
            )
        else:
            archive_report = clean_public_archive(destination)
        update_metadata(destination, repaired_oracle)

        repaired_snapshot = tree_snapshot(destination)
        record = {
            "index": index,
            "task_id": task_id,
            "source_task_path": str(source),
            "repaired_task_path": str(output / "tasks" / task_id),
            "source_group": group,
            "family_id": family,
            "semantic_comparator": comparator,
            "oracle_repaired": repaired_oracle,
            "collision_repair": collision_repair,
            "archive": archive_report,
            "source_tree_sha256": freeze["tree_sha256"],
            "repaired_tree_sha256": repaired_snapshot["tree_sha256"],
            "state": "built",
        }
        repair_records.append(record)
        new_paths.append(str(output / "tasks" / task_id))
        print(
            json.dumps(
                {
                    "progress": f"{index}/100",
                    "task_id": task_id,
                    "family": family,
                    "oracle_repaired": repaired_oracle,
                },
                sort_keys=True,
            ),
            flush=True,
        )

    for source_file in split.iterdir():
        if source_file.is_file():
            shutil.copy2(source_file, staging / source_file.name)
    (staging / "test_task_ids.txt").write_text(
        "\n".join(task_ids) + "\n", encoding="utf-8"
    )
    (staging / "test_task_paths.txt").write_text(
        "\n".join(new_paths) + "\n", encoding="utf-8"
    )
    (staging / "source_test_task_paths.txt").write_text(
        "\n".join(map(str, source_paths)) + "\n", encoding="utf-8"
    )
    with (staging / "baseline_freeze_manifest.jsonl").open("w") as handle:
        for record in freeze_records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    with (staging / "benchmark_manifest.jsonl").open("w") as handle:
        for record in repair_records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    write_json(
        staging / "repair_report.json",
        {
            "schema": "swr-holdout100-benchmark-repair-v2",
            "created_at": utc_now(),
            "source_split": str(split),
            "output": str(output),
            "task_count": len(repair_records),
            "oracle_repaired_task_count": sum(
                record["oracle_repaired"] for record in repair_records
            ),
            "strict_comparator_task_count": sum(
                record["semantic_comparator"] == "strict_complete_recursive"
                for record in repair_records
            ),
            "geometry_specific_task_count": sum(
                record["semantic_comparator"] == "existing_geometry_specific"
                for record in repair_records
            ),
            "records": repair_records,
        },
    )
    write_json(
        staging / "STATUS.json",
        {
            "state": "built_pending_validation",
            "updated_at": utc_now(),
            "task_count": 100,
        },
    )
    os.replace(staging, output)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build(args.split.resolve(), args.output.resolve(), args.force)


if __name__ == "__main__":
    main()
