from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import ChatMessage
from agents.graph import run_pipeline
from api.schemas import ChatRequest, ChatResponse, CitationOut, CalculationOut, ChatHistoryItem

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _load_history(db: Session, session_id: str, limit: int = 5) -> List[dict]:
    rows = db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    ).scalars().all()
    rows = list(reversed(rows))
    return [{"question": r.question, "answer": r.answer} for r in rows]


@router.post("/ask", response_model=ChatResponse)
def ask(req: ChatRequest, db: Session = Depends(get_db)):
    question = req.question.strip()
    if not question:
        raise HTTPException(400, "Question must not be empty.")

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
