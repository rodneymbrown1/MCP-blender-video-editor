"""Tests for sdk.webscraping.auth — OpenverseCredentials, OpenverseAuth."""

import json
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from sdk.webscraping.auth import OpenverseCredentials, OpenverseAuth


# ── OpenverseCredentials ───────────────────────────────────────────────

class TestOpenverseCredentials:
    def test_creation(self):
        creds = OpenverseCredentials(
            client_id="cid",
            client_secret="csec",
            name="test",
            email="test@example.com",
        )
        assert creds.client_id == "cid"
        assert creds.client_secret == "csec"
        assert creds.name == "test"
        assert creds.email == "test@example.com"

    def test_defaults(self):
        creds = OpenverseCredentials()
        assert creds.client_id == ""
        assert creds.access_token == ""
        assert creds.token_expires_at == 0.0

    def test_token_valid_when_active(self):
        creds = OpenverseCredentials(
            access_token="tok",
            token_expires_at=time.time() + 3600,
        )
        assert creds.is_token_valid() is True

    def test_token_invalid_when_expired(self):
        creds = OpenverseCredentials(
            access_token="tok",
            token_expires_at=time.time() - 100,
        )
        assert creds.is_token_valid() is False

    def test_token_invalid_within_buffer(self):
        creds = OpenverseCredentials(
            access_token="tok",
            token_expires_at=time.time() + 200,  # within 5-min buffer
        )
        assert creds.is_token_valid() is False

    def test_token_invalid_when_empty(self):
        creds = OpenverseCredentials()
        assert creds.is_token_valid() is False

    def test_roundtrip_serialization(self):
        original = OpenverseCredentials(
            client_id="cid",
            client_secret="csec",
            name="test",
            email="a@b.com",
            access_token="tok",
            token_expires_at=12345.0,
        )
        data = original.to_dict()
        restored = OpenverseCredentials.from_dict(data)
        assert restored.client_id == original.client_id
        assert restored.client_secret == original.client_secret
        assert restored.access_token == original.access_token
        assert restored.token_expires_at == original.token_expires_at

    def test_from_dict_ignores_unknown_fields(self):
        data = {"client_id": "cid", "unknown_field": "value"}
        creds = OpenverseCredentials.from_dict(data)
        assert creds.client_id == "cid"


# ── OpenverseAuth persistence ─────────────────────────────────────────

class TestOpenverseAuthPersistence:
    def test_save_and_load(self, tmp_path):
        auth = OpenverseAuth(repo_root=tmp_path)
        auth._credentials = OpenverseCredentials(
            client_id="cid", client_secret="csec",
            name="test", email="a@b.com",
        )
        auth.save_credentials()

        auth2 = OpenverseAuth(repo_root=tmp_path)
        loaded = auth2.load_credentials()
        assert loaded is not None
        assert loaded.client_id == "cid"
        assert loaded.client_secret == "csec"

    def test_load_nonexistent_file(self, tmp_path):
        auth = OpenverseAuth(repo_root=tmp_path)
        assert auth.load_credentials() is None

    def test_load_corrupt_file(self, tmp_path):
        creds_dir = tmp_path / ".credentials"
        creds_dir.mkdir()
        (creds_dir / "openverse.json").write_text("not valid json{{{")

        auth = OpenverseAuth(repo_root=tmp_path)
        assert auth.load_credentials() is None

    def test_save_creates_nested_dirs(self, tmp_path):
        auth = OpenverseAuth(repo_root=tmp_path)
        auth._credentials = OpenverseCredentials(client_id="x")
        auth.save_credentials()

        assert (tmp_path / ".credentials" / "openverse.json").exists()

    def test_save_with_no_credentials_is_noop(self, tmp_path):
        auth = OpenverseAuth(repo_root=tmp_path)
        auth.save_credentials()
        assert not (tmp_path / ".credentials" / "openverse.json").exists()


# ── OpenverseAuth register ────────────────────────────────────────────

class TestOpenverseAuthRegister:
    @patch("sdk.webscraping.auth.requests.post")
    def test_register_success(self, mock_post, tmp_path):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "client_id": "new_cid",
            "client_secret": "new_csec",
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        auth = OpenverseAuth(repo_root=tmp_path)
        creds = auth.register("myapp", "desc", "a@b.com")

        assert creds.client_id == "new_cid"
        assert creds.client_secret == "new_csec"
        assert creds.email == "a@b.com"
        # Should have saved to disk
        assert (tmp_path / ".credentials" / "openverse.json").exists()

    @patch("sdk.webscraping.auth.requests.post")
    def test_register_api_error(self, mock_post, tmp_path):
        mock_post.side_effect = Exception("API Error")
        auth = OpenverseAuth(repo_root=tmp_path)
        with pytest.raises(Exception, match="API Error"):
            auth.register("myapp", "desc", "a@b.com")


# ── OpenverseAuth token ───────────────────────────────────────────────

class TestOpenverseAuthToken:
    @patch("sdk.webscraping.auth.requests.post")
    def test_get_token_fresh(self, mock_post, tmp_path):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "access_token": "new_token",
            "expires_in": 43200,
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        auth = OpenverseAuth(repo_root=tmp_path)
        auth._credentials = OpenverseCredentials(
            client_id="cid", client_secret="csec",
        )

        token = auth.get_token()
        assert token == "new_token"

    def test_get_token_cached(self, tmp_path):
        auth = OpenverseAuth(repo_root=tmp_path)
        auth._credentials = OpenverseCredentials(
            client_id="cid",
            client_secret="csec",
            access_token="cached_token",
            token_expires_at=time.time() + 3600,
        )

        token = auth.get_token()
        assert token == "cached_token"

    def test_get_token_no_credentials(self, tmp_path):
        auth = OpenverseAuth(repo_root=tmp_path)
        with pytest.raises(RuntimeError, match="No credentials"):
            auth.get_token()


# ── OpenverseAuth ensure_authenticated ─────────────────────────────────

class TestOpenverseAuthEnsure:
    def test_load_existing_credentials(self, tmp_path):
        # Pre-save credentials with a valid token
        creds_dir = tmp_path / ".credentials"
        creds_dir.mkdir()
        creds = OpenverseCredentials(
            client_id="cid",
            client_secret="csec",
            access_token="existing_token",
            token_expires_at=time.time() + 3600,
        )
        (creds_dir / "openverse.json").write_text(json.dumps(creds.to_dict()))

        auth = OpenverseAuth(repo_root=tmp_path)
        token = auth.ensure_authenticated()
        assert token == "existing_token"

    def test_no_creds_no_email_anonymous(self, tmp_path):
        auth = OpenverseAuth(repo_root=tmp_path)
        token = auth.ensure_authenticated()
        assert token == ""

    @patch("sdk.webscraping.auth.requests.post")
    def test_no_creds_with_email_auto_registers(self, mock_post, tmp_path):
        # First call: register, second call: token
        register_resp = MagicMock()
        register_resp.json.return_value = {
            "client_id": "auto_cid",
            "client_secret": "auto_csec",
        }
        register_resp.raise_for_status = MagicMock()

        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "auto_token",
            "expires_in": 43200,
        }
        token_resp.raise_for_status = MagicMock()

        mock_post.side_effect = [register_resp, token_resp]

        auth = OpenverseAuth(repo_root=tmp_path)
        token = auth.ensure_authenticated(email="user@example.com")
        assert token == "auto_token"
        assert mock_post.call_count == 2
