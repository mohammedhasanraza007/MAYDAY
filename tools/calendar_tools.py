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
    text = f"{title} at {start_datetime}".strip()
    details = description.strip()
    params = [f"text={quote(text)}"]
    if details:
        params.append(f"details={quote(details)}")
    if location:
        params.append(f"location={quote(location)}")
    if start_datetime:
        params.append(f"dates={quote(start_datetime)}")
    url = "https://calendar.google.com/calendar/r/eventedit?" + "&".join(params)
    session_id = ""
    page_url = url
    browser = "playwright"
    try:
        session, page = get_browser_page(create_new=False, return_session=True)
        session_id = session.id
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page_url = page.url
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
