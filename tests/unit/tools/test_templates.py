from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.tools.templates import handle_save_template, handle_use_template


class TestSaveTemplate:
    def test_saves_template_file(self, tmp_template_dir: Path) -> None:
        result = handle_save_template(
            {
                "name": "test_template",
                "subject": "Hello {{name}}",
                "body": "Dear {{name}}, your order {{order_id}} is ready.",
                "contentType": "text/plain",
                "variables": ["name", "order_id"],
            },
            MagicMock(),
            template_dir=tmp_template_dir,
        )
        assert "saved" in result["content"][0]["text"].lower()
        saved = json.loads((tmp_template_dir / "test_template.json").read_text())
        assert saved["name"] == "test_template"
        assert saved["variables"] == ["name", "order_id"]

    def test_name_required(self, tmp_template_dir: Path) -> None:
        with pytest.raises(ValueError, match="name is required"):
            handle_save_template({"body": "test"}, MagicMock(), template_dir=tmp_template_dir)

    def test_validates_placeholders_match_variables(self, tmp_template_dir: Path) -> None:
        with pytest.raises(ValueError, match="not declared in variables"):
            handle_save_template(
                {
                    "name": "bad",
                    "subject": "Hello {{name}}",
                    "body": "Dear {{name}}, {{missing_var}}",
                    "variables": ["name"],
                },
                MagicMock(),
                template_dir=tmp_template_dir,
            )


class TestUseTemplate:
    def test_renders_template_creates_draft(self, tmp_template_dir: Path) -> None:
        tpl = {
            "name": "claim",
            "subject": "Claim for {{policy}}",
            "body": "Dear {{name}}, policy {{policy}}",
            "contentType": "text/plain",
            "variables": ["name", "policy"],
        }
        (tmp_template_dir / "claim.json").write_text(json.dumps(tpl))

        mock_client = MagicMock()
        mock_client.create_draft.return_value = {
            "id": "draft_001",
            "message": {"id": "msg_001"},
        }

        result = handle_use_template(
            {
                "name": "claim",
                "variables": {"name": "Jon", "policy": "12345"},
                "to": "claims@example.com",
            },
            mock_client,
            template_dir=tmp_template_dir,
        )

        call_args = mock_client.create_draft.call_args
        assert "Jon" in call_args.kwargs["body"]
        assert "12345" in call_args.kwargs["subject"]
        assert "draft_001" in result["content"][0]["text"]

    def test_template_not_found_raises(self, tmp_template_dir: Path) -> None:
        with pytest.raises(ValueError, match="Template not found"):
            handle_use_template(
                {"name": "nonexistent", "variables": {}},
                MagicMock(),
                template_dir=tmp_template_dir,
            )

    def test_missing_variable_raises(self, tmp_template_dir: Path) -> None:
        tpl = {
            "name": "test",
            "subject": "{{greeting}}",
            "body": "{{greeting}} {{name}}",
            "contentType": "text/plain",
            "variables": ["greeting", "name"],
        }
        (tmp_template_dir / "test.json").write_text(json.dumps(tpl))

        with pytest.raises(ValueError, match="Missing variables"):
            handle_use_template(
                {"name": "test", "variables": {"greeting": "Hi"}},
                MagicMock(),
                template_dir=tmp_template_dir,
            )
