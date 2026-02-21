"""Tests for sdk.core.workspace — Workspace, AssetMetadata."""

import json
import pytest
from pathlib import Path

from sdk.core.workspace import Workspace, AssetMetadata


@pytest.fixture
def workspace_dir(tmp_path):
    """Provide a temporary directory for workspace tests."""
    return tmp_path / "test_project"


@pytest.fixture
def workspace(workspace_dir):
    """Create and initialize a workspace."""
    ws = Workspace(project_name="test_project", root_path=workspace_dir)
    ws.initialize()
    return ws


# ── AssetMetadata ───────────────────────────────────────────────────────

class TestAssetMetadata:
    def test_basic_creation(self):
        a = AssetMetadata(asset_id="img_001", filename="photo.jpg", type="image")
        assert a.asset_id == "img_001"
        assert a.filename == "photo.jpg"
        assert a.type == "image"
        assert a.source == ""
        assert a.dimensions is None

    def test_with_all_fields(self):
        a = AssetMetadata(
            asset_id="img_002",
            filename="bg.png",
            type="image",
            source="unsplash",
            dimensions=(1920, 1080),
        )
        assert a.source == "unsplash"
        assert a.dimensions == (1920, 1080)

    def test_serialization(self):
        a = AssetMetadata(asset_id="a1", filename="f.mp3", type="audio", source="local")
        data = a.model_dump()
        restored = AssetMetadata(**data)
        assert restored == a


# ── Workspace initialization ───────────────────────────────────────────

class TestWorkspaceInit:
    def test_initialize_creates_dirs(self, workspace):
        assert workspace.images_dir.exists()
        assert workspace.audio_dir.exists()
        assert workspace.video_dir.exists()
        assert workspace.blender_dir.exists()
        assert workspace.exports_dir.exists()

    def test_initialize_creates_manifest(self, workspace):
        assert workspace.manifest_path.exists()
        data = json.loads(workspace.manifest_path.read_text())
        assert data["project_name"] == "test_project"
        assert data["assets"] == {}

    def test_initialize_creates_markdown_files(self, workspace):
        user_md = workspace.root_path / "user.md"
        project_md = workspace.root_path / "project.md"
        assert user_md.exists()
        assert project_md.exists()
        assert "test_project" in user_md.read_text()
        assert "test_project" in project_md.read_text()

    def test_initialize_idempotent(self, workspace):
        """Calling initialize again should not overwrite existing files."""
        user_md = workspace.root_path / "user.md"
        user_md.write_text("custom content")
        workspace.initialize()
        assert user_md.read_text() == "custom content"

    def test_directory_properties(self, workspace):
        assert workspace.assets_dir == workspace.root_path / "assets"
        assert workspace.images_dir == workspace.root_path / "assets" / "images"
        assert workspace.audio_dir == workspace.root_path / "assets" / "audio"
        assert workspace.video_dir == workspace.root_path / "assets" / "video"
        assert workspace.blender_dir == workspace.root_path / "assets" / "blender"
        assert workspace.exports_dir == workspace.root_path / "exports"


# ── Manifest save/load ─────────────────────────────────────────────────

class TestWorkspaceManifest:
    def test_save_and_load(self, workspace):
        workspace.register_asset(AssetMetadata(
            asset_id="img_001", filename="photo.jpg", type="image", source="pexels",
        ))

        loaded = Workspace.load(workspace.root_path)
        assert loaded.project_name == "test_project"
        assert "img_001" in loaded.assets
        assert loaded.assets["img_001"].filename == "photo.jpg"

    def test_load_nonexistent_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            Workspace.load(tmp_path / "nonexistent")

    def test_save_overwrites(self, workspace):
        workspace.register_asset(AssetMetadata(
            asset_id="a1", filename="f1.jpg", type="image",
        ))
        workspace.register_asset(AssetMetadata(
            asset_id="a2", filename="f2.jpg", type="image",
        ))

        loaded = Workspace.load(workspace.root_path)
        assert len(loaded.assets) == 2


# ── Asset registration ─────────────────────────────────────────────────

class TestWorkspaceAssets:
    def test_register_asset(self, workspace):
        asset = AssetMetadata(
            asset_id="img_001", filename="bg.jpg", type="image", source="unsplash",
        )
        result = workspace.register_asset(asset)
        assert result.asset_id == "img_001"
        assert "img_001" in workspace.assets

    def test_register_persists_to_manifest(self, workspace):
        workspace.register_asset(AssetMetadata(
            asset_id="aud_001", filename="narration.wav", type="audio",
        ))
        data = json.loads(workspace.manifest_path.read_text())
        assert "aud_001" in data["assets"]

    def test_register_overwrites_same_id(self, workspace):
        workspace.register_asset(AssetMetadata(
            asset_id="x", filename="old.jpg", type="image",
        ))
        workspace.register_asset(AssetMetadata(
            asset_id="x", filename="new.jpg", type="image",
        ))
        assert workspace.assets["x"].filename == "new.jpg"

    def test_get_asset_path_image(self, workspace):
        workspace.register_asset(AssetMetadata(
            asset_id="img_001", filename="bg.jpg", type="image",
        ))
        path = workspace.get_asset_path("img_001")
        assert path == workspace.images_dir / "bg.jpg"

    def test_get_asset_path_audio(self, workspace):
        workspace.register_asset(AssetMetadata(
            asset_id="aud_001", filename="voice.mp3", type="audio",
        ))
        path = workspace.get_asset_path("aud_001")
        assert path == workspace.audio_dir / "voice.mp3"

    def test_get_asset_path_video(self, workspace):
        workspace.register_asset(AssetMetadata(
            asset_id="vid_001", filename="clip.mp4", type="video",
        ))
        path = workspace.get_asset_path("vid_001")
        assert path == workspace.video_dir / "clip.mp4"

    def test_get_asset_path_blender(self, workspace):
        workspace.register_asset(AssetMetadata(
            asset_id="bl_001", filename="scene.blend", type="blender",
        ))
        path = workspace.get_asset_path("bl_001")
        assert path == workspace.blender_dir / "scene.blend"

    def test_get_asset_path_unknown_type(self, workspace):
        workspace.register_asset(AssetMetadata(
            asset_id="x", filename="data.bin", type="other",
        ))
        path = workspace.get_asset_path("x")
        assert path == workspace.assets_dir / "data.bin"

    def test_get_asset_path_nonexistent(self, workspace):
        assert workspace.get_asset_path("nonexistent") is None
