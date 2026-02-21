"""Tests for sdk.core.frame — Slide, SlideCollection, SlideStyleProps."""

import json
import pytest

from sdk.core.slides import Slide, SlideCollection, SlideStyleProps


# ── SlideStyleProps ─────────────────────────────────────────────────────

class TestSlideStyleProps:
    def test_defaults(self):
        s = SlideStyleProps()
        assert s.font_family == "Bfont"
        assert s.font_size_title == 72
        assert s.font_size_body == 36
        assert s.font_color == "#FFFFFF"
        assert s.background_color == "#1A1A2E"
        assert s.text_alignment == "center"
        assert s.padding == 40

    def test_custom_values(self):
        s = SlideStyleProps(font_family="Arial", font_color="#000000", padding=100)
        assert s.font_family == "Arial"
        assert s.font_color == "#000000"
        assert s.padding == 100

    def test_serialization_roundtrip(self):
        s = SlideStyleProps(font_size_title=80, background_color="#FF0000")
        data = s.model_dump()
        restored = SlideStyleProps(**data)
        assert restored == s


# ── Slide ───────────────────────────────────────────────────────────────

class TestSlide:
    def test_auto_id(self):
        s = Slide()
        assert len(s.id) == 8
        # Two slides get different IDs
        s2 = Slide()
        assert s.id != s2.id

    def test_duration_property(self):
        s = Slide(start_time=1.5, end_time=4.5)
        assert s.duration == pytest.approx(3.0)

    def test_duration_zero(self):
        s = Slide(start_time=0.0, end_time=0.0)
        assert s.duration == 0.0

    def test_fields(self):
        s = Slide(
            id="abc12345",
            order=2,
            start_time=10.0,
            end_time=20.0,
            title="My Title",
            body_text="Hello world.",
            speaker_notes="Remember to pause.",
            background_image_ref="/path/to/img.jpg",
        )
        assert s.id == "abc12345"
        assert s.order == 2
        assert s.title == "My Title"
        assert s.background_image_ref == "/path/to/img.jpg"

    def test_style_overrides_none_by_default(self):
        s = Slide()
        assert s.style_overrides is None

    def test_style_overrides_set(self):
        style = SlideStyleProps(font_color="#FF0000")
        s = Slide(style_overrides=style)
        assert s.style_overrides.font_color == "#FF0000"

    def test_serialization_roundtrip(self):
        s = Slide(title="Test", body_text="Body", start_time=1.0, end_time=5.0)
        data = json.loads(s.model_dump_json())
        restored = Slide(**data)
        assert restored.title == s.title
        assert restored.start_time == s.start_time
        assert restored.id == s.id


# ── SlideCollection ─────────────────────────────────────────────────────

