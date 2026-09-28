#!/usr/bin/env python3
"""Install hidden-oracle judges for materialized new10 tasks."""

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
DEFAULT_TASK_ROOT = DATA_ROOT / "software_reconstruction/materialized_planned2400_20260828/new10"
DEFAULT_SAMTOOLS_RUNNER = (
    Path(__file__).resolve().parents[1]
    / "oracle_validation/validate_new10_oracles_daytona.py"
)
DEFAULT_REPORT = (
    DATA_ROOT
    / "software_reconstruction/materialized_planned2400_20260828/new10_hidden_oracle_integration_report.json"
)


DOCKERFILES = {
    "sqlite_analytics": "FROM python:3.11-slim",
    "ajv_schema": "FROM python:3.11-slim\nRUN pip install --no-cache-dir jsonschema",
    "z3_constraint_system": "FROM python:3.11-slim\nRUN pip install --no-cache-dir z3-solver",
    "duckdb_reporting": "FROM python:3.11-slim\nRUN pip install --no-cache-dir duckdb pandas numpy",
    "opa_rego_policy": "FROM python:3.11-slim",
    "container_supply_chain": "FROM python:3.11-slim",
    "gdal_geospatial": "FROM python:3.11-slim\nRUN pip install --no-cache-dir shapely pyproj",
    "network_security_pcap": "FROM python:3.11-slim\nRUN pip install --no-cache-dir scapy",
    "document_ocr_publishing": "FROM python:3.11-slim\nRUN pip install --no-cache-dir pillow",
    "samtools_bio_qc": "FROM python:3.11-slim\nRUN apt-get update && apt-get install -y --no-install-recommends samtools bcftools seqkit && rm -rf /var/lib/apt/lists/*",
}


