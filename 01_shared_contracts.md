# Shared Contracts (Condensed for Session 5)

## Naming
- use snake_case everywhere
- keep field names stable across JSON, SQL, and Python

## Stable identifiers
- candidate_id
- assessment_id
- ability_id
- requirement_profile_id
- search_session_id
- trace_id
- version
- schema_version

## Stable vector fields
- target_vec_32
- target_vec_128
- target_vec_1024
- ability_vec_32
- ability_vec_128
- ability_vec_1024

## Stable search score fields
- score_32
- score_128
- score_1024
- score_sparse
- score_rrf
- score_rerank
- final_score

## Stable judge fields
- vector_updates
- verified_skills
- reranker_payload
- combat_confidence
- score_coverage
- evidence_refs

## JSON law
- output pure JSON where a contract requires JSON
- no prose around JSON
- no field drift
- no camelCase

## Error object
- error_code
- error_message
- error_stage
- is_retryable
- retry_after_seconds
- trace_id
- details
