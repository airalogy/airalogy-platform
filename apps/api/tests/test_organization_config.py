from pydantic import ValidationError
import pytest
from sqlalchemy import inspect

from app.models.organization import Organization, OrganizationMember
from app.models.lab import Lab, LabUser
from app.models.project import Project
from tests.test_single_lab_config import settings


def test_generic_defaults_and_legacy_defaults_are_independent():
    company = settings(DEPLOYMENT_MODE="single_organization")
    assert company.is_single_organization and company.is_single_lab
    assert company.SINGLE_ORGANIZATION_DEFAULT_PROJECT_UID == "workspace"
    assert company.SINGLE_LAB_DEFAULT_PROJECT_UID == "workspace"
    assert company.default_invitation_project_role == 30
    assert company.effective_organization_type == "company"
    assert company.effective_signup_mode == "invite_only"
    assert company.effective_sms_signup_required is False
    laboratory = settings(DEPLOYMENT_MODE="single_lab")
    assert laboratory.SINGLE_LAB_DEFAULT_PROJECT_UID == "lab_protocols"
    assert laboratory.default_invitation_project_role == 40
    assert laboratory.effective_organization_type == "laboratory"
    assert not settings(DEPLOYMENT_MODE="community").is_single_organization


@pytest.mark.parametrize(
    "suffix,value",
    [
        ("UID", "rd_team"),
        ("NAME", "Synthetic Company"),
        ("DESCRIPTION", "R&D"),
        ("DEFAULT_PROJECT_UID", "glasses"),
        ("DEFAULT_PROJECT_NAME", "Glasses R&D"),
    ],
)
def test_aliases_preserve_values_and_reject_conflicts(suffix, value):
    old, new = f"SINGLE_LAB_{suffix}", f"SINGLE_ORGANIZATION_{suffix}"
    for values in ({old: value}, {new: value}, {old: value, new: value}):
        result = settings(DEPLOYMENT_MODE="single_organization", **values)
        assert getattr(result, old) == getattr(result, new) == value
    with pytest.raises(ValidationError, match="conflicts"):
        settings(**{old: value, new: "different"})


def test_real_environment_aliases_and_conflicts(monkeypatch):
    monkeypatch.setenv("SINGLE_ORGANIZATION_NAME", "Synthetic Company")
    assert settings().SINGLE_LAB_NAME == "Synthetic Company"
    monkeypatch.setenv("SINGLE_LAB_NAME", "Conflicting Laboratory")
    with pytest.raises(ValidationError, match="conflicts"):
        settings()


def test_structure_alias_validation():
    assert (
        settings(ORGANIZATION_STRUCTURE_MODE="structured").effective_lab_structure_mode
        == "structured"
    )
    with pytest.raises(ValidationError, match="conflicts"):
        settings(ORGANIZATION_STRUCTURE_MODE="structured", LAB_STRUCTURE_MODE="flat")
    with pytest.raises(ValidationError):
        settings(SINGLE_ORGANIZATION_TYPE="unrecognized")
    with pytest.raises(ValidationError):
        settings(
            DEPLOYMENT_MODE="single_organization", SINGLE_ORGANIZATION_UID="bad/uid"
        )


def test_generic_models_share_one_mapper_and_the_same_identity():
    assert Organization is Lab
    assert OrganizationMember is LabUser
    assert inspect(Organization) is inspect(Lab)
    from uuid import uuid4

    identity = uuid4()
    member = OrganizationMember(organization_id=identity)
    project = Project(organization_id=identity)
    assert member.lab_id == project.lab_id == identity
    assert inspect(OrganizationMember).synonyms["organization_id"].name == "lab_id"


def test_project_accepts_organization_id_and_rejects_ambiguous_ownership():
    from uuid import uuid4
    from app.routers.projects import ProjectCreateParams

    identity = uuid4()
    payload = {"name": "Glasses R&D", "uid": "glasses", "type": 1}
    for ownership in (
        {"organization_id": str(identity)},
        {"lab_id": str(identity)},
        {"organization_id": str(identity), "lab_id": str(identity)},
    ):
        assert ProjectCreateParams(**payload, **ownership).lab_id == identity
    with pytest.raises(ValidationError, match="conflicts"):
        ProjectCreateParams(**payload, organization_id=identity, lab_id=uuid4())


def test_deployment_gate_accepts_canonical_profile(monkeypatch):
    from app.config import config
    from app.cli.validate_deployment import validate_single_organization_deployment

    for key, value in {
        "APP_ENV": "production",
        "DEPLOYMENT_MODE": "single_organization",
        "LAB_STRUCTURE_MODE": "structured",
        "API_ROOT_PATH": "",
        "SIGNUP_MODE": "invite_only",
        "LOG_REQUEST_BODIES": False,
        "SITE_URL": "https://research.example.org",
        "STORAGE_BACKEND": "minio",
        "MINIO_PROXY_PATH": "/minio",
    }.items():
        monkeypatch.setattr(config, key, value)
    assert validate_single_organization_deployment() == []
