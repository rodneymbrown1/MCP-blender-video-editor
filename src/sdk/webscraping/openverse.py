"""Openverse API client for image and audio search."""

import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

from .auth import OpenverseAuth, BASE_URL
from .images import ImageResult, RateLimiter

logger = logging.getLogger("VideoDraftMCP.webscraping.openverse")


@dataclass
class AudioResult:
    """A search result from Openverse audio."""
    id: str
    source: str
    title: str
    preview_url: str
    download_url: str
    duration: float = 0.0
    creator: str = ""
    license: str = ""
    license_url: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class _CacheEntry:
    results: list
    timestamp: float


class OpenverseClient:
    """Unified client for Openverse image and audio search."""

    CACHE_TTL = 900  # 15 minutes

    def __init__(self, repo_root: Optional[Path] = None):
        self._auth = OpenverseAuth(repo_root=repo_root)
        self._token: str = ""
        self._rate_limiter = RateLimiter(18, 60)  # 18 req/min conservative
        self._cache: dict[str, _CacheEntry] = {}

    def initialize(self, email: Optional[str] = None) -> None:
        """Authenticate with Openverse (or fall back to anonymous access)."""
        self._token = self._auth.ensure_authenticated(email=email)

    def _headers(self) -> dict[str, str]:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    def search_images(self, query: str, count: int = 5,
                      orientation: str = "landscape") -> list[ImageResult]:
        """Search Openverse for images."""
        cache_key = f"img:{query}:{count}:{orientation}"
        cached = self._cache.get(cache_key)
        if cached and (time.time() - cached.timestamp) < self.CACHE_TTL:
            return cached.results[:count]

        if not self._rate_limiter.acquire():
            logger.warning("Openverse rate limit reached")
            return []

        orientation_map = {
            "landscape": "wide",
            "portrait": "tall",
            "squarish": "square",
        }
        ov_orientation = orientation_map.get(orientation, orientation)

        params = {
            "q": query,
            "page_size": count,
        }
        if ov_orientation in ("wide", "tall", "square"):
            params["aspect_ratio"] = ov_orientation

        resp = requests.get(
            f"{BASE_URL}/v1/images/",
            params=params,
            headers=self._headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("results", []):
            results.append(ImageResult(
                id=item["id"],
                source="openverse",
                preview_url=item.get("thumbnail", ""),
                full_url=item.get("url", ""),
                download_url=item.get("url", ""),
                width=item.get("width", 0),
                height=item.get("height", 0),
                photographer=item.get("creator", ""),
                license=item.get("license", "CC"),
            ))

        self._cache[cache_key] = _CacheEntry(results=results, timestamp=time.time())
        return results[:count]

    def search_audio(self, query: str, count: int = 5,
                     duration_max: Optional[float] = None) -> list[AudioResult]:
        """Search Openverse for audio."""
        cache_key = f"aud:{query}:{count}:{duration_max}"
        cached = self._cache.get(cache_key)
        if cached and (time.time() - cached.timestamp) < self.CACHE_TTL:
            return cached.results[:count]

        if not self._rate_limiter.acquire():
            logger.warning("Openverse rate limit reached")
            return []

        params: dict = {
            "q": query,
            "page_size": count,
        }
        if duration_max is not None:
            if duration_max <= 30:
                params["length"] = "shortest"
            elif duration_max <= 120:
                params["length"] = "short"
            else:
                params["length"] = "medium"

        resp = requests.get(
            f"{BASE_URL}/v1/audio/",
            params=params,
            headers=self._headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("results", []):
            tags = [t.get("name", "") for t in item.get("tags", []) if t.get("name")]
            results.append(AudioResult(
                id=item["id"],
                source=item.get("source", "openverse"),
                title=item.get("title", ""),
                preview_url=item.get("thumbnail", ""),
                download_url=item.get("url", ""),
                duration=item.get("duration", 0.0) or 0.0,
                creator=item.get("creator", ""),
                license=item.get("license", ""),
                license_url=item.get("license_url", ""),
                tags=tags,
            ))

        self._cache[cache_key] = _CacheEntry(results=results, timestamp=time.time())
        return results[:count]

    def download(self, url: str, dest_dir: Path,
                 filename: Optional[str] = None) -> Path:
        """Download a file (image or audio) to dest_dir."""
        dest_dir.mkdir(parents=True, exist_ok=True)

        if not filename:
            ext = ".jpg"
            url_lower = url.lower()
            for candidate in [".png", ".webp", ".mp3", ".wav", ".ogg", ".flac"]:
                if candidate in url_lower:
                    ext = candidate
                    break
            filename = f"{uuid.uuid4().hex[:12]}{ext}"

        dest_path = dest_dir / filename
        response = requests.get(url, timeout=30, stream=True)
        response.raise_for_status()

        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info(f"Downloaded to {dest_path}")
        return dest_path

    def get_status(self) -> dict:
        """Report auth state and rate limit info."""
        return {
            "source": "openverse",
            "authenticated": bool(self._token),
            "remaining_requests": self._rate_limiter.tokens,
        }
