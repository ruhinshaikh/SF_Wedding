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

    rsvp: Mapped["Rsvp | None"] = relationship(
        back_populates="guest", uselist=False, cascade="all, delete-orphan"
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


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
        if "dance_group_id" not in guest_have:
            conn.execute(text("ALTER TABLE guests ADD COLUMN dance_group_id INTEGER"))
        if "dance_type" not in have:
            conn.execute(text("ALTER TABLE rsvps ADD COLUMN dance_type VARCHAR(10) NOT NULL DEFAULT ''"))
