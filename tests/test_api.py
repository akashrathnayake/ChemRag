"""
Lightweight smoke tests that don't require Postgres or a Gemini key, so they
run in any environment. Full end-to-end tests (upload -> ask -> citations)
are meant to be run inside the docker-compose stack, e.g.:

    docker compose exec api pytest tests/ -v
"""
from api.schemas import ChatRequest, ChatResponse, CitationOut


def test_chat_request_validates_min_length():
    req = ChatRequest(question="Hi", session_id="s1")
    assert req.question == "Hi"


def test_chat_response_serializes_citations():
    citation = CitationOut(
        source_number=1, document_id="d1", document_title="Leave Policy",
        page=1, chunk_index=0, text_preview="21 days of leave...", similarity=0.87,
    )
    resp = ChatResponse(
        question="How many leave days?",
        search_query="How many leave days?",
        is_followup=False,
        answer="21 days [1].",
        supported="supported",
        citations=[citation],
        rule_check={"passed": True},
    )
    assert resp.citations[0].document_title == "Leave Policy"
    assert resp.supported == "supported"
