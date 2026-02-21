"""Frame templates — reusable slide skeletons for consistent look and feel."""

from typing import Optional
from pydantic import BaseModel, Field

from .styles import SlideStyleProps
from .animations import TextAnimation, SlideTransition, SlideEffect


class FrameTemplate(BaseModel):
    """A reusable slide skeleton defining default style, animations, and layout.

    Style resolution order when rendering:
    1. slide.style_overrides (highest priority)
    2. template.style (template-level defaults)
    3. collection.global_style (project-wide)
    """
    id: str
    name: str
    description: str = ""
    style: Optional[SlideStyleProps] = None
    animations: list[TextAnimation] = Field(default_factory=list)
    transition: Optional[SlideTransition] = None
    effects: list[SlideEffect] = Field(default_factory=list)
    show_title: bool = True
    show_body: bool = True


class TemplateLibrary(BaseModel):
    """Collection of frame templates with CRUD operations."""
    templates: dict[str, FrameTemplate] = Field(default_factory=dict)

    def get(self, template_id: str) -> Optional[FrameTemplate]:
        return self.templates.get(template_id)

    def add(self, template: FrameTemplate) -> FrameTemplate:
        self.templates[template.id] = template
        return template

    def remove(self, template_id: str) -> bool:
        if template_id in self.templates:
            del self.templates[template_id]
            return True
        return False

    def list_templates(self) -> list[dict]:
        return [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "has_style": t.style is not None,
                "animation_count": len(t.animations),
                "show_title": t.show_title,
                "show_body": t.show_body,
            }
            for t in self.templates.values()
        ]
