"""One-off helper: run locally to get the Google credentials for backend/.env.

Usage:
  1. In Google Cloud Console: create a project, enable the Google Drive API, configure the OAuth consent
     screen (External, add your own Google account as a test user), then create an OAuth client of type
     "Desktop app". Download it as client_secret.json into this folder.
  2. python get_refresh_token.py
  3. Sign in with the Google account whose Drive should receive the photos, and copy the printed values into .env.

The app uses the narrow drive.file scope: it creates its own "Wedding Photos" folder on the first upload
and can only touch files it created.
"""
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

print("\nAdd these to backend/.env:\n")
print(f"GOOGLE_CLIENT_ID={creds.client_id}")
print(f"GOOGLE_CLIENT_SECRET={creds.client_secret}")
print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
