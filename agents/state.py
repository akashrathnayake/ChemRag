from typing import List, Optional, TypedDict


class Citation(TypedDict):
    source_number: int
    document_id: str
    document_title: str
    page: Optional[int]
    chunk_index: int
    text_preview: str
    similarity: float


class GraphState(TypedDict, total=False):
    session_id: str
    question: str                 # original user message
    search_query: str             # possibly rewritten (follow-up resolved)
    history: List[dict]           # [{question, answer}, ...]
    is_followup: bool

    retrieved: list                # List[RetrievedChunk]
    has_sufficient_context: bool
    injection_flagged_count: int   # chunks excluded as suspected prompt injection

    answer: str
    citations: List[Citation]
    calculations: List[dict]       # [{expression, result, verified, error}, ...]
    confidence: float              # top retrieval fused_score, 0.0-1.0
    confidence_label: str          # "High" | "Medium" | "Low"
    supported: str                 # "supported" | "unsupported"
    rule_check: dict
    error: Optional[str]
