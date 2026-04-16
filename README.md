# Flight Board

Homelab status dashboard with:
- **Backend:** FastAPI (Python)
- **Frontend:** HTML/CSS/vanilla JS (tile grid)
- **Storage:** SQLite (`data/sqlite/status_board.db`)

## Integration environment variables

Set these before running the server/container:

| Variable | Used by | Purpose |
|---|---|---|
| `AWAKER_KEY` | `backend/apps/awaker/handler.py` | Auth key for Awaker requests |
| `JELLYFIN_KEY` | `backend/apps/jellyfin/handler.py` | Jellyfin API key (MediaBrowser token) |
| `PIHOLE_KEY` | `backend/apps/pihole/handler.py` | Pi-hole password/app password for `/api/auth` |

If any required variable is missing, that app tile will show an error status.

## Data retention

- `app_events` rows older than **30 days** are purged automatically.
- Cleanup runs once at server startup and then daily in a background job.

## Query mode refresh interval

- Query-mode apps are refreshed at most once every **30 minutes**.
- If a query app already has an event newer than 30 minutes, the board uses the latest status from SQLite instead of querying the external app again.

## Run locally (Windows PowerShell)

```powershell
Set-Location C:\Marlos\flight_board
.\.venv\Scripts\Activate.ps1
Set-Item Env:AWAKER_KEY "<your-awaker-key>"
Set-Item Env:JELLYFIN_KEY "<your-jellyfin-api-key>"
Set-Item Env:PIHOLE_KEY "<your-pihole-password>"
Set-Location .\backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Push status updates (generic for all apps)

Push-mode apps post events to:

`POST /events`

Example:

```powershell
Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/events" `
  -ContentType "application/json" `
  -Body '{
    "app_name": "transcoder",
    "timestamp": "2026-04-16T19:25:18Z",
    "event": {
      "text": "HandBrake job running (42%)"
    }
  }'
```

## Container startup script

`start.sh` is the container entrypoint helper:
1. `git pull --ff-only`
2. start API server (`uvicorn app.main:app`)

Supported startup env vars for `start.sh`:
- `REPO_DIR` (default: `/app`)
- `HOST` (default: `0.0.0.0`)
- `PORT` (default: `8000`)
