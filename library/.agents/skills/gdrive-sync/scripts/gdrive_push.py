import os
import sys
import argparse
from pathlib import Path
from googleapiclient.http import MediaFileUpload

try:
    from gdrive_auth import get_drive_service
    from gdrive_pull import extract_id_from_url_or_id
except ImportError:
    from .gdrive_auth import get_drive_service
    from .gdrive_pull import extract_id_from_url_or_id

def create_remote_folder(service, folder_name: str, parent_id: str) -> str:
    query = f"'{parent_id}' in parents and name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(
        q=query,
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]
        
    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id]
    }
    folder = service.files().create(
        body=metadata,
        fields="id",
        supportsAllDrives=True
    ).execute()
    print(f"[gdrive-sync] Created remote folder: '{folder_name}' (ID: {folder.get('id')})")
    return folder.get("id")

def upload_file(service, local_file: Path, parent_id: str, overwrite: bool = True):
    file_name = local_file.name
    query = f"'{parent_id}' in parents and name = '{file_name}' and trashed = false"
    results = service.files().list(
        q=query,
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    existing = results.get("files", [])
    
    media = MediaFileUpload(str(local_file), resumable=True)
    
    if existing and overwrite:
        existing_id = existing[0]["id"]
        print(f" -> Updating existing '{file_name}' (ID: {existing_id})...")
        updated = service.files().update(
            fileId=existing_id,
            media_body=media,
            fields="id",
            supportsAllDrives=True
        ).execute()
        print(f"    Updated successfully: {updated.get('id')}")
        return updated.get("id")
    elif existing and not overwrite:
        print(f"[gdrive-sync] Skipping '{file_name}' (already exists).")
        return existing[0]["id"]
    else:
        print(f" -> Uploading new file '{file_name}'...")
        metadata = {
            "name": file_name,
            "parents": [parent_id]
        }
        created = service.files().create(
            body=metadata,
            media_body=media,
            fields="id",
            supportsAllDrives=True
        ).execute()
        print(f"    Uploaded successfully: {created.get('id')}")
        return created.get("id")

def upload_directory(service, local_dir: Path, parent_id: str, overwrite: bool = True):
    remote_parent_id = create_remote_folder(service, local_dir.name, parent_id)
    for root, dirs, files in os.walk(local_dir):
        rel_path = Path(root).relative_to(local_dir)
        curr_parent = remote_parent_id
        
        # Build subfolder path if any
        if str(rel_path) != ".":
            for part in rel_path.parts:
                curr_parent = create_remote_folder(service, part, curr_parent)
                
        for f in files:
            p = Path(root) / f
            upload_file(service, p, curr_parent, overwrite=overwrite)

def main():
    parser = argparse.ArgumentParser(description="Upload files/folders to Google Drive.")
    parser.add_argument("source", help="Local file or folder path to upload")
    parser.add_argument("--target", "-t", required=True, help="Target Google Drive Folder ID or URL")
    parser.add_argument("--no-overwrite", action="store_true", help="Do not overwrite existing files")
    
    args = parser.parse_args()
    local_path = Path(args.source).resolve()
    target_id = extract_id_from_url_or_id(args.target)
    
    if not local_path.exists():
        print(f"[Error] Local path '{local_path}' does not exist.")
        sys.exit(1)
        
    service = get_drive_service(interactive=True)
    
    if local_path.is_dir():
        print(f"[gdrive-sync] Uploading directory '{local_path.name}' to {target_id}...")
        upload_directory(service, local_path, target_id, overwrite=not args.no_overwrite)
    else:
        print(f"[gdrive-sync] Uploading file '{local_path.name}' to {target_id}...")
        upload_file(service, local_path, target_id, overwrite=not args.no_overwrite)
        
    print("\n[gdrive-sync] Upload completed successfully!")

if __name__ == "__main__":
    main()
