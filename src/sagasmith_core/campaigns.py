"""Campaign management service."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from sagasmith_core.database import Database
from sagasmith_core.models import Campaign, CampaignBranch


class CampaignNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class CampaignInfo:
    id: str
    system_id: str
    slug: str
    name: str
    status: str
    description: str
    settings: dict[str, Any]
    state: dict[str, Any]
    revision: int


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or uuid.uuid4().hex[:12]


class CampaignService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(
        self,
        *,
        system_id: str,
        name: str,
        slug: str | None = None,
        description: str = "",
        settings: dict[str, Any] | None = None,
        state: dict[str, Any] | None = None,
    ) -> CampaignInfo:
        row = Campaign(
            id=str(uuid.uuid4()),
            system_id=system_id,
            slug=slugify(slug or name),
            name=name,
            description=description,
            settings=settings or {},
            state=state or {},
        )
        with self.database.transaction() as session:
            session.add(row)
            session.flush()
            branch = CampaignBranch(
                id=str(uuid.uuid4()),
                campaign_id=row.id,
                name="main",
                is_current=True,
            )
            session.add(branch)
            session.flush()
            row.active_branch_id = branch.id
            return self._info(row)

    def get(self, campaign_id: str) -> CampaignInfo:
        with self.database.transaction() as session:
            row = session.get(Campaign, campaign_id)
            if row is None:
                raise CampaignNotFoundError(campaign_id)
            return self._info(row)

    def list(
        self,
        *,
        system_id: str | None = None,
        status: str | None = None,
    ) -> list[CampaignInfo]:
        statement = select(Campaign).order_by(Campaign.created_at, Campaign.id)
        if system_id:
            statement = statement.where(Campaign.system_id == system_id)
        if status:
            statement = statement.where(Campaign.status == status)
        with self.database.transaction() as session:
            return [self._info(row) for row in session.scalars(statement)]

    def update(
        self,
        campaign_id: str,
        *,
        name: str | None = None,
        status: str | None = None,
        description: str | None = None,
        settings: dict[str, Any] | None = None,
        state: dict[str, Any] | None = None,
        expected_revision: int | None = None,
    ) -> CampaignInfo:
        with self.database.transaction() as session:
            row = session.get(Campaign, campaign_id)
            if row is None:
                raise CampaignNotFoundError(campaign_id)
            if expected_revision is not None and row.revision != expected_revision:
                raise ValueError(f"campaign revision conflict: {campaign_id}")
            if name is not None:
                row.name = name
            if status is not None:
                row.status = status
            if description is not None:
                row.description = description
            if settings is not None:
                row.settings = settings
            if state is not None:
                row.state = state
            row.revision += 1
            session.flush()
            return self._info(row)

    def delete(self, campaign_id: str) -> None:
        with self.database.transaction() as session:
            row = session.get(Campaign, campaign_id)
            if row is None:
                raise CampaignNotFoundError(campaign_id)
            session.delete(row)

    @staticmethod
    def _info(row: Campaign) -> CampaignInfo:
        return CampaignInfo(
            id=row.id,
            system_id=row.system_id,
            slug=row.slug,
            name=row.name,
            status=row.status,
            description=row.description,
            settings=dict(row.settings),
            state=dict(row.state),
            revision=row.revision,
        )
