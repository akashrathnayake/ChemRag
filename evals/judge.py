"""
LLM judge: asks Gemini to score a generated answer against the question and
the retrieved context on correctness / relevance / groundedness (0-2 each).

This is used only offline, by evals/run_eval.py — never on the live
request path (agents/rules.py is the live, deterministic guardrail).
"""
import json
import re

import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential

from rag.config import settings
from rag.prompts import JUDGE_PROMPT_TEMPLATE

genai.configure(api_key=settings.GEMINI_API_KEY)
_judge_model = genai.GenerativeModel(settings.GEMINI_JUDGE_MODEL)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=30))
def judge_answer(question: str, context: str, answer: str) -> dict:
    prompt = JUDGE_PROMPT_TEMPLATE.format(question=question, context=context, answer=answer)
    response = _judge_model.generate_content(prompt)
    text = (response.text or "").strip()

    match = _JSON_RE.search(text)
    if not match:
        return {"correctness": 0, "relevance": 0, "groundedness": 0, "explanation": "Judge returned unparseable output."}

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"correctness": 0, "relevance": 0, "groundedness": 0, "explanation": "Judge JSON parse failed."}

    for key in ("correctness", "relevance", "groundedness"):
        data[key] = max(0, min(2, int(data.get(key, 0))))
    data["explanation"] = data.get("explanation", "")
    return data
