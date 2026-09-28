#!/usr/bin/env python3
"""Profile reconstruction-task behavior inside Daytona sandboxes.

The companion ``profile_task_behavior.py`` can compute local structural
features directly, but oracle execution must happen in an environment matching
each task's ``tests/Dockerfile``. This runner keeps the structural scan on the
controller and delegates only oracle calls to Daytona.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import collections
import hashlib
import json
import os
import re
import sys
import textwrap
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

import profile_task_behavior as base


DEFAULT_OUT = (
    base.DEFAULT_OUT
    / f"daytona_profile_c160_{time.strftime('%Y%m%d_%H%M%S', time.localtime())}"
)


REMOTE_WORKER_CODE = r'''
import base64
import hashlib
import importlib.util
import itertools
import json
import signal
import sys
import traceback
from pathlib import Path


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


def jsonable(obj):
    if isinstance(obj, dict):
        return {str(key): jsonable(value) for key, value in sorted(obj.items())}
    if isinstance(obj, (list, tuple)):
        return [jsonable(value) for value in obj]
    if hasattr(obj, "item") and callable(obj.item):
        try:
            return jsonable(obj.item())
        except Exception:
            pass
    if isinstance(obj, Path):
        return str(obj)
    try:
        json.dumps(obj)
        return obj
    except Exception:
        return str(obj)


def stable_hash(obj):
    return hashlib.sha256(
        json.dumps(jsonable(obj), sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def is_hashy_name(name):
    low = str(name).lower()
    return (
        low in HASHY_NAMES
        or low.endswith("_hash")
        or low.endswith("_digest")
        or low.endswith("_sha256")
        or "checksum" in low
        or "fingerprint" in low
    )


def strip_hashy(obj, parent_key=""):
    obj = jsonable(obj)
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


def semantic_payload(output):
    if isinstance(output, dict) and isinstance(output.get("summary"), dict):
        return output["summary"]
    if isinstance(output, dict) and isinstance(output.get("result"), dict):
        return output["result"]
    return output


def count_semantic_fields(obj):
    obj = strip_hashy(semantic_payload(obj))
    if isinstance(obj, dict):
        return sum(count_semantic_fields(value) for value in obj.values())
    if isinstance(obj, list):
        return sum(count_semantic_fields(value) for value in obj[:64])
    return 1


def load_oracle(path):
    module_name = f"profile_oracle_{stable_hash(str(path))[:12]}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load oracle spec: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def call_oracle(module, family_id, params):
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


class ScenarioTimeout(RuntimeError):
    pass


def _timeout_handler(_signum, _frame):
    raise ScenarioTimeout("oracle scenario timed out")


def call_with_timeout(module, family_id, params, timeout_sec):
    if timeout_sec <= 0:
        return call_oracle(module, family_id, params)
    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(timeout_sec)
    try:
        return call_oracle(module, family_id, params)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def profile_record(module, record, scenario_timeout_sec):
    outputs = []
    for split, scenario in record["scenarios"]:
        params = scenario.get("parameters") or {}
        try:
            output = jsonable(call_with_timeout(module, record["family"], params, scenario_timeout_sec))
            stripped = strip_hashy(output)
            outputs.append(
                {
                    "split": split,
                    "scenario_id": scenario.get("scenario_id"),
                    "parameters_sha256": stable_hash(params),
                    "output_sha256": stable_hash(stripped),
                    "field_count": count_semantic_fields(output),
                    "ok": True,
                    "output": output,
                }
            )
        except Exception as exc:
            outputs.append(
                {
                    "split": split,
                    "scenario_id": scenario.get("scenario_id"),
                    "parameters_sha256": stable_hash(params),
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return {"record_id": record["record_id"], "scenario_outputs": outputs}


def main():
    payload_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    payload = json.loads(base64.b64decode(payload_path.read_text()).decode())
    oracle_path = Path("/tmp/profile_oracle.py")
    oracle_path.write_text(payload["oracle_source"], encoding="utf-8")
    try:
        module = load_oracle(oracle_path)
    except Exception as exc:
        rows = [
            {
                "record_id": record["record_id"],
                "scenario_outputs": [],
                "issues": [f"oracle_import_failed:{type(exc).__name__}:{exc}"],
                "traceback": traceback.format_exc()[-4000:],
            }
            for record in payload["records"]
        ]
    else:
        rows = [
            profile_record(module, record, int(payload["scenario_timeout_sec"]))
            for record in payload["records"]
        ]
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    print(json.dumps({"event": "worker_done", "records": len(rows)}, sort_keys=True))


if __name__ == "__main__":
    main()
'''


def stable_hash(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def docker_run_instructions(dockerfile: Path) -> list[str]:
    if not dockerfile.is_file():
        return []
    logical_lines: list[str] = []
    current = ""
    for raw in read_text(dockerfile).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if current:
            current += " " + line
        else:
            current = line
        if current.endswith("\\"):
            current = current[:-1].rstrip()
            continue
        logical_lines.append(current)
        current = ""
    if current:
        logical_lines.append(current)

    commands = []
    for line in logical_lines:
        match = re.match(r"RUN\s+(.+)", line, re.IGNORECASE)
        if not match:
            continue
        command = match.group(1).strip()
        if command.startswith("chmod ") or "chmod +x /tests" in command:
            continue
        commands.append(command)
    return commands


def setup_script(task_dir: Path) -> str:
    commands = docker_run_instructions(task_dir / "tests" / "Dockerfile")
    if not commands:
        commands = ["python3 -m pip install --no-cache-dir --upgrade pip setuptools wheel"]
    prefix = [
        "set -eu",
        "export DEBIAN_FRONTEND=noninteractive",
        "export HOME=/tmp LC_ALL=C.UTF-8 PYTHONHASHSEED=0",
        "python3 -m pip install --no-cache-dir --upgrade pip setuptools wheel",
    ]
    return "\n".join(prefix + commands)


def collect_task_items(
    sample_per_split: int,
    sources: list[tuple[str, Path]],
) -> tuple[str, list[tuple[str, Path]]]:
    if sample_per_split > 0:
        tasks_by_source = {
            source_label: base.iter_task_dirs_fast(root)
            for source_label, root in sources
        }
        return (
            f"smoke_sample_per_split_{sample_per_split}",
            base.select_smoke_tasks(tasks_by_source, sample_per_split),
        )
    tasks_by_source = {
        source_label: base.iter_tasks(source_label, root)
        for source_label, root in sources
    }
    return (
        "full",
        [
            (source_label, task)
            for source_label, tasks in tasks_by_source.items()
            for task in tasks
        ],
    )


def build_record(source_label: str, task_dir: Path) -> dict[str, Any]:
    private_manifest_path = task_dir / "tests" / "private" / "manifest.json"
    variant_path = task_dir / "tests" / "private" / "variant.json"
    obs_manifest_path = task_dir / "environment" / "app" / "observations" / "manifest.json"

    private_manifest = base.load_json(private_manifest_path) if private_manifest_path.is_file() else {}
    variant = base.load_json(variant_path) if variant_path.is_file() else {}
    obs_manifest = base.load_json(obs_manifest_path) if obs_manifest_path.is_file() else {}

    task_id = str(private_manifest.get("task_id") or variant.get("task_id") or task_dir.name)
    split = base.split_from_manifest(source_label, private_manifest or variant, task_id)
    family = str(private_manifest.get("family_id") or variant.get("family_id") or "unknown")
    demo = str(private_manifest.get("demo_id") or variant.get("demo_id") or "unknown")
    public_scenarios = private_manifest.get("public_scenarios") or obs_manifest.get("public_scenarios") or []
    hidden_scenarios = private_manifest.get("hidden_scenarios") or []
    scenarios = [("public", scenario) for scenario in public_scenarios] + [
        ("hidden", scenario) for scenario in hidden_scenarios
    ]
    param_dim, param_keys = base.params_dim([scenario for _, scenario in scenarios])
    artifact_types, artifact_file_count = base.artifact_types(task_dir)
    oracle_path = base.find_oracle(task_dir)
    issues: list[str] = []
    if not public_scenarios:
        issues.append("missing_public_scenarios")
    if not hidden_scenarios:
        issues.append("missing_hidden_scenarios")
    if not artifact_types:
        issues.append("missing_public_artifacts")
    if oracle_path is None:
        issues.append("missing_oracle")

    return {
        "record_id": str(task_dir),
        "source_label": source_label,
        "task_dir": str(task_dir),
        "task_id": task_id,
        "split": split,
        "family": family,
        "demo": demo,
        "group_id": private_manifest.get("group_id") or variant.get("group_id"),
        "n_public": len(public_scenarios),
        "n_hidden": len(hidden_scenarios),
        "param_dim": param_dim,
        "param_keys": param_keys,
        "artifact_types": artifact_types,
        "artifact_file_count": artifact_file_count,
        "public_scenarios": public_scenarios,
        "hidden_scenarios": hidden_scenarios,
        "scenarios": scenarios,
        "oracle_path": str(oracle_path) if oracle_path else None,
        "oracle_source": read_text(oracle_path) if oracle_path else "",
        "setup_script": setup_script(task_dir),
        "local_issues": issues,
    }


def merge_profile(record: dict[str, Any], remote: dict[str, Any] | None) -> dict[str, Any]:
    issues = list(record["local_issues"])
    outputs = []
    if remote is None:
        issues.append("daytona_missing_result")
    else:
        issues.extend(remote.get("issues") or [])
        outputs = remote.get("scenario_outputs") or []

    failed_outputs = [row for row in outputs if not row.get("ok")]
    if failed_outputs:
        issues.append("oracle_output_failed")
    ok_outputs = [row for row in outputs if row.get("ok")]
    if not ok_outputs:
        issues.append("missing_semantic_outputs")

    sensitivity, changed_pairs, total_pairs = base.pairwise_sensitivity(outputs)
    if sensitivity == 0 and total_pairs > 0:
        issues.append("constant_oracle_behavior")
    if base.param_duplicates(record["public_scenarios"], record["hidden_scenarios"]):
        issues.append("public_hidden_param_duplicate")
    if base.output_duplicates(outputs):
        issues.append("public_hidden_output_duplicate")
    schema_ok = base.schema_consistent(outputs)
    if schema_ok is False:
        issues.append("schema_inconsistent")

    field_counts = [row["field_count"] for row in ok_outputs if "field_count" in row]
    return {
        "task_id": record["task_id"],
        "task_dir": record["task_dir"],
        "split": record["split"],
        "source_label": record["source_label"],
        "family": record["family"],
        "demo": record["demo"],
        "group_id": record["group_id"],
        "n_public": record["n_public"],
        "n_hidden": record["n_hidden"],
        "param_dim": record["param_dim"],
        "param_keys": record["param_keys"],
        "semantic_output_field_count_mean": round(sum(field_counts) / len(field_counts), 3)
        if field_counts
        else None,
        "semantic_output_field_count_max": max(field_counts) if field_counts else None,
        "artifact_types": record["artifact_types"],
        "artifact_file_count": record["artifact_file_count"],
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
            {key: value for key, value in row.items() if key != "output"}
            for row in outputs
        ],
    }


def shard_records(records: list[dict[str, Any]], max_tasks: int) -> list[list[dict[str, Any]]]:
    return [records[idx : idx + max_tasks] for idx in range(0, len(records), max_tasks)]


def make_shards(records: list[dict[str, Any]], max_tasks_per_sandbox: int) -> list[list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for record in records:
        if not record["oracle_path"]:
            continue
        key = (stable_hash(record["setup_script"]), stable_hash(record["oracle_source"]))
        grouped[key].append(record)
    shards: list[list[dict[str, Any]]] = []
    for key in sorted(grouped):
        shards.extend(shard_records(grouped[key], max_tasks_per_sandbox))
    return shards


def heredoc(name: str, body: str) -> str:
    return f"cat > {name} <<'EOF_PROFILE_DAYTONA'\n{body}\nEOF_PROFILE_DAYTONA\n"


def run_shard_sync(
    api_key: str,
    shard: list[dict[str, Any]],
    shard_idx: int,
    args: argparse.Namespace,
) -> dict[str, Any]:
    from daytona_sdk import CreateSandboxFromImageParams, Daytona, DaytonaConfig, Image

    client = Daytona(DaytonaConfig(api_key=api_key))
    family_hint = shard[0]["family"][:18].replace("_", "-")
    sandbox_name = f"profile-{family_hint}-{uuid.uuid4().hex[:8]}"
    sandbox = client.create(
        CreateSandboxFromImageParams(
            name=sandbox_name,
            image=Image.debian_slim("3.11"),
            ttl_minutes=args.ttl_minutes,
            auto_delete_interval=args.auto_delete_interval,
            labels={
                "project": "reconstruction_task_profile",
                "shard": str(shard_idx),
                "family": shard[0]["family"][:60],
            },
        )
    )
    try:
        setup_result = sandbox.process.exec(shard[0]["setup_script"], timeout=args.setup_timeout_sec)
        setup_exit = getattr(setup_result, "exit_code", None)
        setup_text = str(getattr(setup_result, "result", ""))
        if setup_exit not in (0, None):
            return {
                "shard_idx": shard_idx,
                "sandbox_name": sandbox_name,
                "state": "setup_failed",
                "setup_exit_code": setup_exit,
                "setup_output_excerpt": setup_text[-4000:],
                "records": [
                    {
                        "record_id": record["record_id"],
                        "scenario_outputs": [],
                        "issues": ["daytona_setup_failed"],
                    }
                    for record in shard
                ],
            }

        payload = {
            "scenario_timeout_sec": args.scenario_timeout_sec,
            "oracle_source": shard[0]["oracle_source"],
            "records": [
                {
                    "record_id": record["record_id"],
                    "task_id": record["task_id"],
                    "family": record["family"],
                    "scenarios": record["scenarios"],
                }
                for record in shard
            ],
        }
        encoded = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode()).decode()
        prep = heredoc("/tmp/profile_payload.b64", encoded)
        prep += heredoc("/tmp/profile_worker.py", REMOTE_WORKER_CODE)
        exec_timeout = max(
            args.exec_timeout_sec,
            args.scenario_timeout_sec
            * max(1, sum(len(record["scenarios"]) for record in shard))
            + 120,
        )
        exec_result = sandbox.process.exec(
            prep + "python3 /tmp/profile_worker.py /tmp/profile_payload.b64 /tmp/profile_result.jsonl",
            timeout=exec_timeout,
        )
        exec_exit = getattr(exec_result, "exit_code", None)
        fetch_result = sandbox.process.exec("cat /tmp/profile_result.jsonl", timeout=120)
        fetch_exit = getattr(fetch_result, "exit_code", None)
        if fetch_exit not in (0, None):
            return {
                "shard_idx": shard_idx,
                "sandbox_name": sandbox_name,
                "state": "exec_failed",
                "exec_exit_code": exec_exit,
                "exec_output_excerpt": str(getattr(exec_result, "result", ""))[-4000:],
                "records": [
                    {
                        "record_id": record["record_id"],
                        "scenario_outputs": [],
                        "issues": ["daytona_exec_failed"],
                    }
                    for record in shard
                ],
            }
        rows = [
            json.loads(line)
            for line in str(getattr(fetch_result, "result", "")).splitlines()
            if line.strip()
        ]
        return {
            "shard_idx": shard_idx,
            "sandbox_name": sandbox_name,
            "state": "ok",
            "setup_exit_code": setup_exit,
            "exec_exit_code": exec_exit,
            "records": rows,
        }
    except Exception as exc:
        return {
            "shard_idx": shard_idx,
            "sandbox_name": sandbox_name,
            "state": "runner_failed",
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc()[-4000:],
            "records": [
                {
                    "record_id": record["record_id"],
                    "scenario_outputs": [],
                    "issues": ["daytona_runner_failed"],
                }
                for record in shard
            ],
        }
    finally:
        try:
            sandbox.delete()
        except Exception:
            pass


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_status(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


async def run_all_shards(
    api_key: str,
    shards: list[list[dict[str, Any]]],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    semaphore = asyncio.Semaphore(args.concurrency)
    results: list[dict[str, Any]] = []
    status_path = args.out_dir / "STATUS.json"

    async def run_one(idx: int, shard: list[dict[str, Any]]) -> dict[str, Any]:
        async with semaphore:
            return await asyncio.to_thread(run_shard_sync, api_key, shard, idx, args)

    tasks = [asyncio.create_task(run_one(idx, shard)) for idx, shard in enumerate(shards, start=1)]
    completed = 0
    for future in asyncio.as_completed(tasks):
        result = await future
        results.append(result)
        completed += 1
        if completed == 1 or completed % args.status_every == 0 or completed == len(tasks):
            state_counts = collections.Counter(item["state"] for item in results)
            done_records = sum(len(item.get("records") or []) for item in results)
            write_status(
                status_path,
                {
                    "run_mode": args.run_mode,
                    "shards_done": completed,
                    "shards_total": len(tasks),
                    "records_done": done_records,
                    "state_counts": dict(sorted(state_counts.items())),
                    "out_dir": str(args.out_dir),
                },
            )
            print(
                json.dumps(
                    {
                        "event": "progress",
                        "shards_done": completed,
                        "shards_total": len(tasks),
                        "records_done": done_records,
                        "state_counts": dict(sorted(state_counts.items())),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="LABEL=TASK_ROOT",
        help="override default task sources; may be repeated",
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--sample-per-split", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=160)
    parser.add_argument("--max-tasks-per-sandbox", type=int, default=20)
    parser.add_argument("--scenario-timeout-sec", type=int, default=20)
    parser.add_argument("--setup-timeout-sec", type=int, default=1800)
    parser.add_argument("--exec-timeout-sec", type=int, default=300)
    parser.add_argument("--ttl-minutes", type=int, default=240)
    parser.add_argument("--auto-delete-interval", type=int, default=120)
    parser.add_argument("--status-every", type=int, default=5)
    parser.add_argument("--make-plot", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sources = base.DEFAULT_SOURCES
    if args.source:
        sources = []
        for item in args.source:
            label, separator, root = item.partition("=")
            if not separator or not label.strip() or not root.strip():
                raise SystemExit(
                    f"invalid --source {item!r}; expected LABEL=TASK_ROOT"
                )
            sources.append((label.strip(), Path(root).expanduser().resolve()))
    if args.concurrency < 1:
        raise SystemExit("--concurrency must be >= 1")
    if args.max_tasks_per_sandbox < 1:
        raise SystemExit("--max-tasks-per-sandbox must be >= 1")
    api_key = os.environ.get("DAYTONA_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("DAYTONA_API_KEY is required")
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        os.environ.pop(key, None)

    run_mode, task_items = collect_task_items(args.sample_per_split, sources)
    if args.limit > 0:
        task_items = task_items[: args.limit]
        run_mode += f"_limit_{args.limit}"
    args.run_mode = run_mode
    args.out_dir.mkdir(parents=True, exist_ok=True)

    records = [build_record(source_label, task_dir) for source_label, task_dir in task_items]
    immediate_profiles = [
        merge_profile(record, {"scenario_outputs": [], "issues": ["missing_oracle"]})
        for record in records
        if not record["oracle_path"]
    ]
    shards = make_shards(records, args.max_tasks_per_sandbox)
    write_status(
        args.out_dir / "STATUS.json",
        {
            "run_mode": run_mode,
            "task_count": len(records),
            "immediate_profiles": len(immediate_profiles),
            "shards_total": len(shards),
            "out_dir": str(args.out_dir),
            "concurrency": args.concurrency,
            "max_tasks_per_sandbox": args.max_tasks_per_sandbox,
        },
    )
    print(
        json.dumps(
            {
                "event": "start",
                "run_mode": run_mode,
                "tasks": len(records),
                "shards": len(shards),
                "concurrency": args.concurrency,
                "max_tasks_per_sandbox": args.max_tasks_per_sandbox,
            },
            sort_keys=True,
        ),
        flush=True,
    )

    shard_results = asyncio.run(run_all_shards(api_key, shards, args)) if shards else []
    remote_by_record = {
        row["record_id"]: row
        for result in shard_results
        for row in (result.get("records") or [])
    }
    profiles = immediate_profiles + [
        merge_profile(record, remote_by_record.get(record["record_id"]))
        for record in records
        if record["oracle_path"]
    ]
    profiles.sort(key=lambda row: (row["source_label"], row["split"], row["family"], row["task_id"]))

    write_jsonl(args.out_dir / "task_profile.jsonl", profiles)
    write_jsonl(args.out_dir / "issue_tasks.jsonl", [row for row in profiles if row["issues"]])
    shard_report = {
        "run_mode": run_mode,
        "task_count": len(records),
        "profile_count": len(profiles),
        "shard_count": len(shard_results),
        "shard_state_counts": dict(collections.Counter(item["state"] for item in shard_results)),
        "shards": [
            {key: value for key, value in item.items() if key != "records"}
            for item in shard_results
        ],
    }
    base.dump_json(args.out_dir / "daytona_shard_report.json", shard_report)
    summary = base.summarize_profiles(profiles)
    summary["run_mode"] = run_mode
    summary["profile_errors"] = 0
    summary["daytona_shard_state_counts"] = shard_report["shard_state_counts"]
    base.dump_json(args.out_dir / "split_summary.json", summary)
    base.write_summary_txt(args.out_dir / "SUMMARY.txt", summary)
    if args.make_plot:
        plot_error = base.make_plot(args.out_dir / "profile_4panel.png", profiles)
        if plot_error:
            summary["plot_error"] = plot_error
            base.dump_json(args.out_dir / "split_summary.json", summary)
    write_status(
        args.out_dir / "STATUS.json",
        {
            "run_mode": run_mode,
            "task_count": len(records),
            "profile_count": len(profiles),
            "shards_total": len(shards),
            "shards_done": len(shard_results),
            "state_counts": shard_report["shard_state_counts"],
            "out_dir": str(args.out_dir),
            "done": True,
        },
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
