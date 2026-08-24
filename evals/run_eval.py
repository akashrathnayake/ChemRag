"""
Runs every question in evals/benchmark.json through the real RAG pipeline
(agents.graph.run_pipeline), scores each answer with:
  1. the deterministic rules in agents/rules.py (citation validity, etc.)
  2. the Gemini LLM judge (evals/judge.py)
and writes both a evals/results.json file and EvaluationCase rows in the DB.

Run inside the api container:
    python -m evals.run_eval
"""
import json
import os
import time
from datetime import datetime

from google.api_core.exceptions import ResourceExhausted

from agents.graph import run_pipeline
from agents import rules
from evals.judge import judge_answer
from rag.generation import format_context

BENCHMARK_PATH = os.path.join(os.path.dirname(__file__), "benchmark.json")
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "results.json")

# Evaluation fires ~3 Gemini calls per question (query embedding, answer
# generation, judge scoring). Free-tier API keys often have low
# requests-per-minute limits, so a short pause between questions avoids
# bursting past that limit and getting a ResourceExhausted (429) error.
SECONDS_BETWEEN_CASES = float(os.getenv("EVAL_THROTTLE_SECONDS", "3"))


def _retrieval_hit(case: dict, pipeline_result: dict) -> "bool | None":
    """Deterministic retrieval-quality check, independent of the LLM judge:
    if the benchmark case names an expected source document, did that
    document actually appear among the retrieved/cited chunks? Returns
    None for cases with no expected_source (e.g. deliberately unanswerable
    questions), since 'hit' isn't a meaningful concept for those."""
    expected = case.get("expected_source")
    if not expected:
        return None
    citations = pipeline_result.get("citations", [])
    expected_lower = expected.lower()
    return any(expected_lower in c.get("document_title", "").lower() for c in citations)


def _build_context_string(result: dict) -> str:
    chunks = result.get("retrieved", [])
    lines = []
    for i, c in enumerate(chunks, start=1):
        page = f", page {c.page}" if c.page else ""
        lines.append(f"[{i}] ({c.document_title}{page}): {c.text}")
    return "\n\n".join(lines) if lines else "(no context retrieved)"


def run_benchmark(persist_to_db: bool = True) -> list:
    with open(BENCHMARK_PATH) as f:
        cases = json.load(f)

    results = []
    for i, case in enumerate(cases):
        question = case["question"]

        try:
            pipeline_result = run_pipeline(question=question, history=[], session_id="eval")
            answer = pipeline_result.get("answer", "")
            context_str = _build_context_string(pipeline_result)
            num_sources = len(pipeline_result.get("citations", []))
            rule_result = rules.check_answer(answer, num_sources=num_sources)

            try:
                judge_scores = judge_answer(question, context_str, answer)
            except ResourceExhausted as e:
                judge_scores = {"correctness": 0, "relevance": 0, "groundedness": 0,
                                 "explanation": "Judge call hit a Gemini rate limit; scores not available for this case."}
            except Exception as e:
                judge_scores = {"correctness": 0, "relevance": 0, "groundedness": 0, "explanation": f"Judge error: {e}"}

        except ResourceExhausted:
            # Rate limit hit during retrieval/generation itself — record it
            # as a failed case rather than aborting the entire benchmark run.
            answer = "[Skipped: Gemini API rate limit reached during this case.]"
            rule_result = rules.check_answer("", num_sources=0)
            judge_scores = {"correctness": 0, "relevance": 0, "groundedness": 0,
                             "explanation": "Rate limit reached before this case could run."}
            pipeline_result = {"supported": "unknown"}

        record = {
            "question": question,
            "expected_source": case.get("expected_source"),
            "answer": answer,
            "supported": pipeline_result.get("supported", "unknown"),
            "rule_passed": rule_result.passed,
            "rule_reason": rule_result.reason,
            "retrieval_hit": _retrieval_hit(case, pipeline_result),
            "judge_scores": judge_scores,
            "notes": case.get("notes"),
            "evaluated_at": datetime.utcnow().isoformat(),
        }
        results.append(record)

        if persist_to_db:
            _persist(record)

        if i < len(cases) - 1:
            time.sleep(SECONDS_BETWEEN_CASES)

    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)

    return results


def _persist(record: dict):
    from db.database import SessionLocal
    from db.models import EvaluationCase

    db = SessionLocal()
    try:
        db.add(EvaluationCase(
            question=record["question"],
            expected_source=record.get("expected_source"),
            result={
                "answer": record["answer"],
                "supported": record["supported"],
                "rule_passed": record["rule_passed"],
                "rule_reason": record["rule_reason"],
                "retrieval_hit": record["retrieval_hit"],
                "judge_scores": record["judge_scores"],
            },
            notes=record.get("notes"),
        ))
        db.commit()
    finally:
        db.close()


def summarize(results: list) -> dict:
    if not results:
        return {}
    n = len(results)
    rule_pass_rate = sum(1 for r in results if r["rule_passed"]) / n
    avg_correctness = sum(r["judge_scores"].get("correctness", 0) for r in results) / n
    avg_relevance = sum(r["judge_scores"].get("relevance", 0) for r in results) / n
    avg_groundedness = sum(r["judge_scores"].get("groundedness", 0) for r in results) / n

    retrieval_cases = [r for r in results if r["retrieval_hit"] is not None]
    retrieval_hit_rate = (
        sum(1 for r in retrieval_cases if r["retrieval_hit"]) / len(retrieval_cases)
        if retrieval_cases else None
    )

    return {
        "total_cases": n,
        "rule_pass_rate": round(rule_pass_rate, 3),
        "retrieval_hit_rate": round(retrieval_hit_rate, 3) if retrieval_hit_rate is not None else None,
        "avg_correctness_0_2": round(avg_correctness, 3),
        "avg_relevance_0_2": round(avg_relevance, 3),
        "avg_groundedness_0_2": round(avg_groundedness, 3),
    }


if __name__ == "__main__":
    res = run_benchmark()
    summary = summarize(res)
    print(json.dumps(summary, indent=2))
