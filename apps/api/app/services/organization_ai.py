"""Organization-owned provider policy. No provider key is returned to the browser."""

from base64 import b64decode, b64encode
from contextlib import asynccontextmanager
from typing import Literal, get_args
from uuid import UUID

from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import HKDF
from fastapi import HTTPException
from masterbrain.providers.registry import (
    DEFAULT_PROVIDER_BASE_URL,
    QwenFlashModel,
    detect_model_provider,
)
from masterbrain.providers.scoped import ProviderCredential, bind_credential
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import select

from app.config import config
from app.database import sessionmanager
from app.libs.ai_scope import OrganizationAIScope, active_ai_scope
from app.models.lab import Lab, LabUser
from app.models.organization_ai import OrganizationAI, OrganizationAIService
from app.models.project import Project

ModelName = Literal[QwenFlashModel, "qwen3.5-plus", "qwen3-max", "gpt-4.1"]
DEFAULT_MODEL = "qwen3.5-flash"


class KeyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: ModelName
    api_key: SecretStr | None = None
    expected_revision: int = Field(ge=0)


class SettingsInput(KeyInput):
    enabled: bool
    clear_key: bool = False


def cipher_key():
    try:
        secret = bytes.fromhex(config.AES_KEY)
    except ValueError:
        secret = b""
    if len(secret) != 32 or not any(secret):
        raise HTTPException(
            503,
            "Configure a deployment encryption key before storing organization credentials",
        )
    return HKDF(secret, 32, b"", SHA256, context=b"airalogy.organization-ai.v1")


def associated_data(org_id, model):
    return f"{org_id}:{detect_model_provider(model)}".encode()


def seal(value, org_id, model):
    return encrypt_key(value, associated_data(org_id, model))


def encrypt_key(value, binding):
    cipher = AES.new(cipher_key(), AES.MODE_GCM)
    cipher.update(binding)
    data, tag = cipher.encrypt_and_digest(value.encode())
    return b64encode(cipher.nonce + tag + data).decode()


def unseal(row):
    return decrypt_key(
        row.encrypted_key, associated_data(row.organization_id, row.model)
    )


def decrypt_key(encrypted, binding):
    try:
        raw = b64decode(encrypted, validate=True)
        cipher = AES.new(cipher_key(), AES.MODE_GCM, nonce=raw[:16])
        cipher.update(binding)
        return cipher.decrypt_and_verify(raw[32:], raw[16:32]).decode()
    except (ValueError, TypeError, UnicodeError):
        raise HTTPException(503, "Organization credential unavailable") from None


def status(row):
    return {
        "enabled": row.enabled if row else config.instance_ai_enabled,
        "inherited": row is None,
        "models": list(get_args(ModelName)),
        "model": (row.model or DEFAULT_MODEL) if row else DEFAULT_MODEL,
        "has_key": bool(
            row and (row.service if row.default_service_id else row).encrypted_key
        ),
        "revision": row.revision if row else 0,
        "instance_blocked": config.AI_ENABLED is False,
    }


def scope_for(row):
    if row and row.default_service_id:
        return service_scope(row, row.service, row.model)
    return (
        OrganizationAIScope(
            row.organization_id, row.enabled, row.model, bool(row.encrypted_key)
        )
        if row
        else None
    )


def service_alias(provider, model):
    if model in get_args(ModelName) and detect_model_provider(model) == provider:
        return model
    return "gpt-4.1" if provider == "openai" else "qwen3.8-flash"


def service_scope(row, service, model, *, explicit=False):
    return OrganizationAIScope(
        row.organization_id,
        row.enabled,
        service_alias(service.provider, model),
        bool(service.encrypted_key),
        model,
        service.id if explicit else None,
        service.base_url == DEFAULT_PROVIDER_BASE_URL["qwen"]
        and service.provider == "qwen",
    )


async def select_conversation_model(db, selection):
    scope = active_ai_scope.get()
    if not scope or not scope.enabled or not scope.upstream_model:
        raise HTTPException(403, "Organization model unavailable")
    raw_id, _, name = selection.partition("|")
    try:
        service_id = UUID(raw_id)
    except ValueError:
        raise HTTPException(422, "Invalid model selection") from None
    row = await db.get(OrganizationAI, scope.organization_id)
    service = await db.get(OrganizationAIService, (scope.organization_id, service_id))
    if (
        not row
        or not row.enabled
        or not service
        or not service.encrypted_key
        or name not in service.models
    ):
        raise HTTPException(409, "Organization model unavailable")
    active_ai_scope.set(service_scope(row, service, name, explicit=True))


async def bind_organization(db, org_id):
    row = await db.get(OrganizationAI, org_id, populate_existing=True)
    active_ai_scope.set(scope_for(row))
    return row


async def bind_user_scope(db, request, user):
    active_ai_scope.set(None)
    uid = (
        config.SINGLE_LAB_UID
        if config.is_single_lab
        else request.headers.get("X-Airalogy-Organization")
    )
    if not uid:
        return
    org_id = await db.scalar(
        select(Lab.id)
        .join(LabUser, LabUser.lab_id == Lab.id)
        .where(Lab.uid == uid, LabUser.user_id == user.id)
    )
    if org_id:
        await bind_organization(db, org_id)


