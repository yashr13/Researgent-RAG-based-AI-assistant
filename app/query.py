from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import CurrentUser, require_user
from app.db import add_message, create_chat, get_chat, get_recent_messages
from app.rag_service import query_rag


router = APIRouter()


class QueryRequest(BaseModel):
    project_id: str
    question: str
    chat_id: int | None = None


@router.post("/")
def ask_query(req: QueryRequest, user: CurrentUser = Depends(require_user)):
    chat = None
    history = []
    if req.chat_id is None:
        chat = create_chat(user.id, req.project_id, req.question[:80])
        chat_id = chat["id"]
    else:
        if not get_chat(user.id, req.chat_id):
            raise HTTPException(status_code=404, detail="Chat not found.")
        chat_id = req.chat_id
        history = get_recent_messages(user.id, chat_id)

    add_message(user.id, chat_id, "user", req.question)
    result = query_rag(req.project_id, req.question, history, owner_id=user.id)
    answer = result.get("answer", "")
    sources = result.get("sources", [])
    add_message(user.id, chat_id, "assistant", answer, sources)

    payload = {"answer": answer, "sources": sources, "chat_id": chat_id}
    if chat:
        payload["chat"] = chat
    return payload
