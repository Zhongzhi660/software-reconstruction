#!/usr/bin/env python3
"""Run Daytona oracle smoke for new10 samtools_bio_qc tasks.

This supplements the local new10 native smoke, where samtools_bio_qc was marked
as needs_daytona_tooling because samtools/bcftools/seqkit were unavailable
locally. The Daytona API key is read from an existing Harbor run script without
printing or writing the secret.
"""

from __future__ import annotations

import argparse
import json
import re
import textwrap
import time
import uuid
from pathlib import Path
from typing import Any

from daytona_sdk import CreateSandboxFromImageParams, Daytona, DaytonaConfig, Image


DATA_ROOT = Path("/path/to/software_reconstruction_data")
EXP_ROOT = DATA_ROOT / "software_reconstruction/new10family_expansion"
DEFAULT_PLAN = EXP_ROOT / "online_concrete_param_groups_100x6.json"
DEFAULT_OUTPUT = EXP_ROOT / "daytona_oracle_smoke_samtools_60_20260828"
DEFAULT_HARBOR_SCRIPT = Path("/path/to/harbor/run_harbor.sh")


SMOKE_CODE = r'''
import hashlib, json, os, subprocess, tempfile
from pathlib import Path

RECORDS = json.loads(Path("/tmp/records.json").read_text())

BASES = "ACGT"

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()

def seed_from(value):
    return sum((idx + 1) * ord(ch) for idx, ch in enumerate(str(value)))

def run(cmd, cwd, timeout=60):
    p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
    return {
        "cmd": cmd,
        "returncode": p.returncode,
        "stdout": p.stdout[-4000:],
        "stderr": p.stderr[-4000:],
    }

def make_reference(params):
    seed = seed_from(params.get("reference", "")) + seed_from(params.get("region", ""))
    length = 900 + seed % 251
    seq = "".join(BASES[(seed + idx * 7 + idx // 11) % 4] for idx in range(length))
    return seq

def choose_region(params, length):
    seed = seed_from(params.get("region", ""))
    start = 30 + seed % max(1, length - 260)
    end = min(length, start + 120 + seed % 100)
    return start, end

def make_fastq_reads(seq, params):
    threshold = float(params.get("quality_threshold", 10))
    seed = seed_from(params)
    reads = []
    for idx in range(18):
        start = 1 + (seed + idx * 37) % (len(seq) - 80)
        length = 45 + (seed + idx * 11) % 31
        read = seq[start - 1:start - 1 + length]
        if idx % 4 == 0:
            read = read[:10] + "TTAA" + read[14:]
        q = max(2, min(40, int(threshold) + 10 + (idx % 9)))
        qual = chr(33 + q) * len(read)
        reads.append((f"read{idx:02d}", read, qual))
    return reads

def write_inputs(work, seq, params):
    (work / "ref.fa").write_text(">chr1\n" + "\n".join(seq[i:i+80] for i in range(0, len(seq), 80)) + "\n")
    reads = make_fastq_reads(seq, params)
    with (work / "reads.fastq").open("w") as fh:
        for name, read, qual in reads:
            fh.write(f"@{name}\n{read}\n+\n{qual}\n")

    seed = seed_from(params)
    mapq_base = max(1, min(60, int(float(params.get("quality_threshold", 10))) + 12))
    flag_seed = int(float(params.get("mapping_flags", 0)) * 1000)
    with (work / "sample.sam").open("w") as fh:
        fh.write("@HD\tVN:1.6\tSO:unsorted\n")
        fh.write(f"@SQ\tSN:chr1\tLN:{len(seq)}\n")
        fh.write("@RG\tID:rgA\tSM:sampleA\n@RG\tID:rgB\tSM:sampleB\n")
        for idx, (name, read, qual) in enumerate(reads):
            pos = 1 + (seed + idx * 29) % (len(seq) - len(read) - 1)
            flag = 16 if (flag_seed + idx) % 3 == 0 else 0
            rg = "rgA" if idx % 2 == 0 else "rgB"
            mapq = max(1, min(60, mapq_base + idx % 17))
            fh.write(f"{name}\t{flag}\tchr1\t{pos}\t{mapq}\t{len(read)}M\t*\t0\t0\t{read}\t{qual}\tRG:Z:{rg}\n")

    ploidy = max(1, min(6, int(params.get("ploidy", 2))))
    samples = [f"S{i}" for i in range(1, ploidy + 1)]
    with (work / "variants.vcf").open("w") as fh:
        fh.write("##fileformat=VCFv4.2\n")
        fh.write(f"##contig=<ID=chr1,length={len(seq)}>\n")
        fh.write('##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">\n')
        fh.write('##FORMAT=<ID=DP,Number=1,Type=Integer,Description="Read depth">\n')
        fh.write("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t" + "\t".join(samples) + "\n")
        for idx in range(8):
            pos = 40 + (seed + idx * 53) % (len(seq) - 80)
            ref = seq[pos - 1]
            alt = BASES[(BASES.index(ref) + (idx % 3) + 1) % 4]
            qual = round(float(params.get("quality_threshold", 10)) + 5 + idx * 3.3, 2)
            gts = []
            for sidx in range(len(samples)):
                gt = "0/1" if (idx + sidx) % 3 else "1/1"
                dp = 8 + ((seed + idx + sidx) % 31)
                gts.append(f"{gt}:{dp}")
            fh.write(f"chr1\t{pos}\tvar{idx}\t{ref}\t{alt}\t{qual}\tPASS\t.\tGT:DP\t" + "\t".join(gts) + "\n")

def smoke_scenario(params):
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        seq = make_reference(params)
        start, end = choose_region(params, len(seq))
        write_inputs(work, seq, params)

        commands = []
        for cmd in [
            ["samtools", "faidx", "ref.fa"],
            ["samtools", "view", "-bS", "sample.sam", "-o", "sample.bam"],
            ["samtools", "sort", "-o", "sample.sorted.bam", "sample.bam"],
            ["samtools", "index", "sample.sorted.bam"],
        ]:
            commands.append(run(cmd, work))

        min_mapq = max(1, min(50, int(float(params.get("quality_threshold", 10)))))
        flagstat = run(["samtools", "flagstat", "sample.sorted.bam"], work)
        depth = run(["samtools", "depth", "-a", "-r", f"chr1:{start}-{end}", "sample.sorted.bam"], work)
        filtered_count = run(["samtools", "view", "-c", "-q", str(min_mapq), "sample.sorted.bam"], work)
        norm = run(["bcftools", "norm", "-f", "ref.fa", "-o", "norm.vcf", "variants.vcf"], work)
        filt = run(["bcftools", "filter", "-i", f"QUAL>={min_mapq}", "-o", "filtered.vcf", "norm.vcf"], work)
        stats = run(["bcftools", "stats", "filtered.vcf"], work)
        seqkit_stats = run(["seqkit", "stats", "reads.fastq"], work)
        motif = "TTAA" if seed_from(params.get("reference", "")) % 2 == 0 else seq[start - 1:start + 2]
        seqkit_grep = run(["seqkit", "grep", "-s", "-p", motif, "reads.fastq"], work)
        commands.extend([flagstat, depth, filtered_count, norm, filt, stats, seqkit_stats, seqkit_grep])

        ok = all(item["returncode"] == 0 for item in commands)
        depth_lines = [line for line in depth["stdout"].splitlines() if line.strip()]
        return {
            "ok": ok,
            "reference_length": len(seq),
            "region": f"chr1:{start}-{end}",
            "min_mapq": min_mapq,
            "command_count": len(commands),
            "flagstat_digest": hashlib.sha256(flagstat["stdout"].encode()).hexdigest(),
            "depth_rows": len(depth_lines),
            "filtered_read_count": filtered_count["stdout"].strip(),
            "bcftools_stats_digest": hashlib.sha256(stats["stdout"].encode()).hexdigest(),
            "seqkit_stats_digest": hashlib.sha256(seqkit_stats["stdout"].encode()).hexdigest(),
            "seqkit_grep_digest": hashlib.sha256(seqkit_grep["stdout"].encode()).hexdigest(),
            "failed_commands": [item for item in commands if item["returncode"] != 0],
        }

tool_versions = {}
for name, cmd in {
    "samtools": ["samtools", "--version"],
    "bcftools": ["bcftools", "--version"],
    "seqkit": ["seqkit", "version"],
}.items():
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        tool_versions[name] = {"returncode": p.returncode, "output": (p.stdout + p.stderr).splitlines()[:3]}
    except Exception as exc:
        tool_versions[name] = {"returncode": 1, "error": f"{type(exc).__name__}: {exc}"}

records = []
for rec in RECORDS:
    scenario_results = []
    signatures = []
    ok = True
    for scen in rec["public_scenarios"] + rec["hidden_scenarios"]:
        try:
            summary = smoke_scenario(scen["parameters"])
            passed = bool(summary["ok"])
        except Exception as exc:
            summary = {"ok": False, "exception": type(exc).__name__, "message": str(exc)}
            passed = False
        sig = digest(summary)
        signatures.append(sig)
        ok = ok and passed
        scenario_results.append({
            "scenario_id": scen["scenario_id"],
            "passed": passed,
            "signature": sig,
            "summary": summary,
        })
    distinct_output_gate = len(set(signatures)) >= 2
    records.append({
        "task_id": rec["task_id"],
        "demo_id": rec["demo_id"],
        "family_id": rec["family_id"],
        "state": "passed" if ok and distinct_output_gate else "failed",
        "distinct_output_gate": distinct_output_gate,
        "scenario_results": scenario_results,
    })

states = sorted({r["state"] for r in records})
summary = {
    "family_id": "samtools_bio_qc",
    "task_count": len(records),
    "state_counts": {state: sum(1 for r in records if r["state"] == state) for state in states},
    "tool_versions": tool_versions,
    "records": records,
}
Path("/tmp/summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(json.dumps({"family_id": "samtools_bio_qc", "task_count": len(records), "state_counts": summary["state_counts"]}, sort_keys=True))
'''


