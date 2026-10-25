import os
import sys
import argparse
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

try:
    from gdrive_auth import get_drive_service
    from gdrive_pull import extract_id_from_url_or_id
except ImportError:
    from .gdrive_auth import get_drive_service
    from .gdrive_pull import extract_id_from_url_or_id

def list_folder_tree(service, folder_id: str, depth: int = 0, max_depth: int = 3):
    query = f"'{folder_id}' in parents and trashed = false"
    results = service.files().list(
        q=query,
        fields="files(id, name, mimeType, size)",
        pageSize=100,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    
    files = results.get("files", [])
    indent = "  " * depth
    for f in files:
        name = f['name']
        fid = f['id']
        mime = f['mimeType']
        size = f.get('size', 'DIR' if mime == 'application/vnd.google-apps.folder' else 'N/A')
        
        if mime == 'application/vnd.google-apps.folder':
            print(f"{indent}[DIR]  {name}/ (ID: {fid})")
            if depth < max_depth:
                list_folder_tree(service, fid, depth + 1, max_depth)
        else:
            print(f"{indent}[FILE] {name} [{size} B] (ID: {fid})")

def main():
    parser = argparse.ArgumentParser(description="List Google Drive folder tree.")
    parser.add_argument("source", help="Google Drive URL or Folder ID")
    parser.add_argument("--depth", type=int, default=3, help="Max recursion depth (default: 3)")
    
    args = parser.parse_args()
    folder_id = extract_id_from_url_or_id(args.source)
    
    service = get_drive_service(interactive=True)
    print(f"--- Google Drive Folder Tree (ID: {folder_id}) ---")
    list_folder_tree(service, folder_id, depth=0, max_depth=args.depth)

if __name__ == "__main__":
    main()
