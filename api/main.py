from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from db.database import init_db
from api.routes_documents import router as documents_router
from api.routes_chat import router as chat_router
from api.routes_eval import router as eval_router
from api.routes_settings import router as settings_router

app = FastAPI(
    title="Document RAG Assistant",
    description="RAG-based assistant over a small PDF knowledge base, with citations and evaluation.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(eval_router)
app.include_router(settings_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve the web UI (plain HTML/CSS/JS) at "/"
app.mount("/", StaticFiles(directory="app", html=True), name="ui")
