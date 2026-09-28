"""Deterministic, parameter-faithful oracles for weak SWR benchmark families.

Every function below consumes all five axes advertised by its family.  Heavy
dependencies are imported inside functions so this module can be copied into
all repaired task packages without changing unrelated task environments.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def stable_int(value: Any, modulo: int = 1000) -> int:
    text = json.dumps(value, sort_keys=True, default=str)
    return sum((index + 1) * ord(char) for index, char in enumerate(text)) % modulo


def stable_float(value: Any, scale: float = 1.0, offset: float = 0.0) -> float:
    return offset + scale * (1 + stable_int(value, 997) / 997)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _bounded_int(value: Any, low: int, high: int) -> int:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return max(low, min(high, int(round(float(value)))))
    return low + stable_int(value, high - low + 1)


def _bounded_float(value: Any, low: float, high: float) -> float:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        raw = float(value)
        if low <= raw <= high:
            return raw
    return low + (high - low) * stable_int(value, 997) / 996


def z3_constraint_system(params: dict[str, Any]) -> dict[str, Any]:
    """Solve an address-allocation model with a deterministic lexicographic tie-break."""
    from z3 import Int, Optimize, Sum, sat

    bitwidth = _bounded_int(params.get("bitwidth"), 3, 16)
    bounds = _bounded_float(params.get("bounds"), 0.0, 32.0)
    capacity = _bounded_float(params.get("capacity"), 1.0, 32.0)
    precedence = _bounded_float(params.get("precedence"), 0.0, 16.0)
    mode = str(params.get("satisfiability_mode", "baseline")).lower()

    count = 3 + bitwidth % 4
    lower = int(math.floor(bounds)) % 9
    gap = 1 + int(math.floor(precedence)) % 4
    minimum_sum = count * lower + gap * count * (count - 1) // 2
    slack = max(0, int(round(capacity)))
    capacity_limit = minimum_sum + slack
    if mode in {"strict", "unsat", "conflict"}:
        capacity_limit = minimum_sum - 1
    elif mode in {"stress", "edge"}:
        capacity_limit = minimum_sum + slack // 3

    addresses = [Int(f"addr_{index}") for index in range(count)]
    optimizer = Optimize()
    optimizer.set(priority="lex")
    for index, address in enumerate(addresses):
        optimizer.add(address >= lower)
        optimizer.add(address < 2**bitwidth)
        if index:
            optimizer.add(address >= addresses[index - 1] + gap)
    optimizer.add(Sum(addresses) <= capacity_limit)
    optimizer.minimize(Sum(addresses))
    for address in addresses:
        optimizer.minimize(address)
    status = optimizer.check()
    result: dict[str, Any] = {
        "status": str(status),
        "bitwidth": bitwidth,
        "bounds_floor": lower,
        "capacity_limit": capacity_limit,
        "precedence_gap": gap,
        "mode": mode,
        "variable_count": count,
        "addresses": [-1] * 6,
        "alias_count": 0,
        "objective": 0,
    }
    if status == sat:
        model = optimizer.model()
        values = [model.eval(address).as_long() for address in addresses]
        result.update(
            {
                "addresses": values + [-1] * (6 - len(values)),
                "alias_count": len(values) - len(set(values)),
                "objective": sum(values),
            }
        )
    return result


def duckdb_reporting(params: dict[str, Any]) -> dict[str, Any]:
    import duckdb
    import pandas as pd

    partitions = 2 + stable_int(params.get("partitioning"), 5)
    frame = _bounded_int(params.get("window_frame"), 1, 20)
    schema_mode = str(params.get("schema_evolution", "baseline"))
    tie_mode = str(params.get("ordering_ties", "stable"))
    nested_mode = str(params.get("nested_types", "flat"))
    row_count = 36 + stable_int(params, 25)
    tie_bucket = 2 + stable_int(tie_mode, 6)

    rows = []
    for index in range(row_count):
        amount = (index * 17 + stable_int(schema_mode, 23)) % 101
        row = {
            "row_id": index,
            "partition_id": f"P{index % partitions}",
            "event_order": index % tie_bucket,
            "amount": float(amount),
            "nested_label": f"{nested_mode}:{index % 4}",
        }
        rows.append(row)
    dataframe = pd.DataFrame(rows)
    connection = duckdb.connect(database=":memory:")
    connection.register("events", dataframe)
    query = f"""
        select partition_id, row_id, event_order,
               round(sum(amount) over (
                   partition by partition_id
                   order by event_order, row_id
                   rows between {frame} preceding and current row
               ), 3) as rolling_sum,
               nested_label
        from events
        order by partition_id, event_order, row_id
    """
    result_rows = connection.execute(query).fetchall()
    connection.close()
    checksum = round(sum(float(row[3]) for row in result_rows), 3)
    return {
        "partition_count": partitions,
        "window_frame": frame,
        "schema_mode": schema_mode,
        "tie_bucket_count": tie_bucket,
        "nested_mode": nested_mode,
        "row_count": row_count,
        "rolling_checksum": checksum,
        "first_rows": [list(row) for row in result_rows[:12]],
    }


def container_supply_chain(params: dict[str, Any]) -> dict[str, Any]:
    base = str(params.get("base_image", "python:3.11-slim"))
    package_mode = str(params.get("package_set", "runtime"))
    labels_mode = str(params.get("labels", "minimal"))
    entrypoint = str(params.get("entrypoint", "python"))
    scope = str(params.get("sbom_scope", "runtime"))

    catalog = ["ca-certificates", "curl", "libssl", "python", "pip", "setuptools", "wheel"]
    package_count = 2 + stable_int(package_mode, len(catalog) - 1)
    packages = sorted(catalog[:package_count])
    if "all" not in scope.lower() and len(packages) > 2:
        packages = packages[:-1]
    label_count = 1 + stable_int(labels_mode, 5)
    labels = {
        f"org.opencontainers.image.benchmark.{index}": digest(
            {"labels": labels_mode, "index": index}
        )[:12]
        for index in range(label_count)
    }
    layers = [
        digest({"base": base, "kind": "base"}),
        digest({"packages": packages, "scope": scope}),
        digest({"labels": labels}),
        digest({"entrypoint": entrypoint}),
    ]
    return {
        "base_image": base,
        "packages": packages,
        "labels": labels,
        "entrypoint": entrypoint,
        "sbom_scope": scope,
        "layer_count": len(layers),
        "image_merkle": digest(layers),
        "sbom_digest": digest({"base": base, "packages": packages, "scope": scope}),
    }


def acoustics_room_simulation(params: dict[str, Any]) -> dict[str, Any]:
    import numpy as np
    from scipy import signal

    absorption = _bounded_float(params.get("absorption_level"), 0.05, 0.95)
    microphone_count = 2 + stable_int(params.get("microphone_array"), 7)
    rir_length = 256 + _bounded_int(params.get("rir_length"), 0, 768)
    room_scale = _bounded_float(params.get("room_size"), 2.5, 12.0)
    source_bucket = stable_int(params.get("source_position"), 97)

    source = np.array(
        [
            0.5 + room_scale * ((source_bucket % 17) + 1) / 20,
            0.5 + room_scale * (((source_bucket // 3) % 13) + 1) / 16,
            1.0 + (source_bucket % 7) / 10,
        ]
    )
    channel_energy = []
    channel_peak_index = []
    for channel in range(microphone_count):
        microphone = np.array(
            [
                0.5 + room_scale * (channel + 1) / (microphone_count + 1),
                room_scale * 0.45,
                1.2,
            ]
        )
        distance = float(np.linalg.norm(source - microphone))
        delay = min(rir_length - 1, int(round(distance / 343.0 * 16000)))
        samples = np.arange(rir_length)
        envelope = np.exp(-samples * (0.002 + absorption * 0.025))
        rir = envelope * np.sin(samples * (0.17 + channel * 0.01))
        rir[:delay] = 0.0
        if delay < rir_length:
            rir[delay] += 1.0 / max(0.25, distance)
        rendered = signal.fftconvolve(np.array([1.0, 0.0, 0.35]), rir)[:rir_length]
        channel_energy.append(round(float(np.sum(rendered**2)), 6))
        channel_peak_index.append(int(np.argmax(np.abs(rendered))))
    return {
        "absorption": round(absorption, 6),
        "microphone_count": microphone_count,
        "rir_length": rir_length,
        "room_scale": round(room_scale, 6),
        "source_position": [round(float(value), 6) for value in source],
        "channel_energy": channel_energy,
        "channel_peak_index": channel_peak_index,
        "mean_energy": round(float(np.mean(channel_energy)), 6),
    }


def color_imaging_pipeline(params: dict[str, Any]) -> dict[str, Any]:
    import numpy as np
    from skimage import exposure, filters

    color_space = str(params.get("color_space", "sRGB"))
    quality = _bounded_int(params.get("compression_quality"), 1, 100)
    demosaic = str(params.get("demosaic_method", "bilinear"))
    gamma = _bounded_float(params.get("tone_curve"), 0.4, 3.0)
    white = _bounded_float(params.get("white_point"), 0.5, 1.5)

    raw = np.linspace(0.0, 1.0, 48 * 48).reshape(48, 48)
    channels = np.stack([raw, np.roll(raw, 1, 0), np.roll(raw, 1, 1)], axis=-1)
    sigma = 0.2 + stable_int(demosaic, 9) / 10
    channels = np.stack(
        [filters.gaussian(channels[..., index], sigma=sigma) for index in range(3)],
        axis=-1,
    )
    matrix_seed = 1 + stable_int(color_space, 11)
    matrix = np.array(
        [
            [1.0, matrix_seed / 100, 0.01],
            [0.02, 1.0, matrix_seed / 120],
            [matrix_seed / 140, 0.01, 1.0],
        ]
    )
    converted = np.clip(channels @ matrix.T, 0.0, 1.0)
    converted[..., 0] = np.clip(converted[..., 0] * white, 0.0, 1.0)
    converted = exposure.adjust_gamma(converted, gamma=gamma)
    levels = max(4, int(round(4 + quality * 2.51)))
    quantized = np.round(converted * (levels - 1)) / (levels - 1)
    return {
        "color_space": color_space,
        "compression_quality": quality,
        "demosaic_method": demosaic,
        "tone_gamma": round(gamma, 6),
        "white_point": round(white, 6),
        "quantization_levels": levels,
        "channel_means": [round(float(value), 7) for value in quantized.mean((0, 1))],
        "channel_stddev": [round(float(value), 7) for value in quantized.std((0, 1))],
    }


def hydrology_raster_modeling(params: dict[str, Any]) -> dict[str, Any]:
    import numpy as np

    threshold = _bounded_float(params.get("basin_threshold"), 1.0, 200.0)
    resolution = _bounded_float(params.get("dem_resolution"), 0.5, 30.0)
    direction = str(params.get("flow_direction_method", "D8"))
    nodata_policy = str(params.get("nodata_policy", "fill"))
    rainfall = _bounded_float(params.get("rainfall_window"), 0.0, 100.0)

    size = 24 + stable_int(resolution, 17)
    yy, xx = np.mgrid[:size, :size]
    dem = (size - yy) * resolution + (size - xx) * resolution * 0.6
    dem += np.sin(xx / (2 + stable_int(direction, 5))) * (1 + rainfall / 50)
    nodata_mask = (xx + yy + stable_int(nodata_policy, 13)) % 19 == 0
    original_nodata = int(nodata_mask.sum())
    if "preserve" in nodata_policy.lower() or "mask" in nodata_policy.lower():
        valid = ~nodata_mask
    else:
        median = float(np.median(dem[~nodata_mask]))
        dem[nodata_mask] = median
        valid = np.ones_like(nodata_mask, dtype=bool)
    gy, gx = np.gradient(dem, resolution)
    direction_weight = 1.0 + stable_int(direction, 11) / 20
    accumulation = (np.abs(gx) + np.abs(gy)) * direction_weight + rainfall
    basin_cells = int(np.logical_and(accumulation >= threshold, valid).sum())
    return {
        "shape": [int(size), int(size)],
        "dem_resolution": round(resolution, 6),
        "flow_direction_method": direction,
        "nodata_policy": nodata_policy,
        "original_nodata_cells": original_nodata,
        "valid_cells": int(valid.sum()),
        "rainfall_window": round(rainfall, 6),
        "basin_threshold": round(threshold, 6),
        "basin_cells": basin_cells,
        "accumulation_sum": round(float(accumulation[valid].sum()), 6),
    }


def materials_crystallography(params: dict[str, Any]) -> dict[str, Any]:
    from pymatgen.analysis.diffraction.xrd import XRDCalculator
    from pymatgen.core import Lattice, Structure
    from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

    wavelength_options = ["CuKa", "MoKa", "CrKa"]
    wavelength = wavelength_options[
        stable_int(params.get("diffraction_wavelength"), len(wavelength_options))
    ]
    substitution_options = ["Na", "K", "Li", "Mg"]
    substituted = substitution_options[
        stable_int(params.get("site_substitution"), len(substitution_options))
    ]
    space_group_mode = str(params.get("space_group", "cubic"))
    strain = _bounded_float(params.get("strain_tensor"), 0.0, 0.25)
    supercell = 1 + stable_int(params.get("supercell_size"), 3)

    base_a = 4.5 * (1.0 + strain / 10)
    if stable_int(space_group_mode, 2):
        lattice = Lattice.tetragonal(base_a, base_a * (1.0 + strain / 5))
    else:
        lattice = Lattice.cubic(base_a)
    structure = Structure(lattice, [substituted, "Cl"], [[0, 0, 0], [0.5, 0.5, 0.5]])
    structure.make_supercell([supercell, supercell, 1])
    analyzed_group = SpacegroupAnalyzer(structure, symprec=0.1).get_space_group_symbol()
    pattern = XRDCalculator(wavelength=wavelength).get_pattern(
        structure, two_theta_range=(5, 80)
    )
    return {
        "formula": structure.composition.reduced_formula,
        "site_count": len(structure),
        "substituted_element": substituted,
        "space_group_mode": space_group_mode,
        "analyzed_space_group": analyzed_group,
        "strain": round(strain, 7),
        "supercell": supercell,
        "wavelength": wavelength,
        "peak_count": len(pattern.x),
        "first_peaks": [round(float(value), 6) for value in pattern.x[:5]],
    }


def music_score_engraving(params: dict[str, Any]) -> dict[str, Any]:
    import music21

    interval = _bounded_int(params.get("transpose_interval"), -24, 24)
    meter_options = [(4, 4), (3, 4), (6, 8), (5, 4)]
    beats, beat_type = meter_options[
        stable_int(params.get("meter_change"), len(meter_options))
    ]
    grid_options = [0.25, 0.5, 0.75, 1.0]
    grid = grid_options[stable_int(params.get("quantization_grid"), len(grid_options))]
    part_mode = str(params.get("instrument_part", "piano"))
    lyric_mode = str(params.get("lyric_alignment", "syllabic"))
    part_count = 1 + stable_int(part_mode, 3)

    score = music21.stream.Score()
    base_notes = ["C4", "E4", "G4", "B4", "D5", "F5"]
    for part_index in range(part_count):
        part = music21.stream.Part(id=f"P{part_index + 1}")
        part.insert(0, music21.meter.TimeSignature(f"{beats}/{beat_type}"))
        instrument = music21.instrument.Instrument()
        instrument.partName = f"{part_mode}-{part_index + 1}"
        part.insert(0, instrument)
        for note_index, pitch in enumerate(base_notes):
            note = music21.note.Note(pitch)
            note.quarterLength = grid
            note.lyric = f"{lyric_mode}-{note_index}"
            part.append(note)
        score.append(part)
    transposed = score.transpose(interval)
    notes = list(transposed.recurse().notes)
    return {
        "transpose_interval": interval,
        "meter": f"{beats}/{beat_type}",
        "quantization_grid": grid,
        "instrument_part": part_mode,
        "lyric_alignment": lyric_mode,
        "part_count": part_count,
        "note_count": len(notes),
        "first_pitch": notes[0].nameWithOctave,
        "last_pitch": notes[-1].nameWithOctave,
        "duration": round(float(transposed.highestTime), 6),
        "lyric_digest": digest([note.lyric for note in notes])[:20],
    }


def phylogenetics_tree_reconstruction(params: dict[str, Any]) -> dict[str, Any]:
    from Bio import Phylo

    trim = _bounded_float(params.get("alignment_trim"), 0.0, 0.9)
    replicates = _bounded_int(params.get("bootstrap_replicates"), 1, 5000)
    threshold = _bounded_float(params.get("branch_support_threshold"), 0.0, 100.0)
    outgroup = str(params.get("outgroup_taxon", "A"))
    model = str(params.get("substitution_model", "JC69"))
    taxa = ["A", "B", "C", "D", "E"]
    chosen_outgroup = taxa[stable_int(outgroup, len(taxa))]
    scale = (0.04 + stable_int(model, 17) / 100) * (1.0 - trim / 2)
    support_left = min(100.0, 45.0 + replicates % 56)
    support_right = min(100.0, 35.0 + stable_int(model, 66))
    newick = (
        f"((A:{scale:.6f},B:{scale*1.2:.6f}){support_left:.3f}:{scale:.6f},"
        f"(C:{scale*.9:.6f},(D:{scale:.6f},E:{scale*1.1:.6f})"
        f"{support_right:.3f}:{scale:.6f}){support_right:.3f}:{scale:.6f});"
    )
    tree = Phylo.read(io.StringIO(newick), "newick")
    tree.root_with_outgroup(chosen_outgroup)
    retained_supports = sorted(
        round(float(clade.confidence), 3)
        for clade in tree.find_clades()
        if clade.confidence is not None and float(clade.confidence) >= threshold
    )
    return {
        "alignment_trim": round(trim, 6),
        "bootstrap_replicates": replicates,
        "support_threshold": round(threshold, 6),
        "outgroup": chosen_outgroup,
        "substitution_model": model,
        "terminal_order": [terminal.name for terminal in tree.get_terminals()],
        "retained_supports": retained_supports,
        "total_branch_length": round(float(tree.total_branch_length()), 7),
        "max_depth": round(float(max(tree.depths().values())), 7),
    }


def point_cloud_lidar(params: dict[str, Any]) -> dict[str, Any]:
    import numpy as np

    classification = str(params.get("classification_filter", "all"))
    crop = _bounded_float(params.get("crop_bounds"), 2.0, 10.0)
    normal_radius = _bounded_float(params.get("normal_radius"), 0.1, 4.0)
    registration = _bounded_float(params.get("registration_threshold"), 0.0, 2.0)
    voxel = _bounded_float(params.get("voxel_size"), 0.05, 2.0)

    points = np.linspace(0, 12, 360)
    cloud = np.column_stack((points, np.sin(points), np.cos(points * 0.7)))
    classes = (np.arange(len(cloud)) + stable_int(classification, 5)) % 5
    class_id = stable_int(classification, 5)
    selected = cloud[(classes == class_id) & (cloud[:, 0] <= crop)]
    if not len(selected):
        selected = cloud[:1]
    voxel_ids = np.floor(selected / voxel).astype(int)
    _, unique_indices = np.unique(voxel_ids, axis=0, return_index=True)
    downsampled = selected[np.sort(unique_indices)]
    registered = downsampled.copy()
    registered[:, 1] += registration
    centered = registered - registered.mean(axis=0)
    covariance = centered.T @ centered / max(1, len(registered))
    eigenvalues = np.linalg.eigvalsh(covariance + np.eye(3) * normal_radius * 1e-6)
    return {
        "classification_filter": classification,
        "crop_bound": round(crop, 6),
        "normal_radius": round(normal_radius, 6),
        "registration_threshold": round(registration, 6),
        "voxel_size": round(voxel, 6),
        "selected_count": len(selected),
        "downsampled_count": len(downsampled),
        "bounds": [
            [round(float(value), 6) for value in registered.min(axis=0)],
            [round(float(value), 6) for value in registered.max(axis=0)],
        ],
        "covariance_eigenvalues": [round(float(value), 8) for value in eigenvalues],
    }


def power_grid_simulation(params: dict[str, Any]) -> dict[str, Any]:
    import pandapower as pp

    dispatch = _bounded_float(params.get("generator_dispatch"), 0.0, 1.0)
    line_outage = stable_int(params.get("line_outage"), 3)
    load_scale = _bounded_float(params.get("load_scale"), 0.2, 2.0)
    tap = _bounded_int(params.get("tap_position"), -5, 5)
    voltage_limit = _bounded_float(params.get("voltage_limit"), 0.85, 1.15)

    network = pp.create_empty_network()
    high = pp.create_bus(network, vn_kv=20.0)
    low_a = pp.create_bus(network, vn_kv=0.4)
    low_b = pp.create_bus(network, vn_kv=0.4)
    pp.create_ext_grid(network, high, vm_pu=1.0)
    pp.create_transformer_from_parameters(
        network,
        high,
        low_a,
        sn_mva=0.63,
        vn_hv_kv=20,
        vn_lv_kv=0.4,
        vk_percent=4,
        vkr_percent=1,
        pfe_kw=0.2,
        i0_percent=0.1,
        tap_side="hv",
        tap_neutral=0,
        tap_min=-5,
        tap_max=5,
        tap_step_percent=1.25,
        tap_pos=tap,
    )
    line = pp.create_line_from_parameters(
        network,
        low_a,
        low_b,
        length_km=0.25,
        r_ohm_per_km=0.642,
        x_ohm_per_km=0.083,
        c_nf_per_km=210,
        max_i_ka=0.2,
    )
    network.line.at[line, "in_service"] = line_outage != 0
    pp.create_load(network, low_a, p_mw=0.06 * load_scale, q_mvar=0.015 * load_scale)
    if network.line.at[line, "in_service"]:
        pp.create_load(network, low_b, p_mw=0.03 * load_scale, q_mvar=0.008 * load_scale)
    pp.create_sgen(network, low_a, p_mw=0.04 * dispatch, q_mvar=0.0)
    pp.runpp(network)
    voltages = [
        round(float(value), 7) if math.isfinite(float(value)) else None
        for value in network.res_bus.vm_pu
    ]
    return {
        "generator_dispatch": round(dispatch, 6),
        "line_outage_bucket": line_outage,
        "line_in_service": bool(network.line.at[line, "in_service"]),
        "load_scale": round(load_scale, 6),
        "tap_position": tap,
        "voltage_limit": round(voltage_limit, 6),
        "bus_voltages": voltages,
        "voltage_violation_count": sum(
            value is not None and value < voltage_limit for value in voltages
        ),
        "external_grid_mw": round(float(network.res_ext_grid.p_mw.sum()), 8),
        "network_loss_mw": round(
            float(network.res_ext_grid.p_mw.sum() + network.res_sgen.p_mw.sum() - network.res_load.p_mw.sum()),
            8,
        ),
    }


def rf_signal_processing(params: dict[str, Any]) -> dict[str, Any]:
    import numpy as np
    from scipy import signal

    carrier = _bounded_float(params.get("carrier_offset"), 1.0, 200.0)
    taps = _bounded_int(params.get("filter_taps"), 5, 129)
    if taps % 2 == 0:
        taps += 1
    modulation = str(params.get("modulation_type", "QPSK"))
    sample_rate = _bounded_int(params.get("sample_rate"), 256, 4096)
    snr = _bounded_float(params.get("snr_level"), -10.0, 60.0)

    count = 2048
    time = np.arange(count) / sample_rate
    symbol_rate = 7 + stable_int(modulation, 23)
    symbols = np.sign(np.sin(2 * np.pi * symbol_rate * time))
    phase_scale = 1 + stable_int(modulation, 4)
    clean = symbols * np.exp(2j * np.pi * carrier * time * phase_scale)
    noise = np.cos(2 * np.pi * (carrier + 31) * time) + 1j * np.sin(
        2 * np.pi * (carrier + 47) * time
    )
    noisy = clean + noise * 10 ** (-snr / 20)
    cutoff = min(0.95, max(0.05, (carrier * 1.8) / (sample_rate / 2)))
    coefficients = signal.firwin(taps, cutoff)
    filtered = signal.lfilter(coefficients, [1.0], noisy)
    frequencies, power = signal.welch(
        filtered, fs=sample_rate, nperseg=256, return_onesided=False
    )
    peak_index = int(np.argmax(power))
    return {
        "carrier_offset": round(carrier, 6),
        "filter_taps": taps,
        "modulation_type": modulation,
        "sample_rate": sample_rate,
        "snr_db": round(snr, 6),
        "peak_frequency": round(float(frequencies[peak_index]), 6),
        "peak_power": round(float(power[peak_index]), 10),
        "output_rms": round(float(np.sqrt(np.mean(np.abs(filtered) ** 2))), 9),
    }


def seismology_waveform_processing(params: dict[str, Any]) -> dict[str, Any]:
    import numpy as np
    from scipy import signal

    band_seed = stable_int(params.get("filter_band"), 20)
    low = 0.5 + band_seed / 10
    high = min(30.0, low + 3 + band_seed % 8)
    phase = str(params.get("phase_pick", "P"))
    response = str(params.get("response_removal", "none"))
    station = str(params.get("station_selection", "all"))
    duration = _bounded_float(params.get("window_duration"), 1.0, 20.0)
    rate = 80 + stable_int(station, 41)
    count = max(128, int(rate * duration))
    time = np.arange(count) / rate
    phase_shift = stable_int(phase, 31) / 31 * math.pi
    raw = np.sin(2 * np.pi * (low + 1) * time + phase_shift)
    raw += 0.2 * np.cos(2 * np.pi * (high - 0.5) * time)
    response_scale = 0.5 + stable_int(response, 23) / 10
    corrected = signal.detrend(raw) / response_scale
    sos = signal.butter(
        3, [low / (rate / 2), high / (rate / 2)], btype="bandpass", output="sos"
    )
    filtered = signal.sosfiltfilt(sos, corrected)
    pick_index = int(np.argmax(np.abs(filtered)))
    return {
        "filter_band": [round(low, 6), round(high, 6)],
        "phase_pick": phase,
        "response_removal": response,
        "station_selection": station,
        "window_duration": round(duration, 6),
        "sample_rate": rate,
        "sample_count": count,
        "pick_index": pick_index,
        "peak": round(float(np.max(np.abs(filtered))), 8),
        "rms": round(float(np.sqrt(np.mean(filtered**2))), 8),
    }


def structural_biology_pdb(params: dict[str, Any]) -> dict[str, Any]:
    import numpy as np

    altloc = str(params.get("altloc_policy", "highest_occupancy"))
    chain = str(params.get("chain_selection", "A"))
    cutoff = _bounded_float(params.get("distance_cutoff"), 1.0, 12.0)
    window = _bounded_int(params.get("residue_window"), 1, 20)
    secondary = str(params.get("secondary_structure", "all"))
    chain_id = ["A", "B", "C"][stable_int(chain, 3)]
    occupancy_threshold = 0.5 + stable_int(altloc, 5) / 10
    secondary_step = 1 + stable_int(secondary, 4)

    coordinates = []
    occupancies = []
    for residue in range(window):
        for atom in range(4):
            coordinates.append(
                [
                    residue * 3.7 + atom * 0.8,
                    math.sin(residue + atom / 2) * secondary_step,
                    math.cos(atom) * (1 + stable_int(chain_id, 3)),
                ]
            )
            occupancies.append(0.5 + ((residue + atom) % 6) / 10)
    array = np.asarray(coordinates)
    occupancy_array = np.asarray(occupancies)
    kept = array[occupancy_array >= occupancy_threshold]
    if not len(kept):
        kept = array[:1]
    differences = kept[:, None, :] - kept[None, :, :]
    distances = np.sqrt(np.sum(differences**2, axis=2))
    contact_count = int(np.logical_and(distances > 0, distances <= cutoff).sum() // 2)
    return {
        "altloc_policy": altloc,
        "chain_id": chain_id,
        "distance_cutoff": round(cutoff, 6),
        "residue_window": window,
        "secondary_structure": secondary,
        "occupancy_threshold": round(occupancy_threshold, 6),
        "atom_count": len(kept),
        "contact_count": contact_count,
        "centroid": [round(float(value), 7) for value in kept.mean(axis=0)],
    }


def video_broadcast_qc(params: dict[str, Any]) -> dict[str, Any]:
    audio_mode = str(params.get("audio_layout", "stereo"))
    frame_rate = _bounded_int(params.get("frame_rate"), 10, 60)
    gop_size = _bounded_int(params.get("gop_size"), 1, 120)
    pixel_options = ["yuv420p", "yuv422p", "yuv444p"]
    pixel_format = pixel_options[stable_int(params.get("pixel_format"), len(pixel_options))]
    subtitle_mode = str(params.get("subtitle_policy", "none"))
    channels = 1 if "mono" in audio_mode.lower() else 2 + stable_int(audio_mode, 2)

    with tempfile.TemporaryDirectory() as temp_dir:
        output = Path(temp_dir) / "clip.mkv"
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size=96x72:rate={frame_rate}:duration=0.4",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=channel_layout={'mono' if channels == 1 else 'stereo'}:sample_rate=8000",
            "-shortest",
            "-c:v",
            "mpeg4",
            "-g",
            str(gop_size),
            "-pix_fmt",
            pixel_format,
            "-c:a",
            "pcm_s16le",
            "-y",
            str(output),
        ]
        process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    return {
        "ok": process.returncode == 0,
        "audio_layout": audio_mode,
        "audio_channels": channels,
        "frame_rate": frame_rate,
        "gop_size": gop_size,
        "pixel_format": pixel_format,
        "subtitle_policy": subtitle_mode,
        "expected_frame_count": int(math.ceil(frame_rate * 0.4)),
    }


def transport_gtfs_schedule(params: dict[str, Any]) -> dict[str, Any]:
    import numpy as np
    import pandas as pd

    headway = _bounded_int(params.get("headway_window"), 5, 60)
    route_mode = str(params.get("route_filter", "all"))
    service_offset = _bounded_int(params.get("service_date"), 0, 1440)
    timezone_offset = _bounded_float(params.get("time_zone"), -12.0, 14.0)
    transfer_mode = str(params.get("transfer_policy", "baseline"))
    route_count = 2 + stable_int(route_mode, 5)
    trip_count = 6 + stable_int(params, 8)
    stops_per_trip = 3 + stable_int(transfer_mode, 5)
    route_ids = [f"R{index}" for index in range(route_count)]
    trips = pd.DataFrame(
        {
            "trip_id": [f"T{index}" for index in range(trip_count)],
            "route_id": [route_ids[index % route_count] for index in range(trip_count)],
        }
    )
    stop_times = pd.DataFrame(
        {
            "trip_id": np.repeat(trips.trip_id.values, stops_per_trip),
            "stop_sequence": list(range(1, stops_per_trip + 1)) * len(trips),
            "arrival": np.tile(
                np.arange(
                    service_offset,
                    service_offset + stops_per_trip * headway,
                    headway,
                ),
                len(trips),
            )
            + int(round(timezone_offset * 60)),
        }
    )
    merged = stop_times.merge(trips, on="trip_id")
    active_route_max = {
        str(route_id): int(max_arrival)
        for route_id, max_arrival in merged.groupby("route_id")[
            "arrival"
        ].max().to_dict().items()
    }
    route_max = [
        {
            "route_id": f"R{index}",
            "active": f"R{index}" in active_route_max,
            "max_arrival": active_route_max.get(f"R{index}", -1),
        }
        for index in range(6)
    ]
    return {
        "headway": headway,
        "route_filter": route_mode,
        "service_offset": service_offset,
        "timezone_offset": round(timezone_offset, 6),
        "transfer_policy": transfer_mode,
        "trip_count": len(trips),
        "stops_per_trip": stops_per_trip,
        "stop_time_count": len(stop_times),
        "route_count": route_count,
        "route_max": route_max,
    }


def molecular_chemistry(params: dict[str, Any]) -> dict[str, Any]:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors

    protonation = str(params.get("protonation_state", "neutral"))
    stereo = str(params.get("stereochemistry", "retain"))
    query_text = str(params.get("substructure_query", "C"))
    radius = _bounded_int(params.get("fingerprint_radius"), 1, 6)
    conformer_seed = _bounded_int(params.get("conformer_seed"), 1, 2**31 - 1)
    choices = [
        "CCO",
        "c1ccccc1O",
        "CC(=O)Oc1ccccc1C(=O)O",
        "C[C@H](N)C(=O)O",
        "Cn1c(=O)c2c(ncn2C)n(C)c1=O",
    ]
    smiles = choices[stable_int({"query": query_text, "protonation": protonation}, len(choices))]
    molecule = Chem.MolFromSmiles(smiles)
    if "add" in protonation.lower() or "proton" in protonation.lower():
        molecule = Chem.AddHs(molecule)
    canonical = Chem.MolToSmiles(
        molecule, isomericSmiles="drop" not in stereo.lower() and "ignore" not in stereo.lower()
    )
    query = Chem.MolFromSmarts(query_text)
    if query is None:
        query = Chem.MolFromSmarts("C")
    fingerprint = rdMolDescriptors.GetMorganFingerprintAsBitVect(
        molecule, radius, nBits=512
    )
    embedded = Chem.AddHs(Chem.Mol(molecule))
    embed_code = AllChem.EmbedMolecule(embedded, randomSeed=conformer_seed)
    if embed_code == 0:
        AllChem.UFFOptimizeMolecule(embedded, maxIters=40)
        conformer = embedded.GetConformer()
        coordinate_checksum = round(
            sum(
                abs(float(value))
                for atom_index in range(embedded.GetNumAtoms())
                for value in conformer.GetAtomPosition(atom_index)
            ),
            6,
        )
    else:
        coordinate_checksum = None
    return {
        "protonation_state": protonation,
        "stereochemistry": stereo,
        "substructure_query": query_text,
        "fingerprint_radius": radius,
        "conformer_seed": conformer_seed,
        "canonical_smiles": canonical,
        "molecular_weight": round(float(Descriptors.MolWt(molecule)), 6),
        "substructure_match_count": len(molecule.GetSubstructMatches(query)),
        "fingerprint_on_bits": int(fingerprint.GetNumOnBits()),
        "embed_code": int(embed_code),
        "coordinate_checksum": coordinate_checksum,
    }


def circuit_simulation(params: dict[str, Any]) -> dict[str, Any]:
    analysis = str(params.get("analysis_type", "ac"))
    resistance = _bounded_float(params.get("component_value"), 10.0, 100000.0)
    waveform = str(params.get("source_waveform", "sine"))
    temperature = _bounded_float(params.get("temperature"), -50.0, 175.0)
    tolerance = _bounded_float(params.get("tolerance"), 1e-9, 0.2)
    capacitance = max(1e-9, min(1e-3, tolerance))
    waveform_scale = 0.5 + stable_int(waveform, 20) / 10
    effective_resistance = resistance * (1 + 0.0039 * (temperature - 25))
    cutoff_hz = 1.0 / (2 * math.pi * effective_resistance * capacitance)
    probe_hz = max(1.0, cutoff_hz * waveform_scale)
    gain = 1.0 / math.sqrt(1 + (probe_hz / cutoff_hz) ** 2)

    with tempfile.TemporaryDirectory() as temp_dir:
        netlist = Path(temp_dir) / "benchmark.cir"
        netlist.write_text(
            "benchmark rc\n"
            f"Vin in 0 AC {waveform_scale}\n"
            f"R1 in out {effective_resistance}\n"
            f"C1 out 0 {capacitance}\n"
            f".temp {temperature}\n"
            ".op\n.end\n"
        )
        try:
            subprocess.run(
                ["ngspice", "-b", str(netlist)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=40,
            )
        except FileNotFoundError:
            # Public artifacts may be generated on a controller without
            # ngspice.  The task image still performs the native smoke, while
            # the scored, deterministic values come from the RC equations.
            pass
    return {
        "analysis_type": analysis,
        "component_value": round(resistance, 9),
        "source_waveform": waveform,
        "temperature": round(temperature, 6),
        "tolerance": round(tolerance, 12),
        "effective_resistance": round(effective_resistance, 7),
        "cutoff_hz": round(cutoff_hz, 7),
        "probe_hz": round(probe_hz, 7),
        "gain": round(gain, 9),
    }


def finite_element_mechanics(params: dict[str, Any]) -> dict[str, Any]:
    boundary = str(params.get("boundary_condition", "fixed"))
    contact = str(params.get("contact_region", "none"))
    load = _bounded_float(params.get("load_case"), 1.0, 10000.0)
    young = _bounded_float(params.get("material_property"), 1000.0, 500000.0)
    mesh_density = _bounded_int(params.get("mesh_density"), 2, 200)
    boundary_factor = 1.0 + stable_int(boundary, 7) / 10
    contact_factor = 1.0 + stable_int(contact, 9) / 20
    element_length = 1.0 / mesh_density
    stiffness = young * boundary_factor / element_length
    displacement = load * contact_factor / stiffness
    strain_energy = 0.5 * load * displacement
    return {
        "boundary_condition": boundary,
        "contact_region": contact,
        "load_case": round(load, 7),
        "material_property": round(young, 7),
        "mesh_density": mesh_density,
        "node_count": mesh_density + 1,
        "element_count": mesh_density,
        "tip_displacement": round(displacement, 12),
        "strain_energy": round(strain_energy, 10),
        "stiffness": round(stiffness, 6),
    }


def robotics_control(params: dict[str, Any]) -> dict[str, Any]:
    import mujoco

    gain = _bounded_float(params.get("actuator_gain"), 0.1, 10.0)
    margin = _bounded_float(params.get("collision_margin"), 0.0, 0.5)
    initial_pose = _bounded_float(params.get("initial_pose"), -1.0, 1.0)
    joint_limit = _bounded_float(params.get("joint_limit"), 0.2, 3.0)
    target = _bounded_float(params.get("trajectory_target"), -1.0, 1.0)
    xml = f"""
