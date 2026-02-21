"""Tests for sdk.webscraping.openverse — OpenverseClient, AudioResult."""

import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from sdk.webscraping.openverse import AudioResult, OpenverseClient
from sdk.webscraping.images import ImageResult


# ── AudioResult ────────────────────────────────────────────────────────

class TestAudioResult:
    def test_creation(self):
        r = AudioResult(
            id="abc",
            source="freesound",
            title="Rain Sounds",
            preview_url="https://example.com/preview.mp3",
            download_url="https://example.com/download.mp3",
            duration=120.5,
            creator="AudioPerson",
            license="CC-BY",
            license_url="https://creativecommons.org/licenses/by/4.0/",
            tags=["rain", "nature"],
        )
        assert r.id == "abc"
        assert r.title == "Rain Sounds"
        assert r.duration == 120.5
        assert r.tags == ["rain", "nature"]

    def test_defaults(self):
        r = AudioResult(
            id="x", source="openverse", title="t",
            preview_url="p", download_url="d",
        )
        assert r.duration == 0.0
        assert r.creator == ""
        assert r.license == ""
        assert r.tags == []

    def test_tags_list(self):
        r = AudioResult(
            id="x", source="s", title="t",
            preview_url="p", download_url="d",
            tags=["ambient", "electronic", "chill"],
        )
        assert len(r.tags) == 3
        assert "ambient" in r.tags


# ── OpenverseClient image search ───────────────────────────────────────

