"""Session state management with undo support and style presets."""

import json
from typing import Optional
from pydantic import BaseModel, Field

from .slides import SlideCollection, SlideStyleProps
from .slides.templates import TemplateLibrary
from .workspace import Workspace


class StylePreset(BaseModel):
    """A named style preset."""
    name: str
    description: str
    style: SlideStyleProps


# Built-in presets
BUILTIN_PRESETS: dict[str, StylePreset] = {
    "youtube": StylePreset(
        name="youtube",
        description="Bold, high-contrast style for YouTube videos",
        style=SlideStyleProps(
            font_family="Bfont",
            font_size_title=80,
            font_size_body=40,
            font_color="#FFFFFF",
            background_color="#0F0F0F",
            text_alignment="center",
            padding=50,
        ),
    ),
    "presentation": StylePreset(
        name="presentation",
        description="Clean, professional look for presentations",
        style=SlideStyleProps(
            font_family="Bfont",
            font_size_title=64,
            font_size_body=32,
            font_color="#333333",
            background_color="#F5F5F5",
            text_alignment="left",
            padding=60,
        ),
    ),
    "cinematic": StylePreset(
        name="cinematic",
        description="Minimal, dramatic style for cinematic content",
        style=SlideStyleProps(
            font_family="Bfont",
            font_size_title=56,
            font_size_body=28,
            font_color="#E0E0E0",
            background_color="#000000",
            text_alignment="center",
            padding=80,
        ),
    ),
}


class UndoEntry(BaseModel):
    """A snapshot of slides state for undo."""
    description: str
    slides_json: str  # JSON-serialized SlideCollection


class SessionState(BaseModel):
    """Global session state for a video draft session."""
    workspace: Optional[Workspace] = None
    slides: SlideCollection = Field(default_factory=SlideCollection)
    undo_stack: list[UndoEntry] = Field(default_factory=list)
    templates: TemplateLibrary = Field(default_factory=TemplateLibrary)
    whisper_model_size: str = "base"
    transcript_cache: Optional[str] = None

    model_config = {"arbitrary_types_allowed": True}

    def checkpoint(self, description: str):
        """Save current slides state to undo stack."""
        entry = UndoEntry(
            description=description,
            slides_json=self.slides.model_dump_json(),
        )
        self.undo_stack.append(entry)
        # Keep max 50 undo entries
        if len(self.undo_stack) > 50:
            self.undo_stack = self.undo_stack[-50:]

    def undo(self) -> Optional[str]:
        """Revert to the last checkpoint. Returns description of what was undone."""
        if not self.undo_stack:
            return None
        entry = self.undo_stack.pop()
        self.slides = SlideCollection.model_validate_json(entry.slides_json)
        return entry.description

    def auto_save(self):
        """Save current state to workspace if available."""
        if self.workspace:
            self._save_slides_to_workspace()

    def _save_slides_to_workspace(self):
        """Persist slides to the workspace directory."""
        if not self.workspace:
            return
        slides_path = self.workspace.root_path / "slides.json"
        slides_path.write_text(self.slides.model_dump_json(indent=2))

    def load_slides_from_workspace(self):
        """Load slides from workspace if they exist."""
        if not self.workspace:
            return
        slides_path = self.workspace.root_path / "slides.json"
        if slides_path.exists():
            self.slides = SlideCollection.model_validate_json(
                slides_path.read_text()
            )

    @staticmethod
    def get_preset(name: str) -> Optional[StylePreset]:
        return BUILTIN_PRESETS.get(name)

    @staticmethod
    def list_presets() -> list[dict]:
        return [
            {"name": p.name, "description": p.description}
            for p in BUILTIN_PRESETS.values()
        ]
