"""Tests for sdk.webscraping.images — RateLimiter, ImageSearcher, ImageResult."""

import os
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from sdk.webscraping.images import RateLimiter, ImageResult, ImageSearcher, _CacheEntry


# ── RateLimiter ─────────────────────────────────────────────────────────

class TestRateLimiter:
    def test_acquire_within_limit(self):
        limiter = RateLimiter(max_requests=5, period_seconds=60)
        for _ in range(5):
            assert limiter.acquire() is True

    def test_acquire_exceeds_limit(self):
        limiter = RateLimiter(max_requests=3, period_seconds=60)
        for _ in range(3):
            assert limiter.acquire() is True
        assert limiter.acquire() is False

    def test_tokens_refill_over_time(self):
        limiter = RateLimiter(max_requests=10, period_seconds=1.0)
        # Drain all tokens
        for _ in range(10):
            limiter.acquire()
        assert limiter.acquire() is False

        # Simulate time passing
        limiter.last_refill = time.time() - 1.1
        assert limiter.acquire() is True

    def test_single_token(self):
        limiter = RateLimiter(max_requests=1, period_seconds=60)
        assert limiter.acquire() is True
        assert limiter.acquire() is False


# ── ImageResult ─────────────────────────────────────────────────────────

class TestImageResult:
    def test_creation(self):
        r = ImageResult(
            id="abc123",
            source="unsplash",
            preview_url="https://example.com/preview.jpg",
            full_url="https://example.com/full.jpg",
            download_url="https://example.com/download.jpg",
            width=1920,
            height=1080,
            photographer="John Doe",
            license="Unsplash License",
        )
        assert r.id == "abc123"
        assert r.source == "unsplash"
        assert r.width == 1920
        assert r.photographer == "John Doe"

    def test_defaults(self):
        r = ImageResult(
            id="x", source="pexels",
            preview_url="u", full_url="u", download_url="u",
            width=100, height=100,
        )
        assert r.photographer == ""
        assert r.license == "free"


# ── ImageSearcher source status ─────────────────────────────────────────

class TestImageSearcherStatus:
    def test_no_keys_configured(self):
        with patch.dict(os.environ, {}, clear=True):
            searcher = ImageSearcher()
            status = searcher.get_source_status()
            assert status["unsplash"]["configured"] is False
            assert status["pexels"]["configured"] is False
            assert status["pixabay"]["configured"] is False

    def test_some_keys_configured(self):
        env = {"UNSPLASH_API_KEY": "test_key"}
        with patch.dict(os.environ, env, clear=True):
            searcher = ImageSearcher()
            status = searcher.get_source_status()
            assert status["unsplash"]["configured"] is True
            assert status["pexels"]["configured"] is False

    def test_all_keys_configured(self):
        env = {
            "UNSPLASH_API_KEY": "key1",
            "PEXELS_API_KEY": "key2",
            "PIXABAY_API_KEY": "key3",
        }
        with patch.dict(os.environ, env, clear=True):
            searcher = ImageSearcher()
            status = searcher.get_source_status()
            for source in ["unsplash", "pexels", "pixabay"]:
                assert status[source]["configured"] is True


# ── ImageSearcher search ────────────────────────────────────────────────

