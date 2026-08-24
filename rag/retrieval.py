"""
Hybrid retriever: combines pgvector cosine similarity ("search by meaning")
with a simple keyword overlap score ("search by keywords"), then returns a
fused, re-ranked top-K list of chunks with their source document.

Kept as plain SQL/SQLAlchemy (not LlamaIndex's VectorStoreIndex) so the
result rows map 1:1 onto our own Document/Chunk schema and citation format.
"""
import re
from dataclasses import dataclass, field
from typing import List

from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

from db.models import Chunk, Document
from rag.config import settings
from rag.embeddings import embed_text

_WORD_RE = re.compile(r"[a-zA-Z0-9]+")


def _keywords(text: str) -> List[str]:
    return [w.lower() for w in _WORD_RE.findall(text) if len(w) > 2]


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    document_title: str
    text: str
    page: int | None
    chunk_index: int
    similarity: float
    keyword_score: float
    fused_score: float = field(default=0.0)


def retrieve(db: Session, query: str, top_k: int = None) -> List[RetrievedChunk]:
    top_k = top_k or settings.TOP_K

    # ---- 1. Meaning search (pgvector cosine distance, smaller = closer) ----
    query_vector = embed_text(query, task_type="retrieval_query")
    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")

    vector_rows = db.execute(
        select(Chunk, Document.title, distance)
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.embedding.is_not(None))
        .order_by(distance)
        .limit(max(top_k * 4, 20))
    ).all()

    # ---- 2. Keyword search (ILIKE over extracted query keywords) ----
    kw_terms = _keywords(query)
    keyword_rows = []
    if kw_terms:
        conditions = [Chunk.text.ilike(f"%{term}%") for term in kw_terms]
        keyword_rows = db.execute(
            select(Chunk, Document.title)
            .join(Document, Chunk.document_id == Document.id)
            .where(or_(*conditions))
            .limit(max(top_k * 4, 20))
        ).all()

    # ---- 3. Fuse ----
    pool: dict[str, RetrievedChunk] = {}

    for chunk, title, dist in vector_rows:
        similarity = max(0.0, 1.0 - float(dist))  # cosine distance -> similarity
        pool[chunk.id] = RetrievedChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            document_title=title,
            text=chunk.text,
            page=chunk.page,
            chunk_index=chunk.chunk_index,
            similarity=similarity,
            keyword_score=0.0,
        )

    for chunk, title in keyword_rows:
        text_lower = chunk.text.lower()
        hits = sum(1 for term in kw_terms if term in text_lower)
        kw_score = hits / max(len(kw_terms), 1)
        if chunk.id in pool:
            pool[chunk.id].keyword_score = kw_score
        else:
            pool[chunk.id] = RetrievedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_title=title,
                text=chunk.text,
                page=chunk.page,
                chunk_index=chunk.chunk_index,
                similarity=0.0,
                keyword_score=kw_score,
            )

    # weighted fusion: meaning matters more than raw keyword overlap
    ALPHA, BETA = 0.75, 0.25
    for rc in pool.values():
        rc.fused_score = ALPHA * rc.similarity + BETA * rc.keyword_score

    ranked = sorted(pool.values(), key=lambda r: r.fused_score, reverse=True)
    return ranked[:top_k]


def above_confidence_threshold(chunks: List[RetrievedChunk]) -> bool:
    """Used by the verifier: if even the best chunk is a weak match, the
    assistant should say it cannot confirm rather than answer."""
    if not chunks:
        return False
    return chunks[0].fused_score >= settings.MIN_SIMILARITY


def confidence_label(score: float) -> str:
    """Buckets a fused retrieval score into a human-readable confidence
    label shown alongside every answer (distinct from per-citation match
    %, this is a single overall signal for the answer as a whole)."""
    if score >= 0.8:
        return "High"
    if score >= settings.MIN_SIMILARITY:
        return "Medium"
    return "Low"
