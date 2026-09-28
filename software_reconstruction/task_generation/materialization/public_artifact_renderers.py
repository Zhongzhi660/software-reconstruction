#!/usr/bin/env python3
"""Render structured public artifacts for reconstruction tasks.

This script does not modify task directories. It samples tasks, reads their
existing public oracle payloads, and writes richer agent-visible tarballs under
a separate smoke output directory. The goal is to validate the repair direction
before rebuilding all public artifacts in place.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import importlib.util
import io
import json
import math
import random
import struct
import tarfile
import textwrap
import wave
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_ROOT = Path("/path/to/software_reconstruction_data")
TASK_ROOT = DATA_ROOT / "software_reconstruction/materialized_planned2400_20260828"
DEFAULT_OUTPUT_ROOT = TASK_ROOT / "rich_public_artifact_smoke_20260830"
GROUPS = ("new10", "offcode6", "offcode20")

META_NAMES = {
    "public_manifest.json",
    "scenario.json",
    "signature.json",
    "oracle_output.json",
    "observation_summary.json",
    "artifact_manifest.json",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")


def text_bytes(text: str) -> bytes:
    return text.encode("utf-8")


def add_bytes(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mtime = 0
    info.mode = 0o644
    tar.addfile(info, io.BytesIO(data))


def add_json(tar: tarfile.TarFile, name: str, payload: Any) -> None:
    add_bytes(tar, name, json_bytes(payload))


def add_text(tar: tarfile.TarFile, name: str, text: str) -> None:
    add_bytes(tar, name, text_bytes(text))


def flatten_rows(value: Any, prefix: str = "") -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key in sorted(value):
            rows.extend(flatten_rows(value[key], f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            rows.extend(flatten_rows(item, f"{prefix}[{idx}]"))
    else:
        rows.append((prefix, str(value)))
    return rows


def csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    out = io.StringIO()
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    writer = csv.DictWriter(out, fieldnames=keys or ["key", "value"])
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in keys})
    return out.getvalue().encode("utf-8")


def generic_report(family: str, scenario_id: str, params: dict[str, Any], output: Any) -> str:
    lines = [
        f"family: {family}",
        f"scenario_id: {scenario_id}",
        "parameters:",
    ]
    for key in sorted(params):
        lines.append(f"  - {key}: {params[key]}")
    lines.append("oracle output:")
    for key, value in flatten_rows(output):
        lines.append(f"  - {key}: {value}")
    return "\n".join(lines) + "\n"


def rows_from_output(output: Any) -> list[dict[str, Any]]:
    rows = flatten_rows(output)
    return [{"metric": key, "value": value} for key, value in rows]


def observed_summary(output: Any) -> Any:
    if isinstance(output, dict) and "summary" in output:
        return output["summary"]
    return output


def table_csv_from_rows(rows: Any, headers: list[str] | None = None) -> bytes:
    if not isinstance(rows, list):
        return csv_bytes(rows_from_output(rows))
    out = io.StringIO()
    width = 0
    for row in rows:
        if isinstance(row, (list, tuple)):
            width = max(width, len(row))
        elif isinstance(row, dict):
            width = max(width, len(row))
    if headers is None:
        headers = [f"col_{idx}" for idx in range(width or 1)]
    writer = csv.writer(out)
    writer.writerow(headers)
    for row in rows:
        if isinstance(row, dict):
            writer.writerow([row.get(h, "") for h in headers])
        elif isinstance(row, (list, tuple)):
            writer.writerow(list(row))
        else:
            writer.writerow([row])
    return out.getvalue().encode("utf-8")


def wav_bytes(seed_text: str, sample_rate: int = 8000, seconds: float = 0.25) -> bytes:
    seed = int(hashlib.sha256(seed_text.encode()).hexdigest()[:8], 16)
    freq = 220 + seed % 880
    n = max(1, int(sample_rate * seconds))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = bytearray()
        for idx in range(n):
            sample = int(12000 * math.sin(2 * math.pi * freq * idx / sample_rate))
            frames.extend(struct.pack("<h", sample))
        wav.writeframes(bytes(frames))
    return buf.getvalue()


def pcap_bytes(seed_text: str, packet_count: int = 8) -> bytes:
    seed = int(hashlib.sha256(seed_text.encode()).hexdigest()[:8], 16)
    data = bytearray()
    data.extend(struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1))
    for idx in range(packet_count):
        payload = bytes(((seed + idx * 17 + off) % 256 for off in range(42)))
        data.extend(struct.pack("<IIII", idx, 0, len(payload), len(payload)))
        data.extend(payload)
    return bytes(data)


def synthetic_grid(seed_text: str, width: int = 32, height: int = 24) -> bytes:
    seed = int(hashlib.sha256(seed_text.encode()).hexdigest()[:8], 16)
    rows = []
    for y in range(height):
        row = []
        for x in range(width):
            val = (seed + x * 17 + y * 31 + (x * y) % 19) % 256
            row.append(str(val))
        rows.append(" ".join(row))
    return f"P2\n{width} {height}\n255\n" .encode("utf-8") + ("\n".join(rows) + "\n").encode("utf-8")


def minimal_fits_bytes(width: int, height: int, frame: str) -> bytes:
    """Create a tiny FITS image padded to FITS block boundaries."""
    width = max(1, int(width))
    height = max(1, int(height))
    cards = [
        "SIMPLE  =                    T",
        "BITPIX  =                    8",
        "NAXIS   =                    2",
        f"NAXIS1  = {width:20d}",
        f"NAXIS2  = {height:20d}",
        f"FRAME   = '{str(frame)[:18]:<18}'",
        "END",
    ]
    header = "".join(card.ljust(80)[:80] for card in cards).encode("ascii", "replace")
    header += b" " * ((2880 - len(header) % 2880) % 2880)
    data = bytes((idx * 17 + width + height) % 256 for idx in range(width * height))
    data += b"\0" * ((2880 - len(data) % 2880) % 2880)
    return header + data


def stable_int(value: Any, modulo: int = 1000) -> int:
    text = json.dumps(value, sort_keys=True, default=str)
    return sum((idx + 1) * ord(ch) for idx, ch in enumerate(text)) % modulo


def family_artifacts(family: str, scenario_id: str, params: dict[str, Any], output: Any) -> dict[str, bytes]:
    """Render concrete, family-shaped files from the public oracle payload."""
    summary = observed_summary(output)
    files: dict[str, bytes] = {
        "reports/oracle_summary.txt": text_bytes(generic_report(family, scenario_id, params, output)),
        "tables/oracle_metrics.csv": csv_bytes(rows_from_output(output)),
        "data/oracle_output.pretty.json": json_bytes(output),
        "data/public_parameters.json": json_bytes(params),
    }
    f = family.lower()
    if "ajv" in f or "schema" in f:
        require_meta = bool(summary.get("require_meta")) if isinstance(summary, dict) else False
        min_items = int(summary.get("min_items", 1)) if isinstance(summary, dict) else 1
        payload = {"kind": str(params.get("format", "baseline")), "items": list(range(min_items))}
        if require_meta:
            payload["meta"] = {"policy": str(params.get("additional_properties", "strict"))}
        files["schema/reconstructed_schema.json"] = json_bytes(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "title": f"{family}:{scenario_id}",
                "type": "object",
                "required": ["kind", "items"] + (["meta"] if require_meta else []),
                "properties": {
                    "kind": {"enum": ["baseline", "edge", "stress", "compat", str(params.get("format", "baseline"))]},
                    "items": {"type": "array", "minItems": min_items, "items": {"type": "number"}},
                    "meta": {"type": "object", "additionalProperties": {"type": "string"}},
                },
                "additionalProperties": False,
            }
        )
        files["schema/payload.json"] = json_bytes(payload)
        files["schema/validation_report.json"] = json_bytes({"valid": summary.get("valid") if isinstance(summary, dict) else None, "summary": summary})
    elif "duckdb" in f or "sqlite" in f:
        rows = summary.get("rows") if isinstance(summary, dict) else None
        files["queries/reconstruct.sql"] = text_bytes(
            "create table public_observation(region text, grp text, value double, n integer);\n"
            "select region, grp, value, n from public_observation order by region, grp;\n"
        )
        files["tables/query_result.csv"] = table_csv_from_rows(rows, ["region", "group_or_status", "value", "n"])
        files["tables/run_metadata.json"] = json_bytes({"row_count": summary.get("row_count") if isinstance(summary, dict) else None, "params": params})
    elif "container" in f:
        base = summary.get("base", params.get("base_image", "python")) if isinstance(summary, dict) else params.get("base_image", "python")
        files["container/Dockerfile"] = text_bytes(f"FROM {base}\nLABEL org.opencontainers.image.title=\"{family}-{scenario_id}\"\n")
        files["container/sbom.spdx.json"] = json_bytes({"SPDXID": "SPDXRef-DOCUMENT", "name": family, "packages": [{"name": base, "versionInfo": str(params.get("sbom_scope", "public"))}], "summary": summary})
        files["container/attestation.intoto.jsonl"] = text_bytes(json.dumps({"predicateType": "https://slsa.dev/provenance/v1", "predicate": summary}, sort_keys=True) + "\n")
    elif "gdal" in f or "geo" in f or "cartography" in f:
        files["geo/features.geojson"] = json_bytes(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"family": family, "scenario": scenario_id, "oracle": output},
                        "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                    }
                ],
            }
        )
    elif "pcap" in f or "network" in f:
        packet_count = int(summary.get("packet_count", 8)) if isinstance(summary, dict) else 8
        files["network/public_capture.pcap"] = pcap_bytes(json.dumps({"params": params, "summary": summary}, sort_keys=True, default=str), packet_count)
        files["network/flow_report.csv"] = csv_bytes(rows_from_output(summary))
        files["network/capture_summary.txt"] = text_bytes(generic_report(family, scenario_id, params, output))
    elif "opa" in f or "rego" in f:
        files["policy/input.json"] = json_bytes(params)
        files["policy/decision.json"] = json_bytes(output)
        files["policy/policy.rego"] = text_bytes('package public_reconstruction\n\ndefault allow := false\n')
    elif "molecular" in f or "chem" in f:
        query = str(params.get("substructure_query", "c1ccccc1"))
        radius = params.get("fingerprint_radius", params.get("radius", 2))
        seed = params.get("conformer_seed", 0)
        smiles = "CC(=O)Oc1ccccc1C(=O)O" if stable_int(seed, 2) == 0 else "Cn1c(=O)c2c(ncn2C)n(C)c1=O"
        files["chem/public_molecule.smi"] = text_bytes(f"{smiles} {family}_{scenario_id}\n")
        files["chem/substructure_query.smi"] = text_bytes(f"{query} query_{scenario_id}\n")
        files["chem/fingerprint_summary.csv"] = text_bytes(
            "metric,value\n"
            f"fingerprint_radius,{radius}\n"
            f"conformer_seed,{seed}\n"
            + "\n".join(f"{k},{v}" for k, v in flatten_rows(output))
            + "\n"
        )
        files["chem/public_molecule.sdf"] = text_bytes(
            f"{family}_{scenario_id}\n"
            "  public-reconstruction\n\n"
            "  0  0  0  0  0  0            999 V2000\n"
            f">  <SMILES>\n{smiles}\n\n"
            f">  <SUBSTRUCTURE_QUERY>\n{query}\n\n"
            "$$$$\n"
        )
    elif "proteomics" in f or "protein" in f:
        sequence = "MKWVTFISLLFLFSSAYSRGVFRRDTHKSEIAHRFKDLGE"
        files["proteomics/protein_sequence.fasta"] = text_bytes(f">{family}_{scenario_id}\n{sequence}\n")
        files["proteomics/peptide_report.tsv"] = text_bytes("metric\tvalue\n" + "\n".join(f"{k}\t{v}" for k, v in flatten_rows(output)) + "\n")
    elif "pdb" in f or "structural_biology" in f:
        files["structure/public_model.pdb"] = text_bytes(
            "HEADER    PUBLIC RECONSTRUCTION OBSERVATION\n"
            "ATOM      1  N   GLY A   1       0.000   0.000   0.000  1.00 20.00           N\n"
            "ATOM      2  CA  GLY A   1       1.458   0.000   0.000  0.75 20.00           C\n"
            "ATOM      3  C   GLY A   1       2.028   1.410   0.000  0.75 20.00           C\n"
            "TER\nEND\n"
        )
        files["structure/analysis_report.tsv"] = text_bytes("metric\tvalue\n" + "\n".join(f"{k}\t{v}" for k, v in flatten_rows(output)) + "\n")
    elif "samtools" in f or "bio" in f:
        files["bio/public_sequence.fasta"] = text_bytes(f">{family}_{scenario_id}\nACGTACGTACGTACGTACGTACGTACGTACGT\n")
        files["bio/analysis_report.tsv"] = text_bytes("metric\tvalue\n" + "\n".join(f"{k}\t{v}" for k, v in flatten_rows(output)) + "\n")
        files["bio/public_variants.vcf"] = text_bytes("##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\nchr1\t7\tpublic1\tA\tG\t42\tPASS\t.\n")
    elif "audio" in f or "signal" in f or "seismology" in f or "acoustic" in f or "rf" in f:
        files["signals/public_waveform.wav"] = wav_bytes(json.dumps({"params": params, "summary": summary}, sort_keys=True, default=str))
        files["signals/spectrum.csv"] = csv_bytes(rows_from_output(summary))
        files["signals/waveform_preview.pgm"] = synthetic_grid(json.dumps(output, sort_keys=True), 48, 16)
    elif "medical" in f or "microscopy" in f or "color" in f or "image" in f:
        files["images/measurement_preview.pgm"] = synthetic_grid(json.dumps(output, sort_keys=True), 32, 32)
        files["images/image_measurements.json"] = json_bytes(output)
    elif "astronomy" in f or "fits" in f:
        shape = summary.get("shape", [32, 32]) if isinstance(summary, dict) else [32, 32]
        width, height = int(shape[0]), int(shape[1])
        files["astronomy/photometry_catalog.csv"] = csv_bytes(rows_from_output(output))
        files["astronomy/public_image.fits"] = minimal_fits_bytes(width, height, summary.get("frame", "") if isinstance(summary, dict) else "")
        files["astronomy/observation_header.fits.txt"] = text_bytes(
            "SIMPLE  =                    T\n"
            f"NAXIS1  = {width:20}\n"
            f"NAXIS2  = {height:20}\n"
            f"FRAME   = '{summary.get('frame', '') if isinstance(summary, dict) else ''}'\n"
            "END\n"
        )
    elif "climate" in f or "netcdf" in f:
        files["climate/public_dataset.cdl"] = text_bytes("netcdf public_observation {\n// " + json.dumps(output, sort_keys=True, default=str) + "\n}\n")
    elif "music" in f:
        first = summary.get("first", "C4") if isinstance(summary, dict) else "C4"
        ql = summary.get("ql", 1.0) if isinstance(summary, dict) else 1.0
        files["score/public_score.musicxml"] = text_bytes(
            textwrap.dedent(
                f"""\
                <?xml version="1.0" encoding="UTF-8"?>
                <score-partwise version="4.0">
                  <work><work-title>{family} {scenario_id}</work-title></work>
                  <part-list><score-part id="P1"><part-name>Public</part-name></score-part></part-list>
                  <part id="P1">
                    <measure number="1">
                      <attributes><divisions>4</divisions><key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
                      <note><pitch><step>{str(first)[0]}</step><octave>{str(first)[-1] if str(first)[-1].isdigit() else 4}</octave></pitch><duration>{max(1, int(float(ql) * 4))}</duration><type>quarter</type></note>
                    </measure>
                  </part>
                </score-partwise>
                """
            )
        )
    elif "video" in f:
        files["video/ffprobe_streams.json"] = json_bytes(output)
        files["video/qc_report.txt"] = text_bytes(generic_report(family, scenario_id, params, output))
    elif "point_cloud" in f or "lidar" in f:
        files["point_cloud/public_points.xyz"] = text_bytes("x y z\n0 0 0\n1 0 0.5\n2 1 1.0\n")
        files["point_cloud/public_cloud.ply"] = text_bytes(
            "ply\nformat ascii 1.0\nelement vertex 3\n"
            "property float x\nproperty float y\nproperty float z\nend_header\n"
            "0 0 0\n1 0 0.5\n2 1 1.0\n"
        )
    elif "power" in f or "grid" in f:
        files["grid/powerflow.csv"] = csv_bytes(rows_from_output(output))
    elif "font" in f or "typography" in f:
        files["font/shaping_trace.json"] = json_bytes(output)
    elif "circuit" in f:
        files["circuit/public_circuit.cir"] = text_bytes(
            f"* public circuit observation for {family}\nV1 in 0 DC 1 AC 1\nR1 in out {params.get('component_value', 1000)}\nC1 out 0 {params.get('tolerance', '1e-6')}\n.op\n.ac dec 4 10 10000\n.end\n"
        )
        files["circuit/simulation.log"] = text_bytes(generic_report(family, scenario_id, params, output))
    elif "finite" in f or "mechanics" in f:
        files["fea/public_model.inp"] = text_bytes(
            f"*NODE\n1,0,0,0\n2,1,0,0\n*ELEMENT,TYPE=T3D2,ELSET=Eall\n1,1,2\n*MATERIAL,NAME=mat\n*ELASTIC\n{params.get('material_property', 200000)},0.3\n*CLOAD\n2,1,{params.get('load_case', 10)}\n*END STEP\n"
        )
        files["fea/result_summary.csv"] = csv_bytes(rows_from_output(output))
    elif "robot" in f:
        files["robotics/model.xml"] = text_bytes('<mujoco model="public"><worldbody/></mujoco>\n')
        files["robotics/trajectory.csv"] = csv_bytes(rows_from_output(output))
    else:
        files["domain/public_observation.txt"] = text_bytes(generic_report(family, scenario_id, params, output))
    return files


def read_public_payload(task: Path) -> dict[str, Any]:
    tar_path = task / "environment/app/observations/reference_outputs.tar.gz"
    with tarfile.open(tar_path, "r:gz") as tar:
        handle = tar.extractfile("public_manifest.json")
        if handle is None:
            raise RuntimeError(f"{tar_path} has no public_manifest.json")
        return json.loads(handle.read().decode("utf-8"))


def load_oracle(task: Path, group: str):
    oracle_path = task / "tests/private" / f"{group}_oracle.py"
    module_name = f"rich_public_smoke_{group}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, oracle_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import oracle from {oracle_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic_value(key: str, family: str, scenario_id: str, task_name: str) -> Any:
    seed = int(hashlib.sha256(f"{family}:{scenario_id}:{task_name}:{key}".encode()).hexdigest()[:8], 16)
    key_l = key.lower()
    if any(token in key_l for token in ("mode", "policy", "type", "scope", "image", "branch", "goal")):
        return ["baseline", "strict", "stress", "compat", "edge"][seed % 5]
    if any(token in key_l for token in ("count", "depth", "order", "budget", "density", "bound", "variable")):
        return 1 + seed % 9
    if any(token in key_l for token in ("threshold", "scale", "quality", "tolerance")):
        return round(0.5 + (seed % 1000) / 137.0, 4)
    return f"{key}_{seed % 10007}"


def augment_output_with_param_effect(output: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Make repaired smoke outputs explicitly sensitive to every visible param."""
    return {
        "summary": observed_summary(output),
        "parameter_effect": {
            "keys": sorted(params),
            "digest": hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest(),
        },
    }


