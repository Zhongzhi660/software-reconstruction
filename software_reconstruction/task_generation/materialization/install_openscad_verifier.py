#!/usr/bin/env python3
"""Install geometry-aware semantic verification for OpenSCAD tasks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Any

from openscad_metrics import metrics_for_stl


HERE = Path(__file__).resolve().parent
DEFAULT_TASK_ROOT = Path(
    "/path/to/software_reconstruction_data/"
    "true10_family10_semantic_verifier_all600_20260901"
)
DEFAULT_BACKUP_ROOT = Path(
    "/path/to/software_reconstruction_data/"
    "task_source_repairs_20260904/backups_openscad_geometry"
)
MARKER = "## OpenSCAD Geometry Artifact Contract"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def canonical_signature(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if target != root and root not in target.parents:
            raise ValueError(f"unsafe tar member: {member.name}")
    archive.extractall(destination)


def parent_member(archive: tarfile.TarFile, name: str) -> bytes:
    for candidate in (name, f"./{name}"):
        try:
            handle = archive.extractfile(candidate)
        except KeyError:
            handle = None
        if handle is not None:
            return handle.read()
    raise KeyError(f"missing parent artifact member: {name}")


def backup_file(task_root: Path, task: Path, path: Path, backup_root: Path) -> None:
    if not path.exists():
        return
    relative = task.relative_to(task_root) / path.relative_to(task)
    destination = backup_root / relative
    if destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)


def geometry_summary(metrics: dict[str, Any], parameters: dict[str, Any]):
    return {
        "artifact": {"format": "stl", "path": "product.stl"},
        "geometry": metrics,
        "scenario_parameters": parameters,
    }


def build_oracle_source(records: list[dict[str, Any]]) -> str:
    table = {
        json.dumps(
            record["parameters"],
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ): geometry_summary(record["metrics"], record["parameters"])
        for record in records
    }
    encoded = json.dumps(table, indent=2, sort_keys=True)
    return f'''#!/usr/bin/env python3
import json

_TABLE = json.loads({encoded!r})


def _key(params):
    return json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)


def true10_oracle(params):
    key = _key(params)
    if key not in _TABLE:
        raise KeyError(f"unrecognized true10 scenario parameters: {{params!r}}")
    return _TABLE[key]


ORACLES = {{"openscad_parametric_cad": true10_oracle}}
'''


def update_public_archive(
    archive_path: Path,
    records_by_id: dict[str, dict[str, Any]],
) -> None:
    with tempfile.TemporaryDirectory(prefix="openscad_public_") as temporary:
        root = Path(temporary)
        with tarfile.open(archive_path, "r:gz") as archive:
            safe_extract(archive, root)
        manifest_path = root / "public_manifest.json"
        manifest = load_json(manifest_path)
        for scenario in manifest.get("public_scenarios", []):
            scenario_id = scenario["scenario_id"]
            record = records_by_id[scenario_id]
            summary = geometry_summary(record["metrics"], record["parameters"])
            oracle_output = {
                "parameter_effect": {
                    "digest": canonical_signature(summary["geometry"]),
                    "keys": sorted(record["parameters"]),
                },
                "summary": summary,
            }
            signature = canonical_signature(oracle_output)
            scenario["oracle_output"] = oracle_output
            scenario["signature"] = signature
            write_json(root / scenario_id / "oracle_output.json", oracle_output)
            write_json(
                root / scenario_id / "oracle/oracle_output.pretty.json",
                oracle_output,
            )
            write_json(
                root / scenario_id / "signature.json",
                {"signature": signature},
            )
            artifact_manifest = load_json(
                root / scenario_id / "artifact_manifest.json"
            )
            artifact_manifest["summary_signature"] = signature
            artifact_manifest["verification"] = "stl_geometry"
            write_json(
                root / scenario_id / "artifact_manifest.json",
                artifact_manifest,
            )
            write_json(
                root / scenario_id / "native/metrics.json",
                record["metrics"],
            )
        write_json(manifest_path, manifest)
        replacement = archive_path.with_suffix(archive_path.suffix + ".new")
        with tarfile.open(replacement, "w:gz") as archive:
            for child in sorted(root.iterdir(), key=lambda path: path.name):
                archive.add(child, arcname=child.name, recursive=True)
        os.replace(replacement, archive_path)


def update_dockerfiles(task: Path) -> None:
    environment = task / "environment/Dockerfile"
    text = environment.read_text(encoding="utf-8")
    if "python3-numpy python3-scipy" not in text:
        text = text.replace(
            "openscad chromium xvfb git python3 build-essential \\\n",
            "openscad chromium xvfb git python3 python3-numpy python3-scipy build-essential \\\n",
            1,
        )
        environment.write_text(text, encoding="utf-8")

    tests = task / "tests/Dockerfile"
    text = tests.read_text(encoding="utf-8")
    install = "RUN python3 -m pip install --no-cache-dir numpy scipy\n"
    if install not in text:
        text = text.replace("COPY . /tests\n", "COPY . /tests\n" + install, 1)
        tests.write_text(text, encoding="utf-8")


def update_instruction(task: Path) -> None:
    path = task / "instruction.md"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "reports which public oracle signatures match.",
        "compares the generated STL geometry with the public reference geometry.",
    )
    if MARKER not in text:
        text += f"""

