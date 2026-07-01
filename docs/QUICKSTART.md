# Quick start

```bash
pip install sagasmith-core
```

```python
from sagasmith_core import (
    CampaignService,
    CharacterService,
    Database,
    ModuleService,
    RuleService,
)

database = Database("sqlite+pysqlite:///game.db")
database.upgrade_schema()

campaigns = CampaignService(database)
characters = CharacterService(database)
rules = RuleService(database)
modules = ModuleService(database)

campaign = campaigns.create(system_id="my-system", name="First Campaign")
character = characters.create(
    system_id="my-system",
    campaign_id=campaign.id,
    name="Avery",
    sheet={"my-system": {"primary_stat": 60}},
)

rules.ingest(
    system_id="my-system",
    source_key="core-rules",
    title="Core Rules",
    content="# Checks\nRoll against the relevant attribute.",
)

modules.ingest(
    campaign_id=campaign.id,
    source_key="adventure.md",
    title="First Adventure",
    content="# Arrival\n## The Gate\nTwo guards block the road.",
)

print(rules.search(system_id="my-system", query="checks"))
print(modules.search(campaign_id=campaign.id, query="guards"))
```

## Dense retrieval

```bash
pip install "sagasmith-core[embedding,vector]"
```

```python
from sagasmith_core import BgeM3Embedder, VectorStore

embedder = BgeM3Embedder(env_prefix="MY_SYSTEM")
vectors = VectorStore("my_system")

rules.ingest(
    system_id="my-system",
    source_key="core-rules",
    title="Core Rules",
    content="# Checks\nRoll against the relevant attribute.",
    embedder=embedder,
    vector_store=vectors,
)

hits = rules.search(
    system_id="my-system",
    query="How is an uncertain action resolved?",
    embedder=embedder,
    vector_store=vectors,
)
```

