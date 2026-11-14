import pytest

from app.config import config
from app.services.browser_paths import project_browser_path


@pytest.mark.parametrize("mode", ["single_organization", "single_lab"])
def test_single_instance_links_include_only_the_project(mode, monkeypatch):
    monkeypatch.setattr(config, "DEPLOYMENT_MODE", mode)
    monkeypatch.setattr(config, "SINGLE_LAB_UID", "company")
    assert project_browser_path("company", "optics") == "/projects/optics"
    # Never silently reassign an asset from another organization.
    assert project_browser_path("other", "optics") == "/orgs/other/projects/optics"


def test_community_links_always_include_organization(monkeypatch):
    monkeypatch.setattr(config, "DEPLOYMENT_MODE", "community")
    monkeypatch.setattr(config, "SINGLE_LAB_UID", "company")
    assert project_browser_path("company", "optics") == "/orgs/company/projects/optics"
    assert project_browser_path("a/b", "a?b#c") == "/orgs/a%2Fb/projects/a%3Fb%23c"


@pytest.mark.parametrize("mode,prefix", [("community", "/orgs/company"), ("single_organization", "")])
def test_sitemap_uses_canonical_asset_paths(mode, prefix, monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from starlette.requests import Request
    from app.routers.seo import get_sitemap

    monkeypatch.setattr(config, "DEPLOYMENT_MODE", mode)
    monkeypatch.setattr(config, "SINGLE_LAB_UID", "company")

    class Database:
        async def execute(self, query):
            row = SimpleNamespace(lab_uid="company", project_uid="optics", protocol_uid="assay", updated_at=None)
            return SimpleNamespace(all=lambda: [row])

    request = Request({"type": "http", "scheme": "https", "server": ("research.example.org", 443), "path": "/sitemap.xml", "headers": [(b"host", b"research.example.org")]})
    response = asyncio.run(get_sitemap(request, Database()))
    body = response.body.decode()
    assert f"https://research.example.org{prefix}/projects/optics/protocols</loc>" in body
    assert f"https://research.example.org{prefix}/projects/optics/protocols/assay/protocol</loc>" in body
    assert "/labs/" not in body
