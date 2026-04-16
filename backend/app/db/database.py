from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DB_DIR = PROJECT_ROOT / "data" / "sqlite"
DB_PATH = DB_DIR / "status_board.db"


def get_connection() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def init_db() -> None:
    with get_connection() as connection:
        cursor = connection.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS apps (
                app_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                mode TEXT NOT NULL CHECK (mode IN ('push', 'query')),
                api_key TEXT,
                enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                ui_path TEXT NOT NULL,
                handler_path TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS app_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id TEXT NOT NULL,
                workflow_id TEXT NULL,
                step INTEGER NULL,
                event_type TEXT NULL,
                status TEXT NULL,
                title TEXT NULL,
                message TEXT NULL,
                payload_json TEXT NULL,
                parent_event_id INTEGER NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (app_id) REFERENCES apps(app_id) ON DELETE CASCADE,
                FOREIGN KEY (parent_event_id) REFERENCES app_events(id) ON DELETE SET NULL
            );
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_app_events_app_created
            ON app_events(app_id, created_at DESC);
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_app_events_app_workflow_created
            ON app_events(app_id, workflow_id, created_at DESC);
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_app_events_created
            ON app_events(created_at);
            """
        )

        connection.commit()


def ensure_apps_schema() -> None:
    with get_connection() as connection:
        cursor = connection.cursor()
        columns = {
            row["name"]
            for row in cursor.execute("PRAGMA table_info(apps);").fetchall()
        }
        if "api_key" not in columns:
            cursor.execute("ALTER TABLE apps ADD COLUMN api_key TEXT;")
        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_apps_api_key_unique
            ON apps(api_key)
            WHERE api_key IS NOT NULL;
            """
        )
        connection.commit()


def upsert_app(
    app_id: str,
    display_name: str,
    mode: str,
    api_key: str | None,
    ui_path: str,
    handler_path: str,
    enabled: bool = True,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO apps (app_id, display_name, mode, api_key, enabled, ui_path, handler_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(app_id) DO UPDATE SET
                display_name = excluded.display_name,
                mode = excluded.mode,
                api_key = excluded.api_key,
                enabled = excluded.enabled,
                ui_path = excluded.ui_path,
                handler_path = excluded.handler_path,
                updated_at = datetime('now');
            """,
            (app_id, display_name, mode, api_key, int(enabled), ui_path, handler_path),
        )
        connection.commit()


def migrate_app_id(old_app_id: str, new_app_id: str) -> None:
    with get_connection() as connection:
        existing_old = connection.execute(
            "SELECT app_id FROM apps WHERE app_id = ?;",
            (old_app_id,),
        ).fetchone()
        if existing_old is None:
            return
        existing_new = connection.execute(
            "SELECT app_id FROM apps WHERE app_id = ?;",
            (new_app_id,),
        ).fetchone()
        if existing_new is None:
            return
        connection.execute(
            """
            UPDATE app_events
            SET app_id = ?
            WHERE app_id = ?;
            """,
            (new_app_id, old_app_id),
        )
        connection.execute(
            """
            DELETE FROM apps
            WHERE app_id = ?;
            """,
            (old_app_id,),
        )
        connection.commit()


def get_enabled_query_apps() -> list[sqlite3.Row]:
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT app_id, display_name, handler_path
            FROM apps
            WHERE enabled = 1 AND mode = 'query'
            ORDER BY app_id ASC;
            """
        ).fetchall()


def get_enabled_app(app_id: str) -> sqlite3.Row | None:
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT app_id, display_name, mode, enabled, ui_path, handler_path
            FROM apps
            WHERE app_id = ? AND enabled = 1;
            """,
            (app_id,),
        ).fetchone()


def get_enabled_apps_catalog() -> list[sqlite3.Row]:
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT app_id, display_name, mode, ui_path
            FROM apps
            WHERE enabled = 1
            ORDER BY app_id ASC;
            """
        ).fetchall()


