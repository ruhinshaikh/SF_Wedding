from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import io
import json
import os
import time
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

import drive
from db import UPLOAD_DIR, Guest, GroupMark, Photo, Rsvp, SessionLocal, Vendor, init_db

CONFIG_PATH = Path(__file__).parent / "config.json"
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "50")) * 1024 * 1024
DEFAULT_COUNTRY_CODE = os.getenv("DEFAULT_COUNTRY_CODE", "91")
SESSION_SECONDS = 60 * 60 * 24 * 14

app = FastAPI(title="Wedding Invitation API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text())


def event_ids() -> list[str]:
    return [e["id"] for e in load_config()["events"]]


# ---------------------------------------------------------------- admin auth


def _secret() -> bytes:
    return os.getenv("SECRET_KEY", "dev-secret-change-me").encode()


def make_admin_token() -> str:
    expiry = str(int(time.time()) + SESSION_SECONDS)
    sig = hmac.new(_secret(), expiry.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{expiry}.{sig}".encode()).decode()


def valid_admin_token(token: str) -> bool:
    try:
        expiry, sig = base64.urlsafe_b64decode(token.encode()).decode().split(".", 1)
        good = hmac.new(_secret(), expiry.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, good) and int(expiry) > time.time()
    except Exception:
        return False


def require_admin(request: Request, t: Optional[str] = Query(default=None)) -> None:
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else (t or "")
    if not token or not valid_admin_token(token):
        raise HTTPException(401, "Admin login required")


class LoginIn(BaseModel):
    password: str


@app.post("/api/admin/login")
def admin_login(body: LoginIn):
    expected = os.getenv("ADMIN_PASSWORD", "")
    if not expected or not hmac.compare_digest(body.password, expected):
        time.sleep(0.5)
        raise HTTPException(401, "Wrong password")
    return {"token": make_admin_token()}


# ---------------------------------------------------------------- helpers


def normalise_phone(raw: str) -> str:
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) == 10:
        digits = DEFAULT_COUNTRY_CODE + digits
    return digits


def invite_url(guest: Guest) -> str:
    return f"{os.getenv('PUBLIC_URL', 'http://localhost:5173').rstrip('/')}/i/{guest.token}"


def whatsapp_url(guest: Guest) -> str:
    cfg = load_config()
    text = (
        f"Hi {guest.name}! You're invited to the wedding of {cfg['couple']['title']}. "
        f"Please open your personal invitation and RSVP here: {invite_url(guest)}"
    )
    phone = normalise_phone(guest.phone)
    base = f"https://wa.me/{phone}" if phone else "https://wa.me/"
    return f"{base}?text={quote(text)}"


def public_config(cfg: dict) -> dict:
    """Config safe to show anyone: group invite links are only given to attending guests."""
    return {k: v for k, v in cfg.items() if k != "whatsapp_groups"}


def attending_events(guest: Guest) -> set[str]:
    if not guest.rsvp:
        return set()
    return {eid for eid, v in guest.rsvp.events.items() if v.get("attending")}


def in_group(guest: Guest, group: dict) -> bool:
    """Attending guests join the group for their event; "all" means attending anything."""
    going = attending_events(guest)
    target = group.get("for", "all")
    return bool(going) if target == "all" else target in going


def group_message_url(guest: Guest, group: dict) -> str:
    text = (
        f"Hi {guest.name}! Here is the link to join our WhatsApp group for {group['name']}: "
        f"{group.get('url', '')}"
    )
    phone = normalise_phone(guest.phone)
    base = f"https://wa.me/{phone}" if phone else "https://wa.me/"
    return f"{base}?text={quote(text)}"


def rsvp_status(guest: Guest) -> str:
    if not guest.rsvp:
        return "pending"
    attending = any(v.get("attending") for v in guest.rsvp.events.values())
    return "attending" if attending else "declined"


def rsvp_headcount(guest: Guest) -> int:
    if not guest.rsvp:
        return 0
    return max([v.get("headcount", 0) for v in guest.rsvp.events.values() if v.get("attending")] or [0])


def rsvp_dict(r: Rsvp | None) -> dict | None:
    if not r:
        return None
    return {
        "events": r.events,
        "dietary": r.dietary,
        "message": r.message,
        "wants_to_dance": r.wants_to_dance,
        "dance_with": r.dance_with,
        "dance_notes": r.dance_notes,
        "songs": r.songs,
        "needs_stay": r.needs_stay,
        "stay_guests": r.stay_guests,
        "stay_notes": r.stay_notes,
        "responded_at": r.responded_at.isoformat(),
    }


def guest_dict(g: Guest) -> dict:
    return {
        "id": g.id,
        "token": g.token,
        "name": g.name,
        "phone": g.phone,
        "email": g.email,
        "group": g.group,
        "max_party": g.max_party,
        "events": g.events,
        "invite_sent": g.invite_sent,
        "notes": g.notes,
        "offer_stay": g.offer_stay,
        "invite_url": invite_url(g),
        "whatsapp_url": whatsapp_url(g),
        "status": rsvp_status(g),
        "headcount": rsvp_headcount(g),
        "rsvp": rsvp_dict(g.rsvp),
    }


# ---------------------------------------------------------------- public: config + invitation + RSVP


@app.get("/api/config")
def get_config():
    return public_config(load_config())


def guest_by_token(db: Session, token: str) -> Guest:
    g = db.scalar(select(Guest).where(Guest.token == token))
    if not g:
        raise HTTPException(404, "Invitation not found")
    return g


@app.get("/api/invite/{token}")
def get_invite(token: str, db: Session = Depends(get_db)):
    g = guest_by_token(db, token)
    cfg = load_config()
    return {
        "guest": {"name": g.name, "max_party": g.max_party, "events": g.events, "offer_stay": g.offer_stay},
        "config": {**public_config(cfg), "events": [e for e in cfg["events"] if e["id"] in g.events]},
        "rsvp": rsvp_dict(g.rsvp),
    }


@app.get("/api/invite/{token}/groups")
def invite_groups(token: str, db: Session = Depends(get_db)):
    """WhatsApp groups this guest can join. Only returned once they have said yes."""
    g = guest_by_token(db, token)
    return {
        "groups": [
            {"id": grp["id"], "name": grp["name"], "url": grp["url"]}
            for grp in load_config().get("whatsapp_groups", [])
            if grp.get("url") and in_group(g, grp)
        ]
    }


class EventAnswer(BaseModel):
    attending: bool
    headcount: int = Field(default=1, ge=0, le=20)


class SongIn(BaseModel):
    title: str = Field(default="", max_length=200)
    link: str = Field(default="", max_length=500)


class RsvpIn(BaseModel):
    events: dict[str, EventAnswer]
    dietary: str = Field(default="", max_length=1000)
    message: str = Field(default="", max_length=2000)
    wants_to_dance: bool = False
    dance_with: str = Field(default="", max_length=300)
    dance_notes: str = Field(default="", max_length=1000)
    songs: list[SongIn] = Field(default_factory=list, max_length=5)
    needs_stay: bool = False
    stay_guests: int = Field(default=0, ge=0, le=20)
    stay_notes: str = Field(default="", max_length=1000)


@app.post("/api/invite/{token}/rsvp")
def submit_rsvp(token: str, body: RsvpIn, db: Session = Depends(get_db)):
    g = guest_by_token(db, token)
    cfg = load_config()
    sangeet_ids = {e["id"] for e in cfg["events"] if e.get("is_sangeet")}

    answers: dict[str, dict] = {}
    valid_ids = {e["id"] for e in cfg["events"]}
    for eid in [x for x in g.events if x in valid_ids]:
        a = body.events.get(eid)
        if a is None:
            raise HTTPException(422, f"Please answer for every event (missing: {eid})")
        if a.attending and not (1 <= a.headcount <= g.max_party):
            raise HTTPException(422, f"Headcount must be between 1 and {g.max_party}")
        answers[eid] = {"attending": a.attending, "headcount": a.headcount if a.attending else 0}

    attending_sangeet = any(answers.get(s, {}).get("attending") for s in sangeet_ids)
    wants = body.wants_to_dance and attending_sangeet
    songs: list[dict] = []
    if wants:
        for s in body.songs:
            title, link = s.title.strip(), s.link.strip()
            if not title and not link:
                continue
            if link and not link.lower().startswith(("http://", "https://")):
                raise HTTPException(422, f"Song link must start with http:// or https:// ({link[:40]})")
            songs.append({"title": title, "link": link})
        if not songs:
            raise HTTPException(422, "Please add at least one song (a link or a title)")

    any_attending = any(a["attending"] for a in answers.values())
    stay = body.needs_stay and any_attending and g.offer_stay  # only guests the admin offered a stay to
    if stay and not (1 <= body.stay_guests <= g.max_party):
        raise HTTPException(422, f"Number of people needing a room must be between 1 and {g.max_party}")

    r = g.rsvp or Rsvp(guest=g)
    r.needs_stay = stay
    r.stay_guests = body.stay_guests if stay else 0
    r.stay_notes = body.stay_notes.strip() if stay else ""
    r.events = answers
    r.dietary = body.dietary.strip()
    r.message = body.message.strip()
    r.wants_to_dance = wants
    r.dance_with = body.dance_with.strip() if wants else ""
    r.dance_notes = body.dance_notes.strip() if wants else ""
    r.songs = songs
    from db import now

    r.responded_at = now()
    db.add(r)
    db.commit()
    return {"ok": True, "rsvp": rsvp_dict(r)}


# ---------------------------------------------------------------- photos


def sync_photo(photo_id: int) -> None:
    db = SessionLocal()
    try:
        p = db.get(Photo, photo_id)
        if not p or p.drive_status == "synced":
            return
        path = UPLOAD_DIR / p.stored_name
        if not drive.drive_configured():
            p.drive_status = "disabled"
            db.commit()
            return
        if not path.exists():
            p.drive_status, p.error = "failed", "Local file missing"
            db.commit()
            return
        try:
            label = f"{p.uploader_name or 'guest'} - {p.original_name}"
            file_id, link = drive.upload_file(str(path), label, p.mime_type)
            p.drive_file_id, p.drive_link, p.drive_status, p.error = file_id, link, "synced", ""
            path.unlink(missing_ok=True)
        except Exception as e:  # keep the local file so it can be retried
            p.drive_status, p.error = "failed", str(e)[:500]
        db.commit()
    finally:
        db.close()


@app.post("/api/invite/{token}/photos")
async def upload_photos(
    token: str,
    background: BackgroundTasks,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    g = guest_by_token(db, token)
    if len(files) > 25:
        raise HTTPException(422, "Please upload up to 25 files at a time")
    saved = []
    for f in files:
        mime = f.content_type or ""
        if not (mime.startswith("image/") or mime.startswith("video/")):
            raise HTTPException(422, f"{f.filename}: only photos and videos are allowed")
        ext = Path(f.filename or "").suffix.lower()[:10]
        stored = f"{uuid.uuid4().hex}{ext}"
        size = 0
        with open(UPLOAD_DIR / stored, "wb") as out:
            while chunk := await f.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    out.close()
                    (UPLOAD_DIR / stored).unlink(missing_ok=True)
                    raise HTTPException(413, f"{f.filename} is larger than {MAX_UPLOAD_BYTES // 1048576} MB")
                out.write(chunk)
        p = Photo(
            guest_id=g.id,
            uploader_name=g.name,
            original_name=f.filename or stored,
            stored_name=stored,
            mime_type=mime,
            size_bytes=size,
        )
        db.add(p)
        db.flush()
        saved.append(p.id)
    db.commit()
    for pid in saved:
        background.add_task(sync_photo, pid)
    return {"ok": True, "count": len(saved)}


# ---------------------------------------------------------------- admin: summary


@app.get("/api/admin/summary", dependencies=[Depends(require_admin)])
def summary(db: Session = Depends(get_db)):
    cfg = load_config()
    guests = db.scalars(select(Guest)).all()
    vendors = db.scalars(select(Vendor)).all()
    photos = db.scalars(select(Photo)).all()

    per_event = []
    for e in cfg["events"]:
        invited = [g for g in guests if e["id"] in g.events]
        attending = [g for g in invited if g.rsvp and g.rsvp.events.get(e["id"], {}).get("attending")]
        declined = [g for g in invited if g.rsvp and not g.rsvp.events.get(e["id"], {}).get("attending")]
        per_event.append(
            {
                "id": e["id"],
                "name": e["name"],
                "invited_households": len(invited),
                "invited_seats": sum(g.max_party for g in invited),
                "attending_guests": sum(g.rsvp.events[e["id"]]["headcount"] for g in attending),
                "declined_households": len(declined),
                "pending_households": len(invited) - len(attending) - len(declined),
            }
        )

    dancers = [g for g in guests if g.rsvp and g.rsvp.wants_to_dance]
    return {
        "households": len(guests),
        "seats": sum(g.max_party for g in guests),
        "responded": sum(1 for g in guests if g.rsvp),
        "invites_sent": sum(1 for g in guests if g.invite_sent),
        "per_event": per_event,
        "dance_acts": len(dancers),
        "stay_households": sum(1 for g in guests if g.rsvp and g.rsvp.needs_stay),
        "stay_guests": sum(g.rsvp.stay_guests for g in guests if g.rsvp and g.rsvp.needs_stay),
        "songs": sum(len(g.rsvp.songs) for g in dancers),
        "vendors": len(vendors),
        "vendor_total": sum(v.total_cost for v in vendors),
        "vendor_paid": sum(v.amount_paid for v in vendors),
        "photos": len(photos),
        "photos_synced": sum(1 for p in photos if p.drive_status == "synced"),
        "drive_configured": drive.drive_configured(),
        "drive_folder": drive.folder_link(),
        "rsvp_deadline": cfg.get("rsvp_deadline"),
    }


# ---------------------------------------------------------------- admin: guests


class GuestIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str = ""
    email: str = ""
    group: str = ""
    max_party: int = Field(default=1, ge=1, le=20)
    events: list[str] = Field(default_factory=list)
    notes: str = ""
    offer_stay: bool = False


def _clean_events(evs: list[str]) -> list[str]:
    valid = event_ids()
    return [e for e in valid if e in evs]  # keeps config order, drops unknown ids


@app.get("/api/admin/guests", dependencies=[Depends(require_admin)])
def list_guests(db: Session = Depends(get_db)):
    guests = db.scalars(select(Guest).order_by(Guest.name)).all()
    return [guest_dict(g) for g in guests]


@app.post("/api/admin/guests", dependencies=[Depends(require_admin)])
def create_guest(body: GuestIn, db: Session = Depends(get_db)):
    g = Guest(**body.model_dump())
    g.events = _clean_events(body.events) or event_ids()
    db.add(g)
    db.commit()
    return guest_dict(g)


@app.put("/api/admin/guests/{gid}", dependencies=[Depends(require_admin)])
def update_guest(gid: int, body: GuestIn, db: Session = Depends(get_db)):
    g = db.get(Guest, gid)
    if not g:
        raise HTTPException(404, "Guest not found")
    for k, v in body.model_dump().items():
        setattr(g, k, v)
    g.events = _clean_events(body.events)
    db.commit()
    return guest_dict(g)


@app.delete("/api/admin/guests/{gid}", dependencies=[Depends(require_admin)])
def delete_guest(gid: int, db: Session = Depends(get_db)):
    g = db.get(Guest, gid)
    if not g:
        raise HTTPException(404, "Guest not found")
    db.delete(g)
    db.commit()
    return {"ok": True}


@app.post("/api/admin/guests/{gid}/sent", dependencies=[Depends(require_admin)])
def mark_sent(gid: int, sent: bool = True, db: Session = Depends(get_db)):
    g = db.get(Guest, gid)
    if not g:
        raise HTTPException(404, "Guest not found")
    g.invite_sent = sent
    db.commit()
    return guest_dict(g)


@app.get("/api/admin/groups", dependencies=[Depends(require_admin)])
def admin_groups(db: Session = Depends(get_db)):
    guests = db.scalars(select(Guest).order_by(Guest.name)).all()
    marks = {(m.guest_id, m.group_id) for m in db.scalars(select(GroupMark)).all()}
    out = []
    for grp in load_config().get("whatsapp_groups", []):
        members = [
            {
                "id": g.id,
                "name": g.name,
                "phone": g.phone,
                "has_phone": bool(normalise_phone(g.phone)),
                "headcount": rsvp_headcount(g),
                "done": (g.id, grp["id"]) in marks,
                "whatsapp_url": group_message_url(g, grp) if grp.get("url") else "",
                "number": "+" + normalise_phone(g.phone) if normalise_phone(g.phone) else "",
            }
            for g in guests
            if in_group(g, grp)
        ]
        out.append(
            {
                "id": grp["id"],
                "name": grp["name"],
                "for": grp.get("for", "all"),
                "url": grp.get("url", ""),
                "members": members,
            }
        )
    return out


@app.post("/api/admin/groups/{group_id}/guests/{gid}", dependencies=[Depends(require_admin)])
def mark_group(group_id: str, gid: int, done: bool = True, db: Session = Depends(get_db)):
    if not db.get(Guest, gid):
        raise HTTPException(404, "Guest not found")
    existing = db.scalar(select(GroupMark).where(GroupMark.guest_id == gid, GroupMark.group_id == group_id))
    if done and not existing:
        db.add(GroupMark(guest_id=gid, group_id=group_id))
    elif not done and existing:
        db.delete(existing)
    db.commit()
    return {"ok": True}


@app.post("/api/admin/guests/import", dependencies=[Depends(require_admin)])
async def import_guests(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """CSV columns: name, phone, email, group, max_party, events, offer_stay  (events: 'all' or ids separated by ; ; offer_stay: yes to show the accommodation question)"""
    text = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "name" not in [c.strip().lower() for c in reader.fieldnames]:
        raise HTTPException(422, "CSV needs a header row with at least a 'name' column")
    created = skipped = 0
    for row in reader:
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        if not row.get("name"):
            skipped += 1
            continue
        raw_events = row.get("events", "").lower()
        evs = event_ids() if raw_events in ("", "all") else _clean_events([e.strip() for e in raw_events.split(";")])
        try:
            party = max(1, min(20, int(row.get("max_party") or 1)))
        except ValueError:
            party = 1
        db.add(
            Guest(
                name=row["name"],
                phone=row.get("phone", ""),
                email=row.get("email", ""),
                group=row.get("group", ""),
                max_party=party,
                events=evs,
                offer_stay=row.get("offer_stay", "").strip().lower() in ("yes", "y", "true", "1"),
            )
        )
        created += 1
    db.commit()
    return {"created": created, "skipped": skipped}


@app.get("/api/admin/guests/export.csv", dependencies=[Depends(require_admin)])
def export_guests(db: Session = Depends(get_db)):
    cfg = load_config()
    guests = db.scalars(select(Guest).order_by(Guest.name)).all()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(
        ["name", "group", "phone", "email", "max_party", "status", "headcount"]
        + [e["name"] for e in cfg["events"]]
        + ["dietary", "message", "wants_to_dance", "dance_with", "songs", "needs_stay", "stay_guests", "stay_notes", "invite_url"]
    )
    for g in guests:
        r = g.rsvp
        per = []
        for e in cfg["events"]:
            if e["id"] not in g.events:
                per.append("-")
            elif not r:
                per.append("pending")
            else:
                a = r.events.get(e["id"], {})
                per.append(str(a.get("headcount", 0)) if a.get("attending") else "no")
        w.writerow(
            [g.name, g.group, g.phone, g.email, g.max_party, rsvp_status(g), rsvp_headcount(g)]
            + per
            + [
                r.dietary if r else "",
                r.message if r else "",
                "yes" if r and r.wants_to_dance else "",
                r.dance_with if r else "",
                " | ".join(f"{s['title']} {s['link']}".strip() for s in (r.songs if r else [])),
                "yes" if r and r.needs_stay else "",
                r.stay_guests if r and r.needs_stay else "",
                r.stay_notes if r else "",
                invite_url(g),
            ]
        )
    return PlainTextResponse(
        out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=guest-list.csv"},
    )


# ---------------------------------------------------------------- admin: sangeet playlist


@app.get("/api/admin/songs", dependencies=[Depends(require_admin)])
def song_requests(db: Session = Depends(get_db)):
    guests = db.scalars(select(Guest).order_by(Guest.name)).all()
    acts = []
    for g in guests:
        r = g.rsvp
        if r and r.wants_to_dance:
            acts.append(
                {
                    "guest_id": g.id,
                    "guest": g.name,
                    "group": g.group,
                    "dance_with": r.dance_with,
                    "notes": r.dance_notes,
                    "songs": r.songs,
                    "phone": g.phone,
                }
            )
    return acts


# ---------------------------------------------------------------- admin: vendors


class VendorIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str = "Other"
    contact_person: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    total_cost: float = Field(default=0, ge=0)
    amount_paid: float = Field(default=0, ge=0)
    status: str = "Shortlisted"
    event_ids: list[str] = Field(default_factory=list)
    notes: str = ""


def vendor_dict(v: Vendor) -> dict:
    return {
        "id": v.id,
        "name": v.name,
        "category": v.category,
        "contact_person": v.contact_person,
        "phone": v.phone,
        "email": v.email,
        "website": v.website,
        "total_cost": v.total_cost,
        "amount_paid": v.amount_paid,
        "status": v.status,
        "event_ids": v.event_ids,
        "notes": v.notes,
    }


@app.get("/api/admin/vendors", dependencies=[Depends(require_admin)])
def list_vendors(db: Session = Depends(get_db)):
    return [vendor_dict(v) for v in db.scalars(select(Vendor).order_by(Vendor.category, Vendor.name))]


@app.post("/api/admin/vendors", dependencies=[Depends(require_admin)])
def create_vendor(body: VendorIn, db: Session = Depends(get_db)):
    v = Vendor(**body.model_dump())
    db.add(v)
    db.commit()
    return vendor_dict(v)


@app.put("/api/admin/vendors/{vid}", dependencies=[Depends(require_admin)])
def update_vendor(vid: int, body: VendorIn, db: Session = Depends(get_db)):
    v = db.get(Vendor, vid)
    if not v:
        raise HTTPException(404, "Vendor not found")
    for k, val in body.model_dump().items():
        setattr(v, k, val)
    db.commit()
    return vendor_dict(v)


@app.delete("/api/admin/vendors/{vid}", dependencies=[Depends(require_admin)])
def delete_vendor(vid: int, db: Session = Depends(get_db)):
    v = db.get(Vendor, vid)
    if not v:
        raise HTTPException(404, "Vendor not found")
    db.delete(v)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- admin: photos


def photo_dict(p: Photo) -> dict:
    return {
        "id": p.id,
        "uploader": p.uploader_name,
        "name": p.original_name,
        "mime_type": p.mime_type,
        "size_bytes": p.size_bytes,
        "drive_status": p.drive_status,
        "drive_link": p.drive_link,
        "error": p.error,
        "local": (UPLOAD_DIR / p.stored_name).exists(),
        "created_at": p.created_at.isoformat(),
    }


@app.get("/api/admin/photos", dependencies=[Depends(require_admin)])
def list_photos(db: Session = Depends(get_db)):
    photos = db.scalars(select(Photo).order_by(Photo.created_at.desc())).all()
    return {
        "photos": [photo_dict(p) for p in photos],
        "drive_configured": drive.drive_configured(),
        "drive_folder": drive.folder_link(),
    }


@app.get("/api/admin/photos/{pid}/file", dependencies=[Depends(require_admin)])
def photo_file(pid: int, db: Session = Depends(get_db)):
    p = db.get(Photo, pid)
    path = UPLOAD_DIR / p.stored_name if p else None
    if not p or not path or not path.exists():
        raise HTTPException(404, "File is no longer stored on the server (check Google Drive)")
    return FileResponse(path, media_type=p.mime_type, filename=p.original_name)


@app.post("/api/admin/photos/sync", dependencies=[Depends(require_admin)])
def resync_photos(background: BackgroundTasks, db: Session = Depends(get_db)):
    pending = db.scalars(select(Photo).where(Photo.drive_status.in_(["pending", "failed", "disabled"]))).all()
    for p in pending:
        background.add_task(sync_photo, p.id)
    return {"queued": len(pending)}


# ---------------------------------------------------------------- serve built frontend (single-process deploy)

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404)
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
