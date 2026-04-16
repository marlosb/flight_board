from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


S1_PRO_URL = "http://192.168.0.135:8000/printer/objects/query?print_stats"


def fetch_on_demand_status() -> dict[str, Any]:
    request = Request(
        S1_PRO_URL,
        headers={"Accept": "application/json"},
        method="GET",
    )

    try:
        with urlopen(request, timeout=5) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as exc:
        return {
            "event_type": "query",
            "status": "error",
            "title": "S1 Pro unavailable",
            "message": f"Printer API returned HTTP {exc.code}.",
            "payload": {},
        }
    except URLError as exc:
        return {
            "event_type": "query",
            "status": "error",
            "title": "S1 Pro unavailable",
            "message": f"Cannot reach printer API: {exc.reason}.",
            "payload": {},
        }

    data = json.loads(response_body)
    print_stats = (
        data.get("result", {})
        .get("status", {})
        .get("print_stats", {})
    )
    if not isinstance(print_stats, dict):
        print_stats = {}

    state = str(print_stats.get("state", "unknown"))
    filename = str(print_stats.get("filename", "")) if print_stats.get("filename") else "-"
    progress = print_stats.get("progress")
    layer_info = print_stats.get("info") if isinstance(print_stats.get("info"), dict) else {}
    current_layer = layer_info.get("current_layer")
    total_layer = layer_info.get("total_layer")

    progress_text = "-"
    if isinstance(progress, (float, int)):
        progress_text = f"{float(progress) * 100:.1f}%"
    layers_text = (
        f"{current_layer if current_layer is not None else '-'} / "
        f"{total_layer if total_layer is not None else '-'}"
    )

    return {
        "event_type": "query",
        "status": "ok",
        "title": "S1 Pro status",
        "message": f"Printer is {state}.",
        "payload": {
            "state": state,
            "filename": filename,
            "progress": progress_text,
            "layers": layers_text,
            "raw": print_stats,
        },
    }
