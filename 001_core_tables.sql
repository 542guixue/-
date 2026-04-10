-- 001_core_tables.sql
-- Supabase PostgreSQL 15+ / pgvector
-- 核心原则：
-- 1) taxonomy 统一主轴
-- 2) ledger / snapshot / vector publish 分层
-- 3) 三层向量单独发布，不回写基础表作为唯一事实
-- 4) HNSW 用于 candidate_vectors / requirement_profiles
-- 5) 重做 assessment 依赖 contribution versioning

create extension if not exists vector;
create extension if not exists pgcrypto;

-- ---------------------------------------
-- ability taxonomy
-- ---------------------------------------

create table if not exists public.ability_taxonomy_nodes (
    id uuid primary key default gen_random_uuid(),
    ability_code text not null unique,
    ability_name text not null,
    layer smallint not null check (layer in (32, 128, 1024)),
    parent_id uuid null references public.ability_taxonomy_nodes(id) on delete restrict,
    vector_index integer not null check (
        (layer = 32 and vector_index between 0 and 31) or
        (layer = 128 and vector_index between 0 and 127) or
        (layer = 1024 and vector_index between 0 and 1023)
    ),
    status text not null default 'ACTIVE' check (status in ('ACTIVE', 'DEPRECATED', 'DISABLED')),
    metadata jsonb not null default '{}'::jsonb,
    trace_id text not null default 'taxonomy.bootstrap',
    version text not null default 'taxonomy.v1',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (layer, vector_index)
);

create index if not exists idx_ability_taxonomy_nodes_layer on public.ability_taxonomy_nodes(layer);
create index if not exists idx_ability_taxonomy_nodes_parent_id on public.ability_taxonomy_nodes(parent_id);
create index if not exists idx_ability_taxonomy_nodes_metadata_gin on public.ability_taxonomy_nodes using gin (metadata);

create table if not exists public.ability_taxonomy_edges (
    parent_id uuid not null references public.ability_taxonomy_nodes(id) on delete cascade,
    child_id uuid not null references public.ability_taxonomy_nodes(id) on delete cascade,
    weight numeric(6,5) not null check (weight >= 0 and weight <= 1),
    rollup_mode text not null default 'weighted_mean' check (rollup_mode in ('weighted_mean', 'max', 'masked_mean')),
    trace_id text not null default 'taxonomy.bootstrap',
    version text not null default 'taxonomy.v1',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (parent_id, child_id),
    check (parent_id <> child_id)
);

create index if not exists idx_ability_taxonomy_edges_child on public.ability_taxonomy_edges(child_id);

-- ---------------------------------------
-- role schema
-- ---------------------------------------

create table if not exists public.role_schemas (
    id uuid primary key default gen_random_uuid(),
    role_code text not null unique,
    role_name text not null,
    mode text not null check (mode in ('sandbox', 'interview_prd')),
    ability_scope jsonb not null default '[]'::jsonb,
    blueprint_template jsonb not null default '{}'::jsonb,
    status text not null default 'ACTIVE' check (status in ('ACTIVE', 'DISABLED')),
    trace_id text not null,
    version text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (jsonb_typeof(ability_scope) = 'array')
);

create index if not exists idx_role_schemas_ability_scope_gin on public.role_schemas using gin (ability_scope);
create index if not exists idx_role_schemas_blueprint_template_gin on public.role_schemas using gin (blueprint_template);

-- ---------------------------------------
-- assessment + question ledger
-- ---------------------------------------

