import pytest
from app.routers.document_templates import TemplateCreate, TemplateUpdate
from app.services.document_templates import builtin_templates, template_defaults
from fastapi import HTTPException
from pydantic import ValidationError


def test_builtins_have_real_bilingual_starting_content():
    for locale in ("en-US", "zh-CN"):
        templates = builtin_templates(locale)
        assert len(templates) == 4
        assert len({x["id"] for x in templates}) == 4
        for item in templates:
            assert item["revision"] == 1 and not item["can_edit"]
            assert template_defaults(item["body"]) == {"var": {}}
        assert next(x for x in templates if x["id"] == "builtin:meeting")["body"]


def test_template_defaults_are_explicit_and_separate_from_measured_state():
    body = "{{var|temperature: float = 25, ge=0, le=100}} {{var|observation: str}}"
    values = template_defaults(body)
    assert values == {"var": {"temperature": 25}}
    values["var"]["temperature"] = 99
    assert template_defaults(body)["var"]["temperature"] == 25


@pytest.mark.parametrize(
    "body",
    [
        "{{var|duplicate: int}} {{var|duplicate: str}}",
        "{{var|score: int = -1, ge=0}}",
        "{{var|when: date = 'not-a-date'}}",
        "{{var|file: FileIdPNG}}",
        "{{var|code: __import__('os').system('false')}}",
    ],
)
def test_invalid_definitions_and_defaults_never_become_shared_templates(body):
    with pytest.raises(HTTPException) as error:
        template_defaults(body)
    assert error.value.status_code == 422


def test_template_cannot_accept_record_values_files_or_authority():
    for key, value in {
        "record_data": {"var": {"temperature": 99}},
        "file_ids": [],
        "state": "submitted",
        "owner_user_id": "someone",
    }.items():
        with pytest.raises(ValidationError):
            TemplateCreate(scope_type="personal", title="Synthetic", **{key: value})
    with pytest.raises(ValidationError):
        TemplateUpdate(title=" ", expected_revision=1)
