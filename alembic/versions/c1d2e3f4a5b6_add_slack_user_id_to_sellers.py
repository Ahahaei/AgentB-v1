"""add slack_user_id to sellers

Revision ID: c1d2e3f4a5b6
Revises: a7ab668a9cfc
Create Date: 2026-05-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'a7ab668a9cfc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sellers', sa.Column('slack_user_id', sa.String(), nullable=True))
    op.create_index('ix_sellers_slack_user_id', 'sellers', ['slack_user_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_sellers_slack_user_id', table_name='sellers')
    op.drop_column('sellers', 'slack_user_id')
