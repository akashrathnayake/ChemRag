"""
Deterministic calculator tool.

The generation prompt (rag/prompts.py) instructs Gemini to wrap any
arithmetic it needs to perform inside CALC[ ... ] blocks — e.g.
CALC[ -2.179e-18 / 3^2 ] — instead of computing the result itself in
free text. This module extracts every such block, evaluates it with
sympy (real, verified computation, not an LLM guess), and substitutes
the block with the correct result — so the final numeric value shown
to the user is always code-verified.

This is intentionally NOT `eval()` — expressions are restricted to a
safe character set and a small allow-list of math functions/constants
before being parsed by sympy, so arbitrary code execution isn't possible
even if the LLM (or a malicious document) tries to smuggle something
through a CALC[] block.
"""
import re
from dataclasses import dataclass
from typing import List, Tuple

import sympy
from sympy.parsing.sympy_parser import (
    parse_expr, standard_transformations, implicit_multiplication_application,
)

CALC_PATTERN = re.compile(r"CALC\[(.*?)\]", re.DOTALL)

# Only these characters may appear in an expression at all — rejects
# anything that looks like it's trying to reference Python internals,
# imports, attribute access, etc. before it's even parsed.
_SAFE_EXPR_RE = re.compile(r"^[0-9a-zA-Z.\+\-\*/\^(),\s_]+$")

_ALLOWED_NAMES = {
    "sqrt": sympy.sqrt, "log": sympy.log, "ln": sympy.log, "exp": sympy.exp,
    "sin": sympy.sin, "cos": sympy.cos, "tan": sympy.tan,
    "pi": sympy.pi, "e": sympy.E, "abs": sympy.Abs,
}

_TRANSFORMATIONS = standard_transformations + (implicit_multiplication_application,)


@dataclass
class CalculationResult:
    expression: str
    result: str            # formatted for display, e.g. "-2.421e-19"
    verified: bool          # True if evaluation succeeded
    error: str = ""


def _format_number(value) -> str:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if f == 0:
        return "0"
    if 1e-4 <= abs(f) < 1e6:
        return f"{f:.6g}"
    return f"{f:.6e}"


def evaluate_expression(expr: str) -> CalculationResult:
    expr = expr.strip().replace("^", "**")
    if not expr:
        return CalculationResult(expression=expr, result="", verified=False, error="Empty expression.")
    if not _SAFE_EXPR_RE.match(expr.replace("**", "^")):
        return CalculationResult(expression=expr, result="", verified=False, error="Unsupported characters in expression.")
    try:
        parsed = parse_expr(expr, local_dict=_ALLOWED_NAMES, transformations=_TRANSFORMATIONS, evaluate=True)
        value = sympy.N(parsed, 10)
        return CalculationResult(expression=expr, result=_format_number(value), verified=True)
    except Exception as e:
        return CalculationResult(expression=expr, result="", verified=False, error=str(e))


def resolve_calculations(answer: str) -> Tuple[str, List[CalculationResult]]:
    """Finds every CALC[ ... ] block in `answer`, evaluates it
    deterministically, and returns (answer_with_results_substituted,
    list_of_calculation_results). A verified result is substituted in as
    LaTeX ($result$) so it renders via the existing KaTeX integration; an
    unverifiable expression is left as a visible warning instead of a
    silently wrong number."""
    results: List[CalculationResult] = []

    def _replace(match: "re.Match") -> str:
        expr = match.group(1)
        calc = evaluate_expression(expr)
        results.append(calc)
        if calc.verified:
            return f"${calc.result}$"
        return f"[unable to verify calculation: {expr}]"

    new_answer = CALC_PATTERN.sub(_replace, answer)
    return new_answer, results
