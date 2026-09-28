"""Strict, complete semantic comparison used by the repaired SWR benchmark.

The old generated comparator scored only the first 20 object fields and first
8 list items, ignored every digest-looking value, and allowed a 25% numeric
error.  This comparator walks the complete value while bounding diagnostics
rather than scoring coverage.
"""

from __future__ import annotations

import math
from typing import Any


MAX_DIAGNOSTICS = 24
FLOAT_ABS_TOL = 1e-6
FLOAT_REL_TOL = 1e-4


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate(got: Any, expected: Any, family: str | None = None) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    compared = 0

    def fail(path: str, reason: str, actual: Any, wanted: Any) -> None:
        if len(mismatches) < MAX_DIAGNOSTICS:
            mismatches.append(
                {
                    "field": path,
                    "passed": False,
                    "reason": reason,
                    "expected": wanted,
                    "got": actual,
                }
            )

    def compare(path: str, actual: Any, wanted: Any) -> None:
        nonlocal compared
        compared += 1

        if isinstance(wanted, bool):
            if not isinstance(actual, bool) or actual != wanted:
                fail(path, "boolean_mismatch", actual, wanted)
            return

        if _is_number(wanted):
            if not _is_number(actual):
                fail(path, "not_numeric", actual, wanted)
                return
            actual_float = float(actual)
            wanted_float = float(wanted)
            if not (math.isfinite(actual_float) and math.isfinite(wanted_float)):
                if actual_float != wanted_float:
                    fail(path, "non_finite_numeric_mismatch", actual, wanted)
                return
            if isinstance(wanted, int):
                if actual_float != wanted_float:
                    fail(path, "integer_mismatch", actual, wanted)
                return
            tolerance = max(FLOAT_ABS_TOL, abs(wanted_float) * FLOAT_REL_TOL)
            if abs(actual_float - wanted_float) > tolerance:
                fail(path, "float_outside_tolerance", actual, wanted)
            return

        if isinstance(wanted, str) or wanted is None:
            if actual != wanted:
                fail(path, "scalar_mismatch", actual, wanted)
            return

        if isinstance(wanted, (list, tuple)):
            if not isinstance(actual, (list, tuple)):
                fail(path, "not_a_list", actual, wanted)
                return
            if len(actual) != len(wanted):
                fail(f"{path}.length", "list_length_mismatch", len(actual), len(wanted))
            for index, wanted_item in enumerate(wanted):
                if index < len(actual):
                    compare(f"{path}[{index}]", actual[index], wanted_item)
            return

        if isinstance(wanted, dict):
            if not isinstance(actual, dict):
                fail(path, "not_an_object", actual, wanted)
                return
            wanted_keys = set(wanted)
            actual_keys = set(actual)
            if wanted_keys != actual_keys:
                fail(
                    f"{path}.keys",
                    "object_key_mismatch",
                    {
                        "missing": sorted(wanted_keys - actual_keys),
                        "extra": sorted(actual_keys - wanted_keys),
                    },
                    sorted(wanted_keys),
                )
            for key in sorted(wanted_keys):
                if key in actual:
                    compare(f"{path}.{key}", actual[key], wanted[key])
            return

        if actual != wanted:
            fail(path, "value_mismatch", actual, wanted)

    compare("$", got, expected)
    if mismatches:
        return [
            {
                "field": "$",
                "passed": False,
                "reason": "semantic_mismatch",
                "family": family,
                "compared_values": compared,
                "mismatch_count_at_least": len(mismatches),
            },
            *mismatches,
        ]
    return [
        {
            "field": "$",
            "passed": True,
            "family": family,
            "compared_values": compared,
            "float_abs_tol": FLOAT_ABS_TOL,
            "float_rel_tol": FLOAT_REL_TOL,
        }
    ]
