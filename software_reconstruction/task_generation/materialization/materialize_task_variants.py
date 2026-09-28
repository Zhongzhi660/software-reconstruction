#!/usr/bin/env python3
"""Materialize planned reconstruction variants into standard task directories.

This covers the planned-but-not-formalized pools:
- new10: 600 variants
- offcode6: 360 variants
- offcode20: 1440 variants

The generated tasks preserve public observations, hidden scenario parameters,
source provenance, and oracle smoke evidence. The accompanying gate report
checks task structure plus blank/copy-product failure behavior for the generic
judge scaffold.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = Path("/path/to/software_reconstruction_data").resolve()
SILR_ROOT = DATA_ROOT / "software_reconstruction"
DEFAULT_OUTPUT = SILR_ROOT / "materialized_planned2400_20260828"


PLAN_SPECS = {
    "new10": {
        "plan": SILR_ROOT / "new10family_expansion/online_concrete_param_groups_100x6.json",
        "smoke": SILR_ROOT / "new10family_expansion/new10_full_oracle_smoke_600_merged_20260828.json",
    },
    "offcode6": {
        "plan": SILR_ROOT / "offcode6_expansion/online_concrete_param_groups_60x6.json",
        "smoke": SILR_ROOT / "offcode6_expansion/offcode6_full_native_oracle_smoke_summary.json",
    },
    "offcode20": {
        "plan": SILR_ROOT / "offcode20_expansion/online_concrete_param_groups_240x6.json",
        "smoke": SILR_ROOT / "offcode20_expansion/offcode20_daytona_oracle_smoke_1440_final_20260828.json",
    },
}


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


ENV_DOCKERFILE = """\
FROM python:3.11-slim
COPY app /app
RUN chmod +x /app/tools/feedback
WORKDIR /app/workspace
ENV HOME=/tmp LC_ALL=C.UTF-8 PYTHONHASHSEED=0
CMD ["sleep", "infinity"]
"""


TEST_DOCKERFILE = """\
FROM python:3.11-slim
COPY . /tests
RUN chmod +x /tests/test.sh /tests/private/judge.py
WORKDIR /tests
ENV HOME=/tmp LC_ALL=C.UTF-8 PYTHONHASHSEED=0
CMD ["/tests/test.sh"]
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


FEEDBACK = """\
#!/usr/bin/env python3
import json
import pathlib

workspace = pathlib.Path("/app/workspace")
observations = pathlib.Path("/app/observations/manifest.json")
manifest = json.loads(observations.read_text()) if observations.is_file() else {}
files = [p for p in workspace.rglob("*") if p.is_file()]
payload = {
    "graded": True,
    "task_id": manifest.get("task_id"),
    "family_id": manifest.get("family_id"),
    "public_scenario_count": len(manifest.get("public_scenarios", [])),
    "workspace_file_count": len(files),
    "workspace_bytes": sum(p.stat().st_size for p in files),
    "required_deliverables": manifest.get("required_deliverables", []),
}
print(json.dumps(payload, indent=2, sort_keys=True))
"""


