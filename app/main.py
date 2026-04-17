from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import arxiv, chats, documents, messages, projects, query, upload
from app.config import cors_origins
from app.db import init_db
from app.vectorstore import init_vector_store


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
