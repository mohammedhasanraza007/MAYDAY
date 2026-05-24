from __future__ import annotations

from pathlib import Path


MAYDAY_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = MAYDAY_ROOT / "config"
CREDS_FILE = CONFIG_DIR / "google_credentials.json"
TOKEN_FILE = CONFIG_DIR / "google_token.json"

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


def get_google_credentials():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise RuntimeError(
            "Google API packages are not installed. Install google-api-python-client, "
            "google-auth-oauthlib, and google-auth-httplib2."
        ) from exc

    if not CREDS_FILE.exists():
        raise FileNotFoundError(
            f"Google OAuth credentials not found at {CREDS_FILE}. "
            "Create a Google Cloud desktop OAuth client with Calendar and Gmail APIs enabled, "
            "then save it as config/google_credentials.json."
        )

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return creds
