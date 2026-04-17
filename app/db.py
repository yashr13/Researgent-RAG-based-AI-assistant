import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from app.config import (
    database_backend,
    database_connect_timeout,
    database_url,
    sqlite_db_path,
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _is_postgres():
    return database_backend() == "postgres"


def _param(sqlite_sql: str, postgres_sql: str):
    return postgres_sql if _is_postgres() else sqlite_sql


def get_conn():
    if _is_postgres():
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "DATABASE_URL is configured for Postgres, but psycopg is not installed."
            ) from exc

        return psycopg.connect(
            database_url(),
            row_factory=dict_row,
            prepare_threshold=None,
            connect_timeout=database_connect_timeout(),
        )

    conn = sqlite3.connect(sqlite_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with closing(get_conn()) as conn:
        if _is_postgres():
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id BIGSERIAL PRIMARY KEY,
                    user_id TEXT,
                    project_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, project_key)
                );

                CREATE TABLE IF NOT EXISTS documents (
                    id BIGSERIAL PRIMARY KEY,
                    project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    filename TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    uploaded_at TEXT NOT NULL,
                    source_type TEXT NOT NULL DEFAULT 'local',
                    external_id TEXT,
                    title TEXT,
                    authors_json TEXT NOT NULL DEFAULT '[]',
                    abstract TEXT,
                    url TEXT,
                    published_at TEXT,
                    storage_url TEXT
                );

                CREATE TABLE IF NOT EXISTS chats (
                    id BIGSERIAL PRIMARY KEY,
                    project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    title TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id BIGSERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    sources_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
                """
            )
            _ensure_postgres_columns(conn)
        else:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_key TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    filename TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    uploaded_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    title TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    sources_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
                );
                """
            )
            _ensure_sqlite_columns(conn)

        conn.commit()


