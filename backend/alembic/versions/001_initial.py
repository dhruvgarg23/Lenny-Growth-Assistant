"""initial — sessions, messages, documents, chunks with pgvector

Revision ID: 001_initial
Revises:
Create Date: 2026-08-24
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VECTOR_DIM = 384

def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False, server_default="New chat"),
        sa.Column("user_id", sa.String(length=64), nullable=False, server_default="demo-user"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("meta", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"])
    op.create_index("ix_messages_session_created", "messages", ["session_id", "created_at"])

    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_path", sa.Text, nullable=False, unique=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("guest", sa.Text, nullable=True),
        sa.Column("doc_type", sa.String(length=16), nullable=False, server_default="podcast"),
        sa.Column("word_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "chunks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", sa.TEXT, nullable=True),  # placeholder, replaced below
        sa.Column("tsv", postgresql.TSVECTOR, nullable=True),
        sa.Column("token_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("model", sa.String(length=128), nullable=False, server_default="sentence-transformers/all-MiniLM-L6-v2"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    # Replace TEXT embedding with vector(dim)
    op.execute(f"ALTER TABLE chunks ALTER COLUMN embedding TYPE vector({VECTOR_DIM}) USING embedding::vector")
    # Generated tsv via trigger or stored — we use stored column populated by code + GIN, but allow NULL then fill
    op.execute("""
        CREATE OR REPLACE FUNCTION chunks_tsv_update() RETURNS trigger AS $$
        BEGIN
            NEW.tsv := to_tsvector('english', COALESCE(NEW.content, ''));
            RETURN NEW;
        END; $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_chunks_tsv BEFORE INSERT OR UPDATE OF content ON chunks
        FOR EACH ROW EXECUTE FUNCTION chunks_tsv_update();
    """)
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    op.create_index("ix_chunks_document_ordinal", "chunks", ["document_id", "ordinal"])
    op.execute(f"CREATE INDEX ix_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)")
    op.execute("CREATE INDEX ix_chunks_tsv ON chunks USING gin (tsv)")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_chunks_tsv ON chunks")
    op.execute("DROP FUNCTION IF EXISTS chunks_tsv_update()")
    op.drop_index("ix_chunks_tsv")
    op.drop_index("ix_chunks_embedding_hnsw")
    op.drop_index("ix_chunks_document_ordinal")
    op.drop_index("ix_chunks_document_id")
    op.drop_table("chunks")
    op.drop_table("documents")
    op.drop_index("ix_messages_session_created")
    op.drop_index("ix_messages_session_id")
    op.drop_table("messages")
    op.drop_index("ix_sessions_user_id")
    op.drop_table("sessions")
