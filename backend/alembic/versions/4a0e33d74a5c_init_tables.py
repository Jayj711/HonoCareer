"""initial tables

Revision ID: 4a0e33d74a5c
Revises:
Create Date: 2026-10-23 19:40:59.610348

"""
from typing import Sequence, Union

from alembic import op

from app.db import Base
import app.db.models  # noqa: F401  确保所有模型注册到 Base.metadata


# revision identifiers, used by Alembic.
revision: str = '4a0e33d74a5c'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: 按当前 metadata 一次性建全部表。

    开发期引导迁移，直接复用 metadata.create_all，保证建出的表与 models.py 完全一致，
    避免手写 14 张建表语句出错。后续阶段改结构请用 alembic revision --autogenerate 叠加增量迁移。
    """
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    """Downgrade schema: 删除全部表。"""
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
