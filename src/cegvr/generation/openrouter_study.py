"""Bounded research transport; no credentials or hidden reasoning in artifacts."""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import time
from pathlib import Path

import requests

from cegvr.candidate.types import CandidateProposal
from cegvr.generation.llm_candidate_linear import LLMLinearCandidateGenerator


MODEL = "openai/gpt-oss-20b"
ROUTING = {
    "only": ["coreweave/fp4"],
    "allow_fallbacks": False,
    "require_parameters": True,
    "quantizations": ["fp4"],
    "max_price": {"prompt": 0.05, "completion": 0.25},
}


class StudyStopped(RuntimeError):
    """A finite study allowance or operational deadline was reached."""


def stable_seed(problem_id: str, repeat: int, ordinal: int) -> int:
    data = f"cegvr-pilot-v1|{problem_id}|{repeat}|{ordinal}".encode()
    return int(hashlib.sha256(data).hexdigest()[:8], 16) & 0x7FFFFFFF


def cost_reservation(payload: dict) -> int:
    # UTF-8 bytes conservatively bound tokens for this ASCII-dominated prompt.
    # Include JSON/schema and 2,048 tokens of chat-template overhead.
    input_bound = len(json.dumps(payload, ensure_ascii=False).encode()) + 2048
    return math.ceil(input_bound * 0.05 + payload["max_tokens"] * 0.25)


def read_visible_response(body: dict) -> dict:
    """Allowlist only visible content and accounting, never reasoning fields."""
    choices = body.get("choices")
    if not isinstance(choices, list):
        choices = []
    choice = choices[0] if choices and isinstance(choices[0], dict) else {}
    message = choice.get("message") or {}
    if not isinstance(message, dict):
        message = {}
    content = message.get("content")
    usage = body.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    safe_usage = {
        key: value if type(value := usage.get(key)) is int and value >= 0 else None
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    }
    cost = usage.get("cost")
    safe_usage["cost"] = (
        cost
        if type(cost) in (int, float) and math.isfinite(cost) and cost >= 0
        else None
    )
    return {
        "id": body.get("id"),
        "model": body.get("model"),
        "provider": body.get("provider"),
        "choices": [
            {
                "message": {"content": content if isinstance(content, str) else None},
                "finish_reason": choice.get("finish_reason"),
            }
        ],
        "usage": safe_usage,
    }


