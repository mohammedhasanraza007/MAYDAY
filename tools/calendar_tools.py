from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

from tools.base_tool import BaseTool
from integrations.google_auth import OAUTH_SETUP_INSTRUCTIONS
from tools.browser_manager import get_browser_page


logger = logging.getLogger("mayday.tools.calendar")


class CalendarTools(BaseTool):
    @property
    def name(self) -> str:
        return "calendar"

    @property
    def description(self) -> str:
        return "Google Calendar event creation and listing"

    def get_capabilities(self) -> list[str]:
        return ["calendar_create_event", "calendar_create_event_via_browser", "calendar_list_events"]

    def execute(self, parameters: dict) -> dict:
        tool_name = parameters.get("_tool_name", "")
        if tool_name == "calendar_create_event":
            return self._create_event(parameters)
        if tool_name == "calendar_create_event_via_browser":
            return calendar_create_event_via_browser(**parameters)
        if tool_name == "calendar_list_events":
            return self._list_events(parameters)
        return {"status": "error", "error": f"Unknown calendar action: {tool_name}"}

    def _service(self):
        from googleapiclient.discovery import build
        from integrations.google_auth import get_google_credentials

        creds = get_google_credentials()
        if creds is None:
            return None
        return build("calendar", "v3", credentials=creds)

    def _create_event(self, params: dict[str, Any]) -> dict:
        try:
            title = str(params.get("title", "")).strip()
            start_datetime = str(params.get("start_datetime", "")).strip()
            end_datetime = str(params.get("end_datetime", "")).strip()
            timezone_name = str(params.get("timezone", "Asia/Kolkata")).strip() or "Asia/Kolkata"
            attendees = params.get("attendees", [])
            if not title or not start_datetime:
                return {
                    "status": "error",
                    "error": "title and start_datetime are required",
                    "recoverable": True,
                    "next_step": "Retry calendar_create_event with a non-empty title and ISO start_datetime.",
                }
            if not end_datetime:
                normalized = start_datetime.replace("Z", "+00:00")
                try:
                    end_datetime = (datetime.fromisoformat(normalized) + timedelta(hours=1)).isoformat()
                except ValueError:
                    return {
                        "status": "error",
                        "error": "start_datetime must be ISO formatted when end_datetime is omitted",
                        "recoverable": True,
                        "next_step": "Retry with ISO start_datetime, or provide explicit end_datetime.",
                    }

            event_body: dict[str, Any] = {
                "summary": title,
                "description": str(params.get("description", "")),
                "location": str(params.get("location", "")),
                "start": {"dateTime": start_datetime, "timeZone": timezone_name},
                "end": {"dateTime": end_datetime, "timeZone": timezone_name},
            }
            if attendees:
                event_body["attendees"] = [{"email": str(email)} for email in attendees]

            service = self._service()
            if service is None:
                logger.info("OAuth not set up. Falling back to browser Google Calendar.")
                return calendar_create_event_via_browser(
                    title=title,
                    start_datetime=start_datetime,
                    end_datetime=end_datetime,
                    timezone=timezone_name,
                    description=str(params.get("description", "")),
                    location=str(params.get("location", "")),
                )

            result = service.events().insert(
                calendarId="primary",
                body=event_body,
                sendUpdates="all" if attendees else "none",
            ).execute()
            return {
                "status": "success",
                "state": "created",
                "event_id": result.get("id", ""),
                "title": title,
                "start": start_datetime,
                "end": end_datetime,
                "timezone": timezone_name,
                "link": result.get("htmlLink", ""),
                "ready": True,
                "next_step": "Use event_id/link/start/end to confirm the scheduled event; do not recreate the same event.",
            }
        except Exception as exc:
            logger.info("Calendar API error on first attempt. Falling back to browser Calendar: %s", exc)
            return calendar_create_event_via_browser(
                title=str(params.get("title", "")).strip(),
                start_datetime=str(params.get("start_datetime", "")).strip(),
                end_datetime=str(params.get("end_datetime", "")).strip(),
                timezone=str(params.get("timezone", "Asia/Kolkata")).strip() or "Asia/Kolkata",
                description=str(params.get("description", "")),
                location=str(params.get("location", "")),
                oauth_error=str(exc),
            )

    def _list_events(self, params: dict[str, Any]) -> dict:
        try:
            days_ahead = int(params.get("days_ahead", 7))
            max_results = int(params.get("max_results", 10))
            now = datetime.utcnow()
            end = now + timedelta(days=days_ahead)
            service = self._service()
            if service is None:
                return {
                    "status": "success",
                    "source": "browser_fallback",
                    "events": [],
                    "count": 0,
                    "note": "Calendar OAuth is not set up.\n" + OAUTH_SETUP_INSTRUCTIONS,
                    "ready": True,
                    "next_step": "Show setup instructions or ask the user to open Google Calendar in the browser.",
                }
            events_result = service.events().list(
                calendarId="primary",
                timeMin=now.isoformat() + "Z",
                timeMax=end.isoformat() + "Z",
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            events = events_result.get("items", [])
            return {
                "status": "success",
                "count": len(events),
                "ready": True,
                "next_step": "Use the returned events list to answer, or create an event only if the user requested one.",
                "events": [
                    {
                        "title": event.get("summary", "No title"),
                        "start": event.get("start", {}).get("dateTime", event.get("start", {}).get("date", "")),
                        "end": event.get("end", {}).get("dateTime", event.get("end", {}).get("date", "")),
                        "location": event.get("location", ""),
                        "link": event.get("htmlLink", ""),
                    }
                    for event in events
                ],
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc), "recoverable": False}