def _ensure_postgres_columns(conn):
    conn.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS user_id TEXT;")
    conn.execute("ALTER TABLE projects DROP CONSTRAINT IF EXISTS projects_project_key_key;")
    conn.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT 'local';")
    conn.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS external_id TEXT;")
    conn.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS title TEXT;")
    conn.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS authors_json TEXT NOT NULL DEFAULT '[]';")
    conn.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS abstract TEXT;")
    conn.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS url TEXT;")
    conn.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS published_at TEXT;")
    conn.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS storage_url TEXT;")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_projects_user_id
        ON projects(user_id);
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_user_project_key
        ON projects(user_id, project_key);
        """
    )


def _ensure_sqlite_columns(conn):
    project_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(projects)").fetchall()
    }
    if "user_id" not in project_columns:
        conn.execute("ALTER TABLE projects ADD COLUMN user_id TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id)")

    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(documents)").fetchall()
    }
    columns = {
        "source_type": "TEXT NOT NULL DEFAULT 'local'",
        "external_id": "TEXT",
        "title": "TEXT",
        "authors_json": "TEXT NOT NULL DEFAULT '[]'",
        "abstract": "TEXT",
        "url": "TEXT",
        "published_at": "TEXT",
        "storage_url": "TEXT",
    }

    for column, definition in columns.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE documents ADD COLUMN {column} {definition}")


def _normalize_row(row):
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


def get_or_create_project(user_id: str, project_key: str):
    with closing(get_conn()) as conn:
        row = _normalize_row(
            conn.execute(
                _param(
                    "SELECT id, user_id, project_key, created_at FROM projects WHERE user_id = ? AND project_key = ?",
                    "SELECT id, user_id, project_key, created_at FROM projects WHERE user_id = %s AND project_key = %s",
                ),
                (user_id, project_key),
            ).fetchone()
        )
        if row:
            return row

        created_at = _now()
        if _is_postgres():
            row = _normalize_row(
                conn.execute(
                    """
                    INSERT INTO projects (user_id, project_key, created_at)
                    VALUES (%s, %s, %s)
                    RETURNING id, user_id, project_key, created_at
                    """,
                    (user_id, project_key, created_at),
                ).fetchone()
            )
        else:
            cursor = conn.execute(
                "INSERT INTO projects (user_id, project_key, created_at) VALUES (?, ?, ?)",
                (user_id, project_key, created_at),
            )
            row = {
                "id": cursor.lastrowid,
                "user_id": user_id,
                "project_key": project_key,
                "created_at": created_at,
            }
        conn.commit()
        return row


def get_project(user_id: str, project_key: str):
    with closing(get_conn()) as conn:
        row = conn.execute(
            _param(
                "SELECT id, user_id, project_key, created_at FROM projects WHERE user_id = ? AND project_key = ?",
                "SELECT id, user_id, project_key, created_at FROM projects WHERE user_id = %s AND project_key = %s",
            ),
            (user_id, project_key),
        ).fetchone()
        return _normalize_row(row)


def list_projects(user_id: str):
    with closing(get_conn()) as conn:
        rows = conn.execute(
            _param(
                """
                SELECT p.id, p.user_id, p.project_key, p.created_at,
                       COUNT(DISTINCT d.id) AS document_count,
                       COUNT(DISTINCT c.id) AS chat_count
                FROM projects p
                LEFT JOIN documents d ON d.project_id = p.id
                LEFT JOIN chats c ON c.project_id = p.id
                WHERE p.user_id = ?
                GROUP BY p.id
                ORDER BY p.created_at DESC
                """,
                """
                SELECT p.id, p.user_id, p.project_key, p.created_at,
                       COUNT(DISTINCT d.id) AS document_count,
                       COUNT(DISTINCT c.id) AS chat_count
                FROM projects p
                LEFT JOIN documents d ON d.project_id = p.id
                LEFT JOIN chats c ON c.project_id = p.id
                WHERE p.user_id = %s
                GROUP BY p.id
                ORDER BY p.created_at DESC
                """,
            ),
            (user_id,),
        ).fetchall()
        return [_normalize_row(row) for row in rows]


def add_document(
    user_id: str,
    project_key: str,
    filename: str,
    filepath: str,
    source_type: str = "local",
    external_id: str | None = None,
    title: str | None = None,
    authors=None,
    abstract: str | None = None,
    url: str | None = None,
    published_at: str | None = None,
    storage_url: str | None = None,
):
    project = get_or_create_project(user_id, project_key)
    uploaded_at = _now()
    authors_payload = json.dumps(authors or [])
    with closing(get_conn()) as conn:
        if _is_postgres():
            row = _normalize_row(
                conn.execute(
                    """
                    INSERT INTO documents (
                        project_id, filename, filepath, uploaded_at, source_type,
                        external_id, title, authors_json, abstract, url, published_at, storage_url
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        project["id"],
                        filename,
                        filepath,
                        uploaded_at,
                        source_type,
                        external_id,
                        title,
                        authors_payload,
                        abstract,
                        url,
                        published_at,
                        storage_url,
                    ),
                ).fetchone()
            )
            document_id = row["id"]
        else:
            cursor = conn.execute(
                """
                INSERT INTO documents (
                    project_id, filename, filepath, uploaded_at, source_type,
                    external_id, title, authors_json, abstract, url, published_at, storage_url
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project["id"],
                    filename,
                    filepath,
                    uploaded_at,
                    source_type,
                    external_id,
                    title,
                    authors_payload,
                    abstract,
                    url,
                    published_at,
                    storage_url,
                ),
            )
            document_id = cursor.lastrowid

        conn.commit()
        return {
            "id": document_id,
            "project_id": project["id"],
            "filename": filename,
            "filepath": filepath,
            "uploaded_at": uploaded_at,
            "source_type": source_type,
            "external_id": external_id,
            "title": title,
            "authors": authors or [],
            "abstract": abstract,
            "url": url,
            "published_at": published_at,
            "storage_url": storage_url,
        }


def list_documents(user_id: str, project_key: str):
    project = get_project(user_id, project_key)
    if not project:
        return []
    with closing(get_conn()) as conn:
        rows = conn.execute(
            _param(
                """
                SELECT id, filename, filepath, uploaded_at, source_type, external_id,
                       title, authors_json, abstract, url, published_at, storage_url
                FROM documents
                WHERE project_id = ?
                ORDER BY uploaded_at DESC
                """,
                """
                SELECT id, filename, filepath, uploaded_at, source_type, external_id,
                       title, authors_json, abstract, url, published_at, storage_url
                FROM documents
                WHERE project_id = %s
                ORDER BY uploaded_at DESC
                """,
            ),
            (project["id"],),
        ).fetchall()
        documents = []
        for row in rows:
            item = _normalize_row(row)
            item["authors"] = json.loads(item.pop("authors_json") or "[]")
            documents.append(item)
        return documents


def get_document(user_id: str, document_id: int):
    with closing(get_conn()) as conn:
        row = conn.execute(
            _param(
                """
                SELECT d.id, d.project_id, d.filename, d.filepath, d.uploaded_at,
                       d.source_type, d.external_id, d.title, d.authors_json,
                       d.abstract, d.url, d.published_at, d.storage_url, p.project_key
                FROM documents d
                JOIN projects p ON p.id = d.project_id
                WHERE d.id = ? AND p.user_id = ?
                """,
                """
                SELECT d.id, d.project_id, d.filename, d.filepath, d.uploaded_at,
                       d.source_type, d.external_id, d.title, d.authors_json,
                       d.abstract, d.url, d.published_at, d.storage_url, p.project_key
                FROM documents d
                JOIN projects p ON p.id = d.project_id
                WHERE d.id = %s AND p.user_id = %s
                """,
            ),
            (document_id, user_id),
        ).fetchone()
        if not row:
            return None

        item = _normalize_row(row)
        item["authors"] = json.loads(item.pop("authors_json") or "[]")
        return item


def delete_document(user_id: str, document_id: int):
    document = get_document(user_id, document_id)
    if not document:
        return None

    with closing(get_conn()) as conn:
        conn.execute(
            _param(
                "DELETE FROM documents WHERE id = ?",
                "DELETE FROM documents WHERE id = %s",
            ),
            (document_id,),
        )
        conn.commit()
    return document


def delete_project(user_id: str, project_key: str):
    project = get_project(user_id, project_key)
    if not project:
        return None

    documents = list_documents(user_id, project_key)
    with closing(get_conn()) as conn:
        conn.execute(
            _param(
                "DELETE FROM projects WHERE id = ?",
                "DELETE FROM projects WHERE id = %s",
            ),
            (project["id"],),
        )
        conn.commit()

    project["documents"] = documents
    return project


def create_chat(user_id: str, project_key: str, title: str):
    project = get_or_create_project(user_id, project_key)
    created_at = _now()
    with closing(get_conn()) as conn:
        if _is_postgres():
            row = _normalize_row(
                conn.execute(
                    """
                    INSERT INTO chats (project_id, title, created_at)
                    VALUES (%s, %s, %s)
                    RETURNING id
                    """,
                    (project["id"], title, created_at),
                ).fetchone()
            )
            chat_id = row["id"]
        else:
            cursor = conn.execute(
                """
                INSERT INTO chats (project_id, title, created_at)
                VALUES (?, ?, ?)
                """,
                (project["id"], title, created_at),
            )
            chat_id = cursor.lastrowid
        conn.commit()
        return {
            "id": chat_id,
            "project_id": project["id"],
            "title": title,
            "created_at": created_at,
        }


def get_chat(user_id: str, chat_id: int):
    with closing(get_conn()) as conn:
        row = conn.execute(
            _param(
                """
                SELECT c.id, c.project_id, c.title, c.created_at, p.project_key
                FROM chats c
                JOIN projects p ON p.id = c.project_id
                WHERE c.id = ? AND p.user_id = ?
                """,
                """
                SELECT c.id, c.project_id, c.title, c.created_at, p.project_key
                FROM chats c
                JOIN projects p ON p.id = c.project_id
                WHERE c.id = %s AND p.user_id = %s
                """,
            ),
            (chat_id, user_id),
        ).fetchone()
        return _normalize_row(row)


def list_chats(user_id: str, project_key: str):
    project = get_project(user_id, project_key)
    if not project:
        return []
    with closing(get_conn()) as conn:
        rows = conn.execute(
            _param(
                """
                SELECT id, title, created_at
                FROM chats
                WHERE project_id = ?
                ORDER BY created_at DESC
                """,
                """
                SELECT id, title, created_at
                FROM chats
                WHERE project_id = %s
                ORDER BY created_at DESC
                """,
            ),
            (project["id"],),
        ).fetchall()
        return [_normalize_row(row) for row in rows]


def add_message(user_id: str, chat_id: int, role: str, content: str, sources=None):
    if not get_chat(user_id, chat_id):
        return None

    created_at = _now()
    payload = json.dumps(sources or [])
    with closing(get_conn()) as conn:
        if _is_postgres():
            row = _normalize_row(
                conn.execute(
                    """
                    INSERT INTO messages (chat_id, role, content, sources_json, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (chat_id, role, content, payload, created_at),
                ).fetchone()
            )
            message_id = row["id"]
        else:
            cursor = conn.execute(
                """
                INSERT INTO messages (chat_id, role, content, sources_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (chat_id, role, content, payload, created_at),
            )
            message_id = cursor.lastrowid

        conn.commit()
        return {
            "id": message_id,
            "chat_id": chat_id,
            "role": role,
            "content": content,
            "sources": sources or [],
            "created_at": created_at,
        }


def list_messages(user_id: str, chat_id: int):
    if not get_chat(user_id, chat_id):
        return []

    with closing(get_conn()) as conn:
        rows = conn.execute(
            _param(
                """
                SELECT id, role, content, sources_json, created_at
                FROM messages
                WHERE chat_id = ?
                ORDER BY created_at ASC
                """,
                """
                SELECT id, role, content, sources_json, created_at
                FROM messages
                WHERE chat_id = %s
                ORDER BY created_at ASC
                """,
            ),
            (chat_id,),
        ).fetchall()

    messages = []
    for row in rows:
        item = _normalize_row(row)
        item["sources"] = json.loads(item.pop("sources_json") or "[]")
        messages.append(item)
    return messages


def get_recent_messages(user_id: str, chat_id: int, limit: int = 4):
    if not get_chat(user_id, chat_id):
        return []

    with closing(get_conn()) as conn:
        rows = conn.execute(
            _param(
                """
                SELECT role, content
                FROM messages
                WHERE chat_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                """
                SELECT role, content
                FROM messages
                WHERE chat_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
            ),
            (chat_id, limit),
        ).fetchall()

    return [_normalize_row(row) for row in reversed(rows)]
