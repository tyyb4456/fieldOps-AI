# Step 4.4 — Document Storage and Ingestion Foundation

This phase adds real PDF storage and deterministic text ingestion to the
existing document metadata tables. It does not add embeddings, vector search,
RAG retrieval, OCR, LLM extraction, background workers or cloud storage.

## Storage architecture

- `DocumentStorage` is a driver-agnostic interface with `save`, `open`, `read`,
  `delete`, `exists`, key generation and key enumeration.
- `LocalFileStorage` is the only driver in this phase.
- Storage keys are app-generated UUID tokens with a constant `.pdf` suffix.
  User-supplied filenames are never used as filesystem paths.
- Keys are resolved under the configured storage root. Absolute paths, drive
  prefixes, `..` components, symlink components and paths that resolve outside
  the root are rejected.
- Saves use a temporary file followed by `os.replace` in the destination
  directory, with `fsync` before replacement.
- Deletion is idempotent.
- The storage root defaults to `backend/var/document_storage`, which is not
  mounted as a public/static directory.
- Absolute server paths and storage keys are not included in API responses.

## Configuration defaults

| Setting | Default |
| --- | --- |
| `STORAGE_BACKEND` | `local` |
| `STORAGE_ROOT` | `backend/var/document_storage` |
| `MAX_UPLOAD_SIZE_BYTES` | `26214400` (25 MiB) |
| `ALLOWED_DOCUMENT_CONTENT_TYPES` | `application/pdf` |
| `MAX_PDF_PAGES` | `500` |
| `DOCUMENT_CHUNK_SIZE` | `1000` characters |
| `DOCUMENT_CHUNK_OVERLAP` | `200` characters |
| `DOCUMENT_INGESTION_VERSION` | `1` |

Relative storage roots are resolved against the backend directory.

## Upload validation

Administrators upload multipart PDFs with `manufacturer`, `model`,
`document_name`, optional `version` and a `file`. The server validates:

- a non-empty file and configured byte limit;
- a `.pdf` filename extension;
- an allowed declared content type;
- a PDF signature in the first 1024 bytes;
- parser validity (including rejection of encrypted PDFs);
- the configured page limit;
- non-blank metadata and existing document-version uniqueness rules.

The original filename is sanitized to a basename and stored only as metadata.
The stored object key is generated independently.

## PDF extraction and chunking

PDF loading and text splitting use LangChain's reusable components; FieldOps
still owns storage, integrity, lifecycle, concurrency and persistence.

### Loading with `PyPDFLoader`

- `PyPDFLoader` (from `langchain-community`) is the only PDF text extractor.
  No custom page-extraction or PDF-to-text loop remains.
- It is always constructed with `mode="page"`, so each PDF page becomes a
  separate LangChain `Document`. Pages are never merged into one text blob
  before splitting.
- `PyPDFLoader` reports a zero-based `metadata["page"]` and a `page_label`.
  FieldOps converts `page` to the one-based `page_number` used by
  `document_chunks`.
- `source` metadata contains the private storage path and is deliberately not
  persisted. Only the page number, character offsets and ingestion version are
  stored.
- The loader is used on the verified file in private storage. Uploads are
  saved first, loaded once, and the resulting page Documents are reused for
  splitting and persistence. Re-ingestion verifies the stored size and SHA-256
  once, then loads the same stored file once. The PDF is not parsed separately
  for validation, extraction and splitting.
- Validation that needs a parsed PDF (signature beyond the first KiB, encryption,
  page count, malformed xref/text) is satisfied by the loader call. Because
  `PyPDFLoader.load()` materializes every page before FieldOps can enforce
  `MAX_PDF_PAGES`, a page-limit rejection happens after extraction; the 25 MiB
  upload cap bounds this work.
- `PyPDFLoader.load()` is synchronous. It always runs through
  `run_in_threadpool`, never directly on the FastAPI event loop.

### Splitting with `RecursiveCharacterTextSplitter`

- `RecursiveCharacterTextSplitter` (from `langchain-text-splitters`) replaces
  the fixed-window character chunker.
- It is configured from `DOCUMENT_CHUNK_SIZE` and `DOCUMENT_CHUNK_OVERLAP`, with
  `length_function=len` and `add_start_index=True`.
- `split_documents()` receives one source Document per page, so chunks never
  cross page boundaries and page attribution remains unambiguous.
- LangChain's `start_index` is validated against the normalized page text. If
  it is missing or does not match (repeated text, stripped whitespace), a small
  adapter searches the page text from the previous chunk position. `char_end`
  is always `char_start + len(content)`.
