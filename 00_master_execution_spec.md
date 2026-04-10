# Canonical Execution Spec (Condensed for Session 5)

## System objective
Build a PostgreSQL/pgvector-centered L9 combat engine plus B-side hybrid retrieval stack with:
- fixed 1024 atomic abilities
- 32/128/1024 layered vectors
- four agents: ingestion, battlefield, x-rag, oracle judge
- ledger -> snapshot -> vector publish separation
- layered recall -> sparse sidecar -> RRF -> rerank

## Mandatory corrections
1. X-RAG must never trigger on every diff. Use checkpoint / error-log / idle-window / test-state-change only.
2. 1024-d vectors cannot be treated as naive all-zero sparse truth. Use smoothing or masking.
3. Coarse recall must return only light id/score data. Heavy payload fetch is allowed only after RRF shortlist.
4. Persisted assessment lifecycle states must remain:
   - PROVISIONING
   - COMBAT_ACTIVE
   - EVALUATING
   - CERTIFIED
   - FAILED

## Agent boundaries
- Ingestion: resume -> candidate_dna only
- Battlefield: candidate_dna -> battlefield_blueprint only
- X-RAG: evidence-governed injections / follow-ups only
- Oracle Judge: scoped scoring only, no out-of-schema abilities

## Search route
1. query parser
2. filter gate
3. L1 vec32 recall
4. L2 vec128 recall
5. L3 vec1024 recall
6. sparse sidecar recall
7. RRF fusion
8. rerank on shortlisted payloads

## Data discipline
- Scores are for explanation.
- Vectors are for recall.
- Reports are for display.
- Do not collapse them into one asset.
