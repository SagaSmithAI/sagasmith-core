"""System profile and workspace installation contracts."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SystemProfile:
    id: str
    display_name: str
    env_prefix: str
    package_root: Path
    skills_dir: Path
    templates_dir: Path

    def install_workspace(self, workspace: Path, *, overwrite: bool = False) -> list[Path]:
        """Install one system's skills and templates into a nanobot workspace."""
        workspace = workspace.expanduser().resolve()
        installed: list[Path] = []
        target_skills = workspace / "skills"
        target_skills.mkdir(parents=True, exist_ok=True)

        if self.skills_dir.is_dir():
            for source in self.skills_dir.iterdir():
                if not source.is_dir():
                    continue
                target = target_skills / source.name
                if target.exists() and not overwrite:
                    continue
                shutil.copytree(source, target, dirs_exist_ok=True)
                installed.append(target)

        if self.templates_dir.is_dir():
            for source in self.templates_dir.iterdir():
                if not source.is_file():
                    continue
                target = workspace / source.name
                if target.exists() and not overwrite:
                    continue
                shutil.copy2(source, target)
                installed.append(target)
        return installed

