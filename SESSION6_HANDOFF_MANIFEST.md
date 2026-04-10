# Session 6 Handoff Manifest

## Goal
Assemble the final repo package using the authoritative outputs from Sessions 1-5. Session 6 is a packaging and integration pass, not a redesign pass.

## Authoritative inputs

### Keep from Session 1
- `docs/00_master_execution_spec.md`
- `docs/01_shared_contracts.md`

Reason: these files define the top-level execution rules, naming contracts, lifecycle boundaries, and anti-patterns.

### Keep from Session 2
- `prompts/ingestion_agent.system.md`
- `prompts/battlefield_agent.system.md`
- `prompts/xrag_agent.system.md`
- `prompts/oracle_judge_agent.system.md`

Reason: these are the strongest system prompts and remain the authoritative prompt source.

### Keep from Session 3/4 curated set
- `docs/02_agent_workflow_fsm.md`
- `docs/03_data_model_notes.md`
- `workflow/orchestrator_flow.py`
- `schemas/judge_result.schema.json`
- `schemas/geek_cert_report.schema.json`
- `sql/001_core_tables.sql`

Reason: these are already conflict-resolved and aligned to the execution spec.

### Keep from Session 5
- `app/search_pipeline.py`
- `app/mock_rpc.py`
- `app/mock_data.py`
- `tests/test_rrf.py`
- `tests/test_search_pipeline.py`
- `docs/04_search_pipeline_notes.md`

Reason: Session 5 produced a working layered retrieval mock implementation and its tests pass.

## Verified health check
- Session 5 delivered all 6 required files.
- Session 5 test suite passed: `5 passed`.
- `search_pipeline.py` obeys layered recall, sparse sidecar discipline, hand-written RRF, and delayed payload fetch.

## Conflict resolution rules
1. Do not rename any core fields locked by `docs/01_shared_contracts.md`.
2. Persisted top-level assessment lifecycle states remain exactly:
   - `PROVISIONING`
   - `COMBAT_ACTIVE`
   - `EVALUATING`
   - `CERTIFIED`
   - `FAILED`
3. Session 6 may reorganize presentation and packaging, but must not redesign SQL, schemas, or the pipeline contract.
4. If an example JSON is generated, it must validate against the provided schemas or be clearly marked as illustrative if schema validation is not possible in-session.
5. `README.md`, `docs/05_repo_walkthrough.md`, `examples/*`, `run_demo.sh`, and `tree.txt` are new deliverables created by Session 6.

## Known cautions for Session 6
1. Session 5 uses mock-only assets; document this clearly in the README.
2. `prompt_output_contracts.json` was never recovered from Session 2; do not pretend it exists.
3. `sql/001_core_tables.sql` is the curated authoritative SQL input for packaging; do not invent extra migration files unless absolutely necessary for explanation.
4. Session 5 notes mention authoritative inputs including the Session 5 manifest; keep that context but do not over-emphasize the packaging history in the final README.

## What Session 6 must output
- `README.md`
- `docs/05_repo_walkthrough.md`
- `examples/sample_hr_query.json`
- `examples/sample_judge_result.json`
- `examples/sample_geek_cert_report.json`
- `run_demo.sh`
- `tree.txt`

## Packaging objective
Produce a polished GitHub-style final handoff that makes the architecture understandable in this order:
1. what problem is being solved
2. which PRD flaws were corrected
3. how prompts, schemas, SQL, and pipeline connect
4. how to run the mock search demo
5. why the design shows architecture judgment instead of PRD copy-paste
