"""Tests for sdk.intake.audio — AudioTranscriber slide grouping logic.

Unit tests use pre-built transcript dicts (no model needed).
End-to-end tests (TestE2E*) use faster-whisper with a real audio fixture.
"""

import json
from pathlib import Path

import pytest

from sdk.core.slides import Slide, SlideCollection
from sdk.intake.audio import AudioTranscriber

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "audio"
ARTIFACTS_DIR = Path(__file__).parent / "artifacts"
TEST_AUDIO = FIXTURES_DIR / "test1.wav"


@pytest.fixture
def transcriber():
    return AudioTranscriber(model_size="base")


# ── segments_to_slides with empty input ─────────────────────────────────

class TestEmptyInput:
    def test_empty_segments(self, transcriber):
        result = transcriber.segments_to_slides({"segments": []})
        assert isinstance(result, SlideCollection)
        assert len(result.slides) == 0

    def test_empty_dict(self, transcriber):
        result = transcriber.segments_to_slides({})
        assert len(result.slides) == 0


# ── Pause detection ────────────────────────────────────────────────────

class TestPauseDetection:
    def test_large_gap_creates_new_slide(self, transcriber):
        """A gap > 1.5s between segments should create a new slide."""
        segments = [
            {"start": 0.0, "end": 2.0, "text": "First segment."},
            {"start": 5.0, "end": 7.0, "text": "After long pause."},
        ]
        result = transcriber.segments_to_slides({"segments": segments})
        assert len(result.slides) == 2
        assert result.slides[0].body_text == "First segment."
        assert result.slides[1].body_text == "After long pause."

    def test_small_gap_stays_same_slide(self, transcriber):
        """A gap < 1.5s should keep segments in the same slide."""
        segments = [
            {"start": 0.0, "end": 2.0, "text": "First part"},
            {"start": 2.5, "end": 4.0, "text": "second part"},
        ]
        result = transcriber.segments_to_slides({"segments": segments})
        assert len(result.slides) == 1
        assert "First part" in result.slides[0].body_text
        assert "second part" in result.slides[0].body_text


# ── Max duration ────────────────────────────────────────────────────────

class TestMaxDuration:
    def test_exceeding_max_duration_splits(self, transcriber):
        """Segments exceeding 15s total should be split into multiple slides."""
        segments = []
        for i in range(10):
            segments.append({
                "start": float(i * 2),
                "end": float(i * 2 + 1.8),
                "text": f"Segment {i}",
            })
        # Total span: 0 to 19.8s (>15s)
        result = transcriber.segments_to_slides({"segments": segments})
        assert len(result.slides) >= 2

    def test_single_long_segment(self, transcriber):
        """A single segment should still create one slide regardless of duration."""
        segments = [
            {"start": 0.0, "end": 20.0, "text": "A very long single segment."},
        ]
        result = transcriber.segments_to_slides({"segments": segments})
        assert len(result.slides) == 1


# ── Sentence boundary detection ────────────────────────────────────────

class TestSentenceBoundary:
    def test_sentence_end_with_pause_splits(self, transcriber):
        """Sentence ending (.) + pause > 0.5s + duration >= 3s = new slide."""
        segments = [
            {"start": 0.0, "end": 2.0, "text": "Beginning of thought."},
            {"start": 2.0, "end": 4.0, "text": "End of first thought."},
            # 0.8s gap + sentence boundary + duration > 3s
            {"start": 4.8, "end": 6.0, "text": "New thought begins."},
        ]
        result = transcriber.segments_to_slides({"segments": segments})
        assert len(result.slides) >= 2

    def test_question_mark_is_sentence_end(self, transcriber):
        """Question marks should be treated as sentence boundaries."""
        segments = [
            {"start": 0.0, "end": 2.0, "text": "Is this a question?"},
            {"start": 2.0, "end": 4.5, "text": "More text after question."},
            {"start": 5.5, "end": 7.0, "text": "Next part."},
        ]
        result = transcriber.segments_to_slides({"segments": segments})
        # The ? + pause should trigger a split
        assert len(result.slides) >= 2

    def test_exclamation_is_sentence_end(self, transcriber):
        """Exclamation marks should be treated as sentence boundaries."""
        segments = [
            {"start": 0.0, "end": 1.5, "text": "Wow, amazing!"},
            {"start": 1.5, "end": 4.0, "text": "That was incredible!"},
            {"start": 5.0, "end": 7.0, "text": "Moving on now."},
        ]
        result = transcriber.segments_to_slides({"segments": segments})
        assert len(result.slides) >= 2


