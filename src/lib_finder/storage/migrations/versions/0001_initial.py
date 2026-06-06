"""Initial lib-finder storage schema."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from lib_finder.storage.schema import metadata

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    metadata.create_all(bind=bind)

    package_columns = {
        row[1] for row in bind.exec_driver_sql("PRAGMA table_info(packages)")
    }
    if "qualification_reason" not in package_columns:
        op.execute(sa.text("ALTER TABLE packages ADD COLUMN qualification_reason TEXT"))


def downgrade() -> None:
    bind = op.get_bind()
    metadata.drop_all(bind=bind)
