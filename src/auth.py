from __future__ import annotations

import json
from pathlib import Path

import msal
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from loguru import logger

from .config import Config

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/contacts.readonly",
]


class TokenManager:
    def __init__(self, client_secret_path: str, token_path: str) -> None:
        self._client_secret_path = Path(client_secret_path)
        self._token_path = Path(token_path)
        self._cached_creds: Credentials | None = None

    def load_token(self) -> Credentials | None:
        if not self._token_path.exists():
            return None
        try:
            data = json.loads(self._token_path.read_text())
            return Credentials.from_authorized_user_info(data, SCOPES)  # type: ignore[no-any-return,no-untyped-call]
        except Exception as e:
            logger.warning(f"Failed to load token: {e}")
            return None

    def save_token(self, creds: Credentials) -> None:
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_path.write_text(creds.to_json())  # type: ignore[no-untyped-call]
        logger.info("Token saved")

    def get_credentials(self) -> Credentials:
        if self._cached_creds and self._cached_creds.valid:
            return self._cached_creds

        creds = self.load_token()
        if creds is None:
            raise RuntimeError("Not authenticated. Run: python -m gmail_mcp auth")

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                logger.info("Refreshing expired token")
                creds.refresh(Request())  # type: ignore[no-untyped-call]
                self.save_token(creds)
            else:
                raise RuntimeError(
                    "Token invalid and cannot refresh. Run: python -m gmail_mcp auth"
                )

        self._cached_creds = creds
        return creds


MICROSOFT_SCOPES = [
    "https://graph.microsoft.com/Mail.ReadWrite",
    "https://graph.microsoft.com/Mail.Send",
    "https://graph.microsoft.com/User.Read",
]


class MicrosoftTokenManager:
    def __init__(self, client_id: str, tenant_id: str, token_path: str) -> None:
        self._client_id = client_id
        self._tenant_id = tenant_id
        self._token_path = Path(token_path)
        self._cache: msal.SerializableTokenCache | None = None
        self._app: msal.PublicClientApplication | None = None

    def _load_cache(self) -> msal.SerializableTokenCache:
        cache = msal.SerializableTokenCache()
        if self._token_path.exists():
            cache.deserialize(self._token_path.read_text())
        return cache

    def _save_cache(self) -> None:
        if self._cache and self._cache.has_state_changed:
            self._token_path.parent.mkdir(parents=True, exist_ok=True)
            self._token_path.write_text(self._cache.serialize())

    def _get_app(self) -> msal.PublicClientApplication:
        if self._app is None:
            self._cache = self._load_cache()
            self._app = msal.PublicClientApplication(
                self._client_id,
                authority=f"https://login.microsoftonline.com/{self._tenant_id}",
                token_cache=self._cache,
            )
        return self._app

    def get_token(self) -> str:
        app = self._get_app()
        accounts = app.get_accounts()
        if not accounts:
            raise RuntimeError(
                "Not authenticated. Run: python -m gmail_mcp auth --provider outlook"
            )
        result = app.acquire_token_silent(MICROSOFT_SCOPES, account=accounts[0])
        if not result or "access_token" not in result:
            raise RuntimeError(
                "Token expired and cannot refresh. Run: python -m gmail_mcp auth --provider outlook"
            )
        self._save_cache()
        return result["access_token"]

    def run_interactive_auth(self) -> None:
        app = self._get_app()
        result = app.acquire_token_interactive(MICROSOFT_SCOPES)
        if "access_token" not in result:
            error = result.get("error_description", result.get("error", "Unknown"))
            raise RuntimeError(f"Authentication failed: {error}")
        self._save_cache()
        logger.info("Microsoft auth successful")


def run_auth_flow(cfg: Config, provider: str = "gmail") -> None:
    if provider == "gmail":
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

    elif provider == "outlook":
        accounts_path = Path(cfg.accounts_path)
        client_id = ""
        tenant_id = ""
        account_email = ""

        if accounts_path.exists():
            accounts_data = json.loads(accounts_path.read_text())
            for acc in accounts_data.get("accounts", []):
                if acc.get("provider") == "outlook":
                    azure = acc.get("azure", {})
                    client_id = azure.get("client_id", "")
                    tenant_id = azure.get("tenant_id", "")
                    account_email = acc.get("email", "")
                    break

        if not client_id:
            client_id = input("Microsoft Application (client) ID: ").strip()
        if not tenant_id:
            tenant_id = input("Microsoft Directory (tenant) ID: ").strip()

        if not client_id or not tenant_id:
            print("ERROR: client_id and tenant_id are required.")
            return

        token_dir = f"credentials/{account_email}" if account_email else "credentials"
        token_path = str(Path(token_dir) / "token.json")
        ms_mgr = MicrosoftTokenManager(client_id, tenant_id, token_path)
        ms_mgr.run_interactive_auth()
        print(f"Microsoft authentication successful! Token saved to {token_path}")

    else:
        print(f"ERROR: Unknown provider '{provider}'. Use 'gmail' or 'outlook'.")