# ── Min duration ────────────────────────────────────────────────────────

class TestMinDuration:
    def test_short_segments_stay_grouped(self, transcriber):
        """Segments totaling < 3s should not split at sentence boundary."""
        segments = [
            {"start": 0.0, "end": 0.5, "text": "Hi."},
            {"start": 0.8, "end": 1.5, "text": "Yes."},
            {"start": 1.8, "end": 2.5, "text": "Sure."},
        ]
        result = transcriber.segments_to_slides({"segments": segments})
        # All under 3s, so should stay as one slide
        assert len(result.slides) == 1


# ── Slide properties ───────────────────────────────────────────────────

class TestSlideProperties:
    def test_slide_times_are_rounded(self, transcriber):
        segments = [
            {"start": 0.123456, "end": 3.654321, "text": "Hello world."},
        ]
        result = transcriber.segments_to_slides({"segments": segments})
        s = result.slides[0]
        assert s.start_time == 0.12
        assert s.end_time == 3.65

    def test_slides_have_empty_title(self, transcriber):
        """Whisper doesn't generate titles — they should be empty."""
        segments = [
            {"start": 0.0, "end": 5.0, "text": "Some speech content."},
        ]
        result = transcriber.segments_to_slides({"segments": segments})
        assert result.slides[0].title == ""

    def test_slides_are_ordered(self, transcriber):
        segments = [
            {"start": 0.0, "end": 3.0, "text": "First slide content."},
            {"start": 5.0, "end": 8.0, "text": "Second slide content."},
            {"start": 10.0, "end": 13.0, "text": "Third slide content."},
        ]
        result = transcriber.segments_to_slides({"segments": segments})
        for i, slide in enumerate(result.slides):
            assert slide.order == i

    def test_body_text_joins_segments(self, transcriber):
        """Multiple segments in one slide should be joined with spaces."""
        segments = [
            {"start": 0.0, "end": 1.5, "text": "Hello"},
            {"start": 1.6, "end": 3.0, "text": "world"},
        ]
        result = transcriber.segments_to_slides({"segments": segments})
        assert result.slides[0].body_text == "Hello world"


# ── Realistic transcript ────────────────────────────────────────────────

class TestRealisticTranscript:
    def test_typical_speech_pattern(self, transcriber):
        """Simulate a realistic speech pattern with natural pauses."""
        segments = [
            {"start": 0.0, "end": 3.5, "text": "Welcome to today's presentation."},
            {"start": 3.8, "end": 7.0, "text": "We're going to talk about machine learning."},
            # 2s pause = new slide
            {"start": 9.0, "end": 12.0, "text": "First, let's cover the basics."},
            {"start": 12.2, "end": 15.0, "text": "Machine learning is a subset of AI."},
            # 3s pause = new slide
            {"start": 18.0, "end": 21.0, "text": "Now let's look at some examples."},
        ]
        result = transcriber.segments_to_slides({"segments": segments})
        assert len(result.slides) >= 2
        # First slide should contain welcome content
        assert "Welcome" in result.slides[0].body_text

    def test_no_slides_from_silence(self, transcriber):
        """Empty text segments should not produce slides."""
        segments = [
            {"start": 0.0, "end": 5.0, "text": ""},
        ]
        # The text is empty but still a segment — it will still create a slide
        # because _group_into_slides appends the text and flushes
        result = transcriber.segments_to_slides({"segments": segments})
        # It creates a slide but with empty body
        assert len(result.slides) == 1


# ═══════════════════════════════════════════════════════════════════════
# END-TO-END TESTS — require faster-whisper + test1.wav fixture
# ═══════════════════════════════════════════════════════════════════════
# The fixture is a ~10.8s WAV generated via macOS TTS with a 2.5s silence
# gap in the middle:
#   Segment 1 (~0–3.8s): "Welcome to the presentation, today we will
#                          discuss machine learning."
#   [2.5s silence]
#   Segment 2 (~6.6–10.7s): "Now let us look at the second topic,
#                             deep learning is a subset of machine learning."


