"""Google Drive upload using a stored OAuth refresh token (uploads land in your own Drive).

Uses the narrow `drive.file` scope, so the app can only see files/folders it created itself.
That means it creates its own "Wedding Photos" folder on first upload (cached in data/drive_folder.txt).
Open that folder in Drive afterwards and share it with family or move it wherever you like.
"""
from __future__ import annotations

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
FOLDER_CACHE = Path(__file__).parent / "data" / "drive_folder.txt"


def drive_configured() -> bool:
    return all(
        os.getenv(k) for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN")
    )


def _service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _folder_id(service) -> str:
    if FOLDER_CACHE.exists():
        return FOLDER_CACHE.read_text().strip()
    name = os.getenv("GOOGLE_DRIVE_FOLDER_NAME", "Wedding Photos")
    folder = (
        service.files()
        .create(
            body={"name": name, "mimeType": "application/vnd.google-apps.folder"},
            fields="id",
        )
        .execute()
    )
    FOLDER_CACHE.write_text(folder["id"])
    return folder["id"]


def folder_link() -> str:
    if FOLDER_CACHE.exists():
        return f"https://drive.google.com/drive/folders/{FOLDER_CACHE.read_text().strip()}"
    return ""


def upload_file(path: str, name: str, mime_type: str) -> tuple[str, str]:
    """Upload a local file to the wedding folder. Returns (file_id, web_view_link)."""
    service = _service()
    media = MediaFileUpload(path, mimetype=mime_type or "application/octet-stream", resumable=True)
    meta = {"name": name, "parents": [_folder_id(service)]}
    created = service.files().create(body=meta, media_body=media, fields="id, webViewLink").execute()
    return created["id"], created.get("webViewLink", "")
