"""Manage one organization's model services as a revisioned configuration."""

from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid5

import httpx
from fastapi import HTTPException
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    model_validator,
)
from sqlalchemy import select

from app.config import config
from app.models.lab import Lab
from app.models.organization_ai import OrganizationAI, OrganizationAIService
from app.services import organization_ai as ai
from masterbrain.providers.registry import (
    DEFAULT_PROVIDER_BASE_URL,
    detect_model_provider,
)

ModelID = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9_./:@+-]{0,199}$"
    ),
]


class ServiceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: UUID
    name: str = Field(min_length=1, max_length=100)
    provider: Literal["qwen", "openai"]
    base_url: str = Field(min_length=1, max_length=512)
    models: list[ModelID] = Field(min_length=1, max_length=64)
    api_key: SecretStr | None = None
    clear_key: bool = False

    @model_validator(mode="after")
    def unique_models(self):
        if len(set(self.models)) != len(self.models) or (
            self.api_key is not None and self.clear_key
        ):
            raise ValueError("Invalid service settings")
        return self


class CatalogInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    services: list[ServiceInput] = Field(max_length=32)
    default_service_id: UUID | None
    model: ModelID | None
    enabled: bool
    expected_revision: int = Field(ge=0)

    @model_validator(mode="after")
    def valid_default(self):
        ids = {s.id: s for s in self.services}
        selected = ids.get(self.default_service_id)
        if len(ids) != len(self.services) or len(
            {s.name.casefold() for s in self.services}
        ) != len(ids):
            raise ValueError("Duplicate service")
        if self.services and (not selected or self.model not in selected.models):
            raise ValueError("Select a listed default model")
        if not self.services and (
            self.enabled or self.default_service_id or self.model
        ):
            raise ValueError("No default available")
        return self


class TestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service: ServiceInput
    model: ModelID
    expected_revision: int = Field(ge=0)


def trusted_endpoints():
    return list(
        dict.fromkeys(
            [
                *DEFAULT_PROVIDER_BASE_URL.values(),
                *(
                    part.strip().rstrip("/")
                    for part in config.ORGANIZATION_AI_ALLOWED_BASE_URLS.split(",")
                    if part.strip()
                ),
            ]
        )
    )


def allowed_base_url(url):
    url = url.rstrip("/")
    try:
        parts = urlsplit(url)
    except ValueError:
        raise HTTPException(422, "Invalid model service address") from None
    if (
        url not in trusted_endpoints()
        or parts.scheme not in ("https", "http")
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
    ):
        raise HTTPException(
            422, "Model service address is not approved by this deployment"
        )
    return url


def service_binding(service):
    return f"catalog-v1|{service.organization_id}|{service.id}|{service.provider}|{service.base_url}".encode()


def legacy_service(org_id, row):
    if not row or row.default_service_id or not row.model:
        return None
    provider = detect_model_provider(row.model)
    return OrganizationAIService(
        organization_id=org_id,
        id=uuid5(org_id, "existing-model-service"),
        name="DashScope" if provider == "qwen" else "OpenAI",
        provider=provider,
        base_url=DEFAULT_PROVIDER_BASE_URL[provider],
        models=[row.model],
        encrypted_key=row.encrypted_key,
    )


async def existing(db, org_id):
    row = await db.get(OrganizationAI, org_id, populate_existing=True)
    services = list(
        await db.scalars(
            select(OrganizationAIService)
            .where(OrganizationAIService.organization_id == org_id)
            .order_by(OrganizationAIService.name, OrganizationAIService.id)
        )
    )
    legacy = legacy_service(org_id, row)
    if legacy:
        services.append(legacy)
    return row, {s.id: s for s in services}, legacy


async def member_models(db, row):
    services = await db.scalars(
        select(OrganizationAIService)
        .where(
            OrganizationAIService.organization_id == row.organization_id,
            OrganizationAIService.encrypted_key.is_not(None),
        )
        .order_by(OrganizationAIService.name, OrganizationAIService.id)
    )
    trusted = trusted_endpoints()
    return [
        dict(
            value=f"{s.id}|{name}",
            service=s.name,
            model=name,
            is_default=s.id == row.default_service_id and name == row.model,
        )
        for s in services
        if s.base_url in trusted
        for name in s.models
    ]


