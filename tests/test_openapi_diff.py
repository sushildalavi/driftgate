from __future__ import annotations

from pathlib import Path

from scripts.openapi_diff import classify_diff, diff_schemas, diff_openapi_documents, _extract_schema, _load_json


def test_openapi_diff_detects_breaking_changes():
    fixture_dir = Path(__file__).resolve().parent / "fixtures"
    old = _extract_schema(_load_json(fixture_dir / "openapiOld.json"))
    new = _extract_schema(_load_json(fixture_dir / "openapiNew.json"))
    result = classify_diff(diff_schemas(old["Event"], new["Event"]))
    assert result["breaking"] is True
    assert "payload" in result["diff"]["type_changes"][0]


def test_openapi_document_diff_detects_breaking_changes():
    fixture_dir = Path(__file__).resolve().parent / "fixtures"
    result = diff_openapi_documents(_load_json(fixture_dir / "openapiOld.json"), _load_json(fixture_dir / "openapiNew.json"))
    assert result["breaking"] is True


def test_openapi_diff_detects_added_optional_field():
    old = {"properties": {"a": {"type": "string"}}, "required": ["a"]}
    new = {"properties": {"a": {"type": "string"}, "b": {"type": "string"}}, "required": ["a"]}
    result = diff_schemas(old, new)
    assert result["added_optional_fields"] == ["b"]