class TestImageSearcherSearch:
    def test_search_no_keys_returns_empty(self):
        with patch.dict(os.environ, {}, clear=True):
            searcher = ImageSearcher()
            results = searcher.search("sunset")
            assert results == []

    def test_search_uses_cache(self):
        with patch.dict(os.environ, {"UNSPLASH_API_KEY": "key"}, clear=True):
            searcher = ImageSearcher()
            fake_result = ImageResult(
                id="cached", source="unsplash",
                preview_url="p", full_url="f", download_url="d",
                width=800, height=600,
            )
            # Manually populate cache
            from sdk.webscraping.images import _CacheEntry
            searcher._cache["sunset:5:landscape"] = _CacheEntry(
                results=[fake_result], timestamp=time.time(),
            )

            results = searcher.search("sunset", count=5, orientation="landscape")
            assert len(results) == 1
            assert results[0].id == "cached"

    def test_search_cache_expires(self):
        with patch.dict(os.environ, {}, clear=True):
            searcher = ImageSearcher()
            from sdk.webscraping.images import _CacheEntry
            fake_result = ImageResult(
                id="old", source="unsplash",
                preview_url="p", full_url="f", download_url="d",
                width=800, height=600,
            )
            # Expired cache entry (16 minutes ago)
            searcher._cache["test:5:landscape"] = _CacheEntry(
                results=[fake_result], timestamp=time.time() - 960,
            )

            results = searcher.search("test", count=5, orientation="landscape")
            # No API keys, so should return empty even though cache existed
            assert results == []

    @patch("sdk.webscraping.images.requests.get")
    def test_search_unsplash_parses_response(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [{
                "id": "photo1",
                "urls": {
                    "small": "https://example.com/small.jpg",
                    "regular": "https://example.com/regular.jpg",
                    "full": "https://example.com/full.jpg",
                },
                "width": 1920,
                "height": 1080,
                "user": {"name": "Test Photographer"},
            }]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with patch.dict(os.environ, {"UNSPLASH_API_KEY": "test_key"}, clear=True):
            searcher = ImageSearcher()
            results = searcher.search("nature", count=1)
            assert len(results) == 1
            assert results[0].source == "unsplash"
            assert results[0].photographer == "Test Photographer"
            assert results[0].width == 1920

    @patch("sdk.webscraping.images.requests.get")
    def test_search_pexels_parses_response(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "photos": [{
                "id": 12345,
                "src": {
                    "medium": "https://example.com/medium.jpg",
                    "large2x": "https://example.com/large.jpg",
                    "original": "https://example.com/original.jpg",
                },
                "width": 2560,
                "height": 1440,
                "photographer": "Pexels User",
            }]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with patch.dict(os.environ, {"PEXELS_API_KEY": "test_key"}, clear=True):
            searcher = ImageSearcher()
            results = searcher.search("ocean", count=1)
            assert len(results) == 1
            assert results[0].source == "pexels"
            assert results[0].id == "12345"

    @patch("sdk.webscraping.images.requests.get")
    def test_search_handles_api_error(self, mock_get):
        mock_get.side_effect = Exception("API Error")

        with patch.dict(os.environ, {"UNSPLASH_API_KEY": "key"}, clear=True):
            searcher = ImageSearcher()
            results = searcher.search("test")
            assert results == []

    def test_search_respects_count(self):
        with patch.dict(os.environ, {"UNSPLASH_API_KEY": "key"}, clear=True):
            searcher = ImageSearcher()
            from sdk.webscraping.images import _CacheEntry
            fake_results = [
                ImageResult(
                    id=f"r{i}", source="unsplash",
                    preview_url="p", full_url="f", download_url="d",
                    width=800, height=600,
                )
                for i in range(10)
            ]
            searcher._cache["test:3:landscape"] = _CacheEntry(
                results=fake_results, timestamp=time.time(),
            )

            results = searcher.search("test", count=3, orientation="landscape")
            assert len(results) == 3


# ── ImageSearcher download ──────────────────────────────────────────────

class TestImageSearcherDownload:
    @patch("sdk.webscraping.images.requests.get")
    def test_download_creates_file(self, mock_get, tmp_path):
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"fake image data"]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        searcher = ImageSearcher()
        result = searcher.download(
            "https://example.com/photo.jpg",
            tmp_path / "images",
            filename="test.jpg",
        )

        assert result.exists()
        assert result.name == "test.jpg"
        assert result.read_bytes() == b"fake image data"

    @patch("sdk.webscraping.images.requests.get")
    def test_download_auto_filename(self, mock_get, tmp_path):
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"data"]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        searcher = ImageSearcher()
        result = searcher.download(
            "https://example.com/photo.jpg",
            tmp_path / "images",
        )

        assert result.exists()
        assert result.suffix == ".jpg"

    @patch("sdk.webscraping.images.requests.get")
    def test_download_creates_directory(self, mock_get, tmp_path):
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"data"]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        searcher = ImageSearcher()
        dest = tmp_path / "new_dir" / "sub"
        result = searcher.download("https://example.com/img.png", dest, "f.png")

        assert dest.exists()
        assert result.exists()

    @patch("sdk.webscraping.images.requests.get")
    def test_download_detects_png_extension(self, mock_get, tmp_path):
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"data"]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        searcher = ImageSearcher()
        result = searcher.download(
            "https://example.com/photo.PNG?w=500",
            tmp_path,
        )
        assert result.suffix == ".png"

    @patch("sdk.webscraping.images.requests.get")
    def test_download_detects_webp_extension(self, mock_get, tmp_path):
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"data"]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        searcher = ImageSearcher()
        result = searcher.download(
            "https://example.com/photo.webp",
            tmp_path,
        )
        assert result.suffix == ".webp"


