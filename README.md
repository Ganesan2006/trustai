---
title: TrustAI
emoji: 🤖
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# TrustAI

TrustAI is a document question answering application built around retrieval augmented generation (RAG). The repository is organized as a small monorepo with a Python API server and a vanilla HTML/CSS/JavaScript client.

## Repository layout

```text
client/
  pages/                 HTML page documents
  components/             Page-specific CSS and JavaScript
server/
  app/
    api/v1/               Versioned API route registration and route modules
    middleware/           Request middleware
    processors/           Document, OCR, retrieval, and conversation processing
    utils/                Shared backend utilities
    main.py               FastAPI application
    config.py             Settings and SQLAlchemy session setup
    model.py              SQLAlchemy models
  migrations/             Alembic migrations
  alembic.ini             Alembic configuration
docs/                     Frontend, backend, architecture, data, and process docs
```

## Local development

1. Install the dependencies listed in `requirements.txt`.
2. Configure the environment variables described in [Backend documentation](docs/backend.md), including database credentials and any model or storage credentials you use.
3. From the repository root, start the ASGI application with `uvicorn server.app.main:app --reload` or `python -m server.run`.

The frontend component assets are mounted at `/static`. Database schema changes are managed under `server/migrations`; see [the project process](docs/project-process.md) before creating or applying migrations.

## Documentation

- [Frontend](docs/frontend.md)
- [Backend](docs/backend.md)
- [Architecture](docs/architecture.md)
- [Database](docs/database.md)
- [Vector database](docs/vector-database.md)
- [Project process](docs/project-process.md)

## API structure

All supplied route modules are in `server/app/api/v1` and are registered by `server/app/api/v1/router.py`. Their existing URL prefixes are preserved for client compatibility (for example, `/api/auth` and `/api/chat`); `v1` currently identifies the code package, not a `/v1` URL prefix.
