# Wedding invitation app

React (Vite) frontend + FastAPI backend + SQLite. One guest link per household, RSVP per event, Sangeet dance
requests with song links, guest photo uploads into your Google Drive, and an admin dashboard for the guest list,
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
guest list with replies, food preferences and songs.

## 4. Connect Google Drive (photo uploads)

1. Google Cloud Console: create a project, enable the **Google Drive API**.
2. OAuth consent screen: type External, add your own Google account under **Test users**.
3. Credentials: create an **OAuth client ID** of type **Desktop app**, download it as
   `backend/client_secret.json`.
4. `cd backend && python get_refresh_token.py`, sign in, and paste the three printed values into `.env`.
5. Restart the backend. The first upload creates a **Wedding Photos** folder in your Drive; the Photos tab links to it.

Notes:
- Until Drive is connected, uploads stay on the server and show "Waiting for Drive setup". Press
  **Retry Drive upload** after connecting.
- The app uses the narrow `drive.file` scope, so it can only see the folder and files it created.
- While the Google app is in "Testing" mode, refresh tokens expire after 7 days. Before the wedding, publish the
  consent screen to production (fine for personal use; you'll see an "unverified app" warning once) and
  regenerate the token.

## 5. Deploy

```bash
cd frontend && npm run build        # creates frontend/dist
cd ../backend && uvicorn main:app --host 0.0.0.0 --port 8000
```

The backend serves `frontend/dist` itself, so one process serves everything. Any small host with a persistent
disk works (Render, Railway, Fly.io, a VPS). Put it behind HTTPS and keep `backend/data/` on persistent storage:
it holds the SQLite database and any photos not yet copied to Drive. Back it up before the wedding.

## Security notes

- Invitation links are unguessable but are the only protection for a guest's reply. Don't post them publicly.
- Admin access is a single shared password (`ADMIN_PASSWORD`). Use a long one, and keep `.env` out of git.
- Photo uploads accept images and videos only, up to `MAX_UPLOAD_MB` each.
