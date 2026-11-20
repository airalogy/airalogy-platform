"""Real PKCE exchange, callback binding, revocation and MCP audience boundaries."""

import asyncio
import base64
import hashlib
import os
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest

from app.config import config
from tests.test_external_access_postgres import (
    browser,
    call,
    client,
    grant,
    isolated_executor,  # noqa: F401
    seed,
)
from tests.test_record_analysis_postgres import database

pytestmark = pytest.mark.skipif(
    not os.environ.get("RESOURCE_TEST_DATABASE_URL"),
    reason="Isolated PostgreSQL required",
)


@pytest.mark.parametrize("organization", [False, True])
def test_pkce_consent_code_replay_and_resource_binding(organization):
    async def scenario():
        async with database() as sessions, client(sessions) as http:
            scope = await seed(sessions)
            await grant(http, scope)  # Lab opt-in through the ordinary owner flow.
            registration = await http.post(
                "/external-access/oauth/clients",
                headers=browser(scope.owner),
                json={
                    "name": "Synthetic OAuth client",
                    "redirect_uris": ["http://127.0.0.1:8765/callback"],
                },
            )
            assert registration.status_code == 200, registration.text
            client_id = registration.json()["client_id"]
            verifier = "v" * 64
            challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                .rstrip(b"=")
                .decode()
            )
            request = {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": "http://127.0.0.1:8765/callback",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": uuid4().hex,
                "scope": "protocols:read records:read",
                "resource": config.SITE_URL.rstrip("/") + "/api/mcp",
            }
            authorize = await http.get(
                "/external-access/oauth/authorize", params=request
            )
            assert authorize.status_code == 303, authorize.text
            assert "external=1" in authorize.headers["location"]
            wrong_callback = await http.get(
                "/external-access/oauth/authorize",
                params={**request, "redirect_uri": "https://example.test/steal"},
            )
            assert wrong_callback.status_code == 400
            target = {"project_id": str(scope.project.id)}
            if organization:
                request["scope"] = "projects:find projects:create protocols:read"
                target = {
                    "organization_id": str(scope.lab.id),
                    "approved_scopes": ["projects:find"],
                }
            excess = await http.post(
                "/external-access/oauth/consent",
                headers=browser(scope.owner),
                json={
                    **request,
                    **target,
                    "approved_scopes": ["cash:create"],
                    "approve": True,
                },
            )
            assert excess.status_code == 400
            consent = await http.post(
                "/external-access/oauth/consent",
                headers=browser(scope.owner),
                json={**request, **target, "approve": True},
            )
            assert consent.status_code == 200, consent.text
            query = parse_qs(urlsplit(consent.json()["redirect_to"]).query)
            assert query["state"] == [request["state"]]
            body = {
                "grant_type": "authorization_code",
                "client_id": client_id,
                "redirect_uri": request["redirect_uri"],
                "resource": request["resource"],
                "code": query["code"][0],
                "code_verifier": verifier,
            }
            for change in (
                {"code_verifier": "x" * 64},
                {"resource": config.SITE_URL.rstrip("/") + "/api/external-access"},
                {"redirect_uri": "https://example.test/steal"},
                {"client_id": str(uuid4())},
            ):
                rejected = await http.post(
                    "/external-access/oauth/token", data={**body, **change}
                )
                assert rejected.status_code == 400, rejected.text
                assert "access_token" not in rejected.json()
            first, second = await asyncio.gather(
                http.post("/external-access/oauth/token", data=body),
                http.post("/external-access/oauth/token", data=body),
            )
            assert sorted([first.status_code, second.status_code]) == [200, 400]
            credentials = first.json() if first.status_code == 200 else second.json()
            if organization:
                assert credentials["scope"] == "projects:find"
            token = credentials["access_token"]
            assert (
                "no-store"
                in (first if first.status_code == 200 else second).headers[
                    "cache-control"
                ]
            )
            assert (
                await call(http, token, "access_context")
            ).status_code == 401  # MCP audience only
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json, text/event-stream",
            }
            response = await http.post(
                "/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "access_context", "arguments": {}},
                },
            )
            assert response.status_code == 200 and not response.json()["result"].get(
                "isError"
            ), response.text
            no_credential = await http.post("/mcp", json={})
            assert (
                no_credential.status_code == 401
                and "resource_metadata=" in no_credential.headers["www-authenticate"]
            )
            metadata = (
                await http.get("/.well-known/oauth-authorization-server")
            ).json()
            assert metadata["code_challenge_methods_supported"] == ["S256"]
            assert "registration_endpoint" not in metadata
            assert (
                await http.delete(
                    f"/external-access/oauth/clients/{client_id}",
                    headers=browser(scope.outsider),
                )
            ).status_code == 404
            assert (
                await http.delete(
                    f"/external-access/oauth/clients/{client_id}",
                    headers=browser(scope.owner),
                )
            ).status_code == 200
            assert (
                await http.post(
                    "/mcp",
                    headers=headers,
                    json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                )
            ).status_code == 401

    asyncio.run(scenario())
