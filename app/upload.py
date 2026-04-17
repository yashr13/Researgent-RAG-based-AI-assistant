import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile

from app.auth import CurrentUser, require_user
from app.db import add_document, delete_document
from app.ingestion import ingest_file
from app.storage import delete_stored_file, store_upload
from app.vectorstore import delete_document_chunks


router = APIRouter()


@router.post("/")
async def upload_file(
    file: UploadFile,
    project_id: str = Form(...),
    user: CurrentUser = Depends(require_user),
):
    project_key = project_id.strip()
    if not project_key:
        raise HTTPException(status_code=400, detail="Project ID is required.")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Please choose a file to upload.")

    filename = file.filename
    suffix = Path(filename).suffix
    temp_path = None
    stored = None
    document = None

    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        stored = store_upload(
            project_key,
            filename,
            content,
            content_type=file.content_type,
        )
        document = add_document(
            user.id,
            project_key,
            filename,
            stored["filepath"],
            storage_url=stored.get("storage_url"),
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name

        ingest_file(temp_path, project_key, document_id=document["id"], owner_id=user.id)
        return {"status": "success", "filename": filename, "document": document}
    except HTTPException:
        if document:
            delete_document_chunks(document["id"])
            delete_document(user.id, document["id"])
        if stored:
            delete_stored_file(stored.get("filepath"))
        raise
    except Exception as exc:
        if document:
            delete_document_chunks(document["id"])
            delete_document(user.id, document["id"])
        if stored:
            delete_stored_file(stored.get("filepath"))
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed while indexing '{filename}': {exc}",
        ) from exc
    finally:
        if temp_path:
            path = Path(temp_path)
            if path.exists():
                path.unlink()
        await file.close()
