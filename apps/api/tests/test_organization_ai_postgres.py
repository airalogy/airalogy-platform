"""Real membership, encrypted storage and per-call routing; only synthetic keys."""

import asyncio
import os
from types import SimpleNamespace

import httpx
import pytest
from app.config import config
from app.models.lab import LabRole, LabUser
from app.models.organization_ai import OrganizationAI
from app.routers.depends import create_access_token
from app.services import organization_ai as ai
from app.services.model_usage import create_usage_context
from fastapi import HTTPException
from masterbrain.fastapi import provider_health
from masterbrain.providers.scoped import current_credential
from sqlalchemy import update

from tests.test_organization_postgres import client
from tests.test_record_analysis_postgres import database, seed_analysis

pytestmark = pytest.mark.skipif(
    not os.getenv("RESOURCE_TEST_DATABASE_URL"), reason="isolated PostgreSQL required"
)


def test_organization_configuration_and_dispatch(monkeypatch):
    async def run():
        monkeypatch.setattr(config, "DEPLOYMENT_MODE", "community")
        monkeypatch.setattr(config, "AI_ENABLED", None)
        monkeypatch.setattr(config, "AES_KEY", "24" * 32)
        async with database() as sessions:
            monkeypatch.setattr(ai.sessionmanager, "session", sessions)
            a, b = await seed_analysis(sessions), await seed_analysis(sessions)
            async with sessions() as db:
                await db.execute(
                    update(LabUser)
                    .where(LabUser.lab_id == a.lab.id, LabUser.user_id == a.analyst.id)
                    .values(role=LabRole.MANAGER)
                )
                await db.commit()

            def auth(who):
                return {"Auth-Token": create_access_token(who)}

            url = f"/organizations/{a.lab.id}/ai-settings"
            key_a, key_b = "test-fixture-alpha", "test-fixture-bravo"
            options = {"model": "qwen3.5-plus", "expected_revision": 0}
            form = {**options, "enabled": True, "api_key": key_a}
            probe = provider_health.probe_provider

            def directory(req):
                assert (
                    req.url.host == "dashscope.aliyuncs.com"
                    and req.url.path.endswith("/models")
                    and req.method == "GET"
                )
                if req.headers["Authorization"] != "Bearer " + key_a:
                    return httpx.Response(401, text="synthetic rejection")
                return httpx.Response(200, json={"data": [{"id": options["model"]}]})

            async def check(provider, **kwargs):
                return await probe(
                    provider, transport=httpx.MockTransport(directory), **kwargs
                )

            monkeypatch.setattr(provider_health, "probe_provider", check)
            async with client(sessions) as http:
                assert (await http.get(url)).status_code == 401
                for person in [a.recorder, a.outsider, b.owner]:
                    for method, path, payload in [
                        ("GET", url, None),
                        ("PUT", url, form),
                        ("POST", url + "/test", options),
                    ]:
                        denied = await http.request(
                            method, path, headers=auth(person), json=payload
                        )
                        assert denied.status_code == 403
                response = await http.get(url, headers=auth(a.analyst))
                assert response.json()["inherited"] and not response.json()["has_key"]
                invalid = await http.put(
                    url, headers=auth(a.owner), json={**form, "extra": key_a}
                )
                assert invalid.status_code == 422 and key_a not in invalid.text
                for key, result in [(key_b, "authentication_failed"), (key_a, "ok")]:
                    tested = await http.post(
                        url + "/test",
                        headers=auth(a.analyst),
                        json={**options, "api_key": key},
                    )
                    assert tested.json() == {"status": result}
                assert (await http.get(url, headers=auth(a.owner))).json()[
                    "revision"
                ] == 0
                saved = await http.put(url, headers=auth(a.analyst), json=form)
                assert saved.status_code == 200, saved.text
                assert (
                    saved.json()["has_key"]
                    and saved.json()["revision"] == 1
                    and key_a not in saved.text
                )
                assert (
                    await http.put(url, headers=auth(a.owner), json=form)
                ).status_code == 409
                assert (
                    await http.post(
                        url + "/test",
                        headers=auth(a.owner),
                        json={**options, "expected_revision": 1},
                    )
                ).json() == {"status": "ok"}
                url_b = f"/organizations/{b.lab.id}/ai-settings"
                assert (
                    await http.put(
                        url_b,
                        headers=auth(b.owner),
                        json={**form, "model": "gpt-4.1", "api_key": key_b},
                    )
                ).status_code == 200
                caps = await http.get(
                    f"/organizations/uid/{a.lab.uid}/ai-capabilities",
                    headers=auth(a.recorder),
                )
                assert caps.json() == {
                    "ai_enabled": True,
                    "enabled_chat_models": [2],
                    "chat_model_names": {"2": "qwen3.5-plus"},
                }

                async with sessions() as db:
                    row = await db.get(OrganizationAI, a.lab.id)
                    assert key_a not in row.encrypted_key and ai.unseal(row) == key_a
                    with pytest.raises(HTTPException):
                        ai.unseal(
                            SimpleNamespace(
                                organization_id=b.lab.id,
                                model=row.model,
                                encrypted_key=row.encrypted_key,
                            )
                        )
                path = "endpoints/chat/qa/language"
                source = {"model": {"name": "qwen3.5-flash"}}

                def usage(seed, person=None):
                    return create_usage_context(
                        feature="meeting.draft",
                        lab_id=seed.lab.id,
                        project_id=seed.project.id,
                        user_id=(person or seed.owner).id,
                    )

                async def dispatch(seed, expected, model):
                    async with ai.provider_dispatch(path, source, usage(seed)) as body:
                        await asyncio.sleep(0)
                        assert (
                            current_credential(model).key == expected
                            and body["model"]["name"] == model
                        )
                    assert current_credential() is None

                await asyncio.gather(
                    dispatch(a, key_a, options["model"]), dispatch(b, key_b, "gpt-4.1")
                )
                # Exercise the real embedded meeting pipeline, substituting only the provider.
                from app.services.meeting_drafts import DraftTurn, draft_meeting
                from masterbrain import configs

                observed = []

                def provider_client(*, provider, api_key, base_url):
                    async def complete(**kwargs):
                        observed.append((provider, api_key, base_url, kwargs["model"]))

                        async def chunks():
                            yield SimpleNamespace(
                                choices=[
                                    SimpleNamespace(
                                        delta=SimpleNamespace(
                                            content='{"message":"review","draft":null}'
                                        )
                                    )
                                ]
                            )

                        return chunks()

                    return SimpleNamespace(
                        chat=SimpleNamespace(
                            completions=SimpleNamespace(create=complete)
                        )
                    )

                monkeypatch.setattr(
                    configs, "build_litellm_openai_compatible_client", provider_client
                )
                reply = await draft_meeting(
                    DraftTurn(project_id=b.project.id, message="Synthetic agenda"),
                    "qwen3.5-flash",
                    usage(b),
                )
                assert reply.message == "review" and reply.draft is None
                assert observed == [
                    ("openai", key_b, "https://api.openai.com/v1", "gpt-4.1")
                ]
                with pytest.raises(HTTPException, match="membership"):
                    async with ai.provider_dispatch(path, source, usage(a, b.owner)):
                        pytest.fail("cross-organization dispatch")
                # Retain the existing key for the same provider and require a replacement across providers.
                mismatch = await http.put(
                    url,
                    headers=auth(a.owner),
                    json={
                        **options,
                        "model": "gpt-4.1",
                        "enabled": True,
                        "expected_revision": 1,
                    },
                )
                assert mismatch.status_code == 422
                disabled = await http.put(
                    url,
                    headers=auth(a.owner),
                    json={**options, "enabled": False, "expected_revision": 1},
                )
                assert disabled.status_code == 200 and disabled.json()["has_key"]
                with pytest.raises(HTTPException, match="disabled"):
                    async with ai.provider_dispatch(path, source, usage(a)):
                        pytest.fail("disabled dispatch")
                monkeypatch.setattr(config, "AI_ENABLED", False)
                assert (
                    await http.post(
                        url + "/test",
                        headers=auth(a.owner),
                        json={**options, "expected_revision": 2},
                    )
                ).status_code == 409
                with pytest.raises(HTTPException, match="disabled"):
                    async with ai.provider_dispatch(path, source, usage(b)):
                        pytest.fail("instance shutdown")
                cleared = await http.put(
                    url,
                    headers=auth(a.owner),
                    json={
                        **options,
                        "enabled": False,
                        "clear_key": True,
                        "expected_revision": 2,
                    },
                )
                assert cleared.status_code == 200 and not cleared.json()["has_key"]

    asyncio.run(run())
