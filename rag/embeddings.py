"""
Thin wrapper around the Gemini embedding endpoint.

Kept separate from generation.py so ingestion (rag/ingestion.py) and
retrieval (rag/retrieval.py) can share one embedding path and one
retry policy.
"""
from typing import List

import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential

from rag.config import settings

genai.configure(api_key=settings.GEMINI_API_KEY)


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=1, max=10))
def embed_text(text: str, task_type: str = "retrieval_document") -> List[float]:
    """Embed a single piece of text. task_type is either
    'retrieval_document' (for chunks being indexed) or
    'retrieval_query' (for a user question).

    gemini-embedding-001 returns 3072 dimensions by default; we request
    768 via output_dimensionality to match the pgvector column size
    (db/models.py EMBED_DIM) and keep storage/query cost down."""
    result = genai.embed_content(
        model=settings.GEMINI_EMBED_MODEL,
        content=text,
        task_type=task_type,
        output_dimensionality=settings.GEMINI_EMBED_DIM,
    )
    return result["embedding"]


def embed_batch(texts: List[str], task_type: str = "retrieval_document") -> List[List[float]]:
    return [embed_text(t, task_type=task_type) for t in texts]
