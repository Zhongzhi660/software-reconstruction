
import hashlib, json, math, os, subprocess, sys, tempfile
from pathlib import Path


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

def audio(params):
    import numpy as np
    from scipy import signal
    rate = 8000 + int(stable_float(params.get("sample_rate"), 24000))
    window = 128 + int(stable_float(params.get("window_size"), 512))
    cutoff = 300 + int(stable_float(params.get("filter_type"), 1800))
    noise = stable_float(params.get("noise_profile"), 0.08, 0.005)
    phase = stable_float(params.get("channel_layout"), 1.5, 0.1)
    t = np.arange(rate // 8) / rate
    x = np.sin(2 * np.pi * 440 * t) + 0.35 * np.sin(2 * np.pi * (880 + phase * 10) * t)
    x = x + noise * np.cos(2 * np.pi * 123 * t)
    sos = signal.butter(4, min(0.95, cutoff / (rate / 2)), btype="lowpass", output="sos")
    y = signal.sosfilt(sos, x)
    freqs, power = signal.welch(y, fs=rate, nperseg=min(window, len(y)))
    return {
        "rate": rate,
        "window": window,
        "cutoff": cutoff,
        "rms": round(float(np.sqrt(np.mean(y ** 2))), 8),
        "peak_freq": round(float(freqs[int(np.argmax(power))]), 5),
        "power_max": round(float(np.max(power)), 10),
    }

ORACLES["audio_signal_processing"] = audio
