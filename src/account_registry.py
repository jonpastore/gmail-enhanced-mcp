from __future__ import annotations

from typing import Any

from .email_client import EmailClient


class AccountRegistry:
    def __init__(self) -> None:
        self._accounts: dict[str, EmailClient] = {}
        self._default: str | None = None

    def register(self, email: str, client: EmailClient, default: bool = False) -> None:
        self._accounts[email] = client
        if default or self._default is None:
            self._default = email

    def get(self, email: str | None = None) -> EmailClient:
        if email is not None:
            client = self._accounts.get(email)
            if client is None:
                available = ", ".join(self._accounts.keys()) or "none"
                raise ValueError(f"Unknown account: {email}. Available: {available}")
            return client
        if self._default is None:
            raise ValueError("No accounts registered")
        return self._accounts[self._default]

    def load_from_config(self, cfg: Any) -> None:
        accounts = cfg.load_accounts()
        default = cfg.get_default_account()
        for acc in accounts:
            email = acc["email"]
            provider = acc["provider"]
            if provider == "gmail":
                from .auth import TokenManager
                from .gmail_client import GmailClient

                token_path = f"credentials/{email}/token.json"
                tmgr = TokenManager(cfg.client_secret_path, token_path)
                client: EmailClient = GmailClient(tmgr, email)
            elif provider == "outlook":
                from .auth import MicrosoftTokenManager
                from .outlook_client import OutlookClient

                azure = acc.get("azure", {})
                token_path = f"credentials/{email}/token.json"
                tmgr_ms = MicrosoftTokenManager(
                    client_id=azure.get("client_id", ""),
                    tenant_id=azure.get("tenant_id", ""),
                    token_path=token_path,
                )
                client = OutlookClient(tmgr_ms, email)
            else:
                continue
            self.register(email, client, default=(email == default))

    def list_accounts(self) -> list[dict[str, Any]]:
        result = []
        for email, client in self._accounts.items():
            result.append(
                {
                    "email": email,
                    "provider": client.provider,
                    "default": email == self._default,
                }
            )
        return result
