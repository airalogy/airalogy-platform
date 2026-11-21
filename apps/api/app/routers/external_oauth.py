"""Pre-registered public clients, S256 PKCE and explicit per-Project user consent.

No implicit grants, remote client metadata fetches, refresh tokens or client secrets.
"""

import base64
import hashlib
import re
import secrets
from datetime import timedelta
from typing import Annotated, Literal
from urllib.parse import urlencode, urlsplit
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select, update

from app.config import config
from app.database import DBSession
from app.models.external_access import ExternalGrant, ExternalOperation
from app.models.external_research import ExternalOAuthClient, ExternalOAuthCode
from app.routers.depends import CurrentUser
from app.services import external_access as service

router = APIRouter(prefix="/external-access/oauth", tags=["external-access"])
discovery = APIRouter()


def origin():
    return config.SITE_URL.rstrip("/")


def resource(value):
    if value not in (origin() + "/api/mcp", origin() + "/api/external-access"):
        raise HTTPException(400, "invalid_target")
    return value


def redirect(value):
    parsed = urlsplit(value)
    if (
        parsed.username
        or parsed.password
        or parsed.fragment
        or parsed.query
        or not parsed.hostname
        or any(ord(c) < 32 for c in value)
    ):
        raise ValueError("Redirect URI must not contain credentials, query or fragment")
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "[::1]", "::1")
    ):
        raise ValueError("HTTPS or a literal loopback redirect is required")
    return value


class ClientInput(service.StrictModel):
    name: str = Field(min_length=1, max_length=100)
    redirect_uris: list[str] = Field(min_length=1, max_length=5)

    @field_validator("redirect_uris")
    @classmethod
    def uris(cls, values):
        if any(len(v) > 2048 for v in values):
            raise ValueError("Redirect URI too long")
        return sorted({redirect(v) for v in values})


class Authorization(service.StrictModel):
    response_type: Literal["code"] = "code"
    client_id: UUID
    redirect_uri: str = Field(max_length=2048)
    code_challenge: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    code_challenge_method: Literal["S256"]
    state: str = Field(min_length=16, max_length=512)
    scope: str = Field(default="protocols:read", max_length=1024)
    resource: str = Field(max_length=2048)


class AuthorizationQuery(Authorization):
    # RFC 6749 section 3.1 requires ignoring unrecognized authorization parameters.
    model_config = ConfigDict(extra="ignore")


class Consent(Authorization, service.ProjectCoverage):
    approved_scopes: list[str] | None = Field(default=None, min_length=1, max_length=32)
    project_id: UUID | None = None
    organization_id: UUID | None = None
    expires_in_days: int = Field(default=1, ge=1, le=7)
    approve: bool


async def checked_client(db, params):
    resource(params.resource)
    client = await db.get(ExternalOAuthClient, params.client_id)
    if client is None or params.redirect_uri not in client.redirect_uris:
        raise HTTPException(400, "invalid_client_or_redirect_uri")
    scopes = set(params.scope.split())
    if not scopes or not scopes <= service.SCOPES:
        raise HTTPException(400, "invalid_scope")
    return client


@router.post("/clients")
async def register(params: ClientInput, db: DBSession, user: CurrentUser):
    await service.lock_user_calls(db, user.id)
    count = await db.scalar(
        select(func.count())
        .select_from(ExternalOAuthClient)
        .where(ExternalOAuthClient.user_id == user.id)
    )
    if count >= 20:
        raise HTTPException(429, "client_registration_limit")
    client = ExternalOAuthClient(
        user_id=user.id,
        name=params.name,
        redirect_uris=params.redirect_uris,
        created_at=service.now(),
    )
    db.add(client)
    await db.flush()
    service.audit(db, user.id, "oauth.client_registered", client_id=str(client.id))
    result = {
        "client_id": str(client.id),
        "client_name": client.name,
        "redirect_uris": client.redirect_uris,
        "token_endpoint_auth_method": "none",
    }
    await db.commit()
    return result


@router.get("/clients")
async def clients(db: DBSession, user: CurrentUser):
    rows = (
        await db.scalars(
            select(ExternalOAuthClient)
            .where(ExternalOAuthClient.user_id == user.id)
            .order_by(ExternalOAuthClient.created_at.desc())
            .limit(20)
        )
    ).all()
    return {
        "items": [
            {"client_id": str(c.id), "name": c.name, "redirect_uris": c.redirect_uris}
            for c in rows
        ]
    }


@router.post("/request")
async def request_info(params: Authorization, db: DBSession, user: CurrentUser):
    client = await checked_client(db, params)
    return {
        "client_name": client.name,
        "redirect_uri": params.redirect_uri,
        "resource": params.resource,
        "scopes": sorted(set(params.scope.split())),
    }


