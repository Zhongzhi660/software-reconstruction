
import hashlib, io, json, math, os, subprocess, sys, tempfile
from pathlib import Path

import numpy as np


def stable_int(value, modulo=1000):
    text = json.dumps(value, sort_keys=True)
    return sum((idx + 1) * ord(ch) for idx, ch in enumerate(text)) % modulo

def stable_float(value, scale=1.0, offset=0.0):
    return offset + scale * (1 + stable_int(value, 997) / 997)

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()

def run(cmd, cwd=None, timeout=60):
    p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
    return {"cmd": cmd, "returncode": p.returncode, "stdout": p.stdout[-3000:], "stderr": p.stderr[-3000:]}

def astronomy(params):
    from astropy.io import fits
    from astropy.stats import sigma_clipped_stats
    from photutils.aperture import CircularAperture, aperture_photometry
    size = 32 + stable_int(params, 16)
    yy, xx = np.mgrid[:size, :size]
    sigma = max(1.5, stable_float(params.get("sigma_clip"), 2.5, 0.5))
    image = np.sin(xx / 4) + np.cos(yy / 5) + stable_float(params.get("source_threshold"), 3)
    pos = (size / 2 + stable_int(params.get("wcs_frame"), 7) - 3, size / 2)
    radius = max(2, int(stable_float(params.get("aperture_radius"), 4)))
    table = aperture_photometry(image, CircularAperture([pos], r=radius))
    mean, median, std = sigma_clipped_stats(image, sigma=sigma)
    hdu = fits.PrimaryHDU(image.astype("float32"))
    hdu.header["FRAME"] = str(params.get("wcs_frame"))[:16]
    return {"shape": list(image.shape), "flux": round(float(table["aperture_sum"][0]), 5), "median": round(float(median), 5), "std": round(float(std), 5), "frame": hdu.header["FRAME"]}

def seismology(params):
    from obspy import Trace, UTCDateTime
    npts = 512 + stable_int(params.get("window_duration"), 256)
    rate = 80.0
    freq = 1.0 + stable_int(params.get("filter_band"), 12)
    data = np.sin(np.arange(npts) * 2 * np.pi * freq / rate) + 0.05 * np.cos(np.arange(npts) / 3)
    tr = Trace(data=data.astype("float32"))
    tr.stats.sampling_rate = rate
    tr.stats.starttime = UTCDateTime(2020, 1, 1)
    tr.filter("bandpass", freqmin=0.5, freqmax=min(30.0, freq + 5), corners=2, zerophase=True)
    return {"npts": tr.stats.npts, "sampling_rate": tr.stats.sampling_rate, "max": round(float(tr.data.max()), 6), "rms": round(float(np.sqrt(np.mean(tr.data ** 2))), 6)}

def climate(params):
    import xarray as xr
    import netCDF4
    n = 12 + stable_int(params.get("time_window"), 12)
    lat = np.linspace(-60, 60, 9)
    lon = np.linspace(0, 350, 12)
    arr = np.arange(n * len(lat) * len(lon), dtype=float).reshape(n, len(lat), len(lon))
    arr = (arr % (10 + stable_int(params.get("variable_name"), 17))) + stable_float(params.get("missing_value_policy"), 2)
    da = xr.DataArray(arr, dims=("time", "lat", "lon"), coords={"time": np.arange(n), "lat": lat, "lon": lon}, name="var")
    grouped = da.mean(("lat", "lon"))
    return {"netcdf4": netCDF4.__version__, "time": n, "mean0": round(float(grouped.isel(time=0)), 5), "global_mean": round(float(da.mean()), 5)}

def materials(params):
    from pymatgen.analysis.diffraction.xrd import XRDCalculator
    from pymatgen.core import Lattice, Structure
    from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
    a = stable_float(params.get("strain_tensor"), 2.0, 3.0)
    struct = Structure(Lattice.cubic(a), ["Na", "Cl"], [[0, 0, 0], [0.5, 0.5, 0.5]])
    sg = SpacegroupAnalyzer(struct, symprec=0.1).get_space_group_symbol()
    pattern = XRDCalculator(wavelength="CuKa").get_pattern(struct, two_theta_range=(0, 80))
    return {"formula": struct.composition.reduced_formula, "sg": sg, "a": round(a, 5), "peak_count": len(pattern.x), "first_peak": round(float(pattern.x[0]), 5)}

