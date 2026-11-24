from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

def database_url() -> str:
    """DATABASE_URL (e.g. Supabase Postgres) if set, otherwise a local SQLite file."""
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return f"sqlite:///{DATA_DIR / 'wedding.db'}"
    # Supabase / Heroku style URLs start with postgres:// ; SQLAlchemy needs the driver named.
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = database_url()
IS_SQLITE = DATABASE_URL.startswith("sqlite")
if IS_SQLITE:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # prepare_threshold=None keeps this working through Supabase's pooler (pgbouncer);
    # pre_ping replaces connections the pooler has closed.
    engine = create_engine(DATABASE_URL, connect_args={"prepare_threshold": None}, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_token() -> str:
    return secrets.token_urlsafe(8)


class Base(DeclarativeBase):
    pass


class Guest(Base):
    """One invitation = one household/guest row with a unique link."""

    __tablename__ = "guests"

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(32), unique=True, index=True, default=new_token)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(32), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    group: Mapped[str] = mapped_column(String(80), default="")  # e.g. "Bride family", "College friends"
    max_party: Mapped[int] = mapped_column(Integer, default=1)  # seats this invite covers
    events: Mapped[list] = mapped_column(JSON, default=list)  # event ids invited to
    invite_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    offer_stay: Mapped[bool] = mapped_column(Boolean, default=False)  # admin turns on the accommodation question
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    # who opened their link, and when (see /api/invite/{token}/ping)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ip: Mapped[str] = mapped_column(String(64), default="")
    visits: Mapped[int] = mapped_column(Integer, default=0)
    dance_group_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Sangeet dance group set by the admin
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)  # can open the dashboard after logging in with their number

    rsvp: Mapped["Rsvp | None"] = relationship(
        back_populates="guest", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )


class Rsvp(Base):
    __tablename__ = "rsvps"

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id"), unique=True)
    # {event_id: {"attending": bool, "headcount": int}}
    events: Mapped[dict] = mapped_column(JSON, default=dict)
    dietary: Mapped[str] = mapped_column(Text, default="")  # allergies / other notes
    # {"Vegetarian": 2, "Jain": 1}: how many people want each kind of food
    food: Mapped[dict] = mapped_column(JSON, default=dict)
    message: Mapped[str] = mapped_column(Text, default="")
    # Sangeet extras
    wants_to_dance: Mapped[bool] = mapped_column(Boolean, default=False)
    dance_with: Mapped[str] = mapped_column(String(300), default="")  # who is performing
    dance_notes: Mapped[str] = mapped_column(Text, default="")
    dance_type: Mapped[str] = mapped_column(String(10), default="")  # solo | couple | group
    songs: Mapped[list] = mapped_column(JSON, default=list)  # [{"title": str, "link": str}]
    # Accommodation
    needs_stay: Mapped[bool] = mapped_column(Boolean, default=False)
    stay_guests: Mapped[int] = mapped_column(Integer, default=0)
    stay_notes: Mapped[str] = mapped_column(Text, default="")
    responded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    guest: Mapped[Guest] = relationship(back_populates="rsvp")


class DanceGroup(Base):
    """A Sangeet dance group the admin creates (e.g. "Bride's cousins") and adds guests to."""

    __tablename__ = "dance_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    notes: Mapped[str] = mapped_column(Text, default="")
    songs: Mapped[list] = mapped_column(JSON, default=list)  # [{"title": str, "link": str}] chosen by the admins
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)  # guest id when a guest started it in their RSVP
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AdminSeen(Base):
    """Who is using the dashboard: one row per admin mobile number, updated as they use it."""

    __tablename__ = "admin_seen"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(16), unique=True, index=True)  # last 10 digits
    name: Mapped[str] = mapped_column(String(200), default="")
    via: Mapped[str] = mapped_column(String(16), default="")  # "number" (admin guest) or "password"
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_ip: Mapped[str] = mapped_column(String(64), default="")