ORACLE_SOURCE = r'''
import hashlib, json, math, sqlite3

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()

def stable_int(value, modulo=1000):
    text = json.dumps(value, sort_keys=True, default=str)
    return sum((idx + 1) * ord(ch) for idx, ch in enumerate(text)) % modulo

def stable_float(value, scale=1.0, offset=0.0):
    return offset + scale * (1 + stable_int(value, 997) / 997)

def sqlite_analytics(params):
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
    create table orders(id integer primary key, customer text, region text, amount real, day integer, status text);
    create table adjustments(order_id integer, delta real);
    """)
    rows = []
    depth = 6 + stable_int(params.get("join_depth"), 8)
    window = int(stable_float(params.get("date_window"), 25, 5))
    statuses = ["paid", "refunded", "pending"]
    for idx in range(36):
        rows.append((idx, f"C{idx%depth}", ["na","eu","apac"][idx%3], 10 + (idx * 7) % 53, idx % window, statuses[(idx + stable_int(params.get("null_policy"), 3)) % 3]))
    conn.executemany("insert into orders values (?,?,?,?,?,?)", rows)
    conn.executemany("insert into adjustments values (?,?)", [(idx, ((idx % 5) - 2) * 1.25) for idx in range(0, 36, 3)])
    q = """
    select region, status, round(sum(amount + coalesce(delta,0)), 3) as total, count(*) as n
    from orders left join adjustments on orders.id = adjustments.order_id
    where day <= ?
    group by region, status
    order by region, status
    """
    result = conn.execute(q, (window // 2,)).fetchall()
    conn.close()
    return {"window": window, "join_depth": depth, "rows": result}

def ajv_schema(params):
    import jsonschema
    branch_count = 2 + stable_int(params.get("union_branch"), 7)
    required_field_count = 1 + stable_int(params.get("required_fields"), 9)
    recursive_depth = 1 + stable_int(params.get("recursive_ref"), 11)
    format_rule_count = 1 + stable_int(params.get("format"), 13)
    additional_property_budget = stable_int(params.get("additional_properties"), 17)
    min_items = 1 + required_field_count % 5
    item_count = min_items + branch_count % 4
    require_meta = recursive_depth % 2 == 0
    allow_additional = additional_property_budget % 2 == 0
    formats = ["baseline", "strict", "compat", "stress", "edge"]
    selected_format = str(params.get("format", formats[stable_int(params, len(formats))]))
    schema = {
        "type": "object",
        "required": ["kind", "items"] + (["meta"] if require_meta else []),
        "properties": {
            "kind": {"type": "string"},
            "items": {"type": "array", "minItems": min_items, "items": {"type": "number"}},
            "meta": {"type": "object", "additionalProperties": {"type": "string"}},
        },
        "additionalProperties": allow_additional,
    }
    payload = {"kind": selected_format, "items": list(range(item_count))}
    if require_meta:
        payload["meta"] = {"policy": str(params.get("additional_properties", "strict"))}
    if allow_additional:
        payload["extension"] = stable_int(params, 97)
    errors = sorted(e.path for e in jsonschema.Draft202012Validator(schema).iter_errors(payload))
    return {
        "min_items": min_items,
        "item_count": item_count,
        "branch_count": branch_count,
        "required_field_count": required_field_count,
        "recursive_depth": recursive_depth,
        "format_rule_count": format_rule_count,
        "additional_property_budget": additional_property_budget,
        "require_meta": require_meta,
        "allow_additional": allow_additional,
        "selected_format": selected_format,
        "valid": not errors,
        "error_count": len(errors),
        "payload_key_count": len(payload),
    }

def z3_constraint_system(params):
    from z3 import If, Int, Optimize, Sum, sat
    n = 3 + stable_int(params.get("variable_count"), 5)
    lower = stable_int(params.get("bound_shape"), 4)
    penalty = 1 + stable_int(params.get("optimization_goal"), 7)
    xs = [Int(f"x{i}") for i in range(n)]
    opt = Optimize()
    for i, x in enumerate(xs):
        opt.add(x >= lower + i, x <= lower + i + 9)
    opt.add(Sum(xs) >= n * lower + stable_int(params.get("constraint_density"), 12))
    objective = Sum([If(x % 2 == 0, x * penalty, x) for x in xs])
    opt.minimize(objective)
    status = opt.check()
    if status != sat:
        return {"status": str(status), "n": n}
    model = opt.model()
    values = [model.eval(x).as_long() for x in xs]
    return {"status": "sat", "n": n, "lower": lower, "penalty": penalty, "values": values, "objective": sum((v * penalty if v % 2 == 0 else v) for v in values)}

def duckdb_reporting(params):
    import duckdb
    import pandas as pd
    n = 40 + stable_int(params.get("window_frame"), 40)
    df = pd.DataFrame({
        "grp": [f"G{i%5}" for i in range(n)],
        "region": [["na","eu","apac"][i%3] for i in range(n)],
        "amount": [(i * 13 + stable_int(params.get("type_cast_policy"), 17)) % 101 for i in range(n)],
    })
    con = duckdb.connect(database=":memory:")
    con.register("events", df)
    rows = con.execute("select region, grp, round(avg(amount), 3), count(*) from events group by region, grp order by region, grp").fetchall()
    return {"n": n, "rows": rows[:8], "row_count": len(rows)}

def opa_rego_policy(params):
    roles = ["viewer", "editor", "admin", "auditor"]
    resources = ["configmap", "secret", "deployment", "service"]
    identity = params.get("identity", params.get("role_matrix"))
    resource_shape = params.get("resource_shape", params.get("resource_tree"))
    namespace = str(params.get("namespace", params.get("environment_scope", "default")))
    role = roles[stable_int(identity, len(roles))]
    resource = resources[stable_int(resource_shape, len(resources))]
    exception = bool(params.get("exception", False))
    overlay_tier = stable_int(params.get("overlay"), 5)
    deny = resource == "secret" and role not in {"admin", "auditor"} and not exception
    allow = not deny and not (namespace.startswith("namespace_") and role == "viewer" and overlay_tier >= 3)
    obligations = sorted([f"audit:{namespace}", f"resource:{resource}", f"role:{role}", f"overlay:{overlay_tier}"])
    return {
        "role": role,
        "resource": resource,
        "namespace": namespace,
        "exception_applied": exception,
        "overlay_tier": overlay_tier,
        "allow": allow,
        "deny": deny,
        "obligations": obligations,
    }

def container_supply_chain(params):
    layers = []
    base = str(params.get("base_image", "python"))
    for idx in range(4 + stable_int(params.get("layer_order"), 4)):
        content = f"{base}:{idx}:{params.get('sbom_scope')}:{params.get('attestation_policy')}"
        layers.append(hashlib.sha256(content.encode()).hexdigest())
    merkle = digest(layers)
    vuln_budget = stable_int(params.get("vulnerability_policy"), 10)
    return {"base": base, "layer_count": len(layers), "merkle": merkle, "vuln_budget": vuln_budget, "attestation": digest({"layers": layers, "policy": params.get("attestation_policy")})[:16]}

def gdal_geospatial(params):
    from pyproj import Transformer
    from shapely.geometry import LineString, Polygon
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    shift = stable_float({"crs": params.get("crs"), "bbox": params.get("bbox"), "params": params}, 0.2)
    resolution = max(0.1, float(params.get("resolution", 1.0)))
    point_count = 12 + stable_int({"layer_filter": params.get("layer_filter"), "params": params}, 17)
    wave = 2 + stable_int(params.get("nodata"), 7)
    pts = [
        transformer.transform(
            -122 + i * (0.004 + resolution / 10000) + shift / 100,
            37 + math.sin(i / wave) / 100,
        )
        for i in range(point_count)
    ]
    line = LineString(pts)
    bbox = Polygon.from_bounds(min(x for x, _ in pts), min(y for _, y in pts), max(x for x, _ in pts), max(y for _, y in pts))
    return {
        "length": round(float(line.length), 3),
        "area": round(float(bbox.area), 3),
        "bounds": [round(float(x), 3) for x in bbox.bounds],
        "point_count": point_count,
        "resolution": round(resolution, 3),
        "nodata_bucket": stable_int(params.get("nodata"), 11),
    }

def network_security_pcap(params):
    from scapy.all import IP, TCP, UDP, raw
    requested = max(8, int(float(params.get("port", params.get("session_window", 8)))))
    loss = bool(params.get("packet_loss", False))
    n = 8 + requested % 17
    if loss:
        n = max(4, n - 3)
    protocol = str(params.get("protocol", "mixed")).lower()
    destination_port = max(1, min(65535, requested))
    packets = []
    for idx in range(n):
        use_udp = protocol in {"udp", "dns", "dhcp"} or (protocol not in {"tcp", "http", "https"} and idx % 3 == 0)
        if use_udp:
            pkt = IP(src=f"10.0.0.{idx%5+1}", dst="10.0.1.2") / UDP(sport=2000+idx, dport=destination_port)
        else:
            pkt = IP(src=f"10.0.0.{idx%5+1}", dst="10.0.1.1") / TCP(sport=1000+idx, dport=destination_port)
        packets.append(pkt)
    digest_bytes = hashlib.sha256(b"".join(raw(p) for p in packets)).hexdigest()
    alert_threshold = stable_int(params.get("alert_rule"), 7)
    return {
        "packet_count": n,
        "protocol": protocol,
        "tcp": sum(1 for p in packets if TCP in p),
        "udp": sum(1 for p in packets if UDP in p),
        "destination_port": destination_port,
        "loss_applied": loss,
        "flow_score": stable_int(params.get("flow_pattern"), 997),
        "alert_score": stable_int(params.get("alert_rule"), 997),
        "alert_count": sum(1 for idx in range(n) if idx % 7 <= alert_threshold),
        "byte_count": sum(len(raw(p)) for p in packets),
        "digest": digest_bytes[:20],
    }

def document_ocr_publishing(params):
    from PIL import Image, ImageDraw, ImageFont
    page_range = max(1, int(float(params.get("page_range", params.get("layout_template", 1)))))
    dpi = max(1, int(float(params.get("dpi", params.get("dpi_profile", 72)))))
    width = 160 + stable_int({"page_range": page_range, "metadata": params.get("metadata"), "params": params}, 121)
    height = 80 + page_range % 97
    img = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(img)
    language = str(params.get("language", params.get("language_model", "baseline")))
    font_name = str(params.get("font", params.get("table_structure", "default")))
    metadata_bucket = stable_int(params.get("metadata"), 17)
    text = f"{language} {font_name} page={page_range} meta={metadata_bucket}"
    line_count = 1 + dpi % 4
    for idx in range(line_count):
        draw.text((10, 8 + idx * 13), text[: max(8, len(text) - idx)], fill=0, font=ImageFont.load_default())
    hist = img.histogram()
    return {
        "size": list(img.size),
        "ink": int(sum(hist[:128])),
        "blank": int(sum(hist[128:])),
        "line_count": line_count,
        "text_length": len(text),
        "metadata_bucket": metadata_bucket,
        "text_digest": hashlib.sha256(text.encode()).hexdigest()[:16],
    }
'''


