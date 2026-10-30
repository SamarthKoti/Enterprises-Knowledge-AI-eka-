# RAG quality verification — 2026-10-31

Implemented targeted changes; no UI theme, authentication, role, batch, analytics, model weights, or tenant ownership changes.

## Root causes and corrections

- Uploaded metadata: the historical 2024 leave policy was registered as current/version 2026, under a separate family from the 2026 replacement. Other explicit document-control fields also conflicted with stored metadata. Corrected 15 Infosys records using the control blocks, including shared policy families and supersession links. The complete before/after rollback record is in `metadata-repair.json`. No filenames were used to infer authority; passages and original files remain unchanged.
- Retrieval: full question boilerplate and year tokens affected ranking; BM25 could admit generic keyword hits and administrative metadata. Search now fuses full-question/topic-term semantic matches, normalizes plural keyword terms, excludes control blocks from answer evidence, and filters weak lexical hits when stronger topical matches exist. MiniLM embedding identity and stored vectors are unchanged.
- Versions: comparison queries were rejected when they mentioned multiple years. Resolution now unions independently resolved versions and evidence selection reserves relevant passages across resolved versions. Current selection still requires explicit current status; genuine authority conflicts remain excluded.
- Classification: any diagnostic or dropped draft claim used to force partial coverage. Coverage now follows the independent verifier over citation-validated claims and the original question. Empty/invalid/out-of-range support still abstains; partial requested-fact coverage remains partial.
- Citations: strict database/tenant/retrieved-ID and exact normalized quote checks remain. Added document-ID consistency, blank-quote rejection and reason-coded logs. A policy year may be supported by matching authoritative version metadata only when used as a temporal/version label; numerical quantities still need quoted support. All claims also require semantic verification.
- Employee output: detailed diagnostics are logged. Employee warnings are actionable. Broad rules requests produce a selected, cited overview and invite a narrower question.
- Source panel: a new pending/failed/uncovered question cannot inherit older references. Explicit older-response selection persists when another response arrives. No theme changes.

## Live existing-document results

Real cached MiniLM + persistent Chroma + configured Gemini generation and verification; no mocked answers. These are uploaded synthetic demo policies, not official Infosys employment terms.

| Company | Query | Result | Citations |
|---|---|---|---|
| infosys | How many medical leaves are allowed in 2026? | answered | 1 |
| infosys | medical leaves | answered | 3 |
| infosys | What was the medical leave allowance in 2024? | answered | 1 |
| infosys | Compare the 2024 and 2026 medical leave policies. | answered | 2 |
| infosys | What are the company's workplace rules? | answered | 3 |
| infosys | Does the company provide unlimited international vacations? | not_covered | 0 |
| tcs | How many medical leaves are allowed in 2026? | not_covered | 0 |
| tcs | medical leaves | not_covered | 0 |
| tcs | What was the medical leave allowance in 2024? | not_covered | 0 |
| tcs | Compare the 2024 and 2026 medical leave policies. | not_covered | 0 |
| tcs | What are the company's workplace rules? | not_covered | 0 |
| tcs | Does the company provide unlimited international vacations? | not_covered | 0 |

Observed content: 2026 medical leave = 12 paid days/year; 2024 = 10; comparison cites both with no medical-leave carry-forward. Both current phrasings retrieve exactly the same two 2026 leave passages, with no IT, Operations, or Insurance evidence. Workplace overview cites device locking, confidential public calls, and respectful/non-retaliatory conduct. Unlimited international vacations abstains rather than inferring a benefit or prohibition.

Every returned citation belongs to the retrieved evidence and correct tenant; quotes were checked against the source passages. Gemini independently verified the returned claims. Two successful live runs agreed on the medical-leave amounts and classifications. This is a finite regression check, not a guarantee across all paraphrases.

TCS has zero uploaded documents in the current database: all six live queries returned NOT_COVERED with no citations. Both-populated-tenant isolation is separately covered by the automated Chroma and API fixtures; no Infosys document was assigned to TCS.

## Automated validation

- Backend: `python -m pytest tests -q -m "not integration" -o faulthandler_timeout=45`: **52 passed, 1 deselected**. Includes authentication, admin/employee permissions, batch processing, analytics and tenant isolation.
- Final citation change: `python -m pytest tests/test_rag_quality.py -q`: **8 passed**.
- Frontend: `node --test src/services/evidence.test.js`: **3 passed**.
- Frontend: `npm run build`: **passed**.
- The optional fresh-model integration test was not run. Live checks above used real cached MiniLM and existing Chroma data.

## Environment and remaining limits

- Restricted execution blocked outbound Gemini connections and Windows loopback socket initialization for TestClient. Running the authorized checks outside that restriction succeeded. Certificate verification was not disabled.
- Source-panel state selection is unit-tested and compiled; interactive browser rendering was not verified in this task.
- The unsupported vacation query still has low-relevance semantic candidates; the generation/verifier correctly returned no answer. No rule guarantees zero irrelevant candidates for arbitrary unsupported questions.
- The existing running backend must reload/restart to import Python changes if it is not using auto-reload. This task verified the changed service code directly and through TestClient; it did not restart the existing desktop server.

Artifacts: `live-results.json` contains actual answers, citations, retrieved passages, timings and diagnostics. `metadata-repair.json` contains exact previous metadata for rollback. `backend/scripts/check_rag_quality.py` reruns the twelve live cases without adding analytics events or changing documents.
