"""Add non-destructive branches and actor knowledge ledgers."""

from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op

from sagasmith_core.models import Base

revision = "20260713_07"
down_revision = "20260712_06"
branch_labels = None
depends_on = None


def _add(table: str, column: sa.Column) -> None:
    inspector = sa.inspect(op.get_bind())
    if table in inspector.get_table_names():
        existing = {item["name"] for item in inspector.get_columns(table)}
        if column.name not in existing:
            op.add_column(table, column)


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)
    _add("campaigns", sa.Column("active_branch_id", sa.String(36), nullable=True))
    _add("campaign_snapshots", sa.Column("branch_id", sa.String(36), nullable=True))
    _add("campaign_events", sa.Column("branch_id", sa.String(36), nullable=True))
    _add("campaign_events", sa.Column("committed_snapshot_id", sa.String(36), nullable=True))
    _add(
        "campaign_events",
        sa.Column("audience_scope", sa.String(200), nullable=False, server_default="dm"),
    )

    campaigns = bind.execute(sa.text("SELECT id FROM campaigns")).mappings().all()
    for campaign in campaigns:
        campaign_id = campaign["id"]
        branch_id = bind.execute(
            sa.text(
                "SELECT id FROM campaign_branches "
                "WHERE campaign_id = :campaign_id AND name = 'main'"
            ),
            {"campaign_id": campaign_id},
        ).scalar()
        if branch_id is None:
            branch_id = str(uuid.uuid4())
            head_id = bind.execute(
                sa.text(
                    "SELECT id FROM campaign_snapshots "
                    "WHERE campaign_id = :campaign_id AND is_head = 1 "
                    "ORDER BY slot DESC LIMIT 1"
                ),
                {"campaign_id": campaign_id},
            ).scalar()
            bind.execute(
                sa.text(
                    "INSERT INTO campaign_branches "
                    "(id, campaign_id, name, base_snapshot_id, head_snapshot_id, is_current, "
                    "created_at, updated_at) "
                    "VALUES (:id, :campaign_id, 'main', NULL, :head_id, 1, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"id": branch_id, "campaign_id": campaign_id, "head_id": head_id},
            )
        bind.execute(
            sa.text("UPDATE campaigns SET active_branch_id = :branch_id WHERE id = :campaign_id"),
            {"branch_id": branch_id, "campaign_id": campaign_id},
        )
        characters = bind.execute(
            sa.text("SELECT id, notes FROM characters WHERE campaign_id = :campaign_id"),
            {"campaign_id": campaign_id},
        ).mappings()
        for character in characters:
            notes = character["notes"]
            if isinstance(notes, str):
                notes = json.loads(notes or "{}")
            for memory in (notes or {}).get("memories", []):
                memory_id = memory.get("id") or str(uuid.uuid4())
                key = f"legacy:{memory_id}"
                knowledge_id = bind.execute(
                    sa.text(
                        "SELECT id FROM actor_knowledge "
                        "WHERE actor_id = :actor_id AND knowledge_key = :knowledge_key"
                    ),
                    {"actor_id": character["id"], "knowledge_key": key},
                ).scalar()
                if knowledge_id is None:
                    knowledge_id = str(uuid.uuid4())
                    revision_id = str(uuid.uuid4())
                    status = "superseded" if memory.get("status") != "active" else "known"
                    bind.execute(
                        sa.text(
                            "INSERT INTO actor_knowledge "
                            "(id, campaign_id, actor_id, knowledge_key, subject_ref, created_at) "
                            "VALUES (:id, :campaign_id, :actor_id, :knowledge_key, :subject_ref, "
                            "CURRENT_TIMESTAMP)"
                        ),
                        {
                            "id": knowledge_id,
                            "campaign_id": campaign_id,
                            "actor_id": character["id"],
                            "knowledge_key": key,
                            "subject_ref": memory.get("kind", ""),
                        },
                    )
                    bind.execute(
                        sa.text(
                            "INSERT INTO actor_knowledge_revisions "
                            "(id, knowledge_id, parent_id, proposition, epistemic_status, "
                            "confidence, "
                            "source_event_id, cause, disclosure_scope, created_at) "
                            "VALUES (:id, :knowledge_id, NULL, :proposition, :status, :confidence, "
                            "NULL, 'legacy_character_memory', :disclosure_scope, CURRENT_TIMESTAMP)"
                        ),
                        {
                            "id": revision_id,
                            "knowledge_id": knowledge_id,
                            "proposition": memory.get("summary", ""),
                            "status": status,
                            "confidence": max(0, min(int(memory.get("importance", 3)), 5)),
                            "disclosure_scope": memory.get("visibility", "dm"),
                        },
                    )
                    bind.execute(
                        sa.text(
                            "INSERT INTO branch_actor_knowledge_heads "
                            "(branch_id, knowledge_id, revision_id) "
                            "VALUES (:branch_id, :knowledge_id, :revision_id)"
                        ),
                        {
                            "branch_id": branch_id,
                            "knowledge_id": knowledge_id,
                            "revision_id": revision_id,
                        },
                    )
        bind.execute(
            sa.text(
                "UPDATE campaign_snapshots SET branch_id = :branch_id "
                "WHERE campaign_id = :campaign_id AND branch_id IS NULL"
            ),
            {"branch_id": branch_id, "campaign_id": campaign_id},
        )
        bind.execute(
            sa.text(
                "UPDATE campaign_events SET branch_id = :branch_id "
                "WHERE campaign_id = :campaign_id AND branch_id IS NULL"
            ),
            {"branch_id": branch_id, "campaign_id": campaign_id},
        )
        bind.execute(
            sa.text(
                "INSERT INTO branch_fact_heads (branch_id, memory_id, revision_id) "
                "SELECT :branch_id, m.id, r.id "
                "FROM campaign_memories AS m JOIN memory_revisions AS r ON r.memory_id = m.id "
                "WHERE m.campaign_id = :campaign_id AND r.active = 1 "
                "AND NOT EXISTS (SELECT 1 FROM branch_fact_heads AS h "
                "WHERE h.branch_id = :branch_id AND h.memory_id = m.id)"
            ),
            {"branch_id": branch_id, "campaign_id": campaign_id},
        )


def downgrade() -> None:
    # Branch and knowledge history is intentionally retained for user campaign safety.
    pass
