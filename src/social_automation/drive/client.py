"""Client Google Drive: elenco e download file immagine da una cartella."""

from __future__ import annotations

import re
from collections import deque
from io import BytesIO
from pathlib import Path
from typing import Any

from googleapiclient.http import MediaIoBaseDownload

from social_automation.drive.auth import build_drive_service
from social_automation.models import DriveAsset

_IMAGE_MIME_PREFIX = "image/"


class DriveClient:
    """Drive API v3: solo lettura (scope drive.readonly)."""

    def __init__(self, service: Any) -> None:
        self._service = service

    @classmethod
    def from_paths(
        cls,
        credentials_path: Path,
        token_path: Path,
        *,
        open_browser: bool = True,
        oauth_browser: str | None = None,
    ) -> DriveClient:
        service = build_drive_service(
            credentials_path,
            token_path,
            open_browser=open_browser,
            oauth_browser=oauth_browser,
        )
        return cls(service)

    @classmethod
    def from_settings(cls, settings) -> DriveClient:
        creds_json = (getattr(settings, "google_credentials_json", "") or "").strip()
        refresh = (getattr(settings, "google_refresh_token", "") or "").strip()
        if creds_json and refresh:
            service = build_drive_service(
                settings.google_credentials_path,
                settings.google_token_path,
                open_browser=False,
                credentials_json=creds_json,
                refresh_token=refresh,
            )
            return cls(service)
        oauth_browser = (settings.google_oauth_browser or "").strip() or None
        return cls.from_paths(
            settings.google_credentials_path,
            settings.google_token_path,
            open_browser=True,
            oauth_browser=oauth_browser,
        )

    def list_images_in_folder(
        self,
        folder_id: str,
        *,
        category: str | None = None,
        page_size: int = 100,
    ) -> list[DriveAsset]:
        """Elenca file con mime image/* direttamente nella cartella (non ricorsivo)."""
        q = (
            f"'{folder_id}' in parents and trashed = false "
            f"and mimeType contains '{_IMAGE_MIME_PREFIX}'"
        )
        assets: list[DriveAsset] = []
        page_token: str | None = None
        while True:
            resp = (
                self._service.files()
                .list(
                    q=q,
                    spaces="drive",
                    fields="nextPageToken, files(id, name, mimeType)",
                    pageSize=page_size,
                    pageToken=page_token,
                    orderBy="name",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            for f in resp.get("files", []):
                assets.append(
                    DriveAsset(
                        file_id=f["id"],
                        name=f.get("name", ""),
                        mime_type=f.get("mimeType", ""),
                        category=category,
                        path_segments=[],
                    )
                )
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return assets

    def list_images_recursively(
        self,
        root_folder_id: str,
        *,
        category_names: set[str] | None = None,
        page_size: int = 100,
    ) -> list[DriveAsset]:
        """Elenca tutte le immagini sotto root_folder_id (scansione ricorsiva)."""
        normalized_categories = {c.strip().lower() for c in category_names or set() if c.strip()}
        queue: deque[tuple[str, list[str]]] = deque([(root_folder_id, [])])
        assets: list[DriveAsset] = []

        while queue:
            folder_id, segments = queue.popleft()
            for item in self._list_children(folder_id, page_size=page_size):
                mime = item.get("mimeType", "")
                name = item.get("name", "")
                item_id = item.get("id", "")
                if not item_id:
                    continue
                if mime == "application/vnd.google-apps.folder":
                    queue.append((item_id, [*segments, name]))
                    continue
                if not mime.startswith(_IMAGE_MIME_PREFIX):
                    continue
                category = self._infer_category(segments, normalized_categories)
                assets.append(
                    DriveAsset(
                        file_id=item_id,
                        name=name,
                        mime_type=mime,
                        category=category,
                        path_segments=segments.copy(),
                    )
                )
        return assets

    def _list_children(self, folder_id: str, *, page_size: int) -> list[dict[str, str]]:
        q = f"'{folder_id}' in parents and trashed = false"
        children: list[dict[str, str]] = []
        page_token: str | None = None
        while True:
            resp = (
                self._service.files()
                .list(
                    q=q,
                    spaces="drive",
                    fields="nextPageToken, files(id, name, mimeType)",
                    pageSize=page_size,
                    pageToken=page_token,
                    orderBy="name",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            children.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return children

    @staticmethod
    def _infer_category(path_segments: list[str], category_names: set[str]) -> str | None:
        if not category_names:
            return None
        for segment in reversed(path_segments):
            normalized = segment.strip().lower()
            if normalized in category_names:
                return normalized
            for cat in category_names:
                if re.search(rf"\b{re.escape(cat)}\b", normalized):
                    return cat
        return None

    def download_file_bytes(self, file_id: str) -> bytes:
        request = self._service.files().get_media(fileId=file_id)
        buf = BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _status, done = downloader.next_chunk()
        return buf.getvalue()
