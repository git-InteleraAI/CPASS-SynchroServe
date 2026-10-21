"""Google Drive API service for CPASS L1 document management.

Supports Service Account credentials (file or JSON string) and OAuth2 refresh tokens.
Provides hierarchical folder structure creation/reuse:
  CPASS / State / Training Centre / Batch / Candidate ID - Candidate Name / [Appointment Letter | Salary Slips | Bank Statements]

Never makes documents public. Provides authorized streaming/download and controlled replacement.
"""

from __future__ import annotations

import io
import json
import logging
import re
from pathlib import Path
from typing import Any

from googleapiclient.discovery import build, Resource
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from ..config import settings

logger = logging.getLogger("cpass.google_drive")

SCOPES = ["https://www.googleapis.com/auth/drive"]

SUBFOLDER_MAP = {
    "APPOINTMENT_LETTER": "Appointment Letter",
    "SALARY_SLIP": "Salary Slips",
    "BANK_STATEMENT": "Bank Statements",
}

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/jpg",
}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def _clean_folder_id(val: str | None) -> str | None:
    """Extract clean folder ID if a full Google Drive URL is passed."""
    if not val:
        return None
    val = val.strip()
    match = re.search(r"folders/([a-zA-Z0-9_-]+)", val)
    if match:
        return match.group(1)
    if "?" in val:
        val = val.split("?")[0]
    return val.strip() or None


def _resolve_file_path(file_path: str | None) -> str | None:
    """Resolve file path whether relative to CWD or backend directory."""
    if not file_path:
        return None
    p = Path(file_path)
    if p.is_file():
        return str(p.resolve())
    backend_p = Path(__file__).resolve().parent.parent.parent / file_path
    if backend_p.is_file():
        return str(backend_p.resolve())
    return file_path


class GoogleDriveError(Exception):
    """Base exception for Google Drive operations."""
    pass


class GoogleDriveNotConfiguredError(GoogleDriveError):
    """Raised when Google Drive credentials have not been configured."""
    pass


class GoogleDriveUploadError(GoogleDriveError):
    """Raised when an upload to Google Drive fails."""
    pass


