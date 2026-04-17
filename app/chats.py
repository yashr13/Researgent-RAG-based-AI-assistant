from fastapi import APIRouter, Depends

from app.auth import CurrentUser, require_user
from app.db import list_chats


router = APIRouter()


@router.get("/")
def get_chats(project_id: str, user: CurrentUser = Depends(require_user)):
    return {"chats": list_chats(user.id, project_id)}
