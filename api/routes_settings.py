"""
Read-only, non-secret configuration for the "Settings" page (Application
Map requirement: "Store safe configuration notes, not secret keys"). This
endpoint never returns GEMINI_API_KEY or any other credential — only the
model names and tunable parameters that are safe to display.
"""
from fastapi import APIRouter

from rag.config import settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings():
    return {
        "embedding_model": settings.GEMINI_EMBED_MODEL,
        "embedding_dimensions": settings.GEMINI_EMBED_DIM,
        "generation_model": settings.GEMINI_GEN_MODEL,
        "judge_model": settings.GEMINI_JUDGE_MODEL,
        "chunk_size": settings.CHUNK_SIZE,
        "chunk_overlap": settings.CHUNK_OVERLAP,
        "retrieval_top_k": settings.TOP_K,
        "min_similarity_threshold": settings.MIN_SIMILARITY,
        "max_upload_files": settings.MAX_UPLOAD_FILES,
        "api_key_configured": bool(settings.GEMINI_API_KEY),
    }
