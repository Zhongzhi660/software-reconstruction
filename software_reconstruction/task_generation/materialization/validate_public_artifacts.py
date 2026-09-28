#!/usr/bin/env python3
"""Validate that public artifacts are faithful to public oracle outputs.

This is a release-blocking gate for regenerated reconstruction tasks. It checks
for the failure mode found in the rejected 2400-task batch: files that look
native by extension but were not produced by the same oracle/software execution
that produced oracle_output.json.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import tarfile
import wave
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DEFAULT_TASK_ROOT = Path(
    "/path/to/software_reconstruction_data/"
    "software_reconstruction/materialized_planned2400_20260828"
)
DEFAULT_GROUPS = ("new10", "offcode6", "offcode20")
METADATA_NAMES = {
    "public_manifest.json",
    "scenario.json",
    "oracle_output.json",
    "signature.json",
    "artifact_manifest.json",
}
TOOL_HEAVY_FAMILIES = {
    "astronomy_fits_photometry",
    "audio_signal_processing",
    "circuit_simulation",
    "climate_netcdf_analysis",
    "finite_element_mechanics",
    "materials_crystallography",
    "medical_imaging",
    "microscopy_cell_analysis",
    "music_score_engraving",
    "point_cloud_lidar",
    "proteomics_mass_spectrometry",
    "samtools_bio_qc",
    "structural_biology_pdb",
    "video_broadcast_qc",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_json_member(tar: tarfile.TarFile, name: str) -> Any:
    handle = tar.extractfile(name)
    if handle is None:
        return None
    return json.loads(handle.read().decode("utf-8"))


def add_issue(
    issues: list[dict[str, Any]],
    task: str,
    group: str,
    family: str,
    code: str,
    detail: Any = None,
    severity: str = "high",
) -> None:
    issues.append(
        {
            "task": task,
            "group": group,
            "family": family,
            "issue": code,
            "severity": severity,
            "detail": detail,
        }
    )


def fasta_length(text: str) -> int:
    return len("".join(line.strip() for line in text.splitlines() if not line.startswith(">")))


def pdb_atom_count(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.startswith(("ATOM", "HETATM")))


def wav_header(data: bytes) -> tuple[int | None, int | None]:
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            return wav.getframerate(), wav.getnframes()
    except Exception:
        return None, None


def ply_vertex_count(text: str) -> int | None:
    match = re.search(r"element vertex\s+(\d+)", text)
    return int(match.group(1)) if match else None


def member_text(tar: tarfile.TarFile, name: str) -> str:
    handle = tar.extractfile(name)
    if handle is None:
        return ""
    return handle.read().decode("utf-8", errors="replace")


def member_bytes(tar: tarfile.TarFile, name: str) -> bytes:
    handle = tar.extractfile(name)
    if handle is None:
        return b""
    return handle.read()


def validate_scenario_artifacts(
    *,
    tar: tarfile.TarFile,
    names: set[str],
    scenario_id: str,
    task: str,
    group: str,
    family: str,
    issues: list[dict[str, Any]],
) -> None:
    output = read_json_member(tar, f"{scenario_id}/oracle_output.json") or {}
    summary = output.get("summary", output) if isinstance(output, dict) else {}
    native = [
        name
        for name in names
        if name.startswith(f"{scenario_id}/") and Path(name).name not in METADATA_NAMES
    ]
    if not native:
        add_issue(issues, task, group, family, "missing_native_public_artifacts", {"scenario": scenario_id})

    if family == "samtools_bio_qc":
        fasta_name = f"{scenario_id}/bio/public_sequence.fasta"
        if fasta_name in names and isinstance(summary, dict):
            observed = fasta_length(member_text(tar, fasta_name))
            expected = summary.get("reference_length")
            if isinstance(expected, int) and abs(expected - observed) > 10:
                add_issue(
                    issues,
                    task,
                    group,
                    family,
                    "public_fasta_length_mismatch",
                    {"scenario": scenario_id, "oracle_reference_length": expected, "fasta_length": observed},
                )

    if family == "structural_biology_pdb":
        pdb_name = f"{scenario_id}/structure/public_model.pdb"
        if pdb_name in names and isinstance(summary, dict):
            observed = pdb_atom_count(member_text(tar, pdb_name))
            expected = summary.get("atoms")
            if isinstance(expected, int) and expected != observed:
                add_issue(
                    issues,
                    task,
                    group,
                    family,
                    "public_pdb_atom_count_mismatch",
                    {"scenario": scenario_id, "oracle_atoms": expected, "pdb_atom_lines": observed},
                )

    if family == "audio_signal_processing":
        wav_name = f"{scenario_id}/signals/public_waveform.wav"
        if wav_name in names and isinstance(summary, dict):
            rate, frames = wav_header(member_bytes(tar, wav_name))
            expected = summary.get("rate")
            if isinstance(expected, int) and rate != expected:
                add_issue(
                    issues,
                    task,
                    group,
                    family,
                    "public_wav_rate_mismatch",
                    {"scenario": scenario_id, "oracle_rate": expected, "wav_rate": rate, "frames": frames},
                )

    if family == "proteomics_mass_spectrometry":
        fasta_name = f"{scenario_id}/proteomics/protein_sequence.fasta"
        if fasta_name in names and isinstance(summary, dict):
            sequence = "".join(
                line.strip()
                for line in member_text(tar, fasta_name).splitlines()
                if not line.startswith(">")
            )
            observed = hashlib.sha256(sequence.encode()).hexdigest()[:12]
            expected = summary.get("sequence_digest")
            if expected and observed != expected:
                add_issue(
                    issues,
                    task,
                    group,
                    family,
                    "public_protein_sequence_digest_mismatch",
                    {"scenario": scenario_id, "oracle_digest": expected, "fasta_digest": observed},
                )

    if family == "point_cloud_lidar":
        ply_name = f"{scenario_id}/point_cloud/public_cloud.ply"
        if ply_name in names and isinstance(summary, dict):
            observed = ply_vertex_count(member_text(tar, ply_name))
            expected = summary.get("points")
            if isinstance(expected, int) and observed != expected:
                add_issue(
                    issues,
                    task,
                    group,
                    family,
                    "public_point_cloud_count_mismatch",
                    {"scenario": scenario_id, "oracle_points": expected, "ply_vertices": observed},
                )

    if family == "climate_netcdf_analysis" and not any(
        name.startswith(f"{scenario_id}/climate/") and name.endswith(".nc") for name in names
    ):
        add_issue(issues, task, group, family, "no_public_netcdf_file", {"scenario": scenario_id}, "medium")


def validate_task(task_dir: Path, group: str, issues: list[dict[str, Any]]) -> dict[str, Any]:
    manifest = load_json(task_dir / "tests/private/manifest.json")
    family = manifest.get("family_id", "unknown")
    axes = manifest.get("effective_axes_to_vary") or manifest.get("axes_to_vary") or []
    public = manifest.get("public_scenarios") or []
    hidden = manifest.get("hidden_scenarios") or []
    docker = (task_dir / "environment/Dockerfile").read_text(encoding="utf-8", errors="replace")
    row = {
        "task": task_dir.name,
        "group": group,
        "family": family,
        "axes": len(axes),
        "public_scenarios": len(public),
        "hidden_scenarios": len(hidden),
        "tar_size": None,
    }

    if len(public) < max(3, len(axes) + 1):
        add_issue(
            issues,
            task_dir.name,
            group,
            family,
            "insufficient_public_scenario_coverage",
            {"public": len(public), "axes": len(axes), "required_minimum": max(3, len(axes) + 1)},
        )

    installs_stack = "RUN apt-get" in docker or "pip install" in docker or "uv pip install" in docker
    if "FROM python:3.11-slim" in docker and not installs_stack:
        add_issue(issues, task_dir.name, group, family, "bare_python_environment", severity="high")
    if family in TOOL_HEAVY_FAMILIES and not installs_stack:
        add_issue(
            issues,
            task_dir.name,
            group,
            family,
            "declared_tool_stack_not_installed",
            {"software": manifest.get("software")},
        )

    tar_path = task_dir / "environment/app/observations/reference_outputs.tar.gz"
    if not tar_path.exists():
        add_issue(issues, task_dir.name, group, family, "missing_reference_outputs_tar")
        return row
    row["tar_size"] = tar_path.stat().st_size
    try:
        with tarfile.open(tar_path, "r:gz") as tar:
            names = {member.name for member in tar.getmembers() if member.isfile()}
            hidden_members = [name for name in names if name.startswith("hidden") or "/hidden" in name]
            if hidden_members:
                add_issue(
                    issues,
                    task_dir.name,
                    group,
                    family,
                    "hidden_leak_in_public_tar",
                    {"sample": hidden_members[:5]},
                    "critical",
                )
            for scenario_id in ["public_1", "public_2"]:
                validate_scenario_artifacts(
                    tar=tar,
                    names=names,
                    scenario_id=scenario_id,
                    task=task_dir.name,
                    group=group,
                    family=family,
                    issues=issues,
                )
    except Exception as exc:
        add_issue(issues, task_dir.name, group, family, "bad_reference_outputs_tar", repr(exc))
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-root", type=Path, default=DEFAULT_TASK_ROOT)
    parser.add_argument("--groups", nargs="+", default=list(DEFAULT_GROUPS))
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--fail-on-issues", action="store_true")
    args = parser.parse_args()

    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for group in args.groups:
        group_root = args.task_root / group
        for task_dir in sorted(path for path in group_root.iterdir() if path.is_dir()):
            rows.append(validate_task(task_dir, group, issues))

    issue_counts = Counter(issue["issue"] for issue in issues)
    by_group: dict[str, Counter[str]] = defaultdict(Counter)
    by_family: dict[str, Counter[str]] = defaultdict(Counter)
    for issue in issues:
        by_group[issue["group"]][issue["issue"]] += 1
        by_family[issue["family"]][issue["issue"]] += 1

    report = {
        "schema": "public-artifact-faithfulness-gate-v1",
        "task_root": str(args.task_root),
        "groups": args.groups,
        "task_count": len(rows),
        "issue_count": len(issues),
        "issue_counts": dict(issue_counts),
        "issue_counts_by_group": {key: dict(value) for key, value in sorted(by_group.items())},
        "issue_counts_by_family": {key: dict(value) for key, value in sorted(by_family.items())},
        "issue_samples": issues[:200],
        "rows": rows,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["task_count", "issue_count", "issue_counts"]}, indent=2, sort_keys=True))
    print(f"report={args.report}")
    return 1 if args.fail_on_issues and issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
