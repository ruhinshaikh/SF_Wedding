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
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from db import DanceGroup, Guest, GroupMark, Rsvp, SessionLocal, Vendor, init_db

CONFIG_PATH = Path(__file__).parent / "config.json"
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
DEFAULT_COUNTRY_CODE = os.getenv("DEFAULT_COUNTRY_CODE", "91")
SESSION_SECONDS = 60 * 60 * 24 * 14

app = FastAPI(title="Wedding Invitation API")
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    _check_production_settings()
    init_db()


@app.get("/api/health")
def health():
    """For the host's health check (no login needed)."""
    return {"ok": True}


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


def _check_production_settings() -> None:
    """On a real server, refuse to start with the built-in secret: anyone could forge an admin login with it."""
    public = os.getenv("PUBLIC_URL", "")
    is_local = not public or "localhost" in public or "127.0.0.1" in public
    if not is_local and os.getenv("SECRET_KEY", "dev-secret-change-me") in ("", "dev-secret-change-me", "change-me-too"):
        raise RuntimeError("Set SECRET_KEY to a long random value (python -c \"import secrets;print(secrets.token_hex(32))\").")
    if not is_local and len(os.getenv("ADMIN_PASSWORD", "")) < 8:
        raise RuntimeError("Set ADMIN_PASSWORD to at least 8 characters.")


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


# ---------------------------------------------------------------- guest login (phone number)
# A guest proves who they are with the phone number on the guest list. The session token records the last
# 10 digits of that number; an invitation link only opens for the number that belongs to it.


def phone10(raw: str) -> str:
    digits = "".join(c for c in raw if c.isdigit())
    return digits[-10:] if len(digits) >= 10 else ""


def make_guest_token(p10: str) -> str:
    payload = f"g{p10}:{int(time.time()) + SESSION_SECONDS}"
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}.{sig}".encode()).decode()


def guest_session_phone(token: str) -> Optional[str]:
    """The phone (last 10 digits) a valid guest token was issued for, else None."""
    try:
        payload, sig = base64.urlsafe_b64decode(token.encode()).decode().rsplit(".", 1)
        good = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
        who, expiry = payload.split(":", 1)
        if hmac.compare_digest(sig, good) and who.startswith("g") and int(expiry) > time.time():
            return who[1:]
    except Exception:
        pass
    return None


def bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    return auth[7:] if auth.lower().startswith("bearer ") else ""


def require_login(request: Request) -> Optional[str]:
    """Any logged-in guest or the admin may continue. Returns the guest's phone, or None for the admin."""
    token = bearer(request)
    if token and valid_admin_token(token):
        return None
    p = guest_session_phone(token) if token else None
    if not p:
        raise HTTPException(401, "Please log in with your mobile number")
    return p


def require_invite_access(request: Request, guest: Guest) -> None:
    """The guest's own number (or the admin) may open an invitation. Guests with no number on file can't be checked."""
    p = require_login(request)
    mine = phone10(guest.phone)
    if p is not None and mine and p != mine:
        raise HTTPException(403, "This invitation belongs to a different mobile number. Log in with the number it was sent to.")


_login_misses: dict[str, list[float]] = {}


class GuestLoginIn(BaseModel):
    phone: str = Field(max_length=40)


@app.post("/api/login")
def guest_login(body: GuestLoginIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    now_s = time.time()
    misses = [t for t in _login_misses.get(ip, []) if now_s - t < 600]
    if len(misses) >= 8:
        raise HTTPException(429, "Too many tries. Please wait a few minutes and try again.")
    p = phone10(body.phone)
    matches = [g for g in db.scalars(select(Guest).order_by(Guest.name)).all() if p and phone10(g.phone) == p]
    if not matches:
        misses.append(now_s)
        _login_misses[ip] = misses
        raise HTTPException(404, "We couldn't find that number on the guest list. Use the number your invitation was sent to.")
    _login_misses.pop(ip, None)
    return {
        "token": make_guest_token(p),
        "name": matches[0].name,
        "invites": [{"name": g.name, "token": g.token} for g in matches],
    }


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
        "dance_type": r.dance_type,
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


PUBLIC_EVENT_FIELDS = ("id", "name", "date", "time", "venue", "address", "map_url", "dress_code", "film")


@app.get("/api/public/invite")
def public_invite():
    """No login: what the open invitation pages (/nikkah and the /invite carousel) show."""
    cfg = load_config()
    return {
        "couple": cfg["couple"],
        "events": [{k: e.get(k, "") for k in PUBLIC_EVENT_FIELDS} for e in cfg["events"]],
    }


@app.get("/api/config")
def get_config(request: Request):
    require_login(request)
    return public_config(load_config())


def guest_by_token(db: Session, token: str, request: Optional[Request] = None) -> Guest:
    g = db.scalar(select(Guest).where(Guest.token == token))
    if not g:
        raise HTTPException(404, "Invitation not found")
    if request is not None:
        require_invite_access(request, g)
    return g


ACTIVE_WINDOW = 5 * 60  # seconds: "active now" means seen in the last five minutes


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else ""))[:64]


