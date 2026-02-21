"""Tests for sdk.core.state — SessionState, StylePreset, undo, presets."""

import json
import pytest
from pathlib import Path

from sdk.core.slides import Slide, SlideCollection, SlideStyleProps
from sdk.core.workspace import Workspace
from sdk.core.state import SessionState, StylePreset, BUILTIN_PRESETS, UndoEntry


# ── StylePreset & BUILTIN_PRESETS ───────────────────────────────────────

class TestStylePresets:
    def test_builtin_presets_exist(self):
        assert "youtube" in BUILTIN_PRESETS
        assert "presentation" in BUILTIN_PRESETS
        assert "cinematic" in BUILTIN_PRESETS

    def test_preset_has_required_fields(self):
        for name, preset in BUILTIN_PRESETS.items():
            assert preset.name == name
            assert isinstance(preset.description, str)
            assert len(preset.description) > 0
            assert isinstance(preset.style, SlideStyleProps)

    def test_youtube_preset_values(self):
        p = BUILTIN_PRESETS["youtube"]
        assert p.style.font_size_title == 80
        assert p.style.background_color == "#0F0F0F"
        assert p.style.text_alignment == "center"

    def test_presentation_preset_values(self):
        p = BUILTIN_PRESETS["presentation"]
        assert p.style.font_color == "#333333"
        assert p.style.text_alignment == "left"

    def test_cinematic_preset_values(self):
        p = BUILTIN_PRESETS["cinematic"]
        assert p.style.background_color == "#000000"
        assert p.style.padding == 80


# ── SessionState basics ─────────────────────────────────────────────────

class TestSessionStateBasics:
    def test_default_state(self):
        state = SessionState()
        assert state.workspace is None
        assert len(state.slides.slides) == 0
        assert len(state.undo_stack) == 0
        assert state.whisper_model_size == "base"
        assert state.transcript_cache is None

    def test_get_preset(self):
        assert SessionState.get_preset("youtube") is not None
        assert SessionState.get_preset("youtube").name == "youtube"

    def test_get_preset_nonexistent(self):
        assert SessionState.get_preset("nonexistent") is None

    def test_list_presets(self):
        presets = SessionState.list_presets()
        assert len(presets) == 3
        names = {p["name"] for p in presets}
        assert names == {"youtube", "presentation", "cinematic"}
        for p in presets:
            assert "name" in p
            assert "description" in p


# ── Undo ────────────────────────────────────────────────────────────────

class TestUndo:
    def _state_with_slides(self, n=2) -> SessionState:
        state = SessionState()
        for i in range(n):
            state.slides.add(Slide(title=f"Slide {i}", body_text=f"Body {i}"))
        return state

    def test_checkpoint_and_undo(self):
        state = self._state_with_slides(2)
        state.checkpoint("before edit")

        # Mutate
        state.slides.slides[0].title = "Modified"
        assert state.slides.slides[0].title == "Modified"

        # Undo
        desc = state.undo()
        assert desc == "before edit"
        assert state.slides.slides[0].title == "Slide 0"

    def test_undo_empty_stack(self):
        state = SessionState()
        assert state.undo() is None

    def test_multiple_undos(self):
        state = self._state_with_slides(1)

        state.checkpoint("step 1")
        state.slides.slides[0].title = "After step 1"

        state.checkpoint("step 2")
        state.slides.slides[0].title = "After step 2"

        desc2 = state.undo()
        assert desc2 == "step 2"
        assert state.slides.slides[0].title == "After step 1"

        desc1 = state.undo()
        assert desc1 == "step 1"
        assert state.slides.slides[0].title == "Slide 0"

    def test_undo_after_add(self):
        state = self._state_with_slides(2)
        state.checkpoint("before add")
        state.slides.add(Slide(title="New"))
        assert len(state.slides.slides) == 3

        state.undo()
        assert len(state.slides.slides) == 2

    def test_undo_after_remove(self):
        state = self._state_with_slides(3)
        removed_id = state.slides.slides[1].id
        state.checkpoint("before remove")
        state.slides.remove(removed_id)
        assert len(state.slides.slides) == 2

        state.undo()
        assert len(state.slides.slides) == 3
        assert state.slides.get(removed_id) is not None

    def test_undo_stack_limit(self):
        state = SessionState()
        for i in range(60):
            state.checkpoint(f"step {i}")
        assert len(state.undo_stack) == 50

    def test_undo_preserves_slide_data(self):
        state = SessionState()
        state.slides.add(Slide(
            title="Original",
            body_text="Body text here.",
            start_time=1.0,
            end_time=5.0,
            speaker_notes="Notes",
        ))
        state.checkpoint("snapshot")

        state.slides.slides[0].title = "Changed"
        state.slides.slides[0].body_text = "New body"

        state.undo()
        s = state.slides.slides[0]
        assert s.title == "Original"
        assert s.body_text == "Body text here."
        assert s.start_time == 1.0
        assert s.speaker_notes == "Notes"


# ── Auto-save & workspace persistence ──────────────────────────────────

class TestAutoSave:
    def test_auto_save_without_workspace(self):
        """auto_save should not raise without a workspace."""
        state = SessionState()
        state.slides.add(Slide(title="Test"))
        state.auto_save()  # Should not raise

    def test_auto_save_with_workspace(self, tmp_path):
        ws = Workspace(project_name="test", root_path=tmp_path / "proj")
        ws.initialize()

        state = SessionState(workspace=ws)
        state.slides.add(Slide(title="Slide A", start_time=0, end_time=5))
        state.auto_save()

        slides_path = ws.root_path / "slides.json"
        assert slides_path.exists()

        data = json.loads(slides_path.read_text())
        assert len(data["slides"]) == 1
        assert data["slides"][0]["title"] == "Slide A"

    def test_load_slides_from_workspace(self, tmp_path):
        ws = Workspace(project_name="test", root_path=tmp_path / "proj")
        ws.initialize()

        # Save slides
        state1 = SessionState(workspace=ws)
        state1.slides.add(Slide(title="Saved Slide", start_time=0, end_time=3))
        state1.auto_save()

        # Load into fresh state
        state2 = SessionState(workspace=ws)
        assert len(state2.slides.slides) == 0
        state2.load_slides_from_workspace()
        assert len(state2.slides.slides) == 1
        assert state2.slides.slides[0].title == "Saved Slide"

    def test_load_slides_no_file(self, tmp_path):
        ws = Workspace(project_name="test", root_path=tmp_path / "proj")
        ws.initialize()

        state = SessionState(workspace=ws)
        state.load_slides_from_workspace()  # Should not raise
        assert len(state.slides.slides) == 0

    def test_load_slides_without_workspace(self):
        state = SessionState()
        state.load_slides_from_workspace()  # Should not raise
