# Session 5 Search Pipeline Notes

## authoritative inputs checklist

The implementation follows the authoritative inputs declared by `SESSION5_HANDOFF_MANIFEST.md` and resolves conflicts with the priority order required by the manifest:

1. `SESSION5_HANDOFF_MANIFEST.md`
2. `docs/00_master_execution_spec.md`
3. `docs/01_shared_contracts.md`
4. `docs/02_agent_workflow_fsm.md`
5. `docs/03_data_model_notes.md`
6. `schemas/judge_result.schema.json`
7. `schemas/geek_cert_report.schema.json`
8. `sql/001_core_tables.sql`
9. `workflow/orchestrator_flow.py`
10. `prompts/ingestion_agent.system.md`
11. `prompts/battlefield_agent.system.md`
12. `prompts/xrag_agent.system.md`
13. `prompts/oracle_judge_agent.system.md`

## explicit conflict corrections

### 1. persisted lifecycle states
`workflow/orchestrator_flow.py` introduces internal runtime stages such as `INGESTING` and `XRAG_MONITORING`, but the manifest explicitly says these must not become the persisted top-level assessment lifecycle states. The implementation therefore keeps the authoritative persisted lifecycle enum unchanged:

- `PROVISIONING`
- `COMBAT_ACTIVE`
- `EVALUATING`
- `CERTIFIED`
- `FAILED`

Reason: this is required by both the manifest and `docs/00_master_execution_spec.md`.

### 2. Session 4 SQL and schema names win over looser legacy naming
The mock pipeline uses stable snake_case names such as:

- `target_vec_32`
- `target_vec_128`
- `target_vec_1024`
- `ability_vec_32`
- `ability_vec_128`
- `ability_vec_1024`
- `score_32`
- `score_128`
- `score_1024`
- `score_sparse`
- `score_rrf`
- `score_rerank`
- `final_score`

Reason: the manifest explicitly prefers Session 4 schemas and SQL, and `docs/01_shared_contracts.md` locks these field names.

### 3. sparse recall demoted to sidecar
Some earlier design text discusses dense+sparse dual-track recall, but the authoritative route for Session 5 is the layered path from the manifest and `docs/03_data_model_notes.md`:

`filter -> vec32 -> vec128 -> vec1024 -> sparse sidecar -> RRF -> rerank`

Reason: Session 5 must obey layered recall, and sparse can only补漏, not dominate final ordering.

## why use 32 -> 128 -> 1024 layering

### 1. 32-dimensional recall is the cheapest direction-level gate
The 32 layer answers the coarse question: is this candidate even in the right technical direction? It is intentionally broad and inexpensive, so the pipeline can cheaply shrink the search space to a Top 200 light candidate set.

### 2. 128-dimensional recall removes family-level structural mismatch
Candidates can match the broad direction but still be wrong in ability-family shape. The 128 layer is used on top of the 32 shortlist to remove those false positives and keep only the Top 80 whose skill-family distribution still fits the query.

### 3. 1024-dimensional recall is reserved for late precision
The 1024 layer is the most precise but also the most fragile and expensive. It should never be the first full-pool recall stage. By applying it only to the 128 shortlist, the pipeline gets atomic-level precision without paying full-pool latency or sparse-high-dimensional instability costs.

## why sparse is a sidecar

Sparse recall is useful for补漏 because verified labels such as `Golang` or `Redis` can rescue candidates that dense vectors under-rank. But it must stay secondary for three reasons:

1. verified skills are text assets, not the internal primary ability axis;
2. sparse matching is noisy and can over-reward keyword stuffing;
3. the master spec explicitly forbids sparse from dominating final ranking.

The implementation enforces this by:

- running sparse after the three dense layers;
- excluding already-dense L3 hits from sparse sidecar recall by default;
- using a smaller RRF weight for sparse than the combined dense path;
- preserving dense-support influence in final rerank scoring.

## why only light results are returned before RRF

The coarse ranking stages return only lightweight rows:

- `candidate_id`
- light candidate metadata
- layer-specific score
- matched lightweight hints

They do **not** pull:

- full report JSON
- full battle logs
- heavy `reranker_payload`
- large evidence text blobs

This directly follows the authoritative rule from `docs/00_master_execution_spec.md` and `docs/03_data_model_notes.md`: heavy payload fetch is allowed only after RRF shortlist creation. The point is to avoid unnecessary memory growth, RPC traffic, and tail-latency spikes.

## how the RRF weights are designed

The implementation uses hand-written weighted reciprocal rank fusion with:

- `vec32`: `0.15`
- `vec128`: `0.25`
- `vec1024`: `0.40`
- `sparse_sidecar`: `0.20`
- `k = 60`

The intent is:

1. `vec32` contributes early directional evidence but has the lowest authority;
2. `vec128` matters more because family shape is a stronger signal;
3. `vec1024` gets the highest weight because atomic fit is the last dense precision gate;
4. `sparse_sidecar` remains meaningful enough to补漏 but not strong enough to become the main ordering path by itself.

The code implements RRF manually rather than using a black-box dependency, which satisfies the Session 5 hard requirement.

## exact rerank attachment point

Rerank is mounted **after** RRF and **only** on the RRF shortlist. The sequence is:

1. filter gate
2. L1 vec32 recall
3. L2 vec128 recall
4. L3 vec1024 recall
5. sparse sidecar recall
6. hand-written RRF fusion
7. fetch shortlisted `reranker_payload`
8. mock cross-encoder style rerank

This placement matters because rerank needs heavy payload text, and heavy payload fetch is disallowed in coarse recall. Attaching rerank earlier would violate the authoritative data-discipline rules.

## how the implementation avoids OOM and latency blow-ups

### 1. coarse stages use only light rows
All coarse stages return ids, compact metadata, and per-stage scores only.

### 2. recall limits are fixed by stage
The pipeline applies strict caps:

- L1 Top 200
- L2 Top 80
- L3 Top 40
- sparse sidecar Top 40
- rerank shortlist Top N

### 3. payload fetch is whitelist-only
The heavy payload fetch API accepts only the RRF shortlist candidate ids.

### 4. sparse recall is bounded and residual
Sparse sidecar recall runs on a bounded set and excludes already-selected dense hits by default, so it supplements recall instead of doubling full-stage memory pressure.

### 5. vectors are published assets, not reconstructed on every call
The mock data models the authoritative separation from SQL notes:

`ledger -> snapshot -> candidate_vectors`

That keeps retrieval time focused on similarity scoring rather than ad hoc recomputation.

## mock-specific implementation notes

This Session 5 delivery is intentionally mock-only:

- no real PostgreSQL connection;
- no real Supabase RPC;
- no real cross-encoder model;
- all candidate vectors, verified skills, and payloads are generated programmatically.

The mock still follows the authoritative naming and routing constraints so the code can be replaced later with real RPCs without changing the top-level pipeline contract.
