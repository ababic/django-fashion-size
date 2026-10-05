"""Compile the size field assets while building a release."""

from __future__ import annotations

import subprocess
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    """Run the frontend build so the wheel contains the compiled size field."""

    def initialize(self, version: str, build_data: dict) -> None:
        frontend = Path(self.root) / "frontend"
        if not (frontend / "package.json").is_file():
            return
        subprocess.run(["npm", "ci"], cwd=frontend, check=True)
        subprocess.run(["npm", "run", "build"], cwd=frontend, check=True)