def insert_app_event(
    app_id: str,
    workflow_id: str | None,
    step: int | None,
    event_type: str | None,
    status: str | None,
    title: str | None,
    message: str | None,
    payload: dict[str, Any] | None,
    parent_event_id: int | None,
    created_at: str | None = None,
) -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO app_events (
                app_id, workflow_id, step, event_type, status, title, message, payload_json, parent_event_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')));
            """,
            (
                app_id,
                workflow_id,
                step,
                event_type,
                status,
                title,
                message,
                json.dumps(payload) if payload is not None else None,
                parent_event_id,
                created_at,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def get_latest_status_by_app() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                a.app_id,
                a.display_name,
                a.mode,
                a.enabled,
                a.ui_path,
                e.id AS event_id,
                e.workflow_id,
                e.step,
                e.event_type,
                e.status,
                e.title,
                e.message,
                e.payload_json,
                e.parent_event_id,
                e.created_at AS event_created_at
            FROM apps a
            LEFT JOIN app_events e
                ON e.id = (
                    SELECT e2.id
                    FROM app_events e2
                    WHERE e2.app_id = a.app_id
                    ORDER BY e2.created_at DESC, e2.id DESC
                    LIMIT 1
                )
            WHERE a.enabled = 1
            ORDER BY a.app_id ASC;
            """
        ).fetchall()

    latest_status: list[dict[str, Any]] = []
    for row in rows:
        payload = None
        if row["payload_json"]:
            payload = json.loads(row["payload_json"])
        latest_status.append(
            {
                "app_id": row["app_id"],
                "display_name": row["display_name"],
                "mode": row["mode"],
                "ui_path": row["ui_path"],
                "event": {
                    "id": row["event_id"],
                    "workflow_id": row["workflow_id"],
                    "step": row["step"],
                    "event_type": row["event_type"],
                    "status": row["status"],
                    "title": row["title"],
                    "message": row["message"],
                    "payload": payload,
                    "parent_event_id": row["parent_event_id"],
                    "created_at": row["event_created_at"],
                }
                if row["event_id"] is not None
                else None,
            }
        )
    return latest_status


def get_latest_status_for_app(app_id: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                a.app_id,
                a.display_name,
                a.mode,
                a.ui_path,
                e.id AS event_id,
                e.workflow_id,
                e.step,
                e.event_type,
                e.status,
                e.title,
                e.message,
                e.payload_json,
                e.parent_event_id,
                e.created_at AS event_created_at
            FROM apps a
            LEFT JOIN app_events e
                ON e.id = (
                    SELECT e2.id
                    FROM app_events e2
                    WHERE e2.app_id = a.app_id
                    ORDER BY e2.created_at DESC, e2.id DESC
                    LIMIT 1
                )
            WHERE a.enabled = 1 AND a.app_id = ?;
            """,
            (app_id,),
        ).fetchone()

    if row is None:
        return None

    payload = None
    if row["payload_json"]:
        payload = json.loads(row["payload_json"])

    return {
        "app_id": row["app_id"],
        "display_name": row["display_name"],
        "mode": row["mode"],
        "ui_path": row["ui_path"],
        "event": {
            "id": row["event_id"],
            "workflow_id": row["workflow_id"],
            "step": row["step"],
            "event_type": row["event_type"],
            "status": row["status"],
            "title": row["title"],
            "message": row["message"],
            "payload": payload,
            "parent_event_id": row["parent_event_id"],
            "created_at": row["event_created_at"],
        }
        if row["event_id"] is not None
        else None,
    }


def get_recent_events_for_app(app_id: str, limit: int = 3) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                workflow_id,
                step,
                event_type,
                status,
                title,
                message,
                payload_json,
                parent_event_id,
                created_at
            FROM app_events
            WHERE app_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?;
            """,
            (app_id, limit),
        ).fetchall()

    recent_events: list[dict[str, Any]] = []
    for row in rows:
        payload = None
        if row["payload_json"]:
            payload = json.loads(row["payload_json"])
        recent_events.append(
            {
                "id": row["id"],
                "workflow_id": row["workflow_id"],
                "step": row["step"],
                "event_type": row["event_type"],
                "status": row["status"],
                "title": row["title"],
                "message": row["message"],
                "payload": payload,
                "parent_event_id": row["parent_event_id"],
                "created_at": row["created_at"],
            }
        )
    return recent_events


def purge_app_events_older_than(days: int) -> int:
    if days <= 0:
        raise ValueError("days must be a positive integer")
    with get_connection() as connection:
        cursor = connection.execute(
            """
            DELETE FROM app_events
            WHERE created_at < datetime('now', ?);
            """,
            (f"-{days} days",),
        )
        connection.commit()
        return int(cursor.rowcount if cursor.rowcount is not None else 0)
