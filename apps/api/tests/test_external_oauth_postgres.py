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


@pytest.mark.parametrize(
    "coverage", ["single", "organization", "selected", "accessible"]
)
def test_pkce_consent_code_replay_and_resource_binding(coverage):
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
            for hints in ({}, {"ui_locales": "zh-CN en", "display": "page"}):
                authorize = await http.get(
                    "/external-access/oauth/authorize", params={**request, **hints}
                )
                assert authorize.status_code == 303, authorize.text
                location = urlsplit(authorize.headers["location"])
                assert location.path == "/authorize"
                assert parse_qs(location.query) == {
                    **{key: [value] for key, value in request.items()},
                    "external": ["1"],
                }
            strict_request = await http.post(
                "/external-access/oauth/request",
                headers=browser(scope.owner),
                json={**request, "ui_locales": "zh-CN"},
            )
            assert strict_request.status_code == 422
            wrong_callback = await http.get(
                "/external-access/oauth/authorize",
                params={**request, "redirect_uri": "https://example.test/steal"},
            )
            assert wrong_callback.status_code == 400
            target = {"project_id": str(scope.project.id)}
            if coverage in ("selected", "accessible"):
                target = {
                    "organization_id": str(scope.lab.id),
                    "project_coverage": coverage,
                }
                if coverage == "selected":
                    target["selected_project_ids"] = [str(scope.project.id)]
            if coverage == "organization":
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

            async def originals(user):
                response = await http.post(
                    "/external-access/oauth/request",
                    headers=browser(user),
                    json=request,
                )
                assert response.status_code == 200
                return response.json()["prior_grants"]

            assert await originals(scope.outsider) == []
            (prior,) = await originals(scope.owner)
            assert set(prior["scopes"]) == set(credentials["scope"].split())
            supplement = {
                **request,
                **target,
                "approve": True,
                "prior_grant_id": prior["id"],
            }
            if coverage != "organization":
                supplement["scope"] += " documents:read"
                supplement["approved_scopes"] = [*prior["scopes"], "documents:read"]
            for mismatch in [
                {"prior_grant_id": str(uuid4())},
                {"project_id": str(uuid4())},
                *(
                    [{"approved_scopes": ["documents:read"]}]
                    if coverage != "organization"
                    else []
                ),
            ]:
                rejected = await http.post(
                    "/external-access/oauth/consent",
                    headers=browser(scope.owner),
                    json={**supplement, **mismatch},
                )
                assert rejected.status_code == 409, rejected.text
            reviewed = await http.post(
                "/external-access/oauth/consent",
                headers=browser(scope.owner),
                json=supplement,
            )
            assert reviewed.status_code == 200, reviewed.text
            assert await originals(scope.owner) == [
                prior
            ]  # Unredeemed approvals are not connections.
            if coverage == "organization":
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
            if coverage in ("selected", "accessible"):
                assert (
                    response.json()["result"]["structuredContent"]["project_coverage"]
                    == coverage
                )
            if coverage != "organization":
                from app.models.project_operations import (
                    OperationsBook,
                    OperationsOrganization,
                )

                async with sessions() as db:
                    db.add(
                        OperationsOrganization(
                            organization_id=scope.lab.id, enabled=True, revision=1
                        )
                    )
                    await db.flush()
                    db.add(
                        OperationsBook(
                            project_id=scope.project.id, enabled=True, revision=1
                        )
                    )
                    await db.commit()
                checked = await http.post(
                    "/mcp",
                    headers=headers,
                    json={
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {
                            "name": "check_contract_receipt_access",
                            "arguments": (
                                {"project_id": str(scope.project.id)}
                                if coverage != "single"
                                else {}
                            ),
                        },
                    },
                )
                result = checked.json()["result"]
                assert result["isError"]
                challenge = checked.headers["www-authenticate"]
                assert result["_meta"]["mcp/www_authenticate"] == [challenge]
                assert 'error="insufficient_scope"' in challenge
                assert set(challenge.split('scope="')[1].split('"')[0].split()) == {
                    *credentials["scope"].split(),
                    "contracts:read",
                    "contracts:create",
                    "cash:read",
                    "cash:link",
                }
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
