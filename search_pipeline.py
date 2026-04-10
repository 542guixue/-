from __future__ import annotations

"""Layered hybrid retrieval pipeline for Session 5.

Mandatory discipline implemented here:
- filter gate first
- L1 32-d recall -> top 200 light rows
- L2 128-d recall -> top 80 light rows
- L3 1024-d recall -> top 40 light rows
- sparse recall is sidecar补漏, not the dominant ranking path
- hand-written reciprocal rank fusion
- reranker payload fetch happens only after RRF shortlist creation
- no real database access; all storage calls go through mock RPC
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import re
import uuid
from typing import Any, Mapping, Sequence

from app.mock_data import (
    DEFAULT_TRACE_ID,
    DEFAULT_VERSION,
    SPECIAL_ABILITY_BY_ID,
    build_search_alias_map,
    project_target_vectors_from_weights,
)
from app.mock_rpc import MockRpcClient

RRF_K = 60
L1_LIMIT = 200
L2_LIMIT = 80
L3_LIMIT = 40
SPARSE_LIMIT = 40
DEFAULT_RERANK_TOP_N = 12
DEFAULT_TOP_K = 3
STAGE_WEIGHTS: dict[str, float] = {
    "vec32": 0.15,
    "vec128": 0.25,
    "vec1024": 0.40,
    "sparse_sidecar": 0.20,
}


class SearchPipelineError(RuntimeError):
    def __init__(
        self,
        error_code: str,
        error_message: str,
        error_stage: str,
        is_retryable: bool = False,
        retry_after_seconds: int = 0,
        trace_id: str = DEFAULT_TRACE_ID,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.error_code = error_code
        self.error_message = error_message
        self.error_stage = error_stage
        self.is_retryable = is_retryable
        self.retry_after_seconds = retry_after_seconds
        self.trace_id = trace_id
        self.details = dict(details or {})
        super().__init__(error_message)

    def to_error_object(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "error_message": self.error_message,
            "error_stage": self.error_stage,
            "is_retryable": self.is_retryable,
            "retry_after_seconds": self.retry_after_seconds,
            "trace_id": self.trace_id,
            "details": self.details,
        }


@dataclass(frozen=True)
class QueryParseResult:
    requirement_profile_id: str
    query_text: str
    query_text_clean: str
    extracted_tags: list[str]
    must_have_abilities: list[str]
    nice_to_have_abilities: list[str]
    ability_weights: dict[str, float]
    llm_parse_payload: dict[str, Any]
    target_vec_32: list[float]
    target_vec_128: list[float]
    target_vec_1024: list[float]
    trace_id: str
    version: str

    def to_requirement_profile(self) -> dict[str, Any]:
        return {
            "requirement_profile_id": self.requirement_profile_id,
            "query_text": self.query_text,
            "query_text_clean": self.query_text_clean,
            "extracted_tags": self.extracted_tags,
            "must_have_abilities": self.must_have_abilities,
            "nice_to_have_abilities": self.nice_to_have_abilities,
            "ability_weights": self.ability_weights,
            "llm_parse_payload": self.llm_parse_payload,
            "target_vec_32": self.target_vec_32,
            "target_vec_128": self.target_vec_128,
            "target_vec_1024": self.target_vec_1024,
            "trace_id": self.trace_id,
            "version": self.version,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_query_text(query_text: str) -> str:
    if not isinstance(query_text, str):
        raise TypeError("query_text must be a string")
    lowered = query_text.strip().lower()
    if not lowered:
        return ""
    lowered = re.sub(r"[\|,;:/()\[\]{}]+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered


def _human_readable_tag(ability_id: str) -> str:
    spec = SPECIAL_ABILITY_BY_ID.get(ability_id)
    if spec is None:
        return ability_id
    return spec.verified_skill_label


def parse_hr_query(
    query_text: str,
    trace_id: str | None = None,
    version: str = DEFAULT_VERSION,
) -> QueryParseResult:
    """Parse the HR query into tags, weighted abilities, and layered target vectors."""
    cleaned = normalize_query_text(query_text)
    trace = trace_id or DEFAULT_TRACE_ID
    if not cleaned:
        raise SearchPipelineError(
            error_code="query_parse_failed",
            error_message="query_text is empty after normalization",
            error_stage="query_parser",
            trace_id=trace,
        )

    matched_ability_ids: list[str] = []
    matched_aliases: list[str] = []
    for alias, ability_ids in build_search_alias_map().items():
        if alias in cleaned:
            matched_aliases.append(alias)
            matched_ability_ids.extend(ability_ids)

    if not matched_ability_ids:
        # Fallback to a broad backend search intent so the pipeline still returns
        # deterministic results without inventing foreign field names.
        matched_ability_ids = ["ability_0001", "ability_0018"]
        matched_aliases = ["backend", "architecture"]

    # Keep first-seen order but deduplicate.
    deduped_ability_ids: list[str] = []
    seen_ability_ids: set[str] = set()
    for ability_id in matched_ability_ids:
        if ability_id not in seen_ability_ids:
            deduped_ability_ids.append(ability_id)
            seen_ability_ids.add(ability_id)

    extracted_tags = []
    seen_tags: set[str] = set()
    for ability_id in deduped_ability_ids:
        tag = _human_readable_tag(ability_id)
        if tag not in seen_tags:
            extracted_tags.append(tag)
            seen_tags.add(tag)

    must_have_abilities: list[str] = []
    nice_to_have_abilities: list[str] = []
    ability_weights: dict[str, float] = {}
    for ability_id in deduped_ability_ids:
        spec = SPECIAL_ABILITY_BY_ID.get(ability_id)
        if spec is None:
            continue
        weight = spec.default_weight
        if spec.is_hard_skill:
            must_have_abilities.append(ability_id)
            weight += 0.15
        else:
            nice_to_have_abilities.append(ability_id)
        ability_weights[ability_id] = min(1.0, round(weight, 4))

    target_vec_32, target_vec_128, target_vec_1024 = project_target_vectors_from_weights(ability_weights)
    requirement_profile_id = f"req_{uuid.uuid4().hex[:12]}"
    llm_parse_payload = {
        "recognized_aliases": matched_aliases,
        "recognized_ability_ids": deduped_ability_ids,
        "must_have_count": len(must_have_abilities),
        "nice_to_have_count": len(nice_to_have_abilities),
    }

    return QueryParseResult(
        requirement_profile_id=requirement_profile_id,
        query_text=query_text,
        query_text_clean=cleaned,
        extracted_tags=extracted_tags,
        must_have_abilities=must_have_abilities,
        nice_to_have_abilities=nice_to_have_abilities,
        ability_weights=ability_weights,
        llm_parse_payload=llm_parse_payload,
        target_vec_32=target_vec_32,
        target_vec_128=target_vec_128,
        target_vec_1024=target_vec_1024,
        trace_id=trace,
        version=version,
    )


def reciprocal_rank_fusion(
    *,
    stage_results: Mapping[str, Sequence[Mapping[str, Any]]],
    stage_weights: Mapping[str, float] | None = None,
    k: int = RRF_K,
) -> list[dict[str, Any]]:
    """Hand-written weighted reciprocal rank fusion.

    The implementation is intentionally explicit and does not depend on a black
    box library. Only light-stage rows are consumed here.
    """
    if k <= 0:
        raise ValueError("k must be positive")

    weights = dict(stage_weights or STAGE_WEIGHTS)
    fused: dict[str, dict[str, Any]] = {}
    stage_to_score_field = {
        "vec32": "score_32",
        "vec128": "score_128",
        "vec1024": "score_1024",
        "sparse_sidecar": "score_sparse",
    }

    for stage_name, rows in stage_results.items():
        score_field = stage_to_score_field.get(stage_name)
        if score_field is None:
            raise ValueError(f"unsupported stage_name: {stage_name}")
        stage_weight = float(weights.get(stage_name, 0.0))
        for rank_position, row in enumerate(rows, start=1):
            candidate_id = str(row["candidate_id"])
            bucket = fused.setdefault(
                candidate_id,
                {
                    "candidate_id": candidate_id,
                    "display_name": row.get("display_name", ""),
                    "city": row.get("city", ""),
                    "years_experience": row.get("years_experience", 0.0),
                    "score_32": None,
                    "score_128": None,
                    "score_1024": None,
                    "score_sparse": None,
                    "score_rrf": 0.0,
                    "matched_ability_ids": set(),
                    "matched_verified_skills": set(),
                    "stage_rank_positions": {},
                },
            )
            bucket[score_field] = row.get(score_field)
            bucket["score_rrf"] += stage_weight / (k + rank_position)
            bucket["stage_rank_positions"][stage_name] = rank_position
            bucket["matched_ability_ids"].update(row.get("matched_ability_ids", []))
            bucket["matched_verified_skills"].update(row.get("matched_verified_skills", []))

    fused_rows: list[dict[str, Any]] = []
    for row in fused.values():
        row["matched_ability_ids"] = sorted(row["matched_ability_ids"])
        row["matched_verified_skills"] = sorted(row["matched_verified_skills"])
        fused_rows.append(row)

    fused_rows.sort(
        key=lambda row: (
            -float(row["score_rrf"]),
            -(float(row["score_1024"] or 0.0)),
            -(float(row["score_128"] or 0.0)),
            -(float(row["score_32"] or 0.0)),
            -(float(row["score_sparse"] or 0.0)),
            row["candidate_id"],
        )
    )
    return fused_rows


def _tokenize_for_rerank(text: str) -> set[str]:
    lowered = normalize_query_text(text)
    return {token for token in lowered.split() if len(token) >= 2}


def _compute_rerank_score(
    requirement_profile: Mapping[str, Any],
    fused_row: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> tuple[float, dict[str, Any]]:
    target_must = set(requirement_profile["must_have_abilities"])
    target_nice = set(requirement_profile["nice_to_have_abilities"])
    active_ids = set(payload["support_profile"]["verified_ability_ids"])

    must_hits = sorted(active_ids & target_must)
    missing_must = sorted(target_must - active_ids)
    nice_hits = sorted(active_ids & target_nice)
    verified_skills = {skill.lower() for skill in payload["verified_skills"]}
    query_terms = _tokenize_for_rerank(requirement_profile["query_text_clean"]) | {
        tag.lower() for tag in requirement_profile["extracted_tags"]
    }
    payload_terms = _tokenize_for_rerank(payload["reranker_payload"])
    lexical_overlap = len((verified_skills | payload_terms) & query_terms) / max(1, len(query_terms))

    must_score = len(must_hits) / max(1, len(target_must)) if target_must else lexical_overlap
    nice_score = len(nice_hits) / max(1, len(target_nice)) if target_nice else lexical_overlap
    experience_score = min(1.0, float(payload["years_experience"]) / 8.0)
    dense_stage_hits = sum(1 for key in ("score_32", "score_128", "score_1024") if fused_row.get(key) is not None)
    dense_support_ratio = dense_stage_hits / 3.0

    score_rerank = (
        0.40 * must_score
        + 0.20 * nice_score
        + 0.25 * lexical_overlap
        + 0.15 * experience_score
    )
    explanations = {
        "must_have_hits": must_hits,
        "missing_must_have_abilities": missing_must,
        "nice_to_have_hits": nice_hits,
        "matched_verified_skills": sorted(payload["verified_skills"]),
        "dense_stage_hits": dense_stage_hits,
        "payload_overlap_terms": sorted((verified_skills | payload_terms) & query_terms),
        "dense_support_ratio": round(dense_support_ratio, 4),
    }
    return round(score_rerank, 6), explanations


def rerank_fused_candidates(
    *,
    requirement_profile: Mapping[str, Any],
    fused_rows: Sequence[Mapping[str, Any]],
    rpc_client: MockRpcClient,
    rerank_top_n: int = DEFAULT_RERANK_TOP_N,
) -> list[dict[str, Any]]:
    if rerank_top_n <= 0:
        raise ValueError("rerank_top_n must be positive")
    shortlisted = list(fused_rows[:rerank_top_n])
    if not shortlisted:
        return []

    payloads = rpc_client.fetch_reranker_payloads([row["candidate_id"] for row in shortlisted])
    max_rrf = max(float(row["score_rrf"]) for row in shortlisted)
    reranked_rows: list[dict[str, Any]] = []

    for row in shortlisted:
        payload = payloads[row["candidate_id"]]
        score_rerank, explanations = _compute_rerank_score(requirement_profile, row, payload)
        dense_stage_hits = explanations["dense_stage_hits"]
        dense_support_ratio = explanations["dense_support_ratio"]
        normalized_rrf = float(row["score_rrf"]) / max_rrf if max_rrf > 0 else 0.0
        final_score = 0.35 * normalized_rrf + 0.45 * score_rerank + 0.20 * dense_support_ratio
        reranked_rows.append(
            {
                **row,
                "verified_skills": payload["verified_skills"],
                "reranker_payload": payload["reranker_payload"],
                "score_rerank": round(score_rerank, 6),
                "final_score": round(final_score, 6),
                "explanations": explanations,
                "dense_stage_hits": dense_stage_hits,
            }
        )

    reranked_rows.sort(
        key=lambda row: (
            -float(row["final_score"]),
            -int(row["dense_stage_hits"]),
            -float(row["score_rrf"]),
            row["candidate_id"],
        )
    )
    return reranked_rows


def run_search_pipeline(
    query_text: str,
    *,
    filters: Mapping[str, Any] | None = None,
    top_k: int = DEFAULT_TOP_K,
    rerank_top_n: int = DEFAULT_RERANK_TOP_N,
    rpc_client: MockRpcClient | None = None,
    trace_id: str | None = None,
    version: str = DEFAULT_VERSION,
) -> dict[str, Any]:
    if top_k <= 0:
        raise SearchPipelineError(
            error_code="invalid_input",
            error_message="top_k must be positive",
            error_stage="input_validation",
            trace_id=trace_id or DEFAULT_TRACE_ID,
        )

    client = rpc_client or MockRpcClient()
    session_trace_id = trace_id or f"trace_{uuid.uuid4().hex}"
    requirement_profile = parse_hr_query(
        query_text=query_text,
        trace_id=session_trace_id,
        version=version,
    ).to_requirement_profile()
    search_session_id = f"search_{uuid.uuid4().hex[:12]}"
    created_at = _utc_now()

    try:
        filtered_candidate_ids = client.filter_candidates(filters)
        l1_rows = client.search_candidates_by_vec32(
            requirement_profile,
            filtered_candidate_ids,
            limit=L1_LIMIT,
        )
        l2_rows = client.search_candidates_by_vec128(
            requirement_profile,
            [row["candidate_id"] for row in l1_rows],
            limit=L2_LIMIT,
        )
        l3_rows = client.search_candidates_by_vec1024(
            requirement_profile,
            [row["candidate_id"] for row in l2_rows],
            limit=L3_LIMIT,
        )
        sparse_rows = client.search_candidates_by_sparse_sidecar(
            requirement_profile,
            filtered_candidate_ids,
            exclude_candidate_ids=[row["candidate_id"] for row in l3_rows],
            limit=SPARSE_LIMIT,
        )

        fused_rows = reciprocal_rank_fusion(
            stage_results={
                "vec32": l1_rows,
                "vec128": l2_rows,
                "vec1024": l3_rows,
                "sparse_sidecar": sparse_rows,
            },
            stage_weights=STAGE_WEIGHTS,
            k=RRF_K,
        )
        reranked_rows = rerank_fused_candidates(
            requirement_profile=requirement_profile,
            fused_rows=fused_rows,
            rpc_client=client,
            rerank_top_n=rerank_top_n,
        )
        result_rows = reranked_rows[:top_k]
        light_candidates = client.get_light_candidates([row["candidate_id"] for row in result_rows])

        results: list[dict[str, Any]] = []
        for rank_position, row in enumerate(result_rows, start=1):
            light_candidate = light_candidates[row["candidate_id"]]
            results.append(
                {
                    "candidate_id": row["candidate_id"],
                    "display_name": light_candidate["display_name"],
                    "city": light_candidate["city"],
                    "years_experience": light_candidate["years_experience"],
                    "score_32": row.get("score_32"),
                    "score_128": row.get("score_128"),
                    "score_1024": row.get("score_1024"),
                    "score_sparse": row.get("score_sparse"),
                    "score_rrf": round(float(row["score_rrf"]), 6),
                    "score_rerank": row["score_rerank"],
                    "final_score": row["final_score"],
                    "rank_position": rank_position,
                    "verified_skills": row["verified_skills"],
                    "explanations": row["explanations"],
                }
            )

        status = "COMPLETED"
        return {
            "search_session_id": search_session_id,
            "requirement_profile_id": requirement_profile["requirement_profile_id"],
            "query_text": requirement_profile["query_text"],
            "query_text_clean": requirement_profile["query_text_clean"],
            "extracted_tags": requirement_profile["extracted_tags"],
            "must_have_abilities": requirement_profile["must_have_abilities"],
            "nice_to_have_abilities": requirement_profile["nice_to_have_abilities"],
            "ability_weights": requirement_profile["ability_weights"],
            "filters": dict(filters or {}),
            "mode": "layered_hybrid",
            "status": status,
            "rerank_model": "mock_cross_encoder",
            "trace_id": session_trace_id,
            "version": version,
            "created_at": created_at,
            "recall_plan": {
                "l1_limit": L1_LIMIT,
                "l2_limit": L2_LIMIT,
                "l3_limit": L3_LIMIT,
                "sparse_limit": SPARSE_LIMIT,
                "rerank_top_n": rerank_top_n,
                "rrf_k": RRF_K,
                "stage_weights": STAGE_WEIGHTS,
                "stage_counts": {
                    "filtered": len(filtered_candidate_ids),
                    "vec32": len(l1_rows),
                    "vec128": len(l2_rows),
                    "vec1024": len(l3_rows),
                    "sparse_sidecar": len(sparse_rows),
                    "fused": len(fused_rows),
                },
                "payload_fetch_count": client.audit.payload_fetch_count,
                "payload_fetch_candidate_ids": list(client.audit.payload_fetch_candidate_ids),
                "call_order": list(client.audit.call_order),
            },
            "results": results,
        }
    except SearchPipelineError:
        raise
    except Exception as exc:  # pragma: no cover - defensive wrapper
        raise SearchPipelineError(
            error_code="recall_stage_failed",
            error_message=str(exc),
            error_stage="search_pipeline",
            trace_id=session_trace_id,
            is_retryable=False,
        ) from exc
