"""Tests for intake contract validation."""

from inv_man_intake.contracts.intake_contract import validate_intake_payload


def _valid_payload() -> dict[str, object]:
    return {
        "metadata": {
            "firm_name": "Alpha Capital",
            "fund_name": "Alpha Market Neutral Fund",
            "received_at": "2026-03-01T09:00:00Z",
            "source_channel": "email",
        },
        "files": [
            {
                "file_name": "manager_deck.pdf",
                "role": "investment_deck",
                "source_ref": "email:message-123",
            },
            {
                "file_name": "returns.xlsx",
                "role": "performance_track_record",
                "source_ref": "email:attachment-2",
            },
        ],
    }


def test_validate_intake_payload_accepts_valid_payload() -> None:
    result = validate_intake_payload(_valid_payload())
    assert result.is_valid is True
    assert result.errors == ()


def test_validate_intake_payload_rejects_missing_required_metadata() -> None:
    payload = _valid_payload()
    metadata = payload["metadata"]
    assert isinstance(metadata, dict)
    metadata.pop("fund_name")

    result = validate_intake_payload(payload)
    assert result.is_valid is False
    assert any(issue.path == "metadata.fund_name" for issue in result.errors)


def test_validate_intake_payload_requires_primary_document() -> None:
    payload = _valid_payload()
    payload["files"] = [{"file_name": "returns.xlsx", "role": "performance_track_record"}]

    result = validate_intake_payload(payload)
    assert result.is_valid is False
    assert any(issue.code == "missing_primary_document" for issue in result.errors)


def test_validate_intake_payload_rejects_invalid_source_channel() -> None:
    payload = _valid_payload()
    metadata = payload["metadata"]
    assert isinstance(metadata, dict)
    metadata["source_channel"] = "slack"

    result = validate_intake_payload(payload)
    assert result.is_valid is False
    assert any(issue.code == "invalid_source_channel" for issue in result.errors)


def test_validate_intake_payload_rejects_invalid_received_at() -> None:
    payload = _valid_payload()
    metadata = payload["metadata"]
    assert isinstance(metadata, dict)
    metadata["received_at"] = "03/01/2026"

    result = validate_intake_payload(payload)
    assert result.is_valid is False
    assert any(issue.code == "invalid_received_at" for issue in result.errors)


def test_validate_intake_payload_accepts_date_only_received_at() -> None:
    payload = _valid_payload()
    metadata = payload["metadata"]
    assert isinstance(metadata, dict)
    metadata["received_at"] = "2026-03-01"

    result = validate_intake_payload(payload)
    assert result.is_valid is True
    assert not any(issue.code == "invalid_received_at" for issue in result.errors)


def test_validate_intake_payload_warns_on_empty_or_non_string_source_ref() -> None:
    payload = _valid_payload()
    payload["files"] = [
        {"file_name": "manager_deck.pdf", "role": "investment_deck", "source_ref": ""},
        {"file_name": "returns.xlsx", "role": "performance_track_record", "source_ref": 42},
    ]

    result = validate_intake_payload(payload)
    assert result.is_valid is True
    warnings = [issue for issue in result.warnings if issue.code == "missing_source_ref"]
    assert len(warnings) == 2
