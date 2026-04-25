from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app import arxiv, chats, documents, messages, projects, query, upload
from app.config import cors_origins
from app.db import init_db
from app.vectorstore import init_vector_store

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST_DIR = BASE_DIR / "frontend" / "dist"
FRONTEND_INDEX_FILE = FRONTEND_DIST_DIR / "index.html"
SPA_EXCLUDED_PATHS = {
    "upload",
    "query",
    "projects",
    "documents",
    "chats",
    "messages",
    "arxiv",
    "docs",
    "redoc",
    "openapi.json",
    "health",
}


app = FastAPI(title="Simple RAG Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()
    init_vector_store()


@app.get("/")
def read_root():
    if FRONTEND_INDEX_FILE.exists():
        return FileResponse(FRONTEND_INDEX_FILE)
    return {
        "message": "Simple RAG Assistant API is running.",
        "docs": "/docs",
        "frontend_dev_server": "http://localhost:5173",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(upload.router, prefix="/upload", tags=["upload"])
app.include_router(query.router, prefix="/query", tags=["query"])
app.include_router(projects.router, prefix="/projects", tags=["projects"])
app.include_router(documents.router, prefix="/documents", tags=["documents"])
app.include_router(chats.router, prefix="/chats", tags=["chats"])
app.include_router(messages.router, prefix="/messages", tags=["messages"])
app.include_router(arxiv.router, prefix="/arxiv", tags=["arxiv"])


@app.get("/{full_path:path}", include_in_schema=False)
def serve_frontend(full_path: str):
    if not FRONTEND_INDEX_FILE.exists():
        raise HTTPException(status_code=404, detail="Not Found")

    first_segment = full_path.split("/", 1)[0]
    if first_segment in SPA_EXCLUDED_PATHS:
        raise HTTPException(status_code=404, detail="Not Found")

    requested_path = (FRONTEND_DIST_DIR / full_path).resolve()
    try:
        requested_path.relative_to(FRONTEND_DIST_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Not Found") from exc

    if requested_path.is_file():
        return FileResponse(requested_path)

    return FileResponse(FRONTEND_INDEX_FILE)
