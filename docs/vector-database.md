# Vector database (Qdrant)

## Purpose and source code

Qdrant stores chunk-level vectors and payloads used to retrieve passages for RAG answers. It is separate from PostgreSQL (ownership and file metadata) and Supabase Storage (original file bytes).

The integration is implemented in:

- `server/app/processors/qdrant_db.py` — Qdrant client, per-organization collections, payload indexes, upsert, hybrid search, and vector search.
- `server/app/processors/sparse_vector.py` — sparse BM25 vector generation.
- `server/app/globals.py` — shared dense embedding model initialization.
- `server/app/processors/document_loader.py` and `pdf_processor.py` — extraction, OCR fallback, and chunking.
- `server/app/api/v1/files.py` — file upload metadata and Qdrant ingestion.
- `server/app/api/v1/chat.py` — role/scope filters and retrieval for chat.

## Configuration and runtime behavior

| Setting | Use in the current code |
|---|---|
| `QDRANT_URL` | If it contains `cloud.qdrant.io`, creates a remote client and passes `QDRANT_API` when present. For other non-empty URLs, it creates a URL client without passing the API key. |
| `QDRANT_API` | Optional API key. It is currently passed only in the Qdrant Cloud URL branch described above. |
| `QDRANT_COLLECTION_PREFIX` | Declared in `server/app/config.py`, but `QdrantManager()` currently defaults its own prefix to the literal `org_` and does not read this setting. Changing the environment variable alone therefore does not change current collection names. |

When `QDRANT_URL` is unset, the manager creates an in-memory Qdrant client (`:memory:`). This is useful only for temporary/local work: vector data disappears when the process exits and is not shared between application processes. Use a persistent Qdrant deployment for durable data.

The Qdrant async client is stored in a module-level singleton and shared by manager instances in the process. The current manager does not expose a client shutdown/lifecycle hook.

## Collections and vector schema

A separate collection is used for each organization short ID. The current name is:

```text
org_<org_short_id>
```

The short ID comes from the authenticated organization context, not the numeric `organizations.id`. The collection provides the first tenant boundary; payload filters provide document visibility within that organization.

When a collection is first created, the manager configures:

| Vector name | Representation | Configuration |
|---|---|---|
| `dense` | Dense float vector | Embedding dimension is determined at runtime by embedding the text `test`; cosine distance. |
| `sparse` | Sparse index/value vector | Qdrant sparse vector with an in-memory index (`on_disk=False`). |

The dense embedding model is `sentence-transformers/all-MiniLM-L6-v2`, initialized globally through LangChain's `HuggingFaceEmbeddings`. Its model artifacts may be fetched when the application initializes. The sparse model is `Qdrant/bm25` through FastEmbed; it is initialized lazily on the first sparse-vector request.

On collection creation the code attempts keyword payload indexes for `access_level`, `department`, `team`, `uploaded_by`, and `document_id`. Index creation is inside one `try` block and is only attempted when the collection is newly created. Existing collections are not checked or repaired for missing indexes by `ensure_collection_exists`.

## Ingestion and stored payload

The upload path in `POST /api/files/upload` performs these steps:

