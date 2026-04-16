from __future__ import annotations

import importlib.util
import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.db.database import (
    ensure_apps_schema,
    get_enabled_app,
    get_enabled_apps_catalog,
    get_enabled_query_apps,
    get_latest_status_for_app,
    get_latest_status_by_app,
    init_db,
    insert_app_event,
    purge_app_events_older_than,
    upsert_app,
)

app = FastAPI(title="Homelab Status Board")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
EVENT_RETENTION_DAYS = 30
CLEANUP_INTERVAL_SECONDS = 86400

logger = logging.getLogger(__name__)
_cleanup_stop_event = threading.Event()
_cleanup_thread: threading.Thread | None = None

app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")


def _run_retention_cleanup() -> None:
    deleted_rows = purge_app_events_older_than(EVENT_RETENTION_DAYS)
    if deleted_rows > 0:
        logger.info(
            "Purged %s app_events row(s) older than %s day(s).",
            deleted_rows,
            EVENT_RETENTION_DAYS,
        )


def _cleanup_worker() -> None:
    while not _cleanup_stop_event.wait(CLEANUP_INTERVAL_SECONDS):
        try:
            _run_retention_cleanup()
        except Exception:
            logger.exception("Retention cleanup job failed.")


@app.on_event("startup")
def on_startup() -> None:
    global _cleanup_thread
    init_db()
    ensure_apps_schema()
    register_builtin_apps()
    _run_retention_cleanup()
    if _cleanup_thread is None or not _cleanup_thread.is_alive():
        _cleanup_stop_event.clear()
        _cleanup_thread = threading.Thread(target=_cleanup_worker, name="retention-cleanup", daemon=True)
        _cleanup_thread.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    _cleanup_stop_event.set()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


class AppRegistrationRequest(BaseModel):
    app_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    mode: Literal["push", "query"]
    api_key: str | None = Field(default=None, min_length=8)
    ui_path: str = Field(min_length=1)
    handler_path: str = Field(min_length=1)
    enabled: bool = True


class AppEventRequest(BaseModel):
    app_name: str = Field(min_length=1)
    timestamp: str = Field(min_length=1)
    event: Any


@app.post("/apps/register")
def register_app(request: AppRegistrationRequest) -> dict[str, str]:
    try:
        upsert_app(
            app_id=request.app_id,
            display_name=request.display_name,
            mode=request.mode,
            api_key=request.api_key,
            ui_path=request.ui_path,
            handler_path=request.handler_path,
            enabled=request.enabled,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to register app: {exc}") from exc
    return {"status": "ok", "app_id": request.app_id}


def register_builtin_apps() -> None:
    upsert_app(
        app_id="awaker",
        display_name="Awaker",
        mode="query",
        api_key=None,
        ui_path="backend/apps/awaker/ui.json",
        handler_path="backend/apps/awaker/handler.py",
        enabled=True,
    )
    upsert_app(
        app_id="s1_pro",
        display_name="S1 Pro",
        mode="query",
        api_key=None,
        ui_path="backend/apps/s1_pro/ui.json",
        handler_path="backend/apps/s1_pro/handler.py",
        enabled=True,
    )
    upsert_app(
        app_id="jellyfin",
        display_name="Jellyfin",
        mode="query",
        api_key=None,
        ui_path="backend/apps/jellyfin/ui.json",
        handler_path="backend/apps/jellyfin/handler.py",
        enabled=True,
    )
    upsert_app(
        app_id="pihole",
        display_name="Pi-hole",
        mode="query",
        api_key=None,
        ui_path="backend/apps/pihole/ui.json",
        handler_path="backend/apps/pihole/handler.py",
        enabled=True,
    )
    upsert_app(
        app_id="transcoded",
        display_name="Transcoded",
        mode="push",
        api_key=None,
        ui_path="backend/apps/transcoded/ui.json",
        handler_path="backend/apps/transcoded/handler.py",
        enabled=True,
    )


def _load_handler_function(handler_path: str):
    absolute_handler_path = PROJECT_ROOT / handler_path
    if not absolute_handler_path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Handler not found for query app: {handler_path}",
        )

    spec = importlib.util.spec_from_file_location(
        f"dynamic_handler_{absolute_handler_path.parent.name}_{absolute_handler_path.stem}",
        absolute_handler_path,
    )
    if spec is None or spec.loader is None:
        raise HTTPException(
            status_code=500,
            detail=f"Cannot load handler module: {handler_path}",
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fetch_fn = getattr(module, "fetch_on_demand_status", None)
    if fetch_fn is None or not callable(fetch_fn):
        raise HTTPException(
            status_code=500,
            detail=f"Handler must expose callable fetch_on_demand_status(): {handler_path}",
        )
    return fetch_fn


def refresh_query_apps() -> None:
    register_builtin_apps()
    query_apps = get_enabled_query_apps()
    for query_app in query_apps:
        fetch_fn = _load_handler_function(str(query_app["handler_path"]))
        payload = fetch_fn()
        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=500,
                detail=f"Query handler returned invalid payload for app {query_app['app_id']}.",
            )
        insert_app_event(
            app_id=str(query_app["app_id"]),
            workflow_id=payload.get("workflow_id"),
            step=payload.get("step"),
            event_type=payload.get("event_type"),
            status=payload.get("status"),
            title=payload.get("title"),
            message=payload.get("message"),
            payload=payload.get("payload"),
            parent_event_id=payload.get("parent_event_id"),
        )


