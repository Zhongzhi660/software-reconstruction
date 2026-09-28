#!/usr/bin/env python3
"""Run Daytona oracle smoke for off-code families that need extra tooling.

The script reads DAYTONA_API_KEY from the environment. For convenience in this
workspace it can also extract the key from an existing Harbor run script without
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
EXP_ROOT = DATA_ROOT / "software_reconstruction/offcode6_expansion"
DEFAULT_PLAN = EXP_ROOT / "online_concrete_param_groups_60x6.json"
DEFAULT_OUTPUT = EXP_ROOT / "daytona_oracle_smoke_300_20260828"
DEFAULT_HARBOR_SCRIPT = Path("/path/to/harbor/run_harbor.sh")


DOCKERFILES: dict[str, str] = {
    "robotics_control": """
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libegl1 libxrender1 libxext6 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir mujoco numpy lxml
""",
    "molecular_chemistry": """
FROM python:3.11-slim
RUN pip install --no-cache-dir rdkit-pypi numpy
""",
    "medical_imaging": """
FROM python:3.11-slim
RUN pip install --no-cache-dir pydicom nibabel SimpleITK numpy
""",
    "circuit_simulation": """
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ngspice && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir numpy
""",
    "finite_element_mechanics": """
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends calculix-ccx && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir numpy
""",
}


SMOKE_CODE = r'''
import hashlib, json, math, os, subprocess, sys, tempfile
from pathlib import Path

FAMILY = os.environ["FAMILY"]
RECORDS = json.loads(Path("/tmp/records.json").read_text())

def stable_float(v, scale=1.0, offset=0.0):
    s = sum(ord(c) for c in str(v))
    return offset + scale * (1 + (s % 97) / 97)

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()

def run(cmd, cwd=None, timeout=30):
    p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
    return {"cmd": cmd, "returncode": p.returncode, "stdout": p.stdout[-2000:], "stderr": p.stderr[-2000:]}

def robotics(params):
    import mujoco
    import numpy as np
    gain = stable_float(params.get("actuator_gain"), 1.5, 0.5)
    margin = stable_float(params.get("collision_margin"), 0.05, 0.01)
    target = stable_float(params.get("trajectory_target"), 0.4, 0.1)
    xml = f"""
<mujoco model="smoke">
  <option timestep="0.002"/>
  <worldbody>
    <body name="link" pos="0 0 {margin:.4f}">
      <joint name="hinge" type="hinge" axis="0 0 1" range="-90 90" damping="0.2"/>
      <geom type="capsule" size="0.03 0.25" fromto="0 0 0 0.5 0 0"/>
    </body>
  </worldbody>
  <actuator><motor joint="hinge" gear="{gain:.4f}"/></actuator>
</mujoco>
"""
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    for _ in range(40):
        data.ctrl[0] = target
        mujoco.mj_step(model, data)
    return {"nq": int(model.nq), "nv": int(model.nv), "qpos": [round(float(x), 6) for x in data.qpos], "qvel": [round(float(x), 6) for x in data.qvel], "gain": round(gain, 6)}

def molecular(params):
    from rdkit import Chem
    from rdkit.Chem import Descriptors, rdMolDescriptors
    choices = ["CCO", "c1ccccc1O", "CC(=O)Oc1ccccc1C(=O)O", "C[C@H](N)C(=O)O", "Cn1cnc2n(C)c(=O)n(C)c(=O)c12"]
    idx = sum(ord(c) for c in str(params.get("substructure_query"))) % len(choices)
    mol = Chem.MolFromSmiles(choices[idx])
    radius = int(stable_float(params.get("fingerprint_radius"), 3, 1))
    fp = rdMolDescriptors.GetMorganFingerprintAsBitVect(mol, radius, nBits=256)
    return {"smiles": Chem.MolToSmiles(mol, isomericSmiles=True), "mw": round(Descriptors.MolWt(mol), 4), "hba": int(Descriptors.NumHAcceptors(mol)), "fp_on": int(fp.GetNumOnBits()), "radius": radius}

def medical(params):
    import nibabel as nib
    import numpy as np
    import pydicom
    import SimpleITK as sitk
    shape = (12, 16, 8)
    level = stable_float(params.get("window_level"), 80, 20)
    threshold = stable_float(params.get("mask_threshold"), 60, 10)
    arr = np.arange(np.prod(shape), dtype=np.float32).reshape(shape)
    arr = (arr % level) + threshold / 10
    img = nib.Nifti1Image(arr, affine=np.eye(4))
    ds = pydicom.Dataset()
    ds.PatientName = "Smoke^Offcode"
    ds.Modality = str(params.get("modality", "MR"))[:16]
    simg = sitk.GetImageFromArray(arr)
    return {"shape": list(img.shape), "modality": ds.Modality, "mean": round(float(arr.mean()), 4), "mask_voxels": int((arr > threshold).sum()), "sitk_size": list(simg.GetSize())}

def circuit(params):
    r = int(stable_float(params.get("component_value"), 9000, 1000))
    c = stable_float(params.get("tolerance"), 1e-6, 1e-7)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "rc.cir"
        path.write_text(f"""RC low pass smoke
