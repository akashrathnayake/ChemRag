from agents.calculator import evaluate_expression, resolve_calculations


def test_simple_division():
    result = evaluate_expression("-2.179e-18 / 9")
    assert result.verified is True
    assert result.result.startswith("-2.42")


def test_exponent_and_sqrt():
    result = evaluate_expression("sqrt(16) + 2^3")
    assert result.verified is True
    assert result.result == "12"


def test_rejects_unsafe_characters():
    result = evaluate_expression("__import__('os').system('echo hi')")
    assert result.verified is False


def test_rejects_attribute_access():
    result = evaluate_expression("().__class__")
    assert result.verified is False


def test_resolve_calculations_substitutes_verified_result():
    answer = "The energy is CALC[ -2.179e-18 / 9 ] joules [1]."
    new_answer, results = resolve_calculations(answer)
    assert "CALC[" not in new_answer
    assert len(results) == 1
    assert results[0].verified is True
    assert "$" in new_answer  # substituted as LaTeX for KaTeX rendering


def test_resolve_calculations_flags_unverifiable_expression():
    answer = "The result is CALC[ import os ]."
    new_answer, results = resolve_calculations(answer)
    assert "unable to verify" in new_answer
    assert results[0].verified is False


def test_resolve_calculations_handles_no_calc_blocks():
    answer = "This answer has no calculations in it [1]."
    new_answer, results = resolve_calculations(answer)
    assert new_answer == answer
    assert results == []
