"""Add a stable scene-location pointer to scoped progress."""

import sqlalchemy as sa
from alembic import op

revision = "20260715_11"
down_revision = "20260715_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("scene_progress")}
    # The initial migration creates fresh databases from current metadata.
    if "current_location_key" in columns:
        return
    with op.batch_alter_table("scene_progress") as batch:
        batch.add_column(sa.Column("current_location_key", sa.String(length=300), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("scene_progress") as batch:
        batch.drop_column("current_location_key")
