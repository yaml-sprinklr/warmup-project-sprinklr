"""add_trace_context_to_outbox

Revision ID: a1b2c3d4e5f6
Revises: 895253eb6576
Create Date: 2026-02-07 18:00:00.000000

Learning Notes:
--------------
This migration adds distributed tracing fields to the outbox_events table.

Why these columns?
- trace_id (32 chars): 128-bit W3C Trace Context ID for correlating logs across services
- span_id (16 chars): 64-bit span ID representing the operation that created the event
- parent_span_id (16 chars): 64-bit parent span ID for building trace hierarchies

Why nullable?
- Backwards compatibility: existing outbox events don't have trace context
- Graceful degradation: if trace context is missing, event still gets published

Why index trace_id?
- Enables fast Kibana queries: "find all outbox events for trace_id X"
- Correlate events published hours/days after the original HTTP request
- Join with application logs via trace_id

Migration Strategy:
- Add columns as nullable (no default value needed)
- Create index on trace_id for query performance
- Future events will have trace context, old events remain valid
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '895253eb6576'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add distributed tracing columns to outbox_events table.

    Learning: ALTER TABLE ADD COLUMN in PostgreSQL is a metadata-only operation
    when the column is nullable - it doesn't rewrite the table, making it safe
    for large tables with millions of rows.
    """
    # Add trace_id column (128-bit distributed trace ID)
    op.add_column(
        'outbox_events',
        sa.Column('trace_id', sa.String(length=32), nullable=True)
    )

    # Add span_id column (64-bit span ID)
    op.add_column(
        'outbox_events',
        sa.Column('span_id', sa.String(length=16), nullable=True)
    )

    # Add parent_span_id column (64-bit parent span ID)
    op.add_column(
        'outbox_events',
        sa.Column('parent_span_id', sa.String(length=16), nullable=True)
    )

    # Create index on trace_id for fast lookups
    # Learning: This index enables:
    # - Kibana query: "show me all events for this trace"
    # - Grafana dashboard: "event publishing latency per trace"
    # - Debugging: "did this HTTP request create an outbox event?"
    #
    # Why not unique? Multiple outbox events can share the same trace_id
    # (e.g., creating an order might emit multiple events: order.created,
    # inventory.reserved, notification.queued - all with same trace_id)
    op.create_index(
        op.f('ix_outbox_events_trace_id'),
        'outbox_events',
        ['trace_id'],
        unique=False
    )


def downgrade() -> None:
    """
    Remove distributed tracing columns from outbox_events table.

    Learning: Always write downgrade migrations for production safety.
    If this migration breaks something, you can roll back without data loss.

    Order matters: Drop index BEFORE dropping column (otherwise FK constraint error)
    """
    # Drop index first
    op.drop_index(op.f('ix_outbox_events_trace_id'), table_name='outbox_events')

    # Drop columns (in any order since no foreign keys)
    op.drop_column('outbox_events', 'parent_span_id')
    op.drop_column('outbox_events', 'span_id')
    op.drop_column('outbox_events', 'trace_id')
