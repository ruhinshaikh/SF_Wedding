from __future__ import annotations

import secrets
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

engine = create_engine(
    f"sqlite:///{DATA_DIR / 'wedding.db'}", connect_args={"check_same_thread": False}
)
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

    rsvp: Mapped["Rsvp | None"] = relationship(
        back_populates="guest", uselist=False, cascade="all, delete-orphan"
    )


class Rsvp(Base):
    __tablename__ = "rsvps"

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id"), unique=True)
    # {event_id: {"attending": bool, "headcount": int}}
    events: Mapped[dict] = mapped_column(JSON, default=dict)
    dietary: Mapped[str] = mapped_column(Text, default="")
    message: Mapped[str] = mapped_column(Text, default="")
    # Sangeet extras
    wants_to_dance: Mapped[bool] = mapped_column(Boolean, default=False)
    dance_with: Mapped[str] = mapped_column(String(300), default="")  # who is performing
    dance_notes: Mapped[str] = mapped_column(Text, default="")
    songs: Mapped[list] = mapped_column(JSON, default=list)  # [{"title": str, "link": str}]
    # Accommodation
    needs_stay: Mapped[bool] = mapped_column(Boolean, default=False)
    stay_guests: Mapped[int] = mapped_column(Integer, default=0)
    stay_notes: Mapped[str] = mapped_column(Text, default="")
    responded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    guest: Mapped[Guest] = relationship(back_populates="rsvp")


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


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int | None] = mapped_column(ForeignKey("guests.id"), nullable=True)
    uploader_name: Mapped[str] = mapped_column(String(200), default="")
    original_name: Mapped[str] = mapped_column(String(300))
    stored_name: Mapped[str] = mapped_column(String(300))
    mime_type: Mapped[str] = mapped_column(String(100), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    drive_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|synced|failed|disabled
    drive_file_id: Mapped[str] = mapped_column(String(200), default="")
    drive_link: Mapped[str] = mapped_column(String(500), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


def init_db() -> None:
    Base.metadata.create_all(engine)
    # create_all never alters an existing table, so add columns introduced later to databases made before them.
    from sqlalchemy import inspect, text

    have = {c["name"] for c in inspect(engine).get_columns("rsvps")}
    wanted = {
        "needs_stay": "BOOLEAN NOT NULL DEFAULT 0",
        "stay_guests": "INTEGER NOT NULL DEFAULT 0",
        "stay_notes": "TEXT NOT NULL DEFAULT ''",
    }
    guest_have = {c["name"] for c in inspect(engine).get_columns("guests")}
    with engine.begin() as conn:
        if "offer_stay" not in guest_have:
            conn.execute(text("ALTER TABLE guests ADD COLUMN offer_stay BOOLEAN NOT NULL DEFAULT 0"))
        for name, ddl in wanted.items():
            if name not in have:
                conn.execute(text(f"ALTER TABLE rsvps ADD COLUMN {name} {ddl}"))
