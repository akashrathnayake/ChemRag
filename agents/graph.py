"""
LangGraph pipeline wiring the whole request lifecycle together:

  validate -> retrieve -> generate -> verify -> respond

Follow-up handling ("explain more") happens inside `retrieve`: if the rules
module detects a follow-up and there is prior history, the question is
rewritten into a standalone search query using the previous Q/A before
hitting the retriever.
"""
from langgraph.graph import StateGraph, END

from agents.state import GraphState
from agents import rules
from agents.calculator import resolve_calculations
from rag.retrieval import retrieve, above_confidence_threshold, confidence_label
from rag.generation import generate_answer, rewrite_followup


def node_validate(state: GraphState) -> GraphState:
    question = (state.get("question") or "").strip()
    if not question:
        state["error"] = "Question must not be empty."
    state["history"] = state.get("history") or []
    return state


def node_retrieve(state: GraphState) -> GraphState:
    if state.get("error"):
        return state

    question = state["question"]
    history = state["history"]
    is_followup = rules.is_followup_question(question, has_history=bool(history))
    state["is_followup"] = is_followup

    search_query = question
    if is_followup:
        prev = history[-1]
        search_query = rewrite_followup(prev["question"], prev["answer"], question)

    state["search_query"] = search_query

    from db.database import SessionLocal
    db = SessionLocal()
    try:
        chunks = retrieve(db, search_query)
    finally:
        db.close()

    # Security filter (BR-06): exclude any chunk whose text looks like it's
    # trying to inject instructions rather than just being document content.
    # This runs on the retrieved chunks BEFORE they're ever placed into the
    # generation prompt, not as an after-the-fact check on the LLM's output.
    safe_chunks = [c for c in chunks if not rules.contains_injection_attempt(c.text)]
    flagged_count = len(chunks) - len(safe_chunks)
    state["retrieved"] = safe_chunks
    state["has_sufficient_context"] = above_confidence_threshold(safe_chunks)
    state["injection_flagged_count"] = flagged_count
    return state


def node_generate(state: GraphState) -> GraphState:
    if state.get("error"):
        return state

    chunks = state["retrieved"]
    top_score = round(chunks[0].fused_score, 4) if chunks else 0.0

    if not state["has_sufficient_context"]:
        state["answer"] = "I cannot confirm this from the available documents."
        state["citations"] = []
        state["confidence"] = top_score
        state["confidence_label"] = confidence_label(top_score)
        return state

    answer = generate_answer(state["search_query"], chunks, state["history"])
    state["answer"] = answer

    citations = []
    for i, c in enumerate(chunks, start=1):
        citations.append({
            "source_number": i,
            "document_id": c.document_id,
            "document_title": c.document_title,
            "page": c.page,
            "chunk_index": c.chunk_index,
            "text_preview": (c.text[:280] + "...") if len(c.text) > 280 else c.text,
            "similarity": round(c.fused_score, 4),
        })
    state["citations"] = citations
    state["confidence"] = top_score
    state["confidence_label"] = confidence_label(top_score)
    return state


def node_calculate(state: GraphState) -> GraphState:
    """Tool-use step: replaces any CALC[ expression ] blocks the model
    emitted with a deterministically computed, sympy-verified result,
    rather than trusting the model's own arithmetic."""
    if state.get("error"):
        return state

    answer = state.get("answer", "")
    new_answer, calc_results = resolve_calculations(answer)
    state["answer"] = new_answer
    state["calculations"] = [
        {
            "expression": c.expression,
            "result": c.result,
            "verified": c.verified,
            "error": c.error,
        }
        for c in calc_results
    ]
    return state


def node_verify(state: GraphState) -> GraphState:
    if state.get("error"):
        return state

    result = rules.check_answer(state["answer"], num_sources=len(state.get("citations", [])))
    state["rule_check"] = {
        "passed": result.passed,
        "reason": result.reason,
        "has_citations": result.has_citations,
        "citation_numbers": result.citation_numbers,
    }

    if rules.claims_no_answer(state["answer"]):
        state["supported"] = "unsupported"
    elif result.passed:
        state["supported"] = "supported"
    else:
        # Rules failed -> don't show an ungrounded answer, degrade safely.
        state["answer"] = (
            "I cannot confirm this from the available documents "
            "(the generated answer did not include valid citations)."
        )
        state["citations"] = []
        state["supported"] = "unsupported"

    return state


def node_respond(state: GraphState) -> GraphState:
    # Terminal formatting node — kept separate so the API layer only ever
    # reads from `state` after the graph fully completes.
    return state


def build_graph():
    graph = StateGraph(GraphState)
    graph.add_node("validate", node_validate)
    graph.add_node("retrieve", node_retrieve)
    graph.add_node("generate", node_generate)
    graph.add_node("calculate", node_calculate)
    graph.add_node("verify", node_verify)
    graph.add_node("respond", node_respond)

    graph.set_entry_point("validate")
    graph.add_edge("validate", "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "calculate")
    graph.add_edge("calculate", "verify")
    graph.add_edge("verify", "respond")
    graph.add_edge("respond", END)

    return graph.compile()


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def run_pipeline(question: str, history: list, session_id: str = "default") -> GraphState:
    graph = get_graph()
    initial_state: GraphState = {
        "session_id": session_id,
        "question": question,
        "history": history,
    }
    return graph.invoke(initial_state)
