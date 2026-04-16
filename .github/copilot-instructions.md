# Copilot Instructions - Homelab Status Board

## Project Goal
Build a single-user homelab dashboard that consolidates status and ongoing tasks from multiple apps.

## Scope and UX
- Frontend is tile-based.
- Each app can use one or more tiles.
- Tiles should display app-specific status and current/ongoing tasks.
- Do not display generic monitoring telemetry (up/down, CPU, memory).

## Architecture
- Backend: Python + FastAPI.
- Frontend: HTML, CSS, plain JavaScript (no frontend framework).
- Deployment: single container.

## API Behavior
- Expose `POST` routes for apps to push updates.
- Expose `GET` routes for frontend data retrieval.
- Support two status ingestion modes per app: pushed updates via POST and on-demand queried status.
- Push route authentication uses `X-API-Key` per app.
- Query-mode apps are refreshed on status GET.

## App Definition
Each app must have two files:
- `ui.json` (or `ui.yaml`) for frontend appearance parameters.
- `handler.py` for data handling logic.

Recommended path per app:
- `backend/apps/<app_id>/ui.json`
- `backend/apps/<app_id>/handler.py`

## Storage Rules
- Use SQLite for dynamic runtime data (status, tasks, events/history).
- Keep UI parameters in files, not SQLite.
- Keep data handling in Python code, not declarative files.
- Use two runtime tables: `apps` and `app_events`.
- Do not create one table per app.
- Keep `workflow_id` optional in `app_events` to support both simple and chained-task apps.
- Derive current app state from latest events (no dedicated `app_state` table for now).

### Runtime Tables
- `apps`
  - `app_id` (primary key)
  - `display_name`
  - `mode` (`push` or `query`)
  - `api_key` (unique per app)
  - `enabled`
  - `ui_path`
  - `handler_path`
  - `created_at`
  - `updated_at`
- `app_events`
  - `id` (primary key)
  - `app_id` (foreign key to `apps.app_id`)
  - `workflow_id` (nullable)
  - `step`
  - `event_type`
  - `status`
  - `title`
  - `message`
  - `payload_json`
  - `parent_event_id`
  - `created_at`

### Required Indexes
- `apps(api_key)` unique where not null
- `app_events(app_id, created_at DESC)`
- `app_events(app_id, workflow_id, created_at DESC)`
- `app_events(created_at)`

## Data Retention
- Retention is application-managed.
- Support deleting by age (for example, keep last 15 days).
- Support deleting by count (for example, keep last 15 rows per app).

## Implementation Principles
- Keep implementation simple and explicit.
- Optimize for reliability and easy maintenance.
- Prefer clear app-specific status models.
