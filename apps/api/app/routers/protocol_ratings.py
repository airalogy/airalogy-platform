"""Protocol Rating API. Mutations belong to the author, never the Protocol owner."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select

from app.database import DBSession
from app.models.lab import Lab
from app.models.protocol import Protocol
from app.models.protocol_rating import (
    ProtocolRating,
    ProtocolRatingRevision,
    ProtocolUse,
    ProtocolUseRecord,
)
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.research import ResearchAction, ResearchProtocolRun
from app.models.user import User
from app.routers.depends import CurrentUser, OptionalCurrentUser
from app.services.browser_paths import project_browser_path
from app.services.protocol_rating import RatingContext, audit, fields, summary

router = APIRouter(prefix="/protocol-ratings", tags=["protocol-rating"])


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RatingInput(StrictModel):
    expected_revision: int = Field(ge=0, strict=True)
    score: int = Field(ge=1, le=5, strict=True)
    comment: str = Field(default="", max_length=4000)
    conditions: str = Field(default="", max_length=2000)
    use_id: UUID | None = None
    public: bool = False
    active: bool = True


class UseFields(StrictModel):
    outcome: Literal["as_planned", "adjusted", "stopped", "unknown"]
    is_real: bool = False
    public: bool = False
    comment: str = Field(default="", max_length=4000)


class UseInput(UseFields):
    request_key: str = Field(min_length=8, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    record_ids: list[UUID] = Field(min_length=1, max_length=100)


class UseUpdate(UseFields):
    expected_revision: int = Field(ge=1, strict=True)
    active: bool = True


async def lock_author(db, user):
    # Serialize the user's create/update requests even before a unique row exists.
    await db.scalar(select(User).where(User.id == user.id).with_for_update())


async def public_allowed(ctx, protocol, project, records=()):
    if not await ctx.allowed(None, protocol, project) or not all(
        [await ctx.allowed(None, protocol, project, r) for r in records]
    ):
        raise HTTPException(403, "rating.public_source_required")


async def mine_result(ctx, protocol, version, user):
    children = list(
        (
            await ctx.db.scalars(
                select(Protocol.id).where(
                    Protocol.parent_protocol_id == protocol.id,
                    Protocol.parent_protocol_version == version.version,
                    Protocol.deleted_at.is_(None),
                )
            )
        ).all()
    )
    versions = list(
        (
            await ctx.db.scalars(
                select(ProtocolVersion.id).where(
                    or_(
                        ProtocolVersion.id == version.id,
                        ProtocolVersion.protocol_id.in_(children),
                    )
                )
            )
        ).all()
    )
    uses = list(
        (
            await ctx.db.scalars(
                select(ProtocolUse)
                .where(
                    ProtocolUse.user_id == user.id,
                    ProtocolUse.protocol_version_id.in_(versions),
                )
                .order_by(ProtocolUse.updated_at.desc())
            )
        ).all()
    )
    result = []
    for use in uses:
        source_version = await ctx.db.get(ProtocolVersion, use.protocol_version_id)
        try:
            source, source_project = await ctx.context(source_version.protocol_id)
        except HTTPException:
            continue
        if not await ctx.allowed(user, source, source_project):
            continue
        evidence = await ctx.receipt(use)
        source_lab = await ctx.db.get(Lab, source_project.lab_id)
        result.append(
            {
                "id": str(use.id),
                **fields(use),
                "revision": use.revision,
                "source_version_id": str(use.protocol_version_id),
                "source_protocol_id": str(source.id),
                "source_version": source_version.version,
                "source_name": source.name,
                "source_url": f"{project_browser_path(source_lab.uid, source_project.uid)}/protocols/{source.uid}/protocol",
                "record_ids": list(
                    map(
                        str,
                        (
                            await ctx.db.scalars(
                                select(ProtocolUseRecord.record_id).where(
                                    ProtocolUseRecord.use_id == use.id
                                )
                            )
                        ).all(),
                    )
                ),
                "eligible": bool(evidence and use.is_real and use.outcome != "unknown"),
            }
        )
    rating = await ctx.db.scalar(
        select(ProtocolRating).where(
            ProtocolRating.protocol_version_id == version.id,
            ProtocolRating.user_id == user.id,
        )
    )
    history = (
        list(
            (
                await ctx.db.scalars(
                    select(ProtocolRatingRevision)
                    .where(
                        ProtocolRatingRevision.kind == "rating",
                        ProtocolRatingRevision.object_id == rating.id,
                    )
                    .order_by(ProtocolRatingRevision.revision.desc())
                )
            ).all()
        )
        if rating
        else []
    )
    return {
        "rating": {"id": str(rating.id), **fields(rating), "revision": rating.revision}
        if rating
        else None,
        "uses": result,
        "history": [
            {
                "revision": h.revision,
                "payload": h.payload,
                "created_at": h.created_at.isoformat(),
            }
            for h in history
        ],
    }


@router.get("/{protocol_id}")
async def get_rating_summary(
    protocol_id: UUID,
    version: str,
    db_session: DBSession,
    current_user: OptionalCurrentUser,
    scope: Literal["accessible", "public"] = "accessible",
):
    return await summary(
        RatingContext(db_session),
        protocol_id,
        version,
        current_user,
        public_only=scope == "public",
    )


@router.get("/{protocol_id}/mine")
async def get_my_rating(
    protocol_id: UUID, version: str, db_session: DBSession, current_user: CurrentUser
):
    ctx = RatingContext(db_session)
    protocol, _, pv = await ctx.version(protocol_id, version, current_user)
    return await mine_result(ctx, protocol, pv, current_user)


@router.get("/{protocol_id}/records")
async def get_rating_records(
    protocol_id: UUID,
    version: str,
    db_session: DBSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    ctx = RatingContext(db_session)
    protocol, project, _ = await ctx.version(protocol_id, version, current_user)
    latest = (
        select(Record)
        .where(Record.protocol_id == protocol.id, Record.user_id == current_user.id)
        .distinct(Record.id)
        .order_by(Record.id, Record.version.desc())
        .subquery()
    )
    from sqlalchemy.orm import aliased

    row = aliased(Record, latest)
    rows = list(
        (
            await db_session.scalars(
                select(row)
                .where(row.protocol_version == version, row.deleted_at.is_(None))
                .order_by(row.created_at.desc(), row.id)
                .offset((page - 1) * page_size)
                .limit(page_size + 1)
            )
        ).all()
    )
    items = []
    for record in rows[:page_size]:
        if await ctx.allowed(current_user, protocol, project, record):
            link = await db_session.get(ProtocolUseRecord, record.id)
            items.append(
                {
                    "id": str(record.id),
                    "version": record.version,
                    "number": record.number,
                    "use_id": str(link.use_id) if link else None,
                }
            )
    return {"items": items, "has_more": len(rows) > page_size}


@router.put("/{protocol_id}/mine")
async def save_rating(
    protocol_id: UUID,
    version: str,
    payload: RatingInput,
    db_session: DBSession,
    current_user: CurrentUser,
):
    await lock_author(db_session, current_user)
    ctx = RatingContext(db_session)
    protocol, project, pv = await ctx.version(protocol_id, version, current_user)
    if payload.use_id and payload.active:
        use = await db_session.get(ProtocolUse, payload.use_id)
        if (
            not use
            or use.user_id != current_user.id
            or not await ctx.visible_use(use, current_user)
        ):
            raise HTTPException(422, "rating.evidence_unavailable")
        source, _, _ = await ctx.receipt(use)
        if use.protocol_version_id != pv.id and not (
            source.parent_protocol_id == protocol.id
            and source.parent_protocol_version == version
        ):
            raise HTTPException(422, "rating.version_mismatch")
        if payload.public and not await ctx.visible_use(use, None, public_only=True):
            raise HTTPException(403, "rating.public_source_required")
    if payload.public and payload.active:
        await public_allowed(ctx, protocol, project)
    rating = await db_session.scalar(
        select(ProtocolRating).where(
            ProtocolRating.protocol_version_id == pv.id,
            ProtocolRating.user_id == current_user.id,
        )
    )
    desired = payload.model_dump(exclude={"expected_revision"}, mode="json")
    if rating and fields(rating) == desired:
        return await mine_result(ctx, protocol, pv, current_user)
    if payload.expected_revision != (rating.revision if rating else 0):
        raise HTTPException(409, "rating.stale_revision")
    if rating is None:
        rating = ProtocolRating(
            protocol_version_id=pv.id, user_id=current_user.id, revision=1
        )
        db_session.add(rating)
    else:
        rating.revision += 1
    for key, value in payload.model_dump(exclude={"expected_revision"}).items():
        setattr(rating, key, value)
    await audit(db_session, rating, current_user)
    await db_session.commit()
    await db_session.refresh(rating)
    return await mine_result(ctx, protocol, pv, current_user)


@router.post("/{protocol_id}/uses")
async def create_use(
    protocol_id: UUID,
    version: str,
    payload: UseInput,
    db_session: DBSession,
    current_user: CurrentUser,
):
    await lock_author(db_session, current_user)
    ctx = RatingContext(db_session)
    protocol, project, pv = await ctx.version(protocol_id, version, current_user)
    existing = await db_session.scalar(
        select(ProtocolUse).where(
            ProtocolUse.user_id == current_user.id,
            ProtocolUse.request_key == payload.request_key,
        )
    )
    if existing:
        original = await db_session.scalar(
            select(ProtocolRatingRevision).where(
                ProtocolRatingRevision.kind == "use",
                ProtocolRatingRevision.object_id == existing.id,
                ProtocolRatingRevision.revision == 1,
            )
        )
        if (
            existing.protocol_version_id != pv.id
            or not original
            or original.payload.get("request") != payload.model_dump(mode="json")
        ):
            raise HTTPException(409, "rating.request_conflict")
        return {
            "id": str(existing.id),
            **fields(existing),
            "revision": existing.revision,
        }
    if len(set(payload.record_ids)) != len(payload.record_ids):
        raise HTTPException(422, "rating.duplicate_record")
    records = []
    runs = []
    for rid in sorted(payload.record_ids):
        record = await db_session.scalar(
            select(Record)
            .where(Record.id == rid)
            .order_by(Record.version.desc())
            .limit(1)
            .with_for_update()
        )
        if (
            not record
            or record.deleted_at
            or record.user_id != current_user.id
            or record.protocol_id != protocol.id
            or record.protocol_version != version
            or not await ctx.allowed(current_user, protocol, project, record)
        ):
            raise HTTPException(422, "rating.evidence_unavailable")
        if await db_session.get(ProtocolUseRecord, rid):
            raise HTTPException(409, "rating.record_already_linked")
        records.append(record)
        runs.extend(
            (
                await db_session.scalars(
                    select(ResearchProtocolRun).where(
                        ResearchProtocolRun.record_id == rid
                    )
                )
            ).all()
        )
    if len({run.id for run in runs}) > 1:
        raise HTTPException(422, "rating.different_runs")
    run = runs[0] if runs else None
    if run:
        action = await db_session.get(ResearchAction, run.action_id)
        if (
            run.protocol_version_id != pv.id
            or not action
            or action.status != "completed"
        ):
            raise HTTPException(422, "rating.run_not_completed")
        if await db_session.scalar(
            select(ProtocolUse).where(ProtocolUse.research_run_id == run.id)
        ):
            raise HTTPException(409, "rating.record_already_linked")
    if payload.public:
        await public_allowed(ctx, protocol, project, records)
    use = ProtocolUse(
        protocol_version_id=pv.id,
        user_id=current_user.id,
        request_key=payload.request_key,
        research_run_id=run.id if run else None,
        revision=1,
        active=True,
        **payload.model_dump(include={"is_real", "outcome", "public", "comment"}),
    )
    db_session.add(use)
    await audit(
        db_session,
        use,
        current_user,
        extra={
            "request": payload.model_dump(mode="json"),
            "records": [{"id": str(r.id), "version": r.version} for r in records],
        },
    )
    for record in records:
        db_session.add(
            ProtocolUseRecord(
                record_id=record.id, record_version=record.version, use_id=use.id
            )
        )
    await db_session.commit()
    return {"id": str(use.id), **fields(use), "revision": use.revision}


@router.put("/{protocol_id}/uses/{use_id}")
async def update_use(
    protocol_id: UUID,
    use_id: UUID,
    version: str,
    payload: UseUpdate,
    db_session: DBSession,
    current_user: CurrentUser,
):
    await lock_author(db_session, current_user)
    ctx = RatingContext(db_session)
    protocol, project, pv = await ctx.version(protocol_id, version, current_user)
    use = await db_session.get(ProtocolUse, use_id)
    if not use or use.user_id != current_user.id or use.protocol_version_id != pv.id:
        raise HTTPException(404, "rating.evidence_unavailable")
    desired = payload.model_dump(exclude={"expected_revision"})
    if all(getattr(use, k) == v for k, v in desired.items()):
        return {"id": str(use.id), **fields(use), "revision": use.revision}
    if use.revision != payload.expected_revision:
        raise HTTPException(409, "rating.stale_revision")
    # Withdrawal always remains possible. Re-enabling/changing real evidence rechecks it.
    use.active = payload.active
    evidence = await ctx.receipt(use)
    if payload.active and not evidence:
        raise HTTPException(422, "rating.evidence_unavailable")
    if payload.public and payload.active:
        await public_allowed(ctx, protocol, project, evidence[2])
    for key, value in desired.items():
        setattr(use, key, value)
    use.revision += 1
    await audit(db_session, use, current_user)
    await db_session.commit()
    return {"id": str(use.id), **fields(use), "revision": use.revision}


@router.get("/{protocol_id}/uses/{use_id}/history")
async def use_history(
    protocol_id: UUID,
    use_id: UUID,
    version: str,
    db_session: DBSession,
    current_user: CurrentUser,
):
    ctx = RatingContext(db_session)
    _, _, pv = await ctx.version(protocol_id, version, current_user)
    use = await db_session.get(ProtocolUse, use_id)
    if not use or use.user_id != current_user.id or use.protocol_version_id != pv.id:
        raise HTTPException(404, "rating.evidence_unavailable")
    history = (
        await db_session.scalars(
            select(ProtocolRatingRevision)
            .where(
                ProtocolRatingRevision.kind == "use",
                ProtocolRatingRevision.object_id == use.id,
            )
            .order_by(ProtocolRatingRevision.revision.desc())
        )
    ).all()
    return {
        "items": [
            {
                "revision": h.revision,
                "payload": h.payload,
                "created_at": h.created_at.isoformat(),
            }
            for h in history
        ]
    }
