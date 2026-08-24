"""
ORM models.

Note on embeddings: the actual vector used for pgvector similarity search
lives directly on `Chunk.embedding` (indexed, fast to query). The separate
`Embedding` table is an explicit audit/record table (chunk_id, vector,
model_name, created_at) as required by the spec, useful for tracking which
embedding model/version produced a chunk's vector and for re-embedding runs.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Text, Integer, ForeignKey, DateTime, JSON, Float
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from db.database import Base

EMBED_DIM = 768  # gemini-embedding-001, requested at 768 dims via output_dimensionality


def gen_uuid():
    return str(uuid.uuid4())


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    title = Column(String(512), nullable=False)
    source_type = Column(String(50), nullable=False, default="pdf")
    file_path = Column(String(1024), nullable=False)
    content_hash = Column(String(64), unique=True, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    document_id = Column(UUID(as_uuid=False), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    text = Column(Text, nullable=False)
    page = Column(Integer, nullable=True)
    chunk_index = Column(Integer, nullable=False)
    doc_metadata = Column(JSON, default=dict)
    embedding = Column(Vector(EMBED_DIM), nullable=True)

    document = relationship("Document", back_populates="chunks")


class Embedding(Base):
    """Audit record of an embedding generation event for a chunk."""
    __tablename__ = "embeddings"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    chunk_id = Column(UUID(as_uuid=False), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False)
    vector = Column(Vector(EMBED_DIM), nullable=False)
    model_name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    session_id = Column(String(255), nullable=False, default="default")
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    citations = Column(JSON, default=list)
    calculations = Column(JSON, default=list)
    confidence = Column(Float, nullable=True)
    confidence_label = Column(String(20), nullable=True)
    supported = Column(String(20), default="unknown")  # "supported" | "unsupported" | "unknown"
    created_at = Column(DateTime, default=datetime.utcnow)


class EvaluationCase(Base):
    __tablename__ = "evaluation_cases"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    question = Column(Text, nullable=False)
    expected_source = Column(String(512), nullable=True)
    result = Column(JSON, default=dict)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
