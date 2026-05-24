from __future__ import annotations

import base64
from typing import Any

from tools.base_tool import BaseTool


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

        return build("gmail", "v1", credentials=get_google_credentials())

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
            return {"status": "error", "error": str(exc), "recoverable": False}

    def _get_email_body(self, params: dict[str, Any]) -> dict:
        try:
            detail = self._service().users().messages().get(
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
