"""Audio transcription via faster-whisper for slide generation."""

import logging
from pathlib import Path
from typing import Optional

from ..core.frame import Slide, SlideCollection

logger = logging.getLogger("VideoDraftMCP.intake.audio")


class AudioTranscriber:
    """Transcribes audio files using faster-whisper and groups into slides."""

    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self._model = None

    def _get_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            logger.info(f"Loading faster-whisper model '{self.model_size}' (CPU, int8)...")
            self._model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8",
            )
            logger.info("Model loaded successfully")
        return self._model

    def transcribe(self, audio_path: str | Path, model_size: Optional[str] = None) -> dict:
        """Transcribe an audio file and return segments with word-level timestamps.

        Returns:
            dict with keys: segments (list), language, duration
        """
        if model_size and model_size != self.model_size:
            self.model_size = model_size
            self._model = None

        model = self._get_model()
        audio_path = str(audio_path)

        segments_raw, info = model.transcribe(
            audio_path,
            word_timestamps=True,
            vad_filter=True,
        )

        segments = []
        for seg in segments_raw:
            segment_data = {
                "start": seg.start,
                "end": seg.end,
                "text": seg.text.strip(),
                "words": [],
            }
            if seg.words:
                for w in seg.words:
                    segment_data["words"].append({
                        "word": w.word,
                        "start": w.start,
                        "end": w.end,
                        "probability": w.probability,
                    })
            segments.append(segment_data)

        return {
            "segments": segments,
            "language": info.language,
            "duration": info.duration,
        }

    def segments_to_slides(self, transcript: dict) -> SlideCollection:
        """Group transcript segments into slides using pause/sentence detection."""
        segments = transcript.get("segments", [])
        if not segments:
            return SlideCollection()

        return self._group_into_slides(segments)

    def _group_into_slides(self, segments: list[dict]) -> SlideCollection:
        """Group transcript segments into slides.

        Rules:
        - Gap > 1.5s between segments = new slide
        - Sentence boundary (. ? !) at end of segment = potential new slide
        - Max slide duration: 15s
        - Min slide duration: 3s
        """
        MAX_DURATION = 15.0
        MIN_DURATION = 3.0
        PAUSE_THRESHOLD = 1.5

        collection = SlideCollection()
        if not segments:
            return collection

        current_texts: list[str] = []
        current_start = segments[0]["start"]
        current_end = segments[0]["end"]

        def flush_slide():
            nonlocal current_texts, current_start, current_end
            if current_texts:
                body = " ".join(current_texts)
                slide = Slide(
                    start_time=round(current_start, 2),
                    end_time=round(current_end, 2),
                    title="",
                    body_text=body,
                )
                collection.add(slide)
                current_texts = []

        for i, seg in enumerate(segments):
            seg_start = seg["start"]
            seg_end = seg["end"]
            seg_text = seg["text"]

            # Check for pause gap (new slide boundary)
            if current_texts and (seg_start - current_end) > PAUSE_THRESHOLD:
                flush_slide()
                current_start = seg_start

            # Check max duration
            if current_texts and (seg_end - current_start) > MAX_DURATION:
                flush_slide()
                current_start = seg_start

            current_texts.append(seg_text)
            current_end = seg_end

            # Check sentence boundary + sufficient duration
            is_sentence_end = seg_text.rstrip().endswith(('.', '?', '!'))
            duration_so_far = current_end - current_start

            if is_sentence_end and duration_so_far >= MIN_DURATION:
                # Check if next segment has a pause
                if i + 1 < len(segments):
                    next_gap = segments[i + 1]["start"] - seg_end
                    if next_gap > 0.5:  # moderate pause after sentence = good split point
                        flush_slide()
                        if i + 1 < len(segments):
                            current_start = segments[i + 1]["start"]

        # Flush remaining text
        flush_slide()

        return collection
