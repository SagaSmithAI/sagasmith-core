import pytest

from sagasmith_core.campaigns import CampaignService
from sagasmith_core.characters import CharacterService


def test_campaign_and_character_lifecycle(database) -> None:
    campaigns = CampaignService(database)
    characters = CharacterService(database)

    campaign = campaigns.create(system_id="dnd5e", name="The Long Road")
    character = characters.create(
        system_id="dnd5e",
        campaign_id=campaign.id,
        name="Mira",
        sheet={"dnd": {"level": 1, "armor_class": 14}},
    )

    assert campaigns.get(campaign.id).slug == "the-long-road"
    assert characters.get(character.id).sheet["dnd"]["armor_class"] == 14

    updated = characters.update(character.id, sheet={"dnd": {"level": 2}})
    assert updated.revision == 2
    assert characters.bind(character.id, None).campaign_id is None


def test_character_cannot_bind_across_systems(database) -> None:
    campaigns = CampaignService(database)
    characters = CharacterService(database)
    coc = campaigns.create(system_id="coc7", name="Arkham")
    hero = characters.create(system_id="dnd5e", name="Mira")

    with pytest.raises(ValueError):
        characters.bind(hero.id, coc.id)

