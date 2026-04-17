import json
import logging
import hashlib
from contextlib import closing

import chromadb
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

from app.config import (
    chroma_db_path,
    embedding_dimensions,
    pgvector_init_on_startup,
    vector_backend,
)
from app.db import get_conn

logger = logging.getLogger(__name__)


def _embedding_suffix(embeddings):
    if embeddings is None:
        return "default"

    class_name = embeddings.__class__.__name__.lower()
    if "openai" in class_name:
        return "openai"

    dimensions = getattr(embeddings, "dimensions", None)
    if dimensions:
        return f"local_{dimensions}"

    return class_name


def _vector_literal(values):
    return "[" + ",".join(f"{float(value):.8f}" for value in values) + "]"


def _scoped_project_key(project_id: str, owner_id: str | None = None):
    if not owner_id:
        return project_id
    return f"{owner_id}:{project_id}"


def _collection_name(project_id: str, embeddings=None, owner_id: str | None = None):
    scoped = _scoped_project_key(project_id, owner_id)
    digest = hashlib.sha1(scoped.encode("utf-8")).hexdigest()[:16]
    return f"project_{digest}_{_embedding_suffix(embeddings)}"


def _document_from_row(row):
    metadata = json.loads(row.get("metadata_json") or "{}")
    metadata.setdefault("project_id", row.get("project_key"))
    metadata.setdefault("document_id", row.get("document_id"))
    metadata.setdefault("source", row.get("source"))
    metadata.setdefault("filename", row.get("filename"))
    metadata.setdefault("page", row.get("page"))
    metadata.setdefault("section_title", row.get("section_title"))
    return Document(page_content=row.get("content") or "", metadata=metadata)


def get_vectorstore(project_id: str, embeddings=None, owner_id: str | None = None):
    return Chroma(
        collection_name=_collection_name(project_id, embeddings, owner_id),
        persist_directory=chroma_db_path(),
        embedding_function=embeddings,
    )


def init_vector_store():
    if vector_backend() != "pgvector":
        return
    if not pgvector_init_on_startup():
        logger.info("Skipping pgvector schema initialization on startup.")
        return

    with closing(get_conn()) as conn:
        conn.execute("SET statement_timeout = 0;")
        conn.execute("CREATE SCHEMA IF NOT EXISTS extensions;")
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;")
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id BIGSERIAL PRIMARY KEY,
                project_key TEXT NOT NULL,
                document_id BIGINT,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                source TEXT,
                filename TEXT,
                page INTEGER,
                section_title TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{{}}',
                embedding extensions.vector({embedding_dimensions()}) NOT NULL
            );
            """
        )
        try:
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_document_chunks_project_key
                ON document_chunks(project_key);
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id
                ON document_chunks(document_id);
                """
            )
        except Exception as exc:
            logger.warning(
                "Skipping pgvector metadata index creation during startup: %s",
                exc,
            )
        conn.commit()


def add_documents(project_id: str, document_id: int | None, docs, embeddings, owner_id: str | None = None):
    scoped_project = _scoped_project_key(project_id, owner_id)
    if vector_backend() != "pgvector":
        vectordb = get_vectorstore(project_id, embeddings, owner_id)
        hydrated = []
        for doc in docs:
            metadata = dict(doc.metadata or {})
            metadata["project_id"] = project_id
            metadata["owner_id"] = owner_id
            if document_id is not None:
                metadata["document_id"] = document_id
            hydrated.append(Document(page_content=doc.page_content, metadata=metadata))
        vectordb.add_documents(hydrated)
        return

    texts = [doc.page_content for doc in docs]
    if not texts:
        return

    vectors = embeddings.embed_documents(texts)
    with closing(get_conn()) as conn:
        for index, (doc, vector) in enumerate(zip(docs, vectors)):
            metadata = dict(doc.metadata or {})
            metadata["project_id"] = project_id
            metadata["owner_id"] = owner_id
            if document_id is not None:
                metadata["document_id"] = document_id
            conn.execute(
                """
                INSERT INTO document_chunks (
                    project_key, document_id, chunk_index, content, source, filename,
                    page, section_title, metadata_json, embedding
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CAST(%s AS extensions.vector))
                """,
                (
                    scoped_project,
                    document_id,
                    index,
                    doc.page_content,
                    metadata.get("source"),
                    metadata.get("filename"),
                    metadata.get("page"),
                    metadata.get("section_title"),
                    json.dumps(metadata),
                    _vector_literal(vector),
                ),
            )
        conn.commit()


def similarity_search(project_id: str, query: str, limit: int, embeddings, owner_id: str | None = None):
    scoped_project = _scoped_project_key(project_id, owner_id)
    if vector_backend() != "pgvector":
        vectordb = get_vectorstore(project_id, embeddings, owner_id)
        return vectordb.similarity_search(query, k=limit)

    query_vector = embeddings.embed_query(query)
    with closing(get_conn()) as conn:
        rows = conn.execute(
            """
            SELECT project_key, document_id, content, source, filename, page, section_title, metadata_json
            FROM document_chunks
            WHERE project_key = %s
            ORDER BY embedding <=> CAST(%s AS extensions.vector)
            LIMIT %s
            """,
            (scoped_project, _vector_literal(query_vector), limit),
        ).fetchall()
    return [_document_from_row(dict(row) if not isinstance(row, dict) else row) for row in rows]


def get_project_documents(project_id: str, embeddings=None, owner_id: str | None = None):
    scoped_project = _scoped_project_key(project_id, owner_id)
    if vector_backend() != "pgvector":
        vectordb = get_vectorstore(project_id, embeddings, owner_id)
        payload = vectordb.get(include=["documents", "metadatas"])
        documents = payload.get("documents") or []
        metadatas = payload.get("metadatas") or []

        result = []
        for index, text in enumerate(documents):
            metadata = metadatas[index] if index < len(metadatas) else {}
            result.append(Document(page_content=text, metadata=metadata or {}))
        return result

    with closing(get_conn()) as conn:
        rows = conn.execute(
            """
            SELECT project_key, document_id, content, source, filename, page, section_title, metadata_json
            FROM document_chunks
            WHERE project_key = %s
            ORDER BY document_id NULLS LAST, chunk_index ASC
            """,
            (scoped_project,),
        ).fetchall()
    return [_document_from_row(dict(row) if not isinstance(row, dict) else row) for row in rows]


def delete_document_chunks(document_id: int):
    if vector_backend() != "pgvector":
        client = chromadb.PersistentClient(path=chroma_db_path())
        for collection in client.list_collections():
            collection.delete(where={"document_id": document_id})
        return

    with closing(get_conn()) as conn:
        conn.execute("DELETE FROM document_chunks WHERE document_id = %s", (document_id,))
        conn.commit()


def delete_project_collections(project_id: str, owner_id: str | None = None):
    scoped_project = _scoped_project_key(project_id, owner_id)
    if vector_backend() != "pgvector":
        client = chromadb.PersistentClient(path=chroma_db_path())
        prefix = f"project_{hashlib.sha1(scoped_project.encode('utf-8')).hexdigest()[:16]}_"
        deleted = []

        for collection in client.list_collections():
            name = collection.name
            if name.startswith(prefix):
                client.delete_collection(name)
                deleted.append(name)

        return deleted

    with closing(get_conn()) as conn:
        conn.execute("DELETE FROM document_chunks WHERE project_key = %s", (scoped_project,))
        conn.commit()
    return [f"pgvector:{scoped_project}"]
