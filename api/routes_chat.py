import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import ChatMessage
from agents.graph import run_pipeline
from api.schemas import ChatRequest, ChatResponse, CitationOut, CalculationOut, ChatHistoryItem

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _normalize_question(text: str) -> str:
    """Lowercase, collapse whitespace, strip trailing punctuation — used
    only to compare questions for the cache lookup below. Never stored
    anywhere; the original text is always what gets saved/displayed."""
    text = text.strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = text.rstrip("?!. ")
    return text


def _load_history(db: Session, session_id: str, limit: int = 5) -> List[dict]:
    rows = db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    ).scalars().all()
    rows = list(reversed(rows))
    return [{"question": r.question, "answer": r.answer} for r in rows]


def _find_cached_answer(db: Session, session_id: str, question: str, limit: int = 50) -> Optional[ChatMessage]:
    """Looks for a prior message in THIS session whose question matches
    the new one after normalization. Deliberately scoped to the current
    session only — an identical question asked in a different session
    (possibly with a different knowledge base uploaded) is never reused.

    Known limitation: this does not detect that the knowledge base
    changed since the cached answer was generated. If you upload new
    documents mid-session and re-ask an earlier question expecting a
    different answer, clear the chat or start a new session first.
    """
    normalized_target = _normalize_question(question)
    rows = db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    ).scalars().all()
    for row in rows:
        if _normalize_question(row.question) == normalized_target:
            return row
    return None


@router.post("/ask", response_model=ChatResponse)
def ask(req: ChatRequest, db: Session = Depends(get_db)):
    question = req.question.strip()
    if not question:
        raise HTTPException(400, "Question must not be empty.")

    # Cache check — skip the whole pipeline (no new Gemini calls at all)
    # if this exact question was already answered earlier in this session.
    cached = _find_cached_answer(db, req.session_id, question)
    if cached is not None:
        citations = [CitationOut(**c) for c in (cached.citations or [])]
        calculations = [CalculationOut(**c) for c in (cached.calculations or [])]
        return ChatResponse(
            question=question,
            search_query=question,
            is_followup=False,
            answer=cached.answer,
            supported=cached.supported,
            confidence=cached.confidence or 0.0,
            confidence_label=cached.confidence_label or "Low",
            citations=citations,
            calculations=calculations,
            security_flagged_sources=0,
            rule_check={
                "passed": True,
                "reason": "Served from cache — identical question already answered earlier in this session.",
            },
            from_cache=True,
        )

    history = _load_history(db, req.session_id)

    try:
        result = run_pipeline(question=question, history=history, session_id=req.session_id)
    except Exception as e:
        raise HTTPException(500, f"Pipeline failed: {e}")

    if result.get("error"):
        raise HTTPException(400, result["error"])

    citations = [CitationOut(**c) for c in result.get("citations", [])]
    calculations = [CalculationOut(**c) for c in result.get("calculations", [])]

    chat_row = ChatMessage(
        session_id=req.session_id,
        question=question,
        answer=result["answer"],
        citations=result.get("citations", []),
        calculations=result.get("calculations", []),
        confidence=result.get("confidence", 0.0),
        confidence_label=result.get("confidence_label", "Low"),
        supported=result.get("supported", "unknown"),
    )
    db.add(chat_row)
    db.commit()

    return ChatResponse(
        question=question,
        search_query=result.get("search_query", question),
        is_followup=result.get("is_followup", False),
        answer=result["answer"],
        supported=result.get("supported", "unknown"),
        confidence=result.get("confidence", 0.0),
        confidence_label=result.get("confidence_label", "Low"),
        citations=citations,
        calculations=calculations,
        security_flagged_sources=result.get("injection_flagged_count", 0),
        rule_check=result.get("rule_check", {}),
        from_cache=False,
    )


@router.get("/history", response_model=List[ChatHistoryItem])
def get_history(session_id: str = "default", db: Session = Depends(get_db)):
    rows = db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    ).scalars().all()
    return rows


@router.delete("/history")
def clear_history(session_id: str = "default", db: Session = Depends(get_db)):
    rows = db.execute(select(ChatMessage).where(ChatMessage.session_id == session_id)).scalars().all()
    for r in rows:
        db.delete(r)
    db.commit()
    return {"message": "Cleared."}