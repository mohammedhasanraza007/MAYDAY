from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from tools.base_tool import BaseTool


class CalendarTools(BaseTool):
    @property
    def name(self) -> str:
        return "calendar"

    @property
    def description(self) -> str:
        return "Google Calendar event creation and listing"

    def get_capabilities(self) -> list[str]:
        return ["calendar_create_event", "calendar_list_events"]

    def execute(self, parameters: dict) -> dict:
        tool_name = parameters.get("_tool_name", "")
        if tool_name == "calendar_create_event":
            return self._create_event(parameters)
        if tool_name == "calendar_list_events":
            return self._list_events(parameters)
        return {"status": "error", "error": f"Unknown calendar action: {tool_name}"}

    def _service(self):
        from googleapiclient.discovery import build
        from integrations.google_auth import get_google_credentials

        return build("calendar", "v3", credentials=get_google_credentials())

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

            result = self._service().events().insert(
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
            return {"status": "error", "error": str(exc), "recoverable": False}

    def _list_events(self, params: dict[str, Any]) -> dict:
        try:
            days_ahead = int(params.get("days_ahead", 7))
            max_results = int(params.get("max_results", 10))
            now = datetime.utcnow()
            end = now + timedelta(days=days_ahead)
            events_result = self._service().events().list(
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
