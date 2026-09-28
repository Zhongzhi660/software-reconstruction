#!/usr/bin/env python3
"""Deterministic STL geometry metrics used by OpenSCAD task verifiers."""

from __future__ import annotations

import math
import hashlib
import struct
from collections import Counter
from pathlib import Path
from typing import Any


Point = tuple[float, float, float]
Triangle = tuple[Point, Point, Point]


def _binary_triangles(data: bytes) -> list[Triangle] | None:
    if len(data) < 84:
        return None
    count = struct.unpack_from("<I", data, 80)[0]
    if 84 + count * 50 != len(data):
        return None
    triangles: list[Triangle] = []
    offset = 84
    for _ in range(count):
        values = struct.unpack_from("<12fH", data, offset)
        triangles.append(
            (
                (values[3], values[4], values[5]),
                (values[6], values[7], values[8]),
                (values[9], values[10], values[11]),
            )
        )
        offset += 50
    return triangles


def _ascii_triangles(data: bytes) -> list[Triangle]:
    vertices: list[Point] = []
    for raw_line in data.decode("utf-8", errors="replace").splitlines():
        parts = raw_line.strip().split()
        if len(parts) == 4 and parts[0].lower() == "vertex":
            vertices.append(tuple(float(value) for value in parts[1:4]))
    if not vertices or len(vertices) % 3:
        raise ValueError("STL has no complete triangle vertex records")
    return [
        (vertices[index], vertices[index + 1], vertices[index + 2])
        for index in range(0, len(vertices), 3)
    ]


def load_triangles(path: str | Path) -> list[Triangle]:
    data = Path(path).read_bytes()
    triangles = _binary_triangles(data)
    if triangles is None:
        triangles = _ascii_triangles(data)
    if len(triangles) < 4:
        raise ValueError(f"mesh is empty or trivial: {path}")
    return triangles


def _sub(left: Point, right: Point) -> Point:
    return tuple(left[index] - right[index] for index in range(3))


def _cross(left: Point, right: Point) -> Point:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _dot(left: Point, right: Point) -> float:
    return sum(left[index] * right[index] for index in range(3))


def _norm(value: Point) -> float:
    return math.sqrt(_dot(value, value))


def _vertex_key(point: Point) -> tuple[int, int, int]:
    return tuple(round(value * 1_000_000) for value in point)


def mesh_metrics(triangles: list[Triangle]) -> dict[str, Any]:
    points = [point for triangle in triangles for point in triangle]
    low = [min(point[index] for point in points) for index in range(3)]
    high = [max(point[index] for point in points) for index in range(3)]
    area = 0.0
    signed_volume = 0.0
    edges: Counter[tuple[tuple[int, int, int], tuple[int, int, int]]] = Counter()
    parents = list(range(len(triangles)))
    vertex_owner: dict[tuple[int, int, int], int] = {}

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    for triangle_index, (a, b, c) in enumerate(triangles):
        area += _norm(_cross(_sub(b, a), _sub(c, a))) / 2.0
        signed_volume += _dot(a, _cross(b, c)) / 6.0
        keys = [_vertex_key(point) for point in (a, b, c)]
        for key in keys:
            owner = vertex_owner.setdefault(key, triangle_index)
            union(triangle_index, owner)
        for left, right in ((keys[0], keys[1]), (keys[1], keys[2]), (keys[2], keys[0])):
            edges[tuple(sorted((left, right)))] += 1

    return {
        "bbox_min_mm": [round(value, 6) for value in low],
        "bbox_max_mm": [round(value, 6) for value in high],
        "extents_mm": [round(high[index] - low[index], 6) for index in range(3)],
        "volume_mm3": round(abs(signed_volume), 6),
        "surface_area_mm2": round(area, 6),
        "facet_count": len(triangles),
        "component_count": len({find(index) for index in range(len(triangles))}),
        "watertight": bool(edges) and all(count == 2 for count in edges.values()),
    }


def metrics_for_stl(path: str | Path) -> dict[str, Any]:
    return mesh_metrics(load_triangles(path))


