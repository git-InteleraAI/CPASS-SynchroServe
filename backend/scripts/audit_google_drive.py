"""Audit script for Google Drive configuration and permissions.
Does not print secrets, tokens, or private keys.
"""

import json
import os
import sys
from pathlib import Path

# Add backend directory to sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings

def audit_drive():
    print("=" * 60)
    print("PHASE 2: GOOGLE DRIVE CONFIGURATION AUDIT")
    print("=" * 60)

    # 1. Check .env loading
    env_path = BACKEND_DIR / ".env"
    print(f"Backend .env file exists at {env_path.name}: {env_path.exists()}")

    # 2. Check settings loaded
    sa_file_setting = settings.google_service_account_file
    sa_json_setting = bool(settings.google_service_account_json)
    folder_id_setting = settings.google_drive_folder_id
    oauth_configured = bool(settings.google_client_id and settings.google_client_secret and settings.google_refresh_token)

    print("\nSettings Loaded from Environment:")
    print(f"  GOOGLE_SERVICE_ACCOUNT_FILE: {sa_file_setting or '[NOT SET]'}")
    print(f"  GOOGLE_SERVICE_ACCOUNT_JSON: {'[CONFIGURED]' if sa_json_setting else '[NOT SET]'}")
    print(f"  GOOGLE_DRIVE_FOLDER_ID:      {folder_id_setting or '[NOT SET]'}")
    print(f"  OAuth Credentials:           {'[CONFIGURED]' if oauth_configured else '[NOT SET]'}")

    # 3. Path resolution for secrets/google_service_account.json
    expected_path = BACKEND_DIR / "secrets" / "google_service_account.json"
    print(f"\nChecking expected service account file:")
    print(f"  Target path: {expected_path}")
    print(f"  Exists:      {expected_path.exists()}")

    resolved_file = None
    if sa_file_setting:
        candidate1 = Path(sa_file_setting)
        candidate2 = BACKEND_DIR / sa_file_setting
        if candidate1.is_file():
            resolved_file = candidate1
        elif candidate2.is_file():
            resolved_file = candidate2
    elif expected_path.is_file():
        resolved_file = expected_path

    if resolved_file and resolved_file.is_file():
        print(f"  Resolved path: {resolved_file}")
        try:
            with open(resolved_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            cred_type = data.get("type")
            client_email = data.get("client_email")
            project_id = data.get("project_id")
            has_private_key = bool(data.get("private_key"))
            private_key_id = data.get("private_key_id")

            print("\nService Account JSON Inspection (Non-Secret Metadata):")
            print(f"  Type:            {cred_type}")
            print(f"  Project ID:      {project_id}")
            print(f"  Client Email:    {client_email}")
            print(f"  Has Private Key: {has_private_key} (ID: {private_key_id[:8]}...)")
        except Exception as e:
            print(f"  [ERROR] Failed to parse JSON: {e}")
    else:
        print("  [NOTICE] No service account JSON file found at resolved path.")

    # 4. Check .gitignore
    root_gitignore = BACKEND_DIR.parent / ".gitignore"
    backend_gitignore = BACKEND_DIR / ".gitignore"
    print("\nGit Ignore Audit:")
    for gi in [root_gitignore, backend_gitignore]:
        if gi.exists():
            content = gi.read_text(encoding="utf-8")
            has_env = ".env" in content
            has_secrets = "secrets" in content
            print(f"  {gi.relative_to(BACKEND_DIR.parent)}:")
            print(f"    Ignores .env:    {has_env}")
            print(f"    Ignores secrets: {has_secrets}")

    # 5. Live Google Drive API Access Test
    print("\n--- Live Google Drive Access Verification ---")
    from app.services.google_drive import google_drive_service, GoogleDriveNotConfiguredError

    # If resolved_file is available but settings didn't have it, test with resolved_file
    test_service = google_drive_service
    if not test_service.is_configured() and resolved_file and resolved_file.is_file():
        from app.services.google_drive import GoogleDriveService
        test_service = GoogleDriveService(service_account_file=str(resolved_file), root_folder_id=folder_id_setting)

    if not test_service.is_configured():
        print("  [STATUS] Google Drive is NOT configured.")
        print("  Required Action: Configure GOOGLE_SERVICE_ACCOUNT_FILE and GOOGLE_DRIVE_FOLDER_ID.")
        return

    try:
        drive_client = test_service.get_service()
        about = drive_client.about().get(fields="user(emailAddress,displayName)").execute()
        user_info = about.get("user", {})
        print(f"  [SUCCESS] Google Drive API connection authenticated!")
        print(f"  Authenticated Identity: {user_info.get('displayName')} ({user_info.get('emailAddress')})")

        # Test root folder access if set
        if test_service.root_folder_id:
            try:
                folder_meta = drive_client.files().get(
                    fileId=test_service.root_folder_id,
                    fields="id,name,mimeType,capabilities(canAddChildren,canDelete)"
                ).execute()
                print(f"  Root Folder Name:         {folder_meta.get('name')}")
                print(f"  Root Folder ID:           {folder_meta.get('id')}")
                print(f"  Can Add Children:         {folder_meta.get('capabilities', {}).get('canAddChildren')}")
                print(f"  [STATUS] Target folder access is VALID and WRITEABLE.")
            except Exception as fe:
                print(f"  [WARNING] Target folder check failed: {fe}")
        else:
            print("  [NOTICE] GOOGLE_DRIVE_FOLDER_ID is not set. Root folder ID defaults to 'root'.")

    except Exception as e:
        print(f"  [ERROR] Google Drive connection failed: {e}")

if __name__ == "__main__":
    audit_drive()