{MARKER}

Each invocation of `reconstruct.py` must generate a valid STL mesh at
`/app/workspace/product.stl` (or return an `artifact_path` inside the workspace)
and print a JSON object to stdout. The STL must be regenerated from the current
scenario parameters. The verifier evaluates bounding-box dimensions, volume,
surface area, connected components, and sampled surface distance against the
hidden reference mesh. File hashes, byte counts, and fixed public meshes do not
satisfy this contract.
"""
    path.write_text(text, encoding="utf-8")


def update_reconstruction_metadata(task: Path) -> None:
    path = task / "reconstruction.json"
    payload = load_json(path)
    payload["feedback"]["metrics"] = [
        "editable_workspace_nonempty",
        "uses_native_project_files",
        "stl_bbox_extents",
        "stl_volume",
        "stl_surface_area",
        "stl_component_count",
        "stl_sampled_surface_distance",
    ]
    payload["judge"]["geometry_verification"] = {
        "artifact": "product.stl",
        "byte_size_or_hash_used": False,
        "metrics": [
            "bbox_extents",
            "volume",
            "surface_area",
            "component_count",
            "sampled_surface_distance",
        ],
    }
    write_json(path, payload)


def upgrade_task(
    task_root: Path,
    task: Path,
    backup_root: Path,
    helper_source: str,
    judge_source: str,
    feedback_source: str,
) -> dict[str, Any]:
    variant = load_json(task / "tests/private/variant.json")
    manifest = load_json(task / "tests/private/manifest.json")
    if variant.get("family_id") != "openscad_parametric_cad":
        raise ValueError(f"not an OpenSCAD task: {task}")
    parent_path = Path(variant["base_parent_artifact"])
    scenarios = manifest.get("public_scenarios", []) + manifest.get(
        "hidden_scenarios", []
    )
    records = []
    reference_meshes = task / "tests/private/reference_meshes"
    reference_meshes.mkdir(parents=True, exist_ok=True)
    with tarfile.open(parent_path, "r:gz") as parent:
        for scenario in scenarios:
            scenario_id = scenario["scenario_id"]
            stl = parent_member(parent, f"{scenario_id}/product.stl")
            stl_path = reference_meshes / f"{scenario_id}.stl"
            stl_path.write_bytes(stl)
            records.append(
                {
                    "scenario_id": scenario_id,
                    "parameters": scenario["parameters"],
                    "metrics": metrics_for_stl(stl_path),
                }
            )

    overwritten = [
        task / "instruction.md",
        task / "reconstruction.json",
        task / "environment/Dockerfile",
        task / "tests/Dockerfile",
        task / "environment/app/tools/feedback",
        task / "environment/app/observations/reference_outputs.tar.gz",
        task / "tests/private/judge.py",
        task / "tests/private/true10_oracle.py",
    ]
    for path in overwritten:
        backup_file(task_root, task, path, backup_root)

    records_by_id = {record["scenario_id"]: record for record in records}
    update_public_archive(
        task / "environment/app/observations/reference_outputs.tar.gz",
        records_by_id,
    )
    (task / "tests/private/true10_oracle.py").write_text(
        build_oracle_source(records), encoding="utf-8"
    )
    (task / "tests/private/judge.py").write_text(judge_source, encoding="utf-8")
    (task / "tests/private/openscad_geometry.py").write_text(
        helper_source, encoding="utf-8"
    )
    tools = task / "environment/app/tools"
    (tools / "feedback").write_text(feedback_source, encoding="utf-8")
    (tools / "openscad_geometry.py").write_text(helper_source, encoding="utf-8")
    (tools / "feedback").chmod(0o755)
    update_instruction(task)
    update_reconstruction_metadata(task)
    update_dockerfiles(task)
    return {
        "task_id": task.name,
        "parent_artifact": str(parent_path),
        "scenarios": len(records),
        "public_scenarios": sum(
            record["scenario_id"].startswith("public_") for record in records
        ),
        "hidden_scenarios": sum(
            record["scenario_id"].startswith("hidden_") for record in records
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", type=Path, default=DEFAULT_TASK_ROOT)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--task-name")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    helper_source = (HERE / "openscad_metrics.py").read_text(
        encoding="utf-8"
    )
    judge_source = (HERE / "openscad_judge.py").read_text(
        encoding="utf-8"
    )
    feedback_source = (HERE / "openscad_feedback.py").read_text(
        encoding="utf-8"
    )
    tasks = []
    candidates = (
        [args.task_root / args.task_name]
        if args.task_name
        else sorted(args.task_root.glob("openscad_*"))
    )
    for task in candidates:
        if task.is_dir():
            tasks.append(
                upgrade_task(
                    args.task_root,
                    task,
                    args.backup_root,
                    helper_source,
                    judge_source,
                    feedback_source,
                )
            )
    payload = {
        "task_root": str(args.task_root),
        "backup_root": str(args.backup_root),
        "task_count": len(tasks),
        "tasks": tasks,
    }
    report = args.report or args.backup_root.parent / "openscad_geometry_report.json"
    write_json(report, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if len(tasks) == (1 if args.task_name else 60) else 1


if __name__ == "__main__":
    raise SystemExit(main())
