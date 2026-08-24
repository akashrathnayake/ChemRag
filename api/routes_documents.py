import os
import uuid
from typing import List

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Document, Chunk
from rag.config import settings
from rag.ingestion import ingest_uploaded_files, SUPPORTED_EXTENSIONS
from api.schemas import UploadResponse, DocumentOut, FileUploadResult

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _to_document_out(db: Session, d: Document) -> DocumentOut:
    count = db.execute(select(func.count()).select_from(Chunk).where(Chunk.document_id == d.id)).scalar()
    return DocumentOut(
        id=d.id, title=d.title, source_type=d.source_type,
        created_at=d.created_at, chunk_count=count,
        content_hash_prefix=(d.content_hash or "")[:12],
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_documents(files: List[UploadFile] = File(...), db: Session = Depends(get_db)):
    if not files:
        raise HTTPException(400, "No files uploaded.")
    if len(files) > settings.MAX_UPLOAD_FILES:
        raise HTTPException(400, f"Upload at most {settings.MAX_UPLOAD_FILES} files at a time.")

    file_results: List[FileUploadResult] = []
    to_ingest = []  # (title, dest_path) for files that passed the extension check

    for f in files:
        ext = os.path.splitext(f.filename.lower())[1]
        if ext not in SUPPORTED_EXTENSIONS:
            file_results.append(FileUploadResult(
                title=f.filename, status="failed",
                error=f"Unsupported file type '{ext}'. Supported: PDF, TXT, Markdown.",
            ))
            continue
        try:
            safe_name = f"{uuid.uuid4().hex}_{os.path.basename(f.filename)}"
            dest_path = os.path.join(settings.UPLOAD_DIR, safe_name)
            content = await f.read()
            with open(dest_path, "wb") as out:
                out.write(content)
            to_ingest.append((f.filename, dest_path))
        except Exception as e:
            file_results.append(FileUploadResult(title=f.filename, status="failed", error=f"Could not save file: {e}"))

    # Each file in to_ingest is processed independently inside
    # ingest_uploaded_files — one corrupt/unreadable file does not abort
    # the rest of the batch.
    ingest_results = ingest_uploaded_files(db, to_ingest) if to_ingest else []

    documents_out = []
    ingested_count = 0
    duplicate_count = 0
    failed_count = len([r for r in file_results if r.status == "failed"])

    for r in ingest_results:
        if r["status"] == "failed":
            failed_count += 1
            file_results.append(FileUploadResult(title=r["title"], status="failed", error=r["error"]))
            continue

        document = r["document"]
        doc_out = _to_document_out(db, document)
        documents_out.append(doc_out)
        if r["status"] == "duplicate":
            duplicate_count += 1
        else:
            ingested_count += 1
        file_results.append(FileUploadResult(
            title=r["title"], status=r["status"],
            document_id=document.id, chunk_count=doc_out.chunk_count,
        ))

    parts = [f"{ingested_count} ingested"]
    if duplicate_count:
        parts.append(f"{duplicate_count} duplicate (skipped)")
    if failed_count:
        parts.append(f"{failed_count} failed")
    message = ", ".join(parts) + "."

    return UploadResponse(documents=documents_out, file_results=file_results, message=message)


@router.get("", response_model=List[DocumentOut])
def list_documents(db: Session = Depends(get_db)):
    docs = db.execute(select(Document).order_by(Document.created_at.desc())).scalars().all()
    return [_to_document_out(db, d) for d in docs]


@router.delete("/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Document not found.")
    if doc.file_path and os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except OSError:
            pass
    db.delete(doc)
    db.commit()
    return {"message": "Deleted."}