def oracle_function_name(oracle_source: str, family: str) -> str | None:
    tree = ast.parse(oracle_source)
    for node in ast.walk(tree):
        mapping: ast.Dict | None = None
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "ORACLES" for t in node.targets):
            if isinstance(node.value, ast.Dict):
                mapping = node.value
        elif (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "update"
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id == "ORACLES"
            and node.value.args
            and isinstance(node.value.args[0], ast.Dict)
        ):
            mapping = node.value.args[0]
        if mapping is None:
            continue
        for key, value in zip(mapping.keys, mapping.values):
            if isinstance(key, ast.Constant) and key.value == family and isinstance(value, ast.Name):
                return value.id
    return None


def function_param_analysis(task: Path, group: str, family: str) -> tuple[set[str], bool]:
    source = (task / "tests/private" / f"{group}_oracle.py").read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source)
    func_name = oracle_function_name(source, family)
    if func_name is None:
        return set(), False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            keys: set[str] = set()
            uses_full_params = False
            for call in ast.walk(node):
                if not isinstance(call, ast.Call):
                    continue
                if any(isinstance(arg, ast.Name) and arg.id == "params" for arg in call.args):
                    uses_full_params = True
                if not (isinstance(call.func, ast.Attribute) and call.func.attr == "get"):
                    continue
                if not (isinstance(call.func.value, ast.Name) and call.func.value.id == "params"):
                    continue
                if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
                    keys.add(call.args[0].value)
            return keys, uses_full_params
    return set(), False


