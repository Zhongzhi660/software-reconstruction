#!/usr/bin/env python3
"""Profile software-reconstruction task quality without running agents.

The profiler answers a data-level question: do scenario changes induce semantic
oracle-output changes, and are public/hidden observations well formed?
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import itertools
import json
import mimetypes
import os
import signal
import sys
import tarfile
import traceback
from pathlib import Path
from typing import Any


DATA_ROOT = Path(
    os.environ.get(
        "SWR_DATA_ROOT",
        "/path/to/software_reconstruction_data",
    )
)
DEFAULT_SOURCES = [
    (
        "repaired2400",
        DATA_ROOT / "semantic_verifier_all2400_20260901/tasks",
    ),
    (
        "true10",
        DATA_ROOT / "true10_family10_semantic_verifier_all600_20260901",
    ),
]

DEFAULT_OUT = DATA_ROOT / "profile_analysis_3000_20260902"

HASHY_NAMES = {
    "digest",
    "hash",
    "sha",
    "sha1",
    "sha256",
    "checksum",
    "signature",
    "fingerprint",
    "merkle",
    "attestation",
}

ARTIFACT_SUFFIX_TYPES = {
    ".json": "json",
    ".jsonl": "json",
    ".ndjson": "json",
    ".txt": "log_text",
    ".log": "log_text",
    ".out": "log_text",
    ".err": "log_text",
    ".yaml": "config",
    ".yml": "config",
    ".toml": "config",
    ".ini": "config",
    ".cfg": "config",
    ".conf": "config",
    ".xml": "markup",
    ".html": "markup",
    ".md": "markup",
    ".csv": "table",
    ".tsv": "table",
    ".parquet": "table",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".svg": "image",
    ".pdf": "document",
    ".wav": "audio",
    ".flac": "audio",
    ".mp3": "audio",
    ".mp4": "video",
    ".mov": "video",
    ".fits": "scientific_data",
    ".fit": "scientific_data",
    ".nc": "scientific_data",
    ".h5": "scientific_data",
    ".hdf5": "scientific_data",
    ".pdb": "scientific_data",
    ".cif": "scientific_data",
    ".mol": "scientific_data",
    ".mol2": "scientific_data",
    ".sdf": "scientific_data",
    ".fa": "bio_sequence",
    ".fasta": "bio_sequence",
    ".fastq": "bio_sequence",
    ".sam": "bio_sequence",
    ".bam": "bio_sequence",
    ".vcf": "bio_sequence",
    ".pcap": "network_capture",
    ".pcapng": "network_capture",
    ".stl": "geometry",
    ".obj": "geometry",
    ".ply": "geometry",
    ".scad": "source_code",
    ".py": "source_code",
    ".js": "source_code",
    ".ts": "source_code",
    ".v": "source_code",
    ".sv": "source_code",
    ".sh": "source_code",
    ".sql": "source_code",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def dump_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def stable_hash(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def is_hashy_name(name: str) -> bool:
    low = str(name).lower()
    return (
        low in HASHY_NAMES
        or low.endswith("_hash")
        or low.endswith("_digest")
        or low.endswith("_sha256")
        or "checksum" in low
        or "fingerprint" in low
    )


def strip_hashy(obj: Any, parent_key: str = "") -> Any:
    if isinstance(obj, dict):
        return {
            key: strip_hashy(value, key)
            for key, value in sorted(obj.items())
            if not is_hashy_name(key)
        }
    if isinstance(obj, list):
        return [strip_hashy(value, parent_key) for value in obj]
    if isinstance(obj, str):
        low = obj.lower()
        if len(obj) >= 16 and all(ch in "0123456789abcdef" for ch in low):
            return "<HASHLIKE>"
    return obj


def semantic_payload(output: Any) -> Any:
    if isinstance(output, dict) and isinstance(output.get("summary"), dict):
        return output["summary"]
    if isinstance(output, dict) and isinstance(output.get("result"), dict):
        return output["result"]
    return output


def flatten_schema(obj: Any, prefix: str = "$", depth: int = 0) -> dict[str, str]:
    """Return a structural schema without treating list length as a field schema.

    List indices are observations, not field names.  Using ``[0]``, ``[1]``,
    ... made otherwise stable generated-text and table outputs look
    schema-inconsistent whenever their row/token count changed.  Merge item
    shapes under a wildcard while retaining heterogeneous item types.
    """
    if depth > 7:
        return {prefix: "truncated"}
    if isinstance(obj, dict):
        schema = {prefix: "object"}
        for key, value in sorted(obj.items()):
            if is_hashy_name(key):
                continue
            schema.update(flatten_schema(value, f"{prefix}.{key}", depth + 1))
        return schema
    if isinstance(obj, list):
        schema = {prefix: "list"}
        item_shapes: dict[str, set[str]] = {}
        for value in obj[:64]:
            for path, kind in flatten_schema(
                value, f"{prefix}[*]", depth + 1
            ).items():
                item_shapes.setdefault(path, set()).add(kind)
        for path, kinds in sorted(item_shapes.items()):
            schema[path] = "|".join(sorted(kinds))
        return schema
    return {prefix: type(obj).__name__}


def count_semantic_fields(obj: Any) -> int:
    obj = strip_hashy(semantic_payload(obj))
    if isinstance(obj, dict):
        return sum(count_semantic_fields(value) for value in obj.values())
    if isinstance(obj, list):
        return sum(count_semantic_fields(value) for value in obj[:64])
    return 1


def outputs_differ(left: Any, right: Any) -> bool:
    return strip_hashy(semantic_payload(left)) != strip_hashy(semantic_payload(right))


def pairwise_sensitivity(outputs: list[dict[str, Any]]) -> tuple[float | None, int, int]:
    valid = [row for row in outputs if row.get("ok")]
    if len(valid) < 2:
        return None, 0, 0
    pairs = list(itertools.combinations(valid, 2))
    changed = sum(
        outputs_differ(a["output"], b["output"])
        for a, b in pairs
    )
    return changed / len(pairs), changed, len(pairs)


def params_dim(scenarios: list[dict[str, Any]]) -> tuple[int, list[str]]:
    keys: set[str] = set()
    for scenario in scenarios:
        params = scenario.get("parameters") or {}
        if isinstance(params, dict):
            keys.update(str(key) for key in params)
    return len(keys), sorted(keys)


def param_duplicates(
    public_scenarios: list[dict[str, Any]], hidden_scenarios: list[dict[str, Any]]
) -> bool:
    public = {
        stable_hash(scenario.get("parameters") or {})
        for scenario in public_scenarios
    }
    hidden = {
        stable_hash(scenario.get("parameters") or {})
        for scenario in hidden_scenarios
    }
    return bool(public & hidden)


def output_duplicates(outputs: list[dict[str, Any]]) -> bool:
    public = {
        stable_hash(strip_hashy(row["output"]))
        for row in outputs
        if row.get("ok") and row.get("split") == "public"
    }
    hidden = {
        stable_hash(strip_hashy(row["output"]))
        for row in outputs
        if row.get("ok") and row.get("split") == "hidden"
    }
    return bool(public & hidden)


def schema_consistent(outputs: list[dict[str, Any]]) -> bool | None:
    schemas = [
        flatten_schema(semantic_payload(row["output"]))
        for row in outputs
        if row.get("ok")
    ]
    if len(schemas) < 2:
        return None
    paths = set().union(*(schema.keys() for schema in schemas))
    for path in paths:
        observed = {
            schema[path] for schema in schemas if path in schema
        }
        if len(observed) > 1:
            return False
        if (
            len(observed) == 1
            and any(path not in schema for schema in schemas)
            and "[*]" not in path
        ):
            return False
    return True


def artifact_type_for_path(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in ARTIFACT_SUFFIX_TYPES:
        return ARTIFACT_SUFFIX_TYPES[suffix]
    mime, _ = mimetypes.guess_type(path)
    if mime:
        if mime.startswith("image/"):
            return "image"
        if mime.startswith("audio/"):
            return "audio"
        if mime.startswith("video/"):
            return "video"
        if "json" in mime:
            return "json"
        if "text" in mime:
            return "log_text"
    return "other"


def artifact_types(task_dir: Path) -> tuple[list[str], int]:
    paths: list[str] = []
    obs_dir = task_dir / "environment" / "app" / "observations"
    if obs_dir.exists():
        paths.extend(str(path.relative_to(obs_dir)) for path in obs_dir.rglob("*") if path.is_file())
    for ref in [
        obs_dir / "reference_outputs.tar.gz",
        task_dir / "environment" / "app" / "observations" / "reference_outputs.tar.gz",
    ]:
        if ref.is_file():
            try:
                with tarfile.open(ref, "r:gz") as tar:
                    paths.extend(member.name for member in tar.getmembers() if member.isfile())
            except Exception:
                paths.append(str(ref.name))
    types = sorted({artifact_type_for_path(path) for path in paths})
    return types, len(paths)


def find_oracle(task_dir: Path) -> Path | None:
    candidates = sorted((task_dir / "tests" / "private").glob("*_oracle.py"))
    if candidates:
        return candidates[0]
    return None


def load_oracle(path: Path):
    module_name = f"profile_oracle_{stable_hash(str(path))[:12]}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load oracle spec: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def call_oracle(module: Any, family_id: str, params: dict[str, Any]) -> Any:
    if hasattr(module, "ORACLES"):
        oracles = getattr(module, "ORACLES")
        if isinstance(oracles, dict):
            if family_id in oracles:
                return oracles[family_id](params)
            if len(oracles) == 1:
                return next(iter(oracles.values()))(params)
    for name in [family_id, "true10_oracle", "oracle", "run_oracle"]:
        func = getattr(module, name, None)
        if callable(func):
            return func(params)
    raise AttributeError(f"no oracle callable found for family_id={family_id}")


class TimeoutError(RuntimeError):
    pass


def _timeout_handler(_signum, _frame):
    raise TimeoutError("oracle scenario timed out")


def call_oracle_with_timeout(
    module: Any,
    family_id: str,
    params: dict[str, Any],
    timeout_sec: int,
) -> Any:
    if timeout_sec <= 0:
        return call_oracle(module, family_id, params)
    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(timeout_sec)
    try:
        return call_oracle(module, family_id, params)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def scenario_outputs(
    task_dir: Path,
    family_id: str,
    scenarios: list[tuple[str, dict[str, Any]]],
    scenario_timeout_sec: int,
) -> tuple[list[dict[str, Any]], str | None]:
    oracle_path = find_oracle(task_dir)
    if oracle_path is None:
        return [], "missing_oracle"
    try:
        module = load_oracle(oracle_path)
    except Exception as exc:
        return [], f"oracle_import_failed:{type(exc).__name__}:{exc}"
    outputs = []
    for split, scenario in scenarios:
        try:
            params = scenario.get("parameters") or {}
            out = call_oracle_with_timeout(module, family_id, params, scenario_timeout_sec)
            outputs.append(
                {
                    "split": split,
                    "scenario_id": scenario.get("scenario_id"),
                    "parameters_sha256": stable_hash(params),
                    "output_sha256": stable_hash(strip_hashy(out)),
                    "field_count": count_semantic_fields(out),
                    "ok": True,
                    "output": out,
                }
            )
        except Exception as exc:
            outputs.append(
                {
                    "split": split,
                    "scenario_id": scenario.get("scenario_id"),
                    "parameters_sha256": stable_hash(scenario.get("parameters") or {}),
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return outputs, None


def split_from_manifest(source_label: str, manifest: dict[str, Any], task_id: str) -> str:
    source_group = manifest.get("source_group")
    if source_group:
        return str(source_group)
    for prefix in ["new10", "offcode6", "offcode20", "true10"]:
        if task_id.startswith(prefix + "__"):
            return prefix
    return source_label


def profile_task(
    source_label: str,
    task_dir: Path,
    scenario_timeout_sec: int,
) -> dict[str, Any]:
    issues: list[str] = []
    private_manifest_path = task_dir / "tests" / "private" / "manifest.json"
    variant_path = task_dir / "tests" / "private" / "variant.json"
    obs_manifest_path = task_dir / "environment" / "app" / "observations" / "manifest.json"

    private_manifest = load_json(private_manifest_path) if private_manifest_path.is_file() else {}
    variant = load_json(variant_path) if variant_path.is_file() else {}
    obs_manifest = load_json(obs_manifest_path) if obs_manifest_path.is_file() else {}

    task_id = str(private_manifest.get("task_id") or variant.get("task_id") or task_dir.name)
    split = split_from_manifest(source_label, private_manifest or variant, task_id)
    family_id = str(private_manifest.get("family_id") or variant.get("family_id") or "unknown")
    demo_id = str(private_manifest.get("demo_id") or variant.get("demo_id") or "unknown")
    public_scenarios = private_manifest.get("public_scenarios") or obs_manifest.get("public_scenarios") or []
    hidden_scenarios = private_manifest.get("hidden_scenarios") or []
    if not public_scenarios:
        issues.append("missing_public_scenarios")
    if not hidden_scenarios:
        issues.append("missing_hidden_scenarios")

    all_scenarios = [("public", scenario) for scenario in public_scenarios] + [
        ("hidden", scenario) for scenario in hidden_scenarios
    ]
    dim, keys = params_dim([scenario for _, scenario in all_scenarios])
    types, n_artifacts = artifact_types(task_dir)

    outputs, oracle_issue = scenario_outputs(
        task_dir,
        family_id,
        all_scenarios,
        scenario_timeout_sec=scenario_timeout_sec,
    )
    if oracle_issue:
        issues.append(oracle_issue)
    failed_outputs = [row for row in outputs if not row.get("ok")]
    if failed_outputs:
        issues.append("oracle_output_failed")
    ok_outputs = [row for row in outputs if row.get("ok")]
    if not ok_outputs:
        issues.append("missing_semantic_outputs")

    sensitivity, changed_pairs, total_pairs = pairwise_sensitivity(outputs)
    if sensitivity == 0 and total_pairs > 0:
        issues.append("constant_oracle_behavior")
    if param_duplicates(public_scenarios, hidden_scenarios):
        issues.append("public_hidden_param_duplicate")
    if output_duplicates(outputs):
        issues.append("public_hidden_output_duplicate")
    schema_ok = schema_consistent(outputs)
    if schema_ok is False:
        issues.append("schema_inconsistent")
    if not types:
        issues.append("missing_public_artifacts")

    field_counts = [row["field_count"] for row in ok_outputs if "field_count" in row]
    return {
        "task_id": task_id,
        "task_dir": str(task_dir),
        "split": split,
        "source_label": source_label,
        "family": family_id,
        "demo": demo_id,
        "group_id": private_manifest.get("group_id") or variant.get("group_id"),
        "n_public": len(public_scenarios),
        "n_hidden": len(hidden_scenarios),
        "param_dim": dim,
        "param_keys": keys,
        "semantic_output_field_count_mean": round(sum(field_counts) / len(field_counts), 3)
        if field_counts
        else None,
        "semantic_output_field_count_max": max(field_counts) if field_counts else None,
        "artifact_types": types,
        "artifact_file_count": n_artifacts,
        "public_hidden_param_duplicate": "public_hidden_param_duplicate" in issues,
        "public_hidden_output_duplicate": "public_hidden_output_duplicate" in issues,
        "schema_consistent": schema_ok,
        "behavioral_sensitivity": sensitivity,
        "changed_scenario_pairs": changed_pairs,
        "total_scenario_pairs": total_pairs,
        "oracle_output_ok_count": len(ok_outputs),
        "oracle_output_failed_count": len(failed_outputs),
        "issues": sorted(set(issues)),
        "scenario_outputs": [
            {
                key: value
                for key, value in row.items()
                if key not in {"output"}
            }
            for row in outputs
        ],
    }


def iter_tasks(source_label: str, root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.iterdir()
        if path.is_dir() and (path / "tests" / "private" / "manifest.json").is_file()
    )


def iter_task_dirs_fast(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir())


def infer_split_family_from_name(source_label: str, name: str) -> tuple[str, str]:
    if name.startswith(("new10__", "offcode6__", "offcode20__")):
        parts = name.split("__")
        split = parts[0]
        family_hint = parts[1] if len(parts) > 1 else name
        return split, family_hint
    family_hint = name.rsplit("__", 1)[0] if "__" in name else name
    return "true10" if source_label == "true10" else source_label, family_hint


def select_smoke_tasks(tasks_by_source: dict[str, list[Path]], sample_per_split: int) -> list[tuple[str, Path]]:
    selected: list[tuple[str, Path]] = []
    for source_label, tasks in tasks_by_source.items():
        by_split_family: dict[tuple[str, str], list[Path]] = collections.defaultdict(list)
        for task in tasks:
            split, family = infer_split_family_from_name(source_label, task.name)
            by_split_family[(split, family)].append(task)

        split_to_families: dict[str, list[str]] = collections.defaultdict(list)
        for split, family in sorted(by_split_family):
            split_to_families[split].append(family)
        for split, families in sorted(split_to_families.items()):
            # Round-robin over families so a smoke sample does not only test the
            # lexicographically first demo in each split.
            count = 0
            for family in families:
                if count >= sample_per_split:
                    break
                selected.append((source_label, by_split_family[(split, family)][0]))
                count += 1
    return selected


def summarize_profiles(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    by_split: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for profile in profiles:
        by_split[profile["split"]].append(profile)
    split_rows = []
    for split, rows in sorted(by_split.items()):
        sensitivities = [
            row["behavioral_sensitivity"]
            for row in rows
            if row["behavioral_sensitivity"] is not None
        ]
        field_counts = [
            row["semantic_output_field_count_mean"]
            for row in rows
            if row["semantic_output_field_count_mean"] is not None
        ]
        issue_rows = [row for row in rows if row["issues"]]
        artifacts = collections.Counter(
            artifact_type for row in rows for artifact_type in row["artifact_types"]
        )
        split_rows.append(
            {
                "split": split,
                "tasks": len(rows),
                "families": len({row["family"] for row in rows}),
                "demos": len({row["demo"] for row in rows}),
                "avg_public_scenarios": round(sum(row["n_public"] for row in rows) / len(rows), 3),
                "avg_hidden_scenarios": round(sum(row["n_hidden"] for row in rows) / len(rows), 3),
                "avg_param_dim": round(sum(row["param_dim"] for row in rows) / len(rows), 3),
                "avg_semantic_fields": round(sum(field_counts) / len(field_counts), 3)
                if field_counts
                else None,
                "behavioral_sensitivity_mean": round(sum(sensitivities) / len(sensitivities), 3)
                if sensitivities
                else None,
                "behavioral_sensitivity_median": round(sorted(sensitivities)[len(sensitivities) // 2], 3)
                if sensitivities
                else None,
                "issue_task_rate": round(len(issue_rows) / len(rows), 3),
                "artifact_types": dict(sorted(artifacts.items())),
            }
        )
    issue_counter = collections.Counter(issue for row in profiles for issue in row["issues"])
    return {
        "n_tasks": len(profiles),
        "n_splits": len(by_split),
        "n_families": len({row["family"] for row in profiles}),
        "n_demos": len({row["demo"] for row in profiles}),
        "split_summary": split_rows,
        "issue_counts": dict(sorted(issue_counter.items())),
    }


def write_summary_txt(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        f"tasks: {summary['n_tasks']}",
        f"splits: {summary['n_splits']}",
        f"families: {summary['n_families']}",
        f"demos: {summary['n_demos']}",
        "",
        "split summary:",
    ]
    for row in summary["split_summary"]:
        lines.append(
            "  {split}: tasks={tasks} families={families} demos={demos} "
            "public={avg_public_scenarios} hidden={avg_hidden_scenarios} "
            "param_dim={avg_param_dim} semantic_fields={avg_semantic_fields} "
            "sensitivity_mean={behavioral_sensitivity_mean} issue_rate={issue_task_rate}".format(**row)
        )
    lines.append("")
    lines.append("issue counts:")
    for key, value in summary["issue_counts"].items():
        lines.append(f"  {key}: {value}")
    path.write_text("\n".join(lines) + "\n")


def make_plot(path: Path, profiles: list[dict[str, Any]]) -> str | None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        return f"plot_skipped:{type(exc).__name__}:{exc}"

    family_counts = collections.Counter(row["family"] for row in profiles)
    artifact_counts = collections.Counter(
        artifact_type for row in profiles for artifact_type in row["artifact_types"]
    )
    complexities = [
        row["param_dim"] + (row["semantic_output_field_count_mean"] or 0)
        for row in profiles
    ]
    sensitivities = [
        row["behavioral_sensitivity"]
        for row in profiles
        if row["behavioral_sensitivity"] is not None
    ]

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    top_families = family_counts.most_common(20)
    axes[0, 0].barh([key for key, _ in top_families], [value for _, value in top_families])
    axes[0, 0].set_title("Family Coverage")
    axes[0, 0].invert_yaxis()

    axes[0, 1].bar(artifact_counts.keys(), artifact_counts.values())
    axes[0, 1].set_title("Artifact Type Distribution")
    axes[0, 1].tick_params(axis="x", rotation=45)

    axes[1, 0].hist(complexities, bins=min(20, max(5, len(complexities) // 2)))
    axes[1, 0].set_title("Scenario/Output Complexity")
    axes[1, 0].set_xlabel("param_dim + semantic field count")

    axes[1, 1].hist(sensitivities, bins=10, range=(0, 1))
    axes[1, 1].set_title("Behavioral Sensitivity")
    axes[1, 1].set_xlabel("changed scenario pairs / all pairs")

    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="LABEL=TASK_ROOT",
        help="override default task sources; may be repeated",
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--sample-per-split", type=int, default=0)
    parser.add_argument("--scenario-timeout-sec", type=int, default=20)
    parser.add_argument("--make-plot", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true", default=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sources = DEFAULT_SOURCES
    if args.source:
        sources = []
        for item in args.source:
            label, separator, root = item.partition("=")
            if not separator or not label.strip() or not root.strip():
                raise SystemExit(
                    f"invalid --source {item!r}; expected LABEL=TASK_ROOT"
                )
            sources.append((label.strip(), Path(root).expanduser().resolve()))
    if args.sample_per_split > 0:
        tasks_by_source = {
            source_label: iter_task_dirs_fast(root)
            for source_label, root in sources
        }
        task_items = select_smoke_tasks(tasks_by_source, args.sample_per_split)
        run_mode = f"smoke_sample_per_split_{args.sample_per_split}"
    else:
        tasks_by_source = {
            source_label: iter_tasks(source_label, root)
            for source_label, root in sources
        }
        task_items = [
            (source_label, task)
            for source_label, tasks in tasks_by_source.items()
            for task in tasks
        ]
        run_mode = "full"

    profiles: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for idx, (source_label, task_dir) in enumerate(task_items, start=1):
        try:
            profiles.append(profile_task(source_label, task_dir, args.scenario_timeout_sec))
        except Exception as exc:
            errors.append(
                {
                    "source_label": source_label,
                    "task_dir": str(task_dir),
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc()[-4000:],
                }
            )
        if idx % 100 == 0:
            print(f"profiled {idx}/{len(task_items)}", flush=True)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    append_jsonl(args.out_dir / "task_profile.jsonl", profiles)
    append_jsonl(args.out_dir / "issue_tasks.jsonl", [row for row in profiles if row["issues"]])
    if errors:
        append_jsonl(args.out_dir / "profile_errors.jsonl", errors)
    summary = summarize_profiles(profiles)
    summary["run_mode"] = run_mode
    summary["profile_errors"] = len(errors)
    dump_json(args.out_dir / "split_summary.json", summary)
    write_summary_txt(args.out_dir / "SUMMARY.txt", summary)
    if args.make_plot:
        plot_error = make_plot(args.out_dir / "profile_4panel.png", profiles)
        if plot_error:
            summary["plot_error"] = plot_error
            dump_json(args.out_dir / "split_summary.json", summary)

    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors or args.continue_on_error else 1


if __name__ == "__main__":
    raise SystemExit(main())
