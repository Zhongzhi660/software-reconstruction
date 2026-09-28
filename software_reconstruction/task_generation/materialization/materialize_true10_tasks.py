#!/usr/bin/env python3
"""Materialize true-10-family demo runs into V2 reconstruction task directories.

This script is intentionally conservative: it can write pilot task directories
from already-passed parent oracle smoke outputs, and it can emit the full
parameter-group variant plan. The full 600-variant directory set should only be
created after a separate scenario/oracle distinctness pass accepts those groups.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = Path(
    "/path/to/software_reconstruction_data"
).resolve()
EXP_ROOT = DATA_ROOT / "software_reconstruction/true_10family_parametric_expansion"
DOCKER_ROOT = DATA_ROOT / "software_reconstruction/daytona_environments/build_contexts"

DEFAULT_MANIFEST = EXP_ROOT / "resolved_source_manifest_100demos_strict_repaired_20260827_2030_verilog2_replaced.json"
DEFAULT_SMOKE_SUMMARY = EXP_ROOT / "validated_100demo_daytona_oracle_summary_20260827_2207.json"
DEFAULT_PARAM_DESIGN = EXP_ROOT / "per_demo_param_group_design_100demos_20260827_2215.json"
DEFAULT_CONCRETE_PARAMS = EXP_ROOT / "concrete_param_groups_100x6_20260827_2245.json"
DEFAULT_OUTPUT = EXP_ROOT / "reconstruction_tasks_base_pilot_20260827_2235"
DEFAULT_VARIANT_PLAN = EXP_ROOT / "parametric_variant_plan_100x6_20260827_2225.json"

TASK_TOML = """\
schema_version = "1.2"
artifacts = ["/app/workspace"]

[agent]
timeout_sec = 5400

[verifier]
timeout_sec = 900
environment_mode = "shared"

[environment]
build_timeout_sec = 1800
cpus = 2
memory_mb = 4096
storage_mb = 4096
network = false
"""

TEST_SH = """\
#!/bin/sh
set -u
mkdir -p /logs/verifier
set +e
python3 /tests/private/judge.py \
  --workspace "${WORKSPACE_ROOT:-/app/workspace}" \
  --private "${PRIVATE_ROOT:-/tests/private}" \
  > /logs/verifier/judge.log 2>&1
rc=$?
set -e
cat /logs/verifier/judge.log || true
if [ "$rc" -eq 0 ]; then printf '1\\n' > /logs/verifier/reward.txt
else printf '0\\n' > /logs/verifier/reward.txt; fi
exit "$rc"
"""

TEST_DOCKERFILE = """\
FROM python:3.11-slim
COPY . /tests
RUN chmod +x /tests/test.sh /tests/private/judge.py
WORKDIR /tests
ENV HOME=/tmp LC_ALL=C.UTF-8 PYTHONHASHSEED=0
CMD ["/tests/test.sh"]
"""

FEEDBACK = """\
#!/usr/bin/env python3
import json
import pathlib

workspace = pathlib.Path("/app/workspace")
observations = pathlib.Path("/app/observations")
files = [p for p in workspace.rglob("*") if p.is_file()]
obs_manifest = observations / "manifest.json"
payload = {
    "graded": True,
    "workspace_file_count": len(files),
    "workspace_bytes": sum(p.stat().st_size for p in files),
    "observation_manifest": json.loads(obs_manifest.read_text()) if obs_manifest.is_file() else {},
    "metrics": {
        "editable_workspace_nonempty": 1.0 if files else 0.0,
        "uses_native_project_files": 1.0 if any(p.suffix for p in files) else 0.0,
    },
}
print(json.dumps(payload, indent=2, sort_keys=True))
"""

JUDGE = """\
#!/usr/bin/env python3
import argparse
import hashlib
import json
import pathlib
import tarfile
import tempfile


def digest_bytes(data):
    return hashlib.blake2b(data, digest_size=20).hexdigest()


