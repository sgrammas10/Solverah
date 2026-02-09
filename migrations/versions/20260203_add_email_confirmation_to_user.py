"""add email confirmation columns to user

Revision ID: 20260203_add_email_confirmation_to_user
Revises: 139e1d37427a_add_login_lockout_columns
Create Date: 2026-02-03 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260203_add_email_confirmation_to_user'
down_revision = '139e1d37427a'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user', sa.Column('email_confirmed', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('user', sa.Column('confirmation_token', sa.String(length=64), nullable=True))
    op.add_column('user', sa.Column('confirmation_sent_at', sa.DateTime(), nullable=True))
    op.create_index(op.f('ix_user_confirmation_token'), 'user', ['confirmation_token'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_user_confirmation_token'), table_name='user')
    op.drop_column('user', 'confirmation_sent_at')
    op.drop_column('user', 'confirmation_token')
    op.drop_column('user', 'email_confirmed')
