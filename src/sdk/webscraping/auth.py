"""Openverse API credential management and authentication."""

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger("VideoDraftMCP.webscraping.auth")

BASE_URL = "https://api.openverse.org"
CREDENTIALS_DIR = ".credentials"
CREDENTIALS_FILE = "openverse.json"


@dataclass
class OpenverseCredentials:
    """Stored credentials for the Openverse API."""
    client_id: str = ""
    client_secret: str = ""
    name: str = ""
    email: str = ""
    access_token: str = ""
    token_expires_at: float = 0.0

    def is_token_valid(self) -> bool:
        """Check if the access token is still valid (with 5-minute buffer)."""
        if not self.access_token:
            return False
        return time.time() < (self.token_expires_at - 300)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "OpenverseCredentials":
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


class OpenverseAuth:
    """Handles Openverse API registration, token exchange, and credential persistence."""

    def __init__(self, repo_root: Optional[Path] = None):
        if repo_root is None:
            repo_root = Path(__file__).resolve().parent.parent.parent.parent
        self._creds_path = repo_root / CREDENTIALS_DIR / CREDENTIALS_FILE
        self._credentials: Optional[OpenverseCredentials] = None

    def load_credentials(self) -> Optional[OpenverseCredentials]:
        """Load credentials from disk. Returns None if file doesn't exist or is corrupt."""
        if not self._creds_path.exists():
            return None
        try:
            data = json.loads(self._creds_path.read_text())
            self._credentials = OpenverseCredentials.from_dict(data)
            return self._credentials
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.warning(f"Corrupt credentials file, ignoring: {e}")
            return None

    def save_credentials(self) -> None:
        """Write current credentials to disk, creating directories as needed."""
        if self._credentials is None:
            return
        self._creds_path.parent.mkdir(parents=True, exist_ok=True)
        self._creds_path.write_text(json.dumps(self._credentials.to_dict(), indent=2))

    def register(self, name: str, description: str, email: str) -> OpenverseCredentials:
        """Register a new application with the Openverse API."""
        resp = requests.post(
            f"{BASE_URL}/v1/auth_tokens/register/",
            json={
                "name": name,
                "description": description,
                "email": email,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        self._credentials = OpenverseCredentials(
            client_id=data["client_id"],
            client_secret=data["client_secret"],
            name=name,
            email=email,
        )
        self.save_credentials()
        return self._credentials

    def get_token(self) -> str:
        """Exchange client credentials for an access token. Auto-refreshes when expired."""
        if self._credentials is None:
            raise RuntimeError("No credentials available. Register first.")

        if self._credentials.is_token_valid():
            return self._credentials.access_token

        resp = requests.post(
            f"{BASE_URL}/v1/auth_tokens/token/",
            data={
                "grant_type": "client_credentials",
                "client_id": self._credentials.client_id,
                "client_secret": self._credentials.client_secret,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        self._credentials.access_token = data["access_token"]
        self._credentials.token_expires_at = time.time() + data.get("expires_in", 43200)
        self.save_credentials()
        return self._credentials.access_token

    def ensure_authenticated(self, email: Optional[str] = None) -> str:
        """Full authentication lifecycle: load → register if needed → get token.

        Returns an access token, or empty string for anonymous mode
        (when no email provided and no saved credentials exist).
        """
        creds = self.load_credentials()

        if creds and creds.client_id:
            self._credentials = creds
            return self.get_token()

        if not email:
            logger.info("No credentials and no email — using anonymous access")
            return ""

        self.register(
            name="video-draft-mcp",
            description="Video Draft MCP SDK",
            email=email,
        )
        return self.get_token()
