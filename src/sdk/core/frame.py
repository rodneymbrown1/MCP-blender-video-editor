"""Slide data models for video draft projects."""

import uuid
from typing import Optional
from pydantic import BaseModel, Field


class SlideStyleProps(BaseModel):
    """Visual style properties for a slide."""
    font_family: str = "Bfont"
    font_size_title: int = 72
    font_size_body: int = 36
    font_color: str = "#FFFFFF"
    background_color: str = "#1A1A2E"
    text_alignment: str = "center"
    padding: int = 40


class Slide(BaseModel):
    """A single slide in a video draft."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    order: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    title: str = ""
    body_text: str = ""
    speaker_notes: str = ""
    background_image_ref: Optional[str] = None
    style_overrides: Optional[SlideStyleProps] = None

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


class SlideCollection(BaseModel):
    """Ordered collection of slides with CRUD operations."""
    slides: list[Slide] = Field(default_factory=list)
    global_style: SlideStyleProps = Field(default_factory=SlideStyleProps)

    def get(self, slide_id: str) -> Optional[Slide]:
        for s in self.slides:
            if s.id == slide_id:
                return s
        return None

    def add(self, slide: Slide) -> Slide:
        if not self.slides:
            slide.order = 0
        else:
            slide.order = max(s.order for s in self.slides) + 1
        self.slides.append(slide)
        return slide

    def remove(self, slide_id: str) -> bool:
        original_len = len(self.slides)
        self.slides = [s for s in self.slides if s.id != slide_id]
        if len(self.slides) < original_len:
            self._reindex()
            return True
        return False

    def split(self, slide_id: str, at_time: float) -> tuple[Slide, Slide] | None:
        slide = self.get(slide_id)
        if not slide:
            return None
        if at_time <= slide.start_time or at_time >= slide.end_time:
            return None

        # Split body text roughly in half by sentences
        sentences = slide.body_text.split(". ")
        mid = max(1, len(sentences) // 2)
        first_text = ". ".join(sentences[:mid])
        second_text = ". ".join(sentences[mid:])
        if first_text and not first_text.endswith("."):
            first_text += "."

        new_slide = Slide(
            order=slide.order + 1,
            start_time=at_time,
            end_time=slide.end_time,
            title="",
            body_text=second_text,
            speaker_notes="",
        )

        slide.end_time = at_time
        slide.body_text = first_text

        # Insert new slide right after the original
        idx = self.slides.index(slide)
        self.slides.insert(idx + 1, new_slide)
        self._reindex()
        return (slide, new_slide)

    def merge(self, slide_id_1: str, slide_id_2: str) -> Slide | None:
        s1 = self.get(slide_id_1)
        s2 = self.get(slide_id_2)
        if not s1 or not s2:
            return None

        # Ensure s1 comes first
        if s1.order > s2.order:
            s1, s2 = s2, s1

        s1.end_time = s2.end_time
        body_parts = [s1.body_text, s2.body_text]
        s1.body_text = " ".join(p for p in body_parts if p)
        if s2.speaker_notes:
            s1.speaker_notes = " ".join(
                p for p in [s1.speaker_notes, s2.speaker_notes] if p
            )

        self.slides = [s for s in self.slides if s.id != s2.id]
        self._reindex()
        return s1

    def reorder(self, slide_id_list: list[str]) -> bool:
        id_set = {s.id for s in self.slides}
        if set(slide_id_list) != id_set:
            return False

        id_to_slide = {s.id: s for s in self.slides}
        self.slides = [id_to_slide[sid] for sid in slide_id_list]
        self._reindex()
        return True

    def _reindex(self):
        for i, slide in enumerate(self.slides):
            slide.order = i

    def to_summary(self) -> list[dict]:
        return [
            {
                "id": s.id,
                "order": s.order,
                "time_range": f"{s.start_time:.1f}s - {s.end_time:.1f}s",
                "title": s.title or "(untitled)",
                "body_snippet": (s.body_text[:80] + "...") if len(s.body_text) > 80 else s.body_text,
                "has_background": s.background_image_ref is not None,
            }
            for s in self.slides
        ]
