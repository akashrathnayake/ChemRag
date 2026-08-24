import os
from dotenv import load_dotenv

load_dotenv()  # no-op if .env doesn't exist or vars are already set (e.g. in Docker)


class Settings:
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_EMBED_MODEL: str = os.getenv("GEMINI_EMBED_MODEL", "models/gemini-embedding-001")
    GEMINI_EMBED_DIM: int = int(os.getenv("GEMINI_EMBED_DIM", "768"))
    GEMINI_GEN_MODEL: str = os.getenv("GEMINI_GEN_MODEL", "models/gemini-3.6-flash")
    GEMINI_JUDGE_MODEL: str = os.getenv("GEMINI_JUDGE_MODEL", "models/gemini-3.6-flash")

    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "data/uploaded_docs")
    MAX_UPLOAD_FILES: int = int(os.getenv("MAX_UPLOAD_FILES", "10"))

    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "800"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "120"))

    TOP_K: int = int(os.getenv("TOP_K", "5"))
    MIN_SIMILARITY: float = float(os.getenv("MIN_SIMILARITY", "0.55"))


settings = Settings()
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
