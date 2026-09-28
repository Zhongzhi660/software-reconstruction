#!/usr/bin/env python3
"""Install hidden-oracle judges for materialized offcode6 tasks."""

from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = Path("/path/to/software_reconstruction_data").resolve()
DEFAULT_TASK_ROOT = DATA_ROOT / "software_reconstruction/materialized_planned2400_20260828/offcode6"
DEFAULT_RUNNER = (
    Path(__file__).resolve().parents[1]
    / "oracle_validation/validate_offcode6_oracles_daytona.py"
)
DEFAULT_REPORT = (
    DATA_ROOT
    / "software_reconstruction/materialized_planned2400_20260828/offcode6_hidden_oracle_integration_report.json"
)


AUDIO_ORACLE = r'''
def audio(params):
    import numpy as np
    from scipy import signal
    rate = 8000 + int(stable_float(params.get("sample_rate"), 24000))
    window = 128 + int(stable_float(params.get("window_size"), 512))
    cutoff = 300 + int(stable_float(params.get("filter_type"), 1800))
    noise = stable_float(params.get("noise_profile"), 0.08, 0.005)
    phase = stable_float(params.get("channel_layout"), 1.5, 0.1)
    t = np.arange(rate // 8) / rate
    x = np.sin(2 * np.pi * 440 * t) + 0.35 * np.sin(2 * np.pi * (880 + phase * 10) * t)
    x = x + noise * np.cos(2 * np.pi * 123 * t)
    sos = signal.butter(4, min(0.95, cutoff / (rate / 2)), btype="lowpass", output="sos")
    y = signal.sosfilt(sos, x)
    freqs, power = signal.welch(y, fs=rate, nperseg=min(window, len(y)))
    return {
        "rate": rate,
        "window": window,
        "cutoff": cutoff,
        "rms": round(float(np.sqrt(np.mean(y ** 2))), 8),
        "peak_freq": round(float(freqs[int(np.argmax(power))]), 5),
        "power_max": round(float(np.max(power)), 10),
    }
'''


JUDGE = r'''#!/usr/bin/env python3
import argparse
import json
import pathlib
import subprocess
import sys

import offcode6_oracle

EDITABLE_SUFFIXES = {
    ".py", ".json", ".yaml", ".yml", ".toml", ".txt", ".md", ".csv", ".tsv",
    ".xml", ".fasta", ".fa", ".smi", ".mol", ".sdf", ".nii", ".dcm",
    ".cir", ".spice", ".inp", ".wav", ".flac",
}

def load(path):
    return json.loads(pathlib.Path(path).read_text())

def files_under(path):
    return [p for p in path.rglob("*") if p.is_file()]

def candidate_summary(payload):
    if isinstance(payload, dict) and isinstance(payload.get("summary"), dict):
        return payload["summary"]
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        return payload["result"]
    return payload

def run_candidate(entrypoint, scenario):
    proc = subprocess.run(
        [sys.executable, str(entrypoint)],
        input=json.dumps(scenario, sort_keys=True),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=45,
    )
    if proc.returncode != 0:
        return None, {"returncode": proc.returncode, "stderr": proc.stderr[-2000:]}
    try:
        return json.loads(proc.stdout), None
    except Exception as exc:
        return None, {"error": f"candidate stdout is not JSON: {exc}", "stdout": proc.stdout[-2000:]}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=pathlib.Path, default=pathlib.Path("/app/workspace"))
    parser.add_argument("--private", type=pathlib.Path, default=pathlib.Path("/tests/private"))
    args = parser.parse_args()

    variant = load(args.private / "variant.json")
    manifest = load(args.private / "manifest.json")
    family = variant["family_id"]
    hidden = manifest.get("hidden_scenarios", [])
    public = manifest.get("public_scenarios", [])
    files = files_under(args.workspace)
    reconstruct = args.workspace / "reconstruct.py"
    editable = [
        p for p in files
        if p.suffix.lower() in EDITABLE_SUFFIXES or p.name in {"Makefile", "Dockerfile", "README.md"}
    ]
    copied_public = {
        str(p.relative_to(args.workspace))
        for p in files
        if str(p.relative_to(args.workspace)) in {"observations/manifest.json", "manifest.json", "public_observations.json"}
    }
    checks = {
        "workspace_nonempty": bool(files),
        "workspace_has_editable_artifact": bool(editable),
        "has_reconstruct_py": reconstruct.is_file(),
        "does_not_copy_public_products": not copied_public,
        "variant_has_parameter_axes": len(variant.get("axes_to_vary", [])) >= 5,
        "has_public_scenarios": len(public) >= 2,
        "has_hidden_scenarios": len(hidden) >= 3,
        "family_oracle_registered": family in offcode6_oracle.ORACLES,
    }
    details = []
    if all(checks.values()):
        for scenario in hidden:
            try:
                expected = offcode6_oracle.ORACLES[family](scenario["parameters"])
                expected_signature = offcode6_oracle.digest(expected)
            except Exception as exc:
                checks["private_oracle_executes"] = False
                details.append({"scenario_id": scenario.get("scenario_id"), "error": f"oracle failed: {type(exc).__name__}: {exc}"})
                break
            got, error = run_candidate(reconstruct, scenario)
            if error is not None:
                checks["candidate_executes_hidden_scenarios"] = False
                details.append({"scenario_id": scenario.get("scenario_id"), **error})
                break
            summary = candidate_summary(got)
            got_signature = got.get("signature") if isinstance(got, dict) else None
            if got_signature is None:
                got_signature = offcode6_oracle.digest(summary)
            ok = got_signature == expected_signature or summary == expected
            details.append({
                "scenario_id": scenario.get("scenario_id"),
                "passed": ok,
                "expected_signature": expected_signature,
                "candidate_signature": got_signature,
            })
            if not ok:
                checks["candidate_matches_hidden_oracle"] = False
                break
        else:
            checks["private_oracle_executes"] = True
            checks["candidate_executes_hidden_scenarios"] = True
            checks["candidate_matches_hidden_oracle"] = True

    report = {
        "passed": all(checks.values()),
        "checks": checks,
        "copied_public_products": sorted(copied_public),
        "task_id": variant.get("task_id"),
        "family_id": family,
        "details": details,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)

if __name__ == "__main__":
    main()
'''