async def read(db, org_id):
    row, services, legacy = await existing(db, org_id)
    return {
        "services": [
            dict(
                id=s.id,
                name=s.name,
                provider=s.provider,
                base_url=s.base_url,
                models=s.models,
                has_key=bool(s.encrypted_key),
            )
            for s in services.values()
        ],
        "default_service_id": legacy.id
        if legacy
        else (row.default_service_id if row else None),
        "model": row.model if services else None,
        "enabled": row.enabled if row else config.instance_ai_enabled,
        "revision": row.revision if row else 0,
        "inherited": row is None,
        "instance_blocked": config.AI_ENABLED is False,
        "allowed_base_urls": trusted_endpoints(),
    }


def service_secret(draft, saved, legacy, row):
    url = allowed_base_url(draft.base_url)
    if draft.api_key is not None:
        key = draft.api_key.get_secret_value().strip()
        if not 1 <= len(key) <= 4096 or not all(32 < ord(c) < 127 for c in key):
            raise HTTPException(422, "Invalid model service key")
        return key
    if draft.clear_key or not saved or not saved.encrypted_key:
        return None
    if saved.base_url != url or saved.provider != draft.provider:
        raise HTTPException(
            422, "Enter a new key when changing its service address or provider"
        )
    if legacy is not None and saved.id == legacy.id:
        return ai.unseal(row)
    return ai.decrypt_key(saved.encrypted_key, service_binding(saved))


def check_revision(row, expected):
    if (row.revision if row else 0) != expected:
        raise HTTPException(409, "Organization AI settings changed")


async def write(db, org_id, data):
    await db.scalar(select(Lab.id).where(Lab.id == org_id).with_for_update())
    row, saved, legacy = await existing(db, org_id)
    check_revision(row, data.expected_revision)
    if data.enabled and config.AI_ENABLED is False:
        raise HTTPException(409, "AI is disabled by the instance operator")
    if row is None:
        row = OrganizationAI(organization_id=org_id)
        db.add(row)
    # Validate and encrypt all changes before updating the database.
    changes = []
    for draft in data.services:
        old = saved.get(draft.id)
        key = service_secret(draft, old, legacy, row)
        if data.enabled and draft.id == data.default_service_id and not key:
            raise HTTPException(422, "The default model service requires a key")
        service = OrganizationAIService(
            organization_id=org_id,
            id=draft.id,
            name=draft.name,
            provider=draft.provider,
            base_url=allowed_base_url(draft.base_url),
            models=draft.models,
        )
        service.encrypted_key = (
            ai.encrypt_key(key, service_binding(service)) if key else None
        )
        changes.append(service)
    row.enabled, row.model, row.encrypted_key = data.enabled, data.model or "", None
    row.revision = data.expected_revision + 1
    for service in changes:
        await db.merge(service)
    await db.flush()
    row.default_service_id = data.default_service_id
    await db.flush()
    keep = {s.id for s in changes}
    for id_, service in saved.items():
        if id_ not in keep and service is not legacy:
            await db.delete(service)
    await db.commit()
    return await read(db, org_id)


async def test_model(db, org_id, data):
    row, saved, legacy = await existing(db, org_id)
    check_revision(row, data.expected_revision)
    if config.AI_ENABLED is False:
        raise HTTPException(409, "AI is disabled by the instance operator")
    draft = data.service
    if data.model not in draft.models:
        raise HTTPException(422, "Select a listed model")
    key = service_secret(draft, saved.get(draft.id), legacy, row)
    if not key:
        raise HTTPException(422, "Enter a service key")
    await db.commit()
    payload = {
        "model": data.model,
        "messages": [{"role": "user", "content": "Reply with OK."}],
        "max_tokens": 48,
    }
    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=False) as client:
            rsp = await client.post(
                allowed_base_url(draft.base_url) + "/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer " + key},
            )
        if rsp.status_code != 200:
            return {
                "status": {
                    401: "authentication_failed",
                    403: "permission_denied",
                    404: "model_unavailable",
                    429: "rate_limited",
                }.get(rsp.status_code, "provider_error")
            }
        content = rsp.json()["choices"][0]["message"]["content"]
        return {
            "status": "ok"
            if isinstance(content, str) and content.strip()
            else "invalid_response"
        }
    except httpx.HTTPError:
        return {"status": "unreachable"}
    except (KeyError, ValueError, IndexError, TypeError):
        return {"status": "invalid_response"}
