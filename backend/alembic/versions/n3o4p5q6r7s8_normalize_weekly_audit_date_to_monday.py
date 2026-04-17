"""normalize weekly audit_date to monday

Non-reversible data migration: shifts audit_date for weekly audit_results
to the Monday of that calendar week so the cache key is stable across the week.
Deduplicates rows that collapse to the same (user_id, Monday, 'weekly') key.

Revision ID: n3o4p5q6r7s8
Revises: m2n3o4p5q6r7
Create Date: 2026-04-13 00:00:00.000000

"""
from alembic import op

# revision identifiers
revision = "n3o4p5q6r7s8"
down_revision = "m2n3o4p5q6r7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Normalize audit_date to Monday for all weekly rows.
    # ISODOW: Monday=1 ... Sunday=7
    op.execute("""
        UPDATE audit_results
        SET audit_date = audit_date - ((EXTRACT(ISODOW FROM audit_date)::int - 1) * INTERVAL '1 day')::interval
        WHERE audit_type = 'weekly'
          AND EXTRACT(ISODOW FROM audit_date)::int != 1
    """)

    # Step 2: Mark duplicates stale — keep only the newest per (user_id, audit_date, 'weekly').
    op.execute("""
        UPDATE audit_results a
        SET is_stale = TRUE
        WHERE a.audit_type = 'weekly'
          AND a.is_stale = FALSE
          AND EXISTS (
              SELECT 1 FROM audit_results b
              WHERE b.user_id = a.user_id
                AND b.audit_date = a.audit_date
                AND b.audit_type = 'weekly'
                AND b.is_stale = FALSE
                AND b.generated_at > a.generated_at
          )
    """)


def downgrade() -> None:
    # Non-reversible: the original day-of-week is lost after normalization.
    pass
