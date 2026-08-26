"""Unified mail-sort rule models compiled to Gmail filters and Outlook rules."""

from __future__ import annotations

from pydantic import BaseModel, field_validator

STARTER_FOLDERS: tuple[str, ...] = (
    "Newsletters",
    "Receipts",
    "Finance",
    "Travel",
    "Social",
    "Junk",
)


class MailRuleMatch(BaseModel):
    """Match criteria for a sort rule: one sender address or domain."""

    from_value: str
    subject_contains: str | None = None

    @field_validator("from_value")
    @classmethod
    def validate_from_value(cls, value: str) -> str:
        """Normalize and reject values that are neither email nor domain.

        Args:
            value: Raw from value from the caller.

        Returns:
            Lowercased, stripped email or domain.

        Raises:
            ValueError: If the value is not an email address or a domain.
        """
        stripped = value.strip().lower()
        if "*" in stripped or " " in stripped:
            raise ValueError("from_value must be an email address or a domain")
        if "@" in stripped:
            local, _, domain = stripped.partition("@")
            if local and "." in domain:
                return stripped
        elif "." in stripped:
            return stripped
        raise ValueError("from_value must be an email address or a domain")


class MailRule(BaseModel):
    """A durable sort rule stored natively on Gmail or Outlook after create."""

    id: str | None = None
    name: str
    enabled: bool = True
    match: MailRuleMatch
    destination: str
    existing_moved: int = 0
    existing_failed: int = 0
