from app.runtime.classifier import diff_and_classify, summarize_classification


def _classifications(old, new):
    return [d.classification for d in diff_and_classify(old, new)]


def test_add_optional_field_safe():
    old = {"id": {"type": "integer", "nullable": False}}
    new = {"id": {"type": "integer", "nullable": False}, "email": {"type": "string", "nullable": False, "required": False}}
    assert _classifications(old, new) == ["SAFE"]


def test_add_required_field_forward_compatible():
    old = {"id": {"type": "integer", "nullable": False}}
    new = {"id": {"type": "integer", "nullable": False}, "email": {"type": "string", "nullable": False, "required": True}}
    assert _classifications(old, new) == ["FORWARD_COMPATIBLE"]


def test_remove_required_field_breaking():
    old = {"email": {"type": "string", "nullable": False, "required": True}}
    new = {}
    assert _classifications(old, new) == ["BREAKING"]


def test_required_becomes_nullable_backward_compatible():
    old = {"name": {"type": "string", "nullable": False}}
    new = {"name": {"type": "string", "nullable": True}}
    assert _classifications(old, new) == ["BACKWARD_COMPATIBLE"]


def test_nullable_becomes_required_breaking():
    old = {"name": {"type": "string", "nullable": True}}
    new = {"name": {"type": "string", "nullable": False}}
    assert _classifications(old, new) == ["BREAKING"]


def test_int_to_float_risky():
    old = {"score": {"type": "integer", "nullable": False}}
    new = {"score": {"type": "number", "nullable": False}}
    assert _classifications(old, new) == ["RISKY"]


def test_float_to_int_breaking():
    old = {"score": {"type": "number", "nullable": False}}
    new = {"score": {"type": "integer", "nullable": False}}
    assert _classifications(old, new) == ["BREAKING"]


def test_string_to_number_breaking():
    old = {"score": {"type": "string", "nullable": False}}
    new = {"score": {"type": "number", "nullable": False}}
    assert _classifications(old, new) == ["BREAKING"]


def test_enum_expansion_forward_compatible():
    old = {"state": {"type": "string", "nullable": False, "enum": ["a", "b"]}}
    new = {"state": {"type": "string", "nullable": False, "enum": ["a", "b", "c"]}}
    assert _classifications(old, new) == ["FORWARD_COMPATIBLE"]


def test_enum_contraction_breaking():
    old = {"state": {"type": "string", "nullable": False, "enum": ["a", "b", "c"]}}
    new = {"state": {"type": "string", "nullable": False, "enum": ["a", "b"]}}
    assert _classifications(old, new) == ["BREAKING"]


def test_nested_mutation_detected():
    old = {"user": {"id": {"type": "integer", "nullable": False}}}
    new = {"user": {"id": {"type": "string", "nullable": False}}}
    result = diff_and_classify(old, new)
    assert any(d.path == "user.id" for d in result)
    assert summarize_classification(result) == "BREAKING"


def test_array_item_mutation_detected():
    old = {"tags": [{"type": "string", "nullable": False}]}
    new = {"tags": [{"type": "integer", "nullable": False}]}
    result = diff_and_classify(old, new)
    assert result
    assert summarize_classification(result) == "BREAKING"