@router.get("/authorize")
async def authorize(db: DBSession, params: Annotated[AuthorizationQuery, Query()]):
    await checked_client(db, params)
    return RedirectResponse(
        origin()
        + "/authorize?"
        + urlencode({**params.model_dump(mode="json"), "external": "1"}),
        status_code=303,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@router.post("/consent")
async def consent(params: Consent, db: DBSession, user: CurrentUser):
    client = await checked_client(db, params)
    if not params.approve:
        return {
            "redirect_to": params.redirect_uri
            + "?"
            + urlencode({"error": "access_denied", "state": params.state})
        }
    requested = set(params.scope.split())
    approved = (
        set(params.approved_scopes) if params.approved_scopes is not None else requested
    )
    if not approved <= requested:
        raise HTTPException(400, "invalid_scope")
    created = await service.create_grant(
        db,
        user,
        service.GrantInput(
            name=client.name,
            project_id=params.project_id,
            organization_id=params.organization_id,
            project_coverage=params.project_coverage,
            selected_project_ids=params.selected_project_ids,
            scopes=sorted(approved),
            expires_in_days=params.expires_in_days,
        ),
    )
    grant = await db.get(ExternalGrant, UUID(str(created["grant"]["id"])))
    grant.audience = params.resource
    grant.oauth_client_id = client.id
    # The temporary secret is discarded; only a successful one-time PKCE exchange reveals a token.
    code = secrets.token_urlsafe(36)
    db.add(
        ExternalOAuthCode(
            code_hash=hashlib.sha256(code.encode()).hexdigest(),
            client_id=client.id,
            grant_id=grant.id,
            redirect_uri=params.redirect_uri,
            challenge=params.code_challenge,
            resource=params.resource,
            expires_at=service.now() + timedelta(minutes=5),
        )
    )
    await db.execute(
        delete(ExternalOAuthCode).where(
            ExternalOAuthCode.expires_at < service.now() - timedelta(days=1)
        )
    )
    service.audit(db, user.id, "oauth.consent", grant.id, client_id=str(client.id))
    await db.commit()
    return {
        "redirect_to": params.redirect_uri
        + "?"
        + urlencode({"code": code, "state": params.state})
    }


@router.post("/token")
async def token(
    db: DBSession,
    client_id: Annotated[UUID, Form()],
    grant_type: str = Form(),
    code: str = Form(max_length=100),
    code_verifier: str = Form(max_length=128),
    redirect_uri: str = Form(max_length=2048),
    resource: str = Form(max_length=2048),
):
    headers = {"Cache-Control": "no-store", "Pragma": "no-cache"}

    def invalid():
        return JSONResponse(
            {"error": "invalid_grant"}, status_code=400, headers=headers
        )

    if grant_type != "authorization_code" or not re.fullmatch(
        r"[A-Za-z0-9._~-]{43,128}", code_verifier
    ):
        return invalid()
    identity = hashlib.sha256(code.encode()).hexdigest()
    row = await db.get(ExternalOAuthCode, identity)
    if (
        row is None
        or row.consumed_at
        or row.expires_at <= service.now()
        or row.client_id != client_id
        or row.redirect_uri != redirect_uri
        or row.resource != resource
    ):
        return invalid()
    computed = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    if not secrets.compare_digest(computed, row.challenge):
        return invalid()
    grant = await db.get(ExternalGrant, row.grant_id)
    try:
        access = await service.authorize(db, grant_id=grant.id, owner_id=grant.user_id)
    except HTTPException:
        return invalid()
    row = await db.scalar(
        select(ExternalOAuthCode)
        .where(ExternalOAuthCode.code_hash == identity)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row.consumed_at or row.expires_at <= service.now():
        return invalid()
    row.consumed_at = service.now()
    secret = "apl_" + secrets.token_urlsafe(36)
    access.grant.token_hash = hashlib.sha256(secret.encode()).hexdigest()
    access.grant.token_prefix = secret[:12]
    result = {
        "access_token": secret,
        "token_type": "Bearer",
        "expires_in": max(0, int((grant.expires_at - service.now()).total_seconds())),
        "scope": " ".join(grant.scopes),
    }
    service.audit(
        db, access.user.id, "oauth.exchanged", grant.id, client_id=str(client_id)
    )
    await db.commit()
    return JSONResponse(result, headers=headers)


@discovery.get("/.well-known/oauth-authorization-server")
async def metadata():
    return {
        "issuer": origin(),
        "authorization_endpoint": origin() + "/api/external-access/oauth/authorize",
        "token_endpoint": origin() + "/api/external-access/oauth/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "token_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": sorted(service.SCOPES),
    }


@discovery.get("/.well-known/oauth-protected-resource")
@discovery.get("/.well-known/oauth-protected-resource/api/mcp")
async def protected_metadata():
    return {
        "resource": origin() + "/api/mcp",
        "authorization_servers": [origin()],
        "scopes_supported": sorted(service.SCOPES),
        "bearer_methods_supported": ["header"],
    }


@router.delete("/clients/{client_id}")
async def delete_client(client_id: UUID, db: DBSession, user: CurrentUser):
    client = await db.get(ExternalOAuthClient, client_id)
    if client is None or client.user_id != user.id:
        raise HTTPException(404, "Client not found")
    # One statement takes grant locks without taking the separate caller gate.
    await db.execute(
        update(ExternalGrant)
        .where(ExternalGrant.oauth_client_id == client_id)
        .values(revoked_at=service.now())
    )
    await db.execute(
        update(ExternalOperation)
        .where(
            ExternalOperation.grant_id.in_(
                select(ExternalGrant.id).where(
                    ExternalGrant.oauth_client_id == client_id
                )
            ),
            ExternalOperation.state.in_(["pending", "approved"]),
        )
        .values(state="revoked", payload={})
    )
    await db.delete(client)
    service.audit(db, user.id, "oauth.client_deleted", client_id=str(client_id))
    await db.commit()
    return {"deleted": True}
