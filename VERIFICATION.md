# Verification — 2026-10-30

## Phase 2 backend
- Final command: `RUN_MODEL_TESTS=1 python -m pytest -q` (PowerShell environment syntax in README).
- **28 passed in 20.94 seconds; 0 failed, 0 skipped.** No accuracy benchmark is claimed.
- Real MiniLM model download and 384-dimensional embedding generation verified.
- Real semantic and hybrid retrieval verified; Chroma count survives opening from a separate process.
- PDF page extraction/table preservation, TXT/Markdown metadata, chunk headers, duplicate detection, failure/retry, upload validation/limits, current/historical version selection, authority ambiguity, all answer statuses, invalid quotes/IDs/numbers, provider adapter and semantic fallback covered.
- Gemini generation/verification mocked. **No Gemini API key is configured; live provider answer quality and availability remain unverified.**
- Recorded fictional test question/response: verification/phase2-example.json. Uses real MiniLM/Chroma and mocked Gemini; citation IDs refer to the temporary test database, not the production corpus.
- `pip check`: no broken requirements.
- Running server smoke checks: health 200/phase 2; unauthenticated documents 401; login 200; authenticated documents 200; empty-corpus ask 200/not_covered; logout 204; revoked session 401.
- Unchanged frontend HTTP 200. No frontend files modified during Phase 2.

## Retained Phase 1 checks
Production frontend build, login/logout, protected deep links and all five routes previously passed desktop/mobile verification. The decorative hand was removed in the intervening user-requested edit; older saved screenshots predate that removal.

## Limits
No live Gemini test without credentials. No OCR; scanned pages are warned/rejected. Table detection depends on PDF structure. Support verification is conservative and cannot guarantee zero hallucinations. Local ingestion is synchronous, single-worker, and bounded by configured limits. Batch, reports, exports and frontend API integration remain Phase 3.
