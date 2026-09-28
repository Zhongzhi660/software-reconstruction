#!/usr/bin/env python3
import json

_TABLE = json.loads('{\n  "{\\"corner_radius\\":25.86,\\"lip_depth\\":11,\\"wall\\":1.812}": {\n    "artifact": {\n      "format": "stl",\n      "path": "product.stl"\n    },\n    "geometry": {\n      "bbox_max_mm": [\n        73.3486,\n        16.18,\n        21.0\n      ],\n      "bbox_min_mm": [\n        -21.5495,\n        -17.292,\n        0.0\n      ],\n      "component_count": 8,\n      "extents_mm": [\n        94.8981,\n        33.472,\n        21.0\n      ],\n      "facet_count": 672,\n      "surface_area_mm2": 12287.149009,\n      "volume_mm3": 10873.212408,\n      "watertight": true\n    },\n    "scenario_parameters": {\n      "corner_radius": 25.86,\n      "lip_depth": 11,\n      "wall": 1.812\n    }\n  },\n  "{\\"corner_radius\\":26.15,\\"lip_depth\\":6,\\"wall\\":2.9}": {\n    "artifact": {\n      "format": "stl",\n      "path": "product.stl"\n    },\n    "geometry": {\n      "bbox_max_mm": [\n        73.3671,\n        16.18,\n        16.0\n      ],\n      "bbox_min_mm": [\n        -21.5557,\n        -18.38,\n        0.0\n      ],\n      "component_count": 8,\n      "extents_mm": [\n        94.9228,\n        34.56,\n        16.0\n      ],\n      "facet_count": 672,\n      "surface_area_mm2": 10491.869461,\n      "volume_mm3": 13856.186772,\n      "watertight": true\n    },\n    "scenario_parameters": {\n      "corner_radius": 26.15,\n      "lip_depth": 6,\n      "wall": 2.9\n    }\n  },\n  "{\\"corner_radius\\":32.07,\\"lip_depth\\":8,\\"wall\\":2.03}": {\n    "artifact": {\n      "format": "stl",\n      "path": "product.stl"\n    },\n    "geometry": {\n      "bbox_max_mm": [\n        73.7445,\n        16.18,\n        18.0\n      ],\n      "bbox_min_mm": [\n        -21.6815,\n        -17.51,\n        0.0\n      ],\n      "component_count": 8,\n      "extents_mm": [\n        95.426,\n        33.69,\n        18.0\n      ],\n      "facet_count": 672,\n      "surface_area_mm2": 11034.702443,\n      "volume_mm3": 10718.547624,\n      "watertight": true\n    },\n    "scenario_parameters": {\n      "corner_radius": 32.07,\n      "lip_depth": 8,\n      "wall": 2.03\n    }\n  },\n  "{\\"corner_radius\\":34.68,\\"lip_depth\\":10,\\"wall\\":1.015}": {\n    "artifact": {\n      "format": "stl",\n      "path": "product.stl"\n    },\n    "geometry": {\n      "bbox_max_mm": [\n        73.9108,\n        16.18,\n        20.0\n      ],\n      "bbox_min_mm": [\n        -21.7369,\n        -16.495,\n        0.0\n      ],\n      "component_count": 8,\n      "extents_mm": [\n        95.6477,\n        32.675,\n        20.0\n      ],\n      "facet_count": 672,\n      "surface_area_mm2": 11633.463751,\n      "volume_mm3": 6061.684542,\n      "watertight": true\n    },\n    "scenario_parameters": {\n      "corner_radius": 34.68,\n      "lip_depth": 10,\n      "wall": 1.015\n    }\n  }\n}')


def _key(params):
    return json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)


def true10_oracle(params):
    key = _key(params)
    if key not in _TABLE:
        raise KeyError(f"unrecognized true10 scenario parameters: {params!r}")
    return _TABLE[key]


ORACLES = {"openscad_parametric_cad": true10_oracle}
