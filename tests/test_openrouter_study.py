"""Paid transport invariants, exercised with offline HTTP doubles."""

import json
from pathlib import Path
import time

import pytest

from cegvr.generation.openrouter_study import (
    AccountedOpenRouter,
    StudyStopped,
    cost_reservation,
    read_visible_response,
    stable_seed,
)


class Connection:
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, *args):
        return self

    def fetchone(self):
        return [sum(r["charged"] for r in self.store.rows)]


class Store:
    def __init__(self):
        self.rows = []

    def connect(self):
        return Connection(self)

    def reserve(self, bucket, model, amount, run_id=None):
        self.rows.append({"reserved": amount, "charged": amount})
        return len(self.rows) - 1

    def settle(self, ident, amount, usage):
        self.rows[ident]["charged"] = (
            self.rows[ident]["reserved"] if amount is None else amount
        )


class Response:
    def __init__(self, status=200, cost=0.00002):
        self.status_code = status
        self.body = {
            "id": "fixture",
            "model": "openai/gpt-oss-20b",
            "provider": "CoreWeave",
            "choices": [
                {
                    "message": {
                        "content": '{"status":"sat","assignment":{"x":2}}',
                        "reasoning_content": "never save this",
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
                "cost": cost,
            },
        }
        self.content = json.dumps(self.body).encode()

    def json(self):
        return self.body


def generator(tmp_path, **kwargs):
    return AccountedOpenRouter(
        key="test-key",
        store=Store(),
        study_id="study",
        run_id="study:episode",
        repeat=17,
        events_path=tmp_path / "events.jsonl",
        lock_path=tmp_path / "lock",
        deadline=time.time() + 60,
        **kwargs,
    )


PROBLEM = {
    "problem_id": "sat-test",
    "ground_truth": "sat",
    "metadata": {"witness": {"x": 2}},
    "variables": [{"name": "x", "domain": "int", "bounds": {"lower": 0, "upper": 4}}],
    "constraints": [
        {
            "kind": "linear_ineq",
            "terms": [{"variable": "x", "coefficient": 1}],
            "relation": "=",
            "rhs": 2,
        }
    ],
}


def test_prompt_and_capture_have_no_ground_truth_hidden_reasoning_or_key(
    tmp_path, monkeypatch
):
    observed = []

    def post(*args, **kwargs):
        observed.append(kwargs)
        return Response()

    monkeypatch.setattr("requests.post", post)
    g = generator(tmp_path)
    proposals = g.propose_candidates(PROBLEM, 2)
    assert len(proposals) == g.calls == 2
    assert all(p.candidate.assignment == {"x": 2} for p in proposals)
    assert observed[0]["json"]["seed"] != observed[1]["json"]["seed"]
    assert observed[0]["json"]["provider"]["allow_fallbacks"] is False
    capture = (tmp_path / "events.jsonl").read_text()
    for forbidden in (
        "test-key",
        "never save this",
        "sat-test",
        "ground_truth",
        "witness",
    ):
        assert forbidden not in capture
    assert g.accounted_micro_usd == 40


def test_429_retries_have_separate_reservations_and_same_payload(tmp_path, monkeypatch):
    responses = iter([Response(429), Response(429), Response()])
    seen = []

    def post(*args, **kwargs):
        seen.append(kwargs["json"])
        return next(responses)

    monkeypatch.setattr("requests.post", post)
    monkeypatch.setattr("time.sleep", lambda _: None)
    g = generator(tmp_path)
    assert g.propose_candidates(PROBLEM, 1)[0].candidate is not None
    assert g.calls == 3 and g.uncertain_calls == 2 and g.transport_errors == 2
    assert seen[0] == seen[1] == seen[2]
    assert g.accounted_micro_usd == sum(r["charged"] for r in g.store.rows)


def test_cap_checked_before_network(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "requests.post", lambda *a, **k: pytest.fail("network should not be called")
    )
    g = generator(tmp_path, allowance_usd=0.000001)
    with pytest.raises(StudyStopped, match="study_budget"):
        g.propose_candidates(PROBLEM, 1)
    assert g.calls == 0 and not g.store.rows


def test_unknown_cost_retains_reserve_and_no_reasoning_fallback(tmp_path, monkeypatch):
    response = Response(cost=None)
    response.body["choices"][0]["message"]["content"] = None
    monkeypatch.setattr("requests.post", lambda *a, **k: response)
    g = generator(tmp_path)
    result = g.propose_candidates(PROBLEM, 1)[0]
    assert result.candidate is None
    assert g.uncertain_calls == 1
    assert g.store.rows[0]["charged"] == g.store.rows[0]["reserved"]


def test_requested_seed_is_stable_and_reservation_is_bounded():
    assert stable_seed("task", 17, 1) == stable_seed("task", 17, 1)
    assert stable_seed("task", 17, 1) != stable_seed("task", 29, 1)
    assert cost_reservation({"messages": [], "max_tokens": 2048}) > 512
    assert (
        read_visible_response({"choices": []})["choices"][0]["message"]["content"]
        is None
    )


def test_provider_identity_mismatch_stops_after_accounting(tmp_path, monkeypatch):
    response = Response()
    response.body["provider"] = "unexpected"
    monkeypatch.setattr("requests.post", lambda *a, **k: response)
    g = generator(tmp_path)
    with pytest.raises(StudyStopped, match="provider_identity_mismatch"):
        g.propose_candidates(PROBLEM, 1)
    assert g.calls == 1 and g.accounted_micro_usd == 20


def test_invalid_usage_is_unknown():
    body = Response().body
    body["usage"] = {
        "prompt_tokens": "100",
        "completion_tokens": -1,
        "cost": float("nan"),
    }
    assert all(v is None for v in read_visible_response(body)["usage"].values())
