"""Gemini text generation calls used for answering and follow-up rewriting."""
from typing import List

import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential

from rag.config import settings
from rag.prompts import SYSTEM_INSTRUCTIONS, ANSWER_PROMPT_TEMPLATE, FOLLOWUP_REWRITE_PROMPT
from rag.retrieval import RetrievedChunk

genai.configure(api_key=settings.GEMINI_API_KEY)
_gen_model = genai.GenerativeModel(settings.GEMINI_GEN_MODEL)


def format_context(chunks: List[RetrievedChunk]) -> str:
    parts = []
    for i, c in enumerate(chunks, start=1):
        location = f", page {c.page}" if c.page else f", chunk {c.chunk_index}"
        parts.append(f"[{i}] ({c.document_title}{location}):\n{c.text}")
    return "\n\n".join(parts) if parts else "(no relevant context found)"


def format_history(history: List[dict]) -> str:
    if not history:
        return "(none)"
    lines = []
    for turn in history[-3:]:
        lines.append(f"Q: {turn['question']}\nA: {turn['answer']}")
    return "\n\n".join(lines)


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=30))
def generate_answer(question: str, chunks: List[RetrievedChunk], history: List[dict]) -> str:
    if not chunks:
        return "I cannot confirm this from the available documents."

    prompt = ANSWER_PROMPT_TEMPLATE.format(
        system=SYSTEM_INSTRUCTIONS,
        history=format_history(history),
        context=format_context(chunks),
        question=question,
    )
    response = _gen_model.generate_content(prompt)
    return (response.text or "").strip()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def rewrite_followup(prev_question: str, prev_answer: str, followup: str) -> str:
    prompt = FOLLOWUP_REWRITE_PROMPT.format(
        prev_question=prev_question, prev_answer=prev_answer, followup=followup
    )
    response = _gen_model.generate_content(prompt)
    rewritten = (response.text or "").strip()
    return rewritten or followup
