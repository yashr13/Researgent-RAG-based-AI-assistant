import os
import urllib.parse
import urllib.request
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from app.config import (
    storage_backend,
    supabase_service_role_key,
    supabase_storage_bucket,
    supabase_storage_public,
    supabase_url,
    uploads_dir,
)


def _safe_filename(filename: str):
    name = Path(filename).name.replace(" ", "_")
    return f"{uuid4().hex[:12]}_{name}"


def _supabase_object_url(bucket: str, object_path: str):
    base_url = supabase_url().rstrip("/")
    encoded_path = "/".join(urllib.parse.quote(part) for part in object_path.split("/"))
    return f"{base_url}/storage/v1/object/{bucket}/{encoded_path}"


def store_upload(project_key: str, filename: str, content: bytes, content_type: str | None = None):
    object_name = _safe_filename(filename)
    object_path = f"{project_key}/{object_name}"

    if storage_backend() == "supabase":
        bucket = supabase_storage_bucket()
        token = supabase_service_role_key()
        base_url = supabase_url().rstrip("/")
        upload_url = _supabase_object_url(bucket, object_path)
        request = urllib.request.Request(
            upload_url,
            method="POST",
            data=content,
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": token,
                "Content-Type": content_type or "application/octet-stream",
                "x-upsert": "true",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30):
                pass
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Remote file upload failed: {exc}") from exc

        public_url = None
        if supabase_storage_public():
            encoded_path = "/".join(urllib.parse.quote(part) for part in object_path.split("/"))
            public_url = f"{base_url}/storage/v1/object/public/{bucket}/{encoded_path}"

        return {
            "filepath": object_path,
            "storage_url": public_url,
        }

    root = Path(uploads_dir())
    root.mkdir(parents=True, exist_ok=True)
    project_dir = root / project_key
    project_dir.mkdir(parents=True, exist_ok=True)
    target = project_dir / object_name
    target.write_bytes(content)
    return {
        "filepath": str(target),
        "storage_url": None,
    }


def delete_stored_file(filepath: str | None):
    if not filepath:
        return

    if storage_backend() == "supabase":
        bucket = supabase_storage_bucket()
        token = supabase_service_role_key()
        request = urllib.request.Request(
            _supabase_object_url(bucket, filepath),
            method="DELETE",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": token,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30):
                pass
        except Exception:
            # Deletion failure should not mask primary application flow.
            return
        return

    path = Path(filepath)
    if path.exists() and path.is_file():
        path.unlink()