class GoogleDriveService:
    def __init__(
        self,
        service_account_file: str | None = None,
        service_account_json: str | None = None,
        root_folder_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        refresh_token: str | None = None,
        custom_client: Any = None,
    ):
        raw_sa = service_account_file or settings.google_service_account_file
        self.service_account_file = _resolve_file_path(raw_sa)
        self.service_account_json = service_account_json or settings.google_service_account_json
        raw_root = root_folder_id or settings.google_drive_folder_id
        self.root_folder_id = _clean_folder_id(raw_root)
        self.client_id = client_id or settings.google_client_id
        self.client_secret = client_secret or settings.google_client_secret
        self.refresh_token = refresh_token or settings.google_refresh_token
        self._custom_client = custom_client
        self._service: Resource | None = None

    def is_configured(self) -> bool:
        """Check whether Google Drive authentication credentials are configured."""
        if self._custom_client is not None:
            return True
        resolved_sa = _resolve_file_path(self.service_account_file)
        if resolved_sa and Path(resolved_sa).is_file():
            return True
        if self.service_account_json and self.service_account_json.strip():
            return True
        if self.client_id and self.client_secret and self.refresh_token:
            return True
        return False

    def get_service(self) -> Resource:
        """Initialize or return the cached Google Drive v3 Resource."""
        if self._custom_client is not None:
            return self._custom_client
        if self._service is not None:
            return self._service

        if not self.is_configured():
            raise GoogleDriveNotConfiguredError(
                "Google Drive integration is not configured. Set GOOGLE_SERVICE_ACCOUNT_FILE, "
                "GOOGLE_SERVICE_ACCOUNT_JSON, or OAuth2 credentials (GOOGLE_CLIENT_ID, "
                "GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN) in backend/.env."
            )

        # Prefer OAuth2 so uploads use the authenticated personal Google account.
        if self.client_id and self.client_secret and self.refresh_token:
            creds = Credentials(
                None,
                refresh_token=self.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.client_id,
                client_secret=self.client_secret,
                scopes=SCOPES,
                )
            creds.refresh(Request())

        # Fall back to a service account only when OAuth2 is not configured.
        else:
            resolved_sa = _resolve_file_path(self.service_account_file)

            if resolved_sa and Path(resolved_sa).is_file():
                creds = service_account.Credentials.from_service_account_file(
                    resolved_sa, scopes=SCOPES
                )
            elif self.service_account_json:
                sa_info = json.loads(self.service_account_json)
                creds = service_account.Credentials.from_service_account_info(
                    sa_info, scopes=SCOPES
                )

        if creds is None:
            raise GoogleDriveNotConfiguredError(
                "Google Drive credentials are not configured."
            )

        self._service = build(
            "drive",
            "v3",
            credentials=creds,
            cache_discovery=False,
        )
        return self._service

    def get_or_create_folder(self, folder_name: str, parent_id: str | None = None) -> str:
        """Find an existing folder by name under parent_id, or create it if not found."""
        service = self.get_service()
        clean_name = folder_name.replace("'", "\\'").strip() or "Unnamed"

        q_parts = [
            f"name = '{clean_name}'",
            "mimeType = 'application/vnd.google-apps.folder'",
            "trashed = false",
        ]
        if parent_id:
            q_parts.append(f"'{parent_id}' in parents")

        query = " and ".join(q_parts)
        response = (
            service.files()
            .list(q=query, spaces="drive", fields="files(id, name)", pageSize=1)
            .execute()
        )
        files = response.get("files", [])
        if files:
            return files[0]["id"]

        body: dict[str, Any] = {
            "name": folder_name.strip() or "Unnamed",
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            body["parents"] = [parent_id]

        folder = service.files().create(body=body, fields="id").execute()
        return folder["id"]

    def get_or_create_candidate_subfolder(
        self,
        state: str,
        tc_name: str,
        batch_code: str,
        candidate_id: int | str,
        candidate_name: str,
        doc_type: str,
    ) -> tuple[str, str]:
        """Traverse or create the full folder hierarchy:
        CPASS / State / Training Centre / Batch / Candidate ID - Candidate Name / [Subfolder]

        Returns (folder_id, folder_path).
        """
        subfolder_title = SUBFOLDER_MAP.get(doc_type, "General Documents")
        cand_folder_title = f"{candidate_id} - {candidate_name.strip()}"

        root_id = self.root_folder_id
        path_segments = []

        # If root folder ID is specified, create under root. Otherwise create top-level 'CPASS'
        if not root_id:
            cpass_id = self.get_or_create_folder("CPASS", None)
            root_id = cpass_id
            path_segments.append("CPASS")
        else:
            path_segments.append("CPASS")

        # 1. State
        state_name = state.strip() or "Unknown State"
        state_id = self.get_or_create_folder(state_name, root_id)
        path_segments.append(state_name)

        # 2. Training Centre
        tc_clean = tc_name.strip() or "Unknown Centre"
        tc_id = self.get_or_create_folder(tc_clean, state_id)
        path_segments.append(tc_clean)

        # 3. Batch
        batch_clean = batch_code.strip() or "Unknown Batch"
        batch_id = self.get_or_create_folder(batch_clean, tc_id)
        path_segments.append(batch_clean)

        # 4. Candidate
        cand_id = self.get_or_create_folder(cand_folder_title, batch_id)
        path_segments.append(cand_folder_title)

        # 5. Document Type Subfolder
        final_folder_id = self.get_or_create_folder(subfolder_title, cand_id)
        path_segments.append(subfolder_title)

        folder_path = " / ".join(path_segments)
        return final_folder_id, folder_path

    def upload_file(
        self,
        content_bytes: bytes,
        file_name: str,
        mime_type: str,
        destination_folder_id: str,
    ) -> dict[str, Any]:
        """Upload a file to Google Drive under destination_folder_id.

        Returns metadata dict with id, name, mimeType, size.
        """
        service = self.get_service()

        if mime_type not in ALLOWED_MIME_TYPES:
            raise ValueError(
                f"File type '{mime_type}' is not supported. Allowed formats: PDF, PNG, JPG/JPEG."
            )

        if len(content_bytes) > MAX_FILE_SIZE_BYTES:
            max_mb = MAX_FILE_SIZE_BYTES // (1024 * 1024)
            raise ValueError(f"File size exceeds maximum allowed limit of {max_mb} MB.")

        media = MediaIoBaseUpload(
            io.BytesIO(content_bytes), mimetype=mime_type, resumable=True
        )
        file_metadata = {
            "name": file_name,
            "parents": [destination_folder_id],
        }

        try:
            drive_file = (
                service.files()
                .create(
                    body=file_metadata,
                    media_body=media,
                    fields="id, name, mimeType, size",
                )
                .execute()
            )
        except Exception as e:
            logger.error("Failed to upload file to Google Drive: %s", e)
            raise GoogleDriveUploadError(f"Google Drive upload failed: {e}") from e

        return {
            "file_id": drive_file["id"],
            "file_name": drive_file.get("name", file_name),
            "mime_type": drive_file.get("mimeType", mime_type),
            "size": int(drive_file.get("size", len(content_bytes))),
        }

    def download_file(self, file_id: str) -> tuple[bytes, str, str]:
        """Download file content from Google Drive for authorized streaming.

        Returns (file_bytes, file_name, mime_type).
        """
        service = self.get_service()

        # Get metadata
        meta = service.files().get(fileId=file_id, fields="name, mimeType").execute()
        file_name = meta.get("name", "document")
        mime_type = meta.get("mimeType", "application/octet-stream")

        # Download media
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        fh.seek(0)
        return fh.read(), file_name, mime_type

    def delete_file(self, file_id: str) -> bool:
        """Permanently delete or trash a file from Google Drive."""
        service = self.get_service()
        try:
            service.files().delete(fileId=file_id).execute()
            return True
        except Exception as e:
            logger.warning("Failed to delete file %s from Google Drive: %s", file_id, e)
            return False


# Default singleton instance
google_drive_service = GoogleDriveService()
