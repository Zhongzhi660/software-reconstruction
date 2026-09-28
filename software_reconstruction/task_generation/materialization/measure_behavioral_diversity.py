#!/usr/bin/env python3
"""Profile behavioral diversity for software reconstruction tasks.

This is a data-only analysis: it does not run agents, train models, or write
outputs into the source tree. It loads each task's public/private scenario
metadata, executes the private oracle when local dependencies are available,
and writes per-task profiles plus aggregate tables and a 4-panel figure.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import itertools
import json
import math
import os
import re
import signal
import sys
import tarfile
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DEFAULT_2400_ROOT = Path(
    "/path/to/software_reconstruction_data/semantic_verifier_all2400_20260901/tasks"
)
DEFAULT_TRUE10_ROOT = Path(
    "/path/to/software_reconstruction_data/true10_family10_semantic_verifier_all600_20260901"
)
DEFAULT_OUTPUT_ROOT = Path(
    "/path/to/software_reconstruction_data/behavioral_diversity_3000_20260902"
)

HASHY_RE = re.compile(
    r"(sha|hash|digest|signature|checksum|merkle|attestation|uuid|id$)", re.IGNORECASE
)

EXT_TO_TYPE = {
    ".json": "json",
    ".jsonl": "json",
    ".ndjson": "json",
    ".log": "log",
    ".out": "log",
    ".err": "log",
    ".txt": "log",
    ".conf": "config",
    ".cfg": "config",
    ".ini": "config",
    ".toml": "config",
    ".yaml": "config",
    ".yml": "config",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".svg": "image",
    ".tif": "image",
    ".tiff": "image",
    ".fits": "scientific_data",
    ".fit": "scientific_data",
    ".nc": "scientific_data",
    ".h5": "scientific_data",
    ".hdf5": "scientific_data",
    ".cif": "scientific_data",
    ".pdb": "scientific_data",
    ".fa": "scientific_data",
    ".fasta": "scientific_data",
    ".fastq": "scientific_data",
    ".vcf": "scientific_data",
    ".bam": "scientific_data",
    ".sam": "scientific_data",
    ".wav": "audio_video",
    ".mp3": "audio_video",
    ".mp4": "audio_video",
    ".mov": "audio_video",
    ".mkv": "audio_video",
    ".stl": "geometry_cad",
    ".obj": "geometry_cad",
    ".step": "geometry_cad",
    ".scad": "geometry_cad",
    ".kicad_pcb": "geometry_cad",
    ".csv": "tabular",
    ".tsv": "tabular",
    ".parquet": "tabular",
    ".py": "code",
    ".js": "code",
    ".ts": "code",
    ".tsx": "code",
    ".v": "code",
    ".sv": "code",
    ".sh": "code",
    ".sql": "code",
    ".pdf": "document",
    ".html": "document",
    ".xml": "document",
    ".md": "document",
    ".tar": "archive",
    ".gz": "archive",
    ".zip": "archive",
}


class TimeoutError(RuntimeError):
    pass


def load_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def dump_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n")


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def short_error(exc: BaseException) -> str:
    text = "".join(traceback.format_exception_only(type(exc), exc)).strip()
    return text.replace("\n", " | ")[:500]


def list_tasks(roots: list[Path], limit: int | None = None) -> list[Path]:
    tasks: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for item in sorted(root.iterdir(), key=lambda p: p.name):
            if not item.is_dir():
                continue
            if (item / "reconstruction.json").exists() and (item / "tests/private/variant.json").exists():
                tasks.append(item)
                if limit is not None and len(tasks) >= limit:
                    return tasks
    return tasks


def get_nested(*objs: dict[str, Any], path: tuple[str, ...], default: Any = None) -> Any:
    for obj in objs:
        cur: Any = obj
        ok = True
        for key in path:
            if not isinstance(cur, dict) or key not in cur:
                ok = False
                break
            cur = cur[key]
        if ok:
            return cur
    return default


def infer_split(task_dir: Path, rec: dict[str, Any], variant: dict[str, Any], private_manifest: dict[str, Any]) -> str:
    split = (
        variant.get("source_group")
        or private_manifest.get("source_group")
        or get_nested(rec, path=("parametric_expansion", "source_group"))
    )
    if split:
        return str(split)
    name = task_dir.name
    if name.startswith(("new10__", "offcode6__", "offcode20__")):
        return name.split("__", 1)[0]
    return "true10"


def load_scenarios(private_manifest: dict[str, Any], public_manifest: dict[str, Any], variant: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    public = private_manifest.get("public_scenarios") or public_manifest.get("public_scenarios") or variant.get("public_scenarios") or []
    hidden = private_manifest.get("hidden_scenarios") or variant.get("hidden_scenarios") or []
    if not isinstance(public, list):
        public = []
    if not isinstance(hidden, list):
        hidden = []
    return public, hidden


def flatten_param_paths(obj: Any, prefix: str = "") -> set[str]:
    if isinstance(obj, dict):
        out: set[str] = set()
        for key, value in obj.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            out.update(flatten_param_paths(value, child))
        return out or ({prefix} if prefix else set())
    if isinstance(obj, list):
        out = set()
        for idx, value in enumerate(obj[:32]):
            out.update(flatten_param_paths(value, f"{prefix}[]"))
        return out or ({prefix} if prefix else set())
    return {prefix} if prefix else set()


def normalize_semantic(obj: Any, parent_key: str = "", depth: int = 0) -> Any:
    if depth > 8:
        return str(type(obj).__name__)
    if isinstance(obj, dict):
        out = {}
        for key, value in sorted(obj.items(), key=lambda kv: str(kv[0])):
            skey = str(key)
            if HASHY_RE.search(skey):
                continue
            out[skey] = normalize_semantic(value, skey, depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        values = [normalize_semantic(v, parent_key, depth + 1) for v in obj]
        if len(values) > 64:
            return {"__len__": len(values), "__sample__": values[:16]}
        return values
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return str(obj)
        return round(obj, 6)
    if isinstance(obj, (str, int, bool)) or obj is None:
        return obj
    return str(obj)


def flatten_semantic(obj: Any, prefix: str = "$") -> dict[str, str]:
    if isinstance(obj, dict):
        out: dict[str, str] = {}
        for key, value in sorted(obj.items(), key=lambda kv: str(kv[0])):
            out.update(flatten_semantic(value, f"{prefix}.{key}"))
        return out or {prefix: "empty_dict"}
    if isinstance(obj, list):
        out = {"%s.__len__" % prefix: "int"}
        for idx, value in enumerate(obj[:32]):
            out.update(flatten_semantic(value, f"{prefix}[{idx}]"))
        return out
    return {prefix: type(obj).__name__}


def signature(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()


def scenario_key(scenario: dict[str, Any]) -> str:
    return signature(normalize_semantic(scenario.get("parameters", {})))


def artifact_type_for_name(name: str) -> str:
    path = Path(name)
    suffixes = [s.lower() for s in path.suffixes]
    if suffixes[-2:] == [".tar", ".gz"]:
        return "archive"
    for suffix in reversed(suffixes):
        if suffix in EXT_TO_TYPE:
            return EXT_TO_TYPE[suffix]
    return "other"


def artifact_types(task_dir: Path) -> tuple[list[str], int, list[str]]:
    names: list[str] = []
    obs_dir = task_dir / "environment/app/observations"
    manifest = load_json(obs_dir / "manifest.json", {}) or {}
    for key in ("public_observation_files", "files", "artifacts"):
        value = manifest.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    names.append(item)
                elif isinstance(item, dict):
                    for k in ("path", "name", "file"):
                        if isinstance(item.get(k), str):
                            names.append(item[k])
                            break
    for tar_name in ("reference_outputs.tar.gz",):
        tar_path = obs_dir / tar_name
        if tar_path.exists():
            names.append(tar_name)
            try:
                with tarfile.open(tar_path, "r:gz") as tf:
                    for member in tf.getmembers():
                        if member.isfile():
                            names.append(member.name)
            except Exception:
                names.append("__tar_read_error__")
    types = sorted(set(artifact_type_for_name(name) for name in names if name))
    return types, len(names), names[:50]


def load_oracle(task_dir: Path, family: str) -> tuple[Any | None, str | None]:
    private_dir = task_dir / "tests/private"
    candidates = sorted(private_dir.glob("*_oracle.py"))
    if not candidates:
        return None, "missing_oracle_module"
    oracle_path = candidates[0]
    module_name = "task_oracle_" + hashlib.sha1(str(oracle_path).encode()).hexdigest()
    old_path = list(sys.path)
    try:
        sys.path.insert(0, str(private_dir))
        spec = importlib.util.spec_from_file_location(module_name, oracle_path)
        if spec is None or spec.loader is None:
            return None, "oracle_spec_load_failed"
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        oracles = getattr(module, "ORACLES", None)
        if isinstance(oracles, dict) and oracles:
            if family in oracles:
                return oracles[family], None
            return next(iter(oracles.values())), f"family_not_in_oracles:{family}"
        return None, "missing_ORACLES_dict"
    except BaseException as exc:
        return None, "oracle_import_error:" + short_error(exc)
    finally:
        sys.path = old_path


def with_timeout(seconds: int, fn: Any, *args: Any) -> Any:
    def handler(signum: int, frame: Any) -> None:
        raise TimeoutError(f"oracle timed out after {seconds}s")

    old = signal.signal(signal.SIGALRM, handler)
    signal.alarm(seconds)
    try:
        return fn(*args)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def compute_sensitivity(outputs: list[dict[str, Any]]) -> tuple[float | None, int, int]:
    if len(outputs) < 2:
        return None, 0, 0
    changed = 0
    total = 0
    for a, b in itertools.combinations(outputs, 2):
        total += 1
        if a["semantic_signature"] != b["semantic_signature"]:
            changed += 1
    return changed / total if total else None, changed, total


def profile_task(task_dir: Path, oracle_timeout: int) -> dict[str, Any]:
    rec = load_json(task_dir / "reconstruction.json", {}) or {}
    variant = load_json(task_dir / "tests/private/variant.json", {}) or {}
    private_manifest = load_json(task_dir / "tests/private/manifest.json", {}) or {}
    public_manifest = load_json(task_dir / "environment/app/observations/manifest.json", {}) or {}

    split = infer_split(task_dir, rec, variant, private_manifest)
    family = str(
        variant.get("family_id")
        or private_manifest.get("family_id")
        or rec.get("family")
        or "unknown"
    )
    demo = str(
        variant.get("demo_id")
        or private_manifest.get("demo_id")
        or get_nested(rec, path=("parametric_expansion", "demo_id"))
        or "unknown"
    )

    public_scenarios, hidden_scenarios = load_scenarios(private_manifest, public_manifest, variant)
    all_scenarios = [("public", s) for s in public_scenarios] + [("hidden", s) for s in hidden_scenarios]

    axes = variant.get("effective_axes_to_vary") or private_manifest.get("effective_axes_to_vary") or variant.get("axes_to_vary") or private_manifest.get("axes_to_vary") or []
    param_paths: set[str] = set()
    for _, scenario in all_scenarios:
        param_paths.update(flatten_param_paths(scenario.get("parameters", {})))
    scenario_param_dim = len(param_paths)
    declared_param_dim = len(axes) if isinstance(axes, list) else None

    types, artifact_count, artifact_samples = artifact_types(task_dir)

    anomalies: list[str] = []
    if not public_scenarios:
        anomalies.append("missing_public_scenarios")
    if not hidden_scenarios:
        anomalies.append("missing_hidden_scenarios")
    if scenario_param_dim == 0:
        anomalies.append("no_scenario_parameters")
    if not types:
        anomalies.append("missing_artifact_types")

    public_param_keys = {scenario_key(s) for s in public_scenarios}
    hidden_param_keys = {scenario_key(s) for s in hidden_scenarios}
    public_hidden_param_overlap = bool(public_param_keys & hidden_param_keys)
    if public_hidden_param_overlap:
        anomalies.append("public_hidden_param_overlap")

    oracle_fn, oracle_load_error = load_oracle(task_dir, family)
    outputs: list[dict[str, Any]] = []
    oracle_errors: list[dict[str, str]] = []
    if oracle_fn is None:
        anomalies.append("oracle_load_failed")
    else:
        for kind, scenario in all_scenarios:
            sid = str(scenario.get("scenario_id", f"{kind}_{len(outputs) + 1}"))
            params = scenario.get("parameters", {})
            try:
                raw = with_timeout(oracle_timeout, oracle_fn, params)
                normalized = normalize_semantic(raw)
                flat = flatten_semantic(normalized)
                outputs.append(
                    {
                        "scenario_id": sid,
                        "scenario_kind": kind,
                        "semantic_signature": signature(normalized),
                        "field_count": len(flat),
                        "schema_signature": signature(sorted(flat.items())),
                        "schema_keys": sorted(flat.keys())[:200],
                    }
                )
            except BaseException as exc:
                oracle_errors.append(
                    {
                        "scenario_id": sid,
                        "scenario_kind": kind,
                        "error": short_error(exc),
                    }
                )
    if oracle_load_error:
        anomalies.append("oracle_load_warning")
    if oracle_errors:
        anomalies.append("oracle_exec_error")

    sensitivity, changed_pairs, total_pairs = compute_sensitivity(outputs)
    public_output_sigs = {o["semantic_signature"] for o in outputs if o["scenario_kind"] == "public"}
    hidden_output_sigs = {o["semantic_signature"] for o in outputs if o["scenario_kind"] == "hidden"}
    public_hidden_output_overlap = bool(public_output_sigs & hidden_output_sigs)
    if public_hidden_output_overlap and public_output_sigs and hidden_output_sigs:
        anomalies.append("public_hidden_output_overlap")
    if outputs and len(outputs) >= 2 and sensitivity == 0:
        anomalies.append("constant_oracle_behavior")
    if outputs and len(outputs) >= 2 and sensitivity is not None and sensitivity < 0.1:
        anomalies.append("low_behavioral_sensitivity")
    if not outputs:
        anomalies.append("missing_semantic_outputs")

    schema_sigs = {o["schema_signature"] for o in outputs}
    oracle_schema_consistent = len(schema_sigs) <= 1
    if outputs and not oracle_schema_consistent:
        anomalies.append("schema_inconsistent")

    field_counts = [o["field_count"] for o in outputs]
    task_id = str(rec.get("task_id") or f"{split}__{task_dir.name}" if split != "true10" else task_dir.name)
    return {
        "task_id": task_id,
        "task_dir": str(task_dir),
        "split": split,
        "family": family,
        "demo": demo,
        "n_public_scenarios": len(public_scenarios),
        "n_hidden_scenarios": len(hidden_scenarios),
        "n_total_scenarios": len(all_scenarios),
        "scenario_param_dim": scenario_param_dim,
        "declared_param_dim": declared_param_dim,
        "semantic_output_field_count_mean": round(sum(field_counts) / len(field_counts), 3) if field_counts else 0,
        "semantic_output_field_count_max": max(field_counts) if field_counts else 0,
        "artifact_types": types,
        "public_artifact_file_count_observed": artifact_count,
        "artifact_samples": artifact_samples,
        "public_hidden_param_overlap": public_hidden_param_overlap,
        "public_hidden_output_overlap": public_hidden_output_overlap,
        "oracle_schema_consistent": oracle_schema_consistent,
        "behavioral_sensitivity": sensitivity,
        "changed_scenario_pairs": changed_pairs,
        "total_scenario_pairs": total_pairs,
        "oracle_outputs_evaluated": len(outputs),
        "oracle_errors": oracle_errors[:20],
        "oracle_load_error": oracle_load_error,
        "output_schema_count": len(schema_sigs),
        "anomalies": sorted(set(anomalies)),
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def median(values: list[float]) -> float | None:
    return float(sorted(values)[len(values) // 2]) if values else None


def aggregate(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[str(row.get(key, "unknown"))].append(row)
    out: list[dict[str, Any]] = []
    for name, items in sorted(buckets.items()):
        sens = [r["behavioral_sensitivity"] for r in items if isinstance(r.get("behavioral_sensitivity"), (int, float))]
        param_dims = [r["scenario_param_dim"] for r in items if isinstance(r.get("scenario_param_dim"), int)]
        fields = [r["semantic_output_field_count_mean"] for r in items if isinstance(r.get("semantic_output_field_count_mean"), (int, float))]
        artifact_counter = Counter(t for r in items for t in r.get("artifact_types", []))
        anomaly_counter = Counter(a for r in items for a in r.get("anomalies", []))
        out.append(
            {
                key: name,
                "tasks": len(items),
                "families": len(set(r.get("family") for r in items)),
                "demos": len(set(r.get("demo") for r in items)),
                "public_scenarios_mean": round(sum(r.get("n_public_scenarios", 0) for r in items) / len(items), 3),
                "hidden_scenarios_mean": round(sum(r.get("n_hidden_scenarios", 0) for r in items) / len(items), 3),
                "param_dim_median": median(param_dims),
                "semantic_fields_median": median(fields),
                "behavioral_sensitivity_mean": round(sum(sens) / len(sens), 4) if sens else None,
                "behavioral_sensitivity_median": median(sens),
                "constant_behavior_tasks": anomaly_counter.get("constant_oracle_behavior", 0),
                "public_hidden_param_overlap_tasks": anomaly_counter.get("public_hidden_param_overlap", 0),
                "public_hidden_output_overlap_tasks": anomaly_counter.get("public_hidden_output_overlap", 0),
                "missing_output_tasks": anomaly_counter.get("missing_semantic_outputs", 0),
                "schema_inconsistent_tasks": anomaly_counter.get("schema_inconsistent", 0),
                "oracle_error_tasks": anomaly_counter.get("oracle_exec_error", 0)
                + anomaly_counter.get("oracle_load_failed", 0),
                "artifact_types": ";".join(f"{k}:{v}" for k, v in artifact_counter.most_common()),
            }
        )
    return out


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def make_plot(rows: list[dict[str, Any]], output: Path) -> str | None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        return "matplotlib_import_error:" + short_error(exc)

    family_counts = Counter(r["family"] for r in rows)
    artifact_counts = Counter(t for r in rows for t in r.get("artifact_types", []))
    sensitivities = [r["behavioral_sensitivity"] for r in rows if isinstance(r.get("behavioral_sensitivity"), (int, float))]
    param_dims = [r["scenario_param_dim"] for r in rows if isinstance(r.get("scenario_param_dim"), int)]
    fields = [r["semantic_output_field_count_mean"] for r in rows if isinstance(r.get("semantic_output_field_count_mean"), (int, float))]

    fig, axes = plt.subplots(2, 2, figsize=(16, 11))
    fig.suptitle("Software Reconstruction Behavioral Diversity (3000 tasks)", fontsize=16)

    top_families = family_counts.most_common(30)
    axes[0, 0].barh([k for k, _ in reversed(top_families)], [v for _, v in reversed(top_families)])
    axes[0, 0].set_title("Family/domain coverage (top 30)")
    axes[0, 0].set_xlabel("tasks")

    if artifact_counts:
        labels, values = zip(*artifact_counts.most_common())
        axes[0, 1].bar(labels, values)
        axes[0, 1].set_xticklabels(labels, rotation=35, ha="right")
    axes[0, 1].set_title("Artifact type distribution")
    axes[0, 1].set_ylabel("tasks containing type")

    axes[1, 0].scatter(param_dims, fields, s=10, alpha=0.45)
    axes[1, 0].set_title("Scenario/output complexity")
    axes[1, 0].set_xlabel("scenario parameter dimensions")
    axes[1, 0].set_ylabel("semantic output fields (mean)")

    if sensitivities:
        axes[1, 1].hist(sensitivities, bins=20, range=(0, 1), alpha=0.8)
    axes[1, 1].set_title("Behavioral sensitivity distribution")
    axes[1, 1].set_xlabel("changed scenario-pair ratio")
    axes[1, 1].set_ylabel("tasks")

    fig.tight_layout(rect=(0, 0, 1, 0.96))
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)
    return None


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", action="append", type=Path, default=None, help="Task root. May be repeated.")
    ap.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--oracle-timeout", type=int, default=20)
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    roots = args.root or [DEFAULT_2400_ROOT, DEFAULT_TRUE10_ROOT]
    tasks = list_tasks(roots, args.limit)
    args.output_root.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for idx, task_dir in enumerate(tasks, 1):
        try:
            rows.append(profile_task(task_dir, args.oracle_timeout))
        except BaseException as exc:
            rows.append(
                {
                    "task_id": task_dir.name,
                    "task_dir": str(task_dir),
                    "split": "unknown",
                    "family": "unknown",
                    "demo": "unknown",
                    "n_public_scenarios": 0,
                    "n_hidden_scenarios": 0,
                    "n_total_scenarios": 0,
                    "scenario_param_dim": 0,
                    "semantic_output_field_count_mean": 0,
                    "semantic_output_field_count_max": 0,
                    "artifact_types": [],
                    "public_hidden_param_overlap": False,
                    "public_hidden_output_overlap": False,
                    "oracle_schema_consistent": False,
                    "behavioral_sensitivity": None,
                    "changed_scenario_pairs": 0,
                    "total_scenario_pairs": 0,
                    "oracle_outputs_evaluated": 0,
                    "oracle_errors": [],
                    "oracle_load_error": "profile_task_error:" + short_error(exc),
                    "output_schema_count": 0,
                    "anomalies": ["profile_task_error"],
                }
            )
        if idx % 100 == 0:
            print(f"profiled {idx}/{len(tasks)}", flush=True)

    profile_path = args.output_root / "task_profile.jsonl"
    anomalies = [
        {
            "task_id": row["task_id"],
            "task_dir": row["task_dir"],
            "split": row["split"],
            "family": row["family"],
            "demo": row["demo"],
            "anomalies": row["anomalies"],
            "behavioral_sensitivity": row["behavioral_sensitivity"],
            "oracle_load_error": row.get("oracle_load_error"),
            "oracle_errors": row.get("oracle_errors", [])[:5],
        }
        for row in rows
        if row.get("anomalies")
    ]
    write_jsonl(profile_path, rows)
    write_jsonl(args.output_root / "anomalies.jsonl", anomalies)
    split_stats = aggregate(rows, "split")
    family_stats = aggregate(rows, "family")
    write_csv(args.output_root / "split_stats.csv", split_stats)
    write_csv(args.output_root / "family_stats.csv", family_stats)
    plot_error = make_plot(rows, args.output_root / "behavioral_diversity_4panel.png")

    anomaly_counter = Counter(a for row in rows for a in row.get("anomalies", []))
    sens = [row["behavioral_sensitivity"] for row in rows if isinstance(row.get("behavioral_sensitivity"), (int, float))]
    summary = {
        "task_roots": [str(root) for root in roots],
        "tasks_profiled": len(rows),
        "splits": Counter(row["split"] for row in rows),
        "families": len(set(row["family"] for row in rows)),
        "demos": len(set(row["demo"] for row in rows)),
        "behavioral_sensitivity_mean": round(sum(sens) / len(sens), 4) if sens else None,
        "behavioral_sensitivity_median": median(sens),
        "tasks_with_sensitivity": len(sens),
        "anomaly_counts": anomaly_counter,
        "outputs": {
            "task_profile": str(profile_path),
            "anomalies": str(args.output_root / "anomalies.jsonl"),
            "split_stats": str(args.output_root / "split_stats.csv"),
            "family_stats": str(args.output_root / "family_stats.csv"),
            "figure": str(args.output_root / "behavioral_diversity_4panel.png"),
        },
        "plot_error": plot_error,
    }
    dump_json(args.output_root / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
