# RAG Assistant

This project deploys as a single Docker web service:

- FastAPI serves the API
- Vite builds the frontend
- FastAPI serves the built frontend from `frontend/dist`

## Render

Use a Render `Web Service` with `Docker`.

Set these backend environment variables:

- `OPENAI_API_KEY`
- `OPENAI_CHAT_MODEL`
- `EMBEDDINGS_PROVIDER`
- `OPENAI_EMBEDDING_MODEL`
- `EMBEDDING_DIMENSIONS`
- `DATABASE_URL`
- `DATABASE_CONNECT_TIMEOUT`
- `VECTOR_BACKEND`
- `PGVECTOR_INIT_ON_STARTUP`
- `STORAGE_BACKEND`
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_JWKS_URL`
- `SUPABASE_STORAGE_BUCKET`
- `SUPABASE_STORAGE_PUBLIC`
- `AUTH_REQUIRED`
- `CORS_ORIGINS`

Set these frontend build variables too:

- `VITE_API_BASE_URL`
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`

Leave `VITE_API_BASE_URL` empty for same-origin deployment.

Health check path:

- `/health`