def extract_daytona_key(script_path: Path) -> str | None:
    if not script_path.exists():
        return None
    text = script_path.read_text(errors="ignore")
    match = re.search(r"export DAYTONA_API_KEY=(?:\"([^\"]+)\"|'([^']+)'|([^\n]+))", text)
    if not match:
        return None
    return next(group for group in match.groups() if group)


def run_samtools_smoke(client: Daytona, records: list[dict[str, Any]], output: Path) -> dict[str, Any]:
    sandbox_name = f"new10-samtools-{uuid.uuid4().hex[:8]}"
    sandbox = client.create(
        CreateSandboxFromImageParams(
            name=sandbox_name,
            image=Image.debian_slim("3.11"),
            ttl_minutes=120,
            auto_delete_interval=120,
            labels={"project": "new10_oracle_smoke", "family": "samtools_bio_qc"},
        )
    )
    try:
        setup_cmd = textwrap.dedent(
            """
            set -e
            apt-get update
            apt-get install -y --no-install-recommends ca-certificates wget tar samtools bcftools seqkit
            rm -rf /var/lib/apt/lists/*
            samtools --version >/tmp/samtools.version
            bcftools --version >/tmp/bcftools.version
            seqkit version >/tmp/seqkit.version
            """
        ).strip()
        setup = sandbox.process.exec(setup_cmd, timeout=1200)
        if getattr(setup, "exit_code", 1) != 0:
            raise RuntimeError(f"tool setup failed: {setup}")

        prep = "cat > /tmp/records.json <<'JSON'\n" + json.dumps(records) + "\nJSON\n"
        prep += "cat > /tmp/smoke.py <<'PY'\n" + SMOKE_CODE + "\nPY\n"
        result = sandbox.process.exec(prep + "python3 /tmp/smoke.py", timeout=3600)
        fetch = sandbox.process.exec("cat /tmp/summary.json", timeout=120)
        if getattr(fetch, "exit_code", 1) != 0:
            raise RuntimeError(f"failed to fetch summary: {fetch}")

        summary = json.loads(fetch.result)
        summary["sandbox_name"] = sandbox_name
        summary["setup_exit_code"] = getattr(setup, "exit_code", None)
        summary["exec_exit_code"] = getattr(result, "exit_code", None)
        summary["exec_output_excerpt"] = str(getattr(result, "result", ""))[-2000:]
        output.mkdir(parents=True, exist_ok=True)
        (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return summary
    finally:
        sandbox.delete()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--harbor-script", type=Path, default=DEFAULT_HARBOR_SCRIPT)
    args = parser.parse_args()

    key = extract_daytona_key(args.harbor_script)
    if not key:
        raise SystemExit("DAYTONA_API_KEY not found; pass --harbor-script pointing to a run_harbor.sh with exported key")

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    records = [record for record in plan["records"] if record["family_id"] == "samtools_bio_qc"]
    if len(records) != 60:
        raise SystemExit(f"expected 60 samtools_bio_qc records, got {len(records)}")

    client = Daytona(DaytonaConfig(api_key=key))
    print(json.dumps({"event": "start_family", "family": "samtools_bio_qc", "records": len(records)}, sort_keys=True), flush=True)
    family_summary = run_samtools_smoke(client, records, args.output)
    print(json.dumps({"event": "finish_family", "family": "samtools_bio_qc", "state_counts": family_summary["state_counts"]}, sort_keys=True), flush=True)

    aggregate = {
        "schema": "new10-samtools-daytona-oracle-smoke-v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "plan": str(args.plan),
        "output": str(args.output),
        "task_count": family_summary["task_count"],
        "family_counts": {"samtools_bio_qc": family_summary["state_counts"]},
        "tool_versions": family_summary.get("tool_versions", {}),
    }
    (args.output / "aggregate_summary.json").write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(aggregate, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
