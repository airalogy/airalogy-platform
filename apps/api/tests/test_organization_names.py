"""Display names and stable identifiers have intentionally different contracts."""

import pytest
from pydantic import ValidationError

from app.routers.instance import BootstrapParams
from app.routers.labs import LabCreateParams, LabUpdateParams
from app.routers.organizations import OrganizationCreate


def payloads(name):
    return [
        (LabCreateParams, {"name": name, "uid": "synthetic_org", "members": []}),
        (OrganizationCreate, {"name": name, "uid": "synthetic_org", "members": []}),
        (LabUpdateParams, {"name": name, "description": ""}),
        (
            BootstrapParams,
            {
                "organization_name": name,
                "username": "synthetic_owner",
                "email": "owner@example.org",
                "name": "Synthetic Owner",
                "password": "Synthetic123!",
                "confirm_password": "Synthetic123!",
            },
        ),
    ]


@pytest.mark.parametrize(
    "name", ["研", "公司", "AI", "  研  ", "-R&D--", "研" * 64, "🔬"]
)
def test_display_names_accept_short_unicode_text_and_trim(name):
    for schema, payload in payloads(name):
        result = schema.model_validate(payload)
        key = "organization_name" if schema is BootstrapParams else "name"
        assert getattr(result, key) == name.strip()


@pytest.mark.parametrize("name", ["", "   ", "\t\n\u3000", "研" * 65])
def test_empty_or_overlong_names_are_rejected_at_every_write_boundary(name):
    for schema, payload in payloads(name):
        with pytest.raises(ValidationError):
            schema.model_validate(payload)


def test_display_name_relaxation_does_not_change_identifier_rules():
    with pytest.raises(ValidationError):
        OrganizationCreate(name="研", uid="x", members=[])
    with pytest.raises(ValidationError):
        OrganizationCreate(name="研", uid="研发公司", members=[])
    assert LabUpdateParams(description="").name is None


@pytest.mark.parametrize(
    "name,expected",
    [
        (None, None), ("", ""), ("  ", ""),
        ("  眼镜研发  ", "眼镜研发"), ("General", "General"),
        ("研" * 64, "研" * 64),
    ],
)
def test_optional_bootstrap_project_name_trims_and_keeps_valid_names(name, expected):
    _, payload = payloads("Synthetic Company")[-1]
    assert BootstrapParams(**payload, project_name=name).project_name == expected


@pytest.mark.parametrize("name", ["AB", "研" * 65, 123])
def test_invalid_bootstrap_project_name_is_rejected(name):
    _, payload = payloads("Synthetic Company")[-1]
    with pytest.raises(ValidationError):
        BootstrapParams(**payload, project_name=name)
