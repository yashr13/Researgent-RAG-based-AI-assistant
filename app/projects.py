from fastapi import APIRouter, Depends

from app.auth import CurrentUser, require_user
from app.db import delete_project, list_projects
from app.storage import delete_stored_file
from app.vectorstore import delete_project_collections


router = APIRouter()


@router.get("/")
def get_projects(user: CurrentUser = Depends(require_user)):
    return {"projects": list_projects(user.id)}


@router.delete("/{project_id}")
def remove_project(project_id: str, user: CurrentUser = Depends(require_user)):
    project = delete_project(user.id, project_id)
    if project:
        for document in project.get("documents", []):
            if document.get("source_type") == "local":
                delete_stored_file(document.get("filepath"))
    deleted_collections = delete_project_collections(project_id, owner_id=user.id)
    return {
        "status": "deleted" if project else "not_found",
        "project": project,
        "deleted_collections": deleted_collections,
    }
