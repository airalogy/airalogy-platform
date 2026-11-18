from datetime import UTC, datetime
from typing import ClassVar

from app.config import config
from sqlalchemy import DateTime, cast, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class LegacyWallClock(TypeDecorator):
    """Keep the legacy SQL representation while accepting an offset on input."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return value.replace(tzinfo=None) if value is not None else None


def _row_time(context, name):
    # In SQLAlchemy 2.0.45 get_current_parameters() fails for multi-row ORM
    # VALUES. Read this row's bind group, including defaults from earlier columns.
    values = context.get_current_parameters(isolate_multiinsert_groups=False)
    group = context.current_column.key.rpartition("_m")[2]
    if group.isdigit():
        return values.get(f"{name}_m{group}")
    return values.get(f"{name}_m0", values.get(name))


def _new_instant(context):
    supplied = _row_time(context, "created_at")
    if supplied is None:
        return datetime.now(UTC)
    if supplied.tzinfo is not None:
        return supplied.astimezone(UTC)
    # An explicit historical wall clock has no identifiable offset.
    return None


def _local_wall_clock(context):
    instant = _row_time(context, "created_at_utc") or datetime.now(UTC)
    return instant.astimezone().replace(tzinfo=None)


class ActivityCreationTime:
    """Keep the original wall clock for legacy clients and capture an exact instant."""

    # SQLAlchemy evaluates column defaults in table order, including for bulk inserts.
    created_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=_new_instant, sort_order=-2
    )
    created_at: Mapped[datetime] = mapped_column(
        LegacyWallClock(), default=_local_wall_clock, sort_order=-1
    )
    json_exclude_fields: ClassVar[list[str]] = ["created_at_utc"]


def activity_instant(source):
    legacy = source.created_at
    if config.LEGACY_ACTIVITY_TIME_ZONE:
        legacy = func.timezone(config.LEGACY_ACTIVITY_TIME_ZONE, legacy)
    else:
        # Preserve the pre-upgrade PostgreSQL session interpretation of old rows.
        legacy = cast(legacy, DateTime(timezone=True))
    return func.coalesce(source.created_at_utc, legacy)
