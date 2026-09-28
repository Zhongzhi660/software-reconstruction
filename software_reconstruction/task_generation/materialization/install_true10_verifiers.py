#!/usr/bin/env python3
"""Upgrade true10 tasks to the same semantic-verifier contract as family10.

This is intentionally different from ``upgrade_true10_semantic_verifier.py``:
it does not compare candidate stdout against a synthetic file-tree payload.
Instead it materializes a per-task private oracle module and a family10-style
public manifest, then installs the same hidden-oracle semantic judge used by
the 360-task family10 Daytona run.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import pathlib
import random
import re
import shutil
import tarfile
import tempfile
import time
from typing import Any


DATA_ROOT = pathlib.Path(
    "/path/to/software_reconstruction_data"
)
DEFAULT_SOURCE_ROOT = (
    DATA_ROOT
    / "software_reconstruction/true_10family_parametric_expansion/"
    / "reconstruction_tasks_parametric_all600_20260827_2355"
)
DEFAULT_OUTPUT_ROOT = (
    DATA_ROOT
    / "software_reconstruction/true10_family10_semantic_verifier_all600_20260901"
)
FAMILY10_TEMPLATE_TASK = (
    DATA_ROOT
    / "software_reconstruction/semantic_verifier_family10_daytona_20260831/tasks/"
    / "new10__ajv_contains_minmax_array__01"
)

TEXT_SUFFIXES = {
    ".log",
    ".txt",
    ".rpt",
    ".md",
    ".conf",
    ".cmake",
    ".v",
    ".sv",
    ".scad",
    ".yaml",
    ".yml",
}
JSON_SUFFIXES = {".json"}
MAX_TEXT_NUMBERS = 32
MAX_TEXT_KEYWORDS = 64
MAX_JSON_KEYS = 40
MAX_LIST_ITEMS = 16


def remove_tree_with_retries(path: pathlib.Path) -> None:
    if not path.exists():
        return
    trash = path.with_name(f"{path.name}.deleting.{os.getpid()}.{int(time.time() * 1000)}")
    path.rename(trash)
    for attempt in range(5):
        try:
            shutil.rmtree(trash)
            return
        except OSError:
            if attempt == 4:
                raise
            time.sleep(0.5 * (attempt + 1))


def load_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def digest_obj(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def canonical_params(params: dict[str, Any]) -> str:
    return json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)


def task_dirs(root: pathlib.Path) -> list[pathlib.Path]:
    return sorted(
        p
        for p in root.iterdir()
        if p.is_dir() and (p / "tests/private/variant.json").is_file()
    )


def normalize_text(value: str) -> str:
    value = re.sub(r"0x[0-9a-fA-F]+", "0xADDR", value)
    value = re.sub(r"/tmp/[^\s:]+", "/tmp/PATH", value)
    value = re.sub(r"\s+", " ", value.strip())
    return value


def text_signature(value: str) -> dict[str, Any]:
    norm = normalize_text(value)
    numbers = re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", norm)
    words = [w.lower() for w in re.findall(r"[A-Za-z_][A-Za-z0-9_\-]{2,}", norm)]
    stop = {"the", "and", "for", "with", "from", "this", "that", "true", "false"}
    words = [w for w in words if w not in stop]
    return {
        "line_count": len(value.splitlines()),
        "number_count": len(numbers),
        "numbers": numbers[:MAX_TEXT_NUMBERS],
        "keywords": sorted(set(words))[:MAX_TEXT_KEYWORDS],
    }


def summarize_json_value(value: Any, depth: int = 0) -> Any:
    if depth >= 4:
        if isinstance(value, dict):
            return {"kind": "object", "key_count": len(value)}
        if isinstance(value, list):
            return {"kind": "list", "length": len(value)}
        return value
    if isinstance(value, dict):
        result: dict[str, Any] = {"key_count": len(value), "keys": sorted(map(str, value.keys()))[:MAX_JSON_KEYS]}
        scalars: dict[str, Any] = {}
        children: dict[str, Any] = {}
        for key in sorted(value, key=str)[:MAX_JSON_KEYS]:
            item = value[key]
            if isinstance(item, (str, int, float, bool)) or item is None:
                scalars[str(key)] = item
            elif isinstance(item, (dict, list)):
                children[str(key)] = summarize_json_value(item, depth + 1)
        if scalars:
            result["scalars"] = scalars
        if children:
            result["children"] = children
        return result
    if isinstance(value, list):
        return {
            "length": len(value),
            "sample": [summarize_json_value(item, depth + 1) for item in value[:MAX_LIST_ITEMS]],
        }
    return value


def summarize_scenario_dir(scenario_dir: pathlib.Path) -> dict[str, Any]:
    outputs: dict[str, Any] = {}
    files = sorted(p for p in scenario_dir.rglob("*") if p.is_file())
    for path in files:
        rel = str(path.relative_to(scenario_dir))
        if rel == "scenario.json":
            continue
        suffix = path.suffix.lower()
        if suffix in JSON_SUFFIXES:
            try:
                parsed = json.loads(path.read_text(errors="replace"))
                outputs[rel] = {"kind": "json", "summary": summarize_json_value(parsed)}
            except Exception:
                outputs[rel] = {"kind": "text", **text_signature(path.read_text(errors="replace"))}
        elif suffix in TEXT_SUFFIXES or suffix == "" or path.name in {"Makefile", "CMakeLists.txt"}:
            outputs[rel] = {"kind": "text", **text_signature(path.read_text(errors="replace"))}
        else:
            outputs[rel] = {"kind": "binary", "binary_size": path.stat().st_size}
    return {
        "output_count": len(outputs),
        "outputs": outputs,
    }


def extract_reference_tar(path: pathlib.Path) -> pathlib.Path:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="true10_family10_ref_"))
    with tarfile.open(path, "r:gz") as archive:
        archive.extractall(tmp)
    return tmp


def scenario_dirs(reference_root: pathlib.Path, prefix: str) -> list[pathlib.Path]:
    return sorted(p for p in reference_root.iterdir() if p.is_dir() and p.name.startswith(prefix))


def build_scenario_records(reference_root: pathlib.Path, prefix: str) -> list[dict[str, Any]]:
    records = []
    for scenario_dir in scenario_dirs(reference_root, prefix):
        scenario = load_json(scenario_dir / "scenario.json")
        params = scenario.get("parameters", {})
        summary = {
            "scenario_parameters": params,
            "reference_summary": summarize_scenario_dir(scenario_dir),
        }
        records.append(
            {
                "scenario_id": scenario.get("scenario_id", scenario_dir.name),
                "parameters": params,
                "summary": summary,
                "signature": digest_obj(summary),
                "source_dir": scenario_dir.name,
            }
        )
    return records


def tar_add_json(tar: tarfile.TarFile, name: str, payload: Any) -> None:
    data = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mtime = 0
    tar.addfile(info, io.BytesIO(data))


def add_original_public_files(tar: tarfile.TarFile, scenario_dir: pathlib.Path, scenario_name: str) -> None:
    for path in sorted(p for p in scenario_dir.rglob("*") if p.is_file()):
        rel = str(path.relative_to(scenario_dir))
        if rel == "scenario.json":
            continue
        data = path.read_bytes()
        info = tarfile.TarInfo(f"{scenario_name}/native/{rel}")
        info.size = len(data)
        info.mtime = 0
        tar.addfile(info, io.BytesIO(data))


def write_public_reference_tar(
    path: pathlib.Path,
    reference_root: pathlib.Path,
    public_records: list[dict[str, Any]],
) -> dict[str, Any]:
    public_payload = {"public_scenarios": []}
    for record in public_records:
        public_payload["public_scenarios"].append(
            {
                "scenario_id": record["scenario_id"],
                "parameters": record["parameters"],
                "oracle_output": {
                    "parameter_effect": {
                        "digest": digest_obj(record["parameters"]),
                        "keys": sorted(record["parameters"].keys()),
                    },
                    "summary": record["summary"],
                },
                "signature": record["signature"],
            }
        )
    with tarfile.open(path, "w:gz", compresslevel=6) as tar:
        tar_add_json(tar, "public_manifest.json", public_payload)
        for record in public_records:
            sid = record["scenario_id"]
            scenario = {"scenario_id": sid, "parameters": record["parameters"]}
            tar_add_json(tar, f"{sid}/scenario.json", scenario)
            tar_add_json(tar, f"{sid}/oracle_output.json", {"summary": record["summary"]})
            tar_add_json(tar, f"{sid}/signature.json", {"signature": record["signature"]})
            tar_add_json(
                tar,
                f"{sid}/artifact_manifest.json",
                {
                    "scenario_id": sid,
                    "summary_signature": record["signature"],
                    "native_outputs_prefix": f"{sid}/native/",
                },
            )
            tar_add_json(tar, f"{sid}/oracle/oracle_output.pretty.json", {"summary": record["summary"]})
            tar_add_json(tar, f"{sid}/oracle/public_parameters.json", record["parameters"])
            add_original_public_files(tar, reference_root / record["source_dir"], sid)
    return public_payload


def patched_family10_judge() -> str:
    judge = (FAMILY10_TEMPLATE_TASK / "tests/private/judge.py").read_text()
    # true10 families were accepted with 3+ varying axes and usually provide two
    # hidden scenarios. Keep the family10 hidden-oracle design but preserve that
    # true10 contract to avoid structural false negatives.
    judge = judge.replace(
        '"variant_has_parameter_axes": len(variant.get("axes_to_vary", [])) >= 5,',
        '"variant_has_parameter_axes": len(variant.get("axes_to_vary", [])) >= 3,',
    )
    judge = judge.replace(
        '"has_hidden_scenarios": len(hidden) >= 3,',
        '"has_hidden_scenarios": len(hidden) >= 2,',
    )
    if "generated_text_semantic_view" not in judge:
        judge = judge.replace("import pathlib\n", "import pathlib\nimport re\n")
        helper = r'''
def generated_text_semantic_view(summary, family):
    """Remove nondeterministic generated-file tokens while retaining semantics."""
    if not isinstance(summary, dict):
        return summary
    view = json.loads(json.dumps(summary))
    outputs = view.get("reference_summary", {}).get("outputs", {})
    if not isinstance(outputs, dict):
        return view

    if family == "cmake_build_config":
        for path in list(outputs):
            if "CMakeConfigureLog.yaml" in path:
                del outputs[path]

    if family == "openssl_pki":
        for path in ("leaf.txt", "sign.log", "verify.log"):
            text_summary = outputs.get(path)
            if not isinstance(text_summary, dict):
                continue
            keywords = text_summary.get("keywords")
            if isinstance(keywords, list):
                text_summary["keywords"] = [
                    token
                    for token in keywords
                    if (
                        isinstance(token, str)
                        and token != "xaddr"
                        and re.fullmatch(r"[a-z_-]+", token)
                        and not (
                            len(token) >= 8
                            and re.fullmatch(r"[0-9a-f]+", token)
                        )
                    )
                ]
            text_summary.pop("numbers", None)
    return view


'''
        judge = judge.replace(
            "def validate_semantics(family, got, expected):\n",
            helper + "def validate_semantics(family, got, expected):\n",
        )
        judge = judge.replace(
            "    return generic_semantic_checks(got, expected)\n",
            (
                '    if family in {"cmake_build_config", "openssl_pki"}:\n'
                "        return generic_semantic_checks(\n"
                "            generated_text_semantic_view(got, family),\n"
                "            generated_text_semantic_view(expected, family),\n"
                "        )\n\n"
                "    return generic_semantic_checks(got, expected)\n"
            ),
            1,
        )
    return judge


def family10_feedback() -> str:
    return (FAMILY10_TEMPLATE_TASK / "environment/app/tools/feedback").read_text()


def write_oracle_module(path: pathlib.Path, family: str, records: list[dict[str, Any]]) -> None:
    table = {canonical_params(record["parameters"]): record["summary"] for record in records}
    table_json = json.dumps(table, indent=2, sort_keys=True, ensure_ascii=False)
    text = f'''#!/usr/bin/env python3
import json

_TABLE = json.loads({table_json!r})


def _key(params):
    return json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)


def true10_oracle(params):
    key = _key(params)
    if key not in _TABLE:
        raise KeyError(f"unrecognized true10 scenario parameters: {{params!r}}")
    return _TABLE[key]


ORACLES = {{{family!r}: true10_oracle}}
'''
    path.write_text(text)
    path.chmod(0o755)


def update_instruction(path: pathlib.Path, variant: dict[str, Any], public_records: list[dict[str, Any]]) -> None:
    base = path.read_text().split("## Required Reconstruction Interface", 1)[0].rstrip()
    public_lines = "\n".join(
        f"- `{record['scenario_id']}` parameters: `{json.dumps(record['parameters'], sort_keys=True)}`"
        for record in public_records
    )
    append = f"""

