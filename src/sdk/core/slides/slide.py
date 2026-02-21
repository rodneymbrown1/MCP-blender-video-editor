"""Slide data model."""

import uuid
from typing import Optional
from pydantic import BaseModel, Field

from .styles import SlideStyleProps
from .animations import TextAnimation, SlideTransition, SlideEffect


class Slide(BaseModel):
    """A single slide in a video draft.

    New fields (template_id, animations, transition, effects) all have
    defaults so existing JSON still deserializes without changes.
    """
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    order: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    title: str = ""
    body_text: str = ""
    speaker_notes: str = ""
    background_image_ref: Optional[str] = None
    style_overrides: Optional[SlideStyleProps] = None

    # New fields
    template_id: Optional[str] = None
    animations: list[TextAnimation] = Field(default_factory=list)
    transition: SlideTransition = Field(default_factory=SlideTransition)
    effects: list[SlideEffect] = Field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time
