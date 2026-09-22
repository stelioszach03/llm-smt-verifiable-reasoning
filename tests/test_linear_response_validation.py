import pytest

from cegvr.generation.llm_linear import LLMLinearGenerator


def payload(content):
    return {"choices": [{"message": {"content": content}}]}


@pytest.mark.parametrize(
    "content",
    [
        None,
        123,
        "[]",
        "null",
        '{"assignments":{"x":NaN}}',
        '{"assignments":{"x":"Infinity"}}',
    ],
)
def test_malformed_or_nonfinite_assignments_are_rejected(content):
    assert LLMLinearGenerator()._parse_response(payload(content)) is None


def test_valid_numeric_assignment_remains_supported():
    assert LLMLinearGenerator()._parse_response(
        payload('{"assignments":{"x":"1.25"}}')
    ) == {"x": 1.25}


def test_invalid_provider_json_consumes_attempt_without_crashing(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            raise ValueError("invalid provider JSON")

    monkeypatch.setattr(
        "cegvr.generation.llm_linear.requests.post", lambda *a, **kw: Response()
    )
    assert (
        LLMLinearGenerator().propose({"variables": [], "constraints": []}, budget=1)
        == []
    )
