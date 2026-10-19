"""Explicit time provenance, generation evidence and operational status."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = 'b2c3d4e5f607'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.alter_column('news','published_at', nullable=True)
    op.add_column('news',sa.Column('time_quality',sa.String(20),nullable=False,server_default='legacy'))
    op.add_column('events',sa.Column('provenance',postgresql.JSONB(),nullable=True))
    op.create_table('operational_states',sa.Column('key',sa.String(120),primary_key=True),sa.Column('value',postgresql.JSONB(),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))

def downgrade() -> None:
    # 未知时间不可伪造为当前时间；需要操作员先处理 NULL 数据才能降级。
    op.drop_table('operational_states')
    op.drop_column('events','provenance')
    op.drop_column('news','time_quality')
    op.alter_column('news','published_at',nullable=False)
