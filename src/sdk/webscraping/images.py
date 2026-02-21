"""Multi-source image search and download (Unsplash, Pexels, Pixabay)."""

import hashlib
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger("VideoDraftMCP.webscraping.images")


class RateLimiter:
    """Simple token-bucket rate limiter per source."""

    def __init__(self, max_requests: int, period_seconds: float):
        self.max_requests = max_requests
        self.period = period_seconds
        self.tokens = max_requests
        self.last_refill = time.time()

    def acquire(self) -> bool:
        now = time.time()
        elapsed = now - self.last_refill
        refill = int(elapsed / self.period * self.max_requests)
        if refill > 0:
            self.tokens = min(self.max_requests, self.tokens + refill)
            self.last_refill = now

        if self.tokens > 0:
            self.tokens -= 1
            return True
        return False


@dataclass
class ImageResult:
    """A search result from any image source."""
    id: str
    source: str  # "unsplash", "pexels", "pixabay"
    preview_url: str
    full_url: str
    download_url: str
    width: int
    height: int
    photographer: str = ""
    license: str = "free"


@dataclass
class _CacheEntry:
    results: list[ImageResult]
    timestamp: float


class ImageSearcher:
    """Multi-source free image search with rate limiting and caching."""

    CACHE_TTL = 900  # 15 minutes

    def __init__(self):
        self._rate_limiters: dict[str, RateLimiter] = {
            "unsplash": RateLimiter(50, 3600),   # 50/hour
            "pexels": RateLimiter(200, 3600),     # 200/hour
            "pixabay": RateLimiter(100, 60),      # 100/minute
        }
        self._cache: dict[str, _CacheEntry] = {}

    @staticmethod
    def _get_api_key(source: str) -> Optional[str]:
        env_map = {
            "unsplash": "UNSPLASH_API_KEY",
            "pexels": "PEXELS_API_KEY",
            "pixabay": "PIXABAY_API_KEY",
        }
        return os.environ.get(env_map.get(source, ""))

    def get_source_status(self) -> dict[str, dict]:
        """Report which image sources are configured."""
        status = {}
        for source in ["unsplash", "pexels", "pixabay"]:
            key = self._get_api_key(source)
            limiter = self._rate_limiters[source]
            status[source] = {
                "configured": bool(key),
                "remaining_requests": limiter.tokens,
            }
        return status

    def search(self, query: str, count: int = 5,
               min_width: int = 1280,
               orientation: str = "landscape") -> list[ImageResult]:
        """Search multiple sources for images, rotating through available APIs."""
        cache_key = f"{query}:{count}:{orientation}"
        cached = self._cache.get(cache_key)
        if cached and (time.time() - cached.timestamp) < self.CACHE_TTL:
            return cached.results[:count]

        results: list[ImageResult] = []
        per_source = max(1, (count + 2) // 3)

        # Try each source
        for source in ["unsplash", "pexels", "pixabay"]:
            if len(results) >= count:
                break
            key = self._get_api_key(source)
            if not key:
                continue
            if not self._rate_limiters[source].acquire():
                logger.warning(f"Rate limit reached for {source}")
                continue

            try:
                if source == "unsplash":
                    results.extend(self._search_unsplash(query, per_source, orientation, key))
                elif source == "pexels":
                    results.extend(self._search_pexels(query, per_source, orientation, key))
                elif source == "pixabay":
                    results.extend(self._search_pixabay(query, per_source, min_width, orientation, key))
            except Exception as e:
                logger.error(f"Error searching {source}: {e}")

        self._cache[cache_key] = _CacheEntry(results=results, timestamp=time.time())
        return results[:count]

    def download(self, url: str, dest_dir: Path, filename: Optional[str] = None) -> Path:
        """Download an image to the specified directory."""
        dest_dir.mkdir(parents=True, exist_ok=True)

        if not filename:
            ext = ".jpg"
            if ".png" in url.lower():
                ext = ".png"
            elif ".webp" in url.lower():
                ext = ".webp"
            filename = f"{uuid.uuid4().hex[:12]}{ext}"

        dest_path = dest_dir / filename
        response = requests.get(url, timeout=30, stream=True)
        response.raise_for_status()

        with open(dest_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info(f"Downloaded image to {dest_path}")
        return dest_path

    # ── Source-specific search methods ──────────────────────────────────

    def _search_unsplash(self, query: str, count: int, orientation: str,
                         api_key: str) -> list[ImageResult]:
        resp = requests.get(
            "https://api.unsplash.com/search/photos",
            params={
                "query": query,
                "per_page": count,
                "orientation": orientation,
            },
            headers={"Authorization": f"Client-ID {api_key}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("results", []):
            results.append(ImageResult(
                id=item["id"],
                source="unsplash",
                preview_url=item["urls"]["small"],
                full_url=item["urls"]["regular"],
                download_url=item["urls"]["full"],
                width=item["width"],
                height=item["height"],
                photographer=item.get("user", {}).get("name", ""),
                license="Unsplash License",
            ))
        return results

    def _search_pexels(self, query: str, count: int, orientation: str,
                       api_key: str) -> list[ImageResult]:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            params={
                "query": query,
                "per_page": count,
                "orientation": orientation,
            },
            headers={"Authorization": api_key},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("photos", []):
            results.append(ImageResult(
                id=str(item["id"]),
                source="pexels",
                preview_url=item["src"]["medium"],
                full_url=item["src"]["large2x"],
                download_url=item["src"]["original"],
                width=item["width"],
                height=item["height"],
                photographer=item.get("photographer", ""),
                license="Pexels License",
            ))
        return results

    def _search_pixabay(self, query: str, count: int, min_width: int,
                        orientation: str, api_key: str) -> list[ImageResult]:
        resp = requests.get(
            "https://pixabay.com/api/",
            params={
                "key": api_key,
                "q": query,
                "per_page": count,
                "min_width": min_width,
                "orientation": orientation,
                "image_type": "photo",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("hits", []):
            results.append(ImageResult(
                id=str(item["id"]),
                source="pixabay",
                preview_url=item["webformatURL"],
                full_url=item["largeImageURL"],
                download_url=item["largeImageURL"],
                width=item["imageWidth"],
                height=item["imageHeight"],
                photographer=item.get("user", ""),
                license="Pixabay License",
            ))
        return results
