"""Declarative animation, transition, and effect models.

Pure data that the Blender addon translates to keyframe_insert() and VSE calls.
"""

from typing import Optional
from pydantic import BaseModel, Field


class Keyframe(BaseModel):
    """A single keyframe: value at a time offset from slide start."""
    time_offset: float  # seconds from slide start
    value: float


class TextAnimation(BaseModel):
    """Animation applied to a text element (title or body).

    Can use either a preset shorthand or custom keyframes.
    Presets: fade_in, fade_out, fade_in_out, slide_left, slide_right,
             slide_up, slide_down, scale_up, scale_down.
    """
    target: str = "title"  # "title" or "body"
    property: str = "opacity"  # opacity, font_size, x, y
    keyframes: list[Keyframe] = Field(default_factory=list)
    preset: Optional[str] = None
    preset_duration: float = 0.5  # ramp time in seconds


class SlideTransition(BaseModel):
    """Transition effect to the next slide.

    Types map to Blender VSE transition strips:
    cut, cross_dissolve, gamma_cross, wipe_single, wipe_double,
    wipe_iris, wipe_clock.
    """
    type: str = "cut"
    duration: float = 0.0  # seconds; 0 = instant cut


class SlideEffect(BaseModel):
    """Visual effect applied to a slide.

    Types map to Blender VSE effect strips:
    blur, glow, transform, speed, adjustment.
    Type-specific fields are Optional and ignored for non-matching types.
    """
    type: str  # blur, glow, transform, speed, adjustment

    # blur
    size_x: Optional[float] = None
    size_y: Optional[float] = None

    # glow
    threshold: Optional[float] = None

    # transform
    translate_x: Optional[float] = None
    translate_y: Optional[float] = None
    rotation: Optional[float] = None
    scale_x: Optional[float] = None
    scale_y: Optional[float] = None

    # speed
    speed_factor: Optional[float] = None
