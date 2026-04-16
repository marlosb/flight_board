# Flight Board

Homelab status dashboard with:
- **Backend:** FastAPI (Python)
- **Frontend:** HTML/CSS/vanilla JS (tile grid)
- **Storage:** SQLite (`data/sqlite/status_board.db`)

## Authentication environment variables

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

## Container startup script

`start.sh` is the container entrypoint helper:
1. `git pull --ff-only`
2. start API server (`uvicorn app.main:app`)

Supported startup env vars for `start.sh`:
- `REPO_DIR` (default: `/app`)
- `HOST` (default: `0.0.0.0`)
- `PORT` (default: `8000`)
