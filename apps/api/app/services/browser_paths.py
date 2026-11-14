"""Canonical browser links; API resources and published Protocol IDs stay stable."""

from urllib.parse import quote

from app.config import config


def project_browser_path(organization_uid: str, project_uid: str) -> str:
    project = f"/projects/{quote(project_uid, safe='')}"
    if config.is_single_lab and organization_uid == config.SINGLE_LAB_UID:
        return project
    return f"/orgs/{quote(organization_uid, safe='')}{project}"