def cleaned_payload(
    payload: dict[str, Any],
    effective_keys: set[str],
    task: Path,
    group: str,
    family: str,
) -> tuple[dict[str, Any], set[str]]:
    """Return a smoke payload whose visible parameters match oracle semantics."""
    result = json.loads(json.dumps(payload, default=str))
    synthesized: set[str] = set()
    if effective_keys:
        result["effective_axes_to_vary"] = sorted(effective_keys)
        for scenario in result.get("public_scenarios", []):
            params = scenario.get("parameters") or {}
            repaired = {}
            for key in sorted(effective_keys):
                if key in params:
                    repaired[key] = params[key]
                else:
                    repaired[key] = synthetic_value(key, family, scenario.get("scenario_id", ""), task.name)
                    synthesized.add(key)
            scenario["parameters"] = repaired
    if synthesized:
        oracle = load_oracle(task, group)
        if family not in oracle.ORACLES:
            raise RuntimeError(f"family {family!r} not registered in {group}_oracle.ORACLES")
        for scenario in result.get("public_scenarios", []):
            output = oracle.ORACLES[family](scenario["parameters"])
            scenario["oracle_output"] = output
        result["smoke_reran_oracle_after_synthesizing_parameters"] = True
    signatures = []
    for scenario in result.get("public_scenarios", []):
        output = augment_output_with_param_effect(scenario.get("oracle_output"), scenario.get("parameters") or {})
        signature = hashlib.sha256(json.dumps(output, sort_keys=True, default=str).encode()).hexdigest()
        scenario["oracle_output"] = output
        scenario["signature"] = signature
        signatures.append(signature)
    result["distinct_public_signatures"] = len(set(signatures)) == len(signatures)
    result["smoke_augmented_output_with_parameter_effect"] = True
    result["smoke_synthesized_parameter_keys"] = sorted(synthesized)
    return result, synthesized


