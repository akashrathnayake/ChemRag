from rag.retrieval import RetrievedChunk, above_confidence_threshold, confidence_label, _keywords


def _chunk(score):
    return RetrievedChunk(
        chunk_id="c1", document_id="d1", document_title="Leave Policy",
        text="Employees get 21 days of annual leave.", page=1, chunk_index=0,
        similarity=score, keyword_score=0.0, fused_score=score,
    )


def test_above_confidence_threshold_true():
    assert above_confidence_threshold([_chunk(0.8)]) is True


def test_above_confidence_threshold_false_for_weak_match():
    assert above_confidence_threshold([_chunk(0.1)]) is False


def test_above_confidence_threshold_false_for_empty_list():
    assert above_confidence_threshold([]) is False


def test_keyword_extraction_filters_short_words():
    words = _keywords("How do I request sick leave for a day?")
    assert "sick" in words
    assert "leave" in words
    # very short tokens (<=2 chars) like "do", "a" are filtered out
    assert "do" not in words
    assert "a" not in words


def test_confidence_label_buckets():
    assert confidence_label(0.9) == "High"
    assert confidence_label(0.6) == "Medium"
    assert confidence_label(0.2) == "Low"
