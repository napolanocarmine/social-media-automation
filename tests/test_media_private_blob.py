from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from social_automation.api.deps import get_db_path, get_settings
from social_automation.api.main import create_app
from social_automation.db.store import record_processed_artifacts, update_image_media_paths
from social_automation.models import MediaFormat, Platform
from social_automation.services.media import blob_url_requires_proxy, is_private_blob_url
from social_automation.settings import Settings


def test_private_blob_url_detection() -> None:
    url = "https://demo.private.blob.vercel-storage.com/processed/ig/1.jpg"
    assert is_private_blob_url(url) is True
    assert blob_url_requires_proxy(url) is True


def test_media_endpoint_streams_private_blob(tmp_path: Path) -> None:
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    dest = out_dir / "processed.jpg"
    dest.write_bytes(b"processed-bytes")
    db_path = tmp_path / "db.sqlite3"
    settings = Settings(
        db_path=db_path,
        output_dir=out_dir,
        storage_backend="vercel_blob",
        blob_read_write_token="vercel_blob_rw_store_test_secret",
    )
    image_id = record_processed_artifacts(
        db_path,
        image_name="test.jpg",
        image_path=dest,
        metadata_payload={
            "platform": Platform.INSTAGRAM.value,
            "media_format": MediaFormat.POST.value,
        },
    )
    private_url = "https://demo.private.blob.vercel-storage.com/processed/instagram/5.jpg"
    update_image_media_paths(db_path, image_id=image_id, path=private_url)

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_path] = lambda: db_path
    client = TestClient(app)

    mock_storage = MagicMock()
    mock_storage.download.return_value = b"jpeg-bytes"

    with patch("social_automation.services.media.get_storage", return_value=mock_storage):
        response = client.get(f"/api/v1/media/images/{image_id}/processed")

    assert response.status_code == 200
    assert response.content == b"jpeg-bytes"
    assert response.headers["content-type"].startswith("image/")
    mock_storage.download.assert_called_once_with(private_url)
