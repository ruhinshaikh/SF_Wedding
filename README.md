# Wedding invitation app

React (Vite) frontend + FastAPI backend + SQLite. One guest link per household, RSVP per event, Sangeet dance
requests with song links, and an admin dashboard for the guest list,
WhatsApp sending, vendors and the Sangeet playlist.

## 1. Run it locally

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # set ADMIN_PASSWORD and SECRET_KEY
uvicorn main:app --reload --port 8000

# frontend (second terminal)
cd frontend
npm install
npm run dev                  # http://localhost:5173
```

- Admin dashboard: http://localhost:5173/admin
- Guest invitations live at `/i/<token>`. Add a guest in the dashboard to get their link.

## 2. Make it yours

Edit `backend/config.json`: couple names, welcome note, RSVP deadline, and the events (dates, venues, addresses,
map links, dress code). Mark exactly the Sangeet with `"is_sangeet": true`: that event triggers the dance
question and song links. Restart the backend after editing.

Set `PUBLIC_URL` in `backend/.env` to the real site address before sending invitations, because the WhatsApp
message includes that link. `DEFAULT_COUNTRY_CODE` (default 91) is added to 10-digit phone numbers.

## 3. Sending invitations

Guests tab > **WhatsApp** opens WhatsApp with a ready message and that guest's personal link, then marks them
as sent. WhatsApp links can't be sent automatically, so you press send in WhatsApp for each guest.

Bulk add: **Import CSV** with columns `name, phone, email, group, max_party, events`
(`events` is `all` or ids joined with `;`, e.g. `sangeet;wedding`). **Export CSV** gives you the full
guest list with replies, food choices per event and songs.


## 5. Deploy

```bash
cd frontend && npm run build        # creates frontend/dist
cd ../backend && uvicorn main:app --host 0.0.0.0 --port 8000
```

The backend serves `frontend/dist` itself, so one process serves everything. Any small host with a persistent
disk works (Render, Railway, Fly.io, a VPS). Put it behind HTTPS and keep `backend/data/` on persistent storage:
it holds the SQLite database. Back it up before the wedding.

## Security notes

- Invitation links are unguessable but are the only protection for a guest's reply. Don't post them publicly.
- Admin access is a single shared password (`ADMIN_PASSWORD`). Use a long one, and keep `.env` out of git.


## Database: SQLite or Supabase (Postgres)

By default the app keeps everything in a SQLite file (`backend/data/wedding.db`). To use Supabase (or any Postgres) instead, set
`DATABASE_URL` to its connection string. On Supabase use the **Session pooler** string (Project > Connect), with your password filled in.
The tables are created automatically on first start.

## Hosting checklist

- Health check path: `/api/health` (the other API routes need a login).
- On a real server the app refuses to start unless `SECRET_KEY` is set to a long random value and `ADMIN_PASSWORD` has at least 8 characters.
- Set `PUBLIC_URL` to the site's address so invitation and WhatsApp links point to it.