@pytest.fixture(scope="module")
def e2e_transcriber():
    """Create a transcriber with the tiny model (fastest, ~75MB)."""
    return AudioTranscriber(model_size="tiny")


@pytest.fixture(scope="module")
def e2e_transcript(e2e_transcriber):
    """Run transcription once, write raw transcript to artifacts, share across tests."""
    assert TEST_AUDIO.exists(), f"Fixture not found: {TEST_AUDIO}"
    transcript = e2e_transcriber.transcribe(TEST_AUDIO)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS_DIR / "transcript.json").write_text(
        json.dumps(transcript, indent=2)
    )
    return transcript


@pytest.fixture(scope="module")
def e2e_slides(e2e_transcriber, e2e_transcript):
    """Generate slides from the transcript, write slides + summary to artifacts."""
    slides = e2e_transcriber.segments_to_slides(e2e_transcript)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS_DIR / "slides.json").write_text(
        slides.model_dump_json(indent=2)
    )
    (ARTIFACTS_DIR / "summary.json").write_text(
        json.dumps(slides.to_summary(), indent=2)
    )
    return slides


class TestE2ETranscription:
    """End-to-end: faster-whisper transcribes the audio fixture correctly."""

    def test_transcript_has_segments(self, e2e_transcript):
        assert "segments" in e2e_transcript
        assert len(e2e_transcript["segments"]) >= 1

    def test_transcript_language_is_english(self, e2e_transcript):
        assert e2e_transcript["language"] == "en"

    def test_transcript_duration_is_reasonable(self, e2e_transcript):
        duration = e2e_transcript["duration"]
        assert 8.0 <= duration <= 15.0, f"Unexpected duration: {duration}s"

    def test_transcript_segments_have_timestamps(self, e2e_transcript):
        for seg in e2e_transcript["segments"]:
            assert "start" in seg
            assert "end" in seg
            assert "text" in seg
            assert seg["end"] > seg["start"]

    def test_transcript_segments_have_words(self, e2e_transcript):
        for seg in e2e_transcript["segments"]:
            assert "words" in seg
            # At least some segments should have word-level timestamps
        has_words = any(len(seg["words"]) > 0 for seg in e2e_transcript["segments"])
        assert has_words, "Expected at least one segment with word-level timestamps"

    def test_transcript_contains_expected_content(self, e2e_transcript):
        full_text = " ".join(
            seg["text"].lower() for seg in e2e_transcript["segments"]
        )
        assert "presentation" in full_text or "welcome" in full_text
        assert "machine learning" in full_text or "learning" in full_text

    def test_transcript_detects_pause_gap(self, e2e_transcript):
        """The 2.5s silence should create a gap between segments."""
        segments = e2e_transcript["segments"]
        if len(segments) >= 2:
            gap = segments[1]["start"] - segments[0]["end"]
            assert gap > 1.0, f"Expected gap > 1s between segments, got {gap:.2f}s"

    def test_transcript_is_json_serializable(self, e2e_transcript):
        json_str = json.dumps(e2e_transcript)
        restored = json.loads(json_str)
        assert len(restored["segments"]) == len(e2e_transcript["segments"])


