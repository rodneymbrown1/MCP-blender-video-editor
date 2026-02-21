"""Visual style models for slides — typography, shadows, outlines, positioning."""

from typing import Optional
from pydantic import BaseModel


class TextShadow(BaseModel):
    """Text shadow effect (maps to bpy text strip use_shadow, shadow_color, etc.)."""
    enabled: bool = False
    color: str = "#000000"
    offset_x: float = 2.0
    offset_y: float = -2.0
    blur: float = 0.0


class TextOutline(BaseModel):
    """Text outline effect (maps to bpy use_outline, outline_color, outline_width)."""
    enabled: bool = False
    color: str = "#000000"
    width: float = 1.0


class TextBox(BaseModel):
    """Background box behind text (maps to bpy use_box, box_color, box_margin)."""
    enabled: bool = False
    color: str = "#00000080"
    margin: float = 10.0


class TextPosition(BaseModel):
    """Normalized text position (maps to bpy location[], align_x, align_y).

    x and y are 0-1 normalized coordinates.
    align_x: LEFT, CENTER, RIGHT
    align_y: TOP, CENTER, BOTTOM
    """
    x: float = 0.5
    y: float = 0.5
    align_x: str = "CENTER"
    align_y: str = "CENTER"


class SlideStyleProps(BaseModel):
    """Visual style properties for a slide.

    Original 7 fields are preserved with identical defaults.
    New fields are all Optional with defaults for backward compatibility.
    """
    # Original fields (unchanged)
    font_family: str = "Bfont"
    font_size_title: int = 72
    font_size_body: int = 36
    font_color: str = "#FFFFFF"
    background_color: str = "#1A1A2E"
    text_alignment: str = "center"
    padding: int = 40

    # Typography extensions
    use_bold: bool = False
    use_italic: bool = False
    wrap_width: Optional[float] = None

    # Text effects
    shadow: Optional[TextShadow] = None
    outline: Optional[TextOutline] = None
    box: Optional[TextBox] = None

    # Position overrides
    title_position: Optional[TextPosition] = None
    body_position: Optional[TextPosition] = None
