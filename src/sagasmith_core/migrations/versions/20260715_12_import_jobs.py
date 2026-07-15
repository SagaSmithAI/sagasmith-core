"""Add durable import-job records without altering existing campaign data."""

from alembic import op

from sagasmith_core.models import Base

revision = "20260715_12"
down_revision = "20260715_11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    # Import records are audit evidence. Deliberately retain them on downgrade.
    pass
