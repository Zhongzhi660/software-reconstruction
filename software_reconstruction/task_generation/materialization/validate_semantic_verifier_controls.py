#!/usr/bin/env python3
"""Build a small smoke set for a more semantic reconstruction verifier.

The smoke is intentionally tiny: copy a few repaired tasks, replace their
private judge with a prototype that keeps the true10 structural checks but
grades hidden scenarios with tolerant semantic checks instead of exact hidden
signature matching, then run three synthetic candidates:

* blank workspace: must fail
* public lookup with constant hidden fallback: must fail
* oracle-like implementation: must pass
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import textwrap
import time


LEGACY_SAMPLE_SOURCE_TASK_ROOT = pathlib.Path(
    "/path/to/software_reconstruction_runs/"
    "software_reconstruction/repaired_2400_deepseek_smoke_300_20260831/dataset/tasks"
)
DEFAULT_SOURCE_TASK_ROOTS = [
    pathlib.Path(
        "/path/to/software_reconstruction_data/"
        "software_reconstruction/materialized_offcode20_v3_repaired_20260831/offcode20"
    ),
    pathlib.Path(
        "/path/to/software_reconstruction_data/"
        "software_reconstruction/materialized_new10_offcode6_v3_repaired_20260831/new10"
    ),
    pathlib.Path(
        "/path/to/software_reconstruction_data/"
        "software_reconstruction/materialized_new10_offcode6_v3_repaired_20260831/offcode6"
    ),
]
DEFAULT_OUTPUT_ROOT = pathlib.Path(
    "/path/to/software_reconstruction_data/"
    "software_reconstruction/semantic_verifier_family3_smoke_20260831"
)

DEFAULT_SMOKE_TASKS = [
    "offcode20__acoustic_absorption_sweep__01",
    "offcode20__astro_background_subtraction__01",
    "offcode6__audio_bandpass_event_detection__06",
    "offcode6__chem_salt_fragment_cleanup__03",
]


SEMANTIC_JUDGE = r'''#!/usr/bin/env python3
import argparse
import importlib
import json
import pathlib
import re
import subprocess
import sys
import tarfile


EDITABLE_SUFFIXES = {
    ".py", ".json", ".yaml", ".yml", ".toml", ".txt", ".md", ".csv", ".tsv",
    ".xml", ".fasta", ".fa", ".nwk", ".tree", ".pdb", ".cif", ".smi", ".mol",
    ".sdf", ".las", ".ply", ".pcd", ".geojson", ".nc", ".grc", ".cir",
    ".spice", ".inp", ".dss", ".gtfs", ".wav", ".flac", ".fits",
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


def as_float(value):
    try:
        return float(value)
    except Exception:
        return None


def number_close(name, got, expected, abs_tol=0.0, rel_tol=0.0):
    g = as_float(got)
    e = as_float(expected)
    if g is None or e is None:
        return False, {"field": name, "reason": "not_numeric", "expected": expected, "got": got}
    tol = max(abs_tol, abs(e) * rel_tol)
    ok = abs(g - e) <= tol
    return ok, {"field": name, "expected": expected, "got": got, "abs_error": abs(g - e), "tolerance": tol}


def exact(name, got, expected):
    return got == expected, {"field": name, "expected": expected, "got": got}


HASHY_FIELD_NAMES = {
    "digest", "signature", "sha256", "hash", "merkle", "attestation",
    "flagstat_digest", "bcftools_stats_digest", "seqkit_stats_digest",
    "seqkit_grep_digest", "stdout_digest", "probe_digest", "digest_bytes",
}


def is_hashy_field(name):
    low = str(name).lower()
    return low in HASHY_FIELD_NAMES or low.endswith("_digest") or low.endswith("_sha256") or low.endswith("_hash")


def compare_semantic(path, got, expected, checks):
    name = path.rsplit(".", 1)[-1]
    if is_hashy_field(name):
        checks.append({"field": path, "passed": True, "mode": "ignored_digest_field"})
        return
    if isinstance(expected, bool):
        checks.append({"field": path, "passed": got is expected, "expected": expected, "got": got})
        return
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        ok, detail = number_close(path, got, expected, abs_tol=1.0, rel_tol=0.25)
        checks.append({"passed": ok, **detail})
        return
    if isinstance(expected, str):
        if len(expected) >= 16 and all(ch in "0123456789abcdefABCDEF" for ch in expected):
            checks.append({"field": path, "passed": True, "mode": "ignored_hashlike_string"})
        else:
            checks.append({"field": path, "passed": got == expected, "expected": expected, "got": got})
        return
    if isinstance(expected, (list, tuple)):
        if not isinstance(got, (list, tuple)):
            checks.append({"field": path, "passed": False, "reason": "got_not_list", "got": got})
            return
        expected = list(expected)
        got = list(got)
        checks.append({"field": path + ".length", "passed": len(got) == len(expected), "expected": len(expected), "got": len(got)})
        for idx, (g_item, e_item) in enumerate(zip(got[:8], expected[:8])):
            compare_semantic(f"{path}[{idx}]", g_item, e_item, checks)
        return
    if isinstance(expected, dict):
        if not isinstance(got, dict):
            checks.append({"field": path, "passed": False, "reason": "got_not_object", "got": got})
            return
        required_keys = [key for key in expected if not is_hashy_field(key)]
        missing = [key for key in required_keys if key not in got]
        checks.append({"field": path + ".keys", "passed": not missing, "missing": missing[:12]})
        for key in required_keys[:20]:
            if key in got:
                compare_semantic(f"{path}.{key}", got[key], expected[key], checks)
        return
    checks.append({"field": path, "passed": got == expected, "expected": expected, "got": got})


def generic_semantic_checks(got, expected):
    checks = []
    compare_semantic("$", got, expected, checks)
    return checks


def without_internal_seed(summary):
    """Remove the OffCode generator's latent seed from semantic grading."""
    if not isinstance(summary, dict):
        return summary
    view = json.loads(json.dumps(summary))
    view.pop("seed", None)
    return view