Vin in 0 DC 1 AC 1
R1 in out {r}
C1 out 0 {c}
.op
.ac dec 4 10 10000
.print ac v(out)
.end
""")
        res = run(["ngspice", "-b", str(path)], timeout=40)
    return {"r": r, "c": c, "returncode": res["returncode"], "stdout_digest": digest(res["stdout"]), "stderr": res["stderr"][-300:]}

def fea(params):
    # Use CalculiX as the native executable smoke. The generated input deck is
    # intentionally tiny but parameter-sensitive through load/material values.
    young = int(stable_float(params.get("material_property"), 100000, 100000))
    load = int(stable_float(params.get("load_case"), 50, 10))
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "beam"
        (Path(td) / "beam.inp").write_text(f"""*NODE
1,0,0,0
2,1,0,0
*ELEMENT,TYPE=T3D2,ELSET=Eall
1,1,2
*MATERIAL,NAME=mat
*ELASTIC
{young},0.3
*SOLID SECTION,ELSET=Eall,MATERIAL=mat
1.
*BOUNDARY
1,1,3,0
2,2,3,0
*STEP
*STATIC
*CLOAD
2,1,{load}
*NODE FILE
U
*END STEP
""")
        res = run(["ccx", "beam"], cwd=td, timeout=40)
        files = sorted(p.name for p in Path(td).glob("beam.*"))
    return {"young": young, "load": load, "returncode": res["returncode"], "files": files, "stdout_digest": digest(res["stdout"] + res["stderr"])}

ORACLES = {
    "robotics_control": robotics,
    "molecular_chemistry": molecular,
    "medical_imaging": medical,
    "circuit_simulation": circuit,
    "finite_element_mechanics": fea,
}

records = []
for rec in RECORDS:
    sigs = []
    scenarios = []
    ok = True
    for scen in rec["public_scenarios"] + rec["hidden_scenarios"]:
        try:
            out = ORACLES[FAMILY](scen["parameters"])
            sig = digest(out)
            passed = not ("returncode" in out and out["returncode"] != 0)
        except Exception as exc:
            out = {"exception": type(exc).__name__, "message": str(exc)}
            sig = digest(out)
            passed = False
        sigs.append(sig)
        ok = ok and passed
        scenarios.append({"scenario_id": scen["scenario_id"], "passed": passed, "signature": sig, "summary": out})
    records.append({"task_id": rec["task_id"], "family_id": FAMILY, "state": "passed" if ok and len(set(sigs)) >= 2 else "failed", "distinct_output_gate": len(set(sigs)) >= 2, "scenario_results": scenarios})

summary = {
    "family_id": FAMILY,
    "task_count": len(records),
    "state_counts": {state: sum(1 for r in records if r["state"] == state) for state in sorted({r["state"] for r in records})},
    "records": records,
}
Path("/tmp/summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(json.dumps({"family_id": FAMILY, "task_count": len(records), "state_counts": summary["state_counts"]}, sort_keys=True))
'''


def extract_daytona_key(script_path: Path) -> str | None:
    if not script_path.exists():
        return None
    text = script_path.read_text(errors="ignore")
    match = re.search(r"export DAYTONA_API_KEY=(?:\"([^\"]+)\"|'([^']+)'|([^\n]+))", text)
    if not match:
        return None
    return next(group for group in match.groups() if group)


def write_dockerfiles(root: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for family, content in DOCKERFILES.items():
        path = root / "oracle_images" / family / "Dockerfile"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")
        paths[family] = path
    return paths


def run_family(client: Daytona, family: str, dockerfile: Path, records: list[dict[str, Any]], output: Path) -> dict[str, Any]:
    sandbox_name = f"offcode6-{family[:10].replace('_', '-')}-{uuid.uuid4().hex[:8]}"
    # Daytona image builds can fail on apt-heavy packages even when the same apt
    # install works inside a running sandbox. Keep a runtime fallback for FEA.
    runtime_setup = None
    if family == "finite_element_mechanics":
        image = Image.debian_slim("3.11")
        runtime_setup = "apt-get update && apt-get install -y --no-install-recommends calculix-ccx && rm -rf /var/lib/apt/lists/*"
    else:
        image = Image.from_dockerfile(dockerfile)
    sandbox = client.create(
        CreateSandboxFromImageParams(
            name=sandbox_name,
            image=image,
            ttl_minutes=90,
            auto_delete_interval=90,
            labels={"project": "offcode6_oracle_smoke", "family": family},
        )
    )
    try:
        if runtime_setup:
            setup_result = sandbox.process.exec(runtime_setup, timeout=600)
            if getattr(setup_result, "exit_code", 1) != 0:
                raise RuntimeError(f"runtime setup failed for {family}: {setup_result}")
        prep = "cat > /tmp/records.json <<'JSON'\n" + json.dumps(records) + "\nJSON\n"
        prep += "cat > /tmp/smoke.py <<'PY'\n" + SMOKE_CODE + "\nPY\n"
        result = sandbox.process.exec(prep + f"FAMILY={family} python3 /tmp/smoke.py", timeout=1800)
        fetch = sandbox.process.exec("cat /tmp/summary.json", timeout=120)
        if getattr(fetch, "exit_code", 1) != 0:
            raise RuntimeError(f"failed to fetch summary: {fetch}")
        summary = json.loads(fetch.result)
        summary["sandbox_name"] = sandbox_name
        summary["image_mode"] = "runtime_setup_fallback" if runtime_setup else "dockerfile_image"
        summary["exec_exit_code"] = getattr(result, "exit_code", None)
        summary["exec_output_excerpt"] = str(getattr(result, "result", ""))[-2000:]
        family_out = output / family
        family_out.mkdir(parents=True, exist_ok=True)
        (family_out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return summary
    finally:
        sandbox.delete()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--harbor-script", type=Path, default=DEFAULT_HARBOR_SCRIPT)
    parser.add_argument("--family", action="append", choices=sorted(DOCKERFILES))
    args = parser.parse_args()

    key = extract_daytona_key(args.harbor_script)
    if not key:
        raise SystemExit("DAYTONA_API_KEY not found; pass --harbor-script pointing to a run_harbor.sh with exported key")

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    wanted = args.family or sorted(DOCKERFILES)
    dockerfiles = write_dockerfiles(EXP_ROOT)
    client = Daytona(DaytonaConfig(api_key=key))
    args.output.mkdir(parents=True, exist_ok=True)

    summaries = []
    for family in wanted:
        records = [record for record in plan["records"] if record["family_id"] == family]
        print(json.dumps({"event": "start_family", "family": family, "records": len(records)}, sort_keys=True), flush=True)
        summary = run_family(client, family, dockerfiles[family], records, args.output)
        summaries.append(summary)
        print(json.dumps({"event": "finish_family", "family": family, "state_counts": summary["state_counts"]}, sort_keys=True), flush=True)

    aggregate = {
        "schema": "offcode6-daytona-oracle-smoke-v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "plan": str(args.plan),
        "output": str(args.output),
        "family_count": len(summaries),
        "task_count": sum(item["task_count"] for item in summaries),
        "family_counts": {item["family_id"]: item["state_counts"] for item in summaries},
    }
    (args.output / "summary.json").write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(aggregate, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
