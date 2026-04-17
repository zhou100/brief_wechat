"""add custom categories

Revision ID: 65a8ae71f0d5
Revises: 4f29a6261a01
Create Date: 2025-01-26 16:51:23.123456

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '65a8ae71f0d5'
down_revision: Union[str, None] = '4f29a6261a01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add CUSTOM to contentcategory enum in a separate transaction
    connection = op.get_bind()
    connection.execute(text("COMMIT"))  # Close current transaction
    connection.execute(text("ALTER TYPE contentcategory ADD VALUE 'CUSTOM'"))
    connection.execute(text("BEGIN"))  # Start new transaction
    
    # Create custom_categories table
    op.create_table('custom_categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('color', sa.String(length=7), nullable=False),
        sa.Column('icon', sa.String(length=50), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.CheckConstraint("length(name) > 0", name="non_empty_category_name"),
        sa.CheckConstraint("color ~ '^#[0-9a-fA-F]{6}$'", name="valid_hex_color"),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add custom_category_id to categorized_entries
    op.add_column('categorized_entries',
        sa.Column('custom_category_id', sa.Integer(), nullable=True)
    )
    
    # Add foreign key constraint
    op.create_foreign_key(
        'fk_categorized_entries_custom_category',
        'categorized_entries', 'custom_categories',
        ['custom_category_id'], ['id'],
        ondelete='SET NULL'
    )
    
    # Add constraint to ensure custom_category_id is set only when category is CUSTOM
    op.create_check_constraint(
        'valid_custom_category',
        'categorized_entries',
        "(category != 'CUSTOM' AND custom_category_id IS NULL) OR "
        "(category = 'CUSTOM' AND custom_category_id IS NOT NULL)"
    )


def downgrade() -> None:
    # Remove constraints and foreign key first
    op.drop_constraint('valid_custom_category', 'categorized_entries', type_='check')
    op.drop_constraint('fk_categorized_entries_custom_category', 'categorized_entries', type_='foreignkey')
    
    # Remove custom_category_id column
    op.drop_column('categorized_entries', 'custom_category_id')
    
    # Drop custom_categories table
    op.drop_table('custom_categories')
    
    # Cannot remove ENUM value in PostgreSQL, would need to recreate the type
    # This is a limitation we'll have to live with
