from __future__ import annotations

import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


JELLYFIN_BASE_URL = "https://jellyfin.home.marlosbosso.net"
JELLYFIN_API_KEY_ENV = "JELLYFIN_KEY"
JELLYFIN_ACTIVITY_URL = (
    f"{JELLYFIN_BASE_URL}/System/ActivityLog/Entries?startIndex=0&limit=25&hasUserId=true"
)
JELLYFIN_CLIENT_NAME = "FlightBoard"
JELLYFIN_DEVICE_NAME = "FlightBoard"
JELLYFIN_DEVICE_ID = "flight-board"
JELLYFIN_CLIENT_VERSION = "1.0.0"


def _describe_http_error(exc: HTTPError) -> str:
    try:
        raw_body = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        raw_body = ""
    body = raw_body if raw_body else "<empty body>"
    return (
        f"HTTP {exc.code} ({exc.reason}) for {exc.url}. "
        f"Response body: {body}"
    )


def _authorization_header(api_key: str) -> str:
    return (
        "MediaBrowser "
        f'Client="{JELLYFIN_CLIENT_NAME}", '
        f'Device="{JELLYFIN_DEVICE_NAME}", '
        f'DeviceId="{JELLYFIN_DEVICE_ID}", '
        f'Version="{JELLYFIN_CLIENT_VERSION}", '
        f'Token="{api_key}"'
    )


def _get_env_var(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                registry_value, _ = winreg.QueryValueEx(key, name)
                if isinstance(registry_value, str) and registry_value:
                    return registry_value
        except OSError:
            return None
    return None


def _fetch_activity_entries(api_key: str) -> list[dict[str, Any]]:
    request = Request(
        JELLYFIN_ACTIVITY_URL,
        headers={
            "Accept": "application/json",
            "Authorization": _authorization_header(api_key),
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=10) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"Jellyfin activity API failed: {_describe_http_error(exc)}") from exc
    except URLError as exc:
        raise RuntimeError(f"Jellyfin activity connection failed: {exc.reason}.") from exc

    data = json.loads(response_body)
    items = data.get("Items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _normalize_activity(item: dict[str, Any]) -> dict[str, str]:
    title = (
        str(item.get("Name"))
        if item.get("Name")
        else str(item.get("Type") or "Activity")
    )
    description = (
        str(item.get("ShortOverview"))
        if item.get("ShortOverview")
        else str(item.get("Overview") or "")
    )
    return {
        "title": title,
        "description": description,
        "type": str(item.get("Type") or "-"),
        "user": str(item.get("UserName") or "-"),
        "created_at": str(item.get("Date") or "-"),
    }


def fetch_on_demand_status() -> dict[str, Any]:
    api_key = _get_env_var(JELLYFIN_API_KEY_ENV)
    if not api_key:
        return {
            "event_type": "query",
            "status": "error",
            "title": "Jellyfin unavailable",
            "message": f"Environment variable {JELLYFIN_API_KEY_ENV} is not set.",
            "payload": {"activity_count": 0, "activities": []},
        }

    try:
        items = _fetch_activity_entries(api_key)
    except RuntimeError as exc:
        return {
            "event_type": "query",
            "status": "error",
            "title": "Jellyfin unavailable",
            "message": str(exc),
            "payload": {"activity_count": 0, "activities": []},
        }

    activities = [_normalize_activity(item) for item in items[:3]]
    return {
        "event_type": "query",
        "status": "ok",
        "title": "Jellyfin recent activity",
        "message": f"Fetched {len(activities)} recent activit(ies).",
        "payload": {
            "activity_count": len(activities),
            "activities": activities,
        },
    }