def proteomics(params):
    from pyteomics import mass, parser
    amino = "ACDEFGHIKLMNPQRSTVWY"
    seed = stable_int(params, 10_000)
    seq = "PEPTIDE" + "".join(amino[(seed + idx * 7) % len(amino)] for idx in range(8 + seed % 7)) + "KR"
    rule_name = "trypsin" if seed % 2 == 0 else "chymotrypsin high specificity"
    missed = seed % 3
    peptides = parser.cleave(seq, parser.expasy_rules[rule_name], missed_cleavages=missed)
    charge = 1 + stable_int(params.get("charge_state"), 5)
    masses = sorted(mass.calculate_mass(sequence=p, charge=charge) for p in peptides)
    tolerance = round(stable_float(params.get("mass_tolerance"), 0.05, 0.005), 5)
    return {"sequence_digest": hashlib.sha256(seq.encode()).hexdigest()[:12], "rule": rule_name, "missed": missed, "peptide_count": len(peptides), "charge": charge, "tolerance": tolerance, "min_mz": round(float(masses[0]), 5), "max_mz": round(float(masses[-1]), 5)}

def phylogenetics(params):
    from Bio import Phylo
    taxa = ["A", "B", "C", "D", "E"]
    scale = stable_float(params.get("branch_support_threshold"), 0.1, 0.05)
    newick = f"(({taxa[0]}:{scale:.3f},{taxa[1]}:{scale*2:.3f}):{scale:.3f},({taxa[2]}:{scale:.3f},({taxa[3]}:{scale:.3f},{taxa[4]}:{scale:.3f}):{scale:.3f}):{scale:.3f});"
    tree = Phylo.read(io.StringIO(newick), "newick")
    depths = tree.depths()
    return {"terminal_count": len(tree.get_terminals()), "total_branch": round(float(tree.total_branch_length()), 5), "max_depth": round(float(max(depths.values())), 5)}

def music(params):
    import music21
    s = music21.stream.Stream()
    interval = int(stable_float(params.get("transpose_interval"), 5))
    for name in ["C4", "E4", "G4", "B4"]:
        n = music21.note.Note(name)
        n.quarterLength = 0.5 + stable_int(params.get("quantization_grid"), 4) / 4
        s.append(n)
    t = s.transpose(interval)
    return {"notes": len(t.notes), "first": t.notes[0].nameWithOctave, "highest": t.analyze("ambitus").semitones, "ql": float(t.notes[0].quarterLength)}

def video(params):
    rate = max(10, min(60, int(stable_float(params.get("frame_rate"), 30))))
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "clip.mp4"
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=size=96x72:rate={rate}:duration=1", "-pix_fmt", "yuv420p", str(out)]
        enc = run(cmd, timeout=120)
        probe = run(["ffprobe", "-hide_banner", "-loglevel", "error", "-show_streams", "-of", "json", str(out)], timeout=60)
    return {"ok": enc["returncode"] == 0 and probe["returncode"] == 0, "rate": rate, "probe_digest": hashlib.sha256(probe["stdout"].encode()).hexdigest()}

def point_cloud(params):
    import laspy
    count = 80 + stable_int(params.get("voxel_size"), 120)
    header = laspy.LasHeader(point_format=3, version="1.2")
    las = laspy.LasData(header)
    las.x = np.linspace(0, 10, count)
    las.y = np.sin(las.x) * stable_float(params.get("registration_threshold"), 2)
    las.z = np.cos(las.x)
    return {"count": int(len(las.x)), "xmax": round(float(las.x.max()), 4), "ymean": round(float(np.mean(las.y)), 6), "fmt": str(las.header.point_format)}

def power_grid(params):
    import pandapower as pp
    net = pp.create_empty_network()
    b1 = pp.create_bus(net, vn_kv=20.0)
    b2 = pp.create_bus(net, vn_kv=0.4)
    pp.create_ext_grid(net, b1, vm_pu=1.0)
    pp.create_transformer_from_parameters(net, b1, b2, sn_mva=0.4, vn_hv_kv=20, vn_lv_kv=0.4, vk_percent=4, vkr_percent=1, pfe_kw=0.2, i0_percent=0.1)
    pp.create_load(net, b2, p_mw=0.05 * stable_float(params.get("load_scale"), 2), q_mvar=0.01)
    pp.runpp(net)
    return {"buses": len(net.bus), "loads": len(net.load), "vm_min": round(float(net.res_bus.vm_pu.min()), 6), "loss": round(float(net.res_trafo.pl_mw.sum()), 8)}