def kicad_semantic_view(summary):
    """Keep stable KiCad behavior and remove report-rendering noise."""
    if not isinstance(summary, dict):
        return summary
    view = json.loads(json.dumps(summary))
    # Parameters are verifier inputs, not reconstructed output behavior.
    view.pop("scenario_parameters", None)
    try:
        drc = view["reference_summary"]["outputs"]["drc.rpt"]
    except (KeyError, TypeError):
        return view
    if not isinstance(drc, dict):
        return view

    # Keyword order is a tokenization artifact. The first six number tokens
    # encode a timestamp; the final three are stable DRC result counts.
    numbers = drc.pop("numbers", None)
    drc.pop("keywords", None)
    if isinstance(numbers, list):
        drc["drc_counts"] = numbers[-3:]
    return view


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


def validate_semantics(family, got, expected):
    got = candidate_summary(got)
    checks = []

    if not isinstance(got, dict):
        return [{"field": "$", "passed": False, "reason": "summary_not_object", "got": got}]

    if family in {
        "cartography_map_rendering",
        "microscopy_cell_analysis",
        "geology_well_log_analysis",
        "transport_gtfs_schedule",
    }:
        return generic_semantic_checks(
            without_internal_seed(got),
            without_internal_seed(expected),
        )

    if family == "kicad_pcb":
        return generic_semantic_checks(
            kicad_semantic_view(got),
            kicad_semantic_view(expected),
        )

    if family in {"cmake_build_config", "openssl_pki"}:
        return generic_semantic_checks(
            generated_text_semantic_view(got, family),
            generated_text_semantic_view(expected, family),
        )

    if family == "acoustics_room_simulation":
        specs = [
            ("rir_len", 6, 0.02),
            ("energy", 0.0, 0.25),
            ("peak", 0.0, 0.20),
        ]
        for name, abs_tol, rel_tol in specs:
            ok, detail = number_close(name, got.get(name), expected.get(name), abs_tol, rel_tol)
            checks.append({"passed": ok, **detail})
        checks.append({"field": "positive_energy", "passed": as_float(got.get("energy")) is not None and as_float(got.get("energy")) > 0})
        return checks

    if family == "astronomy_fits_photometry":
        ok, detail = exact("shape", got.get("shape"), expected.get("shape"))
        checks.append({"passed": ok, **detail})
        for name, abs_tol, rel_tol in [
            ("flux", 2.0, 0.35),
            ("median", 0.5, 0.35),
            ("std", 0.2, 0.35),
        ]:
            ok, detail = number_close(name, got.get(name), expected.get(name), abs_tol, rel_tol)
            checks.append({"passed": ok, **detail})
        ok, detail = exact("frame", got.get("frame"), expected.get("frame"))
        checks.append({"passed": ok, **detail})
        return checks

    if family == "audio_signal_processing":
        for name, abs_tol, rel_tol in [
            ("rate", 400, 0.05),
            ("window", 40, 0.08),
            ("cutoff", 150, 0.08),
            ("rms", 0.08, 0.15),
            ("peak_freq", 35, 0.08),
            ("power_max", 0.004, 0.60),
        ]:
            ok, detail = number_close(name, got.get(name), expected.get(name), abs_tol, rel_tol)
            checks.append({"passed": ok, **detail})
        return checks

    if family == "molecular_chemistry":
        for name in ["smiles", "hba"]:
            ok, detail = exact(name, got.get(name), expected.get(name))
            checks.append({"passed": ok, **detail})
        for name, abs_tol, rel_tol in [
            ("mw", 0.5, 0.01),
            ("radius", 1.0, 0.25),
            ("fp_on", 6.0, 0.50),
        ]:
            ok, detail = number_close(name, got.get(name), expected.get(name), abs_tol, rel_tol)
            checks.append({"passed": ok, **detail})
        try:
            from rdkit import Chem
            valid_smiles = Chem.MolFromSmiles(str(got.get("smiles", ""))) is not None
        except Exception:
            valid_smiles = False
        checks.append({"field": "valid_smiles", "passed": valid_smiles})
        return checks

    if family == "z3_constraint_system":
        for name in ["status", "n", "lower", "penalty", "objective"]:
            if isinstance(expected.get(name), (int, float)) and not isinstance(expected.get(name), bool):
                ok, detail = number_close(name, got.get(name), expected.get(name), abs_tol=1.0, rel_tol=0.10)
            else:
                ok, detail = exact(name, got.get(name), expected.get(name))
            checks.append({"passed": ok, **detail})
        values = got.get("values")
        checks.append({
            "field": "values_length",
            "passed": isinstance(values, list) and len(values) == int(expected.get("n", -1)),
            "expected": expected.get("n"),
            "got": len(values) if isinstance(values, list) else None,
        })
        return checks

    return generic_semantic_checks(got, expected)


