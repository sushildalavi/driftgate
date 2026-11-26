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


def extract_structural_type(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: extract_structural_type(v) for k, v in sorted(value.items(), key=lambda kv: kv[0])}
    if isinstance(value, list):
        if not value:
            return ["empty_array"]

        inner_types: set[str] = set()
        array_structures: list[str] = []

        for item in value:
            resolved = extract_structural_type(item)
            if isinstance(resolved, str):
                inner_types.add(resolved)
            else:
                stringified_structure = serialize_ast_to_string(resolved)
                array_structures.append(stringified_structure)

        result = sorted(list(inner_types))
        if array_structures:
            result.extend(sorted(array_structures))
        return result
    return _primitive_type(value)


def serialize_ast_to_string(structure: Any) -> str:
    if isinstance(structure, str):
        return structure
    if isinstance(structure, dict):
        parts = [f"{k}:{serialize_ast_to_string(v)}" for k, v in sorted(structure.items(), key=lambda kv: kv[0])]
        return "object{" + ";".join(parts) + "}"
    if isinstance(structure, list):
        parts = [serialize_ast_to_string(item) for item in structure]
        return "array[" + ",".join(parts) + "]"
    return "unknown"


def structural_string(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        raise TypeError("payload must be a JSON object at the root")
    parts = [
        f"{k}:{serialize_ast_to_string(extract_structural_type(v))};"
        for k, v in sorted(payload.items(), key=lambda kv: kv[0])
    ]
    return "".join(parts)


def fingerprint_schema(payload: dict[str, Any]) -> str:
    structural = structural_string(payload)
    return hashlib.sha256(structural.encode("utf-8")).hexdigest()