def rf(params):
    from scipy import signal
    rate = 256
    offset = stable_float(params.get("carrier_offset"), 30)
    t = np.arange(1024) / rate
    x = np.exp(2j * np.pi * offset * t) + 0.1 * np.exp(2j * np.pi * (offset + 15) * t)
    f, pxx = signal.welch(x, fs=rate, nperseg=128, return_onesided=False)
    return {"bins": len(f), "peak_freq": round(float(f[np.argmax(pxx)]), 5), "power": round(float(np.max(pxx)), 8)}

def cartography(params):
    from shapely.geometry import LineString, Polygon
    seed = stable_int(params, 10_000)
    tol = stable_float(params.get("simplification_tolerance"), 0.6, 0.01)
    amp = 0.5 + (seed % 17) / 10
    freq = 1 + stable_int(params.get("zoom_range"), 5)
    phase = stable_int(params.get("projection"), 31) / 10
    pts = [(i, amp * math.sin(i * freq / 7 + phase) + stable_int(params.get("layer_filter"), 11) / 10) for i in np.linspace(0, 10, 50)]
    line = LineString(pts)
    ymax = 2.0 + stable_int(params.get("label_priority"), 20) / 10
    poly = Polygon([(0, -1), (10, -1), (10, ymax), (0, ymax)])
    clipped = line.intersection(poly)
    return {"seed": seed, "tolerance": round(tol, 5), "length": round(float(line.length), 5), "simple_length": round(float(line.simplify(tol).length), 5), "clip_length": round(float(clipped.length), 5), "inside_empty": clipped.is_empty}

def typography(params):
    import fontTools
    import uharfbuzz
    from fontTools.misc.transform import Transform
    scale = stable_float(params.get("variation_axis"), 2)
    tr = Transform().scale(scale).translate(stable_int(params.get("glyph_subset"), 20), stable_int(params.get("script_language"), 20))
    return {"fonttools": fontTools.version, "uharfbuzz": uharfbuzz.version_string(), "matrix": tuple(round(x, 5) for x in tr)}

def color_imaging(params):
    import colour
    from skimage import exposure
    white = stable_float(params.get("white_point"), 0.5, 0.5)
    img = np.linspace(0, 1, 64 * 64 * 3).reshape(64, 64, 3)
    adjusted = exposure.adjust_gamma(img, gamma=stable_float(params.get("tone_curve"), 1.5, 0.5))
    xyz = colour.sRGB_to_XYZ([white, 0.4, 0.3])
    return {"mean": round(float(adjusted.mean()), 6), "xyz": [round(float(x), 6) for x in xyz], "shape": list(adjusted.shape)}

def microscopy(params):
    from skimage import filters, measure, morphology
    seed = stable_int(params, 10_000)
    size = 96 + seed % 16
    yy, xx = np.mgrid[:size, :size]
    r1 = 14 + stable_int(params.get("object_size_range"), 12)
    r2 = 10 + stable_int(params.get("channel_selection"), 10)
    shift = stable_int(params.get("measurement_feature"), 17)
    img = ((xx - (35 + shift % 11)) ** 2 + (yy - 40) ** 2 < r1 * r1).astype(float)
    img += ((xx - (62 + shift % 7)) ** 2 + (yy - 55) ** 2 < r2 * r2).astype(float) * (0.8 + seed % 5 / 10)
    img += stable_float(params.get("illumination_correction"), 0.35) * (xx / size)
    thresh = filters.threshold_otsu(img)
    min_size = 8 + stable_int(params.get("threshold_method"), 40)
    labels = measure.label(morphology.remove_small_objects(img > thresh, min_size=min_size))
    props = measure.regionprops(labels)
    return {"seed": seed, "threshold": round(float(thresh), 6), "min_size": min_size, "objects": len(props), "area_sum": int(sum(p.area for p in props)), "ecc_sum": round(float(sum(p.eccentricity for p in props)), 6)}

def structural_biology(params):
    import gemmi
    pdb = """ATOM      1  N   ALA A   1      11.104  13.207   8.100  1.00 20.00           N
ATOM      2  CA  ALA A   1      12.300  12.500   8.500  1.00 18.00           C
ATOM      3  C   ALA A   1      13.300  13.500   8.900  1.00 22.00           C
ATOM      4  O   ALA A   1      14.100  13.100   9.600  1.00 30.00           O
END
"""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "mini.pdb"
        path.write_text(pdb)
        st = gemmi.read_structure(str(path))
    cutoff = stable_float(params.get("distance_cutoff"), 4)
    atoms = list(st[0][0][0])
    return {"models": len(st), "atoms": len(atoms), "cutoff": round(cutoff, 4), "cell_a": round(float(st.cell.a), 4)}

