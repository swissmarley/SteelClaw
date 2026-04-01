"""Add session status, connector_type, token tracking, agents, user_facts, memory_entries.

Revision ID: 001
Revises: None
Create Date: 2026-03-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Session table additions ──────────────────────────────────────────
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(sa.Column("status", sa.String(), server_default="active", nullable=False))
        batch_op.add_column(sa.Column("connector_type", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("last_activity_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("agent_id", sa.String(), nullable=True))
        batch_op.create_index("ix_sessions_status", ["status"])

    # Populate last_activity_at from updated_at
    op.execute("UPDATE sessions SET last_activity_at = updated_at WHERE last_activity_at IS NULL")
    # Populate status from is_active
    op.execute("UPDATE sessions SET status = CASE WHEN is_active = 1 THEN 'active' ELSE 'closed' END")
    # Populate connector_type from platform
    op.execute("UPDATE sessions SET connector_type = platform WHERE connector_type IS NULL")

    # ── Message table additions ──────────────────────────────────────────
    with op.batch_alter_table("messages") as batch_op:
        batch_op.add_column(sa.Column("model", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("token_usage_prompt", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("token_usage_completion", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("cost_usd", sa.Float(), nullable=True))

    # ── AgentProfile table ───────────────────────────────────────────────
    op.create_table(
        "agents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), server_default=""),
        sa.Column("is_main", sa.Boolean(), server_default="0"),
        sa.Column("system_prompt", sa.String(), server_default=""),
        sa.Column("persona_json", sa.String(), nullable=True),
        sa.Column("model_override", sa.String(), nullable=True),
        sa.Column("temperature_override", sa.Float(), nullable=True),
        sa.Column("memory_namespace", sa.String(), server_default=""),
        sa.Column("is_active", sa.Boolean(), server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_agents_name", "agents", ["name"], unique=True)

    # ── UserFact table ───────────────────────────────────────────────────
    op.create_table(
        "user_facts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("fact_key", sa.String(), server_default=""),
        sa.Column("fact_value", sa.String(), server_default=""),
        sa.Column("source", sa.String(), server_default="conversation"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_user_facts_user_id", "user_facts", ["user_id"])

    # ── MemoryEntry table ────────────────────────────────────────────────
    op.create_table(
        "memory_entries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id"), nullable=True),
        sa.Column("agent_id", sa.String(), sa.ForeignKey("agents.id"), nullable=True),
        sa.Column("content_hash", sa.String(), server_default=""),
        sa.Column("content_preview", sa.String(), server_default=""),
        sa.Column("source_type", sa.String(), server_default="message"),
        sa.Column("metadata_json", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_memory_entries_content_hash", "memory_entries", ["content_hash"])


def downgrade() -> None:
    op.drop_table("memory_entries")
    op.drop_table("user_facts")
    op.drop_table("agents")

    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_column("cost_usd")
        batch_op.drop_column("token_usage_completion")
        batch_op.drop_column("token_usage_prompt")
        batch_op.drop_column("model")

    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_index("ix_sessions_status")
        batch_op.drop_column("agent_id")
        batch_op.drop_column("last_activity_at")
        batch_op.drop_column("connector_type")
        batch_op.drop_column("status")