def proposed_key(data, row):
    if row and row.default_service_id:
        raise HTTPException(409, "Manage this organization through its model services")
    if (row.revision if row else 0) != data.expected_revision:
        raise HTTPException(409, "Organization AI settings changed")
    if data.api_key is not None:
        key = data.api_key.get_secret_value().strip()
        if not (
            1 <= len(key) <= 4096
            and key.isascii()
            and all(32 < ord(c) < 127 for c in key)
        ):
            raise HTTPException(422, "Invalid API key")
        return key
    if (
        row
        and row.encrypted_key
        and detect_model_provider(row.model) == detect_model_provider(data.model)
    ):
        return unseal(row)
    return None


async def save_settings(db, org_id, data):
    # Lock the parent so that two first-time writes also serialize.
    await db.scalar(select(Lab.id).where(Lab.id == org_id).with_for_update())
    row = await db.get(OrganizationAI, org_id, populate_existing=True)
    key = proposed_key(data, row)
    if data.clear_key:
        if data.api_key is not None or data.enabled:
            raise HTTPException(422, "Disable AI before removing its key")
        key = None
    if row and row.encrypted_key and not key and not data.clear_key:
        raise HTTPException(422, "Supply a new key when changing providers")
    if data.enabled and (config.AI_ENABLED is False or not key):
        raise HTTPException(
            409, "A permitted instance and an organization key are required"
        )
    if not row:
        row = OrganizationAI(organization_id=org_id)
        db.add(row)
    row.enabled = data.enabled
    row.model = data.model
    row.encrypted_key = seal(key, org_id, data.model) if key else None
    row.revision = data.expected_revision + 1
    await db.commit()
    return status(row)


async def test_key(row, data):
    if config.AI_ENABLED is False:
        raise HTTPException(409, "AI is disabled by the instance operator")
    key = proposed_key(data, row)
    if not key:
        raise HTTPException(422, "Supply a key for the selected provider")
    provider = detect_model_provider(data.model)
    from masterbrain.fastapi.provider_health import probe_provider

    health = await probe_provider(
        provider,
        api_key=key,
        base_url=DEFAULT_PROVIDER_BASE_URL[provider],
        default_model=data.model,
    )
    return {"status": health.status}


async def resolve_dispatch(usage):
    """Re-read the authoritative tenant at dispatch, including background work."""
    scope = active_ai_scope.get()
    org_id = UUID(str(usage.tenant_id)) if usage and usage.tenant_id else None
    project_id = UUID(str(usage.project_id)) if usage and usage.project_id else None
    if not org_id and not project_id and scope:
        org_id = scope.organization_id
    if not org_id and not project_id and not config.is_single_lab:
        return None
    async with sessionmanager.session() as db:
        if project_id:
            project_org = await db.scalar(
                select(Project.lab_id).where(Project.id == project_id)
            )
            if not project_org or (org_id and org_id != project_org):
                raise HTTPException(403, "Invalid organization for this project")
            org_id = project_org
        if not org_id:
            org_id = await db.scalar(
                select(Lab.id).where(Lab.uid == config.SINGLE_LAB_UID)
            )
        row = await db.get(OrganizationAI, org_id) if org_id else None
        if (
            scope
            and scope.selected_service_id
            and (org_id != scope.organization_id or not row or not row.service)
        ):
            raise HTTPException(409, "Organization model unavailable")
        if row:
            try:
                user_id = UUID(str(usage.user_id)) if usage else None
            except ValueError:
                user_id = None
            if not user_id or not await db.scalar(
                select(LabUser.user_id).where(
                    LabUser.lab_id == org_id, LabUser.user_id == user_id
                )
            ):
                raise HTTPException(
                    403, "Organization membership is required for its AI"
                )
            if (
                config.AI_ENABLED is False
                or not row.enabled
                or not (row.service if row.default_service_id else row).encrypted_key
            ):
                raise HTTPException(503, "Organization AI is disabled")
            if row.service:
                from app.services.organization_ai_catalog import (
                    allowed_base_url,
                    service_binding,
                )

                service, name = row.service, row.model
                if scope and scope.selected_service_id:
                    service = await db.get(
                        OrganizationAIService, (org_id, scope.selected_service_id)
                    )
                    name = scope.upstream_model
                    if (
                        scope.organization_id != org_id
                        or not service
                        or not service.encrypted_key
                        or name not in service.models
                    ):
                        raise HTTPException(409, "Organization model unavailable")
                url = allowed_base_url(service.base_url)
                return service_alias(service.provider, name), ProviderCredential(
                    service.provider,
                    decrypt_key(service.encrypted_key, service_binding(service)),
                    url,
                    name,
                )
            return row.model, ProviderCredential(
                detect_model_provider(row.model), unseal(row)
            )
    return None


@asynccontextmanager
async def provider_dispatch(path, body, usage):
    if config.AI_ENABLED is False:
        raise HTTPException(503, "AI is disabled by the instance operator")
    selection = await resolve_dispatch(usage)
    if not selection:
        yield body
        return
    model, credential = selection
    payload = dict(body)
    if path in {
        "endpoints/embeddings",
        "endpoints/chat/qa/stt",
        "endpoints/chat/qa/vision",
    }:
        if (
            detect_model_provider(body["model"]) != credential.provider
            or credential.base_url != DEFAULT_PROVIDER_BASE_URL[credential.provider]
        ):
            raise HTTPException(
                409, "The selected provider does not support this feature"
            )
        # Embedding, speech and vision endpoints request their own specialized model.
        credential = ProviderCredential(
            credential.provider, credential.key, credential.base_url
        )
    elif "use_model" in body:
        payload["use_model"] = {**body["use_model"], "name": model}
    elif isinstance(body.get("model"), dict):
        payload["model"] = {**body["model"], "name": model}
    elif isinstance(body.get("model"), str):
        payload["model"] = model
    with bind_credential(credential):
        yield payload
