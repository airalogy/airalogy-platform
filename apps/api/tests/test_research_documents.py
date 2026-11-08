from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.main import app
from app.routers.research_materials import material_content_type
from app.services.knowledge import authorize_research_file
from app.services.research_documents import (
    DocumentContent,
    definition_signature,
    document_change_impact,
    validate_document,
)
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError


def test_plain_document_requires_neither_protocol_nor_fields():
    content = DocumentContent(
        title="Research notes", body="# First observation\nAn unfinished sentence"
    )
    assert validate_document(content.body, content.record_data.model_dump())["valid"]
    assert "protocol_id" not in DocumentContent.model_fields


def test_invalid_source_is_saveable_but_not_submittable():
    content = DocumentContent(title="Working draft", body="{{var|temperature: }}")
    assert content.body
    assert not validate_document(content.body, {})["valid"]


@pytest.mark.parametrize(
    "value,valid",
    [
        (21.5, True),
        (0, True),
        (-1, False),
        (101, False),
        ("21", False),
        (True, False),
        (None, False),
    ],
)
def test_structured_results_use_sdk_field_constraints_and_json_types(value, valid):
    result = validate_document(
        '{{var|temperature: float, ge=0, le=100, unit="C"}}',
        {"var": {"temperature": value}},
    )
    assert result["valid"] is valid


def test_missing_and_unknown_values_do_not_get_dropped_or_filled():
    result = validate_document("{{var|name: str}}", {"var": {"other": 12}})
    assert not result["valid"]
    assert len(result["errors"]) == 2


def test_sdk_enum_date_optional_and_default_contracts():
    source = '{{var|choice: Literal["yes", "no"]}} {{var|when: date}} {{var|notes: str | None = None}}'
    result = validate_document(
        source, {"var": {"choice": "yes", "when": "2026-11-07", "notes": None}}
    )
    assert result["valid"], result
    assert not validate_document(
        source, {"var": {"choice": "maybe", "when": "2026-99-99"}}
    )["valid"]


@pytest.mark.parametrize(
    "annotation",
    ["__import__('os').system('false')", "str.__class__", "UnknownType", "FileIdPNG"],
)
def test_untrusted_and_resource_types_never_execute_or_bypass_authorization(annotation):
    result = validate_document(
        f"{{{{var|field: {annotation}}}}}", {"var": {"field": "data"}}
    )
    assert not result["valid"]


def test_prose_and_label_change_do_not_reinterpret_values_but_unit_change_does():
    a = '{{var|weight: float, title="Weight", unit="mg"}}'
    b = 'New paragraph\n{{var|weight: float, title="Measured weight", unit="mg"}}'
    c = '{{var|weight: float, title="Weight", unit="g"}}'
    assert definition_signature(a) == definition_signature(b)
    assert definition_signature(a) != definition_signature(c)
    old = {"body": a, "record_data": {"var": {"weight": 10}}}
    proposal = DocumentContent(
        title="Test", body=c, record_data={"var": {"weight": 10}}
    )
    impact = document_change_impact(old, proposal)
    assert impact["requires_confirmation"]
    assert not impact["removed_values"]


def test_deleting_filled_field_requires_review():
    old = {"body": "{{var|value: int}}", "record_data": {"var": {"value": 0}}}
    proposal = DocumentContent(title="Test", body="A note")
    impact = document_change_impact(old, proposal)
    assert impact["removed_values"] == ["var.value"]
    assert impact["requires_confirmation"]


def test_duplicate_files_nan_and_invalid_dates_are_rejected():
    file_id = uuid4()
    with pytest.raises(ValidationError):
        DocumentContent(title="Test", file_ids=[file_id, file_id])
    with pytest.raises(ValidationError):
        DocumentContent(title="Test", record_data={"var": {"value": float("nan")}})
    with pytest.raises(ValidationError):
        DocumentContent(title="Test", occurred_at="2026-11-07T12:00:00")


def test_original_material_is_opaque_unless_verified_safe_preview_type():
    assert (
        material_content_type(b"<script>alert(1)</script>", "note.html")
        == "application/octet-stream"
    )
    with pytest.raises(ValueError):
        material_content_type(b"<html>not a PDF</html>", "note.pdf")
    buffer = BytesIO()
    Image.new("RGB", (2, 2)).save(buffer, "PNG")
    assert material_content_type(buffer.getvalue(), "note.png") == "image/png"
    with pytest.raises(ValueError):
        material_content_type(buffer.getvalue(), "note.jpg")


def test_personal_file_authorization_checks_the_actual_owner_before_querying():
    import asyncio

    file = SimpleNamespace(scope_type="personal", owner_user_id=uuid4())
    user = SimpleNamespace(id=uuid4())
    with pytest.raises(HTTPException) as error:
        asyncio.run(authorize_research_file(None, user, file))
    assert error.value.status_code == 404


def test_document_endpoints_are_authenticated_and_have_explicit_preview_contracts():
    paths = app.openapi()["paths"]
    client = TestClient(app)
    for path in (
        "/research-documents",
        "/research-materials",
        f"/research-documents/{uuid4()}/submit",
    ):
        assert client.post(path, json={}).status_code == 401
    assert "/research-documents/{document_id}/revisions" in paths
    assert "/research-documents/{document_id}/restore/{revision}" in paths


def test_checkpoint_values_are_strict_and_timers_cannot_be_negative():
    source = "{{check|verified}}"
    assert not validate_document(source, {"check": {"verified": {"checked": "yes"}}})[
        "valid"
    ]
    assert not validate_document(
        source, {"check": {"verified": {"checked": True, "unknown": 1}}}
    )["valid"]
    assert validate_document(
        source,
        {"check": {"verified": {"checked": False, "annotation": "Failed inspection"}}},
    )["valid"]
    assert not validate_document(source, {})["valid"]
    assert not validate_document(
        "{{step|prepare}}", {"step": {"prepare": {"checked": True, "elapsed_ms": -1}}}
    )["valid"]


def test_field_named_title_is_not_mistaken_for_schema_annotation():
    assert definition_signature("{{var|title: str}}") != definition_signature(
        "{{var|title: int}}"
    )


def test_archive_rejects_unexpected_paths_and_checksum_mismatches():
    import hashlib
    import json
    import zipfile

    from app.services.research_document_archive import read_document_archive
    from app.services.research_documents import DOCUMENT_FORMAT

    identity = uuid4()
    original = b"Synthetic data"
    content = DocumentContent(
        title="Archive", body="Note", file_ids=[identity]
    ).model_dump(mode="json")
    manifest = {
        "format": DOCUMENT_FORMAT,
        "content": content,
        "files": [
            {
                "id": str(identity),
                "filename": "original.txt",
                "size_bytes": len(original),
                "sha256": hashlib.sha256(original).hexdigest(),
            }
        ],
    }

    def package(extra=False, tampered=False):
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("document.json", json.dumps(manifest))
            archive.writestr("document.aimd", content["body"])
            archive.writestr(f"files/{identity}", b"Changed" if tampered else original)
            if extra:
                archive.writestr("../outside", "Do not extract")
        return buffer.getvalue()

    assert read_document_archive(package())[1][0][1] == original
    for value in (package(extra=True), package(tampered=True)):
        with pytest.raises(ValueError):
            read_document_archive(value)