class TestSlideCollection:
    def _make_collection(self, n=3) -> SlideCollection:
        c = SlideCollection()
        for i in range(n):
            c.add(Slide(
                start_time=float(i * 5),
                end_time=float(i * 5 + 5),
                title=f"Slide {i}",
                body_text=f"Body text for slide {i}.",
            ))
        return c

    # ── get ──

    def test_get_existing(self):
        c = self._make_collection()
        slide = c.slides[1]
        found = c.get(slide.id)
        assert found is slide

    def test_get_nonexistent(self):
        c = self._make_collection()
        assert c.get("nonexistent") is None

    # ── add ──

    def test_add_assigns_order(self):
        c = SlideCollection()
        s1 = c.add(Slide(title="First"))
        s2 = c.add(Slide(title="Second"))
        assert s1.order == 0
        assert s2.order == 1

    def test_add_to_empty(self):
        c = SlideCollection()
        s = c.add(Slide(title="Only"))
        assert s.order == 0
        assert len(c.slides) == 1

    # ── remove ──

    def test_remove_existing(self):
        c = self._make_collection(3)
        target_id = c.slides[1].id
        result = c.remove(target_id)
        assert result is True
        assert len(c.slides) == 2
        assert c.get(target_id) is None

    def test_remove_reindexes(self):
        c = self._make_collection(3)
        c.remove(c.slides[0].id)
        assert c.slides[0].order == 0
        assert c.slides[1].order == 1

    def test_remove_nonexistent(self):
        c = self._make_collection()
        assert c.remove("nonexistent") is False
        assert len(c.slides) == 3

    # ── split ──

    def test_split_basic(self):
        c = SlideCollection()
        s = c.add(Slide(
            start_time=0.0,
            end_time=10.0,
            body_text="First sentence. Second sentence. Third sentence. Fourth sentence.",
        ))
        result = c.split(s.id, at_time=5.0)
        assert result is not None
        s1, s2 = result
        assert s1.end_time == 5.0
        assert s2.start_time == 5.0
        assert s2.end_time == 10.0
        assert len(c.slides) == 2

    def test_split_preserves_order(self):
        c = self._make_collection(3)
        mid_slide = c.slides[1]
        mid_time = (mid_slide.start_time + mid_slide.end_time) / 2
        c.split(mid_slide.id, at_time=mid_time)
        assert len(c.slides) == 4
        for i, s in enumerate(c.slides):
            assert s.order == i

    def test_split_invalid_time_before_start(self):
        c = SlideCollection()
        s = c.add(Slide(start_time=5.0, end_time=10.0))
        assert c.split(s.id, at_time=3.0) is None

    def test_split_invalid_time_after_end(self):
        c = SlideCollection()
        s = c.add(Slide(start_time=5.0, end_time=10.0))
        assert c.split(s.id, at_time=12.0) is None

    def test_split_invalid_time_at_boundary(self):
        c = SlideCollection()
        s = c.add(Slide(start_time=5.0, end_time=10.0))
        assert c.split(s.id, at_time=5.0) is None
        assert c.split(s.id, at_time=10.0) is None

    def test_split_nonexistent(self):
        c = self._make_collection()
        assert c.split("nonexistent", 5.0) is None

    # ── merge ──

    def test_merge_adjacent(self):
        c = self._make_collection(3)
        id1 = c.slides[0].id
        id2 = c.slides[1].id
        original_end = c.slides[1].end_time

        merged = c.merge(id1, id2)
        assert merged is not None
        assert merged.end_time == original_end
        assert len(c.slides) == 2

    def test_merge_combines_text(self):
        c = SlideCollection()
        s1 = c.add(Slide(body_text="Hello", speaker_notes="Note A"))
        s2 = c.add(Slide(body_text="World", speaker_notes="Note B"))
        merged = c.merge(s1.id, s2.id)
        assert "Hello" in merged.body_text
        assert "World" in merged.body_text
        assert "Note A" in merged.speaker_notes
        assert "Note B" in merged.speaker_notes

    def test_merge_reversed_order(self):
        """Merge should work regardless of argument order."""
        c = self._make_collection(3)
        id1 = c.slides[0].id
        id2 = c.slides[1].id
        merged = c.merge(id2, id1)  # reversed
        assert merged is not None
        assert len(c.slides) == 2

    def test_merge_nonexistent(self):
        c = self._make_collection()
        assert c.merge("nonexistent", c.slides[0].id) is None
        assert c.merge(c.slides[0].id, "nonexistent") is None

    def test_merge_reindexes(self):
        c = self._make_collection(3)
        c.merge(c.slides[0].id, c.slides[1].id)
        for i, s in enumerate(c.slides):
            assert s.order == i

    # ── reorder ──

    def test_reorder_reverses(self):
        c = self._make_collection(3)
        ids = [s.id for s in c.slides]
        reversed_ids = list(reversed(ids))
        assert c.reorder(reversed_ids) is True
        assert [s.id for s in c.slides] == reversed_ids
        for i, s in enumerate(c.slides):
            assert s.order == i

    def test_reorder_wrong_ids(self):
        c = self._make_collection(3)
        assert c.reorder(["a", "b", "c"]) is False

    def test_reorder_missing_id(self):
        c = self._make_collection(3)
        ids = [s.id for s in c.slides]
        ids[0] = "wrong"
        assert c.reorder(ids) is False

    def test_reorder_extra_id(self):
        c = self._make_collection(3)
        ids = [s.id for s in c.slides] + ["extra"]
        assert c.reorder(ids) is False

    # ── to_summary ──

    def test_to_summary(self):
        c = self._make_collection(2)
        summary = c.to_summary()
        assert len(summary) == 2
        assert "id" in summary[0]
        assert "order" in summary[0]
        assert "time_range" in summary[0]
        assert "title" in summary[0]
        assert "body_snippet" in summary[0]
        assert "has_background" in summary[0]

    def test_to_summary_truncates_long_body(self):
        c = SlideCollection()
        c.add(Slide(body_text="x" * 200))
        summary = c.to_summary()
        assert summary[0]["body_snippet"].endswith("...")
        assert len(summary[0]["body_snippet"]) == 83  # 80 + "..."

    def test_to_summary_untitled(self):
        c = SlideCollection()
        c.add(Slide(title=""))
        summary = c.to_summary()
        assert summary[0]["title"] == "(untitled)"

    def test_to_summary_has_background(self):
        c = SlideCollection()
        c.add(Slide(background_image_ref="/path/img.jpg"))
        c.add(Slide())
        summary = c.to_summary()
        assert summary[0]["has_background"] is True
        assert summary[1]["has_background"] is False

    # ── serialization ──

    def test_collection_json_roundtrip(self):
        c = self._make_collection(3)
        c.global_style = SlideStyleProps(font_color="#FF0000")
        json_str = c.model_dump_json()
        restored = SlideCollection.model_validate_json(json_str)
        assert len(restored.slides) == 3
        assert restored.global_style.font_color == "#FF0000"
        for orig, rest in zip(c.slides, restored.slides):
            assert orig.id == rest.id
            assert orig.title == rest.title
            assert orig.start_time == rest.start_time