def refresh_query_app(app_id: str) -> None:
    app_row = get_enabled_app(app_id)
    if app_row is None:
        raise HTTPException(status_code=404, detail=f"App not found or disabled: {app_id}")
    if app_row["mode"] != "query":
        return

    fetch_fn = _load_handler_function(str(app_row["handler_path"]))
    payload = fetch_fn()
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=500,
            detail=f"Query handler returned invalid payload for app {app_id}.",
        )
    insert_app_event(
        app_id=app_id,
        workflow_id=payload.get("workflow_id"),
        step=payload.get("step"),
        event_type=payload.get("event_type"),
        status=payload.get("status"),
        title=payload.get("title"),
        message=payload.get("message"),
        payload=payload.get("payload"),
        parent_event_id=payload.get("parent_event_id"),
    )


def _load_ui_config(ui_path: str) -> dict[str, Any]:
    absolute_ui_path = PROJECT_ROOT / ui_path
    if not absolute_ui_path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"UI config not found: {ui_path}",
        )
    try:
        return json.loads(absolute_ui_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Invalid UI config JSON for {ui_path}: {exc}",
        ) from exc


def _humanize_app_name(app_name: str) -> str:
    tokens = app_name.replace("_", " ").replace("-", " ").split()
    if not tokens:
        return app_name
    return " ".join(token.capitalize() for token in tokens)


def _normalize_timestamp(raw_timestamp: str) -> str:
    timestamp = raw_timestamp.strip()
    if not timestamp:
        raise HTTPException(status_code=400, detail="timestamp cannot be blank.")
    normalized = timestamp.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="timestamp must be ISO-8601.") from exc
    return parsed.isoformat()


def _normalize_event_payload(event_value: Any) -> dict[str, Any]:
    if isinstance(event_value, dict):
        return event_value
    return {"value": event_value}


def _event_record_fields(
    event_payload: dict[str, Any],
) -> tuple[str | None, str | None, str | None, str | None, dict[str, Any]]:
    event_type = event_payload.get("event_type")
    status = event_payload.get("status")
    title = event_payload.get("title")
    message = event_payload.get("message")
    payload = event_payload.get("payload")

    if not isinstance(event_type, str):
        event_type = "push"
    if not isinstance(status, str):
        status = None
    if not isinstance(title, str):
        title = None
    if not isinstance(message, str):
        message = None
    if not isinstance(payload, dict):
        payload = {"event": event_payload}
    return event_type, status, title, message, payload


def _ensure_push_app_registered(app_name: str) -> None:
    existing_app = get_enabled_app(app_name)
    if existing_app is not None:
        return
    upsert_app(
        app_id=app_name,
        display_name=_humanize_app_name(app_name),
        mode="push",
        api_key=None,
        ui_path="backend/apps/template/ui.json",
        handler_path="backend/apps/template/handler.py",
        enabled=True,
    )


@app.post("/events")
def post_generic_app_event(request: AppEventRequest) -> dict[str, int | str]:
    app_name = request.app_name.strip()
    if not app_name:
        raise HTTPException(status_code=400, detail="app_name cannot be blank.")

    _ensure_push_app_registered(app_name)
    event_payload = _normalize_event_payload(request.event)
    event_type, status, title, message, payload = _event_record_fields(event_payload)

    event_id = insert_app_event(
        app_id=app_name,
        workflow_id=None,
        step=None,
        event_type=event_type,
        status=status,
        title=title,
        message=message,
        payload=payload,
        parent_event_id=None,
        created_at=_normalize_timestamp(request.timestamp),
    )
    return {"status": "ok", "event_id": event_id}


@app.get("/apps/status/latest")
def get_apps_latest_status() -> dict[str, list[dict[str, Any]]]:
    refresh_query_apps()
    apps = get_latest_status_by_app()
    for app_status in apps:
        app_status["ui"] = _load_ui_config(str(app_status["ui_path"]))
    return {"apps": apps}


@app.get("/apps/catalog")
def get_apps_catalog() -> dict[str, list[dict[str, Any]]]:
    register_builtin_apps()
    catalog = get_enabled_apps_catalog()
    return {
        "apps": [
            {
                "app_id": str(row["app_id"]),
                "display_name": str(row["display_name"]),
                "mode": str(row["mode"]),
                "ui": _load_ui_config(str(row["ui_path"])),
            }
            for row in catalog
        ]
    }


@app.get("/apps/{app_id}/status/latest")
def get_app_latest_status(app_id: str) -> dict[str, dict[str, Any]]:
    register_builtin_apps()
    refresh_query_app(app_id)
    app_status = get_latest_status_for_app(app_id)
    if app_status is None:
        raise HTTPException(status_code=404, detail=f"App not found or disabled: {app_id}")
    app_status["ui"] = _load_ui_config(str(app_status["ui_path"]))
    return {"app": app_status}
