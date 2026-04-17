from fastapi import APIRouter, Depends

from app.auth import CurrentUser, require_user
from app.db import delete_document, list_documents
from app.storage import delete_stored_file
from app.vectorstore import delete_document_chunks


router = APIRouter()


@router.get("/")
def get_documents(project_id: str, user: CurrentUser = Depends(require_user)):
    return {"documents": list_documents(user.id, project_id)}


@router.delete("/{document_id}")
def remove_document(document_id: int, user: CurrentUser = Depends(require_user)):
    document = delete_document(user.id, document_id)
    if document and document.get("source_type") == "local":
        delete_stored_file(document.get("filepath"))
    if document:
        delete_document_chunks(document_id)

    return {
        "status": "deleted" if document else "not_found",
        "document": document,
    }
