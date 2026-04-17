"""add wechat user fields

Revision ID: o4p5q6r7s8t9
Revises: n3o4p5q6r7s8
Create Date: 2026-04-16 18:10:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "o4p5q6r7s8t9"
down_revision = "n3o4p5q6r7s8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("wechat_openid", sa.String(), nullable=True))
    op.add_column("users", sa.Column("wechat_unionid", sa.String(), nullable=True))
    op.create_index(op.f("ix_users_wechat_openid"), "users", ["wechat_openid"], unique=True)
    op.create_index(op.f("ix_users_wechat_unionid"), "users", ["wechat_unionid"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_wechat_unionid"), table_name="users")
    op.drop_index(op.f("ix_users_wechat_openid"), table_name="users")
    op.drop_column("users", "wechat_unionid")
    op.drop_column("users", "wechat_openid")
