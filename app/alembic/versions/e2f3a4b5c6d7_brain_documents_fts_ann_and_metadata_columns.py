"""brain_documents_fts_ann_and_metadata_columns

Adds three metadata columns (is_section_title, title, description), a generated
tsvector column (content_tsv) for graded Postgres full-text search, a GIN index
on that column, and an HNSW ANN index on the embedding column.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-06-26
"""

from alembic import op
import sqlalchemy as sa

revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Metadata columns
    op.add_column(
        "brain_documents",
        sa.Column(
            "is_section_title",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "brain_documents",
        sa.Column("title", sa.String(512), nullable=True),
    )
    op.add_column(
        "brain_documents",
        sa.Column("description", sa.Text(), nullable=True),
    )

    # 2. Full-text search: generated tsvector column.
    #    setweight gives title+keywords ('A') > description ('B') > content ('C').
    #    STORED means Postgres maintains it automatically; never written by the indexer.
    # Generated column for graded full-text search.
    #
    # Implementation notes:
    # - to_tsvector() must use '::regconfig' cast — the text-arg form is STABLE (not
    #   IMMUTABLE), which Postgres rejects for generated columns.
    # - array_to_string() is also STABLE; replaced by array_to_tsvector() which IS
    #   IMMUTABLE. Trade-off: keywords are matched as exact tokens (no stemming), which
    #   is correct for our controlled OKF vocabulary (e.g. 'brain', 'engine').
    # - setweight gives title+keywords ('A') > description ('B') > content ('C') ranking
    #   influence, so a query term in a doc's title outranks the same term in body text.
    # - Postgres maintains this column automatically; the indexer must NEVER write it.
    op.execute("""
        ALTER TABLE brain_documents
        ADD COLUMN content_tsv tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english'::regconfig, coalesce(title, '')),                      'A') ||
            setweight(array_to_tsvector(coalesce(keywords, ARRAY[]::text[])),                       'A') ||
            setweight(to_tsvector('english'::regconfig, coalesce(description, '')),                'B') ||
            setweight(to_tsvector('english'::regconfig, coalesce(content, '')),                    'C')
        ) STORED
    """)
    op.create_index(
        "ix_brain_documents_content_tsv",
        "brain_documents",
        ["content_tsv"],
        postgresql_using="gin",
    )

    # 3. HNSW ANN index on embedding (cosine ops). Removes the sequential scan.
    op.execute("""
        CREATE INDEX ix_brain_documents_embedding_hnsw
        ON brain_documents USING hnsw (embedding vector_cosine_ops)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_brain_documents_embedding_hnsw")
    op.drop_index("ix_brain_documents_content_tsv", table_name="brain_documents")
    op.execute("ALTER TABLE brain_documents DROP COLUMN IF EXISTS content_tsv")
    op.drop_column("brain_documents", "description")
    op.drop_column("brain_documents", "title")
    op.drop_column("brain_documents", "is_section_title")
