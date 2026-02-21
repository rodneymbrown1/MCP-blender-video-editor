"""Project workspace and asset management."""

import json
import shutil
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field


class AssetMetadata(BaseModel):
    """Metadata for a registered project asset."""
    asset_id: str
    filename: str
    type: str  # "image", "audio", "video", "blender"
    source: str = ""  # e.g. "unsplash", "pexels", "local"
    dimensions: Optional[tuple[int, int]] = None


class Workspace(BaseModel):
    """Manages a video draft project directory and asset manifest."""
    project_name: str
    root_path: Path
    assets: dict[str, AssetMetadata] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}

    @property
    def assets_dir(self) -> Path:
        return self.root_path / "assets"

    @property
    def images_dir(self) -> Path:
        return self.assets_dir / "images"

    @property
    def audio_dir(self) -> Path:
        return self.assets_dir / "audio"

    @property
    def video_dir(self) -> Path:
        return self.assets_dir / "video"

    @property
    def blender_dir(self) -> Path:
        return self.assets_dir / "blender"

    @property
    def exports_dir(self) -> Path:
        return self.root_path / "exports"

    @property
    def manifest_path(self) -> Path:
        return self.root_path / "project.json"

    def initialize(self) -> "Workspace":
        """Create the project directory structure."""
        for d in [self.images_dir, self.audio_dir, self.video_dir,
                  self.blender_dir, self.exports_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Create user.md and project.md if they don't exist
        user_md = self.root_path / "user.md"
        if not user_md.exists():
            user_md.write_text(
                f"# User Notes - {self.project_name}\n\n"
                "Goals:\n\nPreferences:\n"
            )

        project_md = self.root_path / "project.md"
        if not project_md.exists():
            project_md.write_text(
                f"# Project: {self.project_name}\n\n"
                "## Content Strategy\n\n## Decisions\n\n## Notes\n"
            )

        self.save_manifest()
        return self

    def save_manifest(self):
        """Save the project manifest to disk."""
        data = {
            "project_name": self.project_name,
            "assets": {k: v.model_dump() for k, v in self.assets.items()},
        }
        self.manifest_path.write_text(json.dumps(data, indent=2, default=str))

    @classmethod
    def load(cls, project_path: Path) -> "Workspace":
        """Load a workspace from an existing project directory."""
        manifest_path = project_path / "project.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"No project.json found in {project_path}")

        data = json.loads(manifest_path.read_text())
        assets = {
            k: AssetMetadata(**v) for k, v in data.get("assets", {}).items()
        }
        return cls(
            project_name=data["project_name"],
            root_path=project_path,
            assets=assets,
        )

    def register_asset(self, asset: AssetMetadata) -> AssetMetadata:
        """Register an asset in the workspace manifest."""
        self.assets[asset.asset_id] = asset
        self.save_manifest()
        return asset

    def get_asset_path(self, asset_id: str) -> Optional[Path]:
        """Get the full path to an asset file."""
        asset = self.assets.get(asset_id)
        if not asset:
            return None
        type_dirs = {
            "image": self.images_dir,
            "audio": self.audio_dir,
            "video": self.video_dir,
            "blender": self.blender_dir,
        }
        base_dir = type_dirs.get(asset.type, self.assets_dir)
        return base_dir / asset.filename