def seen_ago(g: Guest) -> float | None:
    if not g.last_seen:
        return None
    ts = g.last_seen if g.last_seen.tzinfo else g.last_seen.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds()


def mark_seen(g: Guest, request: Request, db: Session, new_visit: bool) -> None:
    g.last_seen = datetime.now(timezone.utc)
    g.last_ip = client_ip(request)
    if new_visit:
        g.visits = (g.visits or 0) + 1
    db.commit()


@app.post("/api/invite/{token}/ping")
def invite_ping(token: str, request: Request, db: Session = Depends(get_db)):
    g = guest_by_token(db, token, request)
    if not valid_admin_token(bearer(request)):
        mark_seen(g, request, db, new_visit=False)
    return {"ok": True}


@app.get("/api/admin/active", dependencies=[Depends(require_admin)])
def active_guests(db: Session = Depends(get_db)):
    rows = []
    for g in db.scalars(select(Guest).where(Guest.last_seen.is_not(None))).all():
        ago = seen_ago(g)
        rows.append({"id": g.id, "name": g.name, "group": g.group, "ip": g.last_ip, "visits": g.visits,
                     "seconds_ago": ago, "active": ago is not None and ago <= ACTIVE_WINDOW, "replied": g.rsvp is not None})
    rows.sort(key=lambda r: r["seconds_ago"])
    return {"active": [r for r in rows if r["active"]], "recent": rows[:15]}


@app.get("/api/invite/{token}")
def get_invite(token: str, request: Request, db: Session = Depends(get_db)):
    g = guest_by_token(db, token, request)
    if not valid_admin_token(bearer(request)):  # the admin looking at an invitation isn't a guest visit
        mark_seen(g, request, db, new_visit=True)
    cfg = load_config()
    return {
        "guest": {"name": g.name, "max_party": g.max_party, "events": g.events, "offer_stay": g.offer_stay},
        "config": {**public_config(cfg), "events": [e for e in cfg["events"] if e["id"] in g.events]},
        "rsvp": rsvp_dict(g.rsvp),
    }


@app.get("/api/invite/{token}/groups")
def invite_groups(token: str, request: Request, db: Session = Depends(get_db)):
    """WhatsApp groups this guest can join. Only returned once they have said yes."""
    g = guest_by_token(db, token, request)
    return {
        "groups": [
            {"id": grp["id"], "name": grp["name"], "url": grp["url"]}
            for grp in load_config().get("whatsapp_groups", [])
            if grp.get("url") and in_group(g, grp)
        ]
    }


@app.get("/api/invite/{token}/songs-taken")
def songs_taken(token: str, request: Request, db: Session = Depends(get_db)):
    """Songs other guests picked for their Sangeet dance (titles and links only, no names)."""
    me = guest_by_token(db, token, request)
    seen, out = set(), []
    for g in db.scalars(select(Guest)).all():
        if g.id == me.id or not (g.rsvp and g.rsvp.wants_to_dance):
            continue
        for s in g.rsvp.songs or []:
            key = (s.get("title", "").strip().lower(), s.get("link", "").strip().lower())
            if key not in seen:
                seen.add(key)
                out.append({"title": s.get("title", ""), "link": s.get("link", "")})
    return {"songs": out}


class EventAnswer(BaseModel):
    attending: bool
    headcount: int = Field(default=1, ge=0, le=20)
    food: dict[str, int] = Field(default_factory=dict)


class SongIn(BaseModel):
    title: str = Field(default="", max_length=200)
    link: str = Field(default="", max_length=500)


class RsvpIn(BaseModel):
    events: dict[str, EventAnswer]
    dietary: str = Field(default="", max_length=1000)
    message: str = Field(default="", max_length=2000)
    wants_to_dance: bool = False
    dance_type: str = Field(default="", max_length=10)
    dance_with: str = Field(default="", max_length=300)
    dance_notes: str = Field(default="", max_length=1000)
    songs: list[SongIn] = Field(default_factory=list, max_length=5)
    needs_stay: bool = False
    stay_guests: int = Field(default=0, ge=0, le=20)
    stay_notes: str = Field(default="", max_length=1000)


