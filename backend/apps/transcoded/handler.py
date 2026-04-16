from __future__ import annotations

from typing import Any


def normalize_push_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "workflow_id": payload.get("workflow_id"),
        "step": payload.get("step"),
        "event_type": payload.get("event_type", "push"),
        "status": payload.get("status", "unknown"),
        "title": payload.get("title", "Transcoded update"),
        "message": payload.get("message", ""),
        "payload": payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
        "parent_event_id": payload.get("parent_event_id"),
    }
