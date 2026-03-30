from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from loguru import logger

from .config import Config

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]


class TokenManager:
    def __init__(self, client_secret_path: str, token_path: str) -> None:
        self._client_secret_path = Path(client_secret_path)
        self._token_path = Path(token_path)
        self._cached_creds: Optional[Credentials] = None

    def load_token(self) -> Optional[Credentials]:
        if not self._token_path.exists():
            return None
        try:
            data = json.loads(self._token_path.read_text())
            return Credentials.from_authorized_user_info(data, SCOPES)
        except Exception as e:
            logger.warning(f"Failed to load token: {e}")
            return None

    def save_token(self, creds: Credentials) -> None:
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_path.write_text(creds.to_json())
        logger.info("Token saved")

    def get_credentials(self) -> Credentials:
        if self._cached_creds and self._cached_creds.valid:
            return self._cached_creds

        creds = self.load_token()
        if creds is None:
            raise RuntimeError(
                "Not authenticated. Run: python -m gmail_mcp auth"
            )

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                logger.info("Refreshing expired token")
                creds.refresh(Request())
                self.save_token(creds)
            else:
                raise RuntimeError(
                    "Token invalid and cannot refresh. Run: python -m gmail_mcp auth"
                )

        self._cached_creds = creds
        return creds


def run_auth_flow(cfg: Config) -> None:
    if not Path(cfg.client_secret_path).exists():
        logger.error(f"Client secret not found: {cfg.client_secret_path}")
        print(f"ERROR: Place client_secret.json at {cfg.client_secret_path}")
        print("Download from: Google Cloud Console > APIs & Services > Credentials")
        return

    flow = InstalledAppFlow.from_client_secrets_file(cfg.client_secret_path, SCOPES)
    creds = flow.run_local_server(port=0)

    mgr = TokenManager(cfg.client_secret_path, cfg.token_path)
    mgr.save_token(creds)
    print("Authentication successful! Token saved.")