@app.post("/api/invite/{token}/rsvp")
def submit_rsvp(token: str, body: RsvpIn, request: Request, db: Session = Depends(get_db)):
    g = guest_by_token(db, token, request)
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
        opts = set(cfg.get("food_options", []))
        food = {k: v for k, v in a.food.items() if k in opts and v > 0} if a.attending else {}
        if sum(food.values()) > a.headcount:
            raise HTTPException(422, "Food choices can't add up to more than the number of guests")
        answers[eid] = {"attending": a.attending, "headcount": a.headcount if a.attending else 0, "food": food}

    attending_sangeet = any(answers.get(s, {}).get("attending") for s in sangeet_ids)
    wants = body.wants_to_dance and attending_sangeet
    songs: list[dict] = []
    if wants:
        if body.dance_type not in ("", "solo", "couple", "group"):
            raise HTTPException(422, "Dance type must be solo, couple or group")
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
    r.dance_type = body.dance_type if wants else ""
    r.dance_with = body.dance_with.strip() if wants and body.dance_type != "solo" else ""
    r.dance_notes = body.dance_notes.strip() if wants else ""
    r.songs = songs
    from db import now

    r.responded_at = now()
    db.add(r)
    db.commit()
    return {"ok": True, "rsvp": rsvp_dict(r)}


# ---------------------------------------------------------------- admin: summary