def _format_calendar_datetime(dt_str: str) -> str:
    """Convert various datetime formats to Google Calendar's YYYYMMDDTHHmmSS format.

    LAW-21: No dashes, no colons — pure compact format.
    """
    import re
    # Strip any timezone suffix for formatting
    cleaned = re.sub(r"[Zz]$", "", dt_str.strip())
    cleaned = re.sub(r"[+-]\d{2}:\d{2}$", "", cleaned)
    # Remove dashes, colons, and spaces
    cleaned = cleaned.replace("-", "").replace(":", "").replace(" ", "T")
    # Ensure we have a T separator
    if "T" not in cleaned and len(cleaned) >= 8:
        cleaned = cleaned[:8] + "T" + cleaned[8:]
    # Pad to at least YYYYMMDDTHHmmSS
    if "T" in cleaned:
        date_part, time_part = cleaned.split("T", 1)
        time_part = (time_part + "000000")[:6]
        cleaned = f"{date_part}T{time_part}"
    return cleaned


def calendar_create_event_via_browser(
    title: str,
    start_datetime: str,
    end_datetime: str = "",
    timezone: str = "Asia/Kolkata",
    description: str = "",
    location: str = "",
    oauth_error: str = "",
    **_kwargs: Any,
) -> dict:
    import time as _time

    text = title.strip()
    details = description.strip()

    # LAW-21: Build dates parameter with compact format (no dashes, no colons)
    start_compact = _format_calendar_datetime(start_datetime) if start_datetime else ""
    end_compact = _format_calendar_datetime(end_datetime) if end_datetime else ""
    if start_compact and not end_compact:
        # Default to 1 hour after start
        try:
            base = datetime.strptime(start_compact, "%Y%m%dT%H%M%S")
            end_compact = (base + timedelta(hours=1)).strftime("%Y%m%dT%H%M%S")
        except ValueError:
            end_compact = start_compact

    params = [f"text={quote(text)}"]
    if details:
        params.append(f"details={quote(details)}")
    if location:
        params.append(f"location={quote(location)}")
    if start_compact and end_compact:
        params.append(f"dates={start_compact}/{end_compact}")
    elif start_compact:
        params.append(f"dates={start_compact}/{start_compact}")

    url = "https://calendar.google.com/calendar/r/eventedit?" + "&".join(params)
    session_id = ""
    page_url = url
    page_title = "Google Calendar"
    browser = "playwright"
    try:
        # Use create_new=True to avoid TargetClosedError on stale singleton frames
        session, page = get_browser_page(create_new=True, return_session=True)
        session_id = session.id
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        _time.sleep(2)
        page_url = page.url
        try:
            page_title = page.title()
        except Exception:
            pass
    except Exception as exc:
        import webbrowser

        logger.info("Playwright Calendar fallback failed; opening system browser: %s", exc)
        webbrowser.open(url)
        browser = "system_default"
        oauth_error = oauth_error or str(exc)
    result = {
        "status": "success",
        "source": "browser_fallback",
        "state": "browser_opened",
        "browser": browser,
        "session_id": session_id,
        "url": page_url,
        "title": title,
        "page_title": page_title,
        "start_datetime": start_datetime,
        "end_datetime": end_datetime,
        "timezone": timezone,
        "note": (
            "Calendar event form opened with available details. User must click Save to confirm. "
            "Set up OAuth for automatic creation.\n" + OAUTH_SETUP_INSTRUCTIONS
        ),
        "oauth_error": oauth_error,
        "ready": True,
        "next_step": "Tell the user Google Calendar is open and they must click Save.",
    }
    logger.info(
        "TOOL-RESULT: tool=calendar_create_event_via_browser status=success result=%s",
        json.dumps(result, sort_keys=True, default=str)[:800],
    )
    return result
