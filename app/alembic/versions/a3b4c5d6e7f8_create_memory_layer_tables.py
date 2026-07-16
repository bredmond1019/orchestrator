"""create_memory_layer_tables

Creates the block-OR.S entity/memory layer tables: ``peers`` (the multi-peer
entity anchor — clients, companies, products, SOPs, the user), and its two
child tables ``agent_episodes`` (fast ingest-time episodic records) and
``semantic_memories`` (durable, dream-time-consolidated facts).

Revision ID: a3b4c5d6e7f8
Revises: b7a03fc80996
Create Date: 2026-07-16 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "b7a03fc80996"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "peers",
        sa.Column("peer_id", sa.String(length=256), primary_key=True, nullable=False),
        sa.Column("peer_type", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", sa.String(length=256), nullable=False),
        sa.Column("representation", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_peers_workspace_id_peer_type",
        "peers",
        ["workspace_id", "peer_type"],
        unique=False,
    )

    op.create_table(
        "agent_episodes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "peer_id",
            sa.String(length=256),
            sa.ForeignKey("peers.peer_id"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(length=256), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("outcome", sa.String(length=64), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_agent_episodes_peer_id", "agent_episodes", ["peer_id"], unique=False
    )

    op.create_table(
        "semantic_memories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "peer_id",
            sa.String(length=256),
            sa.ForeignKey("peers.peer_id"),
            nullable=False,
        ),
        sa.Column("fact", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence_episode_ids", sa.JSON(), nullable=True),
        sa.Column("decay_factor", sa.Float(), nullable=False, server_default="0.95"),
        sa.Column(
            "source_peer_id",
            sa.String(length=256),
            sa.ForeignKey("peers.peer_id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("embedding", Vector(1024), nullable=True),
    )
    op.create_index(
        "ix_semantic_memories_peer_id", "semantic_memories", ["peer_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_semantic_memories_peer_id", table_name="semantic_memories")
    op.drop_table("semantic_memories")
    op.drop_index("ix_agent_episodes_peer_id", table_name="agent_episodes")
    op.drop_table("agent_episodes")
    op.drop_index("ix_peers_workspace_id_peer_type", table_name="peers")
    op.drop_table("peers")
