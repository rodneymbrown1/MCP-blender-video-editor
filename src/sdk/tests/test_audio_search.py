"""Tests for sdk.webscraping.audio — AudioSearcher delegation to OpenverseClient."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sdk.webscraping.audio import AudioSearcher
from sdk.webscraping.openverse import AudioResult, OpenverseClient


class TestAudioSearcherDelegation:
    def test_search_delegates_to_client(self):
        mock_client = MagicMock(spec=OpenverseClient)
        expected = [
            AudioResult(id="1", source="freesound", title="Rain",
                        preview_url="p", download_url="d"),
        ]
        mock_client.search_audio.return_value = expected

        searcher = AudioSearcher(openverse_client=mock_client)
        results = searcher.search("rain", count=3, duration_max=60)

        mock_client.search_audio.assert_called_once_with("rain", count=3, duration_max=60)
        assert results == expected

    def test_download_delegates_to_client(self, tmp_path):
        mock_client = MagicMock(spec=OpenverseClient)
        expected_path = tmp_path / "audio.mp3"
        mock_client.download.return_value = expected_path

        searcher = AudioSearcher(openverse_client=mock_client)
        result = searcher.download("https://example.com/track.mp3", tmp_path, "audio.mp3")

        mock_client.download.assert_called_once_with(
            "https://example.com/track.mp3", tmp_path, filename="audio.mp3",
        )
        assert result == expected_path

    def test_status_delegates_to_client(self):
        mock_client = MagicMock(spec=OpenverseClient)
        mock_client.get_status.return_value = {
            "source": "openverse",
            "authenticated": True,
            "remaining_requests": 15,
        }

        searcher = AudioSearcher(openverse_client=mock_client)
        status = searcher.get_source_status()

        mock_client.get_status.assert_called_once()
        assert status["source"] == "openverse"

    def test_creates_default_client(self):
        searcher = AudioSearcher()
        assert searcher._client is not None
