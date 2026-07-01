"""Optional contracts used by SagaSmith system packages integrating with nanobot."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sagasmith_core.profile import SystemProfile
from sagasmith_core.systems import SystemDefinition


@dataclass(frozen=True)
class NanobotSystemBundle:
    """Describe the non-code assets installed into a nanobot workspace."""

    definition: SystemDefinition
    skills_dir: Path
    templates_dir: Path

    def profile(self) -> SystemProfile:
        return SystemProfile(
            id=self.definition.id,
            display_name=self.definition.display_name,
            env_prefix=self.definition.id.upper(),
            package_root=self.skills_dir.parent,
            skills_dir=self.skills_dir,
            templates_dir=self.templates_dir,
        )

    def install(self, workspace: str | Path, *, overwrite: bool = False) -> list[Path]:
        return self.profile().install_workspace(Path(workspace), overwrite=overwrite)

