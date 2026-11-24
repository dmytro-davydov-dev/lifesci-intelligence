"""Add monotonic sequence to messages for deterministic ordering.

created_at uses now() (transaction start), so messages written in one transaction tie.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
    )
    op.create_index("ix_messages_conversation_seq", "messages", ["conversation_id", "seq"])


def downgrade() -> None:
    op.drop_index("ix_messages_conversation_seq", table_name="messages")
    op.drop_column("messages", "seq")