create table if not exists public.assessments (
    id uuid primary key default gen_random_uuid(),
    candidate_id uuid not null,
    role_schema_id uuid not null references public.role_schemas(id) on delete restrict,
    status text not null check (status in ('PROVISIONING', 'COMBAT_ACTIVE', 'EVALUATING', 'CERTIFIED', 'FAILED')),
    mode text not null check (mode in ('sandbox', 'interview_prd')),
    runtime_policy jsonb not null default '{}'::jsonb,
    trace_id text not null,
    version text not null,
    started_at timestamptz,
    ended_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_assessments_candidate_role on public.assessments(candidate_id, role_schema_id);
create index if not exists idx_assessments_status on public.assessments(status);

create table if not exists public.assessment_question_instances (
    id uuid primary key default gen_random_uuid(),
    assessment_id uuid not null references public.assessments(id) on delete cascade,
    source_question_bank_id uuid null,
    question_type text not null check (question_type in ('coding', 'debugging', 'architecture', 'prd', 'incident_response')),
    round_no integer not null check (round_no >= 1),
    difficulty_level numeric(4,2) not null check (difficulty_level >= 0 and difficulty_level <= 10),
    generation_prompt_version text not null,
    question_payload jsonb not null default '{}'::jsonb,
    status text not null check (status in ('PENDING', 'ISSUED', 'ANSWERED', 'EVALUATED', 'INVALIDATED')),
    trace_id text not null,
    version text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_assessment_question_instances_assessment on public.assessment_question_instances(assessment_id, round_no);
create index if not exists idx_assessment_question_instances_payload_gin on public.assessment_question_instances using gin (question_payload);

create table if not exists public.question_ability_bindings (
    question_instance_id uuid not null references public.assessment_question_instances(id) on delete cascade,
    ability_id uuid not null references public.ability_taxonomy_nodes(id) on delete restrict,
    layer smallint not null default 1024 check (layer in (32, 128, 1024)),
    weight numeric(6,5) not null check (weight >= 0 and weight <= 1),
    binding_source text not null check (binding_source in ('llm_generated', 'rule_mapped', 'human_reviewed')),
    confidence numeric(6,5) not null check (confidence >= 0 and confidence <= 1),
    trace_id text not null,
    version text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (question_instance_id, ability_id)
);

create index if not exists idx_question_ability_bindings_ability on public.question_ability_bindings(ability_id);

create table if not exists public.question_ability_scores (
    id uuid primary key default gen_random_uuid(),
    question_instance_id uuid not null references public.assessment_question_instances(id) on delete cascade,
    assessment_id uuid not null references public.assessments(id) on delete cascade,
    candidate_id uuid not null,
    ability_id uuid not null references public.ability_taxonomy_nodes(id) on delete restrict,
    raw_score numeric(5,2) not null check (raw_score >= 0 and raw_score <= 100),
    normalized_score numeric(6,5) not null check (normalized_score >= 0 and normalized_score <= 1),
    weight numeric(6,5) not null check (weight >= 0 and weight <= 1),
    contribution_score numeric(8,5) not null check (contribution_score >= 0),
    score_source text not null check (score_source in ('ai_grader', 'objective_rule', 'human_override')),
    grader_version text not null,
    evidence jsonb not null default '{}'::jsonb,
    trace_id text not null,
    version text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_question_ability_scores_candidate_assessment on public.question_ability_scores(candidate_id, assessment_id);
create index if not exists idx_question_ability_scores_ability on public.question_ability_scores(ability_id);
create index if not exists idx_question_ability_scores_evidence_gin on public.question_ability_scores using gin (evidence);

create table if not exists public.assessment_ability_aggregates (
    assessment_id uuid not null references public.assessments(id) on delete cascade,
    candidate_id uuid not null,
    ability_id uuid not null references public.ability_taxonomy_nodes(id) on delete restrict,
    layer smallint not null check (layer in (32, 128, 1024)),
    aggregation_mode text not null default 'weighted_mean' check (aggregation_mode in ('weighted_mean', 'ema', 'masked_mean')),
    score numeric(6,5) not null check (score >= 0 and score <= 1),
    support_count integer not null default 0 check (support_count >= 0),
    support_weight numeric(8,5) not null default 0 check (support_weight >= 0),
    source_question_count integer not null default 0 check (source_question_count >= 0),
    recomputed_at timestamptz not null default now(),
    trace_id text not null,
    version text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (assessment_id, ability_id)
);

create index if not exists idx_assessment_ability_aggregates_candidate on public.assessment_ability_aggregates(candidate_id, layer, score desc);

create table if not exists public.candidate_ability_contributions (
    candidate_id uuid not null,
    assessment_id uuid not null references public.assessments(id) on delete cascade,
    ability_id uuid not null references public.ability_taxonomy_nodes(id) on delete restrict,
    layer smallint not null check (layer in (32, 128, 1024)),
    score numeric(6,5) not null check (score >= 0 and score <= 1),
    weight numeric(8,5) not null check (weight >= 0),
    version integer not null check (version >= 1),
    is_active boolean not null default true,
    status text not null default 'ACTIVE' check (status in ('ACTIVE', 'SUPERSEDED', 'DISCARDED')),
    trace_id text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (candidate_id, assessment_id, ability_id, version)
);

create index if not exists idx_candidate_ability_contributions_active on public.candidate_ability_contributions(candidate_id, ability_id, is_active);
create index if not exists idx_candidate_ability_contributions_assessment on public.candidate_ability_contributions(assessment_id, is_active);

create table if not exists public.candidate_ability_snapshots (
    candidate_id uuid not null,
    ability_id uuid not null references public.ability_taxonomy_nodes(id) on delete restrict,
    layer smallint not null check (layer in (32, 128, 1024)),
    score numeric(6,5) not null check (score >= 0 and score <= 1),
    aggregation_mode text not null default 'mean_of_assessments' check (aggregation_mode in ('mean_of_assessments', 'ema', 'decay_aware_mean')),
    assessment_count integer not null default 0 check (assessment_count >= 0),
    last_assessment_id uuid null references public.assessments(id) on delete set null,
    support_count integer not null default 0 check (support_count >= 0),
    support_weight numeric(8,5) not null default 0 check (support_weight >= 0),
    updated_at timestamptz not null default now(),
    trace_id text not null,
    version text not null,
    primary key (candidate_id, ability_id)
);

create index if not exists idx_candidate_ability_snapshots_layer_score on public.candidate_ability_snapshots(candidate_id, layer, score desc);

-- ---------------------------------------
-- vector publish
-- ---------------------------------------

create table if not exists public.candidate_vectors (
    candidate_id uuid primary key,
    ability_vec_32 vector(32) not null,
    ability_vec_128 vector(128) not null,
    ability_vec_1024 vector(1024) not null,
    vec_version text not null,
    support_profile jsonb not null default '{}'::jsonb,
    last_certified_at timestamptz,
    updated_at timestamptz not null default now(),
    trace_id text not null
);

create index if not exists idx_candidate_vectors_vec32_hnsw
    on public.candidate_vectors
    using hnsw (ability_vec_32 vector_cosine_ops)
    with (m = 16, ef_construction = 64);

create index if not exists idx_candidate_vectors_vec128_hnsw
    on public.candidate_vectors
    using hnsw (ability_vec_128 vector_cosine_ops)
    with (m = 16, ef_construction = 64);

create index if not exists idx_candidate_vectors_vec1024_hnsw
    on public.candidate_vectors
    using hnsw (ability_vec_1024 vector_cosine_ops)
    with (m = 16, ef_construction = 96);

create index if not exists idx_candidate_vectors_support_profile_gin on public.candidate_vectors using gin (support_profile);

-- ---------------------------------------
-- requirement profiles + search sessions
-- ---------------------------------------

create table if not exists public.job_requirement_profiles (
    id uuid primary key default gen_random_uuid(),
    job_id uuid null,
    query_text text not null,
    query_text_clean text not null,
    extracted_tags jsonb not null default '[]'::jsonb,
    must_have_abilities jsonb not null default '[]'::jsonb,
    nice_to_have_abilities jsonb not null default '[]'::jsonb,
    ability_weights jsonb not null default '{}'::jsonb,
    llm_parse_payload jsonb not null default '{}'::jsonb,
    target_vec_32 vector(32) not null,
    target_vec_128 vector(128) not null,
    target_vec_1024 vector(1024) not null,
    trace_id text not null,
    version text not null,
    created_by uuid null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (jsonb_typeof(extracted_tags) = 'array'),
    check (jsonb_typeof(must_have_abilities) = 'array'),
    check (jsonb_typeof(nice_to_have_abilities) = 'array'),
    check (jsonb_typeof(ability_weights) = 'object')
);

create index if not exists idx_job_requirement_profiles_vec32_hnsw
    on public.job_requirement_profiles
    using hnsw (target_vec_32 vector_cosine_ops)
    with (m = 16, ef_construction = 64);

create index if not exists idx_job_requirement_profiles_vec128_hnsw
    on public.job_requirement_profiles
    using hnsw (target_vec_128 vector_cosine_ops)
    with (m = 16, ef_construction = 64);

create index if not exists idx_job_requirement_profiles_vec1024_hnsw
    on public.job_requirement_profiles
    using hnsw (target_vec_1024 vector_cosine_ops)
    with (m = 16, ef_construction = 96);

create index if not exists idx_job_requirement_profiles_tags_gin on public.job_requirement_profiles using gin (extracted_tags);
create index if not exists idx_job_requirement_profiles_ability_weights_gin on public.job_requirement_profiles using gin (ability_weights);

create table if not exists public.search_sessions (
    id uuid primary key default gen_random_uuid(),
    requirement_profile_id uuid not null references public.job_requirement_profiles(id) on delete cascade,
    filters jsonb not null default '{}'::jsonb,
    mode text not null default 'layered_hybrid' check (mode in ('layered_hybrid')),
    recall_plan jsonb not null default '{}'::jsonb,
    rerank_model text not null default 'mock_cross_encoder',
    status text not null check (status in ('CREATED', 'FILTERED', 'RECALLING', 'FUSED', 'RERANKED', 'COMPLETED', 'FAILED')),
    trace_id text not null,
    version text not null,
    created_by uuid null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_search_sessions_requirement_profile on public.search_sessions(requirement_profile_id, status);

create table if not exists public.search_candidate_scores (
    search_session_id uuid not null references public.search_sessions(id) on delete cascade,
    candidate_id uuid not null,
    score_32 numeric(6,5) null,
    score_128 numeric(6,5) null,
    score_1024 numeric(6,5) null,
    score_sparse numeric(6,5) null,
    score_rrf numeric(6,5) null,
    score_rerank numeric(6,5) null,
    final_score numeric(6,5) null,
    rank_position integer null check (rank_position is null or rank_position >= 1),
    explanations jsonb not null default '{}'::jsonb,
    trace_id text not null,
    version text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (search_session_id, candidate_id)
);

create index if not exists idx_search_candidate_scores_final_score on public.search_candidate_scores(search_session_id, final_score desc);

-- ---------------------------------------
-- optional helper view for latest active contributions
-- ---------------------------------------

create or replace view public.v_candidate_active_contributions as
select
    candidate_id,
    assessment_id,
    ability_id,
    layer,
    score,
    weight,
    version,
    trace_id,
    created_at,
    updated_at
from public.candidate_ability_contributions
where is_active = true
  and status = 'ACTIVE';