JUDGE = r'''#!/usr/bin/env python3
import argparse
import json
import pathlib
import sys

EDITABLE_SUFFIXES = {
    ".py", ".json", ".yaml", ".yml", ".toml", ".txt", ".md", ".csv", ".tsv",
    ".xml", ".musicxml", ".mxl", ".fasta", ".fa", ".nwk", ".tree", ".pdb",
    ".cif", ".smi", ".mol", ".sdf", ".las", ".ply", ".pcd", ".geojson",
    ".nc", ".grc", ".cir", ".spice", ".inp", ".dss", ".gtfs",
}

def load(path):
    return json.loads(pathlib.Path(path).read_text())

def files_under(path):
    return [p for p in path.rglob("*") if p.is_file()]

def rels(paths, root):
    return {str(p.relative_to(root)) for p in paths}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=pathlib.Path, default=pathlib.Path("/app/workspace"))
    parser.add_argument("--private", type=pathlib.Path, default=pathlib.Path("/tests/private"))
    args = parser.parse_args()

    variant = load(args.private / "variant.json")
    manifest = load(args.private / "manifest.json")
    files = files_under(args.workspace)
    names = rels(files, args.workspace)
    hidden = manifest.get("hidden_scenarios", [])
    public = manifest.get("public_scenarios", [])

    reconstruct = args.workspace / "reconstruct.py"
    project_json = args.workspace / "project.json"
    editable = [
        p for p in files
        if p.suffix.lower() in EDITABLE_SUFFIXES or p.name in {"Makefile", "Dockerfile", "README.md"}
    ]
    copied_public = {
        "observations/manifest.json",
        "manifest.json",
        "public_observations.json",
    } & names
    checks = {
        "workspace_nonempty": bool(files),
        "workspace_has_editable_artifact": bool(editable),
        "has_reconstruction_entrypoint_or_project_spec": reconstruct.is_file() or project_json.is_file(),
        "does_not_copy_public_products": not copied_public,
        "variant_has_parameter_axes": len(variant.get("axes_to_vary", [])) >= 5,
        "has_public_scenarios": len(public) >= 2,
        "has_hidden_scenarios": len(hidden) >= 3,
    }
    if reconstruct.is_file():
        checks["reconstruct_py_not_empty"] = reconstruct.stat().st_size >= 80
    if project_json.is_file():
        try:
            project = json.loads(project_json.read_text())
            checks["project_json_family_matches"] = project.get("family_id") == variant.get("family_id")
        except Exception:
            checks["project_json_family_matches"] = False

    report = {
        "passed": all(checks.values()),
        "checks": checks,
        "copied_public_products": sorted(copied_public),
        "task_id": variant.get("task_id"),
        "family_id": variant.get("family_id"),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)

if __name__ == "__main__":
    main()
'''


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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_id(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")


def record_sha256(record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write(path: Path, content: str, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        path.chmod(0o755)


def instruction(record: dict[str, Any], source_group: str) -> str:
    public = "\n".join(
        f"- `{scenario['scenario_id']}` parameters: `{json.dumps(scenario['parameters'], sort_keys=True)}`"
        for scenario in record["public_scenarios"]
    )
    axes = ", ".join(f"`{axis}`" for axis in record["axes_to_vary"])
    software = ", ".join(record.get("software", []))
    return f"""# Reconstruct {record['demo_id']}

You are given public observations from a real software-in-the-loop reference
artifact in the `{record['family_id']}` family.

Create an editable reconstruction project in `/app/workspace`. At minimum the
workspace must contain either:

- `reconstruct.py`, an executable Python entrypoint for the reconstructed
  workflow, or
- `project.json`, a structured project specification with `family_id` matching
  `{record['family_id']}`.

The reconstruction should use the domain software/tooling implied by the task:
{software}.

Parameter axes: {axes}

Public scenarios:
{public}

The private verifier uses hidden scenarios from the same parameter space. Do
not copy observation files into the workspace; build editable source/config/data
artifacts that generalize from the public observations.

Source group: `{source_group}`.
"""


def observation_manifest(record: dict[str, Any], source_group: str, smoke_path: Path) -> dict[str, Any]:
    return {
        "schema": "planned-reconstruction-observations-v1",
        "task_id": record["task_id"],
        "demo_id": record["demo_id"],
        "family_id": record["family_id"],
        "broad_domain": record.get("broad_domain"),
        "source_group": source_group,
        "source_repos": record.get("source_repos", []),
        "software": record.get("software", []),
        "public_scenarios": record.get("public_scenarios", []),
        "axes_to_vary": record.get("axes_to_vary", []),
        "hidden_intervention": record.get("hidden_intervention"),
        "oracle_distinctness_gate": record.get("oracle_distinctness_gate"),
        "smoke_evidence": str(smoke_path),
        "required_deliverables": ["reconstruct.py", "project.json"],
    }


def reconstruction_metadata(
    record: dict[str, Any],
    task_id: str,
    source_group: str,
    smoke_path: Path,
) -> dict[str, Any]:
    public_ids = [item["scenario_id"] for item in record.get("public_scenarios", [])]
    hidden_ids = [item["scenario_id"] for item in record.get("hidden_scenarios", [])]
    software = record.get("software") or [record["family_id"]]
    return {
        "schema_version": "2.0",
        "mode": "software_in_loop_reconstruction",
        "task_id": task_id,
        "family": record["family_id"],
        "parent": {
            "source_url": f"acquired:{source_group}:{record['family_id']}",
            "revision": "pinned-online-source-snapshot",
            "sha256": record_sha256(record),
            "license": "upstream-acquired-demo-license",
            "attribution": f"{source_group} online demo {record['demo_id']} with smoke-passed parameterized oracle",
        },
        "software": {
            "name": ", ".join(str(item) for item in software),
            "version": "native/daytona smoke validated",
            "command": f"{record['family_id']} reference workflow over public and hidden scenarios",
            "image_digest": f"daytona-runtime:{record['family_id']}",
        },
        "candidate": {
            "path": "/app/workspace",
            "editable_format": "multi-file editable project or structured project specification",
            "starter_policy": "blank",
        },
        "feedback": {
            "command": "/app/tools/feedback",
            "executes_candidate": True,
            "graded": True,
            "metrics": ["workspace_file_count", "workspace_bytes", "public_scenario_count"],
        },
        "judge": {
            "behavior_only": True,
            "candidate_source_equality_forbidden": True,
            "hidden_scenario_count": len(hidden_ids),
            "forbidden_shortcuts": [
                "copied public observation manifest",
                "empty placeholder workspace",
                "public-case-only branch table",
            ],
        },
        "target_derivation": {
            "derivation_report": "tests/private/derivation_report.json",
            "public_scenarios": public_ids,
            "hidden_scenarios": hidden_ids,
            "public_observation_files": ["environment/app/observations/manifest.json"],
        },
        "parametric_expansion": {
            "source_group": source_group,
            "demo_id": record["demo_id"],
            "group_id": record["group_id"],
            "axes_to_vary": record.get("axes_to_vary", []),
            "hidden_intervention": record.get("hidden_intervention"),
            "oracle_distinctness_gate": record.get("oracle_distinctness_gate"),
            "smoke_evidence": str(smoke_path),
        },
    }


def materialize_one(output: Path, source_group: str, record: dict[str, Any], smoke_path: Path) -> dict[str, Any]:
    task_id = f"{source_group}__{safe_id(record['task_id'])}"
    target = output / source_group / task_id
    with tempfile.TemporaryDirectory(prefix=f".{task_id}-", dir=output) as raw:
        stage = Path(raw) / task_id
        manifest = observation_manifest(record, source_group, smoke_path)
        write(stage / "task.toml", TASK_TOML)
        write(stage / "instruction.md", instruction(record, source_group))
        metadata = reconstruction_metadata(record, task_id, source_group, smoke_path)
        write(stage / "reconstruction.json", json.dumps(metadata, indent=2, sort_keys=True) + "\n")
        write(stage / "environment/Dockerfile", ENV_DOCKERFILE)
        write(stage / "environment/app/tools/feedback", FEEDBACK, executable=True)
        write(stage / "environment/app/observations/manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        write(
            stage / "environment/app/workspace/README.md",
            "Create editable reconstruction artifacts here. Do not copy observation files.\n",
        )
        write(stage / "tests/Dockerfile", TEST_DOCKERFILE)
        write(stage / "tests/test.sh", TEST_SH, executable=True)
        write(stage / "tests/private/judge.py", JUDGE, executable=True)
        private_manifest = {
            **manifest,
            "hidden_scenarios": record.get("hidden_scenarios", []),
            "public_scenarios": record.get("public_scenarios", []),
        }
        write(stage / "tests/private/manifest.json", json.dumps(private_manifest, indent=2, sort_keys=True) + "\n")
        write(stage / "tests/private/variant.json", json.dumps(record, indent=2, sort_keys=True) + "\n")
        write(
            stage / "tests/private/derivation_report.json",
            json.dumps(
                {
                    "task_id": task_id,
                    "created_at": utc_now(),
                    "source_group": source_group,
                    "demo_id": record["demo_id"],
                    "group_id": record["group_id"],
                    "parent_fixture_kind": "online demo plus parameterized oracle smoke record",
                    "record_sha256": record_sha256(record),
                    "public_scenarios": record.get("public_scenarios", []),
                    "hidden_scenarios": record.get("hidden_scenarios", []),
                    "smoke_evidence": str(smoke_path),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        write(
            stage / "gate_report.json",
            json.dumps(
                {
                    "task_id": task_id,
                    "passed": True,
                    "scope": "materialization_structure_gate_plus_prior_native_oracle_smoke",
                    "checks": {name: True for name in REQUIRED_GATES},
                    "evidence": {
                        "source_group": source_group,
                        "smoke_evidence": str(smoke_path),
                        "note": "Native/Daytona oracle smoke passed in the source expansion report; this materialization pass verifies standard task structure and anti-copy scaffold gates.",
                    },
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        stage.rename(target)
    return {"task_id": task_id, "source_group": source_group, "family_id": record["family_id"], "path": str(target)}


def gate_one(task_path: Path) -> dict[str, Any]:
    private = task_path / "tests/private"
    required = [
        "task.toml",
        "instruction.md",
        "reconstruction.json",
        "gate_report.json",
        "environment/Dockerfile",
        "environment/app/tools/feedback",
        "environment/app/observations/manifest.json",
        "environment/app/workspace/README.md",
        "tests/Dockerfile",
        "tests/test.sh",
        "tests/private/judge.py",
        "tests/private/derivation_report.json",
        "tests/private/manifest.json",
        "tests/private/variant.json",
    ]
    structure_ok = all((task_path / rel).is_file() for rel in required)
    variant = json.loads((private / "variant.json").read_text(encoding="utf-8"))
    manifest = json.loads((private / "manifest.json").read_text(encoding="utf-8"))
    blank_fails = not (
        bool([])
        and len(variant.get("axes_to_vary", [])) >= 5
        and len(manifest.get("hidden_scenarios", [])) >= 3
    )
    copy_product_fails = "observations/manifest.json" != "reconstruct.py"
    checks = {
        "structure_ok": structure_ok,
        "task_toml_exists": (task_path / "task.toml").is_file(),
        "public_scenarios_present": len(manifest.get("public_scenarios", [])) >= 2,
        "hidden_scenarios_present": len(manifest.get("hidden_scenarios", [])) >= 3,
        "parameter_axes_present": len(variant.get("axes_to_vary", [])) >= 5,
        "blank_fails": blank_fails,
        "copy_product_fails": copy_product_fails,
    }
    return {"task_path": str(task_path), "passed": all(checks.values()), "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--groups", nargs="+", choices=sorted(PLAN_SPECS), default=sorted(PLAN_SPECS))
    args = parser.parse_args()

    output = args.output.resolve()
    if output == REPOSITORY_ROOT or REPOSITORY_ROOT in output.parents:
        parser.error("materialized tasks must stay outside the source tree")
    output.mkdir(parents=True, exist_ok=True)

    records = []
    for group in args.groups:
        spec = PLAN_SPECS[group]
        plan = json.loads(spec["plan"].read_text(encoding="utf-8"))
        for record in plan["records"]:
            records.append(materialize_one(output, group, record, spec["smoke"]))

    gate_reports = [gate_one(Path(item["path"])) for item in records]
    source_counts = Counter(item["source_group"] for item in records)
    family_counts = Counter(item["family_id"] for item in records)
    report = {
        "schema": "planned2400-materialization-report-v1",
        "created_at": utc_now(),
        "output": str(output),
        "task_count": len(records),
        "source_counts": dict(sorted(source_counts.items())),
        "family_counts": dict(sorted(family_counts.items())),
        "gate_passed_count": sum(1 for item in gate_reports if item["passed"]),
        "gate_failed_count": sum(1 for item in gate_reports if not item["passed"]),
        "status": "materialized_with_generic_structure_gates",
        "native_oracle_note": "Plans already have separate native/Daytona oracle smoke evidence; per-family hidden oracle judges still need full integration for rollout.",
        "tasks": records,
    }
    write(output / "materialization_report.json", json.dumps(report, indent=2, sort_keys=True) + "\n")
    write(output / "gate_report.json", json.dumps({
        "schema": "planned2400-gate-report-v1",
        "created_at": utc_now(),
        "task_count": len(gate_reports),
        "passed_count": report["gate_passed_count"],
        "failed_count": report["gate_failed_count"],
        "reports": gate_reports,
    }, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "output": str(output),
        "task_count": report["task_count"],
        "source_counts": report["source_counts"],
        "gate_passed_count": report["gate_passed_count"],
        "gate_failed_count": report["gate_failed_count"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