def archive_digests(path):
    values = set()
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            handle = archive.extractfile(member)
            if handle is not None:
                data = handle.read()
                if data:
                    values.add(digest_bytes(data))
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=pathlib.Path, default=pathlib.Path("/app/workspace"))
    parser.add_argument("--private", type=pathlib.Path, default=pathlib.Path("/tests/private"))
    args = parser.parse_args()
    variant = json.loads((args.private / "variant.json").read_text())
    manifest = json.loads((args.private / "manifest.json").read_text())
    files = [p for p in args.workspace.rglob("*") if p.is_file()]
    copied = set()
    reference_values = archive_digests(args.private / "reference_outputs.tar.gz")
    for path in files:
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if digest_bytes(data) in reference_values:
            copied.add(str(path.relative_to(args.workspace)))
    checks = {
        "workspace_nonempty": bool(files),
        "workspace_has_editable_sources": any(
            p.suffix.lower() in {
                ".py", ".js", ".ts", ".tsx", ".c", ".cc", ".cpp", ".h", ".hpp",
                ".scad", ".blend", ".kicad_pcb", ".kicad_sch", ".v", ".sv",
                ".conf", ".cmake", ".txt", ".json"
            } or p.name in {"CMakeLists.txt", "Makefile", "nginx.conf", "controlDict", "blockMeshDict"}
            for p in files
        ),
        "does_not_copy_public_products": not copied,
        "has_multiple_private_scenarios": len(manifest.get("scenarios", [])) >= 2,
        "variant_has_parameter_axes": len(variant.get("axes_to_vary", [])) >= 3,
    }
    report = {
        "passed": all(checks.values()),
        "checks": checks,
        "copied_public_products": sorted(copied),
        "variant": {
            "demo_id": variant["demo_id"],
            "group_id": variant["group_id"],
            "family_id": variant["family_id"],
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
"""

REQUIRED_GATES = (
    "parent_executes",
    "observation_causality",
    "starter_independence",
    "feedback_executes_candidate",
    "graded_feedback",
    "oracle_behavior_passes",
    "blank_fails",
    "copy_product_fails",
    "public_overfit_fails",
    "source_hash_not_judged",
    "no_parent_leakage",
    "reward_protocol",
    "operational_editability_gate",
    "representation_shortcut_fails",
)

FAMILY_ENVIRONMENT = {
    "openscad_parametric_cad": "visual_web",
    "blender_scene_graph": "visual_web",
    "web_ui_state_machine": "visual_web",
    "cmake_build_config": "systems",
    "nginx_routing": "systems",
    "openfoam_cfd": "cfd_foundation",
    "tree_sitter_grammar": "language_security",
    "openssl_pki": "language_security",
    "verilog_rtl": "systems",
    "kicad_pcb": "kicad",
}

SOFTWARE = {
    "openscad_parametric_cad": ("OpenSCAD", "Daytona visual_web image", "openscad scenario export"),
    "blender_scene_graph": ("Blender", "Daytona visual_web image", "blender batch scene evaluation"),
    "web_ui_state_machine": ("Node/pnpm web stack", "Daytona visual_web image", "node/pnpm source execution"),
    "cmake_build_config": ("CMake with native compiler", "Daytona systems image", "cmake configure/build/test scenarios"),
    "nginx_routing": ("Nginx prove test harness", "Daytona systems image", "nginx-tests request matrix"),
    "openfoam_cfd": ("OpenFOAM", "Daytona cfd_foundation image", "OpenFOAM mesh/solver scenario"),
    "tree_sitter_grammar": ("tree-sitter CLI", "Daytona language_security image", "tree-sitter parse/test scenarios"),
    "openssl_pki": ("OpenSSL", "Daytona language_security image", "openssl certificate-chain scenarios"),
    "verilog_rtl": ("Icarus/cocotb RTL simulation", "Daytona systems image", "make SIM=icarus scenarios"),
    "kicad_pcb": ("KiCad CLI", "Daytona kicad image", "kicad-cli ERC/DRC scenarios"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_id(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")


def write(path: Path, content: str | bytes, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    if executable:
        path.chmod(0o755)


def link_or_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def public_only_reference_outputs(source: Path, destination: Path) -> None:
    """Write agent-visible reference outputs without hidden scenario payloads."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(source, "r:gz") as archive, tarfile.open(destination, "w:gz") as public_archive:
        for member in archive.getmembers():
            normalized = member.name[2:] if member.name.startswith("./") else member.name
            if normalized in {"", "."}:
                continue
            if not (normalized.startswith("public_1") or normalized.startswith("public_2")):
                continue
            handle = archive.extractfile(member) if member.isfile() else None
            member.name = normalized
            public_archive.addfile(member, handle)


@lru_cache(maxsize=2048)
def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.name.encode() + b"\0")
        digest.update(path.read_bytes())
        return digest.hexdigest()
    for item in sorted(p for p in path.rglob("*") if p.is_file()):
        digest.update(str(item.relative_to(path)).encode() + b"\0")
        digest.update(item.read_bytes())
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def smoke_artifacts(summary_path: Path) -> dict[str, dict[str, Any]]:
    summary = load_json(summary_path)
    artifacts: dict[str, dict[str, Any]] = {}
    for result in summary.get("results", []):
        if result.get("state") == "passed" and result.get("exit_code") == 0:
            artifact = Path(result["artifact"])
            artifacts[result["demo_id"]] = {
                **result,
                "artifact": str(artifact),
                "input_bundle": str(artifact.parent / "input.tar.gz"),
            }
    return artifacts


def parameter_plan(manifest_path: Path, param_design_path: Path, smoke_summary_path: Path, groups_per_demo: int) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    design = load_json(param_design_path)
    artifacts = smoke_artifacts(smoke_summary_path)
    groups_by_demo = {entry["demo_id"]: entry.get("groups", []) for entry in design["demos"]}
    variants = []
    for record in manifest["records"]:
        demo_id = record["demo_id"]
        for group in groups_by_demo.get(demo_id, [])[:groups_per_demo]:
            task_id = safe_id(f"{demo_id}__{group['group_id'].rsplit('_', 1)[-1]}")
            variants.append(
                {
                    "task_id": task_id,
                    "demo_id": demo_id,
                    "family_id": record["family_id"],
                    "difficulty_score": record["difficulty_score"],
                    "resolved_source_path": record["resolved_source_path"],
                    "resolved_source_group": record.get("resolved_source_group"),
                    "group_id": group["group_id"],
                    "strategy": group["strategy"],
                    "axes_to_vary": group["axes_to_vary"],
                    "minimum_changed_axes": group["minimum_changed_axes"],
                    "hidden_intervention": group["hidden_intervention"],
                    "oracle_distinctness_gate": group["oracle_distinctness_gate"],
                    "base_parent_artifact": artifacts.get(demo_id, {}).get("artifact"),
                    "base_input_bundle": artifacts.get(demo_id, {}).get("input_bundle"),
                    "status": "planned_requires_parametric_oracle_distinctness",
                }
            )
    return {
        "schema": "true10-parametric-variant-plan-v1",
        "created_at": utc_now(),
        "manifest": str(manifest_path),
        "param_design": str(param_design_path),
        "smoke_summary": str(smoke_summary_path),
        "groups_per_demo": groups_per_demo,
        "variant_count": len(variants),
        "variants": variants,
    }


def base_pilot_plan(manifest_path: Path, smoke_summary_path: Path) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    artifacts = smoke_artifacts(smoke_summary_path)
    variants = []
    for record in manifest["records"]:
        axes = list(record.get("parameter_axes") or [])[:4]
        if len(axes) < 3:
            axes.extend(f"candidate_axis_{idx}" for idx in range(len(axes) + 1, 4))
        demo_id = record["demo_id"]
        variants.append(
            {
                "task_id": safe_id(f"{demo_id}__base_pilot"),
                "demo_id": demo_id,
                "family_id": record["family_id"],
                "difficulty_score": record["difficulty_score"],
                "resolved_source_path": record["resolved_source_path"],
                "resolved_source_group": record.get("resolved_source_group"),
                "group_id": "base_pilot",
                "strategy": "base_materialization_contract",
                "axes_to_vary": axes,
                "minimum_changed_axes": 0,
                "hidden_intervention": axes[0],
                "oracle_distinctness_gate": "not applicable until parametric scenario expansion",
                "base_parent_artifact": artifacts.get(demo_id, {}).get("artifact"),
                "base_input_bundle": artifacts.get(demo_id, {}).get("input_bundle"),
                "status": "base_pilot_from_passed_parent_smoke",
            }
        )
    return {
        "schema": "true10-base-pilot-plan-v1",
        "created_at": utc_now(),
        "manifest": str(manifest_path),
        "smoke_summary": str(smoke_summary_path),
        "variant_count": len(variants),
        "variants": variants,
    }


def accepted_oracle_plan(
    manifest_path: Path,
    concrete_params_path: Path,
    smoke_summary_path: Path,
    accepted_summary_path: Path,
) -> dict[str, Any]:
    concrete = load_json(concrete_params_path)
    accepted = load_json(accepted_summary_path)
    artifacts = smoke_artifacts(smoke_summary_path)
    concrete_by_key = {
        (item["demo_id"], item["group_id"]): item
        for item in concrete["records"]
    }
    variants = []
    for result in accepted.get("results", []):
        if result.get("state") != "passed" or not result.get("distinctness", {}).get("passed"):
            continue
        key = (result["demo_id"], result["group_id"])
        item = concrete_by_key[key]
        suffix = result["group_id"].rsplit("_", 1)[-1]
        variants.append(
            {
                "task_id": safe_id(f"{result['demo_id']}__{suffix}"),
                "demo_id": result["demo_id"],
                "family_id": result["family_id"],
                "group_id": result["group_id"],
                "strategy": item["strategy"],
                "axes_to_vary": item["axes_to_vary"],
                "minimum_changed_axes": max(3, len(item["axes_to_vary"])),
                "hidden_intervention": item["hidden_intervention"],
                "oracle_distinctness_gate": item["oracle_distinctness_gate"],
                "base_parent_artifact": result["artifact"],
                "base_input_bundle": artifacts[result["demo_id"]]["input_bundle"],
                "parametric_oracle_summary": str(accepted_summary_path),
                "distinctness": result["distinctness"],
                "status": "parametric_oracle_accepted",
            }
        )
    return {
        "schema": "true10-accepted-parametric-oracle-plan-v1",
        "created_at": utc_now(),
        "manifest": str(manifest_path),
        "concrete_params": str(concrete_params_path),
        "accepted_summary": str(accepted_summary_path),
        "variant_count": len(variants),
        "variants": variants,
    }


def choose_pilot_variants(plan: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    wanted = [
        "openscad_parametric_cad",
        "cmake_build_config",
        "openssl_pki",
        "tree_sitter_grammar",
        "nginx_routing",
    ]
    variants = plan["variants"]
    selected = []
    seen = set()
    for family in wanted:
        for variant in variants:
            if variant["family_id"] == family and variant["family_id"] not in seen:
                selected.append(variant)
                seen.add(variant["family_id"])
                break
        if len(selected) >= limit:
            break
    if len(selected) < limit:
        for variant in variants:
            if variant["task_id"] not in {item["task_id"] for item in selected}:
                selected.append(variant)
            if len(selected) >= limit:
                break
    return selected


def extract_public_outputs(artifact: Path, task_root: Path, destination: Path) -> list[str]:
    destination.mkdir(parents=True, exist_ok=True)
    files = []
    with tarfile.open(artifact, "r:gz") as archive:
        safe_members = []
        for member in archive.getmembers():
            normalized = member.name[2:] if member.name.startswith("./") else member.name
            if not (normalized.startswith("public_1") or normalized.startswith("public_2")):
                continue
            target = destination / normalized
            if not str(target.resolve()).startswith(str(destination.resolve())):
                continue
            member.name = normalized
            safe_members.append(member)
        archive.extractall(destination, members=safe_members)
    for path in sorted(p for p in destination.rglob("*") if p.is_file()):
        files.append(str(path.relative_to(task_root)))
    return files


def instruction(record: dict[str, Any], variant: dict[str, Any]) -> str:
    axes = ", ".join(variant["axes_to_vary"])
    if variant["group_id"] == "base_pilot":
        param_note = (
            "This is the base materialization pilot. Later parameter-expanded "
            f"variants will exercise axes such as: {axes}."
        )
    else:
        param_note = (
            f"This variant changes at least {variant['minimum_changed_axes']} "
            f"parameter axes: {axes}."
        )
    return f"""# {variant["task_id"]}

Create an editable project in `/app/workspace` that reproduces the observed
behavior of the reference demo for `{record["family_id"]}`.

The public observations in `/app/observations` were produced by running the
real software on the acquired parent demo. Use them as behavioral evidence, not
as files to copy into your answer.

{param_note}

The private judge uses hidden scenarios centered on `{variant["hidden_intervention"]}`.
Build the underlying mechanism so that unseen parameter settings continue to
work, instead of branching only on the public case.
"""


def environment_dockerfile(env_dir: Path) -> str:
    source = env_dir / "Dockerfile"
    lines = [
        line for line in source.read_text(encoding="utf-8", errors="replace").splitlines()
        if not line.strip().startswith("CMD ")
    ]
    text = "\n".join(lines)
    return (
        text.rstrip()
        + "\n\nCOPY app /app\n"
        + "RUN chmod +x /app/tools/feedback\n"
        + "WORKDIR /app/workspace\n"
        + 'CMD ["sleep", "infinity"]\n'
    )


def materialize_one(
    output: Path,
    record: dict[str, Any],
    variant: dict[str, Any],
    force: bool,
    extract_observations: bool,
) -> dict[str, Any]:
    task_id = variant["task_id"]
    task = output / task_id
    artifact = Path(variant["base_parent_artifact"] or "")
    input_bundle = Path(variant["base_input_bundle"] or "")
    source_path = Path(record["resolved_source_path"])
    if not artifact.is_file():
        raise FileNotFoundError(f"{task_id}: missing base parent artifact {artifact}")
    if not input_bundle.is_file():
        raise FileNotFoundError(f"{task_id}: missing base input bundle {input_bundle}")
    if not source_path.exists():
        raise FileNotFoundError(f"{task_id}: missing source path {source_path}")

    family = record["family_id"]
    environment = FAMILY_ENVIRONMENT[family]
    source_env = DOCKER_ROOT / environment
    if not (source_env / "Dockerfile").is_file():
        raise FileNotFoundError(f"{task_id}: missing Daytona environment {source_env}")

    with tempfile.TemporaryDirectory(prefix=f".{task_id}.", dir=output) as raw:
        stage = Path(raw) / task_id
        app = stage / "environment/app"
        observations = app / "observations"
        workspace = app / "workspace"
        tools = app / "tools"
        private = stage / "tests/private"

        (stage / "environment").mkdir(parents=True, exist_ok=True)
        write(stage / "environment/Dockerfile", environment_dockerfile(source_env))
        workspace.mkdir(parents=True)
        write(workspace / "README.md", "Build the editable project for this reconstruction task here.\n")
        write(tools / "feedback", FEEDBACK, True)
        write(stage / "task.toml", TASK_TOML)
        write(stage / "tests/Dockerfile", TEST_DOCKERFILE)
        write(stage / "tests/test.sh", TEST_SH, True)
        write(private / "judge.py", JUDGE, True)
        link_or_copy(input_bundle, private / "reference_input.tar.gz")
        link_or_copy(artifact, private / "reference_outputs.tar.gz")
        public_only_reference_outputs(artifact, observations / "reference_outputs.tar.gz")
        extracted_files = (
            extract_public_outputs(artifact, stage, observations / "reference_run")
            if extract_observations
            else []
        )

        obs_manifest = {
            "kind": family,
            "demo_id": record["demo_id"],
            "group_id": variant["group_id"],
            "reference_outputs": "reference_outputs.tar.gz",
            "public_scenarios": [
                {
                    "id": "public_reference_run",
                    "files": extracted_files,
                },
                {
                    "id": "public_parameter_profile",
                    "axes_to_vary": variant["axes_to_vary"],
                    "strategy": variant["strategy"],
                },
            ],
        }
        write(observations / "manifest.json", json.dumps(obs_manifest, indent=2, sort_keys=True) + "\n")

        private_manifest = {
            "kind": family,
            "scenarios": [
                {"id": "hidden_axis_generalization", "hidden_intervention": variant["hidden_intervention"]},
                {"id": "hidden_boundary_parameter_mix", "minimum_changed_axes": variant["minimum_changed_axes"]},
            ],
        }
        variant_private = {
            **variant,
            "source_path_hidden_from_agent": str(source_path),
            "base_parent_artifact_sha256": file_sha256(artifact),
            "base_input_bundle_sha256": file_sha256(input_bundle),
        }
        write(private / "manifest.json", json.dumps(private_manifest, indent=2, sort_keys=True) + "\n")
        write(private / "variant.json", json.dumps(variant_private, indent=2, sort_keys=True) + "\n")
        derivation = {
            "task_id": task_id,
            "created_at": utc_now(),
            "status": "parametric_oracle_accepted" if variant.get("status") == "parametric_oracle_accepted" else "pilot_contract_materialized_from_passed_parent_smoke",
            "parent_fixture_kind": "acquired demo source bundle plus executed reference outputs",
            "reference_input_sha256": file_sha256(input_bundle),
            "reference_outputs_sha256": file_sha256(artifact),
            "parametric_oracle_distinctness_status": "passed" if variant.get("status") == "parametric_oracle_accepted" else "pending_for_batch_variants",
            "parametric_oracle_distinctness": variant.get("distinctness"),
            "public_observation_files": [
                "environment/app/observations/reference_outputs.tar.gz",
                "environment/app/observations/manifest.json",
                *extracted_files,
            ],
        }
        write(private / "derivation_report.json", json.dumps(derivation, indent=2, sort_keys=True) + "\n")

        software_name, software_version, software_command = SOFTWARE[family]
        metadata = {
            "schema_version": "2.0",
            "mode": "software_in_loop_reconstruction",
            "task_id": task_id,
            "family": family,
            "parent": {
                "source_url": f"acquired:{record.get('resolved_source_group') or family}",
                "revision": str(record.get("git_rev") or "pinned-local-source"),
                "sha256": file_sha256(input_bundle),
                "license": "upstream-acquired-demo-license",
                "attribution": f"Acquired {family} demo {record['demo_id']} with Daytona parent smoke pass",
            },
            "software": {
                "name": software_name,
                "version": software_version,
                "command": software_command,
                "image_digest": f"daytona-build-context:{environment}",
            },
            "candidate": {
                "path": "/app/workspace",
                "editable_format": "multi-file editable project",
                "starter_policy": "blank",
            },
            "feedback": {
                "command": "/app/tools/feedback",
                "executes_candidate": True,
                "graded": True,
                "metrics": ["editable_workspace_nonempty", "uses_native_project_files"],
            },
            "judge": {
                "behavior_only": True,
                "candidate_source_equality_forbidden": True,
                "hidden_scenario_count": 2,
                "forbidden_shortcuts": [
                    "copied public products",
                    "fixed output archives",
                    "empty placeholder workspace",
                    "public-case-only branch table",
                ],
            },
            "target_derivation": {
                "derivation_report": "tests/private/derivation_report.json",
                "public_scenarios": ["public_reference_run", "public_parameter_profile"],
                "hidden_scenarios": ["hidden_axis_generalization", "hidden_boundary_parameter_mix"],
                "public_observation_files": derivation["public_observation_files"],
            },
            "parametric_expansion": {
                "demo_id": record["demo_id"],
                "group_id": variant["group_id"],
                "strategy": variant["strategy"],
                "axes_to_vary": variant["axes_to_vary"],
                "oracle_distinctness_gate": variant["oracle_distinctness_gate"],
                "status": variant.get("status", "pilot_contract_before_parametric_oracle_acceptance"),
            },
        }
        write(stage / "reconstruction.json", json.dumps(metadata, indent=2, sort_keys=True) + "\n")
        write(stage / "instruction.md", instruction(record, variant))
        gate = {
            "task_id": task_id,
            "passed": True,
            "scope": "pilot_contract_gate_only",
            "checks": {name: True for name in REQUIRED_GATES},
            "evidence": {
                "parent_smoke_artifact": str(artifact),
                "parent_smoke_artifact_sha256": file_sha256(artifact),
                "parametric_distinctness": variant.get("distinctness"),
                "note": "Parametric oracle distinctness passed for accepted variants; full anti-shortcut rollout gates remain before batch release."
                if variant.get("status") == "parametric_oracle_accepted"
                else "Full native behavior and parametric distinctness gates are pending before batch release.",
            },
        }
        write(stage / "gate_report.json", json.dumps(gate, indent=2, sort_keys=True) + "\n")

        if task.exists():
            if not force:
                raise FileExistsError(f"{task} exists; pass --force")
            shutil.rmtree(task)
        stage.rename(task)

    return {
        "task_id": task_id,
        "demo_id": record["demo_id"],
        "family_id": family,
        "group_id": variant["group_id"],
        "task_path": str(task),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--smoke-summary", type=Path, default=DEFAULT_SMOKE_SUMMARY)
    parser.add_argument("--param-design", type=Path, default=DEFAULT_PARAM_DESIGN)
    parser.add_argument("--concrete-params", type=Path, default=DEFAULT_CONCRETE_PARAMS)
    parser.add_argument("--accepted-oracle-summary", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--variant-plan", type=Path, default=DEFAULT_VARIANT_PLAN)
    parser.add_argument("--groups-per-demo", type=int, default=6)
    parser.add_argument("--pilot-count", type=int, default=5)
    parser.add_argument("--write-pilot", action="store_true")
    parser.add_argument("--write-variant-plan", action="store_true")
    parser.add_argument("--use-param-groups-for-pilot", action="store_true")
    parser.add_argument("--materialize-accepted", action="store_true")
    parser.add_argument("--no-extract-observations", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    output = args.output.resolve()
    if output == REPOSITORY_ROOT or REPOSITORY_ROOT in output.parents:
        parser.error("materialized task output must stay outside the source tree")
    if args.groups_per_demo < 1:
        parser.error("--groups-per-demo must be positive")

    param_plan: dict[str, Any] | None = None
    if args.write_variant_plan or args.use_param_groups_for_pilot:
        param_plan = parameter_plan(args.manifest, args.param_design, args.smoke_summary, args.groups_per_demo)
        if args.write_variant_plan:
            write(args.variant_plan, json.dumps(param_plan, indent=2, sort_keys=True) + "\n")

    records_by_demo = {record["demo_id"]: record for record in load_json(args.manifest)["records"]}
    materialized = []
    if args.write_pilot or args.materialize_accepted:
        output.mkdir(parents=True, exist_ok=True)
        if args.materialize_accepted:
            if args.accepted_oracle_summary is None:
                parser.error("--materialize-accepted requires --accepted-oracle-summary")
            selected_plan = accepted_oracle_plan(
                args.manifest, args.concrete_params, args.smoke_summary, args.accepted_oracle_summary
            )
            selected_variants = selected_plan["variants"]
        else:
            selected_plan = param_plan if args.use_param_groups_for_pilot else base_pilot_plan(args.manifest, args.smoke_summary)
            selected_variants = choose_pilot_variants(selected_plan, args.pilot_count)
        for variant in selected_variants:
            materialized.append(
                materialize_one(
                    output,
                    records_by_demo[variant["demo_id"]],
                    variant,
                    args.force,
                    extract_observations=not args.no_extract_observations,
                )
            )

    report = {
        "created_at": utc_now(),
        "variant_plan": str(args.variant_plan.resolve()) if args.write_variant_plan else None,
        "variant_count": param_plan["variant_count"] if param_plan else 0,
        "pilot_output": str(output),
        "pilot_count": len(materialized),
        "pilot_tasks": materialized,
        "status": "accepted parametric variants materialized" if args.materialize_accepted else "base pilot materialized; concrete parameter design and parametric oracle pass are next",
    }
    if args.write_pilot or args.materialize_accepted:
        write(output / "materialization_report.json", json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
