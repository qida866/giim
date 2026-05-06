"""数据库基类模块，定义 Declarative Base 与通用主键混入。"""

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """ORM 基类。"""


class IDMixin:
    """通用整型主键混入。"""

    id: Mapped[int] = mapped_column(primary_key=True)
