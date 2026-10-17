# Project process

This guide describes how the repository is organized and how to make and review changes. The canonical runtime is the FastAPI application at `server.app.main:app`; the repository also contains older root-level entrypoint files, which are not the application entrypoint described by the README and Dockerfile.

## Repository map

```text
client/                    Static HTML, CSS, and JavaScript client
server/app/api/v1/         HTTP and page route modules plus router registry
server/app/middleware/     JWT and organization request context
server/app/processors/     Ingestion, OCR, embeddings, Qdrant, storage helpers
server/app/model.py        SQLAlchemy ORM model definitions
server/migrations/         Alembic environment and revision history
docs/                      Architecture and component references
Dockerfile                 Container build and production ASGI command
requirements.txt           Python dependencies installed by Docker
.env.example               Names and examples for application settings
```

Read [architecture.md](architecture.md) for component and data flows, [backend.md](backend.md) for APIs and settings, [database.md](database.md) for relational data and migrations, [frontend.md](frontend.md) for pages and assets, and [vector-database.md](vector-database.md) for Qdrant and retrieval.

## Local setup reference

1. Use Python 3.12, matching the Docker base image.
2. Install dependencies from `requirements.txt` in a dedicated virtual environment.
3. Copy `.env.example` to `.env` and supply real values through a local, untracked environment file. At minimum, settings require `DATABASE_URL` and `SECRET_KEY`; provider keys and services depend on the feature being used. The storage integration reads Supabase settings directly from process environment variables.
4. Use the canonical ASGI import `server.app.main:app`. The README gives the local Uvicorn command; the container uses port `7860`, while `python -m server.run` binds to port `5000` for local development.
5. The browser assets are served by FastAPI from `/static`; there is no separate frontend install/build command.

Do not copy credentials into docs, source files, screenshots, or committed example files. Check `.gitignore` before adding environment or generated files.

## Change workflow

### 1. Find the owning layer

- Browser presentation or interaction: `client/pages/` and `client/components/`.
- HTTP contract or authorization: `server/app/api/v1/` and, where needed, `server/app/dependencies.py` or middleware.
- RAG orchestration/provider selection: `server/app/action.py`.
- Loading, OCR, chunking, Qdrant, or storage: `server/app/processors/`.
- Relational data: `server/app/model.py` and `server/migrations/versions/`.
- Container or Python dependencies: `Dockerfile`, `requirements.txt`, and deployment environment configuration.

Prefer to keep each change in its owning layer and update the adjacent boundary when a contract changes. For example, adding a field used by the chat UI may require an ORM/migration change, response changes, client rendering, and updates to the API and database documentation.

### 2. Preserve cross-service identifiers

File ingestion and deletion coordinate a PostgreSQL file row, Supabase object key, and Qdrant `document_id`/organization collection. Keep the organization short ID, SQL file ID, document ID, and storage key distinct and consistently mapped. These services do not share a transaction; changes to ordering or failure behavior should be reflected in the architecture, database, and vector database docs.

### 3. Handle schema evolution deliberately

1. Update the SQLAlchemy declaration in `server/app/model.py`.
2. Inspect the current model and migration history, including the known conversation-ID differences documented in [database.md](database.md).
3. Create and review an Alembic revision. Typical commands from the repository root are `alembic -c server/alembic.ini revision --autogenerate -m "describe change"` and, when approved for the target database, `alembic -c server/alembic.ini upgrade head`.
4. Review generated SQL/operations and consider existing data, foreign keys, nullability, indexes, and downgrade behavior. Autogenerate is a draft, not a substitute for review.
5. Update the database documentation and any API/client contract that depends on the changed column.

`server/migrations/recreate_chats.py` is destructive and drops/recreates chat tables. It is not a standard migration workflow. Do not use it to make routine schema changes.

### 4. Update documentation and review the diff

Update the relevant pages under `docs/` when routes, payloads, access rules, settings, persistence, deployment, or process steps change. Review the full diff for accidental secrets, generated data, stale paths, inconsistent URL prefixes, and mismatches between ORM declarations and migrations.

## Dependencies and deployment

`requirements.txt` is installed by the Dockerfile. The root `pyproject.toml` and `uv.lock` are repository-level Python tooling/lock files; they do not introduce a separate browser build. The container installs PDF/OCR system packages, copies the repository, and launches `uvicorn server.app.main:app --host 0.0.0.0 --port 7860`. Set production secrets and service URLs in the deployment environment, not in the image or Git.

The app starts a daily cleanup coroutine, but its current body is a placeholder that logs a message and closes a database session. It does not reconcile orphan files or remove stale vectors; production operations should not rely on it for cleanup.

## Verification expectations

For a code change, choose checks that match its surface: import/type or lint checks for Python changes, a migration review for schema changes, and browser/API contract review for client changes. This documentation update was prepared by inspecting repository sources; the application was not launched and database, storage, vector, or model services were not contacted.
