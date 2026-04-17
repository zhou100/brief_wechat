"""update audio table

Revision ID: 52812e8c744e
Revises: 65a8ae71f0d5
Create Date: 2025-01-26 20:15:31.123456

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '52812e8c744e'
down_revision: Union[str, None] = '65a8ae71f0d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to audio table
    op.add_column('audio', sa.Column('filename', sa.String(), nullable=False, server_default='default.mp3'))
    op.add_column('audio', sa.Column('content_type', sa.String(), nullable=False, server_default='audio/mpeg'))
    op.add_column('audio', sa.Column('file_path', sa.String(), nullable=False, server_default='/tmp/default.mp3'))
    
    # Remove server_default after adding columns
    op.alter_column('audio', 'filename', server_default=None)
    op.alter_column('audio', 'content_type', server_default=None)
    op.alter_column('audio', 'file_path', server_default=None)


def downgrade() -> None:
    # Drop the new columns
    op.drop_column('audio', 'filename')
    op.drop_column('audio', 'content_type')
    op.drop_column('audio', 'file_path')
