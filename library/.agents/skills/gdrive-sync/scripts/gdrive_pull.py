import os
import sys
import re
import argparse
from pathlib import Path
from googleapiclient.http import MediaIoBaseDownload

try:
    from gdrive_auth import get_drive_service
except ImportError:
    from .gdrive_auth import get_drive_service

def extract_id_from_url_or_id(input_str: str) -> str:
    input_str = input_str.strip()
    # Match /folders/<id>
    folder_match = re.search(r'/folders/([a-zA-Z0-9_-]+)', input_str)
    if folder_match:
        return folder_match.group(1)
    # Match /d/<id> (docs, sheets, files)
    file_match = re.search(r'/d/([a-zA-Z0-9_-]+)', input_str)
    if file_match:
        return file_match.group(1)
    # Match id query parameter ?id=<id>
    id_param_match = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', input_str)
    if id_param_match:
        return id_param_match.group(1)
    # Plain ID
    return input_str

def download_file_or_folder(service, item_id: str, dest_dir: Path, recursive: bool = True):
    # Fetch metadata
    meta = service.files().get(
        fileId=item_id,
        fields="id, name, mimeType, size",
        supportsAllDrives=True
    ).execute()
    
    mime = meta.get("mimeType", "")
    name = meta.get("name", item_id)
    
    if mime == 'application/vnd.google-apps.folder':
        target_dir = dest_dir / name if dest_dir.name != name else dest_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        print(f"[gdrive-sync] Entering folder: '{name}' (ID: {item_id})")
        
        query = f"'{item_id}' in parents and trashed = false"
        page_token = None
        
        while True:
            results = service.files().list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType, size)",
                pageSize=100,
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()
            
            files = results.get("files", [])
            for f in files:
                f_id = f["id"]
                f_name = f["name"]
                f_mime = f["mimeType"]
                
                if f_mime == 'application/vnd.google-apps.folder':
                    if recursive:
                        download_file_or_folder(service, f_id, target_dir / f_name, recursive=True)
                    else:
                        print(f"[gdrive-sync] Skipping subfolder '{f_name}' (use --recursive)")
                else:
                    _download_single_file(service, f, target_dir)
                    
            page_token = results.get("nextPageToken")
            if not page_token:
                break
    else:
        dest_dir.mkdir(parents=True, exist_ok=True)
        _download_single_file(service, meta, dest_dir)

def _download_single_file(service, file_meta: dict, target_dir: Path):
    fid = file_meta['id']
    name = file_meta['name']
    mime = file_meta['mimeType']
    size = file_meta.get('size', 'N/A')
    
    target_path = target_dir / name
    
    if 'google-apps' in mime:
        if 'spreadsheet' in mime:
            req = service.files().export_media(fileId=fid, mimeType='text/csv')
            if not target_path.suffix.lower() == '.csv':
                target_path = target_path.with_suffix('.csv')
        elif 'document' in mime:
            req = service.files().export_media(fileId=fid, mimeType='text/plain')
            if not target_path.suffix.lower() == '.txt':
                target_path = target_path.with_suffix('.txt')
        else:
            req = service.files().export_media(fileId=fid, mimeType='application/pdf')
            if not target_path.suffix.lower() == '.pdf':
                target_path = target_path.with_suffix('.pdf')
    else:
        req = service.files().get_media(fileId=fid)
        
    print(f" -> Downloading '{target_path.name}' ({size} bytes)...")
    with open(target_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, req)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            
    print(f"    Saved: {target_path} ({target_path.stat().st_size} bytes)")

def main():
    parser = argparse.ArgumentParser(description="Download files/folders from Google Drive.")
    parser.add_argument("source", help="Google Drive URL or Folder/File ID")
    parser.add_argument("--dest", "-d", default="data/gdrive_download", help="Destination directory (default: data/gdrive_download)")
    parser.add_argument("--no-recursive", action="store_true", help="Do not recursively download subfolders")
    
    args = parser.parse_args()
    
    target_id = extract_id_from_url_or_id(args.source)
    dest_path = Path(args.dest).resolve()
    
    print(f"[gdrive-sync] Target ID: {target_id}")
    print(f"[gdrive-sync] Destination: {dest_path}")
    
    service = get_drive_service(interactive=True)
    download_file_or_folder(service, target_id, dest_path, recursive=not args.no_recursive)
    print("\n[gdrive-sync] Download completed successfully!")

if __name__ == "__main__":
    main()