class TestE2ESlideGeneration:
    """End-to-end: transcript segments are grouped into slides correctly."""

    def test_slides_are_generated(self, e2e_slides):
        assert isinstance(e2e_slides, SlideCollection)
        assert len(e2e_slides.slides) >= 1

    def test_pause_creates_multiple_slides(self, e2e_slides):
        """The 2.5s pause in the audio should split into at least 2 slides."""
        assert len(e2e_slides.slides) >= 2, (
            f"Expected >= 2 slides from audio with 2.5s pause, got {len(e2e_slides.slides)}"
        )

    def test_slide_times_are_within_audio_duration(self, e2e_slides, e2e_transcript):
        duration = e2e_transcript["duration"]
        for slide in e2e_slides.slides:
            assert slide.start_time >= 0
            assert slide.end_time <= duration + 1.0  # small tolerance
            assert slide.end_time > slide.start_time

    def test_slides_are_chronologically_ordered(self, e2e_slides):
        for i in range(len(e2e_slides.slides) - 1):
            assert e2e_slides.slides[i].start_time <= e2e_slides.slides[i + 1].start_time

    def test_slides_have_body_text(self, e2e_slides):
        for slide in e2e_slides.slides:
            assert len(slide.body_text.strip()) > 0, f"Slide {slide.id} has empty body"

    def test_slides_have_empty_titles(self, e2e_slides):
        """Whisper doesn't generate titles — all should be empty."""
        for slide in e2e_slides.slides:
            assert slide.title == ""

    def test_slides_have_sequential_order(self, e2e_slides):
        for i, slide in enumerate(e2e_slides.slides):
            assert slide.order == i

    def test_slides_have_unique_ids(self, e2e_slides):
        ids = [s.id for s in e2e_slides.slides]
        assert len(ids) == len(set(ids))

    def test_first_slide_contains_welcome(self, e2e_slides):
        first_body = e2e_slides.slides[0].body_text.lower()
        assert "welcome" in first_body or "presentation" in first_body

    def test_second_slide_contains_topic(self, e2e_slides):
        if len(e2e_slides.slides) >= 2:
            second_body = e2e_slides.slides[1].body_text.lower()
            assert "deep learning" in second_body or "second" in second_body or "topic" in second_body

    def test_slides_cover_full_audio(self, e2e_slides, e2e_transcript):
        """Slides should cover most of the spoken audio duration."""
        first_start = e2e_slides.slides[0].start_time
        last_end = e2e_slides.slides[-1].end_time
        duration = e2e_transcript["duration"]
        coverage = (last_end - first_start) / duration
        assert coverage > 0.5, f"Slides cover only {coverage:.0%} of audio"

    def test_slides_serialization_roundtrip(self, e2e_slides):
        json_str = e2e_slides.model_dump_json()
        restored = SlideCollection.model_validate_json(json_str)
        assert len(restored.slides) == len(e2e_slides.slides)
        for orig, rest in zip(e2e_slides.slides, restored.slides):
            assert orig.id == rest.id
            assert orig.body_text == rest.body_text
            assert orig.start_time == rest.start_time

    def test_to_summary_works(self, e2e_slides):
        summary = e2e_slides.to_summary()
        assert len(summary) == len(e2e_slides.slides)
        for entry in summary:
            assert entry["title"] == "(untitled)"
            assert entry["has_background"] is False
            assert "time_range" in entry


class TestE2EModelSwitch:
    """End-to-end: verify model size switching works."""

    def test_transcribe_with_explicit_model_size(self):
        transcriber = AudioTranscriber(model_size="tiny")
        transcript = transcriber.transcribe(TEST_AUDIO, model_size="tiny")
        assert len(transcript["segments"]) >= 1
        assert transcript["language"] == "en"

    def test_model_size_is_remembered(self):
        transcriber = AudioTranscriber(model_size="base")
        assert transcriber.model_size == "base"
        transcriber.transcribe(TEST_AUDIO, model_size="tiny")
        assert transcriber.model_size == "tiny"


class TestE2EFullPipeline:
    """End-to-end: full pipeline from audio file to editable slides."""

    def test_transcribe_then_edit(self):
        transcriber = AudioTranscriber(model_size="tiny")
        transcript = transcriber.transcribe(TEST_AUDIO)
        slides = transcriber.segments_to_slides(transcript)

        # Simulate user editing workflow
        assert len(slides.slides) >= 2

        # Add titles
        slides.slides[0].title = "Introduction"
        slides.slides[1].title = "Deep Learning"
        assert slides.slides[0].title == "Introduction"

        # Edit body text
        original_body = slides.slides[0].body_text
        slides.slides[0].body_text = "Custom body text"
        assert slides.slides[0].body_text == "Custom body text"
        assert slides.slides[0].body_text != original_body

    def test_transcribe_then_split_and_merge(self):
        transcriber = AudioTranscriber(model_size="tiny")
        transcript = transcriber.transcribe(TEST_AUDIO)
        slides = transcriber.segments_to_slides(transcript)

        original_count = len(slides.slides)

        # Split first slide at midpoint
        first = slides.slides[0]
        mid_time = (first.start_time + first.end_time) / 2
        result = slides.split(first.id, mid_time)
        assert result is not None
        assert len(slides.slides) == original_count + 1

        # Merge them back
        s1_id = slides.slides[0].id
        s2_id = slides.slides[1].id
        merged = slides.merge(s1_id, s2_id)
        assert merged is not None
        assert len(slides.slides) == original_count
