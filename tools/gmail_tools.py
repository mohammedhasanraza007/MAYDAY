from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any
from urllib.parse import quote

from tools.base_tool import BaseTool
from integrations.google_auth import OAUTH_SETUP_INSTRUCTIONS
from tools.browser_manager import get_browser_page


logger = logging.getLogger("mayday.tools.gmail")


class GmailTools(BaseTool):
    @property
    def name(self) -> str:
        return "gmail"

    @property
    def description(self) -> str:
        return "Gmail unread email lookup and message body reading"

    def get_capabilities(self) -> list[str]:
        return ["gmail_get_unread", "gmail_get_email_body"]

    def execute(self, parameters: dict) -> dict:
        tool_name = parameters.get("_tool_name", "")
        if tool_name == "gmail_get_unread":
            return self._get_unread(parameters)
        if tool_name == "gmail_get_email_body":
            return self._get_email_body(parameters)
        return {"status": "error", "error": f"Unknown Gmail action: {tool_name}"}

    def _service(self):
        from googleapiclient.discovery import build
        from integrations.google_auth import get_google_credentials

        creds = get_google_credentials()
        if creds is None:
            return None
        return build("gmail", "v1", credentials=creds)

    def _get_unread(self, params: dict[str, Any]) -> dict:
        try:
            query = "is:unread"
            sender_filter = str(params.get("sender_filter", "")).strip()
            subject_filter = str(params.get("subject_filter", "")).strip()
            if sender_filter:
                query += f" from:{sender_filter}"
            if subject_filter:
                query += f" subject:{subject_filter}"

            service = self._service()
            if service is None:
                logger.info("OAuth not set up. Falling back to browser Gmail.")
                return gmail_get_unread_via_browser(
                    int(params.get("max_results", 10)),
                    sender_filter,
                )
            result = service.users().messages().list(
                userId="me",
                q=query,
                maxResults=int(params.get("max_results", 10)),
            ).execute()
            messages = result.get("messages", [])
            emails = []
            for message in messages:
                detail = service.users().messages().get(
                    userId="me",
                    id=message["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                ).execute()
                headers = {
                    header["name"]: header["value"]
                    for header in detail.get("payload", {}).get("headers", [])
                    if isinstance(header, dict)
                }
                emails.append(
                    {
                        "id": message["id"],
                        "from": headers.get("From", "Unknown"),
                        "subject": headers.get("Subject", "No subject"),
                        "date": headers.get("Date", ""),
                        "preview": detail.get("snippet", ""),
                    }
                )
            return {
                "status": "success",
                "query": query,
                "count": len(emails),
                "has_unread": bool(emails),
                "emails": emails,
                "ready": True,
                "next_step": (
                    "Use one returned email id with gmail_get_email_body if body text is needed; "
                    "otherwise answer from the unread email metadata."
                ),
            }
        except Exception as exc:
            logger.info("Gmail API error on first attempt. Falling back to browser Gmail: %s", exc)
            return gmail_get_unread_via_browser(
                int(params.get("max_results", 10)),
                str(params.get("sender_filter", "")).strip(),
                oauth_error=str(exc),
            )

    def _get_email_body(self, params: dict[str, Any]) -> dict:
        try:
            service = self._service()
            if service is None:
                return gmail_get_unread_via_browser(
                    10,
                    "",
                    oauth_error="OAuth credentials unavailable for gmail_get_email_body",
                )
            detail = service.users().messages().get(
                userId="me",
                id=str(params.get("email_id", "")),
                format="full",
            ).execute()
            body = self._extract_text(detail.get("payload", {})) or detail.get("snippet", "")
            return {
                "status": "success",
                "email_id": str(params.get("email_id", "")),
                "body": body[:3000],
                "truncated": len(body) > 3000,
                "total_chars": len(body),
                "ready": True,
                "next_step": "Use this body text to answer; do not request the same email body again.",
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc), "recoverable": False}

    def _extract_text(self, payload: dict[str, Any]) -> str:
        mime_type = payload.get("mimeType")
        data = payload.get("body", {}).get("data", "")
        if mime_type == "text/plain" and data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        for part in payload.get("parts", []) or []:
            if isinstance(part, dict):
                text = self._extract_text(part)
                if text:
                    return text
        return ""


def gmail_get_unread_via_browser(
    max_results: int = 10,
    sender_filter: str = "",
    oauth_error: str = "",
) -> dict:
    url = (
        "https://mail.google.com/mail/u/0/#search/from:" + quote(sender_filter)
        if sender_filter
        else "https://mail.google.com/mail/u/0/#inbox"
    )
    session_id = ""
    title = "Gmail"
    page_url = url
    content = "Gmail opened in browser fallback. Sign in if prompted, then review the inbox."
    browser = "playwright"
    emails_parsed: list[dict] = []
    try:
        session, page = get_browser_page(create_new=False, return_session=True)
        session_id = session.id
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)
        page_url = page.url
        title = page.title()
        try:
            content = page.inner_text("body", timeout=5000)
        except Exception as exc:
            content = f"Gmail opened in browser, but visible text could not be read yet: {exc}"

        # Parse real email data from visible page text
        if content and len(content) > 50:
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            # Gmail inbox lines typically contain sender, subject, snippet, and date info
            # Extract consecutive line groups that look like email entries
            i = 0
            while i < len(lines) and len(emails_parsed) < max_results:
                line = lines[i]
                # Skip navigation/menu lines
                if len(line) < 3 or line.lower() in ("inbox", "starred", "snoozed", "sent", "drafts", "more", "compose"):
                    i += 1
                    continue
                # Heuristic: email rows often have sender name, then subject, then snippet
                # Look for lines that contain " - " separator (Gmail subject - snippet pattern)
                if " - " in line and i > 0:
                    parts = line.split(" - ", 1)
                    emails_parsed.append({
                        "from": lines[i - 1] if i > 0 else "Unknown",
                        "subject": parts[0].strip()[:120],
                        "preview": parts[1].strip()[:200] if len(parts) > 1 else "",
                    })
                i += 1

    except Exception as exc:
        import webbrowser

        logger.info("Playwright Gmail fallback failed; opening system browser: %s", exc)
        webbrowser.open(url)
        browser = "system_default"
        oauth_error = oauth_error or str(exc)
    result = {
        "status": "success",
        "source": "browser_fallback",
        "browser": browser,
        "session_id": session_id,
        "url": page_url,
        "title": title,
        "content": content[:4000],
        "max_results": max_results,
        "note": "Retrieved via browser fallback. Set up OAuth for API access.\n" + OAUTH_SETUP_INSTRUCTIONS,
        "oauth_error": oauth_error,
        "ready": True,
        "next_step": "Tell the user Gmail opened in the browser and show the OAuth setup instructions.",
    }
    logger.info(
        "TOOL-RESULT: tool=gmail_get_unread_via_browser status=success result=%s",
        json.dumps(result, sort_keys=True, default=str)[:800],
    )
    return result
