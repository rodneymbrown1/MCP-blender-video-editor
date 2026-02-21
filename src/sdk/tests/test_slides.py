"""Tests for sdk.core.slides — new models: styles, animations, templates."""

import json
import pytest

from sdk.core.slides import (
    Slide,
    SlideCollection,
    SlideStyleProps,
    TextShadow,
    TextOutline,
    TextBox,
    TextPosition,
    Keyframe,
    TextAnimation,
    SlideTransition,
    SlideEffect,
    FrameTemplate,
    TemplateLibrary,
)


# ── TextShadow ────────────────────────────────────────────────────────

class TestTextShadow:
    def test_defaults(self):
        s = TextShadow()
        assert s.enabled is False
        assert s.color == "#000000"
        assert s.offset_x == 2.0
        assert s.offset_y == -2.0
        assert s.blur == 0.0

    def test_custom(self):
        s = TextShadow(enabled=True, color="#FF0000", blur=3.0)
        assert s.enabled is True
        assert s.color == "#FF0000"
        assert s.blur == 3.0

    def test_serialization_roundtrip(self):
        s = TextShadow(enabled=True, offset_x=5.0)
        data = s.model_dump()
        restored = TextShadow(**data)
        assert restored == s


# ── TextOutline ───────────────────────────────────────────────────────

class TestTextOutline:
    def test_defaults(self):
        o = TextOutline()
        assert o.enabled is False
        assert o.color == "#000000"
        assert o.width == 1.0

    def test_custom(self):
        o = TextOutline(enabled=True, width=3.5)
        assert o.width == 3.5

    def test_serialization_roundtrip(self):
        o = TextOutline(enabled=True, color="#00FF00", width=2.0)
        restored = TextOutline(**o.model_dump())
        assert restored == o


# ── TextBox ───────────────────────────────────────────────────────────

class TestTextBox:
    def test_defaults(self):
        b = TextBox()
        assert b.enabled is False
        assert b.margin == 10.0

    def test_custom(self):
        b = TextBox(enabled=True, color="#333333", margin=20.0)
        assert b.enabled is True
        assert b.color == "#333333"

    def test_serialization_roundtrip(self):
        b = TextBox(enabled=True)
        restored = TextBox(**b.model_dump())
        assert restored == b


# ── TextPosition ──────────────────────────────────────────────────────

class TestTextPosition:
    def test_defaults(self):
        p = TextPosition()
        assert p.x == 0.5
        assert p.y == 0.5
        assert p.align_x == "CENTER"
        assert p.align_y == "CENTER"

    def test_custom(self):
        p = TextPosition(x=0.1, y=0.9, align_x="LEFT", align_y="TOP")
        assert p.x == 0.1
        assert p.align_x == "LEFT"

    def test_serialization_roundtrip(self):
        p = TextPosition(x=0.0, y=1.0, align_x="RIGHT")
        restored = TextPosition(**p.model_dump())
        assert restored == p


# ── Expanded SlideStyleProps ──────────────────────────────────────────

class TestExpandedSlideStyleProps:
    def test_original_defaults_unchanged(self):
        s = SlideStyleProps()
        assert s.font_family == "Bfont"
        assert s.font_size_title == 72
        assert s.font_size_body == 36
        assert s.font_color == "#FFFFFF"
        assert s.background_color == "#1A1A2E"
        assert s.text_alignment == "center"
        assert s.padding == 40

    def test_new_fields_default_to_none_or_false(self):
        s = SlideStyleProps()
        assert s.use_bold is False
        assert s.use_italic is False
        assert s.wrap_width is None
        assert s.shadow is None
        assert s.outline is None
        assert s.box is None
        assert s.title_position is None
        assert s.body_position is None

    def test_old_json_still_deserializes(self):
        """JSON from the original 7-field SlideStyleProps must still load."""
        old_json = json.dumps({
            "font_family": "Arial",
            "font_size_title": 80,
            "font_size_body": 40,
            "font_color": "#000000",
            "background_color": "#FFFFFF",
            "text_alignment": "left",
            "padding": 50,
        })
        s = SlideStyleProps.model_validate_json(old_json)
        assert s.font_family == "Arial"
        assert s.shadow is None  # new field absent in old JSON

    def test_new_fields_roundtrip(self):
        s = SlideStyleProps(
            use_bold=True,
            use_italic=True,
            wrap_width=0.8,
            shadow=TextShadow(enabled=True),
            outline=TextOutline(enabled=True, width=2.0),
            box=TextBox(enabled=True),
            title_position=TextPosition(x=0.1, y=0.9),
            body_position=TextPosition(x=0.1, y=0.5),
        )
        data = json.loads(s.model_dump_json())
        restored = SlideStyleProps(**data)
        assert restored.use_bold is True
        assert restored.shadow.enabled is True
        assert restored.outline.width == 2.0
        assert restored.title_position.x == 0.1


