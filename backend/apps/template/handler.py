from __future__ import annotations

from typing import Any


def normalize_push_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize incoming POST payload for the template app.
    """
    return {
        "app_id": payload.get("app_id", "template"),
        "state": payload.get("state", "unknown"),
        "summary": payload.get("summary", ""),
        "tasks": payload.get("tasks", []),
    }


def fetch_on_demand_status() -> dict[str, Any]:
    """
    Return on-demand status shape for query mode.
    Template implementation returns a placeholder.
    """
    return {
        "app_id": "template",
        "state": "unknown",
        "summary": "On-demand status not implemented.",
        "tasks": [],
    }