1. Reads the uploaded bytes and checks the SHA-256 digest against PostgreSQL file metadata for an exact duplicate within the organization.
2. Extracts text from the temporary local file. PDFs are processed page by page with OCR fallback for image-only pages; other supported files use the configured LangChain loaders.
3. Splits extracted documents with `RecursiveCharacterTextSplitter` at a target chunk size of 1,000 and overlap of 200 (the splitter's default character-based length function is used).
4. Creates a `document_id` and one UUID `chunk_id` per chunk, then assembles access and citation metadata.
5. Embeds chunks densely and sparsely, and upserts them into the organization's collection.
6. Uploads original bytes to Supabase and records the file metadata in PostgreSQL.

The point ID is `chunk_id` (a UUID from upload code; the Qdrant manager generates a UUID if a caller omits one). The payload always includes `text` for the chunk. Non-empty fields from the supplied metadata are added; document metadata is then copied for keys not already present. The current upload metadata includes:

| Payload key | Meaning |
|---|---|
| `text` | Chunk text used to build the returned LangChain `Document`. |
| `organization_id` | Organization short ID. The collection is also organization-specific. |
| `document_id` | ID shared by chunks belonging to one uploaded file. |
| `chunk_id` | Point/chunk identifier; also used as the Qdrant point ID. |
| `chunk_number` | One-based chunk position in the processed document. |
| `title`, `file_name` | Original upload filename for display/citations. |
| `page_number` | Page value copied from the extracted document, or `0` if absent. PDF metadata may also provide `page`. |
| `uploaded_by` | User ID represented as a string, used by private-file filters. |
| `upload_date` | Upload timestamp in ISO format. |
| `source_type` | Lowercase file extension. |
| `access_level` | Visibility scope: `private`, `team`, `department`, or `company`. |
| `department`, `team` | Names added for applicable department/team-scoped files. |

PDF loader metadata may add `page`, `source`, `confidence`, and other non-empty fields. The exact payload can therefore contain extra extraction metadata in addition to the upload fields above.

### Cross-store consistency

The stores do not share a transaction. Current ingestion upserts Qdrant points before uploading bytes to Supabase and committing the PostgreSQL row. A later Supabase/database failure can leave vector points without a corresponding file record. Deletion code attempts to remove points by filtering on `document_id`, alongside SQL/storage deletion. There is no dedicated reconciliation or reindex command in the current implementation; keep these failure cases in mind when operating on production data.

## Access control and retrieval

`chat.py` builds a Qdrant `Filter` from the authenticated user, conversation, role, and optional `search_scope`. The implementation uses these payload fields:

- `access_level` to select company, department, team, or private files.
- `department` and `team` to match the user's/selected group's names.
- `uploaded_by` to restrict private files to one or more user IDs.

Admins can select organization departments, teams, or users through explicit scope fields. Department managers are limited to teams in their department. Regular users are restricted to their own department/team/private documents plus the applicable company documents. The filter is sent with both dense and sparse queries. Avoid changing payload names or their data types without updating filter construction and backfilling/recreating affected vectors.

The current hybrid search algorithm is:

1. Return an empty list if the organization's collection does not exist.
2. Embed the query densely and request the top `top_k` points from the `dense` vector.
3. Generate a BM25 sparse query vector and request the top `top_k` points from `sparse`.
4. Keep results with score at least `0.65` for both branches.
5. If there are no qualifying sparse results but dense results exist, return the first `final_k` dense results with their dense scores.
6. Otherwise, combine ranks by reciprocal-rank fusion with `k=60`, sort the fused candidates, and return up to `final_k` documents. The fused RRF score is added to the returned payload metadata as `score`.

`QdrantManager.hybrid_search` defaults to `top_k=20` and `final_k=5`. `llmProcessor.hybrid_search` defaults to `50` and `10`; the current chat endpoint explicitly calls it with `top_k=15` and `final_k=15`. These values are code defaults, not environment settings. `search_by_vector` is a dense-only helper with default limit 5 and score threshold 0.95; it does not apply the chat access filter.

The chat route converts returned points to citation objects using `file_name`/`title`, `page`/`page_number`, chunk text, and the result score. Keep these fields available if ingestion metadata changes.

## Deletion and maintenance

Conversation/file deletion code looks up the file's `document_id`, selects the organization's collection using its short ID, and asks Qdrant to delete points whose payload `document_id` matches. A document may contain many points, so deletion is by document ID rather than individual chunk ID. Verify that any new ingestion or deletion path uses the same organization short ID and `document_id` convention.

The application has no collection migration, snapshot/restore, bulk re-embedding, or stale-point cleanup utility in this package. For model/dimension or payload-schema changes, plan an explicit collection rebuild/backfill and coordinate it with PostgreSQL file metadata and Supabase objects. Keep backups and validate tenant/access filters before switching traffic.

## Operational checklist

- Configure a durable Qdrant URL and the appropriate API key before relying on persistent vectors.
- Treat the in-memory fallback as ephemeral development data.
- Keep collection naming, organization short IDs, point IDs, and payload field names stable across upload, search, and delete operations.
- Keep access-control fields (`access_level`, `department`, `team`, `uploaded_by`) correctly typed and populated.
- Ensure payload indexes exist on existing collections; current code only attempts to create them during initial collection creation.
- Monitor partial failures across Qdrant, Supabase, and PostgreSQL because there is no cross-service transaction or automatic reconciliation job.
- Plan explicit re-embedding/reindexing when changing the dense model, sparse model, chunking, vector configuration, or payload schema.
