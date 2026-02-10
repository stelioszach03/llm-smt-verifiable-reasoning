"""Deterministic rule-based paraphraser for toy datasets."""

from __future__ import annotations

from typing import Dict

REPLACEMENTS = {
    "at least": ["no less than", ">="],
    "at most": ["no more than", "<="],
    "equal": ["identical", "same"],
    "sum": ["total", "aggregate"],
    "difference": ["gap", "delta"],
}


def paraphrase_statement(text: str) -> str:
    """Apply simple synonym replacements to produce a deterministic paraphrase."""

    result = text
    for key, variants in REPLACEMENTS.items():
        if not variants:
            continue
        index = sum(ord(char) for char in (text + key)) % len(variants)
        replacement = variants[index]
        result = result.replace(key, replacement)
    return result


def paraphrase_problem(problem: Dict) -> Dict:
    """Paraphrase textual fields in a problem specification."""

    rewritten = dict(problem)
    if "description" in rewritten and isinstance(rewritten["description"], str):
        rewritten["description"] = paraphrase_statement(rewritten["description"])
    if "assumptions" in rewritten and isinstance(rewritten["assumptions"], list):
        rewritten["assumptions"] = [
            paraphrase_statement(str(item)) for item in rewritten["assumptions"]
        ]
    return rewritten


__all__ = ["paraphrase_statement", "paraphrase_problem"]
