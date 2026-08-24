"""
Ingestion pipeline.

Supports PDF, TXT, and Markdown sources (BR: "Accept PDF, TXT or Markdown
sources"). For PDFs: LlamaIndex's PDFReader gives per-page text, so page
numbers are preserved in citations. For TXT/Markdown: there's no page
concept, so the whole file is treated as one page (page=None) and split
directly into chunks.

Every file's content is hashed (SHA-256) before ingestion. If a document
with the same content hash already exists, ingestion is skipped and the
existing Document is returned instead of creating a duplicate (BR-04:
"The same document should not be ingested repeatedly as duplicates").
"""
import hashlib
import os
from typing import List, Optional, Tuple

from llama_index.core import Document as LIDocument
from llama_index.core.node_parser import SentenceSplitter
from llama_index.readers.file import PDFReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Document, Chunk, Embedding
from rag.config import settings
from rag.embeddings import embed_text

_splitter = SentenceSplitter(
    chunk_size=settings.CHUNK_SIZE,
    chunk_overlap=settings.CHUNK_OVERLAP,
)
_pdf_reader = PDFReader()

TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}
SUPPORTED_EXTENSIONS = {".pdf"} | TEXT_EXTENSIONS


def compute_file_hash(file_path: str) -> str:
    """SHA-256 of the file's raw bytes, used for duplicate detection."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def find_existing_document_by_hash(db: Session, content_hash: str) -> Optional[Document]:
    return db.execute(select(Document).where(Document.content_hash == content_hash)).scalar_one_or_none()


def _load_pdf_pages(file_path: str) -> List[LIDocument]:
    """Returns one LlamaIndex Document per PDF page."""
    return _pdf_reader.load_data(file_path)


def _load_text_pages(file_path: str) -> List[LIDocument]:
    """TXT/Markdown files have no page concept — return a single
    'page' containing the whole file's text."""
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    return [LIDocument(text=text, metadata={"page_label": None})]


def _store_chunks(db: Session, document: Document, pages: List[LIDocument]) -> None:
    chunk_index = 0
    for page in pages:
        page_label = page.metadata.get("page_label") or page.metadata.get("page") or None
        nodes = _splitter.split_text(page.text)
        for node_text in nodes:
            node_text = node_text.strip()
            if not node_text:
                continue

            vector = embed_text(node_text, task_type="retrieval_document")

            chunk = Chunk(
                document_id=document.id,
                text=node_text,
                page=int(page_label) if page_label and str(page_label).isdigit() else None,
                chunk_index=chunk_index,
                doc_metadata={"page_label": page_label},
                embedding=vector,
            )
            db.add(chunk)
            db.flush()

            db.add(Embedding(
                chunk_id=chunk.id,
                vector=vector,
                model_name=settings.GEMINI_EMBED_MODEL,
            ))
            chunk_index += 1


def ingest_file(db: Session, file_path: str, title: str) -> Tuple[Document, bool]:
    """Parse, chunk, embed, and store a single file (PDF, TXT, or Markdown).
    Returns (document, was_duplicate). If was_duplicate is True, `document`
    is the pre-existing row and no new ingestion happened."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}. Supported: {sorted(SUPPORTED_EXTENSIONS)}")

    content_hash = compute_file_hash(file_path)
    existing = find_existing_document_by_hash(db, content_hash)
    if existing is not None:
        return existing, True

    source_type = "pdf" if ext == ".pdf" else "text"
    pages = _load_pdf_pages(file_path) if ext == ".pdf" else _load_text_pages(file_path)

    document = Document(title=title, source_type=source_type, file_path=file_path, content_hash=content_hash)
    db.add(document)
    db.flush()

    _store_chunks(db, document, pages)

    db.commit()
    db.refresh(document)
    return document, False


def ingest_uploaded_files(db: Session, saved_files: List[Tuple[str, str]]) -> List[dict]:
    """saved_files: list of (title, file_path) tuples already written to disk
    by the API layer. Returns a list of per-file result dicts:
    {"title", "file_path", "status": "ingested"|"duplicate"|"failed",
     "document": Document|None, "error": str|None}

    Each file is ingested independently — if one file is corrupt or fails
    to parse, the rest of the batch still proceeds (rather than the whole
    upload failing on one bad file)."""
    results = []
    for title, file_path in saved_files:
        try:
            document, was_duplicate = ingest_file(db, file_path, title)
            results.append({
                "title": title, "file_path": file_path,
                "status": "duplicate" if was_duplicate else "ingested",
                "document": document, "error": None,
            })
        except Exception as e:
            db.rollback()  # clear the failed transaction so later files in this batch still work
            results.append({
                "title": title, "file_path": file_path,
                "status": "failed", "document": None, "error": str(e),
            })
    return results


# Backwards-compatible alias used by earlier code paths / tests.
def ingest_pdf(db: Session, file_path: str, title: str) -> Document:
    document, _ = ingest_file(db, file_path, title)
    return document
