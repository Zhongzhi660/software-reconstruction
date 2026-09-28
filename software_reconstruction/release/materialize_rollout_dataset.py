#!/usr/bin/env python3
"""Materialize the exact 20 F50x2 reconstruction tasks for Harbor."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


TASK_IDS = (
    "openscad_planetary_gears",
    "openscad_skinned_enclosure",
    "blender_mesh_fracturing",
    "blender_tree_leaves_moss",
    "web_dashboard_workspace",
    "web_tasks_console",
    "verilog_axis_fifo",
    "verilog_axis_arb_mux",
    "cmake_export_import",
    "cmake_tutorial_complete",
    "nginx_proxy_cache",
    "nginx_rewrite_precedence",
    "tree_sitter_python_slice",
    "tree_sitter_rust_slice",
    "openssl_pkits_basic_constraints",
    "openssl_pkits_name_constraints",
    "kicad_complex_hierarchy",
    "kicad_stickhub",
    "openfoam_pitz_daily",
    "openfoam_buoyant_cavity",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task", action="append", choices=TASK_IDS)
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    selected = tuple(args.task) if args.task else TASK_IDS
    records = []
    for task_id in selected:
        task = source / task_id
        required = ("task.toml", "instruction.md", "environment/Dockerfile", "tests/test.sh")
        missing = [name for name in required if not (task / name).is_file()]
        if missing:
            raise FileNotFoundError(f"{task_id}: missing {missing}")
        destination = output / task_id
        os.symlink(task, destination, target_is_directory=True)
        records.append(
            {
                "task_id": task_id,
                "source": str(task),
                "dataset_path": str(destination),
            }
        )
    manifest = {
        "task_count": len(records),
        "task_ids": list(selected),
        "tasks": records,
    }
    (output / "dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(output), "task_count": len(records)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