# ── TextAnimation ─────────────────────────────────────────────────────

class TestTextAnimation:
    def test_defaults(self):
        a = TextAnimation()
        assert a.target == "title"
        assert a.property == "opacity"
        assert a.keyframes == []
        assert a.preset is None
        assert a.preset_duration == 0.5

    def test_custom_keyframes(self):
        kf = [Keyframe(time_offset=0.0, value=0.0), Keyframe(time_offset=1.0, value=1.0)]
        a = TextAnimation(target="body", property="opacity", keyframes=kf)
        assert len(a.keyframes) == 2
        assert a.keyframes[0].value == 0.0
        assert a.keyframes[1].value == 1.0

    def test_preset_shorthand(self):
        a = TextAnimation(preset="fade_in", preset_duration=0.8)
        assert a.preset == "fade_in"
        assert a.preset_duration == 0.8

    def test_serialization_roundtrip(self):
        a = TextAnimation(
            target="title",
            property="x",
            keyframes=[Keyframe(time_offset=0.0, value=100.0)],
        )
        restored = TextAnimation(**json.loads(a.model_dump_json()))
        assert restored.keyframes[0].value == 100.0


# ── SlideTransition ───────────────────────────────────────────────────

class TestSlideTransition:
    def test_default_is_cut(self):
        t = SlideTransition()
        assert t.type == "cut"
        assert t.duration == 0.0

    def test_cross_dissolve(self):
        t = SlideTransition(type="cross_dissolve", duration=1.5)
        assert t.type == "cross_dissolve"
        assert t.duration == 1.5

    def test_all_types_serialize(self):
        for ttype in ["cut", "cross_dissolve", "gamma_cross", "wipe_single",
                       "wipe_double", "wipe_iris", "wipe_clock"]:
            t = SlideTransition(type=ttype, duration=0.5)
            restored = SlideTransition(**json.loads(t.model_dump_json()))
            assert restored.type == ttype


# ── SlideEffect ───────────────────────────────────────────────────────

class TestSlideEffect:
    def test_blur(self):
        e = SlideEffect(type="blur", size_x=10.0, size_y=10.0)
        assert e.type == "blur"
        assert e.size_x == 10.0

    def test_glow(self):
        e = SlideEffect(type="glow", threshold=0.5)
        assert e.threshold == 0.5

    def test_transform(self):
        e = SlideEffect(type="transform", translate_x=50.0, rotation=45.0, scale_x=1.5, scale_y=1.5)
        assert e.rotation == 45.0

    def test_speed(self):
        e = SlideEffect(type="speed", speed_factor=2.0)
        assert e.speed_factor == 2.0

    def test_irrelevant_fields_ignored(self):
        """Fields for other types should remain None."""
        e = SlideEffect(type="blur", size_x=5.0)
        assert e.speed_factor is None
        assert e.threshold is None

    def test_serialization_roundtrip(self):
        e = SlideEffect(type="transform", translate_x=10.0, translate_y=20.0)
        restored = SlideEffect(**json.loads(e.model_dump_json()))
        assert restored.translate_x == 10.0


# ── Expanded Slide ────────────────────────────────────────────────────

class TestExpandedSlide:
    def test_new_fields_default(self):
        s = Slide()
        assert s.template_id is None
        assert s.animations == []
        assert s.transition.type == "cut"
        assert s.effects == []

    def test_old_json_still_deserializes(self):
        """JSON from the original Slide (no new fields) must still load."""
        old_json = json.dumps({
            "id": "abc12345",
            "order": 0,
            "start_time": 0.0,
            "end_time": 5.0,
            "title": "Test",
            "body_text": "Body",
            "speaker_notes": "",
            "background_image_ref": None,
            "style_overrides": None,
        })
        s = Slide.model_validate_json(old_json)
        assert s.title == "Test"
        assert s.animations == []

    def test_slide_with_animations(self):
        s = Slide(
            title="Animated",
            animations=[TextAnimation(preset="fade_in")],
            transition=SlideTransition(type="cross_dissolve", duration=1.0),
            effects=[SlideEffect(type="blur", size_x=5.0)],
        )
        assert len(s.animations) == 1
        assert s.transition.type == "cross_dissolve"
        assert len(s.effects) == 1


# ── FrameTemplate ─────────────────────────────────────────────────────

class TestFrameTemplate:
    def test_minimal(self):
        t = FrameTemplate(id="ch", name="Chapter Title")
        assert t.id == "ch"
        assert t.name == "Chapter Title"
        assert t.style is None
        assert t.animations == []
        assert t.show_title is True
        assert t.show_body is True

    def test_full_template(self):
        t = FrameTemplate(
            id="content",
            name="Content Slide",
            description="Standard content layout",
            style=SlideStyleProps(text_alignment="left", shadow=TextShadow(enabled=True)),
            animations=[TextAnimation(preset="slide_down", target="title")],
            transition=SlideTransition(type="cross_dissolve", duration=0.5),
            effects=[],
            show_title=True,
            show_body=True,
        )
        assert t.style.shadow.enabled is True
        assert t.animations[0].preset == "slide_down"

    def test_serialization_roundtrip(self):
        t = FrameTemplate(
            id="quote",
            name="Quote",
            style=SlideStyleProps(use_italic=True),
            show_body=False,
        )
        restored = FrameTemplate(**json.loads(t.model_dump_json()))
        assert restored.id == "quote"
        assert restored.style.use_italic is True
        assert restored.show_body is False


