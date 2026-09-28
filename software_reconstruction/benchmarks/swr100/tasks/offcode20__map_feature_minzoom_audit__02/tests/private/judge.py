#!/usr/bin/env python3
import argparse
import importlib
import json
import pathlib
import subprocess
import sys
import tarfile
import benchmark_semantic


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


def _without_top_level_seed(summary):
    copied = json.loads(json.dumps(summary))
    if isinstance(copied, dict):
        copied.pop("seed", None)
    return copied


def validate_semantics(family, got, expected):
    got = candidate_summary(got)
    expected = candidate_summary(expected)
    return benchmark_semantic.validate(got, expected, family)



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