def acoustics(params):
    from scipy import signal
    n = 256 + stable_int(params.get("rir_length"), 256)
    decay = stable_float(params.get("absorption_level"), 0.02, 0.005)
    rir = np.exp(-np.arange(n) * decay) * np.sin(np.arange(n) / 4)
    src = np.zeros(n); src[0] = 1; src[50] = 0.5
    y = signal.fftconvolve(src, rir)[:n]
    return {"rir_len": n, "energy": round(float(np.sum(y ** 2)), 6), "peak": round(float(np.max(np.abs(y))), 6)}

def hydrology(params):
    import rasterio
    from rasterio.transform import from_origin
    size = 32
    dem = np.add.outer(np.arange(size), np.arange(size)).astype("float32")
    dem += stable_float(params.get("rainfall_window"), 4)
    transform = from_origin(0, 32, 1, 1)
    slope_proxy = np.gradient(dem)[0] + np.gradient(dem)[1]
    return {"rasterio": rasterio.__version__, "shape": list(dem.shape), "mean": round(float(dem.mean()), 5), "slope_sum": round(float(slope_proxy.sum()), 5), "transform_a": transform.a}

def geology(params):
    import bruges
    import welly
    try:
        import striplog
        striplog_version = striplog.__version__
    except Exception as exc:
        striplog_version = f"unavailable:{type(exc).__name__}"
    seed = stable_int(params, 10_000)
    n = 32 + seed % 24
    vp = np.linspace(2500, 4200 + seed % 300, n) * stable_float(params.get("unit_system"), 0.1, 0.95)
    rho = np.linspace(2.1, 2.6 + stable_int(params.get("lithology_alias"), 9) / 20, n)
    smooth = 1 + stable_int(params.get("smoothing_window"), 5)
    if smooth > 1:
        vp = np.convolve(vp, np.ones(smooth) / smooth, mode="same")
    ai = vp * rho
    return {"seed": seed, "welly": welly.__version__, "striplog": striplog_version, "samples": n, "smooth": smooth, "ai_mean": round(float(np.mean(ai)), 5), "ai_std": round(float(np.std(ai)), 5)}

def transport(params):
    import pandas as pd
    seed = stable_int(params, 10_000)
    headway = max(5, int(stable_float(params.get("headway_window"), 20)))
    route_count = 2 + stable_int(params.get("route_filter"), 5)
    trip_count = 6 + seed % 8
    stop_count = 3 + stable_int(params.get("transfer_policy"), 5)
    offset = stable_int(params.get("service_date"), 60)
    trips = pd.DataFrame({"trip_id": [f"T{i}" for i in range(trip_count)], "route_id": [f"R{i%route_count}" for i in range(trip_count)]})
    stop_times = pd.DataFrame({"trip_id": np.repeat(trips.trip_id.values, stop_count), "stop_sequence": list(range(1, stop_count + 1)) * len(trips), "arrival": np.tile(np.arange(offset, offset + stop_count * headway, headway), len(trips))})
    merged = stop_times.merge(trips, on="trip_id")
    by_route = merged.groupby("route_id")["arrival"].max().to_dict()
    return {"seed": seed, "trips": len(trips), "stops_per_trip": stop_count, "stop_times": len(stop_times), "headway": headway, "route_count": route_count, "route_max": {k: int(v) for k, v in by_route.items()}}

ORACLES = {
    "astronomy_fits_photometry": astronomy,
    "seismology_waveform_processing": seismology,
    "climate_netcdf_analysis": climate,
    "materials_crystallography": materials,
    "proteomics_mass_spectrometry": proteomics,
    "phylogenetics_tree_reconstruction": phylogenetics,
    "music_score_engraving": music,
    "video_broadcast_qc": video,
    "point_cloud_lidar": point_cloud,
    "power_grid_simulation": power_grid,
    "rf_signal_processing": rf,
    "cartography_map_rendering": cartography,
    "typography_font_shaping": typography,
    "color_imaging_pipeline": color_imaging,
    "microscopy_cell_analysis": microscopy,
    "structural_biology_pdb": structural_biology,
    "acoustics_room_simulation": acoustics,
    "hydrology_raster_modeling": hydrology,
    "geology_well_log_analysis": geology,
    "transport_gtfs_schedule": transport,
}
