#!/usr/bin/env python3
"""Reject V1 repair tasks and validate V2 reconstruction task contracts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

FAMILIES = {
    "database_cache_recovery",
    "web_messaging_dns",
    "ops_network_storage",
    "gis_geospatial",
    "code_build_language_tooling",
    "bioinformatics_variant_qc",
    "k8s_policy_api_config",
    "container_supply_chain",
    "scientific_engineering_simulation",
    "formal_solver_proof",
    "network_security",
    "crypto_forensics",
    "data_sql_reporting",
    "document_ocr_publishing",
    "eda_hdl_pcb",
    "audio_video_processing",
    "music_audio_analysis",
    "cad_3d_manufacturing",
    "schema_contract_validation",
    "layout_image_reconstruction",
    "graph_diagram_reconstruction",
    "data_visualization_reconstruction",
    "audio_processing_reconstruction",
    "image_pipeline_reconstruction",
    "document_publishing_reconstruction",
    "xml_transform_reconstruction",
    "sql_report_reconstruction",
    "dynamic_system_reconstruction",
    "geospatial_pipeline_reconstruction",
    "scientific_plot_reconstruction",
    "openscad_parametric_cad",
    "blender_scene_graph",
    "web_ui_state_machine",
    "openfoam_cfd",
    "verilog_rtl",
    "kicad_pcb",
    "cmake_build_config",
    "nginx_routing",
    "tree_sitter_grammar",
    "openssl_pki",
    "sqlite_analytics",
    "ajv_schema",
    "z3_constraint_system",
    "duckdb_reporting",
    "opa_rego_policy",
    "container_supply_chain",
    "gdal_geospatial",
    "network_security_pcap",
    "document_ocr_publishing",
    "samtools_bio_qc",
    "audio_signal_processing",
    "robotics_control",
    "molecular_chemistry",
    "medical_imaging",
    "circuit_simulation",
    "finite_element_mechanics",
    "astronomy_fits_photometry",
    "seismology_waveform_processing",
    "climate_netcdf_analysis",
    "materials_crystallography",
    "proteomics_mass_spectrometry",
    "phylogenetics_tree_reconstruction",
    "music_score_engraving",
    "video_broadcast_qc",
    "point_cloud_lidar",
    "power_grid_simulation",
    "rf_signal_processing",
    "cartography_map_rendering",
    "typography_font_shaping",
    "color_imaging_pipeline",
    "microscopy_cell_analysis",
    "structural_biology_pdb",
    "acoustics_room_simulation",
    "hydrology_raster_modeling",
    "geology_well_log_analysis",
    "transport_gtfs_schedule",
}

REQUIRED_GATES = {
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
}

REPAIR_LANGUAGE = re.compile(
    r"\b(repair|restore|unmask|undo damage|damaged (?:file|artifact|source))\b",
    re.IGNORECASE,
)
SOURCE_HASH_JUDGE = re.compile(
    r"(?:candidate|workspace|source).{0,80}(?:sha256|source_hash|read_bytes)"
    r"|(?:sha256|source_hash).{0,80}(?:candidate|workspace|source)",
    re.IGNORECASE | re.DOTALL,
)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain an object")
    return value


def nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def require_strings(
    obj: dict[str, Any], keys: tuple[str, ...], prefix: str, errors: list[str]
) -> None:
    for key in keys:
        if not nonempty_string(obj.get(key)):
            errors.append(f"{prefix}.{key} must be a non-empty string")


def visible_files(environment: Path) -> list[Path]:
    if not environment.is_dir():
        return []
    return [path for path in environment.rglob("*") if path.is_file()]


def inspect_task(metadata_path: Path) -> dict[str, Any]:
    task = metadata_path.parent
    errors: list[str] = []
    try:
        meta = read_json(metadata_path)
    except Exception as exc:
        return {
            "task": str(task),
            "task_id": task.name,
            "family": "",
            "valid": False,
            "errors": [f"invalid reconstruction.json: {exc}"],
        }

    task_id = str(meta.get("task_id") or task.name)
    family = str(meta.get("family") or "")
    if meta.get("schema_version") != "2.0":
        errors.append("schema_version must be 2.0")
    if meta.get("mode") != "software_in_loop_reconstruction":
        errors.append("mode must be software_in_loop_reconstruction")
    if family not in FAMILIES:
        errors.append(f"unknown family: {family!r}")

    required_files = (
        "task.toml",
        "instruction.md",
        "environment/Dockerfile",
        "environment/app/tools/feedback",
        "tests/Dockerfile",
        "tests/test.sh",
        "tests/private/judge.py",
        "tests/private/derivation_report.json",
        "gate_report.json",
    )
    for relative in required_files:
        if not (task / relative).is_file():
            errors.append(f"missing {relative}")

    parent = meta.get("parent")
    if not isinstance(parent, dict):
        errors.append("parent must be an object")
        parent = {}
    require_strings(
        parent,
        ("source_url", "revision", "sha256", "license", "attribution"),
        "parent",
        errors,
    )

    software = meta.get("software")
    if not isinstance(software, dict):
        errors.append("software must be an object")
        software = {}
    require_strings(software, ("name", "version", "command"), "software", errors)
    if not (
        nonempty_string(software.get("image_digest"))
        or nonempty_string(software.get("binary_sha256"))
    ):
        errors.append("software requires image_digest or binary_sha256")

    derivation = meta.get("target_derivation")
    if not isinstance(derivation, dict):
        errors.append("target_derivation must be an object")
        derivation = {}
    public_scenarios = derivation.get("public_scenarios")
    hidden_scenarios = derivation.get("hidden_scenarios")
    public_files = derivation.get("public_observation_files")
    if not isinstance(public_scenarios, list) or len(public_scenarios) < 2:
        errors.append("at least two public scenarios are required")
    if not isinstance(hidden_scenarios, list) or len(hidden_scenarios) < 2:
        errors.append("at least two hidden scenarios are required")
    if not isinstance(public_files, list) or not public_files:
        errors.append("public_observation_files must be a non-empty list")
    else:
        for relative in public_files:
            path = task / str(relative)
            if not path.is_file():
                errors.append(f"missing public observation: {relative}")
            elif (task / "environment/app/observations") not in path.parents:
                errors.append(f"public observation outside observations/: {relative}")

    candidate = meta.get("candidate")
    if not isinstance(candidate, dict):
        errors.append("candidate must be an object")
        candidate = {}
    require_strings(candidate, ("path", "editable_format"), "candidate", errors)
    if candidate.get("starter_policy") not in {"blank", "independent_scaffold"}:
        errors.append("candidate.starter_policy must be blank or independent_scaffold")
    candidate_path = candidate.get("path")
    if nonempty_string(candidate_path):
        relative_candidate = str(candidate_path).removeprefix("/app/")
        if not (task / "environment/app" / relative_candidate).exists():
            errors.append(f"candidate path does not exist: {candidate_path}")

    feedback = meta.get("feedback")
    if not isinstance(feedback, dict):
        errors.append("feedback must be an object")
        feedback = {}
    require_strings(feedback, ("command",), "feedback", errors)
    metrics = feedback.get("metrics")
    if not isinstance(metrics, list) or len(metrics) < 2:
        errors.append("feedback requires at least two metrics")
    if feedback.get("graded") is not True:
        errors.append("feedback.graded must be true")
    if feedback.get("executes_candidate") is not True:
        errors.append("feedback.executes_candidate must be true")

    judge = meta.get("judge")
    if not isinstance(judge, dict):
        errors.append("judge must be an object")
        judge = {}
    if judge.get("behavior_only") is not True:
        errors.append("judge.behavior_only must be true")
    if judge.get("candidate_source_equality_forbidden") is not True:
        errors.append("judge.candidate_source_equality_forbidden must be true")

    instruction_path = task / "instruction.md"
    if instruction_path.is_file():
        instruction = instruction_path.read_text(encoding="utf-8", errors="replace")
        if REPAIR_LANGUAGE.search(instruction):
            errors.append("instruction uses prohibited V1 repair language")

    environment = task / "environment"
    parent_sha = str(parent.get("sha256") or "").encode()
    source_url = str(parent.get("source_url") or "").encode()
    for path in visible_files(environment):
        data = path.read_bytes()
        relative = path.relative_to(task)
        if parent_sha and parent_sha in data:
            errors.append(f"parent hash leaked in {relative}")
        if source_url and source_url in data:
            errors.append(f"parent URL leaked in {relative}")
        if "oracle" in str(relative).lower() or "private" in str(relative).lower():
            errors.append(f"private/oracle naming leaked in {relative}")

    judge_path = task / "tests/private/judge.py"
    if judge_path.is_file():
        judge_text = judge_path.read_text(encoding="utf-8", errors="replace")
        if SOURCE_HASH_JUDGE.search(judge_text):
            errors.append("private judge appears to hash candidate source")

    test_path = task / "tests/test.sh"
    if test_path.is_file():
        test_text = test_path.read_text(encoding="utf-8", errors="replace")
        if "/logs/verifier/reward.txt" not in test_text:
            errors.append("test.sh does not write Harbor reward.txt")

    gate_path = task / "gate_report.json"
    if gate_path.is_file():
        try:
            gate = read_json(gate_path)
            if gate.get("passed") is not True:
                errors.append("gate_report.passed is not true")
            checks = gate.get("checks")
            if not isinstance(checks, dict):
                errors.append("gate_report.checks must be an object")
            else:
                missing = sorted(
                    check for check in REQUIRED_GATES if checks.get(check) is not True
                )
                if missing:
                    errors.append(f"missing or failed gates: {', '.join(missing)}")
        except Exception as exc:
            errors.append(f"invalid gate_report.json: {exc}")

    return {
        "task": str(task.resolve()),
        "task_id": task_id,
        "family": family,
        "valid": not errors,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--require-pilots", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    metadata_files = sorted(args.root.rglob("reconstruction.json"))
    records = [inspect_task(path) for path in metadata_files]
    valid = [record for record in records if record["valid"]]
    counts = Counter(record["family"] for record in valid)
    errors: list[str] = []
    if not records:
        errors.append("no V2 reconstruction tasks found")
    if args.require_pilots:
        missing = sorted(FAMILIES - set(counts))
        extra = sorted(family for family, count in counts.items() if count != 1)
        if missing:
            errors.append(f"missing pilot families: {', '.join(missing)}")
        if extra:
            errors.append(f"pilot families with count != 1: {', '.join(extra)}")

    report = {
        "schema_version": "2.0",
        "root": str(args.root.resolve()),
        "discovered": len(records),
        "valid": len(valid),
        "counts": dict(sorted(counts.items())),
        "valid_contract": len(valid) == len(records) and not errors,
        "global_errors": errors,
        "invalid_tasks": [record for record in records if not record["valid"]],
    }
    output = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output)
    print(output, end="")
    return 0 if report["valid_contract"] else 1


if __name__ == "__main__":
    sys.exit(main())
