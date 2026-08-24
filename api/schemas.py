from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    id: str
    title: str
    source_type: str
    created_at: datetime
    chunk_count: int
    content_hash_prefix: str = ""

    class Config:
        from_attributes = True


class FileUploadResult(BaseModel):
    title: str
    status: str  # "ingested" | "duplicate" | "failed"
    document_id: Optional[str] = None
    chunk_count: Optional[int] = None
    error: Optional[str] = None


class UploadResponse(BaseModel):
    documents: List[DocumentOut]
    file_results: List[FileUploadResult]
    message: str


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(default="default", max_length=255)


class CitationOut(BaseModel):
    source_number: int
    document_id: str
    document_title: str
    page: Optional[int] = None
    chunk_index: int
    text_preview: str
    similarity: float


class CalculationOut(BaseModel):
    expression: str
    result: str
    verified: bool
    error: str = ""


class ChatResponse(BaseModel):
    question: str
    search_query: str
    is_followup: bool
    answer: str
    supported: str
    confidence: float = 0.0
    confidence_label: str = "Low"
    citations: List[CitationOut]
    calculations: List[CalculationOut] = []
    security_flagged_sources: int = 0
    rule_check: dict


class ChatHistoryItem(BaseModel):
    id: str
    question: str
    answer: str
    citations: list
    calculations: list = []
    confidence: Optional[float] = None
    confidence_label: Optional[str] = None
    supported: str
    created_at: datetime

    class Config:
        from_attributes = True


class EvalCaseIn(BaseModel):
    question: str
    expected_source: Optional[str] = None
    notes: Optional[str] = None


class EvalResultOut(BaseModel):
    question: str
    expected_source: Optional[str]
    answer: str
    supported: str
    rule_passed: bool
    judge_scores: Optional[dict] = None
    notes: Optional[str] = None