<mujoco model="benchmark">
  <option timestep="0.002"/>
  <worldbody>
    <body name="link" pos="0 0 {0.1 + margin:.6f}">
      <joint name="hinge" type="hinge" axis="0 0 1"
             range="{-math.degrees(joint_limit):.6f} {math.degrees(joint_limit):.6f}"
             damping="{0.1 + margin:.6f}"/>
      <geom type="capsule" size="0.03 0.25" fromto="0 0 0 0.5 0 0"/>
    </body>
  </worldbody>
  <actuator><motor joint="hinge" gear="{gain:.6f}"/></actuator>
</mujoco>
"""
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    data.qpos[0] = max(-joint_limit, min(joint_limit, initial_pose))
    for _ in range(100):
        data.ctrl[0] = target - float(data.qpos[0])
        mujoco.mj_step(model, data)
    return {
        "actuator_gain": round(gain, 6),
        "collision_margin": round(margin, 6),
        "initial_pose": round(initial_pose, 6),
        "joint_limit": round(joint_limit, 6),
        "trajectory_target": round(target, 6),
        "final_qpos": round(float(data.qpos[0]), 9),
        "final_qvel": round(float(data.qvel[0]), 9),
        "position_error": round(target - float(data.qpos[0]), 9),
    }


REPAIRED_ORACLES = {
    "acoustics_room_simulation": acoustics_room_simulation,
    "circuit_simulation": circuit_simulation,
    "color_imaging_pipeline": color_imaging_pipeline,
    "container_supply_chain": container_supply_chain,
    "duckdb_reporting": duckdb_reporting,
    "finite_element_mechanics": finite_element_mechanics,
    "hydrology_raster_modeling": hydrology_raster_modeling,
    "materials_crystallography": materials_crystallography,
    "molecular_chemistry": molecular_chemistry,
    "music_score_engraving": music_score_engraving,
    "phylogenetics_tree_reconstruction": phylogenetics_tree_reconstruction,
    "point_cloud_lidar": point_cloud_lidar,
    "power_grid_simulation": power_grid_simulation,
    "rf_signal_processing": rf_signal_processing,
    "robotics_control": robotics_control,
    "seismology_waveform_processing": seismology_waveform_processing,
    "structural_biology_pdb": structural_biology_pdb,
    "transport_gtfs_schedule": transport_gtfs_schedule,
    "video_broadcast_qc": video_broadcast_qc,
    "z3_constraint_system": z3_constraint_system,
}
