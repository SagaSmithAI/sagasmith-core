"""Character library and campaign binding service."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from sagasmith_core.campaigns import CampaignNotFoundError
from sagasmith_core.database import Database
from sagasmith_core.models import Campaign, Character


class CharacterNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class CharacterInfo:
    id: str
    system_id: str
    campaign_id: str | None
    character_type: str
    name: str
    player_name: str | None
    summary: str
    sheet: dict[str, Any]
    notes: dict[str, Any]
    revision: int


class CharacterService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(
        self,
        *,
        system_id: str,
        name: str,
        character_type: str = "pc",
        campaign_id: str | None = None,
        player_name: str | None = None,
        summary: str = "",
        sheet: dict[str, Any] | None = None,
        notes: dict[str, Any] | None = None,
    ) -> CharacterInfo:
        with self.database.transaction() as session:
            self._validate_campaign(session, system_id, campaign_id)
            row = Character(
                id=str(uuid.uuid4()),
                system_id=system_id,
                campaign_id=campaign_id,
                character_type=character_type,
                name=name,
                player_name=player_name,
                summary=summary,
                sheet=sheet or {},
                notes=notes or {},
            )
            session.add(row)
            session.flush()
            return self._info(row)

    def get(self, character_id: str) -> CharacterInfo:
        with self.database.transaction() as session:
            row = session.get(Character, character_id)
            if row is None:
                raise CharacterNotFoundError(character_id)
            return self._info(row)

    def list(
        self,
        *,
        system_id: str | None = None,
        campaign_id: str | None = None,
        character_type: str | None = None,
    ) -> list[CharacterInfo]:
        statement = select(Character).order_by(Character.name, Character.id)
        if system_id:
            statement = statement.where(Character.system_id == system_id)
        if campaign_id:
            statement = statement.where(Character.campaign_id == campaign_id)
        if character_type:
            statement = statement.where(Character.character_type == character_type)
        with self.database.transaction() as session:
            return [self._info(row) for row in session.scalars(statement)]

    def update(
        self,
        character_id: str,
        *,
        name: str | None = None,
        player_name: str | None = None,
        summary: str | None = None,
        sheet: dict[str, Any] | None = None,
        notes: dict[str, Any] | None = None,
    ) -> CharacterInfo:
        with self.database.transaction() as session:
            row = session.get(Character, character_id)
            if row is None:
                raise CharacterNotFoundError(character_id)
            if name is not None:
                row.name = name
            if player_name is not None:
                row.player_name = player_name
            if summary is not None:
                row.summary = summary
            if sheet is not None:
                row.sheet = sheet
            if notes is not None:
                row.notes = notes
            row.revision += 1
            session.flush()
            return self._info(row)

    def bind(self, character_id: str, campaign_id: str | None) -> CharacterInfo:
        with self.database.transaction() as session:
            row = session.get(Character, character_id)
            if row is None:
                raise CharacterNotFoundError(character_id)
            self._validate_campaign(session, row.system_id, campaign_id)
            row.campaign_id = campaign_id
            row.revision += 1
            session.flush()
            return self._info(row)

    @staticmethod
    def _validate_campaign(session, system_id: str, campaign_id: str | None) -> None:
        if campaign_id is None:
            return
        campaign = session.get(Campaign, campaign_id)
        if campaign is None:
            raise CampaignNotFoundError(campaign_id)
        if campaign.system_id != system_id:
            raise ValueError("character and campaign must use the same system_id")

    @staticmethod
    def _info(row: Character) -> CharacterInfo:
        return CharacterInfo(
            id=row.id,
            system_id=row.system_id,
            campaign_id=row.campaign_id,
            character_type=row.character_type,
            name=row.name,
            player_name=row.player_name,
            summary=row.summary,
            sheet=dict(row.sheet),
            notes=dict(row.notes),
            revision=row.revision,
        )

