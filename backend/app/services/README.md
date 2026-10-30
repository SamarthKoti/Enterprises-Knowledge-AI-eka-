# Implemented Phase 2 boundaries
- parsing / chunking: deterministic PDF/TXT/MD extraction and structure-aware passages.
- ingestion: validated uploads, hashes, state, SQLite metadata and retry handling.
- embeddings / vector_store: lazy singleton MiniLM, batched pooled embeddings, persistent Chroma.
- versioning / retrieval: explicit policy authority, historical selection, semantic + BM25 RRF.
- llm: configurable Gemini SDK adapter and structured bounded responses.
- citations / answering: database-backed provenance, exact quote and numeric checks, LLM support verification, conservative classification.
Batch processing is intentionally unimplemented.
