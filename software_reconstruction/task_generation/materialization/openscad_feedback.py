#!/usr/bin/env python3
"""Public geometry feedback for OpenSCAD reconstruction tasks."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tarfile
import tempfile

from openscad_geometry import compare_stl


WORKSPACE = pathlib.Path("/app/workspace")
OBSERVATIONS = pathlib.Path("/app/observations")


def run_candidate(scenario):
    artifact = WORKSPACE / "product.stl"
    if artifact.is_file():
        artifact.unlink()
    process = subprocess.run(
        [sys.executable, str(WORKSPACE / "reconstruct.py")],
        input=json.dumps(scenario, sort_keys=True),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=180,
        cwd=WORKSPACE,
    )
    if process.returncode != 0:
        return None, {
            "returncode": process.returncode,
            "stderr": process.stderr[-2000:],
        }
    try:
        payload = json.loads(process.stdout)
    except Exception as exc:
        return None, {"error": f"stdout is not JSON: {exc}"}
    declared = payload.get("artifact_path") if isinstance(payload, dict) else None
    candidates = [artifact, WORKSPACE / "output/product.stl"]
    if isinstance(declared, str):
        path = pathlib.Path(declared)
        candidates.insert(0, path if path.is_absolute() else WORKSPACE / path)
    candidate = next((path for path in candidates if path.is_file()), None)
    if candidate is None:
        return None, {"error": "reconstruct.py did not create product.stl"}
    try:
        candidate.resolve().relative_to(WORKSPACE.resolve())
    except ValueError:
        return None, {"error": "artifact path must remain inside /app/workspace"}
    return candidate, None


def main():
    archive = OBSERVATIONS / "reference_outputs.tar.gz"
    with tarfile.open(archive, "r:gz") as handle:
        public_manifest = json.loads(
            handle.extractfile("public_manifest.json").read().decode("utf-8")
        )
        with tempfile.TemporaryDirectory(prefix="openscad_feedback_") as temporary:
            temporary_path = pathlib.Path(temporary)
            details = []
            for scenario in public_manifest.get("public_scenarios", []):
                scenario_id = scenario["scenario_id"]
                member = handle.extractfile(f"{scenario_id}/native/product.stl")
                reference = temporary_path / f"{scenario_id}.stl"
                reference.write_bytes(member.read())
                candidate, error = run_candidate(scenario)
                if error is not None:
                    details.append({"scenario_id": scenario_id, **error})
                    continue
                comparison = compare_stl(candidate, reference)
                details.append(
                    {
                        "scenario_id": scenario_id,
                        "passed": comparison["passed"],
                        "geometry_comparison": comparison,
                    }
                )
    passed = bool(details) and all(item.get("passed") for item in details)
    print(json.dumps({"passed": passed, "details": details}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
