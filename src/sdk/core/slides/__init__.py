"""Slides package — public API re-exports."""

from .styles import SlideStyleProps, TextShadow, TextOutline, TextBox, TextPosition
from .animations import Keyframe, TextAnimation, SlideTransition, SlideEffect
from .slide import Slide
from .collection import SlideCollection
from .templates import FrameTemplate, TemplateLibrary

__all__ = [
    "Slide",
    "SlideCollection",
    "SlideStyleProps",
    "TextShadow",
    "TextOutline",
    "TextBox",
    "TextPosition",
    "Keyframe",
    "TextAnimation",
    "SlideTransition",
    "SlideEffect",
    "FrameTemplate",
    "TemplateLibrary",
]
