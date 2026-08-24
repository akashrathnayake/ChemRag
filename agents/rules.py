"""
Deterministic, non-LLM checks.

These run every single time (cheap, fast, reliable) and are the primary
guardrail. The LLM judge (evals/judge.py) is used only during offline
evaluation, not on the live answer path, so the live path never depends on
an extra LLM call to decide whether to show an answer.
"""
import re
from dataclasses import dataclass
from typing import List

CITATION_PATTERN = re.compile(r"\[(\d+)\]")

# Heuristic patterns that suggest a document chunk is attempting to inject
# instructions rather than just being content. This is not foolproof (no
# regex-based check can be), but it's a real, deterministic first line of
# defense: any retrieved chunk matching these patterns is excluded from the
# context sent to the generator, rather than trusting the LLM to ignore it.
_INJECTION_PATTERNS = [
    r"ignore (all|any|the) (previous|prior|above) instructions",
    r"disregard (all|any|the) (previous|prior|above)",
    r"you are now",
    r"act as (a|an)\b",
    r"system prompt",
    r"reveal your (instructions|prompt|system)",
    r"new instructions?:",
    r"override (your|the) (rules|instructions|guidelines)",
    r"forget (everything|all) (you|above)",
    r"do not (follow|obey) (the|your) (rules|instructions)",
]
_INJECTION_RE = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]


def contains_injection_attempt(text: str) -> bool:
    """Flags retrieved document text that looks like it's trying to inject
    instructions into the model rather than just being content the user
    uploaded. Used to filter chunks out of the generation context before
    they ever reach the LLM (BR-06: unsafe questions/content must be
    handled, not just unsupported ones)."""
    return any(p.search(text) for p in _INJECTION_RE)

UNSUPPORTED_PHRASES = [
    "i cannot confirm this from the available documents",
    "cannot confirm this from the available documents",
    "i don't have enough information",
    "not found in the provided context",
    "no relevant information",
]

FOLLOWUP_PATTERNS = [
    r"^explain more$", r"^more detail", r"^tell me more", r"^why\b",
    r"^what about", r"^continue", r"^go on", r"^elaborate", r"^and\?*$",
    r"^what else", r"^can you expand", r"^more info", r"^clarify",
]
_FOLLOWUP_RE = [re.compile(p, re.IGNORECASE) for p in FOLLOWUP_PATTERNS]


@dataclass
class RuleCheckResult:
    has_citations: bool
    citation_numbers: List[int]
    citations_in_range: bool
    claims_unsupported_phrase: bool
    is_empty_or_trivial: bool
    passed: bool
    reason: str


def is_followup_question(question: str, has_history: bool) -> bool:
    """Very short questions, or ones matching common follow-up phrasing,
    are treated as follow-ups IF there is prior conversation history."""
    if not has_history:
        return False
    q = question.strip().lower()
    if len(q.split()) <= 3:
        return True
    return any(p.match(q) for p in _FOLLOWUP_RE)


def claims_no_answer(answer: str) -> bool:
    a = answer.strip().lower()
    return any(phrase in a for phrase in UNSUPPORTED_PHRASES)


def extract_citation_numbers(answer: str) -> List[int]:
    return [int(n) for n in CITATION_PATTERN.findall(answer)]


def check_answer(answer: str, num_sources: int) -> RuleCheckResult:
    """
    The core deterministic verifier used on every live request:
      - If the model says it cannot confirm -> that's a valid, "passed" state
        (it correctly rejected an unsupported answer).
      - Otherwise, a factual answer MUST contain at least one citation, and
        every citation number must point at an actually-retrieved source.
    """
    answer_stripped = answer.strip()
    is_empty = len(answer_stripped) == 0

    if claims_no_answer(answer_stripped):
        return RuleCheckResult(
            has_citations=False,
            citation_numbers=[],
            citations_in_range=True,
            claims_unsupported_phrase=True,
            is_empty_or_trivial=is_empty,
            passed=True,
            reason="Model correctly declined to answer without support.",
        )

    if is_empty:
        return RuleCheckResult(
            has_citations=False, citation_numbers=[], citations_in_range=False,
            claims_unsupported_phrase=False, is_empty_or_trivial=True,
            passed=False, reason="Empty answer.",
        )

    numbers = extract_citation_numbers(answer_stripped)
    has_citations = len(numbers) > 0
    in_range = has_citations and all(1 <= n <= max(num_sources, 1) for n in numbers)

    if num_sources == 0:
        # No sources were retrieved at all -> any factual-sounding answer
        # without a "cannot confirm" phrase is a rule violation.
        return RuleCheckResult(
            has_citations=has_citations, citation_numbers=numbers,
            citations_in_range=False, claims_unsupported_phrase=False,
            is_empty_or_trivial=False, passed=False,
            reason="Answer given with zero retrieved sources.",
        )

    passed = has_citations and in_range
    reason = (
        "Answer is grounded with valid citations."
        if passed else
        "Answer is missing valid citation markers referencing retrieved sources."
    )

    return RuleCheckResult(
        has_citations=has_citations,
        citation_numbers=numbers,
        citations_in_range=in_range,
        claims_unsupported_phrase=False,
        is_empty_or_trivial=False,
        passed=passed,
        reason=reason,
    )
