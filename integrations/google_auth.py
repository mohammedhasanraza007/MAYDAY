from __future__ import annotations

import logging
from pathlib import Path


MAYDAY_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = MAYDAY_ROOT / "config"
CREDS_FILE = CONFIG_DIR / "google_credentials.json"
TOKEN_FILE = CONFIG_DIR / "google_token.json"
log = logging.getLogger("mayday.integrations.google_auth")

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

OAUTH_SETUP_INSTRUCTIONS = """
Gmail and Calendar require a one-time Google OAuth setup:

1. Go to https://console.cloud.google.com/
2. Create project -> APIs & Services -> Enable Gmail API + Calendar API
3. Credentials -> Create -> OAuth 2.0 Client IDs -> Desktop app -> Name: MAYDAY
4. Download JSON -> save as E:\\MAYDAY\\config\\google_credentials.json
5. Restart MAYDAY; it will open a browser for one-time authorization.

After setup, MAYDAY reads Gmail and creates calendar events automatically.
""".strip()

OAUTH_ERROR_SHOWN_THIS_SESSION = False


def _show_oauth_setup_once(reason: str) -> None:
    global OAUTH_ERROR_SHOWN_THIS_SESSION
    if OAUTH_ERROR_SHOWN_THIS_SESSION:
        return
    OAUTH_ERROR_SHOWN_THIS_SESSION = True
    log.warning("Google OAuth setup required: %s\n%s", reason, OAUTH_SETUP_INSTRUCTIONS)


def get_google_credentials():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        _show_oauth_setup_once(
            "Google API packages are not installed. Install google-api-python-client, "
            "google-auth-oauthlib, and google-auth-httplib2."
        )
        return None

    if not CREDS_FILE.exists():
        _show_oauth_setup_once(f"Google OAuth credentials not found at {CREDS_FILE}")
        return None

    creds = None
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except Exception as exc:
            _show_oauth_setup_once(f"Google OAuth token could not be read: {exc}")
            return None

    if not creds or not creds.valid:
        try:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
                creds = flow.run_local_server(port=0)
        except Exception as exc:
            _show_oauth_setup_once(f"Google OAuth authorization failed: {exc}")
            return None
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return creds
