import pytest

from sagasmith_core import CampaignService, ImportJobService
from sagasmith_core.import_jobs import ImportJobError


def test_import_job_persists_inspection_candidate_review_and_result(database) -> None:
    campaign = CampaignService(database).create(system_id="dnd5e", name="Import jobs")
    jobs = ImportJobService(database)
    created = jobs.create(
        campaign_id=campaign.id,
        kind="rulebook",
        artifact="xanathar.pdf",
        artifact_checksum="abc123",
        payload={"edition": "2014"},
    )
    inspected = jobs.record_inspection(
        created.id,
        {"sections": 10, "chunks": 35, "parser_profile": "markdown", "parser_version": "1"},
    )
    assert inspected.state == "inspected"
    extracted = jobs.set_candidates(
        created.id,
        [
            {
                "id": "candidate:fireball",
                "kind": "spell",
                "source_chunk_ids": ["chunk-1"],
            }
        ],
    )
    assert extracted.state == "review_required"
    reviewed = jobs.review_candidates(
        created.id,
        [
            {
                "id": "candidate:fireball",
                "review_status": "accepted",
                "artifact": {"kind": "spell", "card": {"name": "Fireball"}},
            }
        ],
    )
    assert reviewed.state == "reviewed"
    completed = jobs.record_result(
        created.id,
        {"pack_id": "dnd5e.xgte", "version": "1.0.0"},
        state="installed",
        source_id="source-1",
    )
    assert completed.source_id == "source-1"
    assert jobs.list(campaign.id)[0].result["pack_id"] == "dnd5e.xgte"


def test_import_job_rejects_invalid_candidate_review(database) -> None:
    campaign = CampaignService(database).create(system_id="dnd5e", name="Import validation")
    jobs = ImportJobService(database)
    job = jobs.create(campaign_id=campaign.id, kind="module", artifact="module.md")
    with pytest.raises(ImportJobError, match="unsupported import kind"):
        jobs.create(campaign_id=campaign.id, kind="other", artifact="x")
    with pytest.raises(ImportJobError, match="candidate ids must be unique"):
        jobs.set_candidates(job.id, [{"id": "same"}, {"id": "same"}])
