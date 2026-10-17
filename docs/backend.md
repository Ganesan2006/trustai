# Backend reference

## Application layout

The backend is a Python 3.12 FastAPI application in the `server.app` package.

- `server/app/main.py` creates the ASGI application, installs organization resolution middleware, mounts client assets at `/static`, and includes the version 1 router registry.
- `server/app/api/v1/router.py` registers the feature routers described below.
- `server/app/config.py` reads settings and creates the SQLAlchemy engine/session factory.
- `server/app/model.py` defines the ORM tables documented in [database.md](database.md).
- `server/app/dependencies.py` provides the database session and bearer-token user dependency.
- `server/app/action.py` coordinates model selection, retrieval, and answer generation.
- `server/app/processors/` contains document loading, OCR, chunking, vector search, and storage integrations.
- `server/app/middleware/org_resolver.py` verifies tokens and sets request organization/user context.
- `server/app/utils/` contains shared helpers, including API-key encryption.

The directory `api/v1` is the route-code version boundary. The current routers retain their existing URL paths; they do not add a `/v1` segment to URLs.

## Authentication and request context

Protected handlers use `get_current_user`, which reads a JWT from `Authorization: Bearer <token>`, verifies it with `SECRET_KEY` and `ALGORITHM`, and loads the matching `User` row. `OrgResolverMiddleware` also verifies the token on non-public requests and sets `request.state.org_short_id` and `request.state.user_id`.

Login, signup, organization registration, organization department lookup, static assets, and the listed page routes are public at the middleware layer. Route dependencies still enforce authentication where applicable. Admin management and analytics handlers generally require `org_admin` or `super_admin`; the endpoint inventory notes the exceptions.

## Router registry

| Module | Router prefix | Responsibility |
|---|---|---|
| `auth.py` | `/api/auth` | Login, employee signup, organization registration, organization departments |
| `conversations.py` | `/api/conversations` | Conversation lifecycle, messages, settings, file associations |
| `files.py` | `/api/files` | Upload, access listing, file serving and download |
| `chat.py` | `/api/chat` | RAG chat, activation, feedback |
| `pages.py` | no prefix | Serves HTML documents from `client/pages` |
| `admin.py` | `/admin` | Organization users, departments, teams, provider keys, assignments, files |
| `admin_analytics.py` | `/admin/analytics` | Organization analytics dashboards |
| `user.py` | `/api/user` | Current-user profile |

### Authentication router — `auth.py`

| Method and path | Purpose and input |
|---|---|
| `POST /api/auth/login` | Accepts `email` and `password`; finds the active organization from the email domain and returns a bearer token plus user summary. |
| `POST /api/auth/signup` | Accepts `name`, `email`, `password`, `org_id`, and optional `mobile`, `designation`, and `department_id`; email must match the organization's domain. Creates an employee account and returns a token. |
| `GET /api/auth/organizations/{org_short_id}/departments` | Returns the department IDs and names for an organization. |
| `POST /api/auth/org/register` | Registers an organization and its first administrator. The body includes organization identity/contact fields and admin name, email, mobile, password, role, confirmation password, and optional department/team lists. |

These endpoints do not require an existing user token. Validation and duplicate checks are performed in the handler.

### Conversation router — `conversations.py`

All endpoints require the current user and scope conversation access to that user's organization/account.

| Method and path | Purpose and input |
|---|---|
| `GET /api/conversations` | Lists the current user's conversations. |
| `POST /api/conversations` | Creates a conversation; optional body `{ "name": "..." }`. |
| `DELETE /api/conversations/{conv_id}` | Deletes a conversation. `delete_files` is a query parameter and defaults to `true`; when true, associated files and Qdrant vectors are also requested for deletion. |
| `PUT /api/conversations/{conv_id}` | Updates the conversation name using `{ "name": "..." }`. |
| `GET /api/conversations/{conv_id}/messages` | Lists messages in a conversation. |
| `POST /api/conversations/{conv_id}/messages` | Adds a message from a JSON object. |
| `GET /api/conversations/{conv_id}/files` | Lists files associated with a conversation. |
| `POST /api/conversations/{conv_id}/allowed-files` | Sets the allowed document IDs for the conversation; body is a list of IDs. |
| `PUT /api/conversations/{conv_id}/settings` | Updates sharing scope and optional department/team settings. |
| `GET /api/conversations/{conv_id}` | Returns one conversation if it belongs to the current user. |

### File router — `files.py`

All endpoints use the current user's organization and file access rules. Uploads use multipart form data and Supabase Storage.