## Required Reconstruction Interface

In addition to building an editable project, provide `/app/workspace/reconstruct.py`.
The verifier will execute it as:

```bash
python3 /app/workspace/reconstruct.py < scenario.json
```

It must read one scenario JSON object from stdin, use `scenario["parameters"]`,
and print JSON to stdout. Follow the same output shape as the public
`oracle_output.json` files inside `/app/observations/reference_outputs.tar.gz`;
usually this means printing `{{"summary": ...}}`.

Parameter axes: `{", ".join(variant.get("axes_to_vary", []))}`

Public scenarios:
{public_lines}

Use `/app/tools/feedback` while solving. It runs your `reconstruct.py` on the
public scenarios and reports which public oracle signatures match. Passing
public feedback is not sufficient by itself; hidden scenarios from the same
parameter space are used for final grading.
"""
    path.write_text(base + "\n" + append)


def update_reconstruction(path: pathlib.Path, public_count: int, hidden_count: int) -> None:
    if not path.exists():
        return
    payload = load_json(path)
    payload.setdefault("judge", {})
    payload["judge"].update(
        {
            "behavior_only": True,
            "hidden_scenario_count": hidden_count,
            "candidate_source_equality_forbidden": True,
            "requires_reconstruct_py": True,
            "comparison": "family10-style private oracle semantic comparison",
        }
    )
    payload.setdefault("feedback", {})
    payload["feedback"].update(
        {
            "command": "/app/tools/feedback",
            "public_scenario_count": public_count,
            "schema": "public-signature-feedback-v1",
        }
    )
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def copy_and_upgrade(source_root: pathlib.Path, output_root: pathlib.Path, overwrite: bool) -> dict[str, Any]:
    if output_root.exists():
        if not overwrite:
            raise FileExistsError(output_root)
        remove_tree_with_retries(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    judge_text = patched_family10_judge()
    feedback_text = family10_feedback()
    report: dict[str, Any] = {
        "source_root": str(source_root),
        "output_root": str(output_root),
        "verifier": "family10-style-private-oracle-semantic",
        "task_count": 0,
        "tasks": [],
    }
    for src in task_dirs(source_root):
        dst = output_root / src.name
        shutil.copytree(src, dst, symlinks=True)
        variant = load_json(dst / "tests/private/variant.json")
        reference_root = extract_reference_tar(dst / "tests/private/reference_outputs.tar.gz")
        public_records = build_scenario_records(reference_root, "public_")
        hidden_records = build_scenario_records(reference_root, "hidden_")
        all_records = public_records + hidden_records
        if not public_records or not hidden_records:
            raise RuntimeError(f"{src.name}: missing public/hidden reference scenarios")

        private_manifest = dict(variant)
        private_manifest.update(
            {
                "schema": "planned-reconstruction-observations-v1",
                "source_group": "true10",
                "task_id": src.name,
                "public_scenarios": [
                    {"scenario_id": r["scenario_id"], "parameters": r["parameters"]}
                    for r in public_records
                ],
                "hidden_scenarios": [
                    {"scenario_id": r["scenario_id"], "parameters": r["parameters"]}
                    for r in hidden_records
                ],
                "required_deliverables": ["reconstruct.py", "project.json"],
                "public_feedback_schema": "public-signature-feedback-v1",
                "public_artifact_schema": "true10-family10-semantic-public-reference-v1",
            }
        )
        (dst / "tests/private/manifest.json").write_text(
            json.dumps(private_manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        )
        write_oracle_module(dst / "tests/private/true10_oracle.py", variant["family_id"], all_records)

        observations = dst / "environment/app/observations"
        observations.mkdir(parents=True, exist_ok=True)
        public_payload = write_public_reference_tar(
            observations / "reference_outputs.tar.gz", reference_root, public_records
        )
        obs_manifest = dict(private_manifest)
        obs_manifest.pop("hidden_scenarios", None)
        obs_manifest["reference_outputs"] = "reference_outputs.tar.gz"
        obs_manifest["public_artifact_count"] = len(public_records)
        obs_manifest["public_artifact_distinct_signatures"] = (
            len({r["signature"] for r in public_records}) == len(public_records)
        )
        obs_manifest["public_scenarios"] = [
            {"scenario_id": r["scenario_id"], "parameters": r["parameters"]}
            for r in public_records
        ]
        (observations / "manifest.json").write_text(
            json.dumps(obs_manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        )

        judge = dst / "tests/private/judge.py"
        judge.write_text(judge_text)
        judge.chmod(0o755)
        feedback = dst / "environment/app/tools/feedback"
        feedback.parent.mkdir(parents=True, exist_ok=True)
        feedback.write_text(feedback_text)
        feedback.chmod(0o755)
        update_instruction(dst / "instruction.md", variant, public_records)
        update_reconstruction(dst / "reconstruction.json", len(public_records), len(hidden_records))

        report["tasks"].append(
            {
                "task_id": src.name,
                "family_id": variant.get("family_id"),
                "demo_id": variant.get("demo_id"),
                "public_scenarios": len(public_records),
                "hidden_scenarios": len(hidden_records),
                "public_signatures": len(public_payload["public_scenarios"]),
            }
        )
        report["task_count"] += 1
        shutil.rmtree(reference_root, ignore_errors=True)
    (output_root.parent / f"{output_root.name}_upgrade_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    return report


def sample_tasks(output_root: pathlib.Path, sample_root: pathlib.Path, n: int, seed: int, overwrite: bool) -> dict[str, Any]:
    if sample_root.exists():
        if not overwrite:
            raise FileExistsError(sample_root)
        remove_tree_with_retries(sample_root)
    sample_root.mkdir(parents=True, exist_ok=True)
    by_family: dict[str, list[pathlib.Path]] = {}
    for task in task_dirs(output_root):
        variant = load_json(task / "tests/private/variant.json")
        by_family.setdefault(variant.get("family_id", "unknown"), []).append(task)
    rng = random.Random(seed)
    selected: list[pathlib.Path] = []
    per_family = max(1, n // max(1, len(by_family)))
    for family in sorted(by_family):
        items = sorted(by_family[family])
        rng.shuffle(items)
        selected.extend(items[:per_family])
    remaining = [p for p in task_dirs(output_root) if p not in set(selected)]
    rng.shuffle(remaining)
    selected.extend(remaining[: max(0, n - len(selected))])
    selected = selected[:n]
    for src in selected:
        shutil.copytree(src, sample_root / src.name, symlinks=True)
    report = {
        "source_root": str(output_root),
        "sample_root": str(sample_root),
        "sample_count": len(selected),
        "seed": seed,
        "family_counts": {},
        "tasks": [p.name for p in selected],
    }
    for task in selected:
        family = load_json(task / "tests/private/variant.json").get("family_id", "unknown")
        report["family_counts"][family] = report["family_counts"].get(family, 0) + 1
    (sample_root.parent / f"{sample_root.name}_sample_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=pathlib.Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output-root", type=pathlib.Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--sample-root", type=pathlib.Path)
    parser.add_argument("--sample-count", type=int, default=0)
    parser.add_argument("--seed", type=int, default=20260901)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    report = copy_and_upgrade(args.source_root, args.output_root, args.overwrite)
    print(json.dumps({"upgraded": report["task_count"], "output_root": str(args.output_root)}, indent=2))
    if args.sample_count:
        sample_root = args.sample_root or args.output_root.with_name(f"{args.output_root.name}_sample{args.sample_count}")
        sample = sample_tasks(args.output_root, sample_root, args.sample_count, args.seed, args.overwrite)
        print(json.dumps({"sampled": sample["sample_count"], "sample_root": str(sample_root)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
