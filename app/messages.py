from fastapi import APIRouter, Depends

from app.auth import CurrentUser, require_user
from app.db import list_messages


router = APIRouter()


@router.get("/")
def get_messages(chat_id: int, user: CurrentUser = Depends(require_user)):
    return {"messages": list_messages(user.id, chat_id)}