class AccountedOpenRouter(LLMLinearCandidateGenerator):
    """One sequential generator per episode; workers use separate processes."""

    def __init__(
        self,
        *,
        key: str,
        store,
        study_id: str,
        run_id: str,
        repeat: int,
        events_path: Path,
        lock_path: Path,
        deadline: float,
        allowance_usd: float = 3.0,
    ):
        super().__init__(model=MODEL, max_tokens=2048, temperature=0.2)
        self.key, self.store = key, store
        self.study_id, self.run_id, self.repeat = study_id, run_id, repeat
        self.events_path, self.lock_path = events_path, lock_path
        self.deadline, self.allowance_usd = deadline, allowance_usd
        self.calls = 0
        self.ordinal = 0
        self.accounted_micro_usd = 0
        self.provider_reported_cost_usd = 0.0
        self.known_cost_calls = 0
        self.uncertain_calls = 0
        self.transport_errors = 0

    def _append(self, event):
        with self.events_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, sort_keys=True) + "\n")
            stream.flush()

    def _reserve(self, payload):
        if time.time() >= self.deadline:
            raise StudyStopped("operational_deadline")
        amount = cost_reservation(payload)
        # Lock spans study-cap query and shared-ledger reservation. The original
        # Forge ledger independently enforces its unchanged global/research caps.
        with self.lock_path.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with self.store.connect() as connection:
                used = connection.execute(
                    "SELECT COALESCE(SUM(charged),0) FROM charges "
                    "WHERE substr(run_id,1,?)=?",
                    (len(self.study_id) + 1, self.study_id + ":"),
                ).fetchone()[0]
            if used + amount > round(self.allowance_usd * 1e6):
                raise StudyStopped("study_budget")
            ident = self.store.reserve("research", MODEL, amount, run_id=self.run_id)
        return ident, amount

    def propose_candidates(self, problem, budget, hint=None):
        proposals = []
        for _ in range(max(0, budget)):
            self.ordinal += 1
            payload = self._build_payload(problem, hint)
            payload.pop("chat_template_kwargs", None)
            # CoreWeave's grammar engine rejects JSON Schema if/then. Retain
            # shape constraints server-side; enforce the full SAT/UNSAT contract
            # with the strict local CandidateOutput validator after generation.
            payload["response_format"]["json_schema"]["schema"].pop("allOf", None)
            payload.update(
                provider=ROUTING,
                reasoning={"effort": "low"},
                seed=stable_seed(problem["problem_id"], self.repeat, self.ordinal),
            )
            proposals.append(self._request(payload))
        return proposals

    def _request(self, payload):
        for retry in range(3):
            charge_id, reserved = self._reserve(payload)
            self.calls += 1
            started = time.time()
            self._append(
                {
                    "type": "request",
                    "call": self.calls,
                    "ordinal": self.ordinal,
                    "retry": retry,
                    "started_at_unix": started,
                    "reserved_micro_usd": reserved,
                    "payload": payload,
                }
            )
            status = None
            visible = None
            error = None
            try:
                response = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": "Bearer " + self.key,
                        "User-Agent": "CEGVR-research-pilot/1.0",
                    },
                    json=payload,
                    timeout=(10, 90),
                    allow_redirects=False,
                )
                status = response.status_code
                if status == 200 and len(response.content) <= 160000:
                    body = response.json()
                    if isinstance(body, dict):
                        visible = read_visible_response(body)
                        if body.get("error"):
                            error = "provider_error_in_response"
                        elif (
                            visible["model"] != MODEL
                            or visible["provider"] != "CoreWeave"
                        ):
                            error = "provider_identity_mismatch"
                    else:
                        error = "invalid_response_shape"
                else:
                    error = f"http_{status}" if status != 200 else "response_too_large"
            except (
                requests.RequestException,
                ValueError,
                TypeError,
                KeyError,
                IndexError,
                OverflowError,
            ):
                error = "transport_or_json_error"
            elapsed_ms = (time.time() - started) * 1000
            usage = (visible or {}).get("usage", {})
            raw_cost = usage.get("cost")
            known = (
                type(raw_cost) in (int, float)
                and math.isfinite(raw_cost)
                and raw_cost >= 0
            )
            accounted = math.ceil(raw_cost * 1e6) if known else reserved
            self.store.settle(charge_id, accounted if known else None, usage)
            self.accounted_micro_usd += accounted
            self.uncertain_calls += int(not known)
            if known:
                self.provider_reported_cost_usd += raw_cost
                self.known_cost_calls += 1
            self.transport_errors += int(error is not None)
            self._append(
                {
                    "type": "response",
                    "call": self.calls,
                    "ordinal": self.ordinal,
                    "retry": retry,
                    "elapsed_ms": elapsed_ms,
                    "http_status": status,
                    "error": error,
                    "response": visible,
                    "accounted_micro_usd": accounted,
                    "cost_known": known,
                }
            )
            if accounted > reserved:
                raise StudyStopped("provider_cost_exceeded_reservation")
            if error == "provider_identity_mismatch":
                raise StudyStopped("provider_identity_mismatch")
            if status in (401, 402, 403):
                raise StudyStopped("provider_access_error")
            if status in (400, 404, 405, 413, 415, 422):
                raise StudyStopped("provider_request_rejected")
            if status == 429 and retry < 2:
                time.sleep(2 ** (retry + 1))
                continue
            if visible is None:
                return CandidateProposal(None, None, None, elapsed_ms)
            # read_visible_response has removed all hidden reasoning, preventing
            # the legacy parser's reasoning_content fallback from being used.
            return self._parse_response(visible, elapsed_ms)
        raise AssertionError("unreachable retry state")