JUDGE = r'''#!/usr/bin/env python3
import argparse
import json
import pathlib
import subprocess
import sys

import new10_oracle

EDITABLE_SUFFIXES = {
    ".py", ".json", ".yaml", ".yml", ".toml", ".txt", ".md", ".csv", ".tsv",
    ".sql", ".rego", ".jsonnet", ".pcap", ".fa", ".fastq", ".sam", ".vcf",
    ".geojson", ".png", ".xml", ".html",
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
        "family_oracle_registered": family in new10_oracle.ORACLES,
    }
    details = []
    if all(checks.values()):
        for scenario in hidden:
            try:
                expected = new10_oracle.ORACLES[family](scenario["parameters"])
                expected_signature = new10_oracle.digest(expected)
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
                got_signature = new10_oracle.digest(summary)
            ok = got_signature == expected_signature or summary == expected
            details.append({"scenario_id": scenario.get("scenario_id"), "passed": ok, "expected_signature": expected_signature, "candidate_signature": got_signature})
            if not ok:
                checks["candidate_matches_hidden_oracle"] = False
                break
        else:
            checks["private_oracle_executes"] = True
            checks["candidate_executes_hidden_scenarios"] = True
            checks["candidate_matches_hidden_oracle"] = True
    report = {"passed": all(checks.values()), "checks": checks, "copied_public_products": sorted(copied_public), "task_id": variant.get("task_id"), "family_id": family, "details": details}
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


def samtools_oracle(path: Path) -> str:
    module = ast.parse(path.read_text(encoding="utf-8"))
    smoke_code = None
    for node in module.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "SMOKE_CODE":
            smoke_code = ast.literal_eval(node.value)
            break
    if smoke_code is None:
        raise RuntimeError(f"failed to extract SMOKE_CODE from {path}")
    prefix = smoke_code.split("\ntool_versions = {}", 1)[0]
    prefix = prefix.replace('RECORDS = json.loads(Path("/tmp/records.json").read_text())\n', "")
    return prefix.rstrip() + "\nORACLES = {\"samtools_bio_qc\": smoke_scenario}\n"


def oracle_source(samtools_runner: Path) -> str:
    return ORACLE_SOURCE.rstrip() + "\n" + samtools_oracle(samtools_runner) + """
ORACLES.update({
    "sqlite_analytics": sqlite_analytics,
    "ajv_schema": ajv_schema,
    "z3_constraint_system": z3_constraint_system,
    "duckdb_reporting": duckdb_reporting,
    "opa_rego_policy": opa_rego_policy,
    "container_supply_chain": container_supply_chain,
    "gdal_geospatial": gdal_geospatial,
    "network_security_pcap": network_security_pcap,
    "document_ocr_publishing": document_ocr_publishing,
})
"""


def dockerfile_for(base: str) -> str:
    return base.strip() + "\n" + TEST_DOCKERFILE_SUFFIX


def integrate_task(task: Path, source: str) -> dict[str, Any]:
    variant_path = task / "tests/private/variant.json"
    if not variant_path.is_file():
        return {"task": str(task), "updated": False, "error": "missing variant.json"}
    variant = json.loads(variant_path.read_text(encoding="utf-8"))
    family = variant["family_id"]
    if family not in DOCKERFILES:
        return {"task": str(task), "updated": False, "family_id": family, "error": "missing dockerfile"}
    write(task / "tests/private/new10_oracle.py", source)
    write(task / "tests/private/judge.py", JUDGE, executable=True)
    write(task / "tests/Dockerfile", dockerfile_for(DOCKERFILES[family]))
    write(
        task / "tests/private/new10_oracle_integration.json",
        json.dumps(
            {
                "task_id": task.name,
                "family_id": family,
                "integrated_at": utc_now(),
                "judge": "new10 hidden native-oracle adapter",
                "hidden_scenario_count": len(variant.get("hidden_scenarios", [])),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    return {"task": str(task), "updated": True, "family_id": family}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-root", type=Path, default=DEFAULT_TASK_ROOT)
    parser.add_argument("--samtools-runner", type=Path, default=DEFAULT_SAMTOOLS_RUNNER)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--limit-per-family", type=int, default=0, help="0 means all tasks")
    args = parser.parse_args()
    task_root = args.task_root.resolve()
    if task_root == REPOSITORY_ROOT or REPOSITORY_ROOT in task_root.parents:
        parser.error("task root must stay outside the source tree")
    source = oracle_source(args.samtools_runner)
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
    results = [integrate_task(task, source) for task in tasks]
    updated = [item for item in results if item.get("updated")]
    family_counts = Counter(item["family_id"] for item in updated)
    report = {
        "schema": "new10-hidden-oracle-integration-v1",
        "created_at": utc_now(),
        "task_root": str(task_root),
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
