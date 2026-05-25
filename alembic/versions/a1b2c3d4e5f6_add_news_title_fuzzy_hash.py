"""add news title_fuzzy_hash"""

revision = "a1b2c3d4e5f6"
down_revision = "c077e7dba698"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column(
        "news",
        sa.Column("title_fuzzy_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_news_source_title_fuzzy",
        "news",
        ["source_name", "title_fuzzy_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_news_source_title_fuzzy", table_name="news")
    op.drop_column("news", "title_fuzzy_hash")