def geometry_fingerprint(triangles: list[Triangle]) -> str:
    """Hash quantized triangle geometry while ignoring STL bytes and facet order."""
    canonical_triangles = sorted(
        tuple(sorted(_vertex_key(point) for point in triangle))
        for triangle in triangles
    )
    digest = hashlib.sha256()
    for triangle in canonical_triangles:
        digest.update(repr(triangle).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _sample_points(triangles: list[Triangle], maximum: int = 2048):
    count = min(len(triangles), maximum)
    indices = [
        min(len(triangles) - 1, int(index * len(triangles) / count))
        for index in range(count)
    ]
    return [
        tuple(sum(triangles[index][vertex][axis] for vertex in range(3)) / 3.0 for axis in range(3))
        for index in indices
    ]


def _center(points: list[Point]) -> tuple[list[Point], float]:
    low = [min(point[index] for point in points) for index in range(3)]
    high = [max(point[index] for point in points) for index in range(3)]
    center = [(low[index] + high[index]) / 2.0 for index in range(3)]
    diagonal = max(
        math.sqrt(sum((high[index] - low[index]) ** 2 for index in range(3))),
        1e-9,
    )
    return [
        tuple(point[index] - center[index] for index in range(3))
        for point in points
    ], diagonal


def surface_distance(
    candidate: list[Triangle], reference: list[Triangle]
) -> dict[str, float]:
    import numpy as np
    from scipy.spatial import cKDTree

    candidate_points, _ = _center(_sample_points(candidate))
    reference_points, diagonal = _center(_sample_points(reference))
    candidate_array = np.asarray(candidate_points, dtype=np.float64)
    reference_array = np.asarray(reference_points, dtype=np.float64)
    candidate_tree = cKDTree(candidate_array)
    reference_tree = cKDTree(reference_array)
    reference_to_candidate = candidate_tree.query(reference_array, workers=1)[0]
    candidate_to_reference = reference_tree.query(candidate_array, workers=1)[0]
    both = np.concatenate((reference_to_candidate, candidate_to_reference)) / diagonal
    return {
        "normalized_mean": float(np.mean(both)),
        "normalized_p95": float(np.percentile(both, 95)),
        "reference_coverage_2pct": float(
            np.mean(reference_to_candidate <= diagonal * 0.02)
        ),
        "candidate_precision_2pct": float(
            np.mean(candidate_to_reference <= diagonal * 0.02)
        ),
    }


def relative_error(actual: float, expected: float) -> float:
    return abs(actual - expected) / max(abs(expected), 1e-9)


def compare_stl(candidate_path: str | Path, reference_path: str | Path) -> dict[str, Any]:
    candidate = load_triangles(candidate_path)
    reference = load_triangles(reference_path)
    candidate_metrics = mesh_metrics(candidate)
    reference_metrics = mesh_metrics(reference)
    extent_errors = [
        relative_error(actual, expected)
        for actual, expected in zip(
            candidate_metrics["extents_mm"], reference_metrics["extents_mm"]
        )
    ]
    distance = surface_distance(candidate, reference)
    checks = {
        "bbox_extents": max(extent_errors) <= 0.05,
        "surface_area": relative_error(
            candidate_metrics["surface_area_mm2"],
            reference_metrics["surface_area_mm2"],
        )
        <= 0.10,
        "volume": (
            relative_error(
                candidate_metrics["volume_mm3"],
                reference_metrics["volume_mm3"],
            )
            <= 0.10
            if reference_metrics["volume_mm3"] > 1e-6
            else True
        ),
        "component_count": (
            candidate_metrics["component_count"]
            == reference_metrics["component_count"]
        ),
        "facet_complexity": (
            0.25
            <= candidate_metrics["facet_count"]
            / max(reference_metrics["facet_count"], 1)
            <= 4.0
        ),
        "watertight": (
            candidate_metrics["watertight"]
            if reference_metrics["watertight"]
            else True
        ),
        "surface_mean": distance["normalized_mean"] <= 0.03,
        "surface_p95": distance["normalized_p95"] <= 0.08,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "candidate_metrics": candidate_metrics,
        "reference_metrics": reference_metrics,
        "extent_relative_errors": extent_errors,
        "surface_distance": distance,
    }