def write_rich_tar(task: Path, group: str, payload: dict[str, Any], output_root: Path) -> Path:
    family = payload["family_id"]
    task_id = str(payload.get("task_id") or task.name)
    out_dir = output_root / group / family / task.name
    out_dir.mkdir(parents=True, exist_ok=True)
    tar_path = out_dir / "reference_outputs.rich_smoke.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        rich_manifest = dict(payload)
        rich_manifest["schema"] = "rich-public-reference-outputs-smoke-v1"
        rich_manifest["source_task"] = str(task)
        rich_manifest["created_at"] = utc_now()
        add_json(tar, "public_manifest.json", rich_manifest)
        for scenario in payload["public_scenarios"]:
            sid = scenario["scenario_id"]
            params = scenario.get("parameters") or {}
            output = scenario.get("oracle_output")
            signature = scenario.get("signature")
            add_json(tar, f"{sid}/scenario.json", {"scenario_id": sid, "parameters": params})
            add_json(tar, f"{sid}/oracle_output.json", output)
            add_json(tar, f"{sid}/signature.json", {"scenario_id": sid, "signature": signature})
            files = family_artifacts(family, sid, params, output)
            add_json(
                tar,
                f"{sid}/artifact_manifest.json",
                {
                    "schema": "rich-public-scenario-artifacts-v1",
                    "scenario_id": sid,
                    "family_id": family,
                    "files": sorted(files),
                },
            )
            for name, data in sorted(files.items()):
                add_bytes(tar, f"{sid}/{name}", data)
    return tar_path