- Offsets are page-local character offsets into the normalized page text, the
  same coordinate system used before this refactor.

### Normalization and empty pages

- Extraction normalization remains FieldOps-owned: line endings are
  normalized, unsafe control characters are removed, trailing line whitespace
  is trimmed and excessive blank lines are collapsed.
- Empty or whitespace-only pages are skipped. If no page contains text after
  normalization, ingestion fails with "The PDF contains no extractable text."
  and no empty chunks are created.
- Chunks never contain only whitespace.
- Token counts are not recorded because no tokenizer is part of this phase.

### Limitations

- `PyPDFLoader` materializes the whole file and all page Documents in memory.
  At the 25 MiB / 500 page limits this is bounded, but it is not a streaming
  pipeline.
- The file is read once to compute the integrity hash and again by the loader.
  This preserves independent SHA-256 verification without introducing an
  in-memory or temporary-file conversion layer.
- A stored file could change between hash verification and loader parsing. The
  ingestion advisory lock and immutable-by-convention storage minimize this
  window; FieldOps does not claim distributed atomicity between PostgreSQL and
  the filesystem.
- LangChain does not provide storage security, integrity verification,
  authorization, transactions, concurrency control or recovery. Those remain
  FieldOps responsibilities.

## Ingestion lifecycle and transactions

Statuses are `pending`, `processing`, `ready` and `failed`.

1. A short transaction locks the document row, deactivates it and moves it to
   `processing` from any non-processing state. A simultaneous request sees
   `processing` and receives `409 ingestion_in_progress`. A successfully
   re-ingested document must be explicitly activated again.
2. No database transaction is held while the stored PDF is read, parsed or
   chunked.
3. A separate transaction deletes the previous chunks, inserts the new chunk
   set and moves the document to `ready` with `ingested_at`. The delete and
   insert are atomic.
4. On failure, a short transaction records a safe message, sets `failed` and
   deactivates the document. Previously persisted chunks are left in place so a
   later successful re-ingestion can replace them; they are not treated as
   active reference material because activation requires `ready`.

The upload endpoint performs initial ingestion synchronously. A valid PDF with
no extractable text is stored and left `failed` so an administrator can retry
or replace it. Re-ingestion is available through the dedicated endpoint.

## Activation rules

Activation requires all of:

- `ingestion_status = ready`;
- at least one persisted chunk;
- storage metadata (key, PDF content type, positive byte size, SHA-256);
- a stored file that still exists.

Generic metadata `PATCH` cannot change `is_active` or any system-managed field
(storage key, checksum, uploader, ingestion status/error/timestamps).

## Deletion and filesystem/database compensation

PostgreSQL and the filesystem do not share a transaction. The implementation
does not claim distributed atomicity.

- Upload order: validate, write stored file, create database row. If database
  creation fails, the newly written file is deleted. If that cleanup also
  fails, the result is an unreferenced orphan file.
- Delete order: delete database metadata (chunks cascade), commit, then delete
  the stored file. If the database delete fails, the file is not touched. If
  the file delete fails after the commit, the result is an orphan file.
- Legacy `file_path` values are never used for deletion.

Residual risk: a process crash between the two systems can leave an orphan
file or (on database delete followed by file delete failure) a stored file with
no metadata. Orphan files are private and contain no database references.

Safe reconciliation:

```bash
python -m app.scripts.reconcile_document_storage
# Review the report, then optionally:
python -m app.scripts.reconcile_document_storage --delete-orphans
```

The script reports unreferenced stored files and database rows whose file is
missing. It never prints absolute paths.

## Legacy migration behavior

Existing `documents.file_path` values are preserved for history but are not
converted into trusted storage keys. All pre-existing documents are set
inactive and `pending`; they are not marked `ready` and require re-upload
before activation. Downgrade refuses while any storage-backed document exists,
because dropping the new columns would discard trusted file metadata while
leaving binaries behind.

## Security and future RAG boundary

PDFs are untrusted input. Only administrators can upload, re-ingest, activate,
deactivate or delete. Extracted text is untrusted reference content; later RAG
and agent phases must treat retrieved text as data, never as instructions.
Prompt injection is not "solved" by PDF parsing.

The current schema is single-tenant: `manufacturer`/`model` identify documents,
and there is no organization/tenant boundary. Steps 4.4 endpoints must not claim
tenant isolation that the schema cannot enforce.