# ── TemplateLibrary ───────────────────────────────────────────────────

class TestTemplateLibrary:
    def test_empty(self):
        lib = TemplateLibrary()
        assert lib.templates == {}
        assert lib.list_templates() == []

    def test_add_and_get(self):
        lib = TemplateLibrary()
        t = FrameTemplate(id="ch", name="Chapter")
        lib.add(t)
        assert lib.get("ch") is t

    def test_get_nonexistent(self):
        lib = TemplateLibrary()
        assert lib.get("missing") is None

    def test_remove(self):
        lib = TemplateLibrary()
        lib.add(FrameTemplate(id="x", name="X"))
        assert lib.remove("x") is True
        assert lib.get("x") is None

    def test_remove_nonexistent(self):
        lib = TemplateLibrary()
        assert lib.remove("missing") is False

    def test_list_templates(self):
        lib = TemplateLibrary()
        lib.add(FrameTemplate(id="a", name="A", description="First"))
        lib.add(FrameTemplate(id="b", name="B", description="Second"))
        listing = lib.list_templates()
        assert len(listing) == 2
        ids = {entry["id"] for entry in listing}
        assert ids == {"a", "b"}
        for entry in listing:
            assert "name" in entry
            assert "has_style" in entry

    def test_serialization_roundtrip(self):
        lib = TemplateLibrary()
        lib.add(FrameTemplate(id="t1", name="T1", style=SlideStyleProps()))
        lib.add(FrameTemplate(id="t2", name="T2"))
        restored = TemplateLibrary(**json.loads(lib.model_dump_json()))
        assert len(restored.templates) == 2
        assert restored.get("t1").style is not None


# ── Style Resolution Order ────────────────────────────────────────────

class TestStyleResolution:
    """Verify the intended style resolution: slide > template > global."""

    def test_slide_overrides_template_overrides_global(self):
        """Style resolution: slide > template > global.

        With Pydantic model_dump(), all fields (including defaults) are emitted,
        so each layer fully overwrites the previous. The priority order is:
        slide.style_overrides > template.style > collection.global_style.
        """
        global_style = SlideStyleProps(font_color="#AAAAAA", font_size_title=50)
        template = FrameTemplate(
            id="tmpl",
            name="Template",
            style=SlideStyleProps(font_color="#BBBBBB", font_size_body=28),
        )
        slide = Slide(
            style_overrides=SlideStyleProps(font_color="#CCCCCC"),
        )

        # Resolution: each layer fully overwrites; last layer wins
        resolved = global_style.model_dump()
        if template.style:
            resolved.update(template.style.model_dump())
        if slide.style_overrides:
            resolved.update(slide.style_overrides.model_dump())
        final = SlideStyleProps(**resolved)

        # slide override wins for font_color (it set #CCCCCC)
        assert final.font_color == "#CCCCCC"
        # slide's default font_size_body (36) overwrites template's 28
        assert final.font_size_body == 36
        # slide's default font_size_title (72) overwrites global's 50
        assert final.font_size_title == 72

    def test_resolution_with_only_template(self):
        """When no slide overrides, template wins over global."""
        global_style = SlideStyleProps(font_color="#AAAAAA")
        template = FrameTemplate(
            id="tmpl",
            name="Template",
            style=SlideStyleProps(font_color="#BBBBBB"),
        )

        resolved = global_style.model_dump()
        if template.style:
            resolved.update(template.style.model_dump())
        final = SlideStyleProps(**resolved)

        assert final.font_color == "#BBBBBB"

    def test_resolution_global_only(self):
        """When no template or slide overrides, global style is used as-is."""
        global_style = SlideStyleProps(font_color="#AAAAAA", padding=100)
        final = SlideStyleProps(**global_style.model_dump())
        assert final.font_color == "#AAAAAA"
        assert final.padding == 100


# ── Backward-compat shim ─────────────────────────────────────────────

class TestBackwardCompatShim:
    def test_import_from_frame(self):
        """The frame.py shim must still export the three original models."""
        from sdk.core.frame import Slide as FrameSlide
        from sdk.core.frame import SlideCollection as FrameCollection
        from sdk.core.frame import SlideStyleProps as FrameStyle

        assert FrameSlide is Slide
        assert FrameCollection is SlideCollection
        assert FrameStyle is SlideStyleProps