def concrete_members(tar_path: Path) -> list[str]:
    with tarfile.open(tar_path, "r:gz") as tar:
        names = []
        for member in tar.getmembers():
            if not member.isfile():
                continue
            if Path(member.name).name not in META_NAMES:
                names.append(member.name)
        return names


def iter_family_samples(groups: list[str], per_family: int, seed: int) -> list[tuple[str, str, Path]]:
    samples: list[tuple[str, str, Path]] = []
    for group in groups:
        buckets: dict[str, list[Path]] = defaultdict(list)
        for task in sorted(p for p in (TASK_ROOT / group).iterdir() if p.is_dir()):
            try:
                family = load_json(task / "tests/private/manifest.json")["family_id"]
            except Exception:
                family = "unknown"
            buckets[family].append(task)
        for family, tasks in sorted(buckets.items()):
            rng = random.Random(f"{seed}:{group}:{family}")
            shuffled = list(tasks)
            rng.shuffle(shuffled)
            for task in sorted(shuffled[:per_family]):
                samples.append((group, family, task))
    return samples


def audit_one(group: str, family: str, task: Path, output_root: Path) -> dict[str, Any]:
    payload = read_public_payload(task)
    obs_manifest = load_json(task / "environment/app/observations/manifest.json")
    metadata_axes = set(obs_manifest.get("axes_to_vary") or [])
    oracle_keys, uses_full_params = function_param_analysis(task, group, family)
    effective_keys = set(metadata_axes) if metadata_axes else set(oracle_keys)
    source_scenario_param_keys = set()
    for scenario in payload.get("public_scenarios", []):
        source_scenario_param_keys.update((scenario.get("parameters") or {}).keys())

    repaired_payload, synthesized_keys = cleaned_payload(payload, effective_keys, task, group, family)
    scenario_param_keys = set()
    for scenario in repaired_payload.get("public_scenarios", []):
        scenario_param_keys.update((scenario.get("parameters") or {}).keys())

    tar_path = write_rich_tar(task, group, repaired_payload, output_root)
    members = concrete_members(tar_path)
    issues: list[str] = []
    source_warnings: list[str] = []
    if not members:
        issues.append("no_concrete_public_members")
    if metadata_axes and oracle_keys and not uses_full_params and not oracle_keys.issuperset(metadata_axes):
        source_warnings.append("source_oracle_does_not_directly_read_all_declared_axes")
    source_irrelevant = sorted(source_scenario_param_keys - effective_keys) if effective_keys else []
    if source_irrelevant:
        source_warnings.append("source_scenario_params_include_irrelevant_keys")
    irrelevant = sorted(scenario_param_keys - effective_keys) if effective_keys else []
    missing_from_scenarios = sorted(effective_keys - scenario_param_keys) if effective_keys else []
    if irrelevant:
        issues.append("repaired_scenario_params_include_irrelevant_keys")
    if missing_from_scenarios:
        issues.append("repaired_scenario_params_missing_oracle_keys")

    return {
        "group": group,
        "family": family,
        "task": task.name,
        "source_task": str(task),
        "rich_tar": str(tar_path),
        "rich_tar_size": tar_path.stat().st_size,
        "concrete_member_count": len(members),
        "concrete_members": members[:40],
        "metadata_axes": sorted(metadata_axes),
        "oracle_param_keys": sorted(oracle_keys),
        "oracle_uses_full_params": uses_full_params,
        "effective_param_keys": sorted(effective_keys),
        "source_scenario_param_keys": sorted(source_scenario_param_keys),
        "repaired_scenario_param_keys": sorted(scenario_param_keys),
        "source_irrelevant_scenario_param_keys": source_irrelevant,
        "repaired_irrelevant_scenario_param_keys": irrelevant,
        "missing_oracle_param_keys": missing_from_scenarios,
        "synthesized_parameter_keys": sorted(synthesized_keys),
        "issues": issues,
        "source_warnings": source_warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groups", nargs="+", choices=GROUPS, default=list(GROUPS))
    parser.add_argument("--per-family", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20260830)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    samples = iter_family_samples(args.groups, args.per_family, args.seed)
    rows: list[dict[str, Any]] = []
    for group, family, task in samples:
        try:
            row = audit_one(group, family, task, args.output_root)
        except Exception as exc:
            row = {
                "group": group,
                "family": family,
                "task": task.name,
                "source_task": str(task),
                "issues": ["smoke_failed"],
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        rows.append(row)
        print(f"[{len(rows)}/{len(samples)}] {group}/{family}/{task.name} issues={row.get('issues')}", flush=True)

    issue_counts = Counter(issue for row in rows for issue in row.get("issues", []))
    warning_counts = Counter(warning for row in rows for warning in row.get("source_warnings", []))
    by_group = defaultdict(Counter)
    by_family = defaultdict(Counter)
    for row in rows:
        group = row["group"]
        family = row["family"]
        by_group[group]["sampled"] += 1
        by_family[(group, family)]["sampled"] += 1
        for issue in row.get("issues", []):
            by_group[group][issue] += 1
            by_family[(group, family)][issue] += 1
        for warning in row.get("source_warnings", []):
            by_group[group][warning] += 1
            by_family[(group, family)][warning] += 1

    report = {
        "schema": "rich-public-artifact-smoke-report-v1",
        "created_at": utc_now(),
        "task_root": str(TASK_ROOT),
        "output_root": str(args.output_root),
        "groups": args.groups,
        "per_family": args.per_family,
        "sample_count": len(rows),
        "issue_counts": dict(issue_counts),
        "source_warning_counts": dict(warning_counts),
        "by_group": {key: dict(value) for key, value in sorted(by_group.items())},
        "by_family": [
            {"group": group, "family": family, **dict(counter)}
            for (group, family), counter in sorted(by_family.items())
        ],
        "rows": rows,
    }
    report_path = args.report or (args.output_root / "rich_public_artifact_smoke_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["schema", "sample_count", "issue_counts", "by_group", "output_root"]}, indent=2, sort_keys=True))
    print(f"report={report_path}")
    return 0 if not any(row.get("error_type") for row in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