| Method and path | Purpose and input |
|---|---|
| `GET /api/files/upload-targets` | Lists department/team destinations the current user may select for an upload. |
| `POST /api/files/upload` | Multipart upload. Fields include required `input_file` and `scope`, optional `conversation_id`, `target_department_id`, and `target_team_id`. Stores metadata and processes the document for retrieval. |
| `DELETE /api/files/{conv_id}` | Deletes the conversation's associated files and their vector records. |
| `GET /api/files/serve/{user_id}/{conv_id}/{filename}` | Serves a stored file, using an optional `token` query parameter or the request bearer token. May redirect to a stored public URL or stream the file. |
| `GET /api/files/accessible` | Lists files the current user can access based on role and company/department/team/private scope. |
| `GET /api/files/download/{file_id}` | Downloads a file by database ID. Supports `token` and `inline` query parameters; non-owner access is restricted to admins. |

### Chat router — `chat.py`

| Method and path | Purpose and input |
|---|---|
| `POST /api/chat/` | Authenticated RAG request. Body includes `input`, `conversation_id`, and optional `search_scope` (`type`, `department_ids`, `team_ids`, `user_emails`). Searches scoped Qdrant content, invokes the selected LLM, stores user/assistant messages and a query log, then returns response, citations, conversation ID, and query-log ID. |
| `POST /api/chat/activate/{conv_id}` | Confirms that the conversation exists and belongs to the current user. |
| `POST /api/chat/feedback` | Records `query_log_id`, `rating`, and optional `comment` against the current user's query. |

The chat handler builds visibility filters from user role, conversation settings, and optional search scope. Citations are returned with source name, page, text, and similarity information.

### Page router — `pages.py`

These handlers return the HTML files under `client/pages`. The page documents reference assets served by the `/static` mount.

| Method and path | Page |
|---|---|
| `GET /` | `login.html` |
| `GET /start` | `chat.html` |
| `GET /chat/{conversation_id}` | `chat.html` |
| `GET /org/register` | `org_login.html` |
| `GET /admin/dashboard` | `admin_dashboard.html` |
| `GET /admin` | `admin.html` |

### Admin management router — `admin.py`

The router prefix is `/admin`. Endpoints guarded by `require_admin` require `org_admin` or `super_admin`. Department/team listing routes require an authenticated user but permit non-admin roles.

| Method and path | Purpose |
|---|---|
| `GET /admin/users` | Lists organization users and their profile/department/team fields. Admin only. |
| `PUT /admin/users/{user_id}` | Updates a user's role, department, or team after validating organization ownership. Admin only. |
| `GET /admin/departments` | Lists the current user's organization departments. Authenticated user. |
| `POST /admin/departments` | Creates a department from `name` and optional `description`. Admin only. |
| `PUT /admin/departments/{dept_id}` | Updates a department's name/description. Admin only. |
| `DELETE /admin/departments/{dept_id}` | Deletes an organization department. Admin only. |
| `GET /admin/teams` | Lists organization teams; optional `department_id` filter. Authenticated user. |
| `POST /admin/teams` | Creates a team from `name`, optional `department_id`, and `description`. Admin only. |
| `PUT /admin/teams/{team_id}` | Updates team name, description, or department. Admin only. |
| `DELETE /admin/teams/{team_id}` | Deletes a team. Admin only. |
| `POST /admin/api-keys` | Saves an organization provider/API key. Body: `provider`, `api_key`, optional `description`; key material is encrypted before storage. Admin only. |
| `GET /admin/api-keys` | Lists key metadata without returning decrypted key material. Admin only. |
| `DELETE /admin/api-keys/{key_id}` | Deletes an organization API-key record. Admin only. |
| `POST /admin/model-assignments` | Assigns a provider/model to a user; body: `user_id`, `provider`, `model_name`. Admin only. |
| `GET /admin/model-assignments` | Lists model assignments for users in the organization. Admin only. |
| `DELETE /admin/model-assignments/{assign_id}` | Deletes a user-model assignment. Admin only. |
| `GET /admin/files` | Lists organization files; optional `user_id` filter. Admin only. |

Provider values are `openai`, `anthropic`, `google`, or `ollama` (represented by `ProviderEnum`).

### Admin analytics router — `admin_analytics.py`

All routes require `org_admin` or `super_admin` and aggregate data for the administrator's organization.