@app.get("/api/admin/summary", dependencies=[Depends(require_admin)])
def summary(db: Session = Depends(get_db)):
    cfg = load_config()
    guests = db.scalars(select(Guest)).all()
    vendors = db.scalars(select(Vendor)).all()

    food_options = cfg.get("food_options", [])
    per_event = []
    for e in cfg["events"]:
        invited = [g for g in guests if e["id"] in g.events]
        attending = [g for g in invited if g.rsvp and g.rsvp.events.get(e["id"], {}).get("attending")]
        declined = [g for g in invited if g.rsvp and not g.rsvp.events.get(e["id"], {}).get("attending")]
        # a guest's food picks apply to every event they attend, never more than that event's headcount
        food_totals = {o: 0 for o in food_options}
        food_unspecified = 0
        for g in attending:
            left = g.rsvp.events[e["id"]]["headcount"]
            for o in food_options:
                n = min(g.rsvp.events[e["id"]].get("food", {}).get(o, 0), left)
                food_totals[o] += n
                left -= n
            food_unspecified += left
        per_event.append(
            {
                "id": e["id"],
                "name": e["name"],
                "invited_households": len(invited),
                "invited_seats": sum(g.max_party for g in invited),
                "attending_guests": sum(g.rsvp.events[e["id"]]["headcount"] for g in attending),
                "declined_households": len(declined),
                "pending_households": len(invited) - len(attending) - len(declined),
                "food": food_totals,
                "food_unspecified": food_unspecified,
            }
        )

    dancers = [g for g in guests if g.rsvp and g.rsvp.wants_to_dance]
    return {
        "households": len(guests),
        "seats": sum(g.max_party for g in guests),
        "responded": sum(1 for g in guests if g.rsvp),
        "invites_sent": sum(1 for g in guests if g.invite_sent),
        "per_event": per_event,
        "food_options": food_options,
        "dance_acts": len(dancers),
        "dance_groups": db.query(DanceGroup).count(),
        "stay_households": sum(1 for g in guests if g.rsvp and g.rsvp.needs_stay),
        "stay_guests": sum(g.rsvp.stay_guests for g in guests if g.rsvp and g.rsvp.needs_stay),
        "songs": sum(len(g.rsvp.songs) for g in dancers),
        "vendors": len(vendors),
        "vendor_total": sum(v.total_cost for v in vendors),
        "vendor_paid": sum(v.amount_paid for v in vendors),
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
    dance_group_names = {d.id: d.name for d in db.scalars(select(DanceGroup)).all()}
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(
        ["name", "group", "phone", "email", "max_party", "status", "headcount"]
        + [e["name"] for e in cfg["events"]]
        + ["allergies / other", "message", "wants_to_dance", "dance_type", "dance_group", "dance_with", "songs", "needs_stay", "stay_guests", "stay_notes", "invite_url"]
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
                if a.get("attending"):
                    f = ", ".join(f"{k} {n}" for k, n in a.get("food", {}).items())
                    per.append(f"{a.get('headcount', 0)} ({f})" if f else str(a.get("headcount", 0)))
                else:
                    per.append("no")
        w.writerow(
            [g.name, g.group, g.phone, g.email, g.max_party, rsvp_status(g), rsvp_headcount(g)]
            + per
            + [
                                r.dietary if r else "",
                r.message if r else "",
                "yes" if r and r.wants_to_dance else "",
                r.dance_type if r else "",
                dance_group_names.get(g.dance_group_id, ""),
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
                    "dance_type": r.dance_type,
                    "dance_with": r.dance_with,
                    "notes": r.dance_notes,
                    "songs": r.songs,
                    "phone": g.phone,
                    "dance_group_id": g.dance_group_id,
                }
            )
    return acts


class DanceGroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    notes: str = Field(default="", max_length=1000)


class DanceGroupAssign(BaseModel):
    group_id: Optional[int] = None


@app.get("/api/admin/dance-groups", dependencies=[Depends(require_admin)])
def list_dance_groups(db: Session = Depends(get_db)):
    groups = db.scalars(select(DanceGroup).order_by(DanceGroup.name)).all()
    guests = db.scalars(select(Guest).order_by(Guest.name)).all()
    sangeet_ids = {e["id"] for e in load_config()["events"] if e.get("is_sangeet")}
    out = []
    for grp in groups:
        members = [
            {
                "guest_id": g.id,
                "name": g.name,
                "wants_to_dance": bool(g.rsvp and g.rsvp.wants_to_dance),
                "dance_type": g.rsvp.dance_type if g.rsvp else "",
                "songs": len(g.rsvp.songs) if g.rsvp else 0,
            }
            for g in guests
            if g.dance_group_id == grp.id
        ]
        out.append({"id": grp.id, "name": grp.name, "notes": grp.notes, "members": members})
    # guests who could be added: invited to a Sangeet and not already in a group
    available = [
        {"guest_id": g.id, "name": g.name, "wants_to_dance": bool(g.rsvp and g.rsvp.wants_to_dance)}
        for g in guests
        if g.dance_group_id is None and sangeet_ids & set(g.events)
    ]
    return {"groups": out, "available": available}


@app.post("/api/admin/dance-groups", dependencies=[Depends(require_admin)])
def create_dance_group(body: DanceGroupIn, db: Session = Depends(get_db)):
    grp = DanceGroup(name=body.name.strip(), notes=body.notes.strip())
    db.add(grp)
    db.commit()
    return {"id": grp.id}


@app.put("/api/admin/dance-groups/{gid}", dependencies=[Depends(require_admin)])
def update_dance_group(gid: int, body: DanceGroupIn, db: Session = Depends(get_db)):
    grp = db.get(DanceGroup, gid)
    if not grp:
        raise HTTPException(404, "Dance group not found")
    grp.name, grp.notes = body.name.strip(), body.notes.strip()
    db.commit()
    return {"ok": True}


@app.delete("/api/admin/dance-groups/{gid}", dependencies=[Depends(require_admin)])
def delete_dance_group(gid: int, db: Session = Depends(get_db)):
    grp = db.get(DanceGroup, gid)
    if not grp:
        raise HTTPException(404, "Dance group not found")
    db.execute(update(Guest).where(Guest.dance_group_id == gid).values(dance_group_id=None))
    db.delete(grp)
    db.commit()
    return {"ok": True}


@app.post("/api/admin/guests/{guest_id}/dance-group", dependencies=[Depends(require_admin)])
def assign_dance_group(guest_id: int, body: DanceGroupAssign, db: Session = Depends(get_db)):
    g = db.get(Guest, guest_id)
    if not g:
        raise HTTPException(404, "Guest not found")
    if body.group_id is not None and not db.get(DanceGroup, body.group_id):
        raise HTTPException(404, "Dance group not found")
    g.dance_group_id = body.group_id
    db.commit()
    return {"ok": True}


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


# ---------------------------------------------------------------- serve built frontend (single-process deploy)

class CachedStatic(StaticFiles):
    """Vite gives built files content-hashed names, so browsers may keep them for a year."""

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        if resp.status_code == 200:
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp


if FRONTEND_DIST.exists():
    DIST_ROOT = FRONTEND_DIST.resolve()
    app.mount("/assets", CachedStatic(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404)
        # resolve and make sure the file is inside the built site, so "../" can't reach other files on the server
        candidate = (DIST_ROOT / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(DIST_ROOT):
            # images, films and music change rarely: cache for a day; the page itself is never cached
            return FileResponse(candidate, headers={"Cache-Control": "public, max-age=86400"})
        return FileResponse(DIST_ROOT / "index.html", headers={"Cache-Control": "no-cache"})
