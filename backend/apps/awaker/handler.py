from __future__ import annotations

import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json


AWAKER_URL = "https://awaker.marlosbosso.net/listcommands?n=3"


def fetch_on_demand_status() -> dict[str, Any]:
    api_key = os.getenv("AWAKER_KEY")
    if not api_key:
        return {
            "event_type": "query",
            "status": "error",
            "title": "Awaker query failed",
            "message": "Environment variable AWAKER_KEY is not set.",
            "payload": {"commands_count": 0, "commands": []},
        }

    request = Request(
        AWAKER_URL,
        headers={
            "X-Functions-Key": api_key,
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=10) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as exc:
        return {
            "event_type": "query",
            "status": "error",
            "title": "Awaker query failed",
            "message": f"HTTP error from Awaker: {exc.code}",
            "payload": {"commands_count": 0, "commands": []},
        }
    except URLError as exc:
        return {
            "event_type": "query",
            "status": "error",
            "title": "Awaker query failed",
            "message": f"Connection error: {exc.reason}",
            "payload": {"commands_count": 0, "commands": []},
        }

    data = json.loads(response_body)
    if isinstance(data, list):
        commands = data
    elif isinstance(data, dict):
        if isinstance(data.get("commands"), list):
            commands = data["commands"]
        elif isinstance(data.get("objects"), list):
            commands = data["objects"]
        else:
            commands = []
    else:
        commands = []

    return {
        "event_type": "query",
        "status": "ok",
        "title": "Awaker latest commands",
        "message": f"Fetched {len(commands)} command(s).",
        "payload": {
            "commands_count": len(commands),
            "commands": commands,
        },
    }