| Method and path | Purpose and notable query parameters |
|---|---|
| `GET /admin/analytics/overview` | Summary counts, activity trend, confidence, cost, and storage. `period`: `today`, `week`, or `month` (default `today`). |
| `GET /admin/analytics/users` | User activity and role/department summaries. Optional `department_id`, `team_id`, `role`, `search`; `limit` defaults to 50. |
| `GET /admin/analytics/documents` | Document/storage totals, access-scope breakdown, file types, recent/largest files, and missing access metadata. Optional department/team filters are accepted. |
| `GET /admin/analytics/ai-usage` | Query volume, model usage/cost/token and latency summaries for a period. `period`: `today`, `week`, or `month`. |
| `GET /admin/analytics/retrieval` | Retrieval activity and similarity/retrieved-chunk summaries. |
| `GET /admin/analytics/knowledge-gaps` | Lists unresolved/resolved organization knowledge-gap records and counts. |
| `GET /admin/analytics/feedback` | Summarizes user ratings and feedback comments. |
| `GET /admin/analytics/security` | Summarizes document-access/security activity. |
| `GET /admin/analytics/organization` | Returns organization-level membership and usage summaries. |

### User profile router — `user.py`

Both endpoints require the current user's bearer token.

| Method and path | Purpose and input |
|---|---|
| `GET /api/user/profile` | Returns the current user's ID, name, email, role, department/team IDs, mobile, and designation. |
| `PUT /api/user/profile` | Updates `department_id`; a positive ID must belong to the user's organization, while a non-positive value clears the department. |

## Configuration and deployment

The backend is configured from the root `.env.example`; `server/app/config.py` uses Pydantic Settings and reads `.env`. The main settings are:

| Variable | Required/default | Used for |
|---|---|---|
| `DATABASE_URL` | Required | SQLAlchemy PostgreSQL connection. |
| `SECRET_KEY` | Required | JWT signing and verification. |
| `ALGORITHM` | `HS256` | JWT algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` | Token lifetime. |
| `ENCRYPTION_KEY` | Required by encryption helper | Fernet encryption of provider keys stored in SQL. |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Required by storage module | Supabase Storage client. `SUPABASE_BUCKET` defaults to `turstai`. |
| `QDRANT_URL`, `QDRANT_API` | Optional in settings | Remote Qdrant endpoint and API key; without a URL, Qdrant manager uses in-memory mode. |
| `QDRANT_COLLECTION_PREFIX` | `org_` | Declared configuration value; the current Qdrant manager uses its own `org_` default instead of reading this setting. |
| `OPENAI_API_KEY` | Optional | Default OpenAI-compatible LLM credential. |
| `OPENAI_BASE_URL` | `https://api.groq.com/openai/v1` | Default OpenAI-compatible endpoint. |
| `OPENAI_DEFAULT_MODEL` | `openai/gpt-oss-20b` | Default generation model. |

The encryption and storage helpers also read environment variables directly. Keep those values in the process environment or a correctly loaded local `.env`; never commit secrets. Qdrant and model settings are used by their corresponding integrations.

### Model selection and RAG processing

`llmProcessor` in `server/app/action.py` selects an active per-user model assignment when an active organization API key is available. It handles OpenAI, Anthropic, and Google assignments; otherwise it falls back to the configured OpenAI-compatible model if `OPENAI_API_KEY` is set, then to the Ollama model `gemma3:12b`. Provider keys saved through admin routes are encrypted by `server/app/utils/encryption.py`.

The chat route validates the conversation, builds a Qdrant filter from user role and requested scope, retrieves documents, passes query/context to the selected model, then stores chat/query data and returns a JSON answer with citations. The code's dense embedding model is initialized in `server/app/globals.py`; sparse retrieval uses FastEmbed's `Qdrant/bm25`. See [vector-database.md](vector-database.md) for the retrieval details.

### Document processing

The file upload route hashes the upload for duplicate detection, writes a temporary local copy for extraction, and dispatches processing through `llmProcessor` and `DocumentLoader`. PDFs are read page by page with PyMuPDF and use EasyOCR when extracted page text is empty and OCR is available. Other supported formats are loaded through LangChain community loaders. The document splitter targets 1,000 characters with 200-character overlap. Chunk points are upserted into Qdrant, original bytes are written to Supabase, and SQL file metadata is committed. Failures between those operations can leave partial cross-service state; there is no transaction spanning them.

`server/app/main.py` mounts the client, installs middleware, includes the router registry, and starts a background cleanup coroutine. The current cleanup body is a placeholder; it does not reconcile orphaned uploads. `server/run.py` is the local development launcher, while the Dockerfile runs the same ASGI app on port `7860`.

Start from the repository root with `uvicorn server.app.main:app --reload` or `python -m server.run`. Docker uses the same ASGI app and listens on port 7860. Do not commit `.env` or paste service credentials into documentation.
