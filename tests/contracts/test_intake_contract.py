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


def test_validate_intake_payload_rejects_non_object_payload() -> None:
    result = validate_intake_payload(payload="not-a-dict")  # type: ignore[arg-type]
    assert result.is_valid is False
    assert len(result.errors) == 1
    assert result.errors[0].code == "invalid_payload_type"


def test_validate_intake_payload_rejects_missing_metadata_object_and_files() -> None:
    payload = {"metadata": None, "files": []}
    result = validate_intake_payload(payload)

    assert result.is_valid is False
    assert any(issue.code == "missing_metadata" for issue in result.errors)
    assert any(issue.code == "missing_files" for issue in result.errors)


def test_validate_intake_payload_rejects_non_object_and_missing_name_file_entries() -> None:
    payload = _valid_payload()
    payload["files"] = [
        "raw-string-entry",
        {"file_name": "", "role": "investment_deck"},
    ]

    result = validate_intake_payload(payload)
    assert result.is_valid is False
    assert any(issue.code == "invalid_file_entry" for issue in result.errors)
    assert any(issue.code == "missing_file_name" for issue in result.errors)
    assert any(issue.code == "missing_primary_document" for issue in result.errors)


def test_validate_intake_payload_rejects_missing_role_and_unsupported_extension() -> None:
    payload = _valid_payload()
    payload["files"] = [
        {"file_name": "manager_deck.pdf", "role": ""},
        {"file_name": "notes", "role": "memo"},
    ]

    result = validate_intake_payload(payload)
    assert result.is_valid is False
    assert any(issue.code == "missing_file_role" for issue in result.errors)
    assert any(issue.code == "unsupported_file_type" for issue in result.errors)


def test_validate_intake_payload_rejects_non_string_or_empty_received_at() -> None:
    payload = _valid_payload()
    metadata = payload["metadata"]
    assert isinstance(metadata, dict)
    metadata["received_at"] = ""

    result_empty = validate_intake_payload(payload)
    assert result_empty.is_valid is False
    assert any(
        issue.code == "invalid_received_at" and "must not be empty" in issue.message
        for issue in result_empty.errors
    )

    metadata["received_at"] = 12345
    result_non_string = validate_intake_payload(payload)
    assert result_non_string.is_valid is False
    assert any(
        issue.code == "invalid_received_at" and "ISO-8601 string" in issue.message
        for issue in result_non_string.errors
    )


def test_validate_intake_payload_rejects_non_canonical_received_at_datetime() -> None:
    payload = _valid_payload()
    metadata = payload["metadata"]
    assert isinstance(metadata, dict)
    metadata["received_at"] = "2026-03-01 09:00:00Z"

    result = validate_intake_payload(payload)
    assert result.is_valid is False
    assert any(issue.code == "invalid_received_at" for issue in result.errors)


def test_validate_intake_payload_rejects_timezone_less_received_at_datetime() -> None:
    payload = _valid_payload()
    metadata = payload["metadata"]
    assert isinstance(metadata, dict)
    metadata["received_at"] = "2026-03-01T09:00:00"

    result = validate_intake_payload(payload)
    assert result.is_valid is False
    assert any(issue.code == "invalid_received_at" for issue in result.errors)


def test_validate_intake_payload_accepts_received_at_datetime_with_offset() -> None:
    payload = _valid_payload()
    metadata = payload["metadata"]
    assert isinstance(metadata, dict)
    metadata["received_at"] = "2026-03-01T09:00:00+00:00"

    result = validate_intake_payload(payload)
    assert result.is_valid is True
    assert not any(issue.code == "invalid_received_at" for issue in result.errors)


def test_validate_intake_payload_accepts_contract_version_and_schema_revision() -> None:
    payload = _valid_payload()
    metadata = payload["metadata"]
    assert isinstance(metadata, dict)
    metadata["contract_version"] = "v1"
    metadata["schema_revision"] = 2

    result = validate_intake_payload(payload)
    assert result.is_valid is True
    assert not any(
        issue.code in {"invalid_contract_version", "invalid_schema_revision"}
        for issue in result.errors
    )


def test_validate_intake_payload_rejects_unsupported_contract_version() -> None:
    payload = _valid_payload()
    metadata = payload["metadata"]
    assert isinstance(metadata, dict)
    metadata["contract_version"] = "v2"

    result = validate_intake_payload(payload)
    assert result.is_valid is False
    assert any(issue.code == "unsupported_contract_version" for issue in result.errors)


def test_validate_intake_payload_rejects_invalid_schema_revision() -> None:
    payload = _valid_payload()
    metadata = payload["metadata"]
    assert isinstance(metadata, dict)
    metadata["schema_revision"] = 0

    result_zero = validate_intake_payload(payload)
    assert result_zero.is_valid is False
    assert any(issue.code == "invalid_schema_revision" for issue in result_zero.errors)

    metadata["schema_revision"] = True
    result_bool = validate_intake_payload(payload)
    assert result_bool.is_valid is False
    assert any(issue.code == "invalid_schema_revision" for issue in result_bool.errors)
