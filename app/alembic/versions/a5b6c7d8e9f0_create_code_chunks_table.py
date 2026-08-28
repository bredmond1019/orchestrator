"""create_code_chunks_table

Adds the `code_chunks` table backing the new "code" corpus (block OR.P):
function/class/method-boundary chunks of source files, embedded and
retrievable through the existing `_CORPUS_CONFIG` retrieval machinery. Mirrors
`brain_documents`' column shape (see migration b3c4d5e6f7a8 and
e2f3a4b5c6d7): a pgvector embedding column, a generated weighted `content_tsv`
column, a GIN index over it, and an HNSW ANN index over the embedding.

Revision ID: a5b6c7d8e9f0
Revises: c1d2e3f4a5b6
Create Date: 2026-08-27

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "a5b6c7d8e9f0"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "code_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("repo", sa.String(length=128), nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("symbol_name", sa.String(length=256), nullable=True),
        sa.Column("symbol_kind", sa.String(length=32), nullable=True),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
        sa.Column("section", sa.String(length=256), nullable=False),
        sa.Column("indexed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "repo", "file_path", "start_line", name="uq_code_chunks_repo_file_path_start_line"
        ),
    )
    op.create_index("ix_code_chunks_repo", "code_chunks", ["repo"])
    op.create_index("ix_code_chunks_file_path", "code_chunks", ["file_path"])
    op.create_index("ix_code_chunks_language", "code_chunks", ["language"])

    # Full-text search: generated tsvector column, mirroring brain_documents'
    # (migration e2f3a4b5c6d7). setweight gives symbol_name ('A') > file_path
    # ('B') > content ('C') — a code search is far more often a symbol-name
    # search than a prose search.
    #
    # Implementation notes (same as brain_documents):
    # - to_tsvector() must use '::regconfig' cast — the text-arg form is STABLE
    #   (not IMMUTABLE), which Postgres rejects for generated columns.
    # - Postgres maintains this column automatically; the indexer must NEVER write it.
    op.execute("""
        ALTER TABLE code_chunks
        ADD COLUMN content_tsv tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english'::regconfig, coalesce(symbol_name, '')), 'A') ||
            setweight(to_tsvector('english'::regconfig, coalesce(file_path, '')),    'B') ||
            setweight(to_tsvector('english'::regconfig, coalesce(content, '')),      'C')
        ) STORED
    """)
    op.create_index(
        "ix_code_chunks_content_tsv",
        "code_chunks",
        ["content_tsv"],
        postgresql_using="gin",
    )

    # HNSW ANN index on embedding (cosine ops), mirroring brain_documents.
    op.execute("""
        CREATE INDEX ix_code_chunks_embedding_hnsw
        ON code_chunks USING hnsw (embedding vector_cosine_ops)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_code_chunks_embedding_hnsw")
    op.drop_index("ix_code_chunks_content_tsv", table_name="code_chunks")
    op.execute("ALTER TABLE code_chunks DROP COLUMN IF EXISTS content_tsv")
    op.drop_index("ix_code_chunks_language", table_name="code_chunks")
    op.drop_index("ix_code_chunks_file_path", table_name="code_chunks")
    op.drop_index("ix_code_chunks_repo", table_name="code_chunks")
    op.drop_table("code_chunks")
