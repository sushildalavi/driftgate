from __future__ import annotations

from pathlib import Path

from scripts.contract_review_agent import build_review, _load_json


def test_removed_required_field_fails():
    fixture_dir = Path(__file__).resolve().parent / "fixtures"
    review = build_review(
        _load_json(fixture_dir / "openapi_old.json"),
        _load_json(fixture_dir / "openapi_new.json"),
    )
    assert review["ci_decision"] == "fail"
    assert review["risk_level"] == "high"
    assert review["breaking_changes"]
    assert review["trace"]


def test_added_optional_field_passes():
    old = {"components": {"schemas": {"Event": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}}}}
    new = {"components": {"schemas": {"Event": {"type": "object", "properties": {"id": {"type": "string"}, "trace_id": {"type": "string"}}, "required": ["id"]}}}}
    review = build_review(old, new)
    assert review["ci_decision"] == "pass"
    assert "Event.trace_id added as optional" in review["non_breaking_changes"]


def test_generated_pr_comment_includes_evidence():
    fixture_dir = Path(__file__).resolve().parent / "fixtures"
    review = build_review(
        _load_json(fixture_dir / "openapi_old.json"),
        _load_json(fixture_dir / "openapi_new.json"),
    )
    assert "DRIFTGATE Contract Review" in review["pr_comment_markdown"]
    assert "Event.payload type object -> string" in review["pr_comment_markdown"]
