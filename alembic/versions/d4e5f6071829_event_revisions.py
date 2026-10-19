"""追加式事件发布版本。"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='d4e5f6071829'
down_revision='c3d4e5f60718'
branch_labels=None
depends_on=None


def upgrade() -> None:
    op.create_table('event_revisions',sa.Column('id',postgresql.UUID(as_uuid=True),primary_key=True),sa.Column('event_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('events.id',ondelete='CASCADE'),nullable=False),sa.Column('evidence_hash',sa.String(64),nullable=False),sa.Column('recorded_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column('snapshot',postgresql.JSONB,nullable=False),sa.UniqueConstraint('event_id','evidence_hash',name='uq_event_revision_evidence'))
    op.create_index('ix_event_revisions_event_id','event_revisions',['event_id'])


def downgrade() -> None:
    op.drop_table('event_revisions')