def load_public_summaries(observations):
    ref = observations / "reference_outputs.tar.gz"
    if not ref.is_file():
        return []
    with tarfile.open(ref, "r:gz") as tar:
        handle = tar.extractfile("public_manifest.json")
        if handle is None:
            return []
        payload = json.loads(handle.read().decode("utf-8"))
    return [candidate_summary(item.get("oracle_output")) for item in payload.get("public_scenarios", [])]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=pathlib.Path, default=pathlib.Path("/app/workspace"))
    parser.add_argument("--private", type=pathlib.Path, default=pathlib.Path("/tests/private"))
    parser.add_argument("--observations", type=pathlib.Path, default=pathlib.Path("/app/observations"))
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
        if p.suffix.lower() in EDITABLE_SUFFIXES or p.name in {"Makefile", "Dockerfile", "README.md", "project.json"}
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
        "does_not_copy_public_manifest": not copied_public,
        "variant_has_parameter_axes": len(variant.get("axes_to_vary", [])) >= 5,
        "has_public_scenarios": len(public) >= 2,
        "has_hidden_scenarios": len(hidden) >= 3,
    }

    details = []
    diagnostics = {}
    hidden_outputs = []
    expected_outputs = []
    public_summaries = load_public_summaries(args.observations)

    if all(checks.values()):
        sys.path.insert(0, str(args.private))
        oracle_names = [p.stem for p in args.private.glob("*_oracle.py")]
        if not oracle_names:
            checks["private_oracle_available"] = False
        else:
            oracle = importlib.import_module(oracle_names[0])
            checks["private_oracle_available"] = family in oracle.ORACLES
            if checks["private_oracle_available"]:
                for scenario in hidden:
                    try:
                        expected = oracle.ORACLES[family](scenario["parameters"])
                        expected_outputs.append(candidate_summary(expected))
                    except Exception as exc:
                        checks["private_oracle_executes"] = False
                        details.append({"scenario_id": scenario.get("scenario_id"), "error": f"oracle failed: {type(exc).__name__}: {exc}"})
                        break
                    got, error = run_candidate(reconstruct, scenario)
                    if error is not None:
                        checks["candidate_executes_hidden_scenarios"] = False
                        details.append({"scenario_id": scenario.get("scenario_id"), **error})
                        break
                    got_summary = candidate_summary(got)
                    hidden_outputs.append(got_summary)
                    semantic_checks = validate_semantics(family, got_summary, expected)
                    passed = bool(semantic_checks) and all(item.get("passed") for item in semantic_checks)
                    details.append({
                        "scenario_id": scenario.get("scenario_id"),
                        "passed": passed,
                        "semantic_checks": semantic_checks,
                    })
                    if not passed:
                        checks["candidate_matches_hidden_semantics"] = False
                        break
                else:
                    checks["private_oracle_executes"] = True
                    checks["candidate_executes_hidden_scenarios"] = True
                    checks["candidate_matches_hidden_semantics"] = True

    if hidden_outputs:
        expected_unique = {json.dumps(x, sort_keys=True, default=str) for x in expected_outputs}
        hidden_unique = {json.dumps(x, sort_keys=True, default=str) for x in hidden_outputs}
        diagnostics["hidden_expected_outputs_vary"] = len(expected_unique) > 1
        diagnostics["candidate_outputs_vary_on_hidden"] = len(hidden_unique) > 1
        if diagnostics["hidden_expected_outputs_vary"] and family not in {"z3_constraint_system"}:
            checks["candidate_outputs_vary_on_hidden"] = diagnostics["candidate_outputs_vary_on_hidden"]
        if public_summaries:
            expected_all_public_replays = all(x in public_summaries for x in expected_outputs)
            candidate_all_public_replays = all(x in public_summaries for x in hidden_outputs)
            diagnostics["hidden_expected_outputs_all_public_replays"] = expected_all_public_replays
            diagnostics["candidate_hidden_outputs_all_public_replays"] = candidate_all_public_replays
            if not expected_all_public_replays:
                checks["hidden_outputs_not_all_public_replays"] = not candidate_all_public_replays

    report = {
        "passed": all(checks.values()),
        "checks": checks,
        "copied_public_products": sorted(copied_public),
        "diagnostics": diagnostics,
        "task_id": variant.get("task_id"),
        "family_id": family,
        "details": details,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
'''


def load_public_manifest(task_dir: pathlib.Path) -> dict:
    ref = task_dir / "environment/app/observations/reference_outputs.tar.gz"
    with tarfile.open(ref, "r:gz") as tar:
        handle = tar.extractfile("public_manifest.json")
        if handle is None:
            raise RuntimeError(f"{task_dir.name}: missing public_manifest.json")
        return json.loads(handle.read().decode("utf-8"))


def write_public_lookup_candidate(workspace: pathlib.Path, task_dir: pathlib.Path) -> None:
    payload = load_public_manifest(task_dir)
    lookup = {
        item["scenario_id"]: item["oracle_output"]
        for item in payload.get("public_scenarios", [])
    }
    fallback = next(iter(lookup.values()))
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "project.json").write_text(json.dumps({"candidate": "public_lookup"}, indent=2) + "\n")
    script = f"""#!/usr/bin/env python3
import json
import sys

lookup = {json.dumps(lookup, sort_keys=True, indent=2)}
fallback = {json.dumps(fallback, sort_keys=True, indent=2)}

scenario = json.load(sys.stdin)
print(json.dumps(lookup.get(scenario.get("scenario_id"), fallback), sort_keys=True))
"""
    path = workspace / "reconstruct.py"
    path.write_text(script)
    path.chmod(0o755)


def write_oracle_like_candidate(workspace: pathlib.Path, task_dir: pathlib.Path) -> None:
    private = task_dir / "tests/private"
    oracle_files = sorted(private.glob("*_oracle.py"))
    if not oracle_files:
        raise RuntimeError(f"{task_dir.name}: missing oracle module")
    oracle_module = oracle_files[0].stem
    variant = json.loads((private / "variant.json").read_text())
    family = variant["family_id"]
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "project.json").write_text(json.dumps({"candidate": "oracle_like"}, indent=2) + "\n")
    script = f"""#!/usr/bin/env python3
import json
import pathlib
import sys

sys.path.insert(0, {str(private)!r})
import {oracle_module} as oracle

scenario = json.load(sys.stdin)
summary = oracle.ORACLES[{family!r}](scenario.get("parameters", {{}}))
print(json.dumps({{"summary": summary}}, sort_keys=True))
"""
    path = workspace / "reconstruct.py"
    path.write_text(script)
    path.chmod(0o755)


def run_judge(task_dir: pathlib.Path, workspace: pathlib.Path) -> dict:
    proc = subprocess.run(
        [
            sys.executable,
            str(task_dir / "tests/private/judge.py"),
            "--workspace",
            str(workspace),
            "--private",
            str(task_dir / "tests/private"),
            "--observations",
            str(task_dir / "environment/app/observations"),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=120,
    )
    try:
        payload = json.loads(proc.stdout)
    except Exception:
        payload = {"passed": False, "parse_error": proc.stdout[-2000:]}
    payload["returncode"] = proc.returncode
    if proc.stderr:
        payload["stderr_tail"] = proc.stderr[-2000:]
    return payload


def task_family(task_dir: pathlib.Path) -> tuple[str, str]:
    manifest = task_dir / "environment/app/observations/manifest.json"
    payload = json.loads(manifest.read_text())
    source_group = payload.get("source_group") or task_dir.name.split("__", 1)[0]
    return source_group, payload.get("family_id", "unknown_family")


def collect_scenario_pools(source_roots: list[pathlib.Path]) -> dict[tuple[str, str], list[dict]]:
    pools: dict[tuple[str, str], list[dict]] = {}
    for root in source_roots:
        if not root.is_dir():
            continue
        for task_dir in sorted(root.iterdir()):
            manifest_path = task_dir / "environment/app/observations/manifest.json"
            if not manifest_path.is_file():
                continue
            manifest = json.loads(manifest_path.read_text())
            key = (manifest.get("source_group") or task_dir.name.split("__", 1)[0], manifest.get("family_id", "unknown_family"))
            scenarios = []
            scenarios.extend(manifest.get("public_scenarios", []))
            private_manifest = task_dir / "tests/private/manifest.json"
            if private_manifest.is_file():
                scenarios.extend(json.loads(private_manifest.read_text()).get("hidden_scenarios", []))
            for scenario in scenarios:
                params = scenario.get("parameters")
                if isinstance(params, dict):
                    pools.setdefault(key, []).append({
                        "parameters": params,
                        "source_task": task_dir.name,
                        "source_scenario_id": scenario.get("scenario_id") or scenario.get("id"),
                    })
    return pools


def load_oracle_module(task_dir: pathlib.Path):
    private = task_dir / "tests/private"
    oracle_files = sorted(private.glob("*_oracle.py"))
    if not oracle_files:
        raise RuntimeError("missing oracle module")
    module_name = f"semantic_smoke_oracle_{abs(hash(str(oracle_files[0])))}"
    spec = importlib.util.spec_from_file_location(module_name, oracle_files[0])
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {oracle_files[0]}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def summary_key(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, default=str)


def resample_hidden_scenarios(task_dir: pathlib.Path, pool: list[dict], target_count: int = 3) -> dict:
    private_manifest_path = task_dir / "tests/private/manifest.json"
    variant_path = task_dir / "tests/private/variant.json"
    obs_manifest_path = task_dir / "environment/app/observations/manifest.json"
    private_manifest = json.loads(private_manifest_path.read_text())
    obs_manifest = json.loads(obs_manifest_path.read_text())
    variant = json.loads(variant_path.read_text())
    family = variant["family_id"]
    try:
        oracle = load_oracle_module(task_dir)
        if family not in oracle.ORACLES:
            return {"status": "oracle_unavailable", "reason": "family_not_registered"}
        public_keys = set()
        for scenario in obs_manifest.get("public_scenarios", []):
            public_keys.add(summary_key(oracle.ORACLES[family](scenario["parameters"])))
        selected = []
        selected_keys = set()
        for candidate in pool:
            params = candidate.get("parameters")
            if not isinstance(params, dict):
                continue
            key = summary_key(oracle.ORACLES[family](params))
            if key in public_keys or key in selected_keys:
                continue
            selected.append({
                "scenario_id": f"hidden_semantic_{len(selected) + 1}",
                "parameters": params,
                "source_task": candidate.get("source_task"),
                "source_scenario_id": candidate.get("source_scenario_id"),
            })
            selected_keys.add(key)
            if len(selected) >= target_count:
                break
    except Exception as exc:
        return {"status": "oracle_unavailable", "reason": f"{type(exc).__name__}: {exc}"}

    if len(selected) < target_count:
        return {
            "status": "insufficient_distinct_hidden",
            "selected": len(selected),
            "target": target_count,
        }

    private_manifest["hidden_scenarios"] = selected
    variant["hidden_scenarios"] = selected
    private_manifest_path.write_text(json.dumps(private_manifest, indent=2, sort_keys=True) + "\n")
    variant_path.write_text(json.dumps(variant, indent=2, sort_keys=True) + "\n")
    return {"status": "resampled", "selected": len(selected)}


def select_tasks(
    source_roots: list[pathlib.Path],
    tasks_per_family: int,
    explicit_tasks: list[str] | None,
) -> list[pathlib.Path]:
    if explicit_tasks:
        selected = []
        for task in explicit_tasks:
            for root in source_roots + [LEGACY_SAMPLE_SOURCE_TASK_ROOT]:
                candidate = root / task
                if candidate.is_dir():
                    selected.append(candidate)
                    break
            else:
                raise FileNotFoundError(f"Cannot locate explicit smoke task {task}")
        return selected

    by_family: dict[tuple[str, str], list[pathlib.Path]] = {}
    for root in source_roots:
        if not root.is_dir():
            raise FileNotFoundError(root)
        for task_dir in sorted(root.iterdir()):
            if not (task_dir / "environment/app/observations/manifest.json").is_file():
                continue
            by_family.setdefault(task_family(task_dir), []).append(task_dir)
    selected = []
    for key in sorted(by_family):
        selected.extend(by_family[key][:tasks_per_family])
    return selected


def remove_tree_with_retries(path: pathlib.Path) -> None:
    for attempt in range(6):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt == 5:
                raise
            time.sleep(0.5 * (attempt + 1))


def build_smoke(
    source_roots: list[pathlib.Path],
    output_root: pathlib.Path,
    overwrite: bool,
    tasks_per_family: int,
    explicit_tasks: list[str] | None,
    run_candidates: bool,
    resample_hidden: bool,
) -> dict:
    if output_root.exists():
        if not overwrite:
            raise FileExistsError(f"{output_root} exists; pass --overwrite")
        old = output_root.with_name(f"{output_root.name}.old.{int(time.time())}.{os.getpid()}")
        output_root.rename(old)
        remove_tree_with_retries(old)
    output_root.mkdir(parents=True, exist_ok=True)

    selected_tasks = select_tasks(source_roots, tasks_per_family, explicit_tasks)
    scenario_pools = collect_scenario_pools(source_roots + [LEGACY_SAMPLE_SOURCE_TASK_ROOT]) if resample_hidden else {}
    report = {
        "output_root": str(output_root),
        "source_roots": [str(root) for root in source_roots],
        "tasks_per_family": tasks_per_family,
        "run_candidates": run_candidates,
        "resample_hidden": resample_hidden,
        "selected_task_count": len(selected_tasks),
        "tasks": [],
    }
    for src in selected_tasks:
        name = src.name
        dst = output_root / "tasks" / name
        if not src.is_dir():
            raise FileNotFoundError(src)
        shutil.copytree(src, dst)
        judge_path = dst / "tests/private/judge.py"
        judge_path.write_text(SEMANTIC_JUDGE)
        judge_path.chmod(0o755)
        hidden_resampling = (
            resample_hidden_scenarios(dst, scenario_pools.get(task_family(dst), []))
            if resample_hidden
            else {"status": "not_requested"}
        )

        results = {}
        expectations = {}
        passed_smoke = None
        if run_candidates:
            candidates = output_root / "candidate_workspaces" / name
            blank_ws = candidates / "blank"
            public_ws = candidates / "public_lookup"
            oracle_ws = candidates / "oracle_like"
            blank_ws.mkdir(parents=True)
            write_public_lookup_candidate(public_ws, dst)
            write_oracle_like_candidate(oracle_ws, dst)

            results = {
                "blank": run_judge(dst, blank_ws),
                "public_lookup": run_judge(dst, public_ws),
                "oracle_like": run_judge(dst, oracle_ws),
            }
            expectations = {
                "blank_fails": not results["blank"].get("passed", False),
                "public_lookup_fails": not results["public_lookup"].get("passed", False),
                "oracle_like_passes": bool(results["oracle_like"].get("passed", False)),
            }
            passed_smoke = all(expectations.values())
        report["tasks"].append({
            "task_id": name,
            "family_id": json.loads((dst / "tests/private/variant.json").read_text()).get("family_id"),
            "source_group": json.loads((dst / "environment/app/observations/manifest.json").read_text()).get("source_group"),
            "hidden_resampling": hidden_resampling,
            "expectations": expectations,
            "passed_smoke": passed_smoke,
            "results": results,
        })

    report["passed"] = all(item["passed_smoke"] for item in report["tasks"]) if run_candidates else True
    report["family_count"] = len({(item.get("source_group"), item["family_id"]) for item in report["tasks"]})
    (output_root / "semantic_verifier_smoke_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    (output_root / "README.md").write_text(textwrap.dedent(f"""\
        # Semantic Verifier Smoke

        This smoke set compares a true10-style structural verifier with a
        semantic hidden verifier that uses tolerant field checks rather than
        exact hidden signature matching.

        Report: `semantic_verifier_smoke_report.json`
        Source task roots: `{", ".join(str(root) for root in source_roots)}`
        Selected task count: {len(selected_tasks)}
        Family count: {report["family_count"]}
        """))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-task-root", type=pathlib.Path, action="append", dest="source_task_roots")
    parser.add_argument("--output-root", type=pathlib.Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--tasks-per-family", type=int, default=3)
    parser.add_argument("--task", action="append", dest="explicit_tasks")
    parser.add_argument("--skip-local-candidates", action="store_true")
    parser.add_argument("--resample-hidden", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    source_roots = args.source_task_roots or DEFAULT_SOURCE_TASK_ROOTS
    explicit_tasks = args.explicit_tasks
    if explicit_tasks is None and args.tasks_per_family == 0:
        explicit_tasks = DEFAULT_SMOKE_TASKS
    report = build_smoke(
        source_roots,
        args.output_root,
        args.overwrite,
        args.tasks_per_family,
        explicit_tasks,
        run_candidates=not args.skip_local_candidates,
        resample_hidden=args.resample_hidden,
    )
    by_status = {
        "passed": sum(1 for item in report["tasks"] if item["passed_smoke"] is True),
        "failed": sum(1 for item in report["tasks"] if item["passed_smoke"] is False),
        "not_run": sum(1 for item in report["tasks"] if item["passed_smoke"] is None),
    }
    print(json.dumps({
        "output_root": report["output_root"],
        "passed": report["passed"],
        "family_count": report["family_count"],
        "selected_task_count": report["selected_task_count"],
        "by_status": by_status,
        "failed_tasks": [
            {
                "task_id": item["task_id"],
                "family_id": item["family_id"],
                "source_group": item.get("source_group"),
                "expectations": item["expectations"],
                "passed_smoke": item["passed_smoke"],
            }
            for item in report["tasks"]
            if item["passed_smoke"] is False
        ],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
