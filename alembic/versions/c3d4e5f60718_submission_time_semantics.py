"""区分聚合站提交时间和原始报道发布时间。"""
from alembic import op

revision = 'c3d4e5f60718'
down_revision = 'b2c3d4e5f607'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE news SET time_quality='submission' WHERE source_name='Hacker News - Frontpage' AND time_quality='verified'")


def downgrade() -> None:
    op.execute("UPDATE news SET time_quality='verified' WHERE source_name='Hacker News - Frontpage' AND time_quality='submission'")
