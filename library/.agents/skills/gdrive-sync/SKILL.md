---
name: gdrive-sync
description: Use when interacting with Google Drive or Shared Drives — authenticating, downloading folders/spreadsheets/datasets, uploading artifacts, or inspecting remote file trees.
---

# Google Drive Sync & Data Exchange Skill

Provides deterministic, zero-friction tools to authenticate, list, download, and upload datasets, catalogs, and artifacts to/from Google Drive and Shared Drives.

## Prerequisites & Auth Resolution

1. **Credentials Resolution Order**:
   - `GDRIVE_TOKEN_PATH` env var → `<repo_root>/token.json`
   - `GDRIVE_CREDENTIALS_PATH` env var → `<repo_root>/credentials.json`
2. **Auto-refresh**: When `token.json` is expired, `gdrive_auth.py` refreshes it automatically via its stored OAuth refresh token without prompting.
3. **Interactive Login (Fallback)**: If `token.json` is missing or revoked, it automatically spins up a local loopback server on port `64744` and captures the OAuth authorization code.

## Bundled CLI Tools

All scripts accept either a direct Google Drive URL or a Folder/File ID.

### 1. Listing Folder Tree (`gdrive_list.py`)
```bash
python .agents/skills/gdrive-sync/scripts/gdrive_list.py "<FOLDER_URL_OR_ID>" [--depth 3]
```
Example:
```bash
python .agents/skills/gdrive-sync/scripts/gdrive_list.py "https://drive.google.com/drive/folders/<FOLDER_ID>"
```

### 2. Pulling / Downloading Files (`gdrive_pull.py`)
Recursively downloads folders, exports Google Sheets to `.csv`, and Google Docs to `.txt`:
```bash
python .agents/skills/gdrive-sync/scripts/gdrive_pull.py "<FOLDER_URL_OR_ID>" --dest "data/my_folder"
```

### 3. Pushing / Uploading Files (`gdrive_push.py`)
Uploads a local file or directory to a remote Google Drive folder:
```bash
python .agents/skills/gdrive-sync/scripts/gdrive_push.py "output/report.csv" --target "<FOLDER_URL_OR_ID>"
python .agents/skills/gdrive-sync/scripts/gdrive_push.py "data/results/" --target "<FOLDER_URL_OR_ID>"
```

### 4. Python API Usage in Custom Scripts
```python
from pathlib import Path
import sys
# Add skill scripts to sys.path if needed
sys.path.append(str(Path(".agents/skills/gdrive-sync/scripts").resolve()))

from gdrive_auth import get_drive_service

service = get_drive_service(interactive=True)
# service is a standard googleapiclient.discovery Resource for Google Drive v3
```

## Supported Features & Best Practices
- **Shared Drives**: All requests pass `supportsAllDrives=True` and `includeItemsFromAllDrives=True`.
- **Google Workspace Export**: Google Sheets are automatically converted to `.csv` on download.
- **Resumable Uploads**: Large binary and CSV files use chunked resumable uploads (`MediaFileUpload(..., resumable=True)`).
- **Zero Secrets Leakage**: `token.json` and `credentials.json` are excluded by `.gitignore`.
