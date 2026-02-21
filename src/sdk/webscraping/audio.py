"""Audio sourcing via Openverse API."""

import logging
from pathlib import Path
from typing import Optional

from .openverse import AudioResult, OpenverseClient

logger = logging.getLogger("VideoDraftMCP.webscraping.audio")


class AudioSearcher:
    """Audio search and download powered by Openverse."""

    def __init__(self, openverse_client: Optional[OpenverseClient] = None):
        self._client = openverse_client or OpenverseClient()

    def search(self, query: str, count: int = 5,
               duration_max: Optional[float] = None) -> list[AudioResult]:
        """Search for audio tracks."""
        return self._client.search_audio(query, count=count, duration_max=duration_max)

    def download(self, url: str, dest_dir: Path,
                 filename: Optional[str] = None) -> Path:
        """Download an audio file."""
        return self._client.download(url, dest_dir, filename=filename)

    def get_source_status(self) -> dict:
        """Report Openverse audio source status."""
        return self._client.get_status()
