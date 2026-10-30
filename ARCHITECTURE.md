# Enterprise Knowledge AI — Phase 2

## Components and flow
Unchanged React/Vite frontend and cookie authentication -> authenticated FastAPI APIs -> SQLite metadata/passages + persistent Chroma vectors -> hybrid retrieval -> Gemini draft -> deterministic citation checks -> separate evidence verification -> conservative classification.

`backend/app/api/knowledge.py` owns upload/list/detail/ask. `services/` contains parsing, chunking, ingestion, embeddings, vector_store, versioning, retrieval, llm, citations and answering. `core/database.py` applies additive Phase 1 migrations. Existing sessions and original Document/Answer fields are retained. The hand was removed from the frontend at the user's request before Phase 2; no Phase 2 UI changes are made.

## Storage and processing
SQLite stores document hashes, policy metadata, processing state, warnings and page/section-aware passages. `DATA_DIR/uploads` stores original files under generated IDs; `DATA_DIR/chroma` stores embeddings; `MODEL_CACHE_DIR` caches MiniLM. Content hashes prevent duplicate embedding; changed metadata on identical content returns 409. Failed uploads are retryable. Interrupted processing becomes failed at startup. Run one backend worker; no distributed jobs in this phase.

PDF parsing uses PyMuPDF text and table extraction, real one-based pages and observed headings. TXT/MD use UTF-8 and null pages. Table headers repeat with rows; oversized indivisible rows fail explicitly. Scanned pages produce warnings; OCR is not implemented. Approximate 500-token chunks overlap by 75, without crossing section/page boundaries. MiniLM's shorter input limit is handled by embedding all token subwindows and pooling normalized vectors. Model/revision-specific collections prevent incompatible embedding reuse.

Version resolution precedes retrieval. Current queries use explicit effective current metadata; draft/future/superseded sources are excluded. Historical queries accept `as_of`, `version`, or a year in the question. Multiple authoritative candidates within a policy family are excluded with an ambiguity warning. Upload time is never authority. Set policy_family consistently across versions. Historical date resolution uses the latest explicit effective date at or before the requested date; exact version selection is also supported. Missing historical metadata cannot be guessed.

Semantic retrieval and BM25Plus are fused with reciprocal rank fusion (k=60), deduplicated and bounded to 6 passages/16,000 characters by default. BM25 failure falls back to semantic search with a warning. Provider or vector failures are explicit 503s. No evidence returns not_covered without an LLM call.

## APIs
All knowledge endpoints require the existing HTTP-only session cookie. Errors use detail; upload per-file errors use results[].error.

| Method/path | Contract |
|---|---|
| GET /api/health | `{status:"ok",phase:2}`; liveness, not provider readiness |
| POST /api/documents/upload | multipart `files` (up to 10), `metadata` JSON object or aligned array; 10 MiB/file, 30 MiB/request. Metadata: policy_family, version, effective_date, status (default draft), superseded_by. Returns `{results:[{document,duplicate,error}]}`; 201 new, 200 all duplicates, 207 mixed, single errors retain HTTP status. |
| GET /api/documents | `Document[]`, includes processing_status, chunk_count, warnings, error, superseded_by |
| GET /api/documents/{id} | Document or 404 |
| POST /api/ask | `{question,policy_family?,version?,as_of?,top_k?:1..12,mode?:hybrid|semantic}` -> Answer |
| POST /api/answers | compatibility alias for /api/ask |
| POST /api/batches | protected 501; not implemented |

Answer retains question, answer, status and citations; adds supported_parts, unsupported_parts and warnings. Citation retains document_id, passage_id, filename, version, section, page, quote; adds requested aliases document and chunk_id. Status remains answered / partially_answered / not_covered. IDs and citation metadata resolve from SQLite. Generated chunk IDs must belong to retrieved evidence, exact quotes must exist, and numeric claims must match quoted evidence. A second bounded Gemini call checks entailment and all requested parts; only accepted claims appear in the answer. Unverified claims are dropped and completeness downgraded. This is conservative validation, not a guarantee of perfect hallucination prevention.

## Phase 3 integration points
Wire the existing page shells to these APIs, display upload states and citations, and add batch processing/reports/exports only when requested. No frontend integration or batch implementation is included here.

## Account registration
POST /api/auth/signup accepts {email,password}, creates an Argon2-hashed SQLite account and returns 201 {email} with the existing HTTP-only session cookie. Passwords require 12–128 characters. Existing demo login is preserved; duplicate or reserved emails return 409. The login screen switches between sign-in and registration with password confirmation. Accounts share this demo workspace; email verification and separate organizations are not implemented.