TEST_DOCKERFILE_SUFFIX = """\
COPY . /tests
RUN chmod +x /tests/test.sh /tests/private/judge.py
WORKDIR /tests
ENV HOME=/tmp LC_ALL=C.UTF-8 PYTHONHASHSEED=0
CMD ["/tests/test.sh"]
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write(path: Path, content: str, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        path.chmod(0o755)


def load_runner_constants(path: Path) -> tuple[dict[str, str], str]:
    module = ast.parse(path.read_text(encoding="utf-8"))
    dockerfiles: dict[str, str] | None = None
    smoke_code: str | None = None
    for node in module.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            value = node.value
        else:
            continue
        if value is None:
            continue
        if isinstance(target, ast.Name) and target.id == "DOCKERFILES":
            dockerfiles = ast.literal_eval(value)
        if isinstance(target, ast.Name) and target.id == "SMOKE_CODE":
            smoke_code = ast.literal_eval(value)
    if dockerfiles is None or smoke_code is None:
        raise RuntimeError(f"failed to extract constants from {path}")
    prefix = smoke_code.split("\nrecords = []", 1)[0]
    prefix = prefix.replace('FAMILY = os.environ["FAMILY"]\nRECORDS = json.loads(Path("/tmp/records.json").read_text())\n', "")
    prefix = prefix.rstrip() + "\n" + AUDIO_ORACLE + "\nORACLES[\"audio_signal_processing\"] = audio\n"
    dockerfiles["audio_signal_processing"] = """\
FROM python:3.11-slim
RUN pip install --no-cache-dir numpy scipy
"""
    return dockerfiles, prefix


def dockerfile_for(base: str) -> str:
    return base.strip() + "\n" + TEST_DOCKERFILE_SUFFIX


def integrate_task(task: Path, dockerfiles: dict[str, str], oracle_source: str) -> dict[str, Any]:
    variant_path = task / "tests/private/variant.json"
    if not variant_path.is_file():
        return {"task": str(task), "updated": False, "error": "missing variant.json"}
    variant = json.loads(variant_path.read_text(encoding="utf-8"))
    family = variant["family_id"]
    if family not in dockerfiles:
        return {"task": str(task), "updated": False, "family_id": family, "error": "missing dockerfile"}
    write(task / "tests/private/offcode6_oracle.py", oracle_source)
    write(task / "tests/private/judge.py", JUDGE, executable=True)
    write(task / "tests/Dockerfile", dockerfile_for(dockerfiles[family]))
    marker = {
        "task_id": task.name,
        "family_id": family,
        "integrated_at": utc_now(),
        "judge": "offcode6 hidden native-oracle adapter",
        "hidden_scenario_count": len(variant.get("hidden_scenarios", [])),
    }
    write(task / "tests/private/offcode6_oracle_integration.json", json.dumps(marker, indent=2, sort_keys=True) + "\n")
    return {"task": str(task), "updated": True, "family_id": family}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-root", type=Path, default=DEFAULT_TASK_ROOT)
    parser.add_argument("--runner", type=Path, default=DEFAULT_RUNNER)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--limit-per-family", type=int, default=0, help="0 means all tasks")
    args = parser.parse_args()

    task_root = args.task_root.resolve()
    if task_root == REPOSITORY_ROOT or REPOSITORY_ROOT in task_root.parents:
        parser.error("task root must stay outside the source tree")
    dockerfiles, oracle_source = load_runner_constants(args.runner)
    tasks = sorted(path for path in task_root.iterdir() if (path / "tests/private/variant.json").is_file())
    if args.limit_per_family:
        selected = []
        seen: Counter[str] = Counter()
        for task in tasks:
            variant = json.loads((task / "tests/private/variant.json").read_text(encoding="utf-8"))
            family = variant["family_id"]
            if seen[family] < args.limit_per_family:
                selected.append(task)
                seen[family] += 1
        tasks = selected
    results = [integrate_task(task, dockerfiles, oracle_source) for task in tasks]
    updated = [item for item in results if item.get("updated")]
    family_counts = Counter(item["family_id"] for item in updated)
    report = {
        "schema": "offcode6-hidden-oracle-integration-v1",
        "created_at": utc_now(),
        "task_root": str(task_root),
        "runner": str(args.runner),
        "selected_task_count": len(tasks),
        "updated_count": len(updated),
        "failed_count": len(results) - len(updated),
        "family_counts": dict(sorted(family_counts.items())),
        "results": results,
    }
    write(args.report, json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: report[k] for k in ("selected_task_count", "updated_count", "failed_count", "family_counts")}, indent=2, sort_keys=True))
    return 0 if report["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
