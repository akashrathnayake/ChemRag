from fastapi import APIRouter, HTTPException

from evals.run_eval import run_benchmark, summarize

router = APIRouter(prefix="/api/eval", tags=["evaluation"])


@router.post("/run")
def run_evaluation():
    try:
        results = run_benchmark()
    except Exception as e:
        raise HTTPException(500, f"Evaluation run failed: {e}")
    return {"summary": summarize(results), "results": results}
