from __future__ import annotations

import hashlib
from typing import Any


def _primitive_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    return "unknown"


def normalize_types(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: normalize_types(v) for k, v in sorted(value.items(), key=lambda kv: kv[0])}
    if isinstance(value, list):
        return [normalize_types(v) for v in value]
    return _primitive_type(value)


def structural_ast(value: Any) -> str:
    if isinstance(value, dict):
        parts = [f"{k}:{structural_ast(v)}" for k, v in sorted(value.items(), key=lambda kv: kv[0])]
        return "object{" + ";".join(parts) + "}"

    if isinstance(value, list):
        if not value:
            return "array_unknown"

        item_types = [structural_ast(v) for v in value]
        first = item_types[0]
        if all(t == first for t in item_types):
            return f"array_{first}"
        return "array_mixed"

    return _primitive_type(value)


def structural_string(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        raise TypeError("payload must be a JSON object at the root")
    parts = [f"{k}:{structural_ast(v)};" for k, v in sorted(payload.items(), key=lambda kv: kv[0])]
    return "".join(parts)


def fingerprint_schema(payload: dict[str, Any]) -> str:
    structural = structural_string(payload)
    return hashlib.sha256(structural.encode("utf-8")).hexdigest()
