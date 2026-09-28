#!/usr/bin/env python3
"""Private behavior verifier for OpenSCAD reconstruction tasks."""

from __future__ import annotations

import argparse
import importlib
import json
import pathlib
import subprocess
import sys

from openscad_geometry import (
    compare_stl,
    geometry_fingerprint,
    load_triangles,
    metrics_for_stl,
)


EDITABLE_SUFFIXES = {
    ".py",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".txt",
    ".md",
    ".scad",
}
STANDARD_ARTIFACT_PATHS = (
    "product.stl",
    "output/product.stl",
    "outputs/product.stl",
)


def load(path: pathlib.Path):
    return json.loads(path.read_text())


def candidate_summary(payload):
    if isinstance(payload, dict) and isinstance(payload.get("summary"), dict):
        return payload["summary"]
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        return payload["result"]
    return payload


def _declared_artifact(payload):
    if not isinstance(payload, dict):
        return None
    for key in ("artifact_path", "stl_path"):
        if isinstance(payload.get(key), str):
            return payload[key]
    summary = candidate_summary(payload)
    if isinstance(summary, dict):
        artifact = summary.get("artifact")
        if isinstance(artifact, dict) and isinstance(artifact.get("path"), str):
            return artifact["path"]
    return None


def _safe_workspace_path(workspace: pathlib.Path, raw_path: str):
    candidate = pathlib.Path(raw_path)
    if not candidate.is_absolute():
        candidate = workspace / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(workspace.resolve())
    except ValueError:
        return None
    return resolved


def run_candidate(entrypoint, workspace, scenario):
    for relative in STANDARD_ARTIFACT_PATHS:
        path = workspace / relative
        if path.is_file():
            path.unlink()
    proc = subprocess.run(
        [sys.executable, str(entrypoint)],
        input=json.dumps(scenario, sort_keys=True),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=180,
        cwd=workspace,
    )
    if proc.returncode != 0:
        return None, None, {
            "returncode": proc.returncode,
            "stderr": proc.stderr[-2000:],
        }
    try:
        payload = json.loads(proc.stdout)
    except Exception as exc:
        return None, None, {
            "error": f"candidate stdout is not JSON: {exc}",
            "stdout": proc.stdout[-2000:],
        }
    paths = []
    declared = _declared_artifact(payload)
    if declared:
        safe = _safe_workspace_path(workspace, declared)
        if safe is not None:
            paths.append(safe)
    paths.extend(workspace / relative for relative in STANDARD_ARTIFACT_PATHS)
    artifact = next((path for path in paths if path.is_file()), None)
    if artifact is None:
        return payload, None, {
            "error": "candidate did not create product.stl inside the workspace",
            "accepted_paths": list(STANDARD_ARTIFACT_PATHS),
        }
    return payload, artifact, None


def geometry_signature(path):
    return geometry_fingerprint(load_triangles(path))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workspace", type=pathlib.Path, default=pathlib.Path("/app/workspace")
    )
    parser.add_argument(
        "--private", type=pathlib.Path, default=pathlib.Path("/tests/private")
    )
    parser.add_argument(
        "--observations",
        type=pathlib.Path,
        default=pathlib.Path("/app/observations"),
    )
    args = parser.parse_args()

    variant = load(args.private / "variant.json")
    manifest = load(args.private / "manifest.json")
    hidden = manifest.get("hidden_scenarios", [])
    public = manifest.get("public_scenarios", [])
    files = [path for path in args.workspace.rglob("*") if path.is_file()]
    reconstruct = args.workspace / "reconstruct.py"
    editable = [
        path
        for path in files
        if path.suffix.lower() in EDITABLE_SUFFIXES
        or path.name in {"Makefile", "Dockerfile", "README.md", "project.json"}
    ]
    checks = {
        "workspace_nonempty": bool(files),
        "workspace_has_editable_artifact": bool(editable),
        "has_reconstruct_py": reconstruct.is_file(),
        "variant_has_parameter_axes": len(variant.get("axes_to_vary", [])) >= 3,
        "has_public_scenarios": len(public) >= 2,
        "has_hidden_scenarios": len(hidden) >= 2,
    }
    details = []
    candidate_signatures = []
    expected_signatures = []

    if all(checks.values()):
        sys.path.insert(0, str(args.private))
        oracle_names = [
            path.stem for path in args.private.glob("*_oracle.py")
        ]
        checks["private_oracle_available"] = bool(oracle_names)
        oracle = importlib.import_module(oracle_names[0]) if oracle_names else None
        for scenario in hidden:
            scenario_id = scenario.get("scenario_id")
            reference = args.private / "reference_meshes" / f"{scenario_id}.stl"
            if not reference.is_file():
                checks["private_reference_meshes_available"] = False
                details.append(
                    {
                        "scenario_id": scenario_id,
                        "error": "private reference STL is missing",
                    }
                )
                break
            checks["private_reference_meshes_available"] = True
            reference_metrics = metrics_for_stl(reference)
            expected_signatures.append(geometry_signature(reference))
            if oracle is not None:
                try:
                    oracle_output = candidate_summary(
                        oracle.ORACLES[variant["family_id"]](scenario["parameters"])
                    )
                    oracle_metrics = oracle_output["geometry"]
                    checks["private_oracle_matches_reference_mesh"] = (
                        oracle_metrics == reference_metrics
                    )
                except Exception as exc:
                    checks["private_oracle_matches_reference_mesh"] = False
                    details.append(
                        {
                            "scenario_id": scenario_id,
                            "error": f"oracle failed: {type(exc).__name__}: {exc}",
                        }
                    )
                    break
            payload, artifact, error = run_candidate(
                reconstruct, args.workspace, scenario
            )
            if error is not None:
                checks["candidate_executes_hidden_scenarios"] = False
                details.append({"scenario_id": scenario_id, **error})
                break
            try:
                comparison = compare_stl(artifact, reference)
            except Exception as exc:
                checks["candidate_generates_valid_stl"] = False
                details.append(
                    {
                        "scenario_id": scenario_id,
                        "error": f"invalid STL: {type(exc).__name__}: {exc}",
                    }
                )
                break
            checks["candidate_generates_valid_stl"] = True
            candidate_signatures.append(geometry_signature(artifact))
            details.append(
                {
                    "scenario_id": scenario_id,
                    "passed": comparison["passed"],
                    "artifact_path": str(artifact),
                    "geometry_comparison": comparison,
                }
            )
            if not comparison["passed"]:
                checks["candidate_matches_hidden_geometry"] = False
                break
        else:
            checks["candidate_executes_hidden_scenarios"] = True
            checks["candidate_matches_hidden_geometry"] = True

    if expected_signatures and len(set(expected_signatures)) > 1:
        checks["candidate_geometry_varies_on_hidden"] = (
            len(candidate_signatures) == len(hidden)
            and len(set(candidate_signatures)) > 1
        )

    report = {
        "passed": all(checks.values()),
        "checks": checks,
        "task_id": variant.get("task_id"),
        "family_id": variant.get("family_id"),
        "details": details,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