# ── ImageSearcher Openverse fallback ───────────────────────────────────

class TestImageSearcherOpenverseFallback:
    def test_uses_openverse_when_no_api_keys(self):
        mock_ov = MagicMock()
        mock_ov.search_images.return_value = [
            ImageResult(
                id="ov1", source="openverse",
                preview_url="p", full_url="f", download_url="d",
                width=800, height=600,
            ),
        ]

        with patch.dict(os.environ, {}, clear=True):
            searcher = ImageSearcher(openverse_client=mock_ov)
            results = searcher.search("sunset", count=1)
            assert len(results) == 1
            assert results[0].source == "openverse"
            mock_ov.search_images.assert_called_once()

    @patch("sdk.webscraping.images.requests.get")
    def test_openverse_supplements_partial_results(self, mock_get):
        # Unsplash returns 1 result, need 3 total → Openverse fills remaining
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [{
                "id": "u1",
                "urls": {"small": "s", "regular": "r", "full": "f"},
                "width": 1920, "height": 1080,
                "user": {"name": "P"},
            }]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        mock_ov = MagicMock()
        mock_ov.search_images.return_value = [
            ImageResult(
                id="ov1", source="openverse",
                preview_url="p", full_url="f", download_url="d",
                width=800, height=600,
            ),
            ImageResult(
                id="ov2", source="openverse",
                preview_url="p", full_url="f", download_url="d",
                width=800, height=600,
            ),
        ]

        with patch.dict(os.environ, {"UNSPLASH_API_KEY": "key"}, clear=True):
            searcher = ImageSearcher(openverse_client=mock_ov)
            results = searcher.search("nature", count=3)
            assert len(results) == 3
            assert results[0].source == "unsplash"
            assert results[1].source == "openverse"
            mock_ov.search_images.assert_called_once_with(
                "nature", count=2, orientation="landscape",
            )

    def test_openverse_error_handled_gracefully(self):
        mock_ov = MagicMock()
        mock_ov.search_images.side_effect = Exception("Openverse down")

        with patch.dict(os.environ, {}, clear=True):
            searcher = ImageSearcher(openverse_client=mock_ov)
            results = searcher.search("test", count=5)
            assert results == []

    def test_openverse_status_included(self):
        mock_ov = MagicMock()
        mock_ov.get_status.return_value = {
            "source": "openverse",
            "authenticated": False,
            "remaining_requests": 18,
        }

        with patch.dict(os.environ, {}, clear=True):
            searcher = ImageSearcher(openverse_client=mock_ov)
            status = searcher.get_source_status()
            assert "openverse" in status
            assert status["openverse"]["source"] == "openverse"

    def test_no_openverse_client_no_fallback(self):
        with patch.dict(os.environ, {}, clear=True):
            searcher = ImageSearcher()
            results = searcher.search("sunset")
            assert results == []