class TestOpenverseClientImageSearch:
    @patch("sdk.webscraping.openverse.requests.get")
    def test_parse_response(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [{
                "id": "img1",
                "thumbnail": "https://example.com/thumb.jpg",
                "url": "https://example.com/full.jpg",
                "width": 1920,
                "height": 1080,
                "creator": "Photographer",
                "license": "CC-BY",
            }]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client = OpenverseClient()
        results = client.search_images("sunset", count=1)

        assert len(results) == 1
        assert results[0].source == "openverse"
        assert results[0].width == 1920
        assert results[0].photographer == "Photographer"

    @patch("sdk.webscraping.openverse.requests.get")
    def test_empty_results(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": []}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client = OpenverseClient()
        results = client.search_images("xyznonexistent")
        assert results == []

    @patch("sdk.webscraping.openverse.requests.get")
    def test_api_error(self, mock_get):
        mock_get.side_effect = Exception("API Error")

        client = OpenverseClient()
        with pytest.raises(Exception, match="API Error"):
            client.search_images("test")

    @patch("sdk.webscraping.openverse.requests.get")
    def test_cache_hit(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [{
                "id": "img1",
                "thumbnail": "t",
                "url": "u",
                "width": 100,
                "height": 100,
                "creator": "",
                "license": "CC",
            }]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client = OpenverseClient()
        # First call hits API
        results1 = client.search_images("sunset", count=1)
        # Second call should use cache
        results2 = client.search_images("sunset", count=1)

        assert mock_get.call_count == 1
        assert len(results2) == 1

    @patch("sdk.webscraping.openverse.requests.get")
    def test_orientation_mapping(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": []}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client = OpenverseClient()
        client.search_images("test", orientation="landscape")

        call_args = mock_get.call_args
        assert call_args[1]["params"]["aspect_ratio"] == "wide"

    @patch("sdk.webscraping.openverse.requests.get")
    def test_portrait_orientation_mapping(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": []}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client = OpenverseClient()
        client.search_images("test", orientation="portrait")

        call_args = mock_get.call_args
        assert call_args[1]["params"]["aspect_ratio"] == "tall"


# ── OpenverseClient audio search ──────────────────────────────────────

class TestOpenverseClientAudioSearch:
    @patch("sdk.webscraping.openverse.requests.get")
    def test_parse_response_with_tags(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [{
                "id": "aud1",
                "source": "freesound",
                "title": "Rain",
                "thumbnail": "https://example.com/thumb.jpg",
                "url": "https://example.com/audio.mp3",
                "duration": 45.0,
                "creator": "SoundArtist",
                "license": "CC-BY",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "tags": [
                    {"name": "rain"},
                    {"name": "nature"},
                    {"name": "ambient"},
                ],
            }]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client = OpenverseClient()
        results = client.search_audio("rain", count=1)

        assert len(results) == 1
        assert results[0].title == "Rain"
        assert results[0].duration == 45.0
        assert results[0].tags == ["rain", "nature", "ambient"]

    @patch("sdk.webscraping.openverse.requests.get")
    def test_duration_filter_shortest(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": []}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client = OpenverseClient()
        client.search_audio("test", duration_max=20)

        call_args = mock_get.call_args
        assert call_args[1]["params"]["length"] == "shortest"

    @patch("sdk.webscraping.openverse.requests.get")
    def test_duration_filter_short(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": []}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client = OpenverseClient()
        client.search_audio("test", duration_max=60)

        call_args = mock_get.call_args
        assert call_args[1]["params"]["length"] == "short"

    @patch("sdk.webscraping.openverse.requests.get")
    def test_duration_filter_medium(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": []}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client = OpenverseClient()
        client.search_audio("test", duration_max=300)

        call_args = mock_get.call_args
        assert call_args[1]["params"]["length"] == "medium"

    @patch("sdk.webscraping.openverse.requests.get")
    def test_no_duration_filter(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": []}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client = OpenverseClient()
        client.search_audio("test")

        call_args = mock_get.call_args
        assert "length" not in call_args[1]["params"]


# ── OpenverseClient download ──────────────────────────────────────────

class TestOpenverseClientDownload:
    @patch("sdk.webscraping.openverse.requests.get")
    def test_download_image(self, mock_get, tmp_path):
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [b"fake image data"]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client = OpenverseClient()
        result = client.download(
            "https://example.com/photo.jpg",
            tmp_path / "images",
            filename="test.jpg",
        )

        assert result.exists()
        assert result.name == "test.jpg"
        assert result.read_bytes() == b"fake image data"

    @patch("sdk.webscraping.openverse.requests.get")
    def test_download_audio_auto_extension(self, mock_get, tmp_path):
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [b"audio data"]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client = OpenverseClient()
        result = client.download(
            "https://example.com/track.mp3",
            tmp_path / "audio",
        )

        assert result.exists()
        assert result.suffix == ".mp3"

    @patch("sdk.webscraping.openverse.requests.get")
    def test_download_wav_extension(self, mock_get, tmp_path):
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [b"wav data"]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client = OpenverseClient()
        result = client.download(
            "https://example.com/sound.wav?dl=1",
            tmp_path / "audio",
        )

        assert result.exists()
        assert result.suffix == ".wav"

    @patch("sdk.webscraping.openverse.requests.get")
    def test_download_creates_directory(self, mock_get, tmp_path):
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [b"data"]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client = OpenverseClient()
        dest = tmp_path / "new" / "nested" / "dir"
        result = client.download("https://example.com/f.jpg", dest, "f.jpg")

        assert dest.exists()
        assert result.exists()

    @patch("sdk.webscraping.openverse.requests.get")
    def test_download_default_jpg_extension(self, mock_get, tmp_path):
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [b"data"]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        client = OpenverseClient()
        result = client.download(
            "https://example.com/unknown_format",
            tmp_path,
        )

        assert result.suffix == ".jpg"


# ── OpenverseClient status ────────────────────────────────────────────

class TestOpenverseClientStatus:
    def test_status_anonymous(self):
        client = OpenverseClient()
        status = client.get_status()
        assert status["source"] == "openverse"
        assert status["authenticated"] is False

    def test_status_authenticated(self):
        client = OpenverseClient()
        client._token = "some_token"
        status = client.get_status()
        assert status["authenticated"] is True
