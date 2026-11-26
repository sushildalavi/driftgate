from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.runtime.models import SeverityRank


@dataclass(frozen=True)
class DiffItem:
    path: str
    old_type: str | None
    new_type: str | None
    old_nullable: bool | None
    new_nullable: bool | None
    classification: str
    reason: str


def _is_leaf(node: Any) -> bool:
    # A payload can have a field called "type". Only a string value marks a schema leaf;
    # a nested schema under that key means this node is an ordinary object.
    return isinstance(node, dict) and isinstance(node.get("type"), str)


def _type_of(node: Any) -> str:
    if _is_leaf(node):
        return node["type"]
    if isinstance(node, dict):
        return "object"
    if isinstance(node, list):
        return "array"
    return "unknown"


def _nullable_of(node: Any) -> bool | None:
    if _is_leaf(node) and "nullable" in node:
        return bool(node["nullable"])
    return None


def _flatten(schema: Any, prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    if isinstance(schema, dict):
        if _is_leaf(schema):
            flat[prefix or "[root]"] = schema
            return flat
        for k, v in schema.items():
            path = f"{prefix}.{k}" if prefix else k
            flat.update(_flatten(v, path))
        return flat
    if isinstance(schema, list):
        flat[prefix or "[root]"] = {"type": "array", "nullable": False}
        for i, item in enumerate(schema):
            flat.update(_flatten(item, f"{prefix}[*{i}]" if prefix else f"[*{i}]"))
        return flat
    flat[prefix or "[root]"] = {"type": "unknown", "nullable": True}
    return flat


def _classify(old: Any | None, new: Any | None) -> tuple[str, str]:
    if old is None and new is not None:
        # default policy: new field is treated optional unless explicitly required metadata exists
        required = isinstance(new, dict) and bool(new.get("required", False))
        if required:
            return "FORWARD_COMPATIBLE", "added required field"
        return "SAFE", "added optional field"
    if old is not None and new is None:
        old_required = isinstance(old, dict) and bool(old.get("required", True))
        if old_required:
            return "BREAKING", "removed required field"
        return "RISKY", "removed optional field"

    old_t = _type_of(old)
    new_t = _type_of(new)
    if old_t != new_t:
        if old_t == "integer" and new_t == "number":
            return "RISKY", "int->float widening"
        if old_t == "number" and new_t == "integer":
            return "BREAKING", "float->int narrowing"
        if old_t == "string" and new_t in {"integer", "number"}:
            return "BREAKING", "string->number"
        if old_t == "array" and new_t == "array":
            return "BREAKING", "array item mutation"
        return "BREAKING", f"type changed {old_t}->{new_t}"

    old_null = _nullable_of(old)
    new_null = _nullable_of(new)
    if old_null is False and new_null is True:
        return "BACKWARD_COMPATIBLE", "required field becomes nullable"
    if old_null is True and new_null is False:
        return "BREAKING", "nullable field becomes required"

    if isinstance(old, dict) and isinstance(new, dict):
        old_enum = old.get("enum")
        new_enum = new.get("enum")
        if isinstance(old_enum, list) and isinstance(new_enum, list):
            old_set = set(old_enum)
            new_set = set(new_enum)
            if old_set < new_set:
                return "FORWARD_COMPATIBLE", "enum expansion"
            if new_set < old_set:
                return "BREAKING", "enum contraction"

    return "SAFE", "no compatibility risk"


def diff_and_classify(old_schema: dict[str, Any], new_schema: dict[str, Any]) -> list[DiffItem]:
    old_flat = _flatten(old_schema)
    new_flat = _flatten(new_schema)
    diffs: list[DiffItem] = []
    for path in sorted(old_flat.keys() | new_flat.keys()):
        old = old_flat.get(path)
        new = new_flat.get(path)
        if old == new:
            continue
        cls, reason = _classify(old, new)
        diffs.append(
            DiffItem(
                path=path,
                old_type=_type_of(old) if old is not None else None,
                new_type=_type_of(new) if new is not None else None,
                old_nullable=_nullable_of(old),
                new_nullable=_nullable_of(new),
                classification=cls,
                reason=reason,
            )
        )
    return diffs


def summarize_classification(diffs: list[DiffItem]) -> str:
    if not diffs:
        return "SAFE"
    order = {k: int(v) for k, v in SeverityRank.__members__.items()}
    return max((d.classification for d in diffs), key=lambda c: order.get(c, 0))