class DanceMember(Base):
    """A guest in a Sangeet dance group. A guest can be in several groups."""

    __tablename__ = "dance_members"
    __table_args__ = (UniqueConstraint("guest_id", "group_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"))
    group_id: Mapped[int] = mapped_column(ForeignKey("dance_groups.id", ondelete="CASCADE"))
    added_by: Mapped[str] = mapped_column(String(10), default="admin")  # "admin" or "guest" (joined from their RSVP)


class GroupMark(Base):
    """Admin has sent this guest the link to (or added them to) a WhatsApp group."""

    __tablename__ = "group_marks"
    __table_args__ = (UniqueConstraint("guest_id", "group_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id", ondelete="CASCADE"))
    group_id: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(80), default="Other")
    contact_person: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    website: Mapped[str] = mapped_column(String(300), default="")
    total_cost: Mapped[float] = mapped_column(default=0)
    amount_paid: Mapped[float] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(40), default="Shortlisted")
    event_ids: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


def init_db() -> None:
    Base.metadata.create_all(engine)
    # create_all never alters an existing table, so add columns introduced later to databases made before them.
    # Plain DDL below works on both SQLite and Postgres.
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    have = {c["name"] for c in insp.get_columns("rsvps")}
    guest_have = {c["name"] for c in insp.get_columns("guests")}
    with engine.begin() as conn:
        if IS_SQLITE:  # older SQLite files only; a fresh database is created complete
            for name, ddl in {"last_seen": "DATETIME", "last_ip": "VARCHAR(64) NOT NULL DEFAULT ''", "visits": "INTEGER NOT NULL DEFAULT 0"}.items():
                if name not in guest_have:
                    conn.execute(text(f"ALTER TABLE guests ADD COLUMN {name} {ddl}"))
            if "offer_stay" not in guest_have:
                conn.execute(text("ALTER TABLE guests ADD COLUMN offer_stay BOOLEAN NOT NULL DEFAULT 0"))
            for name, ddl in {
                "needs_stay": "BOOLEAN NOT NULL DEFAULT 0",
                "stay_guests": "INTEGER NOT NULL DEFAULT 0",
                "stay_notes": "TEXT NOT NULL DEFAULT ''",
                "food": "JSON NOT NULL DEFAULT '{}'",
            }.items():
                if name not in have:
                    conn.execute(text(f"ALTER TABLE rsvps ADD COLUMN {name} {ddl}"))
        dg_have = {c["name"] for c in insp.get_columns("dance_groups")}
        if "songs" not in dg_have:
            conn.execute(text("ALTER TABLE dance_groups ADD COLUMN songs JSON NOT NULL DEFAULT '[]'"))
        if "created_by" not in dg_have:
            conn.execute(text("ALTER TABLE dance_groups ADD COLUMN created_by INTEGER"))
        if "added_by" not in {c["name"] for c in insp.get_columns("dance_members")}:
            conn.execute(text("ALTER TABLE dance_members ADD COLUMN added_by VARCHAR(10) NOT NULL DEFAULT 'admin'"))
        if "is_admin" not in guest_have:
            conn.execute(text("ALTER TABLE guests ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE"))
        if "dance_group_id" not in guest_have:
            conn.execute(text("ALTER TABLE guests ADD COLUMN dance_group_id INTEGER"))
        if "dance_type" not in have:
            conn.execute(text("ALTER TABLE rsvps ADD COLUMN dance_type VARCHAR(10) NOT NULL DEFAULT ''"))
    # guests used to be in one dance group (guests.dance_group_id): carry those over to dance_members once
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO dance_members (guest_id, group_id) "
            "SELECT g.id, g.dance_group_id FROM guests g "
            "WHERE g.dance_group_id IS NOT NULL "
            "AND EXISTS (SELECT 1 FROM dance_groups d WHERE d.id = g.dance_group_id) "
            "AND NOT EXISTS (SELECT 1 FROM dance_members m WHERE m.guest_id = g.id AND m.group_id = g.dance_group_id)"
        ))
        conn.execute(text("UPDATE guests SET dance_group_id = NULL WHERE dance_group_id IS NOT NULL"))
