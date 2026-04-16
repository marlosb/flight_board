from __future__ import annotations

import json
import os
import sys
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PIHOLE_BASE_URL = "https://pihole.home.marlosbosso.net"
PIHOLE_PASSWORD_ENV = "PIHOLE_KEY"
PIHOLE_AUTH_URL = f"{PIHOLE_BASE_URL}/api/auth"
PIHOLE_SUMMARY_URL = f"{PIHOLE_BASE_URL}/api/stats/summary"

_AUTH_LOCK = threading.Lock()
_SID: str | None = None
_SID_EXPIRES_AT_MONOTONIC: float = 0.0


class _PiHoleUnauthorizedError(Exception):
    pass


def _describe_http_error(exc: HTTPError) -> str:
    try:
        raw_body = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        raw_body = ""
    body = raw_body if raw_body else "<empty body>"
    return f"HTTP {exc.code} ({exc.reason}) for {exc.url}. Response body: {body}"


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


def _authenticate() -> tuple[str, int]:
    password = _get_env_var(PIHOLE_PASSWORD_ENV)
    if not password:
        raise RuntimeError(f"Environment variable {PIHOLE_PASSWORD_ENV} is not set.")

    body = json.dumps({"password": password}).encode("utf-8")
    request = Request(
        PIHOLE_AUTH_URL,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=10) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"Pi-hole auth failed: {_describe_http_error(exc)}") from exc
    except URLError as exc:
        raise RuntimeError(f"Pi-hole auth connection failed: {exc.reason}.") from exc

    data = json.loads(response_body)
    session = data.get("session") if isinstance(data, dict) else None
    sid = session.get("sid") if isinstance(session, dict) else None
    validity = session.get("validity") if isinstance(session, dict) else None
    if not isinstance(sid, str) or not sid:
        raise RuntimeError("Pi-hole auth response did not include a valid SID.")
    if not isinstance(validity, int) or validity <= 0:
        validity = 300
    return sid, validity


def _get_or_refresh_sid(force_refresh: bool = False) -> str:
    global _SID, _SID_EXPIRES_AT_MONOTONIC
    with _AUTH_LOCK:
        now = time.monotonic()
        needs_refresh = (
            force_refresh
            or not _SID
            or now >= (_SID_EXPIRES_AT_MONOTONIC - 5.0)
        )
        if needs_refresh:
            sid, validity = _authenticate()
            _SID = sid
            _SID_EXPIRES_AT_MONOTONIC = now + float(validity)
        return _SID


def _fetch_summary(sid: str) -> dict[str, Any]:
    request = Request(
        PIHOLE_SUMMARY_URL,
        headers={
            "Accept": "application/json",
            "X-FTL-SID": sid,
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=10) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as exc:
        if exc.code == 401:
            raise _PiHoleUnauthorizedError(
                f"Pi-hole SID unauthorized: {_describe_http_error(exc)}"
            ) from exc
        raise RuntimeError(f"Pi-hole summary request failed: {_describe_http_error(exc)}") from exc
    except URLError as exc:
        raise RuntimeError(f"Pi-hole summary connection failed: {exc.reason}.") from exc

    data = json.loads(response_body)
    if not isinstance(data, dict):
        raise RuntimeError("Pi-hole summary response is not a JSON object.")
    return data


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _to_percent_text(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}%"
    if isinstance(value, str) and value.strip():
        return value if value.strip().endswith("%") else f"{value.strip()}%"
    return "-"


def fetch_on_demand_status() -> dict[str, Any]:
    try:
        sid = _get_or_refresh_sid(force_refresh=False)
        try:
            summary = _fetch_summary(sid)
        except _PiHoleUnauthorizedError:
            sid = _get_or_refresh_sid(force_refresh=True)
            summary = _fetch_summary(sid)
    except RuntimeError as exc:
        return {
            "event_type": "query",
            "status": "error",
            "title": "Pi-hole unavailable",
            "message": str(exc),
            "payload": {"total": 0, "blocked": 0, "percent_blocked": "-"},
        }

    queries_summary = summary.get("queries") if isinstance(summary.get("queries"), dict) else {}

    total = _to_int(summary.get("total"))
    if total is None:
        total = _to_int(queries_summary.get("total"))
    if total is None:
        total = _to_int(summary.get("dns_queries_today"))

    blocked = _to_int(summary.get("blocked"))
    if blocked is None:
        blocked = _to_int(queries_summary.get("blocked"))
    if blocked is None:
        blocked = _to_int(summary.get("ads_blocked_today"))

    percent_blocked = summary.get("percent_blocked")
    if percent_blocked is None:
        percent_blocked = queries_summary.get("percent_blocked")
    if percent_blocked is None:
        percent_blocked = summary.get("ads_percentage_today")

    return {
        "event_type": "query",
        "status": "ok",
        "title": "Pi-hole summary",
        "message": "Fetched Pi-hole summary stats.",
        "payload": {
            "total": total if total is not None else 0,
            "blocked": blocked if blocked is not None else 0,
            "percent_blocked": _to_percent_text(percent_blocked),
            "raw": summary,
        },
    }
