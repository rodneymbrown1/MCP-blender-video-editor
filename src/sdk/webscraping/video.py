"""Video scraping via yt-dlp (experimental, behind optional dependency)."""

import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("VideoDraftMCP.webscraping.video")

# Rate limit: max 3 downloads per hour
_download_timestamps: list[float] = []
MAX_DOWNLOADS_PER_HOUR = 3


def _check_rate_limit() -> bool:
    """Check if we're within the download rate limit."""
    now = time.time()
    cutoff = now - 3600
    _download_timestamps[:] = [t for t in _download_timestamps if t > cutoff]
    return len(_download_timestamps) < MAX_DOWNLOADS_PER_HOUR


def download_video(url: str, dest_dir: Path, max_resolution: int = 720,
                   cc_only: bool = True) -> Path:
    """Download a video using yt-dlp with Creative Commons filter.

    Requires the 'video' optional dependency: pip install video-draft-mcp[video]
    """
    try:
        import yt_dlp
    except ImportError:
        raise ImportError(
            "yt-dlp is not installed. Install with: pip install video-draft-mcp[video]"
        )

    if not _check_rate_limit():
        raise RuntimeError("Rate limit exceeded: max 3 video downloads per hour")

    dest_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        'format': f'bestvideo[height<={max_resolution}]+bestaudio/best[height<={max_resolution}]',
        'outtmpl': str(dest_dir / '%(title)s.%(ext)s'),
        'restrictfilenames': True,
        'noplaylist': True,
        'quiet': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

        # Check Creative Commons license if required
        if cc_only:
            license_str = (info.get('license') or '').lower()
            if 'creative commons' not in license_str and 'cc' not in license_str:
                raise ValueError(
                    f"Video license '{info.get('license', 'unknown')}' "
                    "is not Creative Commons. Set cc_only=False to override."
                )

        ydl.download([url])

    _download_timestamps.append(time.time())

    # Find the downloaded file
    filename = ydl.prepare_filename(info)
    result_path = Path(filename)
    logger.info(f"Downloaded video to {result_path}")
    return result_path
