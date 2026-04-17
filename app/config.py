import os


def _normalized_env(name: str, default: str = ""):
    return (os.getenv(name) or default).strip()


def parse_bool(value: str | None, default: bool = False):
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def database_backend():
    database_url = _normalized_env("DATABASE_URL")
    if database_url.startswith(("postgres://", "postgresql://")):
        return "postgres"
    return "sqlite"


def sqlite_db_path():
    return _normalized_env("SQLITE_DB", "assistant.db")


def database_url():
    return _normalized_env("DATABASE_URL")


def storage_backend():
    configured = _normalized_env("STORAGE_BACKEND", "auto").lower()
    if configured != "auto":
        return configured

    if supabase_url() and supabase_service_role_key() and supabase_storage_bucket():
        return "supabase"
    return "local"


def vector_backend():
    configured = _normalized_env("VECTOR_BACKEND", "auto").lower()
    if configured != "auto":
        return configured

    if database_backend() == "postgres":
        return "pgvector"
    return "chroma"


def chroma_db_path():
    return _normalized_env("CHROMA_DB", "./chroma_db")


def uploads_dir():
    return _normalized_env("UPLOADS_DIR", "data")


def supabase_url():
    return _normalized_env("SUPABASE_URL")


def supabase_service_role_key():
    return _normalized_env("SUPABASE_SERVICE_ROLE_KEY")


def supabase_anon_key():
    return _normalized_env("SUPABASE_ANON_KEY")


def supabase_storage_bucket():
    return _normalized_env("SUPABASE_STORAGE_BUCKET", "documents")


def supabase_storage_public():
    return parse_bool(os.getenv("SUPABASE_STORAGE_PUBLIC"), default=False)


def embedding_provider():
    return _normalized_env("EMBEDDINGS_PROVIDER", "local").lower()


def embedding_dimensions():
    if embedding_provider() == "openai":
        raw = _normalized_env("EMBEDDING_DIMENSIONS")
        return int(raw) if raw else 1536

    raw = _normalized_env("EMBEDDING_DIMENSIONS")
    return int(raw) if raw else 384


def openai_embedding_model():
    return _normalized_env("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


def openai_chat_model():
    return _normalized_env("OPENAI_CHAT_MODEL", "gpt-4o-mini")


def cors_origins():
    raw = _normalized_env("CORS_ORIGINS")
    if not raw:
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def database_connect_timeout():
    raw = _normalized_env("DATABASE_CONNECT_TIMEOUT", "5")
    try:
        return max(1, int(raw))
    except ValueError:
        return 5


def pgvector_init_on_startup():
    return parse_bool(os.getenv("PGVECTOR_INIT_ON_STARTUP"), default=False)


def auth_required():
    default = bool(supabase_url())
    return parse_bool(os.getenv("AUTH_REQUIRED"), default=default)


def supabase_jwks_url():
    configured = _normalized_env("SUPABASE_JWKS_URL")
    if configured:
        return configured
    if not supabase_url():
        return ""
    return f"{supabase_url().rstrip('/')}/auth/v1/.well-known/jwks.json"
